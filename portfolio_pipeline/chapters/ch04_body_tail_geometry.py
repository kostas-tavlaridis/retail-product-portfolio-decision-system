"""Chapter 04 — Body / Tail Geometry.

Purpose
-------
Validate the four-dimensional KPI space, separate the clusterable portfolio
body from structural extremes, and test whether that partition depends on one
arbitrary percentile choice.

The selected body definition applies the empirical 1st–99th percentile range
to Mean Order Profit, model CV, and Profit Scale. Loss Rate remains a modelling
coordinate but is not used as a body-entry filter, preserving recurring downside
as behavioural information inside the central portfolio structure.

This is mechanism selection, not outlier deletion. K-means minimizes squared
Euclidean distance to centroids and is therefore highly sensitive to extreme
leverage even after standardization. The body is where centroid structure is
meaningful; the tail is preserved one-for-one for explicit rule-based treatment
in Chapter 06.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

try:
    from IPython.display import display as _display
except ImportError:  # pragma: no cover
    def _display(value: object) -> None:
        print(value)

from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.contracts import Chapter04Result
from portfolio_pipeline.validation import validate_chapter_04


MODEL_FEATURES = [
    "mean_order_profit",
    "cv_order_profit",
    "pct_orders_loss",
    "profit_scale",
]

BODY_BOUNDARY_SPECS = {
    "mean_order_profit": (0.01, 0.99),
    "cv_order_profit": (0.01, 0.99),
    "profit_scale": (0.01, 0.99),
}


def prepare_model_geometry(
    df_seg: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate the canonical four-KPI modelling space before separation.

    Any NaN or infinity is treated as a specification failure.  Rows are never
    silently dropped because that would break product coverage and could make
    later portfolio shares appear valid on a smaller, undocumented universe.
    """

    model_feature_source = (
        df_seg[MODEL_FEATURES]
        .replace([np.inf, -np.inf], np.nan)
        .copy()
    )
    invalid_feature_rows = model_feature_source.isna().any(axis=1)
    n_invalid_feature_rows = int(invalid_feature_rows.sum())
    if n_invalid_feature_rows > 0:
        raise ValueError(
            f"{n_invalid_feature_rows} products contain missing or non-finite "
            "values in the K-means feature space."
        )

    km_df_raw = model_feature_source.copy()
    if len(km_df_raw) != len(df_seg):
        raise ValueError("The modelling feature matrix does not preserve full coverage.")

    print("\n=== MODEL KPI SPACE — BEFORE BODY/TAIL SEPARATION ===")
    print(f"Product records received: {len(df_seg):,}")
    print(f"Product records retained: {len(km_df_raw):,}")
    print(f"Modelling features:        {len(MODEL_FEATURES)}")
    print(f"Invalid feature rows:      {n_invalid_feature_rows}")

    model_geometry_profile = (
        km_df_raw.describe(percentiles=[0.01, 0.50, 0.99])
        .T[["count", "min", "1%", "50%", "99%", "max"]]
        .rename(columns={"50%": "median"})
    )
    return km_df_raw, model_geometry_profile


def separate_empirical_body(
    km_df_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.DataFrame]:
    """Translate selected quantile positions into observed body boundaries.

    A product belongs to the body only when it falls inside every selected
    inclusive interval (logical AND).  Crossing any one boundary is sufficient
    for structural-tail treatment.  Loss Rate is omitted from this entry gate
    because it is bounded [0, 1] and represents recurring behaviour that the
    central clustering should be allowed to discover.
    """

    body_thresholds: list[dict[str, object]] = []
    for feature_name, (lower_quantile, upper_quantile) in BODY_BOUNDARY_SPECS.items():
        lower_value, upper_value = km_df_raw[feature_name].quantile(
            [lower_quantile, upper_quantile]
        )
        body_thresholds.append(
            {
                "feature": feature_name,
                "feature_layer": "model_feature_space",
                "lower_quantile": lower_quantile,
                "upper_quantile": upper_quantile,
                "lower_value": lower_value,
                "upper_value": upper_value,
            }
        )

    body_thresholds_df = pd.DataFrame(body_thresholds)
    body_mask = pd.Series(True, index=km_df_raw.index)
    for _, boundary in body_thresholds_df.iterrows():
        body_mask &= km_df_raw[boundary["feature"]].between(
            boundary["lower_value"],
            boundary["upper_value"],
            inclusive="both",
        )

    km_df_clust = km_df_raw.loc[body_mask].copy()
    km_df_tail_candidates = km_df_raw.loc[~body_mask].copy()
    return body_thresholds_df, body_mask, km_df_clust, km_df_tail_candidates


def build_boundary_sensitivity(
    km_df_raw: pd.DataFrame,
    *,
    k_opt: int,
    random_state: int,
) -> pd.DataFrame:
    """Stress-test body retention and K=4 separation across nearby boundaries.

    K, seed and n_init remain fixed so only the boundary specification changes.
    Silhouette measures cohesion versus nearest-cluster separation; smallest
    cluster share detects whether a candidate boundary leaves a tiny isolated
    group masquerading as structure. Inertia is intentionally omitted here
    because it changes mechanically with the candidate sample size.
    """

    boundary_grid = [
        ("No separation", 0.000, 1.000),
        ("0.5%–99.5%", 0.005, 0.995),
        ("1%–99%", 0.010, 0.990),
        ("2.5%–97.5%", 0.025, 0.975),
        ("5%–95%", 0.050, 0.950),
    ]
    sensitivity_rows: list[dict[str, object]] = []

    for boundary_case, lower_quantile, upper_quantile in boundary_grid:
        candidate_body_mask = pd.Series(True, index=km_df_raw.index)
        for feature_name in BODY_BOUNDARY_SPECS:
            lower_value, upper_value = km_df_raw[feature_name].quantile(
                [lower_quantile, upper_quantile]
            )
            candidate_body_mask &= km_df_raw[feature_name].between(
                lower_value,
                upper_value,
                inclusive="both",
            )

        candidate_body = km_df_raw.loc[candidate_body_mask, MODEL_FEATURES].copy()
        candidate_tail = km_df_raw.loc[~candidate_body_mask, MODEL_FEATURES].copy()
        candidate_body_products = len(candidate_body)
        candidate_tail_products = len(candidate_tail)

        if candidate_body_products > k_opt:
            candidate_scaled = StandardScaler().fit_transform(candidate_body[MODEL_FEATURES])
            candidate_model = KMeans(
                n_clusters=k_opt,
                random_state=random_state,
                n_init=20,
            )
            candidate_labels = candidate_model.fit_predict(candidate_scaled)
            candidate_silhouette = silhouette_score(candidate_scaled, candidate_labels)
            candidate_cluster_sizes = pd.Series(candidate_labels).value_counts()
            smallest_products = int(candidate_cluster_sizes.min())
            smallest_share = smallest_products / candidate_body_products
        else:
            candidate_silhouette = np.nan
            smallest_products = np.nan
            smallest_share = np.nan

        sensitivity_rows.append(
            {
                "boundary_case": boundary_case,
                "lower_quantile": lower_quantile,
                "upper_quantile": upper_quantile,
                "body_products": candidate_body_products,
                "tail_products": candidate_tail_products,
                "body_retention_rate": candidate_body_products / len(km_df_raw),
                "tail_share": candidate_tail_products / len(km_df_raw),
                "smallest_cluster_products_k4": smallest_products,
                "smallest_cluster_share_k4": smallest_share,
                "silhouette_score_k4": candidate_silhouette,
            }
        )

    sensitivity = pd.DataFrame(sensitivity_rows)
    best_tested_silhouette = sensitivity["silhouette_score_k4"].max()
    sensitivity["silhouette_gap_from_best"] = (
        best_tested_silhouette - sensitivity["silhouette_score_k4"]
    )
    no_split_silhouette = sensitivity.loc[
        sensitivity["boundary_case"] == "No separation",
        "silhouette_score_k4",
    ].iloc[0]
    sensitivity["silhouette_change_vs_no_separation"] = (
        sensitivity["silhouette_score_k4"] - no_split_silhouette
    )
    sensitivity["selected_boundary"] = (
        sensitivity["lower_quantile"].eq(0.010)
        & sensitivity["upper_quantile"].eq(0.990)
    )
    return sensitivity


def _show_chapter_04_outputs(
    model_geometry_profile: pd.DataFrame,
    body_thresholds_df: pd.DataFrame,
    km_df_raw: pd.DataFrame,
    km_df_clust: pd.DataFrame,
    km_df_tail_candidates: pd.DataFrame,
    sensitivity: pd.DataFrame,
) -> None:
    """Reproduce the notebook-facing diagnostic readouts."""

    model_geometry_view = model_geometry_profile.rename(
        index={
            "mean_order_profit": "Mean Order Profit",
            "cv_order_profit": "Model CV",
            "pct_orders_loss": "Loss Rate",
            "profit_scale": "Profit Scale",
        }
    )
    print("\n=== PRE-BOUNDARY KPI GEOMETRY PROFILE ===")
    _display(model_geometry_view.round(4))

    boundary_view = body_thresholds_df[
        ["feature", "lower_quantile", "upper_quantile", "lower_value", "upper_value"]
    ].copy()
    boundary_view = boundary_view.rename(
        columns={
            "feature": "KPI",
            "lower_quantile": "Lower Quantile",
            "upper_quantile": "Upper Quantile",
            "lower_value": "Lower Value",
            "upper_value": "Upper Value",
        }
    )
    boundary_view["KPI"] = boundary_view["KPI"].map(
        {
            "mean_order_profit": "Mean Order Profit",
            "cv_order_profit": "Model CV",
            "profit_scale": "Profit Scale",
        }
    )
    print("\n=== SELECTED EMPIRICAL BODY BOUNDARIES ===")
    _display(
        boundary_view.round(
            {
                "Lower Quantile": 3,
                "Upper Quantile": 3,
                "Lower Value": 4,
                "Upper Value": 4,
            }
        )
    )

    print("\n=== EMPIRICAL BODY / TAIL SEPARATION SUMMARY ===")
    print(f"Products before separation:  {len(km_df_raw):,}")
    print(f"Products retained in body:   {len(km_df_clust):,}")
    print(f"Structural-tail candidates:  {len(km_df_tail_candidates):,}")
    print(f"Body retention rate:         {len(km_df_clust) / len(km_df_raw):.1%}")
    print(f"Structural-tail share:       {len(km_df_tail_candidates) / len(km_df_raw):.1%}")

    view = sensitivity.copy()
    view["Boundary"] = view["boundary_case"].replace(
        {"No separation": "No separation (0%–100%)"}
    )
    view["Body Products"] = view["body_products"].map(lambda value: f"{value:,}")
    view["Tail Products"] = view["tail_products"].map(lambda value: f"{value:,}")
    view["Body Retention"] = view["body_retention_rate"].map(lambda value: f"{value:.1%}")
    view["Smallest K=4 Cluster"] = (
        view["smallest_cluster_products_k4"].astype(int).map(lambda value: f"{value:,}")
        + " ("
        + view["smallest_cluster_share_k4"].map(lambda value: f"{value:.1%}")
        + ")"
    )
    view["Silhouette (K=4)"] = view["silhouette_score_k4"].map(
        lambda value: f"{value:.3f}"
    )
    view["Change vs No Split"] = view["silhouette_change_vs_no_separation"].map(
        lambda value: "0.000" if abs(value) < 0.0005 else f"{value:+.3f}"
    )
    view["Selected"] = view["selected_boundary"].map({True: "✓", False: ""})
    print("\n=== BODY-BOUNDARY SENSITIVITY CHECK ===")
    _display(
        view[
            [
                "Boundary",
                "Body Products",
                "Tail Products",
                "Body Retention",
                "Smallest K=4 Cluster",
                "Silhouette (K=4)",
                "Change vs No Split",
                "Selected",
            ]
        ]
    )


def run_chapter_04(
    config: AnalysisConfig,
    df_seg: pd.DataFrame,
    *,
    show_outputs: bool = True,
) -> Chapter04Result:
    """Execute, export, and validate the complete Chapter 04 stage."""

    config.prepare_output_directories()
    km_df_raw, model_geometry_profile = prepare_model_geometry(df_seg)
    body_thresholds_df, body_mask, km_df_clust, tail_candidates = (
        separate_empirical_body(km_df_raw)
    )
    sensitivity = build_boundary_sensitivity(
        km_df_raw,
        k_opt=config.k_opt,
        random_state=config.random_state,
    )

    body_thresholds_path = config.reports_dir / "kpi_empirical_body_thresholds.csv"
    sensitivity_path = config.reports_dir / "body_boundary_sensitivity_check.csv"
    body_thresholds_df.to_csv(body_thresholds_path, index=False)
    sensitivity.to_csv(sensitivity_path, index=False)

    if show_outputs:
        _show_chapter_04_outputs(
            model_geometry_profile,
            body_thresholds_df,
            km_df_raw,
            km_df_clust,
            tail_candidates,
            sensitivity,
        )

    result = Chapter04Result(
        features=MODEL_FEATURES.copy(),
        km_df_raw=km_df_raw,
        model_geometry_profile=model_geometry_profile,
        body_boundary_specs=BODY_BOUNDARY_SPECS.copy(),
        body_thresholds_df=body_thresholds_df,
        body_mask=body_mask,
        km_df_clust=km_df_clust,
        km_df_tail_candidates=tail_candidates,
        body_boundary_sensitivity=sensitivity,
        body_thresholds_path=body_thresholds_path,
        boundary_sensitivity_path=sensitivity_path,
    )
    validate_chapter_04(
        result,
        df_seg=df_seg,
        strict_project_baseline=config.strict_project_baseline,
    )
    return result
