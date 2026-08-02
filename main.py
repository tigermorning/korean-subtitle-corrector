import sys
from pathlib import Path

import typer

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from subtitle_corrector.dictionary import DIALECT_MARKERS
from subtitle_corrector.engine import (
    apply_report_fixes,
    correct_entries,
    normalize_subtitle_markers,
    normalize_spacing_mode,
    register_custom_words,
)
from subtitle_corrector.parsers import parse_docx, parse_plain_text, parse_srt, write_plain_text, write_srt
from subtitle_corrector.report import read_report, write_report

app = typer.Typer()


def _read_word_list(path: Path | None) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


@app.command()
def correct(
    input_file: Path = typer.Argument(..., help="입력 파일 경로 (.srt 자막, .docx 문서, .txt 일반 텍스트)"),
    output: Path = typer.Option(None, help="출력 파일 경로 (.srt는 자막 형식 유지, 그 외는 .txt)"),
    report: Path = typer.Option(None, help="플래그 리포트 파일 경로"),
    names: Path = typer.Option(
        None, help="고유명사·요리/음료 이름 목록 파일 (한 줄에 하나씩) - kiwi가 절대 잘못 쪼개지 않게 함. 3번 이상 반복되는 단어는 적지 않아도 자동 감지됨"
    ),
    prose: bool = typer.Option(
        False, "--prose", help="일반 글 모드(구두점 허용). 기본은 자막 모드로, 문장 끝 마침표를 오류로 플래그합니다."
    ),
    spacing: str = typer.Option(
        "principle",
        "--spacing",
        help="보조 용언 띄어쓰기 기준(제47항): principle=원칙(띄어 씀, 기본값), allowance=허용(붙여 씀). 문서 전체에 하나만 적용됩니다.",
    ),
    dialect_region: str = typer.Option(
        None,
        "--dialect-region",
        help="문서 전체 사투리 지역(경상도/제주도/전라도/충청도). 화자 표기가 없는 일반 글에 씁니다.",
    ),
    dialect_mode: str = typer.Option(
        "protect",
        "--dialect-mode",
        help="문서 전체 사투리 처리 모드: protect(기본, 그대로 보호) / assist(사투리 제안 플래그) / to_standard(표준어로 자동 변환). --dialect-region과 함께 씁니다.",
    ),
    screen_text_marker: str = typer.Option(
        "",
        "--screen-text-marker",
        help="자막 모드 전용. 화면자막 표기(예: 큰따옴표 또는 @). 짝이 있는 문자면 감싸인 구간만, 짝이 없는 문자면 그 줄 전체를 교정에서 제외합니다.",
    ),
    line_break_marker: str = typer.Option(
        "", "--line-break-marker", help="자막 모드 전용. 줄바꿈 표기(예: |). 교정할 때만 실제 줄바꿈으로 취급하고 결과에는 그대로 되돌립니다."
    ),
    position_marker: str = typer.Option(
        "",
        "--position-marker",
        help=r"자막 모드 전용. 자막 위치 표기(예: {\an8}). 제어 코드라 통째로 보호합니다.",
    ),
    speaker_bracket: str = typer.Option(
        "",
        "--speaker-bracket",
        help="자막 모드 전용. 화자명 표기 부호(예: [] 또는 ()). 닫는 부호 뒤에 한 칸을 띄웁니다. 기본값은 대괄호.",
    ),
    tone_bracket: str = typer.Option(
        "",
        "--tone-bracket",
        help="자막 모드 전용. 어조·지문 표기 부호(예: [] 또는 ()). 기본값은 대괄호.",
    ),
):
    """자막(.srt), Word 문서(.docx), 일반 텍스트(.txt)를 교정하고, 모호한 항목은 리포트로 모아 출력합니다."""
    register_custom_words(_read_word_list(names), tag="NNP")

    ext = input_file.suffix.lower()
    is_srt = ext == ".srt"
    if is_srt:
        entries = parse_srt(input_file)
    elif ext == ".docx":
        entries = parse_docx(input_file)
    else:
        entries = parse_plain_text(input_file)
    spacing_mode = normalize_spacing_mode(spacing)
    if spacing_mode != spacing.strip().lower():
        typer.echo(f"알 수 없는 --spacing 값 '{spacing}' -> 원칙(principle)으로 진행합니다.")
    region = (dialect_region or "").strip() or None
    if region and region not in DIALECT_MARKERS:
        typer.echo(
            f"알 수 없는 --dialect-region 값 '{region}' -> 사투리 미지정으로 진행합니다. "
            f"(지원: {', '.join(DIALECT_MARKERS)})"
        )
        region = None
    corrected_entries, flags, applied_log = correct_entries(
        entries,
        doc_type="prose" if prose else "subtitle",
        spacing_mode=spacing_mode,
        dialect_region=region,
        dialect_mode=dialect_mode if region else None,
        markers=normalize_subtitle_markers(
            screen_text_marker, line_break_marker, position_marker,
            speaker_bracket, tone_bracket,
        ),
    )

    # .docx는 서식까지 보존하는 새 문서를 만들지 않고(범위 밖), 다른 일반
    # 텍스트와 동일하게 결과를 순수 텍스트(.txt)로 돌려준다.
    suffix = ".srt" if is_srt else ".txt"
    output = output or input_file.with_name(input_file.stem + "_corrected" + suffix)
    report_path = report or input_file.with_name(input_file.stem + "_report.csv")

    if is_srt:
        write_srt(corrected_entries, output)
    else:
        write_plain_text(corrected_entries, output)
    write_report(flags, report_path)

    typer.echo(f"교정된 자막: {output}")
    if applied_log:
        typer.echo(f"자동 교정 {len(applied_log)}건:")
        for line in applied_log:
            typer.echo(f"  {line}")
    typer.echo(f"플래그 항목 {len(flags)}건 -> 리포트: {report_path}")


@app.command(name="apply-report")
def apply_report_cmd(
    report_file: Path = typer.Argument(..., help="사용자가 수정값을 채운 리포트 파일"),
    target_file: Path = typer.Argument(..., help="반영할 자막 파일"),
    output: Path = typer.Option(None, help="출력 파일 경로 (기본: target_file에 덮어씀)"),
):
    """리포트에 사용자가 채운 수정값을 자막 파일에 반영합니다."""
    entries = parse_srt(target_file)
    rows = read_report(report_file)
    updated_entries, applied_count = apply_report_fixes(rows, entries)

    output = output or target_file
    write_srt(updated_entries, output)

    typer.echo(f"리포트 반영 {applied_count}건 -> {output}")


if __name__ == "__main__":
    app()
