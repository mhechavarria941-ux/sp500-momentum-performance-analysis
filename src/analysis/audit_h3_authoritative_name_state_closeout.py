from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-authoritative-name-state-closeout-audit"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

INPUT_PATH = H3_DIR / "h3_authoritative_name_convergence_research_manifest.csv"
OUT_PATH = H3_DIR / "h3_authoritative_name_state_closeout.csv"
REMAINING_PATH = H3_DIR / "h3_authoritative_name_state_research_remaining.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_authoritative_name_state_closeout_integrity_audit.txt"
)

EXPECTED_ROWS = 34


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (INPUT_PATH, OUT_PATH, REMAINING_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    source = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False)
    closed = pd.read_csv(OUT_PATH, dtype=str, keep_default_na=False)
    remaining = pd.read_csv(REMAINING_PATH, dtype=str, keep_default_na=False)

    failures = []
    passed = 0

    lines = [
        "=" * 122,
        "H3 STAGE 3G — AUTHORITATIVE NAME-STATE CLOSEOUT INTEGRITY AUDIT",
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
        "Stage 3F research input contains exactly 34 identities.",
        f"Input rows={len(source)}, expected 34.",
    )

    check(
        len(closed) == EXPECTED_ROWS,
        "Stage 3G closeout contains all 34 identities.",
        f"Closeout rows={len(closed)}, expected 34.",
    )

    check(
        closed["security_key"].nunique() == EXPECTED_ROWS,
        "Every Stage 3G security_key is unique.",
        "Duplicate Stage 3G security_key found.",
    )

    check(
        set(source["security_key"]) == set(closed["security_key"]),
        "Stage 3G security universe exactly matches the Stage 3F research universe.",
        "Stage 3G security universe differs from Stage 3F.",
    )

    check(
        closed["stage3g_resolution_status"].eq("CLOSED_AUTHORITATIVE").all(),
        "Every Stage 3G identity is authoritatively closed.",
        "At least one Stage 3G identity is not closed.",
    )

    check(
        len(remaining) == 0,
        "No external name-state research identity remains after Stage 3G.",
        f"Remaining external research rows={len(remaining)}.",
    )

    check(
        closed["sample_authoritative_company_name"].ne("").all()
        and closed["sample_authoritative_cik"].str.fullmatch(r"\d{10}").all(),
        "Every identity has a nonblank authoritative sample name and 10-digit CIK.",
        "An identity lacks an authoritative sample name or valid 10-digit CIK.",
    )

    check(
        closed["source_url"].ne("").all()
        and closed["source_type"].ne("").all()
        and closed["evidence_note"].ne("").all(),
        "Every resolution has primary-source provenance and an evidence note.",
        "A Stage 3G resolution lacks provenance.",
    )

    # Pre-public transaction names cannot accidentally become production aliases.
    shells = closed[
        closed["resolution_category"].eq(
            "PREPUBLIC_TRANSACTION_NAME_NOT_ATTENTION_ALIAS"
        )
    ]
    check(
        (
            shells["excluded_name"].ne("").all()
            and shells["production_implication"].str.contains(
                "EXCLUDE_", regex=False
            ).all()
        ),
        "Every pre-public transaction name is explicitly excluded from attention aliases.",
        "A pre-public transaction name is not explicitly excluded.",
    )

    # Post-sample changes must be outside 2021-2025.
    post = closed[
        closed["resolution_category"].isin(
            [
                "POST_SAMPLE_BRAND_TICKER_CHANGE_NOT_PIT",
                "POST_SAMPLE_HOLDING_COMPANY_REORG_CURRENT_REFERENCE_NOT_PIT",
            ]
        )
    ].copy()

    if not post.empty:
        post_dates = pd.to_datetime(
            post["post_sample_effective_date"],
            errors="coerce",
        )
        check(
            post_dates.notna().all()
            and (post_dates >= pd.Timestamp("2026-01-01")).all(),
            "Every post-sample identity change is dated 2026 or later.",
            "A post-sample resolution lacks a valid post-2025 date.",
        )
    else:
        check(False, "", "Expected post-sample correction rows are absent.")

    xom = closed.loc[closed["security_key"].eq("XOM")]
    check(
        len(xom) == 1
        and xom.iloc[0]["sample_authoritative_company_name"]
        == "Exxon Mobil Corporation"
        and xom.iloc[0]["sample_authoritative_cik"] == "0000034088"
        and "0002115436" in xom.iloc[0]["excluded_name"],
        "XOM is corrected to Exxon Mobil Corporation / CIK 0000034088 for the 2021-2025 sample.",
        "XOM point-in-time identity correction is missing or incorrect.",
    )

    tjx = closed.loc[closed["security_key"].eq("TJX")]
    check(
        len(tjx) == 1
        and tjx.iloc[0]["sample_authoritative_cik"] == "0000109198",
        "TJX missing Stage 3F CIK is resolved to 0000109198.",
        "TJX authoritative CIK resolution is missing or incorrect.",
    )

    dual_date = closed[
        closed["resolution_category"].eq(
            "TRUE_PUBLIC_NAME_TRANSITION_DUAL_DATE"
        )
    ]
    check(
        dual_date["legal_effective_date"].ne("").all()
        and dual_date["public_effective_date"].ne("").all(),
        "Every dual-date transition preserves both legal and public dates.",
        "A dual-date transition lost one of its authoritative dates.",
    )

    forbidden = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )
    cols = {str(c).casefold() for c in closed.columns}
    bad = [
        c for c in cols
        if any(fragment in c for fragment in forbidden)
    ]
    check(
        not bad,
        "Stage 3G outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like columns found: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = "H3_AUTHORITATIVE_NAME_STATE_CLOSEOUT_INTEGRITY_AUDIT_FAILED"
    else:
        gate = "H3_AUTHORITATIVE_NAME_STATE_CLOSEOUT_INTEGRITY_AUDIT_PASSED"

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Authoritatively closed identities: {len(closed)}",
        f"Remaining external name-state research identities: {len(remaining)}",
        "",
        gate,
        "",
        (
            "Passing this audit closes company-name research and authorizes "
            "construction of the proposed point-in-time attention-alias "
            "interval manifest."
        ),
        (
            "It does NOT yet authorize full-history GDELT extraction or H3 inference."
        ),
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
