from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

GICS_PATH = (
    ROOT
    / "data"
    / "interim"
    / "security_gics_sector_month_end_2021_2025.csv"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_h2_sector_momentum_ranking_integrity_audit.txt"
)

SCRIPT_VERSION = "2026-08-24-v2-h2-sector-ranking-integrity-audit"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}

EXPECTED_GICS_ROWS = 30_211
EXPECTED_RANKING_ROWS = 30_121
EXPECTED_MONTHS = 60
EXPECTED_SECTOR_MONTHS = 660
EXPECTED_SUMMARY_ROWS = 3_300
FLOAT_TOL = 1e-12


def section(title: str) -> list[str]:
    rule = "=" * 88
    return [rule, title, rule]


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
            "Missing environment variables: "
            + ", ".join(missing)
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

    for attempt in range(1, 6):
        try:
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            print(
                f"ODBC connection established on attempt {attempt} / 5."
            )
            return connection
        except pyodbc.Error:
            if attempt == 5:
                raise
            print(
                f"ODBC connection attempt {attempt} / 5 failed. "
                "Retrying in 10 seconds."
            )
            time.sleep(10)

    raise RuntimeError("ODBC retry loop ended unexpectedly.")


def fetch_df(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    return pd.DataFrame.from_records(
        cursor.fetchall(),
        columns=columns,
    )


def scalar(cursor, query: str) -> int:
    cursor.execute(query)
    return int(cursor.fetchone()[0])


def sql_ntile_5(row_number: int, n: int) -> int:
    """
    Exact SQL Server NTILE(5) allocation for row_number 1..n.

    The first (n % 5) buckets receive one additional row.
    """
    if n < 5:
        raise ValueError("NTILE(5) preregistration requires n >= 5.")

    base = n // 5
    extra = n % 5

    cutoff = (base + 1) * extra

    if row_number <= cutoff:
        return ((row_number - 1) // (base + 1)) + 1

    return extra + ((row_number - cutoff - 1) // base) + 1


def close(a: Any, b: Any, tol: float = FLOAT_TOL) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return math.isclose(
        float(a),
        float(b),
        rel_tol=tol,
        abs_tol=tol,
    )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = section(
        "AZURE SQL H2 SECTOR-RELATIVE MOMENTUM RANKING INTEGRITY AUDIT"
    )
    lines += [
        "Mode: LOCAL + Azure SQL READ-ONLY",
        "Database modifications performed: 0",
        "Forward-return / H2 performance inspection: NO",
        "",
    ]

    failures: list[str] = []
    passed = 0
    connection = None

    def check(
        condition: bool,
        success: str,
        failure: str,
    ) -> None:
        nonlocal passed
        if condition:
            lines.append(f"PASS: {success}")
            passed += 1
        else:
            lines.append(f"FAIL: {failure}")
            failures.append(failure)

    try:
        if not GICS_PATH.exists():
            raise FileNotFoundError(GICS_PATH)

        gics = pd.read_csv(GICS_PATH)
        gics["analysis_month_number"] = pd.to_numeric(
            gics["analysis_month_number"],
            errors="raise",
        ).astype(int)
        gics["month_end_date"] = pd.to_datetime(
            gics["month_end_date"],
            errors="raise",
        )
        gics["security_key"] = (
            gics["security_key"].astype(str).str.strip()
        )
        gics["project_ticker"] = (
            gics["project_ticker"].astype(str).str.strip()
        )
        gics["gics_sector"] = (
            gics["gics_sector"].astype(str).str.strip()
        )

        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        cursor = connection.cursor()

        lines += section("1. SOURCE / CORE PRESERVATION")

        check(
            len(gics) == EXPECTED_GICS_ROWS,
            "Local validated GICS file remains exactly 30,211 rows.",
            f"Local GICS rows: {len(gics):,}.",
        )

        for table, expected in CORE_COUNTS.items():
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )
            check(
                actual == expected,
                f"core.{table} remains {expected:,} rows.",
                (
                    f"core.{table}: found {actual:,}; "
                    f"expected {expected:,}."
                ),
            )

        sql_gics = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_end_date,
                security_key,
                project_ticker,
                gics_sector
            FROM analytics.security_month_end_gics_sector
            ORDER BY analysis_month_number, security_key;
            """,
        )

        sql_gics["analysis_month_number"] = pd.to_numeric(
            sql_gics["analysis_month_number"],
            errors="raise",
        ).astype(int)
        sql_gics["month_end_date"] = pd.to_datetime(
            sql_gics["month_end_date"],
            errors="raise",
        )

        for column in ("security_key", "project_ticker", "gics_sector"):
            sql_gics[column] = (
                sql_gics[column].astype(str).str.strip()
            )

        comparison_order = [
            "analysis_month_number",
            "security_key",
        ]

        local_gics = gics.sort_values(
            comparison_order,
            kind="mergesort",
        ).reset_index(drop=True)

        sql_gics = sql_gics.sort_values(
            comparison_order,
            kind="mergesort",
        ).reset_index(drop=True)

        check(
            len(sql_gics) == EXPECTED_GICS_ROWS,
            "Azure GICS table contains exactly 30,211 rows.",
            f"Azure GICS rows: {len(sql_gics):,}.",
        )

        gics_cell_mismatches = 0
        if len(local_gics) == len(sql_gics):
            for column in (
                "analysis_month_number",
                "month_end_date",
                "security_key",
                "project_ticker",
                "gics_sector",
            ):
                gics_cell_mismatches += int(
                    (local_gics[column] != sql_gics[column]).sum()
                )
        else:
            gics_cell_mismatches = abs(
                len(local_gics) - len(sql_gics)
            ) + 1

        check(
            gics_cell_mismatches == 0,
            (
                "Every Azure GICS value exactly matches the validated "
                "local file after deterministic Python-side ordering."
            ),
            (
                "Azure/local GICS cell mismatches after deterministic "
                f"ordering: {gics_cell_mismatches}."
            ),
        )

        lines += section("2. INDEPENDENT H2 RANKING RECONSTRUCTION")

        features = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_end_date,
                security_key,
                project_ticker,
                momentum_12_1_start_date,
                momentum_12_1_end_date,
                momentum_12_1
            FROM analytics.v_security_monthly_return_features
            WHERE momentum_12_1_complete = 1
              AND momentum_12_1 IS NOT NULL
            ORDER BY analysis_month_number, security_key;
            """,
        )

        features["analysis_month_number"] = pd.to_numeric(
            features["analysis_month_number"],
            errors="raise",
        ).astype(int)
        for column in (
            "month_end_date",
            "momentum_12_1_start_date",
            "momentum_12_1_end_date",
        ):
            features[column] = pd.to_datetime(
                features[column],
                errors="raise",
            )
        features["security_key"] = (
            features["security_key"].astype(str).str.strip()
        )
        features["project_ticker"] = (
            features["project_ticker"].astype(str).str.strip()
        )
        features["momentum_12_1"] = pd.to_numeric(
            features["momentum_12_1"],
            errors="raise",
        )

        check(
            len(features) == EXPECTED_RANKING_ROWS,
            "Corrected feature source contains exactly 30,121 eligible signals.",
            f"Eligible feature rows: {len(features):,}.",
        )

        expected = features.merge(
            local_gics,
            on=[
                "analysis_month_number",
                "month_end_date",
                "security_key",
                "project_ticker",
            ],
            how="inner",
            validate="one_to_one",
        )

        check(
            len(expected) == EXPECTED_RANKING_ROWS,
            (
                "Every corrected momentum signal joins to exactly one "
                "validated point-in-time GICS sector."
            ),
            (
                f"Independent momentum/GICS join rows: "
                f"{len(expected):,}; expected {EXPECTED_RANKING_ROWS:,}."
            ),
        )

        reconstructed_parts: list[pd.DataFrame] = []

        for (
            month_number,
            sector,
        ), group in expected.groupby(
            ["analysis_month_number", "gics_sector"],
            sort=True,
        ):
            ordered = group.sort_values(
                ["momentum_12_1", "security_key"],
                ascending=[True, True],
                kind="mergesort",
            ).reset_index(drop=True)

            n = len(ordered)

            if n < 5:
                failures.append(
                    f"Sector-month {month_number}/{sector} has only {n} rows."
                )
                continue

            ordered["sector_eligible_count"] = n
            ordered["sector_momentum_rank_asc"] = (
                range(1, n + 1)
            )
            ordered["sector_momentum_quintile"] = [
                sql_ntile_5(row_number, n)
                for row_number in range(1, n + 1)
            ]

            quintile_counts = (
                ordered.groupby(
                    "sector_momentum_quintile"
                )["security_key"]
                .transform("count")
            )

            ordered["sector_momentum_portfolio"] = (
                ordered["sector_momentum_quintile"].map(
                    {
                        1: "LOSER",
                        2: "MIDDLE",
                        3: "MIDDLE",
                        4: "MIDDLE",
                        5: "WINNER",
                    }
                )
            )
            ordered["sector_quintile_security_count"] = (
                quintile_counts.astype(int)
            )
            ordered["sector_equal_weight"] = (
                1.0
                / ordered[
                    "sector_quintile_security_count"
                ].astype(float)
            )
            ordered["sector_neutral_leg_weight"] = (
                ordered["sector_equal_weight"] / 11.0
            )

            reconstructed_parts.append(ordered)

        expected_rank = pd.concat(
            reconstructed_parts,
            ignore_index=True,
        )

        check(
            len(expected_rank) == EXPECTED_RANKING_ROWS,
            "Independent ranking reconstruction contains 30,121 rows.",
            (
                f"Independent ranking rows: "
                f"{len(expected_rank):,}."
            ),
        )

        check(
            expected_rank[
                ["analysis_month_number", "gics_sector"]
            ]
            .drop_duplicates()
            .shape[0]
            == EXPECTED_SECTOR_MONTHS,
            "Independent reconstruction contains all 660 month/sector partitions.",
            "Independent reconstruction does not contain 660 sector-months.",
        )

        actual = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_start_date,
                month_end_date,
                security_key,
                project_ticker,
                gics_sector,
                momentum_12_1_start_date,
                momentum_12_1_end_date,
                momentum_12_1,
                sector_eligible_count,
                sector_momentum_rank_asc,
                sector_momentum_quintile,
                sector_momentum_portfolio,
                sector_quintile_security_count,
                sector_equal_weight,
                sector_neutral_leg_weight
            FROM analytics.v_security_monthly_sector_momentum_portfolio
            ORDER BY
                analysis_month_number,
                gics_sector,
                sector_momentum_rank_asc;
            """,
        )

        integer_columns = (
            "analysis_month_number",
            "sector_eligible_count",
            "sector_momentum_rank_asc",
            "sector_momentum_quintile",
            "sector_quintile_security_count",
        )
        for column in integer_columns:
            actual[column] = pd.to_numeric(
                actual[column],
                errors="raise",
            ).astype(int)

        for column in (
            "month_start_date",
            "month_end_date",
            "momentum_12_1_start_date",
            "momentum_12_1_end_date",
        ):
            actual[column] = pd.to_datetime(
                actual[column],
                errors="raise",
            )

        for column in (
            "momentum_12_1",
            "sector_equal_weight",
            "sector_neutral_leg_weight",
        ):
            actual[column] = pd.to_numeric(
                actual[column],
                errors="raise",
            )

        for column in (
            "security_key",
            "project_ticker",
            "gics_sector",
            "sector_momentum_portfolio",
        ):
            actual[column] = (
                actual[column].astype(str).str.strip()
            )

        expected_compare = expected_rank[
            [
                "analysis_month_number",
                "month_end_date",
                "security_key",
                "project_ticker",
                "gics_sector",
                "momentum_12_1_start_date",
                "momentum_12_1_end_date",
                "momentum_12_1",
                "sector_eligible_count",
                "sector_momentum_rank_asc",
                "sector_momentum_quintile",
                "sector_momentum_portfolio",
                "sector_quintile_security_count",
                "sector_equal_weight",
                "sector_neutral_leg_weight",
            ]
        ].copy()

        expected_compare["month_start_date"] = (
            expected_compare["month_end_date"]
            .dt.to_period("M")
            .dt.to_timestamp()
        )

        order = [
            "analysis_month_number",
            "gics_sector",
            "sector_momentum_rank_asc",
        ]

        expected_compare = expected_compare.sort_values(
            order
        ).reset_index(drop=True)

        actual = actual.sort_values(
            order
        ).reset_index(drop=True)

        check(
            len(actual) == EXPECTED_RANKING_ROWS,
            "SQL H2 portfolio view contains exactly 30,121 rows.",
            f"SQL H2 portfolio rows: {len(actual):,}.",
        )

        exact_columns = (
            "analysis_month_number",
            "month_start_date",
            "month_end_date",
            "security_key",
            "project_ticker",
            "gics_sector",
            "momentum_12_1_start_date",
            "momentum_12_1_end_date",
            "sector_eligible_count",
            "sector_momentum_rank_asc",
            "sector_momentum_quintile",
            "sector_momentum_portfolio",
            "sector_quintile_security_count",
        )

        exact_mismatches = 0
        numeric_mismatches = 0
        momentum_mismatches = 0
        sector_equal_weight_mismatches = 0
        sector_neutral_weight_mismatches = 0

        for i in range(len(actual)):
            a = actual.iloc[i]
            e = expected_compare.iloc[i]

            if any(a[col] != e[col] for col in exact_columns):
                exact_mismatches += 1

            momentum_ok = close(
                a["momentum_12_1"],
                e["momentum_12_1"],
            )
            sector_equal_ok = close(
                a["sector_equal_weight"],
                e["sector_equal_weight"],
            )
            sector_neutral_ok = close(
                a["sector_neutral_leg_weight"],
                e["sector_neutral_leg_weight"],
            )

            momentum_mismatches += int(not momentum_ok)
            sector_equal_weight_mismatches += int(
                not sector_equal_ok
            )
            sector_neutral_weight_mismatches += int(
                not sector_neutral_ok
            )

            if not (
                momentum_ok
                and sector_equal_ok
                and sector_neutral_ok
            ):
                numeric_mismatches += 1

        lines.append(
            "Numeric mismatch detail: "
            f"momentum={momentum_mismatches:,} | "
            f"sector_equal_weight={sector_equal_weight_mismatches:,} | "
            f"sector_neutral_leg_weight={sector_neutral_weight_mismatches:,}"
        )

        check(
            exact_mismatches == 0,
            (
                "Every SQL ranking key, rank, quintile, label, date, "
                "and security count matches independent Python reconstruction."
            ),
            f"Exact reconstructed-row mismatches: {exact_mismatches}.",
        )
        check(
            numeric_mismatches == 0,
            (
                "Every SQL momentum value and portfolio target weight "
                "matches independent Python reconstruction."
            ),
            f"Numeric reconstructed-row mismatches: {numeric_mismatches}.",
        )

        lines += section("3. PREREGISTERED QUINTILE / WEIGHTING CONTROLS")

        actual_summary = fetch_df(
            cursor,
            """
            SELECT *
            FROM analytics.v_sector_momentum_quintile_monthly_summary
            ORDER BY
                analysis_month_number,
                gics_sector,
                sector_momentum_quintile;
            """,
        )

        check(
            len(actual_summary) == EXPECTED_SUMMARY_ROWS,
            "SQL summary contains exactly 3,300 month/sector/quintile rows.",
            f"SQL summary rows: {len(actual_summary):,}.",
        )

        q_counts = (
            actual.groupby(
                [
                    "analysis_month_number",
                    "gics_sector",
                    "sector_momentum_quintile",
                ]
            )["security_key"]
            .count()
            .reset_index(name="n")
        )

        imbalance = (
            q_counts.groupby(
                ["analysis_month_number", "gics_sector"]
            )["n"]
            .agg(["min", "max"])
        )

        check(
            bool(((imbalance["max"] - imbalance["min"]) <= 1).all()),
            "Every sector-month has SQL NTILE(5) bucket sizes differing by at most one.",
            "At least one sector-month has invalid quintile-size imbalance.",
        )

        loser_top_errors = 0
        for (_, _), group in actual.groupby(
            ["analysis_month_number", "gics_sector"],
            sort=False,
        ):
            q1 = group[
                group["sector_momentum_quintile"] == 1
            ]["momentum_12_1"]
            q5 = group[
                group["sector_momentum_quintile"] == 5
            ]["momentum_12_1"]

            if q1.empty or q5.empty or float(q1.max()) > float(q5.min()):
                loser_top_errors += 1

        check(
            loser_top_errors == 0,
            "Q1 is always the lower-momentum sleeve and Q5 the higher-momentum sleeve.",
            f"Sector-month loser/winner ordering errors: {loser_top_errors}.",
        )

        sector_weight_errors = 0
        neutral_weight_errors = 0
        for (_, _, _), group in actual.groupby(
            [
                "analysis_month_number",
                "gics_sector",
                "sector_momentum_quintile",
            ],
            sort=False,
        ):
            if not close(group["sector_equal_weight"].sum(), 1.0):
                sector_weight_errors += 1
            if not close(
                group["sector_neutral_leg_weight"].sum(),
                1.0 / 11.0,
            ):
                neutral_weight_errors += 1

        check(
            sector_weight_errors == 0,
            "Every sector/quintile sleeve is exactly equal-weighted to 1.",
            f"Sector sleeve weight-sum errors: {sector_weight_errors}.",
        )
        check(
            neutral_weight_errors == 0,
            (
                "Every sector/quintile sleeve contributes exactly 1/11 "
                "to the sector-neutral aggregate leg."
            ),
            (
                "Sector-neutral leg weight-sum errors: "
                f"{neutral_weight_errors}."
            ),
        )

        lines += section("4. LOOK-AHEAD / METHODOLOGY CONTROL")

        dependency_count = scalar(
            cursor,
            """
            SELECT COUNT_BIG(*)
            FROM sys.sql_expression_dependencies AS d
            JOIN sys.views AS v
              ON v.object_id = d.referencing_id
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            WHERE s.name = 'analytics'
              AND v.name IN
              (
                  'v_security_monthly_sector_momentum_ranking',
                  'v_security_monthly_sector_momentum_portfolio',
                  'v_sector_momentum_quintile_monthly_summary'
              )
              AND (
                    LOWER(COALESCE(OBJECT_NAME(d.referenced_id), ''))
                        LIKE '%forward%'
                 OR LOWER(COALESCE(OBJECT_NAME(d.referenced_id), ''))
                        LIKE '%performance%'
              );
            """,
        )

        check(
            dependency_count == 0,
            (
                "H2 ranking layer has no dependency on forward-return "
                "or performance objects."
            ),
            f"Forward/performance dependencies detected: {dependency_count}.",
        )

        view_text = fetch_df(
            cursor,
            """
            SELECT
                v.name,
                m.definition
            FROM sys.views AS v
            JOIN sys.schemas AS s
              ON s.schema_id = v.schema_id
            JOIN sys.sql_modules AS m
              ON m.object_id = v.object_id
            WHERE s.name = 'analytics'
              AND v.name IN
              (
                  'v_security_monthly_sector_momentum_ranking',
                  'v_security_monthly_sector_momentum_portfolio',
                  'v_sector_momentum_quintile_monthly_summary'
              );
            """,
        )

        forbidden = (
            "v_security_monthly_forward_return_1m",
            "v_momentum_decile_forward_return_1m",
            "v_momentum_long_short_forward_return_1m",
            "risk_free",
            "sharpe",
            "capm",
            "transaction_cost",
            "net_of_cost",
        )

        definition_hits = []
        for row in view_text.itertuples(index=False):
            definition = str(row.definition).lower()
            if any(term in definition for term in forbidden):
                definition_hits.append(str(row.name))

        check(
            not definition_hits,
            (
                "SQL view definitions contain only ranking/weighting logic "
                "permitted before H2 performance construction."
            ),
            (
                "Forbidden methodology terms found in: "
                + ", ".join(definition_hits)
            ),
        )

        for table, expected_count in CORE_COUNTS.items():
            actual_count = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )
            check(
                actual_count == expected_count,
                f"core.{table} final population remains {expected_count:,}.",
                (
                    f"core.{table} changed: {actual_count:,} "
                    f"vs {expected_count:,}."
                ),
            )

        lines += section("5. FINAL QUALITY GATE")

        if failures:
            lines += [
                "AZURE_SQL_H2_SECTOR_MOMENTUM_RANKING_INTEGRITY_AUDIT_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]
            for number, failure in enumerate(failures, start=1):
                lines.append(f"{number}. {failure}")
        else:
            lines += [
                "AZURE_SQL_H2_SECTOR_MOMENTUM_RANKING_INTEGRITY_AUDIT_PASSED",
                f"Passed checks: {passed}",
                f"Validated GICS rows: {EXPECTED_GICS_ROWS:,}",
                f"Eligible H2 ranking rows: {EXPECTED_RANKING_ROWS:,}",
                f"Ranking months: {EXPECTED_MONTHS}",
                f"Month/sector partitions: {EXPECTED_SECTOR_MONTHS}",
                f"Month/sector/quintile rows: {EXPECTED_SUMMARY_ROWS:,}",
                "Forward-return / H2 performance results inspected: 0",
                "Azure SQL modifications performed by audit: 0",
                "Core rows modified: 0",
                (
                    "H2 ranking/weighting quality gate complete. "
                    "The next permitted step is construction of the "
                    "one-month forward-return sector sleeves."
                ),
            ]

    except Exception as error:
        lines += [
            "",
            "AUDIT EXECUTION FAILED",
            type(error).__name__,
            str(error),
            "AZURE_SQL_H2_SECTOR_MOMENTUM_RANKING_INTEGRITY_AUDIT_FAILED",
        ]

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

        REPORT_PATH.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(lines))
        print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
