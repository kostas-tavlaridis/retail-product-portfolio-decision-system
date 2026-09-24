"""Runtime checks that protect chapter handoffs and project baselines."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from portfolio_pipeline.contracts import (
    Chapter01Result,
    Chapter02Result,
    Chapter03Result,
    Chapter04Result,
    Chapter05Result,
    Chapter06Result,
    Chapter07Result,
    Chapter08Result,
    Chapter09Result,
)


class PipelineValidationError(RuntimeError):
    """Raised when an analytical stage violates a declared data contract."""


CHAPTER_01_REQUIRED_INPUT_COLUMNS = {
    "order_id",
    "customer_id",
    "product_id",
    "product_name",
    "category",
    "sub_category",
    "order_date",
    "ship_date",
    "sales",
    "profit",
    "discount",
    "quantity",
    "postal_code",
}


CHAPTER_01_PROJECT_BASELINE: Mapping[str, float | int] = {
    "input_rows": 9_986,
    "distinct_orders": 5_009,
    "distinct_customers": 793,
    "distinct_product_ids": 1_862,
    "product_pairs": 1_894,
    "total_sales": 2_297_200.86,
    "total_profit": 286_397.02,
}


def _require(condition: bool, message: str) -> None:
    """Raise one consistent, manager-readable validation error."""

    if not condition:
        raise PipelineValidationError(message)


def validate_chapter_01_input_schema(df: pd.DataFrame) -> None:
    """Confirm that the SQL-cleaned input supports the Chapter 01 logic."""

    missing = sorted(CHAPTER_01_REQUIRED_INPUT_COLUMNS.difference(df.columns))
    _require(
        not missing,
        "Chapter 01 input is missing required columns: " + ", ".join(missing),
    )


def validate_chapter_01(
    result: Chapter01Result,
    *,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate grain integrity, economic reconciliation, and baseline counts.

    Structural checks always run. Dataset-specific headline checks run when
    ``strict_project_baseline`` is enabled, which is the default for this project.
    """

    df = result.df
    order_prod = result.order_prod
    totals = result.totals
    product_dim = result.product_dim
    product_stage1 = result.product_stage1

    validate_chapter_01_input_schema(df)

    product_key = ["product_id", "product_name"]
    order_product_key = ["order_id", *product_key]
    product_pairs = int(df[product_key].drop_duplicates().shape[0])

    _require(
        not order_prod.duplicated(order_product_key).any(),
        "order_prod is not unique at the declared order × product grain.",
    )
    _require(
        not totals.duplicated(product_key).any(),
        "totals contains duplicate product ID + product name pairs.",
    )
    _require(
        not product_dim.duplicated(product_key).any(),
        "A product ID + product name pair maps to multiple category records.",
    )
    _require(
        not product_stage1.duplicated(product_key).any(),
        "product_stage1 is not unique at the declared product grain.",
    )
    _require(
        len(product_stage1) == product_pairs,
        "product_stage1 does not cover the complete product-pair universe.",
    )
    _require(
        np.isclose(order_prod["sales"].sum(), df["sales"].sum(), atol=1e-8),
        "Sales do not reconcile between the transaction and order-product grains.",
    )
    _require(
        np.isclose(order_prod["profit"].sum(), df["profit"].sum(), atol=1e-8),
        "Profit does not reconcile between the transaction and order-product grains.",
    )
    _require(
        np.isclose(totals["total_sales"].sum(), df["sales"].sum(), atol=1e-8),
        "Product total sales do not reconcile to the input dataset.",
    )
    _require(
        np.isclose(totals["total_profit"].sum(), df["profit"].sum(), atol=1e-8),
        "Product total profit does not reconcile to the input dataset.",
    )

    if strict_project_baseline:
        baseline = CHAPTER_01_PROJECT_BASELINE
        _require(len(df) == baseline["input_rows"], "Unexpected input row count.")
        _require(
            df["order_id"].nunique() == baseline["distinct_orders"],
            "Unexpected distinct-order count.",
        )
        _require(
            df["customer_id"].nunique() == baseline["distinct_customers"],
            "Unexpected distinct-customer count.",
        )
        _require(
            df["product_id"].nunique() == baseline["distinct_product_ids"],
            "Unexpected distinct-product-ID count.",
        )
        _require(product_pairs == baseline["product_pairs"], "Unexpected product universe.")
        _require(
            np.isclose(df["sales"].sum(), baseline["total_sales"], atol=0.01),
            "Input sales do not match the locked project baseline.",
        )
        _require(
            np.isclose(df["profit"].sum(), baseline["total_profit"], atol=0.01),
            "Input profit does not match the locked project baseline.",
        )

    return {
        "status": "PASS",
        "input_rows": int(len(df)),
        "order_product_rows": int(len(order_prod)),
        "product_pairs": product_pairs,
        "total_sales": float(df["sales"].sum()),
        "total_profit": float(df["profit"].sum()),
    }


def validate_chapter_02(
    result: Chapter02Result,
    *,
    product_stage1: pd.DataFrame,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate diagnostic coverage, exports, and locked notebook metrics."""

    stage1_diag = result.stage1_diag
    summary = result.stage1_summary_stats

    required_diag_keys = {
        "pareto_df",
        "pareto_x",
        "pareto_80_count",
        "top_10_positive_profit_share",
        "profit_mean",
        "profit_median",
        "loss_bucket_counts",
        "high_loss_share",
    }
    _require(
        required_diag_keys.issubset(stage1_diag),
        "Chapter 02 diagnostic structure is missing required evidence.",
    )
    _require(
        list(summary.columns) == ["Metric", "Value"],
        "Chapter 02 summary schema differs from the notebook contract.",
    )
    _require(len(summary) == 6, "Chapter 02 summary must contain six metrics.")
    _require(
        int(stage1_diag["pareto_80_count"]) > 0,
        "The positive-profit Pareto threshold was not resolved.",
    )
    _require(result.dashboard_path.is_file(), "Chapter 02 dashboard was not exported.")
    _require(
        result.product_diagnostics_path.is_file(),
        "Chapter 02 product diagnostic CSV was not exported.",
    )
    _require(
        result.structural_summary_path.is_file(),
        "Chapter 02 structural summary CSV was not exported.",
    )

    exported_products = pd.read_csv(result.product_diagnostics_path)
    exported_summary = pd.read_csv(result.structural_summary_path)
    _require(
        list(exported_products.columns) == list(product_stage1.columns),
        "Exported Chapter 02 product-diagnostic columns changed order.",
    )
    _require(
        len(exported_products) == len(product_stage1),
        "Exported Chapter 02 product diagnostics have incomplete coverage.",
    )
    _require(
        exported_summary.astype(str).equals(summary.astype(str)),
        "Exported Chapter 02 summary values differ from the in-memory summary.",
    )

    if strict_project_baseline:
        expected_values = ["83.9%", "61.9%", "26.1%", "347", "€151.2", "€43.9"]
        _require(
            summary["Value"].tolist() == expected_values,
            "Chapter 02 summary differs from the locked final-notebook readout.",
        )
        _require(
            int(stage1_diag["pareto_80_count"]) == 347,
            "Chapter 02 Pareto threshold differs from the final notebook.",
        )

    return {
        "status": "PASS",
        "products": int(len(product_stage1)),
        "pareto_80_count": int(stage1_diag["pareto_80_count"]),
        "summary_metrics": int(len(summary)),
    }


def _audit_value(cv_audit: pd.DataFrame, metric: str) -> float:
    """Read one numeric value from the Chapter 03 CV audit."""

    matches = cv_audit.loc[cv_audit["metric"] == metric, "value"]
    _require(len(matches) == 1, f"CV audit metric is missing or duplicated: {metric}")
    return float(matches.iloc[0])


def validate_chapter_03(
    result: Chapter03Result,
    *,
    order_prod: pd.DataFrame,
    totals: pd.DataFrame,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate KPI coverage, CV treatment, reconciliation, and baseline values."""

    vol = result.vol
    cv_audit = result.cv_audit
    product_metrics = result.product_metrics
    df_seg = result.df_seg
    product_key = ["product_id", "product_name"]

    required_kpi_columns = {
        "mean_order_profit",
        "cv_order_profit_raw",
        "cv_order_profit_model",
        "cv_order_profit",
        "pct_orders_loss",
        "profit_scale",
        "cv_not_estimable",
        "cv_capped_flag",
        "cv_cap_used",
        "cv_epsilon_used",
    }
    _require(
        required_kpi_columns.issubset(df_seg.columns),
        "Chapter 03 canonical KPI table is missing required fields.",
    )
    _require(not vol.duplicated(product_key).any(), "vol is not unique by product pair.")
    _require(
        not df_seg.duplicated(product_key).any(),
        "df_seg is not unique by product pair.",
    )
    _require(
        len(vol) == len(totals) == len(product_metrics) == len(df_seg),
        "Chapter 03 structures do not cover the same product universe.",
    )
    _require(len(cv_audit) == 12, "Chapter 03 CV audit must contain twelve metrics.")
    _require(
        np.isfinite(df_seg["cv_order_profit"]).all(),
        "The modelling CV contains non-finite values.",
    )
    _require(
        df_seg["cv_order_profit"].ge(0).all(),
        "The modelling CV contains negative values.",
    )
    _require(
        df_seg["profit_scale"].between(-1, 1).all(),
        "profit_scale lies outside the declared [-1, 1] geometry range.",
    )
    _require(
        np.isclose(product_metrics["total_profit"].sum(), order_prod["profit"].sum()),
        "Chapter 03 product profit does not reconcile to order_prod.",
    )
    _require(
        df_seg.loc[df_seg["cv_not_estimable"], "cv_order_profit"].eq(0).all(),
        "Non-estimable CV products do not use the declared neutral coordinate.",
    )
    _require(
        df_seg["cv_order_profit"].le(result.cv_cap + 1e-12).all(),
        "At least one modelling CV exceeds the empirical cap.",
    )

    if strict_project_baseline:
        _require(len(df_seg) == 1_894, "Unexpected Chapter 03 product universe.")
        _require(
            np.isclose(result.cv_epsilon, 0.2533, atol=0.00005),
            "CV epsilon differs from the final notebook.",
        )
        _require(
            np.isclose(result.cv_cap, 22.6677, atol=0.00005),
            "CV cap differs from the final notebook.",
        )
        _require(
            _audit_value(cv_audit, "cv_not_estimable_products") == 93,
            "Non-estimable CV count differs from the final notebook.",
        )
        _require(
            _audit_value(cv_audit, "cv_capped_products") == 18,
            "Capped CV count differs from the final notebook.",
        )
        top_product = df_seg.iloc[0]
        _require(
            top_product["product_id"] == "TEC-CO-10004722",
            "Chapter 03 top-product ordering differs from the final notebook.",
        )
        _require(
            np.isclose(top_product["cv_order_profit"], 0.549944, atol=0.0000005),
            "Top-product modelling CV differs from the final notebook.",
        )

    return {
        "status": "PASS",
        "products": int(len(df_seg)),
        "cv_epsilon": float(result.cv_epsilon),
        "cv_cap": float(result.cv_cap),
        "cv_not_estimable": int(vol["cv_not_estimable"].sum()),
        "cv_capped": int(vol["cv_capped_flag"].sum()),
    }


def validate_chapter_04(
    result: Chapter04Result,
    *,
    df_seg: pd.DataFrame,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate body/tail closure, threshold evidence, and sensitivity outputs."""

    _require(len(result.features) == 4, "Chapter 04 must use four modelling KPIs.")
    _require(
        len(result.km_df_raw) == len(df_seg),
        "Chapter 04 does not preserve the complete KPI product universe.",
    )
    _require(
        len(result.km_df_clust) + len(result.km_df_tail_candidates) == len(df_seg),
        "Chapter 04 body and tail do not reconstruct the full portfolio.",
    )
    _require(
        result.km_df_clust.index.intersection(
            result.km_df_tail_candidates.index
        ).empty,
        "Chapter 04 body and tail overlap.",
    )
    _require(len(result.body_thresholds_df) == 3, "Expected three body boundaries.")
    _require(
        len(result.body_boundary_sensitivity) == 5,
        "Expected five Chapter 04 sensitivity cases.",
    )
    _require(
        result.body_boundary_sensitivity["selected_boundary"].sum() == 1,
        "Chapter 04 must document exactly one selected boundary.",
    )
    _require(result.body_thresholds_path.is_file(), "Body thresholds CSV is missing.")
    _require(
        result.boundary_sensitivity_path.is_file(),
        "Body-boundary sensitivity CSV is missing.",
    )

    if strict_project_baseline:
        _require(len(result.km_df_raw) == 1_894, "Unexpected modelling universe.")
        _require(len(result.km_df_clust) == 1_822, "Unexpected body-product count.")
        _require(
            len(result.km_df_tail_candidates) == 72,
            "Unexpected structural-tail count.",
        )
        expected_counts = [1_894, 1_867, 1_822, 1_721, 1_574]
        _require(
            result.body_boundary_sensitivity["body_products"].tolist()
            == expected_counts,
            "Chapter 04 sensitivity body counts differ from the final notebook.",
        )
        selected = result.body_boundary_sensitivity.loc[
            result.body_boundary_sensitivity["selected_boundary"]
        ].iloc[0]
        _require(
            np.isclose(selected["silhouette_score_k4"], 0.557, atol=0.0005),
            "Selected-boundary silhouette differs from the final notebook.",
        )

    return {
        "status": "PASS",
        "products": int(len(result.km_df_raw)),
        "body_products": int(len(result.km_df_clust)),
        "tail_products": int(len(result.km_df_tail_candidates)),
        "body_retention": float(len(result.km_df_clust) / len(result.km_df_raw)),
    }


def validate_chapter_05(
    result: Chapter05Result,
    *,
    df_seg: pd.DataFrame,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate assignment closure, stability evidence, body roles, and exports."""

    _require(
        len(result.df_seg_clusters) == len(df_seg),
        "Chapter 05 changed the product universe.",
    )
    _require(
        result.df_seg_clusters["k_cluster"].notna().all(),
        "Chapter 05 contains missing body/tail assignment states.",
    )
    body_mask = result.df_seg_clusters["k_cluster"].ne("Unclustered")
    _require(
        result.df_seg_clusters.loc[body_mask, "body_role"].notna().all(),
        "At least one clustered product is missing its body role.",
    )
    _require(
        result.df_seg_clusters.loc[~body_mask, "body_role"].isna().all(),
        "A structural-tail product received a body role.",
    )
    _require(len(result.cluster_profile) == 4, "Expected four K-means body roles.")
    _require(
        len(result.cluster_stability_iterations) > 0,
        "Cluster stability evidence is empty.",
    )
    _require(
        len(result.cluster_stability_summary) == 2,
        "Cluster stability summary must contain ARI and silhouette.",
    )
    _require(
        all(path.is_file() for path in result.export_paths),
        "At least one Chapter 05 audit export is missing.",
    )

    selected_k_rows = result.kmeans_model_selection.loc[
        result.kmeans_model_selection["selected_k"]
    ]
    _require(len(selected_k_rows) == 1, "Expected one selected K value.")

    if strict_project_baseline:
        counts = result.df_seg_clusters["k_cluster"].value_counts().to_dict()
        expected_counts = {0: 1_246, 1: 384, 2: 123, 3: 69, "Unclustered": 72}
        _require(counts == expected_counts, "K-means assignments differ from the notebook.")
        selected_row = selected_k_rows.iloc[0]
        _require(int(selected_row["K"]) == 4, "The selected model is not K=4.")
        _require(
            np.isclose(selected_row["silhouette_score"], 0.557, atol=0.0005),
            "K=4 silhouette differs from the final notebook.",
        )
        ari_median = float(result.cluster_stability_summary.loc[0, "Median"])
        _require(
            np.isclose(ari_median, 0.976, atol=0.0005),
            "Resampling ARI median differs from the final notebook.",
        )
        cv_row = result.cv_support_summary.iloc[0]
        _require(
            int(cv_row["excluded_non_estimable_cv_products"]) == 80,
            "CV-support exclusion count differs from the final notebook.",
        )
        _require(
            np.isclose(cv_row["adjusted_rand_index_vs_baseline"], 0.992, atol=0.0005),
            "CV-support ARI differs from the final notebook.",
        )

    return {
        "status": "PASS",
        "body_products": int(body_mask.sum()),
        "tail_products": int((~body_mask).sum()),
        "body_roles": int(result.cluster_profile["body_role"].nunique()),
        "ari_median": float(result.cluster_stability_summary.loc[0, "Median"]),
    }


def validate_chapter_06(
    result: Chapter06Result,
    *,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate tail assignment, role closure, overlap evidence, and artifacts."""

    unified = result.df_seg_clusters
    _require(
        len(result.body) + len(result.tail) == len(unified),
        "Chapter 06 body and tail do not reconstruct the portfolio.",
    )
    _require(
        unified["analytical_role"].notna().all(),
        "At least one product is missing its unified analytical role.",
    )
    _require(
        unified["analytical_role"].nunique() == 7,
        "The unified taxonomy must contain seven analytical roles.",
    )
    _require(
        result.tail["primary_tail_type"].notna().all(),
        "At least one structural-tail product is unclassified.",
    )
    _require(
        result.tail["assignment_basis"].notna().all(),
        "At least one structural-tail product lacks assignment provenance.",
    )
    _require(len(result.tail_summary) == 3, "Expected three primary tail regimes.")
    _require(
        len(result.analytical_role_profile) == 7,
        "Expected seven rows in the analytical-role profile.",
    )
    _require(
        len(result.tail_export) == len(result.tail),
        "Tail export does not cover every structural-tail product.",
    )
    _require(result.tail_export_path.is_file(), "Tail classification export is missing.")
    _require(
        result.analytical_role_profile_path.is_file(),
        "Analytical-role profile export is missing.",
    )
    _require(result.geometry_figure_path.is_file(), "Portfolio geometry figure is missing.")

    if strict_project_baseline:
        _require(len(unified) == 1_894, "Unexpected unified portfolio size.")
        _require(len(result.body) == 1_822, "Unexpected Chapter 06 body count.")
        _require(len(result.tail) == 72, "Unexpected Chapter 06 tail count.")
        _require(
            np.isclose(result.cv_threshold, 6.6465, atol=0.00005),
            "Tail CV threshold differs from the final notebook.",
        )
        _require(
            np.isclose(result.impact_threshold, 0.0268, atol=0.00005),
            "Tail impact threshold differs from the final notebook.",
        )
        tail_counts = result.tail["primary_tail_type"].value_counts().to_dict()
        expected_tail_counts = {
            "Extreme Impact Tail": 27,
            "Extreme Volatility Tail": 19,
            "Loss Tail": 26,
        }
        _require(
            tail_counts == expected_tail_counts,
            "Primary tail-type counts differ from the final notebook.",
        )
        _require(
            int(result.tail["fallback_assignment_flag"].sum()) == 2,
            "Boundary-direction assignment count differs from the final notebook.",
        )
        _require(
            int(result.tail["n_tail_flags"].gt(1).sum()) == 2,
            "Multi-flag tail count differs from the final notebook.",
        )

    return {
        "status": "PASS",
        "products": int(len(unified)),
        "body_products": int(len(result.body)),
        "tail_products": int(len(result.tail)),
        "analytical_roles": int(unified["analytical_role"].nunique()),
        "fallback_assignments": int(result.tail["fallback_assignment_flag"].sum()),
    }


def validate_chapter_07(
    result: Chapter07Result,
    *,
    chapter_06: Chapter06Result,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate signal construction, precedence, coverage, and audit exports."""

    flow_df = result.flow_df
    _require(
        len(flow_df) == len(chapter_06.df_seg_clusters),
        "Chapter 07 changed the product universe.",
    )
    _require(
        flow_df["product_row_id"].tolist()
        == chapter_06.df_seg_clusters.index.tolist(),
        "Chapter 07 changed product identity or order.",
    )
    _require(
        flow_df["analytical_role"].notna().all(),
        "Chapter 07 contains a missing analytical role.",
    )
    _require(
        flow_df["primary_action"].notna().all(),
        "Chapter 07 contains a missing Primary Action.",
    )
    _require(
        flow_df["primary_signal"].notna().all(),
        "Chapter 07 contains a missing Primary Signal.",
    )
    valid_statuses = {
        "No Escalation",
        "Intensify Action",
        "Reroute Action",
        "Reassess Classification",
    }
    _require(
        set(flow_df["escalation_status"].unique()) == valid_statuses,
        "Chapter 07 escalation statuses differ from the declared four-state contract.",
    )
    _require(
        flow_df["n_active_signals"].ge(0).all(),
        "Chapter 07 contains a negative active-signal count.",
    )
    _require(len(result.threshold_export) == 14, "Expected fourteen governance references.")
    _require(len(result.deterioration_specs) == 7, "Expected seven Deterioration rule sets.")
    _require(len(result.signal_summary) == 7, "Expected seven signal-severity rows.")
    _require(
        result.signal_summary["Portfolio Share"].between(0, 1).all(),
        "Signal-summary portfolio shares lie outside [0, 1].",
    )
    _require(result.threshold_export_path.is_file(), "Governance threshold export is missing.")
    _require(result.signal_summary_path.is_file(), "Governance signal export is missing.")

    if strict_project_baseline:
        _require(len(flow_df) == 1_894, "Unexpected Chapter 07 portfolio size.")
        expected_references = {
            "impact_p95": 0.0268,
            "impact_p99": 0.0565,
            "cv_p90": 3.8951,
            "cv_p95": 6.6465,
            "cv_p99": 16.0393,
            "loss_p90": 0.5000,
        }
        for reference_name, expected_value in expected_references.items():
            _require(
                np.isclose(
                    result.governance_references[reference_name],
                    expected_value,
                    atol=0.00005,
                ),
                f"Governance reference differs from the notebook: {reference_name}",
            )
        expected_instability = {"none": 1_816, "watch": 41, "high": 37}
        _require(
            flow_df["assignment_instability"].value_counts().to_dict()
            == expected_instability,
            "Classification-instability counts differ from the final notebook.",
        )
        _require(
            result.signal_summary["Products"].tolist()
            == [2, 251, 528, 50, 67, 41, 37],
            "Governance Signal counts differ from the final notebook.",
        )
        expected_status_counts = {
            "No Escalation": 1_008,
            "Reroute Action": 567,
            "Intensify Action": 280,
            "Reassess Classification": 39,
        }
        _require(
            flow_df["escalation_status"].value_counts().to_dict()
            == expected_status_counts,
            "Escalation counts differ from the final notebook.",
        )

    return {
        "status": "PASS",
        "products": int(len(flow_df)),
        "signals": int(len(result.signal_summary)),
        "escalation_statuses": int(flow_df["escalation_status"].nunique()),
        "hard_exposure_products": int(
            flow_df["escalation_status"]
            .isin(["Reroute Action", "Reassess Classification"])
            .sum()
        ),
    }


def validate_chapter_08(
    result: Chapter08Result,
    *,
    chapter_07: Chapter07Result,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate route closure, scorecard economics, sensitivity, and exports."""

    flow_df = result.flow_df
    _require(
        len(flow_df) == len(chapter_07.flow_df),
        "Chapter 08 changed the product universe.",
    )
    _require(
        flow_df["product_row_id"].tolist() == chapter_07.flow_df["product_row_id"].tolist(),
        "Chapter 08 changed product identity or order.",
    )
    _require(
        flow_df["escalation_status"].equals(chapter_07.flow_df["escalation_status"]),
        "Chapter 08 rewrote the Chapter 07 Escalation Status.",
    )
    _require(len(result.final_intervention_map) == 16, "Expected a complete 4 × 4 route matrix.")
    _require(
        flow_df["final_intervention"].notna().all(),
        "At least one product lacks a Final Intervention.",
    )
    _require(
        result.coverage_audit["Coverage"].eq(1).all(),
        "Final-intervention coverage is below 100%.",
    )
    _require(
        result.final_intervention_summary["n_products"].sum() == len(flow_df),
        "Final-intervention summary does not reconcile to the portfolio.",
    )
    _require(
        result.final_intervention_summary["portfolio_share"].between(0, 1).all(),
        "Final-intervention shares lie outside [0, 1].",
    )
    _require(len(result.governance_scorecard) == 4, "Expected four governance states.")
    _require(
        result.governance_scorecard["Products"].sum() == len(flow_df),
        "Governance scorecard does not reconcile to the portfolio.",
    )
    _require(
        len(result.governance_scorecard_sensitivity) == 3,
        "Expected strict, baseline, and lenient governance scenarios.",
    )
    export_paths = [
        result.governance_flow_path,
        result.final_intervention_summary_path,
        result.intervention_distribution_path,
        result.governance_pressure_path,
        result.governance_sensitivity_path,
    ]
    _require(all(path.is_file() for path in export_paths), "A Chapter 08 export is missing.")

    if strict_project_baseline:
        _require(len(flow_df) == 1_894, "Unexpected Chapter 08 portfolio size.")
        expected_counts = [1_008, 280, 567, 39]
        _require(
            result.governance_scorecard["Products"].tolist() == expected_counts,
            "Governance scorecard counts differ from the final notebook.",
        )
        expected_profits = [99_341.588, 67_300.738, 115_690.696, 4_063.999]
        expected_losses = [3_389.698, 6_621.544, 64_085.564, 2_995.212]
        _require(
            np.allclose(result.governance_scorecard["Total_Profit"], expected_profits, atol=0.001),
            "Governance scorecard profit differs from the final notebook.",
        )
        _require(
            np.allclose(result.governance_scorecard["Realized_Loss"], expected_losses, atol=0.001),
            "Governance scorecard realized loss differs from the final notebook.",
        )
        expected_sensitivity = np.array(
            [
                [0.4725, 0.3717, 0.5040, 0.9136],
                [0.5322, 0.3200, 0.4181, 0.8701],
                [0.5861, 0.2677, 0.3606, 0.6858],
            ]
        )
        observed_sensitivity = result.governance_scorecard_sensitivity[
            [
                "stable_core_share",
                "hard_exposure_share",
                "hard_exposure_profit_share",
                "hard_exposure_loss_share",
            ]
        ].to_numpy()
        _require(
            np.allclose(observed_sensitivity, expected_sensitivity, atol=0.00005),
            "Governance sensitivity differs from the final notebook.",
        )

    hard_mask = flow_df["escalation_status"].isin(
        ["Reroute Action", "Reassess Classification"]
    )
    return {
        "status": "PASS",
        "products": int(len(flow_df)),
        "observed_routes": int(len(result.final_intervention_summary)),
        "governance_states": int(len(result.governance_scorecard)),
        "hard_exposure_share": float(hard_mask.mean()),
    }


def validate_chapter_09(
    result: Chapter09Result,
    *,
    chapter_08: Chapter08Result,
    strict_project_baseline: bool,
) -> dict[str, float | int | str]:
    """Validate priority scope, peer benchmarks, guards, sensitivity, and exports."""

    flow_df = result.flow_df
    _require(
        len(flow_df) == len(chapter_08.flow_df),
        "Chapter 09 changed the product universe.",
    )
    _require(
        flow_df["product_row_id"].tolist() == chapter_08.flow_df["product_row_id"].tolist(),
        "Chapter 09 changed product identity or order.",
    )
    _require(
        flow_df["escalation_status"].tolist() == chapter_08.flow_df["escalation_status"].tolist(),
        "Chapter 09 rewrote Escalation Status.",
    )
    _require(
        flow_df["final_intervention"].tolist() == chapter_08.flow_df["final_intervention"].tolist(),
        "Chapter 09 rewrote Final Intervention.",
    )
    _require(len(result.role_perf_ref) == 7, "Expected seven role benchmark profiles.")
    _require(
        result.reliability_guards.shape == (len(flow_df), 5),
        "Reliability guards must contain five checks for every product.",
    )
    _require(
        all(pd.api.types.is_bool_dtype(dtype) for dtype in result.reliability_guards.dtypes),
        "Reliability guards are not Boolean.",
    )
    _require(len(result.priority_zone_summary) == 5, "Expected five active Priority Zones.")
    _require(
        result.priority_zone_summary["Products"].sum()
        == int(flow_df["priority_scope_flag"].sum()),
        "Priority-zone summary does not reconcile to active scope.",
    )
    _require(
        len(result.priority_product_decisions) == len(flow_df),
        "Priority product audit does not cover the complete portfolio.",
    )
    _require(
        flow_df.loc[~flow_df["priority_scope_flag"], "priority_zone"].isna().all(),
        "A routine or neutral product received an active Priority Zone.",
    )
    _require(
        len(result.hidden_opportunity_sensitivity) == 36,
        "Hidden-opportunity sensitivity must contain 36 threshold scenarios.",
    )
    export_paths = [
        result.priority_zone_summary_path,
        result.priority_product_decisions_path,
        result.opportunity_quality_summary_path,
        result.hidden_opportunity_sensitivity_path,
        result.governance_output_path,
    ]
    _require(all(path.is_file() for path in export_paths), "A Chapter 09 export is missing.")

    if strict_project_baseline:
        _require(len(flow_df) == 1_894, "Unexpected Chapter 09 portfolio size.")
        expected_deviation = {
            "Role-Aligned": 941,
            "Negative Deviation": 476,
            "Positive Deviation": 285,
            "High Positive Deviation": 192,
        }
        _require(
            flow_df["performance_deviation"].value_counts().to_dict()
            == expected_deviation,
            "Performance-deviation counts differ from the final notebook.",
        )
        expected_zone_counts = [80, 163, 158, 234, 318]
        _require(
            result.priority_zone_summary["Products"].tolist() == expected_zone_counts,
            "Priority-zone counts differ from the final notebook.",
        )
        expected_zone_profit = [89_097.554, 19_954.745, -22_609.315, 57_182.093, 15_569.294]
        expected_zone_loss = [0.000, 4_839.638, 51_040.720, 2_124.932, 3_840.849]
        _require(
            np.allclose(result.priority_zone_summary["Total_Profit"], expected_zone_profit, atol=0.001),
            "Priority-zone profit differs from the final notebook.",
        )
        _require(
            np.allclose(result.priority_zone_summary["Realized_Loss"], expected_zone_loss, atol=0.001),
            "Priority-zone realized loss differs from the final notebook.",
        )
        _require(
            int(flow_df["priority_scope_flag"].sum()) == 953,
            "Active priority scope differs from the final notebook.",
        )
        _require(
            int((~flow_df["priority_scope_flag"]).sum()) == 941,
            "Routine or neutral scope differs from the final notebook.",
        )
        expected_sensitivity_summary = np.array(
            [
                [0.3111, 0.2531, 0.1935, 0.3131],
                [0.0422, 0.0298, 0.0195, 0.0449],
            ]
        )
        observed_summary = result.opportunity_sensitivity_summary[
            ["Baseline", "Median", "P05", "P95"]
        ].to_numpy()
        _require(
            np.allclose(observed_summary, expected_sensitivity_summary, atol=0.00005),
            "Hidden-opportunity sensitivity summary differs from the notebook.",
        )
        _require(
            int(result.hidden_opportunity_sensitivity["profit_share_vs_baseline"].ge(0.75).sum()) == 24,
            "Strong hidden-opportunity retention count differs from the notebook.",
        )
        _require(
            result.hidden_opportunity_sensitivity["profit_share_vs_baseline"].gt(0.50).all(),
            "At least one hidden-opportunity scenario collapses below 50% retention.",
        )

    return {
        "status": "PASS",
        "products": int(len(flow_df)),
        "priority_zones": int(len(result.priority_zone_summary)),
        "active_priority_products": int(flow_df["priority_scope_flag"].sum()),
        "routine_neutral_products": int((~flow_df["priority_scope_flag"]).sum()),
        "hidden_opportunity_products": int(
            flow_df["performance_context"].eq("True Hidden Opportunity").sum()
        ),
    }
