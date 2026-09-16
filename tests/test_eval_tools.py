"""평가 도구 자체의 회귀 테스트(2026-09-16).

평가 도구가 틀리면 엔진이 아니라 눈금자가 휜다. 여기 고정하는 것은 셋이다.

- `run_eval.py`가 실패를 종류별로 가른다 — 놓침과 과교정은 같은 FAIL이 아니다.
- `audit_llm_pass.py`의 채점이 규칙별 정답·오교정·과교정·forbid 위반을 제자리에 센다.
- 언어 모델 전용 평가셋이 시스템 프롬프트 예시와 겹치지 않고, 규칙마다 같은 수다.
  프롬프트 예시를 바꾸다 평가 문항과 겹치게 되면 점수가 조용히 부풀려진다.

네트워크·모델 호출 없음.
"""

import collections
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_eval = _load("run_eval", ROOT / "examples" / "eval" / "run_eval.py")
audit = _load("audit_llm_pass", ROOT / "tools" / "audit_llm_pass.py")


def _flag(fix):
    return SimpleNamespace(suggested_fix=fix, original_text="", rule="되/돼")


class TestRunEvalActions:
    def test_기대_행동은_gold와_플래그_기대로_정해진다(self):
        assert run_eval.expected_action({"input": "로보트", "gold": "로봇"}) == "FIX"
        assert run_eval.expected_action({"input": "수있다", "gold": "수있다", "expect_flag": True}) == "FLAG"
        assert run_eval.expected_action({"input": "도리어", "gold": "도리어", "trap": True}) == "KEEP"

    def test_실제_행동은_텍스트_변경이_플래그보다_먼저다(self):
        item = {"input": "가", "gold": "가"}
        assert run_eval.actual_action(item, "나", [_flag("다")]) == "FIX"
        assert run_eval.actual_action(item, "가", [_flag("다")]) == "FLAG"
        assert run_eval.actual_action(item, "가", [_flag("")]) == "KEEP"

    def test_놓침은_위험한_실패가_아니다(self):
        assert run_eval.danger({"input": "로보트", "gold": "로봇"}, "로보트") == ""

    def test_맞는_원문을_바꾸면_과교정이다(self):
        assert run_eval.danger({"input": "도리어", "gold": "도리어", "trap": True}, "되레") == "과교정"

    def test_엉뚱한_쪽으로_고치면_오교정이다(self):
        assert run_eval.danger({"input": "로보트", "gold": "로봇"}, "로보또") == "오교정"

    def test_gold_alt도_정답으로_인정한다(self):
        item = {"input": "초과근무했다", "gold": "초과 근무했다", "gold_alt": ["초과근무 했다"]}
        assert run_eval.danger(item, "초과근무 했다") == ""


class TestAuditScoring:
    @pytest.fixture(autouse=True)
    def _no_dictionary(self, monkeypatch):
        monkeypatch.setattr(audit, "invaded_standard", lambda before, after: [])

    def _line(self, fixes=(), blocked=0):
        return {"after_rules": "", "proposals": [_flag(f) for f in fixes],
                "blocked": [("이름표 불일치", "", "", "msg")] * blocked}

    def test_규칙별로_맞힘_오교정_놓침_과교정을_가른다(self):
        items = [
            {"id": "d01", "rule": "되/돼", "split": "positive", "input": "됬네", "gold": "됐네"},
            {"id": "d02", "rule": "되/돼", "split": "positive", "input": "되?", "gold": "돼?"},
            {"id": "d03", "rule": "되/돼", "split": "positive", "input": "되요", "gold": "돼요"},
            {"id": "d04", "rule": "되/돼", "split": "negative", "input": "됐네", "gold": "됐네"},
            {"id": "d05", "rule": "되/돼", "split": "negative", "input": "돼요", "gold": "돼요"},
        ]
        by_line = {
            1: self._line(["됐네"]),      # 맞힘
            2: self._line(["돼요?"]),     # 오교정
            3: self._line(),              # 놓침
            4: self._line(["됬네"]),      # 과교정(목록에 오름)
            5: self._line(blocked=1),     # 과교정 시도(게이트가 막음)
        }
        b = audit.score_eval(items, by_line)["rules"]["되/돼"]
        assert (b["tp"], b["wrong"], b["miss"]) == (1, 1, 1)
        assert (b["overfix"], b["overfix_attempted"]) == (1, 2)
        assert b["precision"] == pytest.approx(1 / 3)
        assert b["recall"] == pytest.approx(1 / 3)

    def test_forbid는_막힌_제안도_따로_센다(self):
        items = [
            {"id": "f01", "rule": None, "split": "forbid", "input": "밥 먹었냐?", "gold": "밥 먹었냐?"},
            {"id": "f02", "rule": None, "split": "forbid", "input": "몰라", "gold": "몰라"},
        ]
        score = audit.score_eval(items, {1: self._line(["밥 먹었니?"]), 2: self._line(blocked=1)})
        assert score["forbid"] == {"lines": 2, "surfaced": 1, "attempted": 2}


class TestLlmPassEvalSet:
    ITEMS = [json.loads(line) for line in
             (ROOT / "examples" / "eval" / "llm_pass" / "llm_pass.jsonl")
             .read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_프롬프트_예시와_겹치는_문항이_없다(self):
        leaks = {i["id"]: audit.prompt_leaks(i["input"]) for i in self.ITEMS}
        assert {k: v for k, v in leaks.items() if v} == {}

    def test_누수_검출기는_예전_평가셋의_t11을_잡는다(self):
        assert audit.prompt_leaks("학생으로서 할 일을 했다") == ["학생으로서"]

    def test_규칙마다_positive와_negative_수가_같다(self):
        counts = collections.Counter((i["rule"], i["split"]) for i in self.ITEMS
                                    if i["split"] in ("positive", "negative"))
        rules = {rule for rule, _ in counts}
        assert len({counts[(r, "positive")] for r in rules}) == 1
        assert len({counts[(r, "negative")] for r in rules}) == 1

    def test_생성_스크립트와_파일이_같다(self):
        builder = _load("build_llm_pass_set",
                        ROOT / "examples" / "eval" / "llm_pass" / "build_llm_pass_set.py")
        assert builder.build() == self.ITEMS
