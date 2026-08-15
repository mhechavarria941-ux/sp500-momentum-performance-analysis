import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Environment
# --------------------------------------------------

load_dotenv()

API_KEY = os.getenv("TWELVE_DATA_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "TWELVE_DATA_API_KEY was not found in .env"
    )


# --------------------------------------------------
# Configuration
# --------------------------------------------------

TICKER = "INFO"

START_DATE = "2020-01-01"
END_DATE = "2022-03-02"

BASE_URL = "https://api.twelvedata.com"


# --------------------------------------------------
# Helper
# --------------------------------------------------

def print_section(title):
    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


# --------------------------------------------------
# Start
# --------------------------------------------------

print_section(
    "TWELVE DATA INFO FALLBACK TEST"
)

print(f"Ticker: {TICKER}")
print(f"Start: {START_DATE}")
print(f"End: {END_DATE}")


# --------------------------------------------------
# 1. Request fully adjusted prices
# --------------------------------------------------

print_section(
    "1. ADJUSTED DAILY PRICE TEST"
)


params = {
    "symbol": TICKER,
    "interval": "1day",
    "start_date": START_DATE,
    "end_date": END_DATE,
    "adjust": "all",
    "order": "ASC",
    "apikey": API_KEY,
}


response = requests.get(
    f"{BASE_URL}/time_series",
    params=params,
    timeout=30,
)


print(
    f"HTTP status: "
    f"{response.status_code}"
)


try:
    payload = response.json()

except Exception as error:
    print(
        f"JSON parsing failed: {error}"
    )

    print(
        response.text[:1000]
    )

    sys.exit(1)


# --------------------------------------------------
# 2. Check for API error
# --------------------------------------------------

if payload.get("status") == "error":

    print("\nAPI ERROR:")

    print(
        payload.get("message")
    )

    sys.exit(2)


# --------------------------------------------------
# 3. Inspect metadata carefully
# --------------------------------------------------

print_section(
    "2. RETURNED METADATA"
)


meta = payload.get(
    "meta",
    {}
)


for field in [
    "symbol",
    "interval",
    "currency",
    "exchange",
    "mic_code",
    "type",
]:

    print(
        f"{field}: "
        f"{meta.get(field)}"
    )


# --------------------------------------------------
# 4. Historical values
# --------------------------------------------------

values = payload.get(
    "values",
    []
)


print_section(
    "3. HISTORICAL DATA"
)


print(
    f"Rows returned: "
    f"{len(values)}"
)


if not values:

    print(
        "\nNO_DATA: Twelve Data returned "
        "no INFO observations for 2020-2022."
    )

    sys.exit(3)


data = pd.DataFrame(
    values
)


print(
    "\nColumns:"
)

print(
    data.columns.tolist()
)


if "datetime" not in data.columns:

    print(
        "\nERROR: datetime column missing."
    )

    sys.exit(4)


data["datetime"] = pd.to_datetime(
    data["datetime"],
    errors="raise",
)


data = (
    data
    .sort_values("datetime")
    .reset_index(drop=True)
)


numeric_columns = [
    column
    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    if column in data.columns
]


for column in numeric_columns:

    data[column] = pd.to_numeric(
        data[column],
        errors="coerce",
    )


# --------------------------------------------------
# 5. Coverage
# --------------------------------------------------

first_date = (
    data["datetime"]
    .min()
    .date()
)

last_date = (
    data["datetime"]
    .max()
    .date()
)


print(
    f"\nFirst returned date: "
    f"{first_date}"
)

print(
    f"Last returned date: "
    f"{last_date}"
)


print(
    "\nFirst 5 rows:"
)

print(
    data.head()
    .to_string(index=False)
)


print(
    "\nLast 5 rows:"
)

print(
    data.tail()
    .to_string(index=False)
)


# --------------------------------------------------
# 6. Quality validation
# --------------------------------------------------

print_section(
    "4. QUALITY VALIDATION"
)


expected_columns = {
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


missing_columns = (
    expected_columns
    - set(data.columns)
)


duplicate_dates = int(
    data["datetime"]
    .duplicated()
    .sum()
)


if numeric_columns:

    required_nulls = int(
        data[numeric_columns]
        .isna()
        .sum()
        .sum()
    )

else:

    required_nulls = None


print(
    f"Missing expected columns: "
    f"{sorted(missing_columns)}"
)

print(
    f"Duplicate dates: "
    f"{duplicate_dates}"
)

print(
    f"Required-field nulls: "
    f"{required_nulls}"
)


# --------------------------------------------------
# 7. Sanity checks
# --------------------------------------------------

print_section(
    "5. IDENTITY / PRICE SANITY CHECK"
)


first_close = (
    data.iloc[0]["close"]
)

last_close = (
    data.iloc[-1]["close"]
)


print(
    f"First close: "
    f"{first_close}"
)

print(
    f"Last close: "
    f"{last_close}"
)


# Known final IHS Markit market price
# should be approximately $108.61 on
# 2022-02-25.

final_target = data[
    data["datetime"]
    == pd.Timestamp("2022-02-25")
]


if final_target.empty:

    print(
        "\nWARNING: No observation "
        "for 2022-02-25."
    )

else:

    final_close = float(
        final_target.iloc[0]["close"]
    )

    print(
        f"2022-02-25 close: "
        f"{final_close}"
    )


    if abs(
        final_close - 108.61
    ) <= 0.10:

        print(
            "PASS: Final price matches "
            "the historical IHS Markit series."
        )

    else:

        print(
            "FAIL: Returned INFO data does "
            "not appear to match IHS Markit."
        )


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section(
    "TEST RESULT"
)


if (
    not missing_columns
    and duplicate_dates == 0
    and required_nulls == 0
):

    print(
        "TWELVE DATA RETURNED A COMPLETE "
        "DAILY INFO DATASET."
    )

    print(
        "\nIdentity still must pass the "
        "2022-02-25 price sanity check "
        "before we accept it."
    )

else:

    print(
        "TWELVE DATA INFO DATA REQUIRES "
        "FURTHER REVIEW."
    )