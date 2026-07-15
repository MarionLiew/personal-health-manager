# GPT analysis export

`health export gpt-bundle` creates a local JSON file that can be reviewed and, only by the user's
separate decision, uploaded to GPT or another analysis service. The project never sends the file or
its contents over the network.

## Safety model

The default bundle includes confirmed structured records, evidence source types, hospital/source
provenance, long-term profile data, timelines, laboratory results, imaging summaries, lesions,
follow-ups and radiation history. It excludes raw documents, report headers/original text, images,
filenames, local paths, content hashes, direct patient IDs, DICOM UIDs and HealthKit UUIDs.

Direct identifiers in remaining structured strings receive a best-effort redaction pass. This is not
a formal anonymization guarantee: health history, dates, rare conditions and hospital combinations
may still be identifying. Always inspect the local JSON before sharing it externally. Use
`--exclude-institutions` when the hospital is unnecessary for the intended analysis.

Pending parser candidates are excluded by default. `--include-pending` places them only under
`unconfirmed_data.parser_candidates`, labels them `system_inference` and includes an instruction that
they must not be presented as medical facts, clinician opinions or diagnoses.

## Commands

Preview a confirmed-facts-only bundle:

```bash
health export gpt-bundle --output my-health.json --dry-run --json
```

Preview a bundle that also contains clearly separated pending candidates:

```bash
health export gpt-bundle --output my-health-review.json --include-pending --dry-run --json
```

After checking the preview, repeat the exact command with `--confirm`. Output must remain under
`data/exports`, must use `.json`, is created with mode `0600`, and never overwrites an existing file.
Every completed export creates an audit event containing only safe metadata and a hash prefix.

The generated JSON includes analysis instructions prohibiting diagnosis, individual cancer
probabilities, immune/inflammation scores, and radiation-to-personal-cancer-risk conversion. It asks
the receiving model to distinguish all five evidence types and use action levels A-E.
