from pathlib import Path
import os
import sys
import time

import pandas as pd
import requests
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

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "tiingo_symbol_candidate_audit.csv"
)


# --------------------------------------------------
# Candidate mappings to test
# --------------------------------------------------

CANDIDATES = {
    "CDAY": "DAY",
    "FBHS": "FBIN",
    "GPS": "GAP",
    "HFC": "DINO",
    "FRC": "FRCB",
    "INFO": "MRKT",
}


# --------------------------------------------------
# Validation settings
# --------------------------------------------------

# A requested range may begin on a weekend or holiday.
# We therefore allow a small difference between the
# requested start and the first actual trading date.
MAX_START_GAP_DAYS = 7

# Some securities stop trading a few days before the
# S&P membership removal takes effect.
#
# We record this gap rather than automatically
# forward-filling prices.
MAX_END_GAP_DAYS_FOR_FULL_COVERAGE = 10

REQUEST_PAUSE_SECONDS = 1.5


EXPECTED_COLUMNS = {
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


REQUIRED_PRICE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjClose",
]


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def print_section(title):

    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


# --------------------------------------------------
# Environment
# --------------------------------------------------

load_dotenv()

API_TOKEN = os.getenv(
    "TIINGO_API_TOKEN"
)


if not API_TOKEN:

    raise RuntimeError(
        "TIINGO_API_TOKEN was not found in .env"
    )


# --------------------------------------------------
# Load manifest
# --------------------------------------------------

print_section(
    "TIINGO HISTORICAL SYMBOL CANDIDATE TEST"
)


if not MANIFEST_FILE.exists():

    print(
        f"\nERROR: Manifest does not exist:\n"
        f"{MANIFEST_FILE}"
    )

    sys.exit(1)


manifest = pd.read_csv(
    MANIFEST_FILE
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
# HTTP session
# --------------------------------------------------

session = requests.Session()

session.headers.update(
    {
        "Content-Type": "application/json",
        "Authorization": f"Token {API_TOKEN}",
    }
)


# --------------------------------------------------
# Test candidates
# --------------------------------------------------

results = []


print_section(
    "TEST CANDIDATE SYMBOLS"
)


for number, (
    original_ticker,
    candidate_ticker,
) in enumerate(
    CANDIDATES.items(),
    start=1,
):

    print(
        f"\n[{number}/{len(CANDIDATES)}] "
        f"{original_ticker} -> {candidate_ticker}"
    )


    # ----------------------------------------------
    # Find ORIGINAL ticker's manifest request
    # ----------------------------------------------

    manifest_match = manifest[
        manifest["project_ticker"]
        == original_ticker
    ]


    if len(manifest_match) != 1:

        print(
            "    MANIFEST ERROR: "
            f"Expected 1 row, found "
            f"{len(manifest_match)}."
        )

        results.append(
            {
                "original_ticker": original_ticker,
                "candidate_ticker": candidate_ticker,
                "status": "MANIFEST_ERROR",
                "error_message": (
                    "Expected exactly one original "
                    "ticker manifest row."
                ),
            }
        )

        continue


    row = manifest_match.iloc[0]

    security_key = row[
        "security_key"
    ]

    requested_start = row[
        "download_start"
    ]

    requested_end_exclusive = row[
        "download_end_exclusive"
    ]

    requested_end_inclusive = (
        requested_end_exclusive
        - pd.Timedelta(days=1)
    )


    print(
        f"    Security key: "
        f"{security_key}"
    )

    print(
        f"    Original manifest range: "
        f"{requested_start.date()} "
        f"through "
        f"{requested_end_exclusive.date()} "
        f"(end exclusive)"
    )


    # ----------------------------------------------
    # Metadata request
    # ----------------------------------------------

    metadata_url = (
        "https://api.tiingo.com/"
        f"tiingo/daily/{candidate_ticker}"
    )


    try:

        metadata_response = session.get(
            metadata_url,
            timeout=30,
        )


        metadata_http_status = (
            metadata_response.status_code
        )


        if metadata_http_status == 200:

            metadata = (
                metadata_response.json()
            )

            metadata_name = (
                metadata.get("name")
            )

            metadata_start = (
                metadata.get("startDate")
            )

            metadata_end = (
                metadata.get("endDate")
            )


            print(
                f"    Candidate name: "
                f"{metadata_name}"
            )

            print(
                f"    Tiingo metadata range: "
                f"{metadata_start} "
                f"through {metadata_end}"
            )


        else:

            metadata = {}

            metadata_name = None
            metadata_start = None
            metadata_end = None


            print(
                f"    Metadata HTTP "
                f"{metadata_http_status}"
            )


        # ------------------------------------------
        # Price request
        #
        # IMPORTANT:
        # We request the candidate symbol using
        # the ORIGINAL ticker's manifest dates.
        # ------------------------------------------

        price_url = (
            "https://api.tiingo.com/"
            f"tiingo/daily/"
            f"{candidate_ticker}/prices"
        )


        params = {
            "startDate": (
                requested_start.strftime(
                    "%Y-%m-%d"
                )
            ),
            "endDate": (
                requested_end_inclusive.strftime(
                    "%Y-%m-%d"
                )
            ),
        }


        response = session.get(
            price_url,
            params=params,
            timeout=30,
        )


        http_status = (
            response.status_code
        )


        print(
            f"    Price HTTP status: "
            f"{http_status}"
        )


        # ------------------------------------------
        # HTTP failure
        # ------------------------------------------

        if http_status != 200:

            print(
                "    RESULT: FAILED"
            )

            results.append(
                {
                    "security_key": security_key,
                    "original_ticker": original_ticker,
                    "candidate_ticker": candidate_ticker,
                    "requested_start": requested_start.date(),
                    "requested_end_exclusive": (
                        requested_end_exclusive.date()
                    ),
                    "metadata_http_status": (
                        metadata_http_status
                    ),
                    "metadata_name": metadata_name,
                    "metadata_start": metadata_start,
                    "metadata_end": metadata_end,
                    "price_http_status": http_status,
                    "rows_returned": 0,
                    "first_returned_date": None,
                    "last_returned_date": None,
                    "start_gap_days": None,
                    "end_gap_days": None,
                    "required_null_count": None,
                    "duplicate_dates": None,
                    "missing_expected_columns": None,
                    "status": "FAILED",
                    "error_message": (
                        response.text[:500]
                    ),
                }
            )

            time.sleep(
                REQUEST_PAUSE_SECONDS
            )

            continue


        payload = response.json()


        # ------------------------------------------
        # No historical data
        # ------------------------------------------

        if not payload:

            print(
                "    Rows returned: 0"
            )

            print(
                "    RESULT: NO_DATA"
            )

            results.append(
                {
                    "security_key": security_key,
                    "original_ticker": original_ticker,
                    "candidate_ticker": candidate_ticker,
                    "requested_start": requested_start.date(),
                    "requested_end_exclusive": (
                        requested_end_exclusive.date()
                    ),
                    "metadata_http_status": (
                        metadata_http_status
                    ),
                    "metadata_name": metadata_name,
                    "metadata_start": metadata_start,
                    "metadata_end": metadata_end,
                    "price_http_status": http_status,
                    "rows_returned": 0,
                    "first_returned_date": None,
                    "last_returned_date": None,
                    "start_gap_days": None,
                    "end_gap_days": None,
                    "required_null_count": None,
                    "duplicate_dates": None,
                    "missing_expected_columns": None,
                    "status": "NO_DATA",
                    "error_message": (
                        "Candidate symbol returned "
                        "no data for the original "
                        "ticker's historical range."
                    ),
                }
            )

            time.sleep(
                REQUEST_PAUSE_SECONDS
            )

            continue


        # ------------------------------------------
        # Convert to DataFrame
        # ------------------------------------------

        data = pd.DataFrame(
            payload
        )


        data["date"] = pd.to_datetime(
            data["date"],
            utc=True,
            errors="raise",
        )


        first_date = (
            data["date"]
            .min()
            .date()
        )

        last_date = (
            data["date"]
            .max()
            .date()
        )


        first_timestamp = pd.Timestamp(
            first_date
        )

        last_timestamp = pd.Timestamp(
            last_date
        )


        # ------------------------------------------
        # Schema checks
        # ------------------------------------------

        missing_columns = sorted(
            EXPECTED_COLUMNS
            - set(data.columns)
        )


        if missing_columns:

            required_null_count = None

        else:

            required_null_count = int(
                data[
                    REQUIRED_PRICE_COLUMNS
                ]
                .isna()
                .sum()
                .sum()
            )


        duplicate_dates = int(
            data["date"]
            .duplicated()
            .sum()
        )


        # ------------------------------------------
        # Coverage calculations
        # ------------------------------------------

        start_gap_days = (
            first_timestamp
            - requested_start.normalize()
        ).days


        # Because project end is exclusive,
        # compare final observation against
        # the final calendar day inside range.
        end_gap_days = (
            requested_end_inclusive.normalize()
            - last_timestamp
        ).days


        # ------------------------------------------
        # Basic quality status
        # ------------------------------------------

        schema_ok = (
            len(missing_columns) == 0
        )

        nulls_ok = (
            required_null_count == 0
        )

        duplicates_ok = (
            duplicate_dates == 0
        )

        start_coverage_ok = (
            start_gap_days
            <= MAX_START_GAP_DAYS
        )

        end_coverage_ok = (
            end_gap_days
            <= MAX_END_GAP_DAYS_FOR_FULL_COVERAGE
        )


        # ------------------------------------------
        # Classification
        # ------------------------------------------

        if (
            schema_ok
            and nulls_ok
            and duplicates_ok
            and start_coverage_ok
            and end_coverage_ok
        ):

            status = (
                "CANDIDATE_FULL_COVERAGE"
            )

            error_message = None


        elif (
            schema_ok
            and nulls_ok
            and duplicates_ok
            and len(data) > 0
        ):

            status = (
                "CANDIDATE_PARTIAL_COVERAGE"
            )

            error_message = (
                "Data quality passed, but the "
                "candidate does not cover the "
                "complete original ticker "
                "manifest range."
            )


        else:

            status = (
                "QUALITY_REVIEW"
            )

            error_message = (
                "Candidate returned data but "
                "failed one or more quality "
                "checks."
            )


        # ------------------------------------------
        # Output
        # ------------------------------------------

        print(
            f"    Rows returned: "
            f"{len(data)}"
        )

        print(
            f"    First returned date: "
            f"{first_date}"
        )

        print(
            f"    Last returned date: "
            f"{last_date}"
        )

        print(
            f"    Start gap: "
            f"{start_gap_days} days"
        )

        print(
            f"    End gap: "
            f"{end_gap_days} days"
        )

        print(
            f"    Missing expected columns: "
            f"{len(missing_columns)}"
        )

        print(
            f"    Required-field nulls: "
            f"{required_null_count}"
        )

        print(
            f"    Duplicate dates: "
            f"{duplicate_dates}"
        )

        print(
            f"    RESULT: {status}"
        )


        results.append(
            {
                "security_key": security_key,
                "original_ticker": original_ticker,
                "candidate_ticker": candidate_ticker,
                "requested_start": requested_start.date(),
                "requested_end_exclusive": (
                    requested_end_exclusive.date()
                ),
                "metadata_http_status": (
                    metadata_http_status
                ),
                "metadata_name": metadata_name,
                "metadata_start": metadata_start,
                "metadata_end": metadata_end,
                "price_http_status": http_status,
                "rows_returned": len(data),
                "first_returned_date": first_date,
                "last_returned_date": last_date,
                "start_gap_days": start_gap_days,
                "end_gap_days": end_gap_days,
                "required_null_count": (
                    required_null_count
                ),
                "duplicate_dates": (
                    duplicate_dates
                ),
                "missing_expected_columns": (
                    "|".join(
                        missing_columns
                    )
                    if missing_columns
                    else ""
                ),
                "status": status,
                "error_message": (
                    error_message
                ),
            }
        )


    except Exception as error:

        print(
            f"    RESULT: FAILED"
        )

        print(
            f"    {error}"
        )


        results.append(
            {
                "security_key": security_key,
                "original_ticker": original_ticker,
                "candidate_ticker": candidate_ticker,
                "requested_start": requested_start.date(),
                "requested_end_exclusive": (
                    requested_end_exclusive.date()
                ),
                "metadata_http_status": None,
                "metadata_name": None,
                "metadata_start": None,
                "metadata_end": None,
                "price_http_status": None,
                "rows_returned": 0,
                "first_returned_date": None,
                "last_returned_date": None,
                "start_gap_days": None,
                "end_gap_days": None,
                "required_null_count": None,
                "duplicate_dates": None,
                "missing_expected_columns": None,
                "status": "FAILED",
                "error_message": str(error),
            }
        )


    time.sleep(
        REQUEST_PAUSE_SECONDS
    )


# --------------------------------------------------
# Save results
# --------------------------------------------------

print_section(
    "CANDIDATE TEST SUMMARY"
)


audit = pd.DataFrame(
    results
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
    audit[
        [
            "original_ticker",
            "candidate_ticker",
            "rows_returned",
            "first_returned_date",
            "last_returned_date",
            "start_gap_days",
            "end_gap_days",
            "status",
        ]
    ].to_string(
        index=False
    )
)


print(
    "\nStatus counts:"
)

print(
    audit[
        "status"
    ]
    .value_counts()
    .to_string()
)


print(
    f"\nAudit saved:\n"
    f"{OUTPUT_FILE}"
)


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section(
    "TEST RESULT"
)


full_coverage = audit[
    audit["status"]
    == "CANDIDATE_FULL_COVERAGE"
]


partial = audit[
    audit["status"]
    == "CANDIDATE_PARTIAL_COVERAGE"
]


unusable = audit[
    ~audit["status"].isin(
        [
            "CANDIDATE_FULL_COVERAGE",
            "CANDIDATE_PARTIAL_COVERAGE",
        ]
    )
]


print(
    f"Full-coverage candidates: "
    f"{len(full_coverage)}"
)

print(
    f"Partial-coverage candidates: "
    f"{len(partial)}"
)

print(
    f"Unusable candidates: "
    f"{len(unusable)}"
)


print(
    "\nCandidate testing complete."
)

print(
    "No candidate has been accepted into "
    "price_source_resolutions.csv yet."
)