from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v2-post-h2-phase3a-research-targets-audit"

EXP_DIR = ROOT / "reports" / "exploratory"

SECURITY_QUEUE_PATH = EXP_DIR / "post_h2_phase3a_security_research_queue.csv"
MONTH_QUEUE_PATH = EXP_DIR / "post_h2_phase3a_month_research_queue.csv"
MONTH_SECURITY_PATH = EXP_DIR / "post_h2_phase3a_month_security_driver_detail.csv"
MONTH_SECTOR_PATH = EXP_DIR / "post_h2_phase3a_month_sector_driver_detail.csv"
MONTH_SIMILARITY_PATH = EXP_DIR / "post_h2_phase3a_month_driver_similarity.csv"
SECURITY_COOCCURRENCE_PATH = EXP_DIR / "post_h2_phase3a_security_cooccurrence.csv"
RESEARCH_MANIFEST_PATH = EXP_DIR / "post_h2_phase3a_external_research_manifest.csv"
SECURITY_SUMMARY_PATH = EXP_DIR / "post_h2_commonality_security_contributions.csv"
MONTH_SUMMARY_PATH = EXP_DIR / "post_h2_commonality_month_drivers.csv"

AUDIT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "post_h2_phase3a_research_targets_integrity_audit.txt"
)

TOP_SECURITY_COUNT = 30
TOP_MONTH_COUNT = 15


def section(title: str) -> list[str]:
    rule = "=" * 108
    return [rule, title, rule]


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        SECURITY_QUEUE_PATH,
        MONTH_QUEUE_PATH,
        MONTH_SECURITY_PATH,
        MONTH_SECTOR_PATH,
        MONTH_SIMILARITY_PATH,
        SECURITY_COOCCURRENCE_PATH,
        RESEARCH_MANIFEST_PATH,
        SECURITY_SUMMARY_PATH,
        MONTH_SUMMARY_PATH,
    ]

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing Phase 3A output(s): " + ", ".join(missing)
        )

    lines = section(
        "POST-H2 PHASE 3A RESEARCH TARGETS INTEGRITY AUDIT"
    )
    lines += [
        "Mode: local exploratory-output verification",
        "H1/H2 conclusion changes permitted: NO",
        "",
    ]

    failures: list[str] = []
    passed = 0

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if condition:
            lines.append(f"PASS: {success}")
            passed += 1
        else:
            lines.append(f"FAIL: {failure}")
            failures.append(failure)

    security_queue = pd.read_csv(SECURITY_QUEUE_PATH)
    month_queue = pd.read_csv(MONTH_QUEUE_PATH)
    month_security = pd.read_csv(MONTH_SECURITY_PATH)
    month_sector = pd.read_csv(MONTH_SECTOR_PATH)
    month_similarity = pd.read_csv(MONTH_SIMILARITY_PATH)
    cooccurrence = pd.read_csv(SECURITY_COOCCURRENCE_PATH)
    manifest = pd.read_csv(RESEARCH_MANIFEST_PATH)

    security_source = pd.read_csv(SECURITY_SUMMARY_PATH)
    month_source = pd.read_csv(MONTH_SUMMARY_PATH)

    lines += section("1. SECURITY QUEUE")

    check(
        len(security_queue) == len(security_source),
        "Security queue preserves every Phase 2 security summary row.",
        (
            f"Security queue rows={len(security_queue)}, "
            f"source rows={len(security_source)}."
        ),
    )

    check(
        not security_queue.duplicated(
            [
                "security_key",
                "project_ticker",
            ]
        ).any(),
        "Security queue contains one row per security/ticker.",
        "Security queue contains duplicate security/ticker rows.",
    )

    check(
        "gics_sectors_seen" in security_queue.columns
        and not any(
            column.startswith("gics_sectors_seen_")
            for column in security_queue.columns
        ),
        (
            "Security queue contains one canonical gics_sectors_seen field "
            "with no merge-suffix duplicates."
        ),
        "Security queue GICS sector-history columns are ambiguous.",
    )

    expected_ranks = np.arange(
        1,
        len(security_queue) + 1,
    )

    check(
        np.array_equal(
            security_queue[
                "research_priority_rank"
            ].to_numpy(dtype=int),
            expected_ranks,
        ),
        "Security priority ranks are contiguous from 1 to N.",
        "Security priority ranks are not contiguous.",
    )

    check(
        security_queue[
            "cumulative_absolute_commonality_contribution"
        ].is_monotonic_decreasing,
        "Security queue is sorted by cumulative absolute commonality contribution.",
        "Security queue sort order is incorrect.",
    )

    lines += section("2. MONTH QUEUE")

    check(
        len(month_queue) == len(month_source) == 59,
        "Month queue preserves all 59 observable Phase 2 months.",
        (
            f"Month queue rows={len(month_queue)}, "
            f"source rows={len(month_source)}."
        ),
    )

    check(
        month_queue[
            "absolute_commonality_factor"
        ].is_monotonic_decreasing,
        "Month queue is sorted by absolute commonality-factor magnitude.",
        "Month queue sort order is incorrect.",
    )

    check(
        set(
            month_queue.head(TOP_MONTH_COUNT)[
                "analysis_month_number"
            ].astype(int)
        )
        == set(
            month_security[
                "analysis_month_number"
            ].astype(int)
        ),
        "Top-month security detail covers exactly the selected top 15 months.",
        "Top-month security detail month set differs from queue.",
    )

    check(
        set(
            month_queue.head(TOP_MONTH_COUNT)[
                "analysis_month_number"
            ].astype(int)
        )
        == set(
            month_sector[
                "analysis_month_number"
            ].astype(int)
        ),
        "Top-month sector detail covers exactly the selected top 15 months.",
        "Top-month sector detail month set differs from queue.",
    )

    lines += section("3. SIMILARITY / CO-OCCURRENCE OUTPUTS")

    expected_month_pairs = math.comb(
        TOP_MONTH_COUNT,
        2,
    )
    check(
        len(month_similarity) == expected_month_pairs,
        (
            "Month similarity output contains all "
            f"{TOP_MONTH_COUNT} choose 2 = {expected_month_pairs} pairs."
        ),
        (
            f"Month similarity rows={len(month_similarity)}, "
            f"expected {expected_month_pairs}."
        ),
    )

    similarity_values = pd.to_numeric(
        month_similarity[
            "cosine_similarity_top30_security_contributions"
        ],
        errors="coerce",
    ).dropna()

    check(
        similarity_values.between(
            -1.0 - 1e-12,
            1.0 + 1e-12,
        ).all(),
        "All finite month cosine similarities lie in [-1, 1].",
        "At least one month cosine similarity is outside [-1, 1].",
    )

    expected_security_pairs = math.comb(
        min(
            TOP_SECURITY_COUNT,
            len(security_queue),
        ),
        2,
    )

    check(
        len(cooccurrence) == expected_security_pairs,
        (
            "Security co-occurrence output contains all top-driver "
            f"pair combinations ({expected_security_pairs})."
        ),
        (
            f"Security co-occurrence rows={len(cooccurrence)}, "
            f"expected {expected_security_pairs}."
        ),
    )

    check(
        pd.to_numeric(
            cooccurrence[
                "winner_month_jaccard"
            ],
            errors="coerce",
        ).dropna().between(0.0, 1.0).all(),
        "All finite security co-occurrence Jaccard values lie in [0, 1].",
        "At least one security Jaccard value is outside [0, 1].",
    )

    lines += section("4. EXTERNAL RESEARCH MANIFEST")

    check(
        len(manifest)
        == min(TOP_SECURITY_COUNT, len(security_queue))
        + TOP_MONTH_COUNT,
        "Research manifest contains the intended security and month targets.",
        (
            f"Manifest rows={len(manifest)}, expected "
            f"{min(TOP_SECURITY_COUNT, len(security_queue)) + TOP_MONTH_COUNT}."
        ),
    )

    check(
        set(manifest["research_type"])
        == {
            "SECURITY",
            "MONTH",
        },
        "Research manifest contains only SECURITY and MONTH target types.",
        "Research manifest contains unexpected target types.",
    )

    check(
        manifest[
            "preferred_source_policy"
        ].astype(str).str.contains(
            "no Wikipedia",
            case=False,
            regex=False,
        ).all(),
        "Every research-manifest row records the no-Wikipedia source policy.",
        "At least one research-manifest row lacks the source policy.",
    )

    lines += section("5. FINAL GATE")

    if failures:
        lines += [
            "POST_H2_PHASE3A_RESEARCH_TARGETS_INTEGRITY_AUDIT_FAILED",
            f"Passed checks: {passed}",
            f"Failed checks: {len(failures)}",
        ]
        for number, failure in enumerate(
            failures,
            start=1,
        ):
            lines.append(f"{number}. {failure}")
    else:
        lines += [
            "POST_H2_PHASE3A_RESEARCH_TARGETS_INTEGRITY_AUDIT_PASSED",
            f"Passed checks: {passed}",
            "Security and month research queues are complete and deterministic.",
            "No qualitative theme labels were introduced.",
            "H1/H2 conclusions modified: 0",
        ]

    AUDIT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(
        text,
        encoding="utf-8",
    )
    print(text, end="")
    print(f"Report saved: {AUDIT_PATH}")


if __name__ == "__main__":
    main()
