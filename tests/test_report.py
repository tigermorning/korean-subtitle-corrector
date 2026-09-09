"""플래그 리포트 CSV 왕복 회귀 테스트.

여기서 고정하는 것: `write_report()`가 사람이 손으로 고쳐 쓰는 `suggested_fix`와
나란히 `engine_suggestion`(엔진이 처음 제안한 값의 얼어붙은 사본)을 함께 적는다는
계약. `feedback.decisions_from_report_rows()`가 이 둘을 비교해 채택/기각을 가리므로,
둘 중 하나라도 깨지면 그 판정이 조용히 틀어진다.
"""

import csv

from subtitle_corrector.report import FlagItem, read_report, write_report


def test_engine_suggestion은_suggested_fix의_얼어붙은_사본이다(tmp_path):
    path = tmp_path / "report.csv"
    write_report([
        FlagItem(line_index=1, original_text="됬다", reason="[모델 제안] 되/돼 — 됬다 -> 됐다",
                  suggested_fix="됐다", source="model", rule="되/돼"),
    ], path)

    rows = read_report(path)
    assert rows[0]["engine_suggestion"] == "됐다"
    assert rows[0]["suggested_fix"] == "됐다"
    assert rows[0]["source"] == "model"
    assert rows[0]["rule"] == "되/돼"


def test_사람이_수정해도_engine_suggestion은_그대로다(tmp_path):
    """사람이 `suggested_fix` 칸만 지워도(반려), `engine_suggestion` 칸은 손대지
    않았으니 엔진이 애초에 무엇을 제안했는지가 남아 있어야 한다."""
    path = tmp_path / "report.csv"
    write_report([FlagItem(line_index=1, original_text="됬다", reason="", suggested_fix="됐다")], path)

    rows = read_report(path)
    rows[0]["suggested_fix"] = ""  # 사람이 반려하며 지웠다고 가정
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    reread = read_report(path)
    assert reread[0]["suggested_fix"] == ""
    assert reread[0]["engine_suggestion"] == "됐다"


def test_기본값은_규칙_엔진이다():
    item = FlagItem(line_index=1, original_text="x", reason="y")
    assert item.source == "rule"
    assert item.rule == ""
