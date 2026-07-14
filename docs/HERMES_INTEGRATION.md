# Hermes integration

Detected on 2026-07-14: `/Users/marionliew/.local/bin/hermes`, Hermes Agent v0.16.0, runtime project
`/Users/marionliew/.hermes/hermes-agent`. The Skill is developed in-repository and will be installed
only after its scripts resolve the active Hermes profile's actual Skill path. It must call
`uv run --project /Users/marionliew/personal-health-agent health ... --json` and must never execute
SQL, alter the database, skip dry-run/confirmation, delete originals, or treat chat memory as fact.

The production WeChat flow must preview imported files, show uncertain fields and provenance, ask
for explicit confirmation, then invoke the matching confirmed CLI command. Long results begin with a
summary. Risk/test responses use the required medical sections and action level A-E.

Version 0.3 supports symptom add/update/resolve/reopen, follow-up and appointment management,
department-specific summaries, data-backed doctor questions, structured clinician/pathology
candidates, Dose Screen partial confirmation and incomplete ordinary-DICOM dose queries. Dose Screen
confirmation must pass only user-selected IDs; low-confidence OCR is never auto-confirmed and Total
DLP is not added to event DLP. If no local OCR engine exists, the CLI returns `OCR_UNAVAILABLE` and
does not send the image to an external service.

Install and verify without overwriting an existing Skill:

```bash
./hermes_skill/install.sh
./hermes_skill/verify.sh
hermes skills list
```

Remove only with explicit confirmation: `./hermes_skill/uninstall.sh --confirm`. The install source
is `hermes_skill/personal-health-manager`; the detected default destination is
`/Users/marionliew/.hermes/skills/personal-health-manager`.
