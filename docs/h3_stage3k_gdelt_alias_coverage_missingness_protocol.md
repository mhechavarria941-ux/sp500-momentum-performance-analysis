# H3 Stage 3K — GDELT Alias Coverage & Missingness Gate

**Gate ID:** `H3_GDELT_ALIAS_COVERAGE_MISSINGNESS_GATE_V1`  
**Version:** `2026-08-25-v1`  
**SHA-256:** `8184dbc3bfb147e1ba561b316c28e9b5c3a58c9e9d56951d1b6e4fe55a4b4533`

## Prerequisite

Stage 3J has passed:

`H3_PIT_ATTENTION_ALIAS_MANIFEST_INTEGRITY_AUDIT_PASSED`

The frozen PIT alias policy remains:

`H3_PIT_ATTENTION_ALIAS_POLICY_V5`

No alias-policy change is made in Stage 3K.

## Purpose

Stage 3K asks a narrower question before committing to roughly five years of
daily GDELT extraction:

> Does the frozen PIT alias system produce technically complete and sufficiently
> broad strict news-attention coverage across the historical universe?

This stage reads **no returns, momentum labels, Winner assignments, commonality
factors, or H3 outcomes**.

## Direct source

Daily direct GDELT GKG 1.0 files:

`https://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip`

Only one daily zip is held at a time. After successful parsing and checksum
recording, the raw zip is deleted. Small daily aggregate/cache files are retained
for reproducibility and resume capability.

## Frozen five-window sample

The gate deliberately reuses the five previously selected 7-day windows:

| Window | Start | End exclusive |
|---|---|---|
| W2021 | 2021-01-11 | 2021-01-18 |
| W2022 | 2022-04-11 | 2022-04-18 |
| W2023 | 2023-07-10 | 2023-07-17 |
| W2024 | 2024-10-07 | 2024-10-14 |
| W2025 | 2025-12-08 | 2025-12-15 |

Total expected source files: **35**.

A security is evaluated only on dates/windows in which its Stage 3J alias
interval is actually active.

## Exact deterministic organization matching

For each organization token from the GKG `ORGANIZATIONS` field, Stage 3K
constructs two frozen deterministic representations:

1. full normalized organization name;
2. conservative legal-core normalized organization name.

A production alias counts only when it equals one of those representations
**exactly**.

There is:

- no substring regex matching;
- no fuzzy/edit-distance matching;
- no semantic expansion;
- no bare-ticker matching.

A GKG row contributes its `NUMARTS` weight at most once to each matching alias.

## Technical completeness gate

All of the following must hold:

- 35 / 35 daily source files parsed or validly reused from cache;
- every daily denominator is positive;
- malformed-row rate per file <= 0.1%;
- every active security-date maps to exactly one PIT production alias;
- every attention share is in [0, 1];
- no outcome-like fields are read or emitted.

## Frozen strict-coverage thresholds

These thresholds are frozen **before** running the complete-universe pilot:

- >= **85%** of securities eligible in at least one anchor window must have at
  least one strict nonzero window;
- among securities eligible in at least two anchor windows, >= **70%** must have
  strict nonzero attention in at least two windows;
- >= **50%** of eligible security-window observations must be strict nonzero;
- >= **65%** of eligible HIGH-ambiguity securities must have at least one strict
  nonzero window.

A zero match is not called missing data. It is retained as a zero-attention
observation. The coverage thresholds determine whether those zeros are plausible
enough to authorize full extraction or instead indicate inadequate strict-alias
recall.

## If Stage 3K passes

The next step is not H3 inference.

It authorizes design of a checkpointed full 2021-2025 direct-GDELT attention
extraction with reproducible source hashes, resume support, and no outcome
joining.

## If Stage 3K fails

Do not tune aliases against returns.

Diagnose strict coverage by:

- ambiguity tier;
- alias-selection reason;
- transition versus stable interval;
- qualified ticker-core aliases;
- shared-issuer aliases;
- source-name layer.

Only source/identity evidence may be used in any remediation.
