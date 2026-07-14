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

Schema version 1 is the baseline. Version 2 adds `record_candidates` so parser inferences remain
separate from formal facts until partial human confirmation. `health db upgrade --confirm` creates a
pre-migration SQLite backup for existing databases; failure restores the main file and removes stale
WAL/SHM state. Version 3 additively introduces structured symptom observations, follow-up events,
appointment fields, pathology/clinician-opinion/Dose Screen candidates and reminder delivery logs.
Existing v2 provenance records are preserved. Every applied migration writes `schema_version` and
`db.migrate` audit rows; an existing database is backed up and integrity-checked before migration.
