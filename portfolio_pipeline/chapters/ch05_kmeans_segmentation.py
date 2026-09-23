"""Chapter 05 — K-Means Structural Segmentation.

Purpose
-------
Standardize the Chapter 04 portfolio body, select and fit the documented K=4
model, stress-test assignment stability, and translate the four numerical
clusters into economically interpretable body roles.

The structural tail remains explicitly unclustered. It is carried forward to
Chapter 06, where body-anchored rules construct the three tail regimes.

K-means solves ``argmin Σ||x_i - μ_{c(i)}||²`` in the standardized four-KPI
space. Numeric cluster IDs have no intrinsic business meaning; role names are a
post-fit interpretation that must be checked against the profile whenever the
model is re-estimated. The fixed random seed and 20 initializations make the
selected local solution reproducible.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

try:
    from IPython.display import display as _display
except ImportError:  # pragma: no cover
    def _display(value: object) -> None:
        print(value)

from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.contracts import Chapter04Result, Chapter05Result
from portfolio_pipeline.validation import validate_chapter_05


BODY_ROLE_MAP = {
    0: "Stable Profit Cluster",
    2: "High-Impact Profit Cluster",
    3: "Risk-Oriented Profit Cluster",
    1: "Stable Loss Cluster",
    "Unclustered": np.nan,
}

BODY_ROLE_ORDER = [
    "Stable Profit Cluster",
    "High-Impact Profit Cluster",
    "Risk-Oriented Profit Cluster",
    "Stable Loss Cluster",
]


def scale_clusterable_body(
    km_df_clust: pd.DataFrame,
    features: list[str],
) -> tuple[StandardScaler, np.ndarray, pd.DataFrame]:
    """Standardize the four KPIs used by Euclidean K-means distance.

    StandardScaler applies z = (x - mean) / population_std on the selected body.
    Without it, the KPI with the largest numeric range would dominate distance.
    Scaling balances units; it does not make extreme observations harmless,
    which is why Chapter 04 performs body/tail separation first.
    """

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(km_df_clust[features])
    scaling_audit = pd.DataFrame(
        {
            "Feature": features,
            "Raw Mean": km_df_clust[features].mean().values,
            "Raw Std": km_df_clust[features].std(ddof=0).values,
            "Scaled Mean": x_scaled.mean(axis=0),
            "Scaled Std": x_scaled.std(axis=0, ddof=0),
        }
    )
    return scaler, x_scaled, scaling_audit


def build_model_selection(
    x_scaled: np.ndarray,
    *,
    k_opt: int,
    random_state: int,
) -> pd.DataFrame:
    """Compare K=1–8 through inertia and silhouette on one fixed body.

    Inertia is the within-cluster sum of squared distances and must decrease as
    K grows; the elbow identifies diminishing compactness gains. For K>1,
    silhouette uses s(i)=(b(i)-a(i))/max(a(i),b(i)), where a is within-cluster
    distance and b is distance to the nearest alternative cluster. K=1 has no
    alternative group, so its silhouette is correctly undefined.
    """

    selection_rows: list[dict[str, object]] = []
    for candidate_k in range(1, 9):
        candidate_model = KMeans(
            n_clusters=candidate_k,
            random_state=random_state,
            n_init=20,
        )
        candidate_labels = candidate_model.fit_predict(x_scaled)
        candidate_silhouette = (
            silhouette_score(x_scaled, candidate_labels)
            if candidate_k > 1
            else np.nan
        )
        selection_rows.append(
            {
                "K": candidate_k,
                "inertia": candidate_model.inertia_,
                "silhouette_score": candidate_silhouette,
                "selected_k": candidate_k == k_opt,
            }
        )
    return pd.DataFrame(selection_rows)


def fit_final_model(
    df_seg: pd.DataFrame,
    km_df_clust: pd.DataFrame,
    x_scaled: np.ndarray,
    *,
    k_opt: int,
    random_state: int,
) -> tuple[KMeans, np.ndarray, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit K=4 and restore assignments to the complete product universe.

    Labels are attached by the preserved analytical index.  Products excluded
    from centroid modelling are marked ``Unclustered`` rather than lost; this is
    an explicit hand-off to Chapter 06, not a missing classification.
    """

    kmeans = KMeans(
        n_clusters=k_opt,
        random_state=random_state,
        n_init=20,
    )
    labels = kmeans.fit_predict(x_scaled)

    assigned_body = km_df_clust.copy()
    assigned_body["k_cluster"] = labels
    df_seg_clusters = df_seg.join(assigned_body[["k_cluster"]], how="left")
    df_seg_clusters["k_cluster"] = (
        df_seg_clusters["k_cluster"].astype("Int64").astype("object")
    )
    df_seg_clusters.loc[
        df_seg_clusters["k_cluster"].isna(),
        "k_cluster",
    ] = "Unclustered"

    assignment_summary = (
        df_seg_clusters["k_cluster"]
        .value_counts(dropna=False)
        .rename_axis("k_cluster")
        .reset_index(name="n_products")
    )
    assignment_summary["portfolio_share"] = (
        assignment_summary["n_products"] / len(df_seg_clusters)
    )
    return kmeans, labels, assigned_body, df_seg_clusters, assignment_summary


def evaluate_cluster_stability(
    df_seg: pd.DataFrame,
    km_df_clust: pd.DataFrame,
    x_scaled: np.ndarray,
    labels: np.ndarray,
    features: list[str],
    *,
    k_opt: int,
    n_iterations: int,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run repeated 80% resampling and non-estimable-CV sensitivity.

    Each of 100 samples is independently rescaled and refitted. Adjusted Rand
    Index compares partitions while correcting for chance and ignoring numeric
    label switching; silhouette checks whether geometric separation survives.
    The second test removes only products whose CV cannot be estimated and
    records their profit share, isolating the effect of the neutral CV coordinate.
    P05/P95 are the 5th/95th percentiles across repetitions, not the fifth
    lowest/highest individual observations.
    """

    # Re-sampling without replacement preserves an 80% product body in each
    # repetition while allowing the composition to vary.
    sample_fraction = 0.80
    stability_rows: list[dict[str, object]] = []
    rng = np.random.default_rng(random_state)

    for iteration in range(1, n_iterations + 1):
        sample_index = rng.choice(
            km_df_clust.index.to_numpy(),
            size=int(len(km_df_clust) * sample_fraction),
            replace=False,
        )
        sample_body = km_df_clust.loc[
            sample_index,
            features + ["k_cluster"],
        ].copy()
        # Refit the scaler inside every sample to reproduce a complete model
        # refit rather than leaking baseline means/variances into validation.
        sample_scaled = StandardScaler().fit_transform(sample_body[features])
        sample_model = KMeans(
            n_clusters=k_opt,
            random_state=random_state + iteration,
            n_init=20,
        )
        sample_labels = sample_model.fit_predict(sample_scaled)
        stability_rows.append(
            {
                "iteration": iteration,
                "sample_fraction": sample_fraction,
                "sample_products": len(sample_body),
                "adjusted_rand_index": adjusted_rand_score(
                    sample_body["k_cluster"],
                    sample_labels,
                ),
                "silhouette_score": silhouette_score(sample_scaled, sample_labels),
            }
        )

    iterations = pd.DataFrame(stability_rows)
    summary = pd.DataFrame(
        {
            "Metric": ["Adjusted Rand Index", "Silhouette Score"],
            "Median": [
                iterations["adjusted_rand_index"].median(),
                iterations["silhouette_score"].median(),
            ],
            "P05": [
                iterations["adjusted_rand_index"].quantile(0.05),
                iterations["silhouette_score"].quantile(0.05),
            ],
            "P95": [
                iterations["adjusted_rand_index"].quantile(0.95),
                iterations["silhouette_score"].quantile(0.95),
            ],
        }
    )
    summary["Verdict"] = [
        "Very stable" if summary.loc[0, "Median"] >= 0.90 else "Review required",
        "Separation remains consistent",
    ]

    # The baseline body definition is held constant; only statistical CV support
    # changes.  This prevents the sensitivity from mixing two specifications.
    cv_support_mask = ~df_seg.loc[
        km_df_clust.index,
        "cv_not_estimable",
    ].astype(bool)
    cv_support_body = km_df_clust.loc[
        cv_support_mask,
        features + ["k_cluster"],
    ].copy()
    cv_support_scaled = StandardScaler().fit_transform(cv_support_body[features])
    cv_support_model = KMeans(
        n_clusters=k_opt,
        random_state=random_state,
        n_init=20,
    )
    cv_support_labels = cv_support_model.fit_predict(cv_support_scaled)
    cv_support_summary = pd.DataFrame(
        {
            "baseline_body_products": [len(km_df_clust)],
            "excluded_non_estimable_cv_products": [int((~cv_support_mask).sum())],
            "sensitivity_body_products": [len(cv_support_body)],
            "baseline_silhouette_k4": [silhouette_score(x_scaled, labels)],
            "sensitivity_silhouette_k4": [
                silhouette_score(cv_support_scaled, cv_support_labels)
            ],
            "adjusted_rand_index_vs_baseline": [
                adjusted_rand_score(cv_support_body["k_cluster"], cv_support_labels)
            ],
            "excluded_profit_share_pct": [
                100
                * df_seg.loc[
                    cv_support_mask.index[~cv_support_mask],
                    "total_profit",
                ].sum()
                / df_seg["total_profit"].sum()
            ],
        }
    )
    return iterations, summary, cv_support_summary


def profile_body_roles(df_seg_clusters: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map numeric clusters to four documented economic body roles.

    Profiles are computed in original KPI units after fitting. This translation
    makes the geometry interpretable but does not become the governance engine:
    Chapter 06 first combines body roles with structural-tail regimes, and only
    Chapter 07 maps the resulting seven roles to actions.
    """

    df_seg_clusters = df_seg_clusters.copy()
    df_seg_clusters["body_role"] = df_seg_clusters["k_cluster"].map(BODY_ROLE_MAP)
    unmapped_body = df_seg_clusters.loc[
        df_seg_clusters["k_cluster"].ne("Unclustered")
        & df_seg_clusters["body_role"].isna()
    ]
    if not unmapped_body.empty:
        raise ValueError("At least one K-means body cluster has no role mapping.")

    cluster_profile = (
        df_seg_clusters.loc[df_seg_clusters["k_cluster"].ne("Unclustered")]
        .groupby(["k_cluster", "body_role"], as_index=False)
        .agg(
            n_products=("product_id", "size"),
            total_profit=("total_profit", "sum"),
            mean_order_profit=("mean_order_profit", "mean"),
            median_cv=("cv_order_profit", "median"),
            mean_loss_rate=("pct_orders_loss", "mean"),
            mean_profit_scale=("profit_scale", "mean"),
        )
    )
    cluster_profile["pct_products"] = (
        100 * cluster_profile["n_products"] / len(df_seg_clusters)
    )
    cluster_profile["pct_net_profit"] = (
        100 * cluster_profile["total_profit"] / df_seg_clusters["total_profit"].sum()
    )
    cluster_profile["body_role"] = pd.Categorical(
        cluster_profile["body_role"],
        categories=BODY_ROLE_ORDER,
        ordered=True,
    )
    cluster_profile = cluster_profile.sort_values("body_role").reset_index(drop=True)
    return df_seg_clusters, cluster_profile


def _show_model_selection_plot(
    model_selection: pd.DataFrame,
    *,
    k_opt: int,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    axes[0].plot(
        model_selection["K"],
        model_selection["inertia"],
        marker="o",
        color="#244e7a",
    )
    axes[0].axvline(k_opt, color="#4f9c70", linestyle="--", linewidth=1.4)
    axes[0].set_title("Elbow — Within-Group Distance")
    axes[0].set_xlabel("Number of clusters (K)")
    axes[0].set_ylabel("Inertia")
    axes[0].grid(alpha=0.25)

    silhouette_view = model_selection.dropna(subset=["silhouette_score"])
    axes[1].plot(
        silhouette_view["K"],
        silhouette_view["silhouette_score"],
        marker="o",
        color="#8a5a9f",
    )
    axes[1].axvline(k_opt, color="#4f9c70", linestyle="--", linewidth=1.4)
    axes[1].set_title("Silhouette — Group Separation")
    axes[1].set_xlabel("Number of clusters (K)")
    axes[1].set_ylabel("Silhouette score")
    axes[1].grid(alpha=0.25)
    plt.tight_layout()
    plt.show()


def _show_chapter_05_outputs(result: Chapter05Result, *, show_plot: bool) -> None:
    print("\n=== SCALING AUDIT — CLUSTERABLE BODY ===")
    _display(result.scaling_audit.round(4))
    print("\n=== K-MEANS MODEL-SELECTION EVIDENCE ===")
    _display(result.kmeans_model_selection.round({"inertia": 1, "silhouette_score": 3}))
    if show_plot:
        _show_model_selection_plot(result.kmeans_model_selection, k_opt=4)

    print("\n=== FINAL K-MEANS ASSIGNMENT SUMMARY ===")
    _display(
        result.assignment_summary.assign(
            portfolio_share=result.assignment_summary["portfolio_share"].map(
                lambda value: f"{value:.1%}"
            )
        )
    )
    print("\n=== RESAMPLING STABILITY ===")
    _display(result.cluster_stability_summary.round(3))
    print("\n=== NON-ESTIMABLE-CV SUPPORT SENSITIVITY ===")
    _display(result.cv_support_summary.round(3))

    view = result.cluster_profile.copy()
    view["Portfolio Footprint"] = view["pct_products"].map(lambda value: f"{value:.1f}%")
    view["Net Profit Share"] = view["pct_net_profit"].map(lambda value: f"{value:.1f}%")
    view["Total Profit"] = view["total_profit"].map(lambda value: f"{value:,.2f}")
    view["Mean Order Profit"] = view["mean_order_profit"].map(lambda value: f"{value:,.2f}")
    view["Median CV"] = view["median_cv"].map(lambda value: f"{value:.2f}")
    view["Mean Loss Rate"] = view["mean_loss_rate"].map(lambda value: f"{value:.1%}")
    print("\n=== K-MEANS BODY ROLE PROFILE ===")
    _display(
        view[
            [
                "body_role",
                "k_cluster",
                "n_products",
                "Portfolio Footprint",
                "Total Profit",
                "Net Profit Share",
                "Mean Order Profit",
                "Median CV",
                "Mean Loss Rate",
            ]
        ].rename(
            columns={
                "body_role": "Economic Role",
                "k_cluster": "Cluster",
                "n_products": "Products",
            }
        )
    )


def run_chapter_05(
    config: AnalysisConfig,
    df_seg: pd.DataFrame,
    chapter_04: Chapter04Result,
    *,
    show_outputs: bool = True,
) -> Chapter05Result:
    """Execute, export, and validate the complete Chapter 05 stage."""

    config.prepare_output_directories()
    scaler, x_scaled, scaling_audit = scale_clusterable_body(
        chapter_04.km_df_clust,
        chapter_04.features,
    )
    model_selection = build_model_selection(
        x_scaled,
        k_opt=config.k_opt,
        random_state=config.random_state,
    )
    kmeans, labels, assigned_body, df_seg_clusters, assignment_summary = fit_final_model(
        df_seg,
        chapter_04.km_df_clust,
        x_scaled,
        k_opt=config.k_opt,
        random_state=config.random_state,
    )
    stability_iterations, stability_summary, cv_support_summary = (
        evaluate_cluster_stability(
            df_seg,
            assigned_body,
            x_scaled,
            labels,
            chapter_04.features,
            k_opt=config.k_opt,
            n_iterations=config.n_resamples,
            random_state=config.random_state,
        )
    )
    df_seg_clusters, cluster_profile = profile_body_roles(df_seg_clusters)

    export_paths = (
        config.reports_dir / "kmeans_model_selection.csv",
        config.reports_dir / "cluster_stability_iterations.csv",
        config.reports_dir / "cluster_stability_summary.csv",
        config.reports_dir / "cv_support_clustering_sensitivity_summary.csv",
        config.reports_dir / "kmeans_cluster_profile.csv",
    )
    model_selection.to_csv(export_paths[0], index=False)
    stability_iterations.to_csv(export_paths[1], index=False)
    stability_summary.to_csv(export_paths[2], index=False)
    cv_support_summary.to_csv(export_paths[3], index=False)
    cluster_profile.to_csv(export_paths[4], index=False)

    result = Chapter05Result(
        scaler=scaler,
        x_scaled=x_scaled,
        scaling_audit=scaling_audit,
        kmeans_model_selection=model_selection,
        kmeans=kmeans,
        labels=labels,
        km_df_clust=assigned_body,
        df_seg_clusters=df_seg_clusters,
        assignment_summary=assignment_summary,
        cluster_stability_iterations=stability_iterations,
        cluster_stability_summary=stability_summary,
        cv_support_summary=cv_support_summary,
        cluster_profile=cluster_profile,
        export_paths=export_paths,
    )
    validate_chapter_05(
        result,
        df_seg=df_seg,
        strict_project_baseline=config.strict_project_baseline,
    )
    if show_outputs:
        _show_chapter_05_outputs(result, show_plot=True)
    return result
