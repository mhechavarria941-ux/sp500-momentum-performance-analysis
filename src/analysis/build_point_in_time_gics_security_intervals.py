from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

MEMBERSHIP_PATH = (
    ROOT / "data" / "interim"
    / "sp500_membership_intervals_2021_2025.csv"
)
OFFICIAL_CHANGES_PATH = (
    ROOT / "data" / "reference" / "membership"
    / "sp500_official_changes.csv"
)
ALIASES_PATH = (
    ROOT / "data" / "reference" / "securities"
    / "security_aliases.csv"
)
SEC_HOLDINGS_PATH = (
    ROOT / "data" / "reference" / "gics"
    / "sec_select_sector_canonical_holdings_clean.csv"
)
TRANSITION_LEDGER_PATH = (
    ROOT / "data" / "reference" / "gics"
    / "gics_transition_effective_dates.csv"
)

ANCHOR_PATH = (
    ROOT / "data" / "interim"
    / "sp500_constituent_anchor_2026-08-10.csv"
)
IDENTITY_OVERRIDES_PATH = (
    ROOT / "data" / "reference" / "gics"
    / "gics_security_key_identity_overrides.csv"
)

EVENT_SECTOR_OVERRIDES_PATH = (
    ROOT / "data" / "reference" / "gics"
    / "gics_official_event_sector_overrides.csv"
)

INTERVAL_OUTPUT_PATH = (
    ROOT / "data" / "reference" / "gics"
    / "security_gics_sector_intervals_2021_2025.csv"
)
MONTHLY_OUTPUT_PATH = (
    ROOT / "data" / "interim"
    / "security_gics_sector_month_end_2021_2025.csv"
)
IDENTIFIER_BRIDGE_PATH = (
    ROOT / "data" / "reference" / "gics"
    / "sec_gics_identifier_security_key_bridge.csv"
)

UNMATCHED_SEC_PATH = (
    ROOT / "reports" / "data_quality"
    / "gics_security_key_unmatched_sec_holdings.csv"
)
UNMATCHED_EVENTS_PATH = (
    ROOT / "reports" / "data_quality"
    / "gics_security_key_unmatched_official_events.csv"
)
EVIDENCE_MISMATCH_PATH = (
    ROOT / "reports" / "data_quality"
    / "gics_sector_evidence_mismatches.csv"
)
MONTHLY_COVERAGE_PATH = (
    ROOT / "reports" / "data_quality"
    / "gics_monthly_sector_coverage.csv"
)
REPORT_PATH = (
    ROOT / "reports" / "data_quality"
    / "point_in_time_gics_security_key_monthly_audit.txt"
)

SCRIPT_VERSION = (
    "2026-08-24-v4-final-identity-and-evidence-scope"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

CANONICAL_SECTORS = {
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
}

SECTOR_NORMALIZATION = {
    "Information Technologies": "Information Technology",
    "Information Technology": "Information Technology",
}

EXPECTED_MEMBERSHIP_INTERVALS = 593
EXPECTED_RANKING_MONTHS = 60
EXPECTED_TRANSITIONS = 20
EXPECTED_RANKING_ROWS = 30211


def line() -> str:
    return "=" * 118


def section(title: str) -> list[str]:
    return ["", line(), title, line()]


def normalize_sector(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None

    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.lower() in {
        "nan", "none", "null", "-", "n/a",
    }:
        return None

    return SECTOR_NORMALIZATION.get(text, text)


def ticker_key(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None

    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "NULL", "-"}:
        return None

    # BRK.B and BRK-B should reconcile, while GOOGL/GOOG remain distinct.
    return re.sub(r"[^A-Z0-9]", "", text)


def normalized_company_name(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None

    text = str(value).upper()
    text = text.replace("&", " AND ")

    # Common SEC / issuer presentation artifacts. This remains exact
    # normalized-name matching, not fuzzy matching.
    text = re.sub(r"\bTHE\b", " ", text)
    text = re.sub(r"\bCLASS\s+[A-Z0-9]+\b", " ", text)
    text = re.sub(r"\bCL\s+[A-Z0-9]+\b", " ", text)
    text = re.sub(r"\bORDINARY\s+SHARES?\b", " ", text)
    text = re.sub(r"\bCOMMON\s+STOCK\b", " ", text)

    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    suffixes = (
        " HOLDINGS CORPORATION",
        " HOLDINGS CORP",
        " HOLDING CORPORATION",
        " HOLDING CORP",
        " HOLDINGS PLC",
        " HOLDING PLC",
        " INCORPORATED",
        " CORPORATION",
        " COMPANY",
        " LIMITED",
        " HOLDINGS",
        " HOLDING",
        " CORP",
        " INC",
        " PLC",
        " LTD",
        " CO",
    )

    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
                break

    return text or None


def build_alias_name_evidence(
    aliases: pd.DataFrame,
    ticker_map: dict[str, str],
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    for row in aliases.itertuples(index=False):
        old_ticker_key = ticker_key(row.old_ticker)
        new_ticker_key = ticker_key(row.new_ticker)

        old_security = (
            ticker_map.get(old_ticker_key)
            if old_ticker_key
            else None
        )
        new_security = (
            ticker_map.get(new_ticker_key)
            if new_ticker_key
            else None
        )

        if old_security and new_security and old_security != new_security:
            raise RuntimeError(
                f"Alias conflict {row.old_ticker}->{row.new_ticker}: "
                f"{old_security} vs {new_security}"
            )

        security_key = old_security or new_security
        if security_key is None:
            continue

        for source_name in (
            row.old_company_name,
            row.new_company_name,
        ):
            name_key = normalized_company_name(source_name)
            if name_key:
                rows.append(
                    {
                        "company_name_key": name_key,
                        "security_key": str(security_key),
                    }
                )

    return pd.DataFrame(rows)


def environment() -> tuple[str, str, str, str]:
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
            "Missing Azure SQL environment variables: "
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
    if ODBC_DRIVER not in pyodbc.drivers():
        raise RuntimeError(
            f"{ODBC_DRIVER} is not installed. "
            f"Available: {pyodbc.drivers()}"
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

    for attempt in range(1, 6):
        try:
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            print(
                f"ODBC connection established on "
                f"attempt {attempt} / 5."
            )
            return connection
        except pyodbc.Error:
            if attempt == 5:
                raise

            print(
                f"ODBC connection attempt "
                f"{attempt} / 5 failed. "
                "Retrying in 10 seconds."
            )
            time.sleep(10)

    raise RuntimeError(
        "ODBC retry loop ended unexpectedly."
    )


def fetch_df(cursor, query: str) -> pd.DataFrame:
    cursor.execute(query)
    columns = [
        str(item[0])
        for item in cursor.description
    ]

    return pd.DataFrame.from_records(
        cursor.fetchall(),
        columns=columns,
    )


def build_unique_map(
    frame: pd.DataFrame,
    key_column: str,
    value_column: str,
) -> tuple[
    dict[str, str],
    set[str],
]:
    working = frame[
        [key_column, value_column]
    ].dropna().copy()

    grouped = working.groupby(
        key_column
    )[value_column].nunique()

    ambiguous = set(
        grouped[
            grouped > 1
        ].index.astype(str)
    )

    unique = (
        working[
            ~working[
                key_column
            ].astype(str).isin(
                ambiguous
            )
        ]
        .drop_duplicates(
            key_column
        )
        .set_index(
            key_column
        )[
            value_column
        ]
        .astype(str)
        .to_dict()
    )

    return unique, ambiguous


def previous_business_day(
    date: pd.Timestamp,
) -> pd.Timestamp:
    return (
        date
        - pd.offsets.BDay(1)
    ).normalize()


def map_official_events(
    changes: pd.DataFrame,
    intervals: pd.DataFrame,
    global_ticker_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    interval_add = intervals.copy()
    interval_add[
        "entry_ticker_key"
    ] = interval_add[
        "entry_ticker"
    ].map(ticker_key)

    interval_del = intervals.copy()
    interval_del[
        "exit_ticker_key"
    ] = interval_del[
        "exit_ticker"
    ].map(ticker_key)

    mapped_rows: list[
        dict[str, Any]
    ] = []
    unmatched_rows: list[
        dict[str, Any]
    ] = []

    for row in changes.itertuples(
        index=False
    ):
        action = str(
            row.action
        ).strip().casefold()

        effective_date = pd.Timestamp(
            row.effective_date
        )

        key = ticker_key(
            row.ticker
        )

        sector = normalize_sector(
            row.gics_sector
        )

        security_key = None
        method = None

        if (
            action == "addition"
            and key
        ):
            candidates = interval_add[
                (
                    interval_add[
                        "valid_from"
                    ]
                    == effective_date
                )
                & (
                    interval_add[
                        "entry_ticker_key"
                    ]
                    == key
                )
            ]

            if len(candidates) == 1:
                security_key = str(
                    candidates.iloc[
                        0
                    ][
                        "security_key"
                    ]
                )
                method = (
                    "MEMBERSHIP_ENTRY_BOUNDARY"
                )

        elif (
            action == "deletion"
            and key
        ):
            candidates = interval_del[
                (
                    interval_del[
                        "valid_to_exclusive"
                    ]
                    == effective_date
                )
                & (
                    interval_del[
                        "exit_ticker_key"
                    ]
                    == key
                )
            ]

            if len(candidates) == 1:
                security_key = str(
                    candidates.iloc[
                        0
                    ][
                        "security_key"
                    ]
                )
                method = (
                    "MEMBERSHIP_EXIT_BOUNDARY"
                )

        if (
            security_key is None
            and key
            and key in global_ticker_map
        ):
            security_key = (
                global_ticker_map[
                    key
                ]
            )
            method = (
                "GLOBAL_UNIQUE_TICKER"
            )

        if (
            security_key is None
            or sector
            not in CANONICAL_SECTORS
        ):
            unmatched_rows.append(
                {
                    "effective_date": (
                        effective_date
                    ),
                    "action": row.action,
                    "ticker": row.ticker,
                    "gics_sector": sector,
                    "reason": (
                        "SECURITY_KEY_OR_SECTOR_"
                        "NOT_RESOLVED"
                    ),
                }
            )
            continue

        evidence_date = (
            effective_date
            if action
            == "addition"
            else previous_business_day(
                effective_date
            )
        )

        mapped_rows.append(
            {
                "security_key": (
                    security_key
                ),
                "effective_date": (
                    effective_date
                ),
                "evidence_date": (
                    evidence_date
                ),
                "action": row.action,
                "ticker": row.ticker,
                "gics_sector": sector,
                "mapping_method": (
                    method
                ),
                "evidence_type": (
                    "OFFICIAL_SP500_MEMBERSHIP_EVENT"
                ),
            }
        )

    return (
        pd.DataFrame(
            mapped_rows
        ),
        pd.DataFrame(
            unmatched_rows
        ),
    )


def predicted_sector(
    sector_intervals: pd.DataFrame,
    security_key: str,
    date: pd.Timestamp,
) -> str | None:
    candidates = sector_intervals[
        (
            sector_intervals[
                "security_key"
            ]
            == security_key
        )
        & (
            sector_intervals[
                "sector_valid_from"
            ]
            <= date
        )
        & (
            date
            < sector_intervals[
                "sector_valid_to_exclusive"
            ]
        )
    ]

    if len(candidates) != 1:
        return None

    return str(
        candidates.iloc[
            0
        ][
            "gics_sector"
        ]
    )


def main() -> None:
    print(
        "RUNNING SCRIPT VERSION: "
        f"{SCRIPT_VERSION}"
    )

    required_paths = (
        MEMBERSHIP_PATH,
        OFFICIAL_CHANGES_PATH,
        ALIASES_PATH,
        SEC_HOLDINGS_PATH,
        TRANSITION_LEDGER_PATH,
        ANCHOR_PATH,
        IDENTITY_OVERRIDES_PATH,
        EVENT_SECTOR_OVERRIDES_PATH,
    )

    for path in required_paths:
        if not path.exists():
            raise FileNotFoundError(
                path
            )

    INTERVAL_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    MONTHLY_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "Loading validated local source layers..."
    )

    intervals = pd.read_csv(
        MEMBERSHIP_PATH
    )
    changes = pd.read_csv(
        OFFICIAL_CHANGES_PATH
    )
    aliases = pd.read_csv(
        ALIASES_PATH
    )
    sec_holdings = pd.read_csv(
        SEC_HOLDINGS_PATH,
        dtype={
            "holding_identifier": str,
            "cusip": str,
            "holding_ticker": str,
        },
    )
    transitions = pd.read_csv(
        TRANSITION_LEDGER_PATH,
        dtype={
            "holding_identifier": str,
        },
    )
    anchor = pd.read_csv(
        ANCHOR_PATH,
        dtype={
            "Ticker": str,
            "Name": str,
            "Identifier": str,
        },
    )
    identity_overrides = pd.read_csv(
        IDENTITY_OVERRIDES_PATH,
        dtype={
            "holding_identifier": str,
            "security_key": str,
        },
    )
    event_sector_overrides = pd.read_csv(
        EVENT_SECTOR_OVERRIDES_PATH,
        dtype={
            "ticker": str,
            "original_gics_sector": str,
            "corrected_gics_sector": str,
        },
    )

    intervals[
        "security_key"
    ] = (
        intervals[
            "security_key"
        ]
        .astype(str)
        .str.strip()
    )

    intervals[
        "valid_from"
    ] = pd.to_datetime(
        intervals[
            "valid_from"
        ],
        errors="raise",
    )

    intervals[
        "valid_to_exclusive"
    ] = pd.to_datetime(
        intervals[
            "valid_to_exclusive"
        ],
        errors="raise",
    )

    changes[
        "effective_date"
    ] = pd.to_datetime(
        changes[
            "effective_date"
        ],
        errors="raise",
    )

    # The source change ledger extends beyond the H2 analytical window.
    # Only 2021-2025 membership actions belong in this construction.
    changes = changes[
        (changes["effective_date"] >= pd.Timestamp("2021-01-01"))
        & (changes["effective_date"] < pd.Timestamp("2026-01-01"))
    ].copy()

    # Apply only audited GICS-evidence corrections. Membership action,
    # effective date, ticker, and constituent history remain unchanged.
    event_sector_overrides["effective_date"] = pd.to_datetime(
        event_sector_overrides["effective_date"],
        errors="raise",
    )

    event_sector_corrections_applied = 0

    for override in event_sector_overrides.itertuples(index=False):
        mask = (
            (changes["effective_date"] == pd.Timestamp(override.effective_date))
            & (
                changes["action"].astype(str).str.casefold()
                == str(override.action).casefold()
            )
            & (
                changes["ticker"].map(ticker_key)
                == ticker_key(override.ticker)
            )
        )

        matched = changes.loc[mask]

        if len(matched) != 1:
            raise RuntimeError(
                "Expected exactly one official membership-event row "
                f"for audited sector correction {override.ticker} "
                f"{pd.Timestamp(override.effective_date).date()}, "
                f"found {len(matched)}."
            )

        existing_sector = normalize_sector(
            matched.iloc[0]["gics_sector"]
        )
        expected_original = normalize_sector(
            override.original_gics_sector
        )
        corrected_sector = normalize_sector(
            override.corrected_gics_sector
        )

        if existing_sector != expected_original:
            raise RuntimeError(
                "Audited official-event sector correction no longer "
                f"matches source row for {override.ticker}: "
                f"expected original {expected_original}, "
                f"found {existing_sector}."
            )

        if corrected_sector not in CANONICAL_SECTORS:
            raise RuntimeError(
                f"Invalid corrected GICS sector: {corrected_sector}"
            )

        changes.loc[mask, "gics_sector"] = corrected_sector
        event_sector_corrections_applied += 1

    transitions[
        "new_sector_valid_from"
    ] = pd.to_datetime(
        transitions[
            "new_sector_valid_from"
        ],
        errors="raise",
    )

    transitions[
        "effective_close_date"
    ] = pd.to_datetime(
        transitions[
            "effective_close_date"
        ],
        errors="raise",
    )

    transitions[
        "holding_identifier"
    ] = (
        transitions[
            "holding_identifier"
        ]
        .astype(str)
        .str.strip()
    )

    sec_holdings[
        "report_date"
    ] = pd.to_datetime(
        sec_holdings[
            "report_date"
        ],
        errors="raise",
    )

    sec_holdings[
        "holding_identifier"
    ] = (
        sec_holdings[
            "holding_identifier"
        ]
        .astype(str)
        .str.strip()
    )

    identity_overrides[
        "holding_identifier"
    ] = (
        identity_overrides[
            "holding_identifier"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    identity_overrides[
        "security_key"
    ] = (
        identity_overrides[
            "security_key"
        ]
        .astype(str)
        .str.strip()
    )

    # ---------------------------------------------------------------
    # Read the exact 60 ranking-date universe from Azure.
    # ---------------------------------------------------------------
    server, database, username, password = (
        environment()
    )

    connection = connect_with_retry(
        server,
        database,
        username,
        password,
    )

    try:
        cursor = connection.cursor()

        snapshot = fetch_df(
            cursor,
            """
            SELECT
                analysis_month_number,
                month_end_date,
                security_key,
                project_ticker
            FROM analytics.security_month_end_snapshot
            ORDER BY
                analysis_month_number,
                security_key;
            """,
        )

        cursor.close()

    finally:
        connection.close()

    snapshot[
        "analysis_month_number"
    ] = pd.to_numeric(
        snapshot[
            "analysis_month_number"
        ],
        errors="raise",
    ).astype(int)

    snapshot[
        "month_end_date"
    ] = pd.to_datetime(
        snapshot[
            "month_end_date"
        ],
        errors="raise",
    )

    snapshot[
        "security_key"
    ] = (
        snapshot[
            "security_key"
        ]
        .astype(str)
        .str.strip()
    )

    snapshot[
        "ticker_key"
    ] = snapshot[
        "project_ticker"
    ].map(
        ticker_key
    )

    # ---------------------------------------------------------------
    # Build a conservative permanent ticker -> security_key bridge.
    # ---------------------------------------------------------------
    ticker_evidence_frames: list[
        pd.DataFrame
    ] = [
        snapshot[
            [
                "ticker_key",
                "security_key",
            ]
        ].copy()
    ]

    membership_ticker_rows: list[
        dict[str, str | None]
    ] = []

    for row in intervals.itertuples(
        index=False
    ):
        for ticker in (
            row.entry_ticker,
            row.exit_ticker,
        ):
            membership_ticker_rows.append(
                {
                    "ticker_key": (
                        ticker_key(
                            ticker
                        )
                    ),
                    "security_key": (
                        row.security_key
                    ),
                }
            )

    ticker_evidence_frames.append(
        pd.DataFrame(
            membership_ticker_rows
        )
    )

    ticker_evidence = pd.concat(
        ticker_evidence_frames,
        ignore_index=True,
    ).dropna()

    global_ticker_map, ambiguous_tickers = (
        build_unique_map(
            ticker_evidence,
            "ticker_key",
            "security_key",
        )
    )

    # ---------------------------------------------------------------
    # Identity-only bridge tier 2: current State Street SPY CUSIP.
    # No current sector field is used.
    # ---------------------------------------------------------------
    anchor["ticker_key"] = anchor["Ticker"].map(ticker_key)
    anchor["security_key"] = anchor["ticker_key"].map(global_ticker_map)

    anchor_identity = anchor[
        anchor["security_key"].notna()
        & anchor["Identifier"].notna()
    ].copy()

    anchor_identity["holding_identifier"] = (
        anchor_identity["Identifier"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    anchor_identifier_map, ambiguous_anchor_identifiers = (
        build_unique_map(
            anchor_identity[
                ["holding_identifier", "security_key"]
            ],
            "holding_identifier",
            "security_key",
        )
    )

    # ---------------------------------------------------------------
    # Identity-only bridge tier 3: unique normalized current/alias name.
    # Ambiguous names (e.g. Alphabet/Fox/News dual classes) are excluded.
    # ---------------------------------------------------------------
    anchor_name_evidence = anchor_identity[
        ["Name", "security_key"]
    ].copy()
    anchor_name_evidence["company_name_key"] = (
        anchor_name_evidence["Name"].map(normalized_company_name)
    )
    anchor_name_evidence = anchor_name_evidence[
        ["company_name_key", "security_key"]
    ]

    alias_name_evidence = build_alias_name_evidence(
        aliases,
        global_ticker_map,
    )

    name_evidence = pd.concat(
        [anchor_name_evidence, alias_name_evidence],
        ignore_index=True,
    ).dropna()

    name_map, ambiguous_names = build_unique_map(
        name_evidence,
        "company_name_key",
        "security_key",
    )

    # ---------------------------------------------------------------
    # Identity-only bridge tier 4: six audited residual overrides.
    # These are exact identifier mappings, never fuzzy rules.
    # ---------------------------------------------------------------
    override_identifier_map, ambiguous_override_identifiers = (
        build_unique_map(
            identity_overrides[
                ["holding_identifier", "security_key"]
            ],
            "holding_identifier",
            "security_key",
        )
    )

    if ambiguous_override_identifiers:
        raise RuntimeError(
            "Ambiguous audited identity override(s): "
            + ", ".join(sorted(ambiguous_override_identifiers))
        )

    # ---------------------------------------------------------------
    # Map SEC holdings to security_key.
    #
    # Hierarchy:
    #   1. direct historical ticker identity;
    #   2. current State Street SPY CUSIP identity;
    #   3. unique exact normalized current/alias company name;
    #   4. six explicit audited residual identifier overrides;
    #   5. unique identifier propagation from already-resolved rows.
    # ---------------------------------------------------------------
    sec = sec_holdings.copy()

    sec["holding_identifier"] = (
        sec["holding_identifier"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    sec["holding_ticker_key"] = sec["holding_ticker"].map(ticker_key)
    sec["company_name_key"] = sec["holding_name"].map(
        normalized_company_name
    )

    sec["security_key"] = sec["holding_ticker_key"].map(
        global_ticker_map
    )
    sec["mapping_method"] = None
    sec.loc[
        sec["security_key"].notna(),
        "mapping_method",
    ] = "DIRECT_HISTORICAL_TICKER"

    anchor_fill_mask = (
        sec["security_key"].isna()
        & sec["holding_identifier"].isin(anchor_identifier_map)
    )
    sec.loc[
        anchor_fill_mask,
        "security_key",
    ] = sec.loc[
        anchor_fill_mask,
        "holding_identifier",
    ].map(anchor_identifier_map)
    sec.loc[
        anchor_fill_mask,
        "mapping_method",
    ] = "CURRENT_STATE_STREET_SPY_CUSIP_IDENTITY"

    name_fill_mask = (
        sec["security_key"].isna()
        & sec["company_name_key"].notna()
        & sec["company_name_key"].isin(name_map)
    )
    sec.loc[
        name_fill_mask,
        "security_key",
    ] = sec.loc[
        name_fill_mask,
        "company_name_key",
    ].map(name_map)
    sec.loc[
        name_fill_mask,
        "mapping_method",
    ] = "UNIQUE_CURRENT_OR_ALIAS_COMPANY_NAME"

    override_fill_mask = (
        sec["security_key"].isna()
        & sec["holding_identifier"].isin(override_identifier_map)
    )
    sec.loc[
        override_fill_mask,
        "security_key",
    ] = sec.loc[
        override_fill_mask,
        "holding_identifier",
    ].map(override_identifier_map)
    sec.loc[
        override_fill_mask,
        "mapping_method",
    ] = "AUDITED_RESIDUAL_IDENTITY_OVERRIDE"

    mapped_identifier_rows = sec[
        sec["security_key"].notna()
        & sec["holding_identifier"].notna()
    ][["holding_identifier", "security_key"]].copy()

    identifier_map, ambiguous_identifiers = build_unique_map(
        mapped_identifier_rows,
        "holding_identifier",
        "security_key",
    )

    identifier_fill_mask = (
        sec["security_key"].isna()
        & sec["holding_identifier"].isin(identifier_map)
    )
    sec.loc[
        identifier_fill_mask,
        "security_key",
    ] = sec.loc[
        identifier_fill_mask,
        "holding_identifier",
    ].map(identifier_map)
    sec.loc[
        identifier_fill_mask,
        "mapping_method",
    ] = "UNIQUE_IDENTIFIER_PROPAGATION"

    unmatched_sec = sec[
        sec[
            "security_key"
        ].isna()
    ].copy()

    unmatched_sec.to_csv(
        UNMATCHED_SEC_PATH,
        index=False,
    )

    # Final bridge only includes identifiers that resolve to one key.
    bridge_source = sec[
        sec[
            "security_key"
        ].notna()
        & sec[
            "holding_identifier"
        ].notna()
    ][
        [
            "holding_identifier",
            "security_key",
        ]
    ].copy()

    bridge_counts = (
        bridge_source.groupby(
            "holding_identifier"
        )[
            "security_key"
        ].nunique()
    )

    bridge_valid_ids = set(
        bridge_counts[
            bridge_counts == 1
        ].index.astype(str)
    )

    bridge = (
        bridge_source[
            bridge_source[
                "holding_identifier"
            ].isin(
                bridge_valid_ids
            )
        ]
        .drop_duplicates()
        .sort_values(
            [
                "security_key",
                "holding_identifier",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    bridge.to_csv(
        IDENTIFIER_BRIDGE_PATH,
        index=False,
    )

    final_identifier_map = (
        bridge.set_index(
            "holding_identifier"
        )[
            "security_key"
        ]
        .astype(str)
        .to_dict()
    )

    # ---------------------------------------------------------------
    # Map official S&P membership-action GICS evidence.
    # ---------------------------------------------------------------
    mapped_events, unmatched_events = (
        map_official_events(
            changes,
            intervals,
            global_ticker_map,
        )
    )

    unmatched_events.to_csv(
        UNMATCHED_EVENTS_PATH,
        index=False,
    )

    # ---------------------------------------------------------------
    # Map the 20 authoritative transitions to security_key.
    # ---------------------------------------------------------------
    transitions["security_key"] = (
        transitions["holding_identifier"].map(final_identifier_map)
    )

    transition_anchor_mask = transitions["security_key"].isna()
    transitions.loc[
        transition_anchor_mask,
        "security_key",
    ] = transitions.loc[
        transition_anchor_mask,
        "holding_identifier",
    ].map(anchor_identifier_map)

    transition_override_mask = transitions["security_key"].isna()
    transitions.loc[
        transition_override_mask,
        "security_key",
    ] = transitions.loc[
        transition_override_mask,
        "holding_identifier",
    ].map(override_identifier_map)

    transition_name_mask = transitions["security_key"].isna()
    transition_name_keys = transitions.loc[
        transition_name_mask,
        "company_name",
    ].map(normalized_company_name)
    transitions.loc[
        transition_name_mask,
        "security_key",
    ] = transition_name_keys.map(name_map).values

    transition_unmapped = transitions[
        transitions[
            "security_key"
        ].isna()
    ].copy()

    # ---------------------------------------------------------------
    # Build security-level sector evidence.
    # ---------------------------------------------------------------
    sec_mapped = sec[
        sec[
            "security_key"
        ].notna()
    ].copy()

    sec_evidence = sec_mapped[
        [
            "security_key",
            "report_date",
            "gics_sector",
            "holding_identifier",
            "holding_name",
            "mapping_method",
        ]
    ].rename(
        columns={
            "report_date": "evidence_date",
        }
    )

    sec_evidence[
        "evidence_type"
    ] = (
        "SEC_SELECT_SECTOR_NPORT"
    )

    event_evidence = mapped_events[
        [
            "security_key",
            "evidence_date",
            "gics_sector",
            "ticker",
            "mapping_method",
            "evidence_type",
        ]
    ].copy()

    # ---------------------------------------------------------------
    # Construct exact sector intervals.
    # ---------------------------------------------------------------
    failures: list[str] = []
    sector_interval_rows: list[
        dict[str, Any]
    ] = []

    if len(intervals) != EXPECTED_MEMBERSHIP_INTERVALS:
        failures.append(
            f"Membership interval rows = {len(intervals)}, "
            f"expected {EXPECTED_MEMBERSHIP_INTERVALS}."
        )

    if len(transitions) != EXPECTED_TRANSITIONS:
        failures.append(
            f"Transition rows = {len(transitions)}, "
            f"expected {EXPECTED_TRANSITIONS}."
        )

    if not transition_unmapped.empty:
        failures.append(
            f"{len(transition_unmapped)} transition(s) "
            "could not map to security_key."
        )

    transition_by_security = {
        security_key: group.sort_values(
            "new_sector_valid_from"
        ).copy()
        for security_key, group in (
            transitions[
                transitions[
                    "security_key"
                ].notna()
            ].groupby(
                "security_key"
            )
        )
    }

    sec_evidence_by_security = {
        security_key: group.copy()
        for security_key, group in (
            sec_evidence.groupby(
                "security_key"
            )
        )
    }

    event_evidence_by_security = {
        security_key: group.copy()
        for security_key, group in (
            event_evidence.groupby(
                "security_key"
            )
        )
    }

    unresolved_initial: list[
        dict[str, Any]
    ] = []

    for membership in intervals.itertuples(
        index=False
    ):
        security_key = str(
            membership.security_key
        )

        membership_start = pd.Timestamp(
            membership.valid_from
        )

        membership_end = pd.Timestamp(
            membership.valid_to_exclusive
        )

        security_transitions = (
            transition_by_security.get(
                security_key,
                pd.DataFrame(),
            )
        )

        if not security_transitions.empty:
            first_transition = (
                security_transitions.iloc[
                    0
                ]
            )

            initial_sector = normalize_sector(
                first_transition[
                    "old_sector"
                ]
            )

        else:
            evidence_sectors: list[
                str
            ] = []

            if security_key in sec_evidence_by_security:
                subset = (
                    sec_evidence_by_security[
                        security_key
                    ]
                )

                subset = subset[
                    (
                        subset[
                            "evidence_date"
                        ]
                        >= membership_start
                        - pd.Timedelta(
                            days=1
                        )
                    )
                    & (
                        subset[
                            "evidence_date"
                        ]
                        < membership_end
                    )
                ]

                evidence_sectors.extend(
                    [
                        str(value)
                        for value in subset[
                            "gics_sector"
                        ].dropna()
                    ]
                )

            if security_key in event_evidence_by_security:
                subset = (
                    event_evidence_by_security[
                        security_key
                    ]
                )

                evidence_sectors.extend(
                    [
                        str(value)
                        for value in subset[
                            "gics_sector"
                        ].dropna()
                    ]
                )

            unique_sectors = sorted(
                set(
                    normalize_sector(
                        value
                    )
                    for value in evidence_sectors
                    if normalize_sector(
                        value
                    )
                    in CANONICAL_SECTORS
                )
            )

            if len(unique_sectors) == 1:
                initial_sector = (
                    unique_sectors[
                        0
                    ]
                )
            else:
                initial_sector = None

                unresolved_initial.append(
                    {
                        "security_key": (
                            security_key
                        ),
                        "company_name_reference": (
                            membership.company_name_reference
                        ),
                        "evidence_sectors": (
                            " | ".join(
                                unique_sectors
                            )
                        ),
                        "reason": (
                            "ZERO_OR_MULTIPLE_SECTOR_STATES_"
                            "WITHOUT_EXACT_TRANSITION"
                        ),
                    }
                )

        if initial_sector not in CANONICAL_SECTORS:
            continue

        current_sector = initial_sector
        current_start = membership_start

        if not security_transitions.empty:
            for transition in (
                security_transitions.itertuples(
                    index=False
                )
            ):
                transition_date = pd.Timestamp(
                    transition.new_sector_valid_from
                )

                old_sector = normalize_sector(
                    transition.old_sector
                )

                new_sector = normalize_sector(
                    transition.new_sector
                )

                if not (
                    membership_start
                    < transition_date
                    < membership_end
                ):
                    failures.append(
                        f"Transition for {security_key} "
                        f"at {transition_date.date()} "
                        "falls outside membership interval."
                    )
                    continue

                if old_sector != current_sector:
                    failures.append(
                        f"Transition chain mismatch for "
                        f"{security_key}: expected old sector "
                        f"{current_sector}, ledger says "
                        f"{old_sector}."
                    )
                    continue

                sector_interval_rows.append(
                    {
                        "security_key": (
                            security_key
                        ),
                        "gics_sector": (
                            current_sector
                        ),
                        "sector_valid_from": (
                            current_start
                        ),
                        "sector_valid_to_exclusive": (
                            transition_date
                        ),
                        "source_basis": (
                            "SEC_QUARTERLY_STATE_PLUS_"
                            "AUTHORITATIVE_GICS_TRANSITION"
                        ),
                    }
                )

                current_sector = (
                    new_sector
                )
                current_start = (
                    transition_date
                )

        sector_interval_rows.append(
            {
                "security_key": (
                    security_key
                ),
                "gics_sector": (
                    current_sector
                ),
                "sector_valid_from": (
                    current_start
                ),
                "sector_valid_to_exclusive": (
                    membership_end
                ),
                "source_basis": (
                    "SEC_QUARTERLY_STATE_PLUS_"
                    "OFFICIAL_MEMBERSHIP_GICS"
                ),
            }
        )

    sector_intervals = pd.DataFrame(
        sector_interval_rows
    )

    sector_intervals[
        "sector_valid_from"
    ] = pd.to_datetime(
        sector_intervals[
            "sector_valid_from"
        ],
        errors="raise",
    )

    sector_intervals[
        "sector_valid_to_exclusive"
    ] = pd.to_datetime(
        sector_intervals[
            "sector_valid_to_exclusive"
        ],
        errors="raise",
    )

    sector_intervals = (
        sector_intervals.sort_values(
            [
                "security_key",
                "sector_valid_from",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # ---------------------------------------------------------------
    # Interval structural audit.
    # ---------------------------------------------------------------
    overlap_count = 0
    gap_count = 0

    for security_key, group in (
        sector_intervals.groupby(
            "security_key"
        )
    ):
        ordered = group.sort_values(
            "sector_valid_from"
        )

        previous_end = None

        for row in ordered.itertuples(
            index=False
        ):
            if previous_end is not None:
                if (
                    row.sector_valid_from
                    < previous_end
                ):
                    overlap_count += 1

                if (
                    row.sector_valid_from
                    > previous_end
                ):
                    gap_count += 1

            previous_end = (
                row.sector_valid_to_exclusive
            )

    # ---------------------------------------------------------------
    # Reconcile source evidence against exact intervals.
    #
    # SEC quarter-end observations outside a security's project
    # membership interval are retained as source/support evidence but
    # are not compared to an in-window classification interval.
    # ---------------------------------------------------------------
    membership_bounds = {
        str(row.security_key): (
            pd.Timestamp(row.valid_from),
            pd.Timestamp(row.valid_to_exclusive),
        )
        for row in intervals.itertuples(index=False)
    }

    evidence_mismatch_rows: list[
        dict[str, Any]
    ] = []

    transition_by_identifier = {
        str(row.holding_identifier): row
        for row in transitions.itertuples(
            index=False
        )
    }

    first_new_sec_date_by_identifier: dict[str, pd.Timestamp] = {}

    for transition in transitions.itertuples(index=False):
        identifier = str(transition.holding_identifier)
        new_sector = normalize_sector(transition.new_sector)

        candidate_rows = sec_evidence[
            (sec_evidence["holding_identifier"].astype(str) == identifier)
            & (
                sec_evidence["gics_sector"].map(normalize_sector)
                == new_sector
            )
        ]

        if not candidate_rows.empty:
            first_new_sec_date_by_identifier[identifier] = pd.Timestamp(
                candidate_rows["evidence_date"].min()
            )

    for row in sec_evidence.itertuples(
        index=False
    ):
        security_key = str(
            row.security_key
        )

        date = pd.Timestamp(
            row.evidence_date
        )

        bounds = membership_bounds.get(security_key)

        if bounds is not None:
            membership_start, membership_end = bounds

            if not (
                membership_start <= date < membership_end
            ):
                # Examples include the 2020-12-31 support snapshot and
                # quarter-end ETF observations after a constituent has
                # left the analytical membership interval.
                continue

        observed_sector = (
            normalize_sector(
                row.gics_sector
            )
        )

        expected_sector = (
            predicted_sector(
                sector_intervals,
                security_key,
                date,
            )
        )

        if observed_sector == expected_sector:
            continue

        allowed_exception = None

        transition = (
            transition_by_identifier.get(
                str(
                    row.holding_identifier
                )
            )
        )

        if transition is not None:
            effective_close = pd.Timestamp(
                transition.effective_close_date
            )
            valid_from = pd.Timestamp(
                transition.new_sector_valid_from
            )
            old_sector = normalize_sector(
                transition.old_sector
            )
            new_sector = normalize_sector(
                transition.new_sector
            )

            if (
                date
                == effective_close
                and observed_sector
                == new_sector
            ):
                allowed_exception = (
                    "SAME_CLOSE_ETF_REBALANCE"
                )

            elif (
                date >= valid_from
                and observed_sector == old_sector
                and str(row.holding_identifier)
                in first_new_sec_date_by_identifier
                and date
                < first_new_sec_date_by_identifier[
                    str(row.holding_identifier)
                ]
            ):
                # Official GICS state overrides the ETF only during the
                # bounded implementation-lag window ending when the SEC
                # sector fund first reports the new sector.
                allowed_exception = (
                    "DOCUMENTED_SEC_ETF_LAG"
                )

        if allowed_exception is None:
            evidence_mismatch_rows.append(
                {
                    "security_key": (
                        security_key
                    ),
                    "evidence_date": (
                        date
                    ),
                    "holding_identifier": (
                        row.holding_identifier
                    ),
                    "holding_name": (
                        row.holding_name
                    ),
                    "observed_sector": (
                        observed_sector
                    ),
                    "expected_sector": (
                        expected_sector
                    ),
                    "reason": (
                        "UNEXPLAINED_SEC_EVIDENCE_MISMATCH"
                    ),
                }
            )

    for row in event_evidence.itertuples(
        index=False
    ):
        security_key = str(
            row.security_key
        )

        date = pd.Timestamp(
            row.evidence_date
        )

        observed_sector = (
            normalize_sector(
                row.gics_sector
            )
        )

        expected_sector = (
            predicted_sector(
                sector_intervals,
                security_key,
                date,
            )
        )

        if observed_sector != expected_sector:
            evidence_mismatch_rows.append(
                {
                    "security_key": (
                        security_key
                    ),
                    "evidence_date": (
                        date
                    ),
                    "holding_identifier": (
                        None
                    ),
                    "holding_name": (
                        row.ticker
                    ),
                    "observed_sector": (
                        observed_sector
                    ),
                    "expected_sector": (
                        expected_sector
                    ),
                    "reason": (
                        "OFFICIAL_MEMBERSHIP_EVENT_"
                        "SECTOR_MISMATCH"
                    ),
                }
            )

    evidence_mismatches = pd.DataFrame(
        evidence_mismatch_rows
    )

    evidence_mismatches.to_csv(
        EVIDENCE_MISMATCH_PATH,
        index=False,
    )

    # ---------------------------------------------------------------
    # Expand intervals to the exact 60 ranking-date security snapshot.
    # ---------------------------------------------------------------
    monthly_rows: list[
        dict[str, Any]
    ] = []

    missing_monthly: list[
        dict[str, Any]
    ] = []

    for row in snapshot.itertuples(
        index=False
    ):
        date = pd.Timestamp(
            row.month_end_date
        )

        sector = predicted_sector(
            sector_intervals,
            str(
                row.security_key
            ),
            date,
        )

        if sector is None:
            missing_monthly.append(
                {
                    "analysis_month_number": (
                        row.analysis_month_number
                    ),
                    "month_end_date": (
                        date
                    ),
                    "security_key": (
                        row.security_key
                    ),
                    "project_ticker": (
                        row.project_ticker
                    ),
                }
            )
            continue

        monthly_rows.append(
            {
                "analysis_month_number": (
                    int(
                        row.analysis_month_number
                    )
                ),
                "month_end_date": (
                    date
                ),
                "security_key": (
                    str(
                        row.security_key
                    )
                ),
                "project_ticker": (
                    row.project_ticker
                ),
                "gics_sector": (
                    sector
                ),
            }
        )

    monthly = pd.DataFrame(
        monthly_rows
    )

    monthly_counts = (
        monthly.groupby(
            [
                "analysis_month_number",
                "month_end_date",
            ]
        )
        .agg(
            assigned_rows=(
                "security_key",
                "count",
            ),
            unique_security_keys=(
                "security_key",
                "nunique",
            ),
            sectors_present=(
                "gics_sector",
                "nunique",
            ),
        )
        .reset_index()
    )

    source_month_counts = (
        snapshot.groupby(
            [
                "analysis_month_number",
                "month_end_date",
            ]
        )[
            "security_key"
        ]
        .count()
        .rename(
            "ranking_snapshot_rows"
        )
        .reset_index()
    )

    monthly_coverage = (
        source_month_counts.merge(
            monthly_counts,
            on=[
                "analysis_month_number",
                "month_end_date",
            ],
            how="left",
        )
    )

    monthly_coverage[
        "difference"
    ] = (
        monthly_coverage[
            "assigned_rows"
        ].fillna(0)
        - monthly_coverage[
            "ranking_snapshot_rows"
        ]
    )

    monthly_coverage.to_csv(
        MONTHLY_COVERAGE_PATH,
        index=False,
    )

    # ---------------------------------------------------------------
    # Final gates.
    # ---------------------------------------------------------------
    if len(snapshot) != EXPECTED_RANKING_ROWS:
        failures.append(
            f"Ranking snapshot rows = {len(snapshot)}, "
            f"expected {EXPECTED_RANKING_ROWS}."
        )

    if (
        snapshot[
            "analysis_month_number"
        ].nunique()
        != EXPECTED_RANKING_MONTHS
    ):
        failures.append(
            "Ranking snapshot does not contain "
            "exactly 60 analysis months."
        )

    if not unmatched_events.empty:
        failures.append(
            f"{len(unmatched_events)} official membership "
            "event row(s) remain unmapped."
        )

    if unresolved_initial:
        failures.append(
            f"{len(unresolved_initial)} security identity/identities "
            "have no single initial sector state."
        )

    if (
        sector_intervals[
            "security_key"
        ].nunique()
        != EXPECTED_MEMBERSHIP_INTERVALS
    ):
        failures.append(
            "Sector intervals do not cover all 593 "
            "membership security identities."
        )

    if overlap_count != 0:
        failures.append(
            f"Sector interval overlaps = {overlap_count}."
        )

    if gap_count != 0:
        failures.append(
            f"Sector interval gaps = {gap_count}."
        )

    if not evidence_mismatches.empty:
        failures.append(
            f"Unexplained sector evidence mismatches = "
            f"{len(evidence_mismatches)}."
        )

    if missing_monthly:
        failures.append(
            f"Ranking-date rows without a sector assignment = "
            f"{len(missing_monthly)}."
        )

    if len(monthly) != len(snapshot):
        failures.append(
            f"Monthly sector assignment rows = {len(monthly)}, "
            f"ranking snapshot rows = {len(snapshot)}."
        )

    if (
        monthly_coverage[
            "difference"
        ].fillna(
            -999
        ).ne(0).any()
    ):
        failures.append(
            "At least one ranking month does not reconcile "
            "exactly to sector assignments."
        )

    if (
        monthly_coverage[
            "sectors_present"
        ].fillna(
            0
        ).ne(11).any()
    ):
        failures.append(
            "At least one ranking month does not contain "
            "all 11 GICS sectors."
        )

    # No duplicate security-month assignments.
    duplicate_security_month = int(
        monthly.duplicated(
            subset=[
                "analysis_month_number",
                "security_key",
            ],
            keep=False,
        ).sum()
    )

    if duplicate_security_month != 0:
        failures.append(
            f"Duplicate security-month assignments = "
            f"{duplicate_security_month}."
        )

    # Write candidate outputs only after construction;
    # quality status is clearly carried by the report.
    sector_intervals.to_csv(
        INTERVAL_OUTPUT_PATH,
        index=False,
    )

    monthly.to_csv(
        MONTHLY_OUTPUT_PATH,
        index=False,
    )

    # ---------------------------------------------------------------
    # Report.
    # ---------------------------------------------------------------
    lines: list[str] = [
        line(),
        (
            "POINT-IN-TIME GICS SECURITY_KEY / "
            "MONTHLY ASSIGNMENT AUDIT"
        ),
        line(),
        (
            "Mode: LOCAL construction + "
            "Azure SQL READ-ONLY"
        ),
        (
            "Source hierarchy: official GICS effective dates "
            "> canonical SEC Select Sector ETF states "
            "> official S&P membership-event GICS evidence; "
            "identity hierarchy: historical ticker > current SPY CUSIP "
            "> unique current/alias name > audited residual override"
        ),
        (
            "Analytical window: 2021-01 through 2025-12"
        ),
        (
            "Ranking dates: exact dates from "
            "analytics.security_month_end_snapshot"
        ),
        "",
    ]

    lines += section(
        "1. IDENTITY BRIDGE"
    )

    lines += [
        (
            "SEC canonical holding rows: "
            f"{len(sec):,}"
        ),
        (
            "SEC rows mapped to security_key: "
            f"{int(sec['security_key'].notna().sum()):,}"
        ),
        (
            "SEC rows unmatched: "
            f"{len(unmatched_sec):,}"
        ),
        (
            "Unique SEC holding identifiers bridged: "
            f"{bridge['holding_identifier'].nunique():,}"
        ),
        (
            "Ambiguous global ticker keys excluded: "
            f"{len(ambiguous_tickers):,}"
        ),
        (
            "Current State Street CUSIP identifiers bridged: "
            f"{len(anchor_identifier_map):,}"
        ),
        (
            "Ambiguous current State Street identifiers excluded: "
            f"{len(ambiguous_anchor_identifiers):,}"
        ),
        (
            "Unique current/alias normalized names bridged: "
            f"{len(name_map):,}"
        ),
        (
            "Ambiguous current/alias normalized names excluded: "
            f"{len(ambiguous_names):,}"
        ),
        (
            "Audited residual identity overrides loaded: "
            f"{len(override_identifier_map):,}"
        ),
        (
            "Ambiguous SEC holding identifiers excluded: "
            f"{len(ambiguous_identifiers):,}"
        ),
        (
            "Official membership-event rows mapped: "
            f"{len(mapped_events):,}"
        ),
        (
            "Official membership-event rows unmatched: "
            f"{len(unmatched_events):,}"
        ),
        (
            "Authoritative GICS transitions mapped to security_key: "
            f"{int(transitions['security_key'].notna().sum()):,}"
        ),
        (
            "Audited official membership-event GICS corrections applied: "
            f"{event_sector_corrections_applied:,}"
        ),
        (
            "Unmapped SEC ETF rows retained for source audit but not used "
            "as a hard H2 gate: "
            f"{len(unmatched_sec):,}"
        ),
    ]

    lines += section(
        "2. PERMANENT SECURITY GICS INTERVALS"
    )

    lines += [
        (
            "Membership security identities: "
            f"{intervals['security_key'].nunique():,}"
        ),
        (
            "Security identities with GICS intervals: "
            f"{sector_intervals['security_key'].nunique():,}"
        ),
        (
            "GICS interval rows: "
            f"{len(sector_intervals):,}"
        ),
        (
            "Authoritative sector transitions represented: "
            f"{len(transitions):,}"
        ),
        (
            "Interval overlaps: "
            f"{overlap_count}"
        ),
        (
            "Interval gaps: "
            f"{gap_count}"
        ),
        (
            "Unresolved initial-sector identities: "
            f"{len(unresolved_initial)}"
        ),
        (
            "Unexplained evidence mismatches: "
            f"{len(evidence_mismatches)}"
        ),
    ]

    lines += section(
        "3. 60-MONTH RANKING-DATE EXPANSION"
    )

    lines += [
        (
            "Azure ranking snapshot rows: "
            f"{len(snapshot):,}"
        ),
        (
            "Monthly GICS assignment rows: "
            f"{len(monthly):,}"
        ),
        (
            "Ranking months: "
            f"{monthly['analysis_month_number'].nunique():,}"
        ),
        (
            "Security identities appearing in monthly assignments: "
            f"{monthly['security_key'].nunique():,}"
        ),
        (
            "Missing ranking-date sector assignments: "
            f"{len(missing_monthly):,}"
        ),
        (
            "Duplicate security-month assignments: "
            f"{duplicate_security_month:,}"
        ),
        (
            "Sector count range across ranking months: "
            f"{int(monthly_coverage['sectors_present'].min())} "
            "to "
            f"{int(monthly_coverage['sectors_present'].max())}"
        ),
        (
            "Monthly assigned-security range: "
            f"{int(monthly_coverage['assigned_rows'].min())} "
            "to "
            f"{int(monthly_coverage['assigned_rows'].max())}"
        ),
    ]

    lines.append("")
    lines.append(
        "Monthly sector coverage:"
    )

    for row in monthly_coverage.itertuples(
        index=False
    ):
        lines.append(
            f"  month={int(row.analysis_month_number):02d} | "
            f"{pd.Timestamp(row.month_end_date).date()} | "
            f"ranking_rows={int(row.ranking_snapshot_rows)} | "
            f"assigned={int(row.assigned_rows)} | "
            f"sectors={int(row.sectors_present)} | "
            f"difference={int(row.difference)}"
        )

    lines += section(
        "4. H2 POINT-IN-TIME GICS QUALITY GATE"
    )

    if failures:
        lines.append(
            "RESULT: REVIEW_REQUIRED"
        )

        for failure in failures:
            lines.append(
                "FAIL: "
                + failure
            )

        lines += [
            "",
            (
                "H2 remains blocked until every failure above "
                "is resolved."
            ),
        ]

    else:
        lines += [
            (
                "PASS: All 593 membership identities have continuous, "
                "non-overlapping point-in-time GICS intervals."
            ),
            (
                "PASS: All 20 authoritative GICS transitions are "
                "incorporated on their exact valid-from dates."
            ),
            (
                "PASS: All 30,211 ranking-date security rows map to "
                "exactly one canonical GICS sector."
            ),
            (
                "PASS: All 60 ranking months contain all 11 GICS sectors."
            ),
            (
                "PASS: No unexplained in-membership SEC or official "
                "membership-event sector evidence conflicts remain."
            ),
            (
                "PASS: SEC observations outside project membership "
                "intervals are retained as support/audit evidence and "
                "excluded from in-window contradiction checks."
            ),
            (
                "PASS: Remaining unmapped SEC ETF rows are informational "
                "only; every ranking-security observation has a complete "
                "point-in-time sector assignment."
            ),
            "",
            (
                "RESULT: POINT_IN_TIME_GICS_MONTHLY_QUALITY_GATE_PASSED"
            ),
            "",
            (
                "H2 SECTOR-RELATIVE MOMENTUM DATA PREREQUISITE: READY"
            ),
        ]

    lines += [
        "",
        (
            "Azure SQL modifications performed: 0"
        ),
        (
            "Validated price/membership core modified: 0"
        ),
        (
            "Permanent GICS intervals: "
            f"{INTERVAL_OUTPUT_PATH.relative_to(ROOT)}"
        ),
        (
            "Monthly GICS assignments: "
            f"{MONTHLY_OUTPUT_PATH.relative_to(ROOT)}"
        ),
        (
            "SEC identifier bridge: "
            f"{IDENTIFIER_BRIDGE_PATH.relative_to(ROOT)}"
        ),
        (
            "Audited residual identity overrides: "
            f"{IDENTITY_OVERRIDES_PATH.relative_to(ROOT)}"
        ),
        (
            "Audited official event-sector corrections: "
            f"{EVENT_SECTOR_OVERRIDES_PATH.relative_to(ROOT)}"
        ),
        (
            "Coverage audit: "
            f"{MONTHLY_COVERAGE_PATH.relative_to(ROOT)}"
        ),
    ]

    report_text = (
        "\n".join(lines)
        + "\n"
    )

    REPORT_PATH.write_text(
        report_text,
        encoding="utf-8",
    )

    print(
        report_text,
        end="",
    )

    print(
        f"Report saved: "
        f"{REPORT_PATH}"
    )


if __name__ == "__main__":
    main()
