from pathlib import Path
import re
import sys

import pandas as pd


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "source"
    / "prices"
    / "info_old_investing_2020_2022.csv"
)

INTERIM_DIR = (
    PROJECT_ROOT
    / "data"
    / "interim"
)

OUTPUT_FILE = (
    INTERIM_DIR
    / "info_old_investing_standardized.csv"
)


# --------------------------------------------------
# Expected analytical coverage
# --------------------------------------------------

REQUESTED_START = pd.Timestamp("2020-01-01")

# IHS Markit's final trading observation
EXPECTED_FINAL_DATE = pd.Timestamp("2022-02-25")

EXPECTED_FINAL_CLOSE = 108.61

FINAL_CLOSE_TOLERANCE = 0.01


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def print_section(title):

    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


def parse_number(value):

    """
    Parse Investing.com numeric strings.

    Examples:
        "108.61" -> 108.61
        "1,234.50" -> 1234.50
    """

    if pd.isna(value):
        return None

    text = str(value).strip()

    if text in {"", "-", "N/A"}:
        return None

    text = text.replace(",", "")

    try:
        return float(text)

    except ValueError:
        return None


def parse_volume(value):

    """
    Convert Investing.com volume notation:

        25.4K -> 25,400
        3.15M -> 3,150,000
        1.2B  -> 1,200,000,000
    """

    if pd.isna(value):
        return None

    text = str(value).strip().upper()

    if text in {"", "-", "N/A"}:
        return None

    text = text.replace(",", "")

    match = re.fullmatch(
        r"([0-9]*\.?[0-9]+)([KMB]?)",
        text,
    )

    if not match:
        return None

    number = float(
        match.group(1)
    )

    suffix = match.group(2)

    multiplier = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
    }[suffix]

    return int(
        round(
            number * multiplier
        )
    )


# --------------------------------------------------
# Start
# --------------------------------------------------

print_section(
    "IHS MARKIT / INFO INVESTING.COM VALIDATION"
)


# --------------------------------------------------
# 1. Verify raw file
# --------------------------------------------------

if not RAW_FILE.exists():

    print(
        "\nERROR: Raw Investing.com file "
        "was not found:"
    )

    print(
        RAW_FILE
    )

    sys.exit(1)


print(
    f"Raw file:\n{RAW_FILE}"
)


# --------------------------------------------------
# 2. Load raw export
# --------------------------------------------------

print_section(
    "1. RAW FILE INSPECTION"
)


raw = pd.read_csv(
    RAW_FILE
)


print(
    f"Rows loaded: "
    f"{len(raw)}"
)

print(
    "\nColumns:"
)

print(
    raw.columns.tolist()
)


EXPECTED_RAW_COLUMNS = {
    "Date",
    "Price",
    "Open",
    "High",
    "Low",
    "Vol.",
    "Change %",
}


missing_raw_columns = (
    EXPECTED_RAW_COLUMNS
    - set(raw.columns)
)


if missing_raw_columns:

    print(
        "\nERROR: Expected Investing.com "
        "columns are missing:"
    )

    print(
        sorted(
            missing_raw_columns
        )
    )

    sys.exit(1)


print(
    "\nPASS: Raw schema matches expected "
    "Investing.com export."
)


# --------------------------------------------------
# 3. Standardize dates
# --------------------------------------------------

print_section(
    "2. DATE VALIDATION"
)


raw["Date"] = pd.to_datetime(
    raw["Date"],
    errors="coerce",
)


invalid_dates = int(
    raw["Date"]
    .isna()
    .sum()
)


print(
    f"Invalid dates: "
    f"{invalid_dates}"
)


if invalid_dates > 0:

    print(
        "\nERROR: One or more dates "
        "could not be parsed."
    )

    sys.exit(1)


raw = (
    raw
    .sort_values("Date")
    .reset_index(drop=True)
)


first_date = (
    raw["Date"]
    .min()
)

last_date = (
    raw["Date"]
    .max()
)


print(
    f"First date: "
    f"{first_date.date()}"
)

print(
    f"Last date: "
    f"{last_date.date()}"
)


duplicate_dates = int(
    raw["Date"]
    .duplicated()
    .sum()
)


print(
    f"Duplicate dates: "
    f"{duplicate_dates}"
)


if duplicate_dates > 0:

    print(
        "\nERROR: Duplicate trading dates "
        "were detected."
    )

    print(
        raw[
            raw["Date"]
            .duplicated(
                keep=False
            )
        ]
        .sort_values("Date")
        .to_string(
            index=False
        )
    )

    sys.exit(1)


print(
    "PASS: Dates are unique."
)


# --------------------------------------------------
# 4. Parse OHLC
# --------------------------------------------------

print_section(
    "3. PRICE FIELD VALIDATION"
)


price_mapping = {
    "Price": "close",
    "Open": "open",
    "High": "high",
    "Low": "low",
}


for source_column, target_column in (
    price_mapping.items()
):

    raw[target_column] = (
        raw[source_column]
        .apply(parse_number)
    )


price_columns = [
    "open",
    "high",
    "low",
    "close",
]


price_nulls = (
    raw[
        price_columns
    ]
    .isna()
    .sum()
)


print(
    "Missing parsed price values:"
)

print(
    price_nulls.to_string()
)


if price_nulls.sum() > 0:

    print(
        "\nERROR: One or more OHLC values "
        "could not be parsed."
    )

    sys.exit(1)


# --------------------------------------------------
# 5. OHLC logical validation
# --------------------------------------------------

invalid_high = raw[
    raw["high"]
    <
    raw[
        [
            "open",
            "low",
            "close",
        ]
    ].max(axis=1)
]


invalid_low = raw[
    raw["low"]
    >
    raw[
        [
            "open",
            "high",
            "close",
        ]
    ].min(axis=1)
]


print(
    f"\nInvalid HIGH rows: "
    f"{len(invalid_high)}"
)

print(
    f"Invalid LOW rows: "
    f"{len(invalid_low)}"
)


if (
    not invalid_high.empty
    or not invalid_low.empty
):

    print(
        "\nERROR: OHLC relationships "
        "failed validation."
    )

    sys.exit(1)


print(
    "PASS: OHLC relationships are valid."
)


# --------------------------------------------------
# 6. Volume parsing
# --------------------------------------------------

print_section(
    "4. VOLUME VALIDATION"
)


raw["volume"] = (
    raw["Vol."]
    .apply(parse_volume)
)


missing_volume = int(
    raw["volume"]
    .isna()
    .sum()
)


print(
    f"Missing/unparseable volume rows: "
    f"{missing_volume}"
)


if missing_volume > 0:

    print(
        "\nRows without usable volume:"
    )

    print(
        raw.loc[
            raw["volume"].isna(),
            [
                "Date",
                "Vol.",
            ],
        ]
        .head(20)
        .to_string(
            index=False
        )
    )


# --------------------------------------------------
# 7. Change-percent parsing
# --------------------------------------------------

raw["change_pct"] = (
    raw["Change %"]
    .astype(str)
    .str.replace(
        "%",
        "",
        regex=False,
    )
    .str.replace(
        ",",
        "",
        regex=False,
    )
)


raw["change_pct"] = pd.to_numeric(
    raw["change_pct"],
    errors="coerce",
)


# --------------------------------------------------
# 8. Identity sanity check
# --------------------------------------------------

print_section(
    "5. IHS MARKIT IDENTITY VALIDATION"
)


final_row = raw[
    raw["Date"]
    == EXPECTED_FINAL_DATE
]


if final_row.empty:

    print(
        f"\nERROR: Expected final trading "
        f"date {EXPECTED_FINAL_DATE.date()} "
        "was not found."
    )

    sys.exit(1)


if len(final_row) != 1:

    print(
        "\nERROR: Expected exactly one "
        "final trading-day observation."
    )

    sys.exit(1)


actual_final_close = float(
    final_row.iloc[0][
        "close"
    ]
)


print(
    f"Expected final trading date: "
    f"{EXPECTED_FINAL_DATE.date()}"
)

print(
    f"Returned final trading date: "
    f"{last_date.date()}"
)

print(
    f"Expected final close: "
    f"{EXPECTED_FINAL_CLOSE:.2f}"
)

print(
    f"Returned final close: "
    f"{actual_final_close:.2f}"
)


final_date_pass = (
    last_date
    == EXPECTED_FINAL_DATE
)


final_price_pass = (
    abs(
        actual_final_close
        - EXPECTED_FINAL_CLOSE
    )
    <= FINAL_CLOSE_TOLERANCE
)


print(
    f"\nFinal date check: "
    f"{'PASS' if final_date_pass else 'FAIL'}"
)

print(
    f"Final close check: "
    f"{'PASS' if final_price_pass else 'FAIL'}"
)


if (
    not final_date_pass
    or not final_price_pass
):

    print(
        "\nERROR: Export does not pass "
        "the IHS Markit identity check."
    )

    sys.exit(1)


print(
    "\nPASS: Historical series matches "
    "the expected IHS Markit endpoint."
)


# --------------------------------------------------
# 9. Date-range validation
# --------------------------------------------------

print_section(
    "6. COVERAGE VALIDATION"
)


start_gap = (
    first_date
    - REQUESTED_START
).days


print(
    f"Requested start: "
    f"{REQUESTED_START.date()}"
)

print(
    f"First observation: "
    f"{first_date.date()}"
)

print(
    f"Start calendar gap: "
    f"{start_gap} day(s)"
)


# Jan 1, 2020 was a market holiday, so
# Jan 2 is the expected first observation.

start_pass = (
    first_date
    == pd.Timestamp(
        "2020-01-02"
    )
)


print(
    f"Start-date coverage: "
    f"{'PASS' if start_pass else 'REVIEW'}"
)


# --------------------------------------------------
# 10. Build standardized raw-price representation
# --------------------------------------------------

print_section(
    "7. STANDARDIZE DATA"
)


standardized = pd.DataFrame(
    {
        "date": raw["Date"],
        "security_key": "INFO",
        "project_ticker": "INFO",
        "provider_symbol": "INFO_OLD",
        "source": "Investing.com",
        "open": raw["open"],
        "high": raw["high"],
        "low": raw["low"],
        "close": raw["close"],
        "volume": raw["volume"],
        "change_pct_source": (
            raw["change_pct"]
        ),
    }
)


standardized = (
    standardized
    .sort_values("date")
    .reset_index(drop=True)
)


# --------------------------------------------------
# 11. Final summary
# --------------------------------------------------

print_section(
    "8. STANDARDIZED DATA SUMMARY"
)


print(
    f"Rows: "
    f"{len(standardized)}"
)

print(
    f"First date: "
    f"{standardized['date'].min().date()}"
)

print(
    f"Last date: "
    f"{standardized['date'].max().date()}"
)

print(
    f"Duplicate dates: "
    f"{standardized['date'].duplicated().sum()}"
)

print(
    f"Missing close prices: "
    f"{standardized['close'].isna().sum()}"
)

print(
    f"Missing volume values: "
    f"{standardized['volume'].isna().sum()}"
)


# --------------------------------------------------
# 12. Save standardized interim file
# --------------------------------------------------

print_section(
    "9. SAVE STANDARDIZED INTERIM DATA"
)


INTERIM_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


standardized.to_csv(
    OUTPUT_FILE,
    index=False,
    date_format="%Y-%m-%d",
)


print(
    f"Standardized INFO dataset saved:\n"
    f"{OUTPUT_FILE}"
)


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section(
    "VALIDATION RESULT"
)


print(
    "INFO INVESTING.COM RAW PRICE "
    "VALIDATION PASSED."
)

print(
    "\nThe archived IHS Markit OHLCV "
    "series is now available for the "
    "standardized market-data pipeline."
)

print(
    "\nAdjusted-price reconstruction "
    "has NOT yet been performed."
)