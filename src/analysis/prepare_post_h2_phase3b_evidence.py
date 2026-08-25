from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-post-h2-phase3b-evidence-preparation"

EXP_DIR = ROOT / "reports" / "exploratory"

MANIFEST_PATH = EXP_DIR / "post_h2_phase3a_external_research_manifest.csv"
SECURITY_QUEUE_PATH = EXP_DIR / "post_h2_phase3a_security_research_queue.csv"
MONTH_QUEUE_PATH = EXP_DIR / "post_h2_phase3a_month_research_queue.csv"

REPORT_PATH = EXP_DIR / "post_h2_phase3b_evidence_preparation.txt"
TARGET_PACKET_PATH = EXP_DIR / "post_h2_phase3b_research_target_packet.csv"
EVIDENCE_LEDGER_PATH = EXP_DIR / "post_h2_phase3b_evidence_ledger_template.csv"
CODING_GUIDE_PATH = EXP_DIR / "post_h2_phase3b_evidence_coding_guide.csv"

TOP_SECURITY_COUNT = 30
TOP_MONTH_COUNT = 15


def rule() -> str:
    return "=" * 118


def section(title: str) -> list[str]:
    return ["", rule(), title, rule()]


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        MANIFEST_PATH,
        SECURITY_QUEUE_PATH,
        MONTH_QUEUE_PATH,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing Phase 3A prerequisite(s): " + ", ".join(missing)
        )

    manifest = pd.read_csv(MANIFEST_PATH)
    securities = pd.read_csv(SECURITY_QUEUE_PATH)
    months = pd.read_csv(MONTH_QUEUE_PATH)

    security_targets = (
        securities
        .sort_values("research_priority_rank")
        .head(TOP_SECURITY_COUNT)
        .copy()
    )

    month_targets = (
        months
        .sort_values("research_priority_rank")
        .head(TOP_MONTH_COUNT)
        .copy()
    )

    # Build a compact packet intended for external-source research.
    packet_rows = []

    for row in security_targets.itertuples(index=False):
        packet_rows.append(
            {
                "target_type": "SECURITY",
                "priority_rank": int(row.research_priority_rank),
                "security_key": row.security_key,
                "project_ticker": row.project_ticker,
                "analysis_month_number": "",
                "ranking_month_end_date": "",
                "gics_context": row.gics_sectors_seen,
                "quantitative_context": (
                    f"abs_contribution_share="
                    f"{float(row.share_of_total_absolute_commonality_contribution):.10f}; "
                    f"winner_months={int(row.winner_months)}; "
                    f"winner_share={float(row.winner_share_of_eligible_months):.10f}; "
                    f"max_streak={int(row.max_consecutive_winner_streak)}"
                ),
                "research_scope": (
                    "company business model and primary products/services; "
                    "material 2021-2025 strategy changes; acquisitions/divestitures; "
                    "major product cycles; AI/automation exposure; commodity/energy exposure; "
                    "consumer/demand exposure; regulatory/litigation events; "
                    "major company-specific catalysts"
                ),
                "preferred_primary_sources": (
                    "SEC filings; company investor relations; regulator/government sources; "
                    "S&P/official index sources"
                ),
            }
        )

    for row in month_targets.itertuples(index=False):
        packet_rows.append(
            {
                "target_type": "MONTH",
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
                "quantitative_context": (
                    f"commonality_factor="
                    f"{float(row.commonality_factor_equal_weight_residual):.10f}; "
                    f"abs_factor={float(row.absolute_commonality_factor):.10f}; "
                    f"pc1_z={float(row.pc1_score_z):.8f}"
                ),
                "research_scope": (
                    "marketwide events around ranking/holding window; monetary/fiscal policy; "
                    "inflation/labor/growth shocks; sector shocks; technology/product cycles; "
                    "top-driver company events; major regulatory/geopolitical developments"
                ),
                "preferred_primary_sources": (
                    "Federal Reserve; BLS; BEA; SEC; company investor relations; "
                    "regulator/government sources; S&P/official index sources"
                ),
            }
        )

    packet = pd.DataFrame(packet_rows)

    expected_rows = min(TOP_SECURITY_COUNT, len(securities)) + min(
        TOP_MONTH_COUNT, len(months)
    )
    if len(packet) != expected_rows:
        raise RuntimeError(
            f"Research packet rows={len(packet)}, expected {expected_rows}."
        )

    packet.to_csv(TARGET_PACKET_PATH, index=False)

    # Blank evidence ledger. One target can have many evidence rows.
    ledger_columns = [
        "target_type",
        "priority_rank",
        "security_key",
        "project_ticker",
        "analysis_month_number",
        "ranking_month_end_date",
        "evidence_id",
        "evidence_date",
        "source_type",
        "source_organization",
        "source_title",
        "source_url",
        "primary_source_flag",
        "event_scope",
        "event_category",
        "timing_relation_to_ranking",
        "evidence_summary",
        "short_quote_max_25_words",
        "provisional_theme_code",
        "supports_cross_sector_commonality_flag",
        "confidence_level",
        "researcher_notes",
    ]

    ledger = pd.DataFrame(columns=ledger_columns)
    ledger.to_csv(EVIDENCE_LEDGER_PATH, index=False)

    coding_guide = pd.DataFrame(
        [
            {
                "field": "source_type",
                "allowed_or_guidance": (
                    "SEC_FILING | COMPANY_IR | FEDERAL_RESERVE | BLS | BEA | "
                    "REGULATOR_GOVERNMENT | SP_INDEX_PROVIDER | OTHER_PRIMARY"
                ),
            },
            {
                "field": "primary_source_flag",
                "allowed_or_guidance": "YES only for authoritative original-source evidence",
            },
            {
                "field": "event_scope",
                "allowed_or_guidance": (
                    "COMPANY_SPECIFIC | SECTOR | CROSS_SECTOR | MARKETWIDE_MACRO"
                ),
            },
            {
                "field": "event_category",
                "allowed_or_guidance": (
                    "Leave descriptive during collection; do not force a final taxonomy yet"
                ),
            },
            {
                "field": "timing_relation_to_ranking",
                "allowed_or_guidance": (
                    "PRE_RANKING | RANKING_WINDOW | HOLDING_WINDOW | POST_HOLDING | BACKGROUND"
                ),
            },
            {
                "field": "provisional_theme_code",
                "allowed_or_guidance": (
                    "Leave blank unless directly supported by evidence. "
                    "Final theme taxonomy is frozen only after evidence collection."
                ),
            },
            {
                "field": "supports_cross_sector_commonality_flag",
                "allowed_or_guidance": "YES | NO | UNCLEAR",
            },
            {
                "field": "confidence_level",
                "allowed_or_guidance": "HIGH | MEDIUM | LOW",
            },
            {
                "field": "source_policy",
                "allowed_or_guidance": (
                    "Prefer SEC/company IR/Fed/BLS/BEA/regulators/S&P. No Wikipedia."
                ),
            },
        ]
    )

    coding_guide.to_csv(CODING_GUIDE_PATH, index=False)

    lines = [
        rule(),
        "POST-H2 PHASE 3B — AUTHORITATIVE EVIDENCE PREPARATION",
        rule(),
        "Status: EXPLORATORY / NON-CONFIRMATORY",
        "H1 conclusion modified: NO",
        "H2 conclusion modified: NO",
        "",
        "Purpose: freeze the external-research target set and evidence schema before qualitative coding.",
    ]

    lines += section("1. TARGET SET")
    lines += [
        f"Security targets: {len(security_targets)}",
        f"Month targets: {len(month_targets)}",
        f"Total research targets: {len(packet)}",
        "",
        "Security targets are the top Phase 3A contribution-ranked securities.",
        "Month targets are the top Phase 3A absolute-commonality-ranked months.",
        "No target was selected using external narratives.",
    ]

    lines += section("2. EVIDENCE RULES")
    lines += [
        "Primary-source preference: SEC, company IR, Federal Reserve, BLS, BEA, regulators/government, S&P/official index sources.",
        "Wikipedia: prohibited.",
        "Theme labels: not frozen yet.",
        "One target may have multiple evidence rows.",
        "Evidence timing relative to ranking/holding window must be recorded.",
        "Company-specific, sector, cross-sector, and macro evidence must remain distinguishable.",
        "Short quotations must remain <=25 words per source.",
    ]

    lines += section("3. OUTPUTS")
    for path in (
        TARGET_PACKET_PATH,
        EVIDENCE_LEDGER_PATH,
        CODING_GUIDE_PATH,
    ):
        lines.append(str(path.relative_to(ROOT)))

    lines += [
        "",
        "POST_H2_PHASE3B_EVIDENCE_PREPARATION_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
