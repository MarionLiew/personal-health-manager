# Command map

Always add `--json` to query commands. Use `--dry-run` before and `--confirm` only after explicit
confirmation for mutations.

- Environment: `health status`, `health doctor`
- General report: `health record import FILE`, `health record reparse SOURCE_DOCUMENT_ID`,
  `health record list`, `health record show ID`, `health record undo-import IMPORT_ID`
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
  `health lesions compare ID`
- Radiation: `health radiation list`, `health radiation show ID`,
  `health radiation acquisitions ID`, `health radiation summary`, `health radiation by-region`,
  `health radiation missing-dose-data`, `health radiation possible-duplicates`,
  `health radiation doctor-summary`
- Visit preparation: `health visit-summary --department DEPARTMENT`,
  `health doctor-questions --department DEPARTMENT`
- Backup: `health backup create`, `health backup list`, `health backup verify FILE`,
  `health backup restore FILE`

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
  replacements and pending candidates to be superseded, then use `--confirm` only after explicit
  approval. Reparse never confirms medical facts and never changes confirmed/rejected candidates.

For a WeChat file, use only the exact local cache path supplied by Hermes and accepted by CLI path
validation. A rejected path must be copied/approved through deployment configuration by the operator;
do not broaden access yourself.

Medical PDF routing is mandatory unless the user explicitly requests read-only summarization:
`health record import FILE --dry-run --json`. Dry-run means “not saved”. A successful confirmed
import must return both `source_document_id` and `import_id`; otherwise report “not imported”.

The command spellings above describe the `health` CLI. Invoke them by replacing the `health` prefix
with `${HERMES_HOME:-$HOME/.hermes}/skills/personal-health-manager/tools/health.sh`.
