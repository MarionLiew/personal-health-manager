from __future__ import annotations

from datetime import UTC, datetime, timedelta

import typer

from health_agent.cli.main import emit
from health_agent.database.migrations import migrate
from health_agent.database.models import RadiationExposure
from health_agent.database.session import session_scope
from health_agent.services.radiation_ledger import (
    acquisition_rows,
    active_exposures,
    exposure_row,
    possible_duplicates,
    summary,
)

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = [exposure_row(item) for item in active_exposures(session)]
    emit("radiation.list", {"exposures": rows}, json_output=json_output)


@app.command("show")
def show_command(exposure_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        exposure = session.get(RadiationExposure, exposure_id)
        if exposure is None:
            raise typer.BadParameter("Radiation exposure not found")
        data = exposure_row(exposure)
        data["acquisitions"] = acquisition_rows(session, exposure_id)
    emit("radiation.show", data, json_output=json_output)


@app.command("acquisitions")
def acquisitions_command(
    exposure_id: str, json_output: bool = typer.Option(False, "--json")
) -> None:
    migrate()
    with session_scope() as session:
        rows = acquisition_rows(session, exposure_id)
    emit(
        "radiation.acquisitions",
        {"exposure_id": exposure_id, "acquisitions": rows},
        json_output=json_output,
    )


@app.command("summary")
def summary_command(
    period: str | None = typer.Option(None, "--period"),
    lifetime: bool = typer.Option(False, "--lifetime"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    if bool(period) == lifetime:
        raise typer.BadParameter("Specify exactly one of --period or --lifetime")
    migrate()
    with session_scope() as session:
        exposures = active_exposures(session)
        if period:
            if not period.endswith("m") or not period[:-1].isdigit():
                raise typer.BadParameter("Period must look like 12m")
            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
                days=int(period[:-1]) * 30.4375
            )
            exposures = [
                item
                for item in exposures
                if item.examination_date and item.examination_date >= cutoff
            ]
        data = summary(exposures)
        data["period"] = "lifetime" if lifetime else period
    emit("radiation.summary", data, json_output=json_output)


@app.command("by-region")
def by_region_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        data = summary(active_exposures(session))["by_region"]
    emit("radiation.by-region", {"regions": data}, json_output=json_output)


@app.command("missing-dose-data")
def missing_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        rows = [
            exposure_row(item)
            for item in active_exposures(session)
            if item.data_quality == "insufficient_data" or item.details.get("dose_incomplete")
        ]
    emit("radiation.missing-dose-data", {"exposures": rows}, json_output=json_output)


@app.command("possible-duplicates")
def duplicates_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        alerts = possible_duplicates(active_exposures(session))
    emit("radiation.possible-duplicates", {"alerts": alerts}, json_output=json_output)


@app.command("doctor-summary")
def doctor_summary_command(json_output: bool = typer.Option(False, "--json")) -> None:
    migrate()
    with session_scope() as session:
        exposures = active_exposures(session)
        data = summary(exposures)
        data["possible_duplicates"] = possible_duplicates(exposures)
        data["questions"] = [
            "Can prior images be reused before repeating the same body region?",
            "Is an RDSR or scanner dose page available for examinations with missing dose data?",
            "Would MRI or ultrasound answer the clinical question when medically appropriate?",
        ]
    emit("radiation.doctor-summary", data, json_output=json_output)
