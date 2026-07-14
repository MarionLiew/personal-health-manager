from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class MedicalRecordMixin(TimestampMixin):
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_documents.id"), nullable=True, index=True
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(64), default="manual")
    extraction_version: Mapped[str] = mapped_column(String(32), default="1")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    created_by: Mapped[str] = mapped_column(String(64), default="health-cli")
    updated_by: Mapped[str] = mapped_column(String(64), default="health-cli")
    audit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Patient(Base, TimestampMixin):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    local_label: Mapped[str] = mapped_column(String(128), default="Primary patient")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SourceDocument(Base, TimestampMixin):
    __tablename__ = "source_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    local_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_origin: Mapped[str] = mapped_column(String(128), default="user_document")
    contains_identity: Mapped[bool] = mapped_column(Boolean, default=False)
    human_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    parser_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ImportSession(Base):
    __tablename__ = "import_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="previewed")
    preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RecordCandidate(Base):
    __tablename__ = "record_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    import_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("import_sessions.id"), index=True
    )
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), index=True)
    candidate_type: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="system_inference")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    original_text: Mapped[str] = mapped_column(Text)
    original_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    formal_record_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    formal_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor: Mapped[str] = mapped_column(String(64), default="health-cli")
    status: Mapped[str] = mapped_column(String(32), default="success")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_hash_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class GuidelineReference(Base):
    __tablename__ = "guideline_references"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_name: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    population: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(64))
    code_version: Mapped[str] = mapped_column(String(64))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expired: Mapped[bool] = mapped_column(Boolean, default=False)


def make_record_model(name: str, table_name: str) -> type[Base]:
    return type(name, (MedicalRecordMixin, Base), {"__tablename__": table_name})


# Records whose domain-specific fields evolve are stored in validated `details` JSON while all
# provenance fields remain first-class columns. This limits unsafe schema churn in release one.
SystemInference = make_record_model("SystemInference", "system_inferences")
SymptomEpisode = make_record_model("SymptomEpisode", "symptom_episodes")
LaboratoryReport = make_record_model("LaboratoryReport", "laboratory_reports")
LaboratoryResult = make_record_model("LaboratoryResult", "laboratory_results")
ImagingStudy = make_record_model("ImagingStudy", "imaging_studies")
ImagingSeries = make_record_model("ImagingSeries", "imaging_series")
ImagingReport = make_record_model("ImagingReport", "imaging_reports")
Lesion = make_record_model("Lesion", "lesions")
LesionMeasurement = make_record_model("LesionMeasurement", "lesion_measurements")
Diagnosis = make_record_model("Diagnosis", "diagnoses")
Procedure = make_record_model("Procedure", "procedures")
Treatment = make_record_model("Treatment", "treatments")
Medication = make_record_model("Medication", "medications")
FamilyHistory = make_record_model("FamilyHistory", "family_histories")
LifestyleRisk = make_record_model("LifestyleRisk", "lifestyle_risks")
FollowUpPlan = make_record_model("FollowUpPlan", "follow_up_plans")
Appointment = make_record_model("Appointment", "appointments")
RiskAssessment = make_record_model("RiskAssessment", "risk_assessments")
RadiationDoseEstimate = make_record_model("RadiationDoseEstimate", "radiation_dose_estimates")
RadiopharmaceuticalAdministration = make_record_model(
    "RadiopharmaceuticalAdministration", "radiopharmaceutical_administrations"
)
DoseAlert = make_record_model("DoseAlert", "dose_alerts")
DoseCalculationMethod = make_record_model("DoseCalculationMethod", "dose_calculation_methods")
HealthDataSource = make_record_model("HealthDataSource", "health_data_sources")
DailyHealthSummary = make_record_model("DailyHealthSummary", "daily_health_summaries")
BodyWeightRecord = make_record_model("BodyWeightRecord", "body_weight_records")
BodyCompositionRecord = make_record_model("BodyCompositionRecord", "body_composition_records")
SleepSession = make_record_model("SleepSession", "sleep_sessions")
SleepDailySummary = make_record_model("SleepDailySummary", "sleep_daily_summaries")
WorkoutRecord = make_record_model("WorkoutRecord", "workout_records")
ActivityDailySummary = make_record_model("ActivityDailySummary", "activity_daily_summaries")
RecoveryMetric = make_record_model("RecoveryMetric", "recovery_metrics")
LifestyleGoal = make_record_model("LifestyleGoal", "lifestyle_goals")
LifestyleRecommendation = make_record_model("LifestyleRecommendation", "lifestyle_recommendations")
RecommendationOutcome = make_record_model("RecommendationOutcome", "recommendation_outcomes")
InflammationEvidenceAssessment = make_record_model(
    "InflammationEvidenceAssessment", "inflammation_evidence_assessments"
)


class RadiationExposure(MedicalRecordMixin, Base):
    __tablename__ = "radiation_exposures"
    examination_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    modality: Mapped[str] = mapped_column(String(32))
    examination_name: Mapped[str] = mapped_column(String(255))
    body_region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    clinical_indication: Mapped[str | None] = mapped_column(Text, nullable=True)
    protocol_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acquisition_count: Mapped[int] = mapped_column(Integer, default=0)
    contrast_used: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dose_data_source: Mapped[str] = mapped_column(String(64), default="unknown")
    data_quality: Mapped[str] = mapped_column(String(64), default="insufficient_data")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RadiationAcquisition(Base):
    __tablename__ = "radiation_acquisitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exposure_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("radiation_exposures.id"), index=True
    )
    series_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    irradiation_event_uid: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    acquisition_uid: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    acquisition_type: Mapped[str] = mapped_column(String(64))
    body_region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scan_length_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctdi_vol_mgy: Mapped[float | None] = mapped_column(Float, nullable=True)
    dlp_mgy_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    phantom_size_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ssde_mgy: Mapped[float | None] = mapped_column(Float, nullable=True)
    tube_voltage_kvp: Mapped[float | None] = mapped_column(Float, nullable=True)
    tube_current_mas: Mapped[float | None] = mapped_column(Float, nullable=True)
    exposure_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    pitch: Mapped[float | None] = mapped_column(Float, nullable=True)
    repeat_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class HealthImportBatch(Base):
    __tablename__ = "health_import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class HealthSample(MedicalRecordMixin, Base):
    __tablename__ = "health_samples"
    healthkit_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sample_type: Mapped[str] = mapped_column(String(255), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_app: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_device: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manually_entered: Mapped[bool] = mapped_column(Boolean, default=False)
    import_batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("health_import_batches.id"))
    original_hash: Mapped[str] = mapped_column(String(64), index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("patient_id", "healthkit_uuid", name="uq_health_sample_uuid"),
        UniqueConstraint("patient_id", "original_hash", name="uq_health_sample_hash"),
    )


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
