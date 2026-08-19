from contextlib import redirect_stdout
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data" / "interim"

PRICE_FILE = (
    INTERIM
    / "standardized_price_history.csv.gz"
)

PRICE_MANIFEST_FILE = (
    INTERIM
    / "standardized_price_history_manifest.csv"
)

MEMBERSHIP_FILE = (
    INTERIM
    / "sp500_membership_intervals_2021_2025.csv"
)

TICKER_FILE = (
    INTERIM
    / "sp500_ticker_history_2021_2025.csv"
)

BRIDGE_FILE = (
    INTERIM
    / "sp500_membership_price_bridge_2021_2025.csv.gz"
)

BRIDGE_MANIFEST_FILE = (
    INTERIM
    / "sp500_membership_price_bridge_manifest.csv"
)

BENCHMARK_FILE = (
    INTERIM
    / "sp500_benchmark_price_history_2021_2025.csv.gz"
)

REPORT_FILE = (
    ROOT
    / "reports"
    / "data_quality"
    / "membership_price_bridge_integrity_audit.txt"
)

START = pd.Timestamp("2021-01-01")
END_EXCLUSIVE = pd.Timestamp("2026-01-01")

PRICE_COLUMNS = [
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

PRICE_MANIFEST_COLUMNS = [
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

CONTROL_COLUMNS = [
    "membership_valid_from",
    "membership_valid_to_exclusive",
    "ticker_valid_from",
    "ticker_valid_to_exclusive",
    "effective_price_start",
    "effective_price_end_exclusive",
    "usable_start",
    "usable_end_exclusive",
]

BRIDGE_COLUMNS = (
    PRICE_COLUMNS
    + CONTROL_COLUMNS
)

BRIDGE_MANIFEST_COLUMNS = [
    "security_key",
    "project_ticker",
    "membership_valid_from",
    "membership_valid_to_exclusive",
    "ticker_valid_from",
    "ticker_valid_to_exclusive",
    "effective_price_start",
    "effective_price_end_exclusive",
    "usable_start",
    "usable_end_exclusive",
    "standardized_rows",
    "bridge_rows",
    "rows_before_usable_window",
    "rows_after_usable_window",
    "first_bridge_date",
    "last_bridge_date",
]

NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividend",
    "split_factor",
]

failures = []
passed = 0


def section(title):
    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


def test(
    condition,
    message,
    detail=None,
):
    global passed

    if bool(condition):
        passed += 1
        print(f"PASS: {message}")

    else:
        failures.append(message)
        print(f"FAIL: {message}")

        if detail:
            print(detail)


def load_exact(
    path,
    label,
    columns,
):
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {label}: {path}"
        )

    frame = pd.read_csv(path)

    if list(frame.columns) != columns:
        raise ValueError(
            f"{label} schema mismatch.\n"
            f"Expected: {columns}\n"
            f"Actual: {list(frame.columns)}"
        )

    return frame


def normalize(
    frame,
    columns,
):
    for column in columns:
        frame[column] = (
            frame[column]
            .astype(str)
            .str.strip()
            .str.upper()
        )


def parse_dates(
    frame,
    columns,
    label,
):
    for column in columns:
        parsed = pd.to_datetime(
            frame[column],
            format="%Y-%m-%d",
            errors="coerce",
        )

        test(
            parsed.notna().all(),
            (
                f"{label}.{column} "
                "contains valid dates."
            ),
        )

        frame[column] = parsed


def pair_set(
    frame,
    ticker_column="project_ticker",
):
    return set(
        frame[
            [
                "security_key",
                ticker_column,
            ]
        ].itertuples(
            index=False,
            name=None,
        )
    )


def key_set(frame):
    return set(
        frame[
            [
                "security_key",
                "project_ticker",
                "date",
            ]
        ].itertuples(
            index=False,
            name=None,
        )
    )


def audit():
    section(
        "S&P 500 MEMBERSHIP-PRICE "
        "BRIDGE INTEGRITY AUDIT"
    )

    prices = load_exact(
        PRICE_FILE,
        "standardized price history",
        PRICE_COLUMNS,
    )

    price_manifest = load_exact(
        PRICE_MANIFEST_FILE,
        "standardized price manifest",
        PRICE_MANIFEST_COLUMNS,
    )

    membership = load_exact(
        MEMBERSHIP_FILE,
        "membership interval table",
        MEMBERSHIP_COLUMNS,
    )

    ticker_history = load_exact(
        TICKER_FILE,
        "ticker-history table",
        TICKER_COLUMNS,
    )

    bridge = load_exact(
        BRIDGE_FILE,
        "membership-price bridge",
        BRIDGE_COLUMNS,
    )

    bridge_manifest = load_exact(
        BRIDGE_MANIFEST_FILE,
        "bridge manifest",
        BRIDGE_MANIFEST_COLUMNS,
    )

    benchmark = load_exact(
        BENCHMARK_FILE,
        "benchmark history",
        PRICE_COLUMNS,
    )

    frames = [
        prices,
        price_manifest,
        membership,
        ticker_history,
        bridge,
        bridge_manifest,
        benchmark,
    ]

    for frame in frames:
        identity_columns = [
            column
            for column in [
                "security_key",
                "project_ticker",
                "ticker",
            ]
            if column in frame.columns
        ]

        normalize(
            frame,
            identity_columns,
        )

    parse_dates(
        prices,
        ["date"],
        "prices",
    )

    parse_dates(
        price_manifest,
        [
            "first_date",
            "last_date",
            "effective_expected_start",
            "effective_expected_end_exclusive",
        ],
        "price_manifest",
    )

    parse_dates(
        membership,
        [
            "valid_from",
            "valid_to_exclusive",
        ],
        "membership",
    )

    parse_dates(
        ticker_history,
        [
            "ticker_valid_from",
            "ticker_valid_to_exclusive",
        ],
        "ticker_history",
    )

    parse_dates(
        bridge,
        [
            "date",
        ]
        + CONTROL_COLUMNS,
        "bridge",
    )

    parse_dates(
        bridge_manifest,
        [
            "membership_valid_from",
            "membership_valid_to_exclusive",
            "ticker_valid_from",
            "ticker_valid_to_exclusive",
            "effective_price_start",
            "effective_price_end_exclusive",
            "usable_start",
            "usable_end_exclusive",
            "first_bridge_date",
            "last_bridge_date",
        ],
        "bridge_manifest",
    )

    parse_dates(
        benchmark,
        ["date"],
        "benchmark",
    )

    section(
        "1. POPULATION AND STRUCTURE"
    )

    test(
        len(prices) == 783_086,
        (
            "Standardized source contains "
            "783,086 rows."
        ),
    )

    test(
        len(price_manifest) == 596,
        (
            "Standardized manifest contains "
            "596 requests."
        ),
    )

    test(
        len(membership) == 593,
        (
            "Membership table contains "
            "593 intervals."
        ),
    )

    test(
        len(ticker_history) == 594,
        (
            "Ticker history contains "
            "594 segments."
        ),
    )

    test(
        len(bridge) == 631_942,
        (
            "Bridge contains 631,942 "
            "constituent observations."
        ),
        f"Actual: {len(bridge):,}",
    )

    test(
        len(bridge_manifest) == 594,
        (
            "Bridge manifest contains "
            "594 segment rows."
        ),
    )

    test(
        len(benchmark) == 2_510,
        (
            "Benchmark output contains "
            "2,510 observations."
        ),
        f"Actual: {len(benchmark):,}",
    )

    test(
        bridge[
            "security_key"
        ].nunique() == 593,
        (
            "Bridge contains 593 "
            "security identities."
        ),
    )

    test(
        bridge[
            "project_ticker"
        ].nunique() == 594,
        (
            "Bridge contains 594 "
            "historical tickers."
        ),
    )

    benchmark_request_count = (
        benchmark[
            [
                "security_key",
                "project_ticker",
            ]
        ]
        .drop_duplicates()
        .shape[0]
    )

    test(
        benchmark_request_count == 2,
        (
            "Benchmark output contains "
            "two request keys."
        ),
    )

    output_frames = [
        ("Bridge", bridge),
        (
            "Bridge manifest",
            bridge_manifest,
        ),
        ("Benchmark", benchmark),
    ]

    for label, frame in output_frames:
        test(
            not frame.duplicated().any(),
            (
                f"{label} has no exact "
                "duplicate rows."
            ),
        )

    test(
        not bridge.duplicated(
            [
                "security_key",
                "project_ticker",
                "date",
            ]
        ).any(),
        (
            "Bridge observation keys "
            "are unique."
        ),
    )

    test(
        not bridge_manifest.duplicated(
            [
                "security_key",
                "project_ticker",
            ]
        ).any(),
        (
            "Bridge-manifest segment keys "
            "are unique."
        ),
    )

    test(
        not benchmark.duplicated(
            [
                "security_key",
                "project_ticker",
                "date",
            ]
        ).any(),
        (
            "Benchmark observation keys "
            "are unique."
        ),
    )

    test(
        not bridge[
            NUMERIC_COLUMNS
            + CONTROL_COLUMNS
        ].isna().any().any(),
        (
            "Bridge required numeric and "
            "control fields contain no nulls."
        ),
    )

    section(
        "2. RECONSTRUCT CONTROL TABLE"
    )

    membership_control = membership[
        [
            "security_key",
            "valid_from",
            "valid_to_exclusive",
        ]
    ].rename(
        columns={
            "valid_from":
                "membership_valid_from",
            "valid_to_exclusive":
                "membership_valid_to_exclusive",
        }
    )

    ticker_control = ticker_history[
        [
            "security_key",
            "ticker",
            "ticker_valid_from",
            "ticker_valid_to_exclusive",
        ]
    ].rename(
        columns={
            "ticker": "project_ticker",
        }
    )

    price_control = price_manifest[
        [
            "security_key",
            "project_ticker",
            "effective_expected_start",
            "effective_expected_end_exclusive",
        ]
    ].rename(
        columns={
            "effective_expected_start":
                "effective_price_start",
            "effective_expected_end_exclusive":
                "effective_price_end_exclusive",
        }
    )

    expected_controls = ticker_control.merge(
        membership_control,
        on="security_key",
        how="left",
        validate="many_to_one",
    )

    expected_controls = (
        expected_controls.merge(
            price_control,
            on=[
                "security_key",
                "project_ticker",
            ],
            how="left",
            validate="one_to_one",
        )
    )

    expected_controls[
        "usable_start"
    ] = (
        expected_controls[
            [
                "membership_valid_from",
                "ticker_valid_from",
                "effective_price_start",
            ]
        ].max(axis=1)
    )

    expected_controls[
        "usable_end_exclusive"
    ] = (
        expected_controls[
            [
                "membership_valid_to_exclusive",
                "ticker_valid_to_exclusive",
                "effective_price_end_exclusive",
            ]
        ].min(axis=1)
    )

    control_keys = [
        "security_key",
        "project_ticker",
    ]

    expected_control_view = (
        expected_controls[
            control_keys
            + CONTROL_COLUMNS
        ]
        .sort_values(
            control_keys
        )
        .reset_index(drop=True)
    )

    manifest_control_view = (
        bridge_manifest[
            control_keys
            + CONTROL_COLUMNS
        ]
        .sort_values(
            control_keys
        )
        .reset_index(drop=True)
    )

    test(
        expected_control_view.equals(
            manifest_control_view
        ),
        (
            "Bridge-manifest controls exactly "
            "reproduce source-derived controls."
        ),
    )

    test(
        (
            expected_controls[
                "usable_start"
            ]
            < expected_controls[
                "usable_end_exclusive"
            ]
        ).all(),
        (
            "Every reconstructed usable "
            "interval has positive duration."
        ),
    )

    test(
        expected_controls[
            "usable_start"
        ].ge(START).all()
        and expected_controls[
            "usable_end_exclusive"
        ].le(
            END_EXCLUSIVE
        ).all(),
        (
            "Every reconstructed usable "
            "interval is inside 2021-2025."
        ),
    )

    early_end = expected_controls[
        expected_controls[
            "usable_end_exclusive"
        ].lt(
            expected_controls[
                "ticker_valid_to_exclusive"
            ]
        )
    ]

    test(
        len(early_end) == 10,
        (
            "Exactly ten usable intervals end "
            "at documented price boundaries."
        ),
        early_end[
            [
                "security_key",
                "project_ticker",
            ]
        ].to_string(index=False),
    )

    expected_early_end_keys = {
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

    test(
        set(
            early_end[
                "security_key"
            ]
        )
        == expected_early_end_keys,
        (
            "The ten shortened intervals are "
            "the validated termination cases."
        ),
    )

    section(
        "3. INDEPENDENT SOURCE RECONCILIATION"
    )

    constituent_pairs = pair_set(
        expected_controls
    )

    source_pair_index = (
        pd.MultiIndex.from_frame(
            prices[
                [
                    "security_key",
                    "project_ticker",
                ]
            ]
        )
    )

    constituent_mask = (
        source_pair_index.isin(
            pd.MultiIndex.from_tuples(
                sorted(
                    constituent_pairs
                )
            )
        )
    )

    source_candidates = (
        prices.loc[
            constituent_mask
        ]
        .merge(
            expected_controls,
            on=[
                "security_key",
                "project_ticker",
            ],
            how="left",
            validate="many_to_one",
        )
    )

    expected_mask = (
        source_candidates[
            "date"
        ].ge(
            source_candidates[
                "usable_start"
            ]
        )
        & source_candidates[
            "date"
        ].lt(
            source_candidates[
                "usable_end_exclusive"
            ]
        )
    )

    expected_bridge = source_candidates.loc[
        expected_mask,
        BRIDGE_COLUMNS,
    ].copy()

    expected_keys = key_set(
        expected_bridge
    )

    actual_keys = key_set(
        bridge
    )

    missing_keys = (
        expected_keys
        - actual_keys
    )

    extra_keys = (
        actual_keys
        - expected_keys
    )

    test(
        len(expected_bridge) == 631_942,
        (
            "Independent reconstruction "
            "produces 631,942 rows."
        ),
        f"Actual: {len(expected_bridge):,}",
    )

    test(
        not missing_keys,
        (
            "No independently expected bridge "
            "observations are missing."
        ),
        str(
            sorted(
                missing_keys
            )[:20]
        ),
    )

    test(
        not extra_keys,
        (
            "No ineligible observations exist "
            "in the bridge."
        ),
        str(
            sorted(
                extra_keys
            )[:20]
        ),
    )

    sort_key = [
        "security_key",
        "project_ticker",
        "date",
    ]

    expected_price = (
        expected_bridge[
            PRICE_COLUMNS
        ]
        .sort_values(
            sort_key,
            kind="stable",
        )
        .reset_index(drop=True)
    )

    actual_price = (
        bridge[
            PRICE_COLUMNS
        ]
        .sort_values(
            sort_key,
            kind="stable",
        )
        .reset_index(drop=True)
    )

    identity_columns = [
        "security_key",
        "project_ticker",
        "provider_symbol",
        "date",
        "source",
    ]

    identity_match = (
        actual_price[
            identity_columns
        ].equals(
            expected_price[
                identity_columns
            ]
        )
    )

    numeric_match = np.isclose(
        actual_price[
            NUMERIC_COLUMNS
        ].to_numpy(
            dtype="float64"
        ),
        expected_price[
            NUMERIC_COLUMNS
        ].to_numpy(
            dtype="float64"
        ),
        rtol=0,
        atol=1e-12,
        equal_nan=False,
    ).all()

    test(
        identity_match,
        (
            "Every bridge identity and source "
            "value matches standardized history."
        ),
    )

    test(
        numeric_match,
        (
            "Every bridge numeric value "
            "matches standardized history."
        ),
    )

    source_counts = (
        source_candidates
        .groupby(
            [
                "security_key",
                "project_ticker",
            ],
            as_index=False,
        )
        .agg(
            standardized_rows=(
                "date",
                "size",
            ),
        )
    )

    expected_summary = (
        expected_bridge
        .groupby(
            [
                "security_key",
                "project_ticker",
            ],
            as_index=False,
        )
        .agg(
            bridge_rows=(
                "date",
                "size",
            ),
            first_bridge_date=(
                "date",
                "min",
            ),
            last_bridge_date=(
                "date",
                "max",
            ),
        )
    )

    before_counts = (
        source_candidates.loc[
            source_candidates[
                "date"
            ].lt(
                source_candidates[
                    "usable_start"
                ]
            )
        ]
        .groupby(
            [
                "security_key",
                "project_ticker",
            ]
        )
        .size()
        .rename(
            "rows_before_usable_window"
        )
        .reset_index()
    )

    after_counts = (
        source_candidates.loc[
            source_candidates[
                "date"
            ].ge(
                source_candidates[
                    "usable_end_exclusive"
                ]
            )
        ]
        .groupby(
            [
                "security_key",
                "project_ticker",
            ]
        )
        .size()
        .rename(
            "rows_after_usable_window"
        )
        .reset_index()
    )

    independent_summary = (
        expected_controls.merge(
            source_counts,
            on=control_keys,
            how="left",
            validate="one_to_one",
        )
    )

    independent_summary = (
        independent_summary.merge(
            expected_summary,
            on=control_keys,
            how="left",
            validate="one_to_one",
        )
    )

    independent_summary = (
        independent_summary.merge(
            before_counts,
            on=control_keys,
            how="left",
            validate="one_to_one",
        )
    )

    independent_summary = (
        independent_summary.merge(
            after_counts,
            on=control_keys,
            how="left",
            validate="one_to_one",
        )
    )

    count_columns = [
        "standardized_rows",
        "bridge_rows",
        "rows_before_usable_window",
        "rows_after_usable_window",
    ]

    for column in count_columns:
        independent_summary[column] = (
            independent_summary[column]
            .fillna(0)
            .astype("int64")
        )

    comparison_columns = (
        control_keys
        + count_columns
        + [
            "first_bridge_date",
            "last_bridge_date",
        ]
    )

    independent_view = (
        independent_summary[
            comparison_columns
        ]
        .sort_values(
            control_keys
        )
        .reset_index(drop=True)
    )

    manifest_view = (
        bridge_manifest[
            comparison_columns
        ]
        .sort_values(
            control_keys
        )
        .reset_index(drop=True)
    )

    test(
        independent_view.equals(
            manifest_view
        ),
        (
            "Every bridge-manifest count and "
            "boundary independently reconciles."
        ),
    )

    section(
        "4. INTERVAL ELIGIBILITY"
    )

    test(
        bridge[
            "date"
        ].ge(
            bridge[
                "membership_valid_from"
            ]
        ).all()
        and bridge[
            "date"
        ].lt(
            bridge[
                "membership_valid_to_exclusive"
            ]
        ).all(),
        (
            "Every bridge row lies inside "
            "its membership interval."
        ),
    )

    test(
        bridge[
            "date"
        ].ge(
            bridge[
                "ticker_valid_from"
            ]
        ).all()
        and bridge[
            "date"
        ].lt(
            bridge[
                "ticker_valid_to_exclusive"
            ]
        ).all(),
        (
            "Every bridge row lies inside "
            "its ticker-validity interval."
        ),
    )

    test(
        bridge[
            "date"
        ].ge(
            bridge[
                "usable_start"
            ]
        ).all()
        and bridge[
            "date"
        ].lt(
            bridge[
                "usable_end_exclusive"
            ]
        ).all(),
        (
            "Every bridge row lies inside "
            "its usable price interval."
        ),
    )

    control_variation = (
        bridge
        .groupby(
            [
                "security_key",
                "project_ticker",
            ]
        )[
            CONTROL_COLUMNS
        ]
        .nunique()
    )

    test(
        control_variation.le(
            1
        ).all().all(),
        (
            "Control boundaries remain "
            "constant within each "
            "ticker segment."
        ),
    )

    test(
        bridge.groupby(
            [
                "security_key",
                "date",
            ]
        ).size().le(1).all(),
        (
            "No security identity appears "
            "more than once on a date."
        ),
    )

    section(
        "5. SPY SESSION COVERAGE"
    )

    spy = benchmark[
        benchmark[
            "project_ticker"
        ].eq("SPY")
    ].copy()

    test(
        spy[
            "security_key"
        ].nunique() == 1,
        (
            "Benchmark output contains "
            "exactly one SPY request."
        ),
    )

    spy_dates = pd.DatetimeIndex(
        sorted(
            spy[
                "date"
            ].unique()
        )
    )

    test(
        len(spy_dates) == 1_255,
        (
            "The 2021-2025 SPY calendar "
            "contains 1,255 sessions."
        ),
        f"Actual: {len(spy_dates):,}",
    )

    actual_dates_by_pair = {
        pair: set(
            group[
                "date"
            ]
        )
        for pair, group in bridge.groupby(
            [
                "security_key",
                "project_ticker",
            ]
        )
    }

    session_errors = []

    daily_expected = pd.Series(
        0,
        index=spy_dates,
        dtype="int64",
    )

    expected_session_rows = 0

    for row in bridge_manifest.itertuples(
        index=False
    ):
        eligible_spy_dates = (
            (
                spy_dates
                >= row.usable_start
            )
            & (
                spy_dates
                < row.usable_end_exclusive
            )
        )

        expected_dates_for_pair = set(
            spy_dates[
                eligible_spy_dates
            ]
        )

        actual_dates_for_pair = (
            actual_dates_by_pair.get(
                (
                    row.security_key,
                    row.project_ticker,
                ),
                set(),
            )
        )

        missing = (
            expected_dates_for_pair
            - actual_dates_for_pair
        )

        extra = (
            actual_dates_for_pair
            - expected_dates_for_pair
        )

        if missing or extra:
            session_errors.append(
                f"{row.security_key}/"
                f"{row.project_ticker}: "
                f"missing={len(missing)}, "
                f"extra={len(extra)}"
            )

        daily_expected.loc[
            eligible_spy_dates
        ] += 1

        expected_session_rows += len(
            expected_dates_for_pair
        )

    test(
        not session_errors,
        (
            "Every ticker segment has exact "
            "SPY-session coverage."
        ),
        "\n".join(
            session_errors[:50]
        ),
    )

    test(
        expected_session_rows
        == len(bridge),
        (
            "Total expected SPY-session rows "
            "equal the bridge row count."
        ),
        (
            f"Expected: "
            f"{expected_session_rows:,}; "
            f"bridge: {len(bridge):,}"
        ),
    )

    daily_actual = (
        bridge
        .groupby(
            "date"
        )
        .size()
        .reindex(
            spy_dates,
            fill_value=0,
        )
        .astype("int64")
    )

    daily_mismatches = (
        daily_actual.ne(
            daily_expected
        )
    )

    mismatch_table = pd.DataFrame(
        {
            "expected":
                daily_expected[
                    daily_mismatches
                ],
            "actual":
                daily_actual[
                    daily_mismatches
                ],
        }
    )

    test(
        not daily_mismatches.any(),
        (
            "Daily bridge populations match "
            "reconstructed usable membership."
        ),
        mismatch_table.head(
            30
        ).to_string(),
    )

    test(
        set(
            bridge[
                "date"
            ]
        )
        == set(spy_dates),
        (
            "Bridge date coverage exactly "
            "matches the SPY calendar."
        ),
    )

    section(
        "6. PRICE AND BENCHMARK INTEGRITY"
    )

    test(
        not bridge[
            NUMERIC_COLUMNS
        ].isna().any().any(),
        (
            "Bridge has no required "
            "numeric nulls."
        ),
    )

    test(
        (
            bridge[
                [
                    "open",
                    "high",
                    "low",
                    "close",
                    "adjusted_close",
                ]
            ]
            > 0
        ).all().all(),
        (
            "Bridge contains only "
            "positive prices."
        ),
    )

    test(
        bridge[
            "volume"
        ].ge(0).all(),
        (
            "Bridge has no "
            "negative volume."
        ),
    )

    test(
        bridge[
            "split_factor"
        ].gt(0).all(),
        (
            "Bridge has only "
            "positive split factors."
        ),
    )

    test(
        bridge[
            "high"
        ].ge(
            bridge[
                [
                    "open",
                    "low",
                    "close",
                ]
            ].max(axis=1)
        ).all(),
        (
            "Bridge has no invalid "
            "HIGH relationships."
        ),
    )

    test(
        bridge[
            "low"
        ].le(
            bridge[
                [
                    "open",
                    "high",
                    "close",
                ]
            ].min(axis=1)
        ).all(),
        (
            "Bridge has no invalid "
            "LOW relationships."
        ),
    )

    benchmark_pairs = pair_set(
        benchmark
    )

    test(
        len(benchmark_pairs) == 2,
        (
            "Benchmark output contains "
            "exactly two distinct requests."
        ),
        str(
            sorted(
                benchmark_pairs
            )
        ),
    )

    test(
        not (
            benchmark_pairs
            & pair_set(bridge)
        ),
        (
            "Benchmark and constituent request "
            "populations are disjoint."
        ),
    )

    benchmark_date_errors = []

    for pair, group in benchmark.groupby(
        [
            "security_key",
            "project_ticker",
        ]
    ):
        if set(
            group[
                "date"
            ]
        ) != set(spy_dates):
            benchmark_date_errors.append(
                str(pair)
            )

    test(
        not benchmark_date_errors,
        (
            "Both benchmark requests exactly "
            "cover the SPY calendar."
        ),
        str(
            benchmark_date_errors
        ),
    )

    section(
        "7. FINAL QUALITY GATE"
    )

    if failures:
        print(
            "MEMBERSHIP_PRICE_BRIDGE_"
            "INTEGRITY_AUDIT_FAILED"
        )

        print(
            f"Passed checks: {passed}"
        )

        print(
            "Failed checks: "
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
        "MEMBERSHIP_PRICE_BRIDGE_"
        "INTEGRITY_AUDIT_PASSED"
    )

    print(
        f"Passed checks: {passed}"
    )

    print(
        "Constituent bridge rows: "
        f"{len(bridge):,}"
    )

    print(
        "Security identities: "
        f"{bridge['security_key'].nunique():,}"
    )

    print(
        "Historical ticker segments: "
        f"{bridge['project_ticker'].nunique():,}"
    )

    print(
        "SPY trading sessions: "
        f"{len(spy_dates):,}"
    )

    print(
        "Benchmark rows: "
        f"{len(benchmark):,}"
    )

    print(
        "Documented early price boundaries: "
        f"{len(early_end):,}"
    )

    print(
        "Minimum daily constituent "
        f"observations: {int(daily_actual.min()):,}"
    )

    print(
        "Maximum daily constituent "
        f"observations: {int(daily_actual.max()):,}"
    )

    print(
        "Missing expected constituent "
        "sessions: 0"
    )

    print(
        "Extra constituent sessions: 0"
    )

    print(
        "Membership/ticker/date "
        "duplicates: 0"
    )

    print(
        "No observations outside membership, "
        "ticker, or usable-price intervals remain."
    )

    print(
        "POINT-IN-TIME MEMBERSHIP-PRICE "
        "INTEGRATION QUALITY GATE COMPLETE."
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
                result = audit()

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
            "MEMBERSHIP-PRICE BRIDGE "
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
            "MEMBERSHIP-PRICE BRIDGE "
            "INTEGRITY AUDIT FAILED"
        )

        print(
            "Saved audit report: "
            f"{REPORT_FILE}"
        )

        sys.exit(1)

    print(
        "MEMBERSHIP-PRICE BRIDGE "
        "INTEGRITY AUDIT PASSED"
    )

    print(
        "Saved audit report: "
        f"{REPORT_FILE}"
    )


if __name__ == "__main__":
    main()