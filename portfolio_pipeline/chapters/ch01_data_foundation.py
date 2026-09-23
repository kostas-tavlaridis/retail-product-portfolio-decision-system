"""Chapter 01 — Data Foundation & Analytical Grain.

Purpose
-------
Load the SQL-cleaned Superstore export, restore pandas-native data types, and
construct the two analytical grains required by the downstream pipeline:

1. one row per order × product occurrence;
2. one row per unique product ID + product name pair.

The SQL pipeline owns data cleaning. This module does not remove observations,
impute values, or redefine business records. Its job is limited to type
restoration, grain construction, economic reconciliation, and the first
product-level diagnostic profile.

Grain is the central control in this stage. Transaction rows are first collapsed
to order x product occurrences so an order containing repeated source lines
cannot receive artificial behavioural weight. Product decisions then use the
observed Product ID x Product Name pair because Product ID alone is not unique
in this dataset. Both grains are retained explicitly for downstream use.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

try:
    from IPython.display import display as _display
except ImportError:  # pragma: no cover - used only in non-notebook environments.
    def _display(value: object) -> None:
        """Fallback preview when IPython is not installed."""

        print(value)

from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.contracts import Chapter01Result
from portfolio_pipeline.validation import (
    validate_chapter_01,
    validate_chapter_01_input_schema,
)


NUMERIC_COLUMNS = [
    "sales",
    "profit",
    "discount",
    "quantity",
    "postal_code",
]


def load_sql_cleaned_data(
    input_csv: str | Path,
    *,
    show_reconciliation: bool = True,
) -> pd.DataFrame:
    """Load the SQL-cleaned CSV and restore analytical data types.

    The CSV is expected to be the validated export from the SQL cleaning
    pipeline. CSV storage removes native date metadata and can also cause
    numeric fields to be read as text, so those pandas types are restored here.
    No rows are filtered, dropped, or otherwise cleaned by this function.
    """

    input_csv = Path(input_csv)
    if not input_csv.is_file():
        raise FileNotFoundError(
            f"SQL-cleaned input CSV was not found: {input_csv.resolve()}"
        )

    df = pd.read_csv(input_csv, encoding="utf-8")
    validate_chapter_01_input_schema(df)

    # SQL already parsed the dates, but CSV export stores them as text again.
    # errors="coerce" retains defensive behaviour for unexpected invalid values.
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["ship_date"] = pd.to_datetime(df["ship_date"], errors="coerce")

    # Restore every numeric column used by the downstream analytical pipeline.
    # The validated SQL baseline should not create unexpected missing values.
    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if show_reconciliation:
        _print_input_reconciliation(df)

    return df


def _print_input_reconciliation(df: pd.DataFrame) -> None:
    """Reproduce the compact Chapter 01 notebook reconciliation readout."""

    print("=== SQL-CLEANED DATASET LOADED INTO PYTHON ===")
    print(f"Rows:                  {len(df):,}")
    print(f"Distinct orders:       {df['order_id'].nunique():,}")
    print(f"Distinct customers:    {df['customer_id'].nunique():,}")
    print(f"Distinct product IDs:  {df['product_id'].nunique():,}")
    print(
        "Product ID + name pairs: "
        f"{df[['product_id', 'product_name']].drop_duplicates().shape[0]:,}"
    )
    print(f"Total sales:           {df['sales'].sum():,.2f}")
    print(f"Total profit:          {df['profit'].sum():,.2f}")


def build_analytical_grain(
    df: pd.DataFrame,
    *,
    show_preview: bool = True,
) -> Chapter01Result:
    """Construct the two canonical grains and reconcile their economics.

    ``order_prod`` is the statistical observation unit used for mean profit,
    volatility and loss frequency.  ``totals`` and ``product_stage1`` are the
    decision grain.  Keeping them separate prevents transaction-line frequency
    from being confused with either order support or product count.
    """

    validate_chapter_01_input_schema(df)

    # A) Order × product analytical grain.
    # Multiple transaction rows for the same product in the same order are
    # collapsed before profitability behaviour is calculated. This prevents
    # duplicated order-product records from inflating sales, profit, or support.
    order_prod = (
        df.groupby(
            [
                "order_id",
                "product_id",
                "product_name",
                "category",
                "sub_category",
            ],
            as_index=False,
        )
        .agg(
            sales=("sales", "sum"),
            profit=("profit", "sum"),
        )
    )

    # B) Product-level economic totals.
    # Product ID alone is not fully unique in this project, so the canonical
    # product key remains product_id + product_name throughout the pipeline.
    totals = (
        order_prod.groupby(["product_id", "product_name"], as_index=False)
        .agg(
            total_sales=("sales", "sum"),
            total_profit=("profit", "sum"),
        )
    )

    # Margin is defined only when sales are positive.  np.where preserves the
    # full product universe while making a zero-sales denominator explicit.
    totals["profit_margin"] = np.where(
        totals["total_sales"] > 0,
        totals["total_profit"] / totals["total_sales"],
        np.nan,
    )

    # C) Product dimension used for category/sub-category context downstream.
    # It is descriptive metadata and never participates in product identity.
    product_dim = order_prod[
        [
            "product_id",
            "product_name",
            "category",
            "sub_category",
        ]
    ].drop_duplicates()

    # D) Order-level profitability and downside behaviour per product.
    # pct_orders_loss = count(order-product profit < 0) / observed order count.
    # Zero-profit occurrences are neutral rather than losses, which keeps the
    # downside rate aligned with realized negative economics.
    loss_profile = (
        order_prod.groupby(["product_id", "product_name"])["profit"]
        .agg(
            mean_order_profit="mean",
            pct_orders_loss=lambda series: (series < 0).mean(),
        )
        .reset_index()
    )

    # E) First product-level analytical base.
    # Sorting by total profit reproduces the notebook's manager-facing preview
    # while leaving the product key explicit for all later joins.
    product_stage1 = (
        totals.merge(
            product_dim,
            on=["product_id", "product_name"],
            how="left",
        )
        .merge(
            loss_profile,
            on=["product_id", "product_name"],
            how="left",
        )
        .sort_values("total_profit", ascending=False)
        .reset_index(drop=True)
    )

    result = Chapter01Result(
        df=df,
        order_prod=order_prod,
        totals=totals,
        product_dim=product_dim,
        loss_profile=loss_profile,
        product_stage1=product_stage1,
    )

    if show_preview:
        _display(product_stage1.head())

    return result


def run_chapter_01(
    config: AnalysisConfig,
    *,
    show_reconciliation: bool = True,
    show_preview: bool = True,
) -> Chapter01Result:
    """Execute and validate the complete Chapter 01 stage."""

    df = load_sql_cleaned_data(
        config.input_csv,
        show_reconciliation=show_reconciliation,
    )
    result = build_analytical_grain(df, show_preview=show_preview)
    validate_chapter_01(
        result,
        strict_project_baseline=config.strict_project_baseline,
    )
    return result
