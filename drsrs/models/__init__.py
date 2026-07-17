"""Analytical reliability, availability, quorum, data-loss, and queueing models.

Implements every closed-form equation from Chapter 4 of the DRSRS report.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.special import factorial


# ---------------------------------------------------------------------------
# 4.1 Component availability
# ---------------------------------------------------------------------------

def node_availability(mttf: float, mttr: float) -> float:
    """A = MTTF / (MTTF + MTTR)."""
    if mttf + mttr <= 0:
        raise ValueError("MTTF + MTTR must be positive")
    return mttf / (mttf + mttr)


# ---------------------------------------------------------------------------
# 4.2 Replicated shard availability (independent failures)
# ---------------------------------------------------------------------------

def shard_availability(a_node: float, k: int) -> float:
    """A_shard = 1 − (1 − A)^k  for k independent replicas."""
    if k < 0:
        raise ValueError("k must be non-negative")
    if k == 0:
        return 0.0
    return 1.0 - (1.0 - a_node) ** k


# ---------------------------------------------------------------------------
# 4.3 Series system availability
# ---------------------------------------------------------------------------

def series_availability(*availabilities: float) -> float:
    """A_series = ∏ A_i."""
    result = 1.0
    for a in availabilities:
        result *= a
    return result


def system_availability(
    a_network: float,
    a_app: float,
    a_shard: float,
) -> float:
    """A_system = A_network × A_app × A_shard."""
    return series_availability(a_network, a_app, a_shard)


# ---------------------------------------------------------------------------
# 4.4 Quorum (binomial) availability
# ---------------------------------------------------------------------------

def binomial_coeff(n: int, i: int) -> int:
    """C(n, i) = n! / (i!(n−i)!)."""
    return math.comb(n, i)


def quorum_availability(a_node: float, n: int) -> float:
    """A_quorum = Σ_{i=m}^{n} C(n,i) A^i (1−A)^{n−i},  m = ⌊n/2⌋ + 1."""
    if n < 1:
        raise ValueError("n must be ≥ 1")
    m = n // 2 + 1
    total = 0.0
    for i in range(m, n + 1):
        total += binomial_coeff(n, i) * (a_node**i) * ((1.0 - a_node) ** (n - i))
    return total


# ---------------------------------------------------------------------------
# 4.5 Permanent data-loss probability
# ---------------------------------------------------------------------------

def data_loss_independent(p: float, k: int) -> float:
    """P_loss = p^k  (fully independent replica failures)."""
    return p**k if k > 0 else 1.0


def data_loss_correlated(
    p1_campus: float,
    p2_cloud: float,
    k1: int,
    k2: int,
    *,
    treat_campus_as_correlated: bool = True,
) -> float:
    """Permanent data-loss probability under hybrid-cloud domains.

    CORRECTION (see docs/CORRECTIONS.md):
    Report prose (Section 4.5) states that correlated on-campus replicas fail
    together under a campus disaster, so P_loss ≈ p1 when k2=0 regardless of
    k1, and P_loss = p1 × p2^{k2} when cloud replicas fail independently.

    Table 4.2 incorrectly applies P_loss = p1^{k1} × p2^{k2} for hybrid rows,
    which contradicts the correlated-failure narrative. We implement the
    academically correct correlated-domain model:

        P_loss = p1 × p2^{k2}     if treat_campus_as_correlated (default)
        P_loss = p1^{k1} × p2^{k2} if treat_campus_as_correlated is False
                                   (report Table 4.2 formula, for comparison)
    """
    if treat_campus_as_correlated:
        # One campus disaster destroys all k1 co-located replicas.
        campus_term = p1_campus if k1 > 0 else 1.0
        cloud_term = (p2_cloud**k2) if k2 > 0 else 1.0
        if k1 == 0 and k2 == 0:
            return 1.0
        if k1 == 0:
            return cloud_term
        if k2 == 0:
            return campus_term
        return campus_term * cloud_term
    # Independent (Table 4.2 hybrid formula)
    campus_term = (p1_campus**k1) if k1 > 0 else 1.0
    cloud_term = (p2_cloud**k2) if k2 > 0 else 1.0
    return campus_term * cloud_term


# ---------------------------------------------------------------------------
# 4.7 M/M/c queueing model (Erlang-C)
# ---------------------------------------------------------------------------

def utilisation(lam: float, mu: float, c: int) -> float:
    """ρ = λ / (c μ). Must be < 1 for stability."""
    if c <= 0 or mu <= 0:
        raise ValueError("c and μ must be positive")
    return lam / (c * mu)


def erlang_c_p0(lam: float, mu: float, c: int) -> float:
    """Steady-state idle probability P0 for an M/M/c queue."""
    rho = utilisation(lam, mu, c)
    if rho >= 1.0:
        return 0.0
    a = lam / mu  # offered load in Erlangs
    s = sum(a**k / float(factorial(k, exact=True)) for k in range(c))
    last = (a**c / float(factorial(c, exact=True))) * (1.0 / (1.0 - rho))
    return 1.0 / (s + last)


def erlang_c_p_wait(lam: float, mu: float, c: int) -> float:
    """P_wait = [(cρ)^c / (c! (1−ρ))] × P0  (Erlang-C formula)."""
    rho = utilisation(lam, mu, c)
    if rho >= 1.0:
        return 1.0
    p0 = erlang_c_p0(lam, mu, c)
    a = lam / mu
    return ((a**c) / (float(factorial(c, exact=True)) * (1.0 - rho))) * p0


def mean_queue_wait(lam: float, mu: float, c: int) -> float:
    """Mean waiting time in queue W_q = P_wait / (cμ − λ) seconds."""
    rho = utilisation(lam, mu, c)
    if rho >= 1.0:
        return float("inf")
    pw = erlang_c_p_wait(lam, mu, c)
    return pw / (c * mu - lam)


def mean_response_time(lam: float, mu: float, c: int) -> float:
    """W = W_q + 1/μ  (seconds)."""
    wq = mean_queue_wait(lam, mu, c)
    if math.isinf(wq):
        return float("inf")
    return wq + 1.0 / mu


def fraction_within_slo(
    lam: float,
    mu: float,
    c: int,
    slo_seconds: float,
) -> float:
    """Approximate P(W ≤ SLO) for M/M/c using exponential tail of waiting time.

    Waiting time has P(W_q = 0) = 1 − P_wait and an exponential residual for
    the waiting portion. Response time = W_q + S, S ~ Exp(μ).
    We use a Monte-Carlo-free closed approximation:
      P(W ≤ t) ≈ 1 − P_wait · exp(−(cμ − λ) · max(0, t − 1/μ))
    for t ≥ 1/μ, else integrate service+wait conservatively via simulation
    helper; here we provide the standard Erlang-C waiting-time CDF for W_q
    and fold in mean service as a lower bound check.
    """
    # Exact waiting-time CDF for W_q, then convolve approximately with Exp(μ).
    # Practical approach used in the report context: simulate analytically via
    # P(W_q ≤ max(0, t)) and require service 1/μ << t.
    rho = utilisation(lam, mu, c)
    if rho >= 1.0:
        return 0.0
    pw = erlang_c_p_wait(lam, mu, c)
    # CDF of W_q: F(t) = 1 − P_wait · exp(−(cμ−λ)t) for t ≥ 0
    # Response W = W_q + S. Use numerical convolution on a fine grid.
    # For publication quality we integrate:
    # P(W_q + S ≤ t) = ∫_0^t f_S(s) F_{Wq}(t−s) ds
    n = 2000
    dt = slo_seconds / n
    # Precompute F_Wq
    rate = c * mu - lam

    def f_wq_cdf(t: float) -> float:
        if t < 0:
            return 0.0
        return 1.0 - pw * math.exp(-rate * t)

    prob = 0.0
    for i in range(n):
        s = (i + 0.5) * dt
        # density of Exp(μ): μ e^{−μs}
        dens = mu * math.exp(-mu * s)
        prob += dens * f_wq_cdf(slo_seconds - s) * dt
    return max(0.0, min(1.0, prob))


@dataclass
class AnalyticalSummary:
    """Closed-form metrics for the baseline DRSRS configuration."""

    a_node: float
    a_shard_independent: float
    a_system: float
    a_quorum: float
    p_loss_correlated: float
    p_loss_table42_formula: float
    rho: float
    p_wait: float
    mean_wait_ms: float
    mean_response_ms: float
    slo_fraction: float


def compute_analytical_baseline(
    mttf: float,
    mttr: float,
    k_independent: int,
    a_network: float,
    a_app: float,
    n_coord: int,
    p1: float,
    p2: float,
    k1: int,
    k2: int,
    lam: float,
    mu: float,
    c: int,
    slo_ms: float,
) -> AnalyticalSummary:
    """Compute all Chapter-4 closed-form metrics for the baseline design."""
    a = node_availability(mttf, mttr)
    a_sh = shard_availability(a, k_independent)
    a_sys = system_availability(a_network, a_app, a_sh)
    a_q = quorum_availability(a, n_coord)
    pl_corr = data_loss_correlated(p1, p2, k1, k2, treat_campus_as_correlated=True)
    pl_tbl = data_loss_correlated(p1, p2, k1, k2, treat_campus_as_correlated=False)
    rho = utilisation(lam, mu, c)
    pw = erlang_c_p_wait(lam, mu, c)
    wq = mean_queue_wait(lam, mu, c)
    wr = mean_response_time(lam, mu, c)
    slo = fraction_within_slo(lam, mu, c, slo_ms / 1000.0)
    return AnalyticalSummary(
        a_node=a,
        a_shard_independent=a_sh,
        a_system=a_sys,
        a_quorum=a_q,
        p_loss_correlated=pl_corr,
        p_loss_table42_formula=pl_tbl,
        rho=rho,
        p_wait=pw,
        mean_wait_ms=wq * 1000.0,
        mean_response_ms=wr * 1000.0,
        slo_fraction=slo,
    )
