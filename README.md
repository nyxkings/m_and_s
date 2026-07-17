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

## Requirements

- **Python 3.10+** (developed and tested on **Python 3.12**)
- A local **virtual environment** created with the standard library
  [`venv`](https://docs.python.org/3/library/venv.html) module
  (folder name: `.venv` in the project root)
- Dependencies listed in `requirements.txt` (SimPy, NumPy, Pandas,
  Matplotlib, SciPy, PyYAML, python-docx, pytest, …)

Do **not** run the project with the system `python3` alone — that is what
causes `ModuleNotFoundError: No module named 'numpy'`. Always activate
`.venv` first (or call `.venv/bin/python` directly).

## Setup (create `.venv` and install packages)

From the project root:

```bash
cd "/path/to/M_and_S"

# Create a fresh virtual environment (once)
python3 -m venv .venv

# Activate it
# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
#   .venv\Scripts\Activate.ps1
# Windows (cmd):
#   .venv\Scripts\activate.bat

# Install dependencies into the venv
python -m pip install --upgrade pip
pip install -r requirements.txt
```

When the venv is active, your shell prompt usually shows `(.venv)`, and
`which python` / `where python` should point inside `.venv`.

To leave the venv later: `deactivate`.

**Already have a `.venv`?** Skip `python3 -m venv .venv`, activate it, then
`pip install -r requirements.txt` if packages are missing.

**Without activating** (Linux/macOS), you can still run:

```bash
.venv/bin/python -m drsrs.main --quick
```

## Run

Activate `.venv` first, then:

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


