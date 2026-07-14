# Deployment

Use the project-managed environment; do not install packages system-wide.

```bash
uv sync --extra test --extra backup
uv run health init --json
uv run health doctor --json
```

Daily commands run as `uv run health ...`, or install an editable local entry point with
`uv pip install -e .`. Keep the working directory private, ensure `data` remains mode 0700, and do
not synchronize real data to public cloud or Git. Upgrade by verifying a backup, pulling reviewed
code, running `uv sync`, then `health init --json` to apply compatible migrations.

