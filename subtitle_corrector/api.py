"""웹 API — 기존 CLI 교정 엔진을 그대로 재사용하는 FastAPI 서버.

PRD.md §4의 아키텍처 원칙("교정 로직은 CLI와 분리된 순수 라이브러리 모듈로 설계")을
그대로 활용한다. 여기서는 engine/parsers를 호출만 하고, 새 교정 로직은 추가하지 않는다.

이 파일이 하는 일은 세 가지뿐이다: (1) 업로드를 검증해 임시 파일로 실체화,
(2) 폼 문자열을 엔진이 받는 설정값으로 정규화, (3) 결과를 JSON으로 직렬화.
교정 규칙에 해당하는 판단은 한 줄도 여기 두지 않는다.
"""

import io
import json
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from urllib.parse import quote
from pathlib import Path

import requests
from fastapi import FastAPI, Form, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles

from . import feedback, store
from .decoding import decode_bytes, verify_ingest_fidelity
from .file_io import SUPPORTED_EXTENSIONS, output_suffix, parse_file, write_file
from .dictionary import DIALECT_MARKERS, lookup_by_source, lookup_stats
from .engine import (
    SubtitleEntry,
    correct_entries,
    normalize_punctuation_style,
    normalize_subtitle_markers,
    normalize_dialect_mode,
    normalize_llm_settings,
    normalize_spacing_mode,
    register_custom_words,
)

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


def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    """업로드를 검증하고 (확장자, 원본 바이트)를 돌려준다.

    확장자·크기 검증은 파일을 받는 모든 엔드포인트가 똑같이 해야 하는 일이라
    여기 한곳에 둔다 — 엔드포인트마다 따로 쓰면 한쪽만 고쳐져 "업로드 화면에서는
    막히는데 다른 경로로는 통과한다" 같은 구멍이 생긴다.

    크기 제한은 한도 + 1바이트까지만 읽어서 판정한다. 먼저 통째로 읽고 나서
    길이를 재면 거부할 파일도 일단 메모리에 다 올리게 된다.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            "지원하지 않는 형식입니다. 지원 형식: " + ", ".join(sorted(_ALLOWED_EXTENSIONS)),
        )
    size_limit = _MAX_PDF_BYTES if ext == ".pdf" else _MAX_UPLOAD_BYTES
    raw = file.file.read(size_limit + 1)
    if len(raw) > size_limit:
        raise HTTPException(
            413, f"파일이 너무 큽니다. 최대 {size_limit // 1_000_000}MB까지 지원합니다."
        )
    return ext, raw


@contextmanager
def _materialized(ext: str, raw: bytes) -> Iterator[Path]:
    """업로드 바이트를 임시 파일로 만들어 경로를 넘긴다.

    파서·저장 함수가 모두 경로를 받는다(ASS/SAMI/TTML은 저장할 때 원본 파일에서
    대사 외의 내용을 그대로 가져와야 해서 경로가 반드시 필요하다).
    """
    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / f"input{ext}"
        in_path.write_bytes(raw)
        yield in_path


def _parse_entries(ext: str, path: Path) -> list[SubtitleEntry]:
    entries = parse_file(path)

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
    return entries


def _parse_json_object(raw: str) -> dict:
    """폼으로 온 JSON 문자열을 dict로 읽는다. 깨졌으면 빈 dict.

    설정값 하나가 깨졌다고 교정 요청 전체를 400으로 돌려보내지 않는다 — 이
    값들은 전부 "지정하지 않음"이라는 안전한 기본값이 있는 선택 항목이다.
    """
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
    ellipsis_style: str = Form("dots"),
    quote_style: str = Form("half"),
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
    ext, raw = _read_upload(file)

    # 번역가가 이 파일에 나오는 고유명사·요리/음료 이름을 미리 알려주면,
    # kiwi가 이후 이 단어를 절대 잘못 쪼개지 않는다(engine.register_custom_words).
    # 문서에서 3번 이상 반복되는 단어는 correct_entries()가 자동으로 감지해
    # 등록하므로, 이 입력은 한두 번만 등장하는 이름을 위한 보조 수단이다.
    register_custom_words(_split_words(names), tag="NNP")

    # 교정 엔진 자체는 자막 전용이 아니라 한국어 텍스트 한 줄을 다루는
    # 범용 엔진이다(engine.correct_entries). .srt는 타임코드 구조를 보존해야
    # 하고, 일반 텍스트는 줄 구성만 보존하면 되므로 파일 형식에 따라
    # 파서/저장 함수만 갈아 끼운다 — 교정 로직 자체는 완전히 동일하다.
    with _materialized(ext, raw) as in_path:
        entries = _parse_entries(ext, in_path)

        # **읽어 낸 원문이 업로드한 파일과 같은지 매번 증명한다.** 파싱이 원문을 조금이라도
        # 바꿔 놓으면 그 뒤 교정이 정확해도 다른 문서를 고친 것이 된다(2026-08-03 사용자
        # 요구). 어긋나면 교정하지 않고 무엇이 어긋났는지 알린다 — 조용히 진행하는 것이
        # 가장 나쁘다. 바이너리(.docx/.pdf)는 텍스트를 뽑아내는 것이라 이 비교가 성립하지
        # 않으므로 건너뛴다.
        ingest_problems: list[str] = []
        if ext not in (".docx", ".pdf"):
            source_text, source_encoding = decode_bytes(raw)
            ingest_problems = verify_ingest_fidelity(source_text, [e.text for e in entries])
            if ingest_problems:
                raise HTTPException(
                    422,
                    "업로드한 파일을 그대로 읽지 못했습니다. 교정을 진행하지 않았습니다 — "
                    f"읽은 인코딩: {source_encoding}. "
                    + " / ".join(ingest_problems[:3]),
                )

        # dialect_modes 파싱: JSON 문자열 → dict.
        # 허용 모드: protect(기본값, 사투리 보호) / assist(사투리 제안) /
        # to_standard(표준어 자동 변환). 하위 호환 별칭 flag_only→protect,
        # to_dialect→assist도 받는다. 그 외 값이나 미지정은 protect로 정규화한다.
        parsed_dialect_modes = {
            speaker: normalize_dialect_mode(mode)
            for speaker, mode in _parse_json_object(dialect_modes).items()
        }

        # 사용목적 모드: subtitle(기본, 문장 끝 마침표를 오류로 플래그) /
        # prose(일반 글, 구두점 허용). 그 외 값은 subtitle로 정규화한다.
        normalized_doc_type = doc_type if doc_type == "prose" else "subtitle"

        # 문서 전체 사투리 설정(화자 표기가 없는 일반 글용). 지원하지 않는 지역
        # 이름은 무시한다 — 오타 하나로 글 전체가 엉뚱한 지역 기준으로 처리되면
        # 안 되고, 미지정(None)이 안전한 기본값이다.
        normalized_dialect_region = dialect_region.strip() or None
        if normalized_dialect_region not in DIALECT_MARKERS:
            normalized_dialect_region = None

        # 교정 전 원문을 줄 번호로 붙들어 둔다. 화면의 "되돌리기"가 이 값으로
        # 그 줄만 원래대로 되돌린다 — 자동 교정 로그의 '원문조각 -> 교정조각'은
        # 긴 줄에서 '…'로 축약되므로(`_localized_change`) 복원에 쓸 수 없다.
        originals = {e.index: e.text for e in entries}

        corrected_entries, flags, applied_log = correct_entries(
            entries,
            dialect_map=_parse_json_object(dialect_map),
            dialect_modes=parsed_dialect_modes,
            doc_type=normalized_doc_type,
            # 띄어쓰기 기준(제47항 보조 용언): principle(기본, 띄어 씀) /
            # allowance(붙여 씀). 한 문서에 하나만 적용해 원칙과 허용이 섞이지
            # 않게 한다. 그 외 값은 principle로 정규화한다.
            spacing_mode=normalize_spacing_mode(spacing_mode),
            dialect_region=normalized_dialect_region,
            dialect_mode=(
                normalize_dialect_mode(dialect_mode) if normalized_dialect_region else None
            ),
            # 자막 편집 표지. 업계 공통 규칙이 없어 값을 고정하지 않고 그때그때
            # 받는다. 자막 모드에서만 쓰이며, 지정된 표지는 교정에서 제외된다.
            # 구두점 표기 방식(말줄임표·따옴표). 납품처마다 달라 설정으로 받는다.
            style=normalize_punctuation_style(ellipsis_style, quote_style),
            markers=normalize_subtitle_markers(
                screen_text_marker, line_break_marker, position_marker,
                speaker_bracket, tone_bracket,
            ),
            # 언어 모델 패스. 화면에서 켜고 끄는 항목으로 두지 않고 **서버 설정
            # (.env)으로만** 정한다 — 원고를 외부로 보낼지 말지는 그 서버를 세운
            # 사람이 정할 문제이지, 업로드하는 사람이 체크칸으로 정할 문제가 아니다.
            # 주소·모델 이름이 없으면 normalize가 알아서 꺼진 설정으로 떨어뜨린다.
            llm=normalize_llm_settings(enabled=True),
        )

        # .docx는 서식까지 보존하는 새 문서를 만들지 않고(범위 밖), 다른
        # 일반 텍스트와 동일하게 결과를 순수 텍스트로 돌려준다.
        out_path = in_path.with_name(f"output{output_suffix(file.filename or '')}")
        write_file(corrected_entries, out_path, in_path)
        corrected_text = out_path.read_text(encoding="utf-8")

        # .docx·.pdf는 원본이 바이너리라 그대로 디코드할 수 없다. 우리가 읽어 낸
        # 텍스트를 원문으로 삼는다.
        if ext in (".docx", ".pdf"):
            original_text = "\n".join(e.text for e in entries) + "\n"
        else:
            original_text = raw.decode("utf-8-sig")

    # 자동 교정 로그는 구조로 내보낸다({message, line_index, is_edit}). 화면이
    # 줄 단위 되돌리기를 제공하려면 어느 줄의 기록인지 알아야 하는데, 문자열을
    # 다시 파싱하면 줄 기록과 문서 전체 안내가 구분되지 않는다.
    applied_payload = [asdict(n) for n in applied_log]

    return {
        "id": _try_save_report(original_text, corrected_text, flags, applied_payload),
        "original_srt": original_text,
        "corrected_srt": corrected_text,
        "flags": [asdict(f) for f in flags],
        "applied_log": applied_payload,
        # 항목별 타임코드까지 함께 준다. 화면에서 다른 자막 형식(.srt/.vtt/.smi)으로
        # 바꿔 받으려면 시각 정보가 필요한데, 완성된 파일 텍스트만으로는 형식을
        # 되짚어 파싱해야 해서 불필요하게 취약해진다.
        "entries": [
            {
                "index": e.index,
                "start": e.start,
                "end": e.end,
                "text": e.text,
                # 되돌리기용 교정 전 원문. 자동 교정이 없었던 줄은 text와 같다.
                "original": originals.get(e.index, e.text),
            }
            for e in corrected_entries
        ],
    }


@app.post("/api/feedback")
def record_feedback(decisions: str = Form(""), document: str = Form("")):
    """화면에서 '반영'을 누른 순간의 판정을 기록한다(기본 꺼짐).

    화면이 이 창구를 부르는 것은 교정의 부수 작업이므로 **어떤 경우에도 사용자의
    작업을 막지 않는다** — 형식이 깨졌으면 0건으로 답하고 끝낸다. 400을 돌려주면
    화면이 오류를 띄우게 되는데, 사용자 입장에서는 방금 반영한 교정과 아무 상관도
    없는 실패라 혼란만 준다.

    `document`는 원고 전문이다. 여기서 즉시 해시로 바꾸고 **원문은 버린다**
    (`feedback.document_id` 참고) — 같은 원고의 중복 판정을 나중에 걸러내는
    용도라 문서를 가릴 수만 있으면 된다.
    """
    if not feedback.is_enabled():
        return {"enabled": False, "recorded": 0}
    try:
        parsed = json.loads(decisions) if decisions.strip() else []
    except json.JSONDecodeError:
        return {"enabled": True, "recorded": 0}
    if not isinstance(parsed, list):
        return {"enabled": True, "recorded": 0}
    written = feedback.record_decisions(
        parsed, doc_hash=feedback.document_id(document) if document else ""
    )
    return {"enabled": True, "recorded": written}


@app.get("/api/feedback/summary")
def feedback_summary():
    """쌓인 판정 건수. 학습을 시작할 만큼 모였는지 보는 용도다."""
    return feedback.summarize()


def _try_save_report(
    original_text: str, corrected_text: str, flags: list, applied_log: list[dict]
) -> str | None:
    """저장(Supabase)을 시도하고, 실패하면 None을 돌려준다.

    저장이 실패해도 이미 완료된 교정 결과 자체는 그대로 돌려준다 — 저장 실패와
    교정 실패는 서로 다른 문제다. 저장 실패는 흔히 일시적이거나(무료 티어
    슬립/네트워크 지연) 설정 문제이지 교정 로직의 결함이 아닌데, 여기서 예외를
    그대로 던지면 이미 성공한 교정 결과까지 통째로 사라지고 사용자는 그냥
    "서버 오류"만 보게 된다. 저장 실패는 "공유 링크를 만들지 못했다"는 사실만
    알려주고, 나머지 결과는 정상적으로 응답한다.
    """
    try:
        return store.save_report(
            original_srt=original_text,
            corrected_srt=corrected_text,
            flags=flags,
            applied_log=applied_log,
        )
    except (RuntimeError, requests.RequestException):
        return None


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
    # id는 저장할 때 uuid4로 만든 값이다(store.save_report). 그 형식이 아니면
    # 조회 자체를 하지 않는다 — 이 값은 PostgREST 필터 문자열("id=eq.{...}")에
    # 그대로 들어가므로, 쉼표 같은 문자가 섞이면 의도하지 않은 질의가 된다.
    try:
        uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(404, "해당 id의 리포트를 찾을 수 없습니다.")

    # 저장소 장애(네트워크·무료 티어 슬립)는 "없는 리포트"와 다른 상황이라
    # 502로 구분해 알린다. 그대로 두면 스택 트레이스와 함께 500이 나간다.
    try:
        row = store.get_report(report_id)
    except requests.RequestException:
        raise HTTPException(502, "리포트 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    if not row:
        raise HTTPException(404, "해당 id의 리포트를 찾을 수 없습니다.")
    return row


@app.post("/api/speakers")
def get_speakers(file: UploadFile):
    """업로드된 SRT 파일에서 화자 목록을 추출해 반환한다.

    SDH 브래킷([이름])이나 "speaker: value" 형식에서 화자를 추출한다.
    """
    ext, raw = _read_upload(file)
    with _materialized(ext, raw) as in_path:
        entries = parse_file(in_path)

    return {"speakers": sorted({e.speaker for e in entries if e.speaker})}


@app.get("/api/dialect-regions")
def get_dialect_regions():
    """사투리 교정에서 지원하는 지역 목록을 반환한다."""
    return {"regions": list(DIALECT_MARKERS.keys())}


# `_get_json()`이 실패를 기록할 때 쓰는 이름. 이 문자열이 바뀌면 아래 판정이 조용히
# 죽으므로 한곳에 모아 둔다.
_KORNORMS_API = "어문 규범 용례(kornorms)"


def _kornorms_failures() -> int:
    return lookup_stats().get(_KORNORMS_API, {}).get("failures", 0)


@app.get("/api/loanword-source")
def get_loanword_by_source(source: str, token: str = ""):
    """원어(로마자) 표기로 국립국어원 확정 한글 표기를 찾는다.

    외래어 음차의 정답은 **원어가 무엇이냐**로 갈린다 — `러스`는 원어가 Ruth면
    `루스`, Russ면 `러스`가 맞다(§57의 실제 사고). 화면의 플래그마다 원어 입력칸을
    두고 이 엔드포인트를 부르면, 번역가가 외래어 표기법 세칙을 직접 읽지 않고도
    국립국어원 용례라는 확정 근거로 판단할 수 있다.

    `token`(자막에 쓰인 음차)을 함께 주면 후보마다 그 토막에 대응하는 조각을
    `segment`로 돌려준다 — 인명 용례의 한글 표기는 `러더퍼드, 어니스트`처럼 전체
    이름이라, 그대로 넣으면 문장에 엉뚱한 이름이 삽입된다.

    응답: `{source, token, candidates: [...], confirmed: bool, lookup_failed: bool}`.
    `candidates`는 비슷한 원어를 참고로 보여 주는 목록일 뿐 정답 근거가 아니다.

    **`lookup_failed`를 먼저 봐야 한다**(2026-09-01 추가, §79). `lookup_by_source()`는
    서버 장애와 미등재를 똑같이 빈 목록으로 돌려준다. 그 값만 보고 "등재된 용례가
    없습니다"라고 화면에 쓰면, 서버가 죽은 날 번역가는 사실이 아닌 단정을 근거로
    판단하게 된다 — 이 도구에서 가장 나쁜 종류의 오류다. 조회가 실패했으면
    `confirmed`·`candidates`는 **아무 뜻도 없는 값**으로 봐야 한다.
    """
    query = (source or "").strip()
    if not query:
        raise HTTPException(400, "원어(로마자) 표기를 입력해 주세요.")
    if len(query) > 100:
        raise HTTPException(400, "원어 표기가 너무 깁니다(100자 이내).")
    # 조회 전후의 실패 건수를 비교해서 이번 조회가 실패했는지 가린다. 전역 통계라
    # 동시에 도는 교정 작업의 실패가 섞일 수 있는데, 그 경우 "실패했다"고 과하게
    # 말하는 쪽으로 틀린다 — 반대(장애를 미등재로 단정)보다 훨씬 안전하다.
    failures_before = _kornorms_failures()
    candidates = lookup_by_source(query, token.strip())
    lookup_failed = _kornorms_failures() > failures_before
    return {
        "source": query,
        "token": token.strip(),
        "candidates": candidates,
        "confirmed": any(c["match"] in ("확정", "일치") for c in candidates),
        "lookup_failed": lookup_failed,
    }


# 정적 프론트엔드 (업로드 화면). API 라우트보다 아래에 있어야
# "/api/..." 요청이 정적 파일 서빙보다 먼저 매칭된다.
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
