"""Unit tests for analytical models and light simulation smoke tests."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from drsrs.config import load_config
from drsrs.models import (
    data_loss_correlated,
    erlang_c_p_wait,
    node_availability,
    quorum_availability,
    shard_availability,
    system_availability,
    utilisation,
)
from drsrs.models.architecture import build_topology, consistent_hash_shard
from drsrs.simulation import run_monte_carlo, run_single_trial


def test_node_availability_worked_example():
    a = node_availability(2000, 2)
    assert abs(a - 2000 / 2002) < 1e-15
    assert abs(a - 0.999000999) < 1e-6


def test_shard_availability_table_4_1():
    a = 0.990
    assert abs(shard_availability(a, 1) - 0.990) < 1e-12
    assert abs(shard_availability(a, 2) - 0.9999) < 1e-12
    assert abs(shard_availability(a, 3) - 0.999999) < 1e-12


def test_system_availability_worked_example():
    a_sys = system_availability(0.9995, 0.999, 0.999999)
    assert abs(a_sys - 0.9995 * 0.999 * 0.999999) < 1e-15
    assert abs(a_sys - 0.9985) < 5e-4


def test_quorum_worked_example():
    a_q = quorum_availability(0.99, 3)
    # Report ≈ 0.9997
    assert abs(a_q - 0.999703) < 1e-5


def test_data_loss_correlated_narrative():
    # Campus-only: loss ≈ p1 regardless of k1
    assert data_loss_correlated(0.001, 0.0001, 1, 0) == 0.001
    assert data_loss_correlated(0.001, 0.0001, 3, 0) == 0.001
    # Hybrid: p1 * p2
    assert abs(data_loss_correlated(0.001, 0.0001, 2, 1) - 1e-7) < 1e-15
    assert abs(data_loss_correlated(0.001, 0.0001, 2, 2) - 1e-11) < 1e-15


def test_erlang_c_utilisation():
    rho = utilisation(50, 20, 4)
    assert abs(rho - 0.625) < 1e-12
    pw = erlang_c_p_wait(50, 20, 4)
    assert 0 < pw < 0.5  # comfortably below saturation


def test_consistent_hashing_spread():
    n = 16
    counts = [0] * n
    for i in range(10_000):
        counts[consistent_hash_shard(f"CSC/20/{i}", n)] += 1
    # Roughly uniform
    assert min(counts) > 400
    assert max(counts) < 900


def test_topology_levels():
    topo = build_topology(n_shards=4, k1=2, k_regional=1, k2=1, n_coordinators=3)
    assert len(topo.shards) == 4
    assert len(topo.shards[0].replicas) == 4
    assert topo.system_db_up()
    assert topo.quorum_up()


def test_single_trial_smoke():
    cfg = load_config()
    from dataclasses import replace

    cfg = replace(cfg, n_shards=4, sim_years=0.5, n_trials=1)
    rng = np.random.default_rng(0)
    result = run_single_trial(cfg, 0, rng, sample_requests=True, request_sample_limit=500)
    assert 0.9 < result.availability <= 1.0
    assert result.sim_hours == pytest.approx(cfg.sim_horizon_hours)


def test_monte_carlo_converges_toward_a():
    from dataclasses import replace

    cfg = load_config()
    cfg = replace(
        cfg,
        n_shards=1,
        k1_campus_replicas=1,
        k_regional_replicas=0,
        k2_cloud_replicas=0,
        disaster_rate_per_year=0.0,
        p2_cloud_annual=0.0,
        sim_years=1.0,
        n_trials=30,
    )
    mc = run_monte_carlo(cfg, n_trials=30, sample_requests=False, progress_every=0)
    a = node_availability(cfg.mttf_hours, cfg.mttr_hours)
    sim = float(np.mean([t.availability for t in mc.trials]))
    assert abs(sim - a) < 0.01
