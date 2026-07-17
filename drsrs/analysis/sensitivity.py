"""Sensitivity analysis over k1, k2, and λ_d (Section 4.8.4)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from drsrs.config import DRSRSConfig
from drsrs.models import data_loss_correlated, node_availability, shard_availability
from drsrs.simulation import run_monte_carlo

logger = logging.getLogger(__name__)


@dataclass
class SensitivityTables:
    by_k1_k2: pd.DataFrame
    by_lambda_d: pd.DataFrame
    analytical_loss: pd.DataFrame


def run_sensitivity(cfg: DRSRSConfig) -> SensitivityTables:
    """Sweep k1, k2, λ_d and collect availability / data-loss metrics."""
    sens = cfg.sensitivity
    n = sens.n_trials_sensitivity
    rows_k = []
    logger.info("Sensitivity: sweeping k1 × k2 (%d trials each)...", n)

    for k1 in sens.k1_values:
        for k2 in sens.k2_values:
            logger.info("  k1=%d k2=%d", k1, k2)
            mc = run_monte_carlo(
                cfg,
                n_trials=n,
                k1=k1,
                k2=k2,
                sample_requests=False,
                progress_every=0,
                seed=cfg.seed + 1000 + k1 * 10 + k2,
            )
            summ = mc.summary()
            rows_k.append(
                {
                    "k1": k1,
                    "k2": k2,
                    "availability_mean": summ["availability_mean"],
                    "availability_std": summ["availability_std"],
                    "data_loss_rate_mean": summ["data_loss_rate_per_shard_year_mean"],
                    "data_loss_rate_std": summ["data_loss_rate_per_shard_year_std"],
                    "total_loss_events_mean": summ["data_loss_events_mean"],
                    "p_loss_analytical": data_loss_correlated(
                        cfg.p1_analytic, cfg.p2_cloud_annual, k1, k2
                    ),
                }
            )

    rows_ld = []
    logger.info("Sensitivity: sweeping λ_d...")
    for ld in sens.lambda_d_values:
        logger.info("  λ_d=%.3f", ld)
        mc = run_monte_carlo(
            cfg,
            n_trials=n,
            disaster_rate_per_year=ld,
            sample_requests=False,
            progress_every=0,
            seed=cfg.seed + 2000 + int(ld * 1000),
        )
        summ = mc.summary()
        # Analytic p1 ≈ 1 - exp(-λ_d) for annual disaster probability
        p1 = 1.0 - float(__import__("math").exp(-ld))
        rows_ld.append(
            {
                "lambda_d": ld,
                "p1_approx": p1,
                "availability_mean": summ["availability_mean"],
                "availability_std": summ["availability_std"],
                "data_loss_rate_mean": summ["data_loss_rate_per_shard_year_mean"],
                "data_loss_rate_std": summ["data_loss_rate_per_shard_year_std"],
                "p_loss_analytical": data_loss_correlated(
                    p1,
                    cfg.p2_cloud_annual,
                    cfg.k1_campus_replicas,
                    cfg.k2_cloud_replicas,
                ),
            }
        )

    # Analytical loss grid for publication table
    a_rows = []
    a = node_availability(cfg.mttf_hours, cfg.mttr_hours)
    for k1 in sens.k1_values:
        for k2 in sens.k2_values:
            a_rows.append(
                {
                    "k1": k1,
                    "k2": k2,
                    "A_shard_indep": shard_availability(a, k1 + cfg.k_regional_replicas + k2),
                    "P_loss_correlated": data_loss_correlated(
                        cfg.p1_analytic, cfg.p2_cloud_annual, k1, k2, treat_campus_as_correlated=True
                    ),
                    "P_loss_table42_formula": data_loss_correlated(
                        cfg.p1_analytic, cfg.p2_cloud_annual, k1, k2, treat_campus_as_correlated=False
                    ),
                }
            )

    return SensitivityTables(
        by_k1_k2=pd.DataFrame(rows_k),
        by_lambda_d=pd.DataFrame(rows_ld),
        analytical_loss=pd.DataFrame(a_rows),
    )
