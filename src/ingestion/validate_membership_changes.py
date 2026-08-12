from pathlib import Path
from urllib.parse import urlparse
import re
import sys

import pandas as pd


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "membership"
    / "sp500_official_changes.csv"
)


# --------------------------------------------------
# Expected structure
# --------------------------------------------------

EXPECTED_COLUMNS = [
    "announcement_date",
    "effective_date",
    "index_name",
    "action",
    "company_name",
    "ticker",
    "gics_sector",
    "source_type",
    "source_url",
    "notes",
]

VALID_ACTIONS = {"Addition", "Deletion"}

VALID_GICS_SECTORS = {
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
}

TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")

ALLOWED_SOURCE_DOMAINS = {
    "press.spglobal.com",
    "www.spglobal.com",
    "spglobal.com",
}


# --------------------------------------------------
# Validation containers
# --------------------------------------------------

errors = []
warnings = []


def print_section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# --------------------------------------------------
# Load file
# --------------------------------------------------

print_section("S&P 500 MEMBERSHIP CHANGE VALIDATOR")

print(f"Source file:\n{SOURCE_FILE}")

if not SOURCE_FILE.exists():
    print("\nERROR: Source file does not exist.")
    sys.exit(1)

try:
    changes = pd.read_csv(SOURCE_FILE)
except Exception as error:
    print("\nERROR: CSV could not be read.")
    print(error)
    sys.exit(1)


print(f"\nRows loaded: {len(changes)}")
print(f"Columns loaded: {len(changes.columns)}")


# --------------------------------------------------
# 1. Column validation
# --------------------------------------------------

print_section("1. COLUMN VALIDATION")

actual_columns = changes.columns.tolist()

missing_columns = [
    column
    for column in EXPECTED_COLUMNS
    if column not in actual_columns
]

unexpected_columns = [
    column
    for column in actual_columns
    if column not in EXPECTED_COLUMNS
]

if missing_columns:
    errors.append(
        f"Missing required columns: {missing_columns}"
    )

if unexpected_columns:
    warnings.append(
        f"Unexpected columns found: {unexpected_columns}"
    )

if actual_columns == EXPECTED_COLUMNS:
    print("PASS: Column structure is correct.")
else:
    print("CHECK: Column structure differs from expected.")


# --------------------------------------------------
# Stop if required columns are missing
# --------------------------------------------------

if missing_columns:
    print("\nCannot continue validation because required columns are missing.")

    for error in errors:
        print(f"ERROR: {error}")

    sys.exit(1)


# --------------------------------------------------
# 2. Missing values
# --------------------------------------------------

print_section("2. REQUIRED VALUE VALIDATION")

required_columns = [
    "announcement_date",
    "effective_date",
    "index_name",
    "action",
    "company_name",
    "ticker",
    "source_type",
    "source_url",
]

missing_required = changes[required_columns].isna().sum()

print(missing_required.to_string())

for column, count in missing_required.items():
    if count > 0:
        errors.append(
            f"{column} contains {count} missing required value(s)."
        )


# --------------------------------------------------
# 3. Date validation
# --------------------------------------------------

print_section("3. DATE VALIDATION")

changes["announcement_date_parsed"] = pd.to_datetime(
    changes["announcement_date"],
    errors="coerce",
    format="%Y-%m-%d"
)

changes["effective_date_parsed"] = pd.to_datetime(
    changes["effective_date"],
    errors="coerce",
    format="%Y-%m-%d"
)

invalid_announcement_dates = changes[
    changes["announcement_date_parsed"].isna()
]

invalid_effective_dates = changes[
    changes["effective_date_parsed"].isna()
]

if not invalid_announcement_dates.empty:
    errors.append(
        f"{len(invalid_announcement_dates)} invalid announcement date(s)."
    )

if not invalid_effective_dates.empty:
    errors.append(
        f"{len(invalid_effective_dates)} invalid effective date(s)."
    )

date_order_problem = changes[
    changes["effective_date_parsed"]
    < changes["announcement_date_parsed"]
]

if not date_order_problem.empty:
    errors.append(
        f"{len(date_order_problem)} row(s) have an effective date "
        "before the announcement date."
    )

if (
    invalid_announcement_dates.empty
    and invalid_effective_dates.empty
    and date_order_problem.empty
):
    print("PASS: Dates are valid and logically ordered.")


# --------------------------------------------------
# 4. Index name validation
# --------------------------------------------------

print_section("4. INDEX VALIDATION")

unexpected_indexes = changes[
    changes["index_name"] != "S&P 500"
]

if unexpected_indexes.empty:
    print("PASS: Every row is identified as S&P 500.")
else:
    errors.append(
        f"{len(unexpected_indexes)} row(s) contain an unexpected index name."
    )

    print(
        unexpected_indexes[
            ["index_name", "company_name", "ticker"]
        ].to_string(index=False)
    )


# --------------------------------------------------
# 5. Action validation
# --------------------------------------------------

print_section("5. ACTION VALIDATION")

invalid_actions = changes[
    ~changes["action"].isin(VALID_ACTIONS)
]

if invalid_actions.empty:
    print("PASS: All actions are Addition or Deletion.")
else:
    errors.append(
        f"{len(invalid_actions)} invalid action value(s)."
    )

    print(
        invalid_actions[
            ["effective_date", "company_name", "ticker", "action"]
        ].to_string(index=False)
    )


# --------------------------------------------------
# 6. Ticker validation
# --------------------------------------------------

print_section("6. TICKER VALIDATION")

changes["ticker"] = (
    changes["ticker"]
    .astype(str)
    .str.strip()
)

invalid_tickers = changes[
    ~changes["ticker"].str.match(TICKER_PATTERN, na=False)
]

if invalid_tickers.empty:
    print("PASS: All ticker formats appear valid.")
else:
    errors.append(
        f"{len(invalid_tickers)} invalid ticker format(s)."
    )

    print(
        invalid_tickers[
            ["company_name", "ticker", "effective_date"]
        ].to_string(index=False)
    )


# --------------------------------------------------
# 7. Duplicate validation
# --------------------------------------------------

print_section("7. DUPLICATE VALIDATION")

exact_duplicates = changes[
    changes.duplicated(
        subset=[
            "effective_date",
            "action",
            "ticker",
        ],
        keep=False,
    )
]

if exact_duplicates.empty:
    print("PASS: No duplicate effective-date/action/ticker records.")
else:
    errors.append(
        f"{len(exact_duplicates)} duplicate change record(s) detected."
    )

    print(
        exact_duplicates[
            [
                "effective_date",
                "action",
                "company_name",
                "ticker",
            ]
        ].sort_values(
            ["effective_date", "ticker"]
        ).to_string(index=False)
    )


# --------------------------------------------------
# 8. Source URL validation
# --------------------------------------------------

print_section("8. SOURCE VALIDATION")

invalid_urls = []

for index, row in changes.iterrows():

    url = str(row["source_url"]).strip()

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        invalid_urls.append(index)
        continue

    if parsed.netloc.lower() not in ALLOWED_SOURCE_DOMAINS:
        invalid_urls.append(index)


if not invalid_urls:
    print("PASS: All source URLs point to approved S&P Global domains.")
else:
    errors.append(
        f"{len(invalid_urls)} source URL(s) do not match "
        "approved S&P Global domains."
    )

    print(
        changes.loc[
            invalid_urls,
            [
                "announcement_date",
                "company_name",
                "ticker",
                "source_url",
            ]
        ].to_string(index=False)
    )


# --------------------------------------------------
# 9. GICS sector audit
# --------------------------------------------------

print_section("9. GICS SECTOR AUDIT")

nonstandard_sectors = changes[
    changes["gics_sector"].notna()
    & ~changes["gics_sector"].isin(VALID_GICS_SECTORS)
]

if nonstandard_sectors.empty:
    print("PASS: All populated GICS sectors use standard sector names.")
else:
    warnings.append(
        f"{len(nonstandard_sectors)} row(s) use non-standard "
        "GICS sector wording."
    )

    print("WARNING: Non-standard GICS wording found:")

    print(
        nonstandard_sectors[
            [
                "company_name",
                "ticker",
                "gics_sector",
                "source_url",
            ]
        ].to_string(index=False)
    )


# --------------------------------------------------
# 10. Change counts
# --------------------------------------------------

print_section("10. CHANGE COUNT SUMMARY")

action_counts = changes["action"].value_counts()

print(action_counts.to_string())

additions = int(
    (changes["action"] == "Addition").sum()
)

deletions = int(
    (changes["action"] == "Deletion").sum()
)

net_change = additions - deletions

print(f"\nAdditions: {additions}")
print(f"Deletions: {deletions}")
print(f"Net security-count change: {net_change:+d}")


# --------------------------------------------------
# 11. Effective-date summary
# --------------------------------------------------

print_section("11. EFFECTIVE DATE SUMMARY")

date_summary = (
    changes
    .groupby(
        ["effective_date", "action"]
    )
    .size()
    .unstack(fill_value=0)
    .sort_index()
)

print(date_summary.to_string())


# --------------------------------------------------
# 12. Chronological record
# --------------------------------------------------

print_section("12. CHRONOLOGICAL CHANGE RECORD")

display_columns = [
    "announcement_date",
    "effective_date",
    "action",
    "ticker",
    "company_name",
]

chronological = changes.sort_values(
    [
        "effective_date_parsed",
        "action",
        "ticker",
    ]
)

print(
    chronological[
        display_columns
    ].to_string(index=False)
)


# --------------------------------------------------
# Final results
# --------------------------------------------------

print_section("VALIDATION RESULT")

if warnings:
    print("\nWARNINGS:")

    for warning in warnings:
        print(f"- {warning}")
else:
    print("\nWarnings: 0")


if errors:
    print("\nERRORS:")

    for error in errors:
        print(f"- {error}")

    print(
        f"\nVALIDATION FAILED: "
        f"{len(errors)} critical issue(s) found."
    )

    sys.exit(1)

else:
    print("\nCritical errors: 0")

    print(
        "\nVALIDATION PASSED."
    )

    print(
        "The membership-change dataset passed all "
        "critical structural and logical checks."
    )

    sys.exit(0)