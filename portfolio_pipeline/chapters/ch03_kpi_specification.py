"""Chapter 03 — KPI Specification.

Purpose
-------
Translate each product's order-level economic behaviour into the four modelling
coordinates used by every later geometry, classification, and governance stage:

* mean order profit;
* stabilized coefficient of variation;
* share of loss-making order occurrences;
* relative portfolio profit impact.

Raw volatility evidence, support limitations, and cap treatment remain attached
to the same product record so modelling stability never removes auditability.

Mathematically, the coordinate vector is
``[mean_order_profit, CV_model, pct_orders_loss, profit_scale]``.  The four
components respectively encode direction, relative dispersion, downside
frequency and portfolio impact.  They are complementary rather than redundant:
two products can have the same mean profitability but radically different risk
frequency, volatility or economic materiality.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from IPython.display import display as _display
except ImportError:  # pragma: no cover - used only outside notebook runtimes.
    def _display(value: object) -> None:
        """Fallback table preview when IPython is not installed."""

        print(value)

from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.contracts import Chapter03Result
from portfolio_pipeline.validation import validate_chapter_03


def build_core_product_metrics(order_prod: pd.DataFrame) -> pd.DataFrame:
    """Aggregate order-level profitability and downside behaviour by product.

    Standard deviation uses pandas' sample definition (ddof=1).  Consequently
    it is undefined for one-observation products; that is evidence about support
    and is handled explicitly by ``stabilize_cv`` rather than silently imputed.
    """

    return (
        order_prod.groupby(["product_id", "product_name"])["profit"]
        .agg(
            n_orders="count",
            mean_order_profit="mean",
            std_order_profit="std",
            pct_orders_loss=lambda series: (series < 0).mean(),
        )
        .reset_index()
    )


def stabilize_cv(vol: pd.DataFrame) -> tuple[pd.DataFrame, float, float]:
    """Create raw and model-stabilized coefficients of variation.

    The raw CV remains an audit field. The modelling version uses a neutral
    coordinate for products with fewer than two order observations and caps
    extreme estimable values at the empirical 99th percentile.
    """

    vol = vol.copy()

    # 1) Dataset-scaled denominator adjustment protects products whose average
    # order profit is close to zero from a mechanically explosive denominator.
    # eps = P01(|mean order profit|), so stabilization follows the observed
    # portfolio scale instead of an arbitrary currency constant.
    eps = float(vol["mean_order_profit"].abs().quantile(0.01))

    # 2) Uncapped diagnostic CV:
    #       CV_raw = std_order_profit / (|mean_order_profit| + eps)
    # Absolute mean keeps dispersion non-negative for loss-making products.
    vol["cv_order_profit_raw"] = (
        vol["std_order_profit"] / (vol["mean_order_profit"].abs() + eps)
    ).replace([np.inf, -np.inf], np.nan)

    # 3) Standard deviation is not estimable with fewer than two observations.
    vol["cv_not_estimable"] = vol["n_orders"] < 2

    # 4) Empirical model cap from finite, estimable CV values only.  P99 limits
    # geometric leverage while remaining data-scaled; it replaces a legacy
    # hard-coded ceiling without suppressing the raw evidence.
    finite_cv = vol.loc[
        vol["cv_order_profit_raw"].notna() & ~vol["cv_not_estimable"],
        "cv_order_profit_raw",
    ]
    if finite_cv.empty:
        raise ValueError("No finite estimable CV values found. Cannot construct CV cap.")
    cv_cap = float(finite_cv.quantile(0.99))

    # 5) Separate modelling coordinate. Non-estimable CV receives a neutral zero
    # geometry coordinate but remains explicitly flagged for governance review.
    # Zero here means "no estimable volatility evidence", not observed stability.
    vol["cv_order_profit_model"] = vol["cv_order_profit_raw"].copy()
    vol.loc[vol["cv_not_estimable"], "cv_order_profit_model"] = 0
    vol["cv_order_profit_model"] = (
        vol["cv_order_profit_model"].fillna(cv_cap).clip(upper=cv_cap)
    )

    # 6) Preserve row-level evidence of every stabilization decision.
    vol["cv_capped_flag"] = (
        vol["cv_order_profit_raw"].notna()
        & (vol["cv_order_profit_raw"] > cv_cap)
    )
    vol["cv_cap_used"] = cv_cap
    vol["cv_epsilon_used"] = eps

    return vol, eps, cv_cap


def build_cv_audit(vol: pd.DataFrame, eps: float, cv_cap: float) -> pd.DataFrame:
    """Build the notebook's twelve-metric CV stabilization audit."""

    return pd.DataFrame(
        {
            "metric": [
                "cv_epsilon",
                "cv_cap_empirical_p99",
                "products_total",
                "cv_not_estimable_products",
                "cv_not_estimable_share_pct",
                "cv_capped_products",
                "cv_capped_share_pct",
                "raw_cv_p50",
                "raw_cv_p90",
                "raw_cv_p95",
                "raw_cv_p99",
                "raw_cv_max",
            ],
            "value": [
                eps,
                cv_cap,
                len(vol),
                int(vol["cv_not_estimable"].sum()),
                100 * vol["cv_not_estimable"].mean(),
                int(vol["cv_capped_flag"].sum()),
                100 * vol["cv_capped_flag"].mean(),
                vol["cv_order_profit_raw"].quantile(0.50),
                vol["cv_order_profit_raw"].quantile(0.90),
                vol["cv_order_profit_raw"].quantile(0.95),
                vol["cv_order_profit_raw"].quantile(0.99),
                vol["cv_order_profit_raw"].max(),
            ],
        }
    )


def build_final_kpi_profile(
    totals: pd.DataFrame,
    vol: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge total economics with order behaviour and create final KPI fields."""

    product_metrics = (
        totals.merge(vol, on=["product_id", "product_name"])
        .sort_values("total_profit", ascending=False)
        .reset_index(drop=True)
    )

    # Relative economic impact:
    #       profit_scale_i = total_profit_i / max_j(|total_profit_j|)
    # It lies in [-1, 1]; sign preserves value/loss direction and magnitude
    # expresses materiality relative to the portfolio's most extreme product.
    max_abs_profit = product_metrics["total_profit"].abs().max()
    product_metrics["profit_scale"] = np.where(
        max_abs_profit == 0,
        0,
        product_metrics["total_profit"] / max_abs_profit,
    )

    # Downstream geometry uses stabilized CV while raw CV and support flags stay
    # on the same canonical product table for later governance decisions.
    product_metrics["cv_order_profit"] = product_metrics["cv_order_profit_model"]
    product_metrics["mean_order_profit"] = product_metrics["mean_order_profit"].fillna(0)
    product_metrics["pct_orders_loss"] = product_metrics["pct_orders_loss"].fillna(0)

    return product_metrics, product_metrics.copy()


def run_chapter_03(
    config: AnalysisConfig,
    order_prod: pd.DataFrame,
    totals: pd.DataFrame,
    *,
    show_audit: bool = True,
    show_preview: bool = True,
) -> Chapter03Result:
    """Execute and validate the complete Chapter 03 KPI stage."""

    vol = build_core_product_metrics(order_prod)
    vol, eps, cv_cap = stabilize_cv(vol)
    cv_audit = build_cv_audit(vol, eps, cv_cap)
    if show_audit:
        _display(cv_audit.round(4))

    product_metrics, df_seg = build_final_kpi_profile(totals, vol)
    if show_preview:
        _display(
            df_seg[
                [
                    "product_id",
                    "product_name",
                    "mean_order_profit",
                    "cv_order_profit",
                    "pct_orders_loss",
                    "profit_scale",
                ]
            ].head()
        )

    result = Chapter03Result(
        vol=vol,
        cv_audit=cv_audit,
        product_metrics=product_metrics,
        df_seg=df_seg,
        cv_epsilon=eps,
        cv_cap=cv_cap,
    )
    validate_chapter_03(
        result,
        order_prod=order_prod,
        totals=totals,
        strict_project_baseline=config.strict_project_baseline,
    )
    return result
