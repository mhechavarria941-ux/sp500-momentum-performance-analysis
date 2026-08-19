from contextlib import redirect_stdout
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INTERVAL_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "sp500_membership_intervals_2021_2025.csv"
)

TICKER_HISTORY_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "sp500_ticker_history_2021_2025.csv"
)

CHECKPOINT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "membership_count_checkpoints.csv"
)

ALIAS_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "securities"
    / "security_aliases.csv"
)

BUILDER_FILE = (
    PROJECT_ROOT
    / "src"
    / "ingestion"
    / "build_membership_intervals.py"
)

REPORT_FILE = (
    PROJECT_ROOT
    / "reports"
    / "data_quality"
    / "membership_interval_inspection.txt"
)


def section(title):
    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


def inspect_frame(
    label,
    file_path,
):
    section(label)

    print(f"Path: {file_path}")
    print(f"Exists: {file_path.exists()}")

    if not file_path.exists():
        return None

    data = pd.read_csv(
        file_path
    )

    print(f"Rows: {len(data)}")
    print(f"Columns: {len(data.columns)}")

    print(
        "Exact duplicate rows: "
        f"{int(data.duplicated().sum())}"
    )

    print("\nColumn names:")

    for number, column in enumerate(
        data.columns,
        start=1,
    ):
        print(
            f"{number:>2}. {column}"
        )

    print("\nData types:")

    print(
        data.dtypes.to_string()
    )

    print("\nNull counts:")

    print(
        data.isna()
        .sum()
        .to_string()
    )

    print("\nUnique counts:")

    print(
        data.nunique(
            dropna=True
        )
        .to_string()
    )

    print("\nFirst ten rows:")

    print(
        data.head(10).to_string(
            index=False
        )
    )

    print("\nLast ten rows:")

    print(
        data.tail(10).to_string(
            index=False
        )
    )

    return data


def inspect_dates(
    data,
    label,
):
    if data is None:
        return

    section(
        f"{label} — DATE COLUMN AUDIT"
    )

    date_columns = [
        column
        for column in data.columns
        if any(
            term in column.lower()
            for term in [
                "date",
                "valid_from",
                "valid_to",
                "effective",
                "start",
                "end",
            ]
        )
    ]

    if not date_columns:
        print(
            "No date-like columns detected."
        )
        return

    for column in date_columns:
        parsed = pd.to_datetime(
            data[column],
            errors="coerce",
        )

        source_non_null = int(
            data[column]
            .notna()
            .sum()
        )

        parsed_non_null = int(
            parsed.notna().sum()
        )

        print(f"\nColumn: {column}")

        print(
            f"Source non-null: "
            f"{source_non_null}"
        )

        print(
            f"Parsed non-null: "
            f"{parsed_non_null}"
        )

        print(
            "Invalid non-null dates: "
            f"{source_non_null - parsed_non_null}"
        )

        valid = parsed.dropna()

        if not valid.empty:
            print(
                f"Minimum: "
                f"{valid.min().date()}"
            )

            print(
                f"Maximum: "
                f"{valid.max().date()}"
            )


def inspect_low_cardinality(
    data,
    label,
):
    if data is None:
        return

    section(
        f"{label} — LOW-CARDINALITY VALUES"
    )

    found = False

    for column in data.columns:
        unique_count = int(
            data[column]
            .nunique(
                dropna=True
            )
        )

        if unique_count <= 12:
            found = True

            print(
                f"\nColumn: {column}"
            )

            print(
                data[column]
                .value_counts(
                    dropna=False
                )
                .to_string()
            )

    if not found:
        print(
            "No columns with 12 or fewer "
            "unique values."
        )


def inspect_candidate_keys(
    data,
    label,
):
    if data is None:
        return

    section(
        f"{label} — CANDIDATE KEY TESTS"
    )

    candidates = [
        ["security_key"],
        ["security_id"],
        ["ticker"],
        ["project_ticker"],
        [
            "security_key",
            "valid_from",
        ],
        [
            "security_id",
            "valid_from",
        ],
        [
            "security_key",
            "ticker",
            "valid_from",
        ],
        [
            "security_id",
            "ticker",
            "valid_from",
        ],
        ["checkpoint_date"],
        ["date"],
    ]

    tested = False

    for columns in candidates:
        if all(
            column in data.columns
            for column in columns
        ):
            tested = True

            duplicates = int(
                data.duplicated(
                    columns
                ).sum()
            )

            print(
                f"{columns}: "
                f"duplicate rows = {duplicates}"
            )

    if not tested:
        print(
            "No predefined candidate-key "
            "combination matched the schema."
        )


def inspect_builder():
    section(
        "MEMBERSHIP BUILDER — "
        "RELEVANT SOURCE LINES"
    )

    print(f"Path: {BUILDER_FILE}")
    print(
        f"Exists: {BUILDER_FILE.exists()}"
    )

    if not BUILDER_FILE.exists():
        return

    keywords = [
        "security_key",
        "security_id",
        "valid_from",
        "valid_to",
        "left_censored",
        "right_censored",
        "ticker_history",
        "membership_intervals",
        "checkpoint",
        "alias",
        "effective_date",
        "to_csv",
    ]

    source = BUILDER_FILE.read_text(
        encoding="utf-8"
    )

    lines = source.splitlines()
    selected = set()

    for index, line in enumerate(lines):
        if any(
            keyword.lower()
            in line.lower()
            for keyword in keywords
        ):
            for nearby in range(
                max(
                    0,
                    index - 2,
                ),
                min(
                    len(lines),
                    index + 3,
                ),
            ):
                selected.add(
                    nearby
                )

    previous = None

    for index in sorted(selected):
        if (
            previous is not None
            and index > previous + 1
        ):
            print(
                "     ..."
            )

        rendered_line = (
            f"{index + 1:>4}: "
            f"{lines[index]}"
        ).rstrip()

        print(rendered_line)

        previous = index

    print(
        "\nRelevant lines with context: "
        f"{len(selected)}"
    )


def run_inspection():
    section(
        "MEMBERSHIP INTERVAL "
        "OUTPUT INSPECTION"
    )

    intervals = inspect_frame(
        "POINT-IN-TIME MEMBERSHIP INTERVALS",
        INTERVAL_FILE,
    )

    ticker_history = inspect_frame(
        "SECURITY TICKER HISTORY",
        TICKER_HISTORY_FILE,
    )

    checkpoints = inspect_frame(
        "MEMBERSHIP COUNT CHECKPOINTS",
        CHECKPOINT_FILE,
    )

    aliases = inspect_frame(
        "SECURITY ALIAS REFERENCE",
        ALIAS_FILE,
    )

    inspect_dates(
        intervals,
        "MEMBERSHIP INTERVALS",
    )

    inspect_dates(
        ticker_history,
        "TICKER HISTORY",
    )

    inspect_dates(
        checkpoints,
        "COUNT CHECKPOINTS",
    )

    inspect_dates(
        aliases,
        "SECURITY ALIASES",
    )

    inspect_low_cardinality(
        intervals,
        "MEMBERSHIP INTERVALS",
    )

    inspect_low_cardinality(
        ticker_history,
        "TICKER HISTORY",
    )

    inspect_low_cardinality(
        checkpoints,
        "COUNT CHECKPOINTS",
    )

    inspect_low_cardinality(
        aliases,
        "SECURITY ALIASES",
    )

    inspect_candidate_keys(
        intervals,
        "MEMBERSHIP INTERVALS",
    )

    inspect_candidate_keys(
        ticker_history,
        "TICKER HISTORY",
    )

    inspect_candidate_keys(
        checkpoints,
        "COUNT CHECKPOINTS",
    )

    inspect_candidate_keys(
        aliases,
        "SECURITY ALIASES",
    )

    inspect_builder()

    section(
        "INSPECTION COMPLETE"
    )

    print(
        "No project source or generated "
        "data files were modified."
    )


def main():
    REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with REPORT_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as report:

        with redirect_stdout(
            report
        ):
            run_inspection()

    print(
        "MEMBERSHIP INTERVAL "
        "INSPECTION PASSED"
    )

    print(
        f"Saved report: {REPORT_FILE}"
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print(
            "MEMBERSHIP INTERVAL "
            "INSPECTION FAILED"
        )

        print(error)

        sys.exit(2)