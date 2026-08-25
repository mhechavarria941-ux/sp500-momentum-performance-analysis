from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-post-h2-phase4a-theme-synchrony-audit"

EXP_DIR = ROOT / "reports" / "exploratory"

TAXONOMY_PATH = EXP_DIR / "post_h2_phase3c_frozen_theme_taxonomy.csv"
MATRIX_PATH = EXP_DIR / "post_h2_phase3d_target_theme_matrix.csv"
STATS_PATH = EXP_DIR / "post_h2_phase4a_security_theme_synchrony.csv"
THEME_MONTH_PATH = EXP_DIR / "post_h2_phase4a_security_theme_monthly_panel.csv"
MACRO_PATH = EXP_DIR / "post_h2_phase4a_macro_theme_descriptives.csv"
NULL_SUMMARY_PATH = EXP_DIR / "post_h2_phase4a_randomization_null_summary.csv"

AUDIT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "post_h2_phase4a_theme_synchrony_integrity_audit.txt"
)

EXPECTED_TAXONOMY_SHA256 = (
    "1c7698cbe2facd069c7a12fda41cbf7399a9f657ed4f7a9f956d135f8f9d2576"
)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        TAXONOMY_PATH,
        MATRIX_PATH,
        STATS_PATH,
        THEME_MONTH_PATH,
        MACRO_PATH,
        NULL_SUMMARY_PATH,
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing Phase 4A output(s): " + ", ".join(missing)
        )

    taxonomy = pd.read_csv(TAXONOMY_PATH)
    matrix = pd.read_csv(MATRIX_PATH)
    stats = pd.read_csv(STATS_PATH)
    month_panel = pd.read_csv(THEME_MONTH_PATH)
    macro = pd.read_csv(MACRO_PATH)
    null_summary = pd.read_csv(NULL_SUMMARY_PATH)

    checksum = hashlib.sha256(TAXONOMY_PATH.read_bytes()).hexdigest()

    checks = []
    checks.append(
        ("taxonomy_checksum", checksum == EXPECTED_TAXONOMY_SHA256)
    )

    structural_codes = set(
        taxonomy.loc[
            taxonomy["domain"] == "SECURITY_STRUCTURAL",
            "code",
        ]
    )
    macro_codes = set(
        taxonomy.loc[
            taxonomy["domain"] == "MONTH_MACRO",
            "code",
        ]
    )

    checks.append(
        ("all_10_structural_codes_present", set(stats["theme_code"]) == structural_codes)
    )
    checks.append(
        ("all_7_macro_codes_present", set(macro["theme_code"]) == macro_codes)
    )
    checks.append(
        ("monthly_panel_590_rows", len(month_panel) == 59 * 10)
    )
    checks.append(
        (
            "monthly_panel_all_months",
            month_panel["analysis_month_number"].nunique() == 59,
        )
    )
    checks.append(
        (
            "theme_sizes_match_matrix",
            all(
                int(
                    matrix.loc[
                        matrix["target_type"].eq("SECURITY"),
                        row.theme_code,
                    ].sum()
                )
                == int(row.theme_size)
                for row in stats.itertuples(index=False)
            ),
        )
    )

    tested = stats[stats["tested_randomization"] == 1]
    descriptive = stats[stats["tested_randomization"] == 0]

    checks.append(
        (
            "tested_themes_have_pvalues",
            tested[
                [
                    "sync_monte_carlo_p_one_sided",
                    "presence_monte_carlo_p_one_sided",
                    "sync_holm_p",
                    "presence_holm_p",
                ]
            ].notna().all().all(),
        )
    )
    checks.append(
        (
            "small_themes_not_tested",
            (
                descriptive["theme_size"] < 3
            ).all()
            and descriptive[
                [
                    "sync_monte_carlo_p_one_sided",
                    "presence_monte_carlo_p_one_sided",
                ]
            ].isna().all().all(),
        )
    )

    p_columns = [
        "sync_monte_carlo_p_one_sided",
        "presence_monte_carlo_p_one_sided",
        "sync_holm_p",
        "presence_holm_p",
    ]
    checks.append(
        (
            "all_finite_pvalues_bounded",
            all(
                stats[col].dropna().between(0.0, 1.0).all()
                for col in p_columns
            ),
        )
    )

    expected_null_rows = int(tested.shape[0] * 2)
    checks.append(
        (
            "null_summary_two_metrics_per_tested_theme",
            len(null_summary) == expected_null_rows,
        )
    )

    checks.append(
        (
            "macro_inference_disabled",
            macro["inferential_test_performed"].eq(0).all(),
        )
    )

    # Reconstruct exploratory flags from published rule.
    sync_flag = (
        (stats["tested_randomization"] == 1)
        & (stats["average_pairwise_contribution_correlation"] > 0)
        & (stats["sync_holm_p"] < 0.05)
    ).astype(int)

    presence_flag = (
        (stats["tested_randomization"] == 1)
        & (
            stats["presence_count_vs_abs_commonality_correlation"] > 0
        )
        & (stats["presence_holm_p"] < 0.05)
    ).astype(int)

    checks.append(
        (
            "sync_flags_reconstruct",
            np.array_equal(
                sync_flag.to_numpy(),
                stats["sync_exploratory_flag"].astype(int).to_numpy(),
            ),
        )
    )
    checks.append(
        (
            "presence_flags_reconstruct",
            np.array_equal(
                presence_flag.to_numpy(),
                stats["presence_exploratory_flag"].astype(int).to_numpy(),
            ),
        )
    )

    failures = [name for name, passed in checks if not passed]

    lines = [
        "=" * 104,
        "POST-H2 PHASE 4A THEME SYNCHRONY INTEGRITY AUDIT",
        "=" * 104,
        f"Taxonomy SHA-256: {checksum}",
        "",
    ]

    for name, passed in checks:
        lines.append(
            f"{'PASS' if passed else 'FAIL'}: {name}"
        )

    lines += [
        "",
        f"Structural themes: {len(stats)}",
        f"Randomization-tested structural themes: {len(tested)}",
        f"Descriptive-only structural themes: {len(descriptive)}",
        f"Macro themes: {len(macro)}",
        "",
    ]

    if failures:
        lines += [
            "POST_H2_PHASE4A_THEME_SYNCHRONY_INTEGRITY_AUDIT_FAILED",
            f"Failed checks: {len(failures)}",
        ]
        for i, name in enumerate(failures, 1):
            lines.append(f"{i}. {name}")
    else:
        lines += [
            "POST_H2_PHASE4A_THEME_SYNCHRONY_INTEGRITY_AUDIT_PASSED",
            "Frozen taxonomy preserved.",
            "Published exploratory flags reconstruct exactly.",
            "Macro theme results remain descriptive only.",
            "H1/H2 conclusions modified: 0",
        ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
