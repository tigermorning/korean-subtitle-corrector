"""언어 모델 패스 회귀 테스트(2026-08-12).

이 패스의 위험은 "모델이 좋은 제안을 못 한다"가 아니라 **"나쁜 제안이 목록에 오른다"**
이다. 화면의 제안은 사람이 누르면 그대로 반영되고, 한 편에 수백 건이 뜨면 하나씩
검증되지 않는다. 그래서 여기 고정하는 불변식은 전부 "무엇이 걸러지는가"다.

모델 호출은 주입한 가짜 함수로 대체하므로 네트워크가 필요 없다.
"""

import json

from subtitle_corrector.engine import LlmSettings, normalize_llm_settings, propose_corrections
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


class TestSettings:
    def test_기본값은_꺼짐(self):
        assert normalize_llm_settings().enabled is False

    def test_주소나_모델이_없으면_켤_수_없다(self):
        assert normalize_llm_settings(enabled=True, base_url="", model="m").enabled is False
        assert normalize_llm_settings(enabled=True, base_url="http://x/v1", model="").enabled is False

    def test_둘_다_있으면_켜진다(self):
        settings = normalize_llm_settings(enabled=True, base_url="http://x/v1/", model="m")
        assert settings.enabled is True
        assert settings.base_url == "http://x/v1"  # 끝의 슬래시는 떼어 낸다

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


class TestResilience:
    def test_코드펜스로_감싸도_읽는다(self):
        raw = (
            "확인했습니다.\n```json\n"
            '[{"id": 1, "before": "그렇게 됬다", "after": "그렇게 됐다",'
            ' "rule": "되/돼", "declared": ["됬다 -> 됐다"]}]\n```'
        )
        flags, _ = propose_corrections([_entry(1, "그렇게 됬다")], ON, complete=_raw_responder(raw))
        assert len(flags) == 1

    def test_깨진_응답은_조용히_무시한다(self):
        flags, notes = propose_corrections(
            [_entry(1, "그렇게 됬다")], ON, complete=_raw_responder("죄송합니다, 못 하겠습니다"),
        )
        assert flags == [] and notes == []

    def test_호출이_실패해도_교정은_계속된다(self):
        def _fail(prompt, settings):
            raise ConnectionError("연결 거부")

        flags, notes = propose_corrections([_entry(1, "그렇게 됬다")], ON, complete=_fail)
        assert flags == []
        assert any("모델 호출 실패" in n.message for n in notes)
        assert any("모델 제안이 하나도 반영되지 않았습니다" in n.message for n in notes)
