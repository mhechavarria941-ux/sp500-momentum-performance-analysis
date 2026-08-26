from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-26-v1-h3-source-gap-finalize-transition-month-fix"

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

SOURCE_LEDGER_PATH = H3_DIR / "h3_gdelt_full_source_files.csv"
GAP_DAYS_PATH = H3_DIR / "h3_gdelt_full_source_gap_days.csv"
MONTH_COVERAGE_PATH = H3_DIR / "h3_gdelt_full_calendar_month_source_coverage.csv"
YEAR_COVERAGE_PATH = H3_DIR / "h3_gdelt_full_year_source_coverage.csv"
MONTHLY_PATH = H3_DIR / "h3_gdelt_full_monthly_security_attention.csv"
TRANSITION_MONTH_DIAGNOSTICS_PATH = (
    H3_DIR
    / "h3_gdelt_transition_month_metadata_diagnostics.csv"
)
REPORT_PATH = H3_DIR / "h3_gdelt_source_gap_reconciliation_report.txt"

YEARLY_TEMPLATE = "h3_gdelt_full_daily_security_{year}.csv.gz"

RECONCILE_MODULE_PATH = (
    ANALYSIS_DIR / "reconcile_h3_gdelt_source_gaps.py"
)


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as h:
        for block in iter(
            lambda: h.read(1024 * 1024),
            b"",
        ):
            d.update(block)
    return d.hexdigest()


def load_reconcile_module():
    spec = importlib.util.spec_from_file_location(
        "h3_source_gap_reconcile",
        RECONCILE_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Unable to load corrected reconciliation module."
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    required = [
        POLICY_PATH,
        BASE_PROTOCOL_PATH,
        MANIFEST_PATH,
        SOURCE_LEDGER_PATH,
        GAP_DAYS_PATH,
        MONTH_COVERAGE_PATH,
        YEAR_COVERAGE_PATH,
        RECONCILE_MODULE_PATH,
    ]

    yearly_paths = [
        H3_DIR / YEARLY_TEMPLATE.format(year=year)
        for year in range(2021, 2026)
    ]
    required += yearly_paths

    for path in required:
        require(path)

    reconcile = load_reconcile_module()

    policy_text = POLICY_PATH.read_text(
        encoding="utf-8"
    )
    policy = json.loads(policy_text)
    policy_sha = hashlib.sha256(
        policy_text.encode("utf-8")
    ).hexdigest()

    base_text = BASE_PROTOCOL_PATH.read_text(
        encoding="utf-8"
    )
    base = json.loads(base_text)
    base_sha = hashlib.sha256(
        base_text.encode("utf-8")
    ).hexdigest()

    manifest = pd.read_csv(
        MANIFEST_PATH,
        dtype=str,
        keep_default_na=False,
    )
    manifest_sha = sha256_file(MANIFEST_PATH)

    source = pd.read_csv(
        SOURCE_LEDGER_PATH,
        dtype=str,
        keep_default_na=False,
    )
    gaps = pd.read_csv(
        GAP_DAYS_PATH,
        dtype=str,
        keep_default_na=False,
    )
    month_coverage = pd.read_csv(
        MONTH_COVERAGE_PATH,
        dtype=str,
        keep_default_na=False,
    )
    year_coverage = pd.read_csv(
        YEAR_COVERAGE_PATH,
        dtype=str,
        keep_default_na=False,
    )

    if len(source) != int(
        base["source"]["expected_daily_files"]
    ):
        raise RuntimeError(
            "Source reconciliation ledger is incomplete. "
            "Do not use finalize-only mode."
        )

    # The failed V3 run already wrote all five yearly shards
    # before reaching the monthly merge.
    frames = []
    for path in yearly_paths:
        frames.append(
            pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                compression="gzip",
            )
        )

    all_daily = pd.concat(
        frames,
        ignore_index=True,
    )

    monthly = reconcile.build_security_month_panel(
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

    for frame, columns in (
        (source, ["source_available_flag"]),
        (month_coverage, ["source_coverage_rate"]),
        (year_coverage, ["source_coverage_rate"]),
    ):
        for column in columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="raise",
            )

    t = policy["frozen_coverage_thresholds"]

    overall_rate = source[
        "source_available_flag"
    ].mean()
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
            t[
                "minimum_overall_calendar_source_coverage"
            ]
        )
        and min_year
        >= float(
            t["minimum_annual_source_coverage"]
        )
        and min_month
        >= float(
            t[
                "minimum_calendar_month_source_coverage"
            ]
        )
        and min_security_month
        >= float(
            t[
                "minimum_security_month_source_coverage"
            ]
        )
    )

    lines = [
        "=" * 128,
        "H3 STAGE 3L — SOURCE-GAP RECONCILIATION FINALIZATION",
        "=" * 128,
        f"Source-gap policy: {policy['policy_id']}",
        f"Source-gap policy SHA-256: {policy_sha}",
        f"Calendar dates classified: {len(source)}",
        f"Available source dates: {int(source['source_available_flag'].sum())}",
        f"Documented source-gap dates: {len(gaps)}",
        (
            "Security-months with >1 PIT alias: "
            f"{int(monthly['pit_alias_transition_month_flag'].sum())}"
        ),
        f"Monthly security-attention rows: {len(monthly)}",
        "",
        "COVERAGE:",
        f"  Overall calendar source coverage: {overall_rate:.6f}",
        f"  Minimum annual source coverage: {min_year:.6f}",
        f"  Minimum calendar-month source coverage: {min_month:.6f}",
        f"  Minimum security-month source coverage: {min_security_month:.6f}",
        "",
        "Source-gap days imputed as zero attention: NO",
        "Return/outcome fields read: 0",
        "Remote GDELT downloads performed by this finalizer: 0",
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
