"""Publication-quality plotting for DRSRS simulation outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from drsrs.analysis.sensitivity import SensitivityTables
from drsrs.models import (
    AnalyticalSummary,
    erlang_c_p_wait,
    mean_response_time,
    utilisation,
)
from drsrs.simulation import MonteCarloResults

# Visual style: academic, clean, not generic AI-purple
plt.rcParams.update(
    {
        "figure.dpi": 140,
        "savefig.dpi": 200,
        "font.family": "DejaVu Sans",
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
    }
)

COLOUR_A = "#0B3D5C"
COLOUR_B = "#C45C26"
COLOUR_C = "#2E7D4F"
COLOUR_D = "#6B4C9A"


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_availability_histogram(mc: MonteCarloResults, out: Path) -> Path:
    arr = mc.to_arrays()["availability"]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.hist(arr * 100, bins=30, color=COLOUR_A, edgecolor="white", alpha=0.9)
    ax.axvline(np.mean(arr) * 100, color=COLOUR_B, linestyle="--", label=f"Mean = {np.mean(arr)*100:.4f}%")
    ax.set_xlabel("System availability (%)")
    ax.set_ylabel("Number of Monte Carlo trials")
    ax.set_title("Empirical system availability across Monte Carlo trials")
    ax.legend()
    return _save(fig, out / "availability_histogram.png")


def plot_availability_boxplot(mc: MonteCarloResults, out: Path) -> Path:
    arr = mc.to_arrays()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    data = [arr["availability"] * 100, arr["quorum_availability"] * 100, arr["shard_availability_mean"] * 100]
    bp = ax.boxplot(data, tick_labels=["System", "Quorum", "Mean shard"], patch_artist=True)
    colours = [COLOUR_A, COLOUR_C, COLOUR_B]
    for patch, c in zip(bp["boxes"], colours):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)
    ax.set_ylabel("Availability (%)")
    ax.set_title("Availability distributions (system, quorum, shard)")
    return _save(fig, out / "availability_boxplot.png")


def plot_reliability_over_replicas(out: Path) -> Path:
    """Closed-form A_shard vs k (Table 4.1 style, using report A=0.990)."""
    a = 0.990
    ks = np.arange(1, 7)
    a_sh = 1 - (1 - a) ** ks
    downtime_h = (1 - a_sh) * 8760
    fig, ax1 = plt.subplots(figsize=(7.5, 4.5))
    ax1.plot(ks, a_sh, "o-", color=COLOUR_A, label="A_shard")
    ax1.set_xlabel("Number of replicas k")
    ax1.set_ylabel("Shard availability A_shard")
    ax1.set_ylim(0.989, 1.0001)
    ax2 = ax1.twinx()
    ax2.plot(ks, downtime_h, "s--", color=COLOUR_B, label="Downtime h/year")
    ax2.set_ylabel("Approx. downtime (hours/year)")
    ax2.set_yscale("log")
    ax1.set_title("Effect of replication factor on shard availability (A = 0.990)")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="center right")
    return _save(fig, out / "reliability_vs_replicas.png")


def plot_data_loss_sensitivity(sens: SensitivityTables, out: Path) -> Path:
    df = sens.by_k1_k2
    fig, ax = plt.subplots(figsize=(8, 5))
    for k2, g in df.groupby("k2"):
        ax.semilogy(
            g["k1"],
            np.maximum(g["data_loss_rate_mean"], 1e-16),
            "o-",
            label=f"k2 = {k2} (simulated)",
        )
        ax.semilogy(
            g["k1"],
            np.maximum(g["p_loss_analytical"], 1e-16),
            "s--",
            alpha=0.7,
            label=f"k2 = {k2} (analytical)",
        )
    ax.set_xlabel("On-campus replicas k1")
    ax.set_ylabel("Data-loss rate / probability (per shard·year)")
    ax.set_title("Sensitivity of data-loss risk to k1 and k2")
    ax.legend(ncol=2, fontsize=8)
    return _save(fig, out / "data_loss_sensitivity.png")


def plot_data_loss_analytical(sens: SensitivityTables, out: Path) -> Path:
    df = sens.analytical_loss
    fig, ax = plt.subplots(figsize=(8, 5))
    for k2, g in df.groupby("k2"):
        ax.semilogy(g["k1"], g["P_loss_correlated"], "o-", label=f"Correlated model, k2={k2}")
    ax.set_xlabel("On-campus replicas k1")
    ax.set_ylabel("P_loss (correlated-domain model)")
    ax.set_title("Analytical permanent data-loss probability (Section 4.5)")
    ax.legend()
    return _save(fig, out / "data_loss_analytical.png")


def plot_lambda_d_sensitivity(sens: SensitivityTables, out: Path) -> Path:
    df = sens.by_lambda_d
    fig, ax1 = plt.subplots(figsize=(7.5, 4.5))
    ax1.plot(df["lambda_d"], df["availability_mean"] * 100, "o-", color=COLOUR_A)
    ax1.set_xlabel("Disaster rate λ_d (events/year)")
    ax1.set_ylabel("System availability (%)", color=COLOUR_A)
    ax2 = ax1.twinx()
    ax2.semilogy(df["lambda_d"], np.maximum(df["data_loss_rate_mean"], 1e-16), "s--", color=COLOUR_B)
    ax2.set_ylabel("Data-loss rate (per shard·year)", color=COLOUR_B)
    ax1.set_title("Sensitivity to campus disaster frequency λ_d")
    return _save(fig, out / "lambda_d_sensitivity.png")


def plot_latency_distribution(mc: MonteCarloResults, out: Path) -> Path:
    # Aggregate per-trial mean response
    means = mc.to_arrays()["mean_response_ms"]
    slo = mc.to_arrays()["slo_fraction"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    axes[0].hist(means, bins=25, color=COLOUR_A, edgecolor="white")
    axes[0].set_xlabel("Mean response time (ms)")
    axes[0].set_ylabel("Trials")
    axes[0].set_title("Per-trial mean response time")
    axes[1].hist(slo * 100, bins=25, color=COLOUR_C, edgecolor="white")
    axes[1].set_xlabel("Requests within 200 ms SLO (%)")
    axes[1].set_ylabel("Trials")
    axes[1].set_title("SLO attainment distribution")
    return _save(fig, out / "latency_distribution.png")


def plot_queueing_vs_load(out: Path, mu: float = 20.0, c: int = 4) -> Path:
    """Erlang-C P_wait and mean response vs arrival rate λ."""
    lambdas = np.linspace(10, 75, 40)
    pwaits = []
    resps = []
    rhos = []
    for lam in lambdas:
        rhos.append(utilisation(lam, mu, c))
        pwaits.append(erlang_c_p_wait(lam, mu, c))
        r = mean_response_time(lam, mu, c)
        resps.append(r * 1000 if np.isfinite(r) else np.nan)
    fig, ax1 = plt.subplots(figsize=(7.5, 4.5))
    ax1.plot(lambdas, pwaits, color=COLOUR_A, label="P_wait (Erlang-C)")
    ax1.axvline(50, color="grey", linestyle=":", label="Design λ = 50 req/s")
    ax1.set_xlabel("Arrival rate λ (req/s)")
    ax1.set_ylabel("P(wait > 0)")
    ax2 = ax1.twinx()
    ax2.plot(lambdas, resps, color=COLOUR_B, linestyle="--", label="Mean response (ms)")
    ax2.set_ylabel("Mean response time (ms)")
    ax1.set_title(f"M/M/c queueing behaviour (c={c}, μ={mu} req/s)")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    return _save(fig, out / "queueing_vs_load.png")


def plot_utilisation_heatmap(sens: SensitivityTables, out: Path) -> Path:
    """Availability heatmap over k1 × k2."""
    df = sens.by_k1_k2
    pivot = df.pivot(index="k2", columns="k1", values="availability_mean")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    im = ax.imshow(pivot.values * 100, aspect="auto", cmap="YlGn", origin="lower")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("k1 (campus replicas)")
    ax.set_ylabel("k2 (cloud replicas)")
    ax.set_title("Simulated system availability (%) vs replica placement")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Availability (%)")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            ax.text(j, i, f"{pivot.values[i, j]*100:.3f}", ha="center", va="center", fontsize=8)
    return _save(fig, out / "availability_heatmap.png")


def plot_analytical_vs_simulated(
    analytical: AnalyticalSummary,
    mc: MonteCarloResults,
    out: Path,
    a_network: float = 0.9995,
    a_app: float = 0.999,
) -> Path:
    sim = mc.summary()
    db_sim = sim["availability_mean"]
    e2e_sim = a_network * a_app * db_sim
    labels = ["A_node", "A_db / A_shard", "A_system (e2e)", "A_quorum", "SLO frac"]
    ana_vals = [
        analytical.a_node,
        analytical.a_shard_independent,
        analytical.a_system,
        analytical.a_quorum,
        analytical.slo_fraction,
    ]
    sim_vals = [
        analytical.a_node,
        db_sim,
        e2e_sim,
        sim["quorum_availability_mean"],
        sim["slo_fraction_mean"],
    ]
    x = np.arange(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(x - w / 2, ana_vals, w, label="Analytical", color=COLOUR_A)
    ax.bar(x + w / 2, sim_vals, w, label="Simulated / composed", color=COLOUR_B)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("Probability / fraction")
    ax.set_ylim(0.990, 1.001)
    ax.set_title("Analytical vs simulated metrics (baseline DRSRS)")
    ax.legend()
    return _save(fig, out / "analytical_vs_simulated.png")


def generate_all_figures(
    mc: MonteCarloResults,
    sens: SensitivityTables,
    analytical: AnalyticalSummary,
    figures_dir: Path,
    a_network: float = 0.9995,
    a_app: float = 0.999,
) -> list[Path]:
    paths = [
        plot_availability_histogram(mc, figures_dir),
        plot_availability_boxplot(mc, figures_dir),
        plot_reliability_over_replicas(figures_dir),
        plot_data_loss_sensitivity(sens, figures_dir),
        plot_data_loss_analytical(sens, figures_dir),
        plot_lambda_d_sensitivity(sens, figures_dir),
        plot_latency_distribution(mc, figures_dir),
        plot_queueing_vs_load(figures_dir),
        plot_utilisation_heatmap(sens, figures_dir),
        plot_analytical_vs_simulated(analytical, mc, figures_dir, a_network, a_app),
    ]
    return paths
