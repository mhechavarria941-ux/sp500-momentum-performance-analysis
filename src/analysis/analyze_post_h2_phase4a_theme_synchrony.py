from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SCRIPT_VERSION = "2026-08-24-v1-post-h2-phase4a-theme-synchrony"

EXP_DIR = ROOT / "reports" / "exploratory"

CONTRIBUTION_PATH = EXP_DIR / "post_h2_commonality_security_month_contributions.csv"
FACTOR_PATH = EXP_DIR / "post_h2_winner_commonality_factor.csv"
MATRIX_PATH = EXP_DIR / "post_h2_phase3d_target_theme_matrix.csv"
TAXONOMY_PATH = EXP_DIR / "post_h2_phase3c_frozen_theme_taxonomy.csv"

REPORT_PATH = EXP_DIR / "post_h2_phase4a_theme_synchrony_analysis.txt"
THEME_STATS_PATH = EXP_DIR / "post_h2_phase4a_security_theme_synchrony.csv"
THEME_MONTH_PATH = EXP_DIR / "post_h2_phase4a_security_theme_monthly_panel.csv"
MACRO_PATH = EXP_DIR / "post_h2_phase4a_macro_theme_descriptives.csv"
NULL_SUMMARY_PATH = EXP_DIR / "post_h2_phase4a_randomization_null_summary.csv"

EXPECTED_TAXONOMY_SHA256 = (
    "1c7698cbe2facd069c7a12fda41cbf7399a9f657ed4f7a9f956d135f8f9d2576"
)

EXPECTED_MONTHS = 59
EXPECTED_SECURITY_TARGETS = 30
RANDOMIZATION_REPLICATIONS = 20_000
RANDOMIZATION_SEED = 20260824
MIN_TESTABLE_THEME_SIZE = 3


def rule() -> str:
    return "=" * 122


def holm_adjust(p_values: np.ndarray) -> np.ndarray:
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    order = np.argsort(p)
    adjusted = np.empty(n, dtype=float)

    running = 0.0
    for rank, idx in enumerate(order):
        value = (n - rank) * p[idx]
        running = max(running, value)
        adjusted[idx] = min(running, 1.0)

    return adjusted


def average_pairwise_correlation(corr: np.ndarray, indices: np.ndarray) -> float:
    if len(indices) < 2:
        return math.nan
    sub = corr[np.ix_(indices, indices)]
    upper = sub[np.triu_indices(len(indices), k=1)]
    if upper.size == 0:
        return math.nan
    return float(np.nanmean(upper))


def pearson_with_fixed_y(x: np.ndarray, y_centered: np.ndarray, y_ss: float) -> float:
    x = np.asarray(x, dtype=float)
    xc = x - x.mean()
    x_ss = float(np.dot(xc, xc))
    if x_ss <= 0 or y_ss <= 0:
        return math.nan
    return float(np.dot(xc, y_centered) / math.sqrt(x_ss * y_ss))


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        CONTRIBUTION_PATH,
        FACTOR_PATH,
        MATRIX_PATH,
        TAXONOMY_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    checksum = hashlib.sha256(TAXONOMY_PATH.read_bytes()).hexdigest()
    if checksum != EXPECTED_TAXONOMY_SHA256:
        raise RuntimeError(
            "Frozen taxonomy checksum mismatch. "
            f"Observed={checksum}; expected={EXPECTED_TAXONOMY_SHA256}."
        )

    contribution = pd.read_csv(CONTRIBUTION_PATH)
    factor = pd.read_csv(FACTOR_PATH)
    target_matrix = pd.read_csv(MATRIX_PATH)
    taxonomy = pd.read_csv(TAXONOMY_PATH)

    contribution["analysis_month_number"] = pd.to_numeric(
        contribution["analysis_month_number"], errors="raise"
    ).astype(int)
    contribution["aggregate_commonality_contribution"] = pd.to_numeric(
        contribution["aggregate_commonality_contribution"], errors="raise"
    )

    factor["analysis_month_number"] = pd.to_numeric(
        factor["analysis_month_number"], errors="raise"
    ).astype(int)
    factor["commonality_factor_equal_weight_residual"] = pd.to_numeric(
        factor["commonality_factor_equal_weight_residual"], errors="raise"
    )

    sec_matrix = (
        target_matrix[target_matrix["target_type"] == "SECURITY"]
        .sort_values("priority_rank")
        .reset_index(drop=True)
    )
    month_matrix = (
        target_matrix[target_matrix["target_type"] == "MONTH"]
        .sort_values("priority_rank")
        .reset_index(drop=True)
    )

    if len(sec_matrix) != EXPECTED_SECURITY_TARGETS:
        raise RuntimeError(
            f"Security target rows={len(sec_matrix)}, expected 30."
        )
    if factor["analysis_month_number"].nunique() != EXPECTED_MONTHS:
        raise RuntimeError("Commonality factor does not span 59 months.")

    security_keys = sec_matrix["security_key"].astype(str).tolist()
    months = sorted(factor["analysis_month_number"].unique().tolist())

    # 59 x 30 signed contribution matrix, zero when target is not a Winner.
    contrib_target = contribution[
        contribution["security_key"].astype(str).isin(security_keys)
    ].copy()

    wide = (
        contrib_target
        .pivot_table(
            index="analysis_month_number",
            columns="security_key",
            values="aggregate_commonality_contribution",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reindex(index=months, columns=security_keys, fill_value=0.0)
        .astype(float)
    )

    activity = (
        contrib_target.assign(active=1)
        .pivot_table(
            index="analysis_month_number",
            columns="security_key",
            values="active",
            aggfunc="max",
            fill_value=0,
        )
        .reindex(index=months, columns=security_keys, fill_value=0)
        .astype(float)
    )

    factor_aligned = (
        factor.set_index("analysis_month_number")
        .loc[months, "commonality_factor_equal_weight_residual"]
        .astype(float)
    )
    abs_factor = factor_aligned.abs().to_numpy(dtype=float)
    abs_factor_centered = abs_factor - abs_factor.mean()
    abs_factor_ss = float(np.dot(abs_factor_centered, abs_factor_centered))

    corr_matrix = wide.corr().to_numpy(dtype=float)

    structural_codes = taxonomy.loc[
        taxonomy["domain"] == "SECURITY_STRUCTURAL", "code"
    ].tolist()

    rng = np.random.default_rng(RANDOMIZATION_SEED)

    stats_rows = []
    month_rows = []
    null_rows = []

    security_index = {
        key: idx
        for idx, key in enumerate(security_keys)
    }

    total_abs_all_target_contrib = float(
        np.abs(wide.to_numpy(dtype=float)).sum()
    )

    for code in structural_codes:
        tagged_keys = sec_matrix.loc[
            sec_matrix[code] == 1,
            "security_key",
        ].astype(str).tolist()

        indices = np.array(
            [security_index[key] for key in tagged_keys],
            dtype=int,
        )
        k = len(indices)

        observed_sync = average_pairwise_correlation(
            corr_matrix,
            indices,
        )

        active_count = activity.iloc[:, indices].sum(axis=1).to_numpy(dtype=float)
        observed_presence_corr = pearson_with_fixed_y(
            active_count,
            abs_factor_centered,
            abs_factor_ss,
        )

        theme_contrib = wide.iloc[:, indices].sum(axis=1).to_numpy(dtype=float)

        individual_variances = np.var(
            wide.iloc[:, indices].to_numpy(dtype=float),
            axis=0,
            ddof=1,
        )
        denominator = float(np.sum(individual_variances))
        variance_ratio = (
            float(np.var(theme_contrib, ddof=1)) / denominator
            if denominator > 0
            else math.nan
        )

        theme_abs_share = (
            float(np.abs(wide.iloc[:, indices].to_numpy(dtype=float)).sum())
            / total_abs_all_target_contrib
            if total_abs_all_target_contrib > 0
            else math.nan
        )

        p_sync = math.nan
        p_presence = math.nan
        null_sync_mean = math.nan
        null_presence_mean = math.nan
        null_sync_p95 = math.nan
        null_presence_p95 = math.nan

        if k >= MIN_TESTABLE_THEME_SIZE:
            null_sync = np.empty(
                RANDOMIZATION_REPLICATIONS,
                dtype=float,
            )
            null_presence = np.empty(
                RANDOMIZATION_REPLICATIONS,
                dtype=float,
            )

            for b in range(RANDOMIZATION_REPLICATIONS):
                sample_idx = rng.choice(
                    EXPECTED_SECURITY_TARGETS,
                    size=k,
                    replace=False,
                )

                null_sync[b] = average_pairwise_correlation(
                    corr_matrix,
                    sample_idx,
                )

                random_active_count = (
                    activity.iloc[:, sample_idx]
                    .sum(axis=1)
                    .to_numpy(dtype=float)
                )
                null_presence[b] = pearson_with_fixed_y(
                    random_active_count,
                    abs_factor_centered,
                    abs_factor_ss,
                )

            finite_sync = null_sync[np.isfinite(null_sync)]
            finite_presence = null_presence[np.isfinite(null_presence)]

            p_sync = (
                1.0
                + float(np.sum(finite_sync >= observed_sync))
            ) / (
                len(finite_sync) + 1.0
            )

            p_presence = (
                1.0
                + float(np.sum(finite_presence >= observed_presence_corr))
            ) / (
                len(finite_presence) + 1.0
            )

            null_sync_mean = float(np.mean(finite_sync))
            null_presence_mean = float(np.mean(finite_presence))
            null_sync_p95 = float(np.quantile(finite_sync, 0.95))
            null_presence_p95 = float(np.quantile(finite_presence, 0.95))

            null_rows.extend(
                [
                    {
                        "theme_code": code,
                        "metric": "average_pairwise_contribution_correlation",
                        "theme_size": k,
                        "null_mean": null_sync_mean,
                        "null_p95": null_sync_p95,
                        "observed": observed_sync,
                        "monte_carlo_p_one_sided": p_sync,
                    },
                    {
                        "theme_code": code,
                        "metric": "active_count_vs_abs_commonality_correlation",
                        "theme_size": k,
                        "null_mean": null_presence_mean,
                        "null_p95": null_presence_p95,
                        "observed": observed_presence_corr,
                        "monte_carlo_p_one_sided": p_presence,
                    },
                ]
            )

        theme_name = taxonomy.loc[
            taxonomy["code"] == code,
            "theme_name",
        ].iloc[0]

        stats_rows.append(
            {
                "theme_code": code,
                "theme_name": theme_name,
                "theme_size": k,
                "tested_randomization": int(
                    k >= MIN_TESTABLE_THEME_SIZE
                ),
                "average_pairwise_contribution_correlation": observed_sync,
                "presence_count_vs_abs_commonality_correlation": observed_presence_corr,
                "aggregate_contribution_variance_ratio": variance_ratio,
                "share_of_top30_absolute_security_contribution": theme_abs_share,
                "sync_monte_carlo_p_one_sided": p_sync,
                "presence_monte_carlo_p_one_sided": p_presence,
                "sync_null_mean": null_sync_mean,
                "sync_null_p95": null_sync_p95,
                "presence_null_mean": null_presence_mean,
                "presence_null_p95": null_presence_p95,
            }
        )

        for month, count, contribution_value in zip(
            months,
            active_count,
            theme_contrib,
        ):
            month_rows.append(
                {
                    "analysis_month_number": int(month),
                    "theme_code": code,
                    "theme_name": theme_name,
                    "active_tagged_winner_count": int(count),
                    "signed_theme_commonality_contribution": float(contribution_value),
                    "absolute_theme_commonality_contribution": abs(
                        float(contribution_value)
                    ),
                    "aggregate_commonality_factor": float(
                        factor_aligned.loc[month]
                    ),
                    "absolute_aggregate_commonality_factor": abs(
                        float(factor_aligned.loc[month])
                    ),
                }
            )

    stats = pd.DataFrame(stats_rows)

    tested_mask = stats["tested_randomization"] == 1

    if tested_mask.any():
        stats.loc[
            tested_mask,
            "sync_holm_p",
        ] = holm_adjust(
            stats.loc[
                tested_mask,
                "sync_monte_carlo_p_one_sided",
            ].to_numpy(dtype=float)
        )

        stats.loc[
            tested_mask,
            "presence_holm_p",
        ] = holm_adjust(
            stats.loc[
                tested_mask,
                "presence_monte_carlo_p_one_sided",
            ].to_numpy(dtype=float)
        )

    stats["sync_exploratory_flag"] = (
        (stats["tested_randomization"] == 1)
        & (
            stats["average_pairwise_contribution_correlation"]
            > 0
        )
        & (stats["sync_holm_p"] < 0.05)
    ).astype(int)

    stats["presence_exploratory_flag"] = (
        (stats["tested_randomization"] == 1)
        & (
            stats[
                "presence_count_vs_abs_commonality_correlation"
            ]
            > 0
        )
        & (stats["presence_holm_p"] < 0.05)
    ).astype(int)

    stats.to_csv(
        THEME_STATS_PATH,
        index=False,
    )
    pd.DataFrame(month_rows).to_csv(
        THEME_MONTH_PATH,
        index=False,
    )
    pd.DataFrame(null_rows).to_csv(
        NULL_SUMMARY_PATH,
        index=False,
    )

    # Macro codes remain descriptive only.
    macro_codes = taxonomy.loc[
        taxonomy["domain"] == "MONTH_MACRO",
        "code",
    ].tolist()

    macro_rows = []

    month_factor_map = factor.set_index(
        "analysis_month_number"
    )[
        "commonality_factor_equal_weight_residual"
    ].astype(float)

    for code in macro_codes:
        coded_months = pd.to_numeric(
            month_matrix.loc[
                month_matrix[code] == 1,
                "analysis_month_number",
            ],
            errors="raise",
        ).astype(int).tolist()

        values = month_factor_map.loc[coded_months].to_numpy(
            dtype=float
        )

        macro_rows.append(
            {
                "theme_code": code,
                "theme_name": taxonomy.loc[
                    taxonomy["code"] == code,
                    "theme_name",
                ].iloc[0],
                "coded_extreme_month_count": len(values),
                "positive_factor_months": int(
                    np.sum(values > 0)
                ),
                "negative_factor_months": int(
                    np.sum(values < 0)
                ),
                "mean_signed_commonality_factor": float(
                    np.mean(values)
                ),
                "mean_absolute_commonality_factor": float(
                    np.mean(np.abs(values))
                ),
                "inferential_test_performed": 0,
            }
        )

    macro = pd.DataFrame(macro_rows)
    macro.to_csv(
        MACRO_PATH,
        index=False,
    )

    report = [
        rule(),
        "POST-H2 EXPLORATORY PHASE 4A — THEME SYNCHRONY",
        rule(),
        f"Script version: {SCRIPT_VERSION}",
        f"Taxonomy SHA-256: {checksum}",
        f"Randomization replications per tested theme: {RANDOMIZATION_REPLICATIONS:,}",
        f"Randomization seed: {RANDOMIZATION_SEED}",
        "Control universe: same 30 Phase 3A top-driver securities",
        "H1/H2 conclusions modified: NO",
        "",
        rule(),
        "1. SECURITY STRUCTURAL THEMES",
        rule(),
    ]

    for row in stats.sort_values(
        [
            "sync_exploratory_flag",
            "average_pairwise_contribution_correlation",
        ],
        ascending=[
            False,
            False,
        ],
    ).itertuples(index=False):
        if int(row.tested_randomization) == 1:
            report.append(
                f"{row.theme_code} | {row.theme_name:<49} | "
                f"n={int(row.theme_size):>2} | "
                f"sync={row.average_pairwise_contribution_correlation:+.4f} "
                f"(MC p={row.sync_monte_carlo_p_one_sided:.4f}, "
                f"Holm={row.sync_holm_p:.4f}) | "
                f"presence/|factor|={row.presence_count_vs_abs_commonality_correlation:+.4f} "
                f"(MC p={row.presence_monte_carlo_p_one_sided:.4f}, "
                f"Holm={row.presence_holm_p:.4f})"
            )
        else:
            report.append(
                f"{row.theme_code} | {row.theme_name:<49} | "
                f"n={int(row.theme_size):>2} | DESCRIPTIVE ONLY (<3 securities)"
            )

    report += [
        "",
        "Exploratory flags require a positive statistic and Holm-adjusted p < 0.05.",
        "A flag is conditional on the selected top-30 control universe and is not a full-S&P-500 result.",
        "",
        rule(),
        "2. MACRO THEME DESCRIPTIVES",
        rule(),
    ]

    for row in macro.itertuples(index=False):
        report.append(
            f"{row.theme_code} | {row.theme_name:<46} | "
            f"n={int(row.coded_extreme_month_count):>2} | "
            f"positive={int(row.positive_factor_months):>2} | "
            f"negative={int(row.negative_factor_months):>2} | "
            f"mean factor={row.mean_signed_commonality_factor:+.4%}"
        )

    report += [
        "",
        rule(),
        "3. INTERPRETATION BOUNDARY",
        rule(),
        "Phase 4A is exploratory and conditional on the 30 preselected top-driver securities.",
        "Randomization tests whether evidence-defined groups are more synchronized than random same-sized groups from those same 30 securities.",
        "It does not establish causality, predictability, or a full-universe theme premium.",
        "Macro code summaries are descriptive only because the 15 months were selected by extreme absolute commonality and factor signs were already exposed in Phase 3D.",
        "No H1 or H2 parameter or conclusion is modified.",
        "",
        "POST_H2_PHASE4A_THEME_SYNCHRONY_COMPLETE",
    ]

    REPORT_PATH.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )
    print("\n".join(report))


if __name__ == "__main__":
    main()
