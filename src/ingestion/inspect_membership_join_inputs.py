from pathlib import Path
import sys

import pandas as pd


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

STANDARDIZED_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "standardized_price_history.csv.gz"
)

STANDARDIZED_MANIFEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "standardized_price_history_manifest.csv"
)

MEMBERSHIP_BUILDER = (
    PROJECT_ROOT
    / "src"
    / "ingestion"
    / "build_sp500_membership.py"
)


def section(title):
    print("\n" + "=" * 79)
    print(title)
    print("=" * 79)


def inspect_csv(
    label,
    file_path,
    expected_max_rows=None,
):
    section(label)

    print(f"Path: {file_path}")
    print(f"Exists: {file_path.exists()}")

    if not file_path.exists():
        return None

    if expected_max_rows is None:
        data = pd.read_csv(
            file_path,
            nrows=10,
        )

        print(
            "Inspection mode: first 10 rows only"
        )

    else:
        data = pd.read_csv(
            file_path
        )

        if len(data) > expected_max_rows:
            raise RuntimeError(
                f"{label} unexpectedly contains "
                f"{len(data)} rows."
            )

        print(f"Rows: {len(data)}")

    print(f"Columns: {len(data.columns)}")

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

    print("\nFirst five rows:")
    print(
        data.head(5).to_string(
            index=False
        )
    )

    if expected_max_rows is not None:
        print("\nLast five rows:")
        print(
            data.tail(5).to_string(
                index=False
            )
        )

    return data


def inspect_candidate_columns(
    data,
    label,
):
    if data is None:
        return

    section(
        f"{label} — CANDIDATE KEY/DATE COLUMNS"
    )

    keywords = [
        "ticker",
        "symbol",
        "security",
        "action",
        "event",
        "effective",
        "start",
        "end",
        "date",
        "added",
        "removed",
    ]

    candidates = [
        column
        for column in data.columns
        if any(
            keyword in column.lower()
            for keyword in keywords
        )
    ]

    if not candidates:
        print(
            "No candidate key/date columns detected."
        )
        return

    for column in candidates:
        print(
            f"\nCOLUMN: {column}"
        )

        print(
            f"Non-null: "
            f"{int(data[column].notna().sum())}"
        )

        print(
            f"Unique: "
            f"{int(data[column].nunique(dropna=True))}"
        )

        print(
            "Sample values:"
        )

        print(
            data[column]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .head(12)
            .to_string(index=False)
        )

        if (
            "date" in column.lower()
            or "effective" in column.lower()
            or "start" in column.lower()
            or "end" in column.lower()
        ):
            parsed = pd.to_datetime(
                data[column],
                errors="coerce",
            )

            valid = parsed.dropna()

            if not valid.empty:
                print(
                    f"Parsed minimum: "
                    f"{valid.min().date()}"
                )

                print(
                    f"Parsed maximum: "
                    f"{valid.max().date()}"
                )


def inspect_membership_files():
    section(
        "MEMBERSHIP-RELATED FILE INVENTORY"
    )

    search_roots = [
        (
            PROJECT_ROOT
            / "data"
            / "reference"
            / "membership"
        ),
        (
            PROJECT_ROOT
            / "data"
            / "interim"
        ),
    ]

    found = []

    for root in search_roots:
        if not root.exists():
            continue

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            name = file_path.name.lower()

            if any(
                term in name
                for term in [
                    "member",
                    "constituent",
                    "holding",
                    "official_changes",
                ]
            ):
                found.append(file_path)

    if not found:
        print(
            "No membership-related files found."
        )
        return

    for file_path in sorted(set(found)):
        print(
            file_path.relative_to(
                PROJECT_ROOT
            )
        )


def inspect_builder():
    section(
        "MEMBERSHIP BUILDER RELEVANT LINES"
    )

    print(f"Path: {MEMBERSHIP_BUILDER}")
    print(f"Exists: {MEMBERSHIP_BUILDER.exists()}")

    if not MEMBERSHIP_BUILDER.exists():
        return

    keywords = [
        "OUTPUT",
        "COLUMN",
        "effective",
        "membership",
        "constituent",
        "action",
        "ticker",
        "security_key",
        "to_csv",
    ]

    source = MEMBERSHIP_BUILDER.read_text(
        encoding="utf-8"
    )

    matched = 0

    for line_number, line in enumerate(
        source.splitlines(),
        start=1,
    ):
        if any(
            keyword.lower() in line.lower()
            for keyword in keywords
        ):
            print(
                f"{line_number:>4}: {line}"
            )

            matched += 1

    print(
        f"\nRelevant source lines: {matched}"
    )


def main():
    inspect_membership_files()

    anchor = inspect_csv(
        "CURRENT SPY CONSTITUENT ANCHOR",
        ANCHOR_FILE,
        expected_max_rows=600,
    )

    changes = inspect_csv(
        "OFFICIAL MEMBERSHIP CHANGES",
        CHANGES_FILE,
        expected_max_rows=1_000,
    )

    manifest = inspect_csv(
        "STANDARDIZED PRICE MANIFEST",
        STANDARDIZED_MANIFEST_FILE,
        expected_max_rows=596,
    )

    inspect_csv(
        "STANDARDIZED PRICE HISTORY HEADER",
        STANDARDIZED_FILE,
    )

    inspect_candidate_columns(
        anchor,
        "ANCHOR",
    )

    inspect_candidate_columns(
        changes,
        "OFFICIAL CHANGES",
    )

    inspect_candidate_columns(
        manifest,
        "PRICE MANIFEST",
    )

    inspect_builder()

    section(
        "INSPECTION COMPLETE"
    )

    print(
        "No source or generated files were modified."
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print(
            "\nMEMBERSHIP INPUT INSPECTION FAILED"
        )

        print(error)

        sys.exit(2)