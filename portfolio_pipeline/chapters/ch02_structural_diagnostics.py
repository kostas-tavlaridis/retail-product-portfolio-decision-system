"""Chapter 02 — Structural Portfolio Diagnostics.

Purpose
-------
Test whether product economics are broadly uniform or already exhibit the
concentration, asymmetry, cross-category dispersion, and recurring downside
that justify deeper structural modelling.

This chapter is descriptive. It does not assign clusters, analytical roles,
governance states, or management actions. Its three persistent outputs are an
executive four-panel diagnostic figure and two compact audit CSV files.

The four panels answer four distinct questions: is value concentrated, is the
profit distribution asymmetric, do categories share one economic centre, and
is loss exposure recurrent across products? Together they establish whether a
homogeneous portfolio assumption is defensible before any segmentation occurs.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

try:
    from IPython.display import display as _display
except ImportError:  # pragma: no cover - used only outside notebook runtimes.
    def _display(value: object) -> None:
        """Fallback table preview when IPython is not installed."""

        print(value)

from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.contracts import Chapter02Result
from portfolio_pipeline.validation import validate_chapter_02


def clip_for_display(
    values: np.ndarray,
    lower_q: float = 1,
    upper_q: float = 99,
) -> np.ndarray:
    """Winsorize one plotted series only; never modify analytical evidence."""

    lower, upper = np.percentile(values, [lower_q, upper_q])
    return np.clip(values, lower, upper)


def prepare_structural_diagnostics(
    product_stage1: pd.DataFrame,
) -> dict[str, object]:
    """Prepare the reusable evidence behind all four diagnostic panels."""

    # A) Profit concentration — cumulative positive-profit Pareto.
    # The question is deliberately narrower than net-profit concentration:
    # among products that generate profit, how many create most positive value?
    pareto_df = (
        product_stage1.loc[product_stage1["total_profit"] > 0]
        .sort_values("total_profit", ascending=False)
        .reset_index(drop=True)
        .copy()
    )

    if pareto_df.empty:
        raise ValueError("No positive-profit products are available for the Pareto diagnostic.")

    pareto_total_profit = pareto_df["total_profit"].sum()
    pareto_df["cum_profit_share"] = (
        pareto_df["total_profit"].cumsum() / pareto_total_profit
    )
    pareto_df["cum_profit_share_pct"] = pareto_df["cum_profit_share"] * 100
    pareto_x = np.arange(1, len(pareto_df) + 1)
    # The first True position is the minimum number of profitable products
    # required to reach 80% of all positive profit.  Loss-makers are excluded
    # from this denominator so positive value creation is not netted against
    # downside before concentration is measured.
    pareto_80_idx = np.argmax(pareto_df["cum_profit_share"].values >= 0.80)
    pareto_80_count = int(pareto_x[pareto_80_idx])

    top_10_n_positive = max(1, int(np.ceil(len(pareto_df) * 0.10)))
    top_10_positive_profit_share = (
        pareto_df["total_profit"].head(top_10_n_positive).sum()
        / pareto_total_profit
    )

    # B) Product-profit distribution.
    # The chart is restricted to the central P01–P99 interval for readability
    # only.  The full distribution remains unchanged and supplies the mean and
    # median; their separation is the direct diagnostic of economic skew.
    profit_dist = product_stage1["total_profit"].dropna().copy()
    profit_lower = profit_dist.quantile(0.01)
    profit_upper = profit_dist.quantile(0.99)
    profit_dist_trim = profit_dist[
        (profit_dist >= profit_lower) & (profit_dist <= profit_upper)
    ].copy()

    if profit_dist_trim.nunique() < 2:
        raise ValueError("Profit distribution has insufficient variation for KDE estimation.")

    # KDE estimates a continuous density whose total area is one.  It describes
    # distributional shape, not product counts or economic contribution.
    kde = gaussian_kde(profit_dist_trim)
    x_vals = np.linspace(profit_lower, profit_upper, 500)
    profit_mean = profit_dist.mean()
    profit_median = profit_dist.median()

    # C) Category dispersion.
    # Each category is clipped independently for display so extreme products do
    # not flatten the boxplots.  The category median ordering is calculated from
    # unmodified values; no stored product value or downstream KPI is changed.
    cat_medians = (
        product_stage1.groupby("category")["total_profit"]
        .median()
        .sort_values(ascending=False)
    )
    ordered_categories = cat_medians.index.tolist()
    category_box_data = [
        clip_for_display(
            product_stage1.loc[
                product_stage1["category"] == category,
                "total_profit",
            ]
            .dropna()
            .values
        )
        for category in ordered_categories
    ]

    # D) Loss exposure bands.
    # The continuous percentage is retained in product_stage1; these buckets are
    # a manager-readable presentation layer used only by the diagnostic figure.
    # The >30% headline is deliberately a frequency threshold, not a statement
    # about the monetary size of product losses.
    loss_dist = product_stage1["pct_orders_loss"].dropna().copy()
    loss_bins = [-0.001, 0.00, 0.10, 0.20, 0.30, 0.40, 0.50, 1.00]
    loss_labels = ["0%", "0–10%", "10–20%", "20–30%", "30–40%", "40–50%", "50%+"]
    loss_bucket = pd.cut(
        loss_dist,
        bins=loss_bins,
        labels=loss_labels,
        include_lowest=True,
    )
    loss_bucket_counts = loss_bucket.value_counts().sort_index()
    high_loss_share = (loss_dist > 0.30).mean()

    return {
        "pareto_df": pareto_df,
        "pareto_x": pareto_x,
        "pareto_80_count": pareto_80_count,
        "top_10_positive_profit_share": top_10_positive_profit_share,
        "profit_dist_trim": profit_dist_trim,
        "profit_lower": profit_lower,
        "profit_upper": profit_upper,
        "x_vals": x_vals,
        "kde": kde,
        "profit_mean": profit_mean,
        "profit_median": profit_median,
        "ordered_categories": ordered_categories,
        "category_box_data": category_box_data,
        "loss_bucket_counts": loss_bucket_counts,
        "high_loss_share": high_loss_share,
    }


def render_structural_dashboard(
    stage1_diag: dict[str, object],
    dashboard_path: Path,
    *,
    show_figure: bool,
) -> None:
    """Render and export the notebook's four-panel structural dashboard."""

    fig, axes = plt.subplots(2, 2, figsize=(22, 14))
    fig.patch.set_facecolor("white")

    # A. Profit Concentration
    ax = axes[0, 0]
    ax.plot(
        stage1_diag["pareto_x"],
        stage1_diag["pareto_df"]["cum_profit_share_pct"],
        marker="o",
        markersize=3.2,
        linewidth=3.0,
        label="Profit Pareto",
    )
    ax.axhline(80, linestyle="--", linewidth=1.6, label="80% cumulative profit")
    ax.axvline(
        stage1_diag["pareto_80_count"],
        linestyle=":",
        linewidth=1.8,
        label=f"80% threshold: {stage1_diag['pareto_80_count']:,} products",
    )
    ax.text(
        0.03,
        0.08,
        "Top 10% positive-profit share: "
        f"{stage1_diag['top_10_positive_profit_share']:.1%}",
        transform=ax.transAxes,
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="lightgray"),
    )
    ax.set_title("A. Profit Concentration", fontsize=15, fontweight="bold")
    ax.set_xlabel("Products ranked by positive profit")
    ax.set_ylabel("Cumulative % of positive profit")
    ax.set_ylim(0, 102)
    ax.grid(axis="y", linestyle=":", alpha=0.35)
    ax.legend(loc="lower right", frameon=True, fontsize=10)

    # B. Profit Distribution Shape
    ax = axes[0, 1]
    ax.hist(
        stage1_diag["profit_dist_trim"],
        bins=50,
        density=True,
        alpha=0.45,
        label="Density histogram",
    )
    ax.plot(
        stage1_diag["x_vals"],
        stage1_diag["kde"](stage1_diag["x_vals"]),
        linewidth=2.8,
        color="orange",
        label="KDE curve",
    )
    ax.axvline(
        stage1_diag["profit_mean"],
        color="crimson",
        linestyle="--",
        linewidth=2.2,
        label=f"Mean = {stage1_diag['profit_mean']:.1f}",
    )
    ax.axvline(
        stage1_diag["profit_median"],
        color="darkgreen",
        linestyle=":",
        linewidth=2.5,
        label=f"Median = {stage1_diag['profit_median']:.1f}",
    )
    ax.set_xlim(stage1_diag["profit_lower"], stage1_diag["profit_upper"])
    ax.set_title("B. Profit Distribution Shape", fontsize=15, fontweight="bold")
    ax.set_xlabel("Product Profit")
    ax.set_ylabel("Density")
    ax.grid(axis="y", linestyle=":", alpha=0.35)
    ax.legend(loc="upper right", frameon=True, fontsize=10)

    # C. Category Profit Dispersion
    ax = axes[1, 0]
    ax.boxplot(
        stage1_diag["category_box_data"],
        tick_labels=stage1_diag["ordered_categories"],
        showfliers=True,
        patch_artist=True,
        boxprops=dict(facecolor="forestgreen", alpha=0.55),
        medianprops=dict(color="darkgreen", linewidth=2.2),
        whiskerprops=dict(color="gray", linewidth=1.1),
        capprops=dict(color="gray", linewidth=1.1),
    )
    ax.axhline(0, color="grey", linewidth=1.1, linestyle="--")
    ax.set_title("C. Category Profit Dispersion", fontsize=15, fontweight="bold")
    ax.set_xlabel("Category")
    ax.set_ylabel("Product Profit")
    ax.grid(axis="y", linestyle=":", alpha=0.35)

    # D. Loss Exposure Structure
    ax = axes[1, 1]
    ax.bar(
        stage1_diag["loss_bucket_counts"].index.astype(str),
        stage1_diag["loss_bucket_counts"].values,
        label="Number of products",
    )
    ax.axvline(3.5, linestyle="--", linewidth=1.7, label="30% loss-rate threshold")
    for index, value in enumerate(stage1_diag["loss_bucket_counts"].values):
        ax.text(
            index,
            value + max(stage1_diag["loss_bucket_counts"].values) * 0.01,
            f"{value}",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    ax.text(
        0.03,
        0.86,
        f"Products >30% loss rate: {stage1_diag['high_loss_share']:.1%}",
        transform=ax.transAxes,
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="lightgray"),
    )
    ax.set_title("D. Loss Exposure Structure", fontsize=15, fontweight="bold")
    ax.set_xlabel("Share of Orders with Loss")
    ax.set_ylabel("Number of Products")
    ax.grid(axis="y", linestyle=":", alpha=0.35)
    ax.legend(loc="upper right", frameon=True, fontsize=10)

    for axis in axes.flat:
        axis.tick_params(axis="both", labelsize=11)

    plt.tight_layout()
    fig.savefig(dashboard_path, dpi=300, bbox_inches="tight")
    if show_figure:
        plt.show()
    else:
        plt.close(fig)


def build_structural_summary(
    product_stage1: pd.DataFrame,
    stage1_diag: dict[str, object],
) -> pd.DataFrame:
    """Build the notebook's compact six-metric diagnostic summary."""

    top_n_all = max(1, int(np.ceil(len(product_stage1) * 0.10)))
    top_10pct_profit_share = (
        product_stage1.nlargest(top_n_all, "total_profit")["total_profit"].sum()
        / product_stage1["total_profit"].sum()
        * 100
    )
    pct_products_loss_gt_30 = (
        (product_stage1["pct_orders_loss"] > 0.30).mean() * 100
    )

    return pd.DataFrame(
        {
            "Metric": [
                "Top 10% of products — net profit share",
                "Top 10% of profitable products — positive-profit share",
                "Products with >30% loss-making orders",
                "Products required to reach 80% of positive profit",
                "Mean product profit",
                "Median product profit",
            ],
            "Value": [
                f"{top_10pct_profit_share:.1f}%",
                f"{stage1_diag['top_10_positive_profit_share'] * 100:.1f}%",
                f"{pct_products_loss_gt_30:.1f}%",
                f"{stage1_diag['pareto_80_count']:,}",
                f"€{stage1_diag['profit_mean']:,.1f}",
                f"€{stage1_diag['profit_median']:,.1f}",
            ],
        }
    )


def run_chapter_02(
    config: AnalysisConfig,
    product_stage1: pd.DataFrame,
    *,
    show_dashboard: bool = True,
    show_summary: bool = True,
) -> Chapter02Result:
    """Execute, export, and validate the complete Chapter 02 stage."""

    config.prepare_output_directories()
    stage1_diag = prepare_structural_diagnostics(product_stage1)
    dashboard_path = config.figures_dir / "stage1_diagnostic_dashboard.png"
    render_structural_dashboard(
        stage1_diag,
        dashboard_path,
        show_figure=show_dashboard,
    )

    stage1_summary_stats = build_structural_summary(product_stage1, stage1_diag)
    if show_summary:
        _display(stage1_summary_stats)

    product_diagnostics_path = config.reports_dir / "stage1_product_diagnostics.csv"
    structural_summary_path = config.reports_dir / "stage1_structural_summary.csv"
    product_stage1.to_csv(product_diagnostics_path, index=False)
    stage1_summary_stats.to_csv(structural_summary_path, index=False)

    result = Chapter02Result(
        stage1_diag=stage1_diag,
        stage1_summary_stats=stage1_summary_stats,
        dashboard_path=dashboard_path,
        product_diagnostics_path=product_diagnostics_path,
        structural_summary_path=structural_summary_path,
    )
    validate_chapter_02(
        result,
        product_stage1=product_stage1,
        strict_project_baseline=config.strict_project_baseline,
    )
    return result
