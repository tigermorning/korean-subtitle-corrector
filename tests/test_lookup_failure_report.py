"""사전 조회 실패를 어떻게 세고 어떻게 알리는가(§62).

2026-08-04 사용자 보고: 우리말샘은 정상 접속되는데 "이 사전이 담당하는 교정은 이번
결과에 반영되지 않았습니다"가 계속 떴다. 원인은 두 가지였다 — ① 순간적인 실패 한 건도
재시도 없이 실패로 확정했고 ② 이름만 모아서 "한 건 실패"와 "전부 불통"을 구분하지
못했다. 아래 테스트가 그 두 가지를 고정한다. 네트워크는 쓰지 않는다(가짜 응답).
"""
import pytest
import requests

from subtitle_corrector.dictionary import clients
from subtitle_corrector.engine import correct_entries
from subtitle_corrector.parsers import SubtitleEntry


class _Response:
    def __init__(self, text: str, status: int = 200, payload=None):
        self.text = text
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


_OK = {"channel": {"total": 1, "item": [{"word": "사랑"}]}}
_ERROR_XML = (
    '<?xml version="1.0" encoding="UTF-8"?><error>'
    "<error_code>100</error_code><message>Incorrect query request</message></error>"
)
_QUOTA_XML = (
    '<?xml version="1.0" encoding="UTF-8"?><error>'
    "<error_code>020</error_code><message>service key limit</message></error>"
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """조회 캐시와 집계를 비우고, 재시도 대기를 없애 테스트를 빠르게 한다."""
    clients._fetch_opendict.cache_clear()
    clients._fetch_stdict.cache_clear()
    clients.reset_failed_lookups()
    monkeypatch.setattr(clients.time, "sleep", lambda _s: None)
    yield
    clients._fetch_opendict.cache_clear()
    clients._fetch_stdict.cache_clear()
    clients.reset_failed_lookups()


def _responses(monkeypatch, sequence):
    """requests.get이 sequence를 차례로 돌려주게 한다(예외 객체면 raise)."""
    calls = {"n": 0}

    def fake_get(_url, **_kw):
        item = sequence[min(calls["n"], len(sequence) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(clients.requests, "get", fake_get)
    return calls


def test_transient_failure_is_retried_and_not_reported(monkeypatch):
    """순간적인 실패는 재시도로 넘긴다 — 리포트에 실패로 남기지 않는다."""
    calls = _responses(monkeypatch, [
        requests.ConnectionError("boom"),
        requests.ReadTimeout("slow"),
        _Response("{...}", payload=_OK),
    ])
    assert clients.search_opendict("사랑") == _OK
    assert calls["n"] == 3
    assert clients.failed_lookups() == []


def test_failure_after_all_retries_is_reported_with_the_query(monkeypatch):
    _responses(monkeypatch, [requests.ConnectionError("boom")])
    assert clients.search_opendict("사랑")["channel"]["total"] == 0
    assert clients.failed_lookups() == ["우리말샘"]
    stats = clients.lookup_stats()["우리말샘"]
    assert stats["attempts"] == 1 and stats["failures"] == 1
    assert stats["queries"] == ["사랑"]  # 어느 낱말이 실패했는지 리포트에 싣는다


def test_failure_is_not_cached(monkeypatch):
    """실패를 캐시하면 순간적인 실패 하나가 그 낱말의 판정을 문서 끝까지 오염시킨다.
    `_LookupFailed` 예외로 올려 보내므로 lru_cache가 그 결과를 남기지 않는다."""
    _responses(monkeypatch, [requests.ConnectionError("boom")])
    assert clients.search_opendict("사랑")["channel"]["total"] == 0
    _responses(monkeypatch, [_Response("{...}", payload=_OK)])
    assert clients.search_opendict("사랑") == _OK


def test_bad_query_error_is_not_counted_as_an_outage(monkeypatch):
    """국립국어원 API는 API 문법에 안 맞는 검색어에 200 + XML `<error>`(코드 100)을
    돌려준다('/'·'^' 실측). 서버 장애가 아니므로 불통으로 세지 않는다. 전에는
    `response.json()`이 그대로 터졌다."""
    _responses(monkeypatch, [_Response(_ERROR_XML)])
    assert clients.search_opendict("/")["channel"]["total"] == 0
    assert clients.failed_lookups() == []


def test_other_api_error_codes_are_reported(monkeypatch):
    """코드 100이 아닌 오류(키 한도 등)는 조회가 실제로 안 된 것이므로 알린다."""
    _responses(monkeypatch, [_Response(_QUOTA_XML)])
    assert clients.search_opendict("사랑")["channel"]["total"] == 0
    assert clients.failed_lookups() == ["우리말샘"]
    assert "error_code=020" in clients.lookup_stats()["우리말샘"]["queries"][0]


def _log_messages(monkeypatch, stats):
    monkeypatch.setattr("subtitle_corrector.engine.pipeline.lookup_stats", lambda: stats)
    entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text="안녕", speaker=None)
    _entries, _flags, log = correct_entries([entry], None, None)
    return [n.message for n in log]


def test_partial_failure_message_does_not_claim_the_dictionary_is_down(monkeypatch):
    messages = _log_messages(
        monkeypatch, {"우리말샘": {"attempts": 1200, "failures": 2, "queries": ["사랑", "구름"]}}
    )
    note = next(m for m in messages if "우리말샘" in m)
    assert note.startswith("[사전 조회 일부 실패]")
    assert "1200건 중 2건" in note
    assert "나머지 교정은 정상입니다" in note
    assert "사랑, 구름" in note
    # 사용자가 연결이 끊긴 줄 알게 만든 문구는 이 경우 나오지 않아야 한다.
    assert "반영되지 않았습니다" not in note


def test_total_outage_message_still_warns_clearly(monkeypatch):
    messages = _log_messages(
        monkeypatch, {"우리말샘": {"attempts": 300, "failures": 300, "queries": ["사랑"]}}
    )
    note = next(m for m in messages if "우리말샘" in m)
    assert note.startswith("[사전 조회 실패]")
    assert "300건이 전부 실패" in note
    assert "반영되지 않았습니다" in note


def test_breaker_stops_hammering_a_dead_api(monkeypatch):
    """API가 정말 죽으면 재시도가 독이 된다 — 자막 40줄에 조회가 1,119건 나가므로
    (2026-08-04 실측) 한 건에 10초 타임아웃 3번이면 실행이 멈춘다. 연속 실패가
    5건을 넘으면 조회를 건너뛰고, 20건마다 한 번만 찔러 본다."""
    calls = _responses(monkeypatch, [requests.ConnectionError("down")])
    for i in range(30):
        clients._fetch_opendict.cache_clear()  # 매번 새 낱말인 것처럼
        clients.search_opendict(f"낱말{i}")
    stats = clients.lookup_stats()["우리말샘"]
    assert stats["failures"] == 30  # 30건 다 실패로 보고된다
    # 앞 5건은 3회씩(15) + 그 뒤로는 20건 건너뛰고 한 번만 찔러 본다(1).
    assert calls["n"] == 16


def test_breaker_reopens_when_the_api_recovers(monkeypatch):
    _responses(monkeypatch, [requests.ConnectionError("down")])
    for i in range(6):
        clients._fetch_opendict.cache_clear()
        clients.search_opendict(f"낱말{i}")
    assert clients.lookup_stats()["우리말샘"]["streak"] >= 5
    _responses(monkeypatch, [_Response("{...}", payload=_OK)])
    clients._fetch_opendict.cache_clear()
    for i in range(21):  # 찔러 보는 차례가 오면 복구를 알아챈다
        clients._fetch_opendict.cache_clear()
        result = clients.search_opendict(f"복구{i}")
    assert result == _OK
    assert clients.lookup_stats()["우리말샘"]["streak"] == 0
