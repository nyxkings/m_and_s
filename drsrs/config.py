"""Configuration loading utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SensitivityConfig:
    k1_values: list[int] = field(default_factory=lambda: [1, 2, 3, 4])
    k2_values: list[int] = field(default_factory=lambda: [0, 1, 2])
    lambda_d_values: list[float] = field(default_factory=lambda: [0.01, 0.05, 0.10, 0.20])
    n_trials_sensitivity: int = 200


@dataclass
class VerificationConfig:
    n_trials: int = 500
    sim_years: float = 2.0


@dataclass
class PathsConfig:
    figures: str = "outputs/figures"
    tables: str = "outputs/tables"
    reports: str = "outputs/reports"
    data: str = "data"


@dataclass
class DRSRSConfig:
    """Full DRSRS simulation configuration (report Table 3.2 + Chapter 4)."""

    seed: int = 42
    n_shards: int = 16
    k1_campus_replicas: int = 2
    k_regional_replicas: int = 1
    k2_cloud_replicas: int = 1
    coordinator_nodes: int = 3
    mttf_hours: float = 2000.0
    mttr_hours: float = 2.0
    a_network: float = 0.9995
    a_app: float = 0.9990
    disaster_rate_per_year: float = 0.05
    disaster_duration_mean_hours: float = 48.0
    p2_cloud_annual: float = 1.0e-4
    p1_analytic: float = 1.0e-3
    lambda_req_per_s: float = 50.0
    mu_per_thread: float = 20.0
    threads_per_replica: int = 4
    slo_latency_ms: float = 200.0
    sim_years: float = 5.0
    n_trials: int = 1000
    availability_sample_hours: float = 1.0
    sensitivity: SensitivityConfig = field(default_factory=SensitivityConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    @property
    def hours_per_year(self) -> float:
        return 8760.0

    @property
    def sim_horizon_hours(self) -> float:
        return self.sim_years * self.hours_per_year

    @property
    def disaster_rate_per_hour(self) -> float:
        return self.disaster_rate_per_year / self.hours_per_year

    @property
    def node_availability(self) -> float:
        """A = MTTF / (MTTF + MTTR) — Section 4.1."""
        return self.mttf_hours / (self.mttf_hours + self.mttr_hours)

    @property
    def total_replicas_per_shard(self) -> int:
        return (
            self.k1_campus_replicas
            + self.k_regional_replicas
            + self.k2_cloud_replicas
        )

    def ensure_dirs(self, root: Path) -> None:
        for rel in (
            self.paths.figures,
            self.paths.tables,
            self.paths.reports,
            self.paths.data,
        ):
            (root / rel).mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path | None = None) -> DRSRSConfig:
    """Load YAML config into a typed DRSRSConfig dataclass."""
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "default.yaml"
    path = Path(path)
    raw: dict[str, Any] = {}
    if path.exists():
        with path.open() as f:
            raw = yaml.safe_load(f) or {}

    sens_raw = raw.pop("sensitivity", {}) or {}
    ver_raw = raw.pop("verification", {}) or {}
    paths_raw = raw.pop("paths", {}) or {}

    return DRSRSConfig(
        **{k: v for k, v in raw.items() if k in DRSRSConfig.__dataclass_fields__},
        sensitivity=SensitivityConfig(**sens_raw),
        verification=VerificationConfig(**ver_raw),
        paths=PathsConfig(**paths_raw),
    )
