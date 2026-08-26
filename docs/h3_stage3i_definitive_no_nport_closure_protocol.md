# H3 Stage 3I — Definitive No-NPORT Closure

## Finding from the Stage 3H unresolved file

All 93 carry-forward rows have exactly the same Stage 3B2 status:

`REVIEW_NO_MAPPED_SEC_NPORT_NAME`

There are no remaining project-vs-NPORT conflicts, multiple-NPORT-name cases, or
other unresolved classifications in this batch.

That changes the interpretation of the problem.

The 93 rows are a **source coverage gap**, not 93 independent company-identity
ambiguities.

## Correct source hierarchy

For the 93 no-NPORT identities:

1. audited S&P 500 point-in-time membership identity and interval;
2. deterministic SEC CIK identity where available;
3. validated security-market termination boundaries;
4. primary-source corporate name/ticker events;
5. SEC former-name metadata as a safety diagnostic.

NPORT is not required to prove identity when no NPORT holding observation exists.

## Known in-sample name-state controls

The package explicitly preserves primary-source events for:

- L Brands -> Bath & Body Works;
- Fortune Brands Home & Security -> Fortune Brands Innovations;
- HollyFrontier -> HF Sinclair successor issuer;
- Kellogg Company -> Kellanova;
- National Oilwell Varco -> NOV Inc.;
- Penn National Gaming -> PENN Entertainment;
- Robert Half International -> Robert Half;
- Gap GPS -> GAP ticker-only change.

The event is applied only when its public/legal boundary lies inside that
security_key's actual S&P membership interval.

If the event lands at or after `valid_to_exclusive`, it belongs to the successor
identity and is not backcast into the departing security.

## Safety diagnostic

The script also inspects SEC former-name records for every deterministically
resolved CIK.

If a distinct former-name boundary falls inside active membership and is not
explained by the known-event ledger, the script writes **all such cases at once**
to:

`h3_no_nport_unexpected_sec_former_name_signals.csv`

The final 593-of-593 closure gate will block in that situation rather than
silently ignoring the evidence.

## Closure standard

The target is:

- 93 / 93 no-NPORT identities explicitly disposed;
- 593 / 593 full-universe identities resolved;
- 0 carry-forward gaps;
- 0 unexpected in-membership former-name signals.

No GDELT history or return data is used.
