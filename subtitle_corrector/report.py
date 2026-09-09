"""플래그 리포트 파일 (csv) 읽기/쓰기"""

import csv
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class FlagItem:
    line_index: int
    original_text: str
    reason: str
    suggested_fix: str = ""
    # 외래어 음차로 의심되는 토막. 값이 있으면 화면이 이 플래그에 **원어 입력칸**을
    # 띄운다 — 음차의 정답은 원어가 무엇이냐로 갈리므로(`러스`는 Ruth면 `루스`,
    # Russ면 `러스`), 텍스트만 보고는 정할 수 없다(§57·docs/log-archive/2026-h2.md §61). 사용자가 원어를 넣으면
    # `/api/loanword-source`가 국립국어원 용례로 확정 표기를 돌려준다.
    source_lookup_token: str = ""
    # 판정 기록장(feedback.py)이 쓰는 구조화된 출처. `reason` 문구 앞부분을 다시
    # 파싱해서 "모델 제안인가 규칙 제안인가"를 알아내던 것을 대신한다 — 표시 문구는
    # 사람이 읽기 좋게 자유로이 바뀌는데, 그걸 다시 정규식으로 갈랐더니 대괄호가 없는
    # 규칙 엔진 flag는 전부 rule=""로 뭉개졌다(AppliedNote와 같은 이유로 문자열
    # 재파싱을 피한다).
    source: str = "rule"
    rule: str = ""


@dataclass
class AppliedNote:
    """자동 교정 로그 한 줄.

    `line_index`가 None이면 문서 전체에 대한 안내다(사투리 기준, 사전 조회 실패 등).
    `is_edit`가 참이면 그 줄의 텍스트를 실제로 바꾼 기록이고, 거짓이면 무언가를
    **하지 않았다**는 안내다(예: "[붙임 불가] …").

    문자열 하나로 두지 않고 구조로 남기는 이유: 화면의 "되돌리기"가 줄 단위로
    동작하는데, `"[12] …"` 같은 문자열을 다시 파싱해서는 줄 기록과 안내문을
    가릴 수 없다. 파싱은 로그 문구를 바꿀 때마다 조용히 깨진다.
    """

    message: str
    line_index: int | None = None
    is_edit: bool = False

    def text(self) -> str:
        """사람이 읽는 한 줄(CLI 출력·기존 로그 표기와 같은 형태)."""
        return f"[{self.line_index}] {self.message}" if self.line_index is not None else self.message


_FIELDS = [
    "line_index", "original_text", "reason", "suggested_fix", "source_lookup_token",
    "source", "rule", "engine_suggestion",
]


def write_report(items: list[FlagItem], path: Path) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writeheader()
        for item in items:
            row = asdict(item)
            # `suggested_fix`는 사람이 손으로 고쳐 쓰는 칸이다. 엔진이 애초에 무엇을
            # 제안했는지가 지워지면 `apply-report`가 나중에 "제안대로 받았는가/사람이
            # 손봤거나 지웠는가"를 가릴 수 없다 — 이 얼어붙은 사본이 그 기준이 된다.
            row["engine_suggestion"] = item.suggested_fix
            writer.writerow(row)


def read_report(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
