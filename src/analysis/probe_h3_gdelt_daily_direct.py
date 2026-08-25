from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import shutil
import sys
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v2-h3-direct-gdelt-csv-field-limit-fix"

MANIFEST_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_daily_pilot_query_manifest.csv"
)
ANCHORS_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_daily_pilot_anchor_windows.csv"
)

OUT_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)
CACHE_DIR = (
    ROOT / "data" / "interim"
    / "h3_gdelt_daily_pilot_cache"
)

REMOTE_BASE = "https://data.gdeltproject.org/gkg"

DOWNLOAD_MANIFEST_PATH = OUT_DIR / "h3_gdelt_daily_pilot_download_manifest.csv"
DAILY_COVERAGE_PATH = OUT_DIR / "h3_gdelt_daily_pilot_daily_coverage.csv"
ANCHOR_COVERAGE_PATH = OUT_DIR / "h3_gdelt_daily_pilot_anchor_coverage.csv"
VARIANT_PATH = OUT_DIR / "h3_gdelt_daily_pilot_org_variants.csv"
ESTIMATE_PATH = OUT_DIR / "h3_gdelt_daily_pilot_download_estimate.json"
RUN_REPORT_PATH = OUT_DIR / "h3_gdelt_daily_pilot_run_report.txt"

# GKG 1.0 daily graph-file field positions from the published codebook.
IDX_DATE = 0
IDX_NUMARTS = 1
IDX_ORGANIZATIONS = 6

REQUEST_TIMEOUT = 120
DOWNLOAD_CHUNK_BYTES = 1024 * 1024


def configure_csv_field_limit() -> int:
    """
    GDELT GKG rows can contain very large semicolon-delimited entity fields.
    Python's csv module defaults to a 131,072-byte field limit, which is too
    small for some valid GKG rows.

    Raise the limit to the largest value supported by this Python build.
    The fallback loop avoids OverflowError on platforms whose C integer size
    is smaller than sys.maxsize.
    """
    candidate = sys.maxsize

    while candidate > 131072:
        try:
            csv.field_size_limit(candidate)
            return int(candidate)
        except OverflowError:
            candidate //= 10

    csv.field_size_limit(131072)
    return 131072


def normalize_org(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def daterange(start: date, end_exclusive: date):
    current = start
    while current < end_exclusive:
        yield current
        current += timedelta(days=1)


def build_days(anchors: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in anchors.itertuples(index=False):
        start = date.fromisoformat(str(row.start_date))
        end_exclusive = date.fromisoformat(str(row.end_date_exclusive))

        for day in daterange(start, end_exclusive):
            ymd = day.strftime("%Y%m%d")
            rows.append(
                {
                    "anchor_id": str(row.anchor_id),
                    "date": day.isoformat(),
                    "ymd": ymd,
                    "url": f"{REMOTE_BASE}/{ymd}.gkg.csv.zip",
                }
            )

    result = pd.DataFrame(rows)

    if result["ymd"].duplicated().any():
        raise RuntimeError("Frozen anchor windows overlap.")

    return result


def remote_size(session: requests.Session, url: str) -> tuple[int | None, str]:
    """
    Prefer HEAD. If the server does not expose Content-Length, request byte 0
    only and inspect Content-Range without consuming the response body.
    """
    try:
        response = session.head(
            url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            length = response.headers.get("Content-Length")
            if length is not None:
                return int(length), "HEAD_CONTENT_LENGTH"
    except requests.RequestException:
        pass

    headers = {"Range": "bytes=0-0"}
    response = session.get(
        url,
        headers=headers,
        stream=True,
        allow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    )
    try:
        response.raise_for_status()

        content_range = response.headers.get("Content-Range", "")
        match = re.search(r"/(\d+)$", content_range)
        if match:
            return int(match.group(1)), "RANGE_CONTENT_RANGE"

        length = response.headers.get("Content-Length")
        if response.status_code == 206 and length:
            return int(length), "RANGE_CONTENT_LENGTH_PARTIAL"

        return None, "SIZE_UNKNOWN"
    finally:
        response.close()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    session: requests.Session,
    url: str,
    destination: Path,
) -> int:
    temp = destination.with_suffix(destination.suffix + ".part")

    with session.get(
        url,
        stream=True,
        allow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    ) as response:
        response.raise_for_status()

        with temp.open("wb") as handle:
            for chunk in response.iter_content(
                chunk_size=DOWNLOAD_CHUNK_BYTES
            ):
                if chunk:
                    handle.write(chunk)

    temp.replace(destination)
    return destination.stat().st_size


def compile_manifest(manifest: pd.DataFrame):
    compiled = {}

    for row in manifest.itertuples(index=False):
        ticker = str(row.ticker).upper()

        strict_aliases = {
            normalize_org(alias)
            for alias in str(row.strict_aliases_pipe).split("|")
            if normalize_org(alias)
        }

        compiled[ticker] = {
            "canonical_company_name": str(row.canonical_company_name),
            "ambiguity_tier": str(row.ambiguity_tier),
            "strict_aliases": strict_aliases,
            "broad_regex": re.compile(
                str(row.broad_variant_regex),
                flags=re.IGNORECASE,
            ),
        }

    return compiled


def parse_daily_gkg(
    zip_path: Path,
    compiled_manifest: dict,
) -> dict:
    configured_csv_field_limit = configure_csv_field_limit()

    total_source_documents = 0
    total_namesets = 0
    malformed_rows = 0

    matched_documents = Counter()
    matched_namesets = Counter()
    variant_documents = {
        ticker: Counter()
        for ticker in compiled_manifest
    }
    variant_namesets = {
        ticker: Counter()
        for ticker in compiled_manifest
    }

    with zipfile.ZipFile(zip_path) as archive:
        members = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".gkg.csv")
        ]

        if len(members) != 1:
            raise RuntimeError(
                f"{zip_path.name}: expected exactly one .gkg.csv member; "
                f"found {members}."
            )

        with archive.open(members[0], "r") as raw:
            text_stream = io.TextIOWrapper(
                raw,
                encoding="utf-8",
                errors="replace",
                newline="",
            )

            reader = csv.reader(
                text_stream,
                delimiter="\t",
                quoting=csv.QUOTE_NONE,
            )

            for fields in reader:
                if len(fields) <= IDX_ORGANIZATIONS:
                    malformed_rows += 1
                    continue

                try:
                    numarts = int(fields[IDX_NUMARTS])
                except (TypeError, ValueError):
                    malformed_rows += 1
                    continue

                if numarts < 0:
                    malformed_rows += 1
                    continue

                total_namesets += 1
                total_source_documents += numarts

                raw_org_field = fields[IDX_ORGANIZATIONS]

                if not raw_org_field:
                    continue

                raw_orgs = [
                    org.strip()
                    for org in raw_org_field.split(";")
                    if org.strip()
                ]

                normalized_orgs = {
                    normalize_org(org)
                    for org in raw_orgs
                    if normalize_org(org)
                }

                for ticker, config in compiled_manifest.items():
                    if (
                        config["strict_aliases"]
                        & normalized_orgs
                    ):
                        matched_documents[ticker] += numarts
                        matched_namesets[ticker] += 1

                    for raw_org in raw_orgs:
                        if config["broad_regex"].search(
                            raw_org.casefold()
                        ):
                            variant_key = normalize_org(raw_org)
                            if variant_key:
                                variant_documents[ticker][
                                    variant_key
                                ] += numarts
                                variant_namesets[ticker][
                                    variant_key
                                ] += 1

    return {
        "configured_csv_field_limit": configured_csv_field_limit,
        "total_source_documents": total_source_documents,
        "total_namesets": total_namesets,
        "malformed_rows": malformed_rows,
        "matched_documents": matched_documents,
        "matched_namesets": matched_namesets,
        "variant_documents": variant_documents,
        "variant_namesets": variant_namesets,
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Download and parse the 35 frozen daily files.",
    )
    parser.add_argument(
        "--max-download-gb",
        type=float,
        default=2.0,
        help=(
            "Maximum estimated compressed download size in decimal GB. "
            "Default: 2.0."
        ),
    )
    parser.add_argument(
        "--allow-unknown-size",
        action="store_true",
        help=(
            "Allow execution if one or more remote sizes cannot be "
            "determined. Use only after reviewing the URL list."
        ),
    )
    parser.add_argument(
        "--keep-cache",
        action="store_true",
        help="Retain raw downloaded ZIPs instead of deleting after parsing.",
    )

    args = parser.parse_args()

    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    manifest = pd.read_csv(MANIFEST_PATH)
    anchors = pd.read_csv(ANCHORS_PATH)

    if len(manifest) != 15:
        raise RuntimeError(
            f"Pilot manifest has {len(manifest)} rows; expected 15."
        )

    days = build_days(anchors)

    if len(days) != 35:
        raise RuntimeError(
            f"Frozen pilot has {len(days)} daily files; expected 35."
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "sp500-momentum-performance-analysis/"
                "h3-gdelt-feasibility-pilot"
            )
        }
    )

    print("Estimating direct GDELT download sizes...")

    size_rows = []

    for index, row in enumerate(
        days.itertuples(index=False),
        start=1,
    ):
        size, method = remote_size(
            session,
            str(row.url),
        )

        size_rows.append(
            {
                "anchor_id": row.anchor_id,
                "date": row.date,
                "ymd": row.ymd,
                "url": row.url,
                "remote_size_bytes": size,
                "size_method": method,
            }
        )

        print(
            f"  {index:02d}/35 {row.ymd}: "
            + (
                f"{size / 1_000_000:.1f} MB"
                if size is not None
                else "size unknown"
            )
        )

    size_frame = pd.DataFrame(size_rows)

    known_bytes = int(
        size_frame["remote_size_bytes"]
        .fillna(0)
        .sum()
    )
    unknown_count = int(
        size_frame["remote_size_bytes"]
        .isna()
        .sum()
    )
    estimated_gb = known_bytes / 1_000_000_000

    estimate = {
        "script_version": SCRIPT_VERSION,
        "daily_files": int(len(size_frame)),
        "known_size_files": int(
            len(size_frame) - unknown_count
        ),
        "unknown_size_files": unknown_count,
        "known_total_bytes": known_bytes,
        "known_total_decimal_gb": estimated_gb,
        "max_download_decimal_gb": args.max_download_gb,
        "execute_requested": bool(args.execute),
        "allow_unknown_size": bool(args.allow_unknown_size),
        "keep_cache": bool(args.keep_cache),
        "google_cloud_used": False,
        "azure_sql_used": False,
    }

    ESTIMATE_PATH.write_text(
        json.dumps(estimate, indent=2) + "\n",
        encoding="utf-8",
    )

    print("")
    print(
        f"Known estimated compressed download: "
        f"{estimated_gb:.3f} GB"
    )
    print(
        f"Files with unknown remote size: {unknown_count}/35"
    )

    if not args.execute:
        report = [
            "H3 DIRECT GDELT DAILY PILOT — ESTIMATE ONLY",
            f"Daily files: {len(size_frame)}",
            (
                "Known estimated compressed download: "
                f"{estimated_gb:.3f} GB"
            ),
            f"Unknown-size files: {unknown_count}",
            f"Configured download cap: {args.max_download_gb:.3f} GB",
            "Google Cloud used: NO",
            "Azure SQL used: NO",
            "Attention values retrieved: NO",
            "Returns/outcomes read: NO",
            "",
            (
                "To execute after reviewing the estimate:\n"
                "python src\\analysis\\probe_h3_gdelt_daily_direct.py "
                f"--max-download-gb {args.max_download_gb} --execute"
            ),
            "",
            "H3_DIRECT_GDELT_DAILY_PILOT_ESTIMATE_COMPLETE",
        ]

        RUN_REPORT_PATH.write_text(
            "\n".join(report) + "\n",
            encoding="utf-8",
        )
        print("\n".join(report))
        return

    if estimated_gb > args.max_download_gb:
        raise RuntimeError(
            f"Execution refused: estimated known download "
            f"{estimated_gb:.3f} GB exceeds cap "
            f"{args.max_download_gb:.3f} GB."
        )

    if unknown_count > 0 and not args.allow_unknown_size:
        raise RuntimeError(
            f"Execution refused: {unknown_count} file sizes are unknown. "
            "Review the estimate and rerun with --allow-unknown-size "
            "only if desired."
        )

    compiled = compile_manifest(manifest)

    daily_rows = []
    download_rows = []
    all_variants_docs = {
        ticker: Counter()
        for ticker in compiled
    }
    all_variants_namesets = {
        ticker: Counter()
        for ticker in compiled
    }

    for index, row in enumerate(
        days.itertuples(index=False),
        start=1,
    ):
        destination = (
            CACHE_DIR / f"{row.ymd}.gkg.csv.zip"
        )

        print(
            f"[{index:02d}/35] Downloading {row.ymd}..."
        )

        if destination.exists():
            downloaded_bytes = destination.stat().st_size
            cache_status = "REUSED_EXISTING_CACHE"
        else:
            downloaded_bytes = download_file(
                session,
                row.url,
                destination,
            )
            cache_status = "DOWNLOADED"

        digest = sha256_file(destination)

        parsed = parse_daily_gkg(
            destination,
            compiled,
        )

        total_docs = int(
            parsed["total_source_documents"]
        )

        for ticker, config in compiled.items():
            matched_docs = int(
                parsed["matched_documents"][ticker]
            )
            matched_namesets = int(
                parsed["matched_namesets"][ticker]
            )

            daily_rows.append(
                {
                    "anchor_id": row.anchor_id,
                    "date": row.date,
                    "ticker": ticker,
                    "canonical_company_name": config[
                        "canonical_company_name"
                    ],
                    "ambiguity_tier": config[
                        "ambiguity_tier"
                    ],
                    "matched_source_documents": matched_docs,
                    "matched_namesets": matched_namesets,
                    "total_source_documents": total_docs,
                    "total_namesets": int(
                        parsed["total_namesets"]
                    ),
                    "malformed_rows": int(
                        parsed["malformed_rows"]
                    ),
                    "configured_csv_field_limit": int(
                        parsed["configured_csv_field_limit"]
                    ),
                    "news_attention_share": (
                        matched_docs / total_docs
                        if total_docs > 0
                        else math.nan
                    ),
                    "mentions_per_100k_source_documents": (
                        100000.0
                        * matched_docs
                        / total_docs
                        if total_docs > 0
                        else math.nan
                    ),
                }
            )

            all_variants_docs[ticker].update(
                parsed["variant_documents"][ticker]
            )
            all_variants_namesets[ticker].update(
                parsed["variant_namesets"][ticker]
            )

        download_rows.append(
            {
                "anchor_id": row.anchor_id,
                "date": row.date,
                "url": row.url,
                "downloaded_bytes": downloaded_bytes,
                "sha256": digest,
                "cache_status": cache_status,
                "deleted_after_parse": int(
                    not args.keep_cache
                ),
            }
        )

        if not args.keep_cache:
            destination.unlink(
                missing_ok=True
            )

    daily = pd.DataFrame(daily_rows)
    daily.to_csv(
        DAILY_COVERAGE_PATH,
        index=False,
    )

    download_manifest = pd.DataFrame(
        download_rows
    )
    download_manifest.to_csv(
        DOWNLOAD_MANIFEST_PATH,
        index=False,
    )

    anchor = (
        daily.groupby(
            [
                "anchor_id",
                "ticker",
                "canonical_company_name",
                "ambiguity_tier",
            ],
            as_index=False,
        )
        .agg(
            matched_source_documents=(
                "matched_source_documents",
                "sum",
            ),
            matched_namesets=(
                "matched_namesets",
                "sum",
            ),
            total_source_documents=(
                "total_source_documents",
                "sum",
            ),
            total_namesets=(
                "total_namesets",
                "sum",
            ),
            malformed_rows=(
                "malformed_rows",
                "sum",
            ),
        )
    )

    anchor["news_attention_share"] = (
        anchor["matched_source_documents"]
        / anchor["total_source_documents"]
    )
    anchor[
        "mentions_per_100k_source_documents"
    ] = (
        100000.0
        * anchor["matched_source_documents"]
        / anchor["total_source_documents"]
    )

    anchor.to_csv(
        ANCHOR_COVERAGE_PATH,
        index=False,
    )

    variant_rows = []

    for ticker, config in compiled.items():
        for rank, (
            variant,
            doc_count,
        ) in enumerate(
            all_variants_docs[ticker].most_common(30),
            start=1,
        ):
            variant_rows.append(
                {
                    "ticker": ticker,
                    "canonical_company_name": config[
                        "canonical_company_name"
                    ],
                    "ambiguity_tier": config[
                        "ambiguity_tier"
                    ],
                    "variant_rank": rank,
                    "normalized_organization_variant": variant,
                    "weighted_source_documents": int(
                        doc_count
                    ),
                    "nameset_rows": int(
                        all_variants_namesets[ticker][
                            variant
                        ]
                    ),
                    "is_strict_alias": int(
                        variant
                        in config["strict_aliases"]
                    ),
                }
            )

    variants = pd.DataFrame(
        variant_rows
    )
    variants.to_csv(
        VARIANT_PATH,
        index=False,
    )

    coverage_summary = (
        anchor.assign(
            nonzero=(
                anchor[
                    "matched_source_documents"
                ] > 0
            ).astype(int)
        )
        .groupby(
            [
                "ticker",
                "ambiguity_tier",
            ],
            as_index=False,
        )
        .agg(
            nonzero_anchor_windows=(
                "nonzero",
                "sum",
            ),
            total_matched_source_documents=(
                "matched_source_documents",
                "sum",
            ),
        )
    )

    usable = int(
        (
            coverage_summary[
                "nonzero_anchor_windows"
            ] >= 2
        ).sum()
    )

    report = [
        "H3 DIRECT GDELT DAILY FEASIBILITY PILOT — EXECUTED",
        f"Pilot companies: {len(manifest)}",
        f"Anchor windows: {len(anchors)}",
        f"Daily GKG files processed: {len(days)}",
        (
            "Companies with strict nonzero organization coverage "
            f"in >=2/5 anchor windows: {usable}/{len(manifest)}"
        ),
        (
            "Compressed files retained after processing: "
            f"{'YES' if args.keep_cache else 'NO'}"
        ),
        "Google Cloud used: NO",
        "BigQuery used: NO",
        "Azure SQL used: NO",
        "Returns/outcomes read: NO",
        "",
        "H3_DIRECT_GDELT_DAILY_PILOT_EXECUTION_COMPLETE",
    ]

    RUN_REPORT_PATH.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )
    print("")
    print("\n".join(report))


if __name__ == "__main__":
    main()
