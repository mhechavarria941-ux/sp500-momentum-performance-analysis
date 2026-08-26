from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-full-universe-name-resolution-closure-audit"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
CANDIDATE_PATH = H3_DIR / "h3_company_query_manifest_candidates.csv"
COVERAGE_PATH = H3_DIR / "h3_full_universe_name_resolution_coverage.csv"
UNRESOLVED_PATH = H3_DIR / "h3_full_universe_name_resolution_unresolved.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_full_universe_name_resolution_closure_integrity_audit.txt"
)

EXPECTED_IDENTITIES = 593

def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (CANDIDATE_PATH, COVERAGE_PATH, UNRESOLVED_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    candidate = pd.read_csv(CANDIDATE_PATH, dtype=str, keep_default_na=False)
    coverage = pd.read_csv(COVERAGE_PATH, dtype=str, keep_default_na=False)
    unresolved = pd.read_csv(UNRESOLVED_PATH, dtype=str, keep_default_na=False)

    failures = []
    passed = 0

    lines = [
        "=" * 122,
        "H3 STAGE 3H — FULL-UNIVERSE NAME-RESOLUTION CLOSURE INTEGRITY AUDIT",
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
        len(candidate) == EXPECTED_IDENTITIES,
        "Candidate universe contains 593 identities.",
        f"Candidate rows={len(candidate)}, expected 593.",
    )
    check(
        len(coverage) == EXPECTED_IDENTITIES,
        "Coverage ledger contains all 593 identities.",
        f"Coverage rows={len(coverage)}, expected 593.",
    )
    check(
        coverage["security_key"].nunique() == EXPECTED_IDENTITIES,
        "Every coverage security_key is unique.",
        "Duplicate security_key found in coverage ledger.",
    )
    check(
        set(candidate["security_key"]) == set(coverage["security_key"]),
        "Coverage security universe exactly matches the canonical candidate universe.",
        "Coverage security universe differs from canonical candidate universe.",
    )
    check(
        coverage["final_name_resolution_status"].ne("").all()
        and coverage["final_name_resolution_layer"].ne("").all(),
        "Every identity has an explicit final resolution status and layer.",
        "An identity lacks a final resolution status/layer.",
    )

    expected_unresolved = set(
        coverage.loc[
            coverage["final_name_resolution_status"].eq("UNRESOLVED_CARRY_FORWARD_GAP"),
            "security_key",
        ]
    )
    check(
        expected_unresolved == set(unresolved["security_key"]),
        "Unresolved manifest exactly reconstructs unresolved coverage rows.",
        "Unresolved manifest differs from coverage ledger.",
    )
    check(
        unresolved["security_key"].nunique() == len(unresolved),
        "Every unresolved identity is unique.",
        "Duplicate unresolved security_key found.",
    )

    forbidden = ("return", "momentum", "winner", "commonality_factor", "outcome")
    cols = {str(c).casefold() for c in coverage.columns}
    bad = [c for c in cols if any(fragment in c for fragment in forbidden)]
    check(
        not bad,
        "Stage 3H outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields found: " + ", ".join(sorted(bad)),
    )

    coverage_gate = (
        "H3_FULL_UNIVERSE_NAME_RESOLUTION_COVERAGE_AUDIT_PASSED"
        if not failures
        else "H3_FULL_UNIVERSE_NAME_RESOLUTION_COVERAGE_AUDIT_FAILED"
    )
    closure_gate = (
        "H3_FULL_UNIVERSE_NAME_RESOLUTION_CLOSURE_GATE_PASSED"
        if len(unresolved) == 0
        else "H3_FULL_UNIVERSE_NAME_RESOLUTION_CLOSURE_GATE_BLOCKED"
    )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Unresolved carry-forward identities: {len(unresolved)}",
        "",
        coverage_gate,
        closure_gate,
        "",
        (
            "Alias-manifest construction is authorized only when BOTH the "
            "coverage audit passes and the closure gate passes."
        ),
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")

if __name__ == "__main__":
    main()
