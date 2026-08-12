"""판정 기록장 회귀 테스트(2026-08-12).

여기 고정하는 불변식은 둘이다.

1. **켜지 않으면 아무것도 쓰이지 않는다.** 쌓이는 것은 남의 원고이므로, 기본값이
   조용히 켜져 있는 사고가 나면 안 된다.
2. **기록이 실패해도 교정은 살아남는다.** 이 기능은 부수 작업이라 어떤 예외도
   밖으로 나가서는 안 된다.

`FEEDBACK_LOG_DIR`은 모듈을 읽을 때 한 번 정해지므로, 테스트에서는 모듈 속성을
직접 갈아 끼우고 끝나면 되돌린다.
"""

import json

import pytest

from subtitle_corrector import feedback


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    """기록장을 임시 폴더로 켠다."""
    monkeypatch.setattr(feedback, "FEEDBACK_LOG_DIR", str(tmp_path))
    return tmp_path


def _records(directory):
    lines = []
    for path in sorted(directory.glob("decisions-*.jsonl")):
        lines.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return lines


def _decision(before="그렇게 됬다", after="그렇게 됐다", accepted=True, reason="[모델 제안] 되/돼 — 됬다 -> 됐다"):
    return {"line_index": 1, "before": before, "after": after, "accepted": accepted, "reason": reason}


class TestDisabledByDefault:
    def test_경로가_없으면_꺼져_있다(self, monkeypatch):
        monkeypatch.setattr(feedback, "FEEDBACK_LOG_DIR", "")
        assert feedback.is_enabled() is False

    def test_꺼져_있으면_한_줄도_쓰지_않는다(self, tmp_path, monkeypatch):
        monkeypatch.setattr(feedback, "FEEDBACK_LOG_DIR", "")
        assert feedback.record_decisions([_decision()]) == 0
        assert list(tmp_path.iterdir()) == []

    def test_꺼져_있으면_통계도_비어_있다(self, monkeypatch):
        monkeypatch.setattr(feedback, "FEEDBACK_LOG_DIR", "")
        assert feedback.summarize() == {
            "enabled": False, "total": 0, "accepted": 0, "by_source": {},
        }


class TestRecording:
    def test_채택과_미채택을_모두_남긴다(self, log_dir):
        written = feedback.record_decisions([
            _decision(accepted=True),
            _decision(before="안되요", after="안 돼요", accepted=False),
        ])
        assert written == 2
        records = _records(log_dir)
        assert [r["accepted"] for r in records] == [True, False]

    def test_짝이_성립하지_않는_것은_버린다(self, log_dir):
        written = feedback.record_decisions([
            {"before": "", "after": "무언가", "accepted": True},        # 원문 없음
            {"before": "무언가", "after": "", "accepted": True},        # 제안 없음
            {"before": "같다", "after": "같다", "accepted": True},      # 바뀐 것 없음
            "문자열",                                                    # 형식이 아예 다름
        ])
        assert written == 0
        assert _records(log_dir) == []

    def test_모델_제안과_규칙_제안을_구분한다(self, log_dir):
        feedback.record_decisions([
            _decision(reason="[모델 제안] 되/돼 — 됬다 -> 됐다"),
            _decision(before="한번 더", after="한 번 더", reason="[제42항] 의존명사는 띄어 씁니다"),
        ])
        records = _records(log_dir)
        assert records[0]["source"] == "model" and records[0]["rule"] == "되/돼"
        assert records[1]["source"] == "rule" and records[1]["rule"] == "제42항"

    def test_원문_전문은_저장하지_않는다(self, log_dir):
        doc = "대사 전문이 여기 통째로 들어 있다"
        feedback.record_decisions([_decision()], doc_hash=feedback.document_id(doc))
        raw = "".join(p.read_text(encoding="utf-8") for p in log_dir.glob("*.jsonl"))
        assert doc not in raw
        assert len(_records(log_dir)[0]["doc"]) == 12

    def test_같은_원고는_같은_해시다(self):
        assert feedback.document_id("가나다") == feedback.document_id("가나다")
        assert feedback.document_id("가나다") != feedback.document_id("가나다라")

    def test_한_번에_받는_건수에_상한이_있다(self, log_dir):
        written = feedback.record_decisions(
            [_decision(before=f"됬다{i}", after=f"됐다{i}") for i in range(feedback.MAX_RECORDS_PER_CALL + 50)]
        )
        assert written == feedback.MAX_RECORDS_PER_CALL

    def test_긴_필드는_잘라서_저장한다(self, log_dir):
        feedback.record_decisions([_decision(before="가" * 5000, after="나" * 5000)])
        record = _records(log_dir)[0]
        assert len(record["before"]) == feedback.MAX_FIELD_LENGTH


class TestResilience:
    def test_쓸_수_없는_경로여도_예외가_나가지_않는다(self, monkeypatch, tmp_path):
        blocker = tmp_path / "파일"
        blocker.write_text("폴더가 아니라 파일이다", encoding="utf-8")
        monkeypatch.setattr(feedback, "FEEDBACK_LOG_DIR", str(blocker / "안쪽"))
        assert feedback.record_decisions([_decision()]) == 0

    def test_깨진_줄이_섞여도_통계가_난다(self, log_dir):
        feedback.record_decisions([_decision()])
        path = next(log_dir.glob("*.jsonl"))
        with open(path, "a", encoding="utf-8") as log:
            log.write("이건 JSON이 아니다\n")
        summary = feedback.summarize()
        assert summary["total"] == 1 and summary["accepted"] == 1


class TestEndpoint:
    """웹 창구는 사용자의 작업을 절대 막지 않는다 — 무엇이 들어와도 200이다."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from subtitle_corrector.api import app

        return TestClient(app)

    def test_꺼져_있으면_그렇다고_답한다(self, client, monkeypatch):
        monkeypatch.setattr(feedback, "FEEDBACK_LOG_DIR", "")
        response = client.post("/api/feedback", data={"decisions": "[]", "document": ""})
        assert response.status_code == 200
        assert response.json() == {"enabled": False, "recorded": 0}

    def test_켜져_있으면_기록하고_건수를_돌려준다(self, client, log_dir):
        response = client.post(
            "/api/feedback",
            data={"decisions": json.dumps([_decision()], ensure_ascii=False), "document": "원고"},
        )
        assert response.status_code == 200
        assert response.json() == {"enabled": True, "recorded": 1}
        assert len(_records(log_dir)) == 1

    def test_깨진_JSON이_와도_200이다(self, client, log_dir):
        response = client.post("/api/feedback", data={"decisions": "{이건 JSON이 아니다", "document": ""})
        assert response.status_code == 200
        assert response.json()["recorded"] == 0

    def test_배열이_아닌_값이_와도_200이다(self, client, log_dir):
        response = client.post("/api/feedback", data={"decisions": '{"a": 1}', "document": ""})
        assert response.status_code == 200
        assert response.json()["recorded"] == 0

    def test_통계_창구가_열려_있다(self, client, log_dir):
        feedback.record_decisions([_decision()])
        body = client.get("/api/feedback/summary").json()
        assert body["enabled"] is True and body["total"] == 1


class TestSummary:
    def test_출처별로_센다(self, log_dir):
        feedback.record_decisions([
            _decision(accepted=True, reason="[모델 제안] 되/돼 — 됬다 -> 됐다"),
            _decision(before="안되요", after="안 돼요", accepted=False,
                      reason="[모델 제안] 안/않 — 안되요 -> 안 돼요"),
            _decision(before="한번 더", after="한 번 더", accepted=True, reason="[제42항] …"),
        ])
        summary = feedback.summarize()
        assert summary["total"] == 3 and summary["accepted"] == 2
        assert summary["by_source"]["model"] == {"total": 2, "accepted": 1}
        assert summary["by_source"]["rule"] == {"total": 1, "accepted": 1}
