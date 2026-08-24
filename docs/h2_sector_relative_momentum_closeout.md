# H2 Sector-Relative Momentum Closeout

**Date:** 2026-08-24

## Hypothesis

Stocks with stronger corrected 12-1 momentum relative to stocks in their own point-in-time GICS sector subsequently outperform weaker sector-relative stocks over the next month.

## Frozen Primary Construction

- 2021-2025 point-in-time S&P 500 universe
- corrected 12-1 momentum signal
- point-in-time GICS sector assignment
- deterministic within-sector quintiles
- Q1 = losers
- Q5 = winners
- equal-weight stocks within each sector sleeve
- equal-weight aggregation across all 11 sectors
- one-month forward holding period
- primary return = aggregate sector-neutral Winner minus Loser

## Validation State Before Inference

The H2 ranking and weighting layer passed its independent integrity audit before forward returns were constructed.

The H2 forward-return population then passed a separate independent integrity audit before inference.

Validated performance population:

- 30,121 H2 security assignments
- 29,620 complete security forward returns
- 501 December-2025 right-censored security rows
- 3,300 sector/quintile rows
- 3,245 complete sector/quintile rows
- 1,320 Winner/Loser sector rows
- 1,298 complete Winner/Loser sector rows
- 120 aggregate sector-neutral Winner/Loser legs
- 118 complete aggregate legs
- 60 aggregate W-L rows
- 59 complete observable W-L months
- only analysis month 60 right-censored
- Azure SQL core rows modified: 0

## Primary Confirmatory Result

Aggregate sector-neutral Winner-minus-Loser:

- mean monthly W-L: **+0.186%**
- arithmetic annualized mean: **+2.237%**
- gross compounded wealth: **1.0814**
- geometric annualized return: **+1.605%**
- annualized volatility: **11.399%**
- maximum drawdown: **-13.234%**

Primary frozen inference:

- HAC / Newey-West lag: **3**
- two-sided alpha: **0.05**
- HAC z: **0.5182**
- HAC p-value: **0.6043**

Primary decision rule:

Support required both a positive W-L estimate and two-sided HAC(3) p < 0.05.

The estimate was positive, but the HAC p-value was far above 0.05.

**Primary rule: FAIL**

## Supporting Statistical Evidence

- classical one-sample t-test: t = 0.4352, p = 0.6650
- 50,000-replication bootstrap 95% CI: **[-0.654%, +0.997%] per month**
- Wilcoxon signed-rank p = 0.4504
- sign test: 33 positive months, 26 negative months, p = 0.4350

All four secondary inferential checks are consistent with the primary result: the positive point estimate is not statistically distinguishable from zero in this sample.

## Sector-Level Evidence

No individual GICS sector produced a statistically significant W-L effect after the preregistered 11-test Holm correction.

All Holm-adjusted p-values were **1.0000**.

Positive mean sector spreads were observed in:

- Communication Services: +1.040% monthly
- Consumer Staples: +0.682%
- Energy: +0.917%
- Information Technology: +0.076%
- Materials: +0.892%
- Real Estate: +0.199%

Negative mean sector spreads were observed in:

- Consumer Discretionary: -0.076%
- Financials: -0.130%
- Health Care: -0.617%
- Industrials: -0.447%
- Utilities: -0.485%

These sector results are descriptive/secondary and do not override the failed aggregate confirmatory test.

## Quintile Monotonicity

Aggregate sector-neutral mean monthly returns:

- Q1: 0.905%
- Q2: 0.952%
- Q3: 0.902%
- Q4: 1.020%
- Q5: 1.091%

Diagnostics:

- Q5 - Q1 mean spread: **+0.186%**
- adjacent quintile increases: **3 of 4**
- Spearman correlation between quintile rank and mean return: **0.700**

This provides some descriptive ordering, but not enough inferential evidence to support H2.

## Risk-Adjusted Context

Annualized gross return / volatility / Sharpe:

- Winner: 12.575% / 15.578% / 0.629
- Loser: 9.482% / 18.980% / 0.397
- W-L: 1.605% / 11.399% / 0.196
- SPY: 14.834% / 15.232% / 0.774
- S&P 500 index: 13.242% / 15.182% / 0.683

Winner active return:

- mean monthly Winner minus SPY: **-0.164%**
- mean monthly Winner minus S&P 500 index: **-0.046%**

CAPM / SPY:

- Winner alpha: -0.094% monthly / -1.123% annualized arithmetic, p = 0.6834, beta = 0.928
- Loser alpha: -0.362% monthly / -4.344% annualized arithmetic, p = 0.3897, beta = 1.012
- W-L alpha: +0.268% monthly / +3.221% annualized arithmetic, p = 0.4601, beta = -0.084

The W-L CAPM alpha is positive but statistically insignificant.

## Turnover and Implementation Costs

Mean one-way target-weight turnover including initial formation:

- Winner: **27.240%**
- Loser: **26.000%**

Gross W-L annualized return: **+1.605%**

Preregistered base case:

- 10 bps transaction cost
- 100 bps annualized loser-leg borrow cost
- net final wealth: **0.9976**
- net annualized return: **-0.049%**

Therefore the gross effect does not survive the preregistered base-case implementation assumptions.

Selected sensitivity:

- 5 bps / 0 borrow: +1.280% annualized
- 5 bps / 100 borrow: +0.272%
- 10 bps / 0 borrow: +0.956%
- 10 bps / 100 borrow: -0.049%
- 20 bps / 0 borrow: +0.311%
- 20 bps / 100 borrow: -0.688%

## Cross-Sector Robustness

Leave-one-sector-out positive mean W-L estimates:

**11 of 11**

This is a useful descriptive sign of breadth.

However, the preregistered concentration test also required no single sector to contribute more than 50% of cumulative gross aggregate arithmetic W-L.

Largest sector contribution:

**50.719%**

Therefore:

**Cross-sector concentration criterion: FAIL**

The threshold miss is narrow, but it was frozen before results and is not relaxed after the fact.

## Final Decision

**H2 FINAL LABEL: NOT SUPPORTED**

Reason:

The primary directional rule failed because the mean sector-neutral W-L was not statistically significant under the preregistered two-sided HAC(3) test.

The conclusion is reinforced rather than rescued by secondary evidence:

- all primary/secondary significance tests fail to reject zero;
- no individual sector survives Holm adjustment;
- the Winner sleeve underperforms SPY and the S&P 500 on average;
- the preregistered base-case net W-L is slightly negative;
- the concentration criterion fails.

At the same time, the positive mean W-L, 3-of-4 monotonic quintile ordering, 11-of-11 positive leave-one-sector-out estimates, and low market beta of W-L are legitimate exploratory signals for follow-up. They cannot alter the H2 conclusion.

## Interpretation Boundary

H2 is closed.

No post-result change to:

- signal definition
- quintile rule
- sector weighting
- sample window
- cost assumptions
- concentration threshold
- significance rule

may be used to relabel H2.

Any subsequent analysis of winner persistence, synchronous winners, residual commonality, company characteristics, or attention/narrative variables is a new exploratory/post-H2 phase and must be labeled separately.

## Final Status

`CLOSED — NOT SUPPORTED IN THE PREREGISTERED 2021-2025 SAMPLE`
