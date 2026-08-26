from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-26-v2-h3-preregistered-attention-predictor-issuer-day"

H3_DIR = ROOT / "reports" / "exploratory" / "h3_attention_feasibility"

PREREG_PATH = (
    ROOT / "data" / "reference" / "h3"
    / "h3_statistical_preregistration_v2.json"
)
PRIMARY_MONTHLY_ATTENTION_PATH = (
    H3_DIR / "h3_gdelt_primary_monthly_security_attention.csv"
)
ATTENTION_AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_gdelt_fail_closed_month_eligibility_audit.txt"
)

YEARLY_TEMPLATE = "h3_gdelt_full_daily_security_{year}.csv.gz"

OUTPUT_PATH = (
    H3_DIR / "h3_preregistered_attention_predictor_panel.csv"
)
ISSUER_DAY_PATH = (
    H3_DIR / "h3_preregistered_attention_issuer_day_panel.csv.gz"
)
ISSUER_MONTH_PATH = (
    H3_DIR / "h3_preregistered_attention_issuer_month_panel.csv"
)
SAME_ISSUER_DAY_DIAGNOSTICS_PATH = (
    H3_DIR / "h3_preregistered_attention_same_issuer_day_diagnostics.csv"
)
MONTH_SUMMARY_PATH = (
    H3_DIR / "h3_preregistered_attention_month_summary.csv"
)
REPORT_PATH = (
    H3_DIR / "h3_statistical_preregistration_preparation_report.txt"
)

REQUIRED_ATTENTION_AUDIT_TOKEN = (
    "H3_FULL_GDELT_ATTENTION_ACQUISITION_CLOSED_FAIL_CLOSED_MONTH_ELIGIBILITY"
)

FORBIDDEN_INPUT_FRAGMENTS = (
    "return",
    "momentum",
    "winner",
    "outcome",
    "commonality",
)


def issuer_id_from_frame(df: pd.DataFrame) -> pd.Series:
    issuer = df["issuer_cik"].astype(str).str.strip()
    missing = issuer.eq("")
    issuer = issuer.copy()
    issuer.loc[missing] = (
        "SECURITY::"
        + df.loc[
            missing,
            "security_key",
        ].astype(str)
    )
    return issuer


def collapse_unique(values: pd.Series) -> str:
    return "|".join(
        sorted(
            {
                str(value).strip()
                for value in values
                if str(value).strip()
            }
        )
    )


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    yearly_paths = [
        H3_DIR / YEARLY_TEMPLATE.format(year=year)
        for year in range(2021, 2026)
    ]

    for path in (
        PREREG_PATH,
        PRIMARY_MONTHLY_ATTENTION_PATH,
        ATTENTION_AUDIT_PATH,
        *yearly_paths,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    audit_text = ATTENTION_AUDIT_PATH.read_text(
        encoding="utf-8",
        errors="replace",
    )
    if REQUIRED_ATTENTION_AUDIT_TOKEN not in audit_text:
        raise RuntimeError(
            "Fail-closed attention acquisition audit has not passed."
        )

    prereg_text = PREREG_PATH.read_text(encoding="utf-8")
    prereg = json.loads(prereg_text)
    prereg_sha = hashlib.sha256(
        prereg_text.encode("utf-8")
    ).hexdigest()

    start = prereg["analysis_timing"]["predictor_month_start"]
    end = prereg["analysis_timing"]["predictor_month_end"]

    # --------------------------------------------------------------
    # Eligible security-month mapping from the fail-closed layer.
    # This determines which securities can receive the frozen predictor.
    # --------------------------------------------------------------
    monthly_security = pd.read_csv(
        PRIMARY_MONTHLY_ATTENTION_PATH,
        dtype=str,
        keep_default_na=False,
    )

    bad_monthly_columns = [
        column
        for column in monthly_security.columns
        if any(
            fragment in column.casefold()
            for fragment in FORBIDDEN_INPUT_FRAGMENTS
        )
    ]
    if bad_monthly_columns:
        raise RuntimeError(
            "Outcome-firewall violation in monthly attention columns: "
            + ", ".join(sorted(bad_monthly_columns))
        )

    required_monthly = {
        "month",
        "security_key",
        "issuer_cik",
        "latest_project_ticker",
        "structural_ambiguity_tier",
        "attention_share",
        "source_coverage_rate",
        "unique_aliases_in_month",
        "primary_attention_eligible_flag",
    }
    missing = required_monthly - set(monthly_security.columns)
    if missing:
        raise RuntimeError(
            "Primary monthly attention panel missing columns: "
            + ", ".join(sorted(missing))
        )

    for column in (
        "attention_share",
        "source_coverage_rate",
        "unique_aliases_in_month",
        "primary_attention_eligible_flag",
    ):
        monthly_security[column] = pd.to_numeric(
            monthly_security[column],
            errors="raise",
        )

    monthly_security = monthly_security[
        monthly_security["month"].between(
            start,
            end,
            inclusive="both",
        )
        & monthly_security[
            "primary_attention_eligible_flag"
        ].eq(1)
    ].copy()

    if monthly_security.empty:
        raise RuntimeError(
            "No eligible security-month predictor rows remain."
        )

    if monthly_security[
        ["month", "security_key"]
    ].duplicated().any():
        raise RuntimeError(
            "Duplicate eligible security-month rows exist."
        )

    monthly_security["issuer_id"] = issuer_id_from_frame(
        monthly_security
    )
    monthly_security = monthly_security.rename(
        columns={
            "attention_share": "security_month_attention_share_provenance"
        }
    )

    # --------------------------------------------------------------
    # Read daily frozen attention shards. Only source-available dates
    # are represented in those shards.
    # --------------------------------------------------------------
    daily_frames = []

    for path in yearly_paths:
        daily = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            compression="gzip",
        )

        bad_daily_columns = [
            column
            for column in daily.columns
            if any(
                fragment in column.casefold()
                for fragment in FORBIDDEN_INPUT_FRAGMENTS
            )
        ]
        if bad_daily_columns:
            raise RuntimeError(
                f"Outcome-firewall violation in {path.name}: "
                + ", ".join(sorted(bad_daily_columns))
            )

        required_daily = {
            "date",
            "month",
            "security_key",
            "issuer_cik",
            "production_alias",
            "matched_source_document_weight",
            "total_source_document_weight",
            "attention_share",
        }
        missing_daily = required_daily - set(daily.columns)
        if missing_daily:
            raise RuntimeError(
                f"{path.name} missing required columns: "
                + ", ".join(sorted(missing_daily))
            )

        daily = daily[
            daily["month"].between(
                start,
                end,
                inclusive="both",
            )
        ].copy()

        daily_frames.append(daily)

    daily = pd.concat(
        daily_frames,
        ignore_index=True,
    )

    for column in (
        "matched_source_document_weight",
        "total_source_document_weight",
        "attention_share",
    ):
        daily[column] = pd.to_numeric(
            daily[column],
            errors="raise",
        )

    daily["issuer_id"] = issuer_id_from_frame(daily)

    if daily[
        ["date", "security_key"]
    ].duplicated().any():
        raise RuntimeError(
            "Daily attention shards contain duplicate security-date rows."
        )

    # --------------------------------------------------------------
    # SAME ISSUER / SAME DAY invariant.
    # Different security-month ratios are allowed because their active
    # date sets can differ. But simultaneous security rows on one date
    # must encode the same issuer attention measurement.
    # --------------------------------------------------------------
    issuer_day_check = (
        daily.groupby(
            ["date", "month", "issuer_id"],
            as_index=False,
        )
        .agg(
            security_rows=("security_key", "size"),
            security_keys_pipe=(
                "security_key",
                collapse_unique,
            ),
            production_aliases_pipe=(
                "production_alias",
                collapse_unique,
            ),
            matched_min=(
                "matched_source_document_weight", "min"
            ),
            matched_max=(
                "matched_source_document_weight", "max"
            ),
            denominator_min=(
                "total_source_document_weight", "min"
            ),
            denominator_max=(
                "total_source_document_weight", "max"
            ),
            attention_min=("attention_share", "min"),
            attention_max=("attention_share", "max"),
        )
    )

    issuer_day_check["matched_spread"] = (
        issuer_day_check["matched_max"]
        - issuer_day_check["matched_min"]
    )
    issuer_day_check["denominator_spread"] = (
        issuer_day_check["denominator_max"]
        - issuer_day_check["denominator_min"]
    )
    issuer_day_check["attention_spread"] = (
        issuer_day_check["attention_max"]
        - issuer_day_check["attention_min"]
    )

    inconsistent = issuer_day_check[
        issuer_day_check["matched_spread"].ne(0)
        | issuer_day_check[
            "denominator_spread"
        ].ne(0)
    ].copy()

    inconsistent.to_csv(
        SAME_ISSUER_DAY_DIAGNOSTICS_PATH,
        index=False,
    )

    if not inconsistent.empty:
        raise RuntimeError(
            "Same-issuer DAILY attention differs across simultaneously active "
            "security rows. This is a genuine alias/measurement conflict. "
            f"Rows={len(inconsistent)}. Inspect "
            f"{SAME_ISSUER_DAY_DIAGNOSTICS_PATH.name}. "
            f"Sample={inconsistent.head(20).to_dict(orient='records')}"
        )

    # --------------------------------------------------------------
    # Deduplicate to one issuer-day. This prevents multiple listed
    # share classes from overweighting an issuer.
    # --------------------------------------------------------------
    issuer_day = (
        daily.sort_values(
            ["date", "issuer_id", "security_key"]
        )
        .groupby(
            ["date", "month", "issuer_id"],
            as_index=False,
        )
        .agg(
            matched_source_document_weight=(
                "matched_source_document_weight", "first"
            ),
            total_source_document_weight=(
                "total_source_document_weight", "first"
            ),
            security_rows=("security_key", "size"),
            security_keys_pipe=(
                "security_key",
                collapse_unique,
            ),
            production_aliases_pipe=(
                "production_alias",
                collapse_unique,
            ),
        )
    )

    issuer_day["issuer_day_attention_share"] = (
        issuer_day["matched_source_document_weight"]
        / issuer_day["total_source_document_weight"]
    )

    if issuer_day[
        ["date", "issuer_id"]
    ].duplicated().any():
        raise RuntimeError(
            "Issuer-day deduplication failed."
        )

    issuer_day.to_csv(
        ISSUER_DAY_PATH,
        index=False,
        compression="gzip",
    )

    # --------------------------------------------------------------
    # Aggregate one issuer-month from unique issuer-days.
    # --------------------------------------------------------------
    issuer_month = (
        issuer_day.groupby(
            ["month", "issuer_id"],
            as_index=False,
        )
        .agg(
            source_available_issuer_days=("date", "nunique"),
            matched_source_document_weight=(
                "matched_source_document_weight", "sum"
            ),
            total_source_document_weight=(
                "total_source_document_weight", "sum"
            ),
            security_keys_pipe=(
                "security_keys_pipe",
                collapse_unique,
            ),
        )
    )

    issuer_month["issuer_attention_share"] = (
        issuer_month["matched_source_document_weight"]
        / issuer_month["total_source_document_weight"]
    )

    # Only issuers that actually map to an eligible security-month
    # belong in the cross-sectional standardization universe.
    eligible_issuer_keys = monthly_security[
        ["month", "issuer_id"]
    ].drop_duplicates()

    issuer_month = issuer_month.merge(
        eligible_issuer_keys,
        on=["month", "issuer_id"],
        how="inner",
        validate="one_to_one",
    )

    if issuer_month.empty:
        raise RuntimeError(
            "No issuer-month rows map to eligible predictor securities."
        )

    scale = float(
        prereg["attention_primary"]["scale_constant"]
    )

    issuer_month["attention_log"] = np.log1p(
        scale * issuer_month["issuer_attention_share"]
    )

    issuer_month["attention_percentile_midrank"] = (
        issuer_month.groupby("month")[
            "issuer_attention_share"
        ].rank(method="average")
        - 0.5
    ) / (
        issuer_month.groupby("month")[
            "issuer_id"
        ].transform("size")
    )

    month_stats = (
        issuer_month.groupby(
            "month",
            as_index=False,
        )
        .agg(
            issuer_count=("issuer_id", "nunique"),
            attention_log_mean=(
                "attention_log", "mean"
            ),
            attention_log_sd=(
                "attention_log",
                lambda s: s.std(ddof=1),
            ),
            zero_attention_issuers=(
                "issuer_attention_share",
                lambda s: int((s == 0).sum()),
            ),
        )
    )

    min_cross_section = int(
        prereg[
            "sample_and_missingness"
        ]["minimum_cross_section_for_attention_z"]
    )

    if (
        month_stats["issuer_count"]
        < min_cross_section
    ).any():
        bad = month_stats[
            month_stats["issuer_count"]
            < min_cross_section
        ]
        raise RuntimeError(
            "A predictor month has too few eligible issuers: "
            f"{bad.to_dict(orient='records')}"
        )

    if (
        month_stats["attention_log_sd"] <= 0
    ).any():
        bad = month_stats[
            month_stats["attention_log_sd"] <= 0
        ]
        raise RuntimeError(
            "A predictor month has non-positive issuer attention-log SD: "
            f"{bad.to_dict(orient='records')}"
        )

    issuer_month = issuer_month.merge(
        month_stats[
            [
                "month",
                "attention_log_mean",
                "attention_log_sd",
            ]
        ],
        on="month",
        how="left",
        validate="many_to_one",
    )

    issuer_month["attention_z"] = (
        issuer_month["attention_log"]
        - issuer_month["attention_log_mean"]
    ) / issuer_month["attention_log_sd"]

    issuer_month["preregistration_sha256"] = prereg_sha

    issuer_month.to_csv(
        ISSUER_MONTH_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Map frozen issuer-month predictor back to eligible securities.
    # --------------------------------------------------------------
    predictor = monthly_security.merge(
        issuer_month[
            [
                "month",
                "issuer_id",
                "issuer_attention_share",
                "source_available_issuer_days",
                "attention_log",
                "attention_z",
                "attention_percentile_midrank",
                "attention_log_mean",
                "attention_log_sd",
                "preregistration_sha256",
            ]
        ],
        on=["month", "issuer_id"],
        how="left",
        validate="many_to_one",
    )

    if predictor["attention_z"].isna().any():
        bad = predictor.loc[
            predictor["attention_z"].isna(),
            ["month", "security_key", "issuer_id"],
        ]
        raise RuntimeError(
            "Eligible security-month failed issuer-month attention mapping: "
            f"{bad.head(20).to_dict(orient='records')}"
        )

    predictor["attention_share"] = predictor[
        "issuer_attention_share"
    ]

    predictor[
        "pit_alias_transition_month_flag"
    ] = (
        predictor["unique_aliases_in_month"] > 1
    ).astype(int)

    predictor[
        "predictor_month_end_of_sample_flag"
    ] = (
        predictor["month"]
        == prereg[
            "analysis_timing"
        ]["predictor_month_end"]
    ).astype(int)

    predictor.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    month_summary = (
        predictor.groupby(
            "month",
            as_index=False,
        )
        .agg(
            security_rows=("security_key", "size"),
            issuer_count=("issuer_id", "nunique"),
            true_zero_issuer_attention_security_rows=(
                "issuer_attention_share",
                lambda s: int((s == 0).sum()),
            ),
            transition_security_rows=(
                "pit_alias_transition_month_flag", "sum"
            ),
            attention_z_mean_security_weighted=(
                "attention_z", "mean"
            ),
            attention_z_sd_security_weighted=(
                "attention_z",
                lambda s: s.std(ddof=1),
            ),
        )
    )

    month_summary.to_csv(
        MONTH_SUMMARY_PATH,
        index=False,
    )

    trigger = predictor[
        (predictor["month"] == "2022-04")
        & (predictor["issuer_id"] == "0001437107")
    ]

    lines = [
        "=" * 128,
        "H3 STATISTICAL PREREGISTRATION V2 — ATTENTION-ONLY PREPARATION",
        "=" * 128,
        f"Preregistration ID: {prereg['preregistration_id']}",
        f"Preregistration SHA-256: {prereg_sha}",
        f"Predictor months: {predictor['month'].nunique()}",
        f"Predictor security-month rows: {len(predictor)}",
        f"Unique securities: {predictor['security_key'].nunique()}",
        f"Unique issuer clusters: {predictor['issuer_id'].nunique()}",
        f"Issuer-day rows: {len(issuer_day)}",
        f"Same-issuer/day disagreement rows: {len(inconsistent)}",
        f"PIT alias-transition security-month rows: {int(predictor['pit_alias_transition_month_flag'].sum())}",
        f"2022-04 CIK 0001437107 eligible security rows: {len(trigger)}",
        "",
        "Primary attention construction:",
        "  security-day -> same-issuer/day check -> one issuer-day -> issuer-month",
        "  log(1 + 1,000,000 * issuer_attention_share)",
        "  within-month z-score across unique eligible issuers",
        "",
        "Returns read: 0",
        "Momentum fields read: 0",
        "Winner fields read: 0",
        "Outcome joins performed: 0",
        "",
        "H3_PREREGISTERED_ATTENTION_PREDICTOR_V2_PREPARATION_COMPLETE",
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
