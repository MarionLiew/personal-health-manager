# WeChat interaction examples

## Medical PDF attachments

User sends one or several medical PDFs without text.

1. Do not extract or summarize them with Python or a generic PDF/document tool.
2. For each exact attachment path, run `health record import FILE --dry-run --json` once.
3. Return one row per file: filename, parser, duplicate state, candidate count, uncertainties and
   whether it is eligible for confirmation. Say “尚未保存” for every successful dry-run.
4. If any command returns `UNSAFE_PATH` or another error, say “未导入”, include the error code and
   stop repeating the same failing command. Never replace a failed import with a prose-only summary.
5. Ask the user to confirm importing the successfully previewed files. Only then run the same
   commands with `--confirm --json` and return `source_document_id` and `import_id` for each.
6. The import confirmation preserves originals and creates candidates; it does not make candidates
   formal medical facts. Show candidate IDs and ask which facts to confirm separately.

Never say “原始 PDF 已保留” after only reading the files or after a dry-run/error.

If the user says “重新导入刚才的文件” after a failed attempt, execute a fresh dry-run for every
attachment path still present in the conversation. Do not call only `--help`, and do not reuse the
earlier error table. Build the new table exclusively from the new CLI JSON responses.

If the file is already saved and the user asks to fix an incorrect preview, do not import the cache
copy again. Run `health record reparse SOURCE_DOCUMENT_ID --dry-run --json`, show the replacement
candidates and IDs that would be superseded, and ask for confirmation. After explicit approval run
the same command with `--confirm --json`; state clearly that the new candidates are still unconfirmed
medical facts until the user selects candidate IDs.

If a PDF returns “no extractable text”, say that no fields were guessed and ask whether to use local
OCR. After approval, run `health record reparse SOURCE_DOCUMENT_ID --ocr --dry-run --json` for a
saved source. Display the OCR engine, confidence, extracted source text, candidate IDs and every
uncertain date/number/unit/side/location. A user must verify those fields before reparse confirmation,
and must later select candidate IDs before any medical fact becomes formal.

## Read-only routing

User: “查看我的健康概览”

Run `health profile summary --json`. Return known long-term issues, current status, monitoring items,
priorities, evidence sources and uncertainties. Do not produce a total health score.

User: “整理我的耳鼻喉复诊资料”

Run `health visit-summary --department 耳鼻喉科 --json`. Keep the returned evidence types and data
gaps distinct. If the user also asks what to discuss, run
`health doctor-questions --department 耳鼻喉科 --json`.

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

## Local GPT analysis export

User: “把我的资料导出给GPT分析。”

1. Run `health export gpt-bundle --output health-analysis.json --dry-run --json`.
2. Show confirmed-record counts, source count, pending-candidate count, whether institutions are
   included, and the exclusions for raw documents, original text and images.
3. Explain that no upload occurs and that the resulting health JSON remains sensitive.
4. Ask whether to create the local file. Only after approval repeat with `--confirm --json`.
5. Never attach or transmit the result automatically. Add `--include-pending` only if the user asks
   to include unconfirmed candidates, and keep their `system_inference` label explicit.
