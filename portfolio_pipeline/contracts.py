"""Explicit handoff objects exchanged between analytical chapters.

The original monolithic script relies on many global variables. Named chapter
results make every dependency visible and prevent a later chapter from silently
using an accidental intermediate object.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class Chapter01Result:
    """Canonical outputs of Chapter 01 — Data Foundation & Analytical Grain."""

    df: pd.DataFrame
    order_prod: pd.DataFrame
    totals: pd.DataFrame
    product_dim: pd.DataFrame
    loss_profile: pd.DataFrame
    product_stage1: pd.DataFrame


@dataclass(frozen=True, slots=True)
class Chapter02Result:
    """Canonical outputs of Chapter 02 — Structural Portfolio Diagnostics."""

    stage1_diag: dict[str, Any]
    stage1_summary_stats: pd.DataFrame
    dashboard_path: Path
    product_diagnostics_path: Path
    structural_summary_path: Path


@dataclass(frozen=True, slots=True)
class Chapter03Result:
    """Canonical outputs of Chapter 03 — KPI Specification."""

    vol: pd.DataFrame
    cv_audit: pd.DataFrame
    product_metrics: pd.DataFrame
    df_seg: pd.DataFrame
    cv_epsilon: float
    cv_cap: float


@dataclass(frozen=True, slots=True)
class Chapter04Result:
    """Canonical outputs of Chapter 04 — Body / Tail Geometry."""

    features: list[str]
    km_df_raw: pd.DataFrame
    model_geometry_profile: pd.DataFrame
    body_boundary_specs: dict[str, tuple[float, float]]
    body_thresholds_df: pd.DataFrame
    body_mask: pd.Series
    km_df_clust: pd.DataFrame
    km_df_tail_candidates: pd.DataFrame
    body_boundary_sensitivity: pd.DataFrame
    body_thresholds_path: Path
    boundary_sensitivity_path: Path


@dataclass(frozen=True, slots=True)
class Chapter05Result:
    """Canonical outputs of Chapter 05 — K-Means Structural Segmentation."""

    scaler: Any
    x_scaled: Any
    scaling_audit: pd.DataFrame
    kmeans_model_selection: pd.DataFrame
    kmeans: Any
    labels: Any
    km_df_clust: pd.DataFrame
    df_seg_clusters: pd.DataFrame
    assignment_summary: pd.DataFrame
    cluster_stability_iterations: pd.DataFrame
    cluster_stability_summary: pd.DataFrame
    cv_support_summary: pd.DataFrame
    cluster_profile: pd.DataFrame
    export_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class Chapter06Result:
    """Canonical outputs of Chapter 06 — Structural Tail Typology."""

    body: pd.DataFrame
    tail: pd.DataFrame
    cv_threshold: float
    impact_threshold: float
    loss_scale_tolerance: float
    tail_reference_table: pd.DataFrame
    tail_materiality: pd.DataFrame
    tail_entry_audit: pd.DataFrame
    mechanism_coverage_summary: pd.DataFrame
    fallback_tail_cases: pd.DataFrame
    fallback_assignment_audit: pd.DataFrame
    assignment_basis_summary: pd.DataFrame
    df_seg_clusters: pd.DataFrame
    tail_summary: pd.DataFrame
    overlap_audit: pd.DataFrame
    tail_export: pd.DataFrame
    analytical_role_profile: pd.DataFrame
    tail_export_path: Path
    analytical_role_profile_path: Path
    geometry_figure_path: Path


@dataclass(frozen=True, slots=True)
class Chapter07Result:
    """Canonical outputs of Chapter 07 — Governance Engine."""

    flow_df: pd.DataFrame
    analytical_to_action: dict[str, str]
    baseline_action_summary: pd.DataFrame
    body_ref: pd.DataFrame
    governance_references: dict[str, float]
    threshold_export: pd.DataFrame
    body_instability: pd.DataFrame
    deterioration_specs: pd.DataFrame
    signal_summary: pd.DataFrame
    escalation_summary: pd.DataFrame
    threshold_export_path: Path
    signal_summary_path: Path


@dataclass(frozen=True, slots=True)
class Chapter08Result:
    """Canonical outputs of Chapter 08 — Final Intervention."""

    flow_df: pd.DataFrame
    final_intervention_map: dict[tuple[str, str], str]
    coverage_audit: pd.DataFrame
    final_intervention_summary: pd.DataFrame
    governance_flow_table: pd.DataFrame
    governance_scorecard: pd.DataFrame
    governance_pressure_scorecard_pct: pd.DataFrame
    governance_scorecard_sensitivity: pd.DataFrame
    governance_flow_path: Path
    final_intervention_summary_path: Path
    intervention_distribution_path: Path
    governance_pressure_path: Path
    governance_sensitivity_path: Path


@dataclass(frozen=True, slots=True)
class Chapter09Result:
    """Canonical outputs of Chapter 09 — Economic Priority Layer."""

    flow_df: pd.DataFrame
    role_perf_ref: pd.DataFrame
    reliability_guards: pd.DataFrame
    priority_zone_meta: dict[str, dict[str, object]]
    priority_zone_summary: pd.DataFrame
    priority_scope_summary: pd.DataFrame
    opportunity_quality_summary: pd.DataFrame
    priority_product_decisions: pd.DataFrame
    hidden_opportunity_sensitivity: pd.DataFrame
    opportunity_sensitivity_summary: pd.DataFrame
    manager_view: pd.DataFrame
    priority_zone_summary_path: Path
    priority_product_decisions_path: Path
    opportunity_quality_summary_path: Path
    hidden_opportunity_sensitivity_path: Path
    governance_output_path: Path
