# Development plan and actual status

Status date: 2026-07-15.

Current release: `0.6.1`; current schema: `6`.

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

Known limitations: general scanned-PDF OCR is available only through explicit local macOS Vision
preview and still requires field-by-field confirmation. DICOM Dose Screen image OCR continues to
require Tesseract or supplied local OCR text. Follow-up recurrence automation and
external reminder delivery are inactive. Department relevance uses deterministic terminology and
requires user review. Apple Health and lifestyle modules remain deferred.

The Personal Health Profile phase is complete for single-user controlled use: long-term conditions,
scar/skin lesion history, treatment events, image timelines, infection context, risk factors and
management priorities are implemented. Automated photo interpretation, disease diagnosis and risk
probability models remain explicitly out of scope.

Report parser maintenance in 0.5.2 distinguishes ultrasound-guided biopsy procedures and pathology
supplements from imaging reports, preserves aggregate lymph-node measurement ranges without turning
them into individual lesions, and supports audited reparse of saved sources. Reparse supersedes only
pending candidates; confirmed and rejected decisions remain immutable.

Parser version 4 in release 0.5.3 preserves PDF layout for laboratory tables, supports coagulation
and expanded CBC fields, distinguishes diagnostic ENT endoscopy from blank pathology templates, and
recognizes MR radiology reports with separate dates and report sections. Exact file duplicates are
now reported during dry-run rather than only during confirmation.

Parser version 5 in release 0.5.4 preserves partial immunohistochemistry positivity, approximate
Ki-67 expressions, multiple pathology recommendations, supplement dates and the explicit boundary
between submitted tissue-fragment size and lesion size.

Parser version 6 in release 0.5.5 adds representative two-axis measurements for multiple lymph
nodes and an opt-in, local-only scanned-PDF OCR path with capped candidate confidence.

Parser version 7 in release 0.5.6 carries the parsed institution into each candidate. Schema
migration 5 adds the indexed source-document institution used by record listing and provenance.

Release 0.6.0 adds a local, redacted GPT analysis bundle. It does not call an external API or upload
data. Pending candidates remain excluded unless explicitly requested and are always separated from
confirmed facts.

Release 0.6.1 separates hospital confirmation from medical-candidate confirmation. Schema 6 records
whether institution provenance is parser-inferred or human-confirmed, and parser version 8 preserves
two-dimensional CT lesion measurements, laterality and detailed locations while excluding repeated
impression text from lesion extraction.

No unfinished feature is represented as production-ready. The implementation order prioritizes
provenance, confirmation, audit, and safety before medical parsing or analysis.
