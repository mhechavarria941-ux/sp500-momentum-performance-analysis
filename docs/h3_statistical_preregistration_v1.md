# H3 Statistical Preregistration V1

**Preregistration ID:** `H3_STATISTICAL_PREREGISTRATION_V1`  
**Version:** `2026-08-26-v1`  
**SHA-256:** `776da9efd51f1c9e724684f04003e71d4ea08c7a67d1c053a9127a39720442c4`

## Status before outcomes

The H3 attention acquisition layer has been closed under the frozen PIT alias,
source-gap, and fail-closed month-eligibility policies.

This preregistration is intentionally completed **before** any H3 attention
variable is joined to:

- security forward returns;
- momentum deciles;
- Winner labels;
- H3 outcomes.

The preparation script is allowed to read the finalized attention panel only.

---

## 1. Timing

Predictor month:

`2021-01 <= t <= 2025-11`

Attention is measured during calendar month `t`.

Every primary H3 outcome is measured at `t+1`.

December 2025 attention is excluded because its one-month-ahead outcome would be
January 2026, outside the frozen outcome sample.

Any attention month already marked unavailable by the fail-closed GKG coverage
rule is removed **before** outcomes are opened.

---

## 2. Primary attention variable

Raw monthly measure:

`attention_share = matched GKG NUMARTS / total GKG NUMARTS`

on source-available PIT-active days.

True observed zeros remain zero.

No attention value is imputed.

### Issuer-level standardization

Attention is fundamentally issuer-level when multiple securities share one SEC
CIK.

Define:

`issuer_id = SEC CIK`

when available, otherwise:

`issuer_id = SECURITY::<security_key>`

For every issuer-month, simultaneously active security classes must carry the
same raw attention share within absolute tolerance `1e-15`. A violation blocks
the preregistration gate.

Transform:

`attention_log = ln(1 + 1,000,000 × attention_share)`

Then, separately within each predictor month, calculate the mean and sample
standard deviation across **unique issuers**:

`attention_z = (attention_log - monthly issuer mean) / monthly issuer SD`

The same issuer-level z-score is mapped back to all of its active securities.

The primary coefficient therefore represents a **+1 cross-sectional standard
deviation attention shock**.

No winsorization is used.

---

## 3. Primary next-month return outcome

H3A and H3C use the corrected H1 one-month gross security forward-return layer.

No new return source will be substituted.

For security `i` in PIT GICS sector `s` at predictor month `t`:

`sector_relative_return_i,t+1`

equals:

`security_forward_return_i,t+1`

minus:

`equal-weight mean forward return of every OTHER valid security in sector s`

for the same predictor month.

This is explicitly leave-one-out.

At least **5 other valid sector peers** are required.

No transaction costs or risk-free subtraction are introduced into this
security-level outcome.

---

## 4. H3A — attention and next-month sector-relative return

Expected sign:

`β_A > 0`

Primary model:

`SRR_i,t+1 = security_FE_i + outcome_month_FE_t+1 + momentum_decile_FE_t + β_A attention_z_i,t + ε_i,t+1`

Primary estimand:

`β_A`

Interpretation:

`100 × β_A`

percentage points of next-month sector-relative return associated with a +1 SD
attention shock.

---

## 5. H3B — attention and next-month Winner entry

Winner is the canonical corrected H1 **12-1 momentum D10** classification.

The H3B risk set contains only securities that:

1. are not D10 at month `t`;
2. have a valid momentum assignment at `t+1`.

Define:

`winner_entry_i,t+1 = 1`

if the security is D10 at `t+1`, otherwise `0`.

Primary model is a linear probability model:

`Entry_i,t+1 = security_FE_i + outcome_month_FE_t+1 + current_decile_FE_t + β_B attention_z_i,t + ε_i,t+1`

Current decile FE span D01-D09.

Expected sign:

`β_B > 0`

Interpretation:

`100 × β_B`

percentage-point change in next-month Winner-entry probability associated with a
+1 SD attention shock.

The LPM is preregistered to preserve security/month fixed effects and a directly
interpretable probability effect without conditional-logit separation silently
removing securities.

---

## 6. H3C — Winner × attention interaction

Current Winner:

`winner_i,t = 1` when canonical D10 at month t.

Primary model:

`SRR_i,t+1 = security_FE_i + outcome_month_FE_t+1 + momentum_decile_FE_t + β_C attention_z_i,t + θ(attention_z_i,t × winner_i,t) + ε_i,t+1`

Primary H3C estimand:

`θ`

Expected sign:

`θ > 0`

Interpretation:

`100 × θ`

percentage points of incremental next-month sector-relative return per +1 SD
attention for current Winners relative to non-Winners.

The total Winner attention slope:

`β_C + θ`

will be reported as a secondary linear combination, but its p-value is not part
of the primary Holm family.

---

## 7. Fixed effects and controls

Every primary model contains:

- security fixed effects;
- outcome-month fixed effects;
- current momentum-decile fixed effects.

H3A/H3C do not add sector fixed effects because the dependent variable is already
PIT sector-relative and security FE absorb stable issuer characteristics.

There are **no additional primary controls**.

Additional post-hoc controls cannot redefine the confirmatory result.

---

## 8. Primary inference

The primary covariance estimator is **two-way cluster robust** by:

1. issuer ID;
2. outcome month.

SEC CIK is the issuer cluster when available. Otherwise the deterministic
security fallback issuer ID is used.

Small-sample correction is required.

Reference degrees of freedom:

`min(number of issuer clusters, number of outcome-month clusters) - 1`

Minimum estimation requirements:

- 1,000 model rows;
- 100 issuer clusters;
- 30 outcome-month clusters;
- H3B additionally requires at least 100 positive Winner-entry events.

The previous HAC lag-3 convention is **not** the H3 primary inference method.
HAC was designed for H1/H2 portfolio time series; H3 is a security-month panel
with issuer and common-month dependence.

---

## 9. Multiple testing

Primary family:

1. H3A `β_A`
2. H3B `β_B`
3. H3C `θ`

All tests are **two-sided**.

Familywise alpha:

`0.05`

Adjustment:

**Holm-Bonferroni**

A component is:

- **SUPPORTED** only when Holm-adjusted `p < 0.05` **and** the coefficient is positive;
- **CONTRADICTED** when Holm-adjusted `p < 0.05` and the coefficient is negative;
- **NOT SUPPORTED** otherwise.

There is no post-hoc umbrella rule that converts one significant component into
“overall H3 supported.”

---

## 10. Missingness and eligibility

Primary attention requires:

`primary_attention_eligible_flag = 1`

True source-observed zero attention is retained.

No source-gap or attention imputation is permitted.

For H3A/H3C, a missing forward return removes only that affected security-month.

For H3B, no valid `t+1` momentum assignment means Winner entry is undefined and
the observation is excluded.

Sector-relative outcomes require at least five other valid PIT same-sector peers.

---

## 11. Prespecified robustness analyses

Robustness analyses cannot upgrade a failed primary result.

Prespecified robustness only:

1. issuer-month attention empirical midrank percentile;
2. unstandardized log attention;
3. exclusion of HIGH ambiguity aliases;
4. exclusion of PIT alias-transition months;
5. leave-one-sector-out H3A/H3C coefficient stability;
6. any future GKG 2.1 source-gap bridge only under a separate source-only frozen
   calibration protocol.

---

## 12. Outcome firewall

Before this preregistration audit passes:

- returns may not be read;
- momentum deciles may not be read;
- Winner labels may not be read;
- no attention/outcome join may be created.

After the preregistration audit passes, the first authorized outcome operation is
a deterministic join implementing the equations above without specification
changes.
