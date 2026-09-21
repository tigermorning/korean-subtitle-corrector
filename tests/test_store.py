"""subtitle_corrector.store — Supabase REST 저장/조회 계약(2026-09-21 스키마 검토에서
발견한 테스트 공백을 메운다).

`save_report`/`get_report`는 지금까지 회귀 테스트가 없었다. 네트워크를 쓰지 않고
`requests.post`/`requests.get`을 가짜로 바꿔, API 계층(api.py)이 기대는 계약만
확인한다: 성공 시 반환 형태, 설정 누락/HTTP 오류/네트워크 오류 시 예외가 그대로
새는가(흡수는 호출부인 api._try_save_report의 몫이지 store의 몫이 아니다).
"""
import uuid

import pytest
import requests

from subtitle_corrector import store


class _Response:
    def __init__(self, status: int = 200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    """모듈 로드 시점에 캡처된 값이라 os.environ이 아니라 모듈 속성을 직접 바꾼다."""
    monkeypatch.setattr(store, "SUPABASE_URL", "https://example.test")
    monkeypatch.setattr(store, "SUPABASE_SERVICE_KEY", "service-role-key")


def test_headers_requires_config(monkeypatch):
    monkeypatch.setattr(store, "SUPABASE_URL", "")
    monkeypatch.setattr(store, "SUPABASE_SERVICE_KEY", "")
    with pytest.raises(RuntimeError):
        store._headers()


def test_headers_uses_service_role_key_not_anon():
    headers = store._headers()
    assert headers["apikey"] == "service-role-key"
    assert headers["Authorization"] == "Bearer service-role-key"


def test_save_report_posts_expected_payload_and_returns_generated_uuid(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Response(status=201)

    monkeypatch.setattr(store.requests, "post", fake_post)

    report_id = store.save_report(
        original_srt="원본",
        corrected_srt="교정본",
        flags=[],
        applied_log=[{"message": "m", "line_index": 1, "is_edit": True}],
    )

    uuid.UUID(report_id)  # 형식이 uuid4가 아니면 여기서 예외
    assert captured["url"] == "https://example.test/rest/v1/reports"
    assert captured["headers"]["apikey"] == "service-role-key"
    assert captured["json"] == {
        "id": report_id,
        "original_srt": "원본",
        "corrected_srt": "교정본",
        "flags": [],
        "applied_log": [{"message": "m", "line_index": 1, "is_edit": True}],
    }


def test_save_report_raises_on_http_error(monkeypatch):
    """호출부(api._try_save_report)가 흡수할 신호 — 여기서 삼키면 안 된다."""
    monkeypatch.setattr(store.requests, "post", lambda *a, **kw: _Response(status=500))
    with pytest.raises(requests.HTTPError):
        store.save_report("o", "c", [], [])


def test_save_report_raises_on_network_error(monkeypatch):
    def fake_post(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(store.requests, "post", fake_post)
    with pytest.raises(requests.ConnectionError):
        store.save_report("o", "c", [], [])


def test_get_report_returns_row_when_found(monkeypatch):
    row = {"id": "abc", "original_srt": "o", "corrected_srt": "c", "flags": [], "applied_log": []}

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url == "https://example.test/rest/v1/reports"
        assert params == {"id": "eq.abc", "select": "*"}
        return _Response(payload=[row])

    monkeypatch.setattr(store.requests, "get", fake_get)
    assert store.get_report("abc") == row


def test_get_report_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr(store.requests, "get", lambda *a, **kw: _Response(payload=[]))
    assert store.get_report("missing-id") is None


def test_get_report_raises_on_network_error(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(store.requests, "get", fake_get)
    with pytest.raises(requests.ConnectionError):
        store.get_report("abc")
