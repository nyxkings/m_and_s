# DRSRS Project — Final Implementation Summary

Generated after the full Monte Carlo campaign (1000 × 5 years).

## Verdict

The report has been transformed into a working, verified Modelling & Simulation
project. End-to-end availability matches the Section 4.3 prediction
(**99.850%**), hybrid-cloud replication eliminates observed permanent data
loss in simulation (vs non-zero loss when k2 = 0), and all four Section 4.9
verification checks **PASS**.

## What was implemented

| Area | Status |
|------|--------|
| System architecture (Levels 0–3) | Done |
| Consistent-hash sharding | Done |
| Replication + multi-region + hybrid cloud | Done |
| Availability / reliability / quorum models | Done |
| Correlated-domain data-loss model | Done |
| M/M/c Erlang-C queueing | Done |
| Request generation, failure/repair, disasters | Done |
| Monte Carlo DES (SimPy) | Done — 1000 × 5 years |
| Sensitivity (k1, k2, λ_d) | Done |
| Publication figures + tables | Done (`outputs/`) |
| Chapter 4.8 placeholder replacement | Done (`outputs/reports/`) |
| V&V against closed forms | Done — 4/4 PASS |

## Key numerical results (full campaign)

| Metric | Value |
|--------|-------|
| A_node (analytical) | 0.999001 |
| A_system (analytical series) | 0.998500 (99.8500%) |
| DB-tier availability (sim) | ≈ 100% (multi-replica) |
| End-to-end A (A_net × A_app × A_db) | **99.850050%** |
| Quorum availability (sim) | 99.999689% |
| P_loss analytical (k1=2, k2=1) | 1.0 × 10⁻⁷ /year |
| Data-loss rate sim (baseline k2=1) | 0 (none observed) |
| Data-loss rate sim (k1=2, k2=0) | **1.625 × 10⁻³** /shard·year |
| ρ | 0.625 |
| Mean response (sim) | 49.96 ms |
| SLO ≤ 200 ms (sim) | **98.18%** |

## Issues found and fixed

Documented in `docs/CORRECTIONS.md`:

1. **Table 3.2 μ=80** vs **§4.7 μ=20** — used μ=20 (ρ=0.625).
2. **P_loss = p1^{k1}×p2^{k2}** contradicts correlated narrative — primary model is **P_loss = p1 × p2^{k2}**.
3. **Regional replica** missing from Table 3.2 — added `k_regional_replicas=1`.
4. Cloud DES rate derived from annual p2; disaster duration ~ Exp(48 h).
5. Request arrivals thinned for computational tractability.

## Assumptions made

- Exp failure/repair/disaster/cloud-outage durations
- Independent λ_d disasters on Campus A and Campus B
- Network/app enter e2e availability via series product (DES focuses on DB/quorum)
- Sensitivity: 100 trials per configuration (baseline: 1000 as specified)

## Project layout

```
config/default.yaml
drsrs/{models,simulation,analysis,viz,main.py}
docs/{CORRECTIONS.md,FINAL_SUMMARY.md,architecture_diagram.txt}
outputs/{figures,tables,reports}/
tests/test_models.py
requirements.txt
README.md
```

## How to reproduce

```bash
cd "/home/user/Desktop/Project stuff/M_and_S"
source .venv/bin/activate
pip install -r requirements.txt
python -m drsrs.main          # full (~hours on 4 cores)
python -m drsrs.main --quick  # smoke test
pytest tests/ -q
```

Paste `outputs/reports/chapter_4_8_results.md` (or the DOCX) into the group
report wherever it says “Insert results here”.

## Remaining limitations

- Exponential (not Weibull) lifetimes; no disaster clustering; no cost model;
  no cyber common-mode failure (§5.2 of the report).
- Baseline P_loss ≈ 10⁻⁷/year is too rare to observe in 1000×5×16 shard-years
  (expected ≪ 1 event); durability claims rest on analytics + k2=0 vs k2≥1
  sensitivity contrast, which is strong and consistent with §4.5.

## Recommendation (aligned with Chapter 5)

Adopt **k1=2**, **≥1 regional async replica**, **k2≥1 cloud DR**, **3-node
Raft quorum**, and keep ρ comfortably below 1.
