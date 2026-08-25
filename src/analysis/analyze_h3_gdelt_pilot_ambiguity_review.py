from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-h3-gdelt-ambiguity-review"

OUT_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

MANIFEST_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_daily_pilot_query_manifest.csv"
)
ANCHOR_PATH = OUT_DIR / "h3_gdelt_daily_pilot_anchor_coverage.csv"
VARIANT_PATH = OUT_DIR / "h3_gdelt_daily_pilot_org_variants.csv"

SUMMARY_PATH = OUT_DIR / "h3_gdelt_pilot_company_coverage_summary.csv"
WORKLIST_PATH = OUT_DIR / "h3_gdelt_pilot_ambiguity_review_worklist.csv"
REPORT_PATH = OUT_DIR / "h3_gdelt_pilot_ambiguity_review_report.txt"

TOP_VARIANTS_PER_COMPANY = 15


def rule() -> str:
    return "=" * 112


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (MANIFEST_PATH, ANCHOR_PATH, VARIANT_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    manifest = pd.read_csv(MANIFEST_PATH)
    anchor = pd.read_csv(ANCHOR_PATH)
    variants = pd.read_csv(VARIANT_PATH)

    # ------------------------------------------------------------------
    # Company coverage summary
    # ------------------------------------------------------------------
    coverage = (
        anchor.assign(
            nonzero_anchor=(
                pd.to_numeric(
                    anchor["matched_source_documents"],
                    errors="raise",
                ) > 0
            ).astype(int)
        )
        .groupby(
            [
                "ticker",
                "canonical_company_name",
                "ambiguity_tier",
            ],
            as_index=False,
        )
        .agg(
            nonzero_anchor_windows=("nonzero_anchor", "sum"),
            total_strict_matched_source_documents=(
                "matched_source_documents",
                "sum",
            ),
            mean_mentions_per_100k=(
                "mentions_per_100k_source_documents",
                "mean",
            ),
            median_mentions_per_100k=(
                "mentions_per_100k_source_documents",
                "median",
            ),
            min_mentions_per_100k=(
                "mentions_per_100k_source_documents",
                "min",
            ),
            max_mentions_per_100k=(
                "mentions_per_100k_source_documents",
                "max",
            ),
        )
    )

    coverage = coverage.merge(
        manifest[
            [
                "ticker",
                "strict_aliases_pipe",
                "historical_alias_note",
                "review_note",
            ]
        ],
        on="ticker",
        how="left",
        validate="one_to_one",
    )

    coverage["coverage_status"] = pd.cut(
        coverage["nonzero_anchor_windows"],
        bins=[-1, 1, 3, 5],
        labels=[
            "SPARSE_0_TO_1_OF_5",
            "USABLE_2_TO_3_OF_5",
            "STRONG_4_TO_5_OF_5",
        ],
    ).astype(str)

    coverage = coverage.sort_values(
        [
            "ambiguity_tier",
            "nonzero_anchor_windows",
            "ticker",
        ],
        ascending=[
            True,
            False,
            True,
        ],
    )

    coverage.to_csv(
        SUMMARY_PATH,
        index=False,
    )

    # ------------------------------------------------------------------
    # Variant review worklist
    # ------------------------------------------------------------------
    variants = variants.copy()

    variants["variant_rank"] = pd.to_numeric(
        variants["variant_rank"],
        errors="raise",
    ).astype(int)

    variants = variants[
        variants["variant_rank"] <= TOP_VARIANTS_PER_COMPANY
    ].copy()

    variants = variants.merge(
        manifest[
            [
                "ticker",
                "strict_aliases_pipe",
                "historical_alias_note",
                "review_note",
            ]
        ],
        on="ticker",
        how="left",
        validate="many_to_one",
    )

    variants["suggested_review_status"] = variants[
        "is_strict_alias"
    ].map(
        {
            1: "ACCEPT_ALREADY_FROZEN_STRICT_ALIAS",
            0: "MANUAL_REVIEW_REQUIRED",
        }
    )

    variants["manual_review_decision"] = ""
    variants["manual_review_rationale"] = ""

    variants["manual_review_priority"] = variants[
        "ambiguity_tier"
    ].map(
        {
            "HIGH": 1,
            "MEDIUM": 2,
            "LOW": 3,
        }
    ).fillna(9)

    worklist = variants.sort_values(
        [
            "manual_review_priority",
            "ticker",
            "variant_rank",
        ]
    )

    worklist.to_csv(
        WORKLIST_PATH,
        index=False,
    )

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    lines = [
        rule(),
        "H3 ATTENTION FEASIBILITY — GDELT PILOT AMBIGUITY REVIEW",
        rule(),
        "Scope: company-name coverage and organization-variant review only",
        "Return/outcome analysis permitted: NO",
        "",
        "Pilot companies: 15",
        "Historical anchor windows per company: 5",
        "",
        rule(),
        "1. COMPANY COVERAGE",
        rule(),
    ]

    for row in coverage.sort_values(
        [
            "nonzero_anchor_windows",
            "mean_mentions_per_100k",
        ],
        ascending=[
            False,
            False,
        ],
    ).itertuples(index=False):
        lines.append(
            f"{row.ticker:<5} | "
            f"{row.ambiguity_tier:<6} | "
            f"nonzero {int(row.nonzero_anchor_windows)}/5 | "
            f"mean {float(row.mean_mentions_per_100k):.4f} per 100k | "
            f"{row.coverage_status}"
        )

    lines += [
        "",
        rule(),
        "2. HIGH-AMBIGUITY VARIANTS",
        rule(),
    ]

    high = worklist[
        worklist["ambiguity_tier"].eq("HIGH")
    ]

    if high.empty:
        lines.append("No HIGH-ambiguity variant rows were found.")
    else:
        for ticker, group in high.groupby("ticker", sort=True):
            lines.append("")
            lines.append(f"{ticker}:")
            for row in group.itertuples(index=False):
                lines.append(
                    f"  rank {int(row.variant_rank):>2} | "
                    f"docs {int(row.weighted_source_documents):>7} | "
                    f"strict {int(row.is_strict_alias)} | "
                    f"{row.normalized_organization_variant}"
                )

    lines += [
        "",
        rule(),
        "3. REVIEW RULE",
        rule(),
        (
            "Only variants already present in the frozen strict-alias manifest "
            "are accepted automatically."
        ),
        (
            "Every other variant remains unaccepted until manually reviewed. "
            "No broad variant may be promoted simply because it is frequent."
        ),
        (
            "HIGH-ambiguity companies must have every displayed non-strict "
            "variant explicitly classified before the pilot ambiguity gate can close."
        ),
        (
            "MEDIUM/LOW companies may retain their current strict aliases if "
            "coverage is adequate; non-strict variants are informational unless "
            "there is clear issuer-specific evidence to add them in a later mapping version."
        ),
        "",
        "H3_GDELT_PILOT_AMBIGUITY_REVIEW_WORKLIST_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        text,
        encoding="utf-8",
    )

    print(text, end="")
    print(f"Coverage summary saved: {SUMMARY_PATH}")
    print(f"Review worklist saved: {WORKLIST_PATH}")


if __name__ == "__main__":
    main()
