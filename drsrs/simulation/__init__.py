"""
Discrete-event Monte Carlo simulation of the DRSRS (Section 3.5).

Processes:
  - Independent exponential failure / repair per replica and coordinator
  - Correlated campus-wide disaster events (Poisson) that take down one
    campus domain for an exponentially distributed duration
  - Independent cloud-region total outages (rare)
  - M/M/c request generation and service for latency sampling
  - Availability and data-loss observation over simulated time
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import simpy

from drsrs.config import DRSRSConfig
from drsrs.models.architecture import (
    Domain,
    Topology,
    build_topology,
)

logger = logging.getLogger(__name__)


@dataclass
class TrialResult:
    """Aggregated metrics from one Monte Carlo trial."""

    trial_id: int
    sim_hours: float
    availability: float                 # fraction of time all shards reachable
    shard_availability_mean: float      # mean over shards of per-shard uptime
    data_loss_events: int               # count of permanent-loss incidents
    data_loss_rate_per_shard_year: float
    quorum_availability: float
    mean_response_ms: float
    p50_response_ms: float
    p95_response_ms: float
    p99_response_ms: float
    slo_fraction: float
    mean_queue_wait_ms: float
    n_requests: int
    n_disasters_campus_a: int
    n_disasters_campus_b: int
    n_cloud_outages: int
    downtime_hours: float


@dataclass
class MonteCarloResults:
    trials: list[TrialResult] = field(default_factory=list)
    config_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_arrays(self) -> dict[str, np.ndarray]:
        if not self.trials:
            return {}
        keys = [
            "availability",
            "shard_availability_mean",
            "data_loss_events",
            "data_loss_rate_per_shard_year",
            "quorum_availability",
            "mean_response_ms",
            "p50_response_ms",
            "p95_response_ms",
            "p99_response_ms",
            "slo_fraction",
            "mean_queue_wait_ms",
            "n_requests",
            "downtime_hours",
        ]
        return {k: np.array([getattr(t, k) for t in self.trials], dtype=float) for k in keys}

    def summary(self) -> dict[str, float]:
        arr = self.to_arrays()
        out: dict[str, float] = {}
        for k, v in arr.items():
            out[f"{k}_mean"] = float(np.mean(v))
            out[f"{k}_std"] = float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
            out[f"{k}_p05"] = float(np.percentile(v, 5))
            out[f"{k}_p95"] = float(np.percentile(v, 95))
        return out


class DRSRSSimulation:
    """One discrete-event trial of the DRSRS."""

    def __init__(
        self,
        env: simpy.Environment,
        cfg: DRSRSConfig,
        rng: np.random.Generator,
        topology: Topology,
        *,
        sample_requests: bool = True,
        request_sample_limit: int = 50_000,
    ) -> None:
        self.env = env
        self.cfg = cfg
        self.rng = rng
        self.topo = topology
        self.sample_requests = sample_requests
        self.request_sample_limit = request_sample_limit

        self.up_time_integral = 0.0
        self.shard_up_integral = np.zeros(cfg.n_shards, dtype=float)
        self.quorum_up_integral = 0.0
        self._last_sample = 0.0
        self._db_was_up = True
        self._quorum_was_up = True
        self._shard_was_up = np.ones(cfg.n_shards, dtype=bool)

        self.data_loss_events = 0
        self._in_loss_episode: set[int] = set()

        self.response_times_s: list[float] = []
        self.queue_waits_s: list[float] = []
        self.n_requests = 0
        self.n_disasters_a = 0
        self.n_disasters_b = 0
        self.n_cloud_outages = 0

        # Domain-level forced downtime (disaster / cloud outage)
        self.domain_forced_down: dict[Domain, bool] = {
            Domain.CAMPUS_A: False,
            Domain.CAMPUS_B: False,
            Domain.CLOUD: False,
        }

        # Per-replica independent failure state (True = independently failed)
        self._indep_failed: dict[str, bool] = {
            r.replica_id: False for r in topology.all_replicas()
        }
        self._coord_indep_failed: dict[int, bool] = {
            c.node_id: False for c in topology.coordinators
        }

        # Shared M/M/c resource representing one active primary's thread pool
        # (aggregate model per shard, Section 4.7)
        self.shard_servers: dict[int, simpy.Resource] = {
            sid: simpy.Resource(env, capacity=cfg.threads_per_replica)
            for sid in range(cfg.n_shards)
        }

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _refresh_replica(self, replica_id: str) -> None:
        for sh in self.topo.shards:
            for r in sh.replicas:
                if r.replica_id == replica_id:
                    forced = self.domain_forced_down[r.domain]
                    indep = self._indep_failed[replica_id]
                    if forced or indep:
                        r.mark_down()
                    else:
                        r.mark_up()
                    return

    def _refresh_all(self) -> None:
        for r in self.topo.all_replicas():
            self._refresh_replica(r.replica_id)
        for c in self.topo.coordinators:
            c.up = not self._coord_indep_failed[c.node_id]

    def _record_integrals(self) -> None:
        now = self.env.now
        dt = now - self._last_sample
        if dt <= 0:
            return
        if self._db_was_up:
            self.up_time_integral += dt
        self.shard_up_integral += self._shard_was_up.astype(float) * dt
        if self._quorum_was_up:
            self.quorum_up_integral += dt
        self._last_sample = now

    def _observe_state(self) -> None:
        """Update integrals and detect permanent data-loss episodes."""
        self._record_integrals()
        self._refresh_all()
        self._db_was_up = self.topo.system_db_up()
        self._quorum_was_up = self.topo.quorum_up()
        for i, sh in enumerate(self.topo.shards):
            self._shard_was_up[i] = sh.has_reachable_replica()
            # Permanent loss: every replica of the shard is down simultaneously
            if sh.all_down():
                if i not in self._in_loss_episode:
                    self._in_loss_episode.add(i)
                    self.data_loss_events += 1
            else:
                self._in_loss_episode.discard(i)

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------

    def replica_lifecycle(self, replica_id: str):
        """Independent exponential failure/repair for one replica."""
        mttf = self.cfg.mttf_hours
        mttr = self.cfg.mttr_hours
        while True:
            # Time to failure
            ttf = float(self.rng.exponential(mttf))
            yield self.env.timeout(ttf)
            self._indep_failed[replica_id] = True
            self._observe_state()
            # Time to repair
            ttr = float(self.rng.exponential(mttr))
            yield self.env.timeout(ttr)
            self._indep_failed[replica_id] = False
            self._observe_state()

    def coordinator_lifecycle(self, node_id: int):
        mttf = self.cfg.mttf_hours
        mttr = self.cfg.mttr_hours
        while True:
            yield self.env.timeout(float(self.rng.exponential(mttf)))
            self._coord_indep_failed[node_id] = True
            self._observe_state()
            yield self.env.timeout(float(self.rng.exponential(mttr)))
            self._coord_indep_failed[node_id] = False
            self._observe_state()

    def campus_disaster_process(self, domain: Domain):
        """Poisson disasters that force-down an entire campus domain."""
        rate = self.cfg.disaster_rate_per_hour
        mean_dur = self.cfg.disaster_duration_mean_hours
        while True:
            # Inter-arrival ~ Exp(λ)
            if rate <= 0:
                yield self.env.timeout(self.cfg.sim_horizon_hours + 1)
                continue
            wait = float(self.rng.exponential(1.0 / rate))
            yield self.env.timeout(wait)
            duration = float(self.rng.exponential(mean_dur))
            self.domain_forced_down[domain] = True
            if domain == Domain.CAMPUS_A:
                self.n_disasters_a += 1
            else:
                self.n_disasters_b += 1
            self._observe_state()
            yield self.env.timeout(duration)
            self.domain_forced_down[domain] = False
            self._observe_state()

    def cloud_outage_process(self):
        """Rare independent cloud-region total outages.

        Annual probability p2 ≈ 1 − exp(−λ_c · T_year). We back out an
        hourly rate λ_c = −ln(1 − p2) / 8760 so that P(≥1 outage/year) ≈ p2
        for small p2 (here p2 = 1e-4).
        """
        p2 = self.cfg.p2_cloud_annual
        if p2 <= 0:
            yield self.env.timeout(self.cfg.sim_horizon_hours + 1)
            return
        # Mean outages per year such that 1 - e^{-λ} ≈ p2 → λ = -ln(1-p2)
        mean_per_year = -np.log(1.0 - min(p2, 0.999999))
        rate = mean_per_year / self.cfg.hours_per_year
        # Cloud outage duration: use same mean as campus disaster (documented assumption)
        mean_dur = self.cfg.disaster_duration_mean_hours
        while True:
            wait = float(self.rng.exponential(1.0 / rate))
            yield self.env.timeout(wait)
            duration = float(self.rng.exponential(mean_dur))
            self.domain_forced_down[Domain.CLOUD] = True
            self.n_cloud_outages += 1
            self._observe_state()
            yield self.env.timeout(duration)
            self.domain_forced_down[Domain.CLOUD] = False
            self._observe_state()

    def request_generator(self):
        """Poisson arrivals per shard; M/M/c service on a live replica."""
        if not self.sample_requests:
            return
        # Aggregate λ across shards; each request hashed to a random shard
        # (uniform under consistent hashing of matric numbers).
        total_lambda = self.cfg.lambda_req_per_s * self.cfg.n_shards
        # Convert to per-hour arrival rate for sim time in hours
        # 1 hour = 3600 s → arrivals/hour = λ_s * 3600
        arrivals_per_hour = total_lambda * 3600.0
        mu = self.cfg.mu_per_thread  # per second
        # Cap sampling: we don't need billions of requests over 5 years.
        # Sample a thinned process so expected samples ≈ request_sample_limit.
        horizon = self.cfg.sim_horizon_hours
        expected = arrivals_per_hour * horizon
        thin = min(1.0, self.request_sample_limit / max(expected, 1.0))
        sampled_rate = arrivals_per_hour * thin

        while True:
            inter = float(self.rng.exponential(1.0 / sampled_rate))
            yield self.env.timeout(inter)
            sid = int(self.rng.integers(0, self.cfg.n_shards))
            shard = self.topo.shards[sid]
            if not shard.has_reachable_replica():
                # Unavailable — count as failed request (infinite latency skip)
                continue
            self.env.process(self._handle_request(sid, mu))

    def _handle_request(self, sid: int, mu: float):
        server = self.shard_servers[sid]
        arrive = self.env.now
        with server.request() as req:
            yield req
            wait_h = self.env.now - arrive
            # Service time in hours: Exp(μ) with μ in 1/s → mean 1/μ seconds
            service_s = float(self.rng.exponential(1.0 / mu))
            service_h = service_s / 3600.0
            yield self.env.timeout(service_h)
            total_s = wait_h * 3600.0 + service_s
            if len(self.response_times_s) < self.request_sample_limit:
                self.response_times_s.append(total_s)
                self.queue_waits_s.append(wait_h * 3600.0)
                self.n_requests += 1

    def periodic_observer(self):
        """Periodic state sampling (also catches steady periods)."""
        dt = self.cfg.availability_sample_hours
        while True:
            yield self.env.timeout(dt)
            self._observe_state()

    def run_processes(self) -> None:
        for r in self.topo.all_replicas():
            self.env.process(self.replica_lifecycle(r.replica_id))
        for c in self.topo.coordinators:
            self.env.process(self.coordinator_lifecycle(c.node_id))
        self.env.process(self.campus_disaster_process(Domain.CAMPUS_A))
        self.env.process(self.campus_disaster_process(Domain.CAMPUS_B))
        self.env.process(self.cloud_outage_process())
        self.env.process(self.periodic_observer())
        if self.sample_requests:
            self.env.process(self.request_generator())

    def finalize(self, trial_id: int) -> TrialResult:
        self._observe_state()
        T = self.env.now
        avail = self.up_time_integral / T if T > 0 else 0.0
        shard_mean = float(np.mean(self.shard_up_integral / T)) if T > 0 else 0.0
        q_avail = self.quorum_up_integral / T if T > 0 else 0.0
        years = T / self.cfg.hours_per_year
        # Per-shard per-year loss rate
        loss_rate = (
            self.data_loss_events / (self.cfg.n_shards * years)
            if years > 0
            else 0.0
        )

        if self.response_times_s:
            rt = np.array(self.response_times_s) * 1000.0  # ms
            qw = np.array(self.queue_waits_s) * 1000.0
            slo = float(np.mean(rt <= self.cfg.slo_latency_ms))
            mean_rt = float(np.mean(rt))
            p50 = float(np.percentile(rt, 50))
            p95 = float(np.percentile(rt, 95))
            p99 = float(np.percentile(rt, 99))
            mean_qw = float(np.mean(qw))
        else:
            mean_rt = p50 = p95 = p99 = mean_qw = float("nan")
            slo = float("nan")

        return TrialResult(
            trial_id=trial_id,
            sim_hours=T,
            availability=avail,
            shard_availability_mean=shard_mean,
            data_loss_events=self.data_loss_events,
            data_loss_rate_per_shard_year=loss_rate,
            quorum_availability=q_avail,
            mean_response_ms=mean_rt,
            p50_response_ms=p50,
            p95_response_ms=p95,
            p99_response_ms=p99,
            slo_fraction=slo,
            mean_queue_wait_ms=mean_qw,
            n_requests=self.n_requests,
            n_disasters_campus_a=self.n_disasters_a,
            n_disasters_campus_b=self.n_disasters_b,
            n_cloud_outages=self.n_cloud_outages,
            downtime_hours=T * (1.0 - avail),
        )


def run_single_trial(
    cfg: DRSRSConfig,
    trial_id: int,
    rng: np.random.Generator,
    *,
    k1: int | None = None,
    k_regional: int | None = None,
    k2: int | None = None,
    disaster_rate_per_year: float | None = None,
    sample_requests: bool = True,
    request_sample_limit: int = 20_000,
) -> TrialResult:
    """Execute one Monte Carlo trial and return metrics."""
    k1 = cfg.k1_campus_replicas if k1 is None else k1
    k_regional = cfg.k_regional_replicas if k_regional is None else k_regional
    k2 = cfg.k2_cloud_replicas if k2 is None else k2

    # Allow per-trial override of disaster rate without mutating shared cfg
    local_cfg = cfg
    if disaster_rate_per_year is not None and disaster_rate_per_year != cfg.disaster_rate_per_year:
        # Shallow copy via dataclass replace would be cleaner; mutate a copy dict
        from dataclasses import replace

        local_cfg = replace(cfg, disaster_rate_per_year=disaster_rate_per_year)

    topo = build_topology(
        n_shards=local_cfg.n_shards,
        k1=k1,
        k_regional=k_regional,
        k2=k2,
        n_coordinators=local_cfg.coordinator_nodes,
    )
    env = simpy.Environment()
    sim = DRSRSSimulation(
        env,
        local_cfg,
        rng,
        topo,
        sample_requests=sample_requests,
        request_sample_limit=request_sample_limit,
    )
    sim.run_processes()
    env.run(until=local_cfg.sim_horizon_hours)
    return sim.finalize(trial_id)


def _trial_worker(args: tuple) -> TrialResult:
    """Picklable worker for ProcessPoolExecutor."""
    (
        cfg,
        trial_id,
        seed,
        k1,
        k2,
        disaster_rate_per_year,
        sample_requests,
        request_sample_limit,
    ) = args
    rng = np.random.default_rng(seed)
    return run_single_trial(
        cfg,
        trial_id=trial_id,
        rng=rng,
        k1=k1,
        k2=k2,
        disaster_rate_per_year=disaster_rate_per_year,
        sample_requests=sample_requests,
        request_sample_limit=request_sample_limit,
    )


def run_monte_carlo(
    cfg: DRSRSConfig,
    *,
    n_trials: int | None = None,
    seed: int | None = None,
    k1: int | None = None,
    k2: int | None = None,
    disaster_rate_per_year: float | None = None,
    sample_requests: bool = True,
    progress_every: int = 50,
    n_workers: int | None = None,
) -> MonteCarloResults:
    """Run N independent Monte Carlo trials (optionally in parallel)."""
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed

    n = cfg.n_trials if n_trials is None else n_trials
    base_seed = cfg.seed if seed is None else seed
    req_limit = 5_000 if sample_requests else 0
    results = MonteCarloResults(
        config_snapshot={
            "n_trials": n,
            "sim_years": cfg.sim_years,
            "k1": k1 if k1 is not None else cfg.k1_campus_replicas,
            "k2": k2 if k2 is not None else cfg.k2_cloud_replicas,
            "k_regional": cfg.k_regional_replicas,
            "lambda_d": (
                disaster_rate_per_year
                if disaster_rate_per_year is not None
                else cfg.disaster_rate_per_year
            ),
            "mttf": cfg.mttf_hours,
            "mttr": cfg.mttr_hours,
        }
    )

    work = [
        (
            cfg,
            i,
            base_seed + i * 10007,
            k1,
            k2,
            disaster_rate_per_year,
            sample_requests,
            req_limit,
        )
        for i in range(n)
    ]

    workers = n_workers if n_workers is not None else max(1, (os.cpu_count() or 2) - 1)
    # Sequential for tiny jobs (avoids process spawn overhead)
    if workers <= 1 or n <= 4:
        for i, args in enumerate(work):
            trial = _trial_worker(args)
            results.trials.append(trial)
            if progress_every and (i + 1) % progress_every == 0:
                logger.info(
                    "Completed trial %d / %d (avail=%.6f)",
                    i + 1,
                    n,
                    trial.availability,
                )
        return results

    logger.info("Running %d trials with %d workers...", n, workers)
    trials_by_id: dict[int, TrialResult] = {}
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_trial_worker, args): args[1] for args in work}
        for fut in as_completed(futures):
            trial = fut.result()
            trials_by_id[trial.trial_id] = trial
            done += 1
            if progress_every and done % progress_every == 0:
                logger.info(
                    "Completed trial %d / %d (avail=%.6f)",
                    done,
                    n,
                    trial.availability,
                )
    results.trials = [trials_by_id[i] for i in range(n)]
    return results
