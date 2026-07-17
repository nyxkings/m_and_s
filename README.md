# Disaster-Resilient Student Record System (DRSRS)
# CSC 508 Modelling and Simulation — Group Project Implementation

Python package that implements the architecture, mathematical models, and
Monte Carlo / discrete-event simulation described in the CSC 508 Group 1
report for a sharded, multi-region, hybrid-cloud student record database.

## Features

- **Architecture:** consistent-hash sharding, multi-level replication
  (campus sync, regional async, cloud DR), Raft-style quorum coordinators
- **Analytical models (Chapter 4):** node/shard/system availability, quorum
  reliability, correlated-domain data-loss probability, M/M/c (Erlang-C) queueing
- **Simulation (Section 3.5):** SimPy DES with exponential failure/repair,
  campus disaster events, cloud outages, request latency sampling, 1000-trial Monte Carlo
- **Sensitivity analysis** over k1, k2, and λ_d
- **Verification** against closed-form limits (Section 4.9)
- **Publication outputs:** figures, CSV tables, Chapter 4.8 results markdown/DOCX

## Project layout

```
M_and_S/
├── config/default.yaml          # All simulation parameters
├── drsrs/
│   ├── models/                  # Analytical models + topology
│   ├── simulation/              # SimPy Monte Carlo engine
│   ├── analysis/                # V&V, sensitivity, reporting
│   ├── viz/                     # Matplotlib figures
│   ├── config.py
│   └── main.py                  # CLI entry point
├── docs/CORRECTIONS.md          # Report issues found and fixes
├── tests/
├── outputs/{figures,tables,reports}/
├── requirements.txt
└── README.md
```

## Setup

```bash
cd "/home/user/Desktop/Project stuff/M_and_S"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# Full campaign (1000 trials × 5 years + sensitivity + verification)
python -m drsrs.main

# Quick smoke test
python -m drsrs.main --quick

# Verification only
python -m drsrs.main --verify-only

# Custom trials / horizon
python -m drsrs.main --trials 200 --years 3

# Unit tests
pytest tests/ -q
```

## Key parameters (Table 3.2)

| Parameter | Default |
|-----------|---------|
| MTTF / MTTR | 2000 h / 2 h |
| k1 / regional / k2 | 2 / 1 / 1 |
| λ_d | 0.05 /year |
| Disaster duration | 48 h mean |
| N shards | 16 |
| λ, μ, c | 50 req/s, 20 /s/thread, 4 threads |
| Trials × years | 1000 × 5 |

See `docs/CORRECTIONS.md` for report inconsistencies (μ labelling, P_loss formula)
and the modelling decisions taken.

## Outputs

After a successful run:

- `outputs/figures/` — availability, reliability, latency, data-loss, sensitivity plots
- `outputs/tables/` — CSV summaries including Tables 4.1/4.2 style and trial data
- `outputs/reports/chapter_4_8_results.md` — replacement text for report placeholders
- `data/monte_carlo_summary.json` — machine-readable summary

## Licence

Coursework artefact for CSC 508, Federal University of Technology, Akure.
