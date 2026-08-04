"""Supabase(Postgres) REST API를 통한 교정 리포트 저장/조회.

브라우저는 이 서버(FastAPI)에만 요청을 보내고 Supabase에는 절대 직접 접근하지 않는다.
그래서 service_role 키(관리자 권한, RLS를 무시함)를 서버 쪽 환경변수로만 들고 있어도 안전하다 —
공개되는 건 이 서버의 주소뿐이고, Supabase 키는 브라우저에 한 번도 내려가지 않는다.
"""

import os
import uuid
from dataclasses import asdict

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

_TABLE = "reports"


def _headers() -> dict:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY가 .env에 설정되어 있지 않습니다.")
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def save_report(original_srt: str, corrected_srt: str, flags: list, applied_log: list[dict]) -> str:
    """교정 결과를 저장하고, 나중에 다시 불러올 수 있는 id를 반환한다.

    `applied_log`는 `AppliedNote`를 asdict한 목록이다. 2026-08-04 이전에 저장된
    행에는 문자열 목록이 들어 있으므로, 불러오는 쪽(화면)이 두 형태를 모두 받아야 한다.
    """
    report_id = str(uuid.uuid4())
    payload = {
        "id": report_id,
        "original_srt": original_srt,
        "corrected_srt": corrected_srt,
        "flags": [asdict(f) for f in flags],
        "applied_log": applied_log,
    }
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{_TABLE}",
        headers=_headers(),
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return report_id


def get_report(report_id: str) -> dict | None:
    """저장된 리포트를 id로 다시 불러온다. 없으면 None."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{_TABLE}",
        headers=_headers(),
        params={"id": f"eq.{report_id}", "select": "*"},
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None
