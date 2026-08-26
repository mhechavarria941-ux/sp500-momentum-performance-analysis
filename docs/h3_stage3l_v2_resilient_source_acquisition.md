# H3 Stage 3L V2 — Resilient GDELT Source Acquisition

The first run stopped on `20221110.gkg.csv.zip` with HTTP 404 after 678
successful days.

The official GDELT GKG archive currently lists that exact file in both its
`md5sums` and `filesizes` catalogs:

- MD5: `267bc1d89adeee67d4d8b0ed8a49c67e`
- size: `24,613,876` bytes

Therefore the 404 is treated as a source-delivery failure, not as evidence that
the historical date is absent.

V2 keeps the Stage 3L protocol unchanged and:

- reuses all existing V1 daily caches;
- loads official GDELT MD5/file-size catalogs;
- validates new downloads against those catalogs;
- retries more patiently;
- tries HTTPS and HTTP GDELT endpoints;
- collects all failed dates instead of aborting on the first;
- performs one deferred retry pass after the main 1,826-date scan;
- only consolidates yearly/monthly panels when the unresolved failure count is 0.

If failures remain, the runner writes
`h3_gdelt_full_download_failures.csv` and exits with
`H3_FULL_GDELT_ATTENTION_EXTRACTION_INCOMPLETE_RETRY_REQUIRED`.

A later rerun retries only the missing dates because successful caches remain
valid.
