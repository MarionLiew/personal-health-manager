class HealthAgentError(Exception):
    code = "HEALTH_ERROR"


class ConfigurationError(HealthAgentError):
    code = "CONFIGURATION_ERROR"


class ConfirmationRequired(HealthAgentError):
    code = "CONFIRMATION_REQUIRED"


class DuplicateImport(HealthAgentError):
    code = "DUPLICATE_IMPORT"


class UnsafePath(HealthAgentError):
    code = "UNSAFE_PATH"


class ValidationFailure(HealthAgentError):
    code = "VALIDATION_ERROR"


class OcrUnavailable(HealthAgentError):
    code = "OCR_UNAVAILABLE"
