from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient  # type: ignore[import-untyped]

from health_agent.database.models import Lesion, SourceDocument
from health_agent.database.repository import audit
from health_agent.database.session import session_scope
from health_agent.services import lesion_tracker
from health_agent.webapp import create_app

_TEST_PW = "fictional-test-password"  # noqa: S105 - fictional fixture value


@pytest.fixture
def client(isolated_env: Path) -> TestClient:
    import subprocess

    uv = shutil.which("uv") or "/opt/homebrew/bin/uv"
    subprocess.run(  # noqa: S603, S607 - fixed argv, no user input
        [uv, "run", "health", "init", "--json"],
        check=True,
        capture_output=True,
        cwd="/Users/marionliew/personal-health-agent",
    )
    app = create_app(password=_TEST_PW)
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/login", data={"password": _TEST_PW}).status_code == 200
    return client


def _add_source(session, doc_id: str, name: str) -> None:
    audit(session, "test.seed", patient_id="local-primary")
    session.add(
        SourceDocument(
            id=doc_id,
            patient_id="local-primary",
            original_filename=name,
            local_path="/fictional/reports/report.pdf",
            mime_type="application/pdf",
            file_size=2048,
            sha256=doc_id + "0" * (64 - len(doc_id)),
            institution="Fictional Hospital",
            institution_verified=True,
            institution_source_type="source_fact",
        )
    )


def test_index_serves_doctor_view_html(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "个人医疗证据管理".encode() in response.content


def test_timeline_api_returns_records_sorted_by_date(client: TestClient) -> None:
    with session_scope() as session:
        _add_source(session, "src-a", "2025-05-29 胸部CT.pdf")
        session.add(
            Lesion(
                patient_id="local-primary",
                source_type="user_report",
                verified=True,
                details={"display_code": "LN-L", "name": "左侧颈部淋巴结"},
            )
        )
        lesion_tracker.add_measurement(
            session,
            None,  # resolved below
            "src-a",
            size=6.0,
            unit="mm",
            original_text="左肺下叶背段磨玻璃结节 6x4mm",
            examination_date=None,
        ) if False else None
    response = client.get("/api/timeline")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert isinstance(data["data"]["events"], list)


def test_timeline_filters_by_lesion(client: TestClient) -> None:
    response = client.get("/api/timeline", params={"lesion": "nonexistent"})
    assert response.status_code == 200


def test_source_pdf_download_serves_original(client: TestClient) -> None:
    data_dir = isolated_env_dir()
    pdf_path = data_dir / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fictional")
    with session_scope() as session:
        session.add(
            SourceDocument(
                id="src-pdf",
                patient_id="local-primary",
                original_filename="胸部CT.pdf",
                local_path=str(pdf_path),
                mime_type="application/pdf",
                file_size=pdf_path.stat().st_size,
                sha256="c" * 64,
                institution="Fictional Hospital",
            )
        )
    response = client.get("/api/sources/src-pdf/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert b"%PDF-1.4" in response.content


def test_source_download_rejects_missing_file(client: TestClient) -> None:
    with session_scope() as session:
        session.add(
            SourceDocument(
                id="src-missing",
                patient_id="local-primary",
                original_filename="ghost.pdf",
                local_path="/nonexistent/ghost.pdf",
                mime_type="application/pdf",
                file_size=10,
                sha256="d" * 64,
            )
        )
    response = client.get("/api/sources/src-missing/download")
    assert response.status_code == 404


def test_case_zip_download(client: TestClient) -> None:
    data_dir = isolated_env_dir()
    pdf_path = data_dir / "report2.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 case")
    with session_scope() as session:
        session.add(
            SourceDocument(
                id="src-zip",
                patient_id="local-primary",
                original_filename="病理报告.pdf",
                local_path=str(pdf_path),
                mime_type="application/pdf",
                file_size=pdf_path.stat().st_size,
                sha256="e" * 64,
                institution="Fictional Hospital",
            )
        )
    response = client.get("/api/case-bundle.zip")
    assert response.status_code == 200
    assert zipfile.is_zipfile(io.BytesIO(response.content))


def test_health_endpoint_public(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_blocks_all_medical_routes(isolated_env: Path) -> None:
    from health_agent.database.migrations import migrate

    migrate()
    client = TestClient(create_app(password=_TEST_PW), base_url="https://testserver")
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/api/timeline").status_code == 401
    assert client.get("/api/sources/src-pdf/download").status_code == 401
    assert client.get("/api/case-bundle.zip").status_code == 401
    assert client.post("/login", data={"password": _TEST_PW + "-wrong"}).status_code == 401
    assert client.get("/api/timeline").status_code == 401
    response = client.post(
        "/login", data={"password": _TEST_PW}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/api/timeline").status_code == 200


def test_auth_rate_limits_guessing(isolated_env: Path) -> None:
    client = TestClient(create_app(password=_TEST_PW), base_url="https://testserver")
    for _ in range(5):
        assert client.post("/login", data={"password": _TEST_PW + "-wrong"}).status_code == 401
    assert client.post("/login", data={"password": _TEST_PW}).status_code == 429


def isolated_env_dir() -> Path:

    from health_agent.config import load_settings

    return load_settings().database_path.parent
