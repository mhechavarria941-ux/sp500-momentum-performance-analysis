# H3 Stage 3L V4 — Transition-Month Aggregation Fix

## Trigger

Source-gap reconciliation completed acquisition/classification and built the
yearly daily shards, then failed while constructing the monthly panel:

- `2023-07 / RTX`
- `2025-10 / SLB`

appeared more than once in the left side of a one-to-one monthly merge.

## Root cause

This is **not a source gap and not a company-name research failure**.

The monthly groupby incorrectly included transition-dependent provenance fields:

- `alias_selection_reason`
- `authoritative_name_source_layer`

and also included the alias-dependent state structure indirectly.

A security that changes its authoritative PIT company name inside a calendar
month can therefore generate two temporary monthly groups even though the
measurement unit is supposed to be one `security_key × month`.

RTX and SLB are exactly the type of cases the PIT alias layer was designed to
handle.

## Correct measurement unit

The Stage 3L monthly measurement is:

`security_key × calendar_month`

not:

`security_key × calendar_month × alias-state metadata`

Daily PIT matching remains unchanged.

For a transition month, matched and denominator NUMARTS are summed across the
appropriate old/new daily PIT aliases, after which one monthly attention share
is calculated.

## Provenance preservation

Transition metadata is not discarded. The corrected panel records:

- `unique_aliases_in_month`
- `production_aliases_pipe`
- `alias_selection_reasons_pipe`
- `authoritative_name_source_layers_pipe`
- `pit_alias_transition_month_flag`

A separate transition-month diagnostics CSV records all security-months whose
PIT alias/provenance changed inside the month.

## Methodology status

The frozen source-gap policy is **unchanged**:

`H3_GDELT_SOURCE_GAP_HANDLING_V1`

No attention values, source-gap thresholds, matching rules, or outcome
definitions changed.

This is an aggregation-implementation correction only.
