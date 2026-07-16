"""웹 API — 기존 CLI 교정 엔진을 그대로 재사용하는 FastAPI 서버.

PRD.md §4의 아키텍처 원칙("교정 로직은 CLI와 분리된 순수 라이브러리 모듈로 설계")을
그대로 활용한다. 여기서는 engine/parsers를 호출만 하고, 새 교정 로직은 추가하지 않는다.
"""

import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from . import store
from .engine import correct_entries
from .parsers import parse_plain_text, parse_srt, write_plain_text, write_srt

app = FastAPI(title="한국어 자막 교정 API")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_ALLOWED_EXTENSIONS = {".srt", ".txt"}


@app.post("/api/correct")
def correct_subtitle(file: UploadFile):
    # 사전 API를 순차적으로 여러 번 호출하는 무거운 동기(blocking) 작업이라,
    # async def로 두면 이 요청이 끝날 때까지 이벤트 루프 전체가 막혀 다른
    # 요청(health check 포함)도 응답을 못 받는다. sync def로 두면 FastAPI가
    # 자동으로 스레드풀에서 돌려서 이 문제를 피한다.
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, ".srt 또는 .txt 파일만 지원합니다.")

    # 교정 엔진 자체는 자막 전용이 아니라 한국어 텍스트 한 줄을 다루는
    # 범용 엔진이다(engine.correct_entries). .srt는 타임코드 구조를 보존해야
    # 하고, 일반 텍스트는 줄 구성만 보존하면 되므로 파일 형식에 따라
    # 파서/저장 함수만 갈아 끼운다 — 교정 로직 자체는 완전히 동일하다.
    raw = file.file.read()
    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / f"input{ext}"
        in_path.write_bytes(raw)

        entries = parse_srt(in_path) if ext == ".srt" else parse_plain_text(in_path)
        corrected_entries, flags, applied_log = correct_entries(entries)

        out_path = Path(tmp) / f"output{ext}"
        if ext == ".srt":
            write_srt(corrected_entries, out_path)
        else:
            write_plain_text(corrected_entries, out_path)
        corrected_text = out_path.read_text(encoding="utf-8")

    original_text = raw.decode("utf-8-sig")
    report_id = store.save_report(
        original_srt=original_text,
        corrected_srt=corrected_text,
        flags=flags,
        applied_log=applied_log,
    )
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


# 정적 프론트엔드 (업로드 화면). API 라우트보다 아래에 있어야
# "/api/..." 요청이 정적 파일 서빙보다 먼저 매칭된다.
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
