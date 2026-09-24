# Python pipeline

The pipeline implements nine ordered, validated chapters. Start with the [architecture guide](Product_Portfolio_Code_Architecture_Guide.md), then inspect [`run_analysis.py`](run_analysis.py) for orchestration and [`portfolio_pipeline/`](portfolio_pipeline/) for the chapter code, contracts, configuration, and validation. Committed audit tables, the governance workbook, and analytical figures are in [`reports/`](reports/).

## Run locally

The input `clean_superstore_csv_export.csv` is created by the [SQL workflow](../sql/README.md) and is not committed. Place it in the repository root, then run from that root:

```bash
python -m pip install -r python/requirements.txt
python python/run_analysis.py --no-show
```

The defaults resolve the input from the repository root and write outputs to `python/reports/` regardless of the shell's working directory. Use `--input-csv` and `--reports-dir` to override either location. Re-running the pipeline can replace committed exports with matching names. The [notebook](../analytical-notebook/README.md) calls the same chapter modules and provides the longer analytical walkthrough.
