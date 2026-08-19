from contextlib import redirect_stdout
from pathlib import Path
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data" / "interim"
REFERENCE = ROOT / "data" / "reference" / "securities"

MEMBERSHIP_FILE = (
    INTERIM
    / "sp500_membership_intervals_2021_2025.csv"
)

TICKER_FILE = (
    INTERIM
    / "sp500_ticker_history_2021_2025.csv"
)

CHECKPOINT_FILE = (
    INTERIM
    / "membership_count_checkpoints.csv"
)

ALIAS_FILE = (
    REFERENCE
    / "security_aliases.csv"
)

TERMINATION_FILE = (
    REFERENCE
    / "security_market_terminations.csv"
)

PRICE_MANIFEST_FILE = (
    INTERIM
    / "standardized_price_history_manifest.csv"
)

REPORT_FILE = (
    ROOT
    / "reports"
    / "data_quality"
    / "membership_interval_integrity_audit.txt"
)

START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2025-12-31")
END_EXCLUSIVE = pd.Timestamp("2026-01-01")

MEMBERSHIP_COLUMNS = [
    "security_key",
    "company_name_reference",
    "valid_from",
    "left_censored",
    "entry_ticker",
    "entry_source_url",
    "valid_to_exclusive",
    "right_censored",
    "exit_ticker",
    "exit_source_url",
]

TICKER_COLUMNS = [
    "security_key",
    "ticker",
    "ticker_valid_from",
    "left_censored",
    "ticker_valid_to_exclusive",
    "right_censored",
]

CHECKPOINT_COLUMNS = [
    "checkpoint_date",
    "expected_security_count",
    "later_additions_reversed",
    "later_deletions_reversed",
]

ALIAS_COLUMNS = [
    "effective_date",
    "old_ticker",
    "new_ticker",
    "old_company_name",
    "new_company_name",
    "event_type",
    "source_type",
    "source_url",
    "notes",
]

MANIFEST_COLUMNS = [
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

TERMINATION_COLUMNS = {
    "security_key",
    "project_ticker",
    "last_valid_trading_date",
    "accepted_effective_end_exclusive",
    "provider_terminal_date",
    "provider_terminal_action",
    "termination_basis",
    "evidence_status",
}

EXPECTED_CHECKPOINTS = [
    ("2021-01-01", 505, 100, 102),
    ("2021-12-31", 505, 81, 83),
    ("2022-12-31", 503, 64, 64),
    ("2023-12-31", 503, 47, 47),
    ("2024-12-31", 503, 31, 31),
    ("2025-12-31", 503, 12, 12),
    ("2026-08-10", 503, 0, 0),
]

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

failures = []
passed = 0


def section(title):
    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


def test(condition, message, detail=None):
    global passed

    if bool(condition):
        passed += 1
        print(f"PASS: {message}")

    else:
        failures.append(message)
        print(f"FAIL: {message}")

        if detail:
            print(detail)


def load_exact(path, label, columns):
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {label}: {path}"
        )

    frame = pd.read_csv(
        path,
        dtype=str,
    )

    if list(frame.columns) != columns:
        raise ValueError(
            f"{label} schema mismatch.\n"
            f"Expected: {columns}\n"
            f"Actual:   {list(frame.columns)}"
        )

    return frame


def load_required(path, label, columns):
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {label}: {path}"
        )

    frame = pd.read_csv(
        path,
        dtype=str,
    )

    missing = (
        columns
        - set(frame.columns)
    )

    if missing:
        raise ValueError(
            f"{label} missing columns: "
            f"{sorted(missing)}"
        )

    return frame


def dates(frame, columns, label):
    pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}$"
    )

    for column in columns:
        raw = frame[column]

        valid_format = (
            raw.notna()
            & raw.astype(str).str.match(pattern)
        )

        test(
            valid_format.all(),
            (
                f"{label}.{column} uses "
                "YYYY-MM-DD format."
            ),
        )

        frame[column] = pd.to_datetime(
            raw,
            format="%Y-%m-%d",
            errors="coerce",
        )

        test(
            frame[column].notna().all(),
            (
                f"{label}.{column} has "
                "valid dates."
            ),
        )


def booleans(frame, columns, label):
    for column in columns:
        raw = (
            frame[column]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        test(
            raw.isin(
                ["true", "false"]
            ).all(),
            (
                f"{label}.{column} contains "
                "only True/False."
            ),
        )

        frame[column] = raw.map(
            {
                "true": True,
                "false": False,
            }
        )


def integers(frame, columns, label):
    for column in columns:
        value = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

        valid = (
            value.notna()
            & value.mod(1).eq(0)
        )

        test(
            valid.all(),
            (
                f"{label}.{column} contains "
                "only integers."
            ),
        )

        frame[column] = value.astype(
            "Int64"
        )


def tickers(frame, columns):
    for column in columns:
        frame[column] = frame[column].apply(
            lambda value: (
                str(value).strip().upper()
                if pd.notna(value)
                else value
            )
        )


def urls(series):
    return (
        series
        .fillna("")
        .astype(str)
        .str.match(
            r"^https?://",
            na=False,
        )
    )


def canonicalizer(aliases):
    forward = dict(
        zip(
            aliases["old_ticker"],
            aliases["new_ticker"],
        )
    )

    def canonical(ticker):
        current = (
            str(ticker)
            .strip()
            .upper()
        )

        seen = set()

        while current in forward:
            if current in seen:
                raise ValueError(
                    "Alias cycle detected at "
                    f"{current}."
                )

            seen.add(current)
            current = forward[current]

        return current

    alias_tickers = (
        set(forward)
        | set(forward.values())
    )

    for ticker in alias_tickers:
        canonical(ticker)

    return canonical


def run_audit():
    section(
        "S&P 500 MEMBERSHIP INTERVAL "
        "INTEGRITY AUDIT"
    )

    membership = load_exact(
        MEMBERSHIP_FILE,
        "membership file",
        MEMBERSHIP_COLUMNS,
    )

    history = load_exact(
        TICKER_FILE,
        "ticker-history file",
        TICKER_COLUMNS,
    )

    checkpoints = load_exact(
        CHECKPOINT_FILE,
        "checkpoint file",
        CHECKPOINT_COLUMNS,
    )

    aliases = load_exact(
        ALIAS_FILE,
        "alias file",
        ALIAS_COLUMNS,
    )

    manifest = load_exact(
        PRICE_MANIFEST_FILE,
        "price manifest",
        MANIFEST_COLUMNS,
    )

    terminations = load_required(
        TERMINATION_FILE,
        "market-termination reference",
        TERMINATION_COLUMNS,
    )

    dates(
        membership,
        [
            "valid_from",
            "valid_to_exclusive",
        ],
        "membership",
    )

    dates(
        history,
        [
            "ticker_valid_from",
            "ticker_valid_to_exclusive",
        ],
        "history",
    )

    dates(
        checkpoints,
        ["checkpoint_date"],
        "checkpoints",
    )

    dates(
        aliases,
        ["effective_date"],
        "aliases",
    )

    dates(
        manifest,
        [
            "first_date",
            "last_date",
            "effective_expected_start",
            "effective_expected_end_exclusive",
        ],
        "manifest",
    )

    dates(
        terminations,
        [
            "last_valid_trading_date",
            "accepted_effective_end_exclusive",
            "provider_terminal_date",
        ],
        "terminations",
    )

    booleans(
        membership,
        [
            "left_censored",
            "right_censored",
        ],
        "membership",
    )

    booleans(
        history,
        [
            "left_censored",
            "right_censored",
        ],
        "history",
    )

    integers(
        checkpoints,
        [
            "expected_security_count",
            "later_additions_reversed",
            "later_deletions_reversed",
        ],
        "checkpoints",
    )

    integers(
        manifest,
        ["analysis_rows"],
        "manifest",
    )

    tickers(
        membership,
        [
            "security_key",
            "entry_ticker",
            "exit_ticker",
        ],
    )

    tickers(
        history,
        [
            "security_key",
            "ticker",
        ],
    )

    tickers(
        aliases,
        [
            "old_ticker",
            "new_ticker",
        ],
    )

    tickers(
        manifest,
        [
            "security_key",
            "project_ticker",
            "provider_symbol",
        ],
    )

    tickers(
        terminations,
        [
            "security_key",
            "project_ticker",
        ],
    )

    section(
        "1. STRUCTURE"
    )

    test(
        len(membership) == 593,
        "Membership contains 593 rows.",
    )

    test(
        membership[
            "security_key"
        ].nunique() == 593,
        (
            "Membership contains 593 "
            "security identities."
        ),
    )

    test(
        len(history) == 594,
        "Ticker history contains 594 rows.",
    )

    test(
        history[
            "ticker"
        ].nunique() == 594,
        (
            "Ticker history contains 594 "
            "historical tickers."
        ),
    )

    test(
        len(manifest) == 596,
        "Price manifest contains 596 requests.",
    )

    test(
        manifest[
            "security_key"
        ].nunique() == 595,
        (
            "Price manifest contains 595 "
            "security keys."
        ),
    )

    frames = [
        ("Membership", membership),
        ("Ticker history", history),
        ("Checkpoints", checkpoints),
        ("Aliases", aliases),
        ("Terminations", terminations),
        ("Price manifest", manifest),
    ]

    for label, frame in frames:
        test(
            not frame.duplicated().any(),
            (
                f"{label} has no exact "
                "duplicates."
            ),
        )

    required_membership = [
        "security_key",
        "company_name_reference",
        "valid_from",
        "left_censored",
        "entry_ticker",
        "valid_to_exclusive",
        "right_censored",
    ]

    test(
        not membership[
            required_membership
        ].isna().any().any(),
        (
            "Required membership fields "
            "have no nulls."
        ),
    )

    test(
        not history.isna().any().any(),
        (
            "Ticker-history fields have "
            "no nulls."
        ),
    )

    test(
        not checkpoints.isna().any().any(),
        (
            "Checkpoint fields have "
            "no nulls."
        ),
    )

    test(
        not aliases.isna().any().any(),
        (
            "Alias fields have no nulls."
        ),
    )

    test(
        not terminations[
            list(TERMINATION_COLUMNS)
        ].isna().any().any(),
        (
            "Required market-termination "
            "fields have no nulls."
        ),
    )

    section(
        "2. MEMBERSHIP SEMANTICS"
    )

    test(
        not membership[
            "security_key"
        ].duplicated().any(),
        (
            "Each security has one membership "
            "interval in this universe."
        ),
    )

    test(
        (
            membership["valid_from"]
            < membership[
                "valid_to_exclusive"
            ]
        ).all(),
        (
            "Every membership interval has "
            "positive duration."
        ),
    )

    test(
        membership[
            "valid_from"
        ].between(
            START,
            END,
        ).all(),
        (
            "Every membership start is "
            "inside the analysis window."
        ),
    )

    test(
        membership[
            "valid_to_exclusive"
        ].le(
            END_EXCLUSIVE
        ).all(),
        (
            "No membership interval extends "
            "beyond the analysis scope."
        ),
    )

    test(
        membership[
            "left_censored"
        ].eq(
            membership[
                "valid_from"
            ].eq(START)
        ).all(),
        (
            "Membership left-censor flags "
            "match the start boundary."
        ),
    )

    test(
        membership[
            "right_censored"
        ].eq(
            membership[
                "valid_to_exclusive"
            ].eq(END_EXCLUSIVE)
        ).all(),
        (
            "Membership right-censor flags "
            "match the end boundary."
        ),
    )

    test(
        int(
            membership[
                "left_censored"
            ].sum()
        ) == 505,
        (
            "Exactly 505 securities are active "
            "at the analysis start."
        ),
    )

    test(
        int(
            membership[
                "right_censored"
            ].sum()
        ) == 503,
        (
            "Exactly 503 securities are active "
            "at the analysis end."
        ),
    )

    test(
        membership[
            "entry_source_url"
        ].isna().eq(
            membership[
                "left_censored"
            ]
        ).all(),
        (
            "Entry provenance is absent only "
            "for left-censored intervals."
        ),
    )

    test(
        membership[
            "exit_ticker"
        ].isna().eq(
            membership[
                "right_censored"
            ]
        ).all(),
        (
            "Exit tickers are absent only for "
            "right-censored intervals."
        ),
    )

    test(
        membership[
            "exit_source_url"
        ].isna().eq(
            membership[
                "right_censored"
            ]
        ).all(),
        (
            "Exit provenance is absent only "
            "for right-censored intervals."
        ),
    )

    test(
        urls(
            membership.loc[
                membership[
                    "entry_source_url"
                ].notna(),
                "entry_source_url",
            ]
        ).all(),
        (
            "Observed entries have HTTP(S) "
            "provenance."
        ),
    )

    test(
        urls(
            membership.loc[
                membership[
                    "exit_source_url"
                ].notna(),
                "exit_source_url",
            ]
        ).all(),
        (
            "Observed exits have HTTP(S) "
            "provenance."
        ),
    )

    section(
        "3. IDENTITY AND TICKER HISTORY"
    )

    test(
        not aliases[
            "old_ticker"
        ].duplicated().any(),
        "Alias old tickers are unique.",
    )

    test(
        not aliases[
            "new_ticker"
        ].duplicated().any(),
        "Alias new tickers are unique.",
    )

    test(
        aliases[
            "old_ticker"
        ].ne(
            aliases[
                "new_ticker"
            ]
        ).all(),
        (
            "No alias maps a ticker "
            "to itself."
        ),
    )

    test(
        urls(
            aliases[
                "source_url"
            ]
        ).all(),
        (
            "Every alias has HTTP(S) "
            "provenance."
        ),
    )

    alias_rows = set(
        zip(
            aliases[
                "effective_date"
            ].dt.strftime("%Y-%m-%d"),
            aliases[
                "old_ticker"
            ],
            aliases[
                "new_ticker"
            ],
        )
    )

    expected_aliases = {
        (
            "2024-02-01",
            "CDAY",
            "DAY",
        ),
        (
            "2026-06-24",
            "SATS",
            "ECHO",
        ),
    }

    test(
        alias_rows == expected_aliases,
        (
            "The alias file contains the two "
            "documented identity events."
        ),
    )

    canonical = canonicalizer(
        aliases
    )

    test(
        membership[
            "entry_ticker"
        ].map(
            canonical
        ).eq(
            membership[
                "security_key"
            ]
        ).all(),
        (
            "Every entry ticker resolves to "
            "its canonical security key."
        ),
    )

    exit_rows = membership[
        "exit_ticker"
    ].notna()

    test(
        membership.loc[
            exit_rows,
            "exit_ticker",
        ].map(
            canonical
        ).eq(
            membership.loc[
                exit_rows,
                "security_key",
            ]
        ).all(),
        (
            "Every exit ticker resolves to "
            "its canonical security key."
        ),
    )

    test(
        history[
            "ticker"
        ].map(
            canonical
        ).eq(
            history[
                "security_key"
            ]
        ).all(),
        (
            "Every historical ticker resolves "
            "to its canonical security key."
        ),
    )

    post_scope = aliases[
        aliases[
            "effective_date"
        ].gt(END)
    ]

    post_symbols = (
        set(
            post_scope[
                "old_ticker"
            ]
        )
        | set(
            post_scope[
                "new_ticker"
            ]
        )
    )

    post_history = history[
        history[
            "ticker"
        ].isin(
            post_symbols
        )
    ]

    test(
        post_history.empty,
        (
            "Post-scope aliases do not create "
            "in-scope ticker-history rows."
        ),
        post_history.to_string(
            index=False
        ),
    )

    test(
        (
            history[
                "ticker_valid_from"
            ]
            < history[
                "ticker_valid_to_exclusive"
            ]
        ).all(),
        (
            "Every ticker segment has "
            "positive duration."
        ),
    )

    test(
        not history.duplicated(
            [
                "security_key",
                "ticker_valid_from",
            ]
        ).any(),
        (
            "Ticker segment starts are unique "
            "within each security."
        ),
    )

    test(
        not history[
            "ticker"
        ].duplicated().any(),
        (
            "Every historical ticker appears "
            "in one segment."
        ),
    )

    test(
        history[
            "left_censored"
        ].eq(
            history[
                "ticker_valid_from"
            ].eq(START)
        ).all(),
        (
            "Ticker left-censor flags match "
            "the start boundary."
        ),
    )

    test(
        history[
            "right_censored"
        ].eq(
            history[
                "ticker_valid_to_exclusive"
            ].eq(END_EXCLUSIVE)
        ).all(),
        (
            "Ticker right-censor flags match "
            "the end boundary."
        ),
    )

    partition_errors = []

    for member in membership.itertuples(
        index=False
    ):
        rows = (
            history[
                history[
                    "security_key"
                ].eq(
                    member.security_key
                )
            ]
            .sort_values(
                "ticker_valid_from"
            )
        )

        if rows.empty:
            partition_errors.append(
                f"{member.security_key}: "
                "no ticker history"
            )

            continue

        first = rows.iloc[0]
        last = rows.iloc[-1]

        if (
            first[
                "ticker_valid_from"
            ]
            != member.valid_from
        ):
            partition_errors.append(
                f"{member.security_key}: "
                "start mismatch"
            )

        if (
            last[
                "ticker_valid_to_exclusive"
            ]
            != member.valid_to_exclusive
        ):
            partition_errors.append(
                f"{member.security_key}: "
                "end mismatch"
            )

        if (
            first[
                "ticker"
            ]
            != member.entry_ticker
        ):
            partition_errors.append(
                f"{member.security_key}: "
                "entry ticker mismatch"
            )

        if (
            not member.right_censored
            and last[
                "ticker"
            ]
            != member.exit_ticker
        ):
            partition_errors.append(
                f"{member.security_key}: "
                "exit ticker mismatch"
            )

        starts = (
            rows[
                "ticker_valid_from"
            ]
            .iloc[1:]
            .reset_index(drop=True)
        )

        prior_ends = (
            rows[
                "ticker_valid_to_exclusive"
            ]
            .iloc[:-1]
            .reset_index(drop=True)
        )

        if not starts.eq(
            prior_ends
        ).all():
            partition_errors.append(
                f"{member.security_key}: "
                "gap or overlap"
            )

    test(
        not partition_errors,
        (
            "Ticker history exactly partitions "
            "membership intervals."
        ),
        "\n".join(
            partition_errors[:50]
        ),
    )

    multi = (
        history
        .groupby(
            "security_key"
        )["ticker"]
        .agg(list)
    )

    multi = (
        multi.loc[
            multi.map(len).gt(1)
        ]
        .to_dict()
    )

    test(
        multi == {
            "DAY": [
                "CDAY",
                "DAY",
            ]
        },
        (
            "DAY is the only multi-segment "
            "identity, with CDAY then DAY."
        ),
        str(multi),
    )

    section(
        "4. CHECKPOINTS"
    )

    actual_checkpoints = [
        (
            row.checkpoint_date.strftime(
                "%Y-%m-%d"
            ),
            int(
                row.expected_security_count
            ),
            int(
                row.later_additions_reversed
            ),
            int(
                row.later_deletions_reversed
            ),
        )
        for row in checkpoints.itertuples(
            index=False
        )
    ]

    test(
        actual_checkpoints
        == EXPECTED_CHECKPOINTS,
        (
            "Checkpoint evidence matches "
            "the documented reconstruction."
        ),
    )

    reconstruction_errors = []
    interval_errors = []

    for row in checkpoints.itertuples(
        index=False
    ):
        reconstructed = (
            503
            - int(
                row.later_additions_reversed
            )
            + int(
                row.later_deletions_reversed
            )
        )

        if reconstructed != int(
            row.expected_security_count
        ):
            reconstruction_errors.append(
                str(
                    row.checkpoint_date.date()
                )
            )

        if row.checkpoint_date <= END:
            active = (
                membership[
                    "valid_from"
                ].le(
                    row.checkpoint_date
                )
                & membership[
                    "valid_to_exclusive"
                ].gt(
                    row.checkpoint_date
                )
            )

            active_count = int(
                active.sum()
            )

            if active_count != int(
                row.expected_security_count
            ):
                interval_errors.append(
                    f"{row.checkpoint_date.date()}: "
                    f"{active_count}"
                )

    test(
        not reconstruction_errors,
        (
            "All checkpoints reconcile to "
            "the 503-security anchor."
        ),
        str(
            reconstruction_errors
        ),
    )

    test(
        not interval_errors,
        (
            "All six in-scope counts match "
            "the interval table."
        ),
        str(
            interval_errors
        ),
    )

    print(
        "INFO: The 2026-08-10 row is an "
        "anchor control outside interval scope."
    )

    section(
        "5. PRICE-BRIDGE READINESS"
    )

    termination_keys = set(
        terminations[
            "security_key"
        ]
    )

    test(
        termination_keys
        == EXPECTED_TERMINATIONS,
        (
            "The termination reference contains "
            "exactly ten validated cases."
        ),
        str(
            sorted(
                termination_keys
            )
        ),
    )

    test(
        not terminations.duplicated(
            [
                "security_key",
                "project_ticker",
            ]
        ).any(),
        (
            "Termination security/ticker "
            "keys are unique."
        ),
    )

    test(
        terminations[
            "evidence_status"
        ].isin(
            [
                "VERIFIED",
                "CORROBORATED",
            ]
        ).all(),
        (
            "All market terminations have "
            "accepted evidence status."
        ),
    )

    test(
        (
            terminations[
                "accepted_effective_end_exclusive"
            ]
            > terminations[
                "last_valid_trading_date"
            ]
        ).all(),
        (
            "Termination boundaries follow "
            "their last valid sessions."
        ),
    )

    history_pairs = set(
        history[
            [
                "security_key",
                "ticker",
            ]
        ].itertuples(
            index=False,
            name=None,
        )
    )

    manifest_pairs = set(
        manifest[
            [
                "security_key",
                "project_ticker",
            ]
        ].itertuples(
            index=False,
            name=None,
        )
    )

    member_keys = set(
        membership[
            "security_key"
        ]
    )

    manifest_keys = set(
        manifest[
            "security_key"
        ]
    )

    missing_pairs = sorted(
        history_pairs
        - manifest_pairs
    )

    missing_keys = sorted(
        member_keys
        - manifest_keys
    )

    extra_pairs = sorted(
        manifest_pairs
        - history_pairs
    )

    extra_keys = sorted(
        manifest_keys
        - member_keys
    )

    test(
        not missing_pairs,
        (
            "Every ticker segment has a "
            "standardized price request."
        ),
        str(
            missing_pairs[:50]
        ),
    )

    test(
        not missing_keys,
        (
            "Every membership key exists "
            "in the price manifest."
        ),
        str(
            missing_keys[:50]
        ),
    )

    test(
        len(extra_pairs) == 2,
        (
            "Exactly two price requests "
            "are benchmarks."
        ),
        str(extra_pairs),
    )

    test(
        len(extra_keys) == 2,
        (
            "Exactly two price security "
            "keys are benchmarks."
        ),
        str(extra_keys),
    )

    test(
        not manifest.duplicated(
            [
                "security_key",
                "project_ticker",
            ]
        ).any(),
        (
            "Price-manifest request keys "
            "are unique."
        ),
    )

    manifest_map = {
        (
            row.security_key,
            row.project_ticker,
        ): row
        for row in manifest.itertuples(
            index=False
        )
    }

    termination_map = {
        (
            row.security_key,
            row.project_ticker,
        ): row
        for row in terminations.itertuples(
            index=False
        )
    }

    coverage_errors = []
    documented = set()

    for row in history.itertuples(
        index=False
    ):
        pair = (
            row.security_key,
            row.ticker,
        )

        request = manifest_map.get(
            pair
        )

        if request is None:
            continue

        if (
            request.effective_expected_start
            > row.ticker_valid_from
        ):
            coverage_errors.append(
                f"{row.security_key}/"
                f"{row.ticker}: late start"
            )

        required_end = (
            row.ticker_valid_to_exclusive
        )

        termination = termination_map.get(
            pair
        )

        if termination is not None:
            required_end = min(
                required_end,
                termination
                .accepted_effective_end_exclusive,
            )

        request_end = (
            request
            .effective_expected_end_exclusive
        )

        if request_end < required_end:
            coverage_errors.append(
                f"{row.security_key}/"
                f"{row.ticker}: early end"
            )

        if (
            request_end
            < row.ticker_valid_to_exclusive
        ):
            if termination is None:
                coverage_errors.append(
                    f"{row.security_key}/"
                    f"{row.ticker}: "
                    "undocumented truncation"
                )

            elif (
                request_end
                != termination
                .accepted_effective_end_exclusive
            ):
                coverage_errors.append(
                    f"{row.security_key}/"
                    f"{row.ticker}: "
                    "termination mismatch"
                )

            else:
                documented.add(
                    row.security_key
                )

    test(
        not coverage_errors,
        (
            "Every price request covers its "
            "usable membership segment."
        ),
        "\n".join(
            coverage_errors[:50]
        ),
    )

    test(
        documented
        == EXPECTED_TERMINATIONS,
        (
            "All ten early price endings are "
            "documented market terminations."
        ),
        str(
            sorted(documented)
        ),
    )

    duplicate_keys = (
        manifest
        .groupby(
            "security_key"
        )["project_ticker"]
        .agg(list)
    )

    duplicate_keys = (
        duplicate_keys.loc[
            duplicate_keys.map(len).gt(1)
        ]
        .to_dict()
    )

    test(
        duplicate_keys == {
            "DAY": [
                "CDAY",
                "DAY",
            ]
        },
        (
            "DAY is the only key with two "
            "standardized ticker requests."
        ),
        str(
            duplicate_keys
        ),
    )

    section(
        "6. FINAL QUALITY GATE"
    )

    if failures:
        print(
            "MEMBERSHIP_INTERVAL_"
            "INTEGRITY_AUDIT_FAILED"
        )

        print(
            f"Passed checks: {passed}"
        )

        print(
            f"Failed checks: "
            f"{len(failures)}"
        )

        for number, failure in enumerate(
            failures,
            start=1,
        ):
            print(
                f"{number}. {failure}"
            )

        return False

    print(
        "MEMBERSHIP_INTERVAL_"
        "INTEGRITY_AUDIT_PASSED"
    )

    print(
        f"Passed checks: {passed}"
    )

    print(
        "Membership intervals: "
        f"{len(membership):,}"
    )

    print(
        "Security identities: "
        f"{membership['security_key'].nunique():,}"
    )

    print(
        "Ticker-history segments: "
        f"{len(history):,}"
    )

    print(
        "Historical tickers: "
        f"{history['ticker'].nunique():,}"
    )

    print(
        "In-scope checkpoints validated: 6"
    )

    print(
        "Standardized constituent requests "
        f"mapped: {len(history_pairs):,}"
    )

    print(
        "Documented market-termination "
        f"truncations: {len(documented):,}"
    )

    print(
        "Non-constituent benchmark requests: "
        f"{len(extra_pairs):,}"
    )

    print(
        "No interval gaps or overlaps remain."
    )

    print(
        "No unexplained identity "
        "mappings remain."
    )

    print(
        "No undocumented price-window "
        "truncations remain."
    )

    print(
        "POINT-IN-TIME MEMBERSHIP "
        "QUALITY GATE COMPLETE."
    )

    return True


def main():
    REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = False
    caught = None

    with REPORT_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as report:
        with redirect_stdout(report):
            try:
                result = run_audit()

            except Exception as error:
                caught = error

                section(
                    "AUDIT ABORTED"
                )

                print(
                    type(error).__name__
                )

                print(error)

    if caught is not None:
        print(
            "MEMBERSHIP INTERVAL "
            "INTEGRITY AUDIT ABORTED"
        )

        print(
            "Saved diagnostic report: "
            f"{REPORT_FILE}"
        )

        print(caught)
        sys.exit(2)

    if not result:
        print(
            "MEMBERSHIP INTERVAL "
            "INTEGRITY AUDIT FAILED"
        )

        print(
            "Saved audit report: "
            f"{REPORT_FILE}"
        )

        sys.exit(1)

    print(
        "MEMBERSHIP INTERVAL "
        "INTEGRITY AUDIT PASSED"
    )

    print(
        "Saved audit report: "
        f"{REPORT_FILE}"
    )


if __name__ == "__main__":
    main()