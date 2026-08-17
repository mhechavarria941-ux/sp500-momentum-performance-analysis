from pathlib import Path
import re
import sys

import pandas as pd


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

TERMINATION_REFERENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "securities"
    / "security_market_terminations.csv"
)

PRICE_EXCEPTION_REFERENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "price_exception_resolutions.csv"
)

INFO_ACTION_REFERENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "info_corporate_actions.csv"
)

BOUNDARY_REFERENCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "market_inception_boundary_resolutions.csv"
)

RESOLVED_ROWS_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_exception_resolved_rows.csv"
)

DISCA_COMPOSITE_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "disca_tiingo_identity_composite.csv"
)

VLTO_COMPOSITE_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "vlto_market_boundary_composite.csv"
)

INFO_ADJUSTED_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "info_adjusted_price_reconstruction.csv"
)

STANDARDIZED_PRICE_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "standardized_price_history.csv.gz"
)

STANDARDIZED_MANIFEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "standardized_price_history_manifest.csv"
)

OUTPUT_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "analysis_ready_price_integrity_audit.csv"
)

OUTPUT_ISSUES_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "analysis_ready_price_integrity_issues.csv"
)

OUTPUT_TRANSFORMATIONS_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "analysis_ready_price_transformations.csv"
)


EXPECTED_REQUEST_COUNT = 596


# ============================================================
# EXPECTED REFERENCE POPULATIONS
# ============================================================

EXPECTED_PRICE_EXCEPTIONS = {
    "UA",
    "FISV",
    "DISCA",
}

EXPECTED_BOUNDARY_RESOLUTIONS = {
    "CARR",
    "OTIS",
    "GEHC",
    "VLTO",
}

EXPECTED_INCEPTION_COUNT = 17

EXPECTED_TERMINATIONS = {
    "ATVI",
    "CTLT",
    "CXO",
    "HES",
    "INFO",
    "JNPR",
    "MRO",
    "PXD",
    "TWTR",
    "VAR",
}

EXPECTED_TERMINAL_ACTION_COUNTS = {
    "EXCLUDE_PROVIDER_ARTIFACT": 8,
    "KEEP": 2,
}


# ============================================================
EXPECTED_INFO_ACTION_COUNT = 9
EXPECTED_INFO_DIVIDEND_TOTAL = 1.68


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
    160,
)


def print_section(title):

    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


# ============================================================
# DATE HELPERS
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
# INVESTING.COM HELPERS
# ============================================================

def parse_investing_number(value):

    if pd.isna(value):
        return None

    text = (
        str(value)
        .strip()
        .replace(",", "")
    )

    if text in {
        "",
        "-",
        "N/A",
    }:
        return None

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
            number
            * multiplier
        )
    )


# ============================================================
# COMMON SOURCE LOADERS
# ============================================================

def load_yahoo(file_path):

    raw = pd.read_csv(
        file_path
    )

    required = {
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
    }

    missing = (
        required
        - set(raw.columns)
    )

    if missing:

        raise RuntimeError(
            "Missing Yahoo columns: "
            f"{sorted(missing)}"
        )


    dividends = (
        pd.to_numeric(
            raw["Dividends"],
            errors="coerce",
        )
        if "Dividends" in raw.columns
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
        if "Stock Splits" in raw.columns
        else pd.Series(
            0.0,
            index=raw.index,
        )
    )


    # Yahoo uses 0 to represent no split.
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

            "dividend":
                dividends,

            "split_factor":
                split_factor,

            "source_component":
                "Yahoo Finance",
        }
    )


    return common


def load_tiingo(file_path):

    raw = pd.read_csv(
        file_path
    )

    required = {
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
        required
        - set(raw.columns)
    )

    if missing:

        raise RuntimeError(
            "Missing Tiingo columns: "
            f"{sorted(missing)}"
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
                "Tiingo",
        }
    )


    return common


def load_investing(file_path):

    raw = pd.read_csv(
        file_path
    )

    required = {
        "Date",
        "Price",
        "Open",
        "High",
        "Low",
        "Vol.",
        "Change %",
    }

    missing = (
        required
        - set(raw.columns)
    )

    if missing:

        raise RuntimeError(
            "Missing Investing.com columns: "
            f"{sorted(missing)}"
        )


    common = pd.DataFrame(
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

            # Deliberately unresolved at this stage.
            "adj_close":
                pd.NA,

            "volume":
                raw["Vol."]
                .apply(
                    parse_investing_volume
                ),

            # We are NOT inventing dividend/split
            # values for this source.
            "dividend":
                pd.NA,

            "split_factor":
                pd.NA,

            "source_component":
                "Investing.com INFO_OLD",
        }
    )


    return common


def load_info_adjusted(file_path):

    raw = pd.read_csv(
        file_path
    )

    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "dividend",
        "split_factor",
        "adjustment_factor",
        "source_component",
    }

    missing = (
        required
        - set(raw.columns)
    )

    if missing:
        raise RuntimeError(
            "INFO reconstructed series missing columns: "
            f"{sorted(missing)}"
        )

    raw = raw.copy()

    raw["date"] = normalize_dates(
        raw["date"]
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "dividend",
        "split_factor",
        "adjustment_factor",
    ]

    for column in numeric_columns:
        raw[column] = pd.to_numeric(
            raw[column],
            errors="coerce",
        )

    if len(raw) != 543:
        raise RuntimeError(
            "Expected 543 reconstructed INFO rows; "
            f"found {len(raw)}."
        )

    if (
        raw["date"].min()
        != pd.Timestamp("2020-01-02")
    ):
        raise RuntimeError(
            "Unexpected reconstructed INFO first date."
        )

    if (
        raw["date"].max()
        != pd.Timestamp("2022-02-25")
    ):
        raise RuntimeError(
            "Unexpected reconstructed INFO last date."
        )

    if (
        raw["date"].isna().any()
        or raw["date"].duplicated().any()
    ):
        raise RuntimeError(
            "Reconstructed INFO dates are invalid "
            "or duplicated."
        )

    if (
        raw[numeric_columns]
        .isna()
        .any()
        .any()
    ):
        raise RuntimeError(
            "Reconstructed INFO numeric fields "
            "contain nulls."
        )

    dividend_events = int(
        (
            raw["dividend"]
            > 0
        ).sum()
    )

    if dividend_events != EXPECTED_INFO_ACTION_COUNT:
        raise RuntimeError(
            "Reconstructed INFO must contain "
            "nine dividends."
        )

    if (
        abs(
            float(
                raw["dividend"].sum()
            )
            - EXPECTED_INFO_DIVIDEND_TOTAL
        )
        > 1e-12
    ):
        raise RuntimeError(
            "Reconstructed INFO dividends "
            "must total $1.68."
        )

    if (
        raw["split_factor"]
        .ne(1.0)
        .any()
    ):
        raise RuntimeError(
            "Unexpected INFO split factor."
        )

    if not (
        raw["adjustment_factor"]
        .between(
            0,
            1,
            inclusive="both",
        )
        .all()
    ):
        raise RuntimeError(
            "INFO adjustment factors fall "
            "outside (0, 1]."
        )

    ordered = (
        raw
        .sort_values("date")
        .reset_index(drop=True)
    )

    factor_changes = (
        ordered["adjustment_factor"]
        .diff()
        .dropna()
    )

    if (
        factor_changes
        < -1e-12
    ).any():
        raise RuntimeError(
            "INFO adjustment factors decrease "
            "moving forward."
        )

    calculated = (
        ordered["close"]
        * ordered["adjustment_factor"]
    )

    differences = (
        ordered["adj_close"]
        - calculated
    ).abs()

    if not (
        differences
        <= 1e-8
    ).all():
        raise RuntimeError(
            "INFO adjusted-close formula "
            "validation failed."
        )

    terminal = ordered.iloc[-1]

    if (
        abs(
            float(
                terminal["adjustment_factor"]
            )
            - 1.0
        )
        > 1e-12
    ):
        raise RuntimeError(
            "INFO terminal adjustment factor "
            "is not 1.0."
        )

    common = ordered[
        [
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "dividend",
            "split_factor",
            "source_component",
        ]
    ].copy()

    return common


def load_disca_composite(file_path):

    raw = pd.read_csv(
        file_path
    )

    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjClose",
        "divCash",
        "splitFactor",
        "source_component",
    }

    missing = (
        required
        - set(raw.columns)
    )

    if missing:

        raise RuntimeError(
            "DISCA composite missing columns: "
            f"{sorted(missing)}"
        )


    return pd.DataFrame(
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
                raw[
                    "source_component"
                ].astype(str),
        }
    )


def load_vlto_composite(file_path):

    raw = pd.read_csv(
        file_path
    )

    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "dividend",
        "split_factor",
        "source_component",
    }

    missing = (
        required
        - set(raw.columns)
    )

    if missing:

        raise RuntimeError(
            "VLTO composite missing columns: "
            f"{sorted(missing)}"
        )


    common = raw[
        [
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "dividend",
            "split_factor",
            "source_component",
        ]
    ].copy()


    common[
        "date"
    ] = normalize_dates(
        common[
            "date"
        ]
    )


    for column in [
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "dividend",
        "split_factor",
    ]:

        common[
            column
        ] = pd.to_numeric(
            common[
                column
            ],
            errors="coerce",
        )


    return common


# ============================================================
# ISSUE RECORDS
# ============================================================

issue_records = []
transformation_records = []


def add_issue(
    security_key,
    project_ticker,
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

            "severity":
                severity,

            "issue_type":
                issue_type,

            "detail":
                detail,
        }
    )


def add_transformation(
    security_key,
    project_ticker,
    transformation,
    detail,
):

    transformation_records.append(
        {
            "security_key":
                security_key,

            "project_ticker":
                project_ticker,

            "transformation":
                transformation,

            "detail":
                detail,
        }
    )


# ============================================================
# LOAD REQUIRED REFERENCES
# ============================================================

print_section(
    "ANALYSIS-READY PRICE INTEGRITY AUDIT"
)


required_files = [
    DOWNLOAD_AUDIT_FILE,
    INCEPTION_REFERENCE_FILE,
    TERMINATION_REFERENCE_FILE,
    PRICE_EXCEPTION_REFERENCE_FILE,
    INFO_ACTION_REFERENCE_FILE,
    BOUNDARY_REFERENCE_FILE,
    RESOLVED_ROWS_FILE,
    DISCA_COMPOSITE_FILE,
    VLTO_COMPOSITE_FILE,
    INFO_ADJUSTED_FILE,
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


inceptions = pd.read_csv(
    INCEPTION_REFERENCE_FILE
)


terminations = pd.read_csv(
    TERMINATION_REFERENCE_FILE
)


price_exceptions = pd.read_csv(
    PRICE_EXCEPTION_REFERENCE_FILE
)


info_actions = pd.read_csv(
    INFO_ACTION_REFERENCE_FILE
)


boundary_resolutions = pd.read_csv(
    BOUNDARY_REFERENCE_FILE
)


resolved_rows = pd.read_csv(
    RESOLVED_ROWS_FILE
)


# ============================================================
# 1. REFERENCE CONTROL GATE
# ============================================================

print_section(
    "1. REFERENCE CONTROL GATE"
)


if len(
    download_audit
) != EXPECTED_REQUEST_COUNT:

    print(
        "\nERROR:"
    )

    print(
        f"Expected {EXPECTED_REQUEST_COUNT} "
        f"requests but found "
        f"{len(download_audit)}."
    )

    sys.exit(1)


print(
    f"Download requests: "
    f"{len(download_audit)}"
)


if len(
    inceptions
) != EXPECTED_INCEPTION_COUNT:

    print(
        "\nERROR:"
    )

    print(
        "Expected exactly 17 "
        "security-inception records."
    )

    sys.exit(1)


print(
    f"Security inception records: "
    f"{len(inceptions)}"
)


required_termination_columns = {
    "security_key",
    "project_ticker",
    "last_valid_trading_date",
    "accepted_effective_end_exclusive",
    "provider_terminal_date",
    "provider_terminal_action",
    "termination_basis",
    "evidence_status",
}


missing_termination_columns = (
    required_termination_columns
    - set(
        terminations.columns
    )
)


if missing_termination_columns:

    print(
        "\nERROR:"
    )

    print(
        "Termination reference is missing "
        "required columns:"
    )

    print(
        sorted(
            missing_termination_columns
        )
    )

    sys.exit(1)


termination_set = set(
    terminations[
        "security_key"
    ]
)


if (
    termination_set
    != EXPECTED_TERMINATIONS
):

    print(
        "\nERROR:"
    )

    print(
        "Termination-reference population "
        "does not match the ten validated "
        "terminal cases."
    )

    print(
        sorted(
            termination_set
        )
    )

    sys.exit(1)


if (
    terminations[
        [
            "security_key",
            "project_ticker",
        ]
    ]
    .duplicated()
    .any()
):

    print(
        "\nERROR:"
    )

    print(
        "Duplicate security/project pairs "
        "exist in the termination reference."
    )

    sys.exit(1)


terminal_action_counts = (
    terminations[
        "provider_terminal_action"
    ]
    .value_counts()
    .to_dict()
)


if (
    terminal_action_counts
    != EXPECTED_TERMINAL_ACTION_COUNTS
):

    print(
        "\nERROR:"
    )

    print(
        "Termination action counts changed."
    )

    print(
        terminal_action_counts
    )

    sys.exit(1)


allowed_evidence_statuses = {
    "VERIFIED",
    "CORROBORATED",
}


if (
    ~terminations[
        "evidence_status"
    ]
    .isin(
        allowed_evidence_statuses
    )
).any():

    print(
        "\nERROR:"
    )

    print(
        "Termination evidence contains an "
        "unaccepted status."
    )

    sys.exit(1)


print(
    "Security terminations: "
    "10 — VERIFIED/CORROBORATED"
)

print(
    "Terminal provider actions: "
    "8 exclusions / 2 retained"
)


price_exception_set = set(
    price_exceptions[
        "security_key"
    ]
)


if (
    price_exception_set
    != EXPECTED_PRICE_EXCEPTIONS
):

    print(
        "\nERROR:"
    )

    print(
        "Price-exception population "
        "does not match UA/FISV/DISCA."
    )

    print(
        sorted(
            price_exception_set
        )
    )

    sys.exit(1)


if (
    price_exceptions[
        "resolution_status"
    ]
    .ne(
        "VALIDATED"
    )
    .any()
):

    print(
        "\nERROR:"
    )

    print(
        "Not every price exception "
        "is VALIDATED."
    )

    sys.exit(1)


print(
    "Price exceptions: "
    "UA, FISV, DISCA — VALIDATED"
)


required_info_action_columns = {
    "security_key",
    "project_ticker",
    "event_type",
    "ex_date",
    "cash_amount",
    "split_factor",
    "evidence_status",
    "resolution_status",
}

missing_info_action_columns = (
    required_info_action_columns
    - set(info_actions.columns)
)

if missing_info_action_columns:
    print("\nERROR:")
    print(
        "INFO corporate-action reference is "
        "missing required columns:"
    )
    print(
        sorted(
            missing_info_action_columns
        )
    )
    sys.exit(1)

info_actions["cash_amount"] = pd.to_numeric(
    info_actions["cash_amount"],
    errors="coerce",
)

info_actions["split_factor"] = pd.to_numeric(
    info_actions["split_factor"],
    errors="coerce",
)

info_actions["ex_date"] = normalize_dates(
    info_actions["ex_date"]
)

info_action_gate_failed = (
    len(info_actions)
    != EXPECTED_INFO_ACTION_COUNT
    or info_actions[
        "security_key"
    ].ne("INFO").any()
    or info_actions[
        "project_ticker"
    ].ne("INFO").any()
    or info_actions[
        "event_type"
    ].ne("CASH_DIVIDEND").any()
    or info_actions[
        "resolution_status"
    ].ne("VALIDATED").any()
    or info_actions[
        "evidence_status"
    ].ne("CORROBORATED").any()
    or info_actions[
        "split_factor"
    ].ne(1.0).any()
    or info_actions[
        "ex_date"
    ].isna().any()
    or info_actions[
        "ex_date"
    ].duplicated().any()
    or abs(
        float(
            info_actions[
                "cash_amount"
            ].sum()
        )
        - EXPECTED_INFO_DIVIDEND_TOTAL
    )
    > 1e-12
)

if info_action_gate_failed:
    print("\nERROR:")
    print(
        "INFO corporate-action reference failed "
        "its validated-control gate."
    )
    sys.exit(1)

print(
    "INFO corporate actions: "
    "9 dividends / $1.68 — VALIDATED"
)


boundary_set = set(
    boundary_resolutions[
        "security_key"
    ]
)


if (
    boundary_set
    != EXPECTED_BOUNDARY_RESOLUTIONS
):

    print(
        "\nERROR:"
    )

    print(
        "Boundary-resolution population "
        "does not match "
        "CARR/OTIS/GEHC/VLTO."
    )

    print(
        sorted(
            boundary_set
        )
    )

    sys.exit(1)


if (
    boundary_resolutions[
        "resolution_status"
    ]
    .ne(
        "VALIDATED"
    )
    .any()
):

    print(
        "\nERROR:"
    )

    print(
        "Not every boundary resolution "
        "is VALIDATED."
    )

    sys.exit(1)


print(
    "Boundary resolutions: "
    "CARR, OTIS, GEHC, VLTO — VALIDATED"
)


resolved_row_keys = set(
    resolved_rows[
        "security_key"
    ]
)


if (
    resolved_row_keys
    != {
        "UA",
        "FISV",
    }
):

    print(
        "\nERROR:"
    )

    print(
        "Resolved-row file should contain "
        "exactly UA and FISV."
    )

    print(
        sorted(
            resolved_row_keys
        )
    )

    sys.exit(1)


print(
    "PASS:"
)

print(
    "All transformation references "
    "are present and validated."
)


# ============================================================
# NORMALIZE REFERENCE DATES
# ============================================================

inceptions[
    "market_inception_date"
] = pd.to_datetime(
    inceptions[
        "market_inception_date"
    ],
    errors="raise",
)


for date_column in [
    "last_valid_trading_date",
    "accepted_effective_end_exclusive",
    "provider_terminal_date",
]:

    terminations[
        date_column
    ] = pd.to_datetime(
        terminations[
            date_column
        ],
        errors="raise",
    )


invalid_termination_boundaries = (
    terminations[
        "accepted_effective_end_exclusive"
    ]
    <= terminations[
        "last_valid_trading_date"
    ]
)


if invalid_termination_boundaries.any():

    print(
        "\nERROR:"
    )

    print(
        "A termination end-exclusive date "
        "does not occur after the last valid "
        "trading date."
    )

    sys.exit(1)


exclude_actions = (
    terminations[
        "provider_terminal_action"
    ]
    == "EXCLUDE_PROVIDER_ARTIFACT"
)


keep_actions = (
    terminations[
        "provider_terminal_action"
    ]
    == "KEEP"
)


if (
    terminations.loc[
        exclude_actions,
        "provider_terminal_date",
    ]
    .ne(
        terminations.loc[
            exclude_actions,
            "accepted_effective_end_exclusive",
        ]
    )
    .any()
):

    print(
        "\nERROR:"
    )

    print(
        "Every excluded provider artifact "
        "must occur exactly on the accepted "
        "end-exclusive boundary."
    )

    sys.exit(1)


if (
    terminations.loc[
        keep_actions,
        "provider_terminal_date",
    ]
    .ne(
        terminations.loc[
            keep_actions,
            "last_valid_trading_date",
        ]
    )
    .any()
):

    print(
        "\nERROR:"
    )

    print(
        "Every retained provider terminal "
        "date must equal the last valid "
        "trading date."
    )

    sys.exit(1)


boundary_resolutions[
    "accepted_effective_start"
] = pd.to_datetime(
    boundary_resolutions[
        "accepted_effective_start"
    ],
    errors="raise",
)


resolved_rows[
    "date"
] = pd.to_datetime(
    resolved_rows[
        "date"
    ],
    errors="raise",
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


if len(
    spy_rows
) != 1:

    print(
        "\nERROR:"
    )

    print(
        "Expected exactly one SPY_ETF row."
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
        "\nERROR: SPY file missing:"
    )

    print(
        spy_file
    )

    sys.exit(1)


spy_raw = pd.read_csv(
    spy_file
)


spy_dates = (
    normalize_dates(
        spy_raw[
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
    f"First session: "
    f"{spy_dates.min().date()}"
)

print(
    f"Last session: "
    f"{spy_dates.max().date()}"
)

print(
    "PASS: SPY calendar ready."
)


# ============================================================
# 3. AUDIT ALL 596 ANALYSIS-READY REQUESTS
# ============================================================

print_section(
    "3. AUDIT ALL ANALYSIS-READY REQUESTS"
)


audit_records = []
standardized_frames = []


for request_number, (_, request) in enumerate(
    download_audit.iterrows(),
    start=1,
):

    security_key = str(
        request[
            "security_key"
        ]
    )

    project_ticker = str(
        request[
            "project_ticker"
        ]
    )

    source = str(
        request[
            "source"
        ]
    )

    provider_symbol = str(
        request[
            "provider_symbol"
        ]
    )


    requested_start = pd.Timestamp(
        request[
            "download_start"
        ]
    ).normalize()


    requested_end_exclusive = pd.Timestamp(
        request[
            "download_end_exclusive"
        ]
    ).normalize()


    effective_expected_end_exclusive = (
        requested_end_exclusive
    )


    raw_file = (
        PROJECT_ROOT
        / str(
            request[
                "output_file"
            ]
        )
    )


    critical_issues = 0
    known_reviews = 0
    flags = []
    transformations = []


    # ========================================================
    # LOAD PRIMARY / FALLBACK SOURCE
    # ========================================================

    try:

        if (
            security_key == "INFO"
            and project_ticker == "INFO"
        ):

            data = load_info_adjusted(
                INFO_ADJUSTED_FILE
            )

            expected_events = (
                info_actions[
                    [
                        "ex_date",
                        "cash_amount",
                    ]
                ]
                .sort_values("ex_date")
                .reset_index(drop=True)
            )

            actual_events = (
                data.loc[
                    data["dividend"] > 0,
                    [
                        "date",
                        "dividend",
                    ],
                ]
                .rename(
                    columns={
                        "date": "ex_date",
                        "dividend": "cash_amount",
                    }
                )
                .sort_values("ex_date")
                .reset_index(drop=True)
            )

            if (
                len(actual_events)
                != len(expected_events)
            ):
                raise RuntimeError(
                    "INFO reconstructed dividend-event "
                    "count changed."
                )

            if not (
                actual_events["ex_date"]
                .equals(
                    expected_events["ex_date"]
                )
            ):
                raise RuntimeError(
                    "INFO reconstructed ex-dates do not "
                    "match the reference."
                )

            amount_difference = (
                actual_events["cash_amount"]
                - expected_events["cash_amount"]
            ).abs()

            if (
                amount_difference
                > 1e-12
            ).any():
                raise RuntimeError(
                    "INFO reconstructed dividends do not "
                    "match the reference."
                )

            transformations.append(
                "INFO_ADJUSTED_PRICE_RECONSTRUCTION"
            )

            add_transformation(
                security_key,
                project_ticker,
                "ADJUSTED_PRICE_RECONSTRUCTION",
                (
                    "Reconstructed historical adjusted "
                    "close from validated INFO "
                    "cash-dividend actions; raw "
                    "Investing.com OHLCV remains unchanged."
                ),
            )

        elif (
            security_key == "DISCA"
            and project_ticker == "DISCA"
        ):

            data = load_disca_composite(
                DISCA_COMPOSITE_FILE
            )

            transformations.append(
                "DISCA_SOURCE_COMPOSITE"
            )

            add_transformation(
                security_key,
                project_ticker,
                "SOURCE_COMPOSITE",
                (
                    "Replaced truncated direct "
                    "Tiingo view with validated "
                    "permanent-identity + direct "
                    "DISCA composite."
                ),
            )


        elif (
            security_key == "VLTO"
            and project_ticker == "VLTO"
        ):

            data = load_vlto_composite(
                VLTO_COMPOSITE_FILE
            )

            transformations.append(
                "VLTO_SOURCE_COMPOSITE"
            )

            add_transformation(
                security_key,
                project_ticker,
                "SOURCE_COMPOSITE",
                (
                    "VLTO-W 2023-09-27 through "
                    "2023-09-29 + Tiingo VLTO "
                    "2023-10-02 through 2023-10-03 "
                    "+ Yahoo VLTO from 2023-10-04."
                ),
            )


        else:

            if not raw_file.exists():

                raise FileNotFoundError(
                    str(
                        raw_file
                    )
                )


            if source == "Yahoo Finance":

                data = load_yahoo(
                    raw_file
                )


            elif source == "Tiingo":

                data = load_tiingo(
                    raw_file
                )


            elif source == "Investing.com":

                data = load_investing(
                    raw_file
                )


            else:

                raise RuntimeError(
                    f"Unsupported source: "
                    f"{source}"
                )


    except Exception as error:

        critical_issues += 1

        flags.append(
            "SOURCE_LOAD_FAILURE"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "SOURCE_LOAD_FAILURE",
            str(error),
        )


        audit_records.append(
            {
                "security_key":
                    security_key,

                "project_ticker":
                    project_ticker,

                "provider_symbol":
                    provider_symbol,

                "original_source":
                    source,

                "status":
                    "FAIL",

                "requested_start":
                    requested_start.date(),

                "effective_expected_start":
                    None,

                "requested_end_exclusive":
                    requested_end_exclusive.date(),

                "effective_expected_end_exclusive":
                    None,

                "analysis_rows":
                    0,

                "first_date":
                    None,

                "last_date":
                    None,

                "missing_expected_sessions":
                    None,

                "extra_nonexpected_sessions":
                    None,

                "duplicate_dates":
                    None,

                "invalid_dates":
                    None,

                "required_ohlcv_nulls":
                    None,

                "adjusted_close_nulls":
                    None,

                "nonpositive_price_rows":
                    None,

                "negative_volume_rows":
                    None,

                "invalid_high_rows":
                    None,

                "invalid_low_rows":
                    None,

                "critical_issues":
                    critical_issues,

                "known_reviews":
                    known_reviews,

                "transformations":
                    "|".join(
                        transformations
                    ),

                "flags":
                    "|".join(
                        flags
                    ),
            }
        )

        continue


    # ========================================================
    # UA — VERIFIED LOW OVERRIDE
    # ========================================================

    if (
        security_key == "UA"
        and project_ticker == "UA"
    ):

        ua_resolution = resolved_rows[
            (
                resolved_rows[
                    "security_key"
                ]
                == "UA"
            )
            &
            (
                resolved_rows[
                    "project_ticker"
                ]
                == "UA"
            )
        ]


        if len(
            ua_resolution
        ) != 1:

            raise RuntimeError(
                "Expected exactly one "
                "UA resolved-row record."
            )


        ua_resolution = (
            ua_resolution.iloc[0]
        )


        target_date = pd.Timestamp(
            ua_resolution[
                "date"
            ]
        ).normalize()


        target_rows = (
            data[
                "date"
            ]
            == target_date
        )


        if int(
            target_rows.sum()
        ) != 1:

            critical_issues += 1

            flags.append(
                "UA_TARGET_ROW_NOT_UNIQUE"
            )

            add_issue(
                security_key,
                project_ticker,
                "CRITICAL",
                "UA_TARGET_ROW_NOT_UNIQUE",
                str(
                    target_date.date()
                ),
            )


        else:

            replacement_low = float(
                ua_resolution[
                    "resolved_low"
                ]
            )


            data.loc[
                target_rows,
                "low",
            ] = replacement_low


            transformations.append(
                "UA_LOW_OVERRIDE"
            )


            add_transformation(
                security_key,
                project_ticker,
                "FIELD_OVERRIDE",
                (
                    "2021-05-05 Low replaced "
                    "in temporary analysis-ready "
                    "view using independently "
                    "validated Tiingo value 20.57. "
                    "Raw Yahoo remains unchanged."
                ),
            )


    # ========================================================
    # FISV — VERIFIED MISSING ROW INSERT
    # ========================================================

    if (
        security_key == "FISV"
        and project_ticker == "FISV"
    ):

        fisv_resolution = resolved_rows[
            (
                resolved_rows[
                    "security_key"
                ]
                == "FISV"
            )
            &
            (
                resolved_rows[
                    "project_ticker"
                ]
                == "FISV"
            )
        ]


        if len(
            fisv_resolution
        ) != 1:

            raise RuntimeError(
                "Expected exactly one "
                "FISV resolved-row record."
            )


        fisv_resolution = (
            fisv_resolution.iloc[0]
        )


        insert_date = pd.Timestamp(
            fisv_resolution[
                "date"
            ]
        ).normalize()


        existing_count = int(
            (
                data[
                    "date"
                ]
                == insert_date
            )
            .sum()
        )


        if existing_count > 1:

            critical_issues += 1

            flags.append(
                "FISV_TARGET_DUPLICATED"
            )

            add_issue(
                security_key,
                project_ticker,
                "CRITICAL",
                "FISV_TARGET_DUPLICATED",
                str(
                    insert_date.date()
                ),
            )


        elif existing_count == 0:

            insert_row = pd.DataFrame(
                [
                    {
                        "date":
                            insert_date,

                        "open":
                            float(
                                fisv_resolution[
                                    "resolved_open"
                                ]
                            ),

                        "high":
                            float(
                                fisv_resolution[
                                    "resolved_high"
                                ]
                            ),

                        "low":
                            float(
                                fisv_resolution[
                                    "resolved_low"
                                ]
                            ),

                        "close":
                            float(
                                fisv_resolution[
                                    "resolved_close"
                                ]
                            ),

                        "adj_close":
                            float(
                                fisv_resolution[
                                    "resolved_adj_close"
                                ]
                            ),

                        "volume":
                            float(
                                fisv_resolution[
                                    "resolved_volume"
                                ]
                            ),

                        # Tiingo verification showed
                        # no corporate action on the
                        # inserted session.
                        "dividend":
                            0.0,

                        "split_factor":
                            1.0,

                        "source_component":
                            (
                                "Tiingo verified "
                                "FISV insert"
                            ),
                    }
                ]
            )


            data = pd.concat(
                [
                    data,
                    insert_row,
                ],
                ignore_index=True,
            )


            transformations.append(
                "FISV_ROW_INSERT"
            )


            add_transformation(
                security_key,
                project_ticker,
                "ROW_INSERT",
                (
                    "Inserted independently "
                    "validated 2025-11-12 "
                    "Tiingo observation."
                ),
            )


        else:

            # If this ever occurs after source
            # refresh, we refuse to silently insert
            # a duplicate.
            transformations.append(
                "FISV_ROW_ALREADY_PRESENT"
            )


    # ========================================================
    # GEHC — REMOVE DOCUMENTED PRE-INCEPTION ARTIFACT
    # ========================================================

    if (
        security_key == "GEHC"
        and project_ticker == "GEHC"
    ):

        pre_count = int(
            (
                data[
                    "date"
                ]
                < pd.Timestamp(
                    "2022-12-16"
                )
            )
            .sum()
        )


        if pre_count != 1:

            critical_issues += 1

            flags.append(
                "GEHC_PRE_INCEPTION_COUNT_CHANGED"
            )

            add_issue(
                security_key,
                project_ticker,
                "CRITICAL",
                "GEHC_PRE_INCEPTION_COUNT_CHANGED",
                (
                    "Expected exactly one "
                    "documented Yahoo "
                    "pre-inception row; "
                    f"found {pre_count}."
                ),
            )


        else:

            pre_dates = data.loc[
                data[
                    "date"
                ]
                < pd.Timestamp(
                    "2022-12-16"
                ),
                "date",
            ]


            if (
                pre_dates.iloc[0]
                != pd.Timestamp(
                    "2022-12-15"
                )
            ):

                critical_issues += 1

                flags.append(
                    "GEHC_UNEXPECTED_PRE_INCEPTION_DATE"
                )


                add_issue(
                    security_key,
                    project_ticker,
                    "CRITICAL",
                    "GEHC_UNEXPECTED_PRE_INCEPTION_DATE",
                    str(
                        pre_dates.iloc[0].date()
                    ),
                )


            else:

                data = data[
                    data[
                        "date"
                    ]
                    >= pd.Timestamp(
                        "2022-12-16"
                    )
                ].copy()


                transformations.append(
                    "GEHC_PRE_INCEPTION_EXCLUSION"
                )


                add_transformation(
                    security_key,
                    project_ticker,
                    "ROW_EXCLUSION",
                    (
                        "Excluded Yahoo "
                        "2022-12-15 observation "
                        "from temporary "
                        "analysis-ready view."
                    ),
                )


    # ========================================================
    # EFFECTIVE EXPECTED START
    # ========================================================

    effective_expected_start = (
        requested_start
    )


    inception_match = inceptions[
        (
            inceptions[
                "security_key"
            ]
            == security_key
        )
        &
        (
            inceptions[
                "project_ticker"
            ]
            == project_ticker
        )
    ]


    if len(
        inception_match
    ) > 1:

        critical_issues += 1

        flags.append(
            "DUPLICATE_INCEPTION_REFERENCE"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "DUPLICATE_INCEPTION_REFERENCE",
            (
                "More than one market "
                "inception reference row."
            ),
        )


    elif len(
        inception_match
    ) == 1:

        market_inception = (
            inception_match
            .iloc[0][
                "market_inception_date"
            ]
            .normalize()
        )


        effective_expected_start = max(
            requested_start,
            market_inception,
        )


    # Boundary-resolution decisions override
    # the generic inception boundary where
    # appropriate.
    boundary_match = (
        boundary_resolutions[
            (
                boundary_resolutions[
                    "security_key"
                ]
                == security_key
            )
            &
            (
                boundary_resolutions[
                    "project_ticker"
                ]
                == project_ticker
            )
        ]
    )


    if len(
        boundary_match
    ) > 1:

        critical_issues += 1

        flags.append(
            "DUPLICATE_BOUNDARY_REFERENCE"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "DUPLICATE_BOUNDARY_REFERENCE",
            (
                "More than one boundary "
                "resolution row."
            ),
        )


    elif len(
        boundary_match
    ) == 1:

        accepted_start = (
            boundary_match
            .iloc[0][
                "accepted_effective_start"
            ]
            .normalize()
        )


        effective_expected_start = max(
            requested_start,
            accepted_start,
        )


        resolution_type = str(
            boundary_match
            .iloc[0][
                "resolution_type"
            ]
        )


        transformations.append(
            "BOUNDARY:"
            + resolution_type
        )


    # ========================================================
    # EFFECTIVE EXPECTED END / MARKET TERMINATION
    # ========================================================

    termination_match = (
        terminations[
            (
                terminations[
                    "security_key"
                ]
                == security_key
            )
            &
            (
                terminations[
                    "project_ticker"
                ]
                == project_ticker
            )
        ]
    )


    termination_last_valid = None


    if len(
        termination_match
    ) > 1:

        critical_issues += 1

        flags.append(
            "DUPLICATE_TERMINATION_REFERENCE"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "DUPLICATE_TERMINATION_REFERENCE",
            (
                "More than one market-"
                "termination reference row."
            ),
        )


    elif len(
        termination_match
    ) == 1:

        termination_row = (
            termination_match.iloc[0]
        )


        accepted_end_exclusive = (
            termination_row[
                "accepted_effective_end_exclusive"
            ]
            .normalize()
        )


        termination_last_valid = (
            termination_row[
                "last_valid_trading_date"
            ]
            .normalize()
        )


        provider_terminal_date = (
            termination_row[
                "provider_terminal_date"
            ]
            .normalize()
        )


        provider_terminal_action = str(
            termination_row[
                "provider_terminal_action"
            ]
        )


        termination_basis = str(
            termination_row[
                "termination_basis"
            ]
        )


        effective_expected_end_exclusive = min(
            requested_end_exclusive,
            accepted_end_exclusive,
        )


        if (
            effective_expected_start
            >= effective_expected_end_exclusive
        ):

            critical_issues += 1

            flags.append(
                "INVALID_EFFECTIVE_PRICE_INTERVAL"
            )

            add_issue(
                security_key,
                project_ticker,
                "CRITICAL",
                "INVALID_EFFECTIVE_PRICE_INTERVAL",
                (
                    "Effective start is not "
                    "earlier than the accepted "
                    "termination boundary."
                ),
            )


        provider_terminal_count = int(
            (
                data[
                    "date"
                ]
                == provider_terminal_date
            )
            .sum()
        )


        if provider_terminal_count != 1:

            critical_issues += 1

            flags.append(
                "TERMINAL_PROVIDER_ROW_NOT_UNIQUE"
            )

            add_issue(
                security_key,
                project_ticker,
                "CRITICAL",
                "TERMINAL_PROVIDER_ROW_NOT_UNIQUE",
                (
                    f"Expected exactly one provider "
                    f"row on "
                    f"{provider_terminal_date.date()}; "
                    f"found {provider_terminal_count}."
                ),
            )


        elif (
            provider_terminal_action
            == "EXCLUDE_PROVIDER_ARTIFACT"
        ):

            data = data[
                data[
                    "date"
                ]
                != provider_terminal_date
            ].copy()


            transformations.append(
                "TERMINAL_PROVIDER_ROW_EXCLUSION"
            )


            add_transformation(
                security_key,
                project_ticker,
                "TERMINAL_ROW_EXCLUSION",
                (
                    f"Excluded provider observation "
                    f"dated "
                    f"{provider_terminal_date.date()} "
                    f"because independent trading "
                    f"had already terminated. Raw "
                    f"provider data remains unchanged."
                ),
            )


        elif (
            provider_terminal_action
            == "KEEP"
        ):

            transformations.append(
                "TERMINAL_PROVIDER_ROW_RETAINED"
            )


            add_transformation(
                security_key,
                project_ticker,
                "MARKET_TERMINATION_BOUNDARY",
                (
                    f"Retained validated final "
                    f"trading observation dated "
                    f"{provider_terminal_date.date()} "
                    f"and capped expected coverage "
                    f"before "
                    f"{accepted_end_exclusive.date()}."
                ),
            )


        else:

            critical_issues += 1

            flags.append(
                "UNSUPPORTED_TERMINAL_ACTION"
            )

            add_issue(
                security_key,
                project_ticker,
                "CRITICAL",
                "UNSUPPORTED_TERMINAL_ACTION",
                provider_terminal_action,
            )


        transformations.append(
            "TERMINATION_BOUNDARY:"
            + termination_basis
        )


    # ========================================================
    # SORT BEFORE FINAL AUDIT
    # ========================================================

    data = (
        data
        .sort_values(
            "date"
        )
        .reset_index(drop=True)
    )


    if termination_last_valid is not None:

        valid_dates = (
            data[
                "date"
            ]
            .dropna()
        )


        actual_last_date = (
            valid_dates.max()
            if not valid_dates.empty
            else None
        )


        if (
            actual_last_date
            != termination_last_valid
        ):

            critical_issues += 1

            flags.append(
                "TERMINATION_LAST_DATE_MISMATCH"
            )

            add_issue(
                security_key,
                project_ticker,
                "CRITICAL",
                "TERMINATION_LAST_DATE_MISMATCH",
                (
                    f"Expected final valid date "
                    f"{termination_last_valid.date()}, "
                    f"but analysis-ready data ends "
                    f"on "
                    f"{actual_last_date.date() if actual_last_date is not None else None}."
                ),
            )


        post_termination_rows = int(
            (
                valid_dates
                >= effective_expected_end_exclusive
            )
            .sum()
        )


        if post_termination_rows > 0:

            critical_issues += 1

            flags.append(
                "POST_TERMINATION_ROWS_REMAIN"
            )

            add_issue(
                security_key,
                project_ticker,
                "CRITICAL",
                "POST_TERMINATION_ROWS_REMAIN",
                (
                    f"{post_termination_rows} row(s) "
                    f"remain on or after the accepted "
                    f"end-exclusive boundary "
                    f"{effective_expected_end_exclusive.date()}."
                ),
            )


    # ========================================================
    # BASIC STRUCTURAL INTEGRITY
    # ========================================================

    invalid_dates = int(
        data[
            "date"
        ]
        .isna()
        .sum()
    )


    duplicate_dates = int(
        data[
            "date"
        ]
        .dropna()
        .duplicated()
        .sum()
    )


    required_ohlcv_nulls = int(
        data[
            [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ]
        .isna()
        .sum()
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
            "CRITICAL",
            "INVALID_DATES",
            str(
                invalid_dates
            ),
        )


    if duplicate_dates > 0:

        critical_issues += 1

        flags.append(
            "DUPLICATE_DATES"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "DUPLICATE_DATES",
            str(
                duplicate_dates
            ),
        )


    if required_ohlcv_nulls > 0:

        critical_issues += 1

        flags.append(
            "REQUIRED_OHLCV_NULLS"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "REQUIRED_OHLCV_NULLS",
            str(
                required_ohlcv_nulls
            ),
        )


    # ========================================================
    # ========================================================
    # ADJUSTED CLOSE
    # ========================================================

    adjusted_numeric = pd.to_numeric(
        data["adj_close"],
        errors="coerce",
    )

    adjusted_close_nulls = int(
        adjusted_numeric
        .isna()
        .sum()
    )

    if adjusted_close_nulls > 0:
        critical_issues += 1

        flags.append(
            "ADJUSTED_CLOSE_NULLS"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "ADJUSTED_CLOSE_NULLS",
            str(
                adjusted_close_nulls
            ),
        )


    # PRICE / VOLUME VALIDITY
    # ========================================================

    nonpositive_price_rows = int(
        (
            data[
                [
                    "open",
                    "high",
                    "low",
                    "close",
                ]
            ]
            <= 0
        )
        .any(
            axis=1
        )
        .sum()
    )


    negative_volume_rows = int(
        (
            data[
                "volume"
            ]
            < 0
        )
        .sum()
    )


    invalid_high_rows = int(
        (
            data[
                "high"
            ]
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


    invalid_low_rows = int(
        (
            data[
                "low"
            ]
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


    if nonpositive_price_rows > 0:

        critical_issues += 1

        flags.append(
            "NONPOSITIVE_PRICE"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "NONPOSITIVE_PRICE",
            str(
                nonpositive_price_rows
            ),
        )


    if negative_volume_rows > 0:

        critical_issues += 1

        flags.append(
            "NEGATIVE_VOLUME"
        )

        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "NEGATIVE_VOLUME",
            str(
                negative_volume_rows
            ),
        )


    if invalid_high_rows > 0:

        critical_issues += 1

        flags.append(
            "INVALID_HIGH"
        )

        add_issue(
            security_key,
            project_ticker,
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
            "CRITICAL",
            "INVALID_LOW",
            str(
                invalid_low_rows
            ),
        )


    # ========================================================
    # EXPECTED MARKET CALENDAR
    # ========================================================

    expected_sessions = spy_dates[
        (
            spy_dates
            >= effective_expected_start
        )
        &
        (
            spy_dates
            < effective_expected_end_exclusive
        )
    ]


    observed_sessions = (
        data[
            "date"
        ]
        .dropna()
        .drop_duplicates()
        .sort_values()
    )


    missing_expected_sessions = (
        expected_sessions[
            ~expected_sessions.isin(
                observed_sessions
            )
        ]
    )


    # Any row outside the analysis-ready
    # expected interval is now unexplained.
    extra_nonexpected_sessions = (
        observed_sessions[
            ~observed_sessions.isin(
                expected_sessions
            )
        ]
    )


    missing_count = len(
        missing_expected_sessions
    )


    extra_count = len(
        extra_nonexpected_sessions
    )


    if missing_count > 0:

        critical_issues += 1

        flags.append(
            "UNEXPLAINED_MISSING_SESSIONS"
        )


        preview = ", ".join(
            str(
                date.date()
            )
            for date
            in missing_expected_sessions[
                :10
            ]
        )


        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "UNEXPLAINED_MISSING_SESSIONS",
            (
                f"{missing_count} expected "
                f"SPY session(s) missing. "
                f"Examples: {preview}"
            ),
        )


    if extra_count > 0:

        critical_issues += 1

        flags.append(
            "UNEXPLAINED_EXTRA_SESSIONS"
        )


        preview = ", ".join(
            str(
                date.date()
            )
            for date
            in extra_nonexpected_sessions[
                :10
            ]
        )


        add_issue(
            security_key,
            project_ticker,
            "CRITICAL",
            "UNEXPLAINED_EXTRA_SESSIONS",
            (
                f"{extra_count} observation(s) "
                f"fall outside the accepted "
                f"analysis-ready calendar. "
                f"Examples: {preview}"
            ),
        )


    # ========================================================
    # FINAL REQUEST STATUS
    # ========================================================

    if critical_issues > 0:

        status = "FAIL"


    elif known_reviews > 0:

        status = "REVIEW_KNOWN"


    else:

        status = "PASS"


    if status == "PASS":

        standardized_request = data[
            [
                "date",
                "open",
                "high",
                "low",
                "close",
                "adj_close",
                "volume",
                "dividend",
                "split_factor",
                "source_component",
            ]
        ].copy()

        standardized_request = (
            standardized_request.rename(
                columns={
                    "adj_close":
                        "adjusted_close",

                    "source_component":
                        "source",
                }
            )
        )

        standardized_request.insert(
            0,
            "provider_symbol",
            provider_symbol,
        )

        standardized_request.insert(
            0,
            "project_ticker",
            project_ticker,
        )

        standardized_request.insert(
            0,
            "security_key",
            security_key,
        )

        standardized_frames.append(
            standardized_request
        )


    first_date = (
        data[
            "date"
        ].min()
        if not data.empty
        else None
    )


    last_date = (
        data[
            "date"
        ].max()
        if not data.empty
        else None
    )


    audit_records.append(
        {
            "security_key":
                security_key,

            "project_ticker":
                project_ticker,

            "provider_symbol":
                provider_symbol,

            "original_source":
                source,

            "status":
                status,

            "requested_start":
                requested_start.date(),

            "effective_expected_start":
                effective_expected_start.date(),

            "requested_end_exclusive":
                requested_end_exclusive.date(),

            "effective_expected_end_exclusive":
                effective_expected_end_exclusive.date(),

            "analysis_rows":
                len(
                    data
                ),

            "first_date":
                (
                    first_date.date()
                    if pd.notna(
                        first_date
                    )
                    else None
                ),

            "last_date":
                (
                    last_date.date()
                    if pd.notna(
                        last_date
                    )
                    else None
                ),

            "missing_expected_sessions":
                missing_count,

            "extra_nonexpected_sessions":
                extra_count,

            "duplicate_dates":
                duplicate_dates,

            "invalid_dates":
                invalid_dates,

            "required_ohlcv_nulls":
                required_ohlcv_nulls,

            "adjusted_close_nulls":
                adjusted_close_nulls,

            "nonpositive_price_rows":
                nonpositive_price_rows,

            "negative_volume_rows":
                negative_volume_rows,

            "invalid_high_rows":
                invalid_high_rows,

            "invalid_low_rows":
                invalid_low_rows,

            "critical_issues":
                critical_issues,

            "known_reviews":
                known_reviews,

            "transformations":
                "|".join(
                    transformations
                ),

            "flags":
                "|".join(
                    flags
                ),
        }
    )


    if (
        request_number % 50 == 0
        or status == "FAIL"
        or request_number
        == EXPECTED_REQUEST_COUNT
    ):

        print(
            f"[{request_number}/"
            f"{EXPECTED_REQUEST_COUNT}] "
            f"{project_ticker}: "
            f"{status}"
        )


# ============================================================
# 4. SAVE AUDIT OUTPUTS
# ============================================================

print_section(
    "4. SAVE ANALYSIS-READY AUDIT"
)


audit = pd.DataFrame(
    audit_records
)


if len(
    audit
) != EXPECTED_REQUEST_COUNT:

    print(
        "\nERROR:"
    )

    print(
        "Final audit did not produce "
        "exactly 596 rows."
    )

    print(
        f"Produced: "
        f"{len(audit)}"
    )

    sys.exit(1)


status_order = {
    "FAIL": 0,
    "REVIEW_KNOWN": 1,
    "PASS": 2,
}


audit[
    "_status_order"
] = audit[
    "status"
].map(
    status_order
)


audit = (
    audit
    .sort_values(
        [
            "_status_order",
            "original_source",
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


audit.to_csv(
    OUTPUT_AUDIT_FILE,
    index=False,
)


print(
    f"Saved:\n"
    f"{OUTPUT_AUDIT_FILE}"
)


issues = pd.DataFrame(
    issue_records
)


if issues.empty:

    if OUTPUT_ISSUES_FILE.exists():

        OUTPUT_ISSUES_FILE.unlink()


    print(
        "\nNo issue table required."
    )


else:

    severity_order = {
        "CRITICAL": 0,
        "KNOWN_REVIEW": 1,
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
        OUTPUT_ISSUES_FILE,
        index=False,
    )


    print(
        f"\nSaved issue table:\n"
        f"{OUTPUT_ISSUES_FILE}"
    )


transformations = pd.DataFrame(
    transformation_records
)


if transformations.empty:

    if (
        OUTPUT_TRANSFORMATIONS_FILE
        .exists()
    ):

        OUTPUT_TRANSFORMATIONS_FILE.unlink()


else:

    transformations = (
        transformations
        .drop_duplicates()
        .sort_values(
            [
                "security_key",
                "project_ticker",
                "transformation",
            ]
        )
        .reset_index(drop=True)
    )


    transformations.to_csv(
        OUTPUT_TRANSFORMATIONS_FILE,
        index=False,
    )


    print(
        f"\nSaved transformation table:\n"
        f"{OUTPUT_TRANSFORMATIONS_FILE}"
    )


# ============================================================
# 5. FINAL STATUS SUMMARY
# ============================================================

print_section(
    "5. FINAL STATUS SUMMARY"
)


print(
    f"Total requests audited: "
    f"{len(audit)}"
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
    "\nStatus by original source:"
)


print(
    pd.crosstab(
        audit[
            "original_source"
        ],
        audit[
            "status"
        ],
    )
    .to_string()
)


critical_failures = (
    audit[
        audit[
            "status"
        ]
        == "FAIL"
    ]
)


known_reviews = (
    audit[
        audit[
            "status"
        ]
        == "REVIEW_KNOWN"
    ]
)


clean_pass = (
    audit[
        audit[
            "status"
        ]
        == "PASS"
    ]
)


print(
    "\nCompletely clean / "
    "resolved PASS:"
)

print(
    len(
        clean_pass
    )
)


print(
    "\nKnown documented review:"
)

print(
    len(
        known_reviews
    )
)


print(
    "\nCritical failures:"
)

print(
    len(
        critical_failures
    )
)


# ============================================================
# 6. TRANSFORMATION SUMMARY
# ============================================================

print_section(
    "6. VALIDATED TRANSFORMATIONS APPLIED"
)


if transformations.empty:

    print(
        "None."
    )


else:

    print(
        transformations[
            [
                "security_key",
                "project_ticker",
                "transformation",
                "detail",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ============================================================
# 7. KNOWN REVIEW ITEMS
# ============================================================

print_section(
    "7. KNOWN REVIEW ITEMS"
)


if known_reviews.empty:

    print(
        "None."
    )


else:

    print(
        known_reviews[
            [
                "security_key",
                "project_ticker",
                "original_source",
                "analysis_rows",
                "first_date",
                "last_date",
                "flags",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ============================================================
# 8. CRITICAL FAILURES
# ============================================================

print_section(
    "8. CRITICAL FAILURES"
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
                "original_source",
                "analysis_rows",
                "first_date",
                "last_date",
                "missing_expected_sessions",
                "extra_nonexpected_sessions",
                "critical_issues",
                "flags",
            ]
        ]
        .to_string(
            index=False
        )
    )


# ============================================================
# 9. ISSUE TYPE SUMMARY
# ============================================================

print_section(
    "9. ISSUE TYPE SUMMARY"
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
                "issue_type",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
    )


    print(
        issue_summary
        .to_string(
            index=False
        )
    )


# ============================================================
# 10. GLOBAL COVERAGE TOTALS
# ============================================================

print_section(
    "10. GLOBAL COVERAGE TOTALS"
)


total_missing = int(
    audit[
        "missing_expected_sessions"
    ]
    .fillna(0)
    .sum()
)


total_extra = int(
    audit[
        "extra_nonexpected_sessions"
    ]
    .fillna(0)
    .sum()
)


total_duplicates = int(
    audit[
        "duplicate_dates"
    ]
    .fillna(0)
    .sum()
)


total_invalid_high = int(
    audit[
        "invalid_high_rows"
    ]
    .fillna(0)
    .sum()
)


total_invalid_low = int(
    audit[
        "invalid_low_rows"
    ]
    .fillna(0)
    .sum()
)


total_required_nulls = int(
    audit[
        "required_ohlcv_nulls"
    ]
    .fillna(0)
    .sum()
)


print(
    f"Unexplained missing sessions: "
    f"{total_missing}"
)

print(
    f"Unexplained extra sessions: "
    f"{total_extra}"
)

print(
    f"Duplicate dates: "
    f"{total_duplicates}"
)

print(
    f"Invalid HIGH rows: "
    f"{total_invalid_high}"
)

print(
    f"Invalid LOW rows: "
    f"{total_invalid_low}"
)

print(
    f"Required OHLCV null values: "
    f"{total_required_nulls}"
)


# ============================================================
# 11. FINAL QUALITY GATE
# ============================================================

print_section(
    "11. FINAL QUALITY GATE"
)

if not critical_failures.empty:
    print(
        "ANALYSIS-READY PRICE "
        "INTEGRITY AUDIT FAILED."
    )

    print(
        f"\nCritical requests: "
        f"{len(critical_failures)}"
    )

    print(
        "\nDO NOT STANDARDIZE "
        "OR CALCULATE RETURNS."
    )

    sys.exit(2)

if (
    total_missing != 0
    or total_extra != 0
    or total_duplicates != 0
    or total_invalid_high != 0
    or total_invalid_low != 0
    or total_required_nulls != 0
):
    print(
        "ANALYSIS-READY PRICE "
        "INTEGRITY AUDIT FAILED."
    )

    print(
        "\nGlobal integrity totals "
        "are not clean."
    )

    sys.exit(2)

if not known_reviews.empty:
    print(
        "ANALYSIS-READY PRICE "
        "INTEGRITY AUDIT INCOMPLETE."
    )

    print(
        f"\nKnown review requests remaining: "
        f"{len(known_reviews)}"
    )

    sys.exit(2)

canonical_columns = [
    "security_key",
    "project_ticker",
    "provider_symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividend",
    "split_factor",
    "source",
]


if (
    len(standardized_frames)
    != EXPECTED_REQUEST_COUNT
):

    print(
        "STANDARDIZED PRICE HISTORY FAILED."
    )

    print(
        "Expected 596 validated request frames; "
        f"found {len(standardized_frames)}."
    )

    sys.exit(2)


standardized_history = pd.concat(
    standardized_frames,
    ignore_index=True,
)


standardized_history = (
    standardized_history
    .sort_values(
        [
            "security_key",
            "project_ticker",
            "date",
        ]
    )
    .reset_index(drop=True)
)


if (
    list(
        standardized_history.columns
    )
    != canonical_columns
):

    print(
        "STANDARDIZED PRICE HISTORY FAILED."
    )

    print(
        "Canonical schema changed."
    )

    sys.exit(2)


duplicate_standardized_keys = int(
    standardized_history
    .duplicated(
        [
            "security_key",
            "project_ticker",
            "date",
        ]
    )
    .sum()
)


if duplicate_standardized_keys != 0:

    print(
        "STANDARDIZED PRICE HISTORY FAILED."
    )

    print(
        "Duplicate canonical keys: "
        f"{duplicate_standardized_keys}"
    )

    sys.exit(2)


standardized_numeric_columns = [
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividend",
    "split_factor",
]


standardized_nulls = int(
    standardized_history[
        standardized_numeric_columns
    ]
    .isna()
    .sum()
    .sum()
)


if standardized_nulls != 0:

    print(
        "STANDARDIZED PRICE HISTORY FAILED."
    )

    print(
        "Canonical numeric nulls: "
        f"{standardized_nulls}"
    )

    sys.exit(2)


if (
    standardized_history[
        [
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
        ]
    ]
    .le(0)
    .any()
    .any()
):

    print(
        "STANDARDIZED PRICE HISTORY FAILED."
    )

    print(
        "Canonical prices must be positive."
    )

    sys.exit(2)


if (
    standardized_history[
        "volume"
    ]
    .lt(0)
    .any()
    or standardized_history[
        "split_factor"
    ]
    .le(0)
    .any()
):

    print(
        "STANDARDIZED PRICE HISTORY FAILED."
    )

    print(
        "Invalid canonical volume "
        "or split factor."
    )

    sys.exit(2)


if (
    standardized_history[
        "source"
    ]
    .isna()
    .any()
    or standardized_history[
        "source"
    ]
    .astype(str)
    .str.strip()
    .eq("")
    .any()
):

    print(
        "STANDARDIZED PRICE HISTORY FAILED."
    )

    print(
        "Canonical source labels are missing."
    )

    sys.exit(2)


expected_standardized_rows = int(
    audit[
        "analysis_rows"
    ]
    .sum()
)


if (
    len(standardized_history)
    != expected_standardized_rows
):

    print(
        "STANDARDIZED PRICE HISTORY FAILED."
    )

    print(
        "Global row count differs from the audit: "
        f"{len(standardized_history)} != "
        f"{expected_standardized_rows}."
    )

    sys.exit(2)


standardized_output = (
    standardized_history.copy()
)


standardized_output[
    "date"
] = (
    standardized_output[
        "date"
    ]
    .dt.strftime(
        "%Y-%m-%d"
    )
)


temporary_price_file = (
    STANDARDIZED_PRICE_FILE
    .with_name(
        STANDARDIZED_PRICE_FILE.name
        + ".tmp"
    )
)


standardized_output.to_csv(
    temporary_price_file,
    index=False,
    float_format="%.12g",
    compression={
        "method": "gzip",
        "mtime": 0,
    },
)


temporary_price_file.replace(
    STANDARDIZED_PRICE_FILE
)


manifest_columns = [
    "security_key",
    "project_ticker",
    "provider_symbol",
    "original_source",
    "analysis_rows",
    "first_date",
    "last_date",
    "effective_expected_start",
    "effective_expected_end_exclusive",
    "transformations",
]


standardized_manifest = audit[
    manifest_columns
].copy()


standardized_manifest = (
    standardized_manifest
    .sort_values(
        [
            "security_key",
            "project_ticker",
        ]
    )
    .reset_index(drop=True)
)


temporary_manifest_file = (
    STANDARDIZED_MANIFEST_FILE
    .with_name(
        STANDARDIZED_MANIFEST_FILE.name
        + ".tmp"
    )
)


standardized_manifest.to_csv(
    temporary_manifest_file,
    index=False,
)


temporary_manifest_file.replace(
    STANDARDIZED_MANIFEST_FILE
)


print(
    "STANDARDIZED_PRICE_HISTORY_PASSED"
)


print(
    f"Standardized requests: "
    f"{len(standardized_frames)}"
)


print(
    f"Standardized rows: "
    f"{len(standardized_history):,}"
)


print(
    "Canonical key duplicates: 0"
)


print(
    f"Saved standardized history:\n"
    f"{STANDARDIZED_PRICE_FILE}"
)


print(
    f"Saved standardized manifest:\n"
    f"{STANDARDIZED_MANIFEST_FILE}"
)


print(
    "ANALYSIS-READY PRICE "
    "INTEGRITY AUDIT PASSED."
)

print(
    "\nAll 596 historical price requests "
    "passed structural and expected-session "
    "coverage validation after applying only "
    "documented, validated resolutions."
)

print(
    "\nNo known review items remain."
)

print(
    "\nNo unexplained missing "
    "trading sessions remain."
)

print(
    "No unexplained extra "
    "trading sessions remain."
)

print(
    "No invalid OHLC relationships remain."
)

print(
    "No required OHLCV nulls remain."
)

print(
    "\nRAW / ACQUISITION QUALITY "
    "GATE COMPLETE."
)
