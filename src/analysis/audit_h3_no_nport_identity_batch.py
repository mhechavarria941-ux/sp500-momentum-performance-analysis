from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v2-h3-definitive-no-nport-closure-audit-lumen-fix"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

OUT_PATH = H3_DIR / "h3_no_nport_definitive_closure.csv"
TRANSITION_PATH = H3_DIR / "h3_no_nport_membership_name_transitions.csv"
UNEXPECTED_PATH = H3_DIR / "h3_no_nport_unexpected_sec_former_name_signals.csv"
FULL_PATH = H3_DIR / "h3_full_universe_name_resolution_coverage_v2.csv"
FULL_UNRESOLVED_PATH = H3_DIR / "h3_full_universe_name_resolution_unresolved_v2.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_definitive_no_nport_closure_integrity_audit.txt"
)

EXPECTED_ROWS = 93
EXPECTED_FULL = 593

def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        OUT_PATH, TRANSITION_PATH, UNEXPECTED_PATH,
        FULL_PATH, FULL_UNRESOLVED_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    result = pd.read_csv(OUT_PATH, dtype=str, keep_default_na=False)
    transitions = pd.read_csv(TRANSITION_PATH, dtype=str, keep_default_na=False)
    unexpected = pd.read_csv(UNEXPECTED_PATH, dtype=str, keep_default_na=False)
    full = pd.read_csv(FULL_PATH, dtype=str, keep_default_na=False)
    full_unresolved = pd.read_csv(FULL_UNRESOLVED_PATH, dtype=str, keep_default_na=False)

    failures, passed = [], 0
    lines = [
        "=" * 124,
        "H3 STAGE 3I V2 — DEFINITIVE NO-NPORT CLOSURE INTEGRITY AUDIT",
        "=" * 124,
        "Production PIT aliases authorized only if final closure gate passes.",
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

    check(len(result) == EXPECTED_ROWS,
          "Definitive no-NPORT closure contains all 93 carry-forward identities.",
          f"Closure rows={len(result)}, expected 93.")

    check(result["security_key"].nunique() == EXPECTED_ROWS,
          "Every no-NPORT security_key is unique.",
          "Duplicate no-NPORT security_key found.")

    check(result["resolution_status"].eq("CLOSED_NO_NPORT_SOURCE_GAP").all(),
          "Every no-NPORT row has an explicit final disposition.",
          "A no-NPORT row lacks final closure status.")

    check(result["membership_company_name"].ne("").all()
          and result["membership_valid_from"].ne("").all()
          and result["membership_valid_to_exclusive"].ne("").all(),
          "Every no-NPORT identity has an official membership name and interval.",
          "A no-NPORT identity lacks membership identity/date evidence.")

    check(result["final_no_nport_disposition"].ne("").all()
          and result["name_state_resolution_basis"].ne("").all(),
          "Every no-NPORT identity has a nonblank name-state disposition and basis.",
          "A no-NPORT identity lacks disposition/basis.")

    check(transitions["source_url"].ne("").all()
          and transitions["event_type"].ne("").all(),
          "Every known event intersecting membership has explicit provenance.",
          "A known event lacks provenance.")

    check(len(unexpected) == 0,
          "No unexpected distinct SEC former-name signal remains.",
          f"{len(unexpected)} unexpected SEC former-name signal(s) remain.")

    lumn = result.loc[result["security_key"].eq("LUMN")]
    check(
        len(lumn) == 1
        and lumn.iloc[0]["final_no_nport_disposition"]
        == "PREWINDOW_PUBLIC_REBRAND_WITH_INWINDOW_LEGAL_NAME_FINALIZATION"
        and lumn.iloc[0]["unexpected_in_membership_sec_former_name_signal_count"] == "0",
        (
            "LUMN is correctly resolved as pre-window public rebrand with "
            "2021-01-22 in-window legal-name finalization."
        ),
        "LUMN dual-date public/legal name-state resolution is incorrect.",
    )

    lumn_event = transitions.loc[
        transitions["security_key"].eq("LUMN")
    ]
    check(
        len(lumn_event) == 1
        and lumn_event.iloc[0]["legal_effective_date"] == "2021-01-22"
        and lumn_event.iloc[0]["public_effective_date"] == "2020-09-14"
        and lumn_event.iloc[0]["legal_boundary_in_membership_flag"] == "1"
        and lumn_event.iloc[0]["public_boundary_in_membership_flag"] == "0",
        "LUMN preserves separate authoritative legal and public identity dates.",
        "LUMN legal/public date provenance is not preserved correctly.",
    )

    check(len(full) == EXPECTED_FULL
          and full["security_key"].nunique() == EXPECTED_FULL,
          "Full closure ledger contains exactly 593 unique identities.",
          "Full closure ledger does not contain exactly 593 unique identities.")

    check(len(full_unresolved) == 0
          and not full["final_name_resolution_status"].eq(
              "UNRESOLVED_CARRY_FORWARD_GAP"
          ).any(),
          "Full 593-security name-resolution universe contains zero unresolved identities.",
          f"Full-universe unresolved identities={len(full_unresolved)}.")

    check(
        int(full["final_name_resolution_status"].eq(
            "RESOLVED_STAGE3I_DEFINITIVE_NO_NPORT_CLOSURE"
        ).sum()) == EXPECTED_ROWS,
        "Exactly 93 identities close through Stage 3I.",
        "Stage 3I does not close exactly 93 identities in the full ledger.",
    )

    forbidden = ("return","momentum","winner","commonality_factor","outcome")
    cols = {str(c).casefold() for c in list(result.columns) + list(full.columns)}
    bad = [c for c in cols if any(fragment in c for fragment in forbidden)]

    check(not bad,
          "Stage 3I outputs contain no return/momentum/Winner/outcome fields.",
          "Prohibited outcome-like fields found: " + ", ".join(sorted(bad)))

    gate = (
        "H3_FULL_UNIVERSE_COMPANY_NAME_RESEARCH_CLOSED_593_OF_593"
        if not failures
        else "H3_FULL_UNIVERSE_COMPANY_NAME_RESEARCH_CLOSURE_BLOCKED"
    )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"No-NPORT identities closed: {len(result)}",
        f"Full-universe identities: {len(full)}",
        f"Full-universe unresolved identities: {len(full_unresolved)}",
        "",
        gate,
        "",
        (
            "A passing 593-of-593 gate authorizes the next step: freeze the "
            "PIT attention-alias policy and construct the proposed alias intervals."
        ),
        (
            "Full-history GDELT extraction remains unauthorized until the "
            "alias manifest passes its own integrity audit."
        ),
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")

if __name__ == "__main__":
    main()
