# Personal Health Profile

The Profile layer organizes a single user's verified long-term management facts. It is not a
diagnostic or disease-probability model.

## Data flow

Every mutation uses the same project gate:

```text
user statement or allowed local image
→ health profile <mutation> --dry-run --json
→ explicit user confirmation
→ health profile <mutation> --confirm --json
→ verified record + audit event + timeline event where applicable
```

The profile stores long-term conditions, scar and skin/mucosal lesions, treatment events, local
hash-addressed images, contextual infection/laboratory information, timeline events and risk factors.
Evidence source types remain distinct. A user-reported dermatologist opinion is not silently changed
to `clinician_opinion`; that source type must be explicitly selected from a confirmed source.

## Dashboard commands

```bash
health profile summary --json
health profile conditions --json
health profile timeline --json
health profile skin --json
health profile infections --json
health profile monitoring --json
health profile priorities --json
```

`config/personal_profile.yaml` contains only operator-managed preferences and goals. It starts empty
and must not contain identifiers, raw reports or secrets. Formal medical facts belong in SQLite via
the CLI, not in YAML.

## Safety boundary

Photo tracking is limited to user/clinician-described size, count and appearance changes. The system
does not diagnose a photo. It does not link a scar directly to cancer risk, state that HPV will become
cancer, attribute HPV persistence to reduced immunity, or generate immune/inflammation scores.
