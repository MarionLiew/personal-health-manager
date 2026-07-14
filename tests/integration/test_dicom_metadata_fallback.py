import json
import uuid
from pathlib import Path

from pydicom.uid import generate_uid
from sqlalchemy import select
from typer.testing import CliRunner

from health_agent.cli.main import app
from health_agent.config import ROOT
from health_agent.database.models import RadiationAcquisition, RadiationExposure
from health_agent.database.session import session_scope
from tests.unit.test_dicom import make_ct


def test_confirmed_ordinary_dicom_is_incomplete_metadata_record(isolated_env: Path) -> None:
    root = ROOT / "data/dicom" / f"metadata-fallback-{uuid.uuid4()}"
    root.mkdir()
    try:
        make_ct(root / "slice.dcm", "AXIAL", generate_uid(), ctdi_vol=3.8)
        result = CliRunner().invoke(app, ["dicom", "import", str(root), "--confirm", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["data"]["rdsr_count"] == 0
        with session_scope() as session:
            exposure = session.scalar(select(RadiationExposure))
            acquisition = session.scalar(select(RadiationAcquisition))
            assert exposure is not None and acquisition is not None
            assert exposure.dose_data_source == "dicom_metadata"
            assert exposure.data_quality == "documented_value"
            assert exposure.details["dose_incomplete"] is True
            assert acquisition.ctdi_vol_mgy == 3.8
            assert acquisition.dlp_mgy_cm is None
        summary = CliRunner().invoke(app, ["radiation", "summary", "--lifetime", "--json"])
        data = json.loads(summary.stdout)["data"]
        assert data["effective_dose_estimate"] is None
        missing = CliRunner().invoke(app, ["radiation", "missing-dose-data", "--json"])
        assert len(json.loads(missing.stdout)["data"]["exposures"]) == 1
    finally:
        for item in root.iterdir():
            item.unlink()
        root.rmdir()
