# Command map

Always add `--json` to query commands. Use `--dry-run` before and `--confirm` only after explicit
confirmation for mutations.

- Environment: `health status`, `health doctor`
- General report: `health record import FILE`, `health record reparse SOURCE_DOCUMENT_ID`,
  `health record institution-set SOURCE_DOCUMENT_ID --institution INSTITUTION`,
  `health record list [--institution INSTITUTION]`, `health record show ID`,
  `health record undo-import IMPORT_ID`
- Symptoms: `health symptoms add`, `health symptoms update ID`, `health symptoms resolve ID`,
  `health symptoms reopen ID`, `health symptoms active`, `health symptoms timeline`
- Follow-up: `health followup add`, `health followup list`, `health followup pending`,
  `health followup upcoming`, `health followup overdue`, `health followup show ID`,
  `health followup postpone ID`, `health followup complete ID`, `health followup cancel ID`
- Appointments: `health appointments add`, `health appointments list`,
  `health appointments upcoming`, `health appointments show ID`,
  `health appointments complete ID`, `health appointments cancel ID`
- Personal profile queries: `health profile summary`, `health profile conditions`,
  `health profile timeline`, `health profile skin`, `health profile infections`,
  `health profile monitoring`, `health profile priorities`, `health profile image-compare --group`
- Personal profile mutations: `health profile condition-add`, `health profile condition-update`,
  `health profile scar-add`, `health profile hpv-add`, `health profile treatment-add`,
  `health profile image-add`, `health profile immune-add`, `health profile timeline-add`,
  `health profile risk-add`
- DICOM: `health dicom inspect PATH`, `health dicom dose PATH`, `health dicom import PATH`,
  `health dicom dose-screen PATH`
- Database: `health db version`, `health db migrations`, `health db upgrade`, `health db verify`
- Candidates: `health record candidates IMPORT_ID`, `health record confirm-candidates IMPORT_ID`,
  `health record reject-candidates IMPORT_ID`
- Laboratory: `health labs list`, `health labs trend --item ITEM`, `health labs compare --item ITEM`,
  `health labs report REPORT_ID`
- Imaging: `health imaging list`
- Lesions: `health lesions list`, `health lesions show ID`, `health lesions measurements ID`,
  `health lesions compare ID`, `health lesions history ID`
- Lesion writes (all preview/confirm gated): `health lesions create --display-code CODE --name NAME`,
  `health lesions update ID`, `health lesions link-source ID SOURCE_DOCUMENT_ID --evidence-type TYPE
  --status STATUS`, `health lesions unlink ID LINK_ID`,
  `health lesions add-measurement ID --source SOURCE_DOCUMENT_ID --size N --unit UNIT
  --original-text TEXT`
- Clinical exports (all preview/confirm gated, local files only, never uploaded):
  `health export lesion-bundle ID --output NAME.json`,
  `health export visit-bundle --department DEPT --purpose PURPOSE --output NAME.json`,
  `health export record-index --output NAME.json`,
  `health export case-bundle --output NAME.zip`
- Radiation: `health radiation list`, `health radiation show ID`,
  `health radiation acquisitions ID`, `health radiation summary`, `health radiation by-region`,
  `health radiation missing-dose-data`, `health radiation possible-duplicates`,
  `health radiation doctor-summary`
- Visit preparation: `health visit-summary --department DEPARTMENT`,
  `health doctor-questions --department DEPARTMENT`
- Backup: `health backup create`, `health backup list`, `health backup verify FILE`,
  `health backup restore FILE`
- Local GPT export: `health export gpt-bundle --output FILE.json`; add `--include-pending` only after
  the user explicitly requests separately labelled unconfirmed parser candidates.

Commands in the product plan for Apple Health, lifestyle, assessment and other future features must
be used only after `health <group> --help` confirms they exist. Never emulate a missing command with
direct file or database access.

Mutation gate examples:

- `health symptoms add ... --dry-run --json`, then the same arguments with `--confirm --json`.
- `health followup postpone ID ... --dry-run --json`, then `--confirm --json`.
- `health profile scar-add ... --dry-run --json`, display evidence type and uncertainty, then use
  the same arguments with `--confirm --json` only after explicit confirmation.
- `health profile image-add FILE ... --dry-run --json` stores a hash-backed local photo candidate;
  confirmation permits change tracking only, never visual diagnosis.
- `health dicom dose-screen PATH --dry-run --json`, then
  `health dicom dose-screen PATH --confirm --candidate-ids ID1,ID2 --json`.
- General report imports first save parser candidates; use `record candidates` and explicitly pass
  only accepted IDs to `record confirm-candidates`. Never confirm every candidate implicitly.
- Reparsing a saved source first uses `record reparse SOURCE_DOCUMENT_ID --dry-run --json`. Show the
  parsed institution, replacements and pending candidates to be superseded, then use `--confirm`
  only after explicit approval. Reparse never confirms medical facts and never changes
  confirmed/rejected candidates.
- Hospital correction is a separate write: `record institution-set SOURCE_DOCUMENT_ID --institution
  INSTITUTION --dry-run --json`, followed by the same command with `--confirm` only after approval.
  State that candidates and formal medical facts are unchanged. Never use reparse as hospital
  confirmation, and never let parser/OCR replace a verified hospital.
- CT reparse previews must show two dimensions, side, detailed location and series/image range for
  every numbered lesion and must not duplicate findings repeated in the impression.
- For a scanned PDF only after explicit OCR approval, add `--ocr` to the import or reparse dry-run.
  Show all OCR uncertainties and require field-by-field review. Do not use external OCR, generic
  vision tools, or `--confirm` until the user has approved that exact preview.
- GPT export always starts with `export gpt-bundle --output FILE.json --dry-run --json`. It creates a
  local file only after confirmation. Never upload or attach it automatically, and never describe
  pending candidates as confirmed facts.
- Lesion source linking first runs
  `lesions link-source ID SOURCE_DOCUMENT_ID --evidence-type TYPE --status STATUS --dry-run --json`.
  Report-backed evidence (`source_fact`, `clinician_opinion`) requires verbatim `--original-text`;
  add `--page`/`--original-offset` only when you can point at the exact location in the source.
  Run the same arguments again with `--confirm --json` and show the returned `link_id`.
- Adding a lesion measurement first runs
  `lesions add-measurement ID --source SOURCE --size N --unit UNIT --original-text TEXT --dry-run
  --json`, then repeats with `--confirm --json`. Bilateral-group text cannot be attached to one
  lesion: say so instead of forcing an individual measurement.
- A clinical bundle export first runs its `--dry-run --json` form, states the output path inside the
  local exports directory and the included source count, and writes the file only after
  `--confirm --json`. The file stays local; the user decides whether and where to share it.

For a WeChat file, use only the exact local cache path supplied by Hermes and accepted by CLI path
validation. A rejected path must be copied/approved through deployment configuration by the operator;
do not broaden access yourself.

Medical PDF routing is mandatory unless the user explicitly requests read-only summarization:
`health record import FILE --dry-run --json`. Dry-run means “not saved”. A successful confirmed
import must return both `source_document_id` and `import_id`; otherwise report “not imported”.

The command spellings above describe the `health` CLI. Invoke them by replacing the `health` prefix
with `${HERMES_HOME:-$HOME/.hermes}/skills/personal-health-manager/tools/health.sh`.
