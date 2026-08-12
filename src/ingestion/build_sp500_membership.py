from pathlib import Path

import pandas as pd


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "source"
    / "constituents"
    / "holdings-daily-us-en-spy.xlsx"
)


# --------------------------------------------------
# Load SPY holdings
# --------------------------------------------------

holdings = pd.read_excel(
    SOURCE_FILE,
    sheet_name="holdings",
    header=4
)


# --------------------------------------------------
# Initial inspection
# --------------------------------------------------

print("Dataset shape:")
print(holdings.shape)

print("\nColumns:")
print(holdings.columns.tolist())

print("\nFirst 10 rows:")
print(holdings.head(10).to_string())

print("\nLast 20 rows:")
print(holdings.tail(20).to_string())

print("\nMissing ticker values:")
print(holdings["Ticker"].isna().sum())

print("\nUnique currencies:")
print(holdings["Local Currency"].value_counts(dropna=False))

# --------------------------------------------------
# Candidate holding rows
# --------------------------------------------------

candidates = holdings[
    holdings["Ticker"].notna()
].copy()

print("\nCandidate rows with a ticker:")
print(candidates.shape)

print("\nLast 20 candidate holdings:")
print(candidates.tail(20).to_string(index=False))

print("\nDuplicate tickers:")
duplicates = candidates[
    candidates["Ticker"].duplicated(keep=False)
].sort_values("Ticker")

print(duplicates.to_string(index=False))

print("\nRows with missing or non-numeric weight:")

candidates["Weight_numeric"] = pd.to_numeric(
    candidates["Weight"],
    errors="coerce"
)

suspicious_weight = candidates[
    candidates["Weight_numeric"].isna()
]

print(suspicious_weight.to_string(index=False))

# --------------------------------------------------
# Investigate possible non-index positions
# --------------------------------------------------

candidates["Ticker"] = candidates["Ticker"].astype(str).str.strip()
candidates["Name"] = candidates["Name"].astype(str).str.strip()

# Normal S&P 500 equity tickers generally consist of letters,
# with an optional class suffix such as BRK.B or BF.B.
ticker_pattern = r"^[A-Z]{1,5}(?:\.[A-Z])?$"

nonstandard_tickers = candidates[
    ~candidates["Ticker"].str.match(ticker_pattern, na=False)
]

print("\nNon-standard ticker formats:")
print(nonstandard_tickers.to_string(index=False))


# Search for fund-specific or corporate-action positions
keywords = (
    r"CASH|DOLLAR|CURRENCY|CONTRA|CVR|RIGHT|"
    r"FUTURE|SWAP|RECEIVABLE|PAYABLE|COLLATERAL"
)

special_positions = candidates[
    candidates["Name"].str.contains(
        keywords,
        case=False,
        regex=True,
        na=False
    )
    |
    candidates["Ticker"].str.contains(
        r"USD|CASH",
        case=False,
        regex=True,
        na=False
    )
]

print("\nPotential fund-specific positions:")
print(special_positions.to_string(index=False))


# Inspect unusual identifiers
identifier_lengths = (
    candidates["Identifier"]
    .astype(str)
    .str.strip()
    .str.len()
)

unusual_identifiers = candidates[
    identifier_lengths != 9
]

print("\nRows with unusual identifier length:")
print(unusual_identifiers.to_string(index=False))

# --------------------------------------------------
# Create benchmark constituent anchor
# --------------------------------------------------

ticker_pattern = r"^[A-Z]{1,5}(?:\.[A-Z])?$"

sp500_anchor = candidates[
    candidates["Ticker"].str.match(ticker_pattern, na=False)
].copy()

print("\nClean S&P 500 constituent anchor:")
print(sp500_anchor.shape)

print("\nFirst 10 constituents:")
print(sp500_anchor.head(10).to_string(index=False))

print("\nLast 10 constituents:")
print(sp500_anchor.tail(10).to_string(index=False))

print("\nTotal constituent securities:")
print(len(sp500_anchor))

print("\nTotal portfolio weight represented:")
print(sp500_anchor["Weight_numeric"].sum())

# --------------------------------------------------
# Save interim anchor
# --------------------------------------------------

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
INTERIM_DIR.mkdir(parents=True, exist_ok=True)

ANCHOR_DATE = "2026-08-10"

sp500_anchor["anchor_date"] = ANCHOR_DATE
sp500_anchor["source"] = "State Street SPDR S&P 500 ETF Trust (SPY)"

output_path = (
    INTERIM_DIR
    / f"sp500_constituent_anchor_{ANCHOR_DATE}.csv"
)

sp500_anchor.to_csv(output_path, index=False)

print("\nAnchor dataset saved:")
print(output_path)