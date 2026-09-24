"""Chapter 07 — Governance Engine.

Purpose
-------
Translate the seven analytical roles into baseline management direction, test
that direction through four independent Governance Signals, and resolve all
overlapping evidence into one auditable Escalation Status per product.

The chapter is deliberately static and deterministic. Deterioration means a
current role-relative tolerance breach; it does not claim that performance
worsened through time. Classification Instability measures weak anchoring in
the observed geometry; it is not literal migration between periods.

Four signals remain analytically independent: Deterioration tests role-specific
operating pressure, Concentration tests dependence on large value contributors,
Tail Overlap tests compound extreme mechanisms, and Classification Instability
tests weak structural anchoring. Signals diagnose; the precedence engine alone
converts their combined evidence into one escalation state.
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
from portfolio_pipeline.contracts import Chapter05Result, Chapter06Result, Chapter07Result
from portfolio_pipeline.validation import validate_chapter_07


ANALYTICAL_TO_ACTION = {
    "Stable Profit Cluster": "Protect",
    "High-Impact Profit Cluster": "Optimize",
    "Risk-Oriented Profit Cluster": "Contain",
    "Stable Loss Cluster": "Correct",
    "Extreme Impact Tail": "Optimize",
    "Extreme Volatility Tail": "Contain",
    "Loss Tail": "Correct",
}

# Classification-instability bands are named once and shared with threshold
# exports and Chapter 08 sensitivity.  For body margins, smaller means closer to
# a competing centroid; for tail excess/distance, smaller means closer to the
# boundary that created the structural role.  In both domains, smaller evidence
# means weaker classification confidence.
BODY_INSTABILITY_WATCH_MARGIN = 0.10
BODY_INSTABILITY_HIGH_MARGIN = 0.05
LOSS_TAIL_WATCH_DISTANCE = 0.02
LOSS_TAIL_HIGH_DISTANCE = 0.01
VOL_TAIL_WATCH_EXCESS = 0.50
VOL_TAIL_HIGH_EXCESS = 0.20
IMPACT_TAIL_WATCH_EXCESS = 0.02
IMPACT_TAIL_HIGH_EXCESS = 0.01


def build_governance_base(
    df_seg_clusters: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create the canonical control table and role-owned baseline route.

    Primary Action is the default managerial direction implied by structure;
    it contains no severity.  Escalation is calculated later from independent
    evidence so the system can distinguish "what this role normally requires"
    from "how urgently this particular product must be handled".
    """

    flow_df = df_seg_clusters.copy()
    if not flow_df.index.is_unique:
        raise ValueError("The analytical product-row index is not unique.")

    # Product ID alone is not unique in the source portfolio. The analytical
    # row index therefore remains explicit throughout every governance export.
    flow_df["product_row_id"] = flow_df.index
    required_inputs = {
        "product_id",
        "product_name",
        "k_cluster",
        "analytical_role",
        "flag_loss",
        "flag_volatility",
        "flag_impact",
        "n_tail_flags",
        "total_profit",
        "mean_order_profit",
        "cv_order_profit",
        "pct_orders_loss",
        "profit_scale",
    }
    missing = required_inputs - set(flow_df.columns)
    if missing:
        raise ValueError(f"Missing Chapter 06 governance inputs: {sorted(missing)}")

    flow_df["domain"] = np.where(
        flow_df["k_cluster"].eq("Unclustered"),
        "Extreme Tail",
        "Clustered Body",
    )
    flow_df["primary_action"] = flow_df["analytical_role"].map(ANALYTICAL_TO_ACTION)
    if flow_df["primary_action"].isna().any():
        missing_roles = (
            flow_df.loc[flow_df["primary_action"].isna(), "analytical_role"]
            .drop_duplicates()
            .tolist()
        )
        raise ValueError("Unmapped analytical roles: " + ", ".join(map(str, missing_roles)))

    for flag_name in ["flag_loss", "flag_volatility", "flag_impact"]:
        flow_df[flag_name] = flow_df[flag_name].fillna(False).astype(bool)
    flow_df["n_tail_flags"] = flow_df["n_tail_flags"].fillna(0).astype(int)

    body_with_tail_flags = (
        flow_df["domain"].eq("Clustered Body")
        & flow_df["n_tail_flags"].gt(0)
    )
    if body_with_tail_flags.any():
        raise ValueError("At least one clustered-body product carries a tail mechanism.")

    # Tail Overlap is diagnostic evidence, not an action. It activates only
    # when an extreme-tail product carries at least two raw mechanisms.
    flow_df["compound_overlap_flag"] = (
        flow_df["domain"].eq("Extreme Tail")
        & flow_df["n_tail_flags"].ge(2)
    )
    baseline_action_summary = (
        flow_df.groupby(["analytical_role", "primary_action"], as_index=False)
        .agg(
            n_products=("product_row_id", "size"),
            total_profit=("total_profit", "sum"),
        )
    )
    return flow_df, baseline_action_summary


def build_classification_instability(
    flow_df: pd.DataFrame,
    chapter_05: Chapter05Result,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict[str, float],
    pd.DataFrame,
    pd.DataFrame,
]:
    """Measure body centroid confidence and tail boundary distance.

    Body confidence uses the normalized separation margin
    ``(d_alt-d_assigned)/d_alt``. A value near zero means the nearest competing
    centroid is almost as plausible as the assigned one; larger values indicate
    clearer ownership. Tail roles have no centroid, so confidence is measured by
    distance/excess from the body-anchored boundary that owns the assignment.
    """

    result = flow_df.copy()
    body_ref = result.loc[result["domain"].eq("Clustered Body")].copy()
    if body_ref.empty:
        raise ValueError("The clustered-body governance reference is empty.")

    # All governance percentiles are estimated from the clustered body. Extreme
    # products are assessed against recurring structure and cannot inflate the
    # thresholds used to judge their own concentration or volatility.
    references = {
        "impact_p95": float(body_ref["profit_scale"].quantile(0.95)),
        "impact_p99": float(body_ref["profit_scale"].quantile(0.99)),
        "cv_p90": float(body_ref["cv_order_profit"].quantile(0.90)),
        "cv_p95": float(body_ref["cv_order_profit"].quantile(0.95)),
        "cv_p99": float(body_ref["cv_order_profit"].quantile(0.99)),
        "loss_p90": float(body_ref["pct_orders_loss"].quantile(0.90)),
    }
    if not np.isfinite(list(references.values())).all():
        raise ValueError("At least one body-anchored governance reference is not finite.")

    result["assignment_instability"] = "none"
    result["instability_margin"] = np.nan
    result["instability_source"] = pd.Series(pd.NA, index=result.index, dtype="object")

    # Clustered body: compare the distance to the assigned centroid with the
    # nearest competing centroid in the same standardized four-KPI space.
    clustered_body = chapter_05.km_df_clust
    if not clustered_body.index.is_unique:
        raise ValueError("The clusterable-body index is not unique.")
    if len(clustered_body) != len(chapter_05.x_scaled):
        raise ValueError("Body rows and standardized feature rows are misaligned.")

    centroids = chapter_05.kmeans.cluster_centers_
    body_labels = clustered_body["k_cluster"].astype(int).to_numpy()
    fitted_labels = np.asarray(chapter_05.kmeans.labels_)
    if not np.array_equal(body_labels, fitted_labels):
        raise ValueError("Stored body labels do not match the fitted K-means order.")

    # Euclidean distances are evaluated in exactly the same standardized KPI
    # space and row order as the fitted K-means model.
    distance_matrix = np.linalg.norm(
        chapter_05.x_scaled[:, None, :] - centroids[None, :, :],
        axis=2,
    )
    expected_shape = (len(clustered_body), centroids.shape[0])
    if distance_matrix.shape != expected_shape:
        raise ValueError("Unexpected product-to-centroid distance-matrix shape.")

    row_index = np.arange(len(clustered_body))
    assigned_distance = distance_matrix[row_index, body_labels]
    if not np.allclose(assigned_distance, distance_matrix.min(axis=1)):
        raise ValueError("A stored body label is not its nearest fitted centroid.")
    nearest_alternative = np.sort(distance_matrix, axis=1)[:, 1]
    cluster_margin = np.where(
        nearest_alternative > 0,
        (nearest_alternative - assigned_distance) / nearest_alternative,
        0,
    )
    body_instability = pd.DataFrame(
        {
            "instability_margin": cluster_margin,
            "assignment_instability": np.select(
                [
                    cluster_margin <= BODY_INSTABILITY_HIGH_MARGIN,
                    cluster_margin <= BODY_INSTABILITY_WATCH_MARGIN,
                ],
                ["high", "watch"],
                default="none",
            ),
            "instability_source": "cluster_margin",
        },
        index=clustered_body.index,
    )
    result.update(body_instability)
    if result.loc[clustered_body.index, "instability_margin"].isna().any():
        raise ValueError("A body product is missing its centroid margin.")

    # Structural tail: weak anchoring is measured by distance from the entry
    # boundary of the mechanism that owns the product's primary tail role.
    loss_mask = result["analytical_role"].eq("Loss Tail")
    volatility_mask = result["analytical_role"].eq("Extreme Volatility Tail")
    impact_mask = result["analytical_role"].eq("Extreme Impact Tail")
    loss_distance = result["profit_scale"].abs()
    volatility_excess = result["cv_order_profit"] - references["cv_p95"]
    impact_excess = result["profit_scale"] - references["impact_p95"]

    result.loc[
        loss_mask & loss_distance.le(LOSS_TAIL_HIGH_DISTANCE),
        "assignment_instability",
    ] = "high"
    result.loc[
        loss_mask
        & loss_distance.gt(LOSS_TAIL_HIGH_DISTANCE)
        & loss_distance.le(LOSS_TAIL_WATCH_DISTANCE),
        "assignment_instability",
    ] = "watch"
    result.loc[loss_mask, "instability_margin"] = loss_distance
    result.loc[loss_mask, "instability_source"] = "distance_to_zero_profit_boundary"

    result.loc[
        volatility_mask & volatility_excess.le(VOL_TAIL_HIGH_EXCESS),
        "assignment_instability",
    ] = "high"
    result.loc[
        volatility_mask
        & volatility_excess.gt(VOL_TAIL_HIGH_EXCESS)
        & volatility_excess.le(VOL_TAIL_WATCH_EXCESS),
        "assignment_instability",
    ] = "watch"
    result.loc[volatility_mask, "instability_margin"] = volatility_excess
    result.loc[volatility_mask, "instability_source"] = "excess_over_cv_p95"

    result.loc[
        impact_mask & impact_excess.le(IMPACT_TAIL_HIGH_EXCESS),
        "assignment_instability",
    ] = "high"
    result.loc[
        impact_mask
        & impact_excess.gt(IMPACT_TAIL_HIGH_EXCESS)
        & impact_excess.le(IMPACT_TAIL_WATCH_EXCESS),
        "assignment_instability",
    ] = "watch"
    result.loc[impact_mask, "instability_margin"] = impact_excess
    result.loc[impact_mask, "instability_source"] = "excess_over_impact_p95"

    threshold_export = pd.DataFrame(
        {
            "threshold_name": [
                "impact_p95",
                "impact_p99",
                "cv_p90",
                "cv_p95",
                "cv_p99",
                "loss_p90",
                "body_instability_watch_margin",
                "body_instability_high_margin",
                "loss_tail_watch_distance",
                "loss_tail_high_distance",
                "vol_tail_watch_excess",
                "vol_tail_high_excess",
                "impact_tail_watch_excess",
                "impact_tail_high_excess",
            ],
            "value": [
                references["impact_p95"],
                references["impact_p99"],
                references["cv_p90"],
                references["cv_p95"],
                references["cv_p99"],
                references["loss_p90"],
                BODY_INSTABILITY_WATCH_MARGIN,
                BODY_INSTABILITY_HIGH_MARGIN,
                LOSS_TAIL_WATCH_DISTANCE,
                LOSS_TAIL_HIGH_DISTANCE,
                VOL_TAIL_WATCH_EXCESS,
                VOL_TAIL_HIGH_EXCESS,
                IMPACT_TAIL_WATCH_EXCESS,
                IMPACT_TAIL_HIGH_EXCESS,
            ],
            "reference_layer": [
                "Clustered-body Profit Scale p95",
                "Clustered-body Profit Scale p99",
                "Clustered-body CV p90",
                "Clustered-body CV p95",
                "Clustered-body CV p99",
                "Clustered-body Loss Rate p90",
                "Body centroid margin",
                "Body centroid margin",
                "Loss Tail distance to zero",
                "Loss Tail distance to zero",
                "Volatility Tail excess over body CV p95",
                "Volatility Tail excess over body CV p95",
                "Impact Tail excess over body impact p95",
                "Impact Tail excess over body impact p95",
            ],
        }
    )
    return result, body_ref, references, threshold_export, body_instability


def build_deterioration_specs(
    *,
    threshold_multiplier: float = 1.0,
    cv_p90_ref: float,
    cv_p95_ref: float,
    cv_p99_ref: float,
    loss_p90_ref: float,
) -> pd.DataFrame:
    """Store all seven role-specific Deterioration rules as auditable data.

    A single universal threshold would misread structurally different roles.
    Each row therefore defines acceptable CV/loss behaviour for one role; tail
    roles reuse body-anchored references where appropriate. The scenario
    multiplier exists solely for Chapter 08 calibration stress.
    """

    multiplier = threshold_multiplier
    clip_rate = lambda value: min(max(value, 0), 1)
    return pd.DataFrame(
        [
            {"analytical_role": "Stable Profit Cluster", "moderate_cv": 1.00 * multiplier, "moderate_loss": clip_rate(0.30 * multiplier), "severe_mean_nonpositive": True, "severe_cv": 1.50 * multiplier, "severe_loss": clip_rate(0.45 * multiplier)},
            {"analytical_role": "High-Impact Profit Cluster", "moderate_cv": 1.25 * multiplier, "moderate_loss": clip_rate(0.25 * multiplier), "severe_mean_nonpositive": True, "severe_cv": 2.00 * multiplier, "severe_loss": clip_rate(0.40 * multiplier)},
            {"analytical_role": "Risk-Oriented Profit Cluster", "moderate_cv": 1.50 * multiplier, "moderate_loss": clip_rate(0.35 * multiplier), "severe_mean_nonpositive": True, "severe_cv": 3.00 * multiplier, "severe_loss": clip_rate(0.50 * multiplier)},
            {"analytical_role": "Stable Loss Cluster", "moderate_cv": 1.50 * multiplier, "moderate_loss": clip_rate(0.45 * multiplier), "severe_mean_nonpositive": False, "severe_cv": 2.50 * multiplier, "severe_loss": clip_rate(0.60 * multiplier)},
            {"analytical_role": "Extreme Volatility Tail", "moderate_cv": cv_p95_ref, "moderate_loss": loss_p90_ref, "severe_mean_nonpositive": True, "severe_cv": cv_p99_ref, "severe_loss": np.nan},
            {"analytical_role": "Extreme Impact Tail", "moderate_cv": 1.50 * multiplier, "moderate_loss": clip_rate(0.25 * multiplier), "severe_mean_nonpositive": True, "severe_cv": 2.50 * multiplier, "severe_loss": clip_rate(0.40 * multiplier)},
            {"analytical_role": "Loss Tail", "moderate_cv": cv_p90_ref, "moderate_loss": clip_rate(0.50 * multiplier), "severe_mean_nonpositive": False, "severe_cv": cv_p95_ref, "severe_loss": clip_rate(0.65 * multiplier)},
        ]
    )


def apply_deterioration_and_concentration(
    frame: pd.DataFrame,
    specification: pd.DataFrame,
    *,
    impact_p95_ref: float,
    impact_p99_ref: float,
) -> pd.DataFrame:
    """Execute Deterioration and Concentration without changing role identity.

    Within a role, moderate/severe conditions use logical OR: breaching any
    relevant risk dimension is sufficient. Severe then overrides moderate.
    Concentration is scoped only to roles whose economic meaning includes
    positive impact; P99 impact or P95 impact under deterioration becomes
    extreme dependence rather than merely elevated value concentration.
    """

    result = frame.copy()
    result["deterioration_level"] = "none"
    result["concentration_level"] = "none"

    for _, rule in specification.iterrows():
        role_mask = result["analytical_role"].eq(rule["analytical_role"])
        moderate = pd.Series(False, index=result.index)
        severe = pd.Series(False, index=result.index)
        if pd.notna(rule["moderate_cv"]):
            moderate |= result["cv_order_profit"].gt(rule["moderate_cv"])
        if pd.notna(rule["moderate_loss"]):
            moderate |= result["pct_orders_loss"].gt(rule["moderate_loss"])
        if bool(rule["severe_mean_nonpositive"]):
            severe |= result["mean_order_profit"].le(0)
        if pd.notna(rule["severe_cv"]):
            severe |= result["cv_order_profit"].gt(rule["severe_cv"])
        if pd.notna(rule["severe_loss"]):
            severe |= result["pct_orders_loss"].gt(rule["severe_loss"])

        result.loc[role_mask & moderate & ~severe, "deterioration_level"] = "moderate"
        result.loc[role_mask & severe, "deterioration_level"] = "severe"

    concentration_scope = result["analytical_role"].isin(
        ["High-Impact Profit Cluster", "Extreme Impact Tail"]
    )
    result.loc[
        concentration_scope & result["profit_scale"].ge(impact_p95_ref),
        "concentration_level",
    ] = "elevated"
    result.loc[
        concentration_scope
        & (
            result["profit_scale"].ge(impact_p99_ref)
            | (
                result["profit_scale"].ge(impact_p95_ref)
                & result["deterioration_level"].ne("none")
            )
        ),
        "concentration_level",
    ] = "extreme"
    return result


def resolve_governance_signals(
    flow_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply Reassess > Reroute > Intensify > No Escalation precedence.

    Precedence resolves action conflict without deleting evidence. Structural
    ambiguity (overlap/high instability) is evaluated before route failure;
    severe deterioration/extreme concentration then require rerouting; moderate
    pressure requests intensification. ``primary_signal`` is a reader-facing
    owner, while ``n_active_signals`` preserves multi-signal complexity.
    """

    result = flow_df.copy()
    reassess = (
        result["compound_overlap_flag"]
        | result["assignment_instability"].eq("high")
    )
    reroute = (
        result["deterioration_level"].eq("severe")
        | result["concentration_level"].eq("extreme")
    )
    intensify = (
        result["deterioration_level"].eq("moderate")
        | result["concentration_level"].eq("elevated")
        | result["assignment_instability"].eq("watch")
    )

    result["escalation_status"] = "No Escalation"
    result.loc[intensify, "escalation_status"] = "Intensify Action"
    result.loc[reroute, "escalation_status"] = "Reroute Action"
    result.loc[reassess, "escalation_status"] = "Reassess Classification"

    result["primary_signal"] = np.select(
        [
            result["compound_overlap_flag"],
            result["assignment_instability"].eq("high"),
            result["deterioration_level"].eq("severe"),
            result["concentration_level"].eq("extreme"),
            result["deterioration_level"].eq("moderate"),
            result["concentration_level"].eq("elevated"),
            result["assignment_instability"].eq("watch"),
        ],
        [
            "Tail Overlap",
            "High Classification Instability",
            "Severe Deterioration",
            "Extreme Concentration",
            "Moderate Deterioration",
            "Elevated Concentration",
            "Classification Instability Watch",
        ],
        default="No Signal",
    )
    result["n_active_signals"] = (
        result["compound_overlap_flag"].astype(int)
        + result["deterioration_level"].ne("none").astype(int)
        + result["concentration_level"].ne("none").astype(int)
        + result["assignment_instability"].ne("none").astype(int)
    )

    signal_summary = pd.DataFrame(
        {
            "Signal": [
                "Tail Overlap",
                "Deterioration — Moderate",
                "Deterioration — Severe",
                "Concentration — Elevated",
                "Concentration — Extreme",
                "Classification Instability — Watch",
                "Classification Instability — High",
            ],
            "Products": [
                int(result["compound_overlap_flag"].sum()),
                int(result["deterioration_level"].eq("moderate").sum()),
                int(result["deterioration_level"].eq("severe").sum()),
                int(result["concentration_level"].eq("elevated").sum()),
                int(result["concentration_level"].eq("extreme").sum()),
                int(result["assignment_instability"].eq("watch").sum()),
                int(result["assignment_instability"].eq("high").sum()),
            ],
        }
    )
    signal_summary["Portfolio Share"] = signal_summary["Products"] / len(result)
    escalation_summary = (
        result["escalation_status"]
        .value_counts()
        .rename_axis("Escalation Status")
        .reset_index(name="Products")
    )
    escalation_summary["Portfolio Share"] = escalation_summary["Products"] / len(result)
    return result, signal_summary, escalation_summary


def _show_chapter_07_outputs(result: Chapter07Result) -> None:
    print("\n=== ANALYTICAL ROLE → BASELINE ACTION ===")
    _display(
        result.baseline_action_summary.rename(
            columns={"n_products": "Products", "total_profit": "Total_Profit"}
        )
    )
    print("\n=== GOVERNANCE THRESHOLD REFERENCE ===")
    _display(result.threshold_export.round({"value": 4}))
    print("\n=== CLASSIFICATION INSTABILITY GOVERNANCE SIGNAL ===")
    _display(
        result.flow_df["assignment_instability"]
        .value_counts()
        .rename_axis("Classification Instability")
        .reset_index(name="Products")
    )
    print("\n=== EXECUTED DETERIORATION RULE SPECIFICATION ===")
    _display(result.deterioration_specs.round(4))
    print("\n=== GOVERNANCE SIGNAL SUMMARY ===")
    _display(result.signal_summary.round(3))
    print("\n=== RESOLVED ESCALATION STATUS ===")
    _display(result.escalation_summary.round(3))


def run_chapter_07(
    config: AnalysisConfig,
    chapter_05: Chapter05Result,
    chapter_06: Chapter06Result,
    *,
    show_outputs: bool = True,
) -> Chapter07Result:
    """Execute, export, and validate the complete Chapter 07 stage."""

    config.prepare_output_directories()
    flow_df, baseline_summary = build_governance_base(chapter_06.df_seg_clusters)
    flow_df, body_ref, references, threshold_export, body_instability = (
        build_classification_instability(flow_df, chapter_05)
    )
    deterioration_specs = build_deterioration_specs(
        cv_p90_ref=references["cv_p90"],
        cv_p95_ref=references["cv_p95"],
        cv_p99_ref=references["cv_p99"],
        loss_p90_ref=references["loss_p90"],
    )
    flow_df = apply_deterioration_and_concentration(
        flow_df,
        deterioration_specs,
        impact_p95_ref=references["impact_p95"],
        impact_p99_ref=references["impact_p99"],
    )
    flow_df, signal_summary, escalation_summary = resolve_governance_signals(flow_df)

    threshold_path = config.reports_dir / "governance_threshold_reference.csv"
    signal_path = config.reports_dir / "governance_signal_summary.csv"
    threshold_export.to_csv(threshold_path, index=False)
    signal_summary.to_csv(signal_path, index=False)

    result = Chapter07Result(
        flow_df=flow_df,
        analytical_to_action=ANALYTICAL_TO_ACTION.copy(),
        baseline_action_summary=baseline_summary,
        body_ref=body_ref,
        governance_references=references,
        threshold_export=threshold_export,
        body_instability=body_instability,
        deterioration_specs=deterioration_specs,
        signal_summary=signal_summary,
        escalation_summary=escalation_summary,
        threshold_export_path=threshold_path,
        signal_summary_path=signal_path,
    )
    validate_chapter_07(
        result,
        chapter_06=chapter_06,
        strict_project_baseline=config.strict_project_baseline,
    )
    if show_outputs:
        _show_chapter_07_outputs(result)
    return result
