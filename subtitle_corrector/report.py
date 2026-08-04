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


_FIELDS = ["line_index", "original_text", "reason", "suggested_fix"]


def write_report(items: list[FlagItem], path: Path) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def read_report(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
