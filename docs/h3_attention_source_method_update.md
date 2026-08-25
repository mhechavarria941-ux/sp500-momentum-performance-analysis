# H3 Attention Feasibility — Source Method Update

## Important correction

The earlier Phase 4A closeout listed the **GDELT DOC 2.0 API** as the leading programmatic
candidate for 2021–2025 news-attention history.

That is not the correct full-history implementation path.

The DOC 2.0 search API is useful for recent article search and timeline work, but its accessible
search horizon is not suitable as the canonical source for reconstructing the entire 2021–2025
project period.

For the historical feasibility pilot, the canonical GDELT candidate is therefore:

**GDELT Global Knowledge Graph (GKG) 2.1 in the public BigQuery table**
`gdelt-bq.gdeltv2.gkg_partitioned`

The GKG has one record per processed document and includes `V2Organizations`, which lists
extracted organizations/companies referenced in the document together with character offsets.

## Pilot attention quantity

For each frozen company query and anchor window:

`normalized_news_share = matching GKG records / total GKG records in the same window`

The pilot is only a **source/coverage/ambiguity diagnostic**.

It must not be joined to security returns or used to choose an H3 attention transformation.

## Why the pilot uses anchor windows

A five-year GKG scan can be large. The pilot therefore uses five fixed seven-day windows spread
across 2021–2025.

This tests:

- whether the public partitioned table is accessible;
- whether early-2021 and late-2025 records can be retrieved;
- approximate media-mention coverage;
- zero-coverage frequency;
- organization-name variant quality;
- name ambiguity.

The script performs a BigQuery dry run by default and refuses to execute if the estimated bytes
exceed a user-specified cap.

## Query policy

- `V2Organizations` is the entity field.
- Bare stock tickers are prohibited as entity queries.
- Query regexes are frozen in `h3_gdelt_gkg_pilot_query_manifest.csv`.
- Historical company aliases are documented before retrieval.
- Broad variant matching is used only for the variant/ambiguity diagnostic.
- Exact organization regexes define pilot coverage counts.

## Google Trends status

Google Trends remains a possible independent search-attention robustness source, not the
canonical historical source at this stage.

The official API is still alpha and provides a rolling five-year window. On 2026-08-24 that
does not cover January–September 2021, so it cannot independently supply the entire project
sample.

No unofficial Google Trends package is authorized by this protocol.

## Gate

The pilot passes to a full-universe design only if:

1. all five historical anchor windows are retrievable;
2. query/cost controls work;
3. most pilot companies show usable nonzero coverage;
4. high-ambiguity names are explicitly reviewed rather than silently accepted;
5. the resulting files contain no return/outcome columns.

Passing this gate authorizes only the design of a full PIT attention extraction. It does not
authorize H3 inference.
