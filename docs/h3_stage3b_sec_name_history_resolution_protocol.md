# H3 Stage 3B — SEC Company Identity and Historical-Name Resolution

## Why this stage exists

Stage 3A created a conservative 593-security company-query candidate manifest.
The report showed:

- 593 security identities;
- 594 ticker-history segments;
- 1 identity with multiple ticker segments;
- 0 duplicate exact normalized aliases;
- 210 HIGH structural-ambiguity identities;
- 220 MEDIUM;
- 163 LOW;
- 8 ticker-like exact legal/current names;
- 211 identities in the PIT/name-history review queue.

These classifications are triage only. They do not establish historical company-name validity.

## Authoritative sources

Stage 3B uses SEC sources only:

1. `company_tickers.json`
   - current ticker / CIK / EDGAR conformed company-name associations.

2. `cik-lookup-data.txt`
   - historically cumulative CIK / entity-name lookup data.

3. SEC Submissions API
   - `https://data.sec.gov/submissions/CIK##########.json`
   - current filer metadata, including current name, tickers, exchanges, and `formerNames`.

The SEC does not require an API key, but programmatic access must identify the caller with a User-Agent.

## Deterministic CIK mapping rules

The resolver does not use fuzzy name matching.

Auto mapping is allowed only when one of these deterministic conditions holds:

- project ticker and exact normalized company name agree on one CIK;
- the SEC current ticker record has the exact normalized company name;
- an exact normalized company name maps uniquely in official current/historical SEC name files.

Ticker-only matches are review cases.

Conflicts and non-unique mappings are review cases.

Unresolved identities remain unresolved.

## Former names

SEC `formerNames` records are downloaded as raw authoritative evidence.

This stage does **not** infer final point-in-time alias intervals from those dates.
That is the next stage after the evidence set passes integrity checks.

## No outcome leakage

This stage does not read:

- momentum;
- H1/H2 portfolio labels;
- Winner assignments;
- forward returns;
- benchmark returns;
- commonality factors.

It also does not perform a full 2021–2025 GDELT extraction.

## Fair-access requirement

Before running, set an SEC User-Agent with a real contact email:

PowerShell example:

`$env:SEC_USER_AGENT="Your Name your.email@example.com"`

The script defaults to a 0.15-second interval between submissions requests.
