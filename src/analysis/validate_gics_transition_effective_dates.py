from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

TRANSITION_CANDIDATE_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "sec_select_sector_canonical_transition_candidates.csv"
)

VALIDATION_LEDGER_PATH = (
    ROOT
    / "data"
    / "reference"
    / "gics"
    / "gics_transition_effective_dates.csv"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "gics_transition_effective_date_validation.txt"
)

MERGED_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "gics_transition_effective_date_validation_detail.csv"
)

SCRIPT_VERSION = "2026-08-24-v3-close-date-aware-validation"

EXPECTED_TRANSITIONS = 20

GICS_SECTOR_PREFIX = {
    "10": "Energy",
    "15": "Materials",
    "20": "Industrials",
    "25": "Consumer Discretionary",
    "30": "Consumer Staples",
    "35": "Health Care",
    "40": "Financials",
    "45": "Information Technology",
    "50": "Communication Services",
    "55": "Utilities",
    "60": "Real Estate",
}


def line() -> str:
    return "=" * 118


def implied_sector(code: object) -> str | None:
    if code is None or pd.isna(code):
        return None

    text = str(code).strip()
    if len(text) < 2:
        return None

    return GICS_SECTOR_PREFIX.get(text[:2])


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        TRANSITION_CANDIDATE_PATH,
        VALIDATION_LEDGER_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates = pd.read_csv(
        TRANSITION_CANDIDATE_PATH,
        dtype={
            "holding_identifier": str,
        },
    )

    ledger = pd.read_csv(
        VALIDATION_LEDGER_PATH,
        dtype={
            "holding_identifier": str,
            "old_gics_subindustry_code": str,
            "new_gics_subindustry_code": str,
        },
    )

    candidates["holding_identifier"] = (
        candidates["holding_identifier"]
        .astype(str)
        .str.strip()
    )

    ledger["holding_identifier"] = (
        ledger["holding_identifier"]
        .astype(str)
        .str.strip()
    )

    candidates["previous_report_date"] = pd.to_datetime(
        candidates["previous_report_date"],
        errors="raise",
    )
    candidates["current_report_date"] = pd.to_datetime(
        candidates["current_report_date"],
        errors="raise",
    )

    ledger["effective_close_date"] = pd.to_datetime(
        ledger["effective_close_date"],
        errors="raise",
    )
    ledger["new_sector_valid_from"] = pd.to_datetime(
        ledger["new_sector_valid_from"],
        errors="raise",
    )

    failures: list[str] = []

    if len(candidates) != EXPECTED_TRANSITIONS:
        failures.append(
            f"Candidate transitions = {len(candidates)}, "
            f"expected {EXPECTED_TRANSITIONS}."
        )

    if len(ledger) != EXPECTED_TRANSITIONS:
        failures.append(
            f"Validation ledger rows = {len(ledger)}, "
            f"expected {EXPECTED_TRANSITIONS}."
        )

    if ledger["holding_identifier"].duplicated().any():
        dup = sorted(
            ledger.loc[
                ledger["holding_identifier"].duplicated(
                    keep=False
                ),
                "holding_identifier",
            ].unique()
        )
        failures.append(
            "Duplicate identifiers in validation ledger: "
            + ", ".join(dup)
        )

    ledger["old_sector_from_code"] = (
        ledger[
            "old_gics_subindustry_code"
        ].map(implied_sector)
    )
    ledger["new_sector_from_code"] = (
        ledger[
            "new_gics_subindustry_code"
        ].map(implied_sector)
    )

    bad_old_codes = ledger[
        ledger["old_sector_from_code"]
        != ledger["old_sector"]
    ]

    bad_new_codes = ledger[
        ledger["new_sector_from_code"]
        != ledger["new_sector"]
    ]

    if not bad_old_codes.empty:
        failures.append(
            "At least one old GICS code does not map "
            "to the stated old sector."
        )

    if not bad_new_codes.empty:
        failures.append(
            "At least one new GICS code does not map "
            "to the stated new sector."
        )

    key_cols = [
        "holding_identifier",
        "previous_sector",
        "current_sector",
    ]

    candidate_key = candidates[
        key_cols
    ].rename(
        columns={
            "previous_sector": "old_sector",
            "current_sector": "new_sector",
        }
    )

    merged = candidates.merge(
        ledger,
        left_on=[
            "holding_identifier",
            "previous_sector",
            "current_sector",
        ],
        right_on=[
            "holding_identifier",
            "old_sector",
            "new_sector",
        ],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )

    missing_ledger = merged[
        merged["_merge"] == "left_only"
    ]

    extra_ledger = merged[
        merged["_merge"] == "right_only"
    ]

    if not missing_ledger.empty:
        failures.append(
            f"{len(missing_ledger)} canonical transition "
            "candidate(s) have no validated effective-date row."
        )

    if not extra_ledger.empty:
        failures.append(
            f"{len(extra_ledger)} validation ledger row(s) "
            "do not correspond to a detected canonical transition."
        )

    matched = merged[
        merged["_merge"] == "both"
    ].copy()

    matched["effective_within_sec_bracket"] = (
        (
            matched["effective_close_date"]
            >= matched["previous_report_date"]
        )
        & (
            matched["effective_close_date"]
            <= matched["current_report_date"]
        )
    )

    # SEC sector-ETF holdings are a detection layer, not the legal/official
    # GICS clock.  In rare cases the ETF can lag an official GICS change.
    # Therefore an authoritative GICS date is allowed to predate the
    # previous ETF snapshot, but it must not occur after the first SEC
    # snapshot that shows the new sector.
    matched["official_date_valid_by_current_snapshot"] = (
        matched["effective_close_date"]
        <= matched["current_report_date"]
    )

    matched["sec_etf_lag_detected"] = (
        matched["effective_close_date"]
        < matched["previous_report_date"]
    )

    # A sector ETF snapshot dated on the same day as an official
    # "effective after the close" GICS change can already reflect the
    # rebalance at that close even though the new classification is
    # analytically valid from the next trading session.
    #
    # Therefore we validate the legal/economic clock directly:
    #   effective_close_date <= first SEC snapshot showing new sector
    #   new_sector_valid_from == next business day after effective close
    #
    # This specifically handles same-close observations such as CoStar
    # on 2023-06-30 -> valid from 2023-07-03.
    matched["same_close_detection"] = (
        matched["effective_close_date"]
        == matched["current_report_date"]
    )

    matched["expected_next_business_day"] = (
        matched["effective_close_date"]
        + pd.offsets.BDay(1)
    )

    matched["valid_from_is_next_business_day"] = (
        matched["new_sector_valid_from"]
        == matched["expected_next_business_day"]
    )

    matched["valid_from_after_effective_close"] = (
        matched["new_sector_valid_from"]
        > matched["effective_close_date"]
    )

    matched["primary_source_present"] = (
        matched["primary_source_url"]
        .fillna("")
        .str.startswith("http")
    )

    if not matched[
        "official_date_valid_by_current_snapshot"
    ].all():
        failures.append(
            "At least one authoritative effective date occurs "
            "after the first SEC snapshot that shows the new sector."
        )

    if not matched[
        "valid_from_is_next_business_day"
    ].all():
        failures.append(
            "At least one new-sector valid-from date is not the "
            "next business day after the authoritative effective-close date."
        )

    if not matched[
        "valid_from_after_effective_close"
    ].all():
        failures.append(
            "At least one new-sector valid-from date does not "
            "follow the official effective-close date."
        )

    if not matched[
        "primary_source_present"
    ].all():
        failures.append(
            "At least one transition lacks a primary source URL."
        )

    MERGED_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    merged.to_csv(
        MERGED_PATH,
        index=False,
    )

    structural = matched[
        matched["change_group"]
        == "2023_GICS_STRUCTURE_REVISION"
    ]

    company_specific = matched[
        matched["change_group"]
        == "COMPANY_SPECIFIC"
    ]

    lines: list[str] = [
        line(),
        "GICS TRANSITION EFFECTIVE-DATE VALIDATION",
        line(),
        "Mode: LOCAL / READ-ONLY",
        f"Detected canonical SEC transition candidates: {len(candidates)}",
        f"Authoritative transition ledger rows: {len(ledger)}",
        f"Exact matches: {len(matched)}",
        f"2023 structural-revision rows: {len(structural)}",
        f"Company-specific rows: {len(company_specific)}",
        (
            "SEC ETF lag cases where the authoritative GICS date "
            "predates the previous fund snapshot: "
            f"{int(matched['sec_etf_lag_detected'].sum())}"
        ),
        (
            "Same-close SEC detections where the ETF snapshot date "
            "equals the official effective-close date: "
            f"{int(matched['same_close_detection'].sum())}"
        ),
        "",
    ]

    for row in matched.sort_values(
        [
            "new_sector_valid_from",
            "holding_identifier",
        ]
    ).itertuples(index=False):
        lines.append(
            f"{row.holding_identifier} | "
            f"{row.company_name} | "
            f"{row.old_sector} -> {row.new_sector} | "
            f"effective close {row.effective_close_date.date()} | "
            f"new sector valid from {row.new_sector_valid_from.date()} | "
            f"{row.change_group}"
        )

    lines += [
        "",
        line(),
        "QUALITY GATE",
        line(),
    ]

    if failures:
        lines.append("RESULT: REVIEW_REQUIRED")
        for failure in failures:
            lines.append("FAIL: " + failure)
    else:
        lines += [
            "PASS: 20/20 detected sector transitions have an authoritative effective-date mapping.",
            "PASS: GICS sub-industry code prefixes reconcile to the stated old/new sectors.",
            "PASS: Every authoritative GICS effective date occurs no later than the first SEC snapshot showing the new sector.",
            (
                "PASS: SEC ETF lag is treated as a source-layer implementation artifact, "
                "not as authority over the official GICS effective date."
            ),
            (
                "PASS: Same-close ETF detections are allowed when the official change "
                "is effective after that close; the analytical sector changes on the next business day."
            ),
            "PASS: Every new-sector valid-from date equals the next business day after the official effective-close date.",
            "PASS: Every transition has a primary source URL.",
            "",
            "RESULT: GICS_TRANSITION_EFFECTIVE_DATE_GATE_PASSED",
            "",
            "Next step: build permanent security_key sector intervals and expand them to the 60 H2 ranking months.",
        ]

    lines += [
        "",
        "Source data modifications performed: 0",
        "Azure SQL modifications performed: 0",
        f"Detail audit: {MERGED_PATH.relative_to(ROOT)}",
    ]

    report_text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report_text,
        encoding="utf-8",
    )

    print(report_text, end="")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
