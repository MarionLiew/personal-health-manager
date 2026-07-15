# Changelog

## 0.5.4 - 2026-07-15

- Preserve pathology immunohistochemistry qualifiers: `部分+` is now
  `partial_positive`, while Ki-67 retains approximate and reported-positive metadata.
- Distinguish submitted tissue-fragment measurements from lesion measurements and mark them
  explicitly as not being lesion size.
- Preserve all pathology recommendations and prefer the supplemental recommendation for repeat
  sampling instead of allowing an earlier immunohistochemistry recommendation to replace it.
- Derive supplemental pathology dates from the final report date when a supplement contains
  multiple report dates, and recognize pathology received dates.

## 0.5.3 - 2026-07-15

- Preserve PDF table layout during text extraction so laboratory result, unit and reference columns
  are not confused with row numbers.
- Add structured coagulation and expanded CBC/reticulocyte items with ASCII abbreviation boundaries
  that prevent `PCT` from becoming CT and `RSI` from becoming serum iron.
- Classify laryngoscopy and nasal endoscopy separately from pathology even when a blank pathology
  template is present, and retain RFS/RSI as report scores rather than laboratory results.
- Recognize `MR` radiology reports, separate examination/report dates and findings/impression
  sections, and remove report footers from candidate text.
- Make report-import dry-runs query exact SHA-256 duplicates and return the existing source/import
  identifiers before confirmation.
- Add parser version 4 and fictional cross-hospital regression fixtures for coagulation, CBC,
  endoscopy and MRI layouts.

## 0.5.2 - 2026-07-15

- Correctly distinguish neck ultrasound reports, ultrasound-guided biopsy procedures and pathology
  supplements, including conservative multi-date handling and structured procedure details.
- Preserve aggregate lymph-node size ranges without converting their lower bound or nearby thyroid
  wording into an individual lesion measurement.
- Add `health record reparse SOURCE_ID` with dry-run/confirmation gating, source hash verification,
  audit logging and protection for confirmed or rejected candidates.
- Update the Hermes Skill so saved reports can be reparsed only through the CLI and only after the
  user approves the new preview.

## 0.5.1 - 2026-07-15

- Allow only the detected Hermes Weixin document-cache directory through a dedicated wrapper
  configuration while continuing to reject the home directory and other over-broad roots.
- Make medical attachments trigger `health record import --dry-run` before any parsing or summary,
  and require per-file import status plus explicit confirmation.
- Prevent Hermes from describing a dry-run or failed import as saved; failed imports now require the
  stable error code and an explicit “not imported” response.
- Move Skill backups outside Hermes' recursively scanned `skills` tree and verify that the active
  copy, rather than a legacy backup, is the discoverable Skill.
- Require fresh CLI dry-runs when retrying earlier attachments; command help and cached error tables
  no longer count as a retry.

## 0.5.0 - 2026-07-14

- Integrate the `personal-health-manager` Skill with the detected Hermes v0.16 default profile and
  running Weixin gateway through a CLI-only wrapper.
- Add safe install/update backup, uninstall, structural verification, Hermes discovery checks, and
  explicit dry-run/confirmation instructions for every write operation.
- Add `health imaging list --json`, exact Weixin intent examples, and deployment documentation for
  Skill reload, permissions, testing, and medical safety boundaries.

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
