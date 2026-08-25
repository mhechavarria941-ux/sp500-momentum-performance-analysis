# H3 Attention Feasibility — Direct GDELT Daily Archive Method

## Decision

Google Cloud / BigQuery is **not part of this project**.

For practical infrastructure and cost reasons, the H3 news-attention feasibility
work will use GDELT's directly downloadable daily Global Knowledge Graph archive.

Canonical pilot source:

`https://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip`

This is the daily GDELT 1.0 GKG stream that GDELT continues to publish in parallel.

## Why this route

- no Google Cloud project;
- no BigQuery billing;
- no new cloud architecture;
- no Azure SQL writes during feasibility;
- deterministic daily URLs;
- files can be downloaded, parsed, and deleted one at a time;
- the GKG contains an `ORGANIZATIONS` field and a `NUMARTS` field.

GDELT's GKG 1.0 documentation describes:

- `NUMARTS` as the number of source documents containing the nameset; and
- `ORGANIZATIONS` as a semicolon-delimited list of extracted company and
  organization names.

## Pilot metric

For each company and frozen anchor week:

`news_attention_share = matched_source_documents / total_source_documents`

where source-document counts are reconstructed by summing `NUMARTS`.

A GKG nameset can represent more than one article, so rows are **not** counted
equally. `NUMARTS` is used as the article weight.

## Language / source limitation

GDELT 1.0 GKG is the older daily stream and does not include the translated
language coverage available in GDELT 2.x.

This is accepted for the feasibility pilot because:

- the project companies are U.S. S&P 500 issuers;
- the objective is a reproducible attention proxy, not a complete census of
  world media;
- using one stable daily source across 2021-2025 is preferable to mixing cloud
  and non-cloud sources.

This limitation must remain in any future H3 interpretation.

## Network/storage design

The pilot uses five frozen seven-day windows: 35 daily ZIP files total.

The script:

1. estimates remote compressed sizes before execution;
2. refuses to download if the estimated total exceeds the configured cap;
3. downloads one ZIP at a time;
4. parses it directly from the ZIP;
5. records the SHA-256 and processing statistics;
6. deletes the ZIP immediately unless `--keep-cache` is explicitly requested.

Therefore the full pilot is not retained as raw local data.

## Entity-query policy

Bare stock tickers are prohibited.

Two separate matching concepts are frozen:

### Strict aliases

Used for the actual pilot attention coverage count.

Examples:

- `nvidia`
- `marathon petroleum`
- `texas pacific land`

Ambiguous short forms such as `mosaic`, `williams`, and bare `meta` are excluded.

### Broad variants

Used only for diagnostics.

This intentionally surfaces organization labels that may be relevant but too
ambiguous to accept automatically.

Iron Mountain and Mosaic are designated HIGH ambiguity and must receive manual
variant review even if the quantitative pilot gate otherwise passes.

## No outcome leakage

This pilot does not read:

- momentum values;
- Winner assignments;
- forward returns;
- benchmark returns;
- residual commonality factors;
- Phase 4A results.

Passing the pilot authorizes only the design of a larger historical
news-attention extraction.

It does not authorize H3 inference.
