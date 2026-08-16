from pathlib import Path
import os
import sys

import pandas as pd
import requests
from dotenv import load_dotenv


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DOWNLOAD_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_download_audit.csv"
)

EXCEPTION_RAW_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "source"
    / "prices"
    / "tiingo_exceptions"
)

DISCA_COMPOSITE_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "disca_tiingo_identity_composite.csv"
)

RESOLVED_ROWS_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_exception_resolved_rows.csv"
)

RESOLUTION_REFERENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "price_exception_resolutions.csv"
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


BASE_URL = (
    "https://api.tiingo.com"
)

HEADERS = {
    "Content-Type": "application/json",
    "Authorization":
        f"Token {TIINGO_API_TOKEN}",
}


# ============================================================
# CONSTANTS
# ============================================================

UA_DATE = pd.Timestamp(
    "2021-05-05"
)

FISV_DATE = pd.Timestamp(
    "2025-11-12"
)

DISCA_PERMATICKER = (
    "US000000000527"
)

PRICE_TOLERANCE = 0.011

VOLUME_RELATIVE_TOLERANCE = 0.001

EXPECTED_REQUEST_COUNT = 596


# ============================================================
# DISPLAY
# ============================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    240,
)


def print_section(title):

    print(
        "\n"
        + "=" * 79
    )

    print(
        title
    )

    print(
        "=" * 79
    )


# ============================================================
# HELPERS
# ============================================================

def normalize_dates(series):

    dates = pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    )

    return (
        dates
        .dt
        .tz_convert(None)
        .dt
        .normalize()
    )


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


def parse_tiingo_response(
    response,
    symbol,
):

    if response.status_code != 200:

        raise RuntimeError(
            f"Tiingo {symbol} HTTP "
            f"{response.status_code}: "
            f"{response.text[:500]}"
        )


    payload = response.json()


    if not isinstance(
        payload,
        list,
    ):

        raise RuntimeError(
            f"Unexpected Tiingo payload "
            f"for {symbol}."
        )


    if not payload:

        raise RuntimeError(
            f"Tiingo returned no data "
            f"for {symbol}."
        )


    data = pd.DataFrame(
        payload
    )


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


    missing_columns = (
        required_columns
        - set(
            data.columns
        )
    )


    if missing_columns:

        raise RuntimeError(
            f"Tiingo {symbol} missing "
            f"columns: "
            f"{sorted(missing_columns)}"
        )


    data["date"] = (
        normalize_dates(
            data["date"]
        )
    )


    if data["date"].isna().any():

        raise RuntimeError(
            f"Tiingo {symbol} returned "
            "unparseable dates."
        )


    if data["date"].duplicated().any():

        raise RuntimeError(
            f"Tiingo {symbol} returned "
            "duplicate dates."
        )


    numeric_columns = [
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
    ]


    for column in numeric_columns:

        data[column] = (
            pd.to_numeric(
                data[column],
                errors="coerce",
            )
        )


    if (
        data[
            numeric_columns
        ]
        .isna()
        .sum()
        .sum()
        > 0
    ):

        raise RuntimeError(
            f"Tiingo {symbol} returned "
            "null numeric values."
        )


    data.insert(
        0,
        "queried_symbol",
        symbol,
    )


    return (
        data
        .sort_values(
            "date"
        )
        .reset_index(
            drop=True
        )
    )


def save_source_native(
    dataframe,
    filename,
):

    EXCEPTION_RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    output_path = (
        EXCEPTION_RAW_DIR
        / filename
    )


    dataframe.to_csv(
        output_path,
        index=False,
        date_format="%Y-%m-%d",
    )


    return output_path


def validate_ohlc(data):

    invalid_high = (
        data["high"]
        <
        data[
            [
                "open",
                "low",
                "close",
            ]
        ].max(
            axis=1
        )
    )


    invalid_low = (
        data["low"]
        >
        data[
            [
                "open",
                "high",
                "close",
            ]
        ].min(
            axis=1
        )
    )


    return (
        int(
            invalid_high.sum()
        ),
        int(
            invalid_low.sum()
        ),
    )


# ============================================================
# LOAD ACQUISITION AUDIT
# ============================================================

print_section(
    "MARKET PRICE EXCEPTION RESOLUTION"
)


if not DOWNLOAD_AUDIT_FILE.exists():

    print(
        "\nERROR: Download audit "
        "does not exist."
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
    .reset_index(
        drop=True
    )
)


if (
    len(download_audit)
    != EXPECTED_REQUEST_COUNT
):

    print(
        "\nERROR: Expected 596 "
        "acquisition rows."
    )

    print(
        f"Found: "
        f"{len(download_audit)}"
    )

    sys.exit(1)


# ============================================================
# LOCATE SPY REFERENCE
# ============================================================

spy_rows = download_audit[
    download_audit[
        "security_key"
    ]
    == "SPY_ETF"
]


if len(spy_rows) != 1:

    print(
        "\nERROR: Expected exactly "
        "one SPY_ETF row."
    )

    sys.exit(1)


spy_path = (
    PROJECT_ROOT
    / str(
        spy_rows.iloc[0][
            "output_file"
        ]
    )
)


spy = pd.read_csv(
    spy_path
)


spy_dates = (
    normalize_dates(
        spy["Date"]
    )
    .dropna()
    .drop_duplicates()
    .sort_values()
    .reset_index(
        drop=True
    )
)


# ============================================================
# 1. UA VERIFICATION / FIELD OVERRIDE
# ============================================================

print_section(
    "1. RESOLVE UA INVALID LOW"
)


ua_response = tiingo_prices(
    symbol="UA",
    start_date="2021-05-05",
    end_date="2021-05-05",
)


ua = parse_tiingo_response(
    ua_response,
    "UA",
)


if len(ua) != 1:

    print(
        "\nERROR: Expected exactly "
        "one Tiingo UA observation."
    )

    sys.exit(1)


ua_row = ua.iloc[0]


print(
    f"Date:   "
    f"{ua_row['date'].date()}"
)

print(
    f"Open:   "
    f"{ua_row['open']}"
)

print(
    f"High:   "
    f"{ua_row['high']}"
)

print(
    f"Low:    "
    f"{ua_row['low']}"
)

print(
    f"Close:  "
    f"{ua_row['close']}"
)

print(
    f"Volume: "
    f"{ua_row['volume']}"
)


ua_invalid_high, ua_invalid_low = (
    validate_ohlc(
        ua
    )
)


if (
    ua_invalid_high > 0
    or ua_invalid_low > 0
):

    print(
        "\nERROR: Tiingo UA "
        "verification row itself "
        "fails OHLC validation."
    )

    sys.exit(1)


# Locate Yahoo UA raw file

ua_audit = download_audit[
    (
        download_audit[
            "security_key"
        ]
        == "UA"
    )
    &
    (
        download_audit[
            "project_ticker"
        ]
        == "UA"
    )
]


if len(ua_audit) != 1:

    print(
        "\nERROR: Expected exactly "
        "one UA acquisition row."
    )

    sys.exit(1)


ua_yahoo_path = (
    PROJECT_ROOT
    / str(
        ua_audit.iloc[0][
            "output_file"
        ]
    )
)


ua_yahoo = pd.read_csv(
    ua_yahoo_path
)


ua_yahoo["Date"] = (
    normalize_dates(
        ua_yahoo["Date"]
    )
)


ua_yahoo_target = ua_yahoo[
    ua_yahoo[
        "Date"
    ]
    == UA_DATE
]


if len(ua_yahoo_target) != 1:

    print(
        "\nERROR: Expected exactly "
        "one Yahoo UA target row."
    )

    sys.exit(1)


ua_yahoo_row = (
    ua_yahoo_target.iloc[0]
)


print(
    "\nYahoo vs Tiingo:"
)

comparison = pd.DataFrame(
    {
        "field": [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ],

        "Yahoo": [
            ua_yahoo_row[
                "Open"
            ],
            ua_yahoo_row[
                "High"
            ],
            ua_yahoo_row[
                "Low"
            ],
            ua_yahoo_row[
                "Close"
            ],
            ua_yahoo_row[
                "Volume"
            ],
        ],

        "Tiingo": [
            ua_row[
                "open"
            ],
            ua_row[
                "high"
            ],
            ua_row[
                "low"
            ],
            ua_row[
                "close"
            ],
            ua_row[
                "volume"
            ],
        ],
    }
)


print(
    comparison.to_string(
        index=False
    )
)


# O/H/C should agree closely.
# Volume is deliberately NOT used as a
# correction because provider volume differs.

for yahoo_column, tiingo_column in [
    ("Open", "open"),
    ("High", "high"),
    ("Close", "close"),
]:

    difference = abs(
        float(
            ua_yahoo_row[
                yahoo_column
            ]
        )
        -
        float(
            ua_row[
                tiingo_column
            ]
        )
    )


    if difference > PRICE_TOLERANCE:

        print(
            "\nERROR: UA providers "
            f"disagree materially on "
            f"{yahoo_column}."
        )

        print(
            f"Difference: "
            f"{difference}"
        )

        sys.exit(1)


ua_raw_path = save_source_native(
    ua,
    "UA__verification__2021-05-05.csv",
)


print(
    "\nPASS:"
)

print(
    "UA low correction independently "
    "verified as 20.57."
)

print(
    "\nThe Yahoo raw file was NOT modified."
)


# ============================================================
# 2. FISV MISSING SESSION
# ============================================================

print_section(
    "2. RESOLVE FISV MISSING SESSION"
)


fisv_response = tiingo_prices(
    symbol="FISV",
    start_date="2025-11-12",
    end_date="2025-11-12",
)


fisv = parse_tiingo_response(
    fisv_response,
    "FISV",
)


if len(fisv) != 1:

    print(
        "\nERROR: Expected exactly "
        "one FISV Tiingo observation."
    )

    sys.exit(1)


fisv_row = fisv.iloc[0]


fisv_invalid_high, fisv_invalid_low = (
    validate_ohlc(
        fisv
    )
)


if (
    fisv_invalid_high > 0
    or fisv_invalid_low > 0
):

    print(
        "\nERROR: FISV verification "
        "row fails OHLC validation."
    )

    sys.exit(1)


print(
    f"Date:   "
    f"{fisv_row['date'].date()}"
)

print(
    f"Open:   "
    f"{fisv_row['open']}"
)

print(
    f"High:   "
    f"{fisv_row['high']}"
)

print(
    f"Low:    "
    f"{fisv_row['low']}"
)

print(
    f"Close:  "
    f"{fisv_row['close']}"
)

print(
    f"Adj:    "
    f"{fisv_row['adjClose']}"
)

print(
    f"Volume: "
    f"{fisv_row['volume']}"
)


fisv_raw_path = save_source_native(
    fisv,
    "FISV__verification__2025-11-12.csv",
)


print(
    "\nPASS:"
)

print(
    "The missing FISV 2025-11-12 "
    "session is independently verified."
)

print(
    "\nThe Yahoo raw file was NOT modified."
)


# ============================================================
# 3. LOAD EXISTING DIRECT DISCA
# ============================================================

print_section(
    "3. LOAD DIRECT DISCA SOURCE"
)


disca_audit = download_audit[
    (
        download_audit[
            "security_key"
        ]
        == "DISCA"
    )
    &
    (
        download_audit[
            "project_ticker"
        ]
        == "DISCA"
    )
]


if len(disca_audit) != 1:

    print(
        "\nERROR: Expected exactly "
        "one DISCA acquisition row."
    )

    sys.exit(1)


disca_audit_row = (
    disca_audit.iloc[0]
)


requested_start = pd.Timestamp(
    disca_audit_row[
        "download_start"
    ]
).normalize()


requested_end_exclusive = (
    pd.Timestamp(
        disca_audit_row[
            "download_end_exclusive"
        ]
    )
    .normalize()
)


direct_disca_path = (
    PROJECT_ROOT
    / str(
        disca_audit_row[
            "output_file"
        ]
    )
)


direct_disca = pd.read_csv(
    direct_disca_path
)


direct_disca[
    "date"
] = normalize_dates(
    direct_disca[
        "date"
    ]
)


print(
    f"Direct DISCA rows: "
    f"{len(direct_disca)}"
)

print(
    f"First date: "
    f"{direct_disca['date'].min().date()}"
)

print(
    f"Last date: "
    f"{direct_disca['date'].max().date()}"
)


# ============================================================
# 4. DOWNLOAD DISCA PERMANENT-IDENTITY HISTORY
# ============================================================

print_section(
    "4. DOWNLOAD DISCA PERMANENT-IDENTITY HISTORY"
)


end_inclusive = (
    requested_end_exclusive
    - pd.Timedelta(
        days=1
    )
)


perma_response = tiingo_prices(
    symbol=DISCA_PERMATICKER,
    start_date=(
        requested_start.strftime(
            "%Y-%m-%d"
        )
    ),
    end_date=(
        end_inclusive.strftime(
            "%Y-%m-%d"
        )
    ),
)


perma = parse_tiingo_response(
    perma_response,
    DISCA_PERMATICKER,
)


print(
    f"Permanent identifier: "
    f"{DISCA_PERMATICKER}"
)

print(
    f"Rows: "
    f"{len(perma)}"
)

print(
    f"First date: "
    f"{perma['date'].min().date()}"
)

print(
    f"Last date: "
    f"{perma['date'].max().date()}"
)


perma_raw_path = save_source_native(
    perma,
    (
        "DISCA__provider_continuity__"
        f"{DISCA_PERMATICKER}.csv"
    ),
)


# ============================================================
# 5. VERIFY DISCA OVERLAP
# ============================================================

print_section(
    "5. VERIFY DISCA IDENTITY OVERLAP"
)


comparison_columns = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjClose",
]


perma_compare = perma[
    comparison_columns
].copy()


direct_compare = direct_disca[
    comparison_columns
].copy()


overlap = perma_compare.merge(
    direct_compare,
    on="date",
    how="inner",
    suffixes=(
        "_perma",
        "_direct",
    ),
)


print(
    f"Overlap sessions: "
    f"{len(overlap)}"
)


if overlap.empty:

    print(
        "\nERROR: Permanent and direct "
        "DISCA histories have no "
        "overlapping observations."
    )

    sys.exit(1)


price_fields = [
    "open",
    "high",
    "low",
    "close",
    "adjClose",
]


overlap_failures = []


for _, row in overlap.iterrows():

    for field in price_fields:

        perma_value = float(
            row[
                f"{field}_perma"
            ]
        )

        direct_value = float(
            row[
                f"{field}_direct"
            ]
        )


        difference = abs(
            perma_value
            - direct_value
        )


        if difference > PRICE_TOLERANCE:

            overlap_failures.append(
                {
                    "date":
                        row["date"],

                    "field":
                        field,

                    "perma":
                        perma_value,

                    "direct":
                        direct_value,

                    "difference":
                        difference,
                }
            )


# Volume may differ slightly because one
# provider identity representation can round
# historical volume.

for _, row in overlap.iterrows():

    perma_volume = float(
        row[
            "volume_perma"
        ]
    )

    direct_volume = float(
        row[
            "volume_direct"
        ]
    )


    denominator = max(
        abs(
            direct_volume
        ),
        1,
    )


    relative_difference = (
        abs(
            perma_volume
            - direct_volume
        )
        / denominator
    )


    if (
        relative_difference
        > VOLUME_RELATIVE_TOLERANCE
    ):

        overlap_failures.append(
            {
                "date":
                    row["date"],

                "field":
                    "volume",

                "perma":
                    perma_volume,

                "direct":
                    direct_volume,

                "difference":
                    relative_difference,
            }
        )


print(
    overlap.to_string(
        index=False
    )
)


if overlap_failures:

    print(
        "\nERROR: DISCA permanent-identity "
        "history does not sufficiently match "
        "the direct DISCA history."
    )

    print(
        pd.DataFrame(
            overlap_failures
        )
        .to_string(
            index=False
        )
    )

    sys.exit(1)


print(
    "\nPASS:"
)

print(
    "Overlapping permanent-identity and "
    "direct DISCA observations match "
    "within defined tolerances."
)


# ============================================================
# 6. CONSTRUCT SOURCE-PRESERVING DISCA COMPOSITE
# ============================================================

print_section(
    "6. BUILD DISCA SOURCE COMPOSITE"
)


tiingo_columns = [
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
]


perma_component = (
    perma[
        tiingo_columns
    ]
    .copy()
)


perma_component[
    "source_component"
] = (
    f"Tiingo permaTicker "
    f"{DISCA_PERMATICKER}"
)


direct_component = (
    direct_disca[
        tiingo_columns
    ]
    .copy()
)


direct_component[
    "source_component"
] = (
    "Tiingo direct DISCA"
)


# Direct DISCA takes precedence on overlapping
# dates because it explicitly identifies the
# requested historical ticker.

perma_component[
    "_priority"
] = 1

direct_component[
    "_priority"
] = 2


disca_composite = pd.concat(
    [
        perma_component,
        direct_component,
    ],
    ignore_index=True,
)


disca_composite = (
    disca_composite
    .sort_values(
        [
            "date",
            "_priority",
        ]
    )
    .drop_duplicates(
        subset=[
            "date"
        ],
        keep="last",
    )
    .drop(
        columns=[
            "_priority"
        ]
    )
    .sort_values(
        "date"
    )
    .reset_index(
        drop=True
    )
)


# ============================================================
# 7. VALIDATE COMPLETE DISCA COMPOSITE
# ============================================================

print_section(
    "7. VALIDATE COMPLETE DISCA COMPOSITE"
)


duplicate_dates = int(
    disca_composite[
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
    "volume",
    "adjOpen",
    "adjHigh",
    "adjLow",
    "adjClose",
    "adjVolume",
    "divCash",
    "splitFactor",
]


null_values = int(
    disca_composite[
        required_columns
    ]
    .isna()
    .sum()
    .sum()
)


invalid_high, invalid_low = (
    validate_ohlc(
        disca_composite
    )
)


nonpositive_prices = int(
    (
        disca_composite[
            [
                "open",
                "high",
                "low",
                "close",
                "adjClose",
            ]
        ]
        <= 0
    )
    .any(
        axis=1
    )
    .sum()
)


invalid_split_factors = int(
    (
        disca_composite[
            "splitFactor"
        ]
        <= 0
    ).sum()
)


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
    disca_composite[
        "date"
    ]
    .drop_duplicates()
)


missing_sessions = request_calendar[
    ~request_calendar.isin(
        observed_dates
    )
]


extra_sessions = observed_dates[
    ~observed_dates.isin(
        request_calendar
    )
]


first_date = (
    disca_composite[
        "date"
    ]
    .min()
)

last_date = (
    disca_composite[
        "date"
    ]
    .max()
)


print(
    f"Composite rows: "
    f"{len(disca_composite)}"
)

print(
    f"First date: "
    f"{first_date.date()}"
)

print(
    f"Last date: "
    f"{last_date.date()}"
)

print(
    f"Duplicate dates: "
    f"{duplicate_dates}"
)

print(
    f"Required null values: "
    f"{null_values}"
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
    f"Invalid split factors: "
    f"{invalid_split_factors}"
)

print(
    f"Missing SPY sessions: "
    f"{len(missing_sessions)}"
)

print(
    f"Extra non-request sessions: "
    f"{len(extra_sessions)}"
)


if not missing_sessions.empty:

    print(
        "\nMissing sessions:"
    )

    print(
        missing_sessions
        .to_string(
            index=False
        )
    )


if not extra_sessions.empty:

    print(
        "\nExtra sessions:"
    )

    print(
        extra_sessions
        .to_string(
            index=False
        )
    )


disca_pass = (
    duplicate_dates == 0
    and null_values == 0
    and invalid_high == 0
    and invalid_low == 0
    and nonpositive_prices == 0
    and invalid_split_factors == 0
    and len(
        missing_sessions
    ) == 0
    and len(
        extra_sessions
    ) == 0
)


if not disca_pass:

    print(
        "\nERROR:"
    )

    print(
        "DISCA composite still does not "
        "provide complete validated coverage."
    )

    print(
        "\nDo not proceed."
    )

    sys.exit(1)


print(
    "\nPASS:"
)

print(
    "DISCA composite provides complete "
    "requested U.S. trading-session coverage."
)


# ============================================================
# 8. SAVE DISCA COMPOSITE
# ============================================================

DISCA_COMPOSITE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


disca_composite.to_csv(
    DISCA_COMPOSITE_FILE,
    index=False,
    date_format="%Y-%m-%d",
)


print(
    f"\nSaved:\n"
    f"{DISCA_COMPOSITE_FILE}"
)


# ============================================================
# 9. SAVE RESOLVED EXCEPTION ROWS
# ============================================================

print_section(
    "8. SAVE RESOLVED EXCEPTION DATA"
)


resolved_rows = pd.DataFrame(
    [
        {
            "security_key":
                "UA",

            "project_ticker":
                "UA",

            "date":
                UA_DATE.date(),

            "resolution_type":
                "FIELD_OVERRIDE",

            "field_name":
                "low",

            "resolved_open":
                None,

            "resolved_high":
                None,

            "resolved_low":
                float(
                    ua_row[
                        "low"
                    ]
                ),

            "resolved_close":
                None,

            "resolved_adj_close":
                None,

            "resolved_volume":
                None,

            "verification_source":
                "Tiingo",

            "verification_symbol":
                "UA",
        },

        {
            "security_key":
                "FISV",

            "project_ticker":
                "FISV",

            "date":
                FISV_DATE.date(),

            "resolution_type":
                "ROW_INSERT",

            "field_name":
                None,

            "resolved_open":
                float(
                    fisv_row[
                        "open"
                    ]
                ),

            "resolved_high":
                float(
                    fisv_row[
                        "high"
                    ]
                ),

            "resolved_low":
                float(
                    fisv_row[
                        "low"
                    ]
                ),

            "resolved_close":
                float(
                    fisv_row[
                        "close"
                    ]
                ),

            "resolved_adj_close":
                float(
                    fisv_row[
                        "adjClose"
                    ]
                ),

            "resolved_volume":
                int(
                    fisv_row[
                        "volume"
                    ]
                ),

            "verification_source":
                "Tiingo",

            "verification_symbol":
                "FISV",
        },
    ]
)


RESOLVED_ROWS_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


resolved_rows.to_csv(
    RESOLVED_ROWS_FILE,
    index=False,
)


print(
    resolved_rows.to_string(
        index=False
    )
)


print(
    f"\nSaved:\n"
    f"{RESOLVED_ROWS_FILE}"
)


# ============================================================
# 10. SAVE COMMITTABLE RESOLUTION REFERENCE
# ============================================================

print_section(
    "9. SAVE PRICE EXCEPTION RESOLUTION REFERENCE"
)


resolution_reference = pd.DataFrame(
    [
        {
            "security_key":
                "UA",

            "project_ticker":
                "UA",

            "effective_start":
                "2021-05-05",

            "effective_end_exclusive":
                "2021-05-06",

            "exception_type":
                "FIELD_OVERRIDE",

            "primary_source":
                "Yahoo Finance",

            "verification_source":
                "Tiingo",

            "verification_symbol":
                "UA",

            "resolution_status":
                "VALIDATED",

            "resolution_method":
                (
                    "Retain Yahoo source row "
                    "except replace Low during "
                    "standardization using the "
                    "independently verified "
                    "Tiingo Low."
                ),

            "notes":
                (
                    "Yahoo Low=21.00 exceeds "
                    "Yahoo Open=20.87. Tiingo "
                    "independently reproduces "
                    "Open=20.87, High=21.825, "
                    "Close=21.13 and reports a "
                    "valid Low=20.57. Raw Yahoo "
                    "file remains unchanged."
                ),
        },

        {
            "security_key":
                "FISV",

            "project_ticker":
                "FISV",

            "effective_start":
                "2025-11-12",

            "effective_end_exclusive":
                "2025-11-13",

            "exception_type":
                "ROW_INSERT",

            "primary_source":
                "Yahoo Finance",

            "verification_source":
                "Tiingo",

            "verification_symbol":
                "FISV",

            "resolution_status":
                "VALIDATED",

            "resolution_method":
                (
                    "Insert the missing "
                    "2025-11-12 Tiingo daily "
                    "observation during "
                    "standardization."
                ),

            "notes":
                (
                    "Yahoo omitted one internal "
                    "U.S. trading session. "
                    "Tiingo returned the same "
                    "2025-11-12 observation when "
                    "queried through both FISV "
                    "and FI provider symbols. "
                    "Raw Yahoo file remains "
                    "unchanged."
                ),
        },

        {
            "security_key":
                "DISCA",

            "project_ticker":
                "DISCA",

            "effective_start":
                requested_start.date(),

            "effective_end_exclusive":
                requested_end_exclusive.date(),

            "exception_type":
                "SOURCE_COMPOSITE",

            "primary_source":
                "Tiingo",

            "verification_source":
                "Tiingo",

            "verification_symbol":
                DISCA_PERMATICKER,

            "resolution_status":
                "VALIDATED",

            "resolution_method":
                (
                    "Use Tiingo permanent-identity "
                    "history for historical coverage "
                    "and direct DISCA observations "
                    "where available, with direct "
                    "DISCA taking date-level "
                    "precedence."
                ),

            "notes":
                (
                    "Direct Tiingo DISCA metadata "
                    "begins only 2022-04-06 and "
                    "returns three requested rows. "
                    "Tiingo permanent identifier "
                    "US000000000527 carries the "
                    "historical predecessor series. "
                    "Overlapping observations were "
                    "required to match within "
                    "defined price and volume "
                    "tolerances, and the resulting "
                    "composite was required to cover "
                    "every SPY trading session in "
                    "the requested interval."
                ),
        },
    ]
)


RESOLUTION_REFERENCE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


resolution_reference.to_csv(
    RESOLUTION_REFERENCE_FILE,
    index=False,
)


print(
    resolution_reference[
        [
            "security_key",
            "project_ticker",
            "exception_type",
            "verification_source",
            "verification_symbol",
            "resolution_status",
        ]
    ]
    .to_string(
        index=False
    )
)


print(
    f"\nSaved:\n"
    f"{RESOLUTION_REFERENCE_FILE}"
)


# ============================================================
# FINAL
# ============================================================

print_section(
    "EXCEPTION RESOLUTION RESULT"
)


print(
    "UA:"
)

print(
    "  VALIDATED FIELD OVERRIDE"
)

print(
    "  Yahoo raw file unchanged."
)


print(
    "\nFISV:"
)

print(
    "  VALIDATED MISSING-ROW INSERT"
)

print(
    "  Yahoo raw file unchanged."
)


print(
    "\nDISCA:"
)

print(
    "  VALIDATED TIINGO "
    "IDENTITY COMPOSITE"
)

print(
    "  Original Tiingo raw file unchanged."
)


print(
    "\nALL THREE IDENTIFIED "
    "MARKET-DATA EXCEPTIONS "
    "HAVE BEEN RESOLVED."
)

print(
    "\nNext step:"
)

print(
    "Build and validate the independent "
    "security-inception reference for the "
    "legitimate start-boundary cases."
)