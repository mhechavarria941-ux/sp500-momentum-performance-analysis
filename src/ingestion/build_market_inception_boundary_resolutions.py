from pathlib import Path
import sys

import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INCEPTION_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "securities"
    / "security_market_inceptions.csv"
)

BOUNDARY_VERIFICATION_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_inception_boundary_verification.csv"
)

VLTO_SEARCH_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "vlto_when_issued_search_audit.csv"
)

DOWNLOAD_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_download_audit.csv"
)

RAW_EXCEPTION_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "source"
    / "prices"
    / "tiingo_exceptions"
)

VLTO_WHEN_ISSUED_FILE = (
    RAW_EXCEPTION_DIR
    / "VLTO__when_issued_probe__VLTO-W.csv"
)

VLTO_REGULAR_BOUNDARY_FILE = (
    RAW_EXCEPTION_DIR
    / "VLTO__inception_boundary__tiingo.csv"
)

RESOLUTION_REFERENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "market_inception_boundary_resolutions.csv"
)

VLTO_COMPOSITE_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "vlto_market_boundary_composite.csv"
)


# ============================================================
# EXPECTED RESOLUTION CASES
# ============================================================

EXPECTED_CASES = {
    "CARR",
    "OTIS",
    "GEHC",
    "VLTO",
}


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
    150,
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


def validate_ohlc(data):

    invalid_high = int(
        (
            data["high"]
            <
            data[
                [
                    "open",
                    "low",
                    "close",
                ]
            ]
            .max(
                axis=1
            )
        )
        .sum()
    )


    invalid_low = int(
        (
            data["low"]
            >
            data[
                [
                    "open",
                    "high",
                    "close",
                ]
            ]
            .min(
                axis=1
            )
        )
        .sum()
    )


    return (
        invalid_high,
        invalid_low,
    )


def load_yahoo_common(file_path):

    raw = pd.read_csv(
        file_path
    )


    required_columns = {
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
    }


    missing = (
        required_columns
        - set(raw.columns)
    )


    if missing:

        raise RuntimeError(
            "Yahoo file is missing columns: "
            f"{sorted(missing)}"
        )


    dates = normalize_dates(
        raw["Date"]
    )


    dividends = (
        pd.to_numeric(
            raw["Dividends"],
            errors="coerce",
        )
        if "Dividends"
        in raw.columns
        else pd.Series(
            0.0,
            index=raw.index,
        )
    )


    yahoo_splits = (
        pd.to_numeric(
            raw["Stock Splits"],
            errors="coerce",
        )
        if "Stock Splits"
        in raw.columns
        else pd.Series(
            0.0,
            index=raw.index,
        )
    )


    # Yahoo uses 0 when no split occurred.
    split_factor = (
        yahoo_splits
        .where(
            yahoo_splits != 0,
            1.0,
        )
    )


    common = pd.DataFrame(
        {
            "date":
                dates,

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

            "dividend":
                dividends,

            "split_factor":
                split_factor,

            "source_component":
                "Yahoo Finance",

            "provider_symbol":
                "VLTO",
        }
    )


    return common


def load_tiingo_common(
    file_path,
    source_component,
    provider_symbol,
):

    raw = pd.read_csv(
        file_path
    )


    required_columns = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjClose",
        "divCash",
        "splitFactor",
    }


    missing = (
        required_columns
        - set(raw.columns)
    )


    if missing:

        raise RuntimeError(
            f"{file_path.name} missing "
            f"columns: {sorted(missing)}"
        )


    common = pd.DataFrame(
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

            "dividend":
                pd.to_numeric(
                    raw["divCash"],
                    errors="coerce",
                ),

            "split_factor":
                pd.to_numeric(
                    raw["splitFactor"],
                    errors="coerce",
                ),

            "source_component":
                source_component,

            "provider_symbol":
                provider_symbol,
        }
    )


    return common


# ============================================================
# START
# ============================================================

print_section(
    "MARKET INCEPTION BOUNDARY RESOLUTION BUILD"
)


required_files = [
    INCEPTION_FILE,
    BOUNDARY_VERIFICATION_FILE,
    VLTO_SEARCH_AUDIT_FILE,
    DOWNLOAD_AUDIT_FILE,
    VLTO_WHEN_ISSUED_FILE,
    VLTO_REGULAR_BOUNDARY_FILE,
]


for file_path in required_files:

    if not file_path.exists():

        print(
            "\nERROR: Required file missing:"
        )

        print(
            file_path
        )

        sys.exit(1)


# ============================================================
# 1. LOAD REFERENCE / VERIFICATION
# ============================================================

print_section(
    "1. LOAD AND VALIDATE BOUNDARY EVIDENCE"
)


inceptions = pd.read_csv(
    INCEPTION_FILE
)


boundary = pd.read_csv(
    BOUNDARY_VERIFICATION_FILE
)


vlto_search = pd.read_csv(
    VLTO_SEARCH_AUDIT_FILE
)


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


boundary_cases = set(
    boundary[
        "security_key"
    ]
)


if boundary_cases != EXPECTED_CASES:

    print(
        "\nERROR: Boundary verification "
        "does not contain the expected "
        "four securities."
    )

    print(
        "Found:"
    )

    print(
        sorted(
            boundary_cases
        )
    )

    sys.exit(1)


expected_classifications = {
    "CARR":
        "TIINGO_CONFIRMS_PROVIDER_BOUNDARY",

    "OTIS":
        "TIINGO_CONFIRMS_PROVIDER_BOUNDARY",

    "GEHC":
        "YAHOO_PRE_INCEPTION_ARTIFACT",

    "VLTO":
        "PARTIALLY_RECOVERED_BY_TIINGO",
}


for security_key, expected in (
    expected_classifications.items()
):

    row = boundary[
        boundary[
            "security_key"
        ]
        == security_key
    ]


    if len(row) != 1:

        print(
            f"\nERROR: Expected one "
            f"boundary row for "
            f"{security_key}."
        )

        sys.exit(1)


    actual = row.iloc[0][
        "classification"
    ]


    if actual != expected:

        print(
            f"\nERROR: {security_key} "
            "classification changed."
        )

        print(
            f"Expected: {expected}"
        )

        print(
            f"Actual:   {actual}"
        )

        sys.exit(1)


print(
    "PASS:"
)

print(
    "CARR, OTIS, GEHC and VLTO "
    "boundary verification results "
    "match expectations."
)


# ============================================================
# 2. VERIFY VLTO-W IDENTITY / COVERAGE
# ============================================================

print_section(
    "2. VERIFY VLTO-W WHEN-ISSUED RESOLUTION"
)


vlto_w = vlto_search[
    vlto_search[
        "candidate_symbol"
    ]
    == "VLTO-W"
]


if len(vlto_w) != 1:

    print(
        "\nERROR: Expected exactly "
        "one VLTO-W search-audit row."
    )

    sys.exit(1)


vlto_w = vlto_w.iloc[0]


identity_valid = str(
    vlto_w[
        "identity_valid"
    ]
).strip().lower()


if identity_valid not in {
    "true",
    "1",
}:

    print(
        "\nERROR: VLTO-W did not pass "
        "identity validation."
    )

    sys.exit(1)


if (
    str(
        vlto_w[
            "status"
        ]
    )
    != "WHEN_ISSUED_FOUND"
):

    print(
        "\nERROR: VLTO-W did not "
        "successfully recover the "
        "when-issued history."
    )

    sys.exit(1)


if int(
    vlto_w[
        "when_issued_sessions"
    ]
) != 3:

    print(
        "\nERROR: Expected three "
        "VLTO-W when-issued sessions."
    )

    sys.exit(1)


print(
    "PASS:"
)

print(
    "VLTO-W is independently identified "
    "as Veralto's when-issued security "
    "and returned all three target sessions."
)


# ============================================================
# 3. CARR / OTIS CROSS-PROVIDER BOUNDARY
# ============================================================

print_section(
    "3. ACCEPT CARR / OTIS OBSERVED MARKET BOUNDARY"
)


for ticker in [
    "CARR",
    "OTIS",
]:

    row = boundary[
        boundary[
            "security_key"
        ]
        == ticker
    ].iloc[0]


    yahoo_first = pd.Timestamp(
        row[
            "yahoo_first_date"
        ]
    )


    tiingo_first = pd.Timestamp(
        row[
            "tiingo_first_date"
        ]
    )


    official = pd.Timestamp(
        row[
            "official_inception_date"
        ]
    )


    if (
        yahoo_first
        != pd.Timestamp(
            "2020-03-19"
        )
        or tiingo_first
        != pd.Timestamp(
            "2020-03-19"
        )
    ):

        print(
            f"\nERROR: {ticker} "
            "provider boundary changed."
        )

        sys.exit(1)


    if official != pd.Timestamp(
        "2020-03-18"
    ):

        print(
            f"\nERROR: {ticker} "
            "official inception changed."
        )

        sys.exit(1)


    print(
        f"{ticker}:"
    )

    print(
        "  Official expected inception: "
        "2020-03-18"
    )

    print(
        "  Yahoo first observation:     "
        "2020-03-19"
    )

    print(
        "  Tiingo first observation:    "
        "2020-03-19"
    )

    print(
        "  Resolution:                  "
        "ACCEPT 2020-03-19 AS FIRST "
        "INDEPENDENTLY OBSERVED SESSION"
    )


# ============================================================
# 4. VALIDATE GEHC PRE-INCEPTION ARTIFACT
# ============================================================

print_section(
    "4. VALIDATE GEHC PRE-INCEPTION ARTIFACT"
)


gehc_boundary = boundary[
    boundary[
        "security_key"
    ]
    == "GEHC"
].iloc[0]


if int(
    gehc_boundary[
        "yahoo_pre_inception_rows"
    ]
) != 1:

    print(
        "\nERROR: Expected exactly one "
        "Yahoo GEHC pre-inception row."
    )

    sys.exit(1)


if int(
    gehc_boundary[
        "tiingo_pre_inception_rows"
    ]
) != 0:

    print(
        "\nERROR: Tiingo unexpectedly "
        "contains a GEHC pre-inception row."
    )

    sys.exit(1)


gehc_acquisition = (
    download_audit[
        download_audit[
            "security_key"
        ]
        == "GEHC"
    ]
)


if len(gehc_acquisition) != 1:

    print(
        "\nERROR: Expected exactly one "
        "GEHC acquisition row."
    )

    sys.exit(1)


gehc_file = (
    PROJECT_ROOT
    / str(
        gehc_acquisition.iloc[0][
            "output_file"
        ]
    )
)


gehc_raw = pd.read_csv(
    gehc_file
)


gehc_dates = normalize_dates(
    gehc_raw[
        "Date"
    ]
)


pre_inception_dates = (
    gehc_dates[
        gehc_dates
        < pd.Timestamp(
            "2022-12-16"
        )
    ]
    .drop_duplicates()
    .sort_values()
)


if len(
    pre_inception_dates
) != 1:

    print(
        "\nERROR: Expected exactly one "
        "GEHC date before 2022-12-16."
    )

    print(
        pre_inception_dates
        .to_string(
            index=False
        )
    )

    sys.exit(1)


if (
    pre_inception_dates.iloc[0]
    != pd.Timestamp(
        "2022-12-15"
    )
):

    print(
        "\nERROR: Unexpected GEHC "
        "pre-inception date."
    )

    sys.exit(1)


if (
    pd.Timestamp(
        "2022-12-16"
    )
    not in set(
        gehc_dates
    )
):

    print(
        "\nERROR: GEHC does not contain "
        "the official 2022-12-16 "
        "market-inception session."
    )

    sys.exit(1)


print(
    "PASS:"
)

print(
    "Yahoo 2022-12-15 will be excluded "
    "from the analysis-ready GEHC series."
)

print(
    "The original Yahoo file remains unchanged."
)


# ============================================================
# 5. LOAD VLTO SOURCE COMPONENTS
# ============================================================

print_section(
    "5. BUILD COMPLETE VLTO MARKET-BOUNDARY SERIES"
)


vlto_acquisition = (
    download_audit[
        download_audit[
            "security_key"
        ]
        == "VLTO"
    ]
)


if len(vlto_acquisition) != 1:

    print(
        "\nERROR: Expected exactly "
        "one VLTO acquisition row."
    )

    sys.exit(1)


vlto_acquisition = (
    vlto_acquisition.iloc[0]
)


vlto_yahoo_file = (
    PROJECT_ROOT
    / str(
        vlto_acquisition[
            "output_file"
        ]
    )
)


if not vlto_yahoo_file.exists():

    print(
        "\nERROR: VLTO Yahoo file missing."
    )

    sys.exit(1)


yahoo = load_yahoo_common(
    vlto_yahoo_file
)


when_issued = load_tiingo_common(
    VLTO_WHEN_ISSUED_FILE,
    source_component=
        "Tiingo Veralto when-issued",

    provider_symbol=
        "VLTO-W",
)


regular_boundary = load_tiingo_common(
    VLTO_REGULAR_BOUNDARY_FILE,
    source_component=
        "Tiingo Veralto regular-way boundary",

    provider_symbol=
        "VLTO",
)


# ============================================================
# 6. VALIDATE SOURCE COMPONENT DATE RANGES
# ============================================================

print_section(
    "6. VALIDATE VLTO SOURCE COMPONENTS"
)


expected_when_issued_dates = {
    pd.Timestamp(
        "2023-09-27"
    ),
    pd.Timestamp(
        "2023-09-28"
    ),
    pd.Timestamp(
        "2023-09-29"
    ),
}


actual_when_issued_dates = set(
    when_issued[
        "date"
    ]
)


if (
    actual_when_issued_dates
    != expected_when_issued_dates
):

    print(
        "\nERROR: VLTO-W date set "
        "is not exactly the expected "
        "three when-issued sessions."
    )

    print(
        sorted(
            date.date()
            for date
            in actual_when_issued_dates
        )
    )

    sys.exit(1)


yahoo_first = (
    yahoo[
        "date"
    ].min()
)


if yahoo_first != pd.Timestamp(
    "2023-10-04"
):

    print(
        "\nERROR: Expected Yahoo VLTO "
        "history to begin 2023-10-04."
    )

    print(
        f"Actual: "
        f"{yahoo_first.date()}"
    )

    sys.exit(1)


# We need only regular-way Tiingo observations
# that occur before Yahoo's first observation.

regular_boundary = (
    regular_boundary[
        (
            regular_boundary[
                "date"
            ]
            >= pd.Timestamp(
                "2023-10-02"
            )
        )
        &
        (
            regular_boundary[
                "date"
            ]
            < yahoo_first
        )
    ]
    .copy()
)


expected_regular_boundary_dates = {
    pd.Timestamp(
        "2023-10-02"
    ),
    pd.Timestamp(
        "2023-10-03"
    ),
}


actual_regular_boundary_dates = set(
    regular_boundary[
        "date"
    ]
)


if (
    actual_regular_boundary_dates
    != expected_regular_boundary_dates
):

    print(
        "\nERROR: Tiingo regular-way "
        "VLTO boundary does not contain "
        "exactly 2023-10-02 and 2023-10-03."
    )

    print(
        sorted(
            date.date()
            for date
            in actual_regular_boundary_dates
        )
    )

    sys.exit(1)


print(
    "VLTO-W:"
)

print(
    when_issued[
        [
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
        ]
    ]
    .to_string(
        index=False
    )
)


print(
    "\nVLTO regular-way Tiingo boundary:"
)

print(
    regular_boundary[
        [
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
        ]
    ]
    .to_string(
        index=False
    )
)


print(
    "\nYahoo primary begins:"
)

print(
    yahoo[
        [
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
        ]
    ]
    .head(3)
    .to_string(
        index=False
    )
)


# ============================================================
# 7. BUILD VLTO COMPOSITE
# ============================================================

print_section(
    "7. BUILD VLTO COMPOSITE"
)


vlto_composite = pd.concat(
    [
        when_issued,
        regular_boundary,
        yahoo,
    ],
    ignore_index=True,
)


vlto_composite = (
    vlto_composite
    .sort_values(
        "date"
    )
    .reset_index(
        drop=True
    )
)


# No overlapping dates should remain because
# each source component occupies a distinct range.

duplicate_dates = int(
    vlto_composite[
        "date"
    ]
    .duplicated()
    .sum()
)


required_columns = [
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividend",
    "split_factor",
]


required_null_values = int(
    vlto_composite[
        required_columns
    ]
    .isna()
    .sum()
    .sum()
)


invalid_high, invalid_low = (
    validate_ohlc(
        vlto_composite
    )
)


nonpositive_prices = int(
    (
        vlto_composite[
            [
                "open",
                "high",
                "low",
                "close",
                "adj_close",
            ]
        ]
        <= 0
    )
    .any(
        axis=1
    )
    .sum()
)


negative_volume = int(
    (
        vlto_composite[
            "volume"
        ]
        < 0
    )
    .sum()
)


invalid_split_factor = int(
    (
        vlto_composite[
            "split_factor"
        ]
        <= 0
    )
    .sum()
)


print(
    f"Composite rows: "
    f"{len(vlto_composite)}"
)

print(
    f"First date: "
    f"{vlto_composite['date'].min().date()}"
)

print(
    f"Last date: "
    f"{vlto_composite['date'].max().date()}"
)

print(
    f"Duplicate dates: "
    f"{duplicate_dates}"
)

print(
    f"Required null values: "
    f"{required_null_values}"
)

print(
    f"Invalid HIGH rows: "
    f"{invalid_high}"
)

print(
    f"Invalid LOW rows: "
    f"{invalid_low}"
)

print(
    f"Nonpositive price rows: "
    f"{nonpositive_prices}"
)

print(
    f"Negative-volume rows: "
    f"{negative_volume}"
)

print(
    f"Invalid split factors: "
    f"{invalid_split_factor}"
)


if (
    duplicate_dates != 0
    or required_null_values != 0
    or invalid_high != 0
    or invalid_low != 0
    or nonpositive_prices != 0
    or negative_volume != 0
    or invalid_split_factor != 0
):

    print(
        "\nERROR:"
    )

    print(
        "VLTO composite failed "
        "structural integrity validation."
    )

    sys.exit(1)


# ============================================================
# 8. SPY CALENDAR COVERAGE
# ============================================================

print_section(
    "8. VALIDATE VLTO TRADING-SESSION COVERAGE"
)


spy_rows = download_audit[
    download_audit[
        "security_key"
    ]
    == "SPY_ETF"
]


if len(spy_rows) != 1:

    print(
        "\nERROR: Expected one "
        "SPY_ETF acquisition row."
    )

    sys.exit(1)


spy_file = (
    PROJECT_ROOT
    / str(
        spy_rows.iloc[0][
            "output_file"
        ]
    )
)


spy = pd.read_csv(
    spy_file
)


spy_dates = (
    normalize_dates(
        spy[
            "Date"
        ]
    )
    .drop_duplicates()
    .sort_values()
)


requested_end_exclusive = pd.Timestamp(
    vlto_acquisition[
        "download_end_exclusive"
    ]
)


expected_sessions = spy_dates[
    (
        spy_dates
        >= pd.Timestamp(
            "2023-09-27"
        )
    )
    &
    (
        spy_dates
        < requested_end_exclusive
    )
]


actual_sessions = (
    vlto_composite[
        "date"
    ]
    .drop_duplicates()
)


missing_sessions = expected_sessions[
    ~expected_sessions.isin(
        actual_sessions
    )
]


extra_sessions = actual_sessions[
    ~actual_sessions.isin(
        expected_sessions
    )
]


print(
    f"Expected sessions from "
    f"market inception: "
    f"{len(expected_sessions)}"
)

print(
    f"Actual sessions: "
    f"{len(actual_sessions)}"
)

print(
    f"Missing sessions: "
    f"{len(missing_sessions)}"
)

print(
    f"Extra sessions: "
    f"{len(extra_sessions)}"
)


if not missing_sessions.empty:

    print(
        "\nMissing:"
    )

    print(
        missing_sessions
        .to_string(
            index=False
        )
    )


if not extra_sessions.empty:

    print(
        "\nExtra:"
    )

    print(
        extra_sessions
        .to_string(
            index=False
        )
    )


if (
    len(
        missing_sessions
    )
    != 0
    or len(
        extra_sessions
    )
    != 0
):

    print(
        "\nERROR:"
    )

    print(
        "VLTO boundary composite does "
        "not provide complete market-session "
        "coverage."
    )

    sys.exit(1)


print(
    "\nPASS:"
)

print(
    "VLTO has complete trading-session "
    "coverage from its documented "
    "2023-09-27 market inception onward."
)


# ============================================================
# 9. SAVE VLTO COMPOSITE
# ============================================================

print_section(
    "9. SAVE VLTO COMPOSITE"
)


VLTO_COMPOSITE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


vlto_composite.to_csv(
    VLTO_COMPOSITE_FILE,
    index=False,
    date_format="%Y-%m-%d",
)


print(
    f"Saved:\n"
    f"{VLTO_COMPOSITE_FILE}"
)


# ============================================================
# 10. BUILD AUTHORITATIVE RESOLUTION TABLE
# ============================================================

print_section(
    "10. BUILD BOUNDARY RESOLUTION REFERENCE"
)


resolution_records = [

    {
        "security_key":
            "CARR",

        "project_ticker":
            "CARR",

        "official_market_inception_date":
            "2020-03-18",

        "regular_way_start_date":
            "2020-04-03",

        "resolution_type":
            "CROSS_PROVIDER_OBSERVED_BOUNDARY",

        "accepted_effective_start":
            "2020-03-19",

        "primary_source":
            "Yahoo Finance",

        "verification_source":
            "Tiingo",

        "verification_symbol":
            "CARR",

        "resolution_status":
            "VALIDATED",

        "analysis_action":
            (
                "Do not fabricate a 2020-03-18 "
                "observation. Treat 2020-03-19 "
                "as the first independently "
                "observed price session."
            ),

        "notes":
            (
                "Official source described the "
                "when-issued start as expected "
                "on or around 2020-03-18. "
                "Both Yahoo and Tiingo independently "
                "begin on 2020-03-19."
            ),
    },


    {
        "security_key":
            "OTIS",

        "project_ticker":
            "OTIS",

        "official_market_inception_date":
            "2020-03-18",

        "regular_way_start_date":
            "2020-04-03",

        "resolution_type":
            "CROSS_PROVIDER_OBSERVED_BOUNDARY",

        "accepted_effective_start":
            "2020-03-19",

        "primary_source":
            "Yahoo Finance",

        "verification_source":
            "Tiingo",

        "verification_symbol":
            "OTIS",

        "resolution_status":
            "VALIDATED",

        "analysis_action":
            (
                "Do not fabricate a 2020-03-18 "
                "observation. Treat 2020-03-19 "
                "as the first independently "
                "observed price session."
            ),

        "notes":
            (
                "Official source described the "
                "when-issued start as expected "
                "on or around 2020-03-18. "
                "Both Yahoo and Tiingo independently "
                "begin on 2020-03-19."
            ),
    },


    {
        "security_key":
            "GEHC",

        "project_ticker":
            "GEHC",

        "official_market_inception_date":
            "2022-12-16",

        "regular_way_start_date":
            "2023-01-04",

        "resolution_type":
            "EXCLUDE_PRE_INCEPTION_PROVIDER_ROW",

        "accepted_effective_start":
            "2022-12-16",

        "primary_source":
            "Yahoo Finance",

        "verification_source":
            "Tiingo",

        "verification_symbol":
            "GEHC",

        "resolution_status":
            "VALIDATED",

        "analysis_action":
            (
                "Exclude Yahoo observation dated "
                "2022-12-15 from all standardized "
                "and analytical datasets. "
                "Preserve the raw Yahoo source file."
            ),

        "notes":
            (
                "Official inception is 2022-12-16. "
                "Yahoo contains one 2022-12-15 row. "
                "Independent Tiingo verification "
                "contains no pre-inception observation."
            ),
    },


    {
        "security_key":
            "VLTO",

        "project_ticker":
            "VLTO",

        "official_market_inception_date":
            "2023-09-27",

        "regular_way_start_date":
            "2023-10-02",

        "resolution_type":
            "SOURCE_COMPOSITE",

        "accepted_effective_start":
            "2023-09-27",

        "primary_source":
            "Yahoo Finance",

        "verification_source":
            "Tiingo",

        "verification_symbol":
            "VLTO-W + VLTO",

        "resolution_status":
            "VALIDATED",

        "analysis_action":
            (
                "Use Tiingo VLTO-W for "
                "2023-09-27 through 2023-09-29; "
                "Tiingo VLTO for 2023-10-02 "
                "through 2023-10-03; "
                "Yahoo VLTO beginning 2023-10-04."
            ),

        "notes":
            (
                "Tiingo Search identifies VLTO-W "
                "as 'Veralto Corp WhenIssued' and "
                "returns all three documented "
                "when-issued sessions. Tiingo VLTO "
                "recovers the first two regular-way "
                "sessions absent from Yahoo. "
                "The combined series has complete "
                "SPY-session coverage from market "
                "inception onward."
            ),
    },
]


resolutions = pd.DataFrame(
    resolution_records
)


if len(resolutions) != 4:

    print(
        "\nERROR: Expected exactly "
        "four boundary resolution rows."
    )

    sys.exit(1)


if (
    set(
        resolutions[
            "security_key"
        ]
    )
    != EXPECTED_CASES
):

    print(
        "\nERROR: Resolution population "
        "does not match expected cases."
    )

    sys.exit(1)


if (
    resolutions[
        [
            "security_key",
            "project_ticker",
        ]
    ]
    .duplicated()
    .any()
):

    print(
        "\nERROR: Duplicate resolution "
        "keys detected."
    )

    sys.exit(1)


if (
    resolutions[
        "resolution_status"
    ]
    .ne(
        "VALIDATED"
    )
    .any()
):

    print(
        "\nERROR: All four boundary "
        "resolutions must be VALIDATED."
    )

    sys.exit(1)


print(
    resolutions[
        [
            "security_key",
            "official_market_inception_date",
            "accepted_effective_start",
            "resolution_type",
            "verification_source",
            "verification_symbol",
            "resolution_status",
        ]
    ]
    .to_string(
        index=False
    )
)


# ============================================================
# 11. SAVE AUTHORITATIVE REFERENCE
# ============================================================

print_section(
    "11. SAVE BOUNDARY RESOLUTION REFERENCE"
)


RESOLUTION_REFERENCE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


resolutions.to_csv(
    RESOLUTION_REFERENCE_FILE,
    index=False,
)


print(
    f"Saved:\n"
    f"{RESOLUTION_REFERENCE_FILE}"
)


# ============================================================
# FINAL
# ============================================================

print_section(
    "BOUNDARY RESOLUTION RESULT"
)


print(
    "CARR:"
)

print(
    "  VALIDATED CROSS-PROVIDER "
    "OBSERVED BOUNDARY"
)


print(
    "\nOTIS:"
)

print(
    "  VALIDATED CROSS-PROVIDER "
    "OBSERVED BOUNDARY"
)


print(
    "\nGEHC:"
)

print(
    "  VALIDATED PRE-INCEPTION "
    "PROVIDER-ROW EXCLUSION"
)


print(
    "\nVLTO:"
)

print(
    "  VALIDATED COMPLETE "
    "MULTI-SOURCE BOUNDARY COMPOSITE"
)


print(
    "\nALL FOUR MARKET-INCEPTION "
    "BOUNDARY CASES ARE RESOLVED."
)

print(
    "\nThere are no remaining "
    "unexplained inception-boundary "
    "coverage gaps."
)