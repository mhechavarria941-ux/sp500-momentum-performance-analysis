from pathlib import Path
import sys

import pandas as pd


# ==================================================
# PROJECT PATHS
# ==================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INTEGRITY_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_integrity_audit.csv"
)

ISSUES_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_integrity_issues.csv"
)


# ==================================================
# DISPLAY SETTINGS
# ==================================================

pd.set_option(
    "display.max_columns",
    None,
)

pd.set_option(
    "display.width",
    240,
)

pd.set_option(
    "display.max_colwidth",
    200,
)


# ==================================================
# HELPERS
# ==================================================

def print_section(title):

    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


def print_float_table(dataframe):

    print(
        dataframe.to_string(
            index=True,
            float_format=lambda value:
                f"{value:.15f}",
        )
    )


# ==================================================
# LOAD AUDIT FILES
# ==================================================

print_section(
    "MARKET PRICE INTEGRITY EXCEPTION DIAGNOSTIC"
)


if not INTEGRITY_FILE.exists():

    print(
        "\nERROR: Integrity audit not found:"
    )

    print(
        INTEGRITY_FILE
    )

    sys.exit(1)


if not ISSUES_FILE.exists():

    print(
        "\nERROR: Integrity issue table not found:"
    )

    print(
        ISSUES_FILE
    )

    sys.exit(1)


integrity = pd.read_csv(
    INTEGRITY_FILE
)

issues = pd.read_csv(
    ISSUES_FILE
)


# ==================================================
# 1. UA AUDIT RECORD
# ==================================================

print_section(
    "1. UA INTEGRITY RECORD"
)


ua_rows = integrity[
    (
        integrity["security_key"] == "UA"
    )
    &
    (
        integrity["project_ticker"] == "UA"
    )
]


if len(ua_rows) != 1:

    print(
        "ERROR: Expected exactly one UA row."
    )

    print(
        f"Rows found: {len(ua_rows)}"
    )

    sys.exit(1)


ua_record = ua_rows.iloc[0]


print(
    ua_record[
        [
            "security_key",
            "project_ticker",
            "provider_symbol",
            "source",
            "status",
            "rows",
            "first_date",
            "last_date",
            "invalid_high_rows",
            "invalid_low_rows",
            "critical_issues",
            "flags",
            "output_file",
        ]
    ].to_string()
)


# ==================================================
# 2. LOAD UA RAW YAHOO FILE
# ==================================================

print_section(
    "2. LOAD UA RAW YAHOO FILE"
)


ua_file = (
    PROJECT_ROOT
    / str(
        ua_record[
            "output_file"
        ]
    )
)


print(
    f"File:\n{ua_file}"
)


if not ua_file.exists():

    print(
        "\nERROR: UA raw file does not exist."
    )

    sys.exit(1)


ua = pd.read_csv(
    ua_file
)


print(
    f"\nRows loaded: {len(ua)}"
)

print(
    "\nColumns:"
)

print(
    ua.columns.tolist()
)


required_columns = [
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
]


missing_columns = [
    column
    for column in required_columns
    if column not in ua.columns
]


if missing_columns:

    print(
        "\nERROR: Missing required columns:"
    )

    print(
        missing_columns
    )

    sys.exit(1)


# ==================================================
# 3. PREPARE UA VALUES
# ==================================================

ua["Date"] = pd.to_datetime(
    ua["Date"],
    errors="raise",
)


numeric_columns = [
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
]


for column in numeric_columns:

    ua[column] = pd.to_numeric(
        ua[column],
        errors="coerce",
    )


# Same logical test used by the integrity audit:
#
# Low must be <= Open, High, and Close.

ua["_minimum_ohc"] = (
    ua[
        [
            "Open",
            "High",
            "Close",
        ]
    ]
    .min(
        axis=1
    )
)


ua["_low_excess"] = (
    ua["Low"]
    - ua["_minimum_ohc"]
)


ua["_low_excess_bps"] = (
    ua["_low_excess"]
    / ua["_minimum_ohc"]
    * 10_000
)


invalid_low = ua[
    ua["Low"]
    > ua["_minimum_ohc"]
].copy()


# ==================================================
# 4. EXACT UA INVALID-LOW OBSERVATION
# ==================================================

print_section(
    "3. EXACT UA INVALID-LOW OBSERVATION"
)


print(
    f"Invalid-low rows found: "
    f"{len(invalid_low)}"
)


if invalid_low.empty:

    print(
        "\nThe current raw file no longer "
        "reproduces the INVALID_LOW result."
    )

    print(
        "If this occurs, we will reconcile "
        "the audit with the current raw file."
    )


else:

    display_columns = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
        "_minimum_ohc",
        "_low_excess",
        "_low_excess_bps",
    ]


    print_float_table(
        invalid_low[
            display_columns
        ]
    )


# ==================================================
# 5. HIGH-PRECISION DIFFERENCE ANALYSIS
# ==================================================

print_section(
    "4. UA DIFFERENCE MAGNITUDE"
)


if not invalid_low.empty:

    maximum_absolute_excess = float(
        invalid_low[
            "_low_excess"
        ].max()
    )


    maximum_bps_excess = float(
        invalid_low[
            "_low_excess_bps"
        ].max()
    )


    print(
        "Maximum Low excess above the "
        "minimum of Open/High/Close:"
    )

    print(
        f"${maximum_absolute_excess:.15f}"
    )


    print(
        "\nMaximum relative excess:"
    )

    print(
        f"{maximum_bps_excess:.15f} basis points"
    )


    # --------------------------------------------------
    # Diagnostic only.
    #
    # We are NOT automatically modifying the audit
    # based on this threshold.
    # --------------------------------------------------

    reference_price = float(
        invalid_low.iloc[0][
            "_minimum_ohc"
        ]
    )


    diagnostic_tolerance = max(
        0.000001,
        abs(reference_price)
        * 0.00000001,
    )


    print(
        "\nDiagnostic floating-point tolerance:"
    )

    print(
        f"${diagnostic_tolerance:.15f}"
    )


    if (
        maximum_absolute_excess
        <= diagnostic_tolerance
    ):

        print(
            "\nDIAGNOSTIC RESULT:"
        )

        print(
            "FLOATING_POINT_TOLERANCE_CANDIDATE"
        )

        print(
            "\nThe violation is small enough "
            "to plausibly result from numeric "
            "representation or source rounding."
        )

        print(
            "\nWe will still inspect the source "
            "row before changing the audit rule."
        )


    else:

        print(
            "\nDIAGNOSTIC RESULT:"
        )

        print(
            "SUBSTANTIVE_OHLC_DIFFERENCE"
        )

        print(
            "\nThe Low discrepancy is too large "
            "to dismiss as ordinary floating-point "
            "representation."
        )


# ==================================================
# 6. SURROUNDING UA OBSERVATIONS
# ==================================================

print_section(
    "5. UA SURROUNDING OBSERVATIONS"
)


if invalid_low.empty:

    print(
        "None to display."
    )


else:

    for invalid_index in invalid_low.index:

        start_index = max(
            0,
            invalid_index - 3,
        )

        end_index = min(
            len(ua),
            invalid_index + 4,
        )


        context = ua.iloc[
            start_index:end_index
        ][
            [
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Adj Close",
                "Volume",
            ]
        ]


        print(
            f"\nContext around raw row "
            f"{invalid_index}:"
        )

        print_float_table(
            context
        )


# ==================================================
# 7. CORPORATE ACTION CONTEXT
# ==================================================

print_section(
    "6. UA CORPORATE ACTION CONTEXT"
)


action_columns = [
    column
    for column in [
        "Dividends",
        "Stock Splits",
        "Capital Gains",
    ]
    if column in ua.columns
]


if not action_columns:

    print(
        "No Yahoo corporate-action columns "
        "are available in this raw file."
    )


elif invalid_low.empty:

    print(
        "Corporate-action columns exist, "
        "but there is no current invalid row "
        "to inspect."
    )


else:

    for invalid_index in invalid_low.index:

        start_index = max(
            0,
            invalid_index - 3,
        )

        end_index = min(
            len(ua),
            invalid_index + 4,
        )


        columns = [
            "Date",
        ] + action_columns


        print(
            f"\nCorporate actions around "
            f"raw row {invalid_index}:"
        )

        print(
            ua.iloc[
                start_index:end_index
            ][
                columns
            ]
            .to_string(
                index=False
            )
        )


# ==================================================
# 8. NON-BLOCKING REVIEW ITEM
# ==================================================

print_section(
    "7. NON-BLOCKING REVIEW ITEMS"
)


review_items = issues[
    issues[
        "severity"
    ]
    == "REVIEW"
]


if review_items.empty:

    print(
        "None."
    )


else:

    print(
        review_items[
            [
                "security_key",
                "project_ticker",
                "provider_symbol",
                "source",
                "issue_type",
                "detail",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ==================================================
# 9. INTERNAL TRADING GAP SPECIFICALLY
# ==================================================

print_section(
    "8. INTERNAL TRADING GAP REVIEW"
)


internal_gap_items = issues[
    issues[
        "issue_type"
    ]
    == "INTERNAL_TRADING_GAPS"
]


if internal_gap_items.empty:

    print(
        "None."
    )


else:

    print(
        internal_gap_items[
            [
                "security_key",
                "project_ticker",
                "provider_symbol",
                "source",
                "severity",
                "detail",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ==================================================
# 10. DISCA COVERAGE PROBLEM
# ==================================================

print_section(
    "9. DISCA COVERAGE DIAGNOSTIC"
)


disca_rows = integrity[
    (
        integrity[
            "security_key"
        ]
        == "DISCA"
    )
    &
    (
        integrity[
            "project_ticker"
        ]
        == "DISCA"
    )
]


if len(disca_rows) != 1:

    print(
        "ERROR: Expected exactly one "
        "DISCA audit row."
    )


else:

    disca_record = (
        disca_rows.iloc[0]
    )


    print(
        disca_record[
            [
                "security_key",
                "project_ticker",
                "provider_symbol",
                "source",
                "status",
                "requested_start",
                "requested_end_exclusive",
                "rows",
                "first_date",
                "last_date",
                "start_missing_sessions",
                "end_missing_sessions",
                "internal_missing_sessions",
                "flags",
                "output_file",
            ]
        ]
        .to_string()
    )


    disca_file = (
        PROJECT_ROOT
        / str(
            disca_record[
                "output_file"
            ]
        )
    )


    if disca_file.exists():

        disca = pd.read_csv(
            disca_file
        )


        print(
            "\nRaw DISCA source rows:"
        )

        print(
            disca.to_string(
                index=False
            )
        )


# ==================================================
# 11. BLOCKING REVIEW SUMMARY
# ==================================================

print_section(
    "10. BLOCKING REVIEW SUMMARY"
)


blocking = integrity[
    integrity[
        "status"
    ]
    == "REVIEW_BLOCKING"
]


print(
    f"Blocking requests: "
    f"{len(blocking)}"
)


if not blocking.empty:

    print(
        blocking[
            [
                "security_key",
                "project_ticker",
                "source",
                "rows",
                "requested_start",
                "first_date",
                "start_missing_sessions",
                "flags",
            ]
        ]
        .sort_values(
            "start_missing_sessions",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )


# ==================================================
# FINAL DIAGNOSTIC STATUS
# ==================================================

print_section(
    "DIAGNOSTIC COMPLETE"
)


print(
    "No raw market-price files were modified."
)

print(
    "\nNext decisions:"
)

print(
    "1. Determine whether UA is numeric "
    "tolerance or a substantive Yahoo error."
)

print(
    "2. Resolve DISCA's incomplete historical "
    "provider coverage."
)

print(
    "3. Convert verified new-security inception "
    "gaps into documented expected boundaries."
)

print(
    "4. Investigate the single internal "
    "trading-gap review."
)