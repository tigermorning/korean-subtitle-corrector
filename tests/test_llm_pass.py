"""언어 모델 패스 회귀 테스트(2026-08-12).

이 패스의 위험은 "모델이 좋은 제안을 못 한다"가 아니라 **"나쁜 제안이 목록에 오른다"**
이다. 화면의 제안은 사람이 누르면 그대로 반영되고, 한 편에 수백 건이 뜨면 하나씩
검증되지 않는다. 그래서 여기 고정하는 불변식은 전부 "무엇이 걸러지는가"다.

모델 호출은 주입한 가짜 함수로 대체하므로 네트워크가 필요 없다.
"""

import json

import pytest
import requests

from subtitle_corrector.engine import LlmSettings, normalize_llm_settings, propose_corrections
from subtitle_corrector.engine import llm_pass
from subtitle_corrector.engine.options import normalize_subtitle_markers
from subtitle_corrector.parsers import SubtitleEntry

ON = LlmSettings(enabled=True, base_url="http://localhost:1234/v1", model="test-model")


def _entry(index, text, speaker=""):
    return SubtitleEntry(
        index=index, start="00:00:01,000", end="00:00:04,000",
        text=text, speaker=speaker,
    )


def _responder(payload):
    """모델이 항상 같은 JSON을 돌려주는 가짜 클라이언트."""
    def _call(prompt, settings):
        return json.dumps(payload, ensure_ascii=False)
    return _call


def _raw_responder(raw):
    def _call(prompt, settings):
        return raw
    return _call


class _FakeResponse:
    """`requests.post`가 돌려주는 것 중 `_chat`이 만지는 부분만 흉내 낸다."""

    def __init__(self, status_code=200, content='{"proposals": []}'):
        self.status_code = status_code
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _record_posts(monkeypatch, responder):
    """`_chat`이 보낸 payload를 순서대로 모은다. 반환값이 그 목록이다."""
    sent = []

    def _post(url, headers=None, json=None, timeout=None):
        sent.append(dict(json))
        return responder(json)

    monkeypatch.setattr(llm_pass.requests, "post", _post)
    llm_pass._SCHEMA_SUPPORT.clear()
    return sent


class TestSettings:
    @pytest.fixture(autouse=True)
    def _no_env_defaults(self, monkeypatch):
        """`.env`에 LLM_BASE_URL/LLM_MODEL을 채워 둔 개발 환경에서 돌려도, 이
        클래스의 "인자를 안 주면 꺼진다" 가정이 실제 환경변수에 흔들리지 않게
        모듈 전역을 비운다(2026-09-09) — `feedback.py`의 `log_dir` 픽스처와 같은
        이유다."""
        from subtitle_corrector.engine import llm_pass

        monkeypatch.setattr(llm_pass, "LLM_BASE_URL", "")
        monkeypatch.setattr(llm_pass, "LLM_MODEL", "")
        monkeypatch.setattr(llm_pass, "LLM_API_KEY", "")

    def test_기본값은_꺼짐(self):
        assert normalize_llm_settings().enabled is False

    def test_모델_이름이_없으면_어느_경로로도_켤_수_없다(self):
        assert normalize_llm_settings(enabled=True, base_url="http://x/v1", model="").enabled is False
        assert normalize_llm_settings(enabled=True, backend="cli", model="").enabled is False

    def test_http_경로는_주소가_있어야_켜진다(self):
        assert normalize_llm_settings(
            enabled=True, backend="http", base_url="", model="m").enabled is False
        settings = normalize_llm_settings(
            enabled=True, backend="http", base_url="http://x/v1/", model="m")
        assert settings.enabled is True
        assert settings.base_url == "http://x/v1"  # 끝의 슬래시는 떼어 낸다

    def test_cli_경로는_실행_파일이_있어야_켜진다(self, monkeypatch):
        from subtitle_corrector.engine import llm_pass

        monkeypatch.setattr(llm_pass, "find_ollama_exe", lambda: "")
        assert normalize_llm_settings(enabled=True, backend="cli", model="m").enabled is False
        monkeypatch.setattr(llm_pass, "find_ollama_exe", lambda: "/usr/bin/ollama")
        assert normalize_llm_settings(enabled=True, backend="cli", model="m").enabled is True

    def test_auto는_주소가_있으면_http_없으면_cli(self, monkeypatch):
        from subtitle_corrector.engine import llm_pass

        monkeypatch.setattr(llm_pass, "find_ollama_exe", lambda: "/usr/bin/ollama")
        assert normalize_llm_settings(
            enabled=True, base_url="http://x/v1", model="m").backend == "http"
        assert normalize_llm_settings(enabled=True, model="m").backend == "cli"

    def test_꺼져_있으면_호출조차_하지_않는다(self):
        def _boom(prompt, settings):
            raise AssertionError("꺼진 설정에서 모델을 불렀다")

        flags, notes = propose_corrections(
            [_entry(1, "됬다")], LlmSettings(), complete=_boom
        )
        assert flags == [] and notes == []


class TestAcceptedProposal:
    def test_근거를_밝힌_제안은_플래그가_된다(self):
        entries = [_entry(1, "그렇게 됬다")]
        flags, _ = propose_corrections(
            entries, ON,
            complete=_responder([{
                "id": 1, "before": "그렇게 됬다", "after": "그렇게 됐다",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]),
        )
        assert len(flags) == 1
        assert flags[0].line_index == 1
        assert flags[0].suggested_fix == "그렇게 됐다"
        assert "됬다 -> 됐다" in flags[0].reason

    def test_본문은_절대_바뀌지_않는다(self):
        entries = [_entry(1, "그렇게 됬다")]
        propose_corrections(
            entries, ON,
            complete=_responder([{
                "id": 1, "before": "그렇게 됬다", "after": "그렇게 됐다",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]),
        )
        assert entries[0].text == "그렇게 됬다"

    def test_모델이_앞뒤_공백을_떼도_원문_여백을_지킨다(self):
        flags, _ = propose_corrections(
            [_entry(1, "  그렇게 됬다  ")], ON,
            complete=_responder([{
                "id": 1, "before": "그렇게 됬다", "after": "그렇게 됐다",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]),
        )
        assert flags[0].suggested_fix == "  그렇게 됐다  "


class TestBlockedProposal:
    def test_근거를_밝히지_않은_변경은_버린다(self):
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON,
            complete=_responder([{
                "id": 1, "before": "그렇게 됬다", "after": "그렇게 되었습니다",
                "rule": "문체", "declared": [],
            }]),
        )
        assert flags == []
        assert any("무엇을 바꿨는지 밝히지 않아" in n.message for n in notes)

    def test_밝힌_것과_다른_낱말을_바꾸면_edit_guard가_막는다(self):
        # declared는 '됬다 -> 됐다' 하나뿐인데 '그렇게'까지 바꿨다.
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON,
            complete=_responder([{
                "id": 1, "before": "그렇게 됬다", "after": "그리하여 됐다",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]),
        )
        assert flags == []
        assert any("근거 없이 낱말을 바꾸려 해" in n.message for n in notes)

    def test_원문을_다르게_인용하면_버린다(self):
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON,
            complete=_responder([{
                "id": 1, "before": "이렇게 됬다", "after": "이렇게 됐다",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]),
        )
        assert flags == []
        assert any("원문을 다르게 인용해" in n.message for n in notes)

    def test_줄바꿈_개수를_바꾸면_버린다(self):
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다\n정말로")], ON,
            complete=_responder([{
                "id": 1, "before": "그렇게 됬다\n정말로", "after": "그렇게 됐다 정말로",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]),
        )
        assert flags == []
        assert any("줄바꿈 개수를 바꾸려 해" in n.message for n in notes)

    def test_한_줄을_통째로_다시_쓰면_버린다(self):
        flags, notes = propose_corrections(
            [_entry(1, "가나다 라마바 사아자 차카타")], ON,
            complete=_responder([{
                "id": 1, "before": "가나다 라마바 사아자 차카타",
                "after": "ㄱㄴㄷ ㄹㅁㅂ ㅅㅇㅈ ㅊㅋㅌ", "rule": "재작성",
                "declared": ["가나다 -> ㄱㄴㄷ", "라마바 -> ㄹㅁㅂ",
                             "사아자 -> ㅅㅇㅈ", "차카타 -> ㅊㅋㅌ"],
            }]),
        )
        assert flags == []
        assert any("재작성" in n.message for n in notes)

    def test_존재하지_않는_줄_번호는_버린다(self):
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON,
            complete=_responder([{
                "id": 99, "before": "아무거나", "after": "아무거나요",
                "rule": "지어냄", "declared": ["아무거나 -> 아무거나요"],
            }]),
        )
        assert flags == []
        assert any("존재하지 않는 줄 번호" in n.message for n in notes)


class TestRuleValidation:
    """모델이 붙인 이름표와 실제 바꾼 내용이 맞지 않는 제안을 막는다(2026-09-09).

    실측(exaone3.5:7.8b, 8~16줄 배치): 완전히 정상인 반말 종결어미를 존댓말로
    바꾸거나("싶다 -> 싶어요") 다른 반말 종결어미로 바꾸면서("계획이야? -> 계획이니?")
    그럴듯한 이름표를 달고 내놓았다 — 시스템 프롬프트가 명시적으로 금지한 말투 훼손이다.
    """

    def test_되돼라고_하고_말투를_바꾸면_버린다(self):
        flags, notes = propose_corrections(
            [_entry(1, "커피 마시면 되")], ON,
            complete=_responder([{
                "id": 1, "before": "커피 마시면 되", "after": "커피 마시면 돼요",
                "rule": "되/돼", "declared": ["되 -> 돼요"],
            }]),
        )
        assert flags == []
        assert any("실제 내용이 그" in n.message for n in notes)

    # 2026-09-16: "그 규칙의 차이만 있는가"로 검사한다.
    @pytest.mark.parametrize("rule, before, after, declared", [
        ("되/돼", "어떻게 됬어?", "어떻게 됐어?", "됬어 -> 됐어"),
        ("되/돼", "그러면 안되", "그러면 안 돼", "안되 -> 안 돼"),
        ("안/않", "밥을 않 먹었다", "밥을 안 먹었다", "않 -> 안"),
        ("로서/로써", "칼로서 깎았다", "칼로써 깎았다", "칼로서 -> 칼로써"),
    ])
    def test_그_규칙의_차이뿐이면_통과한다(self, rule, before, after, declared):
        flags, _ = propose_corrections(
            [_entry(1, before)], ON,
            complete=_responder([{
                "id": 1, "before": before, "after": after,
                "rule": rule, "declared": [declared],
            }]),
        )
        assert [f.suggested_fix for f in flags] == [after]

    @pytest.mark.parametrize("rule, before, after, declared", [
        # 되/돼라는 이름표로 반말을 존댓말로 바꿨다
        ("되/돼", "그렇게 됬어", "그렇게 됐어요", "됬어 -> 됐어요"),
        # 안/않이라는 이름표로 부정 표현을 통째로 바꿨다
        ("안/않", "안 했다", "하지 않았다", "안 했다 -> 하지 않았다"),
        ("로서/로써", "학생으로서", "학생이니까", "학생으로서 -> 학생이니까"),
        # 실제 자막에서 나온 것: 띄어쓰기만 고치고 되/돼·안/않 이름표를 달았다
        ("되/돼", "전화 좀 받고 올 게요", "전화 좀 받고 올게요", "올 게요 -> 올게요"),
        ("안/않", "도와 달라고요", "도와달라고요", "도와 달라고요 -> 도와달라고요"),
    ])
    def test_이름표와_다른_차이가_섞이면_버린다(self, rule, before, after, declared):
        flags, notes = propose_corrections(
            [_entry(1, before)], ON,
            complete=_responder([{
                "id": 1, "before": before, "after": after,
                "rule": rule, "declared": [declared],
            }]),
        )
        assert flags == []
        assert any("실제 내용이 그" in n.message for n in notes)

    def test_밝힌_쌍이_원문과_제안에_실제로_없으면_버린다(self):
        # 실제 자막(2026-09-16): 띄어쓰기만 바꾸고(형사 말로는 -> 형사말로는) 로서/로써
        # 이름표를 달아 목록에 올랐다. declared는 규칙 차이처럼 적혀 있어도 본문에 없다.
        flags, notes = propose_corrections(
            [_entry(1, "형사 말로는")], ON,
            complete=_responder([{
                "id": 1, "before": "형사 말로는", "after": "형사말로는",
                "rule": "로서/로써", "declared": ["형사 말로서 -> 형사말로써"],
            }]),
        )
        assert flags == []
        assert any("실제로 없는" in n.message for n in notes)

    @pytest.mark.parametrize("declared", ["말로는 ->말로써", "말로는→말로써", "로써로"])
    def test_쌍_형식이_어긋나도_검사를_건너뛰지_않는다(self, declared):
        # 실제 자막(2026-09-16): `말로는 ->말로써`(화살표 뒤 공백 없음)로 두 검사를 다
        # 건너뛰고 띄어쓰기만 바꾼 제안이 목록에 올랐다.
        flags, _ = propose_corrections(
            [_entry(1, "형사 말로는")], ON,
            complete=_responder([{
                "id": 1, "before": "형사 말로는", "after": "형사말로는",
                "rule": "로서/로써", "declared": [declared],
            }]),
        )
        assert flags == []

    def test_화살표_공백이_없어도_맞는_제안은_통과한다(self):
        flags, _ = propose_corrections(
            [_entry(1, "칼로서 깎았다")], ON,
            complete=_responder([{
                "id": 1, "before": "칼로서 깎았다", "after": "칼로써 깎았다",
                "rule": "로서/로써", "declared": ["칼로서->칼로써"],
            }]),
        )
        assert [f.suggested_fix for f in flags] == ["칼로써 깎았다"]

    # 2026-09-16 규칙 목록에서 뺀 둘. 스키마를 강제하지 못한 서버에서도 막혀야 한다.
    @pytest.mark.parametrize("rule, before, after, declared", [
        ("데/대", "그 사람이 범인이라던대", "그 사람이 범인이라던데", "던대 -> 던데"),
        ("전사 오류", "네", "네, 알겠습니다", "네 -> 네, 알겠습니다"),
        # 진짜 조사 교체여도 이제 이 패스의 일이 아니다(실제 자막에서 조사 제안 20건이 전부 말투 변경)
        ("조사", "그를 만났다", "그와 만났다", "그를 -> 그와"),
        ("조사", "싶다", "싶어요", "싶다 -> 싶어요"),
    ])
    def test_규칙_목록_밖_이름표는_버린다(self, rule, before, after, declared):
        flags, notes = propose_corrections(
            [_entry(1, before)], ON,
            complete=_responder([{
                "id": 1, "before": before, "after": after,
                "rule": rule, "declared": [declared],
            }]),
        )
        assert flags == []
        assert any("이 패스가 다루는 규칙이 아니라" in n.message for n in notes)

    def test_스키마와_프롬프트에서_뺀_규칙이_사라졌다(self):
        enum = llm_pass._RESPONSE_FORMAT["json_schema"]["schema"]["properties"]["proposals"][
            "items"]["properties"]["rule"]["enum"]
        assert "데/대" not in enum and "전사 오류" not in enum
        assert "데/대" not in llm_pass._SYSTEM_PROMPT
        assert "전사 오류" not in llm_pass._SYSTEM_PROMPT
        assert "조사" not in enum


class TestMultiLineSubtitle:
    """두 줄 자막이 요청문 형식을 깨지 않는다(2026-09-16).

    실제 자막 645줄 측정에서 차단 165건 중 118건이 '원문 오인용'이었다 — 자막 안의
    줄바꿈이 `번호<탭>내용` 형식을 깨서 모델이 첫 줄만 인용했다.
    """

    def test_요청문에서_한_자막은_한_줄이다(self):
        prompt = llm_pass._build_prompt([(7, "그렇게 됬다\n정말로"), (8, "다음 줄")])
        body = prompt.split("\n\n", 1)[1].splitlines()
        assert body == ["7\t그렇게 됬다⏎정말로", "8\t다음 줄"]

    def test_표시로_인용한_제안은_원래_줄바꿈으로_되돌려_받는다(self):
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다\n정말로")], ON,
            complete=_responder([{
                "id": 1, "before": "그렇게 됬다⏎정말로", "after": "그렇게 됐다⏎정말로",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]),
        )
        assert [f.suggested_fix for f in flags] == ["그렇게 됐다\n정말로"]
        assert not any("차단" in n.message for n in notes)

    def test_표시를_지우면_줄바꿈_변경으로_막힌다(self):
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다\n정말로")], ON,
            complete=_responder([{
                "id": 1, "before": "그렇게 됬다⏎정말로", "after": "그렇게 됐다 정말로",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]),
        )
        assert flags == []
        assert any("줄바꿈 개수를 바꾸려 해" in n.message for n in notes)

    def test_원문에_표시_글자가_있으면_보내지_않는다(self):
        sent = []
        propose_corrections(
            [_entry(1, "재생 ⏎ 버튼")], ON,
            complete=lambda prompt, settings: sent.append(prompt) or '{"proposals": []}',
        )
        assert sent == []


class TestSkipping:
    def test_보호된_화자의_줄은_모델에게_보내지_않는다(self):
        sent = {}

        def _capture(prompt, settings):
            sent["prompt"] = prompt
            return "[]"

        propose_corrections(
            [_entry(1, "그카데예"), _entry(2, "그렇게 됬다")], ON,
            skip_indices={1}, complete=_capture,
        )
        assert "그카데예" not in sent["prompt"]
        assert "그렇게 됬다" in sent["prompt"]

    def test_보호_표지가_있는_줄은_건너뛴다(self):
        sent = {}

        def _capture(prompt, settings):
            sent["prompt"] = prompt
            return "[]"

        markers = normalize_subtitle_markers(position="{\\an8}")
        propose_corrections(
            [_entry(1, "{\\an8}화면 위쪽"), _entry(2, "그렇게 됬다")], ON,
            markers=markers, complete=_capture,
        )
        assert "화면 위쪽" not in sent["prompt"]
        assert "그렇게 됬다" in sent["prompt"]

    def test_빈_줄만_있으면_호출하지_않는다(self):
        def _boom(prompt, settings):
            raise AssertionError("보낼 줄이 없는데 모델을 불렀다")

        flags, notes = propose_corrections([_entry(1, "   ")], ON, complete=_boom)
        assert flags == [] and notes == []

    def test_상한을_넘기면_건너뛴_사실을_알린다(self):
        entries = [_entry(i, f"{i}번 대사 됬다") for i in range(1, 6)]
        flags, notes = propose_corrections(
            entries, ON._replace(max_lines=2), complete=_responder([]),
        )
        assert any("뒤쪽 3줄은 모델이 보지 않았습니다" in n.message for n in notes)


class TestTerminalControl:
    """`ollama run`이 섞어 보내는 커서 제어 코드를 화면 결과로 복원한다.

    2026-08-12 실측: 이것 때문에 모든 응답이 JSON 파싱에 실패해 제안이 0건으로
    나왔다. 코드를 **떼기만** 하면 안 된다 — `\\x1b[1D\\x1b[K`는 직전 글자를
    없애라는 뜻이라, 떼기만 하면 지워졌어야 할 글자가 남아 그대로 깨진다.
    """

    def test_직전_글자를_지우는_코드를_흉내_낸다(self):
        from subtitle_corrector.engine.llm_pass import _render_terminal

        assert _render_terminal("abc\x1b[1D\x1b[K") == "ab"

    def test_캐리지리턴은_같은_줄을_덮어쓴다(self):
        from subtitle_corrector.engine.llm_pass import _render_terminal

        assert _render_terminal("가나다\r라") == "라나다"

    def test_깨진_JSON이_복원돼_파싱된다(self):
        raw = '[{"id": 1, "before": "그렇게 됬다", "after": "그렇게 됐다", "rule": "되/돼",X\x1b[1D\x1b[K "declared": ["됬다 -> 됐다"]}]'
        flags, _ = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON, complete=_raw_responder(raw)
        )
        assert len(flags) == 1


class TestResilience:
    def test_코드펜스로_감싸도_읽는다(self):
        raw = (
            "확인했습니다.\n```json\n"
            '[{"id": 1, "before": "그렇게 됬다", "after": "그렇게 됐다",'
            ' "rule": "되/돼", "declared": ["됬다 -> 됐다"]}]\n```'
        )
        flags, _ = propose_corrections([_entry(1, "그렇게 됬다")], ON, complete=_raw_responder(raw))
        assert len(flags) == 1

    def test_형식이_깨진_응답은_검토되지_않았다고_알린다(self):
        """조용히 넘기면 "모델이 괜찮다고 했다"로 읽힌다(2026-09-01 변경).

        검토된 구간과 검토되지 않은 구간이 같은 빈 결과로 보이면 안 된다 —
        `search_dialect()`가 장애와 매칭 없음을 구분 못 해 겪은 일과 같은 자리다.
        교정 자체는 그대로 계속된다.
        """
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON, complete=_raw_responder("죄송합니다, 못 하겠습니다"),
        )
        assert flags == []
        assert any("모델 응답 형식 오류" in n.message for n in notes)
        assert any("검토되지 않은 것으로" in n.message for n in notes)

    def test_고칠_것이_없다는_응답은_알리지_않는다(self):
        """빈 목록은 정상이다. 형식 오류와 뭉개지 않는지 확인한다."""
        flags, notes = propose_corrections(
            [_entry(1, "정상 문장입니다")], ON, complete=_raw_responder('{"proposals": []}'),
        )
        assert flags == []
        assert not any("형식 오류" in n.message for n in notes)

    def test_호출이_실패해도_교정은_계속된다(self):
        def _fail(prompt, settings):
            raise ConnectionError("연결 거부")

        flags, notes = propose_corrections([_entry(1, "그렇게 됬다")], ON, complete=_fail)
        assert flags == []
        assert any("모델 호출 실패" in n.message for n in notes)
        assert any("모델 제안이 하나도 반영되지 않았습니다" in n.message for n in notes)


class TestOutputSchema:
    """출력 형식을 지시문(부탁)이 아니라 서버(강제)에 맡기는지 고정한다.

    지시문은 확률적으로만 지켜진다 — 모델은 코드펜스를 붙이고 설명을 앞에 단다.
    `response_format`을 거는 서버에서는 그 응답 자체가 나올 수 없다.
    """

    def test_객체_형식_응답을_읽는다(self):
        payload = {
            "proposals": [{
                "id": 1, "before": "그렇게 됬다", "after": "그렇게 됐다",
                "rule": "되/돼", "declared": ["됬다 -> 됐다"],
            }]
        }
        flags, _ = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON,
            complete=_raw_responder(json.dumps(payload, ensure_ascii=False)),
        )
        assert len(flags) == 1

    def test_맨_배열_응답도_계속_읽는다(self):
        """스키마를 못 거는 서버는 예전 형식으로 답한다. 그 경로가 살아 있어야 한다."""
        payload = [{
            "id": 1, "before": "그렇게 됬다", "after": "그렇게 됐다",
            "rule": "되/돼", "declared": ["됬다 -> 됐다"],
        }]
        flags, _ = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON,
            complete=_raw_responder(json.dumps(payload, ensure_ascii=False)),
        )
        assert len(flags) == 1

    def test_요청에_스키마를_실어_보낸다(self, monkeypatch):
        sent = _record_posts(monkeypatch, lambda body: _FakeResponse())
        llm_pass._chat("프롬프트", ON)
        assert sent[0]["response_format"]["type"] == "json_schema"
        assert sent[0]["response_format"]["json_schema"]["strict"] is True

    def test_서버가_거절하면_스키마를_빼고_한_번만_다시_부른다(self, monkeypatch):
        def _responder(body):
            return _FakeResponse(status_code=400) if "response_format" in body else _FakeResponse()

        sent = _record_posts(monkeypatch, _responder)
        llm_pass._chat("프롬프트", ON)

        assert len(sent) == 2
        assert "response_format" in sent[0]
        assert "response_format" not in sent[1]
        assert llm_pass._SCHEMA_SUPPORT[(ON.base_url, ON.model)] is False

    def test_거절당한_조합에는_두_번_다시_시도하지_않는다(self, monkeypatch):
        """구간마다 두 번씩 부르면 호출 수가 그대로 두 배가 된다."""
        sent = _record_posts(monkeypatch, lambda body: _FakeResponse())
        llm_pass._SCHEMA_SUPPORT[(ON.base_url, ON.model)] = False

        llm_pass._chat("프롬프트", ON)

        assert len(sent) == 1
        assert "response_format" not in sent[0]

    def test_서버_장애는_기능을_끄지_않는다(self, monkeypatch):
        """500은 서버가 잠깐 아픈 것이지 스키마 자리를 모르는 것이 아니다."""
        sent = _record_posts(monkeypatch, lambda body: _FakeResponse(status_code=500))
        try:
            llm_pass._chat("프롬프트", ON)
        except requests.HTTPError:
            pass

        assert len(sent) == 1
        assert llm_pass._SCHEMA_SUPPORT[(ON.base_url, ON.model)] is True
