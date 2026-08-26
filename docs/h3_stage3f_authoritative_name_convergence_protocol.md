# H3 Stage 3F — Authoritative Name Convergence

## Why Stage 3E left 118 rows

Stage 3E deliberately required the project `company_name_reference` to agree with the historical NPORT/SEC name core. That is too strict for the attention layer because `company_name_reference` contains provider-style abbreviations, security-class labels, and shortened display names.

Examples in the Stage 3E research manifest include forms such as:

- `CBRE GROUP INC   A`
- `MARRIOTT INTERNATIONAL  CL A`
- `COGNIZANT TECH SOLUTIONS A`
- `FIDELITY NATIONAL INFO SERV`

Those strings remain useful project labels, but they do not need to become the authoritative media-attention alias when SEC current identity and SEC-filed NPORT historical issuer names agree.

## Frozen Stage 3F rule A — project-reference presentation differences

A `RESEARCH_PROJECT_VS_NPORT_NAME_CORE_CONFLICT` row is automatically reconciled only when:

1. there is exactly one NPORT registry core; and
2. the SEC current filer-name registry core exactly equals that NPORT core.

The project provider-style name is then retained for project identity but is not treated as the production attention-name authority.

## Frozen Stage 3F rule B — SEC former-name metadata

A former-name row is automatically reconciled only when:

1. SEC current filer name and the single NPORT registry core agree;
2. all project-overlapping SEC former-name rows have complete `from` and `to` dates; and
3. every such former name has exactly the same conservative registry core as the SEC/NPORT current issuer.

If even one former name is semantically distinct, the identity remains research.

## Conservative registry normalization

Only the following may be normalized:

- capitalization and punctuation;
- `&` versus `AND`;
- leading/trailing `THE`;
- explicit security-class presentation;
- EDGAR slash-jurisdiction labels such as `/DE/`;
- trailing legal forms such as Inc., Corp., Co., Ltd., PLC, LLC, N.V.

No fuzzy matching is used.

No word-order changes are allowed.

Semantic words such as Group, Holdings, International, Technologies, Energy, Financial, Systems, Health, and Digital are not stripped to force agreement.

## Next stage

After Stage 3F passes, only the reduced research manifest should receive additional primary-source research.

Production PIT GDELT alias intervals remain unauthorized.
