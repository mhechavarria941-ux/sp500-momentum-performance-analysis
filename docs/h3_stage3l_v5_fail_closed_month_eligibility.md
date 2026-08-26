# H3 Stage 3L V5 — Fail-Closed Month Eligibility

The source-gap finalization showed:

- 1,826 calendar dates classified;
- 1,805 GKG 1.0 source dates available;
- 21 documented source-gap dates;
- overall source coverage 98.8499%;
- minimum annual coverage 95.0685%;
- minimum calendar-month coverage 43.3333%;
- minimum security-month coverage 43.3333%.

The previously frozen 90% calendar/security-month threshold therefore did its
job: the concentrated source outage cannot be silently accepted.

## Why the primary series should not mix GKG generations now

GDELT's official GKG documentation states that Version 2.x changed the storage
unit from Version 1.0 namesets weighted by `NUMARTS` to one row per document.
It also introduced the expanded GDELT 2.x monitoring/translation environment.

Although `V1ORGANIZATIONS` remains backwards-compatible in GKG 2.1, inserting
only GKG 2.1 records into the missing GKG 1.0 dates would create a localized
source-generation change in the primary attention series.

That can be studied later as a source-only robustness bridge, but it should not
be introduced merely because the frozen GKG 1.0 coverage gate failed.

## Fail-closed primary rule

The frozen 90% threshold is **not relaxed**.

A calendar month with <90% GKG 1.0 source coverage is unavailable for primary
H3 attention.

All securities in that month are excluded uniformly, even if an individual
security's short PIT membership interval happens to overlap only available
days.

This avoids cross-sectional selection.

For retained calendar months, each security-month must independently retain
>=90% source coverage.

## Timing consequence

If attention month `t` is unavailable, then later H3 preregistration must mark
the `attention_t -> outcome_(t+1)` observation ineligible **before outcomes are
read**.

No source-gap day is imputed as zero.

## Frozen policy

`H3_GDELT_FAIL_CLOSED_MONTH_ELIGIBILITY_V1`

SHA-256:

`9837f2d31b5da907f0ab17f7ef50d9b22d44d51f51689bae937ffa7e8ab84aac`
