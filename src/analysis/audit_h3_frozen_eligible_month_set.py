from __future__ import annotations

from pathlib import Path

import pandas as pd


SCRIPT_VERSION = "2026-08-26-v3-h3-frozen-eligible-month-set-gate"

ROOT = Path(__file__).resolve().parents[2]

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

ELIGIBILITY_PATH = H3_DIR / "h3_gdelt_primary_month_eligibility.csv"
PREDICTOR_PATH = H3_DIR / "h3_preregistered_attention_predictor_panel.csv"

FROZEN_START = pd.Period("2021-01", freq="M")
FROZEN_END = pd.Period("2025-11", freq="M")

EXPECTED_EXCLUDED_MONTHS = {pd.Period("2025-06", freq="M")}
EXPECTED_JUNE_REASON = "GLOBAL_GKG1_SOURCE_COVERAGE_BELOW_FROZEN_90PCT"

FORBIDDEN_COLUMN_TOKENS = (
    "outcome",
    "return",
    "performance",
    "winner",
    "loser",
    "momentum",
    "forward",
    "holding_return",
    "excess_return",
    "wml",
)


def rule(width: int = 132) -> str:
    return "=" * width


def normalize(value: str) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    print("H3_OUTCOME_JOIN_REMAINS_BLOCKED")
    raise SystemExit(1)


def check_file_exists(path: Path) -> None:
    if not path.exists():
        fail(f"Required file not found: {path.relative_to(ROOT)}")


def read_safe_header(path: Path) -> list[str]:
    cols = list(pd.read_csv(path, nrows=0).columns)
    forbidden = []
    for col in cols:
        n = normalize(col)
        if any(token in n for token in FORBIDDEN_COLUMN_TOKENS):
            forbidden.append(col)

    if forbidden:
        fail(
            f"Outcome-like columns detected in {path.relative_to(ROOT)}: "
            + ", ".join(forbidden)
        )
    return cols


def parse_month(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    out = []

    for raw in text.tolist():
        if pd.isna(raw) or str(raw).strip() == "":
            out.append(pd.NaT)
            continue

        value = str(raw).strip()
        try:
            out.append(pd.Period(value, freq="M"))
        except Exception:
            dt = pd.to_datetime(value, errors="coerce")
            out.append(pd.NaT if pd.isna(dt) else dt.to_period("M"))

    result = pd.Series(out, index=series.index, dtype="period[M]")

    invalid = result.isna() & text.notna()
    if invalid.any():
        fail(
            f"Unparseable month values encountered. "
            f"Sample={text.loc[invalid].head(10).tolist()}"
        )

    return result


def choose_column(columns: list[str], candidates: tuple[str, ...], label: str) -> str:
    normalized = {normalize(c): c for c in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    fail(
        f"Could not identify {label}. Columns were: "
        + ", ".join(columns)
    )
    raise AssertionError("unreachable")


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print(rule())
    print("H3 FROZEN ELIGIBLE-MONTH SET — FINAL PRE-OUTCOME GATE")
    print(rule())
    print("Outcome/return data permitted: NO")
    print("Outcome/return data intentionally opened: 0")
    print(f"Frozen calendar interval: {FROZEN_START} through {FROZEN_END}")

    check_file_exists(ELIGIBILITY_PATH)
    check_file_exists(PREDICTOR_PATH)

    eligibility_cols = read_safe_header(ELIGIBILITY_PATH)
    predictor_cols = read_safe_header(PREDICTOR_PATH)

    eligibility_month_col = choose_column(
        eligibility_cols,
        ("month", "predictor_month", "attention_month"),
        "eligibility month column",
    )
    eligibility_flag_col = choose_column(
        eligibility_cols,
        (
            "global_primary_attention_eligible_flag",
            "primary_attention_eligible_flag",
        ),
        "eligibility flag column",
    )
    eligibility_reason_col = choose_column(
        eligibility_cols,
        (
            "primary_attention_exclusion_reason",
            "attention_exclusion_reason",
            "exclusion_reason",
        ),
        "eligibility exclusion-reason column",
    )

    predictor_month_col = choose_column(
        predictor_cols,
        ("month", "predictor_month", "attention_month"),
        "predictor month column",
    )

    eligibility = pd.read_csv(
        ELIGIBILITY_PATH,
        usecols=[
            eligibility_month_col,
            eligibility_flag_col,
            eligibility_reason_col,
        ],
    )
    predictor = pd.read_csv(
        PREDICTOR_PATH,
        usecols=[predictor_month_col],
    )

    eligibility["__month"] = parse_month(eligibility[eligibility_month_col])
    predictor["__month"] = parse_month(predictor[predictor_month_col])

    frozen_calendar = pd.period_range(FROZEN_START, FROZEN_END, freq="M")
    frozen_set = set(frozen_calendar.tolist())

    e = eligibility[
        eligibility["__month"].between(FROZEN_START, FROZEN_END)
    ].copy()

    if e.empty:
        fail("No eligibility rows found inside the frozen predictor interval.")

    if e["__month"].duplicated().any():
        dupes = sorted(
            e.loc[e["__month"].duplicated(keep=False), "__month"]
            .astype(str)
            .unique()
            .tolist()
        )
        fail(f"Eligibility panel has duplicate month rows: {dupes}")

    eligibility_month_set = set(e["__month"].tolist())

    missing_eligibility_calendar_rows = sorted(frozen_set - eligibility_month_set)
    extra_eligibility_calendar_rows = sorted(eligibility_month_set - frozen_set)

    if missing_eligibility_calendar_rows or extra_eligibility_calendar_rows:
        fail(
            "Eligibility panel does not contain exactly one row for every frozen "
            "calendar month. "
            f"Missing={list(map(str, missing_eligibility_calendar_rows))}; "
            f"Extra={list(map(str, extra_eligibility_calendar_rows))}"
        )

    flags = pd.to_numeric(e[eligibility_flag_col], errors="coerce")
    if flags.isna().any():
        fail("Eligibility flag contains null/non-numeric values.")

    invalid_flags = sorted(set(flags.tolist()) - {0, 1})
    if invalid_flags:
        fail(f"Eligibility flag contains values outside {{0,1}}: {invalid_flags}")

    e["__eligible_flag"] = flags.astype(int)

    expected_eligible = set(
        e.loc[e["__eligible_flag"] == 1, "__month"].tolist()
    )
    frozen_excluded = set(
        e.loc[e["__eligible_flag"] == 0, "__month"].tolist()
    )

    predictor_months = set(
        predictor.loc[
            predictor["__month"].between(FROZEN_START, FROZEN_END),
            "__month",
        ].dropna().unique().tolist()
    )

    missing_predictor_months = sorted(expected_eligible - predictor_months)
    unexpected_predictor_months = sorted(predictor_months - expected_eligible)

    print("")
    print("FROZEN MONTH-ELIGIBILITY RECONSTRUCTION")
    print(f"Calendar months in frozen interval: {len(frozen_set)}")
    print(f"Eligible months under frozen gate: {len(expected_eligible)}")
    print(f"Excluded months under frozen gate: {len(frozen_excluded)}")
    print(
        "Excluded month set: "
        + (
            ", ".join(str(x) for x in sorted(frozen_excluded))
            if frozen_excluded
            else "NONE"
        )
    )

    excluded_rows = e[e["__eligible_flag"] == 0].sort_values("__month")
    if not excluded_rows.empty:
        print("")
        print("FROZEN EXCLUSION DETAIL")
        for _, row in excluded_rows.iterrows():
            print(
                f"{row['__month']}: "
                f"{row[eligibility_reason_col]}"
            )

    print("")
    print("PREDICTOR MONTH-SET COMPARISON")
    print(f"Observed unique predictor months: {len(predictor_months)}")
    print(
        "Missing expected eligible months: "
        + (
            ", ".join(str(x) for x in missing_predictor_months)
            if missing_predictor_months
            else "NONE"
        )
    )
    print(
        "Unexpected predictor months: "
        + (
            ", ".join(str(x) for x in unexpected_predictor_months)
            if unexpected_predictor_months
            else "NONE"
        )
    )

    # Frozen exclusion itself must reproduce exactly.
    if frozen_excluded != EXPECTED_EXCLUDED_MONTHS:
        fail(
            "Frozen exclusion set does not reproduce the preregistered source-coverage "
            f"decision. Expected={[str(x) for x in sorted(EXPECTED_EXCLUDED_MONTHS)]}; "
            f"Observed={[str(x) for x in sorted(frozen_excluded)]}"
        )

    june_row = e[e["__month"] == pd.Period("2025-06", freq="M")]
    if len(june_row) != 1:
        fail("Expected exactly one June 2025 eligibility row.")

    june_flag = int(june_row["__eligible_flag"].iloc[0])
    june_reason = str(june_row[eligibility_reason_col].iloc[0]).strip()

    if june_flag != 0:
        fail(f"June 2025 frozen eligibility flag is {june_flag}, expected 0.")

    if june_reason != EXPECTED_JUNE_REASON:
        fail(
            "June 2025 exclusion reason changed. "
            f"Expected={EXPECTED_JUNE_REASON!r}; Observed={june_reason!r}"
        )

    if len(expected_eligible) != 58:
        fail(
            f"Frozen eligible-month count is {len(expected_eligible)}, expected 58."
        )

    if missing_predictor_months or unexpected_predictor_months:
        fail(
            "Predictor month set does not exactly equal the frozen eligible-month set."
        )

    print("")
    print(rule())
    print("FINAL GATE")
    print(rule())
    print(
        "PASS: Frozen interval contains 59 calendar months, with exactly one "
        "preregistered fail-closed exclusion: 2025-06."
    )
    print(
        "PASS: June 2025 remains excluded for "
        "GLOBAL_GKG1_SOURCE_COVERAGE_BELOW_FROZEN_90PCT."
    )
    print(
        "PASS: Predictor panel contains exactly the 58 months authorized by the "
        "frozen attention-eligibility gate."
    )
    print("PASS: No outcome/return data were read by this audit.")
    print("H3_FROZEN_ELIGIBLE_MONTH_SET_GATE_PASSED")
    print("H3_OUTCOME_JOIN_AUTHORIZED_BY_MONTH_SET_GATE")


if __name__ == "__main__":
    main()
