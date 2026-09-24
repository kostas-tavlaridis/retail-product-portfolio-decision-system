# Analytical notebook

[Open the notebook](Product_Portfolio_Risk_Performance.ipynb) for the detailed chapter-by-chapter analysis. It imports the same modules used by the [Python runner](../python/README.md) and writes audit artifacts to [`python/reports/`](../python/reports/).

The notebook includes saved results from a prior run. To run it locally, install [`python/requirements.txt`](../python/requirements.txt), place the SQL-cleaned `clean_superstore_csv_export.csv` in the repository root, and launch Jupyter from either the repository root or this folder. Its setup cell detects those two working directories; if your kernel starts elsewhere, set `PROJECT_ROOT` to the repository root. Restart the kernel and run all cells. A run can replace committed files with matching names in `python/reports/`.

The committed [tables and figures](../python/reports/) provide a browsable snapshot even when the source CSV is unavailable.
