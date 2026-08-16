from pathlib import Path
import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# PROJECT / ENVIRONMENT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_exception_verification.csv"
)

load_dotenv()

TIINGO_API_TOKEN = os.getenv(
    "TIINGO_API_TOKEN"
)

if not TIINGO_API_TOKEN:

    raise RuntimeError(
        "TIINGO_API_TOKEN was not found in .env"
    )


HEADERS = {
    "Content-Type": "application/json",
    "Authorization":
        f"Token {TIINGO_API_TOKEN}",
}


BASE_URL = (
    "https://api.tiingo.com"
)


# ============================================================
# DISPLAY
# ============================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    220,
)


def print_section(title):

    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


# ============================================================
# HTTP HELPERS
# ============================================================

def tiingo_metadata(symbol):

    url = (
        f"{BASE_URL}/tiingo/daily/"
        f"{symbol}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    return response


def tiingo_prices(
    symbol,
    start_date,
    end_date,
):

    url = (
        f"{BASE_URL}/tiingo/daily/"
        f"{symbol}/prices"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        params={
            "startDate":
                start_date,

            "endDate":
                end_date,
        },
        timeout=30,
    )

    return response


def tiingo_search(query):

    url = (
        f"{BASE_URL}/tiingo/"
        "utilities/search"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        params={
            "query": query,
        },
        timeout=30,
    )

    return response


def parse_price_response(
    response,
    symbol,
):

    if response.status_code != 200:

        return None


    try:

        payload = response.json()

    except Exception:

        return None


    if not isinstance(
        payload,
        list,
    ):

        return None


    if not payload:

        return pd.DataFrame()


    data = pd.DataFrame(
        payload
    )


    if "date" in data.columns:

        data["date"] = pd.to_datetime(
            data["date"],
            utc=True,
            errors="coerce",
        )


    data.insert(
        0,
        "queried_symbol",
        symbol,
    )


    return data


# ============================================================
# RESULTS
# ============================================================

verification_records = []


def add_verification(
    case,
    queried_symbol,
    date,
    open_value,
    high_value,
    low_value,
    close_value,
    adj_close_value,
    volume,
    result,
):

    verification_records.append(
        {
            "case":
                case,

            "queried_symbol":
                queried_symbol,

            "date":
                date,

            "open":
                open_value,

            "high":
                high_value,

            "low":
                low_value,

            "close":
                close_value,

            "adj_close":
                adj_close_value,

            "volume":
                volume,

            "result":
                result,
        }
    )


# ============================================================
# START
# ============================================================

print_section(
    "MARKET PRICE EXCEPTION VERIFICATION"
)


# ============================================================
# 1. UA — VERIFY 2021-05-05
# ============================================================

print_section(
    "1. UA / 2021-05-05"
)


ua_response = tiingo_prices(
    symbol="UA",
    start_date="2021-05-03",
    end_date="2021-05-07",
)


print(
    f"HTTP status: "
    f"{ua_response.status_code}"
)


if ua_response.status_code != 200:

    print(
        ua_response.text[:1000]
    )


else:

    ua_data = parse_price_response(
        ua_response,
        "UA",
    )


    if (
        ua_data is None
        or ua_data.empty
    ):

        print(
            "NO_DATA"
        )


    else:

        print(
            ua_data[
                [
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "adjClose",
                    "volume",
                ]
            ]
            .to_string(
                index=False
            )
        )


        ua_target = ua_data[
            ua_data["date"]
            .dt
            .date
            == pd.Timestamp(
                "2021-05-05"
            ).date()
        ]


        if len(ua_target) == 1:

            row = ua_target.iloc[0]


            logical_pass = (
                row["low"]
                <= min(
                    row["open"],
                    row["high"],
                    row["close"],
                )
            )


            print(
                "\n2021-05-05 Tiingo:"
            )

            print(
                f"Open:  {row['open']}"
            )

            print(
                f"High:  {row['high']}"
            )

            print(
                f"Low:   {row['low']}"
            )

            print(
                f"Close: {row['close']}"
            )

            print(
                f"Volume: "
                f"{row['volume']}"
            )


            print(
                "\nOHLC logical check: "
                f"{'PASS' if logical_pass else 'FAIL'}"
            )


            add_verification(
                case=
                    "UA_INVALID_LOW",

                queried_symbol=
                    "UA",

                date=
                    "2021-05-05",

                open_value=
                    row["open"],

                high_value=
                    row["high"],

                low_value=
                    row["low"],

                close_value=
                    row["close"],

                adj_close_value=
                    row["adjClose"],

                volume=
                    row["volume"],

                result=
                    (
                        "VALID_OHLC"
                        if logical_pass
                        else "INVALID_OHLC"
                    ),
            )


        else:

            print(
                "\nERROR: Expected exactly "
                "one 2021-05-05 UA row."
            )


# ============================================================
# 2. FISV — VERIFY MISSING 2025-11-12
# ============================================================

print_section(
    "2. FISV / 2025-11-12"
)


fisv_symbols = [
    "FISV",
    "FI",
]


for symbol in fisv_symbols:

    print(
        f"\nTesting Tiingo symbol: "
        f"{symbol}"
    )


    response = tiingo_prices(
        symbol=symbol,
        start_date="2025-11-10",
        end_date="2025-11-14",
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


    data = parse_price_response(
        response,
        symbol,
    )


    if (
        data is None
        or data.empty
    ):

        print(
            "NO_DATA"
        )

        continue


    print(
        data[
            [
                "date",
                "open",
                "high",
                "low",
                "close",
                "adjClose",
                "volume",
            ]
        ]
        .to_string(
            index=False
        )
    )


    target = data[
        data["date"]
        .dt
        .date
        == pd.Timestamp(
            "2025-11-12"
        ).date()
    ]


    if len(target) == 1:

        row = target.iloc[0]


        print(
            "\n2025-11-12 FOUND."
        )


        add_verification(
            case=
                "FISV_INTERNAL_GAP",

            queried_symbol=
                symbol,

            date=
                "2025-11-12",

            open_value=
                row["open"],

            high_value=
                row["high"],

            low_value=
                row["low"],

            close_value=
                row["close"],

            adj_close_value=
                row["adjClose"],

            volume=
                row["volume"],

            result=
                "FOUND",
        )


# ============================================================
# 3. DISCA DIRECT METADATA
# ============================================================

print_section(
    "3. DISCA DIRECT TIINGO METADATA"
)


disca_metadata_response = (
    tiingo_metadata(
        "DISCA"
    )
)


print(
    f"HTTP status: "
    f"{disca_metadata_response.status_code}"
)


if (
    disca_metadata_response.status_code
    == 200
):

    try:

        metadata = (
            disca_metadata_response.json()
        )


        print(
            metadata
        )


    except Exception:

        print(
            disca_metadata_response
            .text[:1000]
        )


else:

    print(
        disca_metadata_response
        .text[:1000]
    )


# ============================================================
# 4. DISCA SEARCH
# ============================================================

print_section(
    "4. DISCA TIINGO SEARCH"
)


search_terms = [
    "DISCA",
    "Discovery Inc",
    "Discovery Communications",
]


all_search_results = []


for search_term in search_terms:

    print(
        f"\nSearch term: "
        f"{search_term}"
    )


    response = tiingo_search(
        search_term
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


    try:

        payload = response.json()

    except Exception:

        print(
            response.text[:500]
        )

        continue


    print(
        f"Results returned: "
        f"{len(payload)}"
    )


    for item in payload:

        record = {
            "search_term":
                search_term,

            "ticker":
                item.get(
                    "ticker"
                ),

            "name":
                item.get(
                    "name"
                ),

            "assetType":
                item.get(
                    "assetType"
                ),

            "isActive":
                item.get(
                    "isActive"
                ),

            "permaTicker":
                item.get(
                    "permaTicker"
                ),

            "openFIGI":
                item.get(
                    "openFIGI"
                ),
        }


        all_search_results.append(
            record
        )


if all_search_results:

    search_dataframe = pd.DataFrame(
        all_search_results
    )


    search_dataframe = (
        search_dataframe
        .drop_duplicates()
        .reset_index(drop=True)
    )


    print(
        "\nCombined search results:"
    )


    print(
        search_dataframe
        .to_string(
            index=False
        )
    )


else:

    search_dataframe = (
        pd.DataFrame()
    )


# ============================================================
# 5. TEST DISCA PERMATICKERS
# ============================================================

print_section(
    "5. DISCA PERMATICKER HISTORY TEST"
)


if search_dataframe.empty:

    print(
        "No Tiingo search candidates "
        "were available."
    )


else:

    likely_discovery = (
        search_dataframe[
            (
                search_dataframe[
                    "ticker"
                ]
                .fillna("")
                .str
                .upper()
                .isin(
                    [
                        "DISCA",
                        "DISCK",
                    ]
                )
            )
            |
            (
                search_dataframe[
                    "name"
                ]
                .fillna("")
                .str
                .contains(
                    "Discovery",
                    case=False,
                    regex=False,
                )
            )
        ]
        .copy()
    )


    print(
        "Likely Discovery candidates:"
    )


    if likely_discovery.empty:

        print(
            "None."
        )


    else:

        print(
            likely_discovery
            .to_string(
                index=False
            )
        )


        tested_perma = set()


        for _, candidate in (
            likely_discovery.iterrows()
        ):

            perma_ticker = (
                candidate.get(
                    "permaTicker"
                )
            )


            if pd.isna(
                perma_ticker
            ):

                continue


            perma_ticker = str(
                perma_ticker
            ).strip()


            if not perma_ticker:

                continue


            if (
                perma_ticker
                in tested_perma
            ):

                continue


            tested_perma.add(
                perma_ticker
            )


            print(
                "\nTesting permanent "
                f"identifier: "
                f"{perma_ticker}"
            )


            response = tiingo_prices(
                symbol=perma_ticker,
                start_date="2020-01-01",
                end_date="2022-04-08",
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


            data = parse_price_response(
                response,
                perma_ticker,
            )


            if (
                data is None
                or data.empty
            ):

                print(
                    "NO_DATA"
                )

                continue


            print(
                f"Rows: "
                f"{len(data)}"
            )

            print(
                f"First date: "
                f"{data['date'].min().date()}"
            )

            print(
                f"Last date: "
                f"{data['date'].max().date()}"
            )


            print(
                "\nFirst rows:"
            )

            print(
                data.head()
                .to_string(
                    index=False
                )
            )


            print(
                "\nLast rows:"
            )

            print(
                data.tail()
                .to_string(
                    index=False
                )
            )


# ============================================================
# 6. SAVE MACHINE-READABLE VERIFICATION
# ============================================================

print_section(
    "6. SAVE EXCEPTION VERIFICATION"
)


verification = pd.DataFrame(
    verification_records
)


if verification.empty:

    print(
        "No successful verification "
        "observations were collected."
    )


else:

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    verification.to_csv(
        OUTPUT_FILE,
        index=False,
    )


    print(
        verification.to_string(
            index=False
        )
    )


    print(
        f"\nSaved:\n"
        f"{OUTPUT_FILE}"
    )


# ============================================================
# FINAL
# ============================================================

print_section(
    "VERIFICATION COMPLETE"
)


print(
    "No existing raw market-price "
    "files were modified."
)

print(
    "\nThis script only gathered "
    "independent evidence for:"
)

print(
    "- UA 2021-05-05"
)

print(
    "- FISV 2025-11-12"
)

print(
    "- DISCA historical identity / "
    "Tiingo permanent-symbol coverage"
)