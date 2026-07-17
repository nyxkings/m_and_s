# DRSRS Project — Final Implementation Summary

## What was implemented

A complete Modelling & Simulation project for the **Disaster-Resilient Student
Record System (DRSRS)** from the CSC 508 Group 1 report, including:

| Area | Implementation |
|------|----------------|
| Architecture | Consistent-hash sharding, k1 campus sync, regional async, k2 cloud DR, 3-node Raft quorum |
| §4.1–4.4 | Node, shard, series-system, and quorum availability formulas |
| §4.5 | Correlated-domain data-loss model (+ Table 4.2 formula for comparison) |
| §4.6 | CAP policy documented (AP reads / CP critical writes; last-write-wins) |
| §4.7 | Full M/M/c Erlang-C (P0, P_wait, W_q, W, SLO fraction) |
| §3.5 | SimPy DES: failure/repair, campus disasters, cloud outages, request queueing |
| Monte Carlo | 1000 trials × 5 simulated years (configurable) |
| Sensitivity | Sweeps over k1, k2, λ_d |
| V&V | §4.9 limiting-case checks vs closed forms |
| Outputs | PNG figures, CSV tables, Chapter 4.8 markdown + DOCX |

## How to run

```bash
source .venv/bin/activate
python -m drsrs.main          # full campaign
python -m drsrs.main --quick  # smoke test
pytest tests/ -q
```

## Issues found in the report and corrections

See `docs/CORRECTIONS.md` for full detail. Headline fixes:

1. **μ = 80 vs μ = 20:** Table 3.2 mislabelled total capacity as per-thread rate.
   Code uses μ = 20 req/s/thread per Section 4.7 (ρ = 0.625).
2. **P_loss formula:** Prose says campus replicas are correlated (P_loss ≈ p1 when
   k2=0); Table 4.2 hybrid rows use p1^k1 × p2^k2. Code uses
   **P_loss = p1 × p2^k2** as primary.
3. **Regional replica:** Required by §3.2/§5.4 but missing from Table 3.2 →
   default `k_regional_replicas = 1`.
4. **Cloud DES process:** Derived Poisson rate from annual p2.
5. **Request thinning:** Full λ over 5 years is intractable; thinned sampling
   + Erlang-C closed form.

## Assumptions made (where report was silent)

- Disaster and cloud-outage durations ~ Exp(mean = 48 h)
- Campus A and Campus B each suffer disasters at λ_d independently
- DES tracks DB/quorum availability; A_network × A_app applied for e2e A_system
- Cloud outage mean duration equals campus disaster mean duration
- Sensitivity uses 100 trials/config (baseline uses 1000 as specified)

## Verification status

Automated checks (Section 4.9):

- Node A = MTTF/(MTTF+MTTR) exact match
- Quorum n=3, A=0.99 ≈ 0.9997 match
- Single-node DES converges to A
- Independent 3-replica DES converges to 1−(1−A)^3

## Remaining limitations / recommendations

- Exponential failure times (report §5.2); Weibull aging not modelled
- No cost/energy/bandwidth model
- No security/ransomware common-mode failure
- Rare loss events (P ≈ 10^{-7}/year) need huge simulated exposure to observe
  empirically; rely on analytics + relative k2=0 vs k2=1 sensitivity
- Calibrate MTTF/MTTR/λ_d against institutional operational data when available

## Recommended production configuration (from models + sim)

- Shard by consistent hash of matriculation number (N = 16+)
- k1 = 2 synchronous campus replicas
- ≥1 async regional replica
- k2 ≥ 1 cloud DR replica
- 3-node Raft coordination quorum
- Provision c so ρ = λ/(cμ) stays well below 1 (design ρ ≈ 0.625)
