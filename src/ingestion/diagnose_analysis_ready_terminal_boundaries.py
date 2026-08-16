from pathlib import Path
import sys

import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ANALYSIS_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "analysis_ready_price_integrity_audit.csv"
)

ANALYSIS_ISSUES_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "analysis_ready_price_integrity_issues.csv"
)

DOWNLOAD_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_download_audit.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "analysis_ready_terminal_boundary_diagnostic.csv"
)


# ============================================================
# EXPECTED FAILURE POPULATION
# ============================================================

EXPECTED_FAILURES = {
    "INFO",
    "ATVI",
    "CTLT",
    "CXO",
    "HES",
    "JNPR",
    "MRO",
    "PXD",
    "TWTR",
    "VAR",
}


EXPECTED_FAILURE_COUNT = 10

EXPECTED_TOTAL_MISSING = 18


# ============================================================
# DISPLAY
# ============================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    280,
)

pd.set_option(
    "display.max_colwidth",
    180,
)


def print_section(title):

    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


# ============================================================
# DATE HELPER
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


# ============================================================
# LOAD FILES
# ============================================================

print_section(
    "ANALYSIS-READY TERMINAL BOUNDARY DIAGNOSTIC"
)


required_files = [
    ANALYSIS_AUDIT_FILE,
    ANALYSIS_ISSUES_FILE,
    DOWNLOAD_AUDIT_FILE,
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


audit = pd.read_csv(
    ANALYSIS_AUDIT_FILE
)


issues = pd.read_csv(
    ANALYSIS_ISSUES_FILE
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


# ============================================================
# 1. FAILURE POPULATION CONTROL
# ============================================================

print_section(
    "1. FAILURE POPULATION CONTROL"
)


failures = audit[
    audit[
        "status"
    ]
    == "FAIL"
].copy()


print(
    f"Current failures: "
    f"{len(failures)}"
)


if (
    len(failures)
    != EXPECTED_FAILURE_COUNT
):

    print(
        "\nERROR:"
    )

    print(
        f"Expected exactly "
        f"{EXPECTED_FAILURE_COUNT} "
        f"failures."
    )

    sys.exit(1)


failure_keys = set(
    failures[
        "security_key"
    ]
)


if (
    failure_keys
    != EXPECTED_FAILURES
):

    print(
        "\nERROR:"
    )

    print(
        "Failure population changed."
    )

    print(
        "\nExpected:"
    )

    print(
        sorted(
            EXPECTED_FAILURES
        )
    )

    print(
        "\nActual:"
    )

    print(
        sorted(
            failure_keys
        )
    )

    sys.exit(1)


total_missing = int(
    failures[
        "missing_expected_sessions"
    ]
    .sum()
)


print(
    f"Total unexplained missing sessions: "
    f"{total_missing}"
)


if (
    total_missing
    != EXPECTED_TOTAL_MISSING
):

    print(
        "\nERROR:"
    )

    print(
        f"Expected "
        f"{EXPECTED_TOTAL_MISSING} "
        f"missing sessions."
    )

    sys.exit(1)


print(
    "\nPASS:"
)

print(
    "The expected 10-security / "
    "18-session failure population "
    "is unchanged."
)


# ============================================================
# 2. BUILD SPY TRADING CALENDAR
# ============================================================

print_section(
    "2. BUILD SPY TRADING CALENDAR"
)


spy_rows = download_audit[
    download_audit[
        "security_key"
    ]
    == "SPY_ETF"
]


if len(spy_rows) != 1:

    print(
        "\nERROR:"
    )

    print(
        "Expected exactly one "
        "SPY_ETF row."
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


if not spy_file.exists():

    print(
        "\nERROR: SPY source file missing:"
    )

    print(
        spy_file
    )

    sys.exit(1)


spy = pd.read_csv(
    spy_file
)


spy_dates = (
    normalize_dates(
        spy[
            "Date"
        ]
    )
    .dropna()
    .drop_duplicates()
    .sort_values()
    .reset_index(drop=True)
)


print(
    f"SPY sessions: "
    f"{len(spy_dates)}"
)

print(
    f"First: "
    f"{spy_dates.min().date()}"
)

print(
    f"Last: "
    f"{spy_dates.max().date()}"
)


# ============================================================
# 3. DIAGNOSE EACH FAILURE
# ============================================================

print_section(
    "3. TERMINAL GAP CLASSIFICATION"
)


diagnostic_records = []


for _, row in failures.iterrows():

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


    effective_start = pd.Timestamp(
        row[
            "effective_expected_start"
        ]
    ).normalize()


    requested_end_exclusive = pd.Timestamp(
        row[
            "requested_end_exclusive"
        ]
    ).normalize()


    first_date = pd.Timestamp(
        row[
            "first_date"
        ]
    ).normalize()


    last_date = pd.Timestamp(
        row[
            "last_date"
        ]
    ).normalize()


    audit_missing_count = int(
        row[
            "missing_expected_sessions"
        ]
    )


    # --------------------------------------------------------
    # Full expected calendar
    # --------------------------------------------------------

    expected_sessions = spy_dates[
        (
            spy_dates
            >= effective_start
        )
        &
        (
            spy_dates
            < requested_end_exclusive
        )
    ]


    # --------------------------------------------------------
    # All SPY sessions AFTER the final observed security date
    # but before the project's requested end.
    #
    # If this count equals the audit's complete missing count,
    # then every missing observation is a terminal-boundary
    # session. No internal or beginning gap remains.
    # --------------------------------------------------------

    terminal_sessions = expected_sessions[
        expected_sessions
        > last_date
    ]


    terminal_count = len(
        terminal_sessions
    )


    # --------------------------------------------------------
    # Sessions before first observation inside accepted range
    # --------------------------------------------------------

    start_sessions = expected_sessions[
        expected_sessions
        < first_date
    ]


    start_count = len(
        start_sessions
    )


    # --------------------------------------------------------
    # The audit has already checked internal coverage.
    #
    # We derive a remainder here:
    #
    # total missing
    # - terminal missing
    # - start missing
    #
    # Any positive remainder means the failure is NOT purely
    # terminal and requires another investigation.
    # --------------------------------------------------------

    internal_or_other_count = (
        audit_missing_count
        - terminal_count
        - start_count
    )


    if internal_or_other_count < 0:

        classification = (
            "COUNT_RECONCILIATION_ERROR"
        )


    elif (
        terminal_count
        == audit_missing_count
        and start_count == 0
        and internal_or_other_count == 0
    ):

        classification = (
            "TERMINAL_ONLY"
        )


    elif (
        start_count > 0
        and terminal_count == 0
        and internal_or_other_count == 0
    ):

        classification = (
            "START_ONLY"
        )


    else:

        classification = (
            "MIXED_OR_INTERNAL"
        )


    terminal_dates_text = "|".join(
        str(
            date.date()
        )
        for date
        in terminal_sessions
    )


    start_dates_text = "|".join(
        str(
            date.date()
        )
        for date
        in start_sessions
    )


    diagnostic_records.append(
        {
            "security_key":
                security_key,

            "project_ticker":
                project_ticker,

            "original_source":
                row[
                    "original_source"
                ],

            "provider_symbol":
                row[
                    "provider_symbol"
                ],

            "effective_expected_start":
                effective_start.date(),

            "first_observed_date":
                first_date.date(),

            "last_observed_date":
                last_date.date(),

            "requested_end_exclusive":
                requested_end_exclusive.date(),

            "audit_missing_sessions":
                audit_missing_count,

            "start_missing_sessions":
                start_count,

            "terminal_missing_sessions":
                terminal_count,

            "internal_or_other_missing_sessions":
                internal_or_other_count,

            "start_missing_dates":
                start_dates_text,

            "terminal_missing_dates":
                terminal_dates_text,

            "classification":
                classification,
        }
    )


diagnostic = pd.DataFrame(
    diagnostic_records
)


diagnostic = (
    diagnostic
    .sort_values(
        [
            "classification",
            "last_observed_date",
            "security_key",
        ]
    )
    .reset_index(drop=True)
)


print(
    diagnostic[
        [
            "security_key",
            "original_source",
            "last_observed_date",
            "requested_end_exclusive",
            "audit_missing_sessions",
            "start_missing_sessions",
            "terminal_missing_sessions",
            "internal_or_other_missing_sessions",
            "classification",
        ]
    ]
    .to_string(
        index=False
    )
)


# ============================================================
# 4. EXACT MISSING DATES
# ============================================================

print_section(
    "4. EXACT TERMINAL MISSING DATES"
)


for _, row in (
    diagnostic.iterrows()
):

    print(
        f"\n{row['security_key']}"
    )

    print(
        "-" * 40
    )

    print(
        f"Last observed security date: "
        f"{row['last_observed_date']}"
    )

    print(
        f"Requested end exclusive:      "
        f"{row['requested_end_exclusive']}"
    )

    print(
        f"Audit missing sessions:       "
        f"{row['audit_missing_sessions']}"
    )

    print(
        f"Terminal missing sessions:    "
        f"{row['terminal_missing_sessions']}"
    )

    print(
        "Terminal dates:"
    )


    dates = str(
        row[
            "terminal_missing_dates"
        ]
    )


    if (
        not dates
        or dates == "nan"
    ):

        print(
            "  None"
        )


    else:

        for date in dates.split("|"):

            print(
                f"  {date}"
            )


    if (
        row[
            "internal_or_other_missing_sessions"
        ]
        != 0
    ):

        print(
            "\nWARNING:"
        )

        print(
            "This security has missing "
            "sessions that are NOT explained "
            "by the terminal boundary."
        )


# ============================================================
# 5. REVIEW ISSUE TABLE DETAILS
# ============================================================

print_section(
    "5. ORIGINAL ISSUE DETAILS"
)


missing_issues = issues[
    issues[
        "issue_type"
    ]
    == "UNEXPLAINED_MISSING_SESSIONS"
]


print(
    missing_issues[
        [
            "security_key",
            "project_ticker",
            "severity",
            "detail",
        ]
    ]
    .to_string(
        index=False
    )
)


# ============================================================
# 6. SAVE DIAGNOSTIC
# ============================================================

print_section(
    "6. SAVE TERMINAL BOUNDARY DIAGNOSTIC"
)


OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


diagnostic.to_csv(
    OUTPUT_FILE,
    index=False,
)


print(
    f"Saved:\n"
    f"{OUTPUT_FILE}"
)


# ============================================================
# 7. CLASSIFICATION SUMMARY
# ============================================================

print_section(
    "7. CLASSIFICATION SUMMARY"
)


print(
    diagnostic[
        "classification"
    ]
    .value_counts()
    .to_string()
)


print(
    "\nTotal terminal sessions:"
)

print(
    int(
        diagnostic[
            "terminal_missing_sessions"
        ]
        .sum()
    )
)


print(
    "\nTotal internal/other sessions:"
)

print(
    int(
        diagnostic[
            "internal_or_other_missing_sessions"
        ]
        .sum()
    )
)


# ============================================================
# 8. TERMINATION-REFERENCE READINESS
# ============================================================

print_section(
    "8. TERMINATION-REFERENCE READINESS"
)


non_terminal = diagnostic[
    diagnostic[
        "classification"
    ]
    != "TERMINAL_ONLY"
]


if non_terminal.empty:

    print(
        "ALL 10 FAILURES ARE "
        "PURE TERMINAL-BOUNDARY CASES."
    )

    print(
        "\nAll 18 currently unexplained "
        "sessions occur strictly after "
        "the final observed price for "
        "their respective securities."
    )

    print(
        "\nThe next appropriate model is "
        "an independent-security market "
        "termination reference."
    )

    print(
        "\nDo not fabricate post-merger "
        "or post-delisting prices."
    )


else:

    print(
        "TERMINATION REFERENCE "
        "IS NOT YET READY."
    )

    print(
        "\nThe following securities "
        "contain non-terminal missing "
        "sessions:"
    )

    print(
        non_terminal[
            [
                "security_key",
                "audit_missing_sessions",
                "start_missing_sessions",
                "terminal_missing_sessions",
                "internal_or_other_missing_sessions",
                "classification",
            ]
        ]
        .to_string(
            index=False
        )
    )

    sys.exit(2)