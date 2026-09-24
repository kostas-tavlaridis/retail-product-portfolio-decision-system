"""Chapter 09 — Economic Priority Layer.

Purpose
-------
Compare each product with its own analytical-role peers, apply explicit
reliability guards, and isolate the subset that warrants active management
attention through five Priority Zones.

Priority is intentionally narrower than governance. Products that match none
of the five active contexts keep their Chapter 08 intervention, remain in the
complete audit table, and receive no Priority Zone. This chapter never rewrites
``escalation_status`` or ``final_intervention``.

The assignment chain is:
``role-relative performance × escalation condition × reliability -> context ->
Priority Zone``. This is not a second clustering model and not a ranking of the
entire universe. It is an active-attention queue answering where limited review
capacity should go first while governance continues to cover every product.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from IPython.display import display as _display
except ImportError:  # pragma: no cover
    def _display(value: object) -> None:
        print(value)

from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.contracts import Chapter08Result, Chapter09Result
from portfolio_pipeline.validation import validate_chapter_09


PRIORITY_ZONE_META: dict[str, dict[str, object]] = {
    "Misaligned Upside": {
        "priority_action": "Recover / Reclassify",
        "priority_sort": 1,
        "priority_color": "#1D4ED8",
    },
    "Fragile Value": {
        "priority_action": "Stabilize First",
        "priority_sort": 2,
        "priority_color": "#F97316",
    },
    "Broken Value": {
        "priority_action": "Correct / Exit",
        "priority_sort": 3,
        "priority_color": "#DC2626",
    },
    "Defendable Value": {
        "priority_action": "Protect / Maintain",
        "priority_sort": 4,
        "priority_color": "#15803D",
    },
    "Watchlist / Unresolved": {
        "priority_action": "Diagnose / Monitor",
        "priority_sort": 5,
        "priority_color": "#334155",
    },
}

CONTEXT_TO_PRIORITY_ZONE = {
    "True Hidden Opportunity": "Misaligned Upside",
    "Unstable Upside / Risky Profit": "Fragile Value",
    "Confirmed Downside Risk": "Broken Value",
    "Outperforming Within Governance Route": "Defendable Value",
    "Underperformance Watch": "Watchlist / Unresolved",
}


def build_role_relative_performance(
    flow_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach role-specific profit, volatility and loss-rate benchmarks.

    Products are compared with their own analytical peers because the seven
    roles encode different expected economics. P90 is checked before P75, then
    P25: top-decile, upper-quartile and lower-quartile conditions are therefore
    mutually exclusive. ``role_profit_z`` is explanatory magnitude; percentile
    position, not a universal z cut-off, executes the discrete classification.
    """

    result = flow_df.copy()
    role_reference_columns = [
        "role_mean_profit",
        "role_std_profit",
        "role_p25_profit",
        "role_p75_profit",
        "role_p90_profit",
        "role_median_cv",
        "role_p75_cv",
        "role_median_loss_rate",
        "role_p75_loss_rate",
    ]
    result = result.drop(columns=role_reference_columns, errors="ignore")
    row_identity_before = result["product_row_id"].tolist()

    role_perf_ref = (
        result.groupby("analytical_role", as_index=False)
        .agg(
            role_mean_profit=("mean_order_profit", "mean"),
            role_std_profit=("mean_order_profit", "std"),
            role_p25_profit=("mean_order_profit", lambda values: values.quantile(0.25)),
            role_p75_profit=("mean_order_profit", lambda values: values.quantile(0.75)),
            role_p90_profit=("mean_order_profit", lambda values: values.quantile(0.90)),
            role_median_cv=("cv_order_profit", "median"),
            role_p75_cv=("cv_order_profit", lambda values: values.quantile(0.75)),
            role_median_loss_rate=("pct_orders_loss", "median"),
            role_p75_loss_rate=("pct_orders_loss", lambda values: values.quantile(0.75)),
        )
    )
    result = result.merge(
        role_perf_ref,
        on="analytical_role",
        how="left",
        validate="many_to_one",
        sort=False,
    )
    if len(result) != len(row_identity_before):
        raise ValueError("Role-reference merge changed product coverage.")
    if result["product_row_id"].tolist() != row_identity_before:
        raise ValueError("Role-reference merge changed product identity or order.")
    if result[role_reference_columns].isna().any().any():
        raise ValueError("At least one product is missing its role benchmark.")

    # z = (product mean profit - role mean) / role standard deviation. Roles
    # with zero/undefined spread receive z=0 because standardized distance has
    # no mathematical meaning, while percentile classification remains explicit.
    result["role_profit_z"] = np.where(
        result["role_std_profit"].fillna(0).gt(0),
        (
            result["mean_order_profit"] - result["role_mean_profit"]
        ) / result["role_std_profit"],
        0,
    )
    result["performance_deviation"] = np.select(
        [
            result["mean_order_profit"].ge(result["role_p90_profit"]),
            result["mean_order_profit"].ge(result["role_p75_profit"]),
            result["mean_order_profit"].le(result["role_p25_profit"]),
        ],
        [
            "High Positive Deviation",
            "Positive Deviation",
            "Negative Deviation",
        ],
        default="Role-Aligned",
    )
    return result, role_perf_ref


def apply_reliability_and_context(
    flow_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate reliable hidden opportunity from risky or neutral performance.

    Positive role-relative deviation is necessary but not sufficient. A hidden
    opportunity must also be under governance escalation and pass all five
    absolute guards: positive total profit, positive mean-order profit, Loss
    Rate <=30%, CV <=2.0 and no severe Deterioration. Role-relative loss/CV flags
    are retained as explanations but do not execute acceptance.
    """

    result = flow_df.copy()
    positive_deviation = result["performance_deviation"].isin(
        ["Positive Deviation", "High Positive Deviation"]
    )
    escalated = result["escalation_status"].isin(
        ["Intensify Action", "Reroute Action", "Reassess Classification"]
    )

    # These five absolute guards are the executed opportunity filter. The two
    # role-relative pass fields below remain explanatory audit evidence only.
    reliability_guards = pd.DataFrame(
        {
            "positive_total_profit": result["total_profit"].gt(0),
            "positive_mean_profit": result["mean_order_profit"].gt(0),
            "acceptable_loss_rate": result["pct_orders_loss"].le(0.30),
            "acceptable_volatility": result["cv_order_profit"].le(2.00),
            "not_severe_deterioration": result["deterioration_level"].ne("severe"),
        },
        index=result.index,
    )
    result["opportunity_reliability_pass"] = reliability_guards.all(axis=1)
    result["role_relative_loss_pass"] = result["pct_orders_loss"].le(
        result["role_median_loss_rate"]
    )
    result["role_relative_cv_pass"] = result["cv_order_profit"].le(
        result["role_median_cv"]
    )

    # The conjunction prevents stressed or loss-exposed profit from being
    # mislabeled as scalable upside. Failing any guard routes the same positive
    # deviation to Fragile Value rather than deleting the evidence.
    true_hidden = positive_deviation & escalated & result["opportunity_reliability_pass"]
    unstable_upside = positive_deviation & escalated & ~result["opportunity_reliability_pass"]
    result["opportunity_quality"] = np.select(
        [true_hidden, unstable_upside, positive_deviation & ~escalated],
        [
            "True Hidden Opportunity Candidate",
            "Unstable Upside / Risky Profit",
            "Outperforming Within Governance Route",
        ],
        default="Not Opportunity Candidate",
    )
    result["opportunity_action"] = np.select(
        [
            result["opportunity_quality"].eq("True Hidden Opportunity Candidate"),
            result["opportunity_quality"].eq("Unstable Upside / Risky Profit"),
            result["opportunity_quality"].eq("Outperforming Within Governance Route"),
        ],
        [
            "Reframe / Reclassify",
            "Do Not Scale — Stabilize or Restructure First",
            "Maintain / Monitor",
        ],
        default="No Opportunity Action",
    )
    result["opportunity_filter_reason"] = np.select(
        [
            true_hidden,
            positive_deviation & escalated & ~reliability_guards["positive_total_profit"],
            positive_deviation & escalated & ~reliability_guards["positive_mean_profit"],
            positive_deviation & escalated & ~reliability_guards["acceptable_loss_rate"],
            positive_deviation & escalated & ~reliability_guards["acceptable_volatility"],
            positive_deviation & escalated & ~reliability_guards["not_severe_deterioration"],
            positive_deviation & ~escalated,
        ],
        [
            "Positive deviation + reliability pass",
            "Rejected: negative total profit",
            "Rejected: non-positive mean order profit",
            "Rejected: loss rate above 30%",
            "Rejected: CV above 2.0",
            "Rejected: severe deterioration",
            "Positive but not escalated",
        ],
        default="No positive opportunity signal",
    )
    result["performance_context"] = np.select(
        [
            result["opportunity_quality"].eq("True Hidden Opportunity Candidate"),
            result["opportunity_quality"].eq("Unstable Upside / Risky Profit"),
            result["opportunity_quality"].eq("Outperforming Within Governance Route"),
            result["performance_deviation"].eq("Negative Deviation")
            & result["escalation_status"].isin(
                ["Reroute Action", "Reassess Classification"]
            ),
            result["performance_deviation"].eq("Negative Deviation")
            & result["escalation_status"].isin(
                ["No Escalation", "Intensify Action"]
            ),
        ],
        [
            "True Hidden Opportunity",
            "Unstable Upside / Risky Profit",
            "Outperforming Within Governance Route",
            "Confirmed Downside Risk",
            "Underperformance Watch",
        ],
        default="Neutral",
    )
    return result, reliability_guards


def build_priority_zones(
    flow_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Map five qualifying contexts to five active management zones.

    Context-to-zone is one-to-one and ordered for presentation, not for a
    continuous risk score. Neutral and routine contexts intentionally map to
    missing Priority Zone, set ``priority_scope_flag=False`` and remain fully
    governed through their existing final intervention.
    """

    result = flow_df.copy()
    result["priority_zone"] = result["performance_context"].map(
        CONTEXT_TO_PRIORITY_ZONE
    ).astype("object")
    result.loc[result["priority_zone"].isna(), "priority_zone"] = pd.NA
    result["priority_action"] = result["priority_zone"].map(
        {zone: metadata["priority_action"] for zone, metadata in PRIORITY_ZONE_META.items()}
    )
    result["priority_sort"] = result["priority_zone"].map(
        {zone: metadata["priority_sort"] for zone, metadata in PRIORITY_ZONE_META.items()}
    ).astype("Int64")
    result["priority_color"] = result["priority_zone"].map(
        {zone: metadata["priority_color"] for zone, metadata in PRIORITY_ZONE_META.items()}
    )
    result["priority_scope_flag"] = result["priority_zone"].notna()

    priority_zone_summary = (
        result.loc[result["priority_scope_flag"]]
        .groupby(["priority_zone", "priority_action", "priority_sort"], as_index=False)
        .agg(
            Products=("product_row_id", "size"),
            Total_Profit=("total_profit", "sum"),
            Realized_Loss=("realized_loss_abs", "sum"),
        )
        .sort_values("priority_sort")
        .reset_index(drop=True)
    )
    priority_zone_summary["Product Share"] = priority_zone_summary["Products"] / len(result)
    priority_zone_summary["Profit Share"] = (
        priority_zone_summary["Total_Profit"] / result["total_profit"].sum()
    )
    priority_zone_summary["Loss Share"] = (
        priority_zone_summary["Realized_Loss"] / result["realized_loss_abs"].sum()
    )

    priority_scope_summary = pd.DataFrame(
        {
            "Metric": [
                "Portfolio products",
                "Active priority products",
                "Routine / neutral products",
                "Active priority share",
            ],
            "Value": [
                len(result),
                int(result["priority_scope_flag"].sum()),
                int((~result["priority_scope_flag"]).sum()),
                result["priority_scope_flag"].mean(),
            ],
        }
    )
    opportunity_quality_summary = (
        result.groupby(["opportunity_quality", "opportunity_action"], as_index=False)
        .agg(
            Products=("product_row_id", "size"),
            Total_Profit=("total_profit", "sum"),
            Mean_CV=("cv_order_profit", "mean"),
            Mean_Loss_Rate=("pct_orders_loss", "mean"),
        )
    )

    priority_product_columns = [
        "product_row_id",
        "product_id",
        "product_name",
        "analytical_role",
        "primary_action",
        "escalation_status",
        "final_intervention",
        "performance_deviation",
        "role_profit_z",
        "opportunity_reliability_pass",
        "role_relative_loss_pass",
        "role_relative_cv_pass",
        "opportunity_quality",
        "opportunity_action",
        "opportunity_filter_reason",
        "performance_context",
        "priority_scope_flag",
        "priority_zone",
        "priority_action",
        "priority_sort",
        "total_profit",
        "mean_order_profit",
        "cv_order_profit",
        "pct_orders_loss",
        "profit_scale",
    ]
    priority_product_decisions = (
        result[priority_product_columns]
        .sort_values(
            ["priority_scope_flag", "priority_sort", "total_profit"],
            ascending=[False, True, False],
            na_position="last",
        )
        .reset_index(drop=True)
    )
    return (
        result,
        priority_zone_summary,
        priority_scope_summary,
        opportunity_quality_summary,
        priority_product_decisions,
    )


def build_hidden_opportunity_sensitivity(
    flow_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stress-test opportunity materiality across a 4 × 3 × 3 threshold grid.

    The 36 scenarios cross four role-profit quantiles, three maximum loss rates
    and three maximum CVs while keeping escalation and the other guards fixed.
    Signal retention is measured against baseline profit share: >=75% is
    materially stable, >=50% is moderately sensitive, and zero products is
    collapse. P05/P95 summarize scenario percentiles, not fifth-ranked cases.
    This validates threshold robustness, not future performance or membership
    stability of every individual product.
    """

    baseline_hidden = flow_df["performance_context"].eq("True Hidden Opportunity")
    baseline_hidden_products = int(baseline_hidden.sum())
    baseline_profit_share = (
        flow_df.loc[baseline_hidden, "total_profit"].sum()
        / flow_df["total_profit"].sum()
    )
    sensitivity_rows: list[dict[str, float | int]] = []

    for positive_quantile in [0.75, 0.80, 0.85, 0.90]:
        role_threshold = (
            flow_df.groupby("analytical_role")["mean_order_profit"]
            .transform(lambda values: values.quantile(positive_quantile))
        )
        positive_role_deviation = flow_df["mean_order_profit"].ge(role_threshold)
        governance_stress = flow_df["escalation_status"].isin(
            ["Intensify Action", "Reroute Action", "Reassess Classification"]
        )
        for max_loss_rate in [0.25, 0.30, 0.35]:
            for max_cv in [1.50, 2.00, 2.50]:
                reliability = (
                    flow_df["total_profit"].gt(0)
                    & flow_df["mean_order_profit"].gt(0)
                    & flow_df["pct_orders_loss"].le(max_loss_rate)
                    & flow_df["cv_order_profit"].le(max_cv)
                    & flow_df["deterioration_level"].ne("severe")
                )
                scenario_hidden = positive_role_deviation & governance_stress & reliability
                hidden_profit = flow_df.loc[scenario_hidden, "total_profit"].sum()
                sensitivity_rows.append(
                    {
                        "positive_deviation_quantile": positive_quantile,
                        "max_loss_rate_threshold": max_loss_rate,
                        "max_cv_threshold": max_cv,
                        "true_hidden_products": int(scenario_hidden.sum()),
                        "true_hidden_product_share": scenario_hidden.mean(),
                        "true_hidden_profit": hidden_profit,
                        "true_hidden_profit_share": hidden_profit / flow_df["total_profit"].sum(),
                        "baseline_product_retention": (
                            int((baseline_hidden & scenario_hidden).sum())
                            / baseline_hidden_products
                            if baseline_hidden_products
                            else np.nan
                        ),
                    }
                )

    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity["profit_share_vs_baseline"] = (
        sensitivity["true_hidden_profit_share"] / baseline_profit_share
    )
    sensitivity["materiality_reading"] = np.select(
        [
            sensitivity["true_hidden_products"].eq(0),
            sensitivity["profit_share_vs_baseline"].ge(0.75),
            sensitivity["profit_share_vs_baseline"].ge(0.50),
        ],
        ["collapsed", "materially_stable", "moderately_sensitive"],
        default="highly_sensitive",
    )
    summary = pd.DataFrame(
        {
            "Metric": ["Profit Share", "Product Share"],
            "Baseline": [baseline_profit_share, baseline_hidden.mean()],
            "Median": [
                sensitivity["true_hidden_profit_share"].median(),
                sensitivity["true_hidden_product_share"].median(),
            ],
            "P05": [
                sensitivity["true_hidden_profit_share"].quantile(0.05),
                sensitivity["true_hidden_product_share"].quantile(0.05),
            ],
            "P95": [
                sensitivity["true_hidden_profit_share"].quantile(0.95),
                sensitivity["true_hidden_product_share"].quantile(0.95),
            ],
        }
    )
    return sensitivity, summary


def build_signal_summary(row: pd.Series) -> str:
    """Return one ordered manager-facing string containing every active signal.

    Unlike ``primary_signal``, this field never hides secondary evidence. The
    explicit sort order mirrors governance precedence so workbook readers see
    structural ambiguity and severe conditions before lower-intensity pressure.
    """

    signals: list[tuple[str, int]] = []
    if bool(row.get("compound_overlap_flag", False)):
        signals.append(("Tail Overlap", 1))
    if row.get("assignment_instability") == "high":
        signals.append(("Classification Instability [high]", 2))
    elif row.get("assignment_instability") == "watch":
        signals.append(("Classification Instability [watch]", 7))
    if row.get("deterioration_level") == "severe":
        signals.append(("Deterioration [severe]", 3))
    elif row.get("deterioration_level") == "moderate":
        signals.append(("Deterioration [moderate]", 5))
    if row.get("concentration_level") == "extreme":
        signals.append(("Concentration [extreme]", 4))
    elif row.get("concentration_level") == "elevated":
        signals.append(("Concentration [elevated]", 6))
    if not signals:
        return "No Signal"
    return " | ".join(name for name, _ in sorted(signals, key=lambda item: item[1]))


def export_governance_workbook(
    flow_df: pd.DataFrame,
    output_path: object,
) -> pd.DataFrame:
    """Write a compact manager view and complete audit view to one workbook.

    ``manager_view`` is the decision surface; ``audit_view`` preserves every
    benchmark, signal, guard, context and assignment field needed to reconstruct
    the route. Engine fallback changes only the Excel writer dependency, never
    workbook values, sheet names or analytical content.
    """

    result = flow_df.copy()
    result["signals_summary"] = result.apply(build_signal_summary, axis=1)
    result["governance_class"] = result["analytical_role"]
    manager_view = result[
        [
            "product_row_id",
            "product_name",
            "governance_class",
            "primary_action",
            "primary_signal",
            "signals_summary",
            "escalation_status",
            "final_intervention",
            "performance_deviation",
            "performance_context",
            "opportunity_quality",
            "opportunity_action",
            "opportunity_filter_reason",
        ]
    ].copy()
    manager_view.columns = [
        "Product Row ID",
        "Product",
        "Governance Class",
        "Primary Action",
        "Primary Signal",
        "Signals Summary",
        "Escalation Status",
        "Final Intervention",
        "Performance Deviation",
        "Performance Context",
        "Opportunity Quality",
        "Opportunity Action",
        "Opportunity Filter Reason",
    ]
    try:
        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
            manager_view.to_excel(writer, sheet_name="manager_view", index=False)
            result.to_excel(writer, sheet_name="audit_view", index=False)
    except (ImportError, ModuleNotFoundError, ValueError):
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            manager_view.to_excel(writer, sheet_name="manager_view", index=False)
            result.to_excel(writer, sheet_name="audit_view", index=False)
    return manager_view


def _show_chapter_09_outputs(result: Chapter09Result) -> None:
    print("\n=== ROLE-RELATIVE PERFORMANCE REFERENCES ===")
    _display(result.role_perf_ref.round(3))
    print("\n=== PERFORMANCE DEVIATION DISTRIBUTION ===")
    _display(result.flow_df["performance_deviation"].value_counts().to_frame("Products"))
    print("\n=== ACTIVE MANAGEMENT PRIORITY ZONES ===")
    _display(result.priority_zone_summary.round(3))
    print("\n=== PRIORITY-SCOPE RECONCILIATION ===")
    _display(result.priority_scope_summary)
    print("\n=== HIDDEN-OPPORTUNITY SENSITIVITY SUMMARY ===")
    _display(result.opportunity_sensitivity_summary.round(4))
    print(f"Governance output exported to: {result.governance_output_path}")


def run_chapter_09(
    config: AnalysisConfig,
    chapter_08: Chapter08Result,
    *,
    show_outputs: bool = True,
) -> Chapter09Result:
    """Execute, export, and validate the complete Chapter 09 stage."""

    config.prepare_output_directories()
    flow_df, role_perf_ref = build_role_relative_performance(chapter_08.flow_df)
    flow_df, reliability_guards = apply_reliability_and_context(flow_df)
    (
        flow_df,
        priority_zone_summary,
        priority_scope_summary,
        opportunity_quality_summary,
        priority_product_decisions,
    ) = build_priority_zones(flow_df)
    hidden_sensitivity, sensitivity_summary = build_hidden_opportunity_sensitivity(flow_df)

    priority_zone_path = config.reports_dir / "priority_zone_summary.csv"
    priority_decisions_path = config.reports_dir / "priority_product_decisions.csv"
    opportunity_quality_path = config.reports_dir / "opportunity_quality_summary.csv"
    hidden_sensitivity_path = config.reports_dir / "hidden_opportunity_threshold_sensitivity.csv"
    governance_output_path = config.reports_dir / "governance_output.xlsx"
    priority_zone_summary.to_csv(priority_zone_path, index=False)
    priority_product_decisions.to_csv(priority_decisions_path, index=False)
    opportunity_quality_summary.to_csv(opportunity_quality_path, index=False)
    hidden_sensitivity.to_csv(hidden_sensitivity_path, index=False)
    manager_view = export_governance_workbook(flow_df, governance_output_path)

    # Keep the complete audit view in-memory exactly as exported, including the
    # reader-facing multi-signal summary and governance-class alias.
    flow_df = flow_df.copy()
    flow_df["signals_summary"] = flow_df.apply(build_signal_summary, axis=1)
    flow_df["governance_class"] = flow_df["analytical_role"]

    result = Chapter09Result(
        flow_df=flow_df,
        role_perf_ref=role_perf_ref,
        reliability_guards=reliability_guards,
        priority_zone_meta={zone: metadata.copy() for zone, metadata in PRIORITY_ZONE_META.items()},
        priority_zone_summary=priority_zone_summary,
        priority_scope_summary=priority_scope_summary,
        opportunity_quality_summary=opportunity_quality_summary,
        priority_product_decisions=priority_product_decisions,
        hidden_opportunity_sensitivity=hidden_sensitivity,
        opportunity_sensitivity_summary=sensitivity_summary,
        manager_view=manager_view,
        priority_zone_summary_path=priority_zone_path,
        priority_product_decisions_path=priority_decisions_path,
        opportunity_quality_summary_path=opportunity_quality_path,
        hidden_opportunity_sensitivity_path=hidden_sensitivity_path,
        governance_output_path=governance_output_path,
    )
    validate_chapter_09(
        result,
        chapter_08=chapter_08,
        strict_project_baseline=config.strict_project_baseline,
    )
    if show_outputs:
        _show_chapter_09_outputs(result)
    return result
