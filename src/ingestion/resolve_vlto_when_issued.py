from pathlib import Path
import os
import sys
from urllib.parse import quote

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "vlto_when_issued_search_audit.csv"
)

RAW_OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "source"
    / "prices"
    / "tiingo_exceptions"
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

TIINGO_API_TOKEN = os.getenv(
    "TIINGO_API_TOKEN"
)

if not TIINGO_API_TOKEN:

    raise RuntimeError(
        "TIINGO_API_TOKEN was not found in .env"
    )


BASE_URL = "https://api.tiingo.com"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization":
        f"Token {TIINGO_API_TOKEN}",
}


# ============================================================
# TARGET
# ============================================================

TARGET_START = pd.Timestamp(
    "2023-09-27"
)

TARGET_END = pd.Timestamp(
    "2023-10-03"
)

WHEN_ISSUED_DATES = {
    pd.Timestamp("2023-09-27"),
    pd.Timestamp("2023-09-28"),
    pd.Timestamp("2023-09-29"),
}

REGULAR_WAY_DATES = {
    pd.Timestamp("2023-10-02"),
    pd.Timestamp("2023-10-03"),
}


# Candidate spellings are deliberately broad.
#
# We do NOT accept a candidate merely because it
# returns data. Identity must first be consistent
# with Veralto.

MANUAL_CANDIDATES = [
    "VLTO",
    "VLTO-WI",
    "VLTOWI",
    "VLTO.WI",
    "VLTO-W",
    "VLTOW",
    "VLTO WI",
]


SEARCH_TERMS = [
    "VLTO",
    "VLTO WI",
    "Veralto",
    "Veralto Corporation",
]


# ============================================================
# DISPLAY
# ============================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    260,
)

pd.set_option(
    "display.max_colwidth",
    160,
)


def print_section(title):

    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


# ============================================================
# HELPERS
# ============================================================

def normalize_dates(series):

    values = pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    )

    return (
        values
        .dt
        .tz_convert(None)
        .dt
        .normalize()
    )


def search_tiingo(query):

    response = requests.get(
        (
            f"{BASE_URL}/tiingo/"
            "utilities/search"
        ),
        headers=HEADERS,
        params={
            "query": query,
        },
        timeout=30,
    )

    return response


def get_metadata(symbol):

    encoded_symbol = quote(
        str(symbol),
        safe="",
    )

    response = requests.get(
        (
            f"{BASE_URL}/tiingo/"
            f"daily/{encoded_symbol}"
        ),
        headers=HEADERS,
        timeout=30,
    )

    return response


def get_prices(symbol):

    encoded_symbol = quote(
        str(symbol),
        safe="",
    )

    response = requests.get(
        (
            f"{BASE_URL}/tiingo/"
            f"daily/{encoded_symbol}/prices"
        ),
        headers=HEADERS,
        params={
            "startDate":
                TARGET_START.strftime(
                    "%Y-%m-%d"
                ),

            "endDate":
                TARGET_END.strftime(
                    "%Y-%m-%d"
                ),
        },
        timeout=30,
    )

    return response


def parse_price_response(response):

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


    if "date" not in data.columns:

        return None


    data["date"] = (
        normalize_dates(
            data["date"]
        )
    )


    return (
        data
        .sort_values("date")
        .reset_index(drop=True)
    )


def identity_looks_like_veralto(
    candidate_symbol,
    metadata,
):

    ticker = str(
        metadata.get(
            "ticker",
            "",
        )
    ).upper()


    name = str(
        metadata.get(
            "name",
            "",
        )
    ).upper()


    requested = str(
        candidate_symbol
    ).upper()


    if "VERALTO" in name:

        return True


    if ticker.startswith(
        "VLTO"
    ):

        return True


    if requested == "VLTO":

        return True


    return False


# ============================================================
# START
# ============================================================

print_section(
    "VLTO WHEN-ISSUED HISTORICAL PRICE SEARCH"
)


print(
    "Official when-issued target:"
)

print(
    "2023-09-27 through 2023-09-29"
)

print(
    "\nKnown regular-way start:"
)

print(
    "2023-10-02"
)


# ============================================================
# 1. SEARCH TIINGO DATABASE
# ============================================================

print_section(
    "1. TIINGO SYMBOL SEARCH"
)


search_records = []


for search_term in SEARCH_TERMS:

    response = search_tiingo(
        search_term
    )


    print(
        f"\nSearch term: "
        f"{search_term}"
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

        search_records.append(
            {
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
        )


if search_records:

    search_results = (
        pd.DataFrame(
            search_records
        )
        .drop_duplicates()
        .reset_index(drop=True)
    )


    print(
        "\nCombined search results:"
    )

    print(
        search_results.to_string(
            index=False
        )
    )


else:

    search_results = pd.DataFrame()

    print(
        "\nNo search results."
    )


# ============================================================
# 2. BUILD CANDIDATE SET
# ============================================================

print_section(
    "2. BUILD SYMBOL CANDIDATES"
)


candidate_symbols = set(
    MANUAL_CANDIDATES
)


if not search_results.empty:

    for _, row in (
        search_results.iterrows()
    ):

        ticker = row.get(
            "ticker"
        )

        name = str(
            row.get(
                "name",
                "",
            )
        )


        if (
            pd.notna(ticker)
            and (
                "VERALTO"
                in name.upper()
                or "VLTO"
                in str(
                    ticker
                ).upper()
            )
        ):

            candidate_symbols.add(
                str(ticker)
            )


        perma = row.get(
            "permaTicker"
        )


        if (
            pd.notna(perma)
            and (
                "VERALTO"
                in name.upper()
                or "VLTO"
                in str(
                    ticker
                ).upper()
            )
        ):

            candidate_symbols.add(
                str(perma)
            )


candidate_symbols = sorted(
    candidate_symbols
)


print(
    "Candidates:"
)


for symbol in candidate_symbols:

    print(
        f"  {symbol}"
    )


# ============================================================
# 3. METADATA / IDENTITY VALIDATION
# ============================================================

print_section(
    "3. CANDIDATE IDENTITY VALIDATION"
)


candidate_records = []


for symbol in candidate_symbols:

    response = get_metadata(
        symbol
    )


    print(
        f"\nCandidate: "
        f"{symbol}"
    )

    print(
        f"Metadata HTTP: "
        f"{response.status_code}"
    )


    metadata = {}


    if response.status_code == 200:

        try:

            metadata = (
                response.json()
            )

        except Exception:

            metadata = {}


        print(
            metadata
        )


    else:

        print(
            response.text[:300]
        )


    identity_valid = (
        identity_looks_like_veralto(
            symbol,
            metadata,
        )
        if metadata
        else False
    )


    print(
        "Veralto identity: "
        f"{'PASS' if identity_valid else 'NO'}"
    )


    candidate_records.append(
        {
            "candidate_symbol":
                symbol,

            "metadata_http":
                response.status_code,

            "metadata_ticker":
                metadata.get(
                    "ticker"
                ),

            "metadata_name":
                metadata.get(
                    "name"
                ),

            "metadata_start":
                metadata.get(
                    "startDate"
                ),

            "metadata_end":
                metadata.get(
                    "endDate"
                ),

            "exchange_code":
                metadata.get(
                    "exchangeCode"
                ),

            "identity_valid":
                identity_valid,
        }
    )


candidate_table = pd.DataFrame(
    candidate_records
)


# ============================================================
# 4. TEST ONLY IDENTITY-VALID CANDIDATES
# ============================================================

print_section(
    "4. HISTORICAL PRICE TEST"
)


result_records = []


valid_candidates = (
    candidate_table[
        candidate_table[
            "identity_valid"
        ]
        == True
    ]
)


if valid_candidates.empty:

    print(
        "No candidate passed "
        "Veralto identity validation."
    )


for _, candidate in (
    valid_candidates.iterrows()
):

    symbol = candidate[
        "candidate_symbol"
    ]


    print(
        f"\nTesting: "
        f"{symbol}"
    )


    response = get_prices(
        symbol
    )


    print(
        f"Price HTTP: "
        f"{response.status_code}"
    )


    if response.status_code != 200:

        print(
            response.text[:500]
        )


        result_records.append(
            {
                "candidate_symbol":
                    symbol,

                "status":
                    "HTTP_FAILURE",

                "rows":
                    0,

                "first_date":
                    None,

                "last_date":
                    None,

                "when_issued_sessions":
                    0,

                "regular_way_sessions":
                    0,
            }
        )

        continue


    data = parse_price_response(
        response
    )


    if data is None:

        print(
            "Invalid payload."
        )


        result_records.append(
            {
                "candidate_symbol":
                    symbol,

                "status":
                    "INVALID_PAYLOAD",

                "rows":
                    0,

                "first_date":
                    None,

                "last_date":
                    None,

                "when_issued_sessions":
                    0,

                "regular_way_sessions":
                    0,
            }
        )

        continue


    if data.empty:

        print(
            "NO_DATA"
        )


        result_records.append(
            {
                "candidate_symbol":
                    symbol,

                "status":
                    "NO_DATA",

                "rows":
                    0,

                "first_date":
                    None,

                "last_date":
                    None,

                "when_issued_sessions":
                    0,

                "regular_way_sessions":
                    0,
            }
        )

        continue


    observed_dates = set(
        data["date"]
    )


    when_issued_found = (
        WHEN_ISSUED_DATES
        & observed_dates
    )


    regular_found = (
        REGULAR_WAY_DATES
        & observed_dates
    )


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
        "\nReturned data:"
    )


    display_columns = [
        column
        for column in [
            "date",
            "open",
            "high",
            "low",
            "close",
            "adjClose",
            "volume",
            "divCash",
            "splitFactor",
        ]
        if column in data.columns
    ]


    print(
        data[
            display_columns
        ]
        .to_string(
            index=False
        )
    )


    print(
        "\nWhen-issued sessions found:"
    )

    print(
        sorted(
            date.date()
            for date
            in when_issued_found
        )
    )


    # Save any actual Veralto data returned.
    RAW_OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    safe_symbol = (
        str(symbol)
        .replace(
            " ",
            "_",
        )
        .replace(
            "/",
            "_",
        )
    )


    raw_file = (
        RAW_OUTPUT_DIR
        / (
            "VLTO__when_issued_probe__"
            f"{safe_symbol}.csv"
        )
    )


    data.to_csv(
        raw_file,
        index=False,
        date_format="%Y-%m-%d",
    )


    print(
        f"\nSaved:\n"
        f"{raw_file}"
    )


    result_records.append(
        {
            "candidate_symbol":
                symbol,

            "status":
                (
                    "WHEN_ISSUED_FOUND"
                    if when_issued_found
                    else "REGULAR_ONLY"
                ),

            "rows":
                len(data),

            "first_date":
                data[
                    "date"
                ].min().date(),

            "last_date":
                data[
                    "date"
                ].max().date(),

            "when_issued_sessions":
                len(
                    when_issued_found
                ),

            "regular_way_sessions":
                len(
                    regular_found
                ),
        }
    )


# ============================================================
# 5. SAVE AUDIT
# ============================================================

print_section(
    "5. SAVE SEARCH AUDIT"
)


results = pd.DataFrame(
    result_records
)


audit = candidate_table.merge(
    results,
    on="candidate_symbol",
    how="left",
)


OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


audit.to_csv(
    OUTPUT_FILE,
    index=False,
)


print(
    audit.to_string(
        index=False
    )
)


print(
    f"\nSaved:\n"
    f"{OUTPUT_FILE}"
)


# ============================================================
# 6. FINAL DETERMINATION
# ============================================================

print_section(
    "6. VLTO WHEN-ISSUED DETERMINATION"
)


if results.empty:

    recovered_count = 0

else:

    recovered_count = int(
        results[
            "when_issued_sessions"
        ]
        .fillna(0)
        .max()
    )


print(
    f"Official when-issued sessions "
    f"sought: 3"
)

print(
    f"Maximum recovered from one "
    f"validated provider identity: "
    f"{recovered_count}"
)


if recovered_count == 3:

    print(
        "\nVLTO WHEN-ISSUED HISTORY "
        "FULLY RECOVERED."
    )


elif recovered_count > 0:

    print(
        "\nVLTO WHEN-ISSUED HISTORY "
        "PARTIALLY RECOVERED."
    )


else:

    print(
        "\nNO TIINGO VLTO WHEN-ISSUED "
        "HISTORY WAS FOUND."
    )

    print(
        "\nThe official 2023-09-27 through "
        "2023-09-29 when-issued market will "
        "remain a documented historical "
        "coverage limitation."
    )

    print(
        "\nRegular-way history beginning "
        "2023-10-02 is independently "
        "available from Tiingo."
    )


print_section(
    "SEARCH COMPLETE"
)


print(
    "No existing raw market-price "
    "file was modified."
)