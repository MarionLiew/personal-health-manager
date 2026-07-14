from enum import StrEnum


class SourceType(StrEnum):
    USER_REPORT = "user_report"
    SOURCE_FACT = "source_fact"
    CLINICIAN_OPINION = "clinician_opinion"
    GUIDELINE_RULE = "guideline_rule"
    SYSTEM_INFERENCE = "system_inference"


class ActionLevel(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class DoseDataSource(StrEnum):
    DICOM_RDSR = "dicom_rdsr"
    SCANNER_DOSE_PAGE = "scanner_dose_page"
    DICOM_METADATA = "dicom_metadata"
    RADIOLOGY_REPORT = "radiology_report"
    USER_DOCUMENT = "user_document"
    PROTOCOL_ESTIMATE = "protocol_estimate"
    LITERATURE_RANGE = "literature_range"
    UNKNOWN = "unknown"


class DataQuality(StrEnum):
    EXACT_MACHINE_RECORD = "exact_machine_record"
    DOCUMENTED_VALUE = "documented_value"
    PATIENT_ADJUSTED_ESTIMATE = "patient_adjusted_estimate"
    GENERIC_ESTIMATE = "generic_estimate"
    INSUFFICIENT_DATA = "insufficient_data"
