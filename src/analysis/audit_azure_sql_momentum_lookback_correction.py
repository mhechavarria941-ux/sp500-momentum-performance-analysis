from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

STANDARDIZED_PATH = (
    ROOT / "data" / "interim" / "standardized_price_history.csv.gz"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_momentum_lookback_correction_integrity_audit.txt"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
AUDIT_VERSION = "2026-08-24-v3-anchor-semantics"

EXPECTED_STANDARDIZED_ROWS = 783_086
EXPECTED_SUPPORT_MONTHS = 72
EXPECTED_SECURITY_SUPPORT_ROWS = 37_245
EXPECTED_BENCHMARK_SUPPORT_ROWS = 144
EXPECTED_SNAPSHOT_ROWS = 30_211
EXPECTED_FEATURE_COMPLETE = {
    1: 30_209,
    3: 30_192,
    6: 30_169,
    12: 30_121,
}
EXPECTED_MOMENTUM_ROWS = 30_121
EXPECTED_RANKING_MONTHS = 60
EXPECTED_DECILE_ROWS = 600
EXPECTED_COMPLETE_DECILE_ROWS = 590
EXPECTED_WML_ROWS = 60
EXPECTED_COMPLETE_WML_ROWS = 59
EXPECTED_BENCHMARK_FORWARD_ROWS = 120
EXPECTED_COMPLETE_BENCHMARK_FORWARD_ROWS = 118
EXPECTED_SECURITY_FORWARD_ROWS = 30_121
EXPECTED_COMPLETE_SECURITY_FORWARD_ROWS = 29_620
EXPECTED_RIGHT_CENSORED_ROWS = 501
EXPECTED_PANEL_ROWS = 767
EXPECTED_PERFORMANCE_MONTHS = 59
EXPECTED_SERIES = {
    "D01", "D02", "D03", "D04", "D05",
    "D06", "D07", "D08", "D09", "D10",
    "WML", "SPY", "SP500",
}
EXPECTED_TURNOVER_ROWS = 590
EXPECTED_TURNOVER_MONTHS = 59

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}

FLOAT_ATOL = 1e-11
FLOAT_RTOL = 1e-10


def rule() -> str:
    return "=" * 112


def section(title: str) -> list[str]:
    return ["", rule(), title, rule()]


def environment() -> tuple[str, str, str, str]:
    load_dotenv(ROOT / ".env")

    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )
    values = tuple(os.getenv(name) for name in names)

    missing = [
        name
        for name, value in zip(names, values)
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
        )

    return values  # type: ignore[return-value]


def odbc_escape(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def connect_with_retry(
    server: str,
    database: str,
    username: str,
    password: str,
):
    if ODBC_DRIVER not in pyodbc.drivers():
        raise RuntimeError(
            f"{ODBC_DRIVER} is not installed. "
            f"Available drivers: {pyodbc.drivers()}"
        )

    connection_string = (
        f"DRIVER={{{ODBC_DRIVER}}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={odbc_escape(database)};"
        f"UID={odbc_escape(username)};"
        f"PWD={odbc_escape(password)};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )

    maximum_attempts = 5
    wait_seconds = 15
    retryable_terms = (
        "08001",
        "08s01",
        "hyt00",
        "40613",
        "timeout",
        "not currently available",
        "unable to establish connection",
        "temporarily unavailable",
        "communication link failure",
        "10053",
    )

    for attempt in range(1, maximum_attempts + 1):
        try:
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            print(
                f"ODBC connection established on attempt "
                f"{attempt} / {maximum_attempts}."
            )
            return connection
        except pyodbc.Error as error:
            retryable = any(
                term in str(error).lower()
                for term in retryable_terms
            )
            if not retryable or attempt == maximum_attempts:
                raise

            print(
                f"ODBC connection attempt {attempt} / "
                f"{maximum_attempts} failed. Retrying in "
                f"{wait_seconds} seconds."
            )
            time.sleep(wait_seconds)

    raise RuntimeError(
        "ODBC connection retry loop ended unexpectedly."
    )


def fetch_df(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"RUNNING AUDIT VERSION: {AUDIT_VERSION}")

    lines: list[str] = [
        rule(),
        "AZURE SQL MOMENTUM LOOKBACK-SCOPE CORRECTION — INDEPENDENT INTEGRITY AUDIT",
        rule(),
        "Mode: READ-ONLY",
        "Database modifications: 0",
        "Purpose: independently reconstruct corrected feature support and verify downstream propagation.",
        "Primary local source: validated standardized_price_history.csv.gz",
        "Ranking-date source: validated analytics.security_month_end_snapshot",
        "2020 price history role: FEATURE SUPPORT ONLY",
        "2021-2025 role: POINT-IN-TIME RANKING / PERFORMANCE WINDOW",
    ]

    failures: list[str] = []
    passed = 0
    connection = None

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if condition:
            lines.append(f"PASS: {success}")
            passed += 1
        else:
            lines.append(f"FAIL: {failure}")
            failures.append(failure)

    try:
        if not STANDARDIZED_PATH.exists():
            raise FileNotFoundError(
                f"Required local source not found: {STANDARDIZED_PATH}"
            )

        print("Loading validated standardized price history...")
        prices = pd.read_csv(
            STANDARDIZED_PATH,
            usecols=[
                "security_key",
                "project_ticker",
                "date",
                "adjusted_close",
            ],
            low_memory=False,
        )

        prices["security_key"] = (
            prices["security_key"].astype(str).str.strip()
        )
        prices["project_ticker"] = (
            prices["project_ticker"].astype(str).str.strip()
        )
        prices["date"] = pd.to_datetime(
            prices["date"],
            errors="raise",
        )
        prices["adjusted_close"] = pd.to_numeric(
            prices["adjusted_close"],
            errors="raise",
        )

        lines += section("1. LOCAL SOURCE CONTROLS")

        check(
            len(prices) == EXPECTED_STANDARDIZED_ROWS,
            f"Standardized source contains exactly {len(prices):,} rows.",
            (
                f"Standardized source contains {len(prices):,} rows; "
                f"expected {EXPECTED_STANDARDIZED_ROWS:,}."
            ),
        )
        check(
            prices["adjusted_close"].notna().all()
            and (prices["adjusted_close"] > 0).all(),
            "All standardized adjusted-close values are positive and non-null.",
            "Standardized adjusted-close contains null or nonpositive values.",
        )

        spy = prices[
            prices["project_ticker"] == "SPY"
        ][["date"]].copy()
        spy["period"] = spy["date"].dt.to_period("M")

        month_ends = (
            spy[
                (spy["date"] >= pd.Timestamp("2020-01-01"))
                & (spy["date"] <= pd.Timestamp("2025-12-31"))
            ]
            .groupby("period", sort=True)["date"]
            .max()
        )

        expected_periods = pd.period_range(
            "2020-01",
            "2025-12",
            freq="M",
        )

        check(
            list(month_ends.index) == list(expected_periods),
            "SPY independently provides all 72 exact month-end support anchors from 2020-01 through 2025-12.",
            "SPY support calendar is not exactly 2020-01 through 2025-12.",
        )

        if failures:
            raise RuntimeError(
                "Local source validation failed."
            )

        support_dates = set(pd.Timestamp(x) for x in month_ends.values)

        local_monthly = prices[
            (prices["date"] >= pd.Timestamp("2020-01-01"))
            & (prices["date"] <= pd.Timestamp("2025-12-31"))
            & (prices["date"].isin(support_dates))
        ].copy()

        local_monthly["feature_month_number"] = (
            (local_monthly["date"].dt.year - 2021) * 12
            + local_monthly["date"].dt.month
        ).astype(int)

        local_security_support = local_monthly[
            ~local_monthly["project_ticker"].isin({"SPY", "^GSPC"})
        ][
            [
                "feature_month_number",
                "date",
                "security_key",
                "project_ticker",
                "adjusted_close",
            ]
        ].copy()

        local_benchmark_support = local_monthly[
            local_monthly["project_ticker"].isin({"SPY", "^GSPC"})
        ][
            [
                "feature_month_number",
                "date",
                "security_key",
                "project_ticker",
                "adjusted_close",
            ]
        ].copy()

        check(
            len(local_security_support) == EXPECTED_SECURITY_SUPPORT_ROWS,
            f"Independent constituent support reconstruction contains exactly {len(local_security_support):,} rows.",
            (
                f"Independent constituent support reconstruction contains "
                f"{len(local_security_support):,} rows; expected "
                f"{EXPECTED_SECURITY_SUPPORT_ROWS:,}."
            ),
        )
        check(
            len(local_benchmark_support) == EXPECTED_BENCHMARK_SUPPORT_ROWS,
            "Independent benchmark support reconstruction contains exactly 144 rows.",
            (
                f"Independent benchmark support reconstruction contains "
                f"{len(local_benchmark_support):,} rows; expected 144."
            ),
        )
        check(
            not local_security_support.duplicated(
                ["security_key", "feature_month_number"]
            ).any(),
            "Independent constituent support keys are unique by security and feature month.",
            "Duplicate constituent support security/month keys detected.",
        )
        check(
            not local_benchmark_support.duplicated(
                [
                    "security_key",
                    "project_ticker",
                    "feature_month_number",
                ]
            ).any(),
            "Independent benchmark support keys are unique.",
            "Duplicate benchmark support keys detected.",
        )

        if failures:
            raise RuntimeError(
                "Local support reconstruction failed."
            )

        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        connection.timeout = 600
        cursor = connection.cursor()

        lines += section("2. CORE PRESERVATION")

        for table, expected in CORE_COUNTS.items():
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )
            check(
                actual == expected,
                f"core.{table} remains unchanged at {actual:,} rows.",
                (
                    f"core.{table} contains {actual:,} rows; "
                    f"expected {expected:,}."
                ),
            )

        if failures:
            raise RuntimeError(
                "Core preservation failed."
            )

        lines += section("3. SUPPORT-TABLE RECONCILIATION")
        print("Reading corrected Azure SQL feature-support tables...")

        sql_security_support = fetch_df(
            cursor,
            """
            SELECT
                feature_month_number,
                month_end_date,
                security_key,
                project_ticker,
                adjusted_close
            FROM analytics.security_month_end_feature_support
            ORDER BY security_key, feature_month_number;
            """,
        )

        sql_benchmark_support = fetch_df(
            cursor,
            """
            SELECT
                feature_month_number,
                month_end_date,
                security_key,
                project_ticker,
                adjusted_close
            FROM analytics.benchmark_month_end_feature_support
            ORDER BY security_key, project_ticker, feature_month_number;
            """,
        )

        for frame in (
            sql_security_support,
            sql_benchmark_support,
        ):
            frame["feature_month_number"] = pd.to_numeric(
                frame["feature_month_number"],
                errors="raise",
            ).astype(int)
            frame["month_end_date"] = pd.to_datetime(
                frame["month_end_date"],
                errors="raise",
            )
            frame["security_key"] = (
                frame["security_key"].astype(str).str.strip()
            )
            frame["project_ticker"] = (
                frame["project_ticker"].astype(str).str.strip()
            )
            frame["adjusted_close"] = pd.to_numeric(
                frame["adjusted_close"],
                errors="raise",
            )

        local_security_compare = (
            local_security_support.rename(
                columns={"date": "month_end_date"}
            )
            .sort_values(
                ["security_key", "feature_month_number"]
            )
            .reset_index(drop=True)
        )
        sql_security_compare = (
            sql_security_support.sort_values(
                ["security_key", "feature_month_number"]
            )
            .reset_index(drop=True)
        )

        local_benchmark_compare = (
            local_benchmark_support.rename(
                columns={"date": "month_end_date"}
            )
            .sort_values(
                [
                    "security_key",
                    "project_ticker",
                    "feature_month_number",
                ]
            )
            .reset_index(drop=True)
        )
        sql_benchmark_compare = (
            sql_benchmark_support.sort_values(
                [
                    "security_key",
                    "project_ticker",
                    "feature_month_number",
                ]
            )
            .reset_index(drop=True)
        )

        check(
            len(sql_security_compare)
            == EXPECTED_SECURITY_SUPPORT_ROWS,
            "Azure SQL constituent support contains exactly 37,245 rows.",
            (
                f"Azure SQL constituent support contains "
                f"{len(sql_security_compare):,} rows."
            ),
        )
        check(
            len(sql_benchmark_compare)
            == EXPECTED_BENCHMARK_SUPPORT_ROWS,
            "Azure SQL benchmark support contains exactly 144 rows.",
            (
                f"Azure SQL benchmark support contains "
                f"{len(sql_benchmark_compare):,} rows."
            ),
        )

        # Compare support identifiers semantically column-by-column rather
        # than with DataFrame.equals().  DataFrame.equals() also requires
        # identical pandas dtypes, so SQL INTEGER/date values can generate a
        # false mismatch even when every identifier value is identical.
        def semantic_support_compare(
            local_frame: pd.DataFrame,
            sql_frame: pd.DataFrame,
            label: str,
        ) -> tuple[bool, dict[str, int]]:
            if len(local_frame) != len(sql_frame):
                return False, {"row_count": abs(len(local_frame) - len(sql_frame))}

            mismatch_counts: dict[str, int] = {}

            local_month = local_frame["feature_month_number"].to_numpy(dtype=np.int64)
            sql_month = sql_frame["feature_month_number"].to_numpy(dtype=np.int64)
            mismatch_counts["feature_month_number"] = int(
                np.sum(local_month != sql_month)
            )

            local_date = (
                pd.to_datetime(local_frame["month_end_date"])
                .dt.normalize()
                .to_numpy(dtype="datetime64[D]")
            )
            sql_date = (
                pd.to_datetime(sql_frame["month_end_date"])
                .dt.normalize()
                .to_numpy(dtype="datetime64[D]")
            )
            mismatch_counts["month_end_date"] = int(
                np.sum(local_date != sql_date)
            )

            for column in ("security_key", "project_ticker"):
                local_values = (
                    local_frame[column]
                    .astype(str)
                    .str.strip()
                    .to_numpy()
                )
                sql_values = (
                    sql_frame[column]
                    .astype(str)
                    .str.strip()
                    .to_numpy()
                )
                mismatch_counts[column] = int(
                    np.sum(local_values != sql_values)
                )

            return all(count == 0 for count in mismatch_counts.values()), mismatch_counts

        security_keys_equal, security_key_mismatches = semantic_support_compare(
            local_security_compare,
            sql_security_compare,
            "constituent",
        )

        security_prices_equal = (
            len(local_security_compare)
            == len(sql_security_compare)
            and np.allclose(
                local_security_compare[
                    "adjusted_close"
                ].to_numpy(dtype=float),
                sql_security_compare[
                    "adjusted_close"
                ].to_numpy(dtype=float),
                rtol=FLOAT_RTOL,
                atol=FLOAT_ATOL,
                equal_nan=False,
            )
        )

        check(
            security_keys_equal,
            (
                "Every Azure SQL constituent support key/date/ticker "
                "matches the independent local reconstruction."
            ),
            (
                "Constituent support identifier mismatch counts: "
                + ", ".join(
                    f"{name}={count}"
                    for name, count in security_key_mismatches.items()
                )
            ),
        )
        check(
            security_prices_equal,
            "Every Azure SQL constituent support adjusted close matches the independent local reconstruction.",
            "Constituent support adjusted-close mismatch detected.",
        )

        benchmark_keys_equal, benchmark_key_mismatches = semantic_support_compare(
            local_benchmark_compare,
            sql_benchmark_compare,
            "benchmark",
        )

        benchmark_prices_equal = (
            len(local_benchmark_compare)
            == len(sql_benchmark_compare)
            and np.allclose(
                local_benchmark_compare[
                    "adjusted_close"
                ].to_numpy(dtype=float),
                sql_benchmark_compare[
                    "adjusted_close"
                ].to_numpy(dtype=float),
                rtol=FLOAT_RTOL,
                atol=FLOAT_ATOL,
                equal_nan=False,
            )
        )

        check(
            benchmark_keys_equal,
            (
                "Every Azure SQL benchmark support key/date/ticker "
                "matches the independent local reconstruction."
            ),
            (
                "Benchmark support identifier mismatch counts: "
                + ", ".join(
                    f"{name}={count}"
                    for name, count in benchmark_key_mismatches.items()
                )
            ),
        )
        check(
            benchmark_prices_equal,
            "Every Azure SQL benchmark support adjusted close matches the independent local reconstruction.",
            "Benchmark support adjusted-close mismatch detected.",
        )

        if failures:
            raise RuntimeError(
                "Support-table reconciliation failed."
            )

        lines += section("4. INDEPENDENT CONSTITUENT FEATURE RECONSTRUCTION")
        print("Reading ranking-date snapshot and corrected feature view...")

        snapshot = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_end_date,
                security_key,
                adjusted_close
            FROM analytics.security_month_end_snapshot
            ORDER BY analysis_month_number, security_key;
            """,
        )

        features = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_end_date,
                security_key,
                adjusted_close,
                lag_1_month_end_date,
                trailing_return_1m,
                trailing_return_1m_complete,
                lag_3_month_end_date,
                trailing_return_3m,
                trailing_return_3m_complete,
                lag_6_month_end_date,
                trailing_return_6m,
                trailing_return_6m_complete,
                lag_12_month_end_date,
                trailing_return_12m,
                trailing_return_12m_complete,
                momentum_12_1_start_date,
                momentum_12_1_end_date,
                momentum_12_1,
                momentum_12_1_complete
            FROM analytics.v_security_monthly_return_features
            ORDER BY analysis_month_number, security_key;
            """,
        )

        for frame in (snapshot, features):
            frame["analysis_month_number"] = pd.to_numeric(
                frame["analysis_month_number"],
                errors="raise",
            ).astype(int)
            frame["month_end_date"] = pd.to_datetime(
                frame["month_end_date"],
                errors="raise",
            )
            frame["security_key"] = (
                frame["security_key"].astype(str).str.strip()
            )
            frame["adjusted_close"] = pd.to_numeric(
                frame["adjusted_close"],
                errors="raise",
            )

        date_columns = [
            "lag_1_month_end_date",
            "lag_3_month_end_date",
            "lag_6_month_end_date",
            "lag_12_month_end_date",
            "momentum_12_1_start_date",
            "momentum_12_1_end_date",
        ]
        for column in date_columns:
            features[column] = pd.to_datetime(
                features[column],
                errors="coerce",
            )

        float_columns = [
            "trailing_return_1m",
            "trailing_return_3m",
            "trailing_return_6m",
            "trailing_return_12m",
            "momentum_12_1",
        ]
        for column in float_columns:
            features[column] = pd.to_numeric(
                features[column],
                errors="coerce",
            )

        flag_columns = [
            "trailing_return_1m_complete",
            "trailing_return_3m_complete",
            "trailing_return_6m_complete",
            "trailing_return_12m_complete",
            "momentum_12_1_complete",
        ]
        for column in flag_columns:
            features[column] = pd.to_numeric(
                features[column],
                errors="raise",
            ).astype(int)

        check(
            len(snapshot) == EXPECTED_SNAPSHOT_ROWS,
            "Ranking-date snapshot contains exactly 30,211 rows.",
            (
                f"Ranking-date snapshot contains "
                f"{len(snapshot):,} rows."
            ),
        )
        check(
            len(features) == EXPECTED_SNAPSHOT_ROWS,
            "Corrected constituent feature view preserves exactly 30,211 ranking-date rows.",
            (
                f"Corrected constituent feature view contains "
                f"{len(features):,} rows."
            ),
        )
        check(
            not features.duplicated(
                ["analysis_month_number", "security_key"]
            ).any(),
            "Corrected constituent feature keys are unique.",
            "Duplicate corrected constituent feature keys detected.",
        )

        local_support_lookup = {
            (
                str(row.security_key),
                int(row.feature_month_number),
            ): (
                pd.Timestamp(row.month_end_date),
                float(row.adjusted_close),
            )
            for row in local_security_compare.itertuples(index=False)
        }

        expected_rows: list[dict[str, Any]] = []

        for row in snapshot.itertuples(index=False):
            month_no = int(row.analysis_month_number)
            security_key = str(row.security_key)
            current_price = float(row.adjusted_close)

            expected: dict[str, Any] = {
                "analysis_month_number": month_no,
                "security_key": security_key,
            }

            lag_values: dict[int, tuple[pd.Timestamp, float] | None] = {}

            for horizon in (1, 3, 6, 12):
                lag = local_support_lookup.get(
                    (security_key, month_no - horizon)
                )
                lag_values[horizon] = lag

                if lag is None:
                    expected[f"lag_{horizon}_month_end_date"] = pd.NaT
                    expected[f"trailing_return_{horizon}m"] = np.nan
                    expected[f"trailing_return_{horizon}m_complete"] = 0
                else:
                    lag_date, lag_price = lag
                    expected[f"lag_{horizon}_month_end_date"] = lag_date
                    expected[f"trailing_return_{horizon}m"] = (
                        current_price / lag_price - 1.0
                    )
                    expected[f"trailing_return_{horizon}m_complete"] = 1

            lag_1 = lag_values[1]
            lag_12 = lag_values[12]

            # The SQL view exposes each momentum anchor date independently:
            # start_date comes from lag_12 when available and end_date comes
            # from lag_1 when available.  The momentum value itself is complete
            # only when both anchors exist.  Preserve that exact semantics in
            # the independent reconstruction, including incomplete rows.
            expected["momentum_12_1_start_date"] = (
                lag_12[0] if lag_12 is not None else pd.NaT
            )
            expected["momentum_12_1_end_date"] = (
                lag_1[0] if lag_1 is not None else pd.NaT
            )

            if lag_1 is None or lag_12 is None:
                expected["momentum_12_1"] = np.nan
                expected["momentum_12_1_complete"] = 0
            else:
                expected["momentum_12_1"] = (
                    lag_1[1] / lag_12[1] - 1.0
                )
                expected["momentum_12_1_complete"] = 1

            expected_rows.append(expected)

        expected_features = pd.DataFrame(expected_rows).sort_values(
            ["analysis_month_number", "security_key"]
        ).reset_index(drop=True)

        actual_features = features.sort_values(
            ["analysis_month_number", "security_key"]
        ).reset_index(drop=True)

        key_match = (
            expected_features[
                ["analysis_month_number", "security_key"]
            ].equals(
                actual_features[
                    ["analysis_month_number", "security_key"]
                ]
            )
        )
        check(
            key_match,
            "Independent feature reconstruction keys match all SQL feature rows.",
            "Independent feature reconstruction keys do not match SQL.",
        )

        for horizon, expected_count in EXPECTED_FEATURE_COMPLETE.items():
            flag_col = f"trailing_return_{horizon}m_complete"
            return_col = f"trailing_return_{horizon}m"
            date_col = f"lag_{horizon}_month_end_date"

            actual_count = int(
                actual_features[flag_col].sum()
            )
            independent_count = int(
                expected_features[flag_col].sum()
            )

            check(
                actual_count == expected_count
                and independent_count == expected_count,
                (
                    f"{horizon}-month completeness independently "
                    f"reconciles at {expected_count:,} rows."
                ),
                (
                    f"{horizon}-month completeness mismatch: "
                    f"SQL={actual_count:,}, independent="
                    f"{independent_count:,}, expected="
                    f"{expected_count:,}."
                ),
            )

            date_match = (
                (
                    expected_features[date_col].isna()
                    & actual_features[date_col].isna()
                )
                | (
                    expected_features[date_col]
                    == actual_features[date_col]
                )
            ).all()

            expected_return = expected_features[
                return_col
            ].to_numpy(dtype=float)
            actual_return = actual_features[
                return_col
            ].to_numpy(dtype=float)

            return_match = np.allclose(
                expected_return,
                actual_return,
                rtol=FLOAT_RTOL,
                atol=FLOAT_ATOL,
                equal_nan=True,
            )

            check(
                bool(date_match),
                f"{horizon}-month lag dates match the independent support reconstruction for every row.",
                f"{horizon}-month lag-date mismatch detected.",
            )
            check(
                bool(return_match),
                f"{horizon}-month trailing returns match the independent reconstruction for every row.",
                f"{horizon}-month trailing-return mismatch detected.",
            )

        actual_momentum_count = int(
            actual_features[
                "momentum_12_1_complete"
            ].sum()
        )
        independent_momentum_count = int(
            expected_features[
                "momentum_12_1_complete"
            ].sum()
        )

        check(
            actual_momentum_count == EXPECTED_MOMENTUM_ROWS
            and independent_momentum_count == EXPECTED_MOMENTUM_ROWS,
            "Canonical 12-1 momentum independently reconciles at exactly 30,121 rows.",
            (
                f"Momentum completeness mismatch: SQL="
                f"{actual_momentum_count:,}, independent="
                f"{independent_momentum_count:,}."
            ),
        )

        momentum_return_match = np.allclose(
            expected_features[
                "momentum_12_1"
            ].to_numpy(dtype=float),
            actual_features[
                "momentum_12_1"
            ].to_numpy(dtype=float),
            rtol=FLOAT_RTOL,
            atol=FLOAT_ATOL,
            equal_nan=True,
        )
        check(
            bool(momentum_return_match),
            "Every SQL 12-1 momentum value matches the independent local reconstruction.",
            "12-1 momentum value mismatch detected.",
        )

        momentum_start_match = (
            (
                expected_features[
                    "momentum_12_1_start_date"
                ].isna()
                & actual_features[
                    "momentum_12_1_start_date"
                ].isna()
            )
            | (
                expected_features[
                    "momentum_12_1_start_date"
                ]
                == actual_features[
                    "momentum_12_1_start_date"
                ]
            )
        ).all()

        momentum_end_match = (
            (
                expected_features[
                    "momentum_12_1_end_date"
                ].isna()
                & actual_features[
                    "momentum_12_1_end_date"
                ].isna()
            )
            | (
                expected_features[
                    "momentum_12_1_end_date"
                ]
                == actual_features[
                    "momentum_12_1_end_date"
                ]
            )
        ).all()

        check(
            bool(momentum_start_match and momentum_end_match),
            "Every SQL 12-1 momentum start/end anchor matches months -12 and -1 from the independent support reconstruction.",
            "12-1 momentum anchor-date mismatch detected.",
        )

        if failures:
            raise RuntimeError(
                "Independent constituent feature reconstruction failed."
            )

        lines += section("5. MONTHLY COVERAGE AND RANKING PROPAGATION")

        independent_monthly = (
            expected_features.groupby(
                "analysis_month_number",
                sort=True,
            )["momentum_12_1_complete"]
            .sum()
            .astype(int)
        )

        sql_portfolio_monthly = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                COUNT_BIG(*) AS assignment_count
            FROM analytics.v_security_monthly_momentum_portfolio
            GROUP BY analysis_month_number
            ORDER BY analysis_month_number;
            """,
        )

        sql_portfolio_monthly[
            "analysis_month_number"
        ] = pd.to_numeric(
            sql_portfolio_monthly["analysis_month_number"],
            errors="raise",
        ).astype(int)
        sql_portfolio_monthly["assignment_count"] = pd.to_numeric(
            sql_portfolio_monthly["assignment_count"],
            errors="raise",
        ).astype(int)

        check(
            len(independent_monthly) == EXPECTED_RANKING_MONTHS
            and (independent_monthly > 0).all(),
            "Independent corrected momentum coverage is positive in all 60 ranking months.",
            "Independent corrected momentum coverage does not span all 60 ranking months.",
        )
        check(
            len(sql_portfolio_monthly) == EXPECTED_RANKING_MONTHS,
            "SQL momentum portfolio contains all 60 ranking months.",
            (
                f"SQL momentum portfolio contains "
                f"{len(sql_portfolio_monthly)} ranking months."
            ),
        )

        monthly_reconciliation = (
            sql_portfolio_monthly.set_index(
                "analysis_month_number"
            )["assignment_count"]
            .reindex(independent_monthly.index)
        )

        check(
            monthly_reconciliation.equals(independent_monthly),
            "Every monthly SQL ranking-assignment count equals independently reconstructed corrected momentum eligibility.",
            "One or more monthly portfolio-assignment counts do not match independent momentum eligibility.",
        )

        first_twelve = independent_monthly.loc[1:12]
        lines += [
            "",
            "2021 independently reconstructed complete momentum signals:",
        ]
        for month_no, count in first_twelve.items():
            period = pd.Period(
                year=2021 + (int(month_no) - 1) // 12,
                month=((int(month_no) - 1) % 12) + 1,
                freq="M",
            )
            lines.append(
                f"  {period}: {int(count):,}"
            )

        lines += section("6. DOWNSTREAM POPULATION AUDIT")

        checks = [
            (
                "Momentum portfolio assignments",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_security_monthly_momentum_portfolio;
                """,
                EXPECTED_MOMENTUM_ROWS,
            ),
            (
                "Decile forward-return rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_momentum_decile_forward_return_1m;
                """,
                EXPECTED_DECILE_ROWS,
            ),
            (
                "Complete decile forward-return rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_momentum_decile_forward_return_1m
                WHERE forward_return_1m_complete = 1;
                """,
                EXPECTED_COMPLETE_DECILE_ROWS,
            ),
            (
                "Winner-minus-loser rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_momentum_long_short_forward_return_1m;
                """,
                EXPECTED_WML_ROWS,
            ),
            (
                "Complete winner-minus-loser rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_momentum_long_short_forward_return_1m
                WHERE forward_return_1m_complete = 1;
                """,
                EXPECTED_COMPLETE_WML_ROWS,
            ),
            (
                "Benchmark forward-return rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_benchmark_monthly_forward_return_1m;
                """,
                EXPECTED_BENCHMARK_FORWARD_ROWS,
            ),
            (
                "Complete benchmark forward-return rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_benchmark_monthly_forward_return_1m
                WHERE forward_return_1m_complete = 1;
                """,
                EXPECTED_COMPLETE_BENCHMARK_FORWARD_ROWS,
            ),
            (
                "Security forward-return rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_security_monthly_forward_return_1m;
                """,
                EXPECTED_SECURITY_FORWARD_ROWS,
            ),
            (
                "Complete security forward-return rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_security_monthly_forward_return_1m
                WHERE forward_return_1m_complete = 1;
                """,
                EXPECTED_COMPLETE_SECURITY_FORWARD_ROWS,
            ),
            (
                "Right-censored security assignments",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_security_monthly_forward_return_1m
                WHERE out_of_scope_right_censored = 1;
                """,
                EXPECTED_RIGHT_CENSORED_ROWS,
            ),
            (
                "Gross monthly return-panel rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_momentum_monthly_return_panel;
                """,
                EXPECTED_PANEL_ROWS,
            ),
            (
                "Turnover rows",
                """
                SELECT COUNT_BIG(*)
                FROM analytics.v_momentum_decile_turnover;
                """,
                EXPECTED_TURNOVER_ROWS,
            ),
        ]

        for label, query, expected in checks:
            actual = scalar(cursor, query)
            check(
                actual == expected,
                f"{label}: {actual:,} (expected).",
                (
                    f"{label}: {actual:,}; "
                    f"expected {expected:,}."
                ),
            )

        distinct_performance_months = scalar(
            cursor,
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
        )
        check(
            distinct_performance_months
            == EXPECTED_PERFORMANCE_MONTHS,
            "Gross performance panel contains exactly 59 observable months.",
            (
                f"Gross performance panel contains "
                f"{distinct_performance_months} months; "
                "expected 59."
            ),
        )

        distinct_turnover_months = scalar(
            cursor,
            """
            SELECT COUNT_BIG(DISTINCT analysis_month_number)
            FROM analytics.v_momentum_decile_turnover;
            """,
        )
        check(
            distinct_turnover_months
            == EXPECTED_TURNOVER_MONTHS,
            "Turnover layer contains exactly 59 consecutive rebalance months.",
            (
                f"Turnover layer contains "
                f"{distinct_turnover_months} months; "
                "expected 59."
            ),
        )

        series_codes = fetch_df(
            cursor,
            """
            SELECT DISTINCT series_code
            FROM analytics.v_momentum_monthly_return_panel
            ORDER BY series_code;
            """,
        )
        actual_series = {
            str(value).strip()
            for value in series_codes["series_code"]
        }
        check(
            actual_series == EXPECTED_SERIES,
            "Gross return panel contains the expected 13 analytical series.",
            (
                "Unexpected analytical series: "
                + ", ".join(sorted(actual_series))
            ),
        )

        min_month = scalar(
            cursor,
            """
            SELECT MIN(analysis_month_number)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
        )
        max_month = scalar(
            cursor,
            """
            SELECT MAX(analysis_month_number)
            FROM analytics.v_momentum_monthly_return_panel;
            """,
        )
        check(
            min_month == 1 and max_month == 59,
            "Completed gross performance spans analysis months 1 through 59.",
            (
                f"Gross performance spans analysis months "
                f"{min_month} through {max_month}; expected 1 through 59."
            ),
        )

        censored_months = fetch_df(
            cursor,
            """
            SELECT DISTINCT analysis_month_number
            FROM analytics.v_security_monthly_forward_return_1m
            WHERE out_of_scope_right_censored = 1
            ORDER BY analysis_month_number;
            """,
        )
        censored_values = [
            int(x)
            for x in censored_months[
                "analysis_month_number"
            ].tolist()
        ]
        check(
            censored_values == [60],
            "Only analysis month 60 (December 2025 ranking) is right-censored.",
            (
                "Unexpected right-censored analysis months: "
                + ", ".join(map(str, censored_values))
            ),
        )

        if failures:
            raise RuntimeError(
                "Downstream population audit failed."
            )

        lines += section("7. PERFORMANCE-LAYER STRUCTURAL CONTROLS")

        cumulative_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_cumulative_wealth;
            """,
        )
        drawdown_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_wealth_drawdown;
            """,
        )
        summary_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_performance_summary;
            """,
        )
        turnover_summary_rows = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_turnover_summary;
            """,
        )

        check(
            cumulative_rows == EXPECTED_PANEL_ROWS,
            "Cumulative wealth preserves all 767 monthly return-panel rows.",
            (
                f"Cumulative wealth contains "
                f"{cumulative_rows:,} rows."
            ),
        )
        check(
            drawdown_rows == EXPECTED_PANEL_ROWS,
            "Drawdown layer preserves all 767 monthly return-panel rows.",
            (
                f"Drawdown layer contains "
                f"{drawdown_rows:,} rows."
            ),
        )
        check(
            summary_rows == len(EXPECTED_SERIES),
            "Performance summary contains exactly 13 series.",
            (
                f"Performance summary contains "
                f"{summary_rows} rows."
            ),
        )
        check(
            turnover_summary_rows == 10,
            "Turnover summary contains exactly one row per momentum decile.",
            (
                f"Turnover summary contains "
                f"{turnover_summary_rows} rows."
            ),
        )

        panel_duplicates = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM
            (
                SELECT
                    analysis_month_number,
                    series_code,
                    COUNT_BIG(*) AS n
                FROM analytics.v_momentum_monthly_return_panel
                GROUP BY analysis_month_number, series_code
                HAVING COUNT_BIG(*) > 1
            ) AS duplicate_keys;
            """,
        )
        check(
            panel_duplicates == 0,
            "Gross monthly return-panel month/series keys are unique.",
            (
                f"Gross monthly return panel contains "
                f"{panel_duplicates} duplicate keys."
            ),
        )

        invalid_drawdowns = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM analytics.v_momentum_wealth_drawdown
            WHERE drawdown > 0.000000000001
               OR ending_wealth <= 0
               OR running_peak_wealth <= 0;
            """,
        )
        check(
            invalid_drawdowns == 0,
            "All corrected gross wealth and drawdown observations remain structurally valid.",
            (
                f"Found {invalid_drawdowns} invalid "
                "wealth/drawdown rows."
            ),
        )

        lines += section("8. FINAL INTEGRITY GATE")

        if failures:
            lines += [
                "AZURE_SQL_MOMENTUM_LOOKBACK_SCOPE_CORRECTION_INTEGRITY_AUDIT_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]
        else:
            lines += [
                "AZURE_SQL_MOMENTUM_LOOKBACK_SCOPE_CORRECTION_INTEGRITY_AUDIT_PASSED",
                f"Passed checks: {passed}",
                "Failed checks: 0",
                "Database modifications performed: 0",
                "Core-table modifications detected: 0",
                "Constituent feature-support rows: 37,245",
                "Benchmark feature-support rows: 144",
                "Ranking-date constituent rows: 30,211",
                "Corrected 12-1 momentum rows: 30,121",
                "Ranking months: 60",
                "Observable completed performance months: 59",
                "Gross return-panel rows: 767",
                "Right-censored December 2025 assignments: 501",
                "",
                "CORRECTION QUALITY GATE COMPLETE.",
                (
                    "The 2020 standardized price history is confirmed as "
                    "feature support only and does not expand the "
                    "2021-2025 point-in-time ranking universe."
                ),
                (
                    "The corrected momentum population independently "
                    "reconciles to permanent-security historical price "
                    "support using months -12 through -1."
                ),
            ]

        cursor.close()

    except Exception as error:
        failures.append(str(error))
        lines += [
            "",
            rule(),
            "AUDIT EXECUTION FAILED",
            rule(),
            type(error).__name__,
            str(error),
            "AZURE_SQL_MOMENTUM_LOOKBACK_SCOPE_CORRECTION_INTEGRITY_AUDIT_FAILED",
        ]

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

        report_text = "\n".join(lines) + "\n"
        REPORT_PATH.write_text(
            report_text,
            encoding="utf-8",
        )
        print(report_text, end="")
        print(f"Report saved: {REPORT_PATH}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
