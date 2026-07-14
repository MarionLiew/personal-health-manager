# Command map

Always add `--json` to query commands. Use `--dry-run` before and `--confirm` only after explicit
confirmation for mutations.

- Environment: `health status`, `health doctor`
- General report: `health record import FILE`, `health record list`, `health record show ID`,
  `health record undo-import IMPORT_ID`
- DICOM: `health dicom inspect PATH`, `health dicom dose PATH`
- Backup: `health backup create`, `health backup list`, `health backup verify FILE`,
  `health backup restore FILE`

Commands in the product plan for labs, lesions, symptoms, imaging ledger, radiation ledger, timeline,
follow-up, Apple Health, lifestyle, assessment, visit summary and doctor questions must be used only
after `health <group> --help` confirms they exist. Never emulate a missing command with direct file or
database access.

For a WeChat file, use only the exact local cache path supplied by Hermes and accepted by CLI path
validation. A rejected path must be copied/approved through deployment configuration by the operator;
do not broaden access yourself.

