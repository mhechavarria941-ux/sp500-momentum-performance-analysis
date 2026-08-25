# H3 GDELT Pilot — Ambiguity Review Procedure

## Current gate

The direct-GDELT pilot passed every automated feasibility check:

- 35/35 daily files processed;
- 525/525 company-date rows;
- 75/75 company-window rows;
- all 15 companies present;
- all five anchor windows present;
- all 15 companies have strict nonzero coverage in at least 2/5 windows;
- no Google Cloud;
- no Azure SQL;
- no outcome data.

The only remaining pilot condition is the deliberately retained entity-name ambiguity review.

## What this stage does

It creates:

1. a company-level coverage summary; and
2. a top-15 organization-variant worklist per company.

The actual attention counts continue to use only the frozen strict aliases.

No broad variant becomes a valid company alias automatically.

## High-ambiguity companies

The frozen pilot identifies:

- IRM — Iron Mountain Incorporated
- MOS — The Mosaic Company

For these companies, every non-strict top variant must be reviewed before the ambiguity gate can be closed.

The goal is not to maximize mentions. The goal is to avoid false company matches.

## Decision labels for manual review

When reviewing `h3_gdelt_pilot_ambiguity_review_worklist.csv`, use one of:

- `ACCEPT_ISSUER_ALIAS`
- `REJECT_AMBIGUOUS_OR_OTHER_ENTITY`
- `KEEP_DIAGNOSTIC_ONLY`

Do not change rows already identified as frozen strict aliases.

## Next gate

After reviewing the HIGH-ambiguity variants, create a new versioned company-alias mapping.

Only then should the project design a larger 2021-2025 attention extraction.

The full-history extraction still remains a data-building phase. It must not be joined to forward returns until H3 is formally preregistered.
