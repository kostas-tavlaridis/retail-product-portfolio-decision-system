# Retail Product Portfolio Decision System

**From transaction data to product-level management decisions.** This portfolio project examines 1,894 products, distinguishes recurring patterns from structural extremes, and turns the evidence into governance actions and a priority queue. The case study and executive report explain the business decision; the notebook, SQL, Python pipeline, exports, and Power BI file make the reasoning inspectable.

## Choose a reading path

| Deliverable | Start here | What you will find |
| --- | --- | --- |
| Business story | [Case study](case-study/CASE_STUDY.md) | Problem, method, findings, limitations, and diagrams |
| Management brief | [Executive report (PDF)](executive-report/EXECUTIVE_REPORT.pdf) | Concise decision narrative; [editable PPTX](executive-report/EXECUTIVE_REPORT.pptx) |
| Interactive decision layer | [Power BI dashboard guide](dashboard/POWER_BI_DASHBOARD.md) | Four pages, screenshots, and a downloadable PBIX |
| Analytical walkthrough | [Notebook](analytical-notebook/README.md) | Chapter-by-chapter evidence and implementation |
| Reusable analytical engine | [Python pipeline](python/README.md) | Nine validated chapters, architecture guide, and exported audit evidence |
| Data preparation | [SQL audit and cleaning](sql/README.md) | Raw-data controls, cleaning decisions, and export to Python |

## How the pieces connect

The [SQL workflow](sql/SUPERSTORE_CLEANING_PROCESS.md) produces `clean_superstore_csv_export.csv` from the raw Superstore data. The [Python pipeline](python/Product_Portfolio_Code_Architecture_Guide.md) builds product KPIs, analytical roles, governance decisions, and priority zones; its committed output tables and figures are in [`python/reports/`](python/reports/). The [analytical notebook](analytical-notebook/Product_Portfolio_Risk_Performance.ipynb) calls the same chapter modules and explains the analysis step by step. The [Power BI dashboard](dashboard/POWER_BI_DASHBOARD.md) uses an embedded snapshot of the governance workbook to let a reviewer inspect the management decisions. The case study and executive report communicate the conclusions.

## Reproducing the analysis

The raw source data and SQL-cleaned input CSV are not included in this repository. Export the final result from the SQL workflow as `clean_superstore_csv_export.csv` into the repository root, then from that root run:

```bash
python -m pip install -r python/requirements.txt
python python/run_analysis.py --no-show
```

The runner writes to `python/reports/` by default. To use the notebook instead, see its [setup instructions](analytical-notebook/README.md). Existing exports with matching names may be replaced when the analysis runs. The PBIX embeds a static workbook copy, so regenerating the Excel export does not automatically refresh the dashboard.
