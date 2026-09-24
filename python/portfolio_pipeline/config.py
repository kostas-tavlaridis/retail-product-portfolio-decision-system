"""Central runtime configuration for the analytical pipeline.

Only technical settings belong here: input/output locations and reproducibility
controls. Analytical rules remain inside the chapter that owns them so their
business meaning stays visible next to the executed logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PYTHON_DIR.parent


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Paths and reproducibility settings shared by the notebook and CLI."""

    input_csv: Path = PROJECT_ROOT / "clean_superstore_csv_export.csv"
    reports_dir: Path = PYTHON_DIR / "reports"
    random_state: int = 42
    k_opt: int = 4
    n_resamples: int = 100
    strict_project_baseline: bool = True

    @property
    def figures_dir(self) -> Path:
        """Return the canonical directory for exported report figures."""

        return self.reports_dir / "figures"

    def prepare_output_directories(self) -> None:
        """Create output directories without deleting or overwriting artifacts."""

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.figures_dir.mkdir(parents=True, exist_ok=True)
