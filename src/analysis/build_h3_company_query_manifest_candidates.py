from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v3-h3-company-query-manifest-tickerlike-legal-name-control"

OUT_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

SECURITY_PATH = OUT_DIR / "h3_core_security_snapshot.csv"
TICKER_HISTORY_PATH = OUT_DIR / "h3_core_security_ticker_history_snapshot.csv"

MANIFEST_PATH = OUT_DIR / "h3_company_query_manifest_candidates.csv"
REVIEW_QUEUE_PATH = OUT_DIR / "h3_company_name_history_review_queue.csv"
ALIAS_COLLISION_PATH = OUT_DIR / "h3_company_exact_alias_collision_audit.csv"
REPORT_PATH = OUT_DIR / "h3_company_query_manifest_candidate_report.txt"

EXPECTED_SECURITY_ROWS = 593
EXPECTED_TICKER_HISTORY_ROWS = 594


KEY_CANDIDATES = [
    "security_key",
    "security_id",
    "id",
]

NAME_CANDIDATES = [
    "company_name_reference",
    "security_name",
    "company_name",
    "issuer_name",
    "name",
    "security_description",
    "description",
    "security_full_name",
]

TICKER_CANDIDATES = [
    "project_ticker",
    "ticker",
    "symbol",
    "security_ticker",
]

START_CANDIDATES = [
    "valid_from",
    "effective_from",
    "start_date",
    "effective_date",
    "from_date",
]

END_CANDIDATES = [
    "valid_to",
    "effective_to",
    "end_date",
    "to_date",
]

LEGAL_SUFFIX_PATTERNS = [
    r"\bincorporated\b",
    r"\bcorporation\b",
    r"\bcompany\b",
    r"\blimited\b",
    r"\bholdings\b",
    r"\bholding\b",
    r"\bplc\b",
    r"\binc\b",
    r"\bcorp\b",
    r"\bco\b",
    r"\bltd\b",
    r"\bllc\b",
]


def normalize_text(value: object) -> str:
    text = unicodedata.normalize(
        "NFKC",
        str(value),
    ).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def suffix_stripped_candidate(value: str) -> str:
    text = normalize_text(value)

    previous = None
    while text and text != previous:
        previous = text
        for pattern in LEGAL_SUFFIX_PATTERNS:
            text = re.sub(
                rf"(?:\s+|^){pattern}$",
                "",
                text,
            ).strip()

    return text


def find_column(
    frame: pd.DataFrame,
    candidates: list[str],
    label: str,
    required: bool = True,
) -> str | None:
    lookup = {
        str(column).casefold(): str(column)
        for column in frame.columns
    }

    for candidate in candidates:
        if candidate.casefold() in lookup:
            return lookup[candidate.casefold()]

    if required:
        raise RuntimeError(
            f"Could not identify {label} column. "
            f"Available columns: {list(frame.columns)}"
        )

    return None


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    if not SECURITY_PATH.exists():
        raise FileNotFoundError(SECURITY_PATH)
    if not TICKER_HISTORY_PATH.exists():
        raise FileNotFoundError(TICKER_HISTORY_PATH)

    security = pd.read_csv(
        SECURITY_PATH,
        dtype=str,
        keep_default_na=False,
    )
    ticker_history = pd.read_csv(
        TICKER_HISTORY_PATH,
        dtype=str,
        keep_default_na=False,
    )

    if len(security) != EXPECTED_SECURITY_ROWS:
        raise RuntimeError(
            f"Security snapshot rows={len(security)}, expected 593."
        )
    if len(ticker_history) != EXPECTED_TICKER_HISTORY_ROWS:
        raise RuntimeError(
            f"Ticker-history snapshot rows={len(ticker_history)}, expected 594."
        )

    security_key_col = find_column(
        security,
        KEY_CANDIDATES,
        "security key",
    )
    security_name_col = find_column(
        security,
        NAME_CANDIDATES,
        "company/security name",
    )
    security_ticker_col = find_column(
        security,
        TICKER_CANDIDATES,
        "security ticker",
        required=False,
    )

    ticker_key_col = find_column(
        ticker_history,
        KEY_CANDIDATES,
        "ticker-history security key",
    )
    ticker_col = find_column(
        ticker_history,
        TICKER_CANDIDATES,
        "ticker-history ticker",
    )
    ticker_start_col = find_column(
        ticker_history,
        START_CANDIDATES,
        "ticker-history start",
        required=False,
    )
    ticker_end_col = find_column(
        ticker_history,
        END_CANDIDATES,
        "ticker-history end",
        required=False,
    )

    security = security.rename(
        columns={
            security_key_col: "security_key",
            security_name_col: "canonical_company_name",
        }
    )

    if security_ticker_col:
        security = security.rename(
            columns={
                security_ticker_col: "security_table_ticker"
            }
        )

    ticker_history = ticker_history.rename(
        columns={
            ticker_key_col: "security_key",
            ticker_col: "project_ticker",
        }
    )

    if ticker_start_col:
        ticker_history = ticker_history.rename(
            columns={
                ticker_start_col: "ticker_valid_from"
            }
        )
    else:
        ticker_history["ticker_valid_from"] = ""

    if ticker_end_col:
        ticker_history = ticker_history.rename(
            columns={
                ticker_end_col: "ticker_valid_to"
            }
        )
    else:
        ticker_history["ticker_valid_to"] = ""

    security["security_key"] = security["security_key"].astype(str)
    ticker_history["security_key"] = ticker_history["security_key"].astype(str)

    if security["security_key"].duplicated().any():
        duplicates = security.loc[
            security["security_key"].duplicated(
                keep=False
            ),
            "security_key",
        ].tolist()
        raise RuntimeError(
            "Duplicate security keys in core.security: "
            + ", ".join(duplicates[:20])
        )

    ticker_summary_rows = []

    for security_key, group in ticker_history.groupby(
        "security_key",
        sort=False,
    ):
        group = group.copy()

        if "ticker_valid_from" in group.columns:
            parsed_start = pd.to_datetime(
                group["ticker_valid_from"],
                errors="coerce",
            )
        else:
            parsed_start = pd.Series(
                pd.NaT,
                index=group.index,
            )

        group["_parsed_start"] = parsed_start
        group = group.sort_values(
            [
                "_parsed_start",
                "project_ticker",
            ],
            na_position="first",
        )

        tickers = [
            value
            for value in group["project_ticker"].astype(str)
            if value
        ]

        latest_ticker = (
            tickers[-1]
            if tickers
            else ""
        )

        history_parts = []

        for row in group.itertuples(index=False):
            valid_from = getattr(
                row,
                "ticker_valid_from",
                "",
            )
            valid_to = getattr(
                row,
                "ticker_valid_to",
                "",
            )
            history_parts.append(
                f"{row.project_ticker}"
                f"[{valid_from or '?'}"
                f"→{valid_to or 'OPEN'}]"
            )

        ticker_summary_rows.append(
            {
                "security_key": str(security_key),
                "ticker_segment_count": len(group),
                "latest_project_ticker": latest_ticker,
                "ticker_history_pipe": " | ".join(
                    history_parts
                ),
                "multiple_ticker_segments_flag": int(
                    len(group) > 1
                ),
            }
        )

    ticker_summary = pd.DataFrame(
        ticker_summary_rows
    )

    manifest = security[
        [
            "security_key",
            "canonical_company_name",
        ]
    ].merge(
        ticker_summary,
        on="security_key",
        how="left",
        validate="one_to_one",
    )

    manifest["ticker_segment_count"] = (
        pd.to_numeric(
            manifest["ticker_segment_count"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )
    manifest["multiple_ticker_segments_flag"] = (
        pd.to_numeric(
            manifest[
                "multiple_ticker_segments_flag"
            ],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    if "security_table_ticker" in security.columns:
        current_ticker_map = security.set_index(
            "security_key"
        )["security_table_ticker"]

        manifest["security_table_ticker"] = (
            manifest["security_key"].map(
                current_ticker_map
            )
        )
    else:
        manifest["security_table_ticker"] = ""

    manifest["canonical_company_name"] = (
        manifest["canonical_company_name"]
        .astype(str)
        .str.strip()
    )

    manifest["exact_legal_name_alias"] = (
        manifest["canonical_company_name"]
        .map(normalize_text)
    )

    manifest["suffix_stripped_alias_candidate"] = (
        manifest["canonical_company_name"]
        .map(suffix_stripped_candidate)
    )

    manifest["suffix_stripped_diff_flag"] = (
        manifest["exact_legal_name_alias"]
        != manifest[
            "suffix_stripped_alias_candidate"
        ]
    ).astype(int)

    manifest["base_token_count"] = (
        manifest["suffix_stripped_alias_candidate"]
        .str.split()
        .map(len)
    )

    manifest["base_alias_length"] = (
        manifest[
            "suffix_stripped_alias_candidate"
        ].str.len()
    )

    alias_counts = (
        manifest.groupby(
            "exact_legal_name_alias"
        )["security_key"]
        .transform("count")
    )

    manifest["exact_alias_security_count"] = (
        alias_counts.astype(int)
    )
    manifest["duplicate_exact_alias_flag"] = (
        manifest[
            "exact_alias_security_count"
        ] > 1
    ).astype(int)

    # Some legitimate issuer names are themselves short acronym/brand names
    # that may equal a stock ticker (for example CRH, EQT, FMC, LKQ, NOV, PTC,
    # PVH). This is not automatically an error. It is a controlled ambiguity
    # condition that must remain in the authoritative-name review queue.
    ticker_value_set = {
        normalize_text(value)
        for value in ticker_history["project_ticker"].astype(str)
        if str(value).strip()
    }

    manifest["ticker_like_exact_name_flag"] = (
        manifest["exact_legal_name_alias"]
        .isin(ticker_value_set)
    ).astype(int)

    def ambiguity_tier(row: pd.Series) -> str:
        if row["duplicate_exact_alias_flag"] == 1:
            return "HIGH"

        if (
            int(row["ticker_like_exact_name_flag"]) == 1
            or int(row["base_token_count"]) <= 1
            or int(row["base_alias_length"]) <= 8
        ):
            return "HIGH"

        if (
            int(row["base_token_count"]) == 2
            or int(
                row["multiple_ticker_segments_flag"]
            ) == 1
        ):
            return "MEDIUM"

        return "LOW"

    manifest["structural_ambiguity_tier"] = (
        manifest.apply(
            ambiguity_tier,
            axis=1,
        )
    )

    manifest["current_name_point_in_time_validated"] = 0
    manifest["production_alias_status"] = (
        "CANDIDATE_EXACT_NAME_ONLY_"
        "PENDING_PIT_NAME_HISTORY_REVIEW"
    )
    manifest["production_aliases_pipe"] = (
        manifest["exact_legal_name_alias"]
    )

    manifest["historical_name_review_flag"] = (
        (
            manifest[
                "multiple_ticker_segments_flag"
            ] == 1
        )
        | (
            manifest[
                "structural_ambiguity_tier"
            ].eq("HIGH")
        )
        | (
            manifest[
                "duplicate_exact_alias_flag"
            ] == 1
        )
        | (
            manifest[
                "ticker_like_exact_name_flag"
            ] == 1
        )
    ).astype(int)

    manifest = manifest.sort_values(
        [
            "structural_ambiguity_tier",
            "historical_name_review_flag",
            "latest_project_ticker",
            "security_key",
        ],
        ascending=[
            True,
            False,
            True,
            True,
        ],
    ).reset_index(drop=True)

    manifest.to_csv(
        MANIFEST_PATH,
        index=False,
    )

    collision = (
        manifest[
            manifest[
                "duplicate_exact_alias_flag"
            ] == 1
        ]
        .sort_values(
            [
                "exact_legal_name_alias",
                "security_key",
            ]
        )
    )
    collision.to_csv(
        ALIAS_COLLISION_PATH,
        index=False,
    )

    review_queue = (
        manifest[
            manifest[
                "historical_name_review_flag"
            ] == 1
        ]
        .copy()
    )

    tier_order = {
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3,
    }
    review_queue["review_priority"] = (
        review_queue[
            "structural_ambiguity_tier"
        ].map(tier_order)
    )

    review_queue["review_reason"] = (
        "PIT company-name history not yet validated"
    )

    review_queue.loc[
        review_queue[
            "multiple_ticker_segments_flag"
        ] == 1,
        "review_reason",
    ] += "; multiple ticker-history segments"

    review_queue.loc[
        review_queue[
            "duplicate_exact_alias_flag"
        ] == 1,
        "review_reason",
    ] += "; duplicate exact alias"

    review_queue.loc[
        review_queue[
            "ticker_like_exact_name_flag"
        ] == 1,
        "review_reason",
    ] += "; exact legal/current name is ticker-like and requires issuer-name confirmation"

    review_queue.loc[
        review_queue[
            "structural_ambiguity_tier"
        ].eq("HIGH"),
        "review_reason",
    ] += "; structurally ambiguous/short base name"

    review_queue = review_queue.sort_values(
        [
            "review_priority",
            "latest_project_ticker",
            "security_key",
        ]
    )

    review_queue.to_csv(
        REVIEW_QUEUE_PATH,
        index=False,
    )

    counts = (
        manifest[
            "structural_ambiguity_tier"
        ].value_counts()
        .to_dict()
    )

    lines = [
        "=" * 118,
        "H3 FULL-UNIVERSE COMPANY QUERY MANIFEST — CANDIDATE BUILD",
        "=" * 118,
        f"Security identities: {len(manifest)}",
        (
            "Ticker-history segments represented: "
            f"{int(manifest['ticker_segment_count'].sum())}"
        ),
        (
            "Identities with multiple ticker segments: "
            f"{int(manifest['multiple_ticker_segments_flag'].sum())}"
        ),
        (
            "Duplicate exact normalized aliases: "
            f"{int(manifest['duplicate_exact_alias_flag'].sum())} identities"
        ),
        (
            "HIGH structural ambiguity: "
            f"{int(counts.get('HIGH', 0))}"
        ),
        (
            "MEDIUM structural ambiguity: "
            f"{int(counts.get('MEDIUM', 0))}"
        ),
        (
            "LOW structural ambiguity: "
            f"{int(counts.get('LOW', 0))}"
        ),
        (
            "Ticker-like exact legal/current names: "
            f"{int(manifest['ticker_like_exact_name_flag'].sum())}"
        ),
        (
            "PIT/name-history review queue: "
            f"{len(review_queue)}"
        ),
        "",
        "IMPORTANT:",
        (
            "Canonical company-name source column detected: "
            f"{security_name_col}"
        ),
        (
            "This is a CANDIDATE manifest only. "
            "Current company names have not yet been validated "
            "point-in-time across 2021-2025."
        ),
        (
            "The suffix-stripped alias is diagnostic only and is "
            "NOT authorized as a production attention query."
        ),
        (
            "Production alias remains the normalized exact legal/current "
            "name until authoritative name-history review is completed."
        ),
        "Return/outcome fields read: 0",
        "",
        "H3_COMPANY_QUERY_MANIFEST_CANDIDATE_BUILD_COMPLETE",
    ]

    text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        text,
        encoding="utf-8",
    )
    print(text, end="")


if __name__ == "__main__":
    main()
