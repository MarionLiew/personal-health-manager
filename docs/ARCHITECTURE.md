# Architecture

## Decision summary

The first release is a Python 3.11 monolith with Typer, Pydantic v2, SQLAlchemy 2, SQLite, and
numbered in-process migrations. This keeps deployment local and inspectable. SQLAlchemy gives a
mature transaction and schema layer without introducing a service. JSON is the only Hermes-facing
contract.

```text
WeChat -> Hermes personal-health-manager -> health CLI -> services/rules
                                                 |          |
                                                 v          v
                                            SQLite      local files
```

The CLI owns validation, transactions, deterministic calculations, audits, backup/restore, and all
medical facts. Importers only produce candidates. A mutating flow is preview -> explicit confirm ->
transaction/audit; never preview -> implicit write. Original files are immutable copies referenced
by SHA-256. Hermes has no SQL or direct database/file mutation route.

The schema uses first-class provenance columns and validated JSON `details` for evolving domain
fields in v1. High-risk dose, source-document, import, and HealthKit deduplication fields are
first-class columns. Future schema evolution must be additive and migration-backed.

