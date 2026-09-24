# SQL audit and cleaning

Read the [cleaning process](SUPERSTORE_CLEANING_PROCESS.md) alongside the [MySQL script](superstore_sql_audit_cleaning_pipeline.sql). The workflow checks grain, entity consistency, duplicates, fields, and reconciliation before exporting the validated analytical base.

The raw Sample - Superstore CSV is not included. After running the script with that source, export the final result grid as `clean_superstore_csv_export.csv` in UTF-8, comma-separated form and place it in the repository root. The [Python pipeline](../python/README.md) consumes that file. This section documents the SQL preparation and audit; it is not a separate SQL-based dashboard model.
