"""웹 API — 기존 CLI 교정 엔진을 그대로 재사용하는 FastAPI 서버.

PRD.md §4의 아키텍처 원칙("교정 로직은 CLI와 분리된 순수 라이브러리 모듈로 설계")을
그대로 활용한다. 여기서는 engine/parsers를 호출만 하고, 새 교정 로직은 추가하지 않는다.
"""

import io
import tempfile
from dataclasses import asdict
from urllib.parse import quote
from pathlib import Path

import requests
from fastapi import FastAPI, Form, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles

from . import store
from .file_io import SUPPORTED_EXTENSIONS, output_suffix, parse_file, write_file
from .dictionary import DIALECT_MARKERS
from .engine import (
    correct_entries,
    normalize_subtitle_markers,
    normalize_dialect_mode,
    normalize_spacing_mode,
    register_custom_words,
)
from .parsers import parse_docx, parse_plain_text, parse_srt, write_plain_text, write_srt

app = FastAPI(title="한국어 자막 교정 API")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_ALLOWED_EXTENSIONS = set(SUPPORTED_EXTENSIONS)
# 인증도 업로드 크기 제한도 없으면, 큰 파일 하나가 교정 엔진의 토큰 단위
# 실시간 사전 API 호출(표준국어대사전/우리말샘/kornorms)을 통해 공유 API 키
# 쿼터 자체를 고갈시킬 수 있다(§25 보안 검토, 2026-07-17) — 단순 메모리 DoS
# 보다 "핵심 기능 전체가 막힌다"는 점에서 더 실질적인 위험이라 크기 제한을
# 둔다.
_MAX_UPLOAD_BYTES = 1_000_000
# PDF만 예외로 크게 둔다. 위 제한의 목적은 **사전 조회 횟수**를 묶는 것인데, 그 횟수는
# 글자 수에 비례하지 파일 크기에 비례하지 않는다. PDF는 본문에 그림·도판이 함께 들어가
# 글이 얼마 없어도 파일이 커지므로(2026-08-02 실측: 두 줄짜리 그림 PDF가 1.4MB), 같은
# 잣대를 대면 정상적인 원고까지 막힌다.
_MAX_PDF_BYTES = 30_000_000


def _split_words(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


@app.post("/api/correct")
def correct_subtitle(
    file: UploadFile,
    names: str = Form(""),
    dialect_map: str = Form(""),
    dialect_modes: str = Form(""),
    doc_type: str = Form("subtitle"),
    spacing_mode: str = Form("principle"),
    dialect_region: str = Form(""),
    dialect_mode: str = Form(""),
    screen_text_marker: str = Form(""),
    line_break_marker: str = Form(""),
    position_marker: str = Form(""),
    speaker_bracket: str = Form(""),
    tone_bracket: str = Form(""),
):
    # 사전 API를 순차적으로 여러 번 호출하는 무거운 동기(blocking) 작업이라,
    # async def로 두면 이 요청이 끝날 때까지 이벤트 루프 전체가 막혀 다른
    # 요청(health check 포함)도 응답을 못 받는다. sync def로 두면 FastAPI가
    # 자동으로 스레드풀에서 돌려서 이 문제를 피한다.
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            "지원하지 않는 형식입니다. 지원 형식: " + ", ".join(sorted(_ALLOWED_EXTENSIONS)),
        )

    # 번역가가 이 파일에 나오는 고유명사·요리/음료 이름을 미리 알려주면,
    # kiwi가 이후 이 단어를 절대 잘못 쪼개지 않는다(engine.register_custom_words).
    # 문서에서 3번 이상 반복되는 단어는 correct_entries()가 자동으로 감지해
    # 등록하므로, 이 입력은 한두 번만 등장하는 이름을 위한 보조 수단이다.
    register_custom_words(_split_words(names), tag="NNP")

    # 교정 엔진 자체는 자막 전용이 아니라 한국어 텍스트 한 줄을 다루는
    # 범용 엔진이다(engine.correct_entries). .srt는 타임코드 구조를 보존해야
    # 하고, 일반 텍스트는 줄 구성만 보존하면 되므로 파일 형식에 따라
    # 파서/저장 함수만 갈아 끼운다 — 교정 로직 자체는 완전히 동일하다.
    size_limit = _MAX_PDF_BYTES if ext == ".pdf" else _MAX_UPLOAD_BYTES
    raw = file.file.read(size_limit + 1)
    if len(raw) > size_limit:
        raise HTTPException(413, f"파일이 너무 큽니다. 최대 {size_limit // 1_000_000}MB까지 지원합니다.")

    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / f"input{ext}"
        in_path.write_bytes(raw)

        entries = parse_file(in_path)

        # 스캔본 PDF(글자가 이미지)면 텍스트가 하나도 안 나온다. 조용히 빈 결과를
        # 돌려주면 사용자는 도구가 고장 난 줄 안다 — 무엇이 문제인지 알린다.
        # OCR은 넣지 않는다(2026-08-02 사용자 결정): 실측에서 '초코렛을 좋아해요'가
        # '조 코 렛 을 좋 아 해 요'로 읽혔고, 그런 오독이 리포트를 뒤덮으면 정작
        # 봐야 할 교정 항목이 묻힌다. OCR 품질은 우리가 통제할 수 없는 변수다.
        if ext == ".pdf" and not any(e.text.strip() for e in entries):
            raise HTTPException(
                400,
                "이 PDF에는 텍스트 레이어가 없습니다(글자가 이미지인 스캔본). "
                "이 도구는 글자를 추정해 읽지 않습니다 — 다른 OCR 도구로 텍스트를 "
                "먼저 뽑은 뒤 .txt나 .docx로 올려 주세요.",
            )

        # dialect_map 파싱: JSON 문자열 → dict
        parsed_dialect_map: dict[str, str] = {}
        if dialect_map.strip():
            import json
            try:
                parsed_dialect_map = json.loads(dialect_map)
            except json.JSONDecodeError:
                pass

        # dialect_modes 파싱: JSON 문자열 → dict.
        # 허용 모드: protect(기본값, 사투리 보호) / assist(사투리 제안) /
        # to_standard(표준어 자동 변환). 하위 호환 별칭 flag_only→protect,
        # to_dialect→assist도 받는다. 그 외 값이나 미지정은 protect로 정규화한다.
        parsed_dialect_modes: dict[str, str] = {}
        if dialect_modes.strip():
            import json
            try:
                raw_modes = json.loads(dialect_modes)
                if isinstance(raw_modes, dict):
                    parsed_dialect_modes = {
                        speaker: normalize_dialect_mode(mode)
                        for speaker, mode in raw_modes.items()
                    }
            except json.JSONDecodeError:
                pass

        # 사용목적 모드: subtitle(기본, 문장 끝 마침표를 오류로 플래그) /
        # prose(일반 글, 구두점 허용). 그 외 값은 subtitle로 정규화한다.
        normalized_doc_type = doc_type if doc_type == "prose" else "subtitle"

        # 띄어쓰기 기준(제47항 보조 용언): principle(기본, 띄어 씀) /
        # allowance(붙여 씀). 한 문서에 하나만 적용해 원칙과 허용이 섞이지
        # 않게 한다. 그 외 값은 principle로 정규화한다.
        normalized_spacing_mode = normalize_spacing_mode(spacing_mode)

        # 문서 전체 사투리 설정(화자 표기가 없는 일반 글용). 지원하지 않는 지역
        # 이름은 무시한다 — 오타 하나로 글 전체가 엉뚱한 지역 기준으로 처리되면
        # 안 되고, 미지정(None)이 안전한 기본값이다.
        normalized_dialect_region = dialect_region.strip() or None
        if normalized_dialect_region not in DIALECT_MARKERS:
            normalized_dialect_region = None
        normalized_dialect_mode = (
            normalize_dialect_mode(dialect_mode) if normalized_dialect_region else None
        )

        corrected_entries, flags, applied_log = correct_entries(
            entries,
            dialect_map=parsed_dialect_map,
            dialect_modes=parsed_dialect_modes,
            doc_type=normalized_doc_type,
            spacing_mode=normalized_spacing_mode,
            dialect_region=normalized_dialect_region,
            dialect_mode=normalized_dialect_mode,
            # 자막 편집 표지. 업계 공통 규칙이 없어 값을 고정하지 않고 그때그때
            # 받는다. 자막 모드에서만 쓰이며, 지정된 표지는 교정에서 제외된다.
            markers=normalize_subtitle_markers(
                screen_text_marker, line_break_marker, position_marker,
                speaker_bracket, tone_bracket,
            ),
        )

        # .docx는 서식까지 보존하는 새 문서를 만들지 않고(범위 밖), 다른
        # 일반 텍스트와 동일하게 결과를 순수 텍스트로 돌려준다.
        out_path = Path(tmp) / f"output{output_suffix(file.filename)}"
        write_file(corrected_entries, out_path, in_path)
        corrected_text = out_path.read_text(encoding="utf-8")

        # .docx·.pdf는 원본이 바이너리라 그대로 디코드할 수 없다. 우리가 읽어 낸
        # 텍스트를 원문으로 삼는다.
        if ext in (".docx", ".pdf"):
            original_text = "\n".join(e.text for e in entries) + "\n"
        else:
            original_text = raw.decode("utf-8-sig")
    # 저장(Supabase)이 실패해도 이미 완료된 교정 결과 자체는 그대로 돌려준다 —
    # 저장 실패와 교정 실패는 서로 다른 문제다. 저장 실패는 흔히 일시적이거나
    # (무료 티어 슬립/네트워크 지연) 설정 문제이지 교정 로직의 결함이 아닌데,
    # 여기서 예외를 그대로 던지면 이미 성공한 교정 결과까지 통째로 사라지고
    # 사용자는 그냥 "서버 오류"만 보게 된다. 저장 실패는 "공유 링크를 만들지
    # 못했다"는 사실만 알려주고, 나머지 결과는 정상적으로 응답한다.
    try:
        report_id = store.save_report(
            original_srt=original_text,
            corrected_srt=corrected_text,
            flags=flags,
            applied_log=applied_log,
        )
    except (RuntimeError, requests.RequestException):
        report_id = None
    return {
        "id": report_id,
        "original_srt": original_text,
        "corrected_srt": corrected_text,
        "flags": [asdict(f) for f in flags],
        "applied_log": applied_log,
        # 항목별 타임코드까지 함께 준다. 화면에서 다른 자막 형식(.srt/.vtt/.smi)으로
        # 바꿔 받으려면 시각 정보가 필요한데, 완성된 파일 텍스트만으로는 형식을
        # 되짚어 파싱해야 해서 불필요하게 취약해진다.
        "entries": [
            {"index": e.index, "start": e.start, "end": e.end, "text": e.text}
            for e in corrected_entries
        ],
    }


@app.post("/api/export/docx")
def export_docx(text: str = Form(""), filename: str = Form("교정본")):
    """교정 결과를 Word 문서(.docx)로 만들어 돌려준다.

    .docx는 ZIP 안에 XML이 들어 있는 형식이라 브라우저에서 만들기 번거롭다.
    서버에는 이미 python-docx가 있으므로(문서 읽기에 쓴다) 여기서 만든다.

    문단 구분만 살린 순수 텍스트 문서다 — 서식·스타일을 넣지 않는 이유는 원본
    서식을 되살리는 것이 이 도구의 범위가 아니기 때문이다(parse_docx와 같은 입장).
    """
    from docx import Document

    document = Document()
    for line in text.splitlines() or [""]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    safe_name = quote((filename or "교정본") + ".docx")
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    row = store.get_report(report_id)
    if not row:
        raise HTTPException(404, "해당 id의 리포트를 찾을 수 없습니다.")
    return row


@app.post("/api/speakers")
def get_speakers(file: UploadFile):
    """업로드된 SRT 파일에서 화자 목록을 추출해 반환한다.

    SDH 브래킷([이름])이나 "speaker: value" 형식에서 화자를 추출한다.
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            "지원하지 않는 형식입니다. 지원 형식: " + ", ".join(sorted(_ALLOWED_EXTENSIONS)),
        )

    raw = file.file.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "파일이 너무 큽니다.")

    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / f"input{ext}"
        in_path.write_bytes(raw)
        entries = parse_file(in_path)

    speakers = sorted({e.speaker for e in entries if e.speaker})
    return {"speakers": speakers}


@app.get("/api/dialect-regions")
def get_dialect_regions():
    """사투리 교정에서 지원하는 지역 목록을 반환한다."""
    return {"regions": list(DIALECT_MARKERS.keys())}


# 정적 프론트엔드 (업로드 화면). API 라우트보다 아래에 있어야
# "/api/..." 요청이 정적 파일 서빙보다 먼저 매칭된다.
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
