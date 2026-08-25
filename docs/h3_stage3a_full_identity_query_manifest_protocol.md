# H3 Stage 3A — Full Security Identity / Company-Query Candidate Manifest

## Purpose

Scale the successful 15-company GDELT feasibility pilot to the complete historical security identity universe **without yet downloading full-history attention data**.

The project currently contains:

- 593 canonical security identities;
- 594 ticker-history segments.

Stage 3A extracts those canonical identity tables read-only from Azure SQL and builds a conservative company-query **candidate** manifest.

## Important point-in-time rule

The company name currently stored in `core.security` must not automatically be assumed to have been valid for the entire 2021–2025 period.

Examples of possible complications include:

- corporate renames;
- predecessor/successor issuer names;
- mergers;
- spin-offs;
- ticker changes;
- reorganizations.

Therefore the current normalized company name is only a starting identity.

No current company name is marked point-in-time valid during Stage 3A.

## Alias rule

Stage 3A creates:

1. `exact_legal_name_alias`
   - normalized current canonical name;
   - the only candidate production alias.

2. `suffix_stripped_alias_candidate`
   - diagnostic only;
   - never automatically promoted.

Bare stock tickers are not authorized as attention queries.

## Structural ambiguity triage

The candidate manifest assigns a purely structural review tier:

### HIGH

- duplicate normalized exact alias; or
- one-token base name; or
- very short base alias.

### MEDIUM

- two-token base name; or
- multiple ticker-history segments.

### LOW

All other names.

This is a review-priority device, not a claim that the name is actually ambiguous.

## Next stage after passing

Stage 3B should use authoritative sources, primarily SEC/company records, to resolve:

- historical issuer names;
- former names;
- effective dates;
- predecessor/successor identity;
- ambiguous current names.

Only after that PIT company-name layer is frozen should a broad 2021–2025 GDELT extraction be designed.

No attention/return analysis is authorized at Stage 3A.
