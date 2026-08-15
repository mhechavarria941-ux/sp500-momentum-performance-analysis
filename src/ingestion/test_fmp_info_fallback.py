import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Environment
# --------------------------------------------------

load_dotenv()

API_KEY = os.getenv("FMP_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "FMP_API_KEY was not found in .env"
    )


# --------------------------------------------------
# Configuration
# --------------------------------------------------

TICKER = "INFO"

START_DATE = pd.Timestamp("2020-01-01")
END_EXCLUSIVE = pd.Timestamp("2022-03-03")

END_INCLUSIVE = (
    END_EXCLUSIVE
    - pd.Timedelta(days=1)
)


BASE_URL = (
    "https://financialmodelingprep.com/stable"
)


# --------------------------------------------------
# Helper
# --------------------------------------------------

def print_section(title):

    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


def make_request(endpoint, params=None):

    if params is None:
        params = {}

    params["apikey"] = API_KEY

    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        params=params,
        timeout=30,
    )

    return response


# --------------------------------------------------
# Start
# --------------------------------------------------

print_section(
    "FMP INFO FALLBACK TEST"
)

print(
    f"Ticker: {TICKER}"
)

print(
    f"Target start: "
    f"{START_DATE.date()}"
)

print(
    f"Target end exclusive: "
    f"{END_EXCLUSIVE.date()}"
)


# --------------------------------------------------
# 1. Company profile
# --------------------------------------------------

print_section(
    "1. COMPANY PROFILE TEST"
)


profile_response = make_request(
    "profile",
    {
        "symbol": TICKER
    },
)


print(
    f"HTTP status: "
    f"{profile_response.status_code}"
)


if profile_response.status_code == 200:

    try:

        profile_payload = (
            profile_response.json()
        )

        print(
            f"Records returned: "
            f"{len(profile_payload)}"
        )

        if profile_payload:

            print(
                profile_payload[0]
            )

    except Exception:

        print(
            profile_response.text[:1000]
        )

else:

    print(
        profile_response.text[:1000]
    )


# --------------------------------------------------
# 2. Dividend-adjusted historical prices
# --------------------------------------------------

print_section(
    "2. DIVIDEND-ADJUSTED PRICE TEST"
)


adjusted_response = make_request(
    "historical-price-eod/dividend-adjusted",
    {
        "symbol": TICKER,
    },
)


print(
    f"HTTP status: "
    f"{adjusted_response.status_code}"
)


adjusted_data = None


if adjusted_response.status_code == 200:

    try:

        payload = (
            adjusted_response.json()
        )

        if isinstance(payload, list):

            adjusted_data = pd.DataFrame(
                payload
            )

            print(
                f"Rows returned before "
                f"date filtering: "
                f"{len(adjusted_data)}"
            )

        else:

            print(
                "Unexpected payload:"
            )

            print(
                str(payload)[:1000]
            )

    except Exception as error:

        print(
            f"JSON parsing error: "
            f"{error}"
        )

        print(
            adjusted_response.text[:1000]
        )

else:

    print(
        adjusted_response.text[:1000]
    )


# --------------------------------------------------
# 3. Filter adjusted dataset
# --------------------------------------------------

if (
    adjusted_data is not None
    and not adjusted_data.empty
):

    if "date" not in adjusted_data.columns:

        print(
            "\nAdjusted dataset has no "
            "'date' column."
        )

    else:

        adjusted_data[
            "date"
        ] = pd.to_datetime(
            adjusted_data["date"],
            errors="raise",
        )


        adjusted_window = adjusted_data[
            (
                adjusted_data["date"]
                >= START_DATE
            )
            &
            (
                adjusted_data["date"]
                < END_EXCLUSIVE
            )
        ].copy()


        adjusted_window = (
            adjusted_window
            .sort_values("date")
            .reset_index(drop=True)
        )


        print(
            f"\nRows inside target range: "
            f"{len(adjusted_window)}"
        )


        if not adjusted_window.empty:

            print(
                f"First returned date: "
                f"{adjusted_window['date'].min().date()}"
            )

            print(
                f"Last returned date: "
                f"{adjusted_window['date'].max().date()}"
            )

            print(
                "\nColumns:"
            )

            print(
                adjusted_window.columns.tolist()
            )

            print(
                "\nFirst 5 rows:"
            )

            print(
                adjusted_window
                .head()
                .to_string(index=False)
            )

            print(
                "\nLast 5 rows:"
            )

            print(
                adjusted_window
                .tail()
                .to_string(index=False)
            )


# --------------------------------------------------
# 4. Full EOD historical prices
# --------------------------------------------------

print_section(
    "3. FULL EOD PRICE TEST"
)


full_response = make_request(
    "historical-price-eod/full",
    {
        "symbol": TICKER,
    },
)


print(
    f"HTTP status: "
    f"{full_response.status_code}"
)


full_data = None


if full_response.status_code == 200:

    try:

        payload = (
            full_response.json()
        )

        if isinstance(payload, list):

            full_data = pd.DataFrame(
                payload
            )

            print(
                f"Rows returned before "
                f"date filtering: "
                f"{len(full_data)}"
            )

        else:

            print(
                "Unexpected payload:"
            )

            print(
                str(payload)[:1000]
            )

    except Exception as error:

        print(
            f"JSON parsing error: "
            f"{error}"
        )

        print(
            full_response.text[:1000]
        )

else:

    print(
        full_response.text[:1000]
    )


# --------------------------------------------------
# 5. Filter full dataset
# --------------------------------------------------

if (
    full_data is not None
    and not full_data.empty
):

    if "date" not in full_data.columns:

        print(
            "\nFull dataset has no "
            "'date' column."
        )

    else:

        full_data["date"] = pd.to_datetime(
            full_data["date"],
            errors="raise",
        )


        full_window = full_data[
            (
                full_data["date"]
                >= START_DATE
            )
            &
            (
                full_data["date"]
                < END_EXCLUSIVE
            )
        ].copy()


        full_window = (
            full_window
            .sort_values("date")
            .reset_index(drop=True)
        )


        print(
            f"\nRows inside target range: "
            f"{len(full_window)}"
        )


        if not full_window.empty:

            print(
                f"First returned date: "
                f"{full_window['date'].min().date()}"
            )

            print(
                f"Last returned date: "
                f"{full_window['date'].max().date()}"
            )

            print(
                "\nColumns:"
            )

            print(
                full_window.columns.tolist()
            )

            print(
                "\nFirst 5 rows:"
            )

            print(
                full_window
                .head()
                .to_string(index=False)
            )

            print(
                "\nLast 5 rows:"
            )

            print(
                full_window
                .tail()
                .to_string(index=False)
            )


# --------------------------------------------------
# 6. Final determination
# --------------------------------------------------

print_section(
    "TEST RESULT"
)


adjusted_success = (
    adjusted_data is not None
    and not adjusted_data.empty
    and "date" in adjusted_data.columns
    and len(adjusted_window) > 0
)


full_success = (
    full_data is not None
    and not full_data.empty
    and "date" in full_data.columns
    and len(full_window) > 0
)


if adjusted_success:

    print(
        "FMP DIVIDEND-ADJUSTED INFO "
        "HISTORY FOUND."
    )

    print(
        "\nPreferred fallback candidate:"
    )

    print(
        "Financial Modeling Prep / INFO"
    )


elif full_success:

    print(
        "FMP RAW/SPLIT-ADJUSTED INFO "
        "HISTORY FOUND."
    )

    print(
        "\nAdjusted-price handling will "
        "still require review."
    )


else:

    print(
        "FMP DID NOT RESOLVE INFO."
    )

    print(
        "\nA different historical source "
        "will be required."
    )