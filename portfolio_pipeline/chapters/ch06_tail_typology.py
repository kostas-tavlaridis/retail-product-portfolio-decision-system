"""Chapter 06 — Structural Tail Typology.

Purpose
-------
Translate the 72 structural-tail products into three explicit economic regimes,
preserve raw-mechanism overlap and assignment provenance, and combine those
regimes with the four K-means body roles into one closed seven-role taxonomy.

Raw tail flags are non-exclusive. The reporting hierarchy is Loss, then
Volatility, then Impact. Products that entered the tail only through the Mean
Order Profit boundary remain inside the same three-role system through a fully
audited directional assignment.

The tail rules are anchored to the recurring body so extreme observations do
not define their own benchmark. Raw flags preserve all economic mechanisms;
``primary_tail_type`` is only the mutually exclusive reporting owner selected
by precedence. This separation is essential: overlap remains governance
evidence even after every product receives one primary role.
"""

from __future__ import annotations

from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from IPython.display import display as _display
except ImportError:  # pragma: no cover
    def _display(value: object) -> None:
        print(value)

from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.contracts import Chapter04Result, Chapter05Result, Chapter06Result
from portfolio_pipeline.validation import validate_chapter_06


TAIL_ROLE_ORDER = [
    "Extreme Impact Tail",
    "Extreme Volatility Tail",
    "Loss Tail",
]

ANALYTICAL_ROLE_ORDER = [
    "Stable Profit Cluster",
    "High-Impact Profit Cluster",
    "Risk-Oriented Profit Cluster",
    "Stable Loss Cluster",
    "Extreme Impact Tail",
    "Extreme Volatility Tail",
    "Loss Tail",
]


def construct_tail_references(
    df_seg_clusters: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, float, float, float, pd.DataFrame, pd.DataFrame]:
    """Reconstruct the body/tail partition and body-anchored references.

    CV and positive-impact thresholds are the body's P95 values.  Loss uses a
    small materiality tolerance on normalized profit scale rather than any
    negative numerical noise. Body and tail must be disjoint and collectively
    exhaustive before classification can proceed.
    """

    if not df_seg_clusters.index.is_unique:
        raise ValueError("df_seg_clusters must have a unique analytical-row index.")

    body_mask = df_seg_clusters["k_cluster"].ne("Unclustered")
    body = df_seg_clusters.loc[body_mask].copy()
    tail = df_seg_clusters.loc[~body_mask].copy()
    if body.empty or tail.empty:
        raise ValueError("Both clustered body and structural tail are required.")
    if not body.index.intersection(tail.index).empty:
        raise ValueError("Body and tail overlap; the portfolio partition is invalid.")
    partition_index = body.index.append(tail.index)
    if (
        len(partition_index) != len(df_seg_clusters)
        or set(partition_index) != set(df_seg_clusters.index)
    ):
        raise ValueError("Body and tail do not reconstruct the complete portfolio.")

    # Extremes are evaluated against stable geometry. Letting tail products
    # participate in these percentiles would make the exception population move
    # the boundary used to judge itself.
    cv_threshold = float(body["cv_order_profit"].quantile(0.95))
    impact_threshold = float(body["profit_scale"].quantile(0.95))
    loss_scale_tolerance = 0.001
    if not np.isfinite([cv_threshold, impact_threshold, loss_scale_tolerance]).all():
        raise ValueError("At least one tail reference threshold is not finite.")

    reference_table = pd.DataFrame(
        {
            "Tail Mechanism": [
                "Loss Tail",
                "Extreme Volatility Tail",
                "Extreme Impact Tail",
            ],
            "Reference Layer": [
                "Material negative contribution",
                "Clustered-body CV",
                "Clustered-body Profit Scale",
            ],
            "Rule": [
                "profit_scale < -0.001",
                "cv_order_profit > body p95",
                "profit_scale > body p95",
            ],
            "Observed Threshold": [
                -loss_scale_tolerance,
                cv_threshold,
                impact_threshold,
            ],
        }
    )

    portfolio_total_profit = df_seg_clusters["total_profit"].sum()
    if np.isclose(portfolio_total_profit, 0):
        raise ValueError("Portfolio profit is zero; net-profit shares are undefined.")
    materiality = pd.DataFrame(
        {
            "Layer": ["Clustered Body", "Structural Tail"],
            "Products": [len(body), len(tail)],
            "Total Profit": [body["total_profit"].sum(), tail["total_profit"].sum()],
        }
    )
    materiality["Portfolio Share"] = materiality["Products"] / len(df_seg_clusters)
    materiality["Net Profit Share"] = (
        materiality["Total Profit"] / portfolio_total_profit
    )
    return (
        body,
        tail,
        cv_threshold,
        impact_threshold,
        loss_scale_tolerance,
        reference_table,
        materiality,
    )


def classify_structural_tail(
    df_seg_clusters: pd.DataFrame,
    tail: pd.DataFrame,
    body_thresholds_df: pd.DataFrame,
    *,
    cv_threshold: float,
    impact_threshold: float,
    loss_scale_tolerance: float,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    float,
    float,
]:
    """Apply raw mechanisms, directional closure, and primary precedence.

    Raw mechanisms are deliberately non-exclusive.  The primary assignment is
    Loss > Volatility > Impact because realized negative value requires control
    before dispersion, and dispersion requires stabilization before upside can
    be treated as scalable impact. Mean-profit boundary direction closes only
    the cases that crossed Chapter 04 without activating those three mechanisms.
    """

    tail = tail.copy()
    required_boundary_features = {
        "mean_order_profit",
        "cv_order_profit",
        "profit_scale",
    }
    if body_thresholds_df["feature"].duplicated().any():
        raise ValueError("body_thresholds_df contains duplicate feature specifications.")
    missing = required_boundary_features - set(body_thresholds_df["feature"])
    if missing:
        raise ValueError(f"Missing Chapter 04 body boundaries for: {sorted(missing)}")

    boundary_lookup = body_thresholds_df.set_index("feature")[
        ["lower_value", "upper_value"]
    ]
    mean_profit_lower = float(boundary_lookup.loc["mean_order_profit", "lower_value"])
    mean_profit_upper = float(boundary_lookup.loc["mean_order_profit", "upper_value"])

    # Non-exclusive economic mechanisms. ``n_tail_flags`` retains compound
    # structure for the Chapter 07 Tail Overlap signal; it is not discarded when
    # the reporting hierarchy chooses one owner.
    tail["flag_loss"] = tail["profit_scale"] < -loss_scale_tolerance
    tail["flag_volatility"] = tail["cv_order_profit"] > cv_threshold
    tail["flag_impact"] = tail["profit_scale"] > impact_threshold
    raw_flag_cols = ["flag_loss", "flag_volatility", "flag_impact"]
    tail["n_tail_flags"] = tail[raw_flag_cols].sum(axis=1).astype(int)

    # Audit how each product crossed the Chapter 04 body definition.  This makes
    # tail entry and tail-role assignment separately reproducible.
    audit_cols = [
        "product_id",
        "product_name",
        "total_profit",
        "mean_order_profit",
        "cv_order_profit",
        "pct_orders_loss",
        "profit_scale",
        *raw_flag_cols,
        "n_tail_flags",
    ]
    for support_column in ["n_orders", "cv_not_estimable"]:
        if support_column in tail.columns:
            audit_cols.append(support_column)
    tail_entry_audit = tail[audit_cols].copy()
    for feature_name in required_boundary_features:
        lower_value = boundary_lookup.loc[feature_name, "lower_value"]
        upper_value = boundary_lookup.loc[feature_name, "upper_value"]
        tail_entry_audit[f"below_{feature_name}_boundary"] = (
            tail[feature_name] < lower_value
        )
        tail_entry_audit[f"above_{feature_name}_boundary"] = (
            tail[feature_name] > upper_value
        )
    violation_cols = [
        column
        for column in tail_entry_audit.columns
        if column.startswith("below_") or column.startswith("above_")
    ]
    tail_entry_audit["n_body_boundary_violations"] = (
        tail_entry_audit[violation_cols].sum(axis=1).astype(int)
    )
    tail_entry_audit["no_raw_tail_mechanism"] = tail_entry_audit["n_tail_flags"].eq(0)
    mechanism_coverage = pd.DataFrame(
        {
            "Metric": [
                "Tail products",
                "Products with at least one raw mechanism",
                "Products without a raw mechanism",
                "Raw-mechanism coverage",
            ],
            "Value": [
                len(tail_entry_audit),
                int((~tail_entry_audit["no_raw_tail_mechanism"]).sum()),
                int(tail_entry_audit["no_raw_tail_mechanism"].sum()),
                (~tail_entry_audit["no_raw_tail_mechanism"]).mean(),
            ],
        }
    )
    fallback_tail_cases = tail_entry_audit.loc[
        tail_entry_audit["no_raw_tail_mechanism"]
    ].sort_values(["mean_order_profit", "profit_scale"])

    # Primary precedence: Loss > Volatility > Impact. The successive isna masks
    # implement first-match ownership without erasing the original flags.
    tail["primary_tail_type"] = pd.Series(pd.NA, index=tail.index, dtype="object")
    tail["assignment_basis"] = pd.Series(pd.NA, index=tail.index, dtype="object")
    tail["fallback_assignment_flag"] = False

    loss_assignment = tail["flag_loss"]
    tail.loc[loss_assignment, "primary_tail_type"] = "Loss Tail"
    tail.loc[loss_assignment, "assignment_basis"] = "material_negative_profit_scale"

    volatility_assignment = tail["primary_tail_type"].isna() & tail["flag_volatility"]
    tail.loc[volatility_assignment, "primary_tail_type"] = "Extreme Volatility Tail"
    tail.loc[volatility_assignment, "assignment_basis"] = "cv_above_body_p95"

    impact_assignment = tail["primary_tail_type"].isna() & tail["flag_impact"]
    tail.loc[impact_assignment, "primary_tail_type"] = "Extreme Impact Tail"
    tail.loc[impact_assignment, "assignment_basis"] = "profit_scale_above_body_p95"

    # Directional closure applies only when no raw mechanism fired. These are
    # valid structural extremes created solely by the Chapter 04 mean-profit
    # boundary, not residual errors or a hidden fourth tail category.
    upper_assignment = (
        tail["primary_tail_type"].isna()
        & tail["mean_order_profit"].gt(mean_profit_upper)
    )
    tail.loc[upper_assignment, "primary_tail_type"] = "Extreme Impact Tail"
    tail.loc[upper_assignment, "assignment_basis"] = (
        "mean_order_profit_above_selected_upper_boundary"
    )
    tail.loc[upper_assignment, "fallback_assignment_flag"] = True

    lower_assignment = (
        tail["primary_tail_type"].isna()
        & tail["mean_order_profit"].lt(mean_profit_lower)
    )
    tail.loc[lower_assignment, "primary_tail_type"] = "Loss Tail"
    tail.loc[lower_assignment, "assignment_basis"] = (
        "mean_order_profit_below_selected_lower_boundary"
    )
    tail.loc[lower_assignment, "fallback_assignment_flag"] = True

    unresolved = tail["primary_tail_type"].isna() | tail["assignment_basis"].isna()
    if unresolved.any():
        raise ValueError(
            f"{int(unresolved.sum())} structural-tail products remain unassigned."
        )
    valid_types = {"Loss Tail", "Extreme Volatility Tail", "Extreme Impact Tail"}
    if (~tail["primary_tail_type"].isin(valid_types)).any():
        raise ValueError("At least one product received an invalid primary tail type.")
    if not tail["fallback_assignment_flag"].eq(tail["n_tail_flags"].eq(0)).all():
        raise ValueError("Directional flags do not match raw-mechanism coverage.")

    assignment_basis_summary = (
        tail["assignment_basis"]
        .value_counts()
        .rename_axis("Assignment Basis")
        .reset_index(name="Products")
    )
    fallback_cols = [
        "product_id",
        "product_name",
        "total_profit",
        "mean_order_profit",
        "cv_order_profit",
        "pct_orders_loss",
        "profit_scale",
    ]
    for support_column in ["n_orders", "cv_not_estimable"]:
        if support_column in tail.columns:
            fallback_cols.append(support_column)
    fallback_cols.extend(["n_tail_flags", "assignment_basis", "primary_tail_type"])
    fallback_audit = tail.loc[tail["fallback_assignment_flag"], fallback_cols].copy()

    # Rejoin by the preserved analytical-row index; product ID alone is not
    # unique. A validated one-to-one join is the coverage safeguard that prevents
    # duplicated identifiers from multiplying portfolio economics.
    assignment_cols = [
        "primary_tail_type",
        "assignment_basis",
        "fallback_assignment_flag",
        "flag_loss",
        "flag_volatility",
        "flag_impact",
        "n_tail_flags",
    ]
    index_before = df_seg_clusters.index.copy()
    rows_before = len(df_seg_clusters)
    unified = (
        df_seg_clusters.drop(columns=assignment_cols, errors="ignore")
        .join(tail[assignment_cols], how="left", validate="one_to_one")
    )
    if len(unified) != rows_before or not unified.index.equals(index_before):
        raise ValueError("Tail assignment changed row count, identity, or order.")
    for flag_name in [
        "flag_loss",
        "flag_volatility",
        "flag_impact",
        "fallback_assignment_flag",
    ]:
        unified[flag_name] = unified[flag_name].eq(True)
    unified["n_tail_flags"] = unified["n_tail_flags"].fillna(0).astype(int)
    joined_tail_mask = unified["k_cluster"].eq("Unclustered")
    if unified.loc[
        joined_tail_mask,
        ["primary_tail_type", "assignment_basis"],
    ].isna().any().any():
        raise ValueError("At least one tail product lost its assignment during join.")
    if unified.loc[~joined_tail_mask, "primary_tail_type"].notna().any():
        raise ValueError("A clustered-body product received a tail assignment.")

    unified["analytical_role"] = unified["body_role"].astype("object")
    unified.loc[joined_tail_mask, "analytical_role"] = unified.loc[
        joined_tail_mask,
        "primary_tail_type",
    ]
    if unified["analytical_role"].isna().any():
        raise ValueError("The unified analytical taxonomy contains missing roles.")

    return (
        tail,
        tail_entry_audit,
        mechanism_coverage,
        fallback_tail_cases,
        assignment_basis_summary,
        fallback_audit,
        unified,
        mean_profit_lower,
        mean_profit_upper,
    )


def build_tail_audits(
    df_seg_clusters: pd.DataFrame,
    tail: pd.DataFrame,
    *,
    cv_threshold: float,
    impact_threshold: float,
    loss_scale_tolerance: float,
    mean_profit_lower: float,
    mean_profit_upper: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build tail profiles, overlap evidence, and canonical exports.

    Role summaries use original KPI units for interpretation. Net-profit share
    may be negative for loss roles because its denominator is portfolio net
    profit; overlap share instead reports mechanism complexity by product count.
    Product-level exports include every threshold needed to replay assignment.
    """

    portfolio_total_profit = df_seg_clusters["total_profit"].sum()
    if np.isclose(portfolio_total_profit, 0):
        raise ValueError("Portfolio total profit is zero; role shares are undefined.")

    tail_summary = (
        tail.groupby("primary_tail_type", as_index=False, observed=True)
        .agg(
            n_products=("primary_tail_type", "size"),
            total_profit=("total_profit", "sum"),
            mean_order_profit=("mean_order_profit", "mean"),
            median_order_profit=("mean_order_profit", "median"),
            mean_cv=("cv_order_profit", "mean"),
            median_cv=("cv_order_profit", "median"),
            mean_loss_rate=("pct_orders_loss", "mean"),
            median_loss_rate=("pct_orders_loss", "median"),
            mean_profit_scale=("profit_scale", "mean"),
            median_profit_scale=("profit_scale", "median"),
            overlap_share=("n_tail_flags", lambda values: values.gt(1).mean()),
            boundary_direction_assignments=("fallback_assignment_flag", "sum"),
        )
    )
    tail_summary["pct_products"] = 100 * tail_summary["n_products"] / len(df_seg_clusters)
    tail_summary["pct_net_profit"] = (
        100 * tail_summary["total_profit"] / portfolio_total_profit
    )
    tail_summary["primary_tail_type"] = pd.Categorical(
        tail_summary["primary_tail_type"],
        categories=TAIL_ROLE_ORDER,
        ordered=True,
    )
    tail_summary = tail_summary.sort_values("primary_tail_type").reset_index(drop=True)

    overlap_audit = pd.DataFrame(
        {
            "Metric": [
                "Tail products",
                "Products with at least one raw mechanism",
                "Boundary-direction assignments",
                "Loss flag count",
                "Volatility flag count",
                "Impact flag count",
                "Multi-flag products",
                "Multi-flag share",
            ],
            "Value": [
                len(tail),
                int(tail["n_tail_flags"].gt(0).sum()),
                int(tail["fallback_assignment_flag"].sum()),
                int(tail["flag_loss"].sum()),
                int(tail["flag_volatility"].sum()),
                int(tail["flag_impact"].sum()),
                int(tail["n_tail_flags"].gt(1).sum()),
                tail["n_tail_flags"].gt(1).mean(),
            ],
        }
    )

    tail_export_cols = [
        "product_id",
        "product_name",
        "total_profit",
        "mean_order_profit",
        "cv_order_profit",
        "pct_orders_loss",
        "profit_scale",
    ]
    for support_column in ["n_orders", "cv_not_estimable"]:
        if support_column in tail.columns:
            tail_export_cols.append(support_column)
    tail_export_cols.extend(
        [
            "flag_loss",
            "flag_volatility",
            "flag_impact",
            "n_tail_flags",
            "fallback_assignment_flag",
            "assignment_basis",
            "primary_tail_type",
        ]
    )
    tail_export = tail[tail_export_cols].copy()
    tail_export.insert(0, "product_row_id", tail_export.index)
    tail_export["loss_profit_scale_threshold"] = -loss_scale_tolerance
    tail_export["volatility_cv_body_p95"] = cv_threshold
    tail_export["impact_profit_scale_body_p95"] = impact_threshold
    tail_export["mean_profit_body_lower_boundary"] = mean_profit_lower
    tail_export["mean_profit_body_upper_boundary"] = mean_profit_upper

    role_profile = (
        df_seg_clusters.groupby("analytical_role", as_index=False, observed=True)
        .agg(
            n_products=("analytical_role", "size"),
            total_profit=("total_profit", "sum"),
            mean_order_profit=("mean_order_profit", "mean"),
            median_order_profit=("mean_order_profit", "median"),
            mean_cv=("cv_order_profit", "mean"),
            median_cv=("cv_order_profit", "median"),
            mean_loss_rate=("pct_orders_loss", "mean"),
            median_loss_rate=("pct_orders_loss", "median"),
            mean_profit_scale=("profit_scale", "mean"),
            median_profit_scale=("profit_scale", "median"),
        )
    )
    role_profile["pct_products"] = 100 * role_profile["n_products"] / len(df_seg_clusters)
    role_profile["pct_net_profit"] = 100 * role_profile["total_profit"] / portfolio_total_profit
    role_profile["analytical_role"] = pd.Categorical(
        role_profile["analytical_role"],
        categories=ANALYTICAL_ROLE_ORDER,
        ordered=True,
    )
    role_profile = role_profile.sort_values("analytical_role").reset_index(drop=True)
    role_profile["analytical_role"] = role_profile["analytical_role"].astype("object")
    return tail_summary, overlap_audit, tail_export, role_profile


def render_portfolio_geometry_map(
    df_seg_clusters: pd.DataFrame,
    *,
    cv_threshold: float,
    impact_threshold: float,
    output_path: object,
    show_figure: bool,
) -> None:
    """Render an explanatory 2D projection of the seven-role taxonomy.

    Profit Scale is shown on a symmetric-log axis and CV on the vertical axis;
    bubble area encodes loss frequency.  The chart is an interpretation surface,
    not the classifier: the executed taxonomy uses all four KPIs plus explicit
    body/tail rules, so two-dimensional proximity cannot override a role.
    """

    required = {
        "analytical_role",
        "k_cluster",
        "profit_scale",
        "cv_order_profit",
        "pct_orders_loss",
    }
    missing = required - set(df_seg_clusters.columns)
    if missing:
        raise ValueError(f"Missing geometry-map columns: {sorted(missing)}")

    plot_df = df_seg_clusters.copy()
    plot_df["geometry_group"] = plot_df["analytical_role"].astype("object")
    group_colors = {
        "Stable Profit Cluster": "#3b82f6",
        "High-Impact Profit Cluster": "#22c55e",
        "Risk-Oriented Profit Cluster": "#f59e0b",
        "Stable Loss Cluster": "#ef4444",
        "Extreme Impact Tail": "#047857",
        "Extreme Volatility Tail": "#7c3aed",
        "Loss Tail": "#991b1b",
    }
    tail_groups = {"Extreme Impact Tail", "Extreme Volatility Tail", "Loss Tail"}
    observed_groups = set(plot_df["geometry_group"].dropna())
    unexpected = observed_groups - set(ANALYTICAL_ROLE_ORDER)
    if unexpected:
        raise ValueError(f"Unexpected analytical roles in geometry map: {sorted(unexpected)}")

    body_plot = plot_df.loc[plot_df["k_cluster"].ne("Unclustered")].copy()
    body_x_low = body_plot["profit_scale"].quantile(0.05)
    body_x_high = body_plot["profit_scale"].quantile(0.95)
    body_y_high = body_plot["cv_order_profit"].quantile(0.95)
    bubble_min, bubble_range = 18, 90
    plot_df["bubble_size"] = (
        bubble_min + bubble_range * plot_df["pct_orders_loss"].clip(0, 1)
    )

    fig, ax = plt.subplots(figsize=(15, 8.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.add_patch(
        Rectangle(
            (body_x_low, 0),
            body_x_high - body_x_low,
            body_y_high,
            linewidth=1.5,
            edgecolor="#2563eb",
            facecolor="#dbeafe",
            alpha=0.16,
            zorder=0,
        )
    )

    for group_name in ANALYTICAL_ROLE_ORDER:
        current_group = plot_df.loc[plot_df["geometry_group"].eq(group_name)]
        if current_group.empty:
            continue
        is_tail = group_name in tail_groups
        ax.scatter(
            current_group["profit_scale"],
            current_group["cv_order_profit"],
            s=current_group["bubble_size"],
            color=group_colors[group_name],
            alpha=0.92 if is_tail else 0.22,
            edgecolor="white" if is_tail else "none",
            linewidth=0.7 if is_tail else 0,
            zorder=5 if is_tail else 2,
        )

    ax.axvline(
        0,
        color="#6b7280",
        linestyle=":",
        linewidth=1.4,
        alpha=0.95,
        zorder=1,
    )
    ax.axvline(
        impact_threshold,
        color="#2563eb",
        linestyle="--",
        linewidth=1.6,
        alpha=0.95,
        zorder=1,
    )
    ax.axhline(
        cv_threshold,
        color="#2563eb",
        linestyle="--",
        linewidth=1.6,
        alpha=0.95,
        zorder=1,
    )
    ax.set_xscale("symlog", linthresh=0.01)
    observed_cv_max = plot_df["cv_order_profit"].max()
    y_axis_top = max(observed_cv_max * 1.05, cv_threshold * 1.30)
    ax.set_ylim(-0.02 * y_axis_top, y_axis_top)
    ax.set_title(
        "Portfolio Geometry — Body Roles, Structural Tails, and Loss Intensity",
        fontsize=16,
        fontweight="bold",
        pad=18,
    )
    ax.set_xlabel("Profit Scale — Relative Portfolio Impact (Symmetric-Log Display)", fontsize=12)
    ax.set_ylabel("Model CV — Profit Volatility", fontsize=12)
    x_axis_left, _ = ax.get_xlim()

    ax.text(
        impact_threshold,
        y_axis_top * 0.96,
        f"Impact threshold\nbody p95 = {impact_threshold:.4f}",
        ha="left",
        va="top",
        fontsize=9,
        color="#1d4ed8",
        bbox=dict(
            boxstyle="round,pad=0.25",
            facecolor="white",
            edgecolor="#93c5fd",
            alpha=0.95,
        ),
    )
    ax.text(
        x_axis_left,
        cv_threshold,
        f"Volatility threshold: body CV p95 = {cv_threshold:.2f}",
        ha="left",
        va="bottom",
        fontsize=9,
        color="#1d4ed8",
        bbox=dict(
            boxstyle="round,pad=0.25",
            facecolor="white",
            edgecolor="#93c5fd",
            alpha=0.95,
        ),
    )
    ax.text(
        0,
        y_axis_top * 0.07,
        "Zero-profit boundary",
        ha="left",
        va="bottom",
        fontsize=9,
        color="#4b5563",
        bbox=dict(
            boxstyle="round,pad=0.25",
            facecolor="white",
            edgecolor="#d1d5db",
            alpha=0.95,
        ),
    )
    body_zone_label_x = max(body_x_high * 0.30, 0.002)
    ax.text(
        body_zone_label_x,
        body_y_high * 0.52,
        "Central clustered-body reference zone\nbody Profit Scale p05–p95 × CV p95",
        ha="center",
        va="center",
        fontsize=9,
        color="#1d4ed8",
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor="white",
            edgecolor="#bfdbfe",
            alpha=0.95,
        ),
        zorder=6,
    )

    role_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="white",
            label=group,
            markerfacecolor=group_colors[group],
            markeredgecolor="white" if group in tail_groups else "none",
            markersize=9 if group in tail_groups else 7,
            alpha=0.92 if group in tail_groups else 0.35,
        )
        for group in ANALYTICAL_ROLE_ORDER
        if group in observed_groups
    ]
    role_legend = ax.legend(
        handles=role_handles,
        loc="upper right",
        frameon=True,
        framealpha=0.95,
        title="Analytical Role",
        fontsize=9,
        title_fontsize=10,
    )
    ax.add_artist(role_legend)
    size_handles = [
        ax.scatter(
            [],
            [],
            s=bubble_min + bubble_range * loss_rate,
            color="#6b7280",
            alpha=0.35,
            label=f"{loss_rate:.0%} loss-making orders",
        )
        for loss_rate in [0.0, 0.3, 0.6, 1.0]
    ]
    ax.legend(
        handles=size_handles,
        loc="lower right",
        frameon=True,
        framealpha=0.95,
        title="Loss Frequency",
        fontsize=8.5,
        title_fontsize=9,
    )
    ax.grid(alpha=0.15)
    fig.text(
        0.01,
        0.015,
        "Bubble size represents the share of loss-making orders. The symmetric-log x-axis "
        "expands small values around zero and compresses extreme values; horizontal spacing "
        "is therefore not linear across the full axis.\nClassification uses the complete "
        "KPI framework, not this 2D projection alone. High-CV body products remain governed "
        "through their body roles and downstream escalation.",
        ha="left",
        va="bottom",
        fontsize=9,
        color="#374151",
    )
    plt.tight_layout(rect=[0, 0.075, 1, 1])
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"Saved to: {output_path}")
    if show_figure:
        plt.show()
    else:
        plt.close(fig)


def _show_chapter_06_outputs(result: Chapter06Result) -> None:
    print("\n=== BODY-ANCHORED TAIL REFERENCES ===")
    _display(result.tail_reference_table.round({"Observed Threshold": 4}))
    print("\n=== BODY / TAIL MATERIALITY ===")
    _display(
        result.tail_materiality.assign(
            **{
                "Portfolio Share": result.tail_materiality["Portfolio Share"].map(
                    lambda value: f"{value:.1%}"
                ),
                "Net Profit Share": result.tail_materiality["Net Profit Share"].map(
                    lambda value: f"{value:.1%}"
                ),
                "Total Profit": result.tail_materiality["Total Profit"].map(
                    lambda value: f"{value:,.2f}"
                ),
            }
        )
    )
    print("\n=== RAW-MECHANISM COVERAGE ===")
    _display(result.mechanism_coverage_summary)
    print("\n=== TAIL PRODUCTS WITHOUT A RAW MECHANISM ===")
    _display(result.fallback_tail_cases)
    print("\n=== PRIMARY TAIL ASSIGNMENT BASIS ===")
    _display(result.assignment_basis_summary)
    print("\n=== BOUNDARY-DIRECTION ASSIGNMENT AUDIT ===")
    _display(result.fallback_assignment_audit)
    print("\n=== TAIL ASSIGNMENT COMPLETED ===")
    print(f"Body products:                  {len(result.body):,}")
    print(f"Structural-tail products:      {len(result.tail):,}")
    print(f"Boundary-direction products:  {int(result.tail['fallback_assignment_flag'].sum()):,}")
    print(f"Products in unified taxonomy: {len(result.df_seg_clusters):,}")

    view = result.tail_summary.copy()
    view["Portfolio Footprint"] = view["pct_products"].map(lambda value: f"{value:.1f}%")
    view["Total Profit"] = view["total_profit"].map(lambda value: f"{value:,.2f}")
    view["Net Profit Share"] = view["pct_net_profit"].map(lambda value: f"{value:.1f}%")
    view["Mean Order Profit"] = view["mean_order_profit"].map(lambda value: f"{value:,.2f}")
    view["Median CV"] = view["median_cv"].map(lambda value: f"{value:.2f}")
    view["Median Loss Rate"] = view["median_loss_rate"].map(lambda value: f"{value:.1%}")
    print("\n=== STRUCTURAL TAIL TYPOLOGY ===")
    _display(
        view[
            [
                "primary_tail_type",
                "n_products",
                "Portfolio Footprint",
                "Total Profit",
                "Net Profit Share",
                "Mean Order Profit",
                "Median CV",
                "Median Loss Rate",
            ]
        ].rename(columns={"primary_tail_type": "Tail Type", "n_products": "Products"})
    )
    print("\n=== RAW TAIL-MECHANISM OVERLAP AUDIT ===")
    _display(result.overlap_audit)


def run_chapter_06(
    config: AnalysisConfig,
    chapter_04: Chapter04Result,
    chapter_05: Chapter05Result,
    *,
    show_outputs: bool = True,
) -> Chapter06Result:
    """Execute, export, visualize, and validate the complete Chapter 06 stage."""

    config.prepare_output_directories()
    (
        body,
        tail,
        cv_threshold,
        impact_threshold,
        loss_tolerance,
        reference_table,
        materiality,
    ) = construct_tail_references(chapter_05.df_seg_clusters)

    (
        tail,
        tail_entry_audit,
        mechanism_coverage,
        fallback_tail_cases,
        assignment_basis_summary,
        fallback_audit,
        unified,
        mean_profit_lower,
        mean_profit_upper,
    ) = classify_structural_tail(
        chapter_05.df_seg_clusters,
        tail,
        chapter_04.body_thresholds_df,
        cv_threshold=cv_threshold,
        impact_threshold=impact_threshold,
        loss_scale_tolerance=loss_tolerance,
    )

    tail_summary, overlap_audit, tail_export, role_profile = build_tail_audits(
        unified,
        tail,
        cv_threshold=cv_threshold,
        impact_threshold=impact_threshold,
        loss_scale_tolerance=loss_tolerance,
        mean_profit_lower=mean_profit_lower,
        mean_profit_upper=mean_profit_upper,
    )

    tail_export_path = config.reports_dir / "tail_classification_export.csv"
    role_profile_path = config.reports_dir / "analytical_role_profile.csv"
    geometry_path = config.figures_dir / "portfolio_geometry_loss_intensity_map.png"
    tail_export.to_csv(tail_export_path, index=False)
    role_profile.to_csv(role_profile_path, index=False)
    render_portfolio_geometry_map(
        unified,
        cv_threshold=cv_threshold,
        impact_threshold=impact_threshold,
        output_path=geometry_path,
        show_figure=show_outputs,
    )

    result = Chapter06Result(
        body=body,
        tail=tail,
        cv_threshold=cv_threshold,
        impact_threshold=impact_threshold,
        loss_scale_tolerance=loss_tolerance,
        tail_reference_table=reference_table,
        tail_materiality=materiality,
        tail_entry_audit=tail_entry_audit,
        mechanism_coverage_summary=mechanism_coverage,
        fallback_tail_cases=fallback_tail_cases,
        fallback_assignment_audit=fallback_audit,
        assignment_basis_summary=assignment_basis_summary,
        df_seg_clusters=unified,
        tail_summary=tail_summary,
        overlap_audit=overlap_audit,
        tail_export=tail_export,
        analytical_role_profile=role_profile,
        tail_export_path=tail_export_path,
        analytical_role_profile_path=role_profile_path,
        geometry_figure_path=geometry_path,
    )
    validate_chapter_06(
        result,
        strict_project_baseline=config.strict_project_baseline,
    )
    if show_outputs:
        _show_chapter_06_outputs(result)
    return result
