"""GET /api/reports/{id}와 _try_save_report의 실패 흡수 계약(2026-09-21 스키마
검토에서 발견한 테스트 공백을 메운다).

이 경로는 지금까지 테스트가 없었다. 실제 Supabase는 부르지 않고
`subtitle_corrector.store`의 함수를 가짜로 바꿔, api.py 쪽 분기만 확인한다:

- uuid 형식이 아닌 id는 조회 자체를 하지 않고 404 (PostgREST 필터 문자열 주입 방지).
- 저장소 장애(네트워크)와 "없는 리포트"는 각각 502/404로 구분된다.
- 저장 실패(RuntimeError/RequestException)는 `_try_save_report`가 삼켜 None을
  돌려준다 — 이미 완성된 교정 결과가 저장 실패 때문에 통째로 사라지면 안 된다는
  이 저장소의 원칙(AGENTS.md "실패를 성공처럼 보이게 만들지 마라"의 반대 축,
  즉 "실패라고 전체를 죽이지도 마라")을 고정한다.
"""
import uuid

import pytest
import requests
from fastapi.testclient import TestClient

from subtitle_corrector import api, store


@pytest.fixture
def client():
    return TestClient(api.app)


def test_get_report_rejects_non_uuid_without_querying_store(client, monkeypatch):
    called = []
    monkeypatch.setattr(store, "get_report", lambda rid: called.append(rid))

    res = client.get("/api/reports/not-a-uuid")

    assert res.status_code == 404
    assert called == []  # 형식 검사가 조회보다 먼저 걸러야 한다


def test_get_report_returns_row(client, monkeypatch):
    report_id = str(uuid.uuid4())
    row = {
        "id": report_id,
        "original_srt": "o",
        "corrected_srt": "c",
        "flags": [],
        "applied_log": [],
    }
    monkeypatch.setattr(store, "get_report", lambda rid: row if rid == report_id else None)

    res = client.get(f"/api/reports/{report_id}")

    assert res.status_code == 200
    assert res.json() == row


def test_get_report_404_when_missing(client, monkeypatch):
    monkeypatch.setattr(store, "get_report", lambda rid: None)

    res = client.get(f"/api/reports/{uuid.uuid4()}")

    assert res.status_code == 404


def test_get_report_502_on_storage_failure(client, monkeypatch):
    def fake_get_report(rid):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(store, "get_report", fake_get_report)

    res = client.get(f"/api/reports/{uuid.uuid4()}")

    assert res.status_code == 502


def test_try_save_report_absorbs_missing_config(monkeypatch):
    def fake_save_report(**kw):
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY가 .env에 설정되어 있지 않습니다.")

    monkeypatch.setattr(store, "save_report", fake_save_report)

    assert api._try_save_report("o", "c", [], []) is None


def test_try_save_report_absorbs_network_error(monkeypatch):
    def fake_save_report(**kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(store, "save_report", fake_save_report)

    assert api._try_save_report("o", "c", [], []) is None


def test_try_save_report_returns_id_on_success(monkeypatch):
    monkeypatch.setattr(store, "save_report", lambda **kw: "generated-id")

    assert api._try_save_report("o", "c", [], []) == "generated-id"
