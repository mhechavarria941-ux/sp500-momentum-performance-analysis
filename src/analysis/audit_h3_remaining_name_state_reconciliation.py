from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-deterministic-name-state-reconciliation-audit"

H3_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

REMAINING_PATH = H3_DIR / "h3_name_state_reconciliation_remaining.csv"
OUT_PATH = H3_DIR / "h3_name_state_reconciliation_classification.csv"
RESOLVED_PATH = H3_DIR / "h3_name_state_reconciliation_auto_resolved.csv"
RESEARCH_PATH = H3_DIR / "h3_name_state_reconciliation_research_manifest.csv"
TRANSITION_SUPPORT_PATH = H3_DIR / "h3_combined_resolved_name_transitions.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_deterministic_name_state_reconciliation_integrity_audit.txt"
)

EXPECTED_ROWS = 119


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        REMAINING_PATH,
        OUT_PATH,
        RESOLVED_PATH,
        RESEARCH_PATH,
        TRANSITION_SUPPORT_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    remaining = pd.read_csv(
        REMAINING_PATH,
        dtype=str,
        keep_default_na=False,
    )
    result = pd.read_csv(
        OUT_PATH,
        dtype=str,
        keep_default_na=False,
    )
    resolved = pd.read_csv(
        RESOLVED_PATH,
        dtype=str,
        keep_default_na=False,
    )
    research = pd.read_csv(
        RESEARCH_PATH,
        dtype=str,
        keep_default_na=False,
    )
    transitions = pd.read_csv(
        TRANSITION_SUPPORT_PATH,
        dtype=str,
        keep_default_na=False,
    )

    failures = []
    passed = 0

    lines = [
        "=" * 120,
        "H3 STAGE 3E — DETERMINISTIC NAME-STATE RECONCILIATION INTEGRITY AUDIT",
        "=" * 120,
        "Production PIT aliases authorized: NO",
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
        len(remaining) == EXPECTED_ROWS,
        "Input remaining reconciliation universe contains 119 identities.",
        f"Input rows={len(remaining)}, expected 119.",
    )

    check(
        len(result) == EXPECTED_ROWS,
        "Classification output contains all 119 identities.",
        f"Classification rows={len(result)}, expected 119.",
    )

    check(
        result["security_key"].nunique() == EXPECTED_ROWS,
        "Every classification security_key is unique.",
        "Duplicate classification security_key found.",
    )

    check(
        set(result["security_key"]) == set(remaining["security_key"]),
        "Classification security-key universe exactly matches Stage 3D remainder.",
        "Classification security-key universe differs from Stage 3D remainder.",
    )

    check(
        len(resolved) + len(research) == EXPECTED_ROWS,
        "Resolved plus research partitions reconstruct all 119 identities.",
        (
            f"Resolved={len(resolved)}, research={len(research)}, "
            f"expected total 119."
        ),
    )

    check(
        set(resolved["security_key"]).isdisjoint(
            set(research["security_key"])
        ),
        "Resolved and research partitions are disjoint.",
        "An identity appears in both resolved and research partitions.",
    )

    check(
        resolved["reconciliation_status"].str.startswith(
            "RESOLVED_"
        ).all(),
        "Every auto-resolved row has a RESOLVED_ status.",
        "An auto-resolved row lacks a RESOLVED_ status.",
    )

    check(
        research["reconciliation_status"].str.startswith(
            "RESEARCH_"
        ).all(),
        "Every remaining row has a RESEARCH_ status.",
        "A research row lacks a RESEARCH_ status.",
    )

    # Strong safety check for stable legal-style auto-resolution.
    stable = resolved[
        resolved["reconciliation_status"].eq(
            "RESOLVED_STABLE_LEGAL_STYLE_EQUIVALENT"
        )
    ]

    if not stable.empty:
        check(
            stable["nport_legal_core_count"].eq("1").all(),
            "Every stable legal-style resolution has exactly one NPORT legal core.",
            "A stable legal-style resolution has zero/multiple NPORT legal cores.",
        )

        check(
            stable["project_period_sec_former_name_count"].eq("0").all(),
            "Stable legal-style resolutions have no project-period SEC former-name evidence.",
            "A stable legal-style resolution contains project-period former-name evidence.",
        )

        check(
            stable.apply(
                lambda row: (
                    row["project_name_legal_core"]
                    == row["nport_legal_cores_pipe"]
                    and (
                        row["sec_current_name_legal_core"] == ""
                        or row["sec_current_name_legal_core"]
                        == row["project_name_legal_core"]
                    )
                ),
                axis=1,
            ).all(),
            (
                "Every stable legal-style resolution has exact deterministic "
                "legal-core agreement across required evidence."
            ),
            "A stable legal-style resolution lacks exact legal-core agreement.",
        )
    else:
        check(True, "No stable legal-style auto-resolution rows required.", "")
        check(True, "No stable former-name safety check required.", "")
        check(True, "No stable legal-core agreement check required.", "")

    transition_resolved = resolved[
        resolved["reconciliation_status"].isin(
            [
                "RESOLVED_BY_AUTHORITATIVE_TRANSITION_HISTORY",
                "RESOLVED_FALSE_NPORT_TRANSITION_STABLE_ISSUER",
            ]
        )
    ]

    if not transition_resolved.empty:
        check(
            transition_resolved[
                "all_nport_states_explained_by_transition_flag"
            ].eq("1").all(),
            (
                "Every transition-based resolution has all NPORT states "
                "covered by already-resolved transition evidence."
            ),
            "A transition-based auto-resolution has unexplained NPORT state(s).",
        )
    else:
        check(True, "No transition-based auto-resolution rows required.", "")

    check(
        not transitions["resolution_class"].eq("UNKNOWN").any(),
        "Combined transition-support layer contains no UNKNOWN resolution class.",
        "Combined transition-support layer contains UNKNOWN resolution class.",
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
        for c in (
            list(result.columns)
            + list(resolved.columns)
            + list(research.columns)
            + list(transitions.columns)
        )
    }

    bad = [
        c for c in columns
        if any(fragment in c for fragment in forbidden)
    ]

    check(
        not bad,
        "Stage 3E outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields found: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = (
            "H3_DETERMINISTIC_NAME_STATE_RECONCILIATION_"
            "INTEGRITY_AUDIT_FAILED"
        )
    else:
        gate = (
            "H3_DETERMINISTIC_NAME_STATE_RECONCILIATION_"
            "INTEGRITY_AUDIT_PASSED"
        )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Automatically reconciled identities: {len(resolved)}",
        f"Remaining targeted research identities: {len(research)}",
        "",
        gate,
        "",
        (
            "Passing this audit authorizes primary-source research only for "
            "the remaining research manifest."
        ),
        (
            "Production PIT aliases and full-history GDELT extraction remain "
            "unauthorized."
        ),
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


if __name__ == "__main__":
    main()
