#!/usr/bin/env python3
"""
DRSRS — Disaster-Resilient Student Record System
Monte Carlo / discrete-event simulation entry point.

Usage:
  python -m drsrs.main                  # full run (1000 trials)
  python -m drsrs.main --quick          # reduced trials for smoke test
  python -m drsrs.main --verify-only    # verification suite only
  python -m drsrs.main --config path.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

# Ensure project root is on path when run as script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from drsrs.analysis.reporting import (  # noqa: E402
    export_tables,
    write_docx_results_section,
    write_results_markdown,
)
from drsrs.analysis.sensitivity import run_sensitivity  # noqa: E402
from drsrs.analysis.verification import run_all_verifications  # noqa: E402
from drsrs.config import load_config  # noqa: E402
from drsrs.models import compute_analytical_baseline  # noqa: E402
from drsrs.simulation import run_monte_carlo  # noqa: E402
from drsrs.viz import generate_all_figures  # noqa: E402


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run DRSRS modelling & simulation")
    p.add_argument("--config", type=Path, default=None, help="YAML config path")
    p.add_argument("--quick", action="store_true", help="Fast smoke run (fewer trials)")
    p.add_argument("--verify-only", action="store_true", help="Run verification only")
    p.add_argument("--skip-sensitivity", action="store_true")
    p.add_argument("--skip-verify", action="store_true")
    p.add_argument("--trials", type=int, default=None)
    p.add_argument("--years", type=float, default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--seed", type=int, default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)
    log = logging.getLogger("drsrs.main")

    cfg = load_config(args.config)
    if args.quick:
        cfg = replace(
            cfg,
            n_trials=40,
            sim_years=2.0,
            sensitivity=replace(
                cfg.sensitivity,
                n_trials_sensitivity=20,
                k1_values=[1, 2, 3],
                k2_values=[0, 1],
                lambda_d_values=[0.05, 0.10],
            ),
            verification=replace(cfg.verification, n_trials=80, sim_years=1.0),
        )
        log.warning("QUICK mode: reduced trials/years for smoke testing")
    if args.trials is not None:
        cfg = replace(cfg, n_trials=args.trials)
    if args.years is not None:
        cfg = replace(cfg, sim_years=args.years)
    if args.seed is not None:
        cfg = replace(cfg, seed=args.seed)

    cfg.ensure_dirs(ROOT)
    figures_dir = ROOT / cfg.paths.figures
    tables_dir = ROOT / cfg.paths.tables
    reports_dir = ROOT / cfg.paths.reports
    data_dir = ROOT / cfg.paths.data

    t0 = time.time()

    # --- Analytical baseline ---
    k_indep = cfg.k1_campus_replicas + cfg.k_regional_replicas + cfg.k2_cloud_replicas
    analytical = compute_analytical_baseline(
        mttf=cfg.mttf_hours,
        mttr=cfg.mttr_hours,
        k_independent=k_indep,
        a_network=cfg.a_network,
        a_app=cfg.a_app,
        n_coord=cfg.coordinator_nodes,
        p1=cfg.p1_analytic,
        p2=cfg.p2_cloud_annual,
        k1=cfg.k1_campus_replicas,
        k2=cfg.k2_cloud_replicas,
        lam=cfg.lambda_req_per_s,
        mu=cfg.mu_per_thread,
        c=cfg.threads_per_replica,
        slo_ms=cfg.slo_latency_ms,
    )
    log.info(
        "Analytical: A_node=%.6f A_sys=%.6f A_quorum=%.6f P_loss=%.3e ρ=%.3f",
        analytical.a_node,
        analytical.a_system,
        analytical.a_quorum,
        analytical.p_loss_correlated,
        analytical.rho,
    )

    # --- Verification ---
    checks = []
    if not args.skip_verify:
        checks = run_all_verifications(cfg)
        if args.verify_only:
            n_pass = sum(1 for c in checks if c.passed)
            log.info("Verification done: %d/%d passed (%.1fs)", n_pass, len(checks), time.time() - t0)
            return 0 if n_pass == len(checks) else 1

    # --- Monte Carlo baseline ---
    log.info(
        "Starting baseline Monte Carlo: %d trials × %.1f years...",
        cfg.n_trials,
        cfg.sim_years,
    )
    mc = run_monte_carlo(cfg, progress_every=max(1, cfg.n_trials // 20))
    summ = mc.summary()
    log.info(
        "Baseline done: avail=%.6f±%.6f loss_rate=%.3e SLO=%.4f",
        summ["availability_mean"],
        summ["availability_std"],
        summ["data_loss_rate_per_shard_year_mean"],
        summ["slo_fraction_mean"],
    )

    # Persist raw results
    with (data_dir / "monte_carlo_baseline.pkl").open("wb") as f:
        pickle.dump({"mc": mc, "analytical": analytical, "cfg": cfg}, f)
    with (data_dir / "monte_carlo_summary.json").open("w") as f:
        json.dump({k: float(v) if isinstance(v, (np.floating, float)) else v for k, v in summ.items()}, f, indent=2)

    # --- Sensitivity ---
    if args.skip_sensitivity:
        from drsrs.analysis.sensitivity import SensitivityTables
        import pandas as pd

        sens = SensitivityTables(
            by_k1_k2=pd.DataFrame(
                [
                    {
                        "k1": cfg.k1_campus_replicas,
                        "k2": k2,
                        "availability_mean": summ["availability_mean"],
                        "availability_std": summ["availability_std"],
                        "data_loss_rate_mean": summ["data_loss_rate_per_shard_year_mean"],
                        "data_loss_rate_std": summ["data_loss_rate_per_shard_year_std"],
                        "total_loss_events_mean": summ["data_loss_events_mean"],
                        "p_loss_analytical": analytical.p_loss_correlated,
                    }
                    for k2 in (0, 1)
                ]
            ),
            by_lambda_d=pd.DataFrame(
                [
                    {
                        "lambda_d": cfg.disaster_rate_per_year,
                        "p1_approx": cfg.p1_analytic,
                        "availability_mean": summ["availability_mean"],
                        "availability_std": summ["availability_std"],
                        "data_loss_rate_mean": summ["data_loss_rate_per_shard_year_mean"],
                        "data_loss_rate_std": summ["data_loss_rate_per_shard_year_std"],
                        "p_loss_analytical": analytical.p_loss_correlated,
                    }
                ]
            ),
            analytical_loss=pd.DataFrame(),
        )
    else:
        sens = run_sensitivity(cfg)
        sens.by_k1_k2.to_pickle(data_dir / "sensitivity_k1_k2.pkl")

    # --- Figures & tables ---
    log.info("Generating figures and tables...")
    fig_paths = generate_all_figures(
        mc, sens, analytical, figures_dir, cfg.a_network, cfg.a_app
    )
    table_paths = export_tables(cfg, analytical, mc, sens, checks, tables_dir)
    md_path = write_results_markdown(
        cfg,
        analytical,
        mc,
        sens,
        checks,
        [p.name for p in fig_paths],
        reports_dir,
    )
    docx_path = write_docx_results_section(reports_dir, md_path)

    elapsed = time.time() - t0
    log.info("All done in %.1f s", elapsed)
    log.info("Figures: %s", figures_dir)
    log.info("Tables:  %s", tables_dir)
    log.info("Report:  %s", md_path)
    if docx_path:
        log.info("DOCX:    %s", docx_path)

    print("\n=== DRSRS Simulation Complete ===")
    e2e = cfg.a_network * cfg.a_app * summ["availability_mean"]
    print(f"DB-tier availability (sim):  {summ['availability_mean']*100:.8f}%")
    print(f"End-to-end availability:     {e2e*100:.6f}%  (× network × app)")
    print(f"Data-loss rate (sim):        {summ['data_loss_rate_per_shard_year_mean']:.3e} /shard·year")
    print(f"SLO ≤200 ms (sim):           {summ['slo_fraction_mean']*100:.2f}%")
    print(f"Results written to:          {reports_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
