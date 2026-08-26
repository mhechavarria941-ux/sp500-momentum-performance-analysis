# Stage 3J Preflight Resolution Memo

The batch preflight found exactly three final-state/source mismatches across
26 in-sample transition securities.

## CPB

Transition state: `CAMPBELL S`  
Independent NPORT source: `Campbell's Company/The`

Classification:
`DISPLAY_PUNCTUATION_OR_TOKEN_SPACING_EQUIVALENT`

Resolution:
Treat the compact alphanumeric legal-core equality as a deterministic display
equivalence and use the independently resolved authoritative spelling in the
final interval.

## FBHS

Terminal transition state:
`Fortune Brands Innovations, Inc.`

Static Stage 3I membership identity:
`Fortune Brands Home & Security`

The membership identity is the correct pre-transition name, not the terminal
post-transition name.

Resolution:
Validate the Stage 3I membership identity against the first event old-name
state. The authoritative event chain supplies the post-transition name.

## PENN

Terminal transition state:
`PENN Entertainment, Inc.`

Static Stage 3I membership identity:
`Penn National Gaming`

Same structural condition as FBHS.

Resolution:
Validate the membership identity against the first event old-name state. The
event chain supplies the post-transition name.

## Sequential chain result

No sequential transition-chain nonmatch was found.

## Frozen policy

Policy ID:
`H3_PIT_ATTENTION_ALIAS_POLICY_V3`

SHA-256:
`836ce9690d54e0278fb08c4c8e5027cc2333de3c8fe55a817861c7c11508b838`
