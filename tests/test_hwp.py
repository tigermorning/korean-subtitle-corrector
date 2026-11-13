"""한글 문서(.hwp/.hwpx) 입력 — kordoc 마크다운을 교정할 줄로 바꾸는 부분.

kordoc 자체(Node.js)는 부르지 않는다. 실제 파일 읽기는 2026-11-13 kordoc 4.24.71
내장 기안문 서식으로 만든 HWPX로 손으로 확인했다(CLI correct, 자동 교정 3건).
"""
from subtitle_corrector.file_io import SUBTITLE_EXTENSIONS, is_supported
from subtitle_corrector.parsers import markdown_to_lines


def test_hwp_extensions_supported_as_documents():
    assert is_supported(".hwp") and is_supported(".HWPX")
    assert ".hwp" not in SUBTITLE_EXTENSIONS and ".hwpx" not in SUBTITLE_EXTENSIONS


def test_markdown_marks_stripped():
    md = "**가상시청**\n\n## 회의 결과\n\n오늘은날씨가좋네요.\n"
    assert markdown_to_lines(md) == ["가상시청", "회의 결과", "오늘은날씨가좋네요."]


def test_table_cells_become_lines():
    md = "| 항목 | 내용 |\n| --- | --- |\n| 장소 | 회의실 |\n"
    assert markdown_to_lines(md) == ["항목", "내용", "장소", "회의실"]
