# H3 Stage 3J — All-Transition Name Alignment Preflight

The Stage 3J builder first exposed `CI` and then `CPB` source-format alignment
stops. Failing one security at a time is inefficient.

This preflight does not build aliases and does not change the frozen policy.

It audits every in-sample authoritative company-name transition in one pass and
compares the final transition state with the independently resolved source name
using the same Stage 3J source precedence.

It also audits transition-chain continuity when a security has multiple events.

## Diagnostic classes

- `MATCH_POLICY_V2`
- `DISPLAY_PUNCTUATION_OR_TOKEN_SPACING_EQUIVALENT`
- `WORD_ORDER_ONLY_EQUIVALENT`
- `PREFIX_SUFFIX_OR_ABBREVIATION_DIFFERENCE`
- `SEMANTIC_OR_UNEXPLAINED_MISMATCH`

The compact/token diagnostics are for classification only. They are never
production aliases.

This audit exists specifically so any remaining normalization problem can be
fixed once, as a class, rather than one company at a time.
