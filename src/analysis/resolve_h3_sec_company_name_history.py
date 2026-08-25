from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-h3-sec-name-history-resolution"

IN_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)
MANIFEST_PATH = IN_DIR / "h3_company_query_manifest_candidates.csv"

OUT_DIR = IN_DIR

SEC_TICKERS_CACHE = (
    ROOT / "data" / "interim" / "h3_sec"
    / "company_tickers.json"
)
SEC_CIK_LOOKUP_CACHE = (
    ROOT / "data" / "interim" / "h3_sec"
    / "cik-lookup-data.txt"
)
SEC_SUBMISSIONS_CACHE_DIR = (
    ROOT / "data" / "interim" / "h3_sec"
    / "submissions"
)

MAPPING_PATH = OUT_DIR / "h3_sec_cik_mapping_candidates.csv"
METADATA_PATH = OUT_DIR / "h3_sec_submissions_company_metadata.csv"
FORMER_NAMES_PATH = OUT_DIR / "h3_sec_former_names_raw.csv"
REVIEW_QUEUE_PATH = OUT_DIR / "h3_sec_identity_resolution_review_queue.csv"
DOWNLOAD_LOG_PATH = OUT_DIR / "h3_sec_submissions_download_log.csv"
REPORT_PATH = OUT_DIR / "h3_sec_name_history_resolution_report.txt"

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_CIK_LOOKUP_URL = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"

EXPECTED_SECURITY_ROWS = 593
DEFAULT_REQUEST_INTERVAL_SECONDS = 0.15

AUTO_STATUSES = {
    "AUTO_SOURCE_AGREEMENT",
    "AUTO_EXACT_TICKER_AND_NAME",
    "AUTO_UNIQUE_EXACT_NAME",
}

VALID_STATUSES = AUTO_STATUSES | {
    "REVIEW_TICKER_ONLY",
    "REVIEW_CONFLICT",
    "UNRESOLVED",
}


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_ticker(value: object) -> str:
    return str(value).strip().upper().replace(".", "-")


def sec_user_agent() -> str:
    value = os.getenv("SEC_USER_AGENT", "").strip()
    if not value:
        raise RuntimeError(
            "SEC_USER_AGENT is required for programmatic SEC access.\n"
            "Example PowerShell:\n"
            '$env:SEC_USER_AGENT="Your Name your.email@example.com"'
        )
    if "@" not in value:
        raise RuntimeError(
            "SEC_USER_AGENT should identify you and include a contact email."
        )
    return value


def session_with_headers(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov",
        }
    )
    return session


def download(
    session: requests.Session,
    url: str,
    path: Path,
    force: bool,
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not force:
        return "REUSED_CACHE"

    response = session.get(url, timeout=120)
    response.raise_for_status()
    path.write_bytes(response.content)
    return "DOWNLOADED"


def load_company_tickers(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))

    rows = []
    if isinstance(payload, dict):
        iterable = payload.values()
    else:
        iterable = payload

    for item in iterable:
        rows.append(
            {
                "sec_cik": str(int(item["cik_str"])).zfill(10),
                "sec_ticker": normalize_ticker(item.get("ticker", "")),
                "sec_title": str(item.get("title", "")).strip(),
                "sec_title_normalized": normalize_text(item.get("title", "")),
            }
        )

    return pd.DataFrame(rows)


def load_cik_lookup(path: Path) -> pd.DataFrame:
    rows = []

    with path.open("r", encoding="latin-1", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\r\n")
            if not line:
                continue

            # Historical SEC lookup format is typically ENTITY NAME:CIK:
            # Use rsplit so colons inside a company name do not break parsing.
            parts = line.rsplit(":", 2)
            if len(parts) < 2:
                continue

            name = parts[0].strip()
            cik_raw = parts[1].strip()

            if not cik_raw.isdigit():
                continue

            rows.append(
                {
                    "lookup_name": name,
                    "lookup_name_normalized": normalize_text(name),
                    "sec_cik": str(int(cik_raw)).zfill(10),
                }
            )

    return pd.DataFrame(rows).drop_duplicates()


def unique_ciks(values: Iterable[str]) -> list[str]:
    return sorted(
        {
            str(value).zfill(10)
            for value in values
            if str(value).strip()
        }
    )


def map_identity(
    row: pd.Series,
    tickers: pd.DataFrame,
    cik_lookup: pd.DataFrame,
) -> dict:
    project_ticker = normalize_ticker(row.get("latest_project_ticker", ""))
    exact_name = normalize_text(row["canonical_company_name"])

    ticker_matches = (
        tickers.loc[
            tickers["sec_ticker"].eq(project_ticker)
        ]
        if project_ticker
        else tickers.iloc[0:0]
    )

    ticker_ciks = unique_ciks(ticker_matches["sec_cik"])

    current_name_matches = tickers.loc[
        tickers["sec_title_normalized"].eq(exact_name)
    ]
    current_name_ciks = unique_ciks(current_name_matches["sec_cik"])

    historical_name_matches = cik_lookup.loc[
        cik_lookup["lookup_name_normalized"].eq(exact_name)
    ]
    historical_name_ciks = unique_ciks(
        historical_name_matches["sec_cik"]
    )

    name_ciks = unique_ciks(
        current_name_ciks + historical_name_ciks
    )

    overlap = sorted(set(ticker_ciks) & set(name_ciks))

    status = "UNRESOLVED"
    candidate_cik = ""
    rationale = "No unique SEC ticker or exact-name mapping."

    if len(overlap) == 1:
        candidate_cik = overlap[0]
        status = "AUTO_SOURCE_AGREEMENT"
        rationale = (
            "Project ticker and exact normalized company name agree "
            "on one SEC CIK."
        )
    elif len(ticker_ciks) == 1:
        ticker_cik = ticker_ciks[0]
        ticker_name_exact = bool(
            (
                ticker_matches["sec_cik"].eq(ticker_cik)
                & ticker_matches["sec_title_normalized"].eq(exact_name)
            ).any()
        )

        if ticker_name_exact:
            candidate_cik = ticker_cik
            status = "AUTO_EXACT_TICKER_AND_NAME"
            rationale = (
                "Unique SEC ticker match has the exact normalized "
                "company name."
            )
        elif len(name_ciks) == 1 and name_ciks[0] != ticker_cik:
            status = "REVIEW_CONFLICT"
            rationale = (
                f"Unique ticker candidate {ticker_cik} conflicts "
                f"with unique exact-name candidate {name_ciks[0]}."
            )
        else:
            candidate_cik = ticker_cik
            status = "REVIEW_TICKER_ONLY"
            rationale = (
                "Ticker maps uniquely, but exact normalized company "
                "name did not independently confirm the same CIK."
            )
    elif len(name_ciks) == 1 and len(ticker_ciks) == 0:
        candidate_cik = name_ciks[0]
        status = "AUTO_UNIQUE_EXACT_NAME"
        rationale = (
            "Exact normalized company name maps uniquely in official "
            "SEC current/historical name sources."
        )
    elif len(ticker_ciks) > 1 or len(name_ciks) > 1:
        status = "REVIEW_CONFLICT"
        rationale = (
            "SEC mapping is non-unique and requires authoritative review."
        )

    return {
        "security_key": row["security_key"],
        "latest_project_ticker": row.get("latest_project_ticker", ""),
        "canonical_company_name": row["canonical_company_name"],
        "exact_legal_name_alias": row["exact_legal_name_alias"],
        "structural_ambiguity_tier": row["structural_ambiguity_tier"],
        "historical_name_review_flag": row["historical_name_review_flag"],
        "ticker_like_exact_name_flag": row.get(
            "ticker_like_exact_name_flag", "0"
        ),
        "ticker_candidate_ciks_pipe": "|".join(ticker_ciks),
        "current_exact_name_ciks_pipe": "|".join(current_name_ciks),
        "historical_exact_name_ciks_pipe": "|".join(historical_name_ciks),
        "candidate_sec_cik": candidate_cik,
        "mapping_status": status,
        "mapping_rationale": rationale,
    }


def submissions_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
    )
    return session


def fetch_submission_json(
    session: requests.Session,
    cik10: str,
    force: bool,
    interval: float,
) -> tuple[dict | None, str, str]:
    path = SEC_SUBMISSIONS_CACHE_DIR / f"CIK{cik10}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not force:
        try:
            return (
                json.loads(path.read_text(encoding="utf-8")),
                "REUSED_CACHE",
                "",
            )
        except Exception as exc:
            return None, "CACHE_PARSE_FAILED", str(exc)

    url = SEC_SUBMISSIONS_URL.format(cik10=cik10)

    try:
        response = session.get(url, timeout=120)
        status_code = response.status_code
        response.raise_for_status()
        path.write_bytes(response.content)
        payload = response.json()
        time.sleep(interval)
        return payload, f"DOWNLOADED_HTTP_{status_code}", ""
    except Exception as exc:
        time.sleep(interval)
        return None, "DOWNLOAD_FAILED", str(exc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Redownload official SEC mapping and submission files.",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL_SECONDS,
        help="Seconds between SEC submissions requests. Default: 0.15.",
    )
    args = parser.parse_args()

    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Missing Stage 3A manifest: {MANIFEST_PATH}"
        )

    manifest = pd.read_csv(
        MANIFEST_PATH,
        dtype=str,
        keep_default_na=False,
    )

    if len(manifest) != EXPECTED_SECURITY_ROWS:
        raise RuntimeError(
            f"Stage 3A manifest rows={len(manifest)}, expected 593."
        )

    user_agent = sec_user_agent()

    # ------------------------------------------------------------------
    # Download SEC official mapping files.
    # ------------------------------------------------------------------
    mapping_session = session_with_headers(user_agent)

    ticker_status = download(
        mapping_session,
        SEC_COMPANY_TICKERS_URL,
        SEC_TICKERS_CACHE,
        args.force_refresh,
    )

    cik_lookup_status = download(
        mapping_session,
        SEC_CIK_LOOKUP_URL,
        SEC_CIK_LOOKUP_CACHE,
        args.force_refresh,
    )

    tickers = load_company_tickers(SEC_TICKERS_CACHE)
    cik_lookup = load_cik_lookup(SEC_CIK_LOOKUP_CACHE)

    # ------------------------------------------------------------------
    # Deterministic mapping candidates.
    # ------------------------------------------------------------------
    mapping_rows = [
        map_identity(
            row,
            tickers,
            cik_lookup,
        )
        for _, row in manifest.iterrows()
    ]

    mapping = pd.DataFrame(mapping_rows)

    if not set(mapping["mapping_status"]).issubset(VALID_STATUSES):
        raise RuntimeError("Unexpected SEC mapping status.")

    # ------------------------------------------------------------------
    # Fetch submissions metadata for every unique candidate CIK, including
    # review-only ticker candidates. This is evidence gathering, not automatic
    # acceptance of review cases.
    # ------------------------------------------------------------------
    candidate_ciks = unique_ciks(
        mapping["candidate_sec_cik"]
    )

    submission_session = submissions_session(user_agent)

    metadata_rows = []
    former_name_rows = []
    download_rows = []

    for index, cik10 in enumerate(candidate_ciks, start=1):
        print(
            f"[{index:03d}/{len(candidate_ciks):03d}] "
            f"SEC submissions CIK {cik10}"
        )

        payload, status, error = fetch_submission_json(
            submission_session,
            cik10,
            args.force_refresh,
            args.request_interval,
        )

        download_rows.append(
            {
                "sec_cik": cik10,
                "download_status": status,
                "error": error,
            }
        )

        if payload is None:
            continue

        sec_name = str(payload.get("name", "")).strip()
        sec_tickers = payload.get("tickers") or []
        sec_exchanges = payload.get("exchanges") or []
        former_names = payload.get("formerNames") or []

        metadata_rows.append(
            {
                "sec_cik": cik10,
                "sec_current_name": sec_name,
                "sec_current_name_normalized": normalize_text(sec_name),
                "sec_tickers_pipe": "|".join(
                    str(x) for x in sec_tickers
                ),
                "sec_exchanges_pipe": "|".join(
                    str(x) for x in sec_exchanges
                ),
                "former_name_count": len(former_names),
                "entity_type": str(payload.get("entityType", "")),
                "sic": str(payload.get("sic", "")),
                "sic_description": str(
                    payload.get("sicDescription", "")
                ),
            }
        )

        for position, item in enumerate(former_names, start=1):
            former_name_rows.append(
                {
                    "sec_cik": cik10,
                    "former_name_position": position,
                    "former_name": str(item.get("name", "")).strip(),
                    "former_name_normalized": normalize_text(
                        item.get("name", "")
                    ),
                    "former_name_from": str(item.get("from", "")),
                    "former_name_to": str(item.get("to", "")),
                }
            )

    metadata = pd.DataFrame(metadata_rows)
    former_names = pd.DataFrame(
        former_name_rows,
        columns=[
            "sec_cik",
            "former_name_position",
            "former_name",
            "former_name_normalized",
            "former_name_from",
            "former_name_to",
        ],
    )
    download_log = pd.DataFrame(download_rows)

    # Attach SEC submissions evidence to mapping.
    if not metadata.empty:
        mapping = mapping.merge(
            metadata[
                [
                    "sec_cik",
                    "sec_current_name",
                    "sec_current_name_normalized",
                    "sec_tickers_pipe",
                    "former_name_count",
                ]
            ],
            left_on="candidate_sec_cik",
            right_on="sec_cik",
            how="left",
            validate="many_to_one",
        ).drop(columns=["sec_cik"])
    else:
        mapping["sec_current_name"] = ""
        mapping["sec_current_name_normalized"] = ""
        mapping["sec_tickers_pipe"] = ""
        mapping["former_name_count"] = ""

    mapping["sec_current_name_exact_match_flag"] = (
        mapping["sec_current_name_normalized"]
        .eq(
            mapping["exact_legal_name_alias"]
        )
    ).astype(int)

    mapping["former_name_evidence_flag"] = (
        pd.to_numeric(
            mapping["former_name_count"],
            errors="coerce",
        )
        .fillna(0)
        .gt(0)
        .astype(int)
    )

    # A Stage 3B resolution queue includes:
    # - every non-auto mapping;
    # - every identity with SEC former-name evidence;
    # - every Stage 3A historical-name review case;
    # - every ticker-like exact company name.
    mapping["sec_resolution_review_flag"] = (
        ~mapping["mapping_status"].isin(AUTO_STATUSES)
        | mapping["former_name_evidence_flag"].eq(1)
        | mapping["historical_name_review_flag"].eq("1")
        | mapping["ticker_like_exact_name_flag"].eq("1")
        | mapping["sec_current_name_exact_match_flag"].eq(0)
    ).astype(int)

    review_queue = mapping.loc[
        mapping["sec_resolution_review_flag"].eq(1)
    ].copy()

    status_priority = {
        "REVIEW_CONFLICT": 1,
        "UNRESOLVED": 1,
        "REVIEW_TICKER_ONLY": 2,
        "AUTO_SOURCE_AGREEMENT": 3,
        "AUTO_EXACT_TICKER_AND_NAME": 3,
        "AUTO_UNIQUE_EXACT_NAME": 3,
    }

    review_queue["review_priority"] = (
        review_queue["mapping_status"]
        .map(status_priority)
        .fillna(9)
        .astype(int)
    )

    review_queue["review_reason"] = ""

    review_queue.loc[
        ~review_queue["mapping_status"].isin(AUTO_STATUSES),
        "review_reason",
    ] += "SEC CIK mapping not auto-resolved; "

    review_queue.loc[
        review_queue["former_name_evidence_flag"].eq(1),
        "review_reason",
    ] += "SEC former-name evidence present; "

    review_queue.loc[
        review_queue["historical_name_review_flag"].eq("1"),
        "review_reason",
    ] += "Stage 3A PIT/name-history review flag; "

    review_queue.loc[
        review_queue["ticker_like_exact_name_flag"].eq("1"),
        "review_reason",
    ] += "ticker-like exact company name; "

    review_queue.loc[
        review_queue["sec_current_name_exact_match_flag"].eq(0),
        "review_reason",
    ] += "SEC current name differs from project exact name; "

    review_queue["review_reason"] = (
        review_queue["review_reason"]
        .str.rstrip("; ")
    )

    review_queue = review_queue.sort_values(
        [
            "review_priority",
            "structural_ambiguity_tier",
            "latest_project_ticker",
            "security_key",
        ]
    )

    # ------------------------------------------------------------------
    # Save outputs.
    # ------------------------------------------------------------------
    mapping.to_csv(MAPPING_PATH, index=False)
    metadata.to_csv(METADATA_PATH, index=False)
    former_names.to_csv(FORMER_NAMES_PATH, index=False)
    review_queue.to_csv(REVIEW_QUEUE_PATH, index=False)
    download_log.to_csv(DOWNLOAD_LOG_PATH, index=False)

    status_counts = mapping["mapping_status"].value_counts().to_dict()
    mapped_count = int(mapping["candidate_sec_cik"].ne("").sum())
    auto_count = int(mapping["mapping_status"].isin(AUTO_STATUSES).sum())
    former_identity_count = int(
        mapping["former_name_evidence_flag"].eq(1).sum()
    )
    download_failures = int(
        download_log["download_status"].eq("DOWNLOAD_FAILED").sum()
    )

    lines = [
        "=" * 116,
        "H3 STAGE 3B — SEC COMPANY IDENTITY / NAME-HISTORY RESOLUTION",
        "=" * 116,
        f"Stage 3A identities: {len(mapping)}",
        f"Identities with a candidate SEC CIK: {mapped_count}",
        f"Auto-resolved SEC mappings: {auto_count}",
        (
            "Identities with SEC former-name evidence: "
            f"{former_identity_count}"
        ),
        (
            "Unique SEC submission files requested/reused: "
            f"{len(candidate_ciks)}"
        ),
        f"SEC submissions download failures: {download_failures}",
        f"Stage 3B review queue: {len(review_queue)}",
        "",
        "Mapping status counts:",
    ]

    for status in sorted(VALID_STATUSES):
        lines.append(
            f"  {status}: {int(status_counts.get(status, 0))}"
        )

    lines += [
        "",
        f"SEC company_tickers source: {ticker_status}",
        f"SEC CIK historical lookup source: {cik_lookup_status}",
        "Return/outcome fields read: 0",
        "GDELT full-history extraction performed: NO",
        "",
        "IMPORTANT:",
        (
            "AUTO mapping means the CIK mapping is sufficiently deterministic "
            "for this resolution stage. It does NOT mean the company-name "
            "history is production-ready."
        ),
        (
            "SEC formerNames are retained as raw authoritative evidence. "
            "No PIT attention alias intervals are created in this script."
        ),
        "",
        "H3_SEC_NAME_HISTORY_RESOLUTION_COMPLETE",
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
