from __future__ import annotations

import shutil
import sqlite3
import sys
from typing import Any

import click
import typer
from sqlalchemy import inspect
from typer._click.exceptions import ClickException as TyperClickException
from typer.core import TyperGroup

from health_agent import __version__
from health_agent.config import load_settings
from health_agent.constants import ActionLevel
from health_agent.database.migrations import SCHEMA_VERSION, current_version, migrate
from health_agent.database.session import build_engine
from health_agent.errors import HealthAgentError
from health_agent.safety.response_validator import validate_response
from health_agent.schemas.responses import ErrorDetail, ResponseEnvelope


def _action_from_args(values: object) -> str:
    raw = values if isinstance(values, (list, tuple)) else []
    tokens = [str(value) for value in raw if not str(value).startswith("-")]
    return ".".join(tokens[:2]) or "cli"


class JsonErrorGroup(TyperGroup):
    def main(self, *args: object, **kwargs: object) -> object:
        raw = kwargs.get("args")
        if raw is None and args and isinstance(args[0], (list, tuple)):
            raw = args[0]
        if raw is None:
            raw = sys.argv[1:]
        json_requested = "--json" in raw
        if not json_requested:
            return super().main(*args, **kwargs)
        kwargs["standalone_mode"] = False
        try:
            return super().main(*args, **kwargs)
        except (click.ClickException, TyperClickException) as exc:
            envelope = ResponseEnvelope(
                status="error",
                action=_action_from_args(raw),
                data=None,
                error=ErrorDetail(code="INVALID_ARGUMENT", message=str(exc), details={}),
            )
            click.echo(envelope.model_dump_json(indent=2))
            raise SystemExit(2) from None
        except HealthAgentError as exc:
            envelope = ResponseEnvelope(
                status="error",
                action=_action_from_args(raw),
                data=None,
                error=ErrorDetail(code=exc.code, message=str(exc), details={}),
            )
            click.echo(envelope.model_dump_json(indent=2))
            raise SystemExit(1) from None
        except Exception:
            envelope = ResponseEnvelope(
                status="error",
                action=_action_from_args(raw),
                data=None,
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="The command could not be completed; review local redacted logs.",
                    details={},
                ),
            )
            click.echo(envelope.model_dump_json(indent=2))
            raise SystemExit(1) from None


app = typer.Typer(
    cls=JsonErrorGroup, no_args_is_help=True, help="Local-first personal health record CLI."
)


def emit(
    action: str,
    data: dict[str, Any],
    *,
    json_output: bool = True,
    warnings: list[str] | None = None,
    uncertainties: list[str] | None = None,
    requires_confirmation: bool = False,
    medical_action_level: ActionLevel | None = None,
) -> None:
    envelope = validate_response(
        ResponseEnvelope(
            status="success",
            action=action,
            data=data,
            warnings=warnings or [],
            uncertainties=uncertainties or [],
            requires_confirmation=requires_confirmation,
            medical_action_level=medical_action_level,
        )
    )
    if json_output:
        typer.echo(envelope.model_dump_json(indent=2))
    else:
        typer.echo(data)


def emit_error(action: str, exc: Exception) -> None:
    if isinstance(exc, HealthAgentError):
        code, message = exc.code, str(exc)
    elif isinstance(exc, (ValueError, FileNotFoundError)):
        code, message = "VALIDATION_ERROR", str(exc)
    else:
        code, message = "INTERNAL_ERROR", "Internal error"
    envelope = ResponseEnvelope(
        status="error", action=action, data=None, error=ErrorDetail(code=code, message=message)
    )
    typer.echo(envelope.model_dump_json(indent=2))


@app.command("init")
def init_command(json_output: bool = typer.Option(False, "--json")) -> None:
    """Create/upgrade the local database without overwriting existing records."""
    try:
        settings = load_settings()
        for child in (
            "database",
            "reports",
            "imports",
            "dicom",
            "apple_health",
            "exports",
            "backups",
            "quarantine",
        ):
            (settings.data_root / child).mkdir(parents=True, exist_ok=True, mode=0o700)
        version = migrate()
        emit(
            "init",
            {"database": str(settings.database_path), "schema_version": version, "created": True},
            json_output=json_output,
        )
    except Exception as exc:
        emit_error("init", exc)
        raise typer.Exit(1) from exc


@app.command("status")
def status_command(json_output: bool = typer.Option(False, "--json")) -> None:
    """Report local application and database status."""
    settings = load_settings()
    exists = settings.database_path.exists()
    emit(
        "status",
        {
            "version": __version__,
            "database_exists": exists,
            "database_path": str(settings.database_path),
            "schema_version": current_version() if exists else None,
            "expected_schema_version": SCHEMA_VERSION,
        },
        json_output=json_output,
    )


@app.command("doctor")
def doctor_command(json_output: bool = typer.Option(False, "--json")) -> None:
    """Run non-mutating environment and database checks."""
    settings = load_settings()
    checks: list[dict[str, object]] = []
    checks.append(
        {"name": "python", "ok": sys.version_info >= (3, 11), "value": sys.version.split()[0]}
    )
    checks.append({"name": "git", "ok": shutil.which("git") is not None})
    checks.append({"name": "hermes", "ok": shutil.which("hermes") is not None})
    checks.append({"name": "database_exists", "ok": settings.database_path.exists()})
    if settings.database_path.exists():
        try:
            engine = build_engine()
            tables = inspect(engine).get_table_names()
            checks.append({"name": "database_readable", "ok": True, "tables": len(tables)})
            checks.append(
                {"name": "schema_version", "ok": current_version(engine) == SCHEMA_VERSION}
            )
            with sqlite3.connect(settings.database_path) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            checks.append({"name": "sqlite_integrity", "ok": result == "ok", "value": result})
        except Exception:
            checks.append({"name": "database_readable", "ok": False})
    free = shutil.disk_usage(settings.root).free
    checks.append({"name": "disk_free", "ok": free >= 2 * 1024**3, "bytes": free})
    emit(
        "doctor",
        {"healthy": all(bool(item["ok"]) for item in checks), "checks": checks},
        json_output=json_output,
    )


# Imported last to avoid circular imports: command modules use the shared emit helpers above.
from health_agent.cli import (  # noqa: E402
    appointments,
    backup,
    db,
    dicom,
    followup,
    imaging,
    labs,
    lesions,
    profile,
    radiation,
    record,
    symptoms,
)

app.add_typer(record.app, name="record")
app.add_typer(dicom.app, name="dicom")
app.add_typer(backup.app, name="backup")
app.add_typer(db.app, name="db")
app.add_typer(labs.app, name="labs")
app.add_typer(lesions.app, name="lesions")
app.add_typer(radiation.app, name="radiation")
app.add_typer(symptoms.app, name="symptoms")
app.add_typer(followup.app, name="followup")
app.add_typer(imaging.app, name="imaging")
app.add_typer(appointments.app, name="appointments")
app.add_typer(profile.app, name="profile")


@app.command("visit-summary")
def visit_summary_command(
    department: str = typer.Option(..., "--department"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    from health_agent.database.migrations import migrate
    from health_agent.database.session import session_scope
    from health_agent.services.visit_summary import build_visit_summary

    migrate()
    with session_scope() as session:
        data = build_visit_summary(session, department)
    emit("visit-summary", data, json_output=json_output)


@app.command("doctor-questions")
def doctor_questions_command(
    department: str = typer.Option(..., "--department"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    from health_agent.database.migrations import migrate
    from health_agent.database.session import session_scope
    from health_agent.services.visit_summary import build_visit_summary, questions_from_summary

    migrate()
    with session_scope() as session:
        summary = build_visit_summary(session, department)
    emit(
        "doctor-questions",
        {
            "department": department,
            "questions": questions_from_summary(summary),
            "data_gaps": summary["data_gaps"],
        },
        json_output=json_output,
    )


if __name__ == "__main__":
    app()
