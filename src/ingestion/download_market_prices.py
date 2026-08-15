from pathlib import Path
import os
import re
import sys
import time

import pandas as pd
import requests
import yfinance as yf
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

RESOLUTION_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "price_source_resolutions.csv"
)

PRICE_ROOT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "source"
    / "prices"
)

YAHOO_DIR = (
    PRICE_ROOT
    / "yahoo"
)

TIINGO_DIR = (
    PRICE_ROOT
    / "tiingo"
)

INFO_MANUAL_FILE = (
    PRICE_ROOT
    / "info_old_investing_2020_2022.csv"
)

AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_download_audit.csv"
)


# --------------------------------------------------
# Runtime settings
# --------------------------------------------------

YAHOO_PAUSE_SECONDS = 0.25

TIINGO_PAUSE_SECONDS = 1.5

MAX_YAHOO_ATTEMPTS = 2

YAHOO_RETRY_PAUSE_SECONDS = 3

REQUEST_TIMEOUT = 30


# --------------------------------------------------
# Environment
# --------------------------------------------------

load_dotenv()

TIINGO_API_TOKEN = os.getenv(
    "TIINGO_API_TOKEN"
)


# --------------------------------------------------
# yfinance configuration
# --------------------------------------------------

# Current replacement for the deprecated
# raise_errors=True history() argument.
yf.config.debug.hide_exceptions = False

# Let yfinance retry transient network errors.
yf.config.network.retries = 2


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def print_section(title):

    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


def safe_component(value):

    """
    Convert a ticker/security key into a
    Windows-safe filename component.
    """

    value = str(value).strip()

    return re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value,
    )


def build_filename(
    security_key,
    project_ticker,
    provider_symbol,
):

    security_part = safe_component(
        security_key
    )

    ticker_part = safe_component(
        project_ticker
    )

    provider_part = safe_component(
        provider_symbol
    )

    return (
        f"{security_part}"
        f"__{ticker_part}"
        f"__{provider_part}.csv"
    )


def atomic_save_csv(
    dataframe,
    output_path,
):

    """
    Write to a temporary file first.

    If Python is interrupted during the write,
    an incomplete final CSV will not be left
    behind.
    """

    temporary_path = output_path.with_suffix(
        output_path.suffix + ".tmp"
    )

    dataframe.to_csv(
        temporary_path,
        index=False,
    )

    temporary_path.replace(
        output_path
    )


def save_audit(records):

    audit = pd.DataFrame(
        records
    )

    if audit.empty:
        return

    audit = (
        audit
        .drop_duplicates(
            subset=[
                "security_key",
                "project_ticker",
            ],
            keep="last",
        )
        .sort_values(
            [
                "source",
                "security_key",
                "project_ticker",
            ]
        )
        .reset_index(drop=True)
    )

    AUDIT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit.to_csv(
        AUDIT_FILE,
        index=False,
    )


def inspect_existing_file(
    file_path,
    source,
):

    """
    Read an existing completed raw file
    so a resumed run can report its coverage.
    """

    try:

        data = pd.read_csv(
            file_path
        )

    except Exception:

        return (
            0,
            None,
            None,
        )


    if data.empty:

        return (
            0,
            None,
            None,
        )


    possible_date_columns = [
        "Date",
        "date",
    ]


    date_column = None


    for candidate in possible_date_columns:

        if candidate in data.columns:

            date_column = candidate

            break


    if date_column is None:

        return (
            len(data),
            None,
            None,
        )


    dates = pd.to_datetime(
        data[date_column],
        errors="coerce",
        utc=True,
    )


    if dates.notna().sum() == 0:

        return (
            len(data),
            None,
            None,
        )


    return (
        len(data),
        dates.min().date(),
        dates.max().date(),
    )


# --------------------------------------------------
# Validate required inputs
# --------------------------------------------------

print_section(
    "S&P 500 HISTORICAL MARKET PRICE DOWNLOAD"
)


required_files = [
    MANIFEST_FILE,
    RESOLUTION_FILE,
]


for path in required_files:

    if not path.exists():

        print(
            f"\nERROR: Required file missing:\n"
            f"{path}"
        )

        sys.exit(1)


# --------------------------------------------------
# Load acquisition tables
# --------------------------------------------------

manifest = pd.read_csv(
    MANIFEST_FILE
)

resolution = pd.read_csv(
    RESOLUTION_FILE
)


manifest["download_start"] = pd.to_datetime(
    manifest["download_start"],
    errors="raise",
)

manifest[
    "download_end_exclusive"
] = pd.to_datetime(
    manifest[
        "download_end_exclusive"
    ],
    errors="raise",
)


# --------------------------------------------------
# Merge manifest with validated source resolution
# --------------------------------------------------

download_plan = manifest.merge(
    resolution[
        [
            "security_key",
            "project_ticker",
            "primary_source",
            "primary_symbol",
            "primary_status",
            "fallback_source",
            "fallback_symbol",
            "resolution_status",
        ]
    ],
    on=[
        "security_key",
        "project_ticker",
    ],
    how="left",
    validate="one_to_one",
)


# --------------------------------------------------
# Validate complete resolution
# --------------------------------------------------

print_section(
    "1. DOWNLOAD PLAN VALIDATION"
)


if (
    download_plan[
        "resolution_status"
    ]
    .isna()
    .any()
):

    print(
        "\nERROR: One or more manifest requests "
        "do not have a source-resolution row."
    )

    sys.exit(1)


unresolved = download_plan[
    ~download_plan[
        "resolution_status"
    ].isin(
        [
            "PRIMARY_AVAILABLE",
            "FALLBACK_VALIDATED",
        ]
    )
]


if not unresolved.empty:

    print(
        "\nERROR: Price-source resolution "
        "is incomplete."
    )

    print(
        unresolved[
            [
                "security_key",
                "project_ticker",
                "resolution_status",
            ]
        ].to_string(
            index=False
        )
    )

    sys.exit(1)


if len(download_plan) != 596:

    print(
        "\nERROR: Expected 596 requests "
        f"but found {len(download_plan)}."
    )

    sys.exit(1)


print(
    f"Total requests: "
    f"{len(download_plan)}"
)


primary_count = int(
    (
        download_plan[
            "resolution_status"
        ]
        == "PRIMARY_AVAILABLE"
    ).sum()
)


fallback_count = int(
    (
        download_plan[
            "resolution_status"
        ]
        == "FALLBACK_VALIDATED"
    ).sum()
)


print(
    f"Primary-source requests: "
    f"{primary_count}"
)

print(
    f"Fallback-source requests: "
    f"{fallback_count}"
)

print(
    "PASS: Every request has a "
    "validated acquisition source."
)


# --------------------------------------------------
# Create directories
# --------------------------------------------------

YAHOO_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TIINGO_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# --------------------------------------------------
# Load previous audit for resume support
# --------------------------------------------------

if AUDIT_FILE.exists():

    previous_audit = pd.read_csv(
        AUDIT_FILE
    )

    audit_records = (
        previous_audit
        .to_dict("records")
    )

    print(
        f"\nExisting audit rows loaded: "
        f"{len(previous_audit)}"
    )

else:

    audit_records = []


# --------------------------------------------------
# Tiingo HTTP session
# --------------------------------------------------

tiingo_session = requests.Session()


if TIINGO_API_TOKEN:

    tiingo_session.headers.update(
        {
            "Content-Type":
                "application/json",

            "Authorization":
                f"Token "
                f"{TIINGO_API_TOKEN}",
        }
    )


# --------------------------------------------------
# Counters
# --------------------------------------------------

downloaded_count = 0

existing_count = 0

failed_count = 0

manual_count = 0

rate_limited = False


# --------------------------------------------------
# Process all requests
# --------------------------------------------------

print_section(
    "2. DOWNLOAD MARKET PRICES"
)


total_requests = len(
    download_plan
)


for request_number, (_, row) in enumerate(
    download_plan.iterrows(),
    start=1,
):

    security_key = str(
        row["security_key"]
    )

    project_ticker = str(
        row["project_ticker"]
    )

    download_start = row[
        "download_start"
    ]

    download_end_exclusive = row[
        "download_end_exclusive"
    ]


    # --------------------------------------------------
    # Determine final validated source
    # --------------------------------------------------

    if (
        row["resolution_status"]
        == "PRIMARY_AVAILABLE"
    ):

        source = "Yahoo Finance"

        provider_symbol = str(
            row["primary_symbol"]
        )


    else:

        source = str(
            row["fallback_source"]
        )

        provider_symbol = str(
            row["fallback_symbol"]
        )


    print(
        f"[{request_number}/{total_requests}] "
        f"{security_key} / "
        f"{project_ticker} "
        f"-> {source} "
        f"({provider_symbol})"
    )


    # ==================================================
    # YAHOO FINANCE
    # ==================================================

    if source == "Yahoo Finance":

        filename = build_filename(
            security_key,
            project_ticker,
            provider_symbol,
        )

        output_path = (
            YAHOO_DIR
            / filename
        )


        # ----------------------------------------------
        # Resume / existing file
        # ----------------------------------------------

        if output_path.exists():

            rows, first_date, last_date = (
                inspect_existing_file(
                    output_path,
                    source,
                )
            )


            if rows > 0:

                print(
                    f"    Existing file: "
                    f"{rows} rows "
                    f"({first_date} to "
                    f"{last_date})"
                )

                existing_count += 1


                audit_records.append(
                    {
                        "security_key":
                            security_key,

                        "project_ticker":
                            project_ticker,

                        "provider_symbol":
                            provider_symbol,

                        "source":
                            source,

                        "download_start":
                            download_start.date(),

                        "download_end_exclusive":
                            download_end_exclusive.date(),

                        "status":
                            "EXISTING",

                        "rows_returned":
                            rows,

                        "first_returned_date":
                            first_date,

                        "last_returned_date":
                            last_date,

                        "output_file":
                            str(
                                output_path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),

                        "error_message":
                            None,
                    }
                )


                save_audit(
                    audit_records
                )

                continue


        # ----------------------------------------------
        # Download Yahoo
        # ----------------------------------------------

        history = None

        last_error = None


        for attempt in range(
            1,
            MAX_YAHOO_ATTEMPTS + 1,
        ):

            try:

                ticker_object = yf.Ticker(
                    provider_symbol
                )


                history = (
                    ticker_object.history(
                        start=(
                            download_start.strftime(
                                "%Y-%m-%d"
                            )
                        ),
                        end=(
                            download_end_exclusive.strftime(
                                "%Y-%m-%d"
                            )
                        ),
                        interval="1d",
                        auto_adjust=False,
                        actions=True,
                        repair=False,
                        keepna=False,
                        timeout=20,
                    )
                )


                if (
                    history is not None
                    and not history.empty
                ):

                    break


                last_error = (
                    "Yahoo returned no rows."
                )


            except Exception as error:

                history = None

                last_error = str(
                    error
                )


            if (
                attempt
                < MAX_YAHOO_ATTEMPTS
            ):

                time.sleep(
                    YAHOO_RETRY_PAUSE_SECONDS
                )


        # ----------------------------------------------
        # Yahoo failure
        # ----------------------------------------------

        if (
            history is None
            or history.empty
        ):

            print(
                f"    FAILED: "
                f"{last_error}"
            )

            failed_count += 1


            audit_records.append(
                {
                    "security_key":
                        security_key,

                    "project_ticker":
                        project_ticker,

                    "provider_symbol":
                        provider_symbol,

                    "source":
                        source,

                    "download_start":
                        download_start.date(),

                    "download_end_exclusive":
                        download_end_exclusive.date(),

                    "status":
                        "FAILED",

                    "rows_returned":
                        0,

                    "first_returned_date":
                        None,

                    "last_returned_date":
                        None,

                    "output_file":
                        None,

                    "error_message":
                        last_error,
                }
            )


            save_audit(
                audit_records
            )

            continue


        # ----------------------------------------------
        # Normalize Yahoo date column for storage
        # ----------------------------------------------

        history = (
            history.copy()
        )


        history.index = (
            pd.to_datetime(
                history.index
            )
        )


        if (
            history.index.tz
            is not None
        ):

            history.index = (
                history.index
                .tz_localize(None)
            )


        history.index.name = "Date"


        yahoo_data = (
            history
            .reset_index()
        )


        # ----------------------------------------------
        # Validate date uniqueness
        # ----------------------------------------------

        if (
            yahoo_data["Date"]
            .duplicated()
            .any()
        ):

            error_message = (
                "Yahoo returned duplicate "
                "daily dates."
            )

            print(
                f"    FAILED: "
                f"{error_message}"
            )

            failed_count += 1


            audit_records.append(
                {
                    "security_key":
                        security_key,

                    "project_ticker":
                        project_ticker,

                    "provider_symbol":
                        provider_symbol,

                    "source":
                        source,

                    "download_start":
                        download_start.date(),

                    "download_end_exclusive":
                        download_end_exclusive.date(),

                    "status":
                        "QUALITY_FAILURE",

                    "rows_returned":
                        len(yahoo_data),

                    "first_returned_date":
                        yahoo_data[
                            "Date"
                        ].min().date(),

                    "last_returned_date":
                        yahoo_data[
                            "Date"
                        ].max().date(),

                    "output_file":
                        None,

                    "error_message":
                        error_message,
                }
            )


            save_audit(
                audit_records
            )

            continue


        # ----------------------------------------------
        # Save Yahoo raw acquisition
        # ----------------------------------------------

        atomic_save_csv(
            yahoo_data,
            output_path,
        )


        first_date = (
            yahoo_data[
                "Date"
            ].min().date()
        )

        last_date = (
            yahoo_data[
                "Date"
            ].max().date()
        )


        print(
            f"    DOWNLOADED: "
            f"{len(yahoo_data)} rows "
            f"({first_date} to "
            f"{last_date})"
        )


        downloaded_count += 1


        audit_records.append(
            {
                "security_key":
                    security_key,

                "project_ticker":
                    project_ticker,

                "provider_symbol":
                    provider_symbol,

                "source":
                    source,

                "download_start":
                    download_start.date(),

                "download_end_exclusive":
                    download_end_exclusive.date(),

                "status":
                    "DOWNLOADED",

                "rows_returned":
                    len(yahoo_data),

                "first_returned_date":
                    first_date,

                "last_returned_date":
                    last_date,

                "output_file":
                    str(
                        output_path.relative_to(
                            PROJECT_ROOT
                        )
                    ),

                "error_message":
                    None,
            }
        )


        save_audit(
            audit_records
        )


        time.sleep(
            YAHOO_PAUSE_SECONDS
        )


    # ==================================================
    # TIINGO
    # ==================================================

    elif source == "Tiingo":

        if not TIINGO_API_TOKEN:

            print(
                "\nERROR: "
                "TIINGO_API_TOKEN "
                "was not found in .env."
            )

            sys.exit(1)


        filename = build_filename(
            security_key,
            project_ticker,
            provider_symbol,
        )

        output_path = (
            TIINGO_DIR
            / filename
        )


        # ----------------------------------------------
        # Resume / existing Tiingo file
        # ----------------------------------------------

        if output_path.exists():

            rows, first_date, last_date = (
                inspect_existing_file(
                    output_path,
                    source,
                )
            )


            if rows > 0:

                print(
                    f"    Existing file: "
                    f"{rows} rows "
                    f"({first_date} to "
                    f"{last_date})"
                )

                existing_count += 1


                audit_records.append(
                    {
                        "security_key":
                            security_key,

                        "project_ticker":
                            project_ticker,

                        "provider_symbol":
                            provider_symbol,

                        "source":
                            source,

                        "download_start":
                            download_start.date(),

                        "download_end_exclusive":
                            download_end_exclusive.date(),

                        "status":
                            "EXISTING",

                        "rows_returned":
                            rows,

                        "first_returned_date":
                            first_date,

                        "last_returned_date":
                            last_date,

                        "output_file":
                            str(
                                output_path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),

                        "error_message":
                            None,
                    }
                )


                save_audit(
                    audit_records
                )

                continue


        # ----------------------------------------------
        # Convert project exclusive end to
        # Tiingo inclusive end request.
        # ----------------------------------------------

        end_inclusive = (
            download_end_exclusive
            - pd.Timedelta(days=1)
        )


        url = (
            "https://api.tiingo.com/"
            f"tiingo/daily/"
            f"{provider_symbol}/prices"
        )


        params = {
            "startDate":
                download_start.strftime(
                    "%Y-%m-%d"
                ),

            "endDate":
                end_inclusive.strftime(
                    "%Y-%m-%d"
                ),
        }


        try:

            response = (
                tiingo_session.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
            )


        except Exception as error:

            error_message = str(
                error
            )

            print(
                f"    FAILED: "
                f"{error_message}"
            )

            failed_count += 1


            audit_records.append(
                {
                    "security_key":
                        security_key,

                    "project_ticker":
                        project_ticker,

                    "provider_symbol":
                        provider_symbol,

                    "source":
                        source,

                    "download_start":
                        download_start.date(),

                    "download_end_exclusive":
                        download_end_exclusive.date(),

                    "status":
                        "FAILED",

                    "rows_returned":
                        0,

                    "first_returned_date":
                        None,

                    "last_returned_date":
                        None,

                    "output_file":
                        None,

                    "error_message":
                        error_message,
                }
            )


            save_audit(
                audit_records
            )

            continue


        # ----------------------------------------------
        # Tiingo hourly rate limit
        # ----------------------------------------------

        if response.status_code == 429:

            error_message = (
                "Tiingo HTTP 429: "
                "API rate limit reached."
            )

            print(
                f"    RATE LIMITED"
            )


            audit_records.append(
                {
                    "security_key":
                        security_key,

                    "project_ticker":
                        project_ticker,

                    "provider_symbol":
                        provider_symbol,

                    "source":
                        source,

                    "download_start":
                        download_start.date(),

                    "download_end_exclusive":
                        download_end_exclusive.date(),

                    "status":
                        "RATE_LIMITED",

                    "rows_returned":
                        0,

                    "first_returned_date":
                        None,

                    "last_returned_date":
                        None,

                    "output_file":
                        None,

                    "error_message":
                        error_message,
                }
            )


            save_audit(
                audit_records
            )


            rate_limited = True

            print(
                "\nTiingo quota reached."
            )

            print(
                "Completed files have been "
                "preserved."
            )

            print(
                "Run this script again after "
                "the hourly Tiingo quota resets."
            )

            break


        # ----------------------------------------------
        # Other Tiingo HTTP errors
        # ----------------------------------------------

        if response.status_code != 200:

            error_message = (
                f"HTTP "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )


            print(
                f"    FAILED: "
                f"{error_message}"
            )

            failed_count += 1


            audit_records.append(
                {
                    "security_key":
                        security_key,

                    "project_ticker":
                        project_ticker,

                    "provider_symbol":
                        provider_symbol,

                    "source":
                        source,

                    "download_start":
                        download_start.date(),

                    "download_end_exclusive":
                        download_end_exclusive.date(),

                    "status":
                        "FAILED",

                    "rows_returned":
                        0,

                    "first_returned_date":
                        None,

                    "last_returned_date":
                        None,

                    "output_file":
                        None,

                    "error_message":
                        error_message,
                }
            )


            save_audit(
                audit_records
            )

            continue


        # ----------------------------------------------
        # Parse Tiingo response
        # ----------------------------------------------

        try:

            payload = response.json()


        except Exception as error:

            error_message = (
                f"JSON parsing failure: "
                f"{error}"
            )

            print(
                f"    FAILED: "
                f"{error_message}"
            )

            failed_count += 1


            audit_records.append(
                {
                    "security_key":
                        security_key,

                    "project_ticker":
                        project_ticker,

                    "provider_symbol":
                        provider_symbol,

                    "source":
                        source,

                    "download_start":
                        download_start.date(),

                    "download_end_exclusive":
                        download_end_exclusive.date(),

                    "status":
                        "FAILED",

                    "rows_returned":
                        0,

                    "first_returned_date":
                        None,

                    "last_returned_date":
                        None,

                    "output_file":
                        None,

                    "error_message":
                        error_message,
                }
            )


            save_audit(
                audit_records
            )

            continue


        if not payload:

            error_message = (
                "Tiingo returned no rows."
            )

            print(
                f"    FAILED: "
                f"{error_message}"
            )

            failed_count += 1


            audit_records.append(
                {
                    "security_key":
                        security_key,

                    "project_ticker":
                        project_ticker,

                    "provider_symbol":
                        provider_symbol,

                    "source":
                        source,

                    "download_start":
                        download_start.date(),

                    "download_end_exclusive":
                        download_end_exclusive.date(),

                    "status":
                        "NO_DATA",

                    "rows_returned":
                        0,

                    "first_returned_date":
                        None,

                    "last_returned_date":
                        None,

                    "output_file":
                        None,

                    "error_message":
                        error_message,
                }
            )


            save_audit(
                audit_records
            )

            continue


        tiingo_data = pd.DataFrame(
            payload
        )


        # ----------------------------------------------
        # Validate Tiingo date field
        # ----------------------------------------------

        if (
            "date"
            not in tiingo_data.columns
        ):

            error_message = (
                "Tiingo response is missing "
                "the date field."
            )

            print(
                f"    FAILED: "
                f"{error_message}"
            )

            failed_count += 1

            continue


        tiingo_dates = pd.to_datetime(
            tiingo_data["date"],
            utc=True,
            errors="coerce",
        )


        if (
            tiingo_dates.isna().any()
        ):

            error_message = (
                "Tiingo returned one or more "
                "unparseable dates."
            )

            print(
                f"    FAILED: "
                f"{error_message}"
            )

            failed_count += 1

            continue


        if (
            tiingo_dates
            .duplicated()
            .any()
        ):

            error_message = (
                "Tiingo returned duplicate "
                "daily dates."
            )

            print(
                f"    FAILED: "
                f"{error_message}"
            )

            failed_count += 1

            continue


        # ----------------------------------------------
        # Save Tiingo source-native response
        # ----------------------------------------------

        atomic_save_csv(
            tiingo_data,
            output_path,
        )


        first_date = (
            tiingo_dates
            .min()
            .date()
        )

        last_date = (
            tiingo_dates
            .max()
            .date()
        )


        print(
            f"    DOWNLOADED: "
            f"{len(tiingo_data)} rows "
            f"({first_date} to "
            f"{last_date})"
        )


        downloaded_count += 1


        audit_records.append(
            {
                "security_key":
                    security_key,

                "project_ticker":
                    project_ticker,

                "provider_symbol":
                    provider_symbol,

                "source":
                    source,

                "download_start":
                    download_start.date(),

                "download_end_exclusive":
                    download_end_exclusive.date(),

                "status":
                    "DOWNLOADED",

                "rows_returned":
                    len(tiingo_data),

                "first_returned_date":
                    first_date,

                "last_returned_date":
                    last_date,

                "output_file":
                    str(
                        output_path.relative_to(
                            PROJECT_ROOT
                        )
                    ),

                "error_message":
                    None,
            }
        )


        save_audit(
            audit_records
        )


        time.sleep(
            TIINGO_PAUSE_SECONDS
        )


    # ==================================================
    # INVESTING.COM MANUAL INFO SOURCE
    # ==================================================

    elif source == "Investing.com":

        if (
            security_key != "INFO"
            or project_ticker != "INFO"
            or provider_symbol != "INFO_OLD"
        ):

            print(
                "\nERROR: Unexpected "
                "Investing.com resolution."
            )

            sys.exit(1)


        if not INFO_MANUAL_FILE.exists():

            print(
                "\nERROR: Validated INFO_OLD "
                "raw file is missing:"
            )

            print(
                INFO_MANUAL_FILE
            )

            sys.exit(1)


        info_data = pd.read_csv(
            INFO_MANUAL_FILE
        )


        if info_data.empty:

            print(
                "\nERROR: INFO_OLD raw file "
                "is empty."
            )

            sys.exit(1)


        info_dates = pd.to_datetime(
            info_data["Date"],
            errors="raise",
        )


        first_date = (
            info_dates.min().date()
        )

        last_date = (
            info_dates.max().date()
        )


        print(
            f"    MANUAL SOURCE PRESENT: "
            f"{len(info_data)} rows "
            f"({first_date} to "
            f"{last_date})"
        )


        manual_count += 1


        audit_records.append(
            {
                "security_key":
                    security_key,

                "project_ticker":
                    project_ticker,

                "provider_symbol":
                    provider_symbol,

                "source":
                    source,

                "download_start":
                    download_start.date(),

                "download_end_exclusive":
                    download_end_exclusive.date(),

                "status":
                    "MANUAL_PRESENT",

                "rows_returned":
                    len(info_data),

                "first_returned_date":
                    first_date,

                "last_returned_date":
                    last_date,

                "output_file":
                    str(
                        INFO_MANUAL_FILE.relative_to(
                            PROJECT_ROOT
                        )
                    ),

                "error_message":
                    None,
            }
        )


        save_audit(
            audit_records
        )


    # ==================================================
    # Unknown source
    # ==================================================

    else:

        print(
            f"\nERROR: Unsupported "
            f"resolved source: {source}"
        )

        sys.exit(1)


# --------------------------------------------------
# Build final current-state audit
# --------------------------------------------------

print_section(
    "3. DOWNLOAD SUMMARY"
)


if AUDIT_FILE.exists():

    final_audit = pd.read_csv(
        AUDIT_FILE
    )


    final_audit = (
        final_audit
        .drop_duplicates(
            subset=[
                "security_key",
                "project_ticker",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )


else:

    final_audit = pd.DataFrame()


successful_statuses = {
    "DOWNLOADED",
    "EXISTING",
    "MANUAL_PRESENT",
}


if not final_audit.empty:

    successful = final_audit[
        final_audit["status"]
        .isin(
            successful_statuses
        )
    ]


    incomplete = final_audit[
        ~final_audit["status"]
        .isin(
            successful_statuses
        )
    ]


    print(
        f"Completed requests in audit: "
        f"{len(successful)}"
    )

    print(
        f"Incomplete requests in audit: "
        f"{len(incomplete)}"
    )


    print(
        "\nSource counts:"
    )

    print(
        successful[
            "source"
        ]
        .value_counts()
        .to_string()
    )


    if not incomplete.empty:

        print_section(
            "4. INCOMPLETE REQUESTS"
        )


        print(
            incomplete[
                [
                    "security_key",
                    "project_ticker",
                    "source",
                    "status",
                    "error_message",
                ]
            ].to_string(
                index=False
            )
        )


# --------------------------------------------------
# Current-run statistics
# --------------------------------------------------

print_section(
    "CURRENT RUN"
)


print(
    f"New files downloaded: "
    f"{downloaded_count}"
)

print(
    f"Existing files reused: "
    f"{existing_count}"
)

print(
    f"Manual source files used: "
    f"{manual_count}"
)

print(
    f"Failures encountered: "
    f"{failed_count}"
)


if rate_limited:

    print(
        "\nTiingo rate limit was reached."
    )

    print(
        "Rerun this script after the "
        "hourly quota resets."
    )


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section(
    "DOWNLOAD RESULT"
)


if (
    not final_audit.empty
    and len(successful) == 596
):

    print(
        "ALL 596 HISTORICAL PRICE "
        "REQUESTS ARE PRESENT."
    )

    print(
        "\nMARKET PRICE ACQUISITION PASSED."
    )


else:

    completed_count = (
        len(successful)
        if not final_audit.empty
        else 0
    )


    print(
        f"{completed_count} OF 596 "
        "REQUESTS ARE CURRENTLY PRESENT."
    )

    print(
        "\nThe downloader is restartable."
    )

    print(
        "Run it again to retry any "
        "unfinished requests."
    )