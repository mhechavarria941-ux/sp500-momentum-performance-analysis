from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-post-h2-phase3b-evidence-preparation-audit"

EXP_DIR = ROOT / "reports" / "exploratory"

TARGET_PACKET_PATH = EXP_DIR / "post_h2_phase3b_research_target_packet.csv"
EVIDENCE_LEDGER_PATH = EXP_DIR / "post_h2_phase3b_evidence_ledger_template.csv"
CODING_GUIDE_PATH = EXP_DIR / "post_h2_phase3b_evidence_coding_guide.csv"
SECURITY_QUEUE_PATH = EXP_DIR / "post_h2_phase3a_security_research_queue.csv"
MONTH_QUEUE_PATH = EXP_DIR / "post_h2_phase3a_month_research_queue.csv"

AUDIT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "post_h2_phase3b_evidence_preparation_integrity_audit.txt"
)

TOP_SECURITY_COUNT = 30
TOP_MONTH_COUNT = 15


def rule() -> str:
    return "=" * 108


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        TARGET_PACKET_PATH,
        EVIDENCE_LEDGER_PATH,
        CODING_GUIDE_PATH,
        SECURITY_QUEUE_PATH,
        MONTH_QUEUE_PATH,
    ]

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing Phase 3B preparation output(s): " + ", ".join(missing)
        )

    packet = pd.read_csv(TARGET_PACKET_PATH)
    ledger = pd.read_csv(EVIDENCE_LEDGER_PATH)
    guide = pd.read_csv(CODING_GUIDE_PATH)
    security_queue = pd.read_csv(SECURITY_QUEUE_PATH)
    month_queue = pd.read_csv(MONTH_QUEUE_PATH)

    failures: list[str] = []
    passed = 0
    lines = [
        rule(),
        "POST-H2 PHASE 3B EVIDENCE PREPARATION INTEGRITY AUDIT",
        rule(),
        "H1/H2 conclusion changes permitted: NO",
        "",
    ]

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if condition:
            lines.append(f"PASS: {success}")
            passed += 1
        else:
            lines.append(f"FAIL: {failure}")
            failures.append(failure)

    expected_security = min(TOP_SECURITY_COUNT, len(security_queue))
    expected_month = min(TOP_MONTH_COUNT, len(month_queue))

    check(
        len(packet[packet["target_type"] == "SECURITY"]) == expected_security,
        f"Research packet contains {expected_security} security targets.",
        "Security target count does not match Phase 3A queue.",
    )

    check(
        len(packet[packet["target_type"] == "MONTH"]) == expected_month,
        f"Research packet contains {expected_month} month targets.",
        "Month target count does not match Phase 3A queue.",
    )

    expected_security_keys = set(
        security_queue
        .sort_values("research_priority_rank")
        .head(expected_security)["security_key"]
        .astype(str)
    )
    actual_security_keys = set(
        packet.loc[
            packet["target_type"] == "SECURITY",
            "security_key",
        ].astype(str)
    )

    check(
        actual_security_keys == expected_security_keys,
        "Security research targets exactly match the Phase 3A top-ranked set.",
        "Security research target set differs from Phase 3A.",
    )

    expected_months = set(
        month_queue
        .sort_values("research_priority_rank")
        .head(expected_month)["analysis_month_number"]
        .astype(int)
    )
    actual_months = set(
        pd.to_numeric(
            packet.loc[
                packet["target_type"] == "MONTH",
                "analysis_month_number",
            ],
            errors="raise",
        ).astype(int)
    )

    check(
        actual_months == expected_months,
        "Month research targets exactly match the Phase 3A top-ranked set.",
        "Month research target set differs from Phase 3A.",
    )

    check(
        packet["preferred_primary_sources"]
        .astype(str)
        .str.contains("SEC", regex=False)
        .all(),
        "Every target records an authoritative primary-source preference.",
        "At least one target lacks the primary-source policy.",
    )

    check(
        not packet.astype(str).apply(
            lambda column: column.str.contains(
                "Wikipedia",
                case=False,
                regex=False,
            )
        ).any().any(),
        "Research packet contains no Wikipedia source references.",
        "Research packet contains a Wikipedia reference.",
    )

    required_ledger_columns = {
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
    }

    check(
        set(ledger.columns) == required_ledger_columns,
        "Evidence-ledger template contains the complete frozen field set.",
        "Evidence-ledger template fields differ from the expected schema.",
    )

    check(
        len(ledger) == 0,
        "Evidence ledger is blank before external research begins.",
        "Evidence ledger was pre-populated before research.",
    )

    check(
        "source_policy" in set(guide["field"]),
        "Coding guide explicitly records the source policy.",
        "Coding guide lacks the source-policy rule.",
    )

    if failures:
        lines += [
            "",
            "POST_H2_PHASE3B_EVIDENCE_PREPARATION_INTEGRITY_AUDIT_FAILED",
            f"Passed checks: {passed}",
            f"Failed checks: {len(failures)}",
        ]
        for idx, failure in enumerate(failures, 1):
            lines.append(f"{idx}. {failure}")
    else:
        lines += [
            "",
            "POST_H2_PHASE3B_EVIDENCE_PREPARATION_INTEGRITY_AUDIT_PASSED",
            f"Passed checks: {passed}",
            "External-research target set and evidence schema are frozen.",
            "No evidence or theme labels were pre-populated.",
            "H1/H2 conclusions modified: 0",
        ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"Report saved: {AUDIT_PATH}")


if __name__ == "__main__":
    main()
