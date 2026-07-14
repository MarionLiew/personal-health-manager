# Development plan and actual status

Status date: 2026-07-14.

Current release: `0.5.0`; current schema: `4`.

- Phase 0 — complete: environment audit, isolated Git repository, disk/tool/Hermes discovery, safe
  ignore rules.
- Phase 1 — complete: architecture, data model, safety/threat documentation, configuration,
  schemas, error codes and CLI baseline.
- Phase 2 — complete for v0.3: transactional migrations 0→1→2→3, verified pre-upgrade backup, failure restore,
  migration audit, source hashing, structured candidates, partial confirmation/rejection and undo.
- Phase 3 — complete for v0.3: symptoms, observations, follow-ups, appointments, laboratory trends,
  lesion tracking, clinician/pathology candidates and department-relevant visit preparation.
- Phase 4 — complete for v0.3 scope: safe ZIP, DICOM discovery, semantic RDSR fields, Dose Screen
  candidates, ordinary-DICOM metadata fallback, acquisition/reconstruction deduplication and ledger.
- Phase 5 — pending: Apple Health streaming import and lifestyle analyses.
- Phase 6 — complete: a validated, installed, CLI-only Hermes Skill, guarded
  scripts, command routing and WeChat examples exist.
- Phase 7 — complete for v0.3 scope: unit/integration/end-to-end daily management, DICOM, Dose Screen,
  migration, JSON error, encrypted backup and Hermes validation tests exist.

Known limitations: image OCR requires a locally installed Tesseract executable; this host can parse
supplied local OCR text but cannot render DICOM pixels for OCR. Follow-up recurrence automation and
external reminder delivery are inactive. Department relevance uses deterministic terminology and
requires user review. Apple Health and lifestyle modules remain deferred.

The Personal Health Profile phase is complete for single-user controlled use: long-term conditions,
scar/skin lesion history, treatment events, image timelines, infection context, risk factors and
management priorities are implemented. Automated photo interpretation, disease diagnosis and risk
probability models remain explicitly out of scope.

No unfinished feature is represented as production-ready. The implementation order prioritizes
provenance, confirmation, audit, and safety before medical parsing or analysis.
