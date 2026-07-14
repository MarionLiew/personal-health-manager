# Command map

Always add `--json` to query commands. Use `--dry-run` before and `--confirm` only after explicit
confirmation for mutations.

- Environment: `health status`, `health doctor`
- General report: `health record import FILE`, `health record list`, `health record show ID`,
  `health record undo-import IMPORT_ID`
- DICOM: `health dicom inspect PATH`, `health dicom dose PATH`
- Database: `health db version`, `health db migrations`, `health db upgrade`, `health db verify`
- Candidates: `health record candidates IMPORT_ID`, `health record confirm-candidates IMPORT_ID`,
  `health record reject-candidates IMPORT_ID`
- Laboratory: `health labs list`, `health labs trend --item ITEM`, `health labs compare --item ITEM`,
  `health labs report REPORT_ID`
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

Commands in the product plan for labs, lesions, symptoms, imaging ledger, radiation ledger, timeline,
follow-up, Apple Health, lifestyle, assessment, visit summary and doctor questions must be used only
after `health <group> --help` confirms they exist. Never emulate a missing command with direct file or
database access.

For a WeChat file, use only the exact local cache path supplied by Hermes and accepted by CLI path
validation. A rejected path must be copied/approved through deployment configuration by the operator;
do not broaden access yourself.
