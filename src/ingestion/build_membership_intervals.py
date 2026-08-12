from pathlib import Path
import sys

import pandas as pd


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ANCHOR_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "sp500_constituent_anchor_2026-08-10.csv"
)

CHANGES_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "membership"
    / "sp500_official_changes.csv"
)

ALIASES_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "securities"
    / "security_aliases.csv"
)

INTERIM_DIR = (
    PROJECT_ROOT
    / "data"
    / "interim"
)

MEMBERSHIP_OUTPUT = (
    INTERIM_DIR
    / "sp500_membership_intervals_2021_2025.csv"
)

TICKER_HISTORY_OUTPUT = (
    INTERIM_DIR
    / "sp500_ticker_history_2021_2025.csv"
)


# --------------------------------------------------
# Analysis dates
# --------------------------------------------------

ANCHOR_DATE = pd.Timestamp("2026-08-10")

ANALYSIS_START = pd.Timestamp("2021-01-01")

ANALYSIS_END = pd.Timestamp("2025-12-31")

SCOPE_END_EXCLUSIVE = ANALYSIS_END + pd.Timedelta(days=1)


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def print_section(title):
    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


def normalize_ticker(value):
    return str(value).strip().upper()


# --------------------------------------------------
# Load inputs
# --------------------------------------------------

print_section("S&P 500 POINT-IN-TIME MEMBERSHIP CONSTRUCTION")


required_files = [
    ANCHOR_FILE,
    CHANGES_FILE,
    ALIASES_FILE,
]


for file_path in required_files:

    if not file_path.exists():

        print(
            f"\nERROR: Required file does not exist:\n"
            f"{file_path}"
        )

        sys.exit(1)


anchor = pd.read_csv(ANCHOR_FILE)

changes = pd.read_csv(CHANGES_FILE)

aliases = pd.read_csv(ALIASES_FILE)


# --------------------------------------------------
# Normalize anchor
# --------------------------------------------------

anchor["Ticker"] = (
    anchor["Ticker"]
    .astype(str)
    .str.strip()
    .str.upper()
)


# --------------------------------------------------
# Normalize membership changes
# --------------------------------------------------

changes["ticker"] = (
    changes["ticker"]
    .astype(str)
    .str.strip()
    .str.upper()
)

changes["effective_date"] = pd.to_datetime(
    changes["effective_date"],
    format="%Y-%m-%d",
    errors="raise",
)

changes["announcement_date"] = pd.to_datetime(
    changes["announcement_date"],
    format="%Y-%m-%d",
    errors="raise",
)


# --------------------------------------------------
# Normalize aliases
# --------------------------------------------------

aliases["old_ticker"] = (
    aliases["old_ticker"]
    .astype(str)
    .str.strip()
    .str.upper()
)

aliases["new_ticker"] = (
    aliases["new_ticker"]
    .astype(str)
    .str.strip()
    .str.upper()
)

aliases["effective_date"] = pd.to_datetime(
    aliases["effective_date"],
    format="%Y-%m-%d",
    errors="raise",
)


# --------------------------------------------------
# 1. Build canonical ticker mapping
# --------------------------------------------------

print_section("1. SECURITY IDENTITY MAPPING")


alias_forward = dict(
    zip(
        aliases["old_ticker"],
        aliases["new_ticker"],
    )
)


def canonical_ticker(ticker):

    ticker = normalize_ticker(ticker)

    seen = set()

    while ticker in alias_forward:

        if ticker in seen:

            raise ValueError(
                f"Alias cycle detected involving {ticker}"
            )

        seen.add(ticker)

        ticker = alias_forward[ticker]

    return ticker


for _, alias in aliases.iterrows():

    print(
        f"{alias['old_ticker']} -> "
        f"{alias['new_ticker']} "
        f"({alias['effective_date'].date()})"
    )


# --------------------------------------------------
# 2. Build name lookup
# --------------------------------------------------

name_lookup = {}


for _, row in anchor.iterrows():

    name_lookup[row["Ticker"]] = str(
        row["Name"]
    ).strip()


for _, row in changes.iterrows():

    ticker = row["ticker"]

    if ticker not in name_lookup:

        name_lookup[ticker] = str(
            row["company_name"]
        ).strip()


for _, row in aliases.iterrows():

    name_lookup[row["old_ticker"]] = str(
        row["old_company_name"]
    ).strip()

    name_lookup[row["new_ticker"]] = str(
        row["new_company_name"]
    ).strip()


# --------------------------------------------------
# 3. Reconstruct membership at 2021-01-01
# --------------------------------------------------

print_section("2. RECONSTRUCT 2021-01-01 STARTING STATE")


historical_state = set(anchor["Ticker"])


reverse_dates = sorted(
    set(
        changes.loc[
            changes["effective_date"] > ANALYSIS_START,
            "effective_date",
        ]
    )
    |
    set(
        aliases.loc[
            aliases["effective_date"] > ANALYSIS_START,
            "effective_date",
        ]
    ),
    reverse=True,
)


for effective_date in reverse_dates:

    date_changes = changes[
        changes["effective_date"] == effective_date
    ]

    additions = set(
        date_changes.loc[
            date_changes["action"] == "Addition",
            "ticker",
        ]
    )

    deletions = set(
        date_changes.loc[
            date_changes["action"] == "Deletion",
            "ticker",
        ]
    )


    # Reverse original additions.
    for ticker in sorted(additions):

        if ticker not in historical_state:

            print(
                f"\nERROR: Cannot reverse addition for "
                f"{ticker} on {effective_date.date()}."
            )

            sys.exit(1)

        historical_state.remove(ticker)


    # Reverse original deletions.
    for ticker in sorted(deletions):

        if ticker in historical_state:

            print(
                f"\nERROR: Cannot reverse deletion for "
                f"{ticker} on {effective_date.date()}."
            )

            sys.exit(1)

        historical_state.add(ticker)


    # Reverse ticker aliases.
    date_aliases = aliases[
        aliases["effective_date"] == effective_date
    ]

    for _, alias in date_aliases.iterrows():

        old_ticker = alias["old_ticker"]
        new_ticker = alias["new_ticker"]

        if (
            new_ticker in historical_state
            and old_ticker not in historical_state
        ):

            historical_state.remove(new_ticker)
            historical_state.add(old_ticker)

        elif (
            new_ticker in historical_state
            and old_ticker in historical_state
        ):

            print(
                f"\nERROR: Alias collision while reversing "
                f"{new_ticker} -> {old_ticker}."
            )

            sys.exit(1)


print(
    f"Reconstructed securities at "
    f"{ANALYSIS_START.date()}: "
    f"{len(historical_state)}"
)


if len(historical_state) != 505:

    print(
        "\nERROR: Expected 505 securities at "
        "2021-01-01."
    )

    sys.exit(1)


print("PASS: Starting membership count is 505.")


# --------------------------------------------------
# 4. Initialize active membership
# --------------------------------------------------

print_section("3. INITIALIZE MEMBERSHIP INTERVALS")


active_membership = {}

membership_intervals = []

ticker_history = []

active_ticker_history = {}


for ticker in sorted(historical_state):

    security_key = canonical_ticker(ticker)

    if security_key in active_membership:

        print(
            f"\nERROR: Multiple starting tickers map "
            f"to security key {security_key}."
        )

        sys.exit(1)


    active_membership[security_key] = {
        "security_key": security_key,
        "company_name_reference": name_lookup.get(
            ticker,
            name_lookup.get(
                security_key,
                ticker,
            ),
        ),
        "valid_from": ANALYSIS_START,
        "left_censored": True,
        "entry_ticker": ticker,
        "entry_source_url": None,
    }


    active_ticker_history[security_key] = {
        "security_key": security_key,
        "ticker": ticker,
        "ticker_valid_from": ANALYSIS_START,
        "left_censored": True,
    }


print(
    f"Active security identities initialized: "
    f"{len(active_membership)}"
)


# --------------------------------------------------
# 5. Forward event timeline
# --------------------------------------------------

print_section("4. PROCESS 2021-2025 EVENTS FORWARD")


forward_dates = sorted(
    set(
        changes.loc[
            (
                (changes["effective_date"] > ANALYSIS_START)
                & (
                    changes["effective_date"]
                    <= ANALYSIS_END
                )
            ),
            "effective_date",
        ]
    )
    |
    set(
        aliases.loc[
            (
                (aliases["effective_date"] > ANALYSIS_START)
                & (
                    aliases["effective_date"]
                    <= ANALYSIS_END
                )
            ),
            "effective_date",
        ]
    )
)


for effective_date in forward_dates:

    # --------------------------------------------------
    # Apply ticker aliases first
    # --------------------------------------------------

    date_aliases = aliases[
        aliases["effective_date"] == effective_date
    ]


    for _, alias in date_aliases.iterrows():

        old_ticker = alias["old_ticker"]
        new_ticker = alias["new_ticker"]

        security_key = canonical_ticker(old_ticker)


        if security_key not in active_membership:

            # Security is not an index member at this
            # point, so no membership state changes.
            continue


        if security_key not in active_ticker_history:

            print(
                f"\nERROR: Missing active ticker history "
                f"for {security_key}."
            )

            sys.exit(1)


        current_ticker = (
            active_ticker_history[
                security_key
            ]["ticker"]
        )


        if current_ticker != old_ticker:

            print(
                f"\nERROR: Alias expected active ticker "
                f"{old_ticker}, but found "
                f"{current_ticker}."
            )

            sys.exit(1)


        # Close old ticker history.
        old_ticker_record = (
            active_ticker_history.pop(
                security_key
            )
        )

        old_ticker_record[
            "ticker_valid_to_exclusive"
        ] = effective_date

        old_ticker_record[
            "right_censored"
        ] = False

        ticker_history.append(
            old_ticker_record
        )


        # Open new ticker history.
        active_ticker_history[
            security_key
        ] = {
            "security_key": security_key,
            "ticker": new_ticker,
            "ticker_valid_from": effective_date,
            "left_censored": False,
        }


        print(
            f"Ticker change applied: "
            f"{old_ticker} -> {new_ticker} "
            f"({effective_date.date()})"
        )


    # --------------------------------------------------
    # Membership changes for this effective date
    # --------------------------------------------------

    date_changes = changes[
        changes["effective_date"] == effective_date
    ]


    deletions = date_changes[
        date_changes["action"] == "Deletion"
    ]


    additions = date_changes[
        date_changes["action"] == "Addition"
    ]


    # --------------------------------------------------
    # Process deletions first
    # --------------------------------------------------

    for _, row in deletions.iterrows():

        ticker = row["ticker"]

        security_key = canonical_ticker(ticker)


        if security_key not in active_membership:

            print(
                f"\nERROR: Cannot delete {ticker} "
                f"on {effective_date.date()} because "
                f"security key {security_key} "
                "is not active."
            )

            sys.exit(1)


        interval = active_membership.pop(
            security_key
        )

        interval[
            "valid_to_exclusive"
        ] = effective_date

        interval[
            "right_censored"
        ] = False

        interval[
            "exit_ticker"
        ] = ticker

        interval[
            "exit_source_url"
        ] = row["source_url"]

        membership_intervals.append(
            interval
        )


        # Close ticker history.
        if security_key not in active_ticker_history:

            print(
                f"\nERROR: Missing ticker history "
                f"for deleted security {ticker}."
            )

            sys.exit(1)


        ticker_record = (
            active_ticker_history.pop(
                security_key
            )
        )

        ticker_record[
            "ticker_valid_to_exclusive"
        ] = effective_date

        ticker_record[
            "right_censored"
        ] = False

        ticker_history.append(
            ticker_record
        )


    # --------------------------------------------------
    # Process additions
    # --------------------------------------------------

    for _, row in additions.iterrows():

        ticker = row["ticker"]

        security_key = canonical_ticker(ticker)


        if security_key in active_membership:

            print(
                f"\nERROR: Cannot add {ticker} "
                f"on {effective_date.date()} because "
                f"security key {security_key} "
                "is already active."
            )

            sys.exit(1)


        active_membership[
            security_key
        ] = {
            "security_key": security_key,
            "company_name_reference": str(
                row["company_name"]
            ).strip(),
            "valid_from": effective_date,
            "left_censored": False,
            "entry_ticker": ticker,
            "entry_source_url": row["source_url"],
        }


        active_ticker_history[
            security_key
        ] = {
            "security_key": security_key,
            "ticker": ticker,
            "ticker_valid_from": effective_date,
            "left_censored": False,
        }


# --------------------------------------------------
# 6. Close intervals at analysis boundary
# --------------------------------------------------

print_section("5. CLOSE OPEN INTERVALS AT 2025-12-31")


for security_key in sorted(
    active_membership
):

    interval = active_membership[
        security_key
    ].copy()

    interval[
        "valid_to_exclusive"
    ] = SCOPE_END_EXCLUSIVE

    interval[
        "right_censored"
    ] = True

    interval[
        "exit_ticker"
    ] = None

    interval[
        "exit_source_url"
    ] = None

    membership_intervals.append(
        interval
    )


for security_key in sorted(
    active_ticker_history
):

    ticker_record = (
        active_ticker_history[
            security_key
        ].copy()
    )

    ticker_record[
        "ticker_valid_to_exclusive"
    ] = SCOPE_END_EXCLUSIVE

    ticker_record[
        "right_censored"
    ] = True

    ticker_history.append(
        ticker_record
    )


# --------------------------------------------------
# 7. Create output DataFrames
# --------------------------------------------------

membership_df = pd.DataFrame(
    membership_intervals
)

ticker_history_df = pd.DataFrame(
    ticker_history
)


membership_df = membership_df.sort_values(
    [
        "security_key",
        "valid_from",
    ]
).reset_index(drop=True)


ticker_history_df = (
    ticker_history_df
    .sort_values(
        [
            "security_key",
            "ticker_valid_from",
        ]
    )
    .reset_index(drop=True)
)


# --------------------------------------------------
# 8. Validate interval dates
# --------------------------------------------------

print_section("6. INTERVAL VALIDATION")


invalid_intervals = membership_df[
    membership_df["valid_from"]
    >= membership_df[
        "valid_to_exclusive"
    ]
]


if not invalid_intervals.empty:

    print(
        "\nERROR: Invalid membership "
        "interval(s) detected."
    )

    print(
        invalid_intervals.to_string(
            index=False
        )
    )

    sys.exit(1)


print(
    "PASS: Every membership interval "
    "has a valid date range."
)


# --------------------------------------------------
# 9. Detect overlapping membership intervals
# --------------------------------------------------

overlap_errors = []


for security_key, group in (
    membership_df
    .groupby("security_key")
):

    group = group.sort_values(
        "valid_from"
    )

    previous_end = None


    for _, row in group.iterrows():

        if (
            previous_end is not None
            and row["valid_from"] < previous_end
        ):

            overlap_errors.append(
                security_key
            )

        previous_end = row[
            "valid_to_exclusive"
        ]


if overlap_errors:

    print(
        "\nERROR: Overlapping membership "
        "intervals detected for:"
    )

    print(
        sorted(
            set(overlap_errors)
        )
    )

    sys.exit(1)


print(
    "PASS: No overlapping membership "
    "intervals detected."
)


# --------------------------------------------------
# 10. Checkpoint validation
# --------------------------------------------------

print_section("7. POINT-IN-TIME CHECKPOINT VALIDATION")


EXPECTED_COUNTS = {
    pd.Timestamp("2021-01-01"): 505,
    pd.Timestamp("2021-12-31"): 505,
    pd.Timestamp("2022-12-31"): 503,
    pd.Timestamp("2023-12-31"): 503,
    pd.Timestamp("2024-12-31"): 503,
    pd.Timestamp("2025-12-31"): 503,
}


checkpoint_errors = []


for checkpoint, expected_count in (
    EXPECTED_COUNTS.items()
):

    active_count = len(
        membership_df[
            (
                membership_df[
                    "valid_from"
                ]
                <= checkpoint
            )
            &
            (
                membership_df[
                    "valid_to_exclusive"
                ]
                > checkpoint
            )
        ]
    )


    status = (
        "PASS"
        if active_count == expected_count
        else "FAIL"
    )


    print(
        f"{checkpoint.date()} | "
        f"Expected: {expected_count} | "
        f"Actual: {active_count} | "
        f"{status}"
    )


    if active_count != expected_count:

        checkpoint_errors.append(
            {
                "checkpoint": checkpoint,
                "expected": expected_count,
                "actual": active_count,
            }
        )


if checkpoint_errors:

    print(
        "\nERROR: One or more checkpoint "
        "counts failed."
    )

    sys.exit(1)


# --------------------------------------------------
# 11. Summary
# --------------------------------------------------

print_section("8. MEMBERSHIP INTERVAL SUMMARY")


print(
    f"Membership interval rows: "
    f"{len(membership_df)}"
)

print(
    f"Unique security identities: "
    f"{membership_df['security_key'].nunique()}"
)

print(
    f"Ticker-history rows: "
    f"{len(ticker_history_df)}"
)

print(
    f"Unique historical tickers: "
    f"{ticker_history_df['ticker'].nunique()}"
)

print(
    f"Securities active at analysis start: "
    f"{int(membership_df['left_censored'].sum())}"
)

print(
    f"Securities active at analysis end: "
    f"{int(membership_df['right_censored'].sum())}"
)


# --------------------------------------------------
# 12. Save outputs
# --------------------------------------------------

print_section("9. SAVE OUTPUTS")


INTERIM_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


membership_df.to_csv(
    MEMBERSHIP_OUTPUT,
    index=False,
    date_format="%Y-%m-%d",
)


ticker_history_df.to_csv(
    TICKER_HISTORY_OUTPUT,
    index=False,
    date_format="%Y-%m-%d",
)


print(
    f"Membership intervals saved:\n"
    f"{MEMBERSHIP_OUTPUT}"
)

print(
    f"\nTicker history saved:\n"
    f"{TICKER_HISTORY_OUTPUT}"
)


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section("BUILD RESULT")


print(
    "POINT-IN-TIME MEMBERSHIP "
    "CONSTRUCTION PASSED."
)

print(
    "\nThe 2021-2025 S&P 500 universe "
    "has been reconstructed using "
    "security-level membership intervals."
)

sys.exit(0)