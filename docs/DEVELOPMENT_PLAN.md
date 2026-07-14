# Development plan and actual status

Status date: 2026-07-14.

- Phase 0 — complete: environment audit, isolated Git repository, disk/tool/Hermes discovery, safe
  ignore rules.
- Phase 1 — complete: architecture, data model, safety/threat documentation, configuration,
  schemas, error codes and CLI baseline.
- Phase 2 — partial: SQLite baseline entities, migration 1, audit repository, general report
  preview/confirmation/hash deduplication/read-only originals/undo. Field-specific medical parsing
  and correction commands remain.
- Phase 3 — pending: clinical record commands and trend services.
- Phase 4 — partial: bounded safe ZIP, DICOM discovery, SOP/structure RDSR recognition, identity-tag
  presence detection and acquisition/reconstruction deduplication are implemented. RDSR numeric
  persistence, dose-screen parsing, confirmed import and the radiation ledger commands remain.
- Phase 5 — pending: Apple Health streaming import and lifestyle analyses.
- Phase 6 — partial: a validated, installable, CLI-only Hermes Skill and guarded install/uninstall/
  verify scripts exist. Missing CLI command families prevent complete intent flows.
- Phase 7 — partial: unit/integration/end-to-end baseline, DICOM reconstruction/ZIP tests, encrypted
  backup verification/restore and CLI smoke tests exist. The complete required fixture matrix remains.

No unfinished feature is represented as production-ready. The implementation order prioritizes
provenance, confirmation, audit, and safety before medical parsing or analysis.
