# H3 Stage 3L — Full 2021–2025 Direct-GDELT Attention Extraction

**Protocol:** `H3_FULL_GDELT_ATTENTION_EXTRACTION_V1`  
**Version:** `2026-08-25-v1`  
**SHA-256:** `ab400af7220f4b10a60672c5d6fa1719b14b319bf6d6d9b60a4e7bcfb28e780c`

## Authorization

Stage 3L runs only after the Stage 3J alias-manifest audit and Stage 3K coverage/missingness gate pass. The alias policy remains frozen at `H3_PIT_ATTENTION_ALIAS_POLICY_V5`.

## Scope

`2021-01-01 <= date < 2026-01-01`, exactly **1,826** daily GDELT GKG 1.0 files.

## Source and matching

Direct daily files: `https://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip`. `NUMARTS` is the source-document weight and `ORGANIZATIONS` is matched by the same deterministic full/core exact normalization used by Stage 3K. No fuzzy, substring, semantic, or ticker matching is permitted.

## Checkpoint design

Each day is downloaded, SHA-256 hashed, parsed, reduced to a compressed security-day cache, given metadata, and then the raw zip is deleted. A cache is reused only when the date, protocol checksum, Stage 3J manifest checksum, cache schema, and parser-contract version agree. Cache validity deliberately does not depend on the cosmetic runner version.

## Storage

Daily observations are consolidated into five compressed yearly shards (2021–2025) rather than one giant in-memory frame. A compact monthly security-attention panel is also produced.

## Monthly attention

For security *i* and calendar month *t*: `sum(matched NUMARTS) / sum(total GKG NUMARTS)` over dates when its PIT alias is active. Entry/exit months can have fewer eligible days. Rename months preserve daily PIT name boundaries and are aggregated without backcasting.

## Outcome firewall

This stage reads no returns, momentum, Winner labels, commonality factors, or H3 outcomes. After a passing audit, the next stage is H3 statistical preregistration before any attention/outcome join.
