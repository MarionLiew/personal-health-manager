# Data model

Every medical record carries patient, evidence source type, source document, occurrence and record
times, original text, extraction method/version, confidence, verification status, actor, audit ID,
and domain details. `SourceDocument` is content-addressed by SHA-256. `ImportSession` separates a
preview from a confirmed import and records undo state. `AuditLog` stores only safe identifiers and
hash prefixes.

The baseline schema includes identity/source, medical record, radiation, Apple Health/lifestyle,
follow-up, assessment, recommendation, and evidence entities specified in the product requirements.
`RadiationExposure` and `RadiationAcquisition` keep scanner values distinct from estimates.
`HealthSample` uses patient+HealthKit UUID and patient+content hash uniqueness constraints.

Schema version 1 is created by `health init`. Before any future destructive migration, create and
verify a backup; restoration must target a new database until explicit confirmation.

