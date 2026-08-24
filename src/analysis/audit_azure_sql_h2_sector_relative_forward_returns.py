from __future__ import annotations

import math
import os
import time
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_h2_sector_forward_return_integrity_audit.txt"
)

SCRIPT_VERSION = (
    "2026-08-24-v2-h2-sector-forward-return-null-aware-audit"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"
TOL = 1e-11

CORE_COUNTS = {
    "security": 593,
    "security_ticker_history": 594,
    "index_membership": 593,
    "security_price_eligibility": 594,
    "daily_security_price": 631_942,
    "benchmark_series": 2,
    "daily_benchmark_price": 2_510,
}

EXPECTED_ASSIGNMENTS = 30_121
EXPECTED_COMPLETE_SECURITY = 29_620
EXPECTED_RIGHT_CENSORED_SECURITY = 501
EXPECTED_SECTOR_QUINTILE = 3_300
EXPECTED_COMPLETE_SECTOR_QUINTILE = 3_245
EXPECTED_EXTREME = 1_320
EXPECTED_COMPLETE_EXTREME = 1_298
EXPECTED_LEGS = 120
EXPECTED_COMPLETE_LEGS = 118
EXPECTED_WML = 60
EXPECTED_COMPLETE_WML = 59


def section(title: str) -> list[str]:
    rule = "=" * 92
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


def close(a, b, tol: float = TOL) -> bool:
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


def exact_equal(a, b) -> bool:
    """
    Null-aware exact comparison.

    Pandas/NumPy treats NaT != NaT and NaN != NaN. For this audit,
    matching nulls in the independent source reconstruction and SQL view
    are equal because both represent the same right-censored absence.
    """
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return a == b


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = section(
        "AZURE SQL H2 SECTOR FORWARD-RETURN INTEGRITY AUDIT"
    )
    lines += [
        "Mode: Azure SQL READ-ONLY",
        "Azure SQL modifications performed: 0",
        "Statistical / risk / cost interpretation: NOT PERFORMED",
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
        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        cursor = connection.cursor()

        lines += section("1. SOURCE / CORE PRESERVATION")

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

        portfolio = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_start_date,
                month_end_date,
                security_key,
                project_ticker,
                gics_sector,
                sector_momentum_quintile,
                sector_momentum_portfolio,
                sector_quintile_security_count,
                sector_equal_weight,
                sector_neutral_leg_weight
            FROM analytics.v_security_monthly_sector_momentum_portfolio;
            """,
        )

        source_forward = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                security_key,
                target_holding_end_date,
                holding_end_status,
                holding_end_is_exact_month_end,
                holding_end_is_early_exit,
                holding_end_is_immediate_exit,
                forward_return_1m,
                forward_return_1m_complete,
                out_of_scope_right_censored
            FROM analytics.v_security_monthly_forward_return_1m;
            """,
        )

        check(
            len(portfolio) == EXPECTED_ASSIGNMENTS,
            "H2 portfolio source contains exactly 30,121 assignments.",
            f"H2 portfolio source rows: {len(portfolio):,}.",
        )
        check(
            len(source_forward) == EXPECTED_ASSIGNMENTS,
            "Security forward source contains exactly 30,121 rows.",
            f"Security forward source rows: {len(source_forward):,}.",
        )

        lines += section("2. INDEPENDENT SECURITY-LEVEL JOIN")

        expected_security = portfolio.merge(
            source_forward,
            on=[
                "analysis_month_number",
                "security_key",
            ],
            how="inner",
            validate="one_to_one",
        )

        check(
            len(expected_security) == EXPECTED_ASSIGNMENTS,
            (
                "Independent H2 portfolio/forward join preserves "
                "all 30,121 assignments."
            ),
            (
                "Independent H2 portfolio/forward join rows: "
                f"{len(expected_security):,}."
            ),
        )

        actual_security = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_start_date,
                ranking_month_end_date,
                security_key,
                project_ticker,
                gics_sector,
                sector_momentum_quintile,
                sector_momentum_portfolio,
                sector_quintile_security_count,
                sector_equal_weight,
                sector_neutral_leg_weight,
                target_holding_end_date,
                holding_end_status,
                holding_end_is_exact_month_end,
                holding_end_is_early_exit,
                holding_end_is_immediate_exit,
                forward_return_1m,
                forward_return_1m_complete,
                out_of_scope_right_censored
            FROM analytics.v_h2_security_monthly_forward_return_1m;
            """,
        )

        expected_security = expected_security.rename(
            columns={
                "month_start_date": "ranking_month_start_date",
                "month_end_date": "ranking_month_end_date",
            }
        )

        date_columns = (
            "ranking_month_start_date",
            "ranking_month_end_date",
            "target_holding_end_date",
        )

        for frame in (
            expected_security,
            actual_security,
        ):
            for column in date_columns:
                frame[column] = pd.to_datetime(
                    frame[column],
                    errors="coerce",
                )

            for column in (
                "analysis_month_number",
                "sector_momentum_quintile",
                "sector_quintile_security_count",
                "forward_return_1m_complete",
                "out_of_scope_right_censored",
                "holding_end_is_exact_month_end",
                "holding_end_is_early_exit",
                "holding_end_is_immediate_exit",
            ):
                frame[column] = pd.to_numeric(
                    frame[column],
                    errors="raise",
                ).astype(int)

            for column in (
                "sector_equal_weight",
                "sector_neutral_leg_weight",
                "forward_return_1m",
            ):
                frame[column] = pd.to_numeric(
                    frame[column],
                    errors="coerce",
                )

            for column in (
                "security_key",
                "project_ticker",
                "gics_sector",
                "sector_momentum_portfolio",
                "holding_end_status",
            ):
                frame[column] = (
                    frame[column]
                    .astype(str)
                    .str.strip()
                )

        order = [
            "analysis_month_number",
            "security_key",
        ]

        expected_security = expected_security.sort_values(
            order,
            kind="mergesort",
        ).reset_index(drop=True)

        actual_security = actual_security.sort_values(
            order,
            kind="mergesort",
        ).reset_index(drop=True)

        exact_columns = (
            "analysis_month_number",
            "ranking_month_start_date",
            "ranking_month_end_date",
            "security_key",
            "project_ticker",
            "gics_sector",
            "sector_momentum_quintile",
            "sector_momentum_portfolio",
            "sector_quintile_security_count",
            "target_holding_end_date",
            "holding_end_status",
            "holding_end_is_exact_month_end",
            "holding_end_is_early_exit",
            "holding_end_is_immediate_exit",
            "forward_return_1m_complete",
            "out_of_scope_right_censored",
        )

        exact_mismatch = 0
        weight_mismatch = 0
        return_mismatch = 0
        exact_field_mismatch_counts = {
            column: 0
            for column in exact_columns
        }

        for i in range(len(actual_security)):
            a = actual_security.iloc[i]
            e = expected_security.iloc[i]

            row_exact_mismatch = False

            for column in exact_columns:
                if not exact_equal(
                    a[column],
                    e[column],
                ):
                    exact_field_mismatch_counts[column] += 1
                    row_exact_mismatch = True

            exact_mismatch += int(row_exact_mismatch)

            if not (
                close(
                    a["sector_equal_weight"],
                    e["sector_equal_weight"],
                )
                and close(
                    a["sector_neutral_leg_weight"],
                    e["sector_neutral_leg_weight"],
                )
            ):
                weight_mismatch += 1

            if not close(
                a["forward_return_1m"],
                e["forward_return_1m"],
            ):
                return_mismatch += 1

        nonzero_exact_field_mismatches = {
            column: count
            for column, count in exact_field_mismatch_counts.items()
            if count
        }

        lines.append(
            "Security exact-field mismatch detail: "
            + (
                "none"
                if not nonzero_exact_field_mismatches
                else " | ".join(
                    f"{column}={count:,}"
                    for column, count
                    in nonzero_exact_field_mismatches.items()
                )
            )
        )

        check(
            exact_mismatch == 0,
            (
                "Every H2 security holding key/date/status field matches "
                "the independent source join using null-aware equality."
            ),
            f"Security exact-field mismatches: {exact_mismatch}.",
        )
        check(
            weight_mismatch == 0,
            "Every H2 security target weight matches the fixed ranking source.",
            f"Security target-weight mismatches: {weight_mismatch}.",
        )
        check(
            return_mismatch == 0,
            (
                "Every H2 security forward return exactly matches the "
                "validated security forward-return source."
            ),
            f"Security forward-return mismatches: {return_mismatch}.",
        )

        check(
            int(
                (
                    actual_security[
                        "forward_return_1m_complete"
                    ] == 1
                ).sum()
            )
            == EXPECTED_COMPLETE_SECURITY,
            "H2 security layer has exactly 29,620 complete returns.",
            "Unexpected complete H2 security-return population.",
        )

        check(
            int(
                (
                    actual_security[
                        "out_of_scope_right_censored"
                    ] == 1
                ).sum()
            )
            == EXPECTED_RIGHT_CENSORED_SECURITY,
            "H2 security layer has exactly 501 right-censored rows.",
            "Unexpected H2 right-censored security population.",
        )

        censored_security = actual_security[
            actual_security[
                "out_of_scope_right_censored"
            ] == 1
        ]

        check(
            int(
                censored_security[
                    "target_holding_end_date"
                ].isna().sum()
            )
            == EXPECTED_RIGHT_CENSORED_SECURITY,
            (
                "All 501 right-censored December-2025 rows have null "
                "target_holding_end_date as expected."
            ),
            (
                "Right-censored rows do not have the expected null "
                "target_holding_end_date state."
            ),
        )

        lines += section("3. INDEPENDENT SECTOR-QUINTILE RECONSTRUCTION")

        sector_rows = []

        group_columns = [
            "analysis_month_number",
            "gics_sector",
            "sector_momentum_quintile",
        ]

        for keys, group in expected_security.groupby(
            group_columns,
            sort=True,
        ):
            month, sector, quintile = keys
            complete = bool(
                (
                    group["forward_return_1m_complete"] == 1
                ).all()
            )
            censored = bool(
                (
                    group["out_of_scope_right_censored"] == 1
                ).all()
            )

            value = None
            if complete:
                value = float(
                    (
                        group["sector_equal_weight"]
                        * group["forward_return_1m"]
                    ).sum()
                )

            sector_rows.append(
                {
                    "analysis_month_number": int(month),
                    "gics_sector": str(sector),
                    "sector_momentum_quintile": int(quintile),
                    "sector_momentum_portfolio": (
                        "LOSER"
                        if int(quintile) == 1
                        else (
                            "WINNER"
                            if int(quintile) == 5
                            else "MIDDLE"
                        )
                    ),
                    "security_count": len(group),
                    "complete_security_count": int(
                        (
                            group["forward_return_1m_complete"]
                            == 1
                        ).sum()
                    ),
                    "sector_equal_weight_sum": float(
                        group["sector_equal_weight"].sum()
                    ),
                    "equal_weight_forward_return_1m": value,
                    "forward_return_1m_complete": int(complete),
                    "out_of_scope_right_censored": int(censored),
                }
            )

        expected_sector = pd.DataFrame(sector_rows)

        actual_sector = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                gics_sector,
                sector_momentum_quintile,
                sector_momentum_portfolio,
                security_count,
                complete_security_count,
                sector_equal_weight_sum,
                equal_weight_forward_return_1m,
                forward_return_1m_complete,
                out_of_scope_right_censored
            FROM analytics.v_h2_sector_quintile_forward_return_1m;
            """,
        )

        check(
            len(expected_sector) == EXPECTED_SECTOR_QUINTILE
            and len(actual_sector) == EXPECTED_SECTOR_QUINTILE,
            "Independent and SQL sector/quintile populations are both 3,300 rows.",
            (
                f"Sector/quintile rows expected={len(expected_sector):,}, "
                f"actual={len(actual_sector):,}."
            ),
        )

        sort_cols = group_columns
        expected_sector = expected_sector.sort_values(
            sort_cols,
            kind="mergesort",
        ).reset_index(drop=True)
        actual_sector = actual_sector.sort_values(
            sort_cols,
            kind="mergesort",
        ).reset_index(drop=True)

        sector_exact_mismatch = 0
        sector_numeric_mismatch = 0

        for i in range(len(actual_sector)):
            a = actual_sector.iloc[i]
            e = expected_sector.iloc[i]

            exact_ok = (
                int(a["analysis_month_number"])
                == int(e["analysis_month_number"])
                and str(a["gics_sector"]).strip()
                == str(e["gics_sector"])
                and int(a["sector_momentum_quintile"])
                == int(e["sector_momentum_quintile"])
                and str(
                    a["sector_momentum_portfolio"]
                ).strip()
                == str(e["sector_momentum_portfolio"])
                and int(a["security_count"])
                == int(e["security_count"])
                and int(a["complete_security_count"])
                == int(e["complete_security_count"])
                and int(a["forward_return_1m_complete"])
                == int(e["forward_return_1m_complete"])
                and int(a["out_of_scope_right_censored"])
                == int(e["out_of_scope_right_censored"])
            )

            numeric_ok = (
                close(
                    a["sector_equal_weight_sum"],
                    e["sector_equal_weight_sum"],
                )
                and close(
                    a["equal_weight_forward_return_1m"],
                    e["equal_weight_forward_return_1m"],
                )
            )

            sector_exact_mismatch += int(not exact_ok)
            sector_numeric_mismatch += int(not numeric_ok)

        check(
            sector_exact_mismatch == 0,
            (
                "Every sector/quintile count, label, completeness, and "
                "censoring field matches independent reconstruction."
            ),
            (
                "Sector/quintile exact-field mismatches: "
                f"{sector_exact_mismatch}."
            ),
        )
        check(
            sector_numeric_mismatch == 0,
            (
                "Every sector/quintile equal-weight return matches "
                "independent reconstruction."
            ),
            (
                "Sector/quintile numeric mismatches: "
                f"{sector_numeric_mismatch}."
            ),
        )

        lines += section("4. INDEPENDENT SECTOR-NEUTRAL LEGS / W-L")

        extremes = expected_sector[
            expected_sector["sector_momentum_quintile"].isin(
                [1, 5]
            )
        ].copy()

        expected_legs_rows = []

        for (
            month,
            label,
        ), group in extremes.groupby(
            [
                "analysis_month_number",
                "sector_momentum_portfolio",
            ],
            sort=True,
        ):
            complete = (
                len(group) == 11
                and bool(
                    (
                        group["forward_return_1m_complete"]
                        == 1
                    ).all()
                )
            )
            censored = (
                len(group) == 11
                and bool(
                    (
                        group["out_of_scope_right_censored"]
                        == 1
                    ).all()
                )
            )
            value = None
            if complete:
                value = float(
                    group[
                        "equal_weight_forward_return_1m"
                    ].mean()
                )

            expected_legs_rows.append(
                {
                    "analysis_month_number": int(month),
                    "sector_momentum_portfolio": str(label),
                    "sector_count": len(group),
                    "complete_sector_count": int(
                        (
                            group["forward_return_1m_complete"]
                            == 1
                        ).sum()
                    ),
                    "sector_neutral_forward_return_1m": value,
                    "forward_return_1m_complete": int(complete),
                    "out_of_scope_right_censored": int(censored),
                }
            )

        expected_legs = pd.DataFrame(
            expected_legs_rows
        )

        actual_legs = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                sector_momentum_portfolio,
                sector_count,
                complete_sector_count,
                sector_neutral_forward_return_1m,
                forward_return_1m_complete,
                out_of_scope_right_censored
            FROM analytics.v_h2_sector_neutral_leg_forward_return_1m;
            """,
        )

        check(
            len(expected_legs) == EXPECTED_LEGS
            and len(actual_legs) == EXPECTED_LEGS,
            "Independent and SQL sector-neutral leg populations are 120 rows.",
            (
                f"Sector-neutral leg rows expected={len(expected_legs)}, "
                f"actual={len(actual_legs)}."
            ),
        )

        leg_order = [
            "analysis_month_number",
            "sector_momentum_portfolio",
        ]

        expected_legs = expected_legs.sort_values(
            leg_order
        ).reset_index(drop=True)
        actual_legs = actual_legs.sort_values(
            leg_order
        ).reset_index(drop=True)

        leg_mismatch = 0

        for i in range(len(actual_legs)):
            a = actual_legs.iloc[i]
            e = expected_legs.iloc[i]

            ok = (
                int(a["analysis_month_number"])
                == int(e["analysis_month_number"])
                and str(
                    a["sector_momentum_portfolio"]
                ).strip()
                == str(e["sector_momentum_portfolio"])
                and int(a["sector_count"])
                == int(e["sector_count"])
                and int(a["complete_sector_count"])
                == int(e["complete_sector_count"])
                and int(a["forward_return_1m_complete"])
                == int(e["forward_return_1m_complete"])
                and int(a["out_of_scope_right_censored"])
                == int(e["out_of_scope_right_censored"])
                and close(
                    a["sector_neutral_forward_return_1m"],
                    e["sector_neutral_forward_return_1m"],
                )
            )

            leg_mismatch += int(not ok)

        check(
            leg_mismatch == 0,
            (
                "Every sector-neutral Winner/Loser leg matches "
                "independent 11-sector equal-weight reconstruction."
            ),
            f"Sector-neutral leg mismatches: {leg_mismatch}.",
        )

        winner = expected_legs[
            expected_legs[
                "sector_momentum_portfolio"
            ] == "WINNER"
        ].set_index("analysis_month_number")

        loser = expected_legs[
            expected_legs[
                "sector_momentum_portfolio"
            ] == "LOSER"
        ].set_index("analysis_month_number")

        expected_wml_rows = []

        for month in range(1, 61):
            w = winner.loc[month]
            l = loser.loc[month]
            complete = (
                int(w["forward_return_1m_complete"]) == 1
                and int(l["forward_return_1m_complete"]) == 1
            )
            censored = (
                int(w["out_of_scope_right_censored"]) == 1
                and int(l["out_of_scope_right_censored"]) == 1
            )

            value = None
            if complete:
                value = (
                    float(
                        w[
                            "sector_neutral_forward_return_1m"
                        ]
                    )
                    -
                    float(
                        l[
                            "sector_neutral_forward_return_1m"
                        ]
                    )
                )

            expected_wml_rows.append(
                {
                    "analysis_month_number": month,
                    "winner_sector_count": int(w["sector_count"]),
                    "loser_sector_count": int(l["sector_count"]),
                    "winner_forward_return_1m": (
                        w[
                            "sector_neutral_forward_return_1m"
                        ]
                    ),
                    "loser_forward_return_1m": (
                        l[
                            "sector_neutral_forward_return_1m"
                        ]
                    ),
                    "winner_minus_loser_forward_return_1m": value,
                    "forward_return_1m_complete": int(complete),
                    "out_of_scope_right_censored": int(censored),
                }
            )

        expected_wml = pd.DataFrame(
            expected_wml_rows
        )

        actual_wml = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                winner_sector_count,
                loser_sector_count,
                winner_forward_return_1m,
                loser_forward_return_1m,
                winner_minus_loser_forward_return_1m,
                forward_return_1m_complete,
                out_of_scope_right_censored
            FROM analytics.v_h2_sector_neutral_wml_forward_return_1m
            ORDER BY analysis_month_number;
            """,
        )

        check(
            len(actual_wml) == EXPECTED_WML,
            "SQL H2 W-L layer contains exactly 60 rows.",
            f"SQL H2 W-L rows: {len(actual_wml)}.",
        )

        wml_mismatch = 0

        for i in range(len(actual_wml)):
            a = actual_wml.iloc[i]
            e = expected_wml.iloc[i]

            ok = (
                int(a["analysis_month_number"])
                == int(e["analysis_month_number"])
                and int(a["winner_sector_count"])
                == int(e["winner_sector_count"])
                and int(a["loser_sector_count"])
                == int(e["loser_sector_count"])
                and int(a["forward_return_1m_complete"])
                == int(e["forward_return_1m_complete"])
                and int(a["out_of_scope_right_censored"])
                == int(e["out_of_scope_right_censored"])
                and close(
                    a["winner_forward_return_1m"],
                    e["winner_forward_return_1m"],
                )
                and close(
                    a["loser_forward_return_1m"],
                    e["loser_forward_return_1m"],
                )
                and close(
                    a["winner_minus_loser_forward_return_1m"],
                    e["winner_minus_loser_forward_return_1m"],
                )
            )

            wml_mismatch += int(not ok)

        check(
            wml_mismatch == 0,
            (
                "Every aggregate sector-neutral W-L observation matches "
                "independent reconstruction."
            ),
            f"Aggregate H2 W-L mismatches: {wml_mismatch}.",
        )

        lines += section("5. COMPLETENESS / NO-INTERPRETATION CONTROL")

        check(
            int(
                (
                    actual_sector[
                        "forward_return_1m_complete"
                    ] == 1
                ).sum()
            )
            == EXPECTED_COMPLETE_SECTOR_QUINTILE,
            (
                "Exactly 3,245 sector/quintile returns are complete "
                "across months 1-59."
            ),
            "Unexpected complete sector/quintile population.",
        )

        check(
            int(
                (
                    actual_legs[
                        "forward_return_1m_complete"
                    ] == 1
                ).sum()
            )
            == EXPECTED_COMPLETE_LEGS,
            "Exactly 118 aggregate Winner/Loser legs are complete.",
            "Unexpected complete aggregate-leg population.",
        )

        check(
            int(
                (
                    actual_wml[
                        "forward_return_1m_complete"
                    ] == 1
                ).sum()
            )
            == EXPECTED_COMPLETE_WML,
            "Exactly 59 aggregate H2 W-L observations are complete.",
            "Unexpected complete H2 W-L population.",
        )

        censored_months = actual_wml.loc[
            actual_wml[
                "out_of_scope_right_censored"
            ] == 1,
            "analysis_month_number",
        ].astype(int).tolist()

        check(
            censored_months == [60],
            "Only analysis month 60 is right-censored in aggregate H2 W-L.",
            (
                "Unexpected H2 W-L censored months: "
                + ", ".join(map(str, censored_months))
            ),
        )

        for table, expected in CORE_COUNTS.items():
            actual = scalar(
                cursor,
                f"SELECT COUNT_BIG(*) FROM core.{table};",
            )
            check(
                actual == expected,
                f"core.{table} final population remains {expected:,}.",
                (
                    f"core.{table} changed: {actual:,} "
                    f"vs {expected:,}."
                ),
            )

        lines += section("6. FINAL QUALITY GATE")

        if failures:
            lines += [
                "AZURE_SQL_H2_SECTOR_FORWARD_RETURN_INTEGRITY_AUDIT_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]
            for number, failure in enumerate(
                failures,
                start=1,
            ):
                lines.append(
                    f"{number}. {failure}"
                )
        else:
            lines += [
                "AZURE_SQL_H2_SECTOR_FORWARD_RETURN_INTEGRITY_AUDIT_PASSED",
                f"Passed checks: {passed}",
                f"H2 security holding rows: {EXPECTED_ASSIGNMENTS:,}",
                f"Complete H2 security returns: {EXPECTED_COMPLETE_SECURITY:,}",
                f"Sector/quintile rows: {EXPECTED_SECTOR_QUINTILE:,}",
                f"Winner/Loser sector rows: {EXPECTED_EXTREME:,}",
                f"Sector-neutral leg rows: {EXPECTED_LEGS}",
                f"Aggregate W-L rows: {EXPECTED_WML}",
                f"Complete observable W-L months: {EXPECTED_COMPLETE_WML}",
                "Statistical / risk / cost interpretation performed: 0",
                "Azure SQL modifications performed by audit: 0",
                "Core rows modified: 0",
                (
                    "H2 forward-return population is independently validated. "
                    "The next permitted step is the preregistered statistical, "
                    "risk, turnover, and implementation-cost analysis."
                ),
            ]

    except Exception as error:
        lines += [
            "",
            "AUDIT EXECUTION FAILED",
            type(error).__name__,
            str(error),
            "AZURE_SQL_H2_SECTOR_FORWARD_RETURN_INTEGRITY_AUDIT_FAILED",
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
