"""업로드한 파일을 **그대로** 읽는지 고정하는 테스트.

2026-08-03 사용자 지적: "사용자가 업로드한 원문 그대로를 가져와 교정해야 한다." 파싱이
원문을 바꿔 놓으면 그 뒤 교정이 정확해도 다른 문서를 고친 것이 된다. 인코딩·개행이 다른
실제 자막 파일 형태를 모두 넣어 고정한다.
"""
import pytest

from subtitle_corrector.decoding import (
    decode_bytes,
    detect_encoding,
    verify_ingest_fidelity,
)
from subtitle_corrector.file_io import parse_file

BODY = (
    "1\n00:00:01,000 --> 00:00:03,000\n안녕하세요\n두 번째 줄입니다\n\n"
    "2\n00:00:04,000 --> 00:00:06,000\n두칸  띄었다\n\n"
    "3\n00:00:07,000 --> 00:00:09,000\n　전각 공백으로 시작\n"
)

CASES = {
    "utf8": (BODY.encode("utf-8"), "utf-8"),
    "utf8_bom": (b"\xef\xbb\xbf" + BODY.encode("utf-8"), "utf-8-sig"),
    "cp949": (BODY.encode("cp949"), "cp949"),
    # 윈도우 자막 도구가 만드는 .srt는 대부분 CRLF다. read_bytes()로 바꾸면서 개행
    # 정규화를 빼먹었더니 파일 전체가 자막 한 항목으로 뭉쳤다(타임코드까지 대사에 섞임).
    "crlf": (BODY.replace("\n", "\r\n").encode("utf-8"), "utf-8"),
    "cr_only": (BODY.replace("\n", "\r").encode("utf-8"), "utf-8"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_parsed_entries_match_the_uploaded_file(tmp_path, name):
    data, expected_encoding = CASES[name]
    path = tmp_path / f"{name}.srt"
    path.write_bytes(data)

    assert detect_encoding(path) == expected_encoding

    entries = parse_file(path)
    assert [e.index for e in entries] == [1, 2, 3]
    assert entries[0].text == "안녕하세요\n두 번째 줄입니다"
    assert entries[1].text == "두칸  띄었다"  # 두 칸 공백이 한 칸으로 줄지 않는다
    assert entries[2].text == "　전각 공백으로 시작"

    source_text, _encoding = decode_bytes(data)
    assert verify_ingest_fidelity(source_text, [e.text for e in entries]) == []


def test_fidelity_check_catches_a_parser_that_changes_the_text():
    """검사 자체가 동작하는지 — 없는 대사를 넣으면 잡아내야 한다."""
    problems = verify_ingest_fidelity("안녕하세요", ["안녕 하세요"])
    assert len(problems) == 1
    assert "원문에 그대로 없습니다" in problems[0]


def test_undecodable_bytes_are_not_guessed():
    """어떤 인코딩으로도 못 읽으면 글자를 추측해 채우지 않고 실패한다."""
    with pytest.raises(UnicodeDecodeError):
        decode_bytes(b"\x80\x80\x80")  # utf-8·cp949·euc-kr 모두 못 읽는 바이트


class TestEditGuard:
    """설명되지 않는 낱말 변경은 자동 교정에서 통과하지 못한다(2026-08-03 추가).

    개별 규칙을 고치는 방식으로는 원문 왜곡이 끝나지 않는다 — 새 규칙마다 같은 부류가
    다시 생긴다. 그래서 규칙이 스스로 밝힌 편집으로 결과를 재구성할 수 있는지 검사하고,
    설명되지 않으면 그 규칙의 결과를 버린다(fail-closed).
    """

    def test_declared_substitution_passes(self):
        from subtitle_corrector.engine.edit_guard import verify_edit

        accepted, refusal = verify_edit(
            "규범 표기", "눈쌀을 찌푸렸다", "눈살을 찌푸렸다", ["눈쌀 -> 눈살"]
        )
        assert accepted == "눈살을 찌푸렸다"
        assert refusal is None

    def test_particle_allomorph_is_allowed(self):
        """낱말을 바꾸면 뒤 조사도 함께 바뀌는데 로그에는 낱말만 남는다."""
        from subtitle_corrector.engine.edit_guard import verify_edit

        accepted, refusal = verify_edit(
            "규범 표기", "새 로보트를 샀다", "새 로봇을 샀다", ["로보트 -> 로봇"]
        )
        assert accepted == "새 로봇을 샀다"
        assert refusal is None

    def test_spacing_only_change_passes(self):
        from subtitle_corrector.engine.edit_guard import verify_edit

        accepted, refusal = verify_edit("띄어쓰기", "밥을먹었다", "밥을 먹었다", [])
        assert accepted == "밥을 먹었다"
        assert refusal is None

    def test_undeclared_word_change_is_rejected(self):
        """사투리 표 사고(§52)가 이 검사만으로 막힌다 — 규칙을 고치지 않아도."""
        from subtitle_corrector.engine.edit_guard import verify_edit

        accepted, refusal = verify_edit(
            "사투리", "그래 노래를 불렀다", "그라고 노라고를 불렀다", []
        )
        assert accepted == "그래 노래를 불렀다"  # 원문을 그대로 유지한다
        assert refusal and "자동 교정 차단" in refusal


def test_api_outage_is_reported_not_silent(monkeypatch):
    """사전 조회가 실패하면 그 사실을 리포트에 남긴다(2026-08-04 추가).

    조회 실패는 "등재된 표기 없음"과 같은 경로로 흡수된다 — 크래시보다 안전하지만, 그러면
    그 부류 교정이 **조용히** 건너뛰어진다. kornorms가 DNS 단계에서 안 붙는 동안
    '판넬 -> 패널'이 그냥 통과했고 화면에는 아무 표시도 없었다.
    """
    from subtitle_corrector import parsers
    from subtitle_corrector.dictionary import clients
    from subtitle_corrector.engine import correct_entries

    def boom(*_args, **_kwargs):
        clients.note_lookup_failure("어문 규범 용례(kornorms)")
        return []

    monkeypatch.setattr("subtitle_corrector.dictionary.terms.search_kornorms", boom)
    monkeypatch.setattr("subtitle_corrector.engine.loanwords.search_kornorms", boom, raising=False)

    entry = parsers.SubtitleEntry(index=1, start="", end="", text="판넬 작업을 부탁해서")
    _corrected, _flags, log = correct_entries([entry])
    assert any("[사전 조회 실패]" in line and "kornorms" in line for line in log)
