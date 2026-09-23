# Superstore SQL Data Cleaning Process

## Purpose

This document explains the SQL cleaning pipeline used to convert the raw **Sample - Superstore** CSV into the validated analytical file consumed by the downstream Python workflow.

The process follows a deliberate sequence:

**ingestion -> baseline reconciliation -> grain/cardinality -> entity consistency -> keys/duplicate investigation -> field validity -> cross-field rules -> cleaning decisions -> typed clean table -> final QC -> Python handoff**

The guiding principle is simple: **do not change the data before understanding what a row means, how entities relate, and which apparent anomalies are actual errors versus legitimate business behaviour.**

---

## 1. Source and target

### Raw source

The source CSV contains **9,994 raw transaction-line rows** and 21 fields. During ingestion, all fields are initially stored as `TEXT` in MySQL. This is intentional: it prevents the database from silently coercing or rejecting malformed values before the audit has a chance to inspect them.

### Target analytical base

The final SQL table is:

`clean_superstore_sql`

The target grain is:

**one row per `Order ID + Product ID + Product Name`**

This reproduces the previously validated clean base used by the Python project and produces **9,986 rows**.

The existing Python loader expects the exported file:

`clean_superstore_csv_export.csv`

encoded as UTF-8 and exported in the standard comma-separated CSV format.

---

## 2. Baseline reconciliation

Before any cleaning, the source is reconciled so that later changes can be explained rather than guessed.

| Control | Raw baseline |
|---|---:|
| Raw rows | 9,994 |
| Distinct orders | 5,009 |
| Distinct customers | 793 |
| Distinct Product IDs | 1,862 |
| Product ID + Product Name identities | 1,894 |
| Total Sales | 2,297,200.8603 |
| Total Profit | 286,397.0217 |

These values are treated as control totals for the final post-clean reconciliation.

---

## 3. Grain and relationship validation

The first modelling question is not "are there duplicates?" but **"what does one row represent?"**

The audit established that one raw row behaves as a transaction/order line within an order:

- the same `Order ID` can appear across multiple raw rows;
- every order maps to one customer;
- customers can have multiple orders;
- order-level context remains stable while line-level product/measures can vary.

This supports the core relationships:

- `Customer 1:N Order`
- `Order 1:N Transaction Line`

The distinction is important because repeated `Order ID` values are therefore expected behaviour, not duplicates.

---

## 4. Entity consistency and functional dependencies

The audit then tested whether attributes that should describe the same entity remain consistent every time that entity appears.

### Order entity

The following dependencies were supported by the data:

- `Order ID -> Customer ID`
- `Order ID -> Order Date`
- `Order ID -> Ship Date`
- `Order ID -> Ship Mode`

### Customer entity

The following dependencies were supported:

- `Customer ID -> Customer Name`
- `Customer ID -> Segment`

### Product entity

A key finding appeared here.

`Product ID -> Product Name` **does not hold** for the full dataset. There are **32 Product IDs** that map to two different Product Names. This exactly explains the difference between:

- 1,862 distinct Product IDs; and
- 1,894 distinct `Product ID + Product Name` identities.

At the same time, Product classification remained consistent:

- `Product ID -> Category`
- `Product ID -> Sub-Category`
- `Sub-Category -> Category`

### Cleaning consequence

`Product ID` alone is therefore not treated as the complete observed product identity. The downstream analytical identity remains:

**`Product ID + Product Name`**

No Product IDs are rewritten or invented because there is no external product master proving which source value is incorrect.

---

## 5. Geography consistency

The geography hierarchy was checked separately from free-text formatting.

The audit supported:

- `State -> Region`
- `State -> Country`

At order level, destination fields were also consistent: an order did not vary across `City`, `State`, and `Postal Code` in the observed data.

---

## 6. Technical key, business key and collision investigation

### Technical key

`Row ID` contains one unique value per raw row:

- total raw rows: 9,994
- distinct `Row ID`: 9,994

It therefore works as the technical source-row identifier.

### Candidate business key

The natural candidate for the analytical line was:

`Order ID + Product ID + Product Name`

This candidate is not unique in the raw source.

- raw rows: 9,994
- unique candidate-key combinations: 9,986
- excess source occurrences: 8

The collision groups were investigated rather than deleted automatically.

Most repeated groups contain different economic measures, which supports the interpretation that they are repeated/split source lines rather than simple copies. One pair is identical across the business fields and measures except for `Row ID`, making it a strong exact-business-duplicate candidate.

### Final decision

The pipeline **does not delete rows solely from duplicate suspicion**. Without an external source-of-truth, deleting an economically recorded line would be an unsupported assumption and would change the validated source totals.

Instead, the repeated lines are consolidated into the target `Order x Product` analytical grain. This makes the downstream dataset unique at the required grain while preserving source Sales and Profit totals.

---

## 7. Field validity audit

Each field family was validated before assigning final datatypes.

### Technical and business IDs

Checks included:

- `NULL` and blank values;
- leading/trailing whitespace;
- expected ID patterns via `REGEXP`;
- positive integer structure for `Row ID`.

### Dates

`Order Date` and `Ship Date` were loaded as text, then validated with `STR_TO_DATE()` using the expected `MM/DD/YYYY` source format.

The clean layer converts them to real `DATE` columns.

### Categorical fields

`Ship Mode`, `Segment`, `Country`, `Region`, `Category`, and `Sub-Category` were checked for:

- missing/blank values;
- whitespace issues;
- distinct-value frequencies;
- values outside the expected domain.

### Free text

`Customer Name`, `Product Name`, `City`, and `State` were checked for:

- `NULL`/blank values;
- leading/trailing whitespace;
- repeated internal whitespace;
- control characters;
- suspicious string-length ranges.

No strict "letters only" rule is used because legitimate names and product descriptions can contain numbers and punctuation.

### Monetary and numeric fields

`Sales`, `Profit`, `Quantity`, and `Discount` are validated as numeric strings before conversion.

The clean types are:

- `Sales` -> `DECIMAL(18,4)`
- `Profit` -> `DECIMAL(18,4)`
- `Quantity` -> positive `INT UNSIGNED`
- `Discount` -> `DECIMAL(10,4)` within `[0,1]`

Observed monetary ranges used during the audit included:

| Metric | Minimum | Maximum |
|---|---:|---:|
| Sales | 0.4440 | 22,638.4800 |
| Profit | -6,599.9780 | 8,399.9760 |
| Sales per unit | 0.336 | 3,773.08 |

Negative Profit is explicitly allowed: it represents a business loss, not automatically bad data.

---

## 8. Postal Code finding and correction

Postal Code is treated as an **identifier**, not as a measure.

The audit found an observed length range of **4 to 5 characters**. Investigation showed that the four-character values are systematically associated with US locations whose ZIP codes begin with `0`.

Examples:

- `2138` -> `02138` (Cambridge, Massachusetts)
- `6010` -> `06010` (Bristol, Connecticut)
- `4401` -> `04401` (Bangor, Maine)
- `3301` -> `03301` (Concord, New Hampshire)

The audit identified **51 distinct four-character ZIP/location combinations covering 438 raw rows**.

### Cleaning rule

The clean SQL layer applies:

`LPAD(postal_code, 5, '0')`

and stores the result as `CHAR(5)` so leading zeros are preserved.

### Python compatibility note

The current Python loader later converts `postal_code` to numeric for backward compatibility. That does not affect the existing product analytics because Postal Code is not analytically central there, but it will remove the leading zero again inside pandas. If ZIP-level geography becomes analytically important, `postal_code` should be removed from the Python `numeric_cols` list and kept as string.

---

## 9. Cross-field business rules

After individual fields were validated, the audit checked whether values make sense together.

### Shipping dates

Rule:

`Ship Date >= Order Date`

Result:

- violations: 0
- minimum shipping delay: 0 days
- maximum shipping delay: 7 days

Same-day shipping is therefore valid in the observed data.

### Sales and Profit

`Profit` may be negative, zero, or positive. Rows where `Profit > Sales` were treated as diagnostic candidates rather than automatically removed. The validated workflow did not identify a structural issue requiring a cleaning rule.

### Sales and Quantity

Because Sales and Quantity were both validated as positive, `Sales / Quantity` was used as a sanity metric. The observed range was positive throughout; large values were treated as possible high-value products, not automatic errors.

### Order destination

`City`, `State`, and `Postal Code` remained consistent within the same Order ID in the observed source.

---

## 10. Cleaning transformations

The final SQL transformation creates `clean_superstore_sql` with 21 snake_case fields matching the existing Python interface.

### Target grain

The table is grouped by:

- `order_id`
- `product_id`
- `product_name`

### Additive measures

When multiple raw rows map to the same target grain:

- `sales` -> `SUM()`
- `quantity` -> `SUM()`
- `profit` -> `SUM()`

### Discount

Discount is a rate and must not be summed. The pipeline first verifies that repeated target-grain groups contain only one distinct Discount value. The common value is then retained with `MAX()`.

### Stable entity attributes

Order, customer, product-classification, and geography attributes were already shown to be stable by the functional-dependency audit. `MAX()` is therefore used only as a deterministic way to collapse repeated identical values inside each target-grain group; it is not used to hide conflicts.

### Row ID

The clean table keeps the minimum source `Row ID` inside each consolidated group. This preserves the existing Python interface and remains unique in the clean table, but it should be interpreted as a **representative source-row identifier**, not as the complete lineage of every raw row contributing to the aggregate.

---

## 11. Final clean schema

| Field | Clean datatype | Treatment |
|---|---|---|
| `row_id` | `INT UNSIGNED` | minimum source Row ID per clean group |
| `order_id` | `VARCHAR(14)` | trimmed |
| `order_date` | `DATE` | parsed from source text |
| `ship_date` | `DATE` | parsed from source text |
| `ship_mode` | `VARCHAR(30)` | stable value, trimmed |
| `customer_id` | `VARCHAR(8)` | stable value, trimmed |
| `customer_name` | `VARCHAR(120)` | stable value, trimmed |
| `segment` | `VARCHAR(30)` | stable value, trimmed |
| `country` | `VARCHAR(60)` | stable value, trimmed |
| `city` | `VARCHAR(120)` | stable value, trimmed |
| `state` | `VARCHAR(120)` | stable value, trimmed |
| `postal_code` | `CHAR(5)` | leading-zero restoration |
| `region` | `VARCHAR(20)` | stable value, trimmed |
| `product_id` | `VARCHAR(15)` | target-grain field |
| `category` | `VARCHAR(50)` | stable value |
| `sub_category` | `VARCHAR(50)` | stable value |
| `product_name` | `VARCHAR(255)` | target-grain field |
| `sales` | `DECIMAL(18,4)` | summed |
| `quantity` | `INT UNSIGNED` | summed |
| `discount` | `DECIMAL(10,4)` | common value retained |
| `profit` | `DECIMAL(18,4)` | summed |

The clean table enforces:

- primary key on `row_id`;
- unique constraint on `(order_id, product_id, product_name)`.

---

## 12. Final QC and reconciliation

Cleaning is complete only if the final table reconciles to the raw baseline.

Expected final controls:

| Control | Raw | Clean | Expected interpretation |
|---|---:|---:|---|
| Rows | 9,994 | 9,986 | 8 excess raw occurrences consolidated |
| Orders | 5,009 | 5,009 | unchanged |
| Customers | 793 | 793 | unchanged |
| Product IDs | 1,862 | 1,862 | unchanged |
| Product ID + Name identities | 1,894 | 1,894 | unchanged |
| Sales | 2,297,200.8603 | 2,297,200.8603 | preserved |
| Profit | 286,397.0217 | 286,397.0217 | preserved |

Additional QC requires:

- zero duplicate rows at the clean target grain;
- all clean ZIP codes have length 5;
- zero `Ship Date < Order Date` violations;
- clean shipping delay remains 0-7 days.

---

## 13. Python handoff

The final MySQL result is exported from `clean_superstore_sql` as:

`clean_superstore_csv_export.csv`

The existing Python analysis reads it with:

```python
df = pd.read_csv(
    SQL_CLEAN_CSV_PATH,
    encoding="utf-8"
)
```

Python then restores pandas-native date/numeric types and saves:

`clean_superstore.pkl`

This keeps the established downstream analysis unchanged while moving the actual data cleaning and validation responsibility into SQL.

---

## 14. Reproducibility and limitations

1. The raw source is never overwritten; `raw_superstore` remains the audit layer.
2. The clean table is rebuilt deterministically from the raw source.
3. No Product ID is rewritten without an external product master.
4. No suspicious duplicate is deleted solely because it looks duplicated; source economic totals are preserved.
5. Postal-code restoration is based on a systematic US leading-zero pattern observed in the data.
6. The target grain is chosen deliberately to match the existing downstream product-analysis architecture.
7. Any future source refresh should rerun the complete audit before assuming the same constraints still hold.

---

## Files in the workflow

- `superstore_sql_audit_cleaning_pipeline.sql` - full ingestion, audit, cleaning, QC and Python-handoff SQL.
- `clean_superstore_csv_export.csv` - export-safe final SQL output exported from MySQL Workbench after the script runs.
- `SUPERSTORE_CLEANING_PROCESS.md` - GitHub-readable documentation of the process and decisions.
