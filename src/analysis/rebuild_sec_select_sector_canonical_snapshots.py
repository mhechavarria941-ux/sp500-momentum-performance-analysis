from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

CACHE_DIR = (
    ROOT
    / "data"
    / "reference"
    / "gics"
    / "sec_select_sector_submission_text"
)

MANIFEST_PATH = (
    ROOT
    / "data"
    / "reference"
    / "gics"
    / "sec_select_sector_canonical_manifest.csv"
)

HOLDINGS_RAW_PATH = (
    ROOT
    / "data"
    / "reference"
    / "gics"
    / "sec_select_sector_canonical_holdings_raw.csv"
)

HOLDINGS_CLEAN_PATH = (
    ROOT
    / "data"
    / "reference"
    / "gics"
    / "sec_select_sector_canonical_holdings_clean.csv"
)

SNAPSHOT_COVERAGE_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "sec_select_sector_canonical_snapshot_coverage.csv"
)

RESIDUAL_CROSSHOLDINGS_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "sec_select_sector_residual_crossholdings.csv"
)

UNRESOLVED_DUPLICATES_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "sec_select_sector_unresolved_cross_sector_duplicates.csv"
)

TRANSITIONS_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "sec_select_sector_canonical_transition_candidates.csv"
)

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "sec_select_sector_canonical_rebuild_audit.txt"
)

SCRIPT_VERSION = (
    "2026-08-24-v4-canonical-series-residual-control"
)

REPORT_START = pd.Timestamp("2020-12-31")
REPORT_END = pd.Timestamp("2025-12-31")

# Canonical Select Sector SPDR series, established by the continuity audit.
CANONICAL_SERIES = {
    "Communication Services": {
        "series_id": "S000062095",
        "ticker": "XLC",
    },
    "Consumer Discretionary": {
        "series_id": "S000006408",
        "ticker": "XLY",
    },
    "Consumer Staples": {
        "series_id": "S000006409",
        "ticker": "XLP",
    },
    "Energy": {
        "series_id": "S000006410",
        "ticker": "XLE",
    },
    "Financials": {
        "series_id": "S000006411",
        "ticker": "XLF",
    },
    "Health Care": {
        "series_id": "S000006412",
        "ticker": "XLV",
    },
    "Industrials": {
        "series_id": "S000006413",
        "ticker": "XLI",
    },
    "Information Technology": {
        "series_id": "S000006415",
        "ticker": "XLK",
    },
    "Materials": {
        "series_id": "S000006414",
        "ticker": "XLB",
    },
    "Real Estate": {
        "series_id": "S000051152",
        "ticker": "XLRE",
    },
    "Utilities": {
        "series_id": "S000006416",
        "ticker": "XLU",
    },
}

SERIES_TO_SECTOR = {
    payload["series_id"]: sector
    for sector, payload in CANONICAL_SERIES.items()
}

SERIES_TO_TICKER = {
    payload["series_id"]: payload["ticker"]
    for payload in CANONICAL_SERIES.values()
}

EXPECTED_SECTOR_COUNT = 11

# Extremely conservative residual-crossholding rule.
#
# N-PORT can contain tiny implementation/settlement remnants in a sector ETF
# after the security has economically moved to another sector.  We do NOT
# simply drop every duplicate.  A duplicate is resolved only when:
#
#   1. the dominant sector position is at least 0.01% of the fund;
#   2. every non-dominant duplicate is below 0.001% of its fund; and
#   3. the dominant position is at least 1,000x the largest residual.
#
# Otherwise the duplicate remains unresolved and the quality gate fails.
DOMINANT_MIN_PCT = 0.01
RESIDUAL_MAX_PCT = 0.001
DOMINANCE_RATIO_MIN = 1000.0


def line() -> str:
    return "=" * 118


def section(title: str) -> list[str]:
    return ["", line(), title, line()]


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def first_text(
    root: ET.Element,
    names: set[str],
) -> str | None:
    lowered = {name.lower() for name in names}

    for element in root.iter():
        if local_name(element.tag).lower() in lowered:
            text = (element.text or "").strip()
            if text:
                return text

    return None


def child_text(
    node: ET.Element,
    name: str,
) -> str | None:
    target = name.lower()

    for element in node.iter():
        if local_name(element.tag).lower() == target:
            text = (element.text or "").strip()
            if text:
                return text

    return None


def attribute_value(
    node: ET.Element,
    tag_name: str,
    attribute_name: str,
) -> str | None:
    tag_target = tag_name.lower()
    attr_target = attribute_name.lower()

    for element in node.iter():
        if local_name(element.tag).lower() != tag_target:
            continue

        for key, value in element.attrib.items():
            if local_name(key).lower() == attr_target:
                text = str(value).strip()
                if text:
                    return text

    return None


def extract_nport_xml(
    submission_text: str,
) -> str:
    document_blocks = re.findall(
        r"(?is)<DOCUMENT>(.*?)</DOCUMENT>",
        submission_text,
    )

    for block in document_blocks:
        type_match = re.search(
            r"(?im)^<TYPE>\s*([^\r\n]+)",
            block,
        )
        if not type_match:
            continue

        document_type = (
            type_match.group(1)
            .strip()
            .upper()
        )

        if document_type not in {
            "NPORT-P",
            "NPORT-P/A",
        }:
            continue

        xml_match = re.search(
            r"(?is)<XML>\s*(.*?)\s*</XML>",
            block,
        )

        if not xml_match:
            continue

        xml_text = xml_match.group(1).strip()

        if "<edgarSubmission" in xml_text:
            return xml_text

    raise RuntimeError(
        "Could not locate embedded NPORT-P XML."
    )


def parse_header_date(
    submission_text: str,
    label: str,
) -> pd.Timestamp | pd.NaT:
    pattern = rf"(?im)^{re.escape(label)}:\s*(\d{{8}})"
    match = re.search(pattern, submission_text)

    if not match:
        return pd.NaT

    return pd.to_datetime(
        match.group(1),
        format="%Y%m%d",
        errors="coerce",
    )


def valid_cusip(value: object) -> bool:
    if value is None or pd.isna(value):
        return False

    text = str(value).strip().upper()

    if text in {"", "000000000"}:
        return False

    return bool(
        re.fullmatch(
            r"[0-9A-Z]{8,9}",
            text,
        )
    )


def valid_isin(value: object) -> bool:
    if value is None or pd.isna(value):
        return False

    text = str(value).strip().upper()

    return bool(
        re.fullmatch(
            r"[A-Z]{2}[A-Z0-9]{9}[0-9]",
            text,
        )
    )


def holding_identifier(
    cusip: object,
    isin: object,
    lei: object,
) -> tuple[str | None, str | None]:
    if valid_cusip(cusip):
        return (
            "CUSIP",
            str(cusip).strip().upper(),
        )

    if valid_isin(isin):
        return (
            "ISIN",
            str(isin).strip().upper(),
        )

    if lei is not None and not pd.isna(lei):
        text = str(lei).strip()
        if text and text.upper() != "N/A":
            return ("LEI", text)

    return (None, None)


def parse_cached_submission(
    path: Path,
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
]:
    submission_text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    xml_text = extract_nport_xml(
        submission_text
    )

    root = ET.fromstring(
        xml_text.encode("utf-8")
    )

    series_id = first_text(
        root,
        {"seriesId", "seriesIdNumber"},
    )

    if series_id not in SERIES_TO_SECTOR:
        return None, []

    series_name = first_text(
        root,
        {"seriesName", "nameOfSeries"},
    )

    report_date_text = first_text(
        root,
        {
            "repPdDate",
            "reportingPeriodEndDate",
            "periodOfReport",
        },
    )

    report_date = pd.to_datetime(
        report_date_text,
        errors="coerce",
    )

    if (
        pd.isna(report_date)
        or report_date < REPORT_START
        or report_date > REPORT_END
    ):
        return None, []

    accession = path.stem

    filing_date = parse_header_date(
        submission_text,
        "FILED AS OF DATE",
    )

    accepted_date = parse_header_date(
        submission_text,
        "ACCEPTANCE-DATETIME",
    )

    sector = SERIES_TO_SECTOR[
        series_id
    ]

    sector_etf_ticker = (
        SERIES_TO_TICKER[
            series_id
        ]
    )

    investment_nodes = [
        element
        for element in root.iter()
        if local_name(
            element.tag
        ).lower()
        in {
            "invstorsec",
            "investmentorsecurity",
        }
    ]

    holdings: list[
        dict[str, Any]
    ] = []

    for node in investment_nodes:
        asset_category = child_text(
            node,
            "assetCat",
        )

        if asset_category != "EC":
            continue

        name = child_text(
            node,
            "name",
        )

        title = child_text(
            node,
            "title",
        )

        cusip = child_text(
            node,
            "cusip",
        )

        isin = attribute_value(
            node,
            "isin",
            "value",
        )

        ticker = attribute_value(
            node,
            "ticker",
            "value",
        )

        if ticker is None:
            ticker = child_text(
                node,
                "ticker",
            )

        lei = child_text(
            node,
            "lei",
        )

        value_usd = pd.to_numeric(
            child_text(
                node,
                "valUSD",
            ),
            errors="coerce",
        )

        pct_value = pd.to_numeric(
            child_text(
                node,
                "pctVal",
            ),
            errors="coerce",
        )

        identifier_type, identifier = (
            holding_identifier(
                cusip,
                isin,
                lei,
            )
        )

        holdings.append(
            {
                "accession_number": accession,
                "filing_date": filing_date,
                "accepted_date": accepted_date,
                "report_date": report_date,
                "series_id": series_id,
                "series_name": series_name,
                "gics_sector": sector,
                "sector_etf_ticker": sector_etf_ticker,
                "holding_name": name,
                "holding_title": title,
                "holding_ticker": (
                    str(ticker).strip().upper()
                    if ticker
                    else None
                ),
                "cusip": (
                    str(cusip).strip().upper()
                    if cusip
                    else None
                ),
                "isin": (
                    str(isin).strip().upper()
                    if isin
                    else None
                ),
                "lei": lei,
                "identifier_type": (
                    identifier_type
                ),
                "holding_identifier": (
                    identifier
                ),
                "value_usd": value_usd,
                "pct_value": pct_value,
                "source_file": str(
                    path.relative_to(ROOT)
                ),
                "source_type": (
                    "SEC_NPORT_P_COMPLETE_SUBMISSION"
                ),
            }
        )

    metadata = {
        "accession_number": accession,
        "filing_date": filing_date,
        "accepted_date": accepted_date,
        "report_date": report_date,
        "series_id": series_id,
        "series_name": series_name,
        "gics_sector": sector,
        "sector_etf_ticker": sector_etf_ticker,
        "equity_rows": len(
            holdings
        ),
        "source_file": str(
            path.relative_to(ROOT)
        ),
        "source_type": (
            "SEC_NPORT_P_COMPLETE_SUBMISSION"
        ),
    }

    return metadata, holdings


def choose_latest_filing(
    manifest: pd.DataFrame,
) -> pd.DataFrame:
    # Canonical series are already pinned.  This final grouping exists
    # solely to handle an NPORT-P/A amendment for the same canonical
    # series/report date.
    working = manifest.copy()

    working["selection_date"] = (
        working["filing_date"]
        .fillna(
            working["accepted_date"]
        )
    )

    working = working.sort_values(
        [
            "report_date",
            "series_id",
            "selection_date",
            "accession_number",
        ]
    )

    selected = (
        working.groupby(
            [
                "report_date",
                "series_id",
            ],
            as_index=False,
            sort=True,
        )
        .tail(1)
        .reset_index(drop=True)
    )

    return selected.drop(
        columns=["selection_date"]
    )


def resolve_cross_sector_duplicates(
    holdings: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    working = holdings.copy()

    working[
        "sector_assignment_status"
    ] = "UNIQUE_CANONICAL_SECTOR_HOLDING"

    residual_rows: list[
        dict[str, Any]
    ] = []
    unresolved_rows: list[
        dict[str, Any]
    ] = []

    exclude_indices: set[int] = set()

    grouped = (
        working.dropna(
            subset=[
                "holding_identifier"
            ]
        )
        .groupby(
            [
                "report_date",
                "holding_identifier",
            ],
            sort=True,
        )
    )

    for (
        report_date,
        identifier,
    ), group in grouped:
        if (
            group[
                "gics_sector"
            ].nunique()
            <= 1
        ):
            continue

        ranked = (
            group.assign(
                pct_numeric=pd.to_numeric(
                    group[
                        "pct_value"
                    ],
                    errors="coerce",
                ).fillna(-1.0)
            )
            .sort_values(
                "pct_numeric",
                ascending=False,
            )
        )

        top = ranked.iloc[0]
        residual = ranked.iloc[1:]

        top_pct = float(
            top["pct_numeric"]
        )

        largest_residual_pct = float(
            residual[
                "pct_numeric"
            ].max()
        )

        ratio = (
            float("inf")
            if largest_residual_pct <= 0
            else top_pct
            / largest_residual_pct
        )

        qualifies = bool(
            top_pct
            >= DOMINANT_MIN_PCT
            and largest_residual_pct
            <= RESIDUAL_MAX_PCT
            and ratio
            >= DOMINANCE_RATIO_MIN
        )

        if qualifies:
            working.loc[
                top.name,
                "sector_assignment_status",
            ] = (
                "DOMINANT_MATERIAL_SECTOR_"
                "RESIDUAL_CROSSHOLDING_REMOVED"
            )

            for idx, row in residual.iterrows():
                exclude_indices.add(
                    int(idx)
                )

                residual_rows.append(
                    {
                        "report_date": report_date,
                        "holding_identifier": identifier,
                        "holding_name": (
                            row[
                                "holding_name"
                            ]
                        ),
                        "kept_sector": (
                            top[
                                "gics_sector"
                            ]
                        ),
                        "kept_sector_etf": (
                            top[
                                "sector_etf_ticker"
                            ]
                        ),
                        "kept_pct_value": (
                            top_pct
                        ),
                        "excluded_sector": (
                            row[
                                "gics_sector"
                            ]
                        ),
                        "excluded_sector_etf": (
                            row[
                                "sector_etf_ticker"
                            ]
                        ),
                        "excluded_pct_value": (
                            float(
                                row[
                                    "pct_numeric"
                                ]
                            )
                        ),
                        "dominance_ratio": (
                            ratio
                        ),
                        "resolution": (
                            "RESIDUAL_IMPLEMENTATION_"
                            "CROSSHOLDING_EXCLUDED"
                        ),
                    }
                )

        else:
            for _, row in ranked.iterrows():
                unresolved_rows.append(
                    {
                        "report_date": report_date,
                        "holding_identifier": identifier,
                        "holding_name": (
                            row[
                                "holding_name"
                            ]
                        ),
                        "gics_sector": (
                            row[
                                "gics_sector"
                            ]
                        ),
                        "sector_etf_ticker": (
                            row[
                                "sector_etf_ticker"
                            ]
                        ),
                        "pct_value": (
                            row[
                                "pct_numeric"
                            ]
                        ),
                        "dominance_ratio": ratio,
                        "resolution": (
                            "UNRESOLVED_REVIEW_REQUIRED"
                        ),
                    }
                )

    clean = working.drop(
        index=list(
            exclude_indices
        )
    ).copy()

    residual_frame = pd.DataFrame(
        residual_rows
    )

    unresolved_frame = pd.DataFrame(
        unresolved_rows
    )

    return (
        clean,
        residual_frame,
        unresolved_frame,
    )


def build_snapshot_coverage(
    holdings: pd.DataFrame,
    manifest: pd.DataFrame,
    unresolved: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[
        dict[str, Any]
    ] = []

    for report_date in sorted(
        manifest[
            "report_date"
        ].dropna().unique()
    ):
        report_date = pd.Timestamp(
            report_date
        )

        filing_group = manifest[
            manifest[
                "report_date"
            ]
            == report_date
        ]

        holding_group = holdings[
            holdings[
                "report_date"
            ]
            == report_date
        ]

        unresolved_count = 0

        if not unresolved.empty:
            unresolved_count = (
                unresolved[
                    unresolved[
                        "report_date"
                    ]
                    == report_date
                ][
                    "holding_identifier"
                ]
                .nunique()
            )

        rows.append(
            {
                "report_date": (
                    report_date
                ),
                "canonical_sector_count": (
                    filing_group[
                        "gics_sector"
                    ].nunique()
                ),
                "canonical_filing_count": (
                    len(
                        filing_group
                    )
                ),
                "unique_equity_identifiers": (
                    holding_group[
                        "holding_identifier"
                    ].nunique()
                ),
                "unresolved_cross_sector_identifiers": (
                    unresolved_count
                ),
                "complete_11_sector_partition": bool(
                    filing_group[
                        "gics_sector"
                    ].nunique()
                    == EXPECTED_SECTOR_COUNT
                    and len(
                        filing_group
                    )
                    == EXPECTED_SECTOR_COUNT
                    and 480
                    <= holding_group[
                        "holding_identifier"
                    ].nunique()
                    <= 525
                    and unresolved_count
                    == 0
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


def detect_transitions(
    holdings: pd.DataFrame,
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    complete_dates = (
        coverage.loc[
            coverage[
                "complete_11_sector_partition"
            ],
            "report_date",
        ]
        .sort_values()
        .tolist()
    )

    transition_rows: list[
        dict[str, Any]
    ] = []

    previous_map: dict[
        str,
        str,
    ] | None = None

    previous_name_map: dict[
        str,
        str,
    ] | None = None

    previous_date: pd.Timestamp | None = None

    for current_date in complete_dates:
        current_date = pd.Timestamp(
            current_date
        )

        current = holdings[
            holdings[
                "report_date"
            ]
            == current_date
        ].copy()

        current_map = (
            current.dropna(
                subset=[
                    "holding_identifier"
                ]
            )
            .drop_duplicates(
                [
                    "holding_identifier",
                    "gics_sector",
                ]
            )
            .set_index(
                "holding_identifier"
            )[
                "gics_sector"
            ]
            .to_dict()
        )

        current_name_map = (
            current.dropna(
                subset=[
                    "holding_identifier",
                    "holding_name",
                ]
            )
            .drop_duplicates(
                "holding_identifier"
            )
            .set_index(
                "holding_identifier"
            )[
                "holding_name"
            ]
            .astype(str)
            .to_dict()
        )

        if previous_map is not None:
            shared = sorted(
                set(
                    previous_map
                )
                & set(
                    current_map
                )
            )

            for identifier in shared:
                old_sector = (
                    previous_map[
                        identifier
                    ]
                )
                new_sector = (
                    current_map[
                        identifier
                    ]
                )

                if old_sector == new_sector:
                    continue

                transition_rows.append(
                    {
                        "holding_identifier": (
                            identifier
                        ),
                        "holding_name_previous": (
                            previous_name_map.get(
                                identifier
                            )
                            if previous_name_map
                            else None
                        ),
                        "holding_name_current": (
                            current_name_map.get(
                                identifier
                            )
                        ),
                        "previous_report_date": (
                            previous_date
                        ),
                        "current_report_date": (
                            current_date
                        ),
                        "previous_sector": (
                            old_sector
                        ),
                        "current_sector": (
                            new_sector
                        ),
                        "status": (
                            "REQUIRES_EXACT_EFFECTIVE_"
                            "DATE_CONFIRMATION"
                        ),
                    }
                )

        previous_map = (
            current_map
        )
        previous_name_map = (
            current_name_map
        )
        previous_date = (
            current_date
        )

    return pd.DataFrame(
        transition_rows
    )


def main() -> None:
    print(
        "RUNNING SCRIPT VERSION: "
        f"{SCRIPT_VERSION}"
    )

    if not CACHE_DIR.exists():
        raise FileNotFoundError(
            CACHE_DIR
        )

    text_files = sorted(
        CACHE_DIR.glob(
            "*.txt"
        )
    )

    if not text_files:
        raise RuntimeError(
            "No cached SEC complete-"
            "submission text files found."
        )

    MANIFEST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_rows: list[
        dict[str, Any]
    ] = []

    holding_rows: list[
        dict[str, Any]
    ] = []

    parse_failures: list[
        str
    ] = []

    print(
        "Rebuilding from cached SEC "
        "complete submissions..."
    )

    for path in text_files:
        try:
            metadata, holdings = (
                parse_cached_submission(
                    path
                )
            )
        except Exception as exc:
            parse_failures.append(
                f"{path.name}: {repr(exc)}"
            )
            continue

        if metadata is None:
            continue

        manifest_rows.append(
            metadata
        )
        holding_rows.extend(
            holdings
        )

    manifest = pd.DataFrame(
        manifest_rows
    )
    holdings_raw = pd.DataFrame(
        holding_rows
    )

    if manifest.empty:
        raise RuntimeError(
            "No canonical Select Sector "
            "series were reconstructed."
        )

    manifest[
        "report_date"
    ] = pd.to_datetime(
        manifest[
            "report_date"
        ],
        errors="raise",
    )

    holdings_raw[
        "report_date"
    ] = pd.to_datetime(
        holdings_raw[
            "report_date"
        ],
        errors="raise",
    )

    selected_manifest = (
        choose_latest_filing(
            manifest
        )
    )

    selected_accessions = set(
        selected_manifest[
            "accession_number"
        ]
    )

    selected_holdings_raw = (
        holdings_raw[
            holdings_raw[
                "accession_number"
            ].isin(
                selected_accessions
            )
        ].copy()
    )

    (
        clean_holdings,
        residual_crossholdings,
        unresolved_duplicates,
    ) = resolve_cross_sector_duplicates(
        selected_holdings_raw
    )

    coverage = (
        build_snapshot_coverage(
            clean_holdings,
            selected_manifest,
            unresolved_duplicates,
        )
    )

    transitions = (
        detect_transitions(
            clean_holdings,
            coverage,
        )
    )

    selected_manifest.to_csv(
        MANIFEST_PATH,
        index=False,
    )

    selected_holdings_raw.to_csv(
        HOLDINGS_RAW_PATH,
        index=False,
    )

    clean_holdings.to_csv(
        HOLDINGS_CLEAN_PATH,
        index=False,
    )

    coverage.to_csv(
        SNAPSHOT_COVERAGE_PATH,
        index=False,
    )

    residual_crossholdings.to_csv(
        RESIDUAL_CROSSHOLDINGS_PATH,
        index=False,
    )

    unresolved_duplicates.to_csv(
        UNRESOLVED_DUPLICATES_PATH,
        index=False,
    )

    transitions.to_csv(
        TRANSITIONS_PATH,
        index=False,
    )

    complete_count = int(
        coverage[
            "complete_11_sector_partition"
        ].sum()
    )

    lines: list[str] = [
        line(),
        (
            "SEC SELECT SECTOR SPDR — "
            "CANONICAL SERIES REBUILD AUDIT"
        ),
        line(),
        (
            "Mode: LOCAL SEC CACHE ONLY / "
            "Azure SQL unchanged"
        ),
        (
            "Source: SEC EDGAR NPORT-P "
            "complete-submission XML"
        ),
        (
            "Canonical ETF series explicitly "
            "pinned: 11"
        ),
        (
            "Premium Income ETF series "
            "excluded by series_id: YES"
        ),
        (
            "Wikipedia used: NO"
        ),
    ]

    lines += section(
        "1. CANONICAL SERIES CONTROL"
    )

    lines += [
        (
            "Cached SEC submissions "
            f"inspected: {len(text_files):,}"
        ),
        (
            "Canonical series filings "
            f"parsed: {len(manifest):,}"
        ),
        (
            "Selected canonical "
            "sector/report-date filings: "
            f"{len(selected_manifest):,}"
        ),
        (
            "Canonical series IDs present: "
            f"{selected_manifest['series_id'].nunique():,}"
        ),
        (
            "Canonical sectors present: "
            f"{selected_manifest['gics_sector'].nunique():,}"
        ),
        (
            "Parse failures while scanning "
            f"cache: {len(parse_failures):,}"
        ),
    ]

    lines.append("")

    for sector, payload in (
        CANONICAL_SERIES.items()
    ):
        rows = selected_manifest[
            selected_manifest[
                "series_id"
            ]
            == payload[
                "series_id"
            ]
        ]

        lines.append(
            f"{sector} | "
            f"{payload['ticker']} | "
            f"{payload['series_id']} | "
            f"selected_reports={len(rows)}"
        )

    lines += section(
        "2. RESIDUAL CROSSHOLDING CONTROL"
    )

    lines += [
        (
            "Raw selected equity rows: "
            f"{len(selected_holdings_raw):,}"
        ),
        (
            "Residual crossholding rows "
            "excluded under conservative "
            "dominance rule: "
            f"{len(residual_crossholdings):,}"
        ),
        (
            "Unresolved cross-sector "
            "duplicate rows: "
            f"{len(unresolved_duplicates):,}"
        ),
        (
            "Dominance rule: dominant >= "
            f"{DOMINANT_MIN_PCT}% ; "
            "residual <= "
            f"{RESIDUAL_MAX_PCT}% ; "
            "dominant/residual >= "
            f"{DOMINANCE_RATIO_MIN:,.0f}x"
        ),
    ]

    if not residual_crossholdings.empty:
        lines.append("")
        lines.append(
            "Resolved residual artifacts:"
        )

        for row in (
            residual_crossholdings
            .itertuples(
                index=False
            )
        ):
            lines.append(
                f"  "
                f"{pd.Timestamp(row.report_date).date()} | "
                f"{row.holding_identifier} | "
                f"{row.holding_name} | "
                f"keep {row.kept_sector} "
                f"({row.kept_pct_value:.12g}%) | "
                f"exclude {row.excluded_sector} "
                f"({row.excluded_pct_value:.12g}%) | "
                f"ratio={row.dominance_ratio:,.0f}x"
            )

    lines += section(
        "3. HISTORICAL SNAPSHOT COVERAGE"
    )

    lines += [
        (
            "Historical report dates: "
            f"{len(coverage):,}"
        ),
        (
            "Complete 11-sector partitions: "
            f"{complete_count:,}"
        ),
        (
            "Earliest report date: "
            f"{coverage['report_date'].min().date()}"
        ),
        (
            "Latest report date: "
            f"{coverage['report_date'].max().date()}"
        ),
        (
            "Unique identifier range: "
            f"{int(coverage['unique_equity_identifiers'].min())} "
            "to "
            f"{int(coverage['unique_equity_identifiers'].max())}"
        ),
    ]

    lines.append("")

    for row in coverage.itertuples(
        index=False
    ):
        lines.append(
            f"  "
            f"{pd.Timestamp(row.report_date).date()} | "
            f"sectors={row.canonical_sector_count} | "
            f"filings={row.canonical_filing_count} | "
            f"unique_ids={row.unique_equity_identifiers} | "
            f"unresolved_duplicates="
            f"{row.unresolved_cross_sector_identifiers} | "
            f"complete="
            f"{row.complete_11_sector_partition}"
        )

    lines += section(
        "4. TRANSITION DISCOVERY"
    )

    lines += [
        (
            "Sector transitions between "
            "consecutive complete snapshots: "
            f"{len(transitions):,}"
        ),
        (
            "These remain candidates until "
            "their exact effective dates are "
            "validated against official "
            "S&P/MSCI/GICS or issuer evidence."
        ),
    ]

    if not transitions.empty:
        for row in transitions.itertuples(
            index=False
        ):
            lines.append(
                f"  "
                f"{row.holding_identifier} | "
                f"{row.holding_name_current} | "
                f"{row.previous_sector} -> "
                f"{row.current_sector} | "
                f"{pd.Timestamp(row.previous_report_date).date()} "
                "to "
                f"{pd.Timestamp(row.current_report_date).date()}"
            )

    lines += section(
        "5. H2 SOURCE-LAYER DECISION"
    )

    source_gate_passed = bool(
        complete_count
        == len(coverage)
        and len(
            coverage
        )
        == 21
        and selected_manifest[
            "series_id"
        ].nunique()
        == 11
        and selected_manifest[
            "gics_sector"
        ].nunique()
        == 11
        and unresolved_duplicates.empty
    )

    if source_gate_passed:
        lines += [
            (
                "Canonical SEC quarterly "
                "sector partition: PASSED"
            ),
            (
                "All 21 quarter-end source "
                "snapshots now satisfy the "
                "11-sector partition gate."
            ),
            (
                "Next step: validate exact "
                "effective dates for detected "
                "GICS transitions, then map "
                "the cleaned sector states to "
                "permanent security_key and "
                "the 60 ranking months."
            ),
            "",
            (
                "RESULT: "
                "SEC_SELECT_SECTOR_"
                "CANONICAL_SOURCE_GATE_PASSED"
            ),
        ]
    else:
        lines += [
            (
                "Canonical SEC quarterly "
                "sector partition: REVIEW "
                "REQUIRED"
            ),
            (
                "Do not expand to monthly H2 "
                "sector assignments yet."
            ),
            "",
            (
                "RESULT: "
                "SEC_SELECT_SECTOR_"
                "CANONICAL_SOURCE_GATE_"
                "REVIEW_REQUIRED"
            ),
        ]

    lines += [
        "",
        (
            "Azure SQL modifications "
            "performed: 0"
        ),
        (
            "Validated membership/ranking "
            "data modified: 0"
        ),
        (
            "Canonical manifest: "
            f"{MANIFEST_PATH.relative_to(ROOT)}"
        ),
        (
            "Clean holdings: "
            f"{HOLDINGS_CLEAN_PATH.relative_to(ROOT)}"
        ),
        (
            "Coverage audit: "
            f"{SNAPSHOT_COVERAGE_PATH.relative_to(ROOT)}"
        ),
        (
            "Residual audit: "
            f"{RESIDUAL_CROSSHOLDINGS_PATH.relative_to(ROOT)}"
        ),
        (
            "Transition candidates: "
            f"{TRANSITIONS_PATH.relative_to(ROOT)}"
        ),
    ]

    if parse_failures:
        lines += [
            "",
            "Parse failures:",
        ]
        lines.extend(
            f"  {item}"
            for item in parse_failures
        )

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
