from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-authoritative-name-convergence-audit"

H3_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

INPUT_PATH = H3_DIR / "h3_name_state_reconciliation_research_manifest.csv"
OUT_PATH = H3_DIR / "h3_authoritative_name_convergence_classification.csv"
RESOLVED_PATH = H3_DIR / "h3_authoritative_name_convergence_auto_resolved.csv"
RESEARCH_PATH = H3_DIR / "h3_authoritative_name_convergence_research_manifest.csv"
FORMER_DETAIL_PATH = H3_DIR / "h3_authoritative_name_convergence_former_name_detail.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_authoritative_name_convergence_integrity_audit.txt"
)

EXPECTED_ROWS = 118


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        INPUT_PATH,
        OUT_PATH,
        RESOLVED_PATH,
        RESEARCH_PATH,
        FORMER_DETAIL_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    source = pd.read_csv(
        INPUT_PATH,
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
    detail = pd.read_csv(
        FORMER_DETAIL_PATH,
        dtype=str,
        keep_default_na=False,
    )

    failures = []
    passed = 0

    lines = [
        "=" * 122,
        "H3 STAGE 3F — AUTHORITATIVE NAME CONVERGENCE INTEGRITY AUDIT",
        "=" * 122,
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
        len(source) == EXPECTED_ROWS,
        "Stage 3E source research universe contains 118 identities.",
        f"Source rows={len(source)}, expected 118.",
    )

    check(
        len(result) == EXPECTED_ROWS,
        "Stage 3F classification contains all 118 identities.",
        f"Classification rows={len(result)}, expected 118.",
    )

    check(
        result["security_key"].nunique() == EXPECTED_ROWS,
        "Every Stage 3F security_key is unique.",
        "Duplicate Stage 3F security_key found.",
    )

    check(
        set(source["security_key"]) == set(result["security_key"]),
        "Stage 3F security universe exactly matches Stage 3E research universe.",
        "Stage 3F security universe differs from Stage 3E.",
    )

    check(
        len(resolved) + len(research) == EXPECTED_ROWS,
        "Resolved plus research partitions reconstruct all 118 identities.",
        (
            f"Resolved={len(resolved)}, research={len(research)}, "
            "expected total 118."
        ),
    )

    check(
        set(resolved["security_key"]).isdisjoint(
            set(research["security_key"])
        ),
        "Resolved and research partitions are disjoint.",
        "An identity appears in both Stage 3F partitions.",
    )

    project_diff = resolved[
        resolved["stage3f_status"].eq(
            "RESOLVED_AUTHORITATIVE_SEC_NPORT_AGREEMENT_"
            "PROJECT_REFERENCE_PRESENTATION_DIFFERENCE"
        )
    ]

    if not project_diff.empty:
        check(
            project_diff[
                "sec_nport_authoritative_agreement_flag"
            ].eq("1").all()
            and project_diff[
                "nport_registry_core_count"
            ].eq("1").all(),
            (
                "Every project-reference auto-resolution has one NPORT "
                "registry core exactly agreeing with SEC current identity."
            ),
            (
                "A project-reference auto-resolution lacks exact "
                "SEC/NPORT authoritative agreement."
            ),
        )
    else:
        check(True, "No project-reference auto-resolution rows required.", "")

    former_resolved = resolved[
        resolved["stage3f_status"].eq(
            "RESOLVED_SEC_FORMER_NAMES_REGISTRY_STYLE_EQUIVALENT"
        )
    ]

    if not former_resolved.empty:
        check(
            former_resolved[
                "sec_nport_authoritative_agreement_flag"
            ].eq("1").all()
            and former_resolved[
                "nport_registry_core_count"
            ].eq("1").all(),
            (
                "Every former-name auto-resolution has exact SEC/NPORT "
                "authoritative current-name agreement."
            ),
            "A former-name auto-resolution lacks SEC/NPORT agreement.",
        )

        check(
            former_resolved[
                "former_name_date_complete_flag"
            ].eq("1").all()
            and former_resolved[
                "all_former_names_same_authoritative_core_flag"
            ].eq("1").all(),
            (
                "Every former-name auto-resolution has complete date "
                "boundaries and exact registry-core equivalence."
            ),
            (
                "A former-name auto-resolution has incomplete dates or "
                "a distinct former-name registry core."
            ),
        )
    else:
        check(True, "No former-name auto-resolution rows required.", "")
        check(True, "No former-name date/core auto-resolution checks required.", "")

    # Detail rows underlying a resolved former-name identity must all be same-core.
    resolved_former_keys = set(
        former_resolved["security_key"]
    )
    resolved_detail = detail[
        detail["security_key"].isin(
            resolved_former_keys
        )
    ]

    if resolved_former_keys:
        check(
            not resolved_detail.empty
            and resolved_detail[
                "date_complete_flag"
            ].eq("1").all()
            and resolved_detail[
                "same_core_as_authoritative_flag"
            ].eq("1").all(),
            (
                "Former-name detail evidence independently reproduces "
                "every former-name auto-resolution."
            ),
            (
                "Former-name detail evidence does not reproduce "
                "an auto-resolution."
            ),
        )
    else:
        check(True, "No resolved former-name detail rows required.", "")

    check(
        research["stage3f_status"].str.startswith(
            "RESEARCH_"
        ).all(),
        "Every remaining identity is explicitly RESEARCH_.",
        "A remaining identity lacks a RESEARCH_ status.",
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
            + list(detail.columns)
        )
    }
    bad = [
        c for c in columns
        if any(fragment in c for fragment in forbidden)
    ]

    check(
        not bad,
        "Stage 3F outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields found: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = (
            "H3_AUTHORITATIVE_NAME_CONVERGENCE_"
            "INTEGRITY_AUDIT_FAILED"
        )
    else:
        gate = (
            "H3_AUTHORITATIVE_NAME_CONVERGENCE_"
            "INTEGRITY_AUDIT_PASSED"
        )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Automatically reconciled Stage 3F identities: {len(resolved)}",
        f"Remaining primary-source research identities: {len(research)}",
        "",
        gate,
        "",
        (
            "Passing this audit authorizes external primary-source research "
            "only for the reduced Stage 3F research manifest."
        ),
        (
            "Production PIT aliases and full-history GDELT extraction "
            "remain unauthorized."
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
