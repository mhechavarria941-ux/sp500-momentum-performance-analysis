# H3 Stage 3E — Deterministic Name-State Reconciliation

## Purpose

Stage 3D closes the exact-transition branch. The only remaining identity work is the 119-row `NAME_STATE_RECONCILIATION` universe.

Stage 3E reduces that universe without external research first.

## Evidence used

- Stage 3B2 historical NPORT company-name states;
- Stage 3C automatically resolved exact transition;
- Stage 3D authoritative true-renames and rejected false transitions;
- SEC current filer name;
- SEC former-name evidence restricted to the project period;
- project canonical company-name reference.

## Conservative normalization

The script performs only deterministic legal-style normalization:

- case/punctuation;
- leading `The`;
- apostrophe normalization;
- explicit security-class labels;
- trailing legal forms such as Inc., Corp., Ltd., PLC, LLC, N.V.;
- trailing Delaware/jurisdiction presentation where applicable.

It does **not** strip semantic words merely to force equality.

In particular, words such as:

- Group
- Holdings
- International
- Technologies
- Energy
- Financial
- Systems
- Health
- Digital
- Properties

remain part of the name core.

No fuzzy string matching, edit-distance matching, or embedding similarity is permitted.

## Automatic resolution rules

An identity can leave the research queue automatically only if:

1. already-resolved authoritative transition history explains every observed NPORT name state; or
2. already-rejected false transitions explain the apparent NPORT name variation; or
3. one stable NPORT legal-name core exactly equals the project/current SEC legal-name core after conservative normalization, with no project-period SEC former-name evidence.

All other cases remain research targets.

## Next stage

After the Stage 3E audit passes, only the reduced research manifest should be researched from primary sources.

Production point-in-time GDELT aliases are still not created here.
