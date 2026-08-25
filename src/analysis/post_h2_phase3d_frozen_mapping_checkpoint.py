from __future__ import annotations

# This file records the frozen Phase 3D mapping used by the project.
# It is intentionally data-like and deterministic: code assignments may not
# be altered without creating a new version/sensitivity analysis.
#
# Canonical inputs:
# reports/exploratory/post_h2_phase3b_evidence_ledger_all_batches.csv
# reports/exploratory/post_h2_phase3c_frozen_theme_taxonomy.csv
# reports/exploratory/post_h2_phase3b_research_target_packet.csv
#
# Frozen taxonomy SHA-256:
EXPECTED_TAXONOMY_SHA256 = "1c7698cbe2facd069c7a12fda41cbf7399a9f657ed4f7a9f956d135f8f9d2576"

# The authoritative canonical Phase 3D outputs are:
# reports/exploratory/post_h2_phase3d_evidence_to_theme_bridge.csv
# reports/exploratory/post_h2_phase3d_target_theme_matrix.csv
# reports/exploratory/post_h2_phase3d_theme_prevalence.csv
# reports/exploratory/post_h2_phase3d_theme_cooccurrence.csv
#
# This checkpoint intentionally preserves the generated bridge/matrix as the
# exact coding decision ledger. Any later recoding requires a new version.
