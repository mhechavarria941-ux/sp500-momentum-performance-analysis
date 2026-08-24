# H2 Preregistration — Sector-Relative 12-1 Momentum

**Status:** PREREGISTERED — DO NOT INSPECT H2 PERFORMANCE RESULTS UNTIL THIS SPECIFICATION IS COMMITTED  
**Analytical window:** 2021-01 through 2025-12  
**Lookback support:** 2020 data are support only and never become ranking-universe observations  
**Ranking dates:** exact month-end trading dates already used by the corrected H1 pipeline  
**Universe:** point-in-time S&P 500 membership only  
**Sector classification:** validated point-in-time GICS sector assignment

## 1. Data prerequisite closed

The point-in-time GICS quality gate passed before any H2 return results were inspected.

Validated GICS state:

- 593 membership security identities.
- 593 identities have continuous, non-overlapping GICS intervals.
- 613 GICS interval rows, representing 20 authoritative sector transitions.
- 0 interval overlaps.
- 0 interval gaps.
- 0 unresolved initial-sector identities.
- 0 unexplained in-membership sector-evidence mismatches.
- 30,211 ranking-date security rows.
- 30,211 ranking-date GICS assignments.
- 0 missing ranking-date sector assignments.
- 0 duplicate security-month assignments.
- 60 ranking months.
- All 11 canonical GICS sectors present in every ranking month.
- 13 audited residual identity overrides.
- 1 audited official membership-event GICS correction.
- Remaining unmapped SEC ETF rows are retained for source audit only and do not affect completeness of the project ranking universe.

Canonical local H2 sector input:

`data/interim/security_gics_sector_month_end_2021_2025.csv`

Canonical permanent sector-history input:

`data/reference/gics/security_gics_sector_intervals_2021_2025.csv`

## 2. Hypothesis

**H2 — Sector-relative momentum**

Stocks with stronger 12-1 momentum relative to other stocks in their own point-in-time GICS sector subsequently earn higher one-month returns than stocks with weaker sector-relative momentum.

The economic idea is that conditioning momentum on sector removes part of the broad industry/sector trend embedded in raw cross-sectional momentum and may isolate a cleaner stock-selection effect.

## 3. Signal definition

The signal is identical to the corrected H1 12-1 signal.

For security *i* ranked at month-end *t*:

`MOM12_1(i,t) = price(i,t-1) / price(i,t-12) - 1`

where `t-1` is the prior month-end and `t-12` is the month-end twelve months before the ranking month.

The ranking month itself is skipped. No price from after the ranking date may enter the signal.

The existing corrected H1 feature-support rules, security-price eligibility rules, and incomplete-history exclusions remain unchanged.

## 4. Ranking universe and sector assignment

For each ranking month:

1. Start from the exact point-in-time S&P 500 ranking universe already validated for H1.
2. Join each security to exactly one point-in-time GICS sector using the validated monthly GICS assignment.
3. Exclude only observations that fail the existing H1 12-1 signal-completeness rule.
4. Do not substitute current constituents or current sectors for historical observations.

Each sector-month must contain at least five eligible securities. If any sector-month has fewer than five eligible securities, the pipeline stops for review rather than silently changing the grouping rule.

## 5. Within-sector portfolio formation

Within each `(ranking_month, gics_sector)` partition, securities are ordered by:

1. `momentum_12_1 ASC`
2. `security_key ASC` as a deterministic tie-break only

Quintiles are assigned with the equivalent of:

`NTILE(5) OVER (PARTITION BY ranking_month, gics_sector ORDER BY momentum_12_1 ASC, security_key ASC)`

Definitions:

- **Q1 / Losers:** bottom 20% of the sector.
- **Q5 / Winners:** top 20% of the sector.
- Q2-Q4 are retained for diagnostics and monotonicity checks but are not part of the primary H2 spread.

Exact signal ties are not averaged across boundaries; `security_key` is used only to make the preregistered assignment deterministic.

## 6. Holding-period return

Portfolios are formed at ranking month-end *t* and held for the next one-month period, *t* to *t+1*.

Security forward-return availability and censoring rules are identical to H1.

The 2025-12 ranking is retained for ranking diagnostics but excluded from realized-return inference if the required 2026-01 forward return is unavailable.

## 7. Sector sleeve construction

For each sector and month:

- Winner-sector return = equal-weight mean of forward returns for Q5 securities.
- Loser-sector return = equal-weight mean of forward returns for Q1 securities.
- Sector winner-minus-loser return = Winner-sector return − Loser-sector return.

No market-cap weighting is used.

## 8. Aggregate sector-neutral portfolio

To prevent large sectors from dominating H2, each of the 11 sectors receives equal influence.

For month *t*:

- Aggregate Winner = arithmetic mean of the 11 sector Winner returns.
- Aggregate Loser = arithmetic mean of the 11 sector Loser returns.
- **Aggregate W-L = Aggregate Winner − Aggregate Loser.**

Thus each sector contributes `1/11` of each aggregate sleeve regardless of its number of constituents.

A return month is valid only if all 11 sector sleeves required for that statistic are available.

## 9. Primary confirmatory test

The primary H2 outcome is the time-series mean monthly return of the **aggregate sector-neutral Winner-minus-Loser portfolio**.

Primary null:

`H0: E[W-L] = 0`

Primary alternative:

`H1: E[W-L] != 0`

Inference remains **two-sided**, matching H1 and preventing a post-hoc switch to a one-sided test.

The preregistered primary significance test is the intercept test with **HAC/Newey-West covariance using lag 3**, at `alpha = 0.05`.

For the directional H2 claim to be supported:

1. the estimated mean W-L must be positive; and
2. the two-sided HAC(3) p-value must be `< 0.05`.

If either condition fails, the primary H2 directional hypothesis is not supported.

## 10. Robustness inference

The following are reported using the same implementation conventions as H1:

- ordinary one-sample t-test;
- bootstrap 95% confidence interval for mean monthly W-L;
- Wilcoxon signed-rank test;
- sign test;
- HAC(3) intercept test.

These are robustness evidence. They do not replace the preregistered primary HAC(3) decision rule.

## 11. Sector-level secondary tests

For each of the 11 GICS sectors, report:

- mean monthly Winner return;
- mean monthly Loser return;
- mean monthly W-L;
- annualized return;
- volatility;
- Sharpe ratio;
- maximum drawdown;
- proportion of months with positive W-L;
- HAC(3) p-value.

The 11 sector-level W-L significance tests form one multiple-testing family and will use **Holm adjustment**.

Sector-level results are secondary and cannot rescue a failed aggregate primary test.

## 12. Monotonicity diagnostics

For each sector and for the sector-neutral aggregate, report Q1 through Q5 forward returns.

Diagnostics include:

- Q5 − Q1 spread;
- number of adjacent quintile increases;
- rank correlation between quintile number and mean return.

These are descriptive robustness checks, not alternative primary hypotheses.

## 13. Benchmark comparisons

SPY and the project S&P 500 benchmark series will be reported for context.

Aggregate Winner versus SPY and S&P 500 comparisons are secondary because H2's primary test is the internally sector-neutral W-L spread rather than benchmark outperformance.

No benchmark comparison replaces the primary W-L test.

## 14. Risk-adjusted analysis

Reuse the H1 risk framework without modification:

- DGS1MO as the no-lookahead risk-free input;
- annualized Sharpe ratios;
- CAPM alpha and beta using SPY excess return as the market factor;
- HAC(3) inference for CAPM intercepts.

Primary emphasis remains on aggregate W-L; risk-adjusted results are secondary robustness evidence.

## 15. Turnover and implementation costs

Portfolio weights are formed from the equal-weight stock sleeves and equal-weight 11-sector aggregation.

One-way turnover is:

`0.5 * SUM(abs(w_i,t - w_i,t-1))`

after aligning securities across consecutive portfolios.

For W-L, trading costs apply to both the Winner and Loser legs.

Transaction-cost scenarios:

- 5 bps per unit of one-way turnover;
- 10 bps;
- 20 bps.

Short-borrow scenarios applied to the Loser leg:

- 0 bps annualized;
- 50 bps;
- 100 bps;
- 200 bps.

Monthly borrow cost is annual borrow bps divided by 12 and applied to the unit short notional.

The exact H1 convention for initial formation/rebalancing treatment will be reused so H1 and H2 remain directly comparable.

## 16. Economic robustness / concentration

In addition to the primary significance rule, report:

- cumulative and annualized gross W-L;
- cumulative and annualized net W-L under every cost/borrow scenario;
- sector contribution to cumulative W-L;
- 11 leave-one-sector-out aggregate W-L series.

A result is considered broadly cross-sector rather than sector-concentrated if:

- at least 9 of 11 leave-one-sector-out mean W-L estimates remain positive; and
- no single sector contributes more than 50% of cumulative gross aggregate W-L.

Failure of this concentration test does not change the primary statistical p-value, but any positive primary result will be labeled **sector-concentrated / qualified** rather than broad H2 support.

For implementation robustness, the preregistered base-case net scenario is:

- 10 bps one-way transaction cost;
- 100 bps annualized borrow cost on the Loser leg.

If gross H2 passes statistically but base-case net W-L is non-positive, report it as **statistically supported gross, not cost-robust**.

## 17. Decision labels

Use exactly these interpretation classes:

- **SUPPORTED — BROAD AND COST-ROBUST:** positive W-L, HAC(3) p < 0.05, positive base-case net performance, and concentration criterion passes.
- **SUPPORTED — QUALIFIED:** positive W-L with HAC(3) p < 0.05, but either cost robustness or cross-sector concentration criterion fails.
- **NOT SUPPORTED:** mean W-L <= 0 or HAC(3) p >= 0.05.
- **INVALID / REVIEW REQUIRED:** a preregistered data-quality, portfolio-construction, or forward-return gate fails.

Do not relabel a statistically insignificant positive result as support based on secondary tests.

## 18. Anti-data-mining constraints

Before viewing H2 results:

- do not change quintile breakpoints;
- do not change the 12-1 signal;
- do not remove sectors because of performance;
- do not change equal sector weighting;
- do not change HAC lag, alpha, or two-sided inference;
- do not tune the cost grid;
- do not substitute another sample window;
- do not use H2 results to revise H1.

Any later alternative specification must be labeled exploratory and reported separately from this preregistered H2.

## 19. Planned post-H2 exploratory work

Only after the preregistered H2 analysis is completed and labeled:

- winner persistence across sectors;
- synchronous winner months;
- correlations after removing SPY and own-sector returns;
- common characteristics/themes among sector winners;
- possible cross-sector commonality factor based on residual winner returns;
- later social/cultural attention analysis under a separately preregistered H3.

These analyses cannot modify the H2 confirmatory conclusion.
