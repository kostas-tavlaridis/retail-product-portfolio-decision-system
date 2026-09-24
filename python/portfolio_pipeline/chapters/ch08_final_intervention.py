"""Chapter 08 — Final Intervention.

Purpose
-------
Close the governance system by combining each product's baseline Primary Action
with its precedence-resolved Escalation Status. The same decisions are then
aggregated into four executive control states and stress-tested under stricter
and more lenient governance calibration.

No structural role is rebuilt here. Chapter 08 operates only on the canonical
Chapter 07 control table and preserves every underlying Governance Signal.

The 16-cell routing table is intentionally closed: four baseline actions times
four escalation states must yield exactly one intervention for every product.
The executive scorecard is a reporting compression of those same decisions,
not an alternative classification. Its sensitivity test perturbs calibration
while holding roles, product economics and precedence logic fixed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from IPython.display import display as _display
except ImportError:  # pragma: no cover
    def _display(value: object) -> None:
        print(value)

from portfolio_pipeline.chapters.ch07_governance_engine import (
    apply_deterioration_and_concentration,
    build_deterioration_specs,
)
from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.contracts import Chapter07Result, Chapter08Result
from portfolio_pipeline.validation import validate_chapter_08


FINAL_INTERVENTION_MAP = {
    ("Protect", "No Escalation"): "Protect",
    ("Protect", "Intensify Action"): "Protect (Tight Control)",
    ("Protect", "Reroute Action"): "Reroute to Contain / Correct",
    ("Protect", "Reassess Classification"): "Reassess Classification",
    ("Optimize", "No Escalation"): "Optimize",
    ("Optimize", "Intensify Action"): "Optimize (Risk-Controlled)",
    ("Optimize", "Reroute Action"): "Reroute to Correct",
    ("Optimize", "Reassess Classification"): "Reassess Classification",
    ("Contain", "No Escalation"): "Contain",
    ("Contain", "Intensify Action"): "Contain (Strict)",
    ("Contain", "Reroute Action"): "Reroute to Correct",
    ("Contain", "Reassess Classification"): "Reassess Classification",
    ("Correct", "No Escalation"): "Correct",
    ("Correct", "Intensify Action"): "Correct — Accelerated",
    ("Correct", "Reroute Action"): "Exit / Restructure",
    ("Correct", "Reassess Classification"): "Reassess Classification",
}

SCORECARD_STATE_MAP = {
    "No Escalation": "Stable Core",
    "Intensify Action": "Control Pressure",
    "Reroute Action": "Action Failure",
    "Reassess Classification": "Structural Ambiguity",
}

SCORECARD_ORDER = [
    "Stable Core",
    "Control Pressure",
    "Action Failure",
    "Structural Ambiguity",
]

GOVERNANCE_CALIBRATION_SCENARIOS = [
    {
        "scenario": "strict",
        "threshold_multiplier": 0.85,
        "instability_band_multiplier": 1.25,
    },
    {
        "scenario": "baseline",
        "threshold_multiplier": 1.00,
        "instability_band_multiplier": 1.00,
    },
    {
        "scenario": "lenient",
        "threshold_multiplier": 1.15,
        "instability_band_multiplier": 0.75,
    },
]


def route_final_interventions(
    flow_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply the complete 4 × 4 routing matrix and audit full coverage.

    A tuple lookup makes the decision function deterministic and inspectable:
    ``f(primary_action, escalation_status) -> final_intervention``. Any unknown
    pair is a hard failure rather than a residual category, which guarantees the
    intervention layer is mutually exclusive and collectively exhaustive.
    """

    result = flow_df.copy()
    route_keys = list(zip(result["primary_action"], result["escalation_status"]))
    result["final_intervention"] = [
        FINAL_INTERVENTION_MAP.get(key, pd.NA) for key in route_keys
    ]
    if result["final_intervention"].isna().any():
        unresolved = (
            result.loc[
                result["final_intervention"].isna(),
                ["primary_action", "escalation_status"],
            ]
            .drop_duplicates()
            .to_dict("records")
        )
        raise ValueError(f"Final-intervention routing is incomplete: {unresolved}")

    coverage_audit = pd.DataFrame(
        {
            "Field": [
                "Analytical Role",
                "Primary Action",
                "Escalation Status",
                "Final Intervention",
            ],
            "Assigned Products": [
                int(result["analytical_role"].notna().sum()),
                int(result["primary_action"].notna().sum()),
                int(result["escalation_status"].notna().sum()),
                int(result["final_intervention"].notna().sum()),
            ],
        }
    )
    coverage_audit["Coverage"] = coverage_audit["Assigned Products"] / len(result)

    final_summary = (
        result.groupby(
            ["primary_action", "escalation_status", "final_intervention"],
            as_index=False,
            dropna=False,
        )
        .agg(
            n_products=("product_row_id", "size"),
            total_profit=("total_profit", "sum"),
        )
    )
    final_summary["portfolio_share"] = final_summary["n_products"] / len(result)

    core_columns = [
        "product_row_id",
        "product_id",
        "product_name",
        "domain",
        "k_cluster",
        "analytical_role",
        "primary_action",
        "compound_overlap_flag",
        "assignment_instability",
        "instability_margin",
        "instability_source",
        "deterioration_level",
        "concentration_level",
        "primary_signal",
        "n_active_signals",
        "escalation_status",
        "final_intervention",
        "total_profit",
        "mean_order_profit",
        "cv_order_profit",
        "pct_orders_loss",
        "profit_scale",
    ]
    optional_columns = [
        "body_role",
        "primary_tail_type",
        "assignment_basis",
        "fallback_assignment_flag",
        "flag_loss",
        "flag_volatility",
        "flag_impact",
        "n_tail_flags",
        "total_sales",
        "profit_margin",
        "n_orders",
        "cv_not_estimable",
        "cv_order_profit_raw",
        "cv_order_profit_model",
    ]
    flow_columns = (
        core_columns[:6]
        + [column for column in optional_columns if column in result.columns]
        + core_columns[6:]
    )
    governance_flow_table = result[list(dict.fromkeys(flow_columns))].copy()
    return result, coverage_audit, final_summary, governance_flow_table


def build_governance_scorecards(
    flow_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Condense product routes into four mutually exclusive control states.

    Product Share measures footprint; Profit Share divides state profit by total
    portfolio net profit; Loss Share divides absolute negative product profit by
    total realized loss. These denominators answer different questions and must
    not be interpreted as parts of one common composition measure.
    """

    result = flow_df.copy()
    result["governance_scorecard_state"] = result["escalation_status"].map(
        SCORECARD_STATE_MAP
    )
    if result["governance_scorecard_state"].isna().any():
        raise ValueError("At least one escalation status has no scorecard state.")
    # Only loss-making products contribute to realized-loss exposure. Positive
    # profit never offsets the denominator used to localize downside.
    result["realized_loss_abs"] = np.where(
        result["total_profit"].lt(0),
        -result["total_profit"],
        0.0,
    )

    portfolio_profit = result["total_profit"].sum()
    realized_loss = result["realized_loss_abs"].sum()
    if np.isclose(portfolio_profit, 0) or np.isclose(realized_loss, 0):
        raise ValueError("Scorecard economic shares require non-zero profit and loss totals.")

    governance_scorecard = (
        result.groupby("governance_scorecard_state", as_index=False)
        .agg(
            Products=("product_row_id", "size"),
            Total_Profit=("total_profit", "sum"),
            Realized_Loss=("realized_loss_abs", "sum"),
        )
    )
    governance_scorecard["governance_scorecard_state"] = pd.Categorical(
        governance_scorecard["governance_scorecard_state"],
        categories=SCORECARD_ORDER,
        ordered=True,
    )
    governance_scorecard = governance_scorecard.sort_values(
        "governance_scorecard_state"
    ).reset_index(drop=True)
    governance_scorecard["Product Share"] = governance_scorecard["Products"] / len(result)
    governance_scorecard["Profit Share"] = governance_scorecard["Total_Profit"] / portfolio_profit
    governance_scorecard["Loss Share"] = governance_scorecard["Realized_Loss"] / realized_loss

    pressure_pct = pd.crosstab(
        result["analytical_role"],
        result["governance_scorecard_state"],
        normalize="index",
    ).mul(100)
    pressure_pct = pressure_pct.reindex(columns=SCORECARD_ORDER, fill_value=0)
    return result, governance_scorecard, pressure_pct


def run_governance_sensitivity_scenario(
    base_frame: pd.DataFrame,
    scenario: dict[str, float | str],
    governance_references: dict[str, float],
) -> pd.DataFrame:
    """Recalculate only the calibrated governance layer for one scenario.

    Threshold multipliers move deterioration/concentration references; the
    instability multiplier widens or narrows weak-assignment bands. The method
    deliberately keeps analytical roles, raw KPI evidence, Tail Overlap and
    escalation precedence unchanged, isolating specification sensitivity.
    """

    result = base_frame.copy()
    threshold_multiplier = float(scenario["threshold_multiplier"])
    instability_multiplier = float(scenario["instability_band_multiplier"])

    impact_p95 = governance_references["impact_p95"] * threshold_multiplier
    impact_p99 = governance_references["impact_p99"] * threshold_multiplier
    cv_p90 = governance_references["cv_p90"] * threshold_multiplier
    cv_p95 = governance_references["cv_p95"] * threshold_multiplier
    cv_p99 = governance_references["cv_p99"] * threshold_multiplier
    loss_p90 = min(max(governance_references["loss_p90"] * threshold_multiplier, 0), 1)

    result["scenario_assignment_instability"] = "none"
    body_margin = (
        result["domain"].eq("Clustered Body")
        & result["instability_source"].eq("cluster_margin")
    )
    high_margin = 0.05 * instability_multiplier
    watch_margin = 0.10 * instability_multiplier
    result.loc[
        body_margin & result["instability_margin"].le(high_margin),
        "scenario_assignment_instability",
    ] = "high"
    result.loc[
        body_margin
        & result["instability_margin"].gt(high_margin)
        & result["instability_margin"].le(watch_margin),
        "scenario_assignment_instability",
    ] = "watch"

    loss_mask = result["analytical_role"].eq("Loss Tail")
    volatility_mask = result["analytical_role"].eq("Extreme Volatility Tail")
    impact_mask = result["analytical_role"].eq("Extreme Impact Tail")
    loss_distance = result["profit_scale"].abs()
    volatility_excess = result["cv_order_profit"] - cv_p95
    impact_excess = result["profit_scale"] - impact_p95

    result.loc[
        loss_mask & loss_distance.le(0.01 * instability_multiplier),
        "scenario_assignment_instability",
    ] = "high"
    result.loc[
        loss_mask
        & loss_distance.gt(0.01 * instability_multiplier)
        & loss_distance.le(0.02 * instability_multiplier),
        "scenario_assignment_instability",
    ] = "watch"
    result.loc[
        volatility_mask & volatility_excess.le(0.20 * instability_multiplier),
        "scenario_assignment_instability",
    ] = "high"
    result.loc[
        volatility_mask
        & volatility_excess.gt(0.20 * instability_multiplier)
        & volatility_excess.le(0.50 * instability_multiplier),
        "scenario_assignment_instability",
    ] = "watch"
    result.loc[
        impact_mask & impact_excess.le(0.01 * instability_multiplier),
        "scenario_assignment_instability",
    ] = "high"
    result.loc[
        impact_mask
        & impact_excess.gt(0.01 * instability_multiplier)
        & impact_excess.le(0.02 * instability_multiplier),
        "scenario_assignment_instability",
    ] = "watch"

    scenario_specs = build_deterioration_specs(
        threshold_multiplier=threshold_multiplier,
        cv_p90_ref=cv_p90,
        cv_p95_ref=cv_p95,
        cv_p99_ref=cv_p99,
        loss_p90_ref=loss_p90,
    )
    result = apply_deterioration_and_concentration(
        result,
        scenario_specs,
        impact_p95_ref=impact_p95,
        impact_p99_ref=impact_p99,
    )

    reassess = (
        result["compound_overlap_flag"]
        | result["scenario_assignment_instability"].eq("high")
    )
    reroute = (
        result["deterioration_level"].eq("severe")
        | result["concentration_level"].eq("extreme")
    )
    intensify = (
        result["deterioration_level"].eq("moderate")
        | result["concentration_level"].eq("elevated")
        | result["scenario_assignment_instability"].eq("watch")
    )
    result["scenario_escalation_status"] = "No Escalation"
    result.loc[intensify, "scenario_escalation_status"] = "Intensify Action"
    result.loc[reroute, "scenario_escalation_status"] = "Reroute Action"
    result.loc[reassess, "scenario_escalation_status"] = "Reassess Classification"
    result["scenario"] = str(scenario["scenario"])
    return result


def build_governance_sensitivity(
    flow_df: pd.DataFrame,
    governance_references: dict[str, float],
) -> pd.DataFrame:
    """Summarize strict, baseline, and lenient governance calibration.

    The robustness question is directional: does hard exposure remain material
    under reasonable calibration movement? It is not a search for thresholds
    that reproduce identical product assignments or the baseline percentage.
    """

    rows: list[dict[str, float | str]] = []
    for scenario in GOVERNANCE_CALIBRATION_SCENARIOS:
        scenario_flow = run_governance_sensitivity_scenario(
            flow_df,
            scenario,
            governance_references,
        )
        stable = scenario_flow["scenario_escalation_status"].eq("No Escalation")
        hard = scenario_flow["scenario_escalation_status"].isin(
            ["Reroute Action", "Reassess Classification"]
        )
        rows.append(
            {
                "scenario": str(scenario["scenario"]),
                "stable_core_share": stable.mean(),
                "hard_exposure_share": hard.mean(),
                "hard_exposure_profit_share": (
                    scenario_flow.loc[hard, "total_profit"].sum()
                    / scenario_flow["total_profit"].sum()
                ),
                "hard_exposure_loss_share": (
                    scenario_flow.loc[hard, "realized_loss_abs"].sum()
                    / scenario_flow["realized_loss_abs"].sum()
                ),
            }
        )
    sensitivity = pd.DataFrame(rows)
    sensitivity["scenario"] = pd.Categorical(
        sensitivity["scenario"],
        categories=["strict", "baseline", "lenient"],
        ordered=True,
    )
    return sensitivity.sort_values("scenario").reset_index(drop=True)


def _show_chapter_08_outputs(result: Chapter08Result) -> None:
    print("\n=== FINAL-INTERVENTION COVERAGE AUDIT ===")
    _display(
        result.coverage_audit.assign(
            Coverage=result.coverage_audit["Coverage"].map(lambda value: f"{value:.1%}")
        )
    )
    print("\n=== FINAL INTERVENTION SUMMARY ===")
    _display(
        result.final_intervention_summary.rename(
            columns={
                "n_products": "Products",
                "total_profit": "Total_Profit",
                "portfolio_share": "Portfolio Share",
            }
        ).round(3)
    )
    print("\n=== PORTFOLIO GOVERNANCE SCORECARD ===")
    _display(result.governance_scorecard.round(3))
    print("\n=== GOVERNANCE PRESSURE BY ANALYTICAL ROLE (%) ===")
    _display(result.governance_pressure_scorecard_pct.round(1))
    print("\n=== GOVERNANCE CALIBRATION SENSITIVITY ===")
    _display(result.governance_scorecard_sensitivity.round(4))


def run_chapter_08(
    config: AnalysisConfig,
    chapter_07: Chapter07Result,
    *,
    show_outputs: bool = True,
) -> Chapter08Result:
    """Execute, export, and validate the complete Chapter 08 stage."""

    config.prepare_output_directories()
    flow_df, coverage, final_summary, governance_flow = route_final_interventions(
        chapter_07.flow_df
    )
    flow_df, governance_scorecard, pressure_pct = build_governance_scorecards(flow_df)
    sensitivity = build_governance_sensitivity(
        flow_df,
        chapter_07.governance_references,
    )

    governance_flow_path = config.reports_dir / "governance_flow_decisions.csv"
    final_summary_path = config.reports_dir / "final_intervention_summary.csv"
    intervention_distribution_path = config.reports_dir / "intervention_distribution.csv"
    pressure_path = config.reports_dir / "governance_pressure_scorecard_pct.csv"
    sensitivity_path = config.reports_dir / "governance_scorecard_sensitivity.csv"
    governance_flow.to_csv(governance_flow_path, index=False)
    final_summary.to_csv(final_summary_path, index=False)
    governance_scorecard.to_csv(intervention_distribution_path, index=False)
    pressure_pct.to_csv(pressure_path)
    sensitivity.to_csv(sensitivity_path, index=False)

    result = Chapter08Result(
        flow_df=flow_df,
        final_intervention_map=FINAL_INTERVENTION_MAP.copy(),
        coverage_audit=coverage,
        final_intervention_summary=final_summary,
        governance_flow_table=governance_flow,
        governance_scorecard=governance_scorecard,
        governance_pressure_scorecard_pct=pressure_pct,
        governance_scorecard_sensitivity=sensitivity,
        governance_flow_path=governance_flow_path,
        final_intervention_summary_path=final_summary_path,
        intervention_distribution_path=intervention_distribution_path,
        governance_pressure_path=pressure_path,
        governance_sensitivity_path=sensitivity_path,
    )
    validate_chapter_08(
        result,
        chapter_07=chapter_07,
        strict_project_baseline=config.strict_project_baseline,
    )
    if show_outputs:
        _show_chapter_08_outputs(result)
    return result
