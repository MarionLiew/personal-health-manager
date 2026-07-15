# Threat model

Protected assets include health records, identity fields, raw reports, DICOM identifiers, databases,
backup keys, and audit integrity. Primary threats are accidental Git inclusion, over-broad file
access, malicious archives, symlink/path traversal, duplicate imports, parser confusion, sensitive
logging, unconfirmed writes, direct Hermes SQL, and tampered backups.

Controls include deny-by-default import roots, content hashes, immutable originals, `.gitignore`,
0700 data directories, SQLite foreign keys/transactions, stable confirmation gates, audit logs,
archive count/size/ratio limits, no symlink extraction, response validation, and integrity-checked
backups. Logs may contain operation, opaque IDs, result/error, parser version, and hash prefix only.

Hermes uses a separate deployment config that permits only its detected `cache/documents` directory,
not `~/.hermes` or the user home. The loader rejects external roots that are the home directory or
one of its ancestors. Files still pass the same hash, parser, preview and confirmation gates.

Residual risk: local machine compromise or an unlocked user session exposes local plaintext data.
Encrypted backups protect copies, not the live database. DICOM and document parsers are an attack
surface and should process only user-selected files in quarantine. Dependencies require routine
security updates.
