# H3 Candidate — Attention Data Feasibility Protocol

**Status:** DATA-SOURCE FEASIBILITY ONLY — NO H3 RETURN TEST IS AUTHORIZED YET

## Motivation

H1 and H2 are closed as not supported. Post-H2 Phase 4A also found no evidence-defined structural theme whose contribution synchronization survived Holm correction.

The next scientifically defensible step is therefore not to force the existing themes into a new return explanation. Instead, evaluate whether a reproducible public-attention data layer can be built independently enough to support a future H3.

## Candidate H3 Concept

A future preregistered hypothesis may test whether an abnormal increase in public attention at month t is associated with:

1. next-month residual security return;
2. next-month probability of entering the sector-relative momentum Winner sleeve; and/or
3. an interaction between current Winner status and attention shock for next-month residual return.

No one of these becomes the primary H3 endpoint until the attention-data feasibility gate passes and the final H3 preregistration is written.

## Candidate Attention Sources

### A. GDELT DOC 2.0 — candidate primary *news-attention* source

Use normalized article-volume timelines rather than raw article counts when possible.

Rationale:

- programmatic historical access;
- coverage beginning before the 2021-2025 project window;
- normalized timeline volume is designed to account for changes in the total amount of monitored coverage;
- reproducible company-name queries can be logged.

Primary limitation:

GDELT measures media/news attention, not direct public search attention. Company-name ambiguity and historical name changes require an auditable query-alias layer.

### B. Google Trends — candidate secondary *search-attention* robustness source

Preferred representation:

- Google Trends Topic when an unambiguous company topic exists;
- otherwise a documented exact company-name search term.

Rationale:

Google describes Trends as an anonymized, categorized, aggregated sample of Google searches. Topics are preferred because they represent a real-world entity across related search terms and languages.

Important constraints:

1. The public Trends website rescales each request to 0-100, so direct level comparison across separate requests is unsafe.
2. A within-company attention shock can still be considered because multiplicative request scaling does not change a within-series standardized score.
3. Google's official Trends API is currently an alpha product with limited tester access.
4. The official API provides a rolling 1800-day / roughly five-year window. On 2026-08-24 that begins around 2021-09-19, so it does not by itself cover the entire January 2021-December 2025 project period.
5. The public Explore interface can export chart data and may therefore be required to recover the early-2021 portion if Google Trends becomes part of H3.

## Source Policy

- No Wikipedia.
- Do not use unofficial social-media scrapes as the primary H3 data source.
- Do not use a source merely because it produces a convenient attention number.
- Every company query must have an auditable query string/topic identifier and date coverage record.
- Company names and historical aliases must be frozen before attention values are joined to returns.

## Feasibility Gate

Before any H3 return association is calculated:

### GDELT gate

For a stratified pilot set of companies:

- verify historical retrieval over 2021-2025;
- verify normalized timeline output;
- inspect company-name ambiguity;
- inspect zero/near-zero coverage;
- verify repeat requests are stable enough for reproducible monthly aggregation.

Then expand to the full PIT security identity set only if the pilot succeeds.

### Google Trends gate

Determine which access mode is actually available:

- official API alpha access; or
- official public Explore CSV exports.

Do not substitute an unofficial library without explicitly creating a new source-methodology version.

### Coverage gate before H3 preregistration

The final attention layer must report:

- securities requested;
- securities with usable attention histories;
- monthly coverage per security;
- zero-observation frequency;
- historical alias/query changes;
- ambiguous-query exclusions;
- source-specific missingness.

The H3 universe must be frozen from this coverage audit before any attention-return statistic is inspected.

## Candidate Attention Transformations — NOT YET PRIMARY

Potential no-look-ahead measures to evaluate for feasibility:

- month-over-month change in normalized attention;
- current attention relative to trailing 6-month median;
- trailing 12-month within-security z-score;
- positive attention-shock indicator.

Do not select the primary transformation by comparing which one best predicts returns.

A final transformation must be frozen before outcome analysis.

## Timing Boundary

For a future H3:

- attention measured through ranking month t;
- outcome measured in t+1;
- contemporaneous attention and return may be studied separately but must not be confused with prediction.

No future-month attention may enter the t signal.

## Outcome Boundary

A future H3 residual-return outcome must explicitly control for market and sector exposure without using future information.

The exact residualization method will be frozen only after the attention source and coverage universe are known.

## Current Decision

**PROCEED TO ATTENTION-DATA FEASIBILITY, NOT H3 INFERENCE.**

Phase 4A did not provide an adjusted theme-synchrony effect, so attention analysis must stand on its own methodology rather than being framed as confirmation of the Phase 3 themes.
