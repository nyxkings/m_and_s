# DRSRS Simulation Results (Chapter 4.8 Replacement)

This document replaces the report placeholders that stated
*"Insert your group's actual simulation output here"*.

## Configuration

| Parameter | Value |
|-----------|-------|
| Shards N | 16 |
| Campus replicas k1 | 2 |
| Regional replicas | 1 |
| Cloud replicas k2 | 1 |
| MTTF / MTTR | 2000.0 h / 2.0 h |
| Disaster rate λ_d | 0.05 /year |
| Mean disaster duration | 48.0 h |
| λ, μ, c | 50.0 req/s, 20.0 /s/thread, 4 threads |
| Horizon × trials | 2.0 years × 40 trials |

## 4.8.1 Availability Results

**Analytical (Section 4.3):** system availability
A_system = A_network × A_app × A_shard ≈ **0.998500**
(99.8500%), corresponding to roughly
**13.14 hours** of downtime per year.
As predicted, the network (0.9995) and application (0.999)
layers dominate over the highly redundant database tier
(A_shard ≈ 1.00000000).

**Simulated (database tier):** across 40 Monte Carlo trials of
2.0 simulated years each, mean *database* availability
(every shard has ≥1 reachable replica — Section 3.5 metric) was
**100.00000000%** (std = 0.000000 pp).
Composing with the network and application layers as in Section 4.3 gives
end-to-end availability
**A_e2e = A_network × A_app × A_db ≈ 99.850050%**,
or about **13.14 hours/year** of end-to-end downtime — close to
the analytical prediction of 99.8500%.
Mean quorum availability was **99.999395%**
(analytical: 99.999701%).

The DES intentionally models database/coordination failures and disasters;
network and application availability enter via the series product so that
results remain comparable to Section 4.3.

See figures: `availability_histogram.png`, `availability_boxplot.png`,
`analytical_vs_simulated.png`.

## 4.8.2 Data-Loss Results

**Analytical (corrected correlated-domain model, Section 4.5):**
P_loss = p1 × p2^k2 = **1.000e-07** per year for the
baseline (k1=2, k2=1,
p1=0.001, p2=0.0001).

**Simulated:** mean permanent data-loss rate =
**0.000e+00** events per shard·year.
Sensitivity runs confirm the hybrid-cloud thesis:

| Configuration | Simulated loss rate /shard·year |
|---------------|----------------------------------|
| k1=2, k2=0 (no cloud) | 7.812e-03 |
| k1=2, k2=1 (hybrid) | 0.000e+00 |

Adding a single independent cloud replica reduces empirical loss risk by
orders of magnitude relative to campus-only replication, matching the
narrative of Section 4.5. See `data_loss_sensitivity.png` and
`data_loss_analytical.png`.

## 4.8.3 Latency and Access Results

Queue utilisation ρ = λ/(cμ) = **0.6250** with
λ=50.0, μ=20.0, c=4.
Erlang-C P_wait ≈ **0.3199**; analytical mean response ≈
**60.66 ms**.

Simulation: mean response **49.83 ms**
(p95 of trial means: 148.96 ms);
fraction of requests meeting the 200 ms SLO ≈ **98.24%**
(analytical ≈ 97.16%).

As ρ approaches 1, P_wait and response time grow sharply
(`queueing_vs_load.png`), justifying the provisioned thread count.

## 4.8.4 Sensitivity Analysis

Varying k1, k2, and λ_d shows:

1. **P_loss is far more sensitive to k2** (independent domain) than to k1
   (correlated campus replicas).
2. Increasing λ_d reduces availability roughly linearly at the rates studied
   and raises loss risk when k2 = 0; with k2 ≥ 1, loss remains extremely rare.
3. Availability stays above three nines for the recommended configuration
   across the λ_d sweep (0.01–0.20 /year).

Tables: `sensitivity_k1_k2.csv`, `sensitivity_lambda_d.csv`.
Figures: `lambda_d_sensitivity.png`, `availability_heatmap.png`.

## 4.9 Verification Summary

4/4 automated checks passed.

- **[PASS]** Node availability formula MTTF=2000, MTTR=2: analytical=0.999001, simulated=0.999001, |err|=0
- **[PASS]** Quorum formula (n=3, A=0.99) vs worked example: analytical=0.999703, simulated=0.999702, |err|=1e-06
- **[PASS]** Single-node availability (k1=1, λ_d=0): analytical=0.999001, simulated=0.99899569, |err|=5.31e-06
- **[PASS]** Independent 3-replica shard availability (λ_d=0): analytical=1, simulated=1, |err|=9.97e-10

## Generated figures

- `availability_histogram.png`
- `availability_boxplot.png`
- `reliability_vs_replicas.png`
- `data_loss_sensitivity.png`
- `data_loss_analytical.png`
- `lambda_d_sensitivity.png`
- `latency_distribution.png`
- `queueing_vs_load.png`
- `availability_heatmap.png`
- `analytical_vs_simulated.png`

## Interpretation for recommendations (Chapter 5)

The simulation empirically supports the Chapter 5 recommendation of
**k1 = 2 synchronous campus replicas**, **≥1 regional async replica**,
**k2 ≥ 1 cloud DR replica**, and a **3-node Raft quorum**. Hybrid-cloud
placement, not additional co-located copies, is the dominant lever for
durability under campus-scale disasters.
