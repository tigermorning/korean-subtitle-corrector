"""자막 형식별 파싱·저장 회귀 테스트 (사용자 요청 2026-08-02).

이 도구가 다루는 것은 대사 텍스트뿐이다. 형식마다 붙는 스타일·배치·메타데이터는
교정 대상이 아니므로 **원본 그대로 되돌아와야 한다** — 그것을 잃지 않는지가 이
파일의 핵심 검증이다.

사전 API를 쓰지 않으므로 네트워크가 필요 없다.
"""

from subtitle_corrector import formats
from subtitle_corrector.file_io import is_supported, output_suffix, parse_file, write_file


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestVtt:
    SAMPLE = (
        "WEBVTT\n\n"
        "NOTE 이 줄은 주석이다\n\n"
        "cue-1\n"
        "00:00:01.000 --> 00:00:04.000 line:0 position:50%\n"
        "[민수] 안녕하세요\n\n"
        "01:02.500 --> 01:05.000\n"
        "짬짜면을 시켰다\n"
    )

    def test_parses_cues(self, tmp_path):
        entries = parse_file(_write(tmp_path, "a.vtt", self.SAMPLE))
        assert [e.text for e in entries] == ["[민수] 안녕하세요", "짬짜면을 시켰다"]

    def test_timecodes_normalized(self, tmp_path):
        """시가 생략된 VTT 타임코드(01:02.500)도 읽기 속도 계산이 가능해야 한다."""
        entries = parse_file(_write(tmp_path, "a.vtt", self.SAMPLE))
        assert entries[0].start == "00:00:01,000"
        assert entries[1].start == "00:01:02,500"

    def test_speaker_extracted(self, tmp_path):
        entries = parse_file(_write(tmp_path, "a.vtt", self.SAMPLE))
        assert entries[0].speaker == "민수"

    def test_cue_id_and_settings_preserved(self, tmp_path):
        source = _write(tmp_path, "a.vtt", self.SAMPLE)
        entries = parse_file(source)
        entries[0].text = "[민수] 반갑습니다"
        out = tmp_path / "out.vtt"
        write_file(entries, out, source)
        saved = out.read_text(encoding="utf-8")
        assert saved.startswith("WEBVTT")
        assert "cue-1" in saved
        assert "line:0 position:50%" in saved
        assert "[민수] 반갑습니다" in saved

    def test_notes_are_not_entries(self, tmp_path):
        entries = parse_file(_write(tmp_path, "a.vtt", self.SAMPLE))
        assert not any("주석" in e.text for e in entries)


class TestSami:
    SAMPLE = (
        "<SAMI>\n<HEAD><STYLE TYPE='text/css'>P { color: white; }</STYLE></HEAD>\n<BODY>\n"
        "<SYNC Start=1000><P Class=KRCC>안녕하세요\n"
        "<SYNC Start=4000><P Class=KRCC>&nbsp;\n"
        "<SYNC Start=5000><P Class=KRCC>짬짜면을 시켰다\n"
        "</BODY>\n</SAMI>\n"
    )

    def test_parses_cues_and_skips_blank(self, tmp_path):
        entries = parse_file(_write(tmp_path, "a.smi", self.SAMPLE))
        assert [e.text for e in entries] == ["안녕하세요", "짬짜면을 시켰다"]

    def test_end_time_comes_from_next_sync(self, tmp_path):
        entries = parse_file(_write(tmp_path, "a.smi", self.SAMPLE))
        assert entries[0].start == "00:00:01,000"
        assert entries[0].end == "00:00:04,000"

    def test_style_header_preserved(self, tmp_path):
        source = _write(tmp_path, "a.smi", self.SAMPLE)
        entries = parse_file(source)
        entries[0].text = "반갑습니다"
        out = tmp_path / "out.smi"
        write_file(entries, out, source)
        saved = out.read_text(encoding="utf-8")
        assert "color: white" in saved
        assert "Class=KRCC" in saved
        assert "반갑습니다" in saved


class TestAss:
    SAMPLE = (
        "[Script Info]\nTitle: 테스트\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,안녕하세요\\N반갑습니다\n"
    )

    def test_parses_dialogue_only(self, tmp_path):
        entries = parse_file(_write(tmp_path, "a.ass", self.SAMPLE))
        assert len(entries) == 1
        assert entries[0].text == "안녕하세요\n반갑습니다"  # \\N은 줄바꿈으로

    def test_timecodes(self, tmp_path):
        entries = parse_file(_write(tmp_path, "a.ass", self.SAMPLE))
        assert entries[0].start == "00:00:01,000"
        assert entries[0].end == "00:00:04,000"

    def test_styles_and_fields_preserved(self, tmp_path):
        source = _write(tmp_path, "a.ass", self.SAMPLE)
        entries = parse_file(source)
        entries[0].text = "안녕하세요\n또 봐요"
        out = tmp_path / "out.ass"
        write_file(entries, out, source)
        saved = out.read_text(encoding="utf-8")
        assert "[V4+ Styles]" in saved and "Style: Default,Arial" in saved
        assert "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,," in saved
        assert "안녕하세요\\N또 봐요" in saved  # 저장할 때 \\N으로 되돌린다


class TestSbvAndSubViewer:
    def test_sbv(self, tmp_path):
        source = _write(tmp_path, "a.sbv", "0:00:01.000,0:00:04.000\n안녕하세요\n\n")
        entries = parse_file(source)
        assert entries[0].text == "안녕하세요"
        assert entries[0].start == "00:00:01,000"
        entries[0].text = "반갑습니다"
        out = tmp_path / "out.sbv"
        write_file(entries, out, source)
        assert "0:00:01.000,0:00:04.000\n반갑습니다" in out.read_text(encoding="utf-8")

    def test_subviewer_line_break_token(self, tmp_path):
        source = _write(tmp_path, "a.sub", "00:00:01.00,00:00:04.00\n첫 줄[br]둘째 줄\n\n")
        entries = parse_file(source)
        assert entries[0].text == "첫 줄\n둘째 줄"
        out = tmp_path / "out.sub"
        write_file(entries, out, source)
        assert "[br]" in out.read_text(encoding="utf-8")


class TestTtml:
    SAMPLE = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<tt xmlns="http://www.w3.org/ns/ttml"><body><div>\n'
        '<p begin="00:00:01.000" end="00:00:04.000" region="bottom">안녕하세요<br/>반갑습니다</p>\n'
        "</div></body></tt>\n"
    )

    def test_parses_paragraphs(self, tmp_path):
        entries = parse_file(_write(tmp_path, "a.ttml", self.SAMPLE))
        assert entries[0].text == "안녕하세요\n반갑습니다"
        assert entries[0].start == "00:00:01,000"

    def test_attributes_preserved(self, tmp_path):
        source = _write(tmp_path, "a.ttml", self.SAMPLE)
        entries = parse_file(source)
        entries[0].text = "안녕하세요\n또 봐요"
        out = tmp_path / "out.ttml"
        write_file(entries, out, source)
        saved = out.read_text(encoding="utf-8")
        assert 'region="bottom"' in saved
        assert "xmlns=" in saved
        assert "안녕하세요<br/>또 봐요" in saved


class TestDispatcher:
    def test_supported_extensions(self):
        for ext in (".srt", ".vtt", ".smi", ".ass", ".ssa", ".sbv", ".sub", ".ttml", ".dfxp", ".txt", ".docx"):
            assert is_supported(ext), ext

    def test_unsupported_extension(self):
        assert not is_supported(".scc")  # 바이트 스트림이라 텍스트 교정 대상이 아니다
        assert not is_supported(".mp4")

    def test_subtitle_keeps_its_format_documents_become_txt(self):
        assert output_suffix("영화.vtt") == ".vtt"
        assert output_suffix("영화.smi") == ".smi"
        assert output_suffix("원고.docx") == ".txt"
        assert output_suffix("원고.txt") == ".txt"

    def test_unknown_extension_raises(self, tmp_path):
        source = _write(tmp_path, "a.scc", "무엇")
        try:
            parse_file(source)
        except ValueError as error:
            assert ".scc" in str(error)
        else:
            raise AssertionError("지원하지 않는 형식은 ValueError여야 한다")


class TestTimecodeNormalization:
    def test_various_shapes(self):
        assert formats._to_hms("00:00:01.500") == "00:00:01,500"
        assert formats._to_hms("01:02.500") == "00:01:02,500"
        assert formats._to_hms("0:00:04.00") == "00:00:04,000"
        assert formats._to_hms("이상한 값") == ""
