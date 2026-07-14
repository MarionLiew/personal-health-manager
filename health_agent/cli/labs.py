from __future__ import annotations

import typer

from health_agent.cli.main import emit
from health_agent.database.migrations import migrate
from health_agent.database.models import LaboratoryReport
from health_agent.database.session import session_scope
from health_agent.services.laboratory_trends import lab_rows, trend_summary

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = lab_rows(session)
    emit("labs.list", {"results": rows}, json_output=json_output)


@app.command("trend")
def trend_command(
    item: str = typer.Option(..., "--item"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    migrate()
    with session_scope() as session:
        rows = lab_rows(session, item)
    emit("labs.trend", {"item": item, **trend_summary(rows)}, json_output=json_output)


@app.command("compare")
def compare_command(
    item: str = typer.Option(..., "--item"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    trend_command(item, json_output)


@app.command("report")
def report_command(report_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        report = session.get(LaboratoryReport, report_id)
        if report is None:
            raise typer.BadParameter("Laboratory report not found")
        rows = [
            row
            for row in lab_rows(session)
            if row["source_document_id"] == report.source_document_id
        ]
    emit("labs.report", {"report_id": report_id, "results": rows}, json_output=json_output)
