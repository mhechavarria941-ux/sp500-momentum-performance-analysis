from pathlib import Path
import sys
import time

import pandas as pd
import yfinance as yf
yf.config.debug.hide_exceptions = False

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

INTERIM_DIR = (
    PROJECT_ROOT
    / "data"
    / "interim"
)

AVAILABILITY_OUTPUT = (
    INTERIM_DIR
    / "price_availability_audit.csv"
)

FAILURES_OUTPUT = (
    INTERIM_DIR
    / "price_availability_failures.csv"
)


# --------------------------------------------------
# Probe settings
# --------------------------------------------------

PROBE_DAYS = 45
REQUEST_PAUSE_SECONDS = 0.25
MAX_ATTEMPTS = 2
RETRY_PAUSE_SECONDS = 1.5


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def print_section(title):
    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


# --------------------------------------------------
# Load manifest
# --------------------------------------------------

print_section("YAHOO FINANCE PRICE AVAILABILITY AUDIT")

if not MANIFEST_FILE.exists():

    print(
        "\nERROR: Price download manifest does not exist."
    )

    print(
        "Run build_price_download_manifest.py first."
    )

    sys.exit(1)


manifest = pd.read_csv(
    MANIFEST_FILE
)


# --------------------------------------------------
# Normalize dates
# --------------------------------------------------

date_columns = [
    "ticker_valid_from",
    "ticker_valid_to_exclusive",
    "download_start",
    "download_end_exclusive",
]


for column in date_columns:

    manifest[column] = pd.to_datetime(
        manifest[column],
        format="%Y-%m-%d",
        errors="raise",
    )


# --------------------------------------------------
# 1. Build probe windows
# --------------------------------------------------

print_section("1. BUILD PROBE WINDOWS")


probe_rows = []


for _, row in manifest.iterrows():

    probe_start = row["ticker_valid_from"]

    probe_end = min(
        probe_start
        + pd.Timedelta(days=PROBE_DAYS),
        row["ticker_valid_to_exclusive"],
        row["download_end_exclusive"],
    )


    if probe_end <= probe_start:

        print(
            f"\nERROR: Invalid probe range for "
            f"{row['project_ticker']}."
        )

        print(
            f"Start: {probe_start.date()}"
        )

        print(
            f"End: {probe_end.date()}"
        )

        sys.exit(1)


    probe_rows.append(
        {
            "security_key": row["security_key"],
            "project_ticker": row["project_ticker"],
            "yahoo_ticker": row["yahoo_ticker"],
            "source_kind": row["source_kind"],
            "probe_start": probe_start,
            "probe_end_exclusive": probe_end,
        }
    )


probe_manifest = pd.DataFrame(
    probe_rows
)


print(
    f"Probe requests prepared: "
    f"{len(probe_manifest)}"
)


# --------------------------------------------------
# 2. Query Yahoo Finance
# --------------------------------------------------

print_section("2. TEST YAHOO FINANCE AVAILABILITY")


results = []

total_requests = len(
    probe_manifest
)


for request_number, (_, row) in enumerate(
    probe_manifest.iterrows(),
    start=1,
):

    yahoo_ticker = row["yahoo_ticker"]

    probe_start = row["probe_start"]

    probe_end = row[
        "probe_end_exclusive"
    ]


    status = "FAILED"
    error_message = None
    history = None
    attempts_used = 0


    for attempt in range(
        1,
        MAX_ATTEMPTS + 1,
    ):

        attempts_used = attempt

        try:

            ticker_object = yf.Ticker(
                yahoo_ticker
            )


            history = ticker_object.history(
                start=probe_start,
                end=probe_end,
                interval="1d",
                auto_adjust=False,
                actions=False,
                repair=False,
                keepna=False,
                timeout=15,
            )


            if (
                history is not None
                and not history.empty
            ):

                status = "AVAILABLE"
                error_message = None
                break


            status = "NO_DATA"

            error_message = (
                "Yahoo returned no rows "
                "for the probe window."
            )


        except Exception as error:

            status = "FAILED"

            error_message = str(error)


        if attempt < MAX_ATTEMPTS:

            time.sleep(
                RETRY_PAUSE_SECONDS
            )


    # --------------------------------------------------
    # Summarize returned data
    # --------------------------------------------------

    if (
        history is not None
        and not history.empty
    ):

        returned_rows = len(
            history
        )

        first_date = (
            history.index.min().date()
        )

        last_date = (
            history.index.max().date()
        )

        columns_returned = (
            "|".join(
                str(column)
                for column in history.columns
            )
        )

    else:

        returned_rows = 0
        first_date = None
        last_date = None
        columns_returned = None


    results.append(
        {
            "security_key": row[
                "security_key"
            ],
            "project_ticker": row[
                "project_ticker"
            ],
            "yahoo_ticker": yahoo_ticker,
            "source_kind": row[
                "source_kind"
            ],
            "probe_start": probe_start,
            "probe_end_exclusive": probe_end,
            "status": status,
            "returned_rows": returned_rows,
            "first_returned_date": first_date,
            "last_returned_date": last_date,
            "attempts_used": attempts_used,
            "columns_returned": columns_returned,
            "error_message": error_message,
        }
    )


    # --------------------------------------------------
    # Progress reporting
    # --------------------------------------------------

    if status != "AVAILABLE":

        print(
            f"[{request_number}/{total_requests}] "
            f"{row['project_ticker']} "
            f"({yahoo_ticker}) -> {status}"
        )

        if error_message:

            print(
                f"    {error_message}"
            )


    elif (
        request_number % 25 == 0
        or request_number
        == total_requests
    ):

        print(
            f"[{request_number}/{total_requests}] "
            "availability checks completed..."
        )


    time.sleep(
        REQUEST_PAUSE_SECONDS
    )


# --------------------------------------------------
# 3. Create audit results
# --------------------------------------------------

availability = pd.DataFrame(
    results
)


failures = availability[
    availability["status"]
    != "AVAILABLE"
].copy()


# --------------------------------------------------
# 4. Summary
# --------------------------------------------------

print_section("3. AVAILABILITY SUMMARY")


status_counts = (
    availability[
        "status"
    ]
    .value_counts()
)

print(
    status_counts.to_string()
)


available_count = int(
    (
        availability["status"]
        == "AVAILABLE"
    ).sum()
)

failure_count = len(
    failures
)


print(
    f"\nTotal requests: "
    f"{len(availability)}"
)

print(
    f"Available: "
    f"{available_count}"
)

print(
    f"Requires investigation: "
    f"{failure_count}"
)


# --------------------------------------------------
# 5. Failure details
# --------------------------------------------------

print_section("4. SYMBOLS REQUIRING INVESTIGATION")


if failures.empty:

    print(
        "PASS: Every manifest symbol returned "
        "historical price data."
    )


else:

    print(
        failures[
            [
                "security_key",
                "project_ticker",
                "yahoo_ticker",
                "probe_start",
                "probe_end_exclusive",
                "status",
                "error_message",
            ]
        ].to_string(
            index=False
        )
    )


# --------------------------------------------------
# 6. Column audit
# --------------------------------------------------

print_section("5. RETURNED COLUMN PATTERNS")


available = availability[
    availability["status"]
    == "AVAILABLE"
]


column_patterns = (
    available[
        "columns_returned"
    ]
    .value_counts(
        dropna=False
    )
)


print(
    column_patterns.to_string()
)


# --------------------------------------------------
# 7. Save outputs
# --------------------------------------------------

print_section("6. SAVE AUDIT OUTPUTS")


INTERIM_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


availability.to_csv(
    AVAILABILITY_OUTPUT,
    index=False,
    date_format="%Y-%m-%d",
)


print(
    f"Availability audit saved:\n"
    f"{AVAILABILITY_OUTPUT}"
)


if failures.empty:

    if FAILURES_OUTPUT.exists():
        FAILURES_OUTPUT.unlink()

    print(
        "\nNo failure report required."
    )


else:

    failures.to_csv(
        FAILURES_OUTPUT,
        index=False,
        date_format="%Y-%m-%d",
    )

    print(
        f"\nFailure report saved:\n"
        f"{FAILURES_OUTPUT}"
    )


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section("AUDIT RESULT")


print(
    f"Yahoo requests tested: "
    f"{len(availability)}"
)

print(
    f"Available symbols: "
    f"{available_count}"
)

print(
    f"Symbols requiring investigation: "
    f"{failure_count}"
)


if failure_count == 0:

    print(
        "\nPRICE AVAILABILITY AUDIT PASSED."
    )

    sys.exit(0)


else:

    print(
        "\nPRICE AVAILABILITY AUDIT "
        "REQUIRES SYMBOL RESOLUTION."
    )

    print(
        "Do not begin the full historical "
        "download until failed symbols have "
        "been investigated."
    )

    sys.exit(2)