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


class TestPdf:
    """PDF는 읽기 전용 입력이다(도서 번역 원고 검토 등).

    텍스트 레이어가 있는 PDF만 읽을 수 있다 — 스캔본은 글자가 이미지라 아무것도
    나오지 않으며, 그 경우 OCR이 선행되어야 한다.
    """

    def _make_pdf(self, tmp_path, lines):
        import fitz  # PyMuPDF: 테스트용 PDF 생성

        doc = fitz.open()
        page = doc.new_page()
        # insert_text는 줄바꿈을 렌더링하지 않으므로 줄마다 따로 찍는다.
        for offset, line in enumerate(lines):
            page.insert_text((72, 72 + offset * 24), line, fontsize=12)
        path = tmp_path / "a.pdf"
        doc.save(str(path))
        doc.close()
        return path

    def test_supported(self):
        assert is_supported(".pdf")

    def test_output_is_plain_text(self):
        """서식·쪽 배치를 되돌릴 수 없으므로 결과는 텍스트로 준다."""
        assert output_suffix("원고.pdf") == ".txt"

    def test_extracts_text_lines(self, tmp_path):
        """텍스트 레이어에서 줄을 뽑아 오는지 확인한다.

        본문을 ASCII로 쓰는 이유는 우리 파서가 아니라 **테스트용 PDF를 만드는 쪽**의
        한계 때문이다 — PyMuPDF 기본 폰트로 한글을 써 넣으면 글리프가 깨져 저장된다.
        실제 원고 PDF는 한글 폰트가 임베드돼 있어 그대로 추출된다.
        """
        path = self._make_pdf(tmp_path, ["first line here", "second line here"])
        entries = parse_file(path)
        joined = chr(10).join(e.text for e in entries)
        assert "first line here" in joined and "second line here" in joined

    def test_scanned_pdf_yields_nothing(self, tmp_path):
        """텍스트 레이어가 없으면 빈 결과 — 호출부가 이 사실을 사용자에게 알린다."""
        import fitz

        doc = fitz.open()
        doc.new_page()
        path = tmp_path / "scan.pdf"
        doc.save(str(path))
        doc.close()
        assert [e for e in parse_file(path) if e.text.strip()] == []


class TestDocxExport:
    """교정 결과를 워드 문서로 내려받는 경로 (사용자 요청 2026-08-02).

    .docx는 ZIP 안에 XML이 들어 있어 브라우저에서 만들기 번거롭다. 서버에 이미
    python-docx가 있으므로(문서 읽기에 쓴다) 거기서 만들어 내려보낸다.
    """

    def _client(self):
        from fastapi.testclient import TestClient

        from subtitle_corrector.api import app

        return TestClient(app)

    def test_returns_docx_with_text(self):
        import io
        import zipfile

        response = self._client().post(
            "/api/export/docx", data={"text": "첫 문단입니다\n둘째 문단입니다", "filename": "테스트본"}
        )
        assert response.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        document_xml = archive.read("word/document.xml").decode("utf-8")
        assert "첫 문단입니다" in document_xml
        assert "둘째 문단입니다" in document_xml

    def test_korean_filename_is_encoded(self):
        """한글 파일명은 헤더에 그대로 넣을 수 없어 UTF-8로 인코딩해 보낸다."""
        response = self._client().post(
            "/api/export/docx", data={"text": "본문", "filename": "교정본"}
        )
        assert "filename*=UTF-8''" in response.headers["content-disposition"]

    def test_empty_text_still_produces_a_file(self):
        response = self._client().post("/api/export/docx", data={"text": ""})
        assert response.status_code == 200
        assert len(response.content) > 0


class TestCorrectApiRevertContract:
    """화면의 "되돌리기"가 기대는 응답 계약 (2026-08-04).

    되돌리기는 줄 단위로 동작한다 — 자동 교정 로그의 '원문조각 -> 교정조각'은 긴
    줄에서 '…'로 축약되므로(`_localized_change`) 복원에 쓸 수 없기 때문이다. 그래서
    응답이 두 가지를 반드시 줘야 한다: 줄마다 교정 전 원문(`entries[].original`),
    그리고 각 로그가 어느 줄의 기록이며 텍스트를 실제로 바꿨는지(`applied_log`).
    """

    def _client(self):
        from fastapi.testclient import TestClient

        from subtitle_corrector.api import app

        return TestClient(app)

    def _correct(self, body: str):
        response = self._client().post(
            "/api/correct",
            files={"file": ("t.srt", body.encode("utf-8"), "text/plain")},
        )
        assert response.status_code == 200
        return response.json()

    def test_entries_carry_pre_correction_text(self):
        data = self._correct(
            "1\n00:00:01,000 --> 00:00:02,000\n초코렛 좋아\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\n그대로 둘 줄\n"
        )
        by_index = {e["index"]: e for e in data["entries"]}
        assert by_index[1]["original"] == "초코렛 좋아"
        assert by_index[1]["text"] == "초콜릿 좋아"
        # 자동 교정이 없었던 줄은 원문과 결과가 같다 — 되돌려도 달라지지 않는다.
        assert by_index[2]["original"] == by_index[2]["text"] == "그대로 둘 줄"

    def test_applied_log_is_structured_per_line(self):
        data = self._correct("1\n00:00:01,000 --> 00:00:02,000\n초코렛 좋아\n")
        edits = [n for n in data["applied_log"] if n["is_edit"]]
        assert edits, "자동 교정이 한 건은 있어야 계약을 확인할 수 있다"
        assert all(n["line_index"] == 1 for n in edits)
        assert any("초콜릿" in n["message"] for n in edits)
