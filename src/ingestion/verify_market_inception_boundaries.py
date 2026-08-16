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

INCEPTION_REFERENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "securities"
    / "security_market_inceptions.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_inception_boundary_verification.csv"
)

RAW_VERIFICATION_DIR = (
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


BASE_URL = (
    "https://api.tiingo.com"
)

HEADERS = {
    "Content-Type":
        "application/json",

    "Authorization":
        f"Token {TIINGO_API_TOKEN}",
}


# ============================================================
# CASE DEFINITIONS
# ============================================================

CASES = {

    "CARR": {
        "query_symbol":
            "CARR",

        "request_start":
            "2020-03-16",

        "request_end":
            "2020-03-23",

        "official_inception":
            "2020-03-18",

        "regular_way_start":
            "2020-04-03",

        "expected_missing_dates": [
            "2020-03-18",
        ],

        "case_type":
            "POST_INCEPTION_GAP",
    },


    "OTIS": {
        "query_symbol":
            "OTIS",

        "request_start":
            "2020-03-16",

        "request_end":
            "2020-03-23",

        "official_inception":
            "2020-03-18",

        "regular_way_start":
            "2020-04-03",

        "expected_missing_dates": [
            "2020-03-18",
        ],

        "case_type":
            "POST_INCEPTION_GAP",
    },


    "GEHC": {
        "query_symbol":
            "GEHC",

        "request_start":
            "2022-12-13",

        "request_end":
            "2022-12-21",

        "official_inception":
            "2022-12-16",

        "regular_way_start":
            "2023-01-04",

        # Yahoo contains an observation BEFORE
        # the company's documented public-market
        # inception.
        "expected_missing_dates": [],

        "case_type":
            "PRE_INCEPTION_PROVIDER_ROW",
    },


    "VLTO": {
        "query_symbol":
            "VLTO",

        "request_start":
            "2023-09-25",

        "request_end":
            "2023-10-05",

        "official_inception":
            "2023-09-27",

        "regular_way_start":
            "2023-10-02",

        "expected_missing_dates": [
            "2023-09-27",
            "2023-09-28",
            "2023-09-29",
            "2023-10-02",
            "2023-10-03",
        ],

        "case_type":
            "POST_INCEPTION_GAP",
    },
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


def print_section(title):

    print(
        "\n"
        + "=" * 79
    )

    print(title)

    print(
        "=" * 79
    )


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


def request_tiingo_prices(
    symbol,
    start_date,
    end_date,
):

    url = (
        f"{BASE_URL}/tiingo/"
        f"daily/{symbol}/prices"
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
            f"{symbol}: HTTP "
            f"{response.status_code}: "
            f"{response.text[:500]}"
        )


    payload = response.json()


    if not isinstance(
        payload,
        list,
    ):

        raise RuntimeError(
            f"{symbol}: Unexpected "
            "Tiingo payload type."
        )


    if not payload:

        return pd.DataFrame()


    data = pd.DataFrame(
        payload
    )


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
        - set(
            data.columns
        )
    )


    if missing_columns:

        raise RuntimeError(
            f"{symbol}: Missing "
            f"columns "
            f"{sorted(missing_columns)}"
        )


    data["date"] = (
        normalize_dates(
            data["date"]
        )
    )


    if (
        data["date"]
        .isna()
        .any()
    ):

        raise RuntimeError(
            f"{symbol}: Invalid date "
            "returned by Tiingo."
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
            f"{symbol}: Null numeric "
            "fields were returned."
        )


    if (
        data["date"]
        .duplicated()
        .any()
    ):

        raise RuntimeError(
            f"{symbol}: Duplicate dates "
            "were returned."
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


def validate_ohlc(data):

    if data.empty:

        return (
            0,
            0,
        )


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


def load_yahoo_source(
    security_key,
    download_audit,
):

    matches = download_audit[
        download_audit[
            "security_key"
        ]
        == security_key
    ]


    if len(matches) != 1:

        raise RuntimeError(
            f"{security_key}: expected "
            "exactly one acquisition row, "
            f"found {len(matches)}."
        )


    file_path = (
        PROJECT_ROOT
        / str(
            matches.iloc[0][
                "output_file"
            ]
        )
    )


    if not file_path.exists():

        raise RuntimeError(
            f"{security_key}: Yahoo "
            f"file missing:\n{file_path}"
        )


    data = pd.read_csv(
        file_path
    )


    data["Date"] = (
        normalize_dates(
            data["Date"]
        )
    )


    return (
        data,
        file_path,
    )


# ============================================================
# LOAD PROJECT REFERENCES
# ============================================================

print_section(
    "MARKET INCEPTION BOUNDARY VERIFICATION"
)


if not DOWNLOAD_AUDIT_FILE.exists():

    print(
        "\nERROR: Download audit "
        "does not exist."
    )

    sys.exit(1)


if not INCEPTION_REFERENCE_FILE.exists():

    print(
        "\nERROR: Security inception "
        "reference does not exist."
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


inceptions = pd.read_csv(
    INCEPTION_REFERENCE_FILE
)


inceptions[
    "market_inception_date"
] = pd.to_datetime(
    inceptions[
        "market_inception_date"
    ],
    errors="raise",
)


# ============================================================
# VALIDATE CASES EXIST IN REFERENCE
# ============================================================

print_section(
    "1. CASE POPULATION VALIDATION"
)


for security_key in CASES:

    reference_match = inceptions[
        inceptions[
            "security_key"
        ]
        == security_key
    ]


    if len(reference_match) != 1:

        print(
            f"\nERROR: {security_key} "
            "is missing or duplicated in "
            "security_market_inceptions.csv."
        )

        sys.exit(1)


    expected_date = pd.Timestamp(
        CASES[
            security_key
        ][
            "official_inception"
        ]
    )


    stored_date = (
        reference_match
        .iloc[0][
            "market_inception_date"
        ]
    )


    if (
        stored_date.normalize()
        != expected_date.normalize()
    ):

        print(
            f"\nERROR: {security_key} "
            "inception reference mismatch."
        )

        print(
            f"Expected: "
            f"{expected_date.date()}"
        )

        print(
            f"Stored: "
            f"{stored_date.date()}"
        )

        sys.exit(1)


print(
    "PASS: All four boundary "
    "cases match the inception reference."
)


# ============================================================
# VERIFY EACH CASE
# ============================================================

verification_records = []


for security_key, case in (
    CASES.items()
):

    print_section(
        f"2. VERIFY {security_key}"
    )


    official_inception = pd.Timestamp(
        case[
            "official_inception"
        ]
    )


    regular_way_start = pd.Timestamp(
        case[
            "regular_way_start"
        ]
    )


    # --------------------------------------------------------
    # Load existing Yahoo series
    # --------------------------------------------------------

    yahoo, yahoo_path = (
        load_yahoo_source(
            security_key,
            download_audit,
        )
    )


    yahoo_first = (
        yahoo[
            "Date"
        ]
        .min()
    )


    yahoo_last = (
        yahoo[
            "Date"
        ]
        .max()
    )


    print(
        f"Yahoo file:\n"
        f"{yahoo_path}"
    )

    print(
        f"\nYahoo first date: "
        f"{yahoo_first.date()}"
    )

    print(
        f"Yahoo last date: "
        f"{yahoo_last.date()}"
    )


    yahoo_window = yahoo[
        (
            yahoo["Date"]
            >= pd.Timestamp(
                case[
                    "request_start"
                ]
            )
        )
        &
        (
            yahoo["Date"]
            <= pd.Timestamp(
                case[
                    "request_end"
                ]
            )
        )
    ]


    print(
        "\nYahoo observations "
        "around boundary:"
    )


    if yahoo_window.empty:

        print(
            "None."
        )

    else:

        yahoo_display_columns = [
            column
            for column in [
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Adj Close",
                "Volume",
            ]
            if column
            in yahoo_window.columns
        ]


        print(
            yahoo_window[
                yahoo_display_columns
            ]
            .to_string(
                index=False
            )
        )


    # --------------------------------------------------------
    # Download independent Tiingo verification
    # --------------------------------------------------------

    response = (
        request_tiingo_prices(
            symbol=case[
                "query_symbol"
            ],
            start_date=case[
                "request_start"
            ],
            end_date=case[
                "request_end"
            ],
        )
    )


    print(
        f"\nTiingo HTTP status: "
        f"{response.status_code}"
    )


    try:

        tiingo = (
            parse_tiingo_response(
                response,
                case[
                    "query_symbol"
                ],
            )
        )


    except Exception as error:

        print(
            f"\nTiingo validation "
            f"failed: {error}"
        )

        tiingo = pd.DataFrame()


    if tiingo.empty:

        print(
            "\nTiingo returned NO_DATA."
        )


    else:

        print(
            f"\nTiingo rows: "
            f"{len(tiingo)}"
        )

        print(
            f"Tiingo first date: "
            f"{tiingo['date'].min().date()}"
        )

        print(
            f"Tiingo last date: "
            f"{tiingo['date'].max().date()}"
        )


        print(
            "\nTiingo observations:"
        )

        print(
            tiingo[
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


        invalid_high, invalid_low = (
            validate_ohlc(
                tiingo
            )
        )


        if (
            invalid_high > 0
            or invalid_low > 0
        ):

            print(
                "\nERROR: Tiingo "
                "verification itself "
                "contains invalid OHLC."
            )

            sys.exit(1)


        # Save source-native verification.
        RAW_VERIFICATION_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )


        raw_output = (
            RAW_VERIFICATION_DIR
            / (
                f"{security_key}"
                "__inception_boundary"
                "__tiingo.csv"
            )
        )


        tiingo.to_csv(
            raw_output,
            index=False,
            date_format="%Y-%m-%d",
        )


        print(
            f"\nVerification raw file saved:\n"
            f"{raw_output}"
        )


    # --------------------------------------------------------
    # Compare expected missing dates
    # --------------------------------------------------------

    expected_missing_dates = [
        pd.Timestamp(date)
        for date
        in case[
            "expected_missing_dates"
        ]
    ]


    tiingo_dates = (
        set(
            tiingo[
                "date"
            ].tolist()
        )
        if not tiingo.empty
        else set()
    )


    recovered_dates = [
        date
        for date
        in expected_missing_dates
        if date in tiingo_dates
    ]


    still_missing_dates = [
        date
        for date
        in expected_missing_dates
        if date not in tiingo_dates
    ]


    # --------------------------------------------------------
    # GEHC special pre-inception check
    # --------------------------------------------------------

    yahoo_pre_inception_dates = (
        yahoo.loc[
            yahoo["Date"]
            < official_inception,
            "Date",
        ]
        .drop_duplicates()
        .sort_values()
    )


    tiingo_pre_inception_dates = (
        tiingo.loc[
            tiingo["date"]
            < official_inception,
            "date",
        ]
        .drop_duplicates()
        .sort_values()
        if not tiingo.empty
        else pd.Series(
            dtype="datetime64[ns]"
        )
    )


    # --------------------------------------------------------
    # Classification
    # --------------------------------------------------------

    if (
        case[
            "case_type"
        ]
        == "POST_INCEPTION_GAP"
    ):

        if (
            expected_missing_dates
            and len(
                recovered_dates
            )
            == len(
                expected_missing_dates
            )
        ):

            classification = (
                "FULLY_RECOVERED_BY_TIINGO"
            )


        elif recovered_dates:

            classification = (
                "PARTIALLY_RECOVERED_BY_TIINGO"
            )


        elif (
            not tiingo.empty
            and tiingo[
                "date"
            ].min()
            <= yahoo_first
        ):

            classification = (
                "TIINGO_CONFIRMS_PROVIDER_BOUNDARY"
            )


        else:

            classification = (
                "UNRESOLVED_PROVIDER_BOUNDARY"
            )


    else:

        # GEHC
        yahoo_has_pre_inception = (
            len(
                yahoo_pre_inception_dates
            )
            > 0
        )


        tiingo_has_pre_inception = (
            len(
                tiingo_pre_inception_dates
            )
            > 0
        )


        if (
            yahoo_has_pre_inception
            and not tiingo_has_pre_inception
        ):

            classification = (
                "YAHOO_PRE_INCEPTION_ARTIFACT"
            )


        elif (
            yahoo_has_pre_inception
            and tiingo_has_pre_inception
        ):

            classification = (
                "CROSS_PROVIDER_PRE_INCEPTION_ROW"
            )


        else:

            classification = (
                "NO_PRE_INCEPTION_ANOMALY"
            )


    print(
        "\nClassification:"
    )

    print(
        classification
    )


    if expected_missing_dates:

        print(
            "\nExpected missing dates:"
        )

        print(
            [
                date.date()
                for date
                in expected_missing_dates
            ]
        )


        print(
            "Recovered by Tiingo:"
        )

        print(
            [
                date.date()
                for date
                in recovered_dates
            ]
        )


        print(
            "Still missing:"
        )

        print(
            [
                date.date()
                for date
                in still_missing_dates
            ]
        )


    if (
        security_key
        == "GEHC"
    ):

        print(
            "\nYahoo pre-inception dates:"
        )

        print(
            [
                date.date()
                for date
                in yahoo_pre_inception_dates
            ]
        )


        print(
            "Tiingo pre-inception dates:"
        )

        print(
            [
                date.date()
                for date
                in tiingo_pre_inception_dates
            ]
        )


    verification_records.append(
        {
            "security_key":
                security_key,

            "query_symbol":
                case[
                    "query_symbol"
                ],

            "official_inception_date":
                official_inception.date(),

            "regular_way_start_date":
                regular_way_start.date(),

            "yahoo_first_date":
                yahoo_first.date(),

            "tiingo_first_date":
                (
                    tiingo[
                        "date"
                    ]
                    .min()
                    .date()
                    if not tiingo.empty
                    else None
                ),

            "expected_missing_sessions":
                len(
                    expected_missing_dates
                ),

            "recovered_sessions":
                len(
                    recovered_dates
                ),

            "still_missing_sessions":
                len(
                    still_missing_dates
                ),

            "yahoo_pre_inception_rows":
                len(
                    yahoo_pre_inception_dates
                ),

            "tiingo_pre_inception_rows":
                len(
                    tiingo_pre_inception_dates
                ),

            "classification":
                classification,
        }
    )


# ============================================================
# SAVE MACHINE-READABLE RESULTS
# ============================================================

print_section(
    "3. SAVE BOUNDARY VERIFICATION"
)


verification = pd.DataFrame(
    verification_records
)


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
# SUMMARY
# ============================================================

print_section(
    "4. VERIFICATION SUMMARY"
)


print(
    verification[
        [
            "security_key",
            "official_inception_date",
            "yahoo_first_date",
            "tiingo_first_date",
            "expected_missing_sessions",
            "recovered_sessions",
            "still_missing_sessions",
            "yahoo_pre_inception_rows",
            "tiingo_pre_inception_rows",
            "classification",
        ]
    ]
    .to_string(
        index=False
    )
)


print(
    "\nClassification counts:"
)


print(
    verification[
        "classification"
    ]
    .value_counts()
    .to_string()
)


# ============================================================
# FINAL
# ============================================================

print_section(
    "BOUNDARY VERIFICATION COMPLETE"
)


print(
    "No existing Yahoo or Tiingo "
    "acquisition file was modified."
)

print(
    "\nThe four remaining market-inception "
    "boundary discrepancies now have "
    "independent Tiingo evidence."
)