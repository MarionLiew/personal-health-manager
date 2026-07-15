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

Parser-only upgrades do not require a database migration. `health record reparse SOURCE_ID` verifies
the managed source path and SHA-256 before creating replacement candidates. Confirmation marks only
obsolete `pending` candidates as `superseded`; `confirmed` and `rejected` candidates and their formal
records are never rewritten. The operation records a `record.reparse` audit event and parser version.
Parser version 4 adds only candidate payload fields and therefore keeps schema version 4 unchanged.
Parser version 5 adds pathology candidate detail fields for qualified immunohistochemistry,
recommendation lists and submitted-fragment measurements; it also requires no schema migration.
Parser version 6 adds aggregate two-axis node measurements and OCR provenance flags to candidate
JSON only, so schema version 4 remains unchanged.

Version 4 adds `PersonalCondition`, `ScarLesion`, `HPVLesion`, `TreatmentEvent`, `LesionImage`,
`ImmuneContext`, `HealthTimelineEvent` and `RiskFactorProfile`. These are verified medical-management
facts with the same provenance and audit columns as existing records. Images are content-addressed
local files; the database stores their hash and repository-controlled data path, never image bytes.
