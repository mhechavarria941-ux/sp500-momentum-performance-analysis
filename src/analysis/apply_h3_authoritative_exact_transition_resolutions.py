from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-authoritative-exact-transition-closeout"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
RESEARCH_PATH = H3_DIR / "h3_exact_name_transition_research_manifest.csv"
REFERENCE_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_authoritative_exact_name_transition_resolutions.csv"
)

OUT_PATH = H3_DIR / "h3_authoritative_exact_name_transition_resolutions.csv"
REMAINING_PATH = H3_DIR / "h3_name_state_reconciliation_remaining.csv"
REPORT_PATH = H3_DIR / "h3_authoritative_exact_transition_closeout_report.txt"

EXPECTED_EXACT_ROWS = 22
EXPECTED_TRUE_RENAMES = 18
EXPECTED_FALSE_TRANSITIONS = 4


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (RESEARCH_PATH, REFERENCE_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    research = pd.read_csv(RESEARCH_PATH, dtype=str, keep_default_na=False)
    ref = pd.read_csv(REFERENCE_PATH, dtype=str, keep_default_na=False)

    exact = research[research["research_type"].eq("EXACT_RENAME_DATE")].copy()
    remaining = research[
        research["research_type"].eq("NAME_STATE_RECONCILIATION")
    ].copy()

    if len(exact) != EXPECTED_EXACT_ROWS:
        raise RuntimeError(
            f"Exact research rows={len(exact)}, expected {EXPECTED_EXACT_ROWS}."
        )

    key_cols = [
        "security_key",
        "from_name_key",
        "to_name_key",
        "search_start_date",
        "search_end_date",
    ]

    ref_keyed = ref.rename(
        columns={
            "bounded_start": "search_start_date",
            "bounded_end": "search_end_date",
        }
    )

    merged = exact.merge(
        ref_keyed,
        on=key_cols,
        how="left",
        validate="one_to_one",
        suffixes=("_research", ""),
    )

    if merged["resolution_status"].eq("").any():
        missing = merged.loc[
            merged["resolution_status"].eq(""),
            key_cols,
        ]
        raise RuntimeError(
            "Authoritative resolution missing for exact row(s):\n"
            + missing.to_string(index=False)
        )

    true_rename = merged["resolution_status"].str.startswith(
        "RESOLVED_TRUE_LEGAL_RENAME"
    )
    false_transition = merged["resolution_status"].str.startswith(
        "REJECT_FALSE_TRANSITION"
    )

    if int(true_rename.sum()) != EXPECTED_TRUE_RENAMES:
        raise RuntimeError(
            f"True rename rows={int(true_rename.sum())}, expected 18."
        )
    if int(false_transition.sum()) != EXPECTED_FALSE_TRANSITIONS:
        raise RuntimeError(
            f"False transition rows={int(false_transition.sum())}, expected 4."
        )

    merged.to_csv(OUT_PATH, index=False)
    remaining.to_csv(REMAINING_PATH, index=False)

    lines = [
        "=" * 120,
        "H3 STAGE 3D — AUTHORITATIVE EXACT TRANSITION CLOSEOUT",
        "=" * 120,
        f"Stage 3C exact-date research rows: {len(exact)}",
        f"Authoritatively resolved true legal/company renames: {int(true_rename.sum())}",
        f"Rejected false NPORT transitions: {int(false_transition.sum())}",
        f"Unresolved exact-date rows remaining: 0",
        f"Name-state reconciliation rows remaining: {len(remaining)}",
        "",
        "False-transition classes:",
        (
            "  CSCO: jurisdiction/legal-suffix NPORT label variation; "
            "Cisco Systems, Inc. remained the registrant."
        ),
        (
            "  FRT: simultaneous parent/operating-partnership registrants; "
            "Federal Realty OP LP is not a parent-company rename."
        ),
        "",
        "Production PIT alias intervals created: NO",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_AUTHORITATIVE_EXACT_TRANSITION_CLOSEOUT_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
