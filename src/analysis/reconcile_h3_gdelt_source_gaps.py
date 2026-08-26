from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-26-v2-h3-gdelt-source-gap-reconciliation-transition-month-fix"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"
ANALYSIS_DIR = ROOT / "src" / "analysis"

POLICY_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_gdelt_source_gap_handling_v1.json"
)
BASE_PROTOCOL_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_full_gdelt_attention_extraction_v1.json"
)
MANIFEST_PATH = H3_DIR / "h3_pit_attention_alias_intervals.csv"

RUNNER_PATH = ANALYSIS_DIR / "run_h3_full_gdelt_attention_extraction.py"

CACHE_ROOT = ROOT / "data" / "interim" / "h3_gdelt_full"
RAW_DIR = CACHE_ROOT / "raw"
DAILY_CACHE_DIR = CACHE_ROOT / "daily_security"
META_DIR = CACHE_ROOT / "metadata"

SOURCE_LEDGER_PATH = H3_DIR / "h3_gdelt_full_source_files.csv"
GAP_DAYS_PATH = H3_DIR / "h3_gdelt_full_source_gap_days.csv"
MONTH_COVERAGE_PATH = H3_DIR / "h3_gdelt_full_calendar_month_source_coverage.csv"
YEAR_COVERAGE_PATH = H3_DIR / "h3_gdelt_full_year_source_coverage.csv"
MONTHLY_PATH = H3_DIR / "h3_gdelt_full_monthly_security_attention.csv"
REPORT_PATH = H3_DIR / "h3_gdelt_source_gap_reconciliation_report.txt"
TRANSITION_MONTH_DIAGNOSTICS_PATH = H3_DIR / "h3_gdelt_transition_month_metadata_diagnostics.csv"

YEARLY_TEMPLATE = "h3_gdelt_full_daily_security_{year}.csv.gz"


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as h:
        for block in iter(lambda: h.read(1024 * 1024), b""):
            d.update(block)
    return d.hexdigest()


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "h3_stage3l_runner",
        RUNNER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Stage 3L runner module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def all_dates(base: dict) -> list[pd.Timestamp]:
    return list(
        pd.date_range(
            start=base["source"]["date_start"],
            end=pd.Timestamp(base["source"]["date_end_exclusive"])
            - pd.Timedelta(days=1),
            freq="D",
        )
    )


def active_alias_rows(
    manifest: pd.DataFrame,
    date: pd.Timestamp,
) -> pd.DataFrame:
    return manifest[
        (manifest["alias_valid_from_dt"] <= date)
        & (manifest["alias_valid_to_dt"] > date)
    ].copy()


def cache_valid_for_base(
    runner,
    meta_path: Path,
    daily_path: Path,
    *,
    date: pd.Timestamp,
    manifest_sha: str,
    base_protocol_sha: str,
    base: dict,
) -> bool:
    return runner.cache_valid(
        meta_path,
        daily_path,
        date=date,
        manifest_sha=manifest_sha,
        protocol_sha=base_protocol_sha,
        cache_schema_version=base["cache"]["schema_version"],
        parser_contract_version=base["cache"]["parser_contract_version"],
    )


def source_row_from_meta(
    meta: dict,
    *,
    date: pd.Timestamp,
    status: str,
    catalog_listed: int,
    catalog_md5: str,
    catalog_size: object,
    source_gap_policy_sha: str,
) -> dict:
    return {
        "date": date.date().isoformat(),
        "year": date.year,
        "month": date.strftime("%Y-%m"),
        "source_url": meta.get("source_url", ""),
        "resolved_source_url": meta.get(
            "resolved_source_url",
            meta.get("source_url", ""),
        ),
        "source_file_sha256": meta.get("source_file_sha256", ""),
        "source_file_md5": meta.get("source_file_md5", ""),
        "source_file_bytes": meta.get("source_file_bytes", ""),
        "parsed_rows": meta.get("parsed_rows", ""),
        "malformed_rows": meta.get("malformed_rows", ""),
        "malformed_row_rate": meta.get("malformed_row_rate", ""),
        "total_source_document_weight": meta.get(
            "total_source_document_weight", ""
        ),
        "active_security_count": meta.get("active_security_count", ""),
        "unique_active_alias_count": meta.get(
            "unique_active_alias_count", ""
        ),
        "status": status,
        "catalog_listed_flag": catalog_listed,
        "catalog_md5": catalog_md5,
        "catalog_size_bytes": catalog_size,
        "source_available_flag": 1,
        "source_gap_class": "",
        "source_gap_policy_sha256": source_gap_policy_sha,
    }


def build_gap_row(
    *,
    date: pd.Timestamp,
    url: str,
    active: pd.DataFrame,
    catalog_listed: int,
    catalog_md5: str,
    catalog_size: object,
    gap_class: str,
    error: str,
    source_gap_policy_sha: str,
) -> dict:
    return {
        "date": date.date().isoformat(),
        "year": date.year,
        "month": date.strftime("%Y-%m"),
        "source_url": url,
        "resolved_source_url": "",
        "source_file_sha256": "",
        "source_file_md5": "",
        "source_file_bytes": "",
        "parsed_rows": "",
        "malformed_rows": "",
        "malformed_row_rate": "",
        "total_source_document_weight": "",
        "active_security_count": len(active),
        "unique_active_alias_count": active["production_alias"].nunique(),
        "status": "DOCUMENTED_SOURCE_GAP",
        "catalog_listed_flag": catalog_listed,
        "catalog_md5": catalog_md5,
        "catalog_size_bytes": catalog_size,
        "source_available_flag": 0,
        "source_gap_class": gap_class,
        "source_gap_error": error,
        "source_gap_policy_sha256": source_gap_policy_sha,
    }



def collapse_unique_strings(values: pd.Series) -> str:
    unique = sorted(
        {
            str(value).strip()
            for value in values
            if str(value).strip()
        }
    )
    return "|".join(unique)


def build_security_month_panel(
    *,
    all_daily: pd.DataFrame,
    manifest: pd.DataFrame,
    base: dict,
    manifest_sha: str,
    base_sha: str,
    policy_sha: str,
    diagnostics_path: Path,
) -> pd.DataFrame:
    """
    Build exactly one row per security-month.

    IMPORTANT:
    Alias/name-transition metadata must NOT be part of the groupby key.
    A security can validly use two PIT aliases inside one calendar month
    (for example RTX in 2023-07 or SLB in 2025-10).

    The measurement unit remains security-month. Transition metadata is
    summarized diagnostically rather than splitting the measurement row.
    """
    daily = all_daily.copy()

    for column in (
        "matched_source_document_weight",
        "total_source_document_weight",
        "strict_nonzero_day_flag",
    ):
        daily[column] = pd.to_numeric(
            daily[column],
            errors="raise",
        )

    stable_columns = [
        "issuer_cik",
        "latest_project_ticker",
        "structural_ambiguity_tier",
    ]

    # --------------------------------------------------------------
    # Validate that identity-level metadata is stable inside each
    # security-month. Transition-dependent fields are deliberately
    # excluded from this invariant.
    # --------------------------------------------------------------
    stability = (
        daily.groupby(
            ["month", "security_key"],
            as_index=False,
        )
        .agg(
            issuer_cik_nunique=("issuer_cik", "nunique"),
            latest_project_ticker_nunique=(
                "latest_project_ticker", "nunique"
            ),
            structural_ambiguity_tier_nunique=(
                "structural_ambiguity_tier", "nunique"
            ),
            production_alias_nunique=(
                "production_alias", "nunique"
            ),
            alias_selection_reason_nunique=(
                "alias_selection_reason", "nunique"
            ),
            authoritative_name_source_layer_nunique=(
                "authoritative_name_source_layer", "nunique"
            ),
        )
    )

    bad_stability = stability[
        (stability["issuer_cik_nunique"] > 1)
        | (stability["latest_project_ticker_nunique"] > 1)
        | (stability["structural_ambiguity_tier_nunique"] > 1)
    ].copy()

    transition_months = stability[
        (stability["production_alias_nunique"] > 1)
        | (stability["alias_selection_reason_nunique"] > 1)
        | (
            stability[
                "authoritative_name_source_layer_nunique"
            ]
            > 1
        )
    ].copy()

    # Enrich the transition-month diagnostic with the exact PIT states.
    if not transition_months.empty:
        detail = (
            daily.merge(
                transition_months[
                    ["month", "security_key"]
                ],
                on=["month", "security_key"],
                how="inner",
            )
            .groupby(
                ["month", "security_key"],
                as_index=False,
            )
            .agg(
                issuer_cik=(
                    "issuer_cik",
                    collapse_unique_strings,
                ),
                latest_project_ticker=(
                    "latest_project_ticker",
                    collapse_unique_strings,
                ),
                structural_ambiguity_tier=(
                    "structural_ambiguity_tier",
                    collapse_unique_strings,
                ),
                production_aliases_pipe=(
                    "production_alias",
                    collapse_unique_strings,
                ),
                alias_selection_reasons_pipe=(
                    "alias_selection_reason",
                    collapse_unique_strings,
                ),
                authoritative_name_source_layers_pipe=(
                    "authoritative_name_source_layer",
                    collapse_unique_strings,
                ),
                first_available_date=("date", "min"),
                last_available_date=("date", "max"),
            )
        )
    else:
        detail = pd.DataFrame(
            columns=[
                "month",
                "security_key",
                "issuer_cik",
                "latest_project_ticker",
                "structural_ambiguity_tier",
                "production_aliases_pipe",
                "alias_selection_reasons_pipe",
                "authoritative_name_source_layers_pipe",
                "first_available_date",
                "last_available_date",
            ]
        )

    detail.to_csv(
        diagnostics_path,
        index=False,
    )

    if not bad_stability.empty:
        sample = bad_stability.head(20).to_dict(
            orient="records"
        )
        raise RuntimeError(
            "Identity-level metadata is not stable within "
            "security-month for "
            f"{len(bad_stability)} row(s). Sample={sample}. "
            f"Inspect {diagnostics_path.name}."
        )

    # --------------------------------------------------------------
    # Aggregate the MEASUREMENT at security-month level.
    # Transition-dependent metadata becomes pipe-delimited provenance.
    # --------------------------------------------------------------
    monthly = (
        daily.groupby(
            ["month", "security_key"],
            as_index=False,
        )
        .agg(
            issuer_cik=("issuer_cik", "first"),
            latest_project_ticker=(
                "latest_project_ticker", "first"
            ),
            structural_ambiguity_tier=(
                "structural_ambiguity_tier", "first"
            ),
            source_available_days=("date", "nunique"),
            nonzero_days=(
                "strict_nonzero_day_flag", "sum"
            ),
            matched_source_document_weight=(
                "matched_source_document_weight", "sum"
            ),
            total_source_document_weight=(
                "total_source_document_weight", "sum"
            ),
            unique_aliases_in_month=(
                "production_alias", "nunique"
            ),
            production_aliases_pipe=(
                "production_alias",
                collapse_unique_strings,
            ),
            alias_selection_reasons_pipe=(
                "alias_selection_reason",
                collapse_unique_strings,
            ),
            authoritative_name_source_layers_pipe=(
                "authoritative_name_source_layer",
                collapse_unique_strings,
            ),
        )
    )

    if monthly[
        ["month", "security_key"]
    ].duplicated().any():
        duplicates = monthly.loc[
            monthly[
                ["month", "security_key"]
            ].duplicated(keep=False),
            ["month", "security_key"],
        ]
        raise RuntimeError(
            "Corrected security-month aggregation still "
            "contains duplicate keys: "
            f"{duplicates.head(20).to_dict(orient='records')}"
        )

    # --------------------------------------------------------------
    # Expected PIT-active calendar days, including source-gap days.
    # Multiple alias intervals inside a month are summed into the
    # same security-month expectation.
    # --------------------------------------------------------------
    expected_rows = []

    for row in manifest.itertuples(index=False):
        start = max(
            pd.Timestamp(row.alias_valid_from),
            pd.Timestamp(
                base["source"]["date_start"]
            ),
        )
        end = min(
            pd.Timestamp(
                row.alias_valid_to_exclusive
            ),
            pd.Timestamp(
                base["source"]["date_end_exclusive"]
            ),
        )

        if start >= end:
            continue

        current = start

        while current < end:
            month = current.strftime("%Y-%m")
            month_end = (
                current.to_period("M")
                .end_time.normalize()
                + pd.Timedelta(days=1)
            )
            segment_end = min(end, month_end)

            expected_rows.append(
                {
                    "month": month,
                    "security_key": row.security_key,
                    "expected_active_calendar_days": (
                        segment_end - current
                    ).days,
                }
            )
            current = segment_end

    expected = pd.DataFrame(expected_rows)

    expected = (
        expected.groupby(
            ["month", "security_key"],
            as_index=False,
        )["expected_active_calendar_days"]
        .sum()
    )

    if expected[
        ["month", "security_key"]
    ].duplicated().any():
        raise RuntimeError(
            "Expected PIT-active calendar-day panel "
            "contains duplicate security-month keys."
        )

    monthly = monthly.merge(
        expected,
        on=["month", "security_key"],
        how="left",
        validate="one_to_one",
    )

    if monthly[
        "expected_active_calendar_days"
    ].isna().any():
        raise RuntimeError(
            "A monthly attention row failed to map to its "
            "expected PIT-active calendar days."
        )

    monthly["source_missing_days"] = (
        monthly["expected_active_calendar_days"]
        - monthly["source_available_days"]
    )

    if (
        monthly["source_missing_days"] < 0
    ).any():
        bad = monthly.loc[
            monthly["source_missing_days"] < 0,
            [
                "month",
                "security_key",
                "source_available_days",
                "expected_active_calendar_days",
            ],
        ]
        raise RuntimeError(
            "Source-available days exceed expected PIT-active "
            "calendar days. Sample="
            f"{bad.head(20).to_dict(orient='records')}"
        )

    monthly["source_coverage_rate"] = (
        monthly["source_available_days"]
        / monthly["expected_active_calendar_days"]
    )
    monthly["attention_share"] = (
        monthly["matched_source_document_weight"]
        / monthly["total_source_document_weight"]
    )
    monthly["strict_nonzero_month_flag"] = (
        monthly[
            "matched_source_document_weight"
        ]
        > 0
    ).astype(int)
    monthly["source_gap_month_flag"] = (
        monthly["source_missing_days"] > 0
    ).astype(int)
    monthly["pit_alias_transition_month_flag"] = (
        monthly["unique_aliases_in_month"] > 1
    ).astype(int)

    monthly["stage3j_manifest_sha256"] = (
        manifest_sha
    )
    monthly["stage3l_protocol_sha256"] = base_sha
    monthly["source_gap_policy_sha256"] = policy_sha

    return monthly.sort_values(
        ["month", "security_key"]
    ).reset_index(drop=True)

def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        POLICY_PATH,
        BASE_PROTOCOL_PATH,
        MANIFEST_PATH,
        RUNNER_PATH,
    ):
        require(path)

    runner = load_runner()

    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    policy = json.loads(policy_text)
    policy_sha = hashlib.sha256(
        policy_text.encode("utf-8")
    ).hexdigest()

    base_text = BASE_PROTOCOL_PATH.read_text(encoding="utf-8")
    base = json.loads(base_text)
    base_sha = hashlib.sha256(
        base_text.encode("utf-8")
    ).hexdigest()

    manifest = pd.read_csv(
        MANIFEST_PATH,
        dtype=str,
        keep_default_na=False,
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

    dates = all_dates(base)
    expected_days = int(base["source"]["expected_daily_files"])
    if len(dates) != expected_days:
        raise RuntimeError(
            f"Calendar dates={len(dates)}, expected {expected_days}."
        )

    catalog = runner.load_gdelt_catalog()
    if not catalog:
        raise RuntimeError(
            "Official GDELT catalog could not be loaded; source-gap "
            "classification is not authorized without it."
        )

    source_rows = []
    newly_acquired = 0
    available_cache = 0
    gap_count = 0

    for ordinal, date in enumerate(dates, start=1):
        ymd = date.strftime("%Y%m%d")
        filename = f"{ymd}.gkg.csv.zip"
        url = base["source"]["url_template"].replace(
            "{YYYYMMDD}", ymd
        )

        raw_path = RAW_DIR / filename
        daily_path = (
            DAILY_CACHE_DIR
            / f"{ymd}_security_attention.csv.gz"
        )
        meta_path = META_DIR / f"{ymd}.json"

        active = active_alias_rows(manifest, date)
        if active["security_key"].duplicated().any():
            raise RuntimeError(
                f"{ymd}: duplicate active security aliases."
            )

        entry = catalog.get(filename, {})
        listed = int(bool(entry))
        catalog_md5 = str(
            entry.get("catalog_md5", "")
        ).strip()
        catalog_size = entry.get(
            "catalog_size_bytes", ""
        )

        if cache_valid_for_base(
            runner,
            meta_path,
            daily_path,
            date=date,
            manifest_sha=manifest_sha,
            base_protocol_sha=base_sha,
            base=base,
        ):
            meta = json.loads(
                meta_path.read_text(encoding="utf-8")
            )
            source_rows.append(
                source_row_from_meta(
                    meta,
                    date=date,
                    status="AVAILABLE_VALID_CACHE",
                    catalog_listed=listed,
                    catalog_md5=catalog_md5,
                    catalog_size=catalog_size,
                    source_gap_policy_sha=policy_sha,
                )
            )
            available_cache += 1
            continue

        attempts = (
            int(
                policy["reconciliation"][
                    "catalog_listed_retry_attempts_per_endpoint"
                ]
            )
            if listed
            else int(
                policy["reconciliation"][
                    "catalog_absent_direct_probe_attempts_per_endpoint"
                ]
            )
        )

        print(
            f"[{ordinal:04d}/{len(dates)}] reconcile {date.date()} | "
            f"catalog_listed={listed} | attempts/endpoint={attempts}"
        )

        try:
            info = runner.download_file(
                url,
                raw_path,
                attempts=attempts,
                expected_md5=catalog_md5,
                expected_size=catalog_size,
            )

            raw_sha = sha256_file(raw_path)
            raw_bytes = raw_path.stat().st_size

            (
                parsed_rows,
                malformed_rows,
                total_weight,
                alias_weight,
            ) = runner.parse_gkg_daily(
                raw_path,
                set(
                    active["production_alias"].astype(str)
                ),
            )

            if total_weight <= 0:
                raise RuntimeError(
                    f"{ymd}: non-positive source denominator."
                )

            malformed_rate = (
                malformed_rows
                / (parsed_rows + malformed_rows)
                if parsed_rows + malformed_rows
                else 1.0
            )

            daily = runner.build_daily_output(
                date=date,
                active=active,
                alias_weight=alias_weight,
                total_weight=total_weight,
                stage3j_manifest_sha=manifest_sha,
                protocol_sha=base_sha,
            )
            daily.to_csv(
                daily_path,
                index=False,
                compression="gzip",
            )

            meta = {
                "date": date.date().isoformat(),
                "source_url": url,
                "resolved_source_url": info[
                    "resolved_url"
                ],
                "source_file_sha256": raw_sha,
                "source_file_md5": info[
                    "source_file_md5"
                ],
                "source_file_bytes": raw_bytes,
                "parsed_rows": parsed_rows,
                "malformed_rows": malformed_rows,
                "malformed_row_rate": malformed_rate,
                "total_source_document_weight": total_weight,
                "active_security_count": len(active),
                "unique_active_alias_count": active[
                    "production_alias"
                ].nunique(),
                "stage3j_manifest_sha256": manifest_sha,
                "protocol_sha256": base_sha,
                "cache_schema_version": base["cache"][
                    "schema_version"
                ],
                "parser_contract_version": base["cache"][
                    "parser_contract_version"
                ],
                "runner_script_version": SCRIPT_VERSION,
                "source_gap_reconciliation_flag": 1,
                "catalog_listed_flag": listed,
                "catalog_md5": catalog_md5,
                "catalog_size_bytes": catalog_size,
            }
            meta_path.write_text(
                json.dumps(
                    meta,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            if raw_path.exists():
                raw_path.unlink()

            source_rows.append(
                source_row_from_meta(
                    meta,
                    date=date,
                    status="ACQUIRED_DURING_SOURCE_GAP_RECONCILIATION",
                    catalog_listed=listed,
                    catalog_md5=catalog_md5,
                    catalog_size=catalog_size,
                    source_gap_policy_sha=policy_sha,
                )
            )
            newly_acquired += 1

        except Exception as exc:
            if raw_path.exists():
                raw_path.unlink()

            gap_class = (
                "CATALOG_LISTED_BUT_UNDELIVERABLE_AFTER_RETRIES"
                if listed
                else
                "OFFICIAL_CATALOG_ABSENT_AND_DIRECT_UNAVAILABLE"
            )

            source_rows.append(
                build_gap_row(
                    date=date,
                    url=url,
                    active=active,
                    catalog_listed=listed,
                    catalog_md5=catalog_md5,
                    catalog_size=catalog_size,
                    gap_class=gap_class,
                    error=str(exc),
                    source_gap_policy_sha=policy_sha,
                )
            )
            gap_count += 1

    source = pd.DataFrame(source_rows).sort_values("date")
    source.to_csv(
        SOURCE_LEDGER_PATH,
        index=False,
    )

    gaps = source[
        pd.to_numeric(
            source["source_available_flag"],
            errors="raise",
        ).eq(0)
    ].copy()
    gaps.to_csv(
        GAP_DAYS_PATH,
        index=False,
    )

    available_dates = set(
        source.loc[
            pd.to_numeric(
                source["source_available_flag"],
                errors="raise",
            ).eq(1),
            "date",
        ]
    )

    # ----------------------------------------------------------
    # Global calendar coverage.
    # ----------------------------------------------------------
    source["source_available_flag"] = pd.to_numeric(
        source["source_available_flag"],
        errors="raise",
    )

    month_coverage = (
        source.groupby("month", as_index=False)
        .agg(
            expected_calendar_days=("date", "size"),
            source_available_days=(
                "source_available_flag", "sum"
            ),
        )
    )
    month_coverage["source_missing_days"] = (
        month_coverage["expected_calendar_days"]
        - month_coverage["source_available_days"]
    )
    month_coverage["source_coverage_rate"] = (
        month_coverage["source_available_days"]
        / month_coverage["expected_calendar_days"]
    )
    month_coverage.to_csv(
        MONTH_COVERAGE_PATH,
        index=False,
    )

    year_coverage = (
        source.groupby("year", as_index=False)
        .agg(
            expected_calendar_days=("date", "size"),
            source_available_days=(
                "source_available_flag", "sum"
            ),
        )
    )
    year_coverage["source_missing_days"] = (
        year_coverage["expected_calendar_days"]
        - year_coverage["source_available_days"]
    )
    year_coverage["source_coverage_rate"] = (
        year_coverage["source_available_days"]
        / year_coverage["expected_calendar_days"]
    )
    year_coverage.to_csv(
        YEAR_COVERAGE_PATH,
        index=False,
    )

    # ----------------------------------------------------------
    # Consolidate available daily caches into yearly shards.
    # ----------------------------------------------------------
    yearly_paths = []
    daily_frames_for_monthly = []

    for year in range(2021, 2026):
        year_dates = [
            date
            for date in dates
            if date.year == year
            and date.date().isoformat() in available_dates
        ]

        frames = []
        for date in year_dates:
            path = (
                DAILY_CACHE_DIR
                / f"{date.strftime('%Y%m%d')}_security_attention.csv.gz"
            )
            require(path)
            frames.append(
                pd.read_csv(
                    path,
                    dtype=str,
                    keep_default_na=False,
                    compression="gzip",
                )
            )

        if not frames:
            raise RuntimeError(
                f"{year}: no available daily source caches."
            )

        year_df = pd.concat(
            frames,
            ignore_index=True,
        )
        if year_df[
            ["date", "security_key"]
        ].duplicated().any():
            raise RuntimeError(
                f"{year}: duplicate security-date rows."
            )

        output_path = (
            H3_DIR
            / YEARLY_TEMPLATE.format(year=year)
        )
        year_df.to_csv(
            output_path,
            index=False,
            compression="gzip",
        )
        yearly_paths.append(output_path)
        daily_frames_for_monthly.append(year_df)

    # ----------------------------------------------------------
    # Monthly attention over available source days.
    #
    # V2 correction:
    # The measurement unit is security-month. PIT alias/source metadata
    # are provenance fields and may legitimately change inside a month.
    # They therefore MUST NOT be groupby keys.
    # ----------------------------------------------------------
    all_daily = pd.concat(
        daily_frames_for_monthly,
        ignore_index=True,
    )

    monthly = build_security_month_panel(
        all_daily=all_daily,
        manifest=manifest,
        base=base,
        manifest_sha=manifest_sha,
        base_sha=base_sha,
        policy_sha=policy_sha,
        diagnostics_path=(
            TRANSITION_MONTH_DIAGNOSTICS_PATH
        ),
    )

    monthly.to_csv(
        MONTHLY_PATH,
        index=False,
    )

    t = policy["frozen_coverage_thresholds"]

    overall_rate = (
        source["source_available_flag"].sum()
        / len(source)
    )
    min_year = year_coverage[
        "source_coverage_rate"
    ].min()
    min_month = month_coverage[
        "source_coverage_rate"
    ].min()
    min_security_month = monthly[
        "source_coverage_rate"
    ].min()

    pass_gate = bool(
        overall_rate
        >= float(
            t["minimum_overall_calendar_source_coverage"]
        )
        and min_year
        >= float(
            t["minimum_annual_source_coverage"]
        )
        and min_month
        >= float(
            t["minimum_calendar_month_source_coverage"]
        )
        and min_security_month
        >= float(
            t["minimum_security_month_source_coverage"]
        )
    )

    lines = [
        "=" * 128,
        "H3 STAGE 3L — GDELT SOURCE-GAP RECONCILIATION",
        "=" * 128,
        f"Source-gap policy: {policy['policy_id']}",
        f"Source-gap policy SHA-256: {policy_sha}",
        f"Calendar dates classified: {len(source)}",
        f"Available source dates: {int(source['source_available_flag'].sum())}",
        f"Documented source-gap dates: {len(gaps)}",
        f"Newly acquired during reconciliation: {newly_acquired}",
        f"Existing valid caches reused: {available_cache}",
        f"Security-months with >1 PIT alias: {int(monthly['pit_alias_transition_month_flag'].sum())}",
        "",
        "SOURCE-GAP CLASSES:",
    ]

    for key, value in gaps[
        "source_gap_class"
    ].value_counts().to_dict().items():
        lines.append(f"  {key}: {value}")

    lines += [
        "",
        "COVERAGE:",
        f"  Overall calendar source coverage: {overall_rate:.6f}",
        f"  Minimum annual source coverage: {min_year:.6f}",
        f"  Minimum calendar-month source coverage: {min_month:.6f}",
        f"  Minimum security-month source coverage: {min_security_month:.6f}",
        "",
        "THRESHOLDS:",
        f"  Overall >= {t['minimum_overall_calendar_source_coverage']:.2%}",
        f"  Annual >= {t['minimum_annual_source_coverage']:.2%}",
        f"  Calendar month >= {t['minimum_calendar_month_source_coverage']:.2%}",
        f"  Security month >= {t['minimum_security_month_source_coverage']:.2%}",
        "",
        "Source-gap days imputed as zero attention: NO",
        "Return/outcome fields read: 0",
        "",
        (
            "H3_FULL_GDELT_SOURCE_GAP_RECONCILIATION_PASSED"
            if pass_gate
            else
            "H3_FULL_GDELT_SOURCE_GAP_RECONCILIATION_FAILED_COVERAGE"
        ),
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )
    print(report, end="")


if __name__ == "__main__":
    main()
