import sys
from pathlib import Path

import typer

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from subtitle_corrector.engine import apply_report_fixes, correct_entries, register_custom_words
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
    names: Path = typer.Option(None, help="고유명사 목록 파일 (한 줄에 하나씩) - kiwi가 절대 잘못 쪼개지 않게 함"),
    dishes: Path = typer.Option(None, help="요리/음료 이름 목록 파일 (한 줄에 하나씩) - 항상 붙여 쓰도록 등록"),
):
    """자막(.srt), Word 문서(.docx), 일반 텍스트(.txt)를 교정하고, 모호한 항목은 리포트로 모아 출력합니다."""
    register_custom_words(_read_word_list(names), tag="NNP")
    register_custom_words(_read_word_list(dishes), tag="NNG")

    ext = input_file.suffix.lower()
    is_srt = ext == ".srt"
    if is_srt:
        entries = parse_srt(input_file)
    elif ext == ".docx":
        entries = parse_docx(input_file)
    else:
        entries = parse_plain_text(input_file)
    corrected_entries, flags, applied_log = correct_entries(entries)

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
