from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-h3-gdelt-ambiguity-review-audit"

OUT_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

MANIFEST_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_daily_pilot_query_manifest.csv"
)
SUMMARY_PATH = OUT_DIR / "h3_gdelt_pilot_company_coverage_summary.csv"
WORKLIST_PATH = OUT_DIR / "h3_gdelt_pilot_ambiguity_review_worklist.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_gdelt_pilot_ambiguity_review_integrity_audit.txt"
)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        MANIFEST_PATH,
        SUMMARY_PATH,
        WORKLIST_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    manifest = pd.read_csv(MANIFEST_PATH)
    summary = pd.read_csv(SUMMARY_PATH)
    worklist = pd.read_csv(WORKLIST_PATH)

    failures = []
    passed = 0
    lines = [
        "=" * 108,
        "H3 GDELT PILOT AMBIGUITY REVIEW INTEGRITY AUDIT",
        "=" * 108,
        "Return/outcome analysis permitted: NO",
        "",
    ]

    def check(condition: bool, success: str, failure: str):
        nonlocal passed
        if bool(condition):
            lines.append("PASS: " + success)
            passed += 1
        else:
            lines.append("FAIL: " + failure)
            failures.append(failure)

    check(
        len(summary) == len(manifest) == 15,
        "Coverage summary contains all 15 pilot companies.",
        (
            f"Summary rows={len(summary)}, manifest rows={len(manifest)}."
        ),
    )

    check(
        set(summary["ticker"]) == set(manifest["ticker"]),
        "Coverage summary ticker set matches frozen pilot manifest.",
        "Coverage summary ticker set differs from manifest.",
    )

    check(
        summary["nonzero_anchor_windows"].between(0, 5).all(),
        "All nonzero-anchor counts lie in [0, 5].",
        "Invalid nonzero-anchor count detected.",
    )

    check(
        (summary["nonzero_anchor_windows"] >= 2).sum() == 15,
        "All 15 pilot companies meet the >=2/5 strict nonzero-anchor rule.",
        "At least one pilot company does not meet >=2/5 coverage.",
    )

    check(
        worklist["variant_rank"].between(1, 15).all(),
        "Variant worklist contains only frozen top-15 variants per company.",
        "Unexpected variant rank outside 1-15.",
    )

    check(
        worklist.loc[
            worklist["is_strict_alias"].eq(1),
            "suggested_review_status",
        ].eq(
            "ACCEPT_ALREADY_FROZEN_STRICT_ALIAS"
        ).all(),
        "All frozen strict aliases are automatically marked accepted.",
        "A strict alias has an incorrect review status.",
    )

    check(
        worklist.loc[
            worklist["is_strict_alias"].eq(0),
            "suggested_review_status",
        ].eq(
            "MANUAL_REVIEW_REQUIRED"
        ).all(),
        "Every non-strict variant remains manual-review-only.",
        "A non-strict variant was automatically accepted.",
    )

    high_tickers = set(
        manifest.loc[
            manifest["ambiguity_tier"].eq("HIGH"),
            "ticker",
        ]
    )
    worklist_high = set(
        worklist.loc[
            worklist["ambiguity_tier"].eq("HIGH"),
            "ticker",
        ]
    )

    check(
        high_tickers.issubset(worklist_high),
        "All HIGH-ambiguity companies appear in the review worklist.",
        "A HIGH-ambiguity company is missing from the worklist.",
    )

    forbidden = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )
    columns = {
        str(c).casefold()
        for c in list(summary.columns) + list(worklist.columns)
    }
    bad = [
        c
        for c in columns
        if any(fragment in c for fragment in forbidden)
    ]

    check(
        not bad,
        "Review outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like columns found: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = "H3_GDELT_PILOT_AMBIGUITY_REVIEW_INTEGRITY_AUDIT_FAILED"
    else:
        gate = "H3_GDELT_PILOT_AMBIGUITY_REVIEW_INTEGRITY_AUDIT_PASSED"

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        "",
        gate,
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
