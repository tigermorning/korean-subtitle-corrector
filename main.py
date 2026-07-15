import sys
from pathlib import Path

import typer

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from subtitle_corrector.engine import correct_entries
from subtitle_corrector.parsers import parse_srt, write_srt
from subtitle_corrector.report import write_report

app = typer.Typer()


@app.command()
def correct(
    input_file: Path = typer.Argument(..., help="입력 SRT 파일 경로"),
    output: Path = typer.Option(None, help="출력 SRT 파일 경로"),
    report: Path = typer.Option(None, help="플래그 리포트 파일 경로"),
):
    """자막 파일을 교정하고, 모호한 항목은 리포트로 모아 출력합니다."""
    entries = parse_srt(input_file)
    corrected_entries, flags, applied_log = correct_entries(entries)

    output = output or input_file.with_name(input_file.stem + "_corrected.srt")
    report_path = report or input_file.with_name(input_file.stem + "_report.csv")

    write_srt(corrected_entries, output)
    write_report(flags, report_path)

    typer.echo(f"교정된 자막: {output}")
    if applied_log:
        typer.echo(f"자동 교정 {len(applied_log)}건:")
        for line in applied_log:
            typer.echo(f"  {line}")
    typer.echo(f"플래그 항목 {len(flags)}건 -> 리포트: {report_path}")


@app.command(name="apply-report")
def apply_report(
    report_file: Path = typer.Argument(..., help="사용자가 수정값을 채운 리포트 파일"),
    target_file: Path = typer.Argument(..., help="반영할 자막 파일"),
):
    """리포트에 채운 수정값을 자막 파일에 반영합니다. (다음 단계에서 구현 예정)"""
    typer.echo("아직 구현 전입니다 — 다음 단계에서 작업할 예정이에요.")


if __name__ == "__main__":
    app()
