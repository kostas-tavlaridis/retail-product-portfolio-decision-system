"""Command-line entry point for the complete product-portfolio decision system.

Panoramic architecture
----------------------
The project translates transaction-level evidence into one deterministic,
auditable decision record per analytical product.  The implementation is split
into nine chapter modules, but it remains one ordered pipeline with three linked
methodological layers:

1. Diagnostics establish structural reality (Chapters 01–03).  They lock the
   analytical grain, reconcile the economics, test concentration/asymmetry and
   express product behaviour through four governed KPIs.
2. Geometry formalizes portfolio structure (Chapters 04–06).  It separates the
   recurring body from structural extremes, fits K-means only where centroid
   geometry is appropriate, and closes the result into seven economic roles.
3. Governance converts structure into management decisions (Chapters 07–09).
   It combines role-owned actions with independent control signals, resolves
   escalation, assigns one final intervention and then creates a narrower
   role-relative priority queue without overwriting governance.

Execution contract
------------------
``run_analysis.py`` is orchestration only: it owns configuration, chapter order,
explicit hand-offs and the final checkpoint.  Analytical formulas and business
rules remain in the chapter that owns their meaning.  Each stage returns a
typed result contract, writes its documented audit artifacts and is validated
before the next stage consumes it.  This makes the modular code equivalent to
the final notebook while avoiding the hidden global state of the former
monolithic script.

The active source deliberately stops at Chapter 09.  Chapter 10 is the report's
claim/deployment boundary rather than a computational stage, and the deferred
Power BI integration is not part of this Python execution path.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# Numerical libraries may initialize their worker pools at import time.  These
# controls must therefore be applied before importing any chapter that loads
# NumPy/scikit-learn; they reproduce the notebook's bounded, deterministic
# runtime footprint and do not alter the analytical specification.
os.environ["LOKY_MAX_CPU_COUNT"] = "6"
os.environ["OMP_NUM_THREADS"] = "6"
os.environ["MKL_NUM_THREADS"] = "6"

from portfolio_pipeline.chapters.ch01_data_foundation import run_chapter_01
from portfolio_pipeline.chapters.ch02_structural_diagnostics import run_chapter_02
from portfolio_pipeline.chapters.ch03_kpi_specification import run_chapter_03
from portfolio_pipeline.chapters.ch04_body_tail_geometry import run_chapter_04
from portfolio_pipeline.chapters.ch05_kmeans_segmentation import run_chapter_05
from portfolio_pipeline.chapters.ch06_tail_typology import run_chapter_06
from portfolio_pipeline.chapters.ch07_governance_engine import run_chapter_07
from portfolio_pipeline.chapters.ch08_final_intervention import run_chapter_08
from portfolio_pipeline.chapters.ch09_economic_priority import run_chapter_09
from portfolio_pipeline.config import AnalysisConfig
from portfolio_pipeline.validation import (
    validate_chapter_01,
    validate_chapter_02,
    validate_chapter_03,
    validate_chapter_04,
    validate_chapter_05,
    validate_chapter_06,
    validate_chapter_07,
    validate_chapter_08,
    validate_chapter_09,
)


def _parse_args() -> argparse.Namespace:
    """Expose only runtime concerns; analytical thresholds stay chapter-owned."""

    parser = argparse.ArgumentParser(
        description="Run the modular Superstore product portfolio analysis."
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=AnalysisConfig().input_csv,
        help="Path to the SQL-cleaned Superstore CSV export.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=AnalysisConfig().reports_dir,
        help="Directory used by chapter exports.",
    )
    parser.add_argument(
        "--allow-alternative-data",
        action="store_true",
        help="Keep structural checks but disable fixed Superstore baseline counts.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Export figures and tables without opening interactive previews.",
    )
    return parser.parse_args()


def main() -> None:
    """Execute the nine validated stages in dependency order.

    Dataframes are passed in memory between result contracts.  No intermediate
    pickle is required: persistent CSV/figure/workbook outputs are audit and
    reporting artifacts, not a second source of pipeline state.
    """

    # ---------------------------------------------------------------------
    # RUNTIME CONFIGURATION
    # ---------------------------------------------------------------------
    # Strict mode checks both universal invariants (schema, coverage, finite
    # values, closed mappings) and the fixed Superstore reference counts.  The
    # alternative-data flag retains the former while disabling only the latter.
    args = _parse_args()
    config = AnalysisConfig(
        input_csv=args.input_csv,
        reports_dir=args.reports_dir,
        strict_project_baseline=not args.allow_alternative_data,
    )
    config.prepare_output_directories()

    show_outputs = not args.no_show

    # ---------------------------------------------------------------------
    # DIAGNOSTIC LAYER — Chapters 01–03
    # ---------------------------------------------------------------------
    # Ch01 restores pandas types from the SQL-cleaned CSV and establishes two
    # non-interchangeable grains: order x product for behavioural evidence and
    # product ID x product name for all product-level decisions.
    chapter_01 = run_chapter_01(
        config,
        show_reconciliation=True,
        show_preview=show_outputs,
    )
    chapter_01_checks = validate_chapter_01(
        chapter_01,
        strict_project_baseline=config.strict_project_baseline,
    )

    # Ch02 is a descriptive validation gate.  It tests whether concentration,
    # asymmetry, category dispersion and downside exposure justify modelling;
    # it never assigns a cluster or action.
    chapter_02 = run_chapter_02(
        config,
        chapter_01.product_stage1,
        show_dashboard=show_outputs,
        show_summary=show_outputs,
    )
    chapter_02_checks = validate_chapter_02(
        chapter_02,
        product_stage1=chapter_01.product_stage1,
        strict_project_baseline=config.strict_project_baseline,
    )

    # Ch03 intentionally returns to Ch01 rather than consuming a chart-oriented
    # Ch02 table.  It builds the governed four-KPI coordinate system directly
    # from canonical order-product observations and reconciled totals.
    chapter_03 = run_chapter_03(
        config,
        chapter_01.order_prod,
        chapter_01.totals,
        show_audit=show_outputs,
        show_preview=show_outputs,
    )
    chapter_03_checks = validate_chapter_03(
        chapter_03,
        order_prod=chapter_01.order_prod,
        totals=chapter_01.totals,
        strict_project_baseline=config.strict_project_baseline,
    )

    # ---------------------------------------------------------------------
    # GEOMETRY LAYER — Chapters 04–06
    # ---------------------------------------------------------------------
    # Ch04 identifies the recurring empirical body.  Tail rows remain present:
    # the split selects the appropriate modelling mechanism, not valid/invalid
    # observations.
    chapter_04 = run_chapter_04(
        config,
        chapter_03.df_seg,
        show_outputs=show_outputs,
    )
    chapter_04_checks = validate_chapter_04(
        chapter_04,
        df_seg=chapter_03.df_seg,
        strict_project_baseline=config.strict_project_baseline,
    )

    # Ch05 standardizes the body, fits the documented K=4 solution and tests
    # whether assignments survive resampling and removal of unsupported CVs.
    chapter_05 = run_chapter_05(
        config,
        chapter_03.df_seg,
        chapter_04,
        show_outputs=show_outputs,
    )
    chapter_05_checks = validate_chapter_05(
        chapter_05,
        df_seg=chapter_03.df_seg,
        strict_project_baseline=config.strict_project_baseline,
    )

    # Ch06 interprets the four numeric body clusters and classifies structural
    # extremes with body-anchored rules, yielding one closed seven-role system.
    chapter_06 = run_chapter_06(
        config,
        chapter_04,
        chapter_05,
        show_outputs=show_outputs,
    )
    chapter_06_checks = validate_chapter_06(
        chapter_06,
        strict_project_baseline=config.strict_project_baseline,
    )

    # ---------------------------------------------------------------------
    # GOVERNANCE & PRIORITY LAYER — Chapters 07–09
    # ---------------------------------------------------------------------
    # Ch07 maps role to baseline action, evaluates four independent signals and
    # applies precedence so overlapping evidence becomes one escalation state.
    chapter_07 = run_chapter_07(
        config,
        chapter_05,
        chapter_06,
        show_outputs=show_outputs,
    )
    chapter_07_checks = validate_chapter_07(
        chapter_07,
        chapter_06=chapter_06,
        strict_project_baseline=config.strict_project_baseline,
    )

    # Ch08 closes the 4 x 4 action/escalation routing matrix, creates the
    # executive scorecard and stress-tests governance calibration.
    chapter_08 = run_chapter_08(
        config,
        chapter_07,
        show_outputs=show_outputs,
    )
    chapter_08_checks = validate_chapter_08(
        chapter_08,
        chapter_07=chapter_07,
        strict_project_baseline=config.strict_project_baseline,
    )

    # Ch09 adds a separate role-relative attention lens.  Priority narrows the
    # management queue; it does not modify any Chapter 08 intervention.
    chapter_09 = run_chapter_09(
        config,
        chapter_08,
        show_outputs=show_outputs,
    )
    chapter_09_checks = validate_chapter_09(
        chapter_09,
        chapter_08=chapter_08,
        strict_project_baseline=config.strict_project_baseline,
    )

    # ---------------------------------------------------------------------
    # FINAL CROSS-CHAPTER CHECKPOINT
    # ---------------------------------------------------------------------
    # Reaching this block means every chapter-level contract and invariant has
    # passed.  The values below are a compact operational fingerprint, not a
    # substitute for the detailed audit artifacts written by each stage.
    print("\n=== MODULAR PIPELINE CHECKPOINT ===")
    print("Chapter 01 — Data Foundation & Analytical Grain: PASS")
    print("Chapter 02 — Structural Portfolio Diagnostics: PASS")
    print("Chapter 03 — KPI Specification: PASS")
    print("Chapter 04 — Body / Tail Geometry: PASS")
    print("Chapter 05 — K-Means Structural Segmentation: PASS")
    print("Chapter 06 — Structural Tail Typology: PASS")
    print("Chapter 07 — Governance Engine: PASS")
    print("Chapter 08 — Final Intervention: PASS")
    print("Chapter 09 — Economic Priority Layer: PASS")
    print(f"Product universe: {chapter_01_checks['product_pairs']:,}")
    print(f"Pareto 80% threshold: {chapter_02_checks['pareto_80_count']:,} products")
    print(f"CV epsilon: {chapter_03_checks['cv_epsilon']:.4f}")
    print(f"CV cap: {chapter_03_checks['cv_cap']:.4f}")
    print(
        "Body / structural tail: "
        f"{chapter_04_checks['body_products']:,} / "
        f"{chapter_04_checks['tail_products']:,}"
    )
    print(f"Body roles: {chapter_05_checks['body_roles']}")
    print(f"Unified analytical roles: {chapter_06_checks['analytical_roles']}")
    print(
        "Hard exposure: "
        f"{chapter_07_checks['hard_exposure_products']:,} products "
        f"({chapter_08_checks['hard_exposure_share']:.1%})"
    )
    print(
        "Active priority scope: "
        f"{chapter_09_checks['active_priority_products']:,} products"
    )
    print(
        "Routine / neutral scope: "
        f"{chapter_09_checks['routine_neutral_products']:,} products"
    )
    print("Pipeline migration complete through Chapter 09")


if __name__ == "__main__":
    main()
