from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-26-v2-h3-gdelt-source-gap-reconciliation-audit-transition-month-fix"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

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
TRANSITION_MONTH_DIAGNOSTICS_PATH = H3_DIR / "h3_gdelt_transition_month_metadata_diagnostics.csv"

YEARLY_TEMPLATE = "h3_gdelt_full_daily_security_{year}.csv.gz"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_gdelt_source_gap_reconciliation_integrity_audit.txt"
)

FORBIDDEN = (
    "return",
    "momentum",
    "winner",
    "commonality_factor",
    "outcome",
)


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as h:
        for block in iter(lambda: h.read(1024 * 1024), b""):
            d.update(block)
    return d.hexdigest()


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
        MONTHLY_PATH,
        TRANSITION_MONTH_DIAGNOSTICS_PATH,
    ]
    yearly_paths = [
        H3_DIR / YEARLY_TEMPLATE.format(year=y)
        for y in range(2021, 2026)
    ]
    required += yearly_paths

    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

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
    month_cov = pd.read_csv(
        MONTH_COVERAGE_PATH,
        dtype=str,
        keep_default_na=False,
    )
    year_cov = pd.read_csv(
        YEAR_COVERAGE_PATH,
        dtype=str,
        keep_default_na=False,
    )
    monthly = pd.read_csv(
        MONTHLY_PATH,
        dtype=str,
        keep_default_na=False,
    )

    for frame, columns in (
        (source, ["source_available_flag"]),
        (
            month_cov,
            [
                "expected_calendar_days",
                "source_available_days",
                "source_missing_days",
                "source_coverage_rate",
            ],
        ),
        (
            year_cov,
            [
                "expected_calendar_days",
                "source_available_days",
                "source_missing_days",
                "source_coverage_rate",
            ],
        ),
        (
            monthly,
            [
                "source_available_days",
                "nonzero_days",
                "matched_source_document_weight",
                "total_source_document_weight",
                "unique_aliases_in_month",
                "expected_active_calendar_days",
                "source_missing_days",
                "source_coverage_rate",
                "attention_share",
                "strict_nonzero_month_flag",
                "source_gap_month_flag",
                "pit_alias_transition_month_flag",
            ],
        ),
    ):
        for column in columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="raise",
            )

    failures = []
    passed = 0

    lines = [
        "=" * 128,
        "H3 STAGE 3L — SOURCE-GAP RECONCILIATION INTEGRITY AUDIT",
        "=" * 128,
        "H3 statistical inference authorized: NO",
        "",
    ]

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if bool(condition):
            lines.append("PASS: " + success)
            passed += 1
        else:
            lines.append("FAIL: " + failure)
            failures.append(failure)

    expected_days = int(
        base["source"]["expected_daily_files"]
    )

    check(
        len(source) == expected_days
        and source["date"].nunique() == expected_days,
        f"All {expected_days} calendar dates have an explicit source classification.",
        (
            f"Source rows={len(source)}, unique dates="
            f"{source['date'].nunique()}, expected {expected_days}."
        ),
    )

    check(
        source["source_available_flag"].isin([0, 1]).all(),
        "Every date is classified as source available or documented source gap.",
        "A source date lacks a binary availability classification.",
    )

    expected_gap_classes = {
        "OFFICIAL_CATALOG_ABSENT_AND_DIRECT_UNAVAILABLE",
        "CATALOG_LISTED_BUT_UNDELIVERABLE_AFTER_RETRIES",
    }

    check(
        set(gaps["source_gap_class"]).issubset(
            expected_gap_classes
        ),
        "Every source-gap date uses a frozen documented gap class.",
        "An unexpected source-gap classification exists.",
    )

    check(
        len(gaps)
        == int(
            source["source_available_flag"].eq(0).sum()
        ),
        "Source-gap ledger exactly matches unavailable dates in the source ledger.",
        "Source-gap row count differs from unavailable source dates.",
    )

    check(
        source["source_gap_policy_sha256"].eq(
            policy_sha
        ).all()
        and monthly["source_gap_policy_sha256"].eq(
            policy_sha
        ).all(),
        "Source and monthly outputs reproduce the frozen source-gap policy checksum.",
        "A source-gap output checksum differs from the frozen policy.",
    )

    t = policy["frozen_coverage_thresholds"]

    overall_rate = source[
        "source_available_flag"
    ].mean()
    min_year = year_cov[
        "source_coverage_rate"
    ].min()
    min_month = month_cov[
        "source_coverage_rate"
    ].min()
    min_security_month = monthly[
        "source_coverage_rate"
    ].min()

    check(
        overall_rate
        >= float(
            t["minimum_overall_calendar_source_coverage"]
        ),
        f"Overall source coverage passes ({overall_rate:.2%}).",
        f"Overall source coverage below threshold: {overall_rate:.2%}.",
    )

    check(
        min_year
        >= float(
            t["minimum_annual_source_coverage"]
        ),
        f"Every year passes source coverage; minimum={min_year:.2%}.",
        f"At least one year is below source coverage threshold: {min_year:.2%}.",
    )

    check(
        min_month
        >= float(
            t["minimum_calendar_month_source_coverage"]
        ),
        f"Every calendar month passes source coverage; minimum={min_month:.2%}.",
        f"At least one calendar month is below source coverage threshold: {min_month:.2%}.",
    )

    check(
        min_security_month
        >= float(
            t["minimum_security_month_source_coverage"]
        ),
        (
            "Every security-month passes the frozen source coverage threshold; "
            f"minimum={min_security_month:.2%}."
        ),
        (
            "At least one security-month is below source coverage threshold: "
            f"{min_security_month:.2%}."
        ),
    )

    check(
        monthly["attention_share"].between(
            0.0, 1.0, inclusive="both"
        ).all(),
        "Every monthly attention share lies in [0, 1].",
        "A monthly attention share lies outside [0, 1].",
    )

    check(
        (
            monthly["matched_source_document_weight"]
            <= monthly["total_source_document_weight"]
        ).all(),
        "Monthly matched source-document weight never exceeds its denominator.",
        "A monthly matched weight exceeds its denominator.",
    )

    check(
        not monthly[
            ["month", "security_key"]
        ].duplicated().any(),
        (
            "Monthly panel contains exactly one row per "
            "security-month, including PIT name-transition months."
        ),
        (
            "Duplicate security-month rows remain after "
            "transition-month aggregation."
        ),
    )

    transition_diagnostics = pd.read_csv(
        TRANSITION_MONTH_DIAGNOSTICS_PATH,
        dtype=str,
        keep_default_na=False,
    )

    transition_keys = set(
        map(
            tuple,
            transition_diagnostics[
                ["month", "security_key"]
            ].drop_duplicates().to_numpy(),
        )
    )
    monthly_transition_keys = set(
        map(
            tuple,
            monthly.loc[
                monthly[
                    "pit_alias_transition_month_flag"
                ].eq(1),
                ["month", "security_key"],
            ].to_numpy(),
        )
    )

    check(
        transition_keys == monthly_transition_keys,
        (
            "Transition-month diagnostic keys exactly equal "
            "monthly rows flagged with multiple PIT aliases."
        ),
        (
            "Transition-month diagnostics and monthly transition "
            "flags do not reconcile."
        ),
    )

    # Reaggregate all available daily shards exactly.
    daily_frames = []
    for path in yearly_paths:
        daily = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            compression="gzip",
        )
        for column in (
            "matched_source_document_weight",
            "total_source_document_weight",
        ):
            daily[column] = pd.to_numeric(
                daily[column],
                errors="raise",
            )
        daily_frames.append(daily)

    daily_all = pd.concat(
        daily_frames,
        ignore_index=True,
    )

    check(
        not daily_all[
            ["date", "security_key"]
        ].duplicated().any(),
        "Available daily shards contain no duplicate security-date rows.",
        "Duplicate security-date rows exist in available daily shards.",
    )

    available_dates = set(
        source.loc[
            source["source_available_flag"].eq(1),
            "date",
        ]
    )

    check(
        set(daily_all["date"].unique())
        == available_dates,
        "Yearly daily shards contain exactly the source-available calendar dates.",
        "Daily shard dates differ from the source-available date ledger.",
    )

    recomputed = (
        daily_all.groupby(
            ["month", "security_key"],
            as_index=False,
        )
        .agg(
            source_available_days_recomputed=(
                "date", "nunique"
            ),
            matched_recomputed=(
                "matched_source_document_weight", "sum"
            ),
            denominator_recomputed=(
                "total_source_document_weight", "sum"
            ),
        )
    )

    compare = monthly.merge(
        recomputed,
        on=["month", "security_key"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )

    check(
        compare["_merge"].eq("both").all()
        and (
            compare["source_available_days"]
            == compare[
                "source_available_days_recomputed"
            ]
        ).all()
        and (
            compare["matched_source_document_weight"]
            == compare["matched_recomputed"]
        ).all()
        and (
            compare["total_source_document_weight"]
            == compare["denominator_recomputed"]
        ).all(),
        "Monthly attention panel exactly reaggregates from available daily shards.",
        "Monthly attention panel differs from daily-shard reaggregation.",
    )

    all_columns = {
        str(c).casefold()
        for frame in [source, gaps, monthly, daily_all]
        for c in frame.columns
    }
    bad = [
        c
        for c in all_columns
        if any(fragment in c for fragment in FORBIDDEN)
    ]

    check(
        not bad,
        "Source-gap reconciliation contains no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields found: " + ", ".join(sorted(bad)),
    )

    gate = (
        "H3_FULL_GDELT_ATTENTION_ACQUISITION_CLOSED_WITH_DOCUMENTED_SOURCE_GAPS"
        if not failures
        else
        "H3_FULL_GDELT_ATTENTION_ACQUISITION_SOURCE_GAP_AUDIT_FAILED"
    )

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Calendar dates: {len(source)}",
        f"Available source dates: {int(source['source_available_flag'].sum())}",
        f"Documented source-gap dates: {len(gaps)}",
        f"Monthly security-attention rows: {len(monthly)}",
        f"Overall source coverage: {overall_rate:.6f}",
        f"Minimum annual coverage: {min_year:.6f}",
        f"Minimum calendar-month coverage: {min_month:.6f}",
        f"Minimum security-month coverage: {min_security_month:.6f}",
        "",
        gate,
        "",
        (
            "A passing gate closes attention acquisition. Source-gap days remain "
            "missing source coverage and are never imputed as zero attention."
        ),
        (
            "The next authorized task is H3 statistical preregistration before "
            "any attention/outcome join."
        ),
    ]

    AUDIT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(
        text,
        encoding="utf-8",
    )
    print(text, end="")


if __name__ == "__main__":
    main()
