from __future__ import annotations

import math
from pathlib import Path
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.spatial.distance import cosine


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v2-phase3a-duplicate-sector-column-fix"

EXP_DIR = ROOT / "reports" / "exploratory"

# Phase 1 inputs
PERSISTENCE_PATH = EXP_DIR / "post_h2_winner_persistence_by_security.csv"

# Phase 2 inputs
SECURITY_MONTH_PATH = EXP_DIR / "post_h2_commonality_security_month_contributions.csv"
SECURITY_SUMMARY_PATH = EXP_DIR / "post_h2_commonality_security_contributions.csv"
MONTH_SUMMARY_PATH = EXP_DIR / "post_h2_commonality_month_drivers.csv"
SECTOR_VARIANCE_PATH = EXP_DIR / "post_h2_commonality_sector_variance_contributions.csv"
PAIRWISE_PATH = EXP_DIR / "post_h2_commonality_residual_pairwise_correlations.csv"
PC1_SCORE_PATH = EXP_DIR / "post_h2_commonality_pc1_scores.csv"

# Phase 3A outputs
REPORT_PATH = EXP_DIR / "post_h2_phase3a_research_target_analysis.txt"
SECURITY_QUEUE_PATH = EXP_DIR / "post_h2_phase3a_security_research_queue.csv"
MONTH_QUEUE_PATH = EXP_DIR / "post_h2_phase3a_month_research_queue.csv"
MONTH_SECURITY_PATH = EXP_DIR / "post_h2_phase3a_month_security_driver_detail.csv"
MONTH_SECTOR_PATH = EXP_DIR / "post_h2_phase3a_month_sector_driver_detail.csv"
MONTH_SIMILARITY_PATH = EXP_DIR / "post_h2_phase3a_month_driver_similarity.csv"
SECURITY_COOCCURRENCE_PATH = EXP_DIR / "post_h2_phase3a_security_cooccurrence.csv"
RESEARCH_MANIFEST_PATH = EXP_DIR / "post_h2_phase3a_external_research_manifest.csv"

TOP_SECURITY_COUNT = 30
TOP_MONTH_COUNT = 15
TOP_SECURITIES_PER_MONTH = 12
TOP_SECTORS_PER_MONTH = 5

CANONICAL_SECTORS = [
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
]


def rule() -> str:
    return "=" * 122


def section(title: str) -> list[str]:
    return ["", rule(), title, rule()]


def pct(value: float, digits: int = 2) -> str:
    return f"{100.0 * float(value):.{digits}f}%"


def num(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def safe_cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)

    if np.allclose(a, 0.0) or np.allclose(b, 0.0):
        return math.nan

    return float(1.0 - cosine(a, b))


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        PERSISTENCE_PATH,
        SECURITY_MONTH_PATH,
        SECURITY_SUMMARY_PATH,
        MONTH_SUMMARY_PATH,
        SECTOR_VARIANCE_PATH,
        PAIRWISE_PATH,
        PC1_SCORE_PATH,
    ]

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing prerequisite exploratory output(s): "
            + ", ".join(missing)
        )

    lines = [
        rule(),
        "POST-H2 EXPLORATORY COMMONALITY — PHASE 3A RESEARCH TARGETS",
        rule(),
        "Status: EXPLORATORY / NON-CONFIRMATORY",
        "Purpose: convert Phase 1-2 return-commonality findings into a structured research queue",
        "H1 conclusion modified: NO",
        "H2 conclusion modified: NO",
        "",
        "This phase does NOT assign narrative/theme labels.",
        "It objectively identifies the securities and months that deserve external-source research next.",
    ]

    persistence = pd.read_csv(PERSISTENCE_PATH)
    security_month = pd.read_csv(SECURITY_MONTH_PATH)
    security_summary = pd.read_csv(SECURITY_SUMMARY_PATH)
    month_summary = pd.read_csv(MONTH_SUMMARY_PATH)
    sector_variance = pd.read_csv(SECTOR_VARIANCE_PATH)
    pairwise = pd.read_csv(PAIRWISE_PATH)
    pc1 = pd.read_csv(PC1_SCORE_PATH)

    for frame in (
        security_month,
        month_summary,
        pc1,
    ):
        if "analysis_month_number" in frame.columns:
            frame["analysis_month_number"] = pd.to_numeric(
                frame["analysis_month_number"],
                errors="raise",
            ).astype(int)

    for column in (
        "ranking_month_end_date",
        "return_period_end_date",
    ):
        if column in security_month.columns:
            security_month[column] = pd.to_datetime(
                security_month[column],
                errors="raise",
            )
        if column in month_summary.columns:
            month_summary[column] = pd.to_datetime(
                month_summary[column],
                errors="raise",
            )
        if column in pc1.columns:
            pc1[column] = pd.to_datetime(
                pc1[column],
                errors="raise",
            )

    lines += section("1. SECURITY RESEARCH QUEUE")

    security_queue = (
        security_summary
        .merge(
            persistence[
                [
                    "security_key",
                    "project_ticker",
                    "winner_months",
                    "eligible_months",
                    "winner_share_of_eligible_months",
                    "max_consecutive_winner_streak",
                    "winner_sector_count",
                    "latest_winner_sector",
                ]
            ],
            on=[
                "security_key",
                "project_ticker",
            ],
            how="left",
            validate="one_to_one",
        )
        .sort_values(
            [
                "cumulative_absolute_commonality_contribution",
                "winner_months",
                "project_ticker",
            ],
            ascending=[
                False,
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )

    if "gics_sectors_seen" not in security_queue.columns:
        raise RuntimeError(
            "Security queue is missing canonical gics_sectors_seen from "
            "the Phase 2 security contribution summary."
        )

    duplicate_sector_columns = [
        column
        for column in security_queue.columns
        if column.startswith("gics_sectors_seen_")
    ]

    if duplicate_sector_columns:
        raise RuntimeError(
            "Unexpected duplicate GICS sector-history columns after merge: "
            + ", ".join(duplicate_sector_columns)
        )

    security_queue["research_priority_rank"] = np.arange(
        1,
        len(security_queue) + 1,
    )

    security_queue["research_priority_band"] = pd.cut(
        security_queue["research_priority_rank"],
        bins=[0, 10, 30, len(security_queue)],
        labels=[
            "TIER_1_TOP_10",
            "TIER_2_TOP_30",
            "TIER_3_REMAINDER",
        ],
        include_lowest=True,
    ).astype(str)

    security_queue.to_csv(
        SECURITY_QUEUE_PATH,
        index=False,
    )

    lines += [
        f"Security research queue rows: {len(security_queue):,}",
        f"Tier 1 securities: {min(10, len(security_queue))}",
        f"Tier 2 cumulative securities: {min(TOP_SECURITY_COUNT, len(security_queue))}",
        "",
        "Top 15 research-priority securities:",
    ]

    for row in security_queue.head(15).itertuples(index=False):
        lines.append(
            f"{int(row.research_priority_rank):>2}. "
            f"{row.project_ticker:<8} | "
            f"Abs share {pct(row.share_of_total_absolute_commonality_contribution)} | "
            f"Winner months {int(row.winner_months):>2}/{int(row.eligible_months):>2} | "
            f"Max streak {int(row.max_consecutive_winner_streak):>2} | "
            f"{row.gics_sectors_seen}"
        )

    lines += section("2. MONTH RESEARCH QUEUE")

    month_queue = (
        month_summary
        .merge(
            pc1[
                [
                    "analysis_month_number",
                    "pc1_score",
                    "pc1_score_z",
                ]
            ],
            on="analysis_month_number",
            how="left",
            validate="one_to_one",
        )
        .sort_values(
            [
                "absolute_commonality_factor",
                "analysis_month_number",
            ],
            ascending=[
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )

    month_queue["research_priority_rank"] = np.arange(
        1,
        len(month_queue) + 1,
    )

    month_queue["research_priority_band"] = pd.cut(
        month_queue["research_priority_rank"],
        bins=[0, 5, 15, len(month_queue)],
        labels=[
            "TIER_1_TOP_5",
            "TIER_2_TOP_15",
            "TIER_3_REMAINDER",
        ],
        include_lowest=True,
    ).astype(str)

    month_queue.to_csv(
        MONTH_QUEUE_PATH,
        index=False,
    )

    lines += [
        f"Month research queue rows: {len(month_queue)}",
        "",
        "Top 15 research-priority months:",
    ]

    for row in month_queue.head(TOP_MONTH_COUNT).itertuples(index=False):
        lines.append(
            f"{int(row.research_priority_rank):>2}. "
            f"Month {int(row.analysis_month_number):>2} | "
            f"Ranking {pd.Timestamp(row.ranking_month_end_date).date()} | "
            f"Factor {pct(row.commonality_factor_equal_weight_residual, 4)} | "
            f"|Factor| {pct(row.absolute_commonality_factor, 4)} | "
            f"Positive residual sectors {int(row.positive_residual_sector_count):>2}/11 | "
            f"PC1 z {num(row.pc1_score_z)}"
        )

    lines += section("3. TOP MONTH SECURITY / SECTOR DRIVER DETAIL")

    top_months = set(
        month_queue.head(TOP_MONTH_COUNT)[
            "analysis_month_number"
        ].astype(int)
    )

    month_security = security_month[
        security_month[
            "analysis_month_number"
        ].isin(top_months)
    ].copy()

    month_security[
        "within_month_absolute_security_rank"
    ] = (
        month_security.groupby(
            "analysis_month_number"
        )["absolute_commonality_contribution"]
        .rank(
            method="first",
            ascending=False,
        )
        .astype(int)
    )

    month_security = month_security[
        month_security[
            "within_month_absolute_security_rank"
        ]
        <= TOP_SECURITIES_PER_MONTH
    ].sort_values(
        [
            "analysis_month_number",
            "within_month_absolute_security_rank",
        ]
    )

    month_security.to_csv(
        MONTH_SECURITY_PATH,
        index=False,
    )

    month_sector = (
        security_month[
            security_month[
                "analysis_month_number"
            ].isin(top_months)
        ]
        .groupby(
            [
                "analysis_month_number",
                "gics_sector",
            ],
            as_index=False,
        )["aggregate_commonality_contribution"]
        .sum()
        .rename(
            columns={
                "aggregate_commonality_contribution":
                "sector_aggregate_commonality_contribution"
            }
        )
    )

    month_sector[
        "absolute_sector_commonality_contribution"
    ] = month_sector[
        "sector_aggregate_commonality_contribution"
    ].abs()

    month_sector[
        "within_month_absolute_sector_rank"
    ] = (
        month_sector.groupby(
            "analysis_month_number"
        )["absolute_sector_commonality_contribution"]
        .rank(
            method="first",
            ascending=False,
        )
        .astype(int)
    )

    month_sector = month_sector[
        month_sector[
            "within_month_absolute_sector_rank"
        ]
        <= TOP_SECTORS_PER_MONTH
    ].sort_values(
        [
            "analysis_month_number",
            "within_month_absolute_sector_rank",
        ]
    )

    month_sector.to_csv(
        MONTH_SECTOR_PATH,
        index=False,
    )

    lines += [
        f"Top-month security driver rows: {len(month_security):,}",
        f"Top-month sector driver rows: {len(month_sector):,}",
    ]

    lines += section("4. MONTH-TO-MONTH DRIVER SIMILARITY")

    top_security_keys = (
        security_queue.head(TOP_SECURITY_COUNT)[
            "security_key"
        ].astype(str).tolist()
    )

    selected_months = (
        month_queue.head(TOP_MONTH_COUNT)[
            "analysis_month_number"
        ].astype(int).tolist()
    )

    contribution_matrix = (
        security_month[
            security_month[
                "analysis_month_number"
            ].isin(selected_months)
            & security_month[
                "security_key"
            ].astype(str).isin(top_security_keys)
        ]
        .pivot_table(
            index="analysis_month_number",
            columns="security_key",
            values="aggregate_commonality_contribution",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reindex(
            index=selected_months,
            columns=top_security_keys,
            fill_value=0.0,
        )
    )

    month_similarity_rows = []

    for month_a, month_b in combinations(
        selected_months,
        2,
    ):
        similarity = safe_cosine_similarity(
            contribution_matrix.loc[month_a].to_numpy(dtype=float),
            contribution_matrix.loc[month_b].to_numpy(dtype=float),
        )

        month_similarity_rows.append(
            {
                "analysis_month_number_a": month_a,
                "analysis_month_number_b": month_b,
                "cosine_similarity_top30_security_contributions": similarity,
                "absolute_similarity": abs(similarity)
                if math.isfinite(similarity)
                else math.nan,
            }
        )

    month_similarity = pd.DataFrame(
        month_similarity_rows
    ).sort_values(
        [
            "absolute_similarity",
            "cosine_similarity_top30_security_contributions",
        ],
        ascending=[
            False,
            False,
        ],
    )

    month_similarity.to_csv(
        MONTH_SIMILARITY_PATH,
        index=False,
    )

    lines += [
        "Most similar top-commonality month pairs by contribution pattern:",
    ]

    for row in month_similarity.head(10).itertuples(index=False):
        lines.append(
            f"Month {int(row.analysis_month_number_a):>2} <-> "
            f"Month {int(row.analysis_month_number_b):>2} | "
            f"cosine {num(row.cosine_similarity_top30_security_contributions)}"
        )

    lines += section("5. TOP-SECURITY CO-OCCURRENCE")

    top_presence = (
        security_month[
            security_month[
                "security_key"
            ].astype(str).isin(top_security_keys)
        ][
            [
                "analysis_month_number",
                "security_key",
                "project_ticker",
            ]
        ]
        .drop_duplicates()
    )

    ticker_map = (
        top_presence[
            [
                "security_key",
                "project_ticker",
            ]
        ]
        .drop_duplicates()
        .set_index("security_key")[
            "project_ticker"
        ]
        .to_dict()
    )

    security_cooccurrence_rows = []

    for key_a, key_b in combinations(
        top_security_keys,
        2,
    ):
        months_a = set(
            top_presence.loc[
                top_presence["security_key"].astype(str)
                == key_a,
                "analysis_month_number",
            ].astype(int)
        )
        months_b = set(
            top_presence.loc[
                top_presence["security_key"].astype(str)
                == key_b,
                "analysis_month_number",
            ].astype(int)
        )

        intersection = months_a & months_b
        union = months_a | months_b

        security_cooccurrence_rows.append(
            {
                "security_key_a": key_a,
                "ticker_a": ticker_map.get(key_a, ""),
                "security_key_b": key_b,
                "ticker_b": ticker_map.get(key_b, ""),
                "winner_months_a": len(months_a),
                "winner_months_b": len(months_b),
                "cooccurring_winner_months": len(intersection),
                "winner_month_jaccard": (
                    len(intersection) / len(union)
                    if union
                    else math.nan
                ),
            }
        )

    security_cooccurrence = pd.DataFrame(
        security_cooccurrence_rows
    ).sort_values(
        [
            "cooccurring_winner_months",
            "winner_month_jaccard",
        ],
        ascending=[
            False,
            False,
        ],
    )

    security_cooccurrence.to_csv(
        SECURITY_COOCCURRENCE_PATH,
        index=False,
    )

    lines += [
        "Most frequent top-driver Winner co-occurrences:",
    ]

    for row in security_cooccurrence.head(10).itertuples(index=False):
        lines.append(
            f"{row.ticker_a:<7} + {row.ticker_b:<7} | "
            f"Co-Winner months {int(row.cooccurring_winner_months):>2} | "
            f"Jaccard {num(row.winner_month_jaccard)}"
        )

    lines += section("6. EXTERNAL RESEARCH MANIFEST")

    manifest_rows = []

    for row in security_queue.head(TOP_SECURITY_COUNT).itertuples(index=False):
        manifest_rows.append(
            {
                "research_type": "SECURITY",
                "priority_rank": int(row.research_priority_rank),
                "security_key": row.security_key,
                "project_ticker": row.project_ticker,
                "analysis_month_number": "",
                "ranking_month_end_date": "",
                "gics_context": row.gics_sectors_seen,
                "quantitative_reason": (
                    f"absolute contribution share="
                    f"{float(row.share_of_total_absolute_commonality_contribution):.8f}; "
                    f"winner_months={int(row.winner_months)}; "
                    f"max_streak={int(row.max_consecutive_winner_streak)}"
                ),
                "research_fields_to_collect": (
                    "official_company_description; business_model; primary_products_services; "
                    "material_2021_2025_strategy_changes; major_acquisitions_divestitures; "
                    "AI_or_automation_exposure; energy_or_commodity_exposure; "
                    "consumer_attention_exposure; major_regulatory_or_litigation_events; "
                    "primary_source_urls"
                ),
                "preferred_source_policy": (
                    "SEC filings; company investor-relations releases; S&P/official index sources; "
                    "regulator or government sources; no Wikipedia"
                ),
            }
        )

    for row in month_queue.head(TOP_MONTH_COUNT).itertuples(index=False):
        manifest_rows.append(
            {
                "research_type": "MONTH",
                "priority_rank": int(row.research_priority_rank),
                "security_key": "",
                "project_ticker": "",
                "analysis_month_number": int(row.analysis_month_number),
                "ranking_month_end_date": pd.Timestamp(
                    row.ranking_month_end_date
                ).date().isoformat(),
                "gics_context": (
                    f"positive_residual_sectors="
                    f"{int(row.positive_residual_sector_count)}/11"
                ),
                "quantitative_reason": (
                    f"commonality_factor="
                    f"{float(row.commonality_factor_equal_weight_residual):.8f}; "
                    f"absolute_factor={float(row.absolute_commonality_factor):.8f}; "
                    f"pc1_z={float(row.pc1_score_z):.6f}"
                ),
                "research_fields_to_collect": (
                    "marketwide_events_near_ranking_and_holding_window; "
                    "major_macro_policy_events; sector_specific_shocks; "
                    "top_driver_company_events; broad_technology_product_or_demand_theme; "
                    "primary_source_urls"
                ),
                "preferred_source_policy": (
                    "Federal Reserve; BLS; BEA; SEC; company investor relations; "
                    "official agencies; S&P/official index sources; no Wikipedia"
                ),
            }
        )

    manifest = pd.DataFrame(
        manifest_rows
    )

    manifest.to_csv(
        RESEARCH_MANIFEST_PATH,
        index=False,
    )

    lines += [
        f"External research manifest rows: {len(manifest)} "
        f"({TOP_SECURITY_COUNT} securities + {TOP_MONTH_COUNT} months).",
        "No qualitative theme labels were assigned in this phase.",
    ]

    lines += section("7. INTERPRETATION BOUNDARY / NEXT STEP")

    lines += [
        "Phase 3A is a target-selection and clustering precursor, not a narrative result.",
        "The research queue is generated only from validated post-H2 return-commonality outputs.",
        "Month similarity uses the signed contribution vectors of the top 30 security drivers.",
        "Security co-occurrence measures simultaneous Winner membership, not causal linkage.",
        "The external research manifest intentionally specifies fields before qualitative coding begins.",
        "The next phase is Phase 3B: collect authoritative primary-source evidence for the Tier 1 securities and Tier 1/Tier 2 months, then code themes using a documented evidence ledger.",
        "Theme coding must distinguish company-specific events, sector shocks, and marketwide/macroeconomic events.",
        "No attention/news/search variable should be tested against returns until the evidence-led theme taxonomy is frozen.",
    ]

    lines += section("8. OUTPUTS")

    for path in (
        SECURITY_QUEUE_PATH,
        MONTH_QUEUE_PATH,
        MONTH_SECURITY_PATH,
        MONTH_SECTOR_PATH,
        MONTH_SIMILARITY_PATH,
        SECURITY_COOCCURRENCE_PATH,
        RESEARCH_MANIFEST_PATH,
    ):
        lines.append(str(path.relative_to(ROOT)))

    lines += [
        "",
        "POST_H2_PHASE3A_RESEARCH_TARGETS_COMPLETE",
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )
    print(report, end="")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
