from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-pit-name-evidence-consolidation-audit"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

SUMMARY_PATH = H3_DIR / "h3_pit_name_evidence_security_summary.csv"
OBSERVATIONS_PATH = H3_DIR / "h3_pit_name_state_observations.csv"
TRANSITIONS_PATH = H3_DIR / "h3_pit_name_transition_candidates.csv"
REVIEW_PATH = H3_DIR / "h3_pit_name_evidence_review_queue.csv"
ALIAS_EVENTS_PATH = H3_DIR / "h3_pit_name_alias_events_mapped.csv"
UNMAPPED_ALIAS_EVENTS_PATH = H3_DIR / "h3_pit_name_alias_events_unmapped.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_pit_name_evidence_consolidation_integrity_audit.txt"
)

EXPECTED_IDENTITIES = 593

ALLOWED_STATUSES = {
    "READY_STABLE_SEC_NPORT_NAME",
    "REVIEW_NO_MAPPED_SEC_NPORT_NAME",
    "REVIEW_MULTIPLE_SEC_NPORT_NAMES",
    "REVIEW_PROJECT_NAME_DIFFERS_FROM_SEC_NPORT",
    "REVIEW_PROJECT_PERIOD_NAME_EVENT_EVIDENCE",
}


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        SUMMARY_PATH,
        OBSERVATIONS_PATH,
        TRANSITIONS_PATH,
        REVIEW_PATH,
        ALIAS_EVENTS_PATH,
        UNMAPPED_ALIAS_EVENTS_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    summary = pd.read_csv(SUMMARY_PATH, dtype=str, keep_default_na=False)
    observations = pd.read_csv(
        OBSERVATIONS_PATH, dtype=str, keep_default_na=False
    )
    transitions = pd.read_csv(
        TRANSITIONS_PATH, dtype=str, keep_default_na=False
    )
    review = pd.read_csv(REVIEW_PATH, dtype=str, keep_default_na=False)

    failures = []
    passed = 0

    lines = [
        "=" * 116,
        "H3 STAGE 3B2 — PIT NAME-EVIDENCE CONSOLIDATION INTEGRITY AUDIT",
        "=" * 116,
        "Production alias intervals authorized: NO",
        "Full-history GDELT extraction authorized: NO",
        "H3 outcome analysis authorized: NO",
        "",
    ]

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if bool(condition):
            lines.append("PASS: " + success)
            passed += 1
        else:
            lines.append("FAIL: " + failure)
            failures.append(failure)

    check(
        len(summary) == EXPECTED_IDENTITIES,
        "Evidence summary contains all 593 security identities.",
        f"Evidence summary rows={len(summary)}, expected 593.",
    )

    check(
        summary["security_key"].nunique() == EXPECTED_IDENTITIES,
        "Every evidence-summary security_key is unique.",
        "Duplicate security_key found in evidence summary.",
    )

    check(
        set(summary["pit_name_evidence_status"]).issubset(ALLOWED_STATUSES),
        "Every PIT name-evidence status is from the frozen status set.",
        "Unexpected PIT name-evidence status found.",
    )

    review_keys = set(review["security_key"])
    expected_review_keys = set(
        summary.loc[
            summary["pit_name_review_flag"].eq("1"),
            "security_key",
        ]
    )

    check(
        review_keys == expected_review_keys,
        "Focused review queue exactly reconstructs review flags.",
        "Focused review queue differs from summary review flags.",
    )

    ready = summary[
        summary["pit_name_evidence_status"].eq(
            "READY_STABLE_SEC_NPORT_NAME"
        )
    ]

    check(
        ready["sec_nport_unique_name_count"].eq("1").all(),
        "Every READY identity has exactly one normalized SEC NPORT name state.",
        "A READY identity has zero or multiple SEC NPORT name states.",
    )

    check(
        ready["project_current_name_seen_in_sec_nport_flag"].eq("1").all(),
        "Every READY identity's project current name is observed in SEC NPORT evidence.",
        "A READY identity lacks project-name support in SEC NPORT evidence.",
    )

    check(
        ready["project_period_alias_event_count"].eq("0").all()
        and ready["project_period_sec_former_name_count"].eq("0").all(),
        (
            "No READY identity contains project-period alias-event or "
            "SEC former-name evidence."
        ),
        "A READY identity contains unresolved project-period name-event evidence.",
    )

    if not observations.empty:
        check(
            observations["security_key"].isin(set(summary["security_key"])).all(),
            "Every SEC NPORT name observation maps to a canonical security identity.",
            "An SEC NPORT name observation references an unknown security_key.",
        )
    else:
        check(False, "", "SEC NPORT name-observation output is empty.")

    if not transitions.empty:
        check(
            transitions["transition_date_status"].eq("BOUNDED_NOT_EXACT").all(),
            (
                "Every NPORT-derived name transition remains explicitly "
                "bounded/not-exact."
            ),
            "A quarterly NPORT observation was incorrectly treated as an exact transition date.",
        )
    else:
        check(True, "No NPORT name transition candidates required.", "")

    forbidden_fragments = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )

    columns = {
        str(c).casefold()
        for c in (
            list(summary.columns)
            + list(observations.columns)
            + list(transitions.columns)
            + list(review.columns)
        )
    }

    bad = [
        c
        for c in columns
        if any(fragment in c for fragment in forbidden_fragments)
    ]

    check(
        not bad,
        "Stage 3B2 outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields found: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = "H3_PIT_NAME_EVIDENCE_CONSOLIDATION_INTEGRITY_AUDIT_FAILED"
    else:
        gate = "H3_PIT_NAME_EVIDENCE_CONSOLIDATION_INTEGRITY_AUDIT_PASSED"

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Focused PIT-name review queue rows: {len(review)}",
        f"SEC NPORT name observation rows: {len(observations)}",
        f"Bounded transition candidates: {len(transitions)}",
        "",
        gate,
        "",
        (
            "Passing this audit authorizes targeted resolution of exact "
            "name-change dates for the focused review queue only."
        ),
        (
            "It does NOT authorize production PIT aliases, full GDELT history, "
            "or H3 inference."
        ),
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
