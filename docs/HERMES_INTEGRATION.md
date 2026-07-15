# Hermes integration

## Detected installation

The deployment was inspected on 2026-07-14 before integration:

- Hermes executable: `/Users/marionliew/.local/bin/hermes`
- Hermes Agent: `v0.16.0` (`2026.6.5`, upstream `9e484f05`)
- Runtime checkout: `/Users/marionliew/.hermes/hermes-agent`
- Active profile: `default`
- Configuration: `/Users/marionliew/.hermes/config.yaml`, schema version 29
- Local Skill root: `/Users/marionliew/.hermes/skills`
- Weixin document cache: `/Users/marionliew/.hermes/cache/documents`
- Gateway: launchd service `ai.hermes.gateway`
- Weixin adapter: configured and loaded by the running gateway

Secrets remain in Hermes' own credential files and are not read by this project. The Hermes config
uses a `skills` section for Skill behavior and a `gateway` section for messaging. A local Skill is a
directory under the active profile's `skills` root with a YAML-frontmatter `SKILL.md`; bundled and
local Skills are shown by `hermes skills list`.

## Data path and trust boundary

```text
Weixin message
  -> Hermes gateway and agent
  -> personal-health-manager
  -> tools/health.sh
  -> health CLI JSON envelope
  -> Hermes Chinese summary
  -> Weixin reply
```

Hermes may call only the wrapper. The wrapper selects `config/hermes.yaml`, which adds only the
detected Weixin document-cache directory to the normal project-local import roots. It then selects
the project's installed `health` executable
or runs it through `uv`; it contains no database path. Hermes must never execute SQL, inspect or edit
`data/`, use chat memory as a medical fact, or bypass CLI validation and audit behavior.

## Install and enable

From the repository:

```bash
cd /Users/marionliew/personal-health-agent
./hermes_skill/install.sh
./hermes_skill/verify.sh
hermes skills list
```

If a different copy already exists, review it first, then update with a timestamped backup:

```bash
./hermes_skill/install.sh --update
```

Backups are stored outside the scanned Skill tree at
`~/.hermes/backups/personal-health-manager-skills`. Version 0.5.1 and later automatically move the earlier
`.personal-health-manager-backups` directory out of `~/.hermes/skills`; otherwise Hermes may load a
backup copy instead of the active Skill.

Hermes can re-scan without changing credentials or configuration. Send `/reload-skills` in the
active Hermes chat or Weixin conversation. Restarting the installed gateway also creates a fresh
Skill scan:

```bash
hermes gateway restart
hermes gateway status
```

To remove only this Skill, use `./hermes_skill/uninstall.sh --confirm`, then reload Skills. The
uninstaller does not touch the application, database, imports, or backups.

## Verification

The repository verifier checks Skill structure, the wrapper, `health doctor --json`, database
verification, prohibited direct-database instructions, and Hermes discovery:

```bash
./hermes_skill/verify.sh
hermes skills list | grep personal-health-manager
```

Hermes v0.16 reports local Skills through `skills list`; `skills audit` applies only to hub-installed
Skills and therefore does not validate this local installation.

Read-only smoke tests:

```bash
~/.hermes/skills/personal-health-manager/tools/health.sh profile summary --json
~/.hermes/skills/personal-health-manager/tools/health.sh imaging list --json
~/.hermes/skills/personal-health-manager/tools/health.sh radiation summary --json
~/.hermes/skills/personal-health-manager/tools/health.sh visit-summary \
  --department 耳鼻喉科 --json
```

Intent checks:

- “查看我的健康概览” routes to `health profile summary --json`.
- “整理我的耳鼻喉复诊资料” routes to
  `health visit-summary --department 耳鼻喉科 --json`.
- “白细胞最近有什么变化” asks for the item if needed, then routes to
  `health labs trend --item 白细胞 --json`.
- “比较这个病灶” requires a lesion ID, then routes to `health lesions compare ID --json`.

For a deterministic local agent test, preload the Skill:

```bash
hermes -s personal-health-manager -z '查看我的健康概览。只调用 health CLI，并简要说明来源和不确定性。'
```

Do not run that command against real health data if the selected Hermes model is a remote inference
provider. Use a fictional test database instead.

## Write-operation confirmation

Every mutation is a four-step exchange:

1. Call the same operation with `--dry-run --json`.
2. Show the candidate fields, evidence source, uncertainty, duplicate warnings, and record IDs.
3. Wait for explicit confirmation referring to that preview.
4. Call the same operation with `--confirm --json`.

Hermes must never add `--confirm` itself. This applies to symptoms, treatments, report imports,
lesion changes, correction, undo, and restore. Low-confidence dates, numbers, units, laterality,
pathology status, or Dose Screen values remain unconfirmed until the user selects them.

### Medical PDF attachments

Sending one or more medical PDFs without explanatory text is an import intent by default. Hermes
must not use Python or a generic document Skill to extract the report first. For each exact cache
path it calls:

```bash
~/.hermes/skills/personal-health-manager/tools/health.sh \
  record import ATTACHMENT.pdf --dry-run --json
```

Hermes reports preview success or failure separately for every file. A successful dry-run is still
“not saved”. After explicit user confirmation it repeats each successful file with `--confirm`, and
only then may say that the original was preserved if the response contains both
`source_document_id` and `import_id`. Extracted candidate facts require another explicit selection;
importing the source does not silently promote them to formal medical facts.

### Reparse an already saved report

If the original was saved but its pending candidates were parsed incorrectly, Hermes first runs:

```bash
~/.hermes/skills/personal-health-manager/tools/health.sh \
  record reparse SOURCE_DOCUMENT_ID --dry-run --json
```

It must show the new candidate types, measurements, uncertainties, IDs that would be superseded and
any protected confirmed/rejected IDs. Only after the user explicitly approves that preview may it
repeat the command with `--confirm`. Reparse verifies the saved source hash, supersedes only pending
candidates, creates an audit event and never confirms the replacement candidates automatically.

If the CLI returns `UNSAFE_PATH`, Hermes must stop retrying, show the error code, and state “未导入”.
It must never fall back to a prose summary that implies the source entered the system.

The deployment-specific cache permission is defined in `config/hermes.yaml`. Do not replace it with
`~/.hermes`, the home directory, or another broad parent directory.

## Weixin reply behavior

Long results begin with a short Chinese summary. Preserve the JSON envelope's warnings,
uncertainties, sources, record IDs, and action level A-E. Risk or examination-necessity replies use
the project's required medical headings. Action level A advises immediate real-world care and also
states that this is not an emergency service.

The assistant is not a doctor, cannot diagnose cancer, calculate an individual cancer probability,
replace a clinician, or infer disease from one result. It cannot emit total health, immunity, or
inflammation scores, and it cannot convert radiation history into personal cancer probability.

## Permissions

The gateway account needs execute permission for the installed wrapper and read/execute permission
for the project environment. Import file access is limited to paths accepted by the project's CLI
configuration, including an explicitly configured Hermes attachment-cache directory. Do not grant
Hermes broader home-directory access and do not add the database directory to its direct file
allowlist.

## Troubleshooting

If Hermes can summarize a PDF but returns no `import_id`, inspect the CLI result rather than the
summary. In the observed pre-0.5.1 failure, all seven dry-runs returned `UNSAFE_PATH` because the
Weixin cache was outside the normal project roots; no file had entered the health database despite a
reply claiming the originals were retained. Version 0.5.1 fixes the exact cache permission and makes
that misleading fallback prohibited.
