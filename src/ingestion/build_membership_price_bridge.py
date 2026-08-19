from pathlib import Path
import sys

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


def section(title):
    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


def require(
    condition,
    message,
    detail=None,
):
    if bool(condition):
        print(f"PASS: {message}")
        return

    print(f"\nERROR: {message}")

    if detail:
        print(detail)

    raise RuntimeError(message)


def load_exact(
    path,
    label,
    columns,
):
    require(
        path.exists(),
        f"Required {label} exists: {path}",
    )

    frame = pd.read_csv(path)

    require(
        list(frame.columns) == columns,
        f"{label} has the expected schema.",
        (
            f"Expected: {columns}\n"
            f"Actual: {list(frame.columns)}"
        ),
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

        require(
            parsed.notna().all(),
            (
                f"{label}.{column} "
                "contains valid dates."
            ),
        )

        frame[column] = parsed


def date_strings(
    frame,
    columns,
):
    output = frame.copy()

    for column in columns:
        output[column] = (
            output[column]
            .dt.strftime("%Y-%m-%d")
        )

    return output


def pairs(
    frame,
    ticker_column,
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


def build():
    section(
        "S&P 500 POINT-IN-TIME "
        "MEMBERSHIP-PRICE BRIDGE"
    )

    prices = load_exact(
        PRICE_FILE,
        "standardized price history",
        PRICE_COLUMNS,
    )

    price_manifest = load_exact(
        PRICE_MANIFEST_FILE,
        "standardized price manifest",
        MANIFEST_COLUMNS,
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

    normalize(
        prices,
        [
            "security_key",
            "project_ticker",
            "provider_symbol",
        ],
    )

    normalize(
        price_manifest,
        [
            "security_key",
            "project_ticker",
            "provider_symbol",
        ],
    )

    normalize(
        membership,
        [
            "security_key",
            "entry_ticker",
        ],
    )

    normalize(
        ticker_history,
        [
            "security_key",
            "ticker",
        ],
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

    section(
        "1. INPUT CONTROL GATE"
    )

    require(
        len(prices) == 783_086,
        (
            "Standardized price history "
            "contains 783,086 rows."
        ),
        f"Actual: {len(prices):,}",
    )

    require(
        len(price_manifest) == 596,
        (
            "Standardized manifest contains "
            "596 requests."
        ),
    )

    require(
        len(membership) == 593,
        (
            "Membership table contains "
            "593 rows."
        ),
    )

    require(
        membership[
            "security_key"
        ].nunique() == 593,
        (
            "Membership table contains "
            "593 security identities."
        ),
    )

    require(
        len(ticker_history) == 594,
        (
            "Ticker history contains "
            "594 segments."
        ),
    )

    require(
        ticker_history[
            "ticker"
        ].nunique() == 594,
        (
            "Ticker history contains "
            "594 historical tickers."
        ),
    )

    require(
        not prices.duplicated(
            [
                "security_key",
                "project_ticker",
                "date",
            ]
        ).any(),
        (
            "Standardized price keys "
            "are unique."
        ),
    )

    require(
        not price_manifest.duplicated(
            [
                "security_key",
                "project_ticker",
            ]
        ).any(),
        (
            "Standardized request keys "
            "are unique."
        ),
    )

    require(
        not membership[
            "security_key"
        ].duplicated().any(),
        (
            "Membership security keys "
            "are unique."
        ),
    )

    require(
        not ticker_history.duplicated(
            [
                "security_key",
                "ticker",
            ]
        ).any(),
        (
            "Ticker-history security/ticker "
            "keys are unique."
        ),
    )

    section(
        "2. SEGMENT CONTROL TABLE"
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

    manifest_control = price_manifest[
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

    controls = ticker_control.merge(
        membership_control,
        on="security_key",
        how="left",
        validate="many_to_one",
    )

    controls = controls.merge(
        manifest_control,
        on=[
            "security_key",
            "project_ticker",
        ],
        how="left",
        validate="one_to_one",
    )

    required_dates = [
        "membership_valid_from",
        "membership_valid_to_exclusive",
        "ticker_valid_from",
        "ticker_valid_to_exclusive",
        "effective_price_start",
        "effective_price_end_exclusive",
    ]

    require(
        not controls[
            required_dates
        ].isna().any().any(),
        (
            "Every ticker segment has "
            "complete membership and "
            "price controls."
        ),
    )

    controls["usable_start"] = (
        controls[
            [
                "membership_valid_from",
                "ticker_valid_from",
                "effective_price_start",
            ]
        ].max(axis=1)
    )

    controls[
        "usable_end_exclusive"
    ] = (
        controls[
            [
                "membership_valid_to_exclusive",
                "ticker_valid_to_exclusive",
                "effective_price_end_exclusive",
            ]
        ].min(axis=1)
    )

    require(
        (
            controls[
                "usable_start"
            ]
            < controls[
                "usable_end_exclusive"
            ]
        ).all(),
        (
            "Every ticker segment has a "
            "positive usable interval."
        ),
    )

    require(
        controls[
            "usable_start"
        ].ge(START).all(),
        (
            "Every usable segment starts "
            "inside the analysis period."
        ),
    )

    require(
        controls[
            "usable_end_exclusive"
        ].le(
            END_EXCLUSIVE
        ).all(),
        (
            "Every usable segment ends "
            "inside the analysis scope."
        ),
    )

    section(
        "3. REQUEST CLASSIFICATION"
    )

    segment_pairs = pairs(
        controls,
        "project_ticker",
    )

    manifest_pairs = pairs(
        price_manifest,
        "project_ticker",
    )

    missing_pairs = sorted(
        segment_pairs
        - manifest_pairs
    )

    benchmark_pairs = sorted(
        manifest_pairs
        - segment_pairs
    )

    require(
        not missing_pairs,
        (
            "Every constituent segment has "
            "a standardized request."
        ),
        str(
            missing_pairs[:50]
        ),
    )

    require(
        len(benchmark_pairs) == 2,
        (
            "Exactly two standardized "
            "requests are benchmarks."
        ),
        str(benchmark_pairs),
    )

    price_pair_index = (
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
        price_pair_index.isin(
            pd.MultiIndex.from_tuples(
                sorted(segment_pairs)
            )
        )
    )

    benchmark_mask = (
        price_pair_index.isin(
            pd.MultiIndex.from_tuples(
                benchmark_pairs
            )
        )
    )

    require(
        (
            constituent_mask
            | benchmark_mask
        ).all(),
        (
            "Every standardized row "
            "is classified."
        ),
    )

    require(
        not (
            constituent_mask
            & benchmark_mask
        ).any(),
        (
            "Constituent and benchmark "
            "classifications do not overlap."
        ),
    )

    constituent_prices = prices.loc[
        constituent_mask
    ].copy()

    benchmark = prices.loc[
        benchmark_mask
        & prices[
            "date"
        ].ge(START)
        & prices[
            "date"
        ].lt(
            END_EXCLUSIVE
        ),
        PRICE_COLUMNS,
    ].copy()

    section(
        "4. POINT-IN-TIME FILTER"
    )

    candidates = constituent_prices.merge(
        controls,
        on=[
            "security_key",
            "project_ticker",
        ],
        how="left",
        validate="many_to_one",
    )

    require(
        not candidates[
            CONTROL_COLUMNS
        ].isna().any().any(),
        (
            "Every constituent price row "
            "maps to one segment control."
        ),
    )

    eligible = (
        candidates[
            "date"
        ].ge(
            candidates[
                "membership_valid_from"
            ]
        )
        & candidates[
            "date"
        ].lt(
            candidates[
                "membership_valid_to_exclusive"
            ]
        )
        & candidates[
            "date"
        ].ge(
            candidates[
                "ticker_valid_from"
            ]
        )
        & candidates[
            "date"
        ].lt(
            candidates[
                "ticker_valid_to_exclusive"
            ]
        )
        & candidates[
            "date"
        ].ge(
            candidates[
                "usable_start"
            ]
        )
        & candidates[
            "date"
        ].lt(
            candidates[
                "usable_end_exclusive"
            ]
        )
    )

    bridge = candidates.loc[
        eligible,
        BRIDGE_COLUMNS,
    ].copy()

    bridge = bridge.sort_values(
        [
            "date",
            "security_key",
            "project_ticker",
        ],
        kind="stable",
    ).reset_index(drop=True)

    benchmark = benchmark.sort_values(
        [
            "date",
            "security_key",
            "project_ticker",
        ],
        kind="stable",
    ).reset_index(drop=True)

    removed_rows = (
        len(candidates)
        - len(bridge)
    )

    print(
        "Eligible constituent rows: "
        f"{len(bridge):,}"
    )

    print(
        "Removed lookback/out-of-window "
        f"constituent rows: {removed_rows:,}"
    )

    section(
        "5. RECONCILIATION MANIFEST"
    )

    source_summary = (
        constituent_prices
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

    bridge_summary = (
        bridge
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

    before_summary = (
        candidates.loc[
            candidates[
                "date"
            ].lt(
                candidates[
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

    after_summary = (
        candidates.loc[
            candidates[
                "date"
            ].ge(
                candidates[
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

    bridge_manifest = controls.merge(
        source_summary,
        on=[
            "security_key",
            "project_ticker",
        ],
        how="left",
        validate="one_to_one",
    )

    bridge_manifest = bridge_manifest.merge(
        bridge_summary,
        on=[
            "security_key",
            "project_ticker",
        ],
        how="left",
        validate="one_to_one",
    )

    bridge_manifest = bridge_manifest.merge(
        before_summary,
        on=[
            "security_key",
            "project_ticker",
        ],
        how="left",
        validate="one_to_one",
    )

    bridge_manifest = bridge_manifest.merge(
        after_summary,
        on=[
            "security_key",
            "project_ticker",
        ],
        how="left",
        validate="one_to_one",
    )

    count_columns = [
        "standardized_rows",
        "bridge_rows",
        "rows_before_usable_window",
        "rows_after_usable_window",
    ]

    for column in count_columns:
        bridge_manifest[column] = (
            bridge_manifest[column]
            .fillna(0)
            .astype("int64")
        )

    bridge_manifest = (
        bridge_manifest[
            BRIDGE_MANIFEST_COLUMNS
        ]
        .sort_values(
            [
                "security_key",
                "ticker_valid_from",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    require(
        len(bridge_manifest) == 594,
        (
            "Bridge manifest contains "
            "all 594 ticker segments."
        ),
    )

    require(
        bridge_manifest[
            "bridge_rows"
        ].gt(0).all(),
        (
            "Every ticker segment "
            "contributes bridge rows."
        ),
        bridge_manifest.loc[
            bridge_manifest[
                "bridge_rows"
            ].eq(0)
        ].to_string(index=False),
    )

    require(
        bridge_manifest[
            "bridge_rows"
        ].sum() == len(bridge),
        (
            "Manifest bridge-row counts "
            "reconcile to the output."
        ),
    )

    reconciled = (
        bridge_manifest[
            "bridge_rows"
        ]
        + bridge_manifest[
            "rows_before_usable_window"
        ]
        + bridge_manifest[
            "rows_after_usable_window"
        ]
    )

    require(
        reconciled.eq(
            bridge_manifest[
                "standardized_rows"
            ]
        ).all(),
        (
            "Every constituent source row "
            "is classified exactly once."
        ),
        bridge_manifest.loc[
            ~reconciled.eq(
                bridge_manifest[
                    "standardized_rows"
                ]
            )
        ].to_string(index=False),
    )

    section(
        "6. OUTPUT VALIDATION"
    )

    require(
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

    require(
        pairs(
            bridge,
            "project_ticker",
        ) == segment_pairs,
        (
            "Bridge contains all and only "
            "594 constituent ticker segments."
        ),
    )

    require(
        bridge[
            "date"
        ].ge(START).all()
        and bridge[
            "date"
        ].lt(
            END_EXCLUSIVE
        ).all(),
        (
            "Every bridge observation falls "
            "inside 2021-2025."
        ),
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend",
        "split_factor",
    ]

    require(
        not bridge[
            numeric_columns
        ].isna().any().any(),
        (
            "Bridge has no required "
            "numeric nulls."
        ),
    )

    require(
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
            "Bridge has only "
            "positive prices."
        ),
    )

    require(
        bridge[
            "volume"
        ].ge(0).all(),
        (
            "Bridge has no "
            "negative volume."
        ),
    )

    require(
        bridge[
            "split_factor"
        ].gt(0).all(),
        (
            "Bridge has only "
            "positive split factors."
        ),
    )

    require(
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

    require(
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

    require(
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

    require(
        pairs(
            benchmark,
            "project_ticker",
        ) == set(
            benchmark_pairs
        ),
        (
            "Benchmark output contains "
            "exactly two requests."
        ),
    )

    section(
        "7. SAVE OUTPUTS"
    )

    INTERIM.mkdir(
        parents=True,
        exist_ok=True,
    )

    bridge_output = date_strings(
        bridge,
        [
            "date",
        ]
        + CONTROL_COLUMNS,
    )

    benchmark_output = date_strings(
        benchmark,
        ["date"],
    )

    manifest_output = date_strings(
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
    )

    bridge_output.to_csv(
        BRIDGE_FILE,
        index=False,
        compression="gzip",
    )

    benchmark_output.to_csv(
        BENCHMARK_FILE,
        index=False,
        compression="gzip",
    )

    manifest_output.to_csv(
        BRIDGE_MANIFEST_FILE,
        index=False,
    )

    print(
        "Membership-price bridge saved:\n"
        f"{BRIDGE_FILE}"
    )

    print(
        "\nBridge manifest saved:\n"
        f"{BRIDGE_MANIFEST_FILE}"
    )

    print(
        "\nBenchmark history saved:\n"
        f"{BENCHMARK_FILE}"
    )

    section(
        "BUILD RESULT"
    )

    print(
        "MEMBERSHIP_PRICE_BRIDGE_BUILD_PASSED"
    )

    print(
        "Constituent bridge rows: "
        f"{len(bridge):,}"
    )

    print(
        "Constituent security identities: "
        f"{bridge['security_key'].nunique():,}"
    )

    print(
        "Constituent ticker segments: "
        f"{len(segment_pairs):,}"
    )

    print(
        "Benchmark rows: "
        f"{len(benchmark):,}"
    )

    print(
        "Benchmark requests: "
        f"{len(benchmark_pairs):,}"
    )

    print(
        "Removed lookback/out-of-window "
        f"constituent rows: {removed_rows:,}"
    )

    print(
        "Point-in-time membership, ticker "
        "validity, and usable price "
        "boundaries applied."
    )


def main():
    try:
        build()

    except Exception as error:
        print(
            "\nMEMBERSHIP PRICE "
            "BRIDGE BUILD FAILED"
        )

        print(error)
        sys.exit(1)


if __name__ == "__main__":
    main()