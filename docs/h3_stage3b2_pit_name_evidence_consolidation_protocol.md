# H3 Stage 3B2 — PIT Company-Name Evidence Consolidation

## Reason for this stage

The first SEC CIK/name-history resolver completed successfully, but its review queue expanded to 525 of 593 identities.

That queue is intentionally conservative but is too broad to use as the next manual-resolution layer.

The project already contains a stronger point-in-time historical name source: the SEC-filed Select Sector SPDR NPORT holdings used and independently audited for the H2 GICS construction.

Those holdings contain issuer names at repeated report dates from 2020-12-31 through 2025-12-31 and are already mapped to canonical `security_key` values through the audited SEC identifier bridge.

Stage 3B2 therefore consolidates the existing authoritative evidence before any manual review is expanded.

## Source hierarchy

1. **SEC Select Sector NPORT historical holding names**
   - primary point-in-time name-state evidence;
   - already validated in the GICS pipeline;
   - mapped by audited identifier bridge.

2. **Project `security_aliases.csv`**
   - explicit dated ticker/company-name events.

3. **SEC Submissions / formerNames**
   - secondary identity and name-history evidence;
   - only project-period-overlapping former names trigger current review.

4. **`core.security.company_name_reference`**
   - current/reference comparison only.

## Important methodological correction

A filer having any SEC former name at any point in its history is not, by itself, a reason to review its 2021–2025 attention aliases.

Only former-name evidence overlapping the project window is relevant to the PIT alias construction.

Likewise, a current SEC name differing only because of a legal suffix does not automatically invalidate the identity.

## Output classes

- `READY_STABLE_SEC_NPORT_NAME`
- `REVIEW_NO_MAPPED_SEC_NPORT_NAME`
- `REVIEW_MULTIPLE_SEC_NPORT_NAMES`
- `REVIEW_PROJECT_NAME_DIFFERS_FROM_SEC_NPORT`
- `REVIEW_PROJECT_PERIOD_NAME_EVENT_EVIDENCE`

Quarterly NPORT changes generate only a **bounded transition candidate**. They never create an exact effective date.

## No outcome leakage

This stage reads no returns, momentum values, Winner labels, commonality factors, or H3 outcomes.

Passing Stage 3B2 authorizes only targeted exact-date resolution for the focused review queue.
