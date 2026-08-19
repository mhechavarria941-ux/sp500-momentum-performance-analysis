from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from mssql_python import connect


ROOT = Path(__file__).resolve().parents[2]

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "azure_sql_load_input_inspection.txt"
)


SOURCE_FILES = {
    "MEMBERSHIP INTERVALS": (
        ROOT
        / "data"
        / "interim"
        / "sp500_membership_intervals_2021_2025.csv",
        593,
    ),
    "TICKER HISTORY": (
        ROOT
        / "data"
        / "interim"
        / "sp500_ticker_history_2021_2025.csv",
        594,
    ),
    "MEMBERSHIP-PRICE BRIDGE": (
        ROOT
        / "data"
        / "interim"
        / "sp500_membership_price_bridge_2021_2025.csv.gz",
        631_942,
    ),
    "BRIDGE MANIFEST": (
        ROOT
        / "data"
        / "interim"
        / "sp500_membership_price_bridge_manifest.csv",
        594,
    ),
    "BENCHMARK HISTORY": (
        ROOT
        / "data"
        / "interim"
        / "sp500_benchmark_price_history_2021_2025.csv.gz",
        2_510,
    ),
}


CORE_LOAD_TABLES = [
    "security",
    "security_ticker_history",
    "index_membership",
    "security_price_eligibility",
    "daily_security_price",
    "benchmark_series",
    "daily_benchmark_price",
]


STAGING_TABLES = [
    "security",
    "security_ticker_history",
    "index_membership",
    "security_price_eligibility",
    "daily_security_price",
    "benchmark_series",
    "daily_benchmark_price",
]


EXPECTED_MEMBERSHIP_COLUMNS = [
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


EXPECTED_TICKER_COLUMNS = [
    "security_key",
    "ticker",
    "ticker_valid_from",
    "left_censored",
    "ticker_valid_to_exclusive",
    "right_censored",
]


def section(title: str) -> list[str]:

    rule = "=" * 79

    return [
        rule,
        title,
        rule,
    ]


def require_environment() -> tuple[
    str,
    str,
    str,
    str,
]:

    load_dotenv(ROOT / ".env")

    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )

    values = tuple(
        os.getenv(name)
        for name in names
    )

    missing = [
        name
        for name, value in zip(
            names,
            values,
        )
        if not value
    ]

    if missing:

        raise RuntimeError(
            "Missing required environment "
            "variable(s): "
            + ", ".join(missing)
        )

    return values  # type: ignore[return-value]


def inspect_source(
    label: str,
    path: Path,
    expected_rows: int,
    lines: list[str],
) -> pd.DataFrame:

    lines.extend(section(label))

    lines.append(f"Path: {path}")
    lines.append(f"Exists: {path.exists()}")

    if not path.exists():

        raise FileNotFoundError(
            f"Required source file not found: {path}"
        )

    frame = pd.read_csv(
        path,
        low_memory=False,
    )

    lines.append(
        f"Rows: {len(frame):,}"
    )

    lines.append(
        f"Expected rows: {expected_rows:,}"
    )

    lines.append(
        f"Columns: {len(frame.columns)}"
    )

    lines.append(
        "Exact duplicate rows: "
        f"{int(frame.duplicated().sum()):,}"
    )

    if len(frame) != expected_rows:

        raise RuntimeError(
            f"{label} row count does not match "
            f"the validated anchor."
        )

    lines.append(
        "PASS: Row count matches the "
        "validated project anchor."
    )

    lines.append("")

    lines.append("Column names:")

    for number, column in enumerate(
        frame.columns,
        start=1,
    ):

        lines.append(
            f"{number:>2}. {column}"
        )

    lines.append("")

    lines.append("Data types:")

    for column in frame.columns:

        lines.append(
            f"{column}: {frame[column].dtype}"
        )

    lines.append("")

    lines.append("Null counts:")

    for column in frame.columns:

        lines.append(
            f"{column}: "
            f"{int(frame[column].isna().sum()):,}"
        )

    object_columns = [
        column
        for column in frame.columns
        if frame[column].dtype == "object"
    ]

    if object_columns:

        lines.append("")
        lines.append(
            "Maximum populated string lengths:"
        )

        for column in object_columns:

            populated = (
                frame[column]
                .dropna()
                .astype(str)
            )

            maximum = (
                int(populated.str.len().max())
                if not populated.empty
                else 0
            )

            lines.append(
                f"{column}: {maximum}"
            )

    lines.append("")

    return frame


def table_count(
    cursor,
    schema_name: str,
    table_name: str,
) -> int:

    cursor.execute(
        "SELECT COUNT_BIG(*) "
        f"FROM {schema_name}.{table_name};"
    )

    return int(
        cursor.fetchone()[0]
    )


def main() -> None:

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines: list[str] = []

    connection = None

    passed = False

    try:

        lines.extend(
            section(
                "AZURE SQL LOAD-INPUT INSPECTION"
            )
        )

        lines.append(
            "Inspection mode: READ-ONLY"
        )

        lines.append(
            "Credentials included in report: NO"
        )

        lines.append("")

        inspected_frames: dict[
            str,
            pd.DataFrame,
        ] = {}

        for label, (
            path,
            expected_rows,
        ) in SOURCE_FILES.items():

            inspected_frames[label] = (
                inspect_source(
                    label,
                    path,
                    expected_rows,
                    lines,
                )
            )

        membership_columns = list(
            inspected_frames[
                "MEMBERSHIP INTERVALS"
            ].columns
        )

        ticker_columns = list(
            inspected_frames[
                "TICKER HISTORY"
            ].columns
        )

        lines.extend(
            section(
                "SOURCE-SCHEMA CONTROLS"
            )
        )

        if (
            membership_columns
            != EXPECTED_MEMBERSHIP_COLUMNS
        ):

            raise RuntimeError(
                "Membership interval columns "
                "do not match the validated schema."
            )

        lines.append(
            "PASS: Membership interval columns "
            "match the validated schema."
        )

        if (
            ticker_columns
            != EXPECTED_TICKER_COLUMNS
        ):

            raise RuntimeError(
                "Ticker-history columns do not "
                "match the validated schema."
            )

        lines.append(
            "PASS: Ticker-history columns "
            "match the validated schema."
        )

        lines.append("")

        (
            server,
            database,
            username,
            password,
        ) = require_environment()

        connection = connect(
            server=server,
            database=database,
            uid=username,
            pwd=password,
            encrypt="yes",
            trust_server_certificate="no",
            timeout=90,
        )

        cursor = connection.cursor()

        lines.extend(
            section(
                "MSSQL-PYTHON LOAD CAPABILITY"
            )
        )

        package_version = (
            importlib.metadata.version(
                "mssql-python"
            )
        )

        lines.append(
            f"mssql-python version: "
            f"{package_version}"
        )

        bulkcopy_available = callable(
            getattr(
                cursor,
                "bulkcopy",
                None,
            )
        )

        lines.append(
            "cursor.bulkcopy available: "
            f"{bulkcopy_available}"
        )

        if not bulkcopy_available:

            raise RuntimeError(
                "The installed mssql-python "
                "version does not expose "
                "cursor.bulkcopy."
            )

        lines.append(
            "PASS: Controlled bulk-copy "
            "loading is available."
        )

        lines.append("")

        lines.extend(
            section(
                "DATABASE TARGET STATE"
            )
        )

        cursor.execute(
            """
            SELECT COUNT_BIG(*)
            FROM core.market_index
            WHERE
                index_code = 'SP500'
                AND analysis_start =
                    '2021-01-01'
                AND analysis_end =
                    '2025-12-31';
            """
        )

        anchor_count = int(
            cursor.fetchone()[0]
        )

        lines.append(
            "SP500 analytical anchors: "
            f"{anchor_count}"
        )

        if anchor_count != 1:

            raise RuntimeError(
                "Expected exactly one SP500 "
                "analytical anchor."
            )

        nonempty_targets: list[str] = []

        for table_name in CORE_LOAD_TABLES:

            count = table_count(
                cursor,
                "core",
                table_name,
            )

            lines.append(
                f"core.{table_name}: "
                f"{count:,} rows"
            )

            if count != 0:

                nonempty_targets.append(
                    f"core.{table_name}"
                )

        for table_name in STAGING_TABLES:

            count = table_count(
                cursor,
                "staging",
                table_name,
            )

            lines.append(
                f"staging.{table_name}: "
                f"{count:,} rows"
            )

            if count != 0:

                nonempty_targets.append(
                    f"staging.{table_name}"
                )

        if nonempty_targets:

            raise RuntimeError(
                "Load targets expected to be "
                "empty contain rows: "
                + ", ".join(nonempty_targets)
            )

        lines.append("")

        lines.append(
            "PASS: All controlled-load "
            "targets are empty."
        )

        cursor.close()

        lines.append("")

        lines.extend(
            section(
                "FINAL QUALITY GATE"
            )
        )

        lines.append(
            "AZURE_SQL_LOAD_INPUT_"
            "INSPECTION_PASSED"
        )

        lines.append(
            "Source datasets inspected: 5"
        )

        lines.append(
            "Validated constituent observations: "
            "631,942"
        )

        lines.append(
            "Validated benchmark observations: "
            "2,510"
        )

        lines.append(
            "Database modifications performed: 0"
        )

        lines.append(
            "Source-to-staging mapping can now "
            "be defined from observed columns."
        )

        passed = True

    except Exception as error:

        lines.append("")

        lines.extend(
            section(
                "INSPECTION FAILED"
            )
        )

        lines.append(
            type(error).__name__
        )

        lines.append(
            str(error)
        )

        lines.append(
            "AZURE_SQL_LOAD_INPUT_"
            "INSPECTION_FAILED"
        )

    finally:

        if connection is not None:

            try:

                connection.close()

            except Exception:

                pass

        report = "\n".join(lines) + "\n"

        REPORT_PATH.write_text(
            report,
            encoding="utf-8",
        )

        print(
            report,
            end="",
        )

        print(
            "Report saved: "
            f"{REPORT_PATH}"
        )

    if not passed:

        raise SystemExit(1)


if __name__ == "__main__":

    main()