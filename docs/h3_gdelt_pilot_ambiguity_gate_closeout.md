# H3 GDELT Pilot — High-Ambiguity Review Closeout

## Decision

**AMBIGUITY REVIEW CLOSED — CONSERVATIVE STRICT-ALIAS POLICY RETAINED**

The direct-GDELT feasibility pilot passed all automated checks and all 15 pilot companies had strict nonzero organization coverage in at least 2 of 5 historical anchor windows.

The manual review of the two HIGH-ambiguity names, IRM and MOS, does **not** justify broadening the canonical attention aliases.

### IRM — Iron Mountain Incorporated

Accepted canonical aliases remain:

- `iron mountain incorporated`
- `iron mountain inc`

School, library, medical-center, and academic variants are rejected.

Issuer-adjacent phrases such as `iron mountain data centers`, `iron mountain incorporated united states`, and `boston iron mountain incorporated` are retained as **diagnostic only** rather than promoted into the production alias set.

Reason: strict aliases already produced nonzero coverage in 5/5 anchor windows, so there is no methodological need to trade precision for additional recall.

### MOS — The Mosaic Company

Accepted canonical alias remains:

- `mosaic company` / the already frozen strict company-name form

The broad word `mosaic` remains prohibited.

`mosaic co` is retained as **diagnostic only**. Although it can plausibly refer to the issuer, it is too short and ambiguous to add when the strict company-name query already produced nonzero coverage in 5/5 anchor windows.

Other Mosaic variants in the pilot refer to unrelated community, health, cultural, religious, financial, or commercial entities and are rejected.

## Methodological consequence

The pilot ambiguity gate can close without changing the frozen strict aliases.

This is preferable because the purpose of the attention layer is a **high-precision company-news proxy**, not maximization of article counts.

No return or outcome data were used to make these decisions.

## Next authorized step

Build the full point-in-time 2021–2025 company identity/query manifest for the complete historical S&P 500 security universe.

Before downloading full-history attention data, the full-universe manifest must be audited for:

- company-name coverage;
- historical corporate-name changes;
- ticker changes;
- ambiguous generic names;
- spin-offs / mergers / predecessor identities;
- exact effective dates for alias changes where needed.

Only after that identity/query manifest passes should the full monthly GDELT attention layer be downloaded.

H3 inference remains unauthorized.
