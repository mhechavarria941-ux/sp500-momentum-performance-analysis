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

FAILURES_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "price_availability_failures.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "tiingo_fallback_audit.csv"
)


# --------------------------------------------------
# Environment
# --------------------------------------------------

load_dotenv()

API_TOKEN = os.getenv("TIINGO_API_TOKEN")

if not API_TOKEN:

    raise RuntimeError(
        "TIINGO_API_TOKEN was not found in .env"
    )


# --------------------------------------------------
# Settings
# --------------------------------------------------

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


def save_results(records):

    if not records:
        return

    result_df = pd.DataFrame(records)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
    )


# --------------------------------------------------
# Load files
# --------------------------------------------------

print_section("TIINGO FALLBACK AVAILABILITY AUDIT")


for path in [
    MANIFEST_FILE,
    FAILURES_FILE,
]:

    if not path.exists():

        print(
            f"\nERROR: Required file missing:\n{path}"
        )

        sys.exit(1)


manifest = pd.read_csv(
    MANIFEST_FILE
)

failures = pd.read_csv(
    FAILURES_FILE
)


manifest["download_start"] = pd.to_datetime(
    manifest["download_start"],
    errors="raise",
)

manifest["download_end_exclusive"] = pd.to_datetime(
    manifest["download_end_exclusive"],
    errors="raise",
)


# --------------------------------------------------
# Validate failure population
# --------------------------------------------------

print(
    f"\nYahoo failures to investigate: "
    f"{len(failures)}"
)


if len(failures) != 43:

    print(
        "\nWARNING: Expected 43 Yahoo failures "
        f"but found {len(failures)}."
    )


# --------------------------------------------------
# Existing audit / resume support
# --------------------------------------------------

existing_records = []


if OUTPUT_FILE.exists():

    existing = pd.read_csv(
        OUTPUT_FILE
    )

    existing_records = (
        existing
        .to_dict("records")
    )

    completed_keys = set(
        zip(
            existing.loc[
                existing["tiingo_status"]
                == "VALIDATED",
                "security_key",
            ],
            existing.loc[
                existing["tiingo_status"]
                == "VALIDATED",
                "project_ticker",
            ],
        )
    )

    print(
        f"Previously validated fallback rows: "
        f"{len(completed_keys)}"
    )

else:

    completed_keys = set()


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
# Audit each Yahoo failure
# --------------------------------------------------

print_section("TEST TIINGO FALLBACKS")


results = list(existing_records)

total = len(failures)


for number, (_, failure) in enumerate(
    failures.iterrows(),
    start=1,
):

    security_key = str(
        failure["security_key"]
    ).strip()

    project_ticker = str(
        failure["project_ticker"]
    ).strip().upper()


    key = (
        security_key,
        project_ticker,
    )


    # ----------------------------------------------
    # Skip already validated requests
    # ----------------------------------------------

    if key in completed_keys:

        print(
            f"[{number}/{total}] "
            f"{project_ticker} -> "
            "already VALIDATED"
        )

        continue


    # ----------------------------------------------
    # Find exact manifest request
    # ----------------------------------------------

    manifest_match = manifest[
        (
            manifest["security_key"]
            == security_key
        )
        &
        (
            manifest["project_ticker"]
            == project_ticker
        )
    ]


    if len(manifest_match) != 1:

        print(
            f"[{number}/{total}] "
            f"{project_ticker} -> "
            "MANIFEST_ERROR"
        )

        result = {
            "security_key": security_key,
            "project_ticker": project_ticker,
            "tiingo_symbol": project_ticker,
            "download_start": None,
            "download_end_exclusive": None,
            "http_status": None,
            "rows_returned": 0,
            "first_returned_date": None,
            "last_returned_date": None,
            "missing_expected_columns": None,
            "required_null_count": None,
            "duplicate_dates": None,
            "tiingo_status": "MANIFEST_ERROR",
            "error_message": (
                "Expected exactly one matching "
                "manifest request."
            ),
        }

        results.append(result)

        save_results(results)

        continue


    manifest_row = manifest_match.iloc[0]

    download_start = manifest_row[
        "download_start"
    ]

    download_end_exclusive = manifest_row[
        "download_end_exclusive"
    ]

    end_inclusive = (
        download_end_exclusive
        - pd.Timedelta(days=1)
    )


    # ----------------------------------------------
    # Request Tiingo
    # ----------------------------------------------

    url = (
        "https://api.tiingo.com/"
        f"tiingo/daily/{project_ticker}/prices"
    )

    params = {
        "startDate": (
            download_start.strftime(
                "%Y-%m-%d"
            )
        ),
        "endDate": (
            end_inclusive.strftime(
                "%Y-%m-%d"
            )
        ),
    }


    try:

        response = session.get(
            url,
            params=params,
            timeout=30,
        )

        http_status = (
            response.status_code
        )


        if http_status != 200:

            result = {
                "security_key": security_key,
                "project_ticker": project_ticker,
                "tiingo_symbol": project_ticker,
                "download_start": download_start.date(),
                "download_end_exclusive": (
                    download_end_exclusive.date()
                ),
                "http_status": http_status,
                "rows_returned": 0,
                "first_returned_date": None,
                "last_returned_date": None,
                "missing_expected_columns": None,
                "required_null_count": None,
                "duplicate_dates": None,
                "tiingo_status": "FAILED",
                "error_message": (
                    response.text[:500]
                ),
            }

            results.append(result)

            print(
                f"[{number}/{total}] "
                f"{project_ticker} -> "
                f"FAILED HTTP {http_status}"
            )

            save_results(results)

            time.sleep(
                REQUEST_PAUSE_SECONDS
            )

            continue


        payload = response.json()


        if not payload:

            result = {
                "security_key": security_key,
                "project_ticker": project_ticker,
                "tiingo_symbol": project_ticker,
                "download_start": download_start.date(),
                "download_end_exclusive": (
                    download_end_exclusive.date()
                ),
                "http_status": http_status,
                "rows_returned": 0,
                "first_returned_date": None,
                "last_returned_date": None,
                "missing_expected_columns": None,
                "required_null_count": None,
                "duplicate_dates": None,
                "tiingo_status": "NO_DATA",
                "error_message": (
                    "Tiingo returned an empty "
                    "price dataset."
                ),
            }

            results.append(result)

            print(
                f"[{number}/{total}] "
                f"{project_ticker} -> NO_DATA"
            )

            save_results(results)

            time.sleep(
                REQUEST_PAUSE_SECONDS
            )

            continue


        # ------------------------------------------
        # Convert response
        # ------------------------------------------

        data = pd.DataFrame(
            payload
        )

        data["date"] = pd.to_datetime(
            data["date"],
            utc=True,
            errors="raise",
        )


        # ------------------------------------------
        # Schema validation
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


        # ------------------------------------------
        # Validation decision
        # ------------------------------------------

        if (
            len(data) > 0
            and not missing_columns
            and required_null_count == 0
            and duplicate_dates == 0
        ):

            tiingo_status = (
                "VALIDATED"
            )

            error_message = None

        else:

            tiingo_status = (
                "QUALITY_REVIEW"
            )

            error_message = (
                "Returned data failed one or "
                "more schema/quality checks."
            )


        result = {
            "security_key": security_key,
            "project_ticker": project_ticker,
            "tiingo_symbol": project_ticker,
            "download_start": download_start.date(),
            "download_end_exclusive": (
                download_end_exclusive.date()
            ),
            "http_status": http_status,
            "rows_returned": len(data),
            "first_returned_date": first_date,
            "last_returned_date": last_date,
            "missing_expected_columns": (
                "|".join(missing_columns)
                if missing_columns
                else ""
            ),
            "required_null_count": (
                required_null_count
            ),
            "duplicate_dates": (
                duplicate_dates
            ),
            "tiingo_status": (
                tiingo_status
            ),
            "error_message": (
                error_message
            ),
        }


        results.append(result)


        print(
            f"[{number}/{total}] "
            f"{project_ticker} -> "
            f"{tiingo_status} "
            f"({len(data)} rows, "
            f"{first_date} to {last_date})"
        )


    except Exception as error:

        result = {
            "security_key": security_key,
            "project_ticker": project_ticker,
            "tiingo_symbol": project_ticker,
            "download_start": download_start.date(),
            "download_end_exclusive": (
                download_end_exclusive.date()
            ),
            "http_status": None,
            "rows_returned": 0,
            "first_returned_date": None,
            "last_returned_date": None,
            "missing_expected_columns": None,
            "required_null_count": None,
            "duplicate_dates": None,
            "tiingo_status": "FAILED",
            "error_message": str(error),
        }


        results.append(result)


        print(
            f"[{number}/{total}] "
            f"{project_ticker} -> FAILED"
        )

        print(
            f"    {error}"
        )


    # ----------------------------------------------
    # Save after every ticker
    # ----------------------------------------------

    save_results(results)


    time.sleep(
        REQUEST_PAUSE_SECONDS
    )


# --------------------------------------------------
# Final audit
# --------------------------------------------------

print_section("TIINGO FALLBACK SUMMARY")


audit = pd.DataFrame(
    results
)


# Keep newest result if a ticker was retried.
audit = (
    audit
    .drop_duplicates(
        subset=[
            "security_key",
            "project_ticker",
        ],
        keep="last",
    )
    .reset_index(drop=True)
)


audit.to_csv(
    OUTPUT_FILE,
    index=False,
)


status_counts = (
    audit[
        "tiingo_status"
    ]
    .value_counts()
)


print(
    status_counts.to_string()
)


validated_count = int(
    (
        audit["tiingo_status"]
        == "VALIDATED"
    ).sum()
)


unresolved = audit[
    audit["tiingo_status"]
    != "VALIDATED"
]


print(
    f"\nValidated fallback requests: "
    f"{validated_count}"
)

print(
    f"Still unresolved: "
    f"{len(unresolved)}"
)


# --------------------------------------------------
# Unresolved details
# --------------------------------------------------

print_section("STILL REQUIRING INVESTIGATION")


if unresolved.empty:

    print(
        "None. Every Yahoo failure has "
        "a validated Tiingo fallback."
    )

else:

    print(
        unresolved[
            [
                "security_key",
                "project_ticker",
                "tiingo_status",
                "http_status",
                "error_message",
            ]
        ].to_string(
            index=False
        )
    )


print_section("AUDIT RESULT")


if unresolved.empty:

    print(
        "ALL YAHOO FAILURES HAVE A "
        "VALIDATED TIINGO FALLBACK."
    )

else:

    print(
        f"{len(unresolved)} SYMBOL(S) STILL "
        "REQUIRE INDIVIDUAL RESOLUTION."
    )