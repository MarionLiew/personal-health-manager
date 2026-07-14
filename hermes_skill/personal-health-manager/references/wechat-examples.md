# WeChat interaction examples

## Record and update a symptom

User: “记录右侧咽喉痛，今天开始，4/10。”

1. Run `health symptoms add ... --dry-run --json`.
2. Reply with the structured preview, `source_type=user_report`, uncertainties and any specifically
   matched red-flag rule. Do not diagnose a cause.
3. Ask whether to save this episode. After explicit confirmation, rerun with `--confirm --json`.
4. A later “三天后好一点” uses `health symptoms update ID ... --dry-run --json`; do not silently
   merge it with a different episode.

## Follow-up range

For “医生建议6至12个月复查”, show both `due_date_start` and `due_date_end` plus original text. Never
choose six or twelve months as a single date. Report-extracted plans remain candidates until their ID
is explicitly confirmed.

## Dose Screen partial confirmation

1. Run `health dicom dose-screen ATTACHMENT --dry-run --json` only for a detected dose page.
2. List CTDIvol, event DLP and Total DLP candidates with IDs, regions and confidence.
3. Ask which IDs to accept. Do not auto-confirm low-confidence OCR.
4. Run `--confirm --candidate-ids ... --json`. Explain that event DLP is not added again to Total
   DLP and that OCR values are documented user-confirmed values, not RDSR machine records.

## Department summary

For “准备耳鼻喉科就诊摘要”, call `health visit-summary --department 耳鼻喉科 --json`, lead with
current relevant symptoms and red flags, retain sources and data gaps, and omit unrelated bulk data.
Then call `health doctor-questions --department 耳鼻喉科 --json`; do not add generic questions that
are not grounded in returned gaps.

## Long-term personal profile

User: “记录左下颌角瘢痕做过多次治疗，现在又变硬。”

1. Query `health profile conditions --json` to find an existing condition ID.
2. If absent, preview `health profile condition-add --category scar_disorder ... --dry-run --json`.
3. Preview `health profile scar-add --condition-id ID ... --dry-run --json`, preserving whether the
   scar type is reported, suspected or clinician-assessed.
4. Confirm only after the user approves. Reply with treatment history, observed change and next
   monitoring item. Do not connect the scar to cancer risk.

User: “这些疣是不是HPV，以后会不会癌变？”

Query `health profile skin --json`. Preserve `confirmed`, `suspected`, `uncertain` or
`not_supported` exactly. Explain recorded evidence and changes to observe; do not infer malignant
transformation or a probability. Use `health profile hpv-add` only through preview and confirmation.

User: “给我看看长期健康重点。”

Call `health profile priorities --json` or `health profile summary --json`. Present the returned
known problem, current status and next attention in priority order. Never invent a total health,
immune or inflammation score.
