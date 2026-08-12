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

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

ISSUES_FILE = (
    INTERIM_DIR
    / "membership_integrity_issues.csv"
)

CHECKPOINT_FILE = (
    INTERIM_DIR
    / "membership_count_checkpoints.csv"
)


# --------------------------------------------------
# Project dates
# --------------------------------------------------

ANCHOR_DATE = pd.Timestamp("2026-08-10")
ANALYSIS_START = pd.Timestamp("2021-01-01")
ANALYSIS_END = pd.Timestamp("2025-12-31")


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
# Load files
# --------------------------------------------------

print_section("FULL S&P 500 MEMBERSHIP HISTORY INTEGRITY AUDIT")

print(f"Anchor file:\n{ANCHOR_FILE}")
print(f"\nChange history:\n{CHANGES_FILE}")


if not ANCHOR_FILE.exists():
    print("\nERROR: Constituent anchor does not exist.")
    print(
        "Run src/ingestion/build_sp500_membership.py "
        "before running this audit."
    )
    sys.exit(1)


if not CHANGES_FILE.exists():
    print("\nERROR: Membership-change reference does not exist.")
    sys.exit(1)

if not ALIASES_FILE.exists():
    print("\nERROR: Security-alias reference does not exist.")
    sys.exit(1)

anchor = pd.read_csv(ANCHOR_FILE)
changes = pd.read_csv(CHANGES_FILE)
aliases = pd.read_csv(ALIASES_FILE)

# --------------------------------------------------
# Normalize fields
# --------------------------------------------------

anchor["Ticker"] = (
    anchor["Ticker"]
    .astype(str)
    .str.strip()
    .str.upper()
)

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
# Normalize security aliases
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
# 1. Anchor integrity
# --------------------------------------------------

print_section("1. ANCHOR INTEGRITY")

anchor_count = len(anchor)
unique_anchor_count = anchor["Ticker"].nunique()

print(f"Anchor rows: {anchor_count}")
print(f"Unique anchor tickers: {unique_anchor_count}")
print(f"Anchor date: {ANCHOR_DATE.date()}")


anchor_duplicates = anchor[
    anchor["Ticker"].duplicated(keep=False)
]

if anchor_count != 503:
    print(
        f"ERROR: Expected 503 anchor securities, "
        f"but found {anchor_count}."
    )
    sys.exit(1)


if not anchor_duplicates.empty:
    print("\nERROR: Duplicate anchor tickers detected:")
    print(
        anchor_duplicates[
            ["Name", "Ticker"]
        ].to_string(index=False)
    )
    sys.exit(1)


print("PASS: Anchor contains 503 unique securities.")


# --------------------------------------------------
# 2. Historical coverage
# --------------------------------------------------

print_section("2. HISTORICAL COVERAGE")

print(
    f"Earliest effective date: "
    f"{changes['effective_date'].min().date()}"
)

print(
    f"Latest effective date: "
    f"{changes['effective_date'].max().date()}"
)

print(f"Total membership actions: {len(changes)}")


out_of_scope_future = changes[
    changes["effective_date"] > ANCHOR_DATE
]

if not out_of_scope_future.empty:
    print("\nERROR: Change records occur after the anchor date.")

    print(
        out_of_scope_future[
            [
                "effective_date",
                "action",
                "ticker",
                "company_name",
            ]
        ].to_string(index=False)
    )

    sys.exit(1)


if changes["effective_date"].min() <= ANALYSIS_START:
    print(
        "CHECK: History includes an action on or before "
        "the analysis start date."
    )
else:
    print(
        "PASS: Historical actions begin after "
        "2021-01-01, allowing reconstruction of "
        "the start-of-period state."
    )


# --------------------------------------------------
# 3. Annual change summary
# --------------------------------------------------

print_section("3. ANNUAL CHANGE SUMMARY")

changes["effective_year"] = changes["effective_date"].dt.year

annual_summary = (
    changes
    .groupby(
        ["effective_year", "action"]
    )
    .size()
    .unstack(fill_value=0)
    .sort_index()
)

for column in ["Addition", "Deletion"]:
    if column not in annual_summary.columns:
        annual_summary[column] = 0

annual_summary["Net Change"] = (
    annual_summary["Addition"]
    - annual_summary["Deletion"]
)

print(annual_summary.to_string())


# --------------------------------------------------
# 4. Expected constituent-security counts
# --------------------------------------------------

print_section("4. EXPECTED SECURITY COUNTS BY CHECKPOINT")

checkpoint_dates = [
    pd.Timestamp("2021-01-01"),
    pd.Timestamp("2021-12-31"),
    pd.Timestamp("2022-12-31"),
    pd.Timestamp("2023-12-31"),
    pd.Timestamp("2024-12-31"),
    pd.Timestamp("2025-12-31"),
    ANCHOR_DATE,
]

checkpoint_rows = []

for checkpoint in checkpoint_dates:

    later_changes = changes[
        changes["effective_date"] > checkpoint
    ]

    later_additions = int(
        (later_changes["action"] == "Addition").sum()
    )

    later_deletions = int(
        (later_changes["action"] == "Deletion").sum()
    )

    expected_count = (
        anchor_count
        - later_additions
        + later_deletions
    )

    checkpoint_rows.append(
        {
            "checkpoint_date": checkpoint.date(),
            "expected_security_count": expected_count,
            "later_additions_reversed": later_additions,
            "later_deletions_reversed": later_deletions,
        }
    )


checkpoint_df = pd.DataFrame(checkpoint_rows)

print(checkpoint_df.to_string(index=False))


# --------------------------------------------------
# 5. Reverse membership integrity test
# --------------------------------------------------
print_section("5. REVERSE MEMBERSHIP INTEGRITY TEST")

current_state = set(anchor["Ticker"])

issues = []
transition_rows = []

# Membership events and ticker-alias events must
# share the same reverse chronological timeline.
effective_dates = sorted(
    set(changes["effective_date"])
    | set(aliases["effective_date"]),
    reverse=True,
)


for effective_date in effective_dates:

    date_rows = changes[
        changes["effective_date"] == effective_date
    ]

    additions = set(
        date_rows.loc[
            date_rows["action"] == "Addition",
            "ticker",
        ]
    )

    deletions = set(
        date_rows.loc[
            date_rows["action"] == "Deletion",
            "ticker",
        ]
    )

    aliases_applied = 0


    # ----------------------------------------------
    # A ticker should not normally be both added
    # and deleted on the same effective date.
    # ----------------------------------------------

    same_day_overlap = additions & deletions

    for ticker in sorted(same_day_overlap):

        issues.append(
            {
                "effective_date": effective_date.date(),
                "ticker": ticker,
                "issue_type": "same_day_addition_and_deletion",
                "details": (
                    "Ticker appears as both an addition "
                    "and deletion on the same effective date."
                ),
            }
        )


    # ----------------------------------------------
    # Reverse original additions
    #
    # Forward:
    # security enters index
    #
    # Backward:
    # security must be removed
    # ----------------------------------------------

    for ticker in sorted(additions):

        company_rows = date_rows.loc[
            (
                (date_rows["ticker"] == ticker)
                & (date_rows["action"] == "Addition")
            ),
            "company_name",
        ]

        company = (
            company_rows.iloc[0]
            if not company_rows.empty
            else ticker
        )

        if ticker not in current_state:

            issues.append(
                {
                    "effective_date": effective_date.date(),
                    "ticker": ticker,
                    "issue_type": (
                        "reverse_addition_security_not_present"
                    ),
                    "details": (
                        f"{company}: security should be present "
                        "in the later membership state before "
                        "its addition is reversed."
                    ),
                }
            )

        else:

            current_state.remove(ticker)


    # ----------------------------------------------
    # Reverse original deletions
    #
    # Forward:
    # security leaves index
    #
    # Therefore the later state should NOT contain it.
    #
    # Backward:
    # restore the security.
    # ----------------------------------------------

    for ticker in sorted(deletions):

        company_rows = date_rows.loc[
            (
                (date_rows["ticker"] == ticker)
                & (date_rows["action"] == "Deletion")
            ),
            "company_name",
        ]

        company = (
            company_rows.iloc[0]
            if not company_rows.empty
            else ticker
        )

        # Check state BEFORE restoring the security.
        if ticker in current_state:

            issues.append(
                {
                    "effective_date": effective_date.date(),
                    "ticker": ticker,
                    "issue_type": (
                        "reverse_deletion_security_already_present"
                    ),
                    "details": (
                        f"{company}: security was already present "
                        "before its historical deletion was reversed."
                    ),
                }
            )

        else:

            # Restore it to obtain the state that existed
            # immediately before the deletion.
            current_state.add(ticker)


    # ----------------------------------------------
    # Reverse ticker / identity changes
    #
    # Forward:
    # CDAY -> DAY
    #
    # Backward:
    # DAY -> CDAY
    #
    # No membership-count change should occur.
    # ----------------------------------------------

    date_aliases = aliases[
        aliases["effective_date"] == effective_date
    ]

    for _, alias in date_aliases.iterrows():

        old_ticker = alias["old_ticker"]
        new_ticker = alias["new_ticker"]

        if (
            new_ticker in current_state
            and old_ticker not in current_state
        ):

            current_state.remove(new_ticker)
            current_state.add(old_ticker)

            aliases_applied += 1

            print(
                f"Alias reversed: "
                f"{new_ticker} -> {old_ticker} "
                f"({effective_date.date()})"
            )

        elif (
            new_ticker in current_state
            and old_ticker in current_state
        ):

            issues.append(
                {
                    "effective_date": effective_date.date(),
                    "ticker": new_ticker,
                    "issue_type": "alias_identity_collision",
                    "details": (
                        f"Both {old_ticker} and {new_ticker} "
                        "are present while reversing this alias."
                    ),
                }
            )

        elif (
            new_ticker not in current_state
            and old_ticker in current_state
        ):

            issues.append(
                {
                    "effective_date": effective_date.date(),
                    "ticker": new_ticker,
                    "issue_type": "alias_already_in_old_state",
                    "details": (
                        f"{old_ticker} is already present while "
                        f"{new_ticker} is absent before alias reversal."
                    ),
                }
            )

        else:

            issues.append(
                {
                    "effective_date": effective_date.date(),
                    "ticker": new_ticker,
                    "issue_type": "alias_security_not_present",
                    "details": (
                        f"Neither {new_ticker} nor {old_ticker} "
                        "is present at the alias effective date."
                    ),
                }
            )


    # ----------------------------------------------
    # Record state after reversing this date
    # ----------------------------------------------

    transition_rows.append(
        {
            "effective_date": effective_date.date(),
            "security_count_after_reverse": len(current_state),
            "additions_reversed": len(additions),
            "deletions_reversed": len(deletions),
            "aliases_reversed": aliases_applied,
        }
    )
# --------------------------------------------------
# 6. Reverse-state result
# --------------------------------------------------

print_section("6. REVERSE-STATE RESULT")

print(
    f"Anchor security count: {anchor_count}"
)

print(
    f"Security count after reversing all actions: "
    f"{len(current_state)}"
)

expected_start_count = (
    anchor_count
    - int((changes["action"] == "Addition").sum())
    + int((changes["action"] == "Deletion").sum())
)

print(
    f"Count expected from action totals: "
    f"{expected_start_count}"
)


if len(current_state) == expected_start_count:
    print(
        "PASS: Reverse-state security count matches "
        "the count implied by the action ledger."
    )
else:
    print(
        "CHECK: Reverse-state security count does not "
        "match the count implied by the action ledger."
    )


# --------------------------------------------------
# 7. Integrity issues
# --------------------------------------------------

print_section("7. SECURITY-IDENTITY ISSUES")

issues_df = pd.DataFrame(issues)


if issues_df.empty:

    print(
        "PASS: No security-identity conflicts were "
        "detected during reverse reconstruction."
    )

else:

    print(
        f"Detected {len(issues_df)} issue(s).\n"
    )

    print(
        issues_df.to_string(index=False)
    )


# --------------------------------------------------
# 8. Save audit outputs
# --------------------------------------------------

print_section("8. AUDIT OUTPUTS")

INTERIM_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

checkpoint_df.to_csv(
    CHECKPOINT_FILE,
    index=False,
)

print(
    f"Checkpoint report saved:\n{CHECKPOINT_FILE}"
)


if issues_df.empty:

    if ISSUES_FILE.exists():
        ISSUES_FILE.unlink()

    print(
        "\nNo integrity-issue file was required."
    )

else:

    issues_df.to_csv(
        ISSUES_FILE,
        index=False,
    )

    print(
        f"\nIntegrity issues saved:\n{ISSUES_FILE}"
    )


# --------------------------------------------------
# Final result
# --------------------------------------------------

print_section("AUDIT RESULT")

print(
    f"Anchor securities: {anchor_count}"
)

print(
    f"Historical actions: {len(changes)}"
)

print(
    f"Expected securities at 2021-01-01: "
    f"{expected_start_count}"
)

print(
    f"Security-identity issues: {len(issues_df)}"
)


if issues_df.empty:

    print("\nFULL-HISTORY INTEGRITY AUDIT PASSED.")

    print(
        "The historical action ledger is compatible "
        "with the constituent anchor."
    )

    sys.exit(0)

else:

    print(
        "\nAUDIT REQUIRES IDENTITY RESOLUTION."
    )

    print(
        "The action ledger is structurally valid, "
        "but one or more ticker/security identities "
        "must be reconciled before membership intervals "
        "are generated."
    )

    sys.exit(2)