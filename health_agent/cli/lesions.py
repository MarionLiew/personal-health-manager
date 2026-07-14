from __future__ import annotations

import typer

from health_agent.cli.main import emit
from health_agent.database.migrations import migrate
from health_agent.database.models import Lesion
from health_agent.database.session import session_scope
from health_agent.services.lesion_tracker import active_lesions, comparison, measurement_rows

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        lesions = active_lesions(session)
        data = {
            "lesions": [
                {"id": lesion.id, **lesion.details, "source_document_id": lesion.source_document_id}
                for lesion in lesions
            ]
        }
    emit("lesions.list", data, json_output=json_output)


@app.command("show")
def show_command(lesion_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        lesion = session.get(Lesion, lesion_id)
        if lesion is None:
            raise typer.BadParameter("Lesion not found")
        rows = measurement_rows(session, lesion_id)
        data = {"id": lesion.id, **lesion.details, "measurements": rows}
    emit("lesions.show", data, json_output=json_output)


@app.command("measurements")
def measurements_command(lesion_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = measurement_rows(session, lesion_id)
    emit(
        "lesions.measurements",
        {"lesion_id": lesion_id, "measurements": rows},
        json_output=json_output,
    )


@app.command("compare")
def compare_command(lesion_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = measurement_rows(session, lesion_id)
    emit(
        "lesions.compare",
        {"lesion_id": lesion_id, **comparison(rows)},
        json_output=json_output,
    )
