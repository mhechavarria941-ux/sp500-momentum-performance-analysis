# H3 Stage 3C — Exact Company-Name Transition Resolution

## Purpose

Stage 3B2 established which security identities have stable historical names and which still require targeted point-in-time name resolution.

Stage 3C does **not** jump directly to production alias intervals.

It first attempts to resolve exact name-change dates from already existing, explicit, dated project alias evidence.

## Automatic exact-date rule

An exact rename date is accepted automatically only when all conditions hold:

1. a bounded SEC NPORT old-name → new-name transition exists;
2. `security_aliases.csv` contains an explicit event for the same canonical `security_key`;
3. the normalized old company name exactly matches the bounded old state;
4. the normalized new company name exactly matches the bounded new state;
5. the explicit event date is after the last old-name observation and no later than the first new-name observation;
6. the matching event date is unique.

If any condition fails, the transition remains unresolved.

## SEC formerNames policy

SEC Submissions `formerNames` metadata remains authoritative corroborating evidence, but Stage 3C does **not** interpret its `from`/`to` fields as the exact legal rename effective date automatically.

Exact dates still require an explicit dated corporate/SEC event or manual authoritative-source review.

## Research manifest

The script builds a narrow research manifest containing only:

- unresolved bounded name transitions; and
- project-period name-state conflicts not represented by a bounded NPORT transition.

This is the set to research next using SEC filings, official company investor-relations releases, or equivalent primary corporate sources.

## Prohibited actions

Stage 3C does not:

- create production PIT GDELT alias intervals;
- download full 2021–2025 GDELT history;
- inspect returns;
- choose an H3 attention transformation;
- run H3.
