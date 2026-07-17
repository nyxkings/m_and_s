"""Verification & validation against closed-form models (Section 4.9)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from drsrs.config import DRSRSConfig
from drsrs.models import (
    node_availability,
    quorum_availability,
    shard_availability,
)
from drsrs.simulation import run_monte_carlo

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    analytical: float
    simulated: float
    abs_error: float
    rel_error: float
    passed: bool
    tolerance: float
    notes: str = ""


def _rel_err(analytical: float, simulated: float) -> float:
    if analytical == 0:
        return abs(simulated)
    return abs(simulated - analytical) / abs(analytical)


def verify_single_node(cfg: DRSRSConfig) -> CheckResult:
    """Limiting case k1=1, k2=0, λ_d=0 → availability → A = MTTF/(MTTF+MTTR)."""
    from dataclasses import replace

    a = node_availability(cfg.mttf_hours, cfg.mttr_hours)
    vcfg = replace(
        cfg,
        n_shards=1,
        k1_campus_replicas=1,
        k_regional_replicas=0,
        k2_cloud_replicas=0,
        disaster_rate_per_year=0.0,
        sim_years=cfg.verification.sim_years,
        n_trials=cfg.verification.n_trials,
        p2_cloud_annual=0.0,
    )
    mc = run_monte_carlo(
        vcfg,
        n_trials=vcfg.n_trials,
        sample_requests=False,
        progress_every=100,
        seed=cfg.seed + 1,
    )
    sim_a = float(np.mean([t.availability for t in mc.trials]))
    tol = 0.002  # 0.2% absolute for 500×2yr trials
    err = abs(sim_a - a)
    return CheckResult(
        name="Single-node availability (k1=1, λ_d=0)",
        analytical=a,
        simulated=sim_a,
        abs_error=err,
        rel_error=_rel_err(a, sim_a),
        passed=err <= tol,
        tolerance=tol,
        notes="Section 4.9.1 limiting case",
    )


def verify_independent_replicas(cfg: DRSRSConfig, k: int = 3) -> CheckResult:
    """Disaster-free k independent replicas → A_shard = 1−(1−A)^k."""
    from dataclasses import replace

    a = node_availability(cfg.mttf_hours, cfg.mttr_hours)
    a_sh = shard_availability(a, k)
    vcfg = replace(
        cfg,
        n_shards=1,
        k1_campus_replicas=k,
        k_regional_replicas=0,
        k2_cloud_replicas=0,
        disaster_rate_per_year=0.0,
        sim_years=cfg.verification.sim_years,
        n_trials=cfg.verification.n_trials,
        p2_cloud_annual=0.0,
    )
    mc = run_monte_carlo(
        vcfg,
        n_trials=vcfg.n_trials,
        sample_requests=False,
        progress_every=100,
        seed=cfg.seed + 2,
    )
    # Per-shard availability (only one shard)
    sim_a = float(np.mean([t.shard_availability_mean for t in mc.trials]))
    # Unavailability is tiny; use relative error on downtime
    a_down = 1.0 - a_sh
    s_down = 1.0 - sim_a
    # Absolute tolerance on availability itself
    tol = 5e-4
    err = abs(sim_a - a_sh)
    return CheckResult(
        name=f"Independent {k}-replica shard availability (λ_d=0)",
        analytical=a_sh,
        simulated=sim_a,
        abs_error=err,
        rel_error=_rel_err(a_sh, sim_a),
        passed=err <= tol or _rel_err(a_down, s_down) <= 0.5,
        tolerance=tol,
        notes="Section 4.9.1 / Eq. A_shard = 1−(1−A)^k",
    )


def verify_quorum_formula(cfg: DRSRSConfig) -> CheckResult:
    """Closed-form quorum check (no DES needed) against worked example."""
    # Worked example: n=3, A=0.99 → ≈0.9997
    a_ex = 0.99
    analytical = quorum_availability(a_ex, 3)
    expected = 0.999703  # from report ≈0.9997
    err = abs(analytical - expected)
    return CheckResult(
        name="Quorum formula (n=3, A=0.99) vs worked example",
        analytical=expected,
        simulated=analytical,  # "simulated" = computed formula
        abs_error=err,
        rel_error=_rel_err(expected, analytical),
        passed=err < 1e-4,
        tolerance=1e-4,
        notes="Section 4.4 worked example",
    )


def verify_node_formula(cfg: DRSRSConfig) -> CheckResult:
    a = node_availability(2000.0, 2.0)
    expected = 2000.0 / 2002.0
    err = abs(a - expected)
    return CheckResult(
        name="Node availability formula MTTF=2000, MTTR=2",
        analytical=expected,
        simulated=a,
        abs_error=err,
        rel_error=_rel_err(expected, a),
        passed=err < 1e-12,
        tolerance=1e-12,
        notes="Section 4.1 worked example",
    )


def run_all_verifications(cfg: DRSRSConfig) -> list[CheckResult]:
    logger.info("Running verification suite (Section 4.9)...")
    checks = [
        verify_node_formula(cfg),
        verify_quorum_formula(cfg),
        verify_single_node(cfg),
        verify_independent_replicas(cfg, k=3),
    ]
    for c in checks:
        status = "PASS" if c.passed else "FAIL"
        logger.info(
            "[%s] %s: analytical=%.8g sim=%.8g abs_err=%.3g",
            status,
            c.name,
            c.analytical,
            c.simulated,
            c.abs_error,
        )
    return checks
