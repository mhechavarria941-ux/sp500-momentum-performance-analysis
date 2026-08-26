# H3 Statistical Preregistration V2

**Preregistration ID:** `H3_STATISTICAL_PREREGISTRATION_V2`  
**Version:** `2026-08-26-v2`  
**SHA-256:** `95e88d99f2b0c9beca50073844b9dadc32c11a6aa820fe04cf3ed12e94841506`

## Amendment status

V2 amends V1 **before the preregistration audit passed and before any H3 outcome
data were opened**.

The H3A/H3B/H3C hypotheses, timing, fixed effects, covariance estimator,
multiple-testing family, missingness rules, and support criteria are unchanged.

The amendment corrects only the construction of the already intended
**issuer-level attention predictor**.

## Why V1 failed

V1 compared already aggregated `security × month` attention shares and required
all securities with the same issuer CIK to have identical monthly values.

That assumption is invalid when one legal issuer spans a mid-month security,
ticker, or company-name transition.

The observed control case was:

- month: `2022-04`
- SEC CIK: `0001437107`
- security identities: `DISCA | DISCK | WBD`

Those security-month rows cover different subsets of April, so their monthly
attention ratios need not be identical even though they refer to one continuing
issuer.

## Correct issuer-level construction

The primary attention unit is built in this order:

`security-day -> issuer-day -> issuer-month -> security-month mapping`

### Step 1 — issuer identity

`issuer_id = SEC CIK`

when nonblank; otherwise:

`issuer_id = SECURITY::<security_key>`

### Step 2 — same-issuer/day check

For every `issuer_id × date`, all simultaneously active security rows must have
the same:

- matched GKG `NUMARTS`;
- total GKG `NUMARTS`.

This catches genuine same-day alias disagreement.

### Step 3 — deduplicate share classes

After the same-day check, keep one observation per `issuer_id × date`.

This prevents GOOG/GOOGL-style multiple securities from giving one issuer extra
weight.

### Step 4 — aggregate issuer month

For issuer `i`, month `t`:

`issuer_attention_share_it = Σ matched NUMARTS_issuer-day / Σ total NUMARTS_issuer-day`

over source-available PIT-active issuer-days.

Sequential identities sharing one CIK naturally combine across their respective
days.

### Step 5 — transform

`attention_log = ln(1 + 1,000,000 × issuer_attention_share)`

Then standardize within each predictor month across **unique issuers** using the
sample standard deviation:

`attention_z = (attention_log - mean_t) / sd_t`

### Step 6 — map to securities

The same issuer-month `attention_z` is mapped to every eligible security-month
of that issuer.

The original Stage 3L security-month attention share is retained as provenance
only.

## Everything else remains frozen

### H3A

Attention predicts next-month leave-one-out PIT sector-relative return.

### H3B

Attention predicts next-month entry into canonical H1 momentum D10 among
current non-Winners.

### H3C

Current Winner × attention predicts incremental next-month sector-relative
return.

### Models

Security FE + outcome-month FE + current momentum-decile FE.

### Inference

Two-way cluster robust by issuer and outcome month.

### Primary multiple-testing family

H3A `β_A`, H3B `β_B`, H3C `θ`.

Two-sided Holm-Bonferroni, familywise `α = 0.05`.

Support additionally requires the preregistered positive sign.

## Outcome firewall

The V2 predictor preparation and audit read:

- attention data;
- issuer/security identity fields;
- source-coverage fields.

They do **not** read:

- returns;
- momentum;
- Winner labels;
- H3 outcomes.

Only a passing V2 audit authorizes the first attention/outcome join.
