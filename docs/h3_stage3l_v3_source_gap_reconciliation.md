# H3 Stage 3L V3 — Source-Gap Reconciliation

The resilient Stage 3L run completed the full calendar scan but ended with:

- 21 unresolved source dates;
- 3 listed in the refreshed official GDELT catalog;
- 18 not listed in the loaded official catalog.

This is now handled as a **source coverage problem**, not as 21 company-data
problems.

## Frozen rule

A day for which GDELT GKG cannot be obtained is **missing source coverage**.

It is never encoded as:

`attention = 0`

because zero attention means the source existed and the company had no strict
match, which is fundamentally different.

## Reconciliation classes

`OFFICIAL_CATALOG_ABSENT_AND_DIRECT_UNAVAILABLE`

and

`CATALOG_LISTED_BUT_UNDELIVERABLE_AFTER_RETRIES`

Both remain explicit in the source-gap ledger.

## Frozen coverage thresholds

Before examining the exact distribution of the 21 dates, the source-gap gate is:

- overall 2021–2025 source coverage >= 98%;
- every calendar year >= 95%;
- every calendar month >= 90%;
- every security-month >= 90% of its PIT-active calendar days.

## Monthly estimator

For a security-month:

`sum(matched NUMARTS on source-available active days) /
 sum(total NUMARTS on source-available active days)`

Source-missing days are omitted from both numerator and denominator and are
carried explicitly as coverage fields.

## Policy

`H3_GDELT_SOURCE_GAP_HANDLING_V1`

SHA-256:

`1284f9141657400869b7eaef1ce7a19eb6fdf6e26e34509f819c6e0920dfd135`
