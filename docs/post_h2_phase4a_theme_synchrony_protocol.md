# Post-H2 Phase 4A — Frozen Exploratory Theme-Synchrony Protocol

## Status

**FROZEN BEFORE THEME-SYNCHRONY STATISTICS ARE INSPECTED**

This phase is exploratory. It does not alter H1 or H2 and does not constitute H3.

## Inputs

1. `reports/exploratory/post_h2_commonality_security_month_contributions.csv`
2. `reports/exploratory/post_h2_winner_commonality_factor.csv`
3. `reports/exploratory/post_h2_phase3d_target_theme_matrix.csv`
4. `reports/exploratory/post_h2_phase3c_frozen_theme_taxonomy.csv`

Frozen taxonomy SHA-256:

`1c7698cbe2facd069c7a12fda41cbf7399a9f657ed4f7a9f956d135f8f9d2576`

## Analysis universe

The security analysis is conditional on the **30 Phase 3A top-driver securities**.

This is important: these 30 were selected because they contributed strongly to post-H2 residual commonality.
Therefore Phase 4A cannot estimate theme prevalence or theme effects for the full S&P 500.

The control population for randomization is the same 30 selected top-driver securities.

## Monthly contribution matrix

For each of the 30 securities, construct a 59-month series:

- use its exact Phase 2 `aggregate_commonality_contribution` when it is a Winner;
- use zero when it is not in the Winner sleeve that month.

This preserves both Winner co-occurrence and signed contribution behavior.

## Structural theme analysis

For each frozen security theme `S01`–`S10`:

### Metric A — contribution synchrony

Calculate the average pairwise Pearson correlation among the 59-month signed
contribution series of all securities assigned to the theme.

Themes with fewer than 3 tagged securities are descriptive only and are not
assigned a randomization p-value.

### Metric B — strong-month clustering

For each month, count how many securities assigned to the theme are active Winners.
Calculate the Pearson correlation between this monthly active-theme count and the
absolute aggregate residual commonality factor.

Themes with fewer than 3 tagged securities are descriptive only.

## Randomization null

For a theme containing `k` securities:

- repeatedly draw `k` securities without replacement from the same frozen 30-security control universe;
- preserve every selected security's exact observed 59-month contribution and Winner-activity history;
- recompute Metric A and Metric B.

Monte Carlo settings:

- replications: **20,000 per tested theme**
- seed: **20260824**
- one-sided p-value for greater-than-null synchrony:
  `(1 + count(null >= observed)) / (B + 1)`

This asks whether the evidence-defined grouping is more synchronized than a random
same-sized grouping of already-selected top-driver securities.

## Multiple testing

Apply Holm correction separately to:

1. Metric A p-values across all tested structural themes.
2. Metric B p-values across all tested structural themes.

Exploratory flag threshold:

- observed statistic must be positive; and
- Holm-adjusted p < 0.05.

The label is:

`UNUSUALLY SYNCHRONIZED WITHIN SELECTED TOP-DRIVER SAMPLE`

It is **not** a causal, predictive, or S&P-500-wide result.

## Secondary descriptive outputs

For every security theme:

- number of tagged securities;
- contribution-series synchrony;
- active-count/commonality correlation;
- variance ratio:
  `Var(sum theme contributions) / sum individual contribution variances`;
- fraction of aggregate absolute commonality contribution associated with tagged
  securities, using Phase 2 security contribution magnitudes;
- monthly theme presence and contribution series.

Because themes are multi-label, theme contribution shares overlap and cannot be summed.

## Month macro codes

The 15 month targets were selected by absolute commonality magnitude and Phase 3D has
already exposed their factor signs. Therefore macro-code sign summaries remain
**descriptive only** in Phase 4A.

For each `M01`–`M07`, report:

- number of coded extreme months;
- positive/negative factor counts;
- mean signed factor;
- mean absolute factor.

No confirmatory p-value or support label is assigned.

## Interpretation boundary

A significant randomization result would mean only that, **conditional on the selected
30 top-driver securities**, companies sharing the frozen evidence-based theme display
more synchronized contribution or Winner-presence behavior than random same-sized
groups from those 30.

It would not establish:

- causality;
- predictability;
- a full-universe effect;
- attention/narrative causation;
- support for H1 or H2.

A possible H3 may be designed only after Phase 4A is complete and its limitations are
documented.
