# Hermes integration

## Detected installation

The deployment was inspected on 2026-07-14 before integration:

- Hermes executable: `/Users/marionliew/.local/bin/hermes`
- Hermes Agent: `v0.16.0` (`2026.6.5`, upstream `9e484f05`)
- Runtime checkout: `/Users/marionliew/.hermes/hermes-agent`
- Active profile: `default`
- Configuration: `/Users/marionliew/.hermes/config.yaml`, schema version 29
- Local Skill root: `/Users/marionliew/.hermes/skills`
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

Hermes may call only the wrapper. The wrapper selects the project's installed `health` executable
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
