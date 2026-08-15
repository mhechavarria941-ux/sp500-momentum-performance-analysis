import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv


# --------------------------------------------------
# Environment
# --------------------------------------------------

load_dotenv()

API_TOKEN = os.getenv("TIINGO_API_TOKEN")

if not API_TOKEN:

    raise RuntimeError(
        "TIINGO_API_TOKEN was not found in .env"
    )


headers = {
    "Content-Type": "application/json",
    "Authorization": f"Token {API_TOKEN}",
}


# --------------------------------------------------
# Search terms
# --------------------------------------------------

SEARCH_TERMS = [
    "INFO",
    "IHS Markit",
    "Markit",
]


print("=" * 75)
print("TIINGO INFO PERMATICKER SEARCH")
print("=" * 75)


all_results = []


# --------------------------------------------------
# 1. Search Tiingo asset database
# --------------------------------------------------

for term in SEARCH_TERMS:

    url = (
        "https://api.tiingo.com/"
        "tiingo/utilities/search"
    )

    response = requests.get(
        url,
        headers=headers,
        params={
            "query": term
        },
        timeout=30,
    )


    print(
        f"\nSearch: {term}"
    )

    print(
        f"HTTP status: "
        f"{response.status_code}"
    )


    if response.status_code != 200:

        print(
            response.text[:500]
        )

        continue


    payload = response.json()


    print(
        f"Results returned: "
        f"{len(payload)}"
    )


    for item in payload:

        record = {
            "search_term": term,
            "ticker": item.get(
                "ticker"
            ),
            "name": item.get(
                "name"
            ),
            "assetType": item.get(
                "assetType"
            ),
            "isActive": item.get(
                "isActive"
            ),
            "permaTicker": item.get(
                "permaTicker"
            ),
            "openFIGI": item.get(
                "openFIGI"
            ),
        }

        all_results.append(
            record
        )


# --------------------------------------------------
# 2. Display useful search results
# --------------------------------------------------

print("\n" + "=" * 75)
print("SEARCH RESULTS")
print("=" * 75)


results = pd.DataFrame(
    all_results
)


if results.empty:

    print(
        "No Tiingo search results returned."
    )

    sys.exit(1)


results = (
    results
    .drop_duplicates(
        subset=[
            "ticker",
            "name",
            "permaTicker",
        ]
    )
    .reset_index(drop=True)
)


print(
    results.to_string(
        index=False
    )
)


# --------------------------------------------------
# 3. Find likely IHS Markit record
# --------------------------------------------------

name_series = (
    results["name"]
    .fillna("")
    .astype(str)
)


ticker_series = (
    results["ticker"]
    .fillna("")
    .astype(str)
    .str.upper()
)


candidates = results[
    (
        name_series
        .str.contains(
            "IHS Markit",
            case=False,
            regex=False,
        )
    )
    |
    (
        ticker_series
        == "INFO"
    )
].copy()


print("\n" + "=" * 75)
print("IHS MARKIT CANDIDATES")
print("=" * 75)


if candidates.empty:

    print(
        "No IHS Markit candidate was "
        "identified by Tiingo Search."
    )

    sys.exit(2)


print(
    candidates.to_string(
        index=False
    )
)


# --------------------------------------------------
# 4. Test each returned permaTicker
# --------------------------------------------------

print("\n" + "=" * 75)
print("PERMATICKER PRICE TEST")
print("=" * 75)


tested_any = False


for _, candidate in (
    candidates.iterrows()
):

    perma_ticker = candidate.get(
        "permaTicker"
    )


    if (
        pd.isna(perma_ticker)
        or not str(
            perma_ticker
        ).strip()
    ):

        print(
            f"\n{candidate['ticker']} "
            "has no permaTicker."
        )

        continue


    perma_ticker = str(
        perma_ticker
    ).strip()


    tested_any = True


    print(
        f"\nTesting:"
    )

    print(
        f"Ticker: "
        f"{candidate['ticker']}"
    )

    print(
        f"Name: "
        f"{candidate['name']}"
    )

    print(
        f"PermaTicker: "
        f"{perma_ticker}"
    )


    # ----------------------------------------------
    # Original INFO manifest range
    # ----------------------------------------------

    start_date = "2020-01-01"

    # INFO left the analytical universe in 2022.
    # Request slightly beyond expected final trading
    # history so Tiingo can return its natural endpoint.
    end_date = "2022-03-10"


    price_url = (
        "https://api.tiingo.com/"
        f"tiingo/daily/"
        f"{perma_ticker}/prices"
    )


    response = requests.get(
        price_url,
        headers=headers,
        params={
            "startDate": start_date,
            "endDate": end_date,
        },
        timeout=30,
    )


    print(
        f"Price HTTP status: "
        f"{response.status_code}"
    )


    if response.status_code != 200:

        print(
            "Response:"
        )

        print(
            response.text[:1000]
        )

        continue


    payload = response.json()


    if not payload:

        print(
            "Result: NO_DATA"
        )

        continue


    data = pd.DataFrame(
        payload
    )


    data["date"] = pd.to_datetime(
        data["date"],
        utc=True,
        errors="raise",
    )


    print(
        f"Rows returned: "
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


    print(
        "\nColumns:"
    )

    print(
        data.columns.tolist()
    )


    print(
        "\nFirst 5 rows:"
    )

    print(
        data.head()
        .to_string(
            index=False
        )
    )


    print(
        "\nLast 5 rows:"
    )

    print(
        data.tail()
        .to_string(
            index=False
        )
    )


    print(
        "\nPERMATICKER PRICE DATA FOUND."
    )


if not tested_any:

    print(
        "\nNo usable permaTicker was "
        "returned by the search endpoint."
    )