# H3 Stage 3J — Frozen Point-in-Time Attention Alias Policy

**Policy ID:** `H3_PIT_ATTENTION_ALIAS_POLICY_V5`  
**Version:** `2026-08-25-v5`  
**SHA-256:** `c18b1ce9c421f52afb3d0d2ea85fe4e1e4f282fa5d14a85cefd9ccf21da2bb40`

## Purpose

Company-name research is closed at 593/593. Stage 3J freezes the primary company-name
matching policy before any full-history GDELT extraction.

The manifest is a **point-in-time company-attention query layer**, not a return dataset.

## Time and membership

The primary sample is:

`2021-01-01 <= date < 2026-01-01`

Every alias interval is clipped to the canonical point-in-time S&P 500 membership interval.

A security that is not an index member on a date receives no production alias for that date.

## Name-transition boundary

For media attention, the public-facing identity date has priority.

1. use an authoritative public/trading effective date when available;
2. otherwise use the authoritative legal effective date.

The old alias ends immediately before that boundary. The new alias begins on the
boundary.

There is no month-wide old/new overlap in the primary specification.

### Pre-window public rebranding

If the public rebrand occurred before 2021 but legal-name finalization occurred during
2021, use the already-public post-rebrand name from the start of the sample.

LUMN is the canonical example:

- Lumen public brand: 2020-09-14
- ticker LUMN: 2020-09-18
- legal CenturyLink -> Lumen Technologies: 2021-01-22

The primary 2021 attention alias is therefore Lumen, not CenturyLink.

## Stable-name source precedence

1. Stage 3G authoritative sample company name;
2. Stage 3I official membership company name for no-NPORT securities;
3. latest in-membership SEC NPORT issuer name;
4. canonical project company name only as a final fallback.

## Production alias normalization

Two deterministic representations are constructed.

### Full normalized authoritative name

- lowercase;
- `&` -> `and`;
- punctuation collapsed to spaces;
- leading `the` removed;
- provider-style trailing `/The` display notation normalized (for example, `Cigna Group/The`);
- explicit class/jurisdiction display annotations removed;
- legal suffixes retained.

### Conservative legal core

The full normalization plus removal of trailing legal forms only:

- Inc. / Incorporated
- Corp. / Corporation
- Co. / Company
- Ltd. / Limited
- PLC
- LLC / LLP / LP
- N.V. / AG / SE / SA

Semantic company words are **never** stripped merely to improve coverage.

Examples of words retained:

`Group`, `Holdings`, `International`, `Technologies`, `Energy`, `Financial`,
`Systems`, `Health`, `Digital`, `Properties`.

## Precision-first alias selection

The conservative legal core is the default only when it remains sufficiently specific.

The full authoritative name is required when any of the following holds:

- Stage 3A structural ambiguity tier is HIGH;
- the exact issuer name was flagged ticker-like;
- the legal core is shorter than four characters;
- the legal core exactly equals any historical stock ticker.

Bare tickers are prohibited.

## Collision control

After initial alias selection, overlapping alias collisions across different securities
are detected.

The automatic response is:

1. escalate every colliding row to the full normalized authoritative name;
2. re-run collision detection;
3. block Stage 3J if an overlapping cross-security collision still remains.

No manual broadening is permitted to solve a collision.

## Matching

The primary matching mode is:

`EXACT_NORMALIZED_GKG_ORGANIZATION`

No regex substring matching is authorized in the primary specification.

No broad company-name variants are authorized yet.

## Next gate

A passing Stage 3J manifest does **not** immediately authorize the full 2021-2025 GDELT
download.

The next step is a frozen no-outcome coverage/missingness pilot on the complete alias
manifest or a deterministic sample of it.

Only after that gate is passed may full-history attention extraction begin.


## Policy V2 clarification

The initial build exposed a provider-format representation: `Cigna Group/The`.

This is not a substantive name difference. It is the same display convention seen in
provider/holdings names such as `Charles Schwab Corp/The`.

Policy V2 therefore normalizes a **trailing `/The` display token before punctuation
collapse**. This is a deterministic presentation correction only; it does not introduce
fuzzy matching, synonym expansion, or semantic word stripping.


## Policy V3 — all-transition preflight resolution

The all-transition preflight audited 26 in-sample transition securities before
the production manifest was allowed to build.

Result:

- 23 exact Policy-V2 matches;
- 1 deterministic punctuation/token-spacing equivalent (`CPB`);
- 2 apparent semantic mismatches caused by comparing the terminal rename state
  to a static pre-transition Stage 3I membership label (`FBHS`, `PENN`);
- 0 sequential transition-chain nonmatches.

### Static membership names with in-sample renames

When a Stage 3I membership name spans an authoritative rename event, it is an
identity anchor for the pre-transition state. It is validated against the first
event's old name, not against the post-transition terminal state.

### Deterministic display equivalence

If two authoritative legal cores differ only because punctuation was converted
to token spacing, their compact alphanumeric cores may be compared.

Example:

`CAMPBELL S` and `Campbell's Company/The`

Both reduce diagnostically to:

`campbells`

This compact representation is never the production alias. It is only a strict
presentation-equivalence test. The independently resolved authoritative spelling
is used for the resulting final interval.

No fuzzy matching, edit distance, substring matching, synonym expansion, or
semantic word deletion is permitted.


## Policy V4 — event-chain authority

Further SEC verification confirmed that the repeated build stops were caused by
an invalid endpoint assumption.

`K` is the decisive case:

- Kellogg Company -> Kellanova is already in the authoritative Stage 3I event ledger;
- SEC confirms the change effective 2023-10-02;
- the static Stage 3I membership name is already `Kellanova`, the post-transition
  state.

In contrast:

- `FBHS` has a static membership name matching the pre-transition state;
- `PENN` has a static membership name matching the pre-transition state;
- `CPB` has a static source matching the terminal state after deterministic
  punctuation/token-spacing equivalence.

Therefore a static source label cannot be assumed to occupy a fixed temporal
position.

### Frozen V4 rule

For every security with an authoritative transition event chain:

1. the ordered authoritative event chain owns the temporal company-name states;
2. a static source name is identity corroboration only;
3. it must match **any** event-chain state;
4. the builder checks all transition securities in one batch;
5. all remaining issues are written to one diagnostic file before the build
   blocks.

This removes the one-security-at-a-time failure mode.

No fuzzy matching is introduced.


## Policy V5 — complete alias-safety audit resolution

The first successful Stage 3J build exposed the complete remaining safety set:

- 5 overlapping production-alias pairs;
- 8 bare-ticker production-alias rows;
- 0 transition-alignment issues.

These are handled as classes rather than individual securities.

### Bare-ticker qualification

A production organization alias may never be a bare stock ticker.

When a state legal core is itself ticker-like, the builder searches authoritative
same-issuer names for a fuller spelling with the **exact same legal core**.

Examples of the permitted structure are:

- core `rtx` -> full legal/display name `RTX Corporation`;
- core `nov` -> full legal/display name `NOV Inc.`;
- core `eqt` -> full legal/display name `EQT Corporation`.

The exact names are determined from local authoritative evidence at runtime.

No fuzzy matching or semantic expansion is permitted.

### Same-issuer alias sharing

Company-level news attention is an issuer construct.

If two simultaneously active S&P security identities have:

1. the same production alias; and
2. the same nonblank authoritative SEC CIK,

their overlap is an intentional shared-issuer alias rather than an ambiguity.

This is the expected structure for multiple listed share classes of one issuer.

The diagnostic remains explicit so downstream H3 work can account for shared
issuer-level attention and avoid pretending the observations are independent.

### True collisions

Different-CIK or unresolved-CIK overlaps remain blocking and are escalated to
the safest qualified full authoritative name before one final collision test.
