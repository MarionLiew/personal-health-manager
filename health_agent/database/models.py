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
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    institution_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    institution_source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    institution_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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


class SymptomEpisode(MedicalRecordMixin, Base):
    __tablename__ = "symptom_episodes"
    symptom_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_symptom_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    anatomical_region: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    anatomical_side: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    severity: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity_scale: Mapped[str | None] = mapped_column(String(32), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trigger: Mapped[str | None] = mapped_column(Text, nullable=True)
    relieving_factor: Mapped[str | None] = mapped_column(Text, nullable=True)
    aggravating_factor: Mapped[str | None] = mapped_column(Text, nullable=True)
    associated_symptoms: Mapped[list[str]] = mapped_column(JSON, default=list)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SymptomObservation(Base):
    __tablename__ = "symptom_observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    symptom_episode_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("symptom_episodes.id"), index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    severity: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    trigger: Mapped[str | None] = mapped_column(Text, nullable=True)
    medication_or_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="user_report")
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    audit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FollowUpPlan(MedicalRecordMixin, Base):
    __tablename__ = "follow_up_plans"
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_record_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recommendation_source_type: Mapped[str] = mapped_column(String(32), default="user_report")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requested_test: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completion_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    postpone_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FollowUpEvent(Base):
    __tablename__ = "follow_up_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    followup_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("follow_up_plans.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    previous_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    audit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Appointment(MedicalRecordMixin, Base):
    __tablename__ = "appointments"
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    clinician_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_followup_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)
    preparation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CandidateMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    import_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("import_sessions.id"), index=True
    )
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    original_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    formal_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ClinicalOpinionCandidate(CandidateMixin, Base):
    __tablename__ = "clinical_opinion_candidates"


class PathologyCandidate(CandidateMixin, Base):
    __tablename__ = "pathology_candidates"


class DoseScreenCandidate(CandidateMixin, Base):
    __tablename__ = "dose_screen_candidates"
    region: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ReminderDeliveryLog(Base):
    __tablename__ = "reminder_delivery_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    followup_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("follow_up_plans.id"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    status: Mapped[str] = mapped_column(String(32))
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


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


class PersonalCondition(MedicalRecordMixin, Base):
    __tablename__ = "personal_conditions"
    condition_name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    body_region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_noted_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    severity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recurrence_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    related_records: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    monitoring_plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScarLesion(MedicalRecordMixin, Base):
    __tablename__ = "scar_lesions"
    condition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_conditions.id"), index=True
    )
    location: Mapped[str] = mapped_column(String(255))
    scar_type: Mapped[str] = mapped_column(String(128), default="uncertain")
    onset_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_event: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_treatment: Mapped[list[str]] = mapped_column(JSON, default=list)
    treatment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recurrence_after_treatment: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    size_change: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color_change: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hardness_change: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symptoms: Mapped[list[str]] = mapped_column(JSON, default=list)
    dermatologist_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)


class HPVLesion(MedicalRecordMixin, Base):
    __tablename__ = "hpv_lesions"
    condition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_conditions.id"), index=True
    )
    location: Mapped[str] = mapped_column(String(255))
    lesion_type: Mapped[str] = mapped_column(String(128), default="uncertain")
    first_found: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    diagnosis_method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hpv_related: Mapped[str] = mapped_column(String(32), default="uncertain")
    treatment_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    laser_dates: Mapped[list[str]] = mapped_column(JSON, default=list)
    recurrence: Mapped[str] = mapped_column(String(32), default="unknown")
    pathology_done: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dermatologist_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos_available: Mapped[bool] = mapped_column(Boolean, default=False)
    current_status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)


class TreatmentEvent(MedicalRecordMixin, Base):
    __tablename__ = "treatment_events"
    condition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_conditions.id"), index=True
    )
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    treatment_type: Mapped[str] = mapped_column(String(255))
    treatment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LesionImage(MedicalRecordMixin, Base):
    __tablename__ = "lesion_images"
    condition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_conditions.id"), index=True
    )
    lesion_type: Mapped[str] = mapped_column(String(64))
    lesion_id: Mapped[str] = mapped_column(String(36), index=True)
    taken_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    body_location: Mapped[str] = mapped_column(String(255))
    image_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    local_path: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_group: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)


class ImmuneContext(MedicalRecordMixin, Base):
    __tablename__ = "immune_contexts"
    infections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    vaccinations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    influencing_factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    laboratory_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    current_observations: Mapped[list[str]] = mapped_column(JSON, default=list)
    monitoring_items: Mapped[list[str]] = mapped_column(JSON, default=list)


class HealthTimelineEvent(MedicalRecordMixin, Base):
    __tablename__ = "health_timeline_events"
    condition_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("personal_conditions.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_record_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class RiskFactorProfile(MedicalRecordMixin, Base):
    __tablename__ = "risk_factor_profiles"
    factor_name: Mapped[str] = mapped_column(String(255), index=True)
    factor_group: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    current_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    management_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitoring_metric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
