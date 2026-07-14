# Changelog

## 0.4.0 - 2026-07-14

- Add schema migration 4 and a single-user Personal Health Profile layer for long-term conditions,
  scar lesions, HPV-related or uncertain skin lesions, treatment events and local lesion images.
- Add infection/immune context without scoring, unified health timeline events, actionable risk
  factors, monitoring preferences and long-term management priorities.
- Add audited preview/confirmation CLI mutations and seven stable profile dashboard queries.
- Extend medical safety validation and Hermes routing to prohibit photo diagnosis, scar-to-cancer
  inference, HPV malignant-transformation claims and immune/inflammation scores.

## 0.3.0 - 2026-07-14

- Add schema migration 3 with symptom observations, follow-up events, appointments, structured
  pathology/clinician-opinion candidates, Dose Screen candidates and reminder delivery logs.
- Add audited symptom, follow-up and appointment CLI workflows with preview/confirmation gates,
  fuzzy follow-up date ranges and department-relevant visit summaries/questions.
- Add local Dose Screen candidate parsing and partial confirmation without Total/event DLP double
  counting, plus ordinary DICOM acquisition de-duplication and incomplete metadata dose records.
- Expand liver, kidney, thyroid and inflammation laboratory aliases and units; unify JSON errors.
- Update the Hermes Skill command routing, safety gates and WeChat examples.

## 0.2.0 - 2026-07-14

- Add transactional database migrations 0→1→2 with dry-run, backup, verification, audit, and
  failure restoration.
- Add Chinese report classification, deterministic laboratory/imaging/lesion candidates, partial
  confirmation/rejection, laboratory trends, lesion tracking, semantic RDSR parsing, confirmed
  DICOM dose import, radiation ledger, visit summary, and fictional end-to-end coverage.

## 0.1.0 - 2026-07-14

- Initialize the local-first CLI, configuration, safety policy, SQLite schema, documentation, and
  test harness.
