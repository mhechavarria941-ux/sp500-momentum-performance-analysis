from pathlib import Path
import re
import sys

import pandas as pd


# ==================================================
# PROJECT PATHS
# ==================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DOWNLOAD_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_download_audit.csv"
)

INTEGRITY_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_integrity_audit.csv"
)

ISSUES_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_integrity_issues.csv"
)

GAPS_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_calendar_gaps.csv"
)


EXPECTED_REQUEST_COUNT = 596


# ==================================================
# COVERAGE REVIEW THRESHOLDS
# ==================================================

# A few sessions at the beginning can occur because
# of weekends, holidays, IPO timing, listing changes,
# or source-specific boundaries.
#
# We do NOT immediately classify these as corruption.
# Instead, larger gaps become blocking review items.

START_REVIEW_SESSIONS = 5
START_BLOCKING_SESSIONS = 20

END_REVIEW_SESSIONS = 3
END_BLOCKING_SESSIONS = 10

INTERNAL_REVIEW_SESSIONS = 1
INTERNAL_BLOCKING_SESSIONS = 5

EXTRA_DATE_BLOCKING_COUNT = 5


# ==================================================
# HELPERS
# ==================================================

def print_section(title):

    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


def parse_investing_number(value):

    if pd.isna(value):
        return None

    text = str(value).strip()

    if text in {
        "",
        "-",
        "N/A",
    }:
        return None

    text = text.replace(
        ",",
        "",
    )

    try:
        return float(text)

    except ValueError:
        return None


def parse_investing_volume(value):

    if pd.isna(value):
        return None

    text = (
        str(value)
        .strip()
        .upper()
        .replace(",", "")
    )

    if text in {
        "",
        "-",
        "N/A",
    }:
        return None


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


def normalize_dates(series):

    """
    Convert provider dates to timezone-naive
    normalized calendar dates.

    Using utc=True allows this to safely handle
    both timezone-aware and timezone-naive
    source strings.
    """

    dates = pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    )

    dates = (
        dates
        .dt
        .tz_convert(None)
        .dt
        .normalize()
    )

    return dates


def load_normalized_file(
    file_path,
    source,
):

    """
    Read a source-native price file and return a
    temporary common representation for validation.

    IMPORTANT:
    This does NOT produce our final standardized
    analytical dataset.
    """

    raw = pd.read_csv(
        file_path
    )


    # ==================================================
    # YAHOO FINANCE
    # ==================================================

    if source == "Yahoo Finance":

        required_columns = {
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
            "Adj Close",
            "Volume",
        }


        missing_columns = sorted(
            required_columns
            - set(raw.columns)
        )


        if missing_columns:

            return {
                "raw": raw,
                "normalized": None,
                "missing_columns": missing_columns,
                "adjusted_available": True,
                "corporate_action_columns_present": False,
                "corporate_action_nulls": None,
                "invalid_split_rows": None,
            }


        normalized = pd.DataFrame(
            {
                "date":
                    normalize_dates(
                        raw["Date"]
                    ),

                "open":
                    pd.to_numeric(
                        raw["Open"],
                        errors="coerce",
                    ),

                "high":
                    pd.to_numeric(
                        raw["High"],
                        errors="coerce",
                    ),

                "low":
                    pd.to_numeric(
                        raw["Low"],
                        errors="coerce",
                    ),

                "close":
                    pd.to_numeric(
                        raw["Close"],
                        errors="coerce",
                    ),

                "adj_close":
                    pd.to_numeric(
                        raw["Adj Close"],
                        errors="coerce",
                    ),

                "volume":
                    pd.to_numeric(
                        raw["Volume"],
                        errors="coerce",
                    ),
            }
        )


        action_columns_present = (
            "Dividends" in raw.columns
            and "Stock Splits" in raw.columns
        )


        corporate_action_nulls = None
        invalid_split_rows = None


        if action_columns_present:

            dividends = pd.to_numeric(
                raw["Dividends"],
                errors="coerce",
            )

            splits = pd.to_numeric(
                raw["Stock Splits"],
                errors="coerce",
            )


            corporate_action_nulls = int(
                dividends.isna().sum()
                + splits.isna().sum()
            )


            # Yahoo represents "no split" as 0.
            # Positive values represent actual split
            # ratios. Negative split values are invalid.
            invalid_split_rows = int(
                (
                    splits < 0
                ).sum()
            )


        return {
            "raw": raw,
            "normalized": normalized,
            "missing_columns": [],
            "adjusted_available": True,
            "corporate_action_columns_present":
                action_columns_present,
            "corporate_action_nulls":
                corporate_action_nulls,
            "invalid_split_rows":
                invalid_split_rows,
        }


    # ==================================================
    # TIINGO
    # ==================================================

    elif source == "Tiingo":

        required_columns = {
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


        missing_columns = sorted(
            required_columns
            - set(raw.columns)
        )


        if missing_columns:

            return {
                "raw": raw,
                "normalized": None,
                "missing_columns": missing_columns,
                "adjusted_available": True,
                "corporate_action_columns_present": True,
                "corporate_action_nulls": None,
                "invalid_split_rows": None,
            }


        normalized = pd.DataFrame(
            {
                "date":
                    normalize_dates(
                        raw["date"]
                    ),

                "open":
                    pd.to_numeric(
                        raw["open"],
                        errors="coerce",
                    ),

                "high":
                    pd.to_numeric(
                        raw["high"],
                        errors="coerce",
                    ),

                "low":
                    pd.to_numeric(
                        raw["low"],
                        errors="coerce",
                    ),

                "close":
                    pd.to_numeric(
                        raw["close"],
                        errors="coerce",
                    ),

                "adj_close":
                    pd.to_numeric(
                        raw["adjClose"],
                        errors="coerce",
                    ),

                "volume":
                    pd.to_numeric(
                        raw["volume"],
                        errors="coerce",
                    ),
            }
        )


        div_cash = pd.to_numeric(
            raw["divCash"],
            errors="coerce",
        )

        split_factor = pd.to_numeric(
            raw["splitFactor"],
            errors="coerce",
        )


        corporate_action_nulls = int(
            div_cash.isna().sum()
            + split_factor.isna().sum()
        )


        # Tiingo represents no split with 1.0.
        # A split factor <= 0 is impossible.
        invalid_split_rows = int(
            (
                split_factor <= 0
            ).sum()
        )


        return {
            "raw": raw,
            "normalized": normalized,
            "missing_columns": [],
            "adjusted_available": True,
            "corporate_action_columns_present": True,
            "corporate_action_nulls":
                corporate_action_nulls,
            "invalid_split_rows":
                invalid_split_rows,
        }


    # ==================================================
    # INVESTING.COM — INFO_OLD
    # ==================================================

    elif source == "Investing.com":

        required_columns = {
            "Date",
            "Price",
            "Open",
            "High",
            "Low",
            "Vol.",
            "Change %",
        }


        missing_columns = sorted(
            required_columns
            - set(raw.columns)
        )


        if missing_columns:

            return {
                "raw": raw,
                "normalized": None,
                "missing_columns": missing_columns,
                "adjusted_available": False,
                "corporate_action_columns_present": False,
                "corporate_action_nulls": None,
                "invalid_split_rows": None,
            }


        normalized = pd.DataFrame(
            {
                "date":
                    normalize_dates(
                        raw["Date"]
                    ),

                "open":
                    raw["Open"]
                    .apply(
                        parse_investing_number
                    ),

                "high":
                    raw["High"]
                    .apply(
                        parse_investing_number
                    ),

                "low":
                    raw["Low"]
                    .apply(
                        parse_investing_number
                    ),

                "close":
                    raw["Price"]
                    .apply(
                        parse_investing_number
                    ),

                # Deliberately missing.
                #
                # INFO adjusted-price reconstruction
                # is a separate documented stage.
                "adj_close":
                    pd.NA,

                "volume":
                    raw["Vol."]
                    .apply(
                        parse_investing_volume
                    ),
            }
        )


        return {
            "raw": raw,
            "normalized": normalized,
            "missing_columns": [],
            "adjusted_available": False,
            "corporate_action_columns_present": False,
            "corporate_action_nulls": None,
            "invalid_split_rows": None,
        }


    else:

        raise ValueError(
            f"Unsupported source: {source}"
        )


# ==================================================
# ISSUE / GAP RECORDS
# ==================================================

issue_records = []
gap_records = []


def add_issue(
    security_key,
    project_ticker,
    provider_symbol,
    source,
    severity,
    issue_type,
    detail,
):

    issue_records.append(
        {
            "security_key":
                security_key,

            "project_ticker":
                project_ticker,

            "provider_symbol":
                provider_symbol,

            "source":
                source,

            "severity":
                severity,

            "issue_type":
                issue_type,

            "detail":
                detail,
        }
    )


def add_gap_dates(
    security_key,
    project_ticker,
    provider_symbol,
    source,
    gap_type,
    dates,
):

    for date in dates:

        gap_records.append(
            {
                "security_key":
                    security_key,

                "project_ticker":
                    project_ticker,

                "provider_symbol":
                    provider_symbol,

                "source":
                    source,

                "gap_type":
                    gap_type,

                "date":
                    date.date(),
            }
        )


# ==================================================
# LOAD DOWNLOAD AUDIT
# ==================================================

print_section(
    "RAW MARKET PRICE INTEGRITY AUDIT"
)


if not DOWNLOAD_AUDIT_FILE.exists():

    print(
        "\nERROR: The market-price download "
        "audit does not exist:"
    )

    print(
        DOWNLOAD_AUDIT_FILE
    )

    sys.exit(1)


download_audit = pd.read_csv(
    DOWNLOAD_AUDIT_FILE
)


download_audit = (
    download_audit
    .drop_duplicates(
        subset=[
            "security_key",
            "project_ticker",
        ],
        keep="last",
    )
    .reset_index(drop=True)
)


# ==================================================
# 1. ACQUISITION POPULATION VALIDATION
# ==================================================

print_section(
    "1. ACQUISITION POPULATION VALIDATION"
)


print(
    f"Current acquisition rows: "
    f"{len(download_audit)}"
)


if len(download_audit) != EXPECTED_REQUEST_COUNT:

    print(
        "\nERROR:"
    )

    print(
        f"Expected {EXPECTED_REQUEST_COUNT} "
        f"requests but found "
        f"{len(download_audit)}."
    )

    sys.exit(1)


successful_statuses = {
    "DOWNLOADED",
    "EXISTING",
    "MANUAL_PRESENT",
}


unfinished = download_audit[
    ~download_audit[
        "status"
    ].isin(
        successful_statuses
    )
]


if not unfinished.empty:

    print(
        "\nERROR: The acquisition audit "
        "contains unfinished requests."
    )

    print(
        unfinished[
            [
                "security_key",
                "project_ticker",
                "source",
                "status",
            ]
        ]
        .to_string(
            index=False
        )
    )

    sys.exit(1)


print(
    "PASS: All 596 requests are marked "
    "as acquired."
)


print(
    "\nSource distribution:"
)

print(
    download_audit[
        "source"
    ]
    .value_counts()
    .to_string()
)


# ==================================================
# 2. BUILD THE SPY TRADING CALENDAR
# ==================================================

print_section(
    "2. BUILD U.S. TRADING-DATE REFERENCE"
)


spy_rows = download_audit[
    download_audit[
        "security_key"
    ]
    == "SPY_ETF"
]


if len(spy_rows) != 1:

    print(
        "\nERROR: Expected exactly one "
        "SPY_ETF row."
    )

    print(
        f"Rows found: "
        f"{len(spy_rows)}"
    )

    sys.exit(1)


spy_row = spy_rows.iloc[0]


spy_file = (
    PROJECT_ROOT
    / str(
        spy_row[
            "output_file"
        ]
    )
)


if not spy_file.exists():

    print(
        "\nERROR: SPY raw file does "
        "not exist:"
    )

    print(
        spy_file
    )

    sys.exit(1)


spy_loaded = load_normalized_file(
    spy_file,
    "Yahoo Finance",
)


if spy_loaded[
    "missing_columns"
]:

    print(
        "\nERROR: SPY raw source does not "
        "contain the expected price schema."
    )

    print(
        spy_loaded[
            "missing_columns"
        ]
    )

    sys.exit(1)


spy_data = spy_loaded[
    "normalized"
]


spy_dates = (
    spy_data[
        "date"
    ]
    .dropna()
    .drop_duplicates()
    .sort_values()
    .reset_index(drop=True)
)


if spy_dates.empty:

    print(
        "\nERROR: SPY trading calendar "
        "is empty."
    )

    sys.exit(1)


print(
    f"SPY reference sessions: "
    f"{len(spy_dates)}"
)

print(
    f"First SPY date: "
    f"{spy_dates.min().date()}"
)

print(
    f"Last SPY date: "
    f"{spy_dates.max().date()}"
)

print(
    "\nPASS: SPY trading sessions will "
    "be used as the local U.S. market "
    "calendar reference."
)


# ==================================================
# 3. AUDIT EVERY RAW PRICE FILE
# ==================================================

print_section(
    "3. AUDIT ALL 596 RAW PRICE REQUESTS"
)


audit_results = []

total_requests = len(
    download_audit
)


for request_number, (_, row) in enumerate(
    download_audit.iterrows(),
    start=1,
):

    security_key = str(
        row[
            "security_key"
        ]
    )

    project_ticker = str(
        row[
            "project_ticker"
        ]
    )

    provider_symbol = str(
        row[
            "provider_symbol"
        ]
    )

    source = str(
        row[
            "source"
        ]
    )


    requested_start = pd.Timestamp(
        row[
            "download_start"
        ]
    ).normalize()


    requested_end_exclusive = pd.Timestamp(
        row[
            "download_end_exclusive"
        ]
    ).normalize()


    expected_rows = int(
        row[
            "rows_returned"
        ]
    )


    expected_first = pd.to_datetime(
        row[
            "first_returned_date"
        ],
        errors="coerce",
    )


    expected_last = pd.to_datetime(
        row[
            "last_returned_date"
        ],
        errors="coerce",
    )


    file_path = (
        PROJECT_ROOT
        / str(
            row[
                "output_file"
            ]
        )
    )


    critical_issues = 0
    blocking_reviews = 0
    review_issues = 0
    flags = []


    # Default values so every request produces
    # one complete audit row.
    actual_rows = 0

    first_date = None
    last_date = None

    duplicate_dates = None
    invalid_dates = None

    required_null_values = None
    adjusted_close_nulls = None
    nonpositive_adjusted_rows = None

    nonpositive_price_rows = None
    negative_volume_rows = None

    invalid_high_rows = None
    invalid_low_rows = None

    outside_requested_range = None

    start_missing_sessions = None
    end_missing_sessions = None
    internal_missing_sessions = None
    extra_non_spy_dates = None

    corporate_action_nulls = None
    invalid_split_rows = None


    # ==================================================
    # FILE EXISTENCE
    # ==================================================

    if not file_path.exists():

        critical_issues += 1

        flags.append(
            "FILE_MISSING"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "FILE_MISSING",
            str(file_path),
        )


        audit_results.append(
            {
                "security_key":
                    security_key,

                "project_ticker":
                    project_ticker,

                "provider_symbol":
                    provider_symbol,

                "source":
                    source,

                "status":
                    "FAIL",

                "requested_start":
                    requested_start.date(),

                "requested_end_exclusive":
                    requested_end_exclusive.date(),

                "rows":
                    actual_rows,

                "expected_rows":
                    expected_rows,

                "first_date":
                    first_date,

                "last_date":
                    last_date,

                "duplicate_dates":
                    duplicate_dates,

                "invalid_dates":
                    invalid_dates,

                "required_null_values":
                    required_null_values,

                "adjusted_close_nulls":
                    adjusted_close_nulls,

                "nonpositive_adjusted_rows":
                    nonpositive_adjusted_rows,

                "nonpositive_price_rows":
                    nonpositive_price_rows,

                "negative_volume_rows":
                    negative_volume_rows,

                "invalid_high_rows":
                    invalid_high_rows,

                "invalid_low_rows":
                    invalid_low_rows,

                "outside_requested_range":
                    outside_requested_range,

                "start_missing_sessions":
                    start_missing_sessions,

                "end_missing_sessions":
                    end_missing_sessions,

                "internal_missing_sessions":
                    internal_missing_sessions,

                "extra_non_spy_dates":
                    extra_non_spy_dates,

                "corporate_action_nulls":
                    corporate_action_nulls,

                "invalid_split_rows":
                    invalid_split_rows,

                "critical_issues":
                    critical_issues,

                "blocking_reviews":
                    blocking_reviews,

                "review_issues":
                    review_issues,

                "flags":
                    "|".join(flags),

                "output_file":
                    str(file_path),
            }
        )

        continue


    # ==================================================
    # FILE READ / PROVIDER SCHEMA
    # ==================================================

    try:

        loaded = load_normalized_file(
            file_path,
            source,
        )


    except Exception as error:

        critical_issues += 1

        flags.append(
            "FILE_READ_FAILURE"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "FILE_READ_FAILURE",
            str(error),
        )


        audit_results.append(
            {
                "security_key":
                    security_key,

                "project_ticker":
                    project_ticker,

                "provider_symbol":
                    provider_symbol,

                "source":
                    source,

                "status":
                    "FAIL",

                "requested_start":
                    requested_start.date(),

                "requested_end_exclusive":
                    requested_end_exclusive.date(),

                "rows":
                    actual_rows,

                "expected_rows":
                    expected_rows,

                "first_date":
                    first_date,

                "last_date":
                    last_date,

                "duplicate_dates":
                    duplicate_dates,

                "invalid_dates":
                    invalid_dates,

                "required_null_values":
                    required_null_values,

                "adjusted_close_nulls":
                    adjusted_close_nulls,

                "nonpositive_adjusted_rows":
                    nonpositive_adjusted_rows,

                "nonpositive_price_rows":
                    nonpositive_price_rows,

                "negative_volume_rows":
                    negative_volume_rows,

                "invalid_high_rows":
                    invalid_high_rows,

                "invalid_low_rows":
                    invalid_low_rows,

                "outside_requested_range":
                    outside_requested_range,

                "start_missing_sessions":
                    start_missing_sessions,

                "end_missing_sessions":
                    end_missing_sessions,

                "internal_missing_sessions":
                    internal_missing_sessions,

                "extra_non_spy_dates":
                    extra_non_spy_dates,

                "corporate_action_nulls":
                    corporate_action_nulls,

                "invalid_split_rows":
                    invalid_split_rows,

                "critical_issues":
                    critical_issues,

                "blocking_reviews":
                    blocking_reviews,

                "review_issues":
                    review_issues,

                "flags":
                    "|".join(flags),

                "output_file":
                    str(file_path),
            }
        )

        continue


    raw = loaded[
        "raw"
    ]

    data = loaded[
        "normalized"
    ]

    missing_columns = loaded[
        "missing_columns"
    ]

    adjusted_available = loaded[
        "adjusted_available"
    ]

    action_columns_present = loaded[
        "corporate_action_columns_present"
    ]

    corporate_action_nulls = loaded[
        "corporate_action_nulls"
    ]

    invalid_split_rows = loaded[
        "invalid_split_rows"
    ]


    actual_rows = len(
        raw
    )


    # ==================================================
    # REQUIRED PROVIDER COLUMNS
    # ==================================================

    if missing_columns:

        critical_issues += 1

        flags.append(
            "MISSING_COLUMNS"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "MISSING_COLUMNS",
            "|".join(
                missing_columns
            ),
        )


        audit_results.append(
            {
                "security_key":
                    security_key,

                "project_ticker":
                    project_ticker,

                "provider_symbol":
                    provider_symbol,

                "source":
                    source,

                "status":
                    "FAIL",

                "requested_start":
                    requested_start.date(),

                "requested_end_exclusive":
                    requested_end_exclusive.date(),

                "rows":
                    actual_rows,

                "expected_rows":
                    expected_rows,

                "first_date":
                    first_date,

                "last_date":
                    last_date,

                "duplicate_dates":
                    duplicate_dates,

                "invalid_dates":
                    invalid_dates,

                "required_null_values":
                    required_null_values,

                "adjusted_close_nulls":
                    adjusted_close_nulls,

                "nonpositive_adjusted_rows":
                    nonpositive_adjusted_rows,

                "nonpositive_price_rows":
                    nonpositive_price_rows,

                "negative_volume_rows":
                    negative_volume_rows,

                "invalid_high_rows":
                    invalid_high_rows,

                "invalid_low_rows":
                    invalid_low_rows,

                "outside_requested_range":
                    outside_requested_range,

                "start_missing_sessions":
                    start_missing_sessions,

                "end_missing_sessions":
                    end_missing_sessions,

                "internal_missing_sessions":
                    internal_missing_sessions,

                "extra_non_spy_dates":
                    extra_non_spy_dates,

                "corporate_action_nulls":
                    corporate_action_nulls,

                "invalid_split_rows":
                    invalid_split_rows,

                "critical_issues":
                    critical_issues,

                "blocking_reviews":
                    blocking_reviews,

                "review_issues":
                    review_issues,

                "flags":
                    "|".join(flags),

                "output_file":
                    str(
                        file_path.relative_to(
                            PROJECT_ROOT
                        )
                    ),
            }
        )

        continue


    # ==================================================
    # ROW COUNT RECONCILIATION
    # ==================================================

    if actual_rows != expected_rows:

        critical_issues += 1

        flags.append(
            "ROW_COUNT_MISMATCH"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "ROW_COUNT_MISMATCH",
            (
                f"Download audit recorded "
                f"{expected_rows} rows; "
                f"raw file currently contains "
                f"{actual_rows} rows."
            ),
        )


    # ==================================================
    # DATE INTEGRITY
    # ==================================================

    invalid_dates = int(
        data[
            "date"
        ]
        .isna()
        .sum()
    )


    if invalid_dates > 0:

        critical_issues += 1

        flags.append(
            "INVALID_DATES"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "INVALID_DATES",
            str(
                invalid_dates
            ),
        )


    valid_dates = (
        data[
            "date"
        ]
        .dropna()
    )


    if valid_dates.empty:

        critical_issues += 1

        flags.append(
            "NO_VALID_DATES"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "NO_VALID_DATES",
            "No valid date observations remain.",
        )


    else:

        first_date = (
            valid_dates.min()
        )

        last_date = (
            valid_dates.max()
        )


    duplicate_dates = int(
        valid_dates
        .duplicated()
        .sum()
    )


    if duplicate_dates > 0:

        critical_issues += 1

        flags.append(
            "DUPLICATE_DATES"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "DUPLICATE_DATES",
            str(
                duplicate_dates
            ),
        )


    # ==================================================
    # RECONCILE FIRST/LAST DATES WITH DOWNLOAD AUDIT
    # ==================================================

    if (
        first_date is not None
        and pd.notna(expected_first)
        and first_date.normalize()
        != expected_first.normalize()
    ):

        critical_issues += 1

        flags.append(
            "FIRST_DATE_MISMATCH"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "FIRST_DATE_MISMATCH",
            (
                f"Download audit: "
                f"{expected_first.date()}; "
                f"raw file: "
                f"{first_date.date()}."
            ),
        )


    if (
        last_date is not None
        and pd.notna(expected_last)
        and last_date.normalize()
        != expected_last.normalize()
    ):

        critical_issues += 1

        flags.append(
            "LAST_DATE_MISMATCH"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "LAST_DATE_MISMATCH",
            (
                f"Download audit: "
                f"{expected_last.date()}; "
                f"raw file: "
                f"{last_date.date()}."
            ),
        )


    # ==================================================
    # REQUIRED OHLCV VALUES
    # ==================================================

    required_numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


    required_null_values = int(
        data[
            required_numeric_columns
        ]
        .isna()
        .sum()
        .sum()
    )


    if required_null_values > 0:

        critical_issues += 1

        flags.append(
            "REQUIRED_VALUE_NULLS"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "REQUIRED_VALUE_NULLS",
            str(
                required_null_values
            ),
        )


    # ==================================================
    # ADJUSTED CLOSE
    # ==================================================

    if adjusted_available:

        adjusted_close_numeric = pd.to_numeric(
            data[
                "adj_close"
            ],
            errors="coerce",
        )


        adjusted_close_nulls = int(
            adjusted_close_numeric
            .isna()
            .sum()
        )


        nonpositive_adjusted_rows = int(
            (
                adjusted_close_numeric
                <= 0
            ).sum()
        )


        if adjusted_close_nulls > 0:

            critical_issues += 1

            flags.append(
                "ADJUSTED_CLOSE_NULLS"
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "CRITICAL",
                "ADJUSTED_CLOSE_NULLS",
                str(
                    adjusted_close_nulls
                ),
            )


        if nonpositive_adjusted_rows > 0:

            critical_issues += 1

            flags.append(
                "NONPOSITIVE_ADJUSTED_CLOSE"
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "CRITICAL",
                "NONPOSITIVE_ADJUSTED_CLOSE",
                str(
                    nonpositive_adjusted_rows
                ),
            )


    else:

        adjusted_close_nulls = None
        nonpositive_adjusted_rows = None

        review_issues += 1

        flags.append(
            "ADJUSTED_PRICE_RECONSTRUCTION_PENDING"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "REVIEW",
            "ADJUSTED_PRICE_RECONSTRUCTION_PENDING",
            (
                "Historical INFO_OLD contains "
                "validated raw OHLCV but does not "
                "yet contain a reconstructed "
                "dividend-adjusted price series."
            ),
        )


    # ==================================================
    # RAW PRICE POSITIVITY
    # ==================================================

    price_columns = [
        "open",
        "high",
        "low",
        "close",
    ]


    nonpositive_price_rows = int(
        data[
            price_columns
        ]
        .le(0)
        .any(
            axis=1
        )
        .sum()
    )


    if nonpositive_price_rows > 0:

        critical_issues += 1

        flags.append(
            "NONPOSITIVE_RAW_PRICE"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "NONPOSITIVE_RAW_PRICE",
            str(
                nonpositive_price_rows
            ),
        )


    # ==================================================
    # VOLUME
    # ==================================================

    negative_volume_rows = int(
        (
            data[
                "volume"
            ]
            < 0
        ).sum()
    )


    if negative_volume_rows > 0:

        critical_issues += 1

        flags.append(
            "NEGATIVE_VOLUME"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "NEGATIVE_VOLUME",
            str(
                negative_volume_rows
            ),
        )


    # ==================================================
    # OHLC LOGICAL RELATIONSHIPS
    # ==================================================

    row_max = data[
        [
            "open",
            "low",
            "close",
        ]
    ].max(
        axis=1
    )


    row_min = data[
        [
            "open",
            "high",
            "close",
        ]
    ].min(
        axis=1
    )


    invalid_high_rows = int(
        (
            data[
                "high"
            ]
            < row_max
        ).sum()
    )


    invalid_low_rows = int(
        (
            data[
                "low"
            ]
            > row_min
        ).sum()
    )


    if invalid_high_rows > 0:

        critical_issues += 1

        flags.append(
            "INVALID_HIGH"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "INVALID_HIGH",
            str(
                invalid_high_rows
            ),
        )


    if invalid_low_rows > 0:

        critical_issues += 1

        flags.append(
            "INVALID_LOW"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "INVALID_LOW",
            str(
                invalid_low_rows
            ),
        )


    # ==================================================
    # CORPORATE ACTION FIELDS
    # ==================================================

    if source == "Yahoo Finance":

        if not action_columns_present:

            review_issues += 1

            flags.append(
                "YAHOO_ACTION_COLUMNS_MISSING"
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "REVIEW",
                "YAHOO_ACTION_COLUMNS_MISSING",
                (
                    "Dividends and/or Stock Splits "
                    "were not present in the Yahoo "
                    "raw file."
                ),
            )


        elif (
            corporate_action_nulls is not None
            and corporate_action_nulls > 0
        ):

            review_issues += 1

            flags.append(
                "YAHOO_ACTION_NULLS"
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "REVIEW",
                "YAHOO_ACTION_NULLS",
                str(
                    corporate_action_nulls
                ),
            )


        if (
            invalid_split_rows is not None
            and invalid_split_rows > 0
        ):

            critical_issues += 1

            flags.append(
                "INVALID_SPLIT_FACTOR"
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "CRITICAL",
                "INVALID_SPLIT_FACTOR",
                str(
                    invalid_split_rows
                ),
            )


    elif source == "Tiingo":

        if (
            corporate_action_nulls is not None
            and corporate_action_nulls > 0
        ):

            critical_issues += 1

            flags.append(
                "TIINGO_ACTION_NULLS"
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "CRITICAL",
                "TIINGO_ACTION_NULLS",
                str(
                    corporate_action_nulls
                ),
            )


        if (
            invalid_split_rows is not None
            and invalid_split_rows > 0
        ):

            critical_issues += 1

            flags.append(
                "INVALID_SPLIT_FACTOR"
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "CRITICAL",
                "INVALID_SPLIT_FACTOR",
                str(
                    invalid_split_rows
                ),
            )


    # ==================================================
    # REQUESTED RANGE
    # ==================================================

    outside_requested_range = int(
        (
            (
                data[
                    "date"
                ]
                < requested_start
            )
            |
            (
                data[
                    "date"
                ]
                >= requested_end_exclusive
            )
        )
        .sum()
    )


    if outside_requested_range > 0:

        critical_issues += 1

        flags.append(
            "OUTSIDE_REQUESTED_RANGE"
        )


        add_issue(
            security_key,
            project_ticker,
            provider_symbol,
            source,
            "CRITICAL",
            "OUTSIDE_REQUESTED_RANGE",
            str(
                outside_requested_range
            ),
        )


    # ==================================================
    # TRADING CALENDAR / COVERAGE
    # ==================================================

    if (
        first_date is not None
        and last_date is not None
    ):

        request_calendar = spy_dates[
            (
                spy_dates
                >= requested_start
            )
            &
            (
                spy_dates
                < requested_end_exclusive
            )
        ]


        observed_dates = (
            data[
                "date"
            ]
            .dropna()
            .drop_duplicates()
            .sort_values()
        )


        # ----------------------------------------------
        # Missing sessions BEFORE first observation
        # ----------------------------------------------

        start_missing = request_calendar[
            request_calendar
            < first_date
        ]


        start_missing_sessions = len(
            start_missing
        )


        if start_missing_sessions > 0:

            add_gap_dates(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "START_BOUNDARY_MISSING",
                start_missing,
            )


        if (
            start_missing_sessions
            > START_BLOCKING_SESSIONS
        ):

            blocking_reviews += 1

            flags.append(
                (
                    "MAJOR_START_GAP:"
                    f"{start_missing_sessions}"
                )
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "BLOCKING_REVIEW",
                "MAJOR_START_COVERAGE_GAP",
                (
                    f"{start_missing_sessions} SPY "
                    f"trading sessions occur between "
                    f"requested start "
                    f"{requested_start.date()} and "
                    f"first returned observation "
                    f"{first_date.date()}."
                ),
            )


        elif (
            start_missing_sessions
            > START_REVIEW_SESSIONS
        ):

            review_issues += 1

            flags.append(
                (
                    "START_GAP:"
                    f"{start_missing_sessions}"
                )
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "REVIEW",
                "START_COVERAGE_GAP",
                (
                    f"{start_missing_sessions} SPY "
                    f"trading sessions occur before "
                    f"the first returned observation."
                ),
            )


        # ----------------------------------------------
        # Missing sessions AFTER last observation
        # ----------------------------------------------

        end_missing = request_calendar[
            request_calendar
            > last_date
        ]


        end_missing_sessions = len(
            end_missing
        )


        if end_missing_sessions > 0:

            add_gap_dates(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "END_BOUNDARY_MISSING",
                end_missing,
            )


        if (
            end_missing_sessions
            > END_BLOCKING_SESSIONS
        ):

            blocking_reviews += 1

            flags.append(
                (
                    "MAJOR_END_GAP:"
                    f"{end_missing_sessions}"
                )
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "BLOCKING_REVIEW",
                "MAJOR_END_COVERAGE_GAP",
                (
                    f"{end_missing_sessions} SPY "
                    f"trading sessions occur after "
                    f"the final returned observation "
                    f"{last_date.date()} and before "
                    f"requested end "
                    f"{requested_end_exclusive.date()}."
                ),
            )


        elif (
            end_missing_sessions
            > END_REVIEW_SESSIONS
        ):

            review_issues += 1

            flags.append(
                (
                    "END_GAP:"
                    f"{end_missing_sessions}"
                )
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "REVIEW",
                "END_COVERAGE_GAP",
                (
                    f"{end_missing_sessions} SPY "
                    f"trading sessions occur after "
                    f"the final returned observation."
                ),
            )


        # ----------------------------------------------
        # Missing INTERNAL market sessions
        # ----------------------------------------------

        internal_calendar = request_calendar[
            (
                request_calendar
                >= first_date
            )
            &
            (
                request_calendar
                <= last_date
            )
        ]


        internal_missing = internal_calendar[
            ~internal_calendar.isin(
                observed_dates
            )
        ]


        internal_missing_sessions = len(
            internal_missing
        )


        if internal_missing_sessions > 0:

            add_gap_dates(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "INTERNAL_MISSING",
                internal_missing,
            )


        if (
            internal_missing_sessions
            > INTERNAL_BLOCKING_SESSIONS
        ):

            blocking_reviews += 1

            flags.append(
                (
                    "MAJOR_INTERNAL_GAPS:"
                    f"{internal_missing_sessions}"
                )
            )


            preview = ", ".join(
                str(date.date())
                for date
                in internal_missing[:10]
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "BLOCKING_REVIEW",
                "MAJOR_INTERNAL_TRADING_GAPS",
                (
                    f"{internal_missing_sessions} "
                    f"SPY trading sessions are "
                    f"missing internally. "
                    f"Examples: {preview}"
                ),
            )


        elif (
            internal_missing_sessions
            >= INTERNAL_REVIEW_SESSIONS
        ):

            review_issues += 1

            flags.append(
                (
                    "INTERNAL_GAPS:"
                    f"{internal_missing_sessions}"
                )
            )


            preview = ", ".join(
                str(date.date())
                for date
                in internal_missing[:10]
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "REVIEW",
                "INTERNAL_TRADING_GAPS",
                (
                    f"{internal_missing_sessions} "
                    f"SPY trading session(s) are "
                    f"missing internally. "
                    f"Examples: {preview}"
                ),
            )


        # ----------------------------------------------
        # Dates that SPY did NOT trade
        # ----------------------------------------------

        extra_dates = observed_dates[
            ~observed_dates.isin(
                spy_dates
            )
        ]


        extra_non_spy_dates = len(
            extra_dates
        )


        if extra_non_spy_dates > 0:

            add_gap_dates(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "EXTRA_NON_SPY_DATE",
                extra_dates,
            )


        if (
            extra_non_spy_dates
            > EXTRA_DATE_BLOCKING_COUNT
        ):

            blocking_reviews += 1

            flags.append(
                (
                    "MAJOR_EXTRA_DATES:"
                    f"{extra_non_spy_dates}"
                )
            )


            preview = ", ".join(
                str(date.date())
                for date
                in extra_dates[:10]
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "BLOCKING_REVIEW",
                "MAJOR_EXTRA_NON_SPY_DATES",
                (
                    f"{extra_non_spy_dates} "
                    f"observations occur on dates "
                    f"outside the SPY U.S. trading "
                    f"calendar. Examples: {preview}"
                ),
            )


        elif extra_non_spy_dates > 0:

            review_issues += 1

            flags.append(
                (
                    "EXTRA_NON_SPY_DATES:"
                    f"{extra_non_spy_dates}"
                )
            )


            preview = ", ".join(
                str(date.date())
                for date
                in extra_dates[:10]
            )


            add_issue(
                security_key,
                project_ticker,
                provider_symbol,
                source,
                "REVIEW",
                "EXTRA_NON_SPY_DATES",
                (
                    f"{extra_non_spy_dates} "
                    f"observation(s) occur outside "
                    f"the SPY calendar. "
                    f"Examples: {preview}"
                ),
            )


    # ==================================================
    # FINAL REQUEST STATUS
    # ==================================================

    if critical_issues > 0:

        request_status = "FAIL"

    elif blocking_reviews > 0:

        request_status = "REVIEW_BLOCKING"

    elif review_issues > 0:

        request_status = "REVIEW"

    else:

        request_status = "PASS"


    audit_results.append(
        {
            "security_key":
                security_key,

            "project_ticker":
                project_ticker,

            "provider_symbol":
                provider_symbol,

            "source":
                source,

            "status":
                request_status,

            "requested_start":
                requested_start.date(),

            "requested_end_exclusive":
                requested_end_exclusive.date(),

            "rows":
                actual_rows,

            "expected_rows":
                expected_rows,

            "first_date":
                (
                    first_date.date()
                    if first_date
                    is not None
                    else None
                ),

            "last_date":
                (
                    last_date.date()
                    if last_date
                    is not None
                    else None
                ),

            "duplicate_dates":
                duplicate_dates,

            "invalid_dates":
                invalid_dates,

            "required_null_values":
                required_null_values,

            "adjusted_close_nulls":
                adjusted_close_nulls,

            "nonpositive_adjusted_rows":
                nonpositive_adjusted_rows,

            "nonpositive_price_rows":
                nonpositive_price_rows,

            "negative_volume_rows":
                negative_volume_rows,

            "invalid_high_rows":
                invalid_high_rows,

            "invalid_low_rows":
                invalid_low_rows,

            "outside_requested_range":
                outside_requested_range,

            "start_missing_sessions":
                start_missing_sessions,

            "end_missing_sessions":
                end_missing_sessions,

            "internal_missing_sessions":
                internal_missing_sessions,

            "extra_non_spy_dates":
                extra_non_spy_dates,

            "corporate_action_nulls":
                corporate_action_nulls,

            "invalid_split_rows":
                invalid_split_rows,

            "critical_issues":
                critical_issues,

            "blocking_reviews":
                blocking_reviews,

            "review_issues":
                review_issues,

            "flags":
                "|".join(
                    flags
                ),

            "output_file":
                str(
                    file_path.relative_to(
                        PROJECT_ROOT
                    )
                ),
        }
    )


    if (
        request_number % 50 == 0
        or request_status == "FAIL"
        or request_status == "REVIEW_BLOCKING"
        or request_number == total_requests
    ):

        print(
            f"[{request_number}/{total_requests}] "
            f"{project_ticker}: "
            f"{request_status}"
        )


# ==================================================
# 4. SAVE OUTPUTS
# ==================================================

print_section(
    "4. SAVE INTEGRITY AUDIT"
)


integrity = pd.DataFrame(
    audit_results
)


if len(integrity) != EXPECTED_REQUEST_COUNT:

    print(
        "\nERROR: Integrity audit did not "
        "produce exactly 596 rows."
    )

    print(
        f"Rows produced: "
        f"{len(integrity)}"
    )

    sys.exit(1)


status_order = {
    "FAIL": 0,
    "REVIEW_BLOCKING": 1,
    "REVIEW": 2,
    "PASS": 3,
}


integrity[
    "_status_order"
] = integrity[
    "status"
].map(
    status_order
)


integrity = (
    integrity
    .sort_values(
        [
            "_status_order",
            "source",
            "security_key",
            "project_ticker",
        ]
    )
    .drop(
        columns=[
            "_status_order"
        ]
    )
    .reset_index(drop=True)
)


integrity.to_csv(
    INTEGRITY_OUTPUT,
    index=False,
)


print(
    f"Integrity audit saved:\n"
    f"{INTEGRITY_OUTPUT}"
)


# --------------------------------------------------
# Issue table
# --------------------------------------------------

issues = pd.DataFrame(
    issue_records
)


if issues.empty:

    if ISSUES_OUTPUT.exists():

        ISSUES_OUTPUT.unlink()


    print(
        "\nNo integrity issue table "
        "was required."
    )


else:

    severity_order = {
        "CRITICAL": 0,
        "BLOCKING_REVIEW": 1,
        "REVIEW": 2,
    }


    issues[
        "_severity_order"
    ] = issues[
        "severity"
    ].map(
        severity_order
    )


    issues = (
        issues
        .sort_values(
            [
                "_severity_order",
                "source",
                "security_key",
                "project_ticker",
                "issue_type",
            ]
        )
        .drop(
            columns=[
                "_severity_order"
            ]
        )
        .reset_index(drop=True)
    )


    issues.to_csv(
        ISSUES_OUTPUT,
        index=False,
    )


    print(
        f"\nIssue table saved:\n"
        f"{ISSUES_OUTPUT}"
    )


# --------------------------------------------------
# Full date-gap detail table
# --------------------------------------------------

gaps = pd.DataFrame(
    gap_records
)


if gaps.empty:

    if GAPS_OUTPUT.exists():

        GAPS_OUTPUT.unlink()


    print(
        "\nNo trading-calendar gap table "
        "was required."
    )


else:

    gaps = (
        gaps
        .sort_values(
            [
                "source",
                "security_key",
                "project_ticker",
                "gap_type",
                "date",
            ]
        )
        .reset_index(drop=True)
    )


    gaps.to_csv(
        GAPS_OUTPUT,
        index=False,
    )


    print(
        f"\nTrading-calendar gap detail saved:\n"
        f"{GAPS_OUTPUT}"
    )


# ==================================================
# 5. INTEGRITY SUMMARY
# ==================================================

print_section(
    "5. INTEGRITY SUMMARY"
)


critical_failures = integrity[
    integrity[
        "status"
    ]
    == "FAIL"
]


blocking_requests = integrity[
    integrity[
        "status"
    ]
    == "REVIEW_BLOCKING"
]


review_requests = integrity[
    integrity[
        "status"
    ]
    == "REVIEW"
]


clean_requests = integrity[
    integrity[
        "status"
    ]
    == "PASS"
]


critical_pass_count = (
    len(integrity)
    - len(critical_failures)
)


print(
    f"Total requests audited: "
    f"{len(integrity)}"
)

print(
    f"Critical integrity PASS: "
    f"{critical_pass_count}"
)

print(
    f"Critical integrity FAIL: "
    f"{len(critical_failures)}"
)

print(
    f"Blocking coverage review: "
    f"{len(blocking_requests)}"
)

print(
    f"Non-blocking review: "
    f"{len(review_requests)}"
)

print(
    f"Completely clean: "
    f"{len(clean_requests)}"
)


print(
    "\nStatus by source:"
)

print(
    pd.crosstab(
        integrity[
            "source"
        ],
        integrity[
            "status"
        ],
    )
    .to_string()
)


# ==================================================
# 6. CRITICAL FAILURES
# ==================================================

print_section(
    "6. CRITICAL FAILURES"
)


if critical_failures.empty:

    print(
        "None."
    )


else:

    print(
        critical_failures[
            [
                "security_key",
                "project_ticker",
                "provider_symbol",
                "source",
                "critical_issues",
                "flags",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ==================================================
# 7. BLOCKING COVERAGE REVIEWS
# ==================================================

print_section(
    "7. BLOCKING COVERAGE REVIEWS"
)


if blocking_requests.empty:

    print(
        "None."
    )


else:

    print(
        blocking_requests[
            [
                "security_key",
                "project_ticker",
                "provider_symbol",
                "source",
                "rows",
                "first_date",
                "last_date",
                "start_missing_sessions",
                "end_missing_sessions",
                "internal_missing_sessions",
                "extra_non_spy_dates",
                "flags",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ==================================================
# 8. ISSUE TYPE SUMMARY
# ==================================================

print_section(
    "8. ISSUE TYPE SUMMARY"
)


if issues.empty:

    print(
        "None."
    )


else:

    issue_summary = (
        issues
        .groupby(
            [
                "severity",
                "issue_type",
            ]
        )
        .size()
        .reset_index(
            name="requests"
        )
        .sort_values(
            [
                "severity",
                "requests",
            ],
            ascending=[
                True,
                False,
            ],
        )
    )


    print(
        issue_summary
        .to_string(
            index=False
        )
    )


# ==================================================
# 9. SPECIAL INFO STATUS
# ==================================================

print_section(
    "9. HISTORICAL INFO STATUS"
)


info_result = integrity[
    (
        integrity[
            "security_key"
        ]
        == "INFO"
    )
    &
    (
        integrity[
            "project_ticker"
        ]
        == "INFO"
    )
]


if len(info_result) != 1:

    print(
        "ERROR: Expected exactly one "
        "historical INFO request."
    )


else:

    print(
        info_result[
            [
                "security_key",
                "project_ticker",
                "provider_symbol",
                "source",
                "status",
                "rows",
                "first_date",
                "last_date",
                "flags",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ==================================================
# 10. AUDIT RESULT
# ==================================================

print_section(
    "10. AUDIT RESULT"
)


if not critical_failures.empty:

    print(
        "RAW MARKET PRICE INTEGRITY AUDIT "
        "FAILED."
    )

    print(
        f"\n{len(critical_failures)} request(s) "
        "contain critical structural or "
        "data-integrity problems."
    )

    print(
        "\nDO NOT STANDARDIZE OR CALCULATE "
        "RETURNS."
    )

    print(
        "\nResolve critical failures first."
    )

    sys.exit(2)


elif not blocking_requests.empty:

    print(
        "RAW MARKET PRICE STRUCTURAL "
        "INTEGRITY PASSED."
    )

    print(
        f"\nHowever, "
        f"{len(blocking_requests)} request(s) "
        "require blocking coverage review."
    )

    print(
        "\nDO NOT STANDARDIZE YET."
    )

    print(
        "\nThese series may represent legitimate "
        "IPO/delisting boundaries, or they may "
        "represent incomplete provider history."
    )

    print(
        "\nEach blocking coverage case must be "
        "resolved or explicitly documented first."
    )


else:

    print(
        "RAW MARKET PRICE INTEGRITY AUDIT "
        "PASSED."
    )


    if not review_requests.empty:

        print(
            f"\n{len(review_requests)} request(s) "
            "contain non-blocking review items."
        )

        print(
            "These must be documented during "
            "standardization."
        )


    print(
        "\nNo blocking raw-data integrity "
        "problems remain."
    )