from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import numpy as np
import pyodbc
from dotenv import load_dotenv


SCRIPT_VERSION = "2026-08-28-v1-apply-bi-semantic-model"
ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = ROOT / "sql" / "analytics" / "014_bi_semantic_model.sql"
REPORT_PATH = ROOT / "reports" / "data_quality" / "bi_semantic_model_audit.txt"

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


def environment() -> tuple[str, str, str, str]:
    load_dotenv(ROOT / ".env")
    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )
    vals = tuple(os.getenv(n) for n in names)
    missing = [n for n, v in zip(names, vals) if not v]
    if missing:
        raise RuntimeError(
            "Missing Azure SQL environment variables: " + ", ".join(missing)
        )
    return vals  # type: ignore[return-value]


def esc(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def connect(server: str, database: str, username: str, password: str):
    cs = (
        f"DRIVER={{{ODBC_DRIVER}}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={esc(database)};"
        f"UID={esc(username)};"
        f"PWD={esc(password)};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    for attempt in range(1, 6):
        try:
            c = pyodbc.connect(cs, timeout=30, autocommit=False)
            c.timeout = 180
            print(f"ODBC connection established on attempt {attempt} / 5.")
            return c
        except pyodbc.Error:
            if attempt == 5:
                raise
            time.sleep(15)
    raise RuntimeError("Connection retry loop ended unexpectedly.")


def batches(text: str) -> list[str]:
    return [
        x.strip()
        for x in re.split(
            r"^\s*GO\s*(?:--.*)?$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if x.strip()
    ]


def scalar(cur, sql: str):
    cur.execute(sql)
    row = cur.fetchone()
    return None if row is None else row[0]


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("POWER BI SQL SEMANTIC MODEL")
    print("=" * 124)

    if not SQL_PATH.exists():
        raise RuntimeError(f"Missing SQL file: {SQL_PATH}")

    server, database, username, password = environment()
    conn = connect(server, database, username, password)
    cur = conn.cursor()
    run_id = None
    failures: list[str] = []

    try:
        authorized = int(
            scalar(
                cur,
                """
                SELECT COUNT_BIG(*)
                FROM audit.pipeline_run
                WHERE pipeline_name = 'Research data binding'
                  AND status = 'PASSED';
                """,
            )
            or 0
        )
        if authorized < 1:
            raise RuntimeError(
                "No passed Research data binding run found. "
                "Power BI semantic model is not authorized."
            )

        for i, batch in enumerate(
            batches(SQL_PATH.read_text(encoding="utf-8")),
            start=1,
        ):
            cur.execute(batch)
            while cur.nextset():
                pass
            print(f"Applied SQL batch {i}.")
        conn.commit()

        cur.execute(
            """
            INSERT INTO audit.pipeline_run
            (pipeline_name,script_version,git_commit,started_at_utc,status,notes)
            OUTPUT INSERTED.run_id
            VALUES
            ('Power BI semantic model',?,?,SYSUTCDATETIME(),'STARTED',
             'Creates curated bi dimensions/facts for Power BI.');
            """,
            (SCRIPT_VERSION, git_commit()),
        )
        run_id = int(cur.fetchone()[0])
        conn.commit()

        required_views = [
            "dim_hypothesis",
            "dim_variable",
            "bridge_hypothesis_variable",
            "dim_date",
            "fact_results",
            "fact_result_breakdown",
            "fact_h1_monthly",
            "fact_h1_summary",
            "fact_h1_primary_monthly",
            "fact_h2_monthly",
            "fact_h3_panel",
            "dim_h4_session",
            "fact_h4_events",
            "fact_h4_yearly",
            "fact_data_quality",
            "fact_exclusions",
            "fact_artifacts",
        ]

        cur.execute(
            """
            SELECT o.name
            FROM sys.views AS o
            JOIN sys.schemas AS s
              ON s.schema_id = o.schema_id
            WHERE s.name = 'bi';
            """
        )
        present = {str(r[0]) for r in cur.fetchall()}
        missing = sorted(set(required_views) - present)
        if missing:
            failures.append(f"Missing bi views: {missing}")

        counts = {
            "dim_hypothesis": int(scalar(cur, "SELECT COUNT_BIG(*) FROM bi.dim_hypothesis;")),
            "dim_variable": int(scalar(cur, "SELECT COUNT_BIG(*) FROM bi.dim_variable;")),
            "dim_date": int(scalar(cur, "SELECT COUNT_BIG(*) FROM bi.dim_date;")),
            "fact_results": int(scalar(cur, "SELECT COUNT_BIG(*) FROM bi.fact_results;")),
            "fact_h2_monthly": int(scalar(cur, "SELECT COUNT_BIG(*) FROM bi.fact_h2_monthly;")),
            "fact_h3_panel": int(scalar(cur, "SELECT COUNT_BIG(*) FROM bi.fact_h3_panel;")),
            "fact_h4_events": int(scalar(cur, "SELECT COUNT_BIG(*) FROM bi.fact_h4_events;")),
        }

        expectations = {
            "dim_hypothesis": (7, None),
            "dim_variable": (22, None),
            "dim_date": (1200, None),
            "fact_results": (8, None),
            "fact_h2_monthly": (59, 59),
            "fact_h3_panel": (29287, 29287),
            "fact_h4_events": (164, 164),
        }

        for name, (minimum, exact) in expectations.items():
            observed = counts[name]
            ok = observed == exact if exact is not None else observed >= minimum
            if not ok:
                failures.append(
                    f"{name}: observed {observed}; "
                    + (f"expected {exact}" if exact is not None else f"expected >= {minimum}")
                )

        duplicate_results = int(
            scalar(
                cur,
                """
                SELECT COUNT_BIG(*)
                FROM
                (
                    SELECT result_id
                    FROM bi.fact_results
                    GROUP BY result_id
                    HAVING COUNT_BIG(*) > 1
                ) AS d;
                """,
            )
        )
        if duplicate_results != 0:
            failures.append(
                f"bi.fact_results duplicate result_id groups={duplicate_results}"
            )

        h4_primary_rows = int(
            scalar(
                cur,
                """
                SELECT COUNT_BIG(*)
                FROM bi.fact_results
                WHERE hypothesis_id = 'H4A'
                  AND primary_secondary = 'PRIMARY';
                """,
            )
        )
        if h4_primary_rows != 1:
            failures.append(
                f"H4A primary result rows={h4_primary_rows}; expected 1"
            )

        h4_events = int(
            scalar(
                cur,
                """
                SELECT COUNT_BIG(*)
                FROM bi.fact_h4_events
                WHERE liquidity_sweep_trigger = 1
                  AND horizon_30m_clock_eligible = 1;
                """,
            )
        )
        h4_sessions = int(
            scalar(
                cur,
                """
                SELECT COUNT(DISTINCT session_date)
                FROM bi.fact_h4_events
                WHERE liquidity_sweep_trigger = 1
                  AND horizon_30m_clock_eligible = 1;
                """,
            )
        )
        h4_mean = float(
            scalar(
                cur,
                """
                SELECT AVG(signed_forward_return_30m)
                FROM bi.fact_h4_events
                WHERE liquidity_sweep_trigger = 1
                  AND horizon_30m_clock_eligible = 1;
                """,
            )
        )

        if h4_events != 164:
            failures.append(f"H4 BI events={h4_events}; expected 164")
        if h4_sessions != 156:
            failures.append(f"H4 BI sessions={h4_sessions}; expected 156")
        if not np.isclose(
            h4_mean,
            -0.000613142249862,
            atol=1e-14,
            rtol=1e-12,
        ):
            failures.append(
                f"H4 BI mean={h4_mean:.15g}; expected -0.000613142249862"
            )

        checks = [
            ("BI hypothesis rows", ">=7", str(counts["dim_hypothesis"]), counts["dim_hypothesis"] >= 7),
            ("BI variable rows", ">=22", str(counts["dim_variable"]), counts["dim_variable"] >= 22),
            ("BI H2 monthly rows", "59", str(counts["fact_h2_monthly"]), counts["fact_h2_monthly"] == 59),
            ("BI H3 panel rows", "29287", str(counts["fact_h3_panel"]), counts["fact_h3_panel"] == 29287),
            ("BI H4 events", "164", str(h4_events), h4_events == 164),
            ("BI H4 sessions", "156", str(h4_sessions), h4_sessions == 156),
            (
                "BI H4 mean signed 30m",
                "-0.000613142249862",
                f"{h4_mean:.15g}",
                np.isclose(
                    h4_mean,
                    -0.000613142249862,
                    atol=1e-14,
                    rtol=1e-12,
                ),
            ),
        ]

        for check_name, expected, observed, passed in checks:
            cur.execute(
                """
                INSERT INTO audit.quality_check
                (run_id,check_name,expected_value,observed_value,passed)
                VALUES (?,?,?,?,?);
                """,
                (run_id, check_name, expected, observed, int(bool(passed))),
            )

        cur.execute(
            """
            UPDATE audit.pipeline_run
            SET completed_at_utc = SYSUTCDATETIME(),
                status = ?,
                notes = ?
            WHERE run_id = ?;
            """,
            (
                "PASSED" if not failures else "FAILED",
                "Power BI semantic model validation complete."
                if not failures
                else "Power BI semantic model validation failed.",
                run_id,
            ),
        )

        if failures:
            conn.rollback()
        else:
            conn.commit()

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
            "=" * 124,
            "POWER BI SQL SEMANTIC MODEL",
            "=" * 124,
            f"Database: {database}",
            f"bi.dim_hypothesis rows: {counts['dim_hypothesis']:,}",
            f"bi.dim_variable rows: {counts['dim_variable']:,}",
            f"bi.dim_date rows: {counts['dim_date']:,}",
            f"bi.fact_results rows: {counts['fact_results']:,}",
            f"bi.fact_h2_monthly rows: {counts['fact_h2_monthly']:,}",
            f"bi.fact_h3_panel rows: {counts['fact_h3_panel']:,}",
            f"bi.fact_h4_events rows: {counts['fact_h4_events']:,}",
            f"H4 primary sessions: {h4_sessions:,}",
            f"H4 mean signed 30m return: {h4_mean:.12g}",
            "",
            f"FINAL POWER BI SQL SEMANTIC MODEL GATE: {'PASS' if not failures else 'FAIL'}",
        ]
        if failures:
            lines += ["", "FAILURES:"] + [f"- {x}" for x in failures]
        else:
            lines += [
                "",
                "POWER_BI_SQL_SEMANTIC_MODEL_PASSED",
                "POWER_BI_DESKTOP_MODELING_AUTHORIZED",
            ]

        REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print()
        print(REPORT_PATH.read_text(encoding="utf-8"))

        if failures:
            raise RuntimeError("Power BI semantic model gate failed.")

    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    main()
