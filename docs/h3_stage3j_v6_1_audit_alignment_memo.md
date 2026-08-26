# H3 Stage 3J V6.1 — Audit Alignment Patch

## What the latest audit established

The Stage 3J build itself is structurally clean on the two newly introduced
safety classes:

- alias-safety diagnostic: 0 rows;
- blocking cross/unresolved-issuer collision diagnostic: 0 rows;
- all five remaining overlapping aliases are explicitly same-issuer,
  same-CIK shared aliases;
- bare-ticker production aliases: 0;
- transition-alignment diagnostic: 0 rows.

The only two audit failures are legacy assertions from the pre-V6 policy:

1. HIGH ambiguity required `production_alias == full_normalized_alias`;
2. ticker-like issuer names required the same exact-string equality.

Those assertions became obsolete when Policy V5 introduced deterministic
qualified full-authoritative names for ticker-like legal cores.

Example structure:

    state legal core:        rtx
    raw state full alias:    rtx
    qualified full alias:    rtx corporation
    normalized legal core:   rtx

`rtx corporation` is MORE specific than bare `rtx`, not broader.

## Correct invariant

For HIGH-ambiguity and ticker-like rows, the production alias must satisfy:

- nonblank;
- conservative legal core exactly equals the frozen state legal core;
- AND either:
  - equals the raw full normalized state name; or
  - was selected through one of the frozen qualified-full-authoritative controls.

This preserves precision while permitting the exact safety mechanism introduced
by Policy V5.

## Methodology status

Frozen alias policy:
`H3_PIT_ATTENTION_ALIAS_POLICY_V5`

Policy checksum:
`c18b1ce9c421f52afb3d0d2ea85fe4e1e4f282fa5d14a85cefd9ccf21da2bb40`

UNCHANGED.

This is an audit-implementation correction only. No manifest rebuild is required.
No GDELT extraction or return/outcome data are involved.
