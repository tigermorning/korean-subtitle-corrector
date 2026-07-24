"""웹 API — 기존 CLI 교정 엔진을 그대로 재사용하는 FastAPI 서버.

PRD.md §4의 아키텍처 원칙("교정 로직은 CLI와 분리된 순수 라이브러리 모듈로 설계")을
그대로 활용한다. 여기서는 engine/parsers를 호출만 하고, 새 교정 로직은 추가하지 않는다.
"""

import tempfile
from dataclasses import asdict
from pathlib import Path

import requests
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from . import store
from .dictionary import DIALECT_MARKERS
from .engine import correct_entries, register_custom_words
from .parsers import parse_docx, parse_plain_text, parse_srt, write_plain_text, write_srt

app = FastAPI(title="한국어 자막 교정 API")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_ALLOWED_EXTENSIONS = {".srt", ".txt", ".docx"}
# 인증도 업로드 크기 제한도 없으면, 큰 파일 하나가 교정 엔진의 토큰 단위
# 실시간 사전 API 호출(표준국어대사전/우리말샘/kornorms)을 통해 공유 API 키
# 쿼터 자체를 고갈시킬 수 있다(§25 보안 검토, 2026-07-17) — 단순 메모리 DoS
# 보다 "핵심 기능 전체가 막힌다"는 점에서 더 실질적인 위험이라 크기 제한을
# 둔다.
_MAX_UPLOAD_BYTES = 1_000_000


def _split_words(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


@app.post("/api/correct")
def correct_subtitle(
    file: UploadFile,
    names: str = Form(""),
    dialect_map: str = Form(""),
):
    # 사전 API를 순차적으로 여러 번 호출하는 무거운 동기(blocking) 작업이라,
    # async def로 두면 이 요청이 끝날 때까지 이벤트 루프 전체가 막혀 다른
    # 요청(health check 포함)도 응답을 못 받는다. sync def로 두면 FastAPI가
    # 자동으로 스레드풀에서 돌려서 이 문제를 피한다.
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, ".srt, .txt, .docx 파일만 지원합니다.")

    # 번역가가 이 파일에 나오는 고유명사·요리/음료 이름을 미리 알려주면,
    # kiwi가 이후 이 단어를 절대 잘못 쪼개지 않는다(engine.register_custom_words).
    # 문서에서 3번 이상 반복되는 단어는 correct_entries()가 자동으로 감지해
    # 등록하므로, 이 입력은 한두 번만 등장하는 이름을 위한 보조 수단이다.
    register_custom_words(_split_words(names), tag="NNP")

    # 교정 엔진 자체는 자막 전용이 아니라 한국어 텍스트 한 줄을 다루는
    # 범용 엔진이다(engine.correct_entries). .srt는 타임코드 구조를 보존해야
    # 하고, 일반 텍스트는 줄 구성만 보존하면 되므로 파일 형식에 따라
    # 파서/저장 함수만 갈아 끼운다 — 교정 로직 자체는 완전히 동일하다.
    raw = file.file.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"파일이 너무 큽니다. 최대 {_MAX_UPLOAD_BYTES // 1_000_000}MB까지 지원합니다.")

    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / f"input{ext}"
        in_path.write_bytes(raw)

        if ext == ".srt":
            entries = parse_srt(in_path)
        elif ext == ".docx":
            entries = parse_docx(in_path)
        else:
            entries = parse_plain_text(in_path)

        # dialect_map 파싱: JSON 문자열 → dict
        parsed_dialect_map: dict[str, str] = {}
        if dialect_map.strip():
            import json
            try:
                parsed_dialect_map = json.loads(dialect_map)
            except json.JSONDecodeError:
                pass

        corrected_entries, flags, applied_log = correct_entries(
            entries, dialect_map=parsed_dialect_map,
        )

        # .docx는 서식까지 보존하는 새 문서를 만들지 않고(범위 밖), 다른
        # 일반 텍스트와 동일하게 결과를 순수 텍스트로 돌려준다.
        out_path = Path(tmp) / "output.txt"
        if ext == ".srt":
            out_path = Path(tmp) / "output.srt"
            write_srt(corrected_entries, out_path)
        else:
            write_plain_text(corrected_entries, out_path)
        corrected_text = out_path.read_text(encoding="utf-8")

        if ext == ".docx":
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
    }


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    row = store.get_report(report_id)
    if not row:
        raise HTTPException(404, "해당 id의 리포트를 찾을 수 없습니다.")
    return row


@app.get("/api/speakers")
def get_speakers(file: UploadFile):
    """업로드된 SRT 파일에서 화자 목록을 추출해 반환한다.

    SDH 브래킷([이름])이나 "speaker: value" 형식에서 화자를 추출한다.
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, ".srt, .txt, .docx 파일만 지원합니다.")

    raw = file.file.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "파일이 너무 큽니다.")

    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / f"input{ext}"
        in_path.write_bytes(raw)
        if ext == ".srt":
            entries = parse_srt(in_path)
        elif ext == ".docx":
            entries = parse_docx(in_path)
        else:
            entries = parse_plain_text(in_path)

    speakers = sorted({e.speaker for e in entries if e.speaker})
    return {"speakers": speakers}


@app.get("/api/dialect-regions")
def get_dialect_regions():
    """사투리 교정에서 지원하는 지역 목록을 반환한다."""
    return {"regions": list(DIALECT_MARKERS.keys())}


# 정적 프론트엔드 (업로드 화면). API 라우트보다 아래에 있어야
# "/api/..." 요청이 정적 파일 서빙보다 먼저 매칭된다.
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
