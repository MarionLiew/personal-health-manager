# Apple Health

Phase 5 will stream `export.xml` directly or from a bounded safe ZIP, normalize timezone/source
metadata, and deduplicate by HealthKit UUID and content hash. Unknown record types are retained as
raw typed metadata without blocking the batch. Step data from overlapping devices/apps is not
blindly summed. Undo marks the import batch and its samples rather than deleting audit history.

