from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FILE_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "source"
    / "constituents"
    / "holdings-daily-us-en-spy.xlsx"
)


print("Reading file:")
print(FILE_PATH)

excel_file = pd.ExcelFile(FILE_PATH)

print("\nSheet names:")
print(excel_file.sheet_names)

for sheet in excel_file.sheet_names:
    print(f"\n--- Sheet: {sheet} ---")

    preview = pd.read_excel(
        FILE_PATH,
        sheet_name=sheet,
        header=None,
        nrows=20
    )

    print(preview.to_string())