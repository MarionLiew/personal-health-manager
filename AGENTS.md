# Repository instructions

This is a local-first medical record and decision-support project. Never place real health data,
identifiers, DICOM identity tags, raw report text, secrets, or runtime databases in Git. Restrict
file access to this repository and explicitly configured import/cache paths.

All persistent medical facts must enter through the `health` CLI, use one of the five evidence
source types, and create an audit event. Mutating commands require a preview/dry-run followed by
explicit confirmation. Hermes may invoke the CLI only; it must never execute SQL or alter files.

Do not output aggregate health/cancer/inflammation scores or turn radiation dose into an individual
cancer probability. Use action levels A-E. Keep user report, source fact, clinician opinion,
guideline rule, and system inference distinct. Use fictional data in tests.

Before delivery run tests and lint. Preserve backward compatibility of JSON response envelopes and
stable error codes. Database schema changes require a numbered migration and backup-aware upgrade.

