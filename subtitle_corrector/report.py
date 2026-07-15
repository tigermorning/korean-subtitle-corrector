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
