# H3 Stage 3D — Authoritative Exact Transition Closeout

Stage 3C produced 22 unresolved bounded name-transition research rows.

These 22 rows were researched against primary SEC/company evidence.

## Result

- 18 rows are genuine corporate/legal name changes.
- 4 rows are false historical-name transitions caused by source-label structure:
  - two Cisco rows are `Cisco Systems` / `Cisco Systems Inc Delaware` presentation variants;
  - two Federal Realty rows alternate between the parent REIT and its operating partnership.

No false transition is assigned an invented rename date.

## Date hierarchy

`exact_legal_effective_date` is the authoritative corporate/legal transition date.

`public_or_trading_effective_date` is separately retained when public rebranding or exchange presentation began on a later date.

This distinction is deliberate because the eventual GDELT attention-layer design may choose a transition-month overlap rule for old/new public names rather than treating a one-day legal cutover as a perfect media-language cutover.

That alias policy is **not** frozen in Stage 3D.

## Important special cases

- CPAY: legal corporate event on 2024-03-24; company/ticker public transition on 2024-03-25.
- ELV: legal name effective 2022-06-27; operating/ticker transition 2022-06-28.
- GEN: legal name effective 2022-11-07; ticker GEN begins 2022-11-08.
- RTX: legal name effective 2023-07-17; NYSE company-name presentation begins 2023-07-27.
- HIG: legal name effective 2025-02-06; NYSE presentation as new name begins 2025-02-18.
- RVTY: legal name effective 2023-04-26; RVTY ticker effective 2023-05-16.
- SRE: primary SEC evidence places the legal rename on 2023-05-12, earlier than the NPORT observation bound; authoritative evidence overrides the quarterly observation bound.

## Next scope

After Stage 3D passes, the only research rows remaining are the 119 `NAME_STATE_RECONCILIATION` cases.

Those should be reduced through deterministic normalization and primary-source identity checks before production PIT alias intervals are built.

No full-history GDELT extraction or return analysis is authorized.
