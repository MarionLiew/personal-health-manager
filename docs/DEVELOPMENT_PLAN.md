# Development plan and actual status

Status date: 2026-07-14.

- Phase 0 — complete: environment audit, isolated Git repository, disk/tool/Hermes discovery, safe
  ignore rules.
- Phase 1 — complete: architecture, data model, safety/threat documentation, configuration,
  schemas, error codes and CLI baseline.
- Phase 2 — complete for v0.2: transactional migrations 0→1→2, pre-upgrade backup, failure restore,
  migration audit, source hashing, structured candidates, partial confirmation/rejection and undo.
- Phase 3 — partial: laboratory trends, lesion tracking and visit summaries are implemented. Symptom
  and follow-up commands remain.
- Phase 4 — complete for structured RDSR v0.2: safe ZIP, DICOM discovery, semantic RDSR fields,
  confirmed dose import, acquisition/reconstruction deduplication and radiation ledger. Dose Screen
  OCR confirmation and generic effective-dose estimation remain intentionally unsupported.
- Phase 5 — pending: Apple Health streaming import and lifestyle analyses.
- Phase 6 — partial: a validated, installable, CLI-only Hermes Skill and guarded install/uninstall/
  verify scripts exist. Missing CLI command families prevent complete intent flows.
- Phase 7 — partial: unit/integration/end-to-end baseline, DICOM reconstruction/ZIP tests, encrypted
  backup verification/restore and CLI smoke tests exist. The complete required fixture matrix remains.

No unfinished feature is represented as production-ready. The implementation order prioritizes
provenance, confirmation, audit, and safety before medical parsing or analysis.
