from pathlib import Path
import sys

import pandas as pd


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TICKER_HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "sp500_ticker_history_2021_2025.csv"
)

ALIASES_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "securities"
    / "security_aliases.csv"
)

INTERIM_DIR = (
    PROJECT_ROOT
    / "data"
    / "interim"
)

OUTPUT_FILE = (
    INTERIM_DIR
    / "price_download_manifest.csv"
)


# --------------------------------------------------
# Acquisition boundaries
# --------------------------------------------------

ANALYSIS_START = pd.Timestamp("2021-01-01")
ANALYSIS_END_EXCLUSIVE = pd.Timestamp("2026-01-01")

# Approximately enough calendar history to support
# a 12-month / 252-trading-day momentum calculation.
LOOKBACK_DAYS = 400

EARLIEST_LOOKBACK = pd.Timestamp("2020-01-01")


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def print_section(title):
    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


def yahoo_symbol(ticker):
    """
    Convert project ticker format to Yahoo Finance format.

    Examples:
    BRK.B -> BRK-B
    BF.B  -> BF-B
    """
    ticker = str(ticker).strip().upper()

    return ticker.replace(".", "-")


# --------------------------------------------------
# Load inputs
# --------------------------------------------------

print_section("HISTORICAL PRICE DOWNLOAD MANIFEST")


if not TICKER_HISTORY_FILE.exists():
    print(
        "\nERROR: Ticker-history dataset does not exist."
    )
    print(
        "Run build_membership_intervals.py first."
    )
    sys.exit(1)


if not ALIASES_FILE.exists():
    print(
        "\nERROR: Security-alias reference does not exist."
    )
    sys.exit(1)


ticker_history = pd.read_csv(
    TICKER_HISTORY_FILE
)

aliases = pd.read_csv(
    ALIASES_FILE
)


# --------------------------------------------------
# Normalize fields
# --------------------------------------------------

ticker_history["ticker"] = (
    ticker_history["ticker"]
    .astype(str)
    .str.strip()
    .str.upper()
)

ticker_history["ticker_valid_from"] = pd.to_datetime(
    ticker_history["ticker_valid_from"],
    format="%Y-%m-%d",
    errors="raise",
)

ticker_history["ticker_valid_to_exclusive"] = pd.to_datetime(
    ticker_history["ticker_valid_to_exclusive"],
    format="%Y-%m-%d",
    errors="raise",
)


aliases["old_ticker"] = (
    aliases["old_ticker"]
    .astype(str)
    .str.strip()
    .str.upper()
)

aliases["new_ticker"] = (
    aliases["new_ticker"]
    .astype(str)
    .str.strip()
    .str.upper()
)

alias_new_tickers = set(
    aliases["new_ticker"]
)


# --------------------------------------------------
# 1. Build equity download requests
# --------------------------------------------------

print_section("1. BUILD SECURITY REQUESTS")


manifest_rows = []


for _, row in ticker_history.iterrows():

    ticker = row["ticker"]

    valid_from = row["ticker_valid_from"]

    valid_to = row[
        "ticker_valid_to_exclusive"
    ]


    # --------------------------------------------------
    # Lookback logic
    #
    # For a security entering the analytical universe,
    # obtain enough earlier history to calculate
    # trailing momentum.
    #
    # For the NEW side of a documented ticker change,
    # do not extend backward through the old ticker's
    # validity period. The old ticker segment will
    # provide that history and will later be stitched
    # using security_key.
    # --------------------------------------------------

    if ticker in alias_new_tickers:

        download_start = valid_from

        lookback_extended = False

    else:

        download_start = max(
            valid_from
            - pd.Timedelta(
                days=LOOKBACK_DAYS
            ),
            EARLIEST_LOOKBACK,
        )

        lookback_extended = (
            download_start < valid_from
        )


    download_end = min(
        valid_to,
        ANALYSIS_END_EXCLUSIVE,
    )


    if download_start >= download_end:

        print(
            f"\nERROR: Invalid download range "
            f"for {ticker}."
        )
        print(
            f"Start: {download_start.date()}"
        )
        print(
            f"End: {download_end.date()}"
        )

        sys.exit(1)


    yahoo_ticker = yahoo_symbol(
        ticker
    )


    manifest_rows.append(
        {
            "security_key": row[
                "security_key"
            ],
            "project_ticker": ticker,
            "yahoo_ticker": yahoo_ticker,
            "ticker_valid_from": valid_from,
            "ticker_valid_to_exclusive": valid_to,
            "download_start": download_start,
            "download_end_exclusive": download_end,
            "lookback_extended": lookback_extended,
            "symbol_transformed": (
                yahoo_ticker != ticker
            ),
            "source_kind": "equity",
            "source": "Yahoo Finance",
        }
    )


# --------------------------------------------------
# 2. Add benchmark requests
# --------------------------------------------------

print_section("2. ADD BENCHMARK REQUESTS")


# ^GSPC:
# Official S&P 500 price index representation
# available through Yahoo Finance.
#
# SPY:
# Investable ETF proxy that can later be useful
# for adjusted/total-return comparisons.

benchmark_rows = [
    {
        "security_key": "SP500_INDEX",
        "project_ticker": "^GSPC",
        "yahoo_ticker": "^GSPC",
        "ticker_valid_from": ANALYSIS_START,
        "ticker_valid_to_exclusive": ANALYSIS_END_EXCLUSIVE,
        "download_start": EARLIEST_LOOKBACK,
        "download_end_exclusive": ANALYSIS_END_EXCLUSIVE,
        "lookback_extended": True,
        "symbol_transformed": False,
        "source_kind": "benchmark_index",
        "source": "Yahoo Finance",
    },
    {
        "security_key": "SPY_ETF",
        "project_ticker": "SPY",
        "yahoo_ticker": "SPY",
        "ticker_valid_from": ANALYSIS_START,
        "ticker_valid_to_exclusive": ANALYSIS_END_EXCLUSIVE,
        "download_start": EARLIEST_LOOKBACK,
        "download_end_exclusive": ANALYSIS_END_EXCLUSIVE,
        "lookback_extended": True,
        "symbol_transformed": False,
        "source_kind": "benchmark_etf",
        "source": "Yahoo Finance",
    },
]


manifest_rows.extend(
    benchmark_rows
)


# --------------------------------------------------
# 3. Create manifest
# --------------------------------------------------

manifest = pd.DataFrame(
    manifest_rows
)


manifest = manifest.sort_values(
    [
        "source_kind",
        "security_key",
        "download_start",
    ]
).reset_index(drop=True)


# --------------------------------------------------
# 4. Validate uniqueness
# --------------------------------------------------

print_section("3. MANIFEST VALIDATION")


duplicate_requests = manifest[
    manifest.duplicated(
        subset=[
            "security_key",
            "project_ticker",
            "download_start",
            "download_end_exclusive",
        ],
        keep=False,
    )
]


if not duplicate_requests.empty:

    print(
        "\nERROR: Duplicate download requests detected."
    )

    print(
        duplicate_requests.to_string(
            index=False
        )
    )

    sys.exit(1)


print(
    "PASS: No duplicate download requests."
)


# --------------------------------------------------
# 5. Inspect Yahoo ticker transformations
# --------------------------------------------------

transformed = manifest[
    manifest["symbol_transformed"]
]


print_section("4. YAHOO SYMBOL TRANSFORMATIONS")


if transformed.empty:

    print(
        "No ticker transformations required."
    )

else:

    print(
        transformed[
            [
                "project_ticker",
                "yahoo_ticker",
            ]
        ]
        .drop_duplicates()
        .to_string(index=False)
    )


# --------------------------------------------------
# 6. Manifest summary
# --------------------------------------------------

print_section("5. DOWNLOAD MANIFEST SUMMARY")


print(
    f"Total download requests: "
    f"{len(manifest)}"
)

print(
    f"Equity ticker segments: "
    f"{int((manifest['source_kind'] == 'equity').sum())}"
)

print(
    f"Benchmark requests: "
    f"{int((manifest['source_kind'] != 'equity').sum())}"
)

print(
    f"Unique security keys: "
    f"{manifest['security_key'].nunique()}"
)

print(
    f"Unique project tickers: "
    f"{manifest['project_ticker'].nunique()}"
)

print(
    f"Unique Yahoo tickers: "
    f"{manifest['yahoo_ticker'].nunique()}"
)

print(
    f"Lookback-extended requests: "
    f"{int(manifest['lookback_extended'].sum())}"
)

print(
    f"Yahoo symbol transformations: "
    f"{int(manifest['symbol_transformed'].sum())}"
)


# --------------------------------------------------
# 7. Save manifest
# --------------------------------------------------

print_section("6. SAVE MANIFEST")


INTERIM_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


manifest.to_csv(
    OUTPUT_FILE,
    index=False,
    date_format="%Y-%m-%d",
)


print(
    f"Manifest saved:\n"
    f"{OUTPUT_FILE}"
)


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section("BUILD RESULT")


print(
    "PRICE DOWNLOAD MANIFEST PASSED."
)

print(
    "\nNo market prices have been downloaded yet."
)

print(
    "The acquisition plan is now explicit "
    "and ready for availability testing."
)

sys.exit(0)