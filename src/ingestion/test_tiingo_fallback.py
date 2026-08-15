from pathlib import Path
import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "price_download_manifest.csv"
)


# --------------------------------------------------
# Ticker currently being investigated
# --------------------------------------------------

TEST_TICKER = "ATVI"


# --------------------------------------------------
# Environment
# --------------------------------------------------

load_dotenv()

API_TOKEN = os.getenv("TIINGO_API_TOKEN")

if not API_TOKEN:
    raise RuntimeError(
        "TIINGO_API_TOKEN was not found in .env"
    )


# --------------------------------------------------
# Load manifest
# --------------------------------------------------

manifest = pd.read_csv(
    MANIFEST_FILE
)

manifest["download_start"] = pd.to_datetime(
    manifest["download_start"]
)

manifest["download_end_exclusive"] = pd.to_datetime(
    manifest["download_end_exclusive"]
)


ticker_rows = manifest[
    manifest["project_ticker"] == TEST_TICKER
]


if len(ticker_rows) != 1:

    print(
        f"ERROR: Expected exactly one manifest row "
        f"for {TEST_TICKER}, found {len(ticker_rows)}."
    )

    sys.exit(1)


row = ticker_rows.iloc[0]


START_DATE = row["download_start"]

END_EXCLUSIVE = row[
    "download_end_exclusive"
]

# Tiingo endDate is treated as an inclusive date
# for this request, while our project uses an
# exclusive ending boundary.
END_INCLUSIVE = (
    END_EXCLUSIVE
    - pd.Timedelta(days=1)
)


# --------------------------------------------------
# Request configuration
# --------------------------------------------------

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Token {API_TOKEN}",
}


print("=" * 70)
print("TIINGO FALLBACK VALIDATION")
print("=" * 70)

print(
    f"\nProject ticker: {TEST_TICKER}"
)

print(
    f"Manifest download start: "
    f"{START_DATE.date()}"
)

print(
    f"Manifest end exclusive: "
    f"{END_EXCLUSIVE.date()}"
)

print(
    f"Tiingo request end inclusive: "
    f"{END_INCLUSIVE.date()}"
)


# --------------------------------------------------
# 1. Metadata
# --------------------------------------------------

metadata_url = (
    f"https://api.tiingo.com/"
    f"tiingo/daily/{TEST_TICKER}"
)

metadata_response = requests.get(
    metadata_url,
    headers=headers,
    timeout=30,
)


print(
    f"\nMetadata HTTP status: "
    f"{metadata_response.status_code}"
)


if metadata_response.status_code != 200:

    print(metadata_response.text[:1000])

    sys.exit(1)


metadata = metadata_response.json()


print("\nTicker metadata:")

for field in [
    "ticker",
    "name",
    "exchangeCode",
    "startDate",
    "endDate",
]:

    print(
        f"{field}: "
        f"{metadata.get(field)}"
    )


# --------------------------------------------------
# 2. Historical prices
# --------------------------------------------------

price_url = (
    f"https://api.tiingo.com/"
    f"tiingo/daily/{TEST_TICKER}/prices"
)


params = {
    "startDate": START_DATE.strftime(
        "%Y-%m-%d"
    ),
    "endDate": END_INCLUSIVE.strftime(
        "%Y-%m-%d"
    ),
}


price_response = requests.get(
    price_url,
    headers=headers,
    params=params,
    timeout=30,
)


print(
    f"\nPrice HTTP status: "
    f"{price_response.status_code}"
)


if price_response.status_code != 200:

    print(price_response.text[:1000])

    sys.exit(1)


prices = price_response.json()


if not prices:

    print(
        "\nFAILED: Tiingo returned no "
        "historical rows."
    )

    sys.exit(1)


data = pd.DataFrame(
    prices
)


data["date"] = pd.to_datetime(
    data["date"],
    utc=True,
)


# --------------------------------------------------
# 3. Schema validation
# --------------------------------------------------

expected_columns = {
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjOpen",
    "adjHigh",
    "adjLow",
    "adjClose",
    "adjVolume",
    "divCash",
    "splitFactor",
}


missing_columns = (
    expected_columns
    - set(data.columns)
)


print(
    f"\nRows returned: "
    f"{len(data)}"
)

print(
    f"First returned date: "
    f"{data['date'].min().date()}"
)

print(
    f"Last returned date: "
    f"{data['date'].max().date()}"
)


print("\nMissing expected columns:")

if missing_columns:

    print(
        sorted(missing_columns)
    )

else:

    print("None")


# --------------------------------------------------
# 4. Basic quality audit
# --------------------------------------------------

required_price_columns = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjClose",
]


missing_values = (
    data[
        required_price_columns
    ]
    .isna()
    .sum()
)


duplicate_dates = int(
    data["date"].duplicated().sum()
)


print("\nMissing values:")

print(
    missing_values.to_string()
)


print(
    f"\nDuplicate dates: "
    f"{duplicate_dates}"
)


# --------------------------------------------------
# 5. Result
# --------------------------------------------------

if (
    not missing_columns
    and duplicate_dates == 0
    and missing_values.sum() == 0
):

    print(
        "\nTIINGO FALLBACK VALIDATION PASSED."
    )

else:

    print(
        "\nTIINGO FALLBACK VALIDATION "
        "REQUIRES INVESTIGATION."
    )

    sys.exit(2)