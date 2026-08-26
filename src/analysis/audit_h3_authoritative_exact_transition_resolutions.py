from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-authoritative-exact-transition-closeout-audit"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
OUT_PATH = H3_DIR / "h3_authoritative_exact_name_transition_resolutions.csv"
REMAINING_PATH = H3_DIR / "h3_name_state_reconciliation_remaining.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_authoritative_exact_transition_closeout_integrity_audit.txt"
)

def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (OUT_PATH, REMAINING_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    resolved = pd.read_csv(OUT_PATH, dtype=str, keep_default_na=False)
    remaining = pd.read_csv(REMAINING_PATH, dtype=str, keep_default_na=False)

    failures = []
    passed = 0
    lines = [
        "=" * 118,
        "H3 STAGE 3D — AUTHORITATIVE EXACT TRANSITION CLOSEOUT INTEGRITY AUDIT",
        "=" * 118,
        "Production PIT aliases authorized: NO",
        "Full-history GDELT extraction authorized: NO",
        "H3 outcome analysis authorized: NO",
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
        len(resolved) == 22,
        "All 22 Stage 3C exact research rows are present.",
        f"Resolved rows={len(resolved)}, expected 22.",
    )

    true_mask = resolved["resolution_status"].str.startswith(
        "RESOLVED_TRUE_LEGAL_RENAME"
    )
    false_mask = resolved["resolution_status"].str.startswith(
        "REJECT_FALSE_TRANSITION"
    )

    check(
        int(true_mask.sum()) == 18,
        "Exactly 18 rows are confirmed true legal/company renames.",
        f"True-rename rows={int(true_mask.sum())}, expected 18.",
    )

    check(
        int(false_mask.sum()) == 4,
        "Exactly 4 rows are rejected as false NPORT name transitions.",
        f"False-transition rows={int(false_mask.sum())}, expected 4.",
    )

    check(
        resolved.loc[true_mask, "exact_legal_effective_date"].ne("").all(),
        "Every true rename has an authoritative exact legal effective date.",
        "A true rename lacks an exact legal effective date.",
    )

    check(
        resolved.loc[false_mask, "exact_legal_effective_date"].eq("").all(),
        "False transitions do not receive invented legal rename dates.",
        "A false transition was assigned a legal rename date.",
    )

    check(
        resolved["source_url"].ne("").all()
        and resolved["source_type"].ne("").all(),
        "Every resolution has authoritative source provenance.",
        "A resolution lacks source provenance.",
    )

    check(
        len(remaining) == 119
        and remaining["research_type"].eq(
            "NAME_STATE_RECONCILIATION"
        ).all(),
        "The remaining research universe is exactly the 119 name-state reconciliation rows.",
        (
            f"Remaining rows={len(remaining)} or unexpected research type present."
        ),
    )

    forbidden = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )
    cols = {
        str(c).casefold()
        for c in list(resolved.columns) + list(remaining.columns)
    }
    bad = [
        c for c in cols
        if any(fragment in c for fragment in forbidden)
    ]

    check(
        not bad,
        "Stage 3D outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = "H3_AUTHORITATIVE_EXACT_TRANSITION_CLOSEOUT_INTEGRITY_AUDIT_FAILED"
    else:
        gate = "H3_AUTHORITATIVE_EXACT_TRANSITION_CLOSEOUT_INTEGRITY_AUDIT_PASSED"

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Remaining name-state reconciliation rows: {len(remaining)}",
        "",
        gate,
        "",
        (
            "Passing this audit closes the exact-transition research branch and "
            "authorizes only reconciliation of the remaining 119 name-state rows."
        ),
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
