# Corrections and modelling decisions relative to CSC 508 Group 1 report
# =====================================================================

## C1. Service rate μ in Table 3.2 vs Section 4.7

**Issue:** Table 3.2 lists `Service rate per server thread μ = 80 req/s` with
`c = 4` threads, which would give ρ = λ/(cμ) = 50/320 ≈ 0.156.
Section 4.7's worked example clearly states each of c = 4 threads handles
μ = 20 req/s, giving total capacity cμ = 80 and ρ = 0.625.

**Fix:** Use μ = 20 req/s per thread (Section 4.7). Treat Table 3.2's "80"
as the *total* capacity cμ, not the per-thread rate.

## C2. Data-loss formula P_loss = p1^{k1} × p2^{k2} vs correlated narrative

**Issue:** Section 4.5 prose states that co-located campus replicas fail
*together* under a campus disaster, so with k2 = 0, P_loss ≈ p1 regardless
of k1. Worked Example 2 then gives P_loss = p1 × p2 for one cloud replica.
Table 4.2 hybrid rows instead compute p1^{k1} × p2^{k2}
(e.g. 10^{-10} for k1=2, k2=1), which treats campus replicas as independent
and contradicts the same section's narrative (and yields
0.001 × 0.0001 = 10^{-7}, not 10^{-10}, for the worked example).

**Fix:** Implement the correlated-domain model as the primary formula:

    P_loss = p1 × p2^{k2}     (campus disaster destroys all k1 campus copies)

and also compute Table 4.2's independent product for comparison. Simulation
matches the correlated model: a campus disaster force-downs an entire campus
domain; permanent loss is recorded only when *all* replicas of a shard
(including cloud) are simultaneously down.

## C3. Regional (Campus B) replica not in Table 3.2

**Issue:** Section 3.2 Level 2 requires asynchronous replication to a second
campus/region, and Section 5.4 recommends it, but Table 3.2 only lists k1
and k2.

**Fix:** Add `k_regional_replicas = 1` (Campus B) as a documented default
assumption, independent of k1/k2. Disasters can strike Campus A or Campus B
independently at rate λ_d each.

## C4. Cloud failure process unspecified for DES

**Issue:** The report gives p2 = 10^{-4}/year for analytics but does not
specify a DES cloud-outage process.

**Assumption:** Model cloud-region total outages as a Poisson process with
mean rate λ_c = −ln(1 − p2) per year (so P(≥1 outage/year) ≈ p2), and
duration ~ Exp(mean = disaster_duration_mean_hours). Documented as an
engineering assumption.

## C5. Network and application stochastic failures

**Issue:** A_network and A_app appear only in the series product (Section 4.3),
not as DES processes.

**Assumption:** Analytical A_system uses the series product. The DES tracks
database/quorum availability directly; reported "system availability" from
simulation is database-tier reachability (every shard has ≥1 live replica),
which is the metric defined in Section 3.5. Analytical series A_system is
reported alongside for comparison.

## C6. Request sampling over multi-year horizons

**Issue:** λ = 50 req/s × 16 shards × 5 years ≈ 1.3×10^{12} requests — not
feasible to simulate exhaustively.

**Assumption:** Thin the request process so each trial samples ≤ ~15,000
requests, preserving M/M/c statistics while remaining computationally
tractable. Erlang-C closed forms provide the exact steady-state reference.

## C7. Disaster duration distribution

**Issue:** Table 3.2 gives mean duration 48 h without a distribution.

**Assumption:** Exponential with mean 48 h (memoryless, consistent with the
report's exponential failure/repair modelling).

## C8. p1 analytic vs λ_d

**Issue:** Worked examples use p1 = 0.001 while Table 3.2 uses λ_d = 0.05/year.
These are different illustrative numbers.

**Assumption:** DES uses λ_d from Table 3.2. Closed-form P_loss uses
p1_analytic = 0.001 from Section 4.5 worked examples. Sensitivity sweeps
set p1 ≈ 1 − e^{−λ_d} when varying λ_d.
