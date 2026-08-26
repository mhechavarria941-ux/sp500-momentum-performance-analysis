from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import time
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-gdelt-alias-coverage-missingness-gate"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
CACHE_DIR = ROOT / "data" / "interim" / "h3_gdelt_stage3k"
RAW_DIR = CACHE_DIR / "raw"
DAILY_DIR = CACHE_DIR / "daily"
META_DIR = CACHE_DIR / "metadata"

CONFIG_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_alias_coverage_missingness_gate_v1.json"
)
MANIFEST_PATH = H3_DIR / "h3_pit_attention_alias_intervals.csv"
STAGE3J_AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_pit_attention_alias_manifest_integrity_audit.txt"
)

SOURCE_FILES_PATH = H3_DIR / "h3_gdelt_stage3k_source_files.csv"
DAILY_SECURITY_PATH = H3_DIR / "h3_gdelt_stage3k_daily_security_attention.csv"
WINDOW_SECURITY_PATH = H3_DIR / "h3_gdelt_stage3k_window_security_coverage.csv"
SECURITY_SUMMARY_PATH = H3_DIR / "h3_gdelt_stage3k_security_coverage_summary.csv"
WINDOW_SUMMARY_PATH = H3_DIR / "h3_gdelt_stage3k_window_summary.csv"
REPORT_PATH = H3_DIR / "h3_gdelt_stage3k_coverage_gate_report.txt"

EXPECTED_STAGE3J_POLICY_ID = "H3_PIT_ATTENTION_ALIAS_POLICY_V5"
STAGE3J_PASS_TOKEN = "H3_PIT_ATTENTION_ALIAS_MANIFEST_INTEGRITY_AUDIT_PASSED"

LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "ltd", "limited", "plc", "llc", "llp", "lp", "nv", "ag", "se", "sa",
}


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_full(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    raw = unicodedata.normalize("NFKC", str(value)).casefold()

    # Frozen provider/display corrections from Stage 3J.
    raw = re.sub(r"/\s*the\s*$", " ", raw)
    raw = re.sub(
        r"/\s*(?:de|md|mo|mn|ny|oh|nj|pa|va|ca|tx)\s*/",
        " ",
        raw,
    )

    raw = raw.replace("&", " and ")
    raw = re.sub(r"[’']", "", raw)
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    if raw.startswith("the "):
        raw = raw[4:].strip()

    tokens = raw.split()

    if len(tokens) >= 2 and tokens[-2] in {"class", "cl"}:
        tokens = tokens[:-2]

    return " ".join(tokens).strip()


def normalize_core(value: object) -> str:
    tokens = normalize_full(value).split()

    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens = tokens[:-1]

    return " ".join(tokens).strip()


def all_anchor_dates(config: dict) -> list[tuple[str, pd.Timestamp]]:
    rows: list[tuple[str, pd.Timestamp]] = []

    for window in config["sample"]["anchor_windows"]:
        start = pd.Timestamp(window["start"])
        end = pd.Timestamp(window["end_exclusive"])
        current = start

        while current < end:
            rows.append((window["window_id"], current))
            current += timedelta(days=1)

    return rows


def download_file(url: str, destination: Path, attempts: int = 4) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")

    if temp.exists():
        temp.unlink()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 H3-SP500-Attention-Research/1.0 "
            "(academic reproducibility pilot)"
        )
    }

    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(request, timeout=120) as response:
                with temp.open("wb") as handle:
                    shutil.copyfileobj(response, handle)

            if temp.stat().st_size <= 0:
                raise RuntimeError("Downloaded file is empty.")

            temp.replace(destination)
            return

        except Exception as exc:
            last_error = exc

            if temp.exists():
                temp.unlink()

            if attempt < attempts:
                time.sleep(min(2 ** attempt, 20))

    raise RuntimeError(
        f"Download failed after {attempts} attempts: {url} | {last_error}"
    )


def active_alias_rows(
    manifest: pd.DataFrame,
    date: pd.Timestamp,
) -> pd.DataFrame:
    return manifest[
        (manifest["alias_valid_from_dt"] <= date)
        & (manifest["alias_valid_to_dt"] > date)
    ].copy()


def parse_gkg_daily(
    zip_path: Path,
    active_aliases: set[str],
) -> tuple[int, int, int, dict[str, int]]:
    """
    Returns:
      parsed_rows,
      malformed_rows,
      total_source_document_weight,
      alias -> matched source-document weight
    """
    parsed_rows = 0
    malformed_rows = 0
    total_weight = 0
    alias_weight = defaultdict(int)

    # Large organization/name fields are legitimate in GKG.
    csv.field_size_limit(256 * 1024 * 1024)

    with zipfile.ZipFile(zip_path, "r") as archive:
        members = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
        ]

        if len(members) != 1:
            raise RuntimeError(
                f"Expected one member in {zip_path.name}; found {len(members)}."
            )

        with archive.open(members[0], "r") as binary:
            with io.TextIOWrapper(
                binary,
                encoding="utf-8",
                errors="replace",
                newline="",
            ) as text:
                reader = csv.reader(text, delimiter="\t")

                for fields in reader:
                    if len(fields) <= 6:
                        malformed_rows += 1
                        continue

                    try:
                        weight = int(fields[1])
                    except Exception:
                        malformed_rows += 1
                        continue

                    if weight < 0:
                        malformed_rows += 1
                        continue

                    parsed_rows += 1
                    total_weight += weight

                    organizations = fields[6]

                    if not organizations or not active_aliases:
                        continue

                    matched_aliases: set[str] = set()

                    for raw_org in organizations.split(";"):
                        raw_org = raw_org.strip()

                        if not raw_org:
                            continue

                        full = normalize_full(raw_org)
                        core = normalize_core(raw_org)

                        if full in active_aliases:
                            matched_aliases.add(full)

                        if core in active_aliases:
                            matched_aliases.add(core)

                    for alias in matched_aliases:
                        alias_weight[alias] += weight

    return (
        parsed_rows,
        malformed_rows,
        total_weight,
        dict(alias_weight),
    )


def self_test() -> None:
    cases = {
        "Cigna Group/The": ("cigna group", "cigna group"),
        "The Cigna Group": ("cigna group", "cigna group"),
        "RTX Corporation": ("rtx corporation", "rtx"),
        "Campbell's Company/The": ("campbells company", "campbells"),
    }

    for raw, expected in cases.items():
        observed = (normalize_full(raw), normalize_core(raw))

        if observed != expected:
            raise RuntimeError(
                f"Normalization self-test failed for {raw!r}: "
                f"{observed!r} != {expected!r}"
            )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    self_test()

    for path in (
        CONFIG_PATH,
        MANIFEST_PATH,
        STAGE3J_AUDIT_PATH,
    ):
        require(path)

    audit_text = STAGE3J_AUDIT_PATH.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if STAGE3J_PASS_TOKEN not in audit_text:
        raise RuntimeError(
            "Stage 3J alias-manifest integrity audit has not passed."
        )

    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    config = json.loads(config_text)
    config_sha = hashlib.sha256(
        config_text.encode("utf-8")
    ).hexdigest()

    manifest = pd.read_csv(
        MANIFEST_PATH,
        dtype=str,
        keep_default_na=False,
    )

    if not manifest["policy_id"].eq(
        EXPECTED_STAGE3J_POLICY_ID
    ).all():
        raise RuntimeError(
            "Stage 3J manifest policy ID differs from frozen V5 prerequisite."
        )

    manifest["alias_valid_from_dt"] = pd.to_datetime(
        manifest["alias_valid_from"],
        errors="raise",
    )
    manifest["alias_valid_to_dt"] = pd.to_datetime(
        manifest["alias_valid_to_exclusive"],
        errors="raise",
    )

    manifest_sha = sha256_file(MANIFEST_PATH)

    for directory in (
        CACHE_DIR,
        RAW_DIR,
        DAILY_DIR,
        META_DIR,
        H3_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    source_rows = []
    daily_security_frames = []

    dates = all_anchor_dates(config)

    if len(dates) != int(
        config["sample"]["expected_daily_files"]
    ):
        raise RuntimeError(
            f"Anchor-date count={len(dates)}, expected "
            f"{config['sample']['expected_daily_files']}."
        )

    for ordinal, (window_id, date) in enumerate(dates, start=1):
        ymd = date.strftime("%Y%m%d")
        url = config["source"]["url_template"].replace(
            "{YYYYMMDD}",
            ymd,
        )

        raw_path = RAW_DIR / f"{ymd}.gkg.csv.zip"
        daily_path = DAILY_DIR / f"{ymd}_security_attention.csv"
        meta_path = META_DIR / f"{ymd}.json"

        active = active_alias_rows(manifest, date)

        if active["security_key"].duplicated().any():
            duplicated = sorted(
                active.loc[
                    active["security_key"].duplicated(keep=False),
                    "security_key",
                ].unique()
            )
            raise RuntimeError(
                f"{ymd}: multiple active aliases for security_key(s): "
                f"{duplicated[:10]}"
            )

        active_aliases = set(
            active["production_alias"].astype(str)
        )

        cache_reused = False
        metadata = {}

        if daily_path.exists() and meta_path.exists():
            try:
                metadata = json.loads(
                    meta_path.read_text(encoding="utf-8")
                )

                cache_reused = (
                    metadata.get("script_version")
                    == SCRIPT_VERSION
                    and metadata.get("manifest_sha256")
                    == manifest_sha
                    and metadata.get("config_sha256")
                    == config_sha
                    and metadata.get("date")
                    == date.date().isoformat()
                )
            except Exception:
                cache_reused = False

        if cache_reused:
            daily = pd.read_csv(
                daily_path,
                dtype=str,
                keep_default_na=False,
            )

            # Convert numeric fields back for aggregation.
            for column in (
                "matched_source_document_weight",
                "total_source_document_weight",
                "strict_nonzero_day_flag",
            ):
                daily[column] = pd.to_numeric(
                    daily[column],
                    errors="raise",
                )

            daily["attention_share"] = pd.to_numeric(
                daily["attention_share"],
                errors="raise",
            )

            status = "REUSED_VALID_CACHE"

        else:
            print(
                f"[{ordinal:02d}/{len(dates)}] Downloading {ymd} "
                f"({len(active)} active securities)..."
            )

            download_file(url, raw_path)
            file_sha = sha256_file(raw_path)
            file_bytes = raw_path.stat().st_size

            (
                parsed_rows,
                malformed_rows,
                total_weight,
                alias_weight,
            ) = parse_gkg_daily(
                raw_path,
                active_aliases,
            )

            if total_weight <= 0:
                raise RuntimeError(
                    f"{ymd}: non-positive GKG denominator."
                )

            output_rows = []

            for row in active.itertuples(index=False):
                matched = int(
                    alias_weight.get(
                        str(row.production_alias),
                        0,
                    )
                )

                share = matched / total_weight

                output_rows.append({
                    "date": date.date().isoformat(),
                    "window_id": window_id,
                    "security_key": row.security_key,
                    "issuer_cik": row.issuer_cik,
                    "latest_project_ticker": row.latest_project_ticker,
                    "structural_ambiguity_tier": row.structural_ambiguity_tier,
                    "alias_selection_reason": row.alias_selection_reason,
                    "authoritative_name_source_layer": row.authoritative_name_source_layer,
                    "production_alias": row.production_alias,
                    "matched_source_document_weight": matched,
                    "total_source_document_weight": total_weight,
                    "attention_share": share,
                    "strict_nonzero_day_flag": int(matched > 0),
                    "stage3j_policy_id": row.policy_id,
                    "stage3j_policy_sha256": row.policy_sha256,
                    "stage3k_config_sha256": config_sha,
                })

            daily = pd.DataFrame(output_rows)
            daily.to_csv(daily_path, index=False)

            malformed_rate = (
                malformed_rows
                / (parsed_rows + malformed_rows)
                if (parsed_rows + malformed_rows) > 0
                else 1.0
            )

            metadata = {
                "date": date.date().isoformat(),
                "window_id": window_id,
                "source_url": url,
                "source_file_sha256": file_sha,
                "source_file_bytes": file_bytes,
                "parsed_rows": parsed_rows,
                "malformed_rows": malformed_rows,
                "malformed_row_rate": malformed_rate,
                "total_source_document_weight": total_weight,
                "active_security_count": len(active),
                "unique_active_alias_count": len(active_aliases),
                "manifest_sha256": manifest_sha,
                "config_sha256": config_sha,
                "script_version": SCRIPT_VERSION,
            }

            meta_path.write_text(
                json.dumps(
                    metadata,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            # Raw source file is intentionally not retained.
            if raw_path.exists():
                raw_path.unlink()

            status = "DOWNLOADED_PARSED_RAW_DELETED"

        source_rows.append({
            "date": date.date().isoformat(),
            "window_id": window_id,
            "source_url": metadata.get("source_url", url),
            "source_file_sha256": metadata.get(
                "source_file_sha256", ""
            ),
            "source_file_bytes": metadata.get(
                "source_file_bytes", ""
            ),
            "parsed_rows": metadata.get("parsed_rows", ""),
            "malformed_rows": metadata.get("malformed_rows", ""),
            "malformed_row_rate": metadata.get(
                "malformed_row_rate", ""
            ),
            "total_source_document_weight": metadata.get(
                "total_source_document_weight", ""
            ),
            "active_security_count": metadata.get(
                "active_security_count", len(active)
            ),
            "unique_active_alias_count": metadata.get(
                "unique_active_alias_count",
                len(active_aliases),
            ),
            "status": status,
            "manifest_sha256": manifest_sha,
            "config_sha256": config_sha,
            "script_version": SCRIPT_VERSION,
        })

        daily_security_frames.append(daily)

    source_files = pd.DataFrame(source_rows)
    daily_security = pd.concat(
        daily_security_frames,
        ignore_index=True,
    )

    source_files.to_csv(
        SOURCE_FILES_PATH,
        index=False,
    )
    daily_security.to_csv(
        DAILY_SECURITY_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Window-security aggregation.
    # --------------------------------------------------------------
    window_security = (
        daily_security.groupby(
            [
                "window_id",
                "security_key",
                "issuer_cik",
                "latest_project_ticker",
                "structural_ambiguity_tier",
                "alias_selection_reason",
                "authoritative_name_source_layer",
            ],
            as_index=False,
        )
        .agg(
            eligible_days=("date", "nunique"),
            nonzero_days=("strict_nonzero_day_flag", "sum"),
            matched_source_document_weight=(
                "matched_source_document_weight",
                "sum",
            ),
            total_source_document_weight=(
                "total_source_document_weight",
                "sum",
            ),
        )
    )

    window_security["attention_share"] = (
        window_security["matched_source_document_weight"]
        / window_security["total_source_document_weight"]
    )
    window_security["strict_nonzero_window_flag"] = (
        window_security["matched_source_document_weight"] > 0
    ).astype(int)

    window_security.to_csv(
        WINDOW_SECURITY_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Security summary.
    # --------------------------------------------------------------
    security_summary = (
        window_security.groupby(
            [
                "security_key",
                "issuer_cik",
                "latest_project_ticker",
                "structural_ambiguity_tier",
            ],
            as_index=False,
        )
        .agg(
            eligible_anchor_windows=(
                "window_id",
                "nunique",
            ),
            nonzero_anchor_windows=(
                "strict_nonzero_window_flag",
                "sum",
            ),
            total_matched_source_document_weight=(
                "matched_source_document_weight",
                "sum",
            ),
            total_source_document_weight=(
                "total_source_document_weight",
                "sum",
            ),
        )
    )

    security_summary["any_nonzero_window_flag"] = (
        security_summary["nonzero_anchor_windows"] > 0
    ).astype(int)
    security_summary["two_plus_nonzero_windows_flag"] = (
        security_summary["nonzero_anchor_windows"] >= 2
    ).astype(int)
    security_summary["nonzero_window_rate"] = (
        security_summary["nonzero_anchor_windows"]
        / security_summary["eligible_anchor_windows"]
    )

    security_summary.to_csv(
        SECURITY_SUMMARY_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Window summary.
    # --------------------------------------------------------------
    window_summary = (
        window_security.groupby(
            "window_id",
            as_index=False,
        )
        .agg(
            eligible_security_count=(
                "security_key",
                "nunique",
            ),
            strict_nonzero_security_count=(
                "strict_nonzero_window_flag",
                "sum",
            ),
            total_matched_source_document_weight=(
                "matched_source_document_weight",
                "sum",
            ),
            total_source_document_weight=(
                "total_source_document_weight",
                "sum",
            ),
        )
    )

    window_summary["strict_nonzero_security_rate"] = (
        window_summary["strict_nonzero_security_count"]
        / window_summary["eligible_security_count"]
    )

    window_summary.to_csv(
        WINDOW_SUMMARY_PATH,
        index=False,
    )

    eligible = security_summary[
        security_summary["eligible_anchor_windows"] >= 1
    ]
    eligible_2plus = security_summary[
        security_summary["eligible_anchor_windows"] >= 2
    ]
    high = eligible[
        eligible["structural_ambiguity_tier"].eq("HIGH")
    ]

    any_nonzero_rate = (
        eligible["any_nonzero_window_flag"].mean()
        if len(eligible) else 0.0
    )
    repeat_nonzero_rate = (
        eligible_2plus[
            "two_plus_nonzero_windows_flag"
        ].mean()
        if len(eligible_2plus) else 0.0
    )
    security_window_nonzero_rate = (
        window_security[
            "strict_nonzero_window_flag"
        ].mean()
        if len(window_security) else 0.0
    )
    high_any_nonzero_rate = (
        high["any_nonzero_window_flag"].mean()
        if len(high) else 0.0
    )

    lines = [
        "=" * 128,
        "H3 STAGE 3K — DIRECT GDELT ALIAS COVERAGE & MISSINGNESS GATE",
        "=" * 128,
        f"Gate ID: {config['gate_id']}",
        f"Gate SHA-256: {config_sha}",
        f"Stage 3J manifest SHA-256: {manifest_sha}",
        f"Daily GDELT files: {len(source_files)}",
        f"Eligible securities across anchor windows: {len(eligible)}",
        f"Eligible security-window observations: {len(window_security)}",
        "",
        "STRICT COVERAGE METRICS:",
        f"  Any-nonzero security rate: {any_nonzero_rate:.6f}",
        f"  Repeat nonzero rate among securities eligible >=2 windows: {repeat_nonzero_rate:.6f}",
        f"  Nonzero security-window rate: {security_window_nonzero_rate:.6f}",
        f"  HIGH-ambiguity any-nonzero security rate: {high_any_nonzero_rate:.6f}",
        "",
        "THRESHOLDS:",
        f"  Any-nonzero security rate >= {config['coverage_thresholds']['minimum_any_nonzero_security_rate']:.2f}",
        (
            "  Repeat nonzero rate among eligible >=2 windows >= "
            f"{config['coverage_thresholds']['minimum_repeat_nonzero_rate_among_securities_eligible_2plus_windows']:.2f}"
        ),
        f"  Nonzero security-window rate >= {config['coverage_thresholds']['minimum_nonzero_security_window_rate']:.2f}",
        (
            "  HIGH-ambiguity any-nonzero security rate >= "
            f"{config['coverage_thresholds']['minimum_high_ambiguity_any_nonzero_rate']:.2f}"
        ),
        "",
        "Raw daily GDELT zip retention: NONE after successful parse",
        "Full-history GDELT extraction performed: NO",
        "Return/outcome fields read: 0",
        "",
        "H3_GDELT_ALIAS_COVERAGE_MISSINGNESS_PILOT_COMPLETE",
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )
    print(report, end="")


if __name__ == "__main__":
    main()
