from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyodbc
from dotenv import load_dotenv

try:
    from scipy import stats
except ImportError as exc:
    raise RuntimeError(
        "This script requires scipy. Install it in MYVENV with: pip install scipy"
    ) from exc


ROOT = Path(__file__).resolve().parents[2]

REPORT_PATH = (
    ROOT
    / "reports"
    / "analysis"
    / "momentum_statistical_tests.txt"
)

ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

EXPECTED_SERIES = {
    "D01",
    "D02",
    "D03",
    "D04",
    "D05",
    "D06",
    "D07",
    "D08",
    "D09",
    "D10",
    "WML",
    "SPY",
    "SP500",
}

ALPHA = 0.05
BOOTSTRAP_REPLICATIONS = 50_000
BOOTSTRAP_SEED = 20260823
HAC_LAG = 3
TOLERANCE = 1e-12
EXPECTED_PANEL_ROWS = 767
EXPECTED_OBSERVED_MONTHS = 59
EXPECTED_FIRST_ANALYSIS_MONTH = 1
EXPECTED_LAST_ANALYSIS_MONTH = 59


def environment() -> tuple[str, str, str, str]:
    load_dotenv(ROOT / ".env")

    names = (
        "AZURE_SQL_SERVER",
        "AZURE_SQL_DATABASE",
        "AZURE_SQL_USERNAME",
        "AZURE_SQL_PASSWORD",
    )
    values = tuple(os.getenv(name) for name in names)
    missing = [
        name
        for name, value in zip(names, values)
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing environment variables: "
            + ", ".join(missing)
        )

    return values  # type: ignore[return-value]


def odbc_escape(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def connect_with_retry(
    server: str,
    database: str,
    username: str,
    password: str,
):
    if ODBC_DRIVER not in pyodbc.drivers():
        raise RuntimeError(
            f"{ODBC_DRIVER} is not installed. "
            f"Available drivers: {pyodbc.drivers()}"
        )

    connection_string = (
        f"DRIVER={{{ODBC_DRIVER}}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={odbc_escape(database)};"
        f"UID={odbc_escape(username)};"
        f"PWD={odbc_escape(password)};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )

    maximum_attempts = 5
    retry_wait_seconds = 15
    retryable_terms = (
        "08001",
        "08s01",
        "hyt00",
        "40613",
        "timeout",
        "not currently available",
        "unable to establish connection",
        "temporarily unavailable",
        "communication link failure",
        "10053",
    )

    for attempt in range(1, maximum_attempts + 1):
        try:
            connection = pyodbc.connect(
                connection_string,
                timeout=30,
                autocommit=True,
            )
            print(
                "ODBC connection established on attempt "
                f"{attempt} / {maximum_attempts}."
            )
            return connection
        except pyodbc.Error as error:
            retryable = any(
                term in str(error).lower()
                for term in retryable_terms
            )

            if not retryable or attempt == maximum_attempts:
                raise

            print(
                "ODBC connection attempt "
                f"{attempt} / {maximum_attempts} failed. "
                f"Retrying in {retry_wait_seconds} seconds."
            )
            time.sleep(retry_wait_seconds)

    raise RuntimeError(
        "ODBC connection retry loop ended unexpectedly."
    )


def fetch_dicts(cursor, query: str) -> list[dict[str, Any]]:
    cursor.execute(query)
    columns = [str(item[0]) for item in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


def rule() -> str:
    return "=" * 112


def section(title: str) -> list[str]:
    return ["", rule(), title, rule()]


def pct(value: float | None, digits: int = 3) -> str:
    if value is None or not math.isfinite(float(value)):
        return "N/A"
    return f"{float(value) * 100:.{digits}f}%"


def num(value: float | None, digits: int = 4) -> str:
    if value is None or not math.isfinite(float(value)):
        return "N/A"
    return f"{float(value):.{digits}f}"


def p_text(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "N/A"
    value = float(value)
    if value < 0.0001:
        return "<0.0001"
    return f"{value:.4f}"


def date_text(value: Any) -> str:
    if value is None:
        return "N/A"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def one_sample_t(values: np.ndarray) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    n = len(x)
    mean = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    se = sd / math.sqrt(n)
    t_stat = mean / se if se > 0 else math.nan
    p_value = (
        float(2.0 * stats.t.sf(abs(t_stat), df=n - 1))
        if math.isfinite(t_stat)
        else math.nan
    )
    critical = float(stats.t.ppf(0.975, df=n - 1))
    ci_low = mean - critical * se
    ci_high = mean + critical * se
    return {
        "n": float(n),
        "mean": mean,
        "sd": sd,
        "se": se,
        "t_stat": t_stat,
        "df": float(n - 1),
        "p_value": p_value,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def bootstrap_mean_ci(
    values: np.ndarray,
    replications: int = BOOTSTRAP_REPLICATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    x = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    n = len(x)

    # Chunked bootstrap avoids allocating one very large matrix.
    chunk_size = 5_000
    means: list[np.ndarray] = []
    remaining = replications

    while remaining > 0:
        current = min(chunk_size, remaining)
        indices = rng.integers(0, n, size=(current, n))
        means.append(np.mean(x[indices], axis=1))
        remaining -= current

    all_means = np.concatenate(means)
    low, high = np.percentile(all_means, [2.5, 97.5])
    return float(low), float(high)


def wilcoxon_test(values: np.ndarray) -> tuple[float, float]:
    x = np.asarray(values, dtype=float)
    if np.allclose(x, 0.0):
        return 0.0, 1.0
    result = stats.wilcoxon(
        x,
        zero_method="wilcox",
        correction=False,
        alternative="two-sided",
        mode="auto",
    )
    return float(result.statistic), float(result.pvalue)


def sign_test(values: np.ndarray) -> tuple[int, int, float]:
    x = np.asarray(values, dtype=float)
    positives = int(np.sum(x > 0))
    negatives = int(np.sum(x < 0))
    nonzero = positives + negatives

    if nonzero == 0:
        return positives, negatives, 1.0

    result = stats.binomtest(
        positives,
        n=nonzero,
        p=0.5,
        alternative="two-sided",
    )
    return positives, negatives, float(result.pvalue)


def newey_west_mean_test(
    values: np.ndarray,
    lag: int = HAC_LAG,
) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    n = len(x)
    mean = float(np.mean(x))
    residual = x - mean

    gamma0 = float(np.dot(residual, residual) / n)
    long_run_variance = gamma0

    max_lag = min(lag, n - 1)
    for k in range(1, max_lag + 1):
        gamma_k = float(
            np.dot(residual[k:], residual[:-k]) / n
        )
        weight = 1.0 - k / (max_lag + 1.0)
        long_run_variance += 2.0 * weight * gamma_k

    long_run_variance = max(long_run_variance, 0.0)
    se_mean = math.sqrt(long_run_variance / n)
    z_stat = mean / se_mean if se_mean > 0 else math.nan
    p_value = (
        float(2.0 * stats.norm.sf(abs(z_stat)))
        if math.isfinite(z_stat)
        else math.nan
    )
    critical = float(stats.norm.ppf(0.975))
    ci_low = mean - critical * se_mean
    ci_high = mean + critical * se_mean

    return {
        "mean": mean,
        "se": se_mean,
        "z_stat": z_stat,
        "p_value": p_value,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    items = sorted(
        p_values.items(),
        key=lambda item: item[1],
    )
    m = len(items)
    adjusted: dict[str, float] = {}
    running_max = 0.0

    for rank, (name, p_value) in enumerate(items, start=1):
        candidate = min(
            1.0,
            (m - rank + 1) * float(p_value),
        )
        running_max = max(running_max, candidate)
        adjusted[name] = running_max

    return adjusted


def sensitivity_summary(values: np.ndarray) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    n = len(x)

    best_index = int(np.argmax(x))
    worst_index = int(np.argmin(x))

    remove_best = np.delete(x, best_index)
    remove_worst = np.delete(x, worst_index)
    trim_both = np.delete(
        x,
        sorted([best_index, worst_index]),
    )

    loo_means = []
    loo_p_values = []
    for index in range(n):
        sample = np.delete(x, index)
        result = one_sample_t(sample)
        loo_means.append(result["mean"])
        loo_p_values.append(result["p_value"])

    return {
        "original_mean": float(np.mean(x)),
        "best_value": float(x[best_index]),
        "worst_value": float(x[worst_index]),
        "remove_best_mean": float(np.mean(remove_best)),
        "remove_best_p": one_sample_t(remove_best)["p_value"],
        "remove_worst_mean": float(np.mean(remove_worst)),
        "remove_worst_p": one_sample_t(remove_worst)["p_value"],
        "trim_both_mean": float(np.mean(trim_both)),
        "trim_both_p": one_sample_t(trim_both)["p_value"],
        "loo_mean_min": float(np.min(loo_means)),
        "loo_mean_max": float(np.max(loo_means)),
        "loo_p_min": float(np.min(loo_p_values)),
        "loo_p_max": float(np.max(loo_p_values)),
    }


def inferential_block(
    label: str,
    values: np.ndarray,
    bootstrap_seed_offset: int,
) -> tuple[list[str], dict[str, float]]:
    classical = one_sample_t(values)
    boot_low, boot_high = bootstrap_mean_ci(
        values,
        seed=BOOTSTRAP_SEED + bootstrap_seed_offset,
    )
    w_stat, w_p = wilcoxon_test(values)
    positives, negatives, sign_p = sign_test(values)
    hac = newey_west_mean_test(values)

    lines = [
        f"{label}",
        f"Observations: {int(classical['n'])}",
        f"Mean monthly return/spread: {pct(classical['mean'])}",
        f"Arithmetic annualization of monthly mean: {pct(classical['mean'] * 12.0)}",
        f"Monthly standard deviation: {pct(classical['sd'])}",
        (
            "Classical one-sample t-test: "
            f"t={num(classical['t_stat'])}, "
            f"df={int(classical['df'])}, "
            f"p={p_text(classical['p_value'])}"
        ),
        (
            "Classical 95% CI for mean: "
            f"[{pct(classical['ci_low'])}, {pct(classical['ci_high'])}]"
        ),
        (
            f"Bootstrap 95% mean CI ({BOOTSTRAP_REPLICATIONS:,} replications): "
            f"[{pct(boot_low)}, {pct(boot_high)}]"
        ),
        (
            "Wilcoxon signed-rank robustness test: "
            f"W={num(w_stat, 2)}, p={p_text(w_p)}"
        ),
        (
            "Sign test: "
            f"positive={positives}, negative={negatives}, "
            f"p={p_text(sign_p)}"
        ),
        (
            f"Newey-West/HAC mean test (lag {HAC_LAG}): "
            f"z={num(hac['z_stat'])}, p={p_text(hac['p_value'])}"
        ),
        (
            "Newey-West/HAC 95% CI for mean: "
            f"[{pct(hac['ci_low'])}, {pct(hac['ci_high'])}]"
        ),
    ]

    metrics = {
        "mean": classical["mean"],
        "t_p": classical["p_value"],
        "t_stat": classical["t_stat"],
        "ci_low": classical["ci_low"],
        "ci_high": classical["ci_high"],
        "bootstrap_low": boot_low,
        "bootstrap_high": boot_high,
        "wilcoxon_p": w_p,
        "sign_p": sign_p,
        "hac_p": hac["p_value"],
        "hac_ci_low": hac["ci_low"],
        "hac_ci_high": hac["ci_high"],
    }
    return lines, metrics


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = None
    lines: list[str] = [
        rule(),
        "S&P 500 MOMENTUM — FORMAL STATISTICAL TESTING CHECKPOINT",
        rule(),
        "Mode: READ-ONLY",
        "Source: validated Azure SQL monthly return panel",
        f"Primary significance level: {ALPHA:.2f}",
        "Primary tests: two-sided",
        f"Bootstrap replications: {BOOTSTRAP_REPLICATIONS:,}",
        f"Newey-West/HAC lag: {HAC_LAG}",
        (
            "Inference status: EXPLORATORY / POST-SELECTION. "
            "The descriptive results were reviewed before these tests were run."
        ),
        (
            "Interpretation rule: statistical significance in this sample is not "
            "treated as proof of future performance."
        ),
    ]

    try:
        server, database, username, password = environment()
        connection = connect_with_retry(
            server,
            database,
            username,
            password,
        )
        connection.timeout = 600
        cursor = connection.cursor()

        print("Loading validated monthly return panel...")
        rows = fetch_dicts(
            cursor,
            """
            SELECT
                analysis_month_number,
                ranking_month_end_date,
                return_period_end_date,
                series_code,
                series_name,
                series_sort_order,
                monthly_return
            FROM analytics.v_momentum_monthly_return_panel
            ORDER BY analysis_month_number, series_sort_order;
            """,
        )

        if len(rows) != EXPECTED_PANEL_ROWS:
            raise RuntimeError(
                f"Expected {EXPECTED_PANEL_ROWS} validated panel rows; found {len(rows)}."
            )

        series_codes = {
            str(row["series_code"])
            for row in rows
        }
        if series_codes != EXPECTED_SERIES:
            raise RuntimeError(
                "Unexpected analytical-series population. "
                f"Found: {sorted(series_codes)}"
            )

        keyed: dict[
            tuple[int, str],
            dict[str, Any],
        ] = {}

        for row in rows:
            key = (
                int(row["analysis_month_number"]),
                str(row["series_code"]),
            )
            if key in keyed:
                raise RuntimeError(
                    f"Duplicate month/series key detected: {key}"
                )
            if row["monthly_return"] is None:
                raise RuntimeError(
                    f"Null monthly return detected: {key}"
                )
            keyed[key] = row

        months = sorted({
            int(row["analysis_month_number"])
            for row in rows
        })
        if months != list(range(EXPECTED_FIRST_ANALYSIS_MONTH, EXPECTED_LAST_ANALYSIS_MONTH + 1)):
            raise RuntimeError(
                (
                    "Expected analysis months "
                    f"{EXPECTED_FIRST_ANALYSIS_MONTH} through "
                    f"{EXPECTED_LAST_ANALYSIS_MONTH}; found {months}."
                )
            )

        for month in months:
            month_codes = {
                str(row["series_code"])
                for row in rows
                if int(row["analysis_month_number"]) == month
            }
            if month_codes != EXPECTED_SERIES:
                raise RuntimeError(
                    f"Month {month} does not contain all 13 series."
                )

        lines += section("1. SOURCE AND DESIGN CONTROLS")
        lines += [
            f"PASS: Validated monthly return panel contains exactly {EXPECTED_PANEL_ROWS} rows.",
            "PASS: All 13 analytical series are present.",
            f"PASS: Exactly {EXPECTED_OBSERVED_MONTHS} observable performance months are present.",
            (
                "PASS: Analysis months are exactly "
                f"{EXPECTED_FIRST_ANALYSIS_MONTH} through "
                f"{EXPECTED_LAST_ANALYSIS_MONTH}."
            ),
            "PASS: Every month contains all 13 analytical series.",
            "PASS: Month/series keys are unique.",
            "PASS: No monthly returns are null.",
            (
                "NOTE: Statistical tests are exploratory because the portfolio "
                "results were inspected before this inferential checkpoint."
            ),
        ]

        def vector(code: str) -> np.ndarray:
            return np.array(
                [
                    float(keyed[(month, code)]["monthly_return"])
                    for month in months
                ],
                dtype=float,
            )

        d01 = vector("D01")
        d10 = vector("D10")
        wml = vector("WML")
        spy = vector("SPY")

        d10_minus_d01 = d10 - d01
        d10_minus_spy = d10 - spy

        max_wml_difference = float(
            np.max(np.abs(wml - d10_minus_d01))
        )
        if max_wml_difference > TOLERANCE:
            raise RuntimeError(
                "WML does not reconcile to D10 minus D01. "
                f"Maximum absolute difference: {max_wml_difference}"
            )

        lines += section("2. PRIMARY TEST — WML / D10 MINUS D01")
        wml_lines, wml_metrics = inferential_block(
            "Null hypothesis: mean monthly WML return = 0.",
            wml,
            bootstrap_seed_offset=1,
        )
        lines.extend(wml_lines)
        lines += [
            (
                "D10 minus D01 reconciliation maximum absolute difference: "
                f"{max_wml_difference:.12g}"
            ),
            (
                "Interpretation: the WML mean test and the paired D10-versus-D01 "
                "mean-difference test are the same underlying hypothesis."
            ),
        ]

        lines += section("3. PRIMARY TEST — D10 EXCESS RETURN VERSUS SPY")
        d10_spy_lines, d10_spy_metrics = inferential_block(
            "Null hypothesis: mean monthly D10 minus SPY return = 0.",
            d10_minus_spy,
            bootstrap_seed_offset=2,
        )
        lines.extend(d10_spy_lines)

        lines += section("4. EXTREME-MONTH AND LEAVE-ONE-OUT SENSITIVITY")
        wml_sensitivity = sensitivity_summary(wml)
        d10_spy_sensitivity = sensitivity_summary(d10_minus_spy)

        lines += [
            "WML sensitivity:",
            f"  Best monthly WML: {pct(wml_sensitivity['best_value'])}",
            f"  Worst monthly WML: {pct(wml_sensitivity['worst_value'])}",
            (
                "  Remove best month -> mean "
                f"{pct(wml_sensitivity['remove_best_mean'])}, "
                f"t-test p={p_text(wml_sensitivity['remove_best_p'])}"
            ),
            (
                "  Remove worst month -> mean "
                f"{pct(wml_sensitivity['remove_worst_mean'])}, "
                f"t-test p={p_text(wml_sensitivity['remove_worst_p'])}"
            ),
            (
                "  Remove both best and worst -> mean "
                f"{pct(wml_sensitivity['trim_both_mean'])}, "
                f"t-test p={p_text(wml_sensitivity['trim_both_p'])}"
            ),
            (
                "  Leave-one-out mean range: "
                f"[{pct(wml_sensitivity['loo_mean_min'])}, "
                f"{pct(wml_sensitivity['loo_mean_max'])}]"
            ),
            (
                "  Leave-one-out t-test p-value range: "
                f"[{p_text(wml_sensitivity['loo_p_min'])}, "
                f"{p_text(wml_sensitivity['loo_p_max'])}]"
            ),
            "",
            "D10 minus SPY sensitivity:",
            f"  Best monthly excess return: {pct(d10_spy_sensitivity['best_value'])}",
            f"  Worst monthly excess return: {pct(d10_spy_sensitivity['worst_value'])}",
            (
                "  Remove best month -> mean "
                f"{pct(d10_spy_sensitivity['remove_best_mean'])}, "
                f"t-test p={p_text(d10_spy_sensitivity['remove_best_p'])}"
            ),
            (
                "  Remove worst month -> mean "
                f"{pct(d10_spy_sensitivity['remove_worst_mean'])}, "
                f"t-test p={p_text(d10_spy_sensitivity['remove_worst_p'])}"
            ),
            (
                "  Remove both best and worst -> mean "
                f"{pct(d10_spy_sensitivity['trim_both_mean'])}, "
                f"t-test p={p_text(d10_spy_sensitivity['trim_both_p'])}"
            ),
            (
                "  Leave-one-out mean range: "
                f"[{pct(d10_spy_sensitivity['loo_mean_min'])}, "
                f"{pct(d10_spy_sensitivity['loo_mean_max'])}]"
            ),
            (
                "  Leave-one-out t-test p-value range: "
                f"[{p_text(d10_spy_sensitivity['loo_p_min'])}, "
                f"{p_text(d10_spy_sensitivity['loo_p_max'])}]"
            ),
        ]

        lines += section("5. CROSS-DECILE TREND TEST")
        decile_numbers = np.arange(1.0, 11.0)
        monthly_slopes = []
        monthly_spearman = []

        for month in months:
            decile_returns = np.array(
                [
                    float(
                        keyed[(month, f"D{decile:02d}")][
                            "monthly_return"
                        ]
                    )
                    for decile in range(1, 11)
                ],
                dtype=float,
            )

            slope, intercept = np.polyfit(
                decile_numbers,
                decile_returns,
                1,
            )
            _ = intercept
            monthly_slopes.append(float(slope))

            rho_result = stats.spearmanr(
                decile_numbers,
                decile_returns,
            )
            monthly_spearman.append(float(rho_result.statistic))

        monthly_slopes_array = np.array(
            monthly_slopes,
            dtype=float,
        )
        monthly_spearman_array = np.array(
            monthly_spearman,
            dtype=float,
        )

        slope_test = one_sample_t(monthly_slopes_array)
        slope_hac = newey_west_mean_test(monthly_slopes_array)
        slope_boot_low, slope_boot_high = bootstrap_mean_ci(
            monthly_slopes_array,
            seed=BOOTSTRAP_SEED + 3,
        )
        positive_slope_months = int(
            np.sum(monthly_slopes_array > 0)
        )
        slope_sign_p = float(
            stats.binomtest(
                positive_slope_months,
                n=len(monthly_slopes_array),
                p=0.5,
                alternative="two-sided",
            ).pvalue
        )

        rho_test = one_sample_t(monthly_spearman_array)
        positive_rho_months = int(
            np.sum(monthly_spearman_array > 0)
        )

        lines += [
            (
                f"Method: for each of the {EXPECTED_OBSERVED_MONTHS} months, regress the ten decile "
                "returns on decile number 1 through 10; then test the mean "
                "monthly slope against zero."
            ),
            f"Mean monthly decile slope: {pct(slope_test['mean'])} return per decile step",
            (
                "Arithmetic annualization of mean slope: "
                f"{pct(slope_test['mean'] * 12.0)} per decile step"
            ),
            (
                "Classical slope t-test: "
                f"t={num(slope_test['t_stat'])}, "
                f"df={int(slope_test['df'])}, "
                f"p={p_text(slope_test['p_value'])}"
            ),
            (
                "Classical 95% CI for mean slope: "
                f"[{pct(slope_test['ci_low'])}, {pct(slope_test['ci_high'])}]"
            ),
            (
                f"Bootstrap 95% slope CI ({BOOTSTRAP_REPLICATIONS:,} replications): "
                f"[{pct(slope_boot_low)}, {pct(slope_boot_high)}]"
            ),
            (
                f"Newey-West/HAC slope test (lag {HAC_LAG}): "
                f"z={num(slope_hac['z_stat'])}, "
                f"p={p_text(slope_hac['p_value'])}"
            ),
            (
                "Months with positive decile slope: "
                f"{positive_slope_months} of {EXPECTED_OBSERVED_MONTHS}; "
                f"sign-test p={p_text(slope_sign_p)}"
            ),
            (
                "Mean monthly Spearman rank correlation between decile and return: "
                f"{num(rho_test['mean'])}"
            ),
            (
                "Mean-Spearman t-test: "
                f"t={num(rho_test['t_stat'])}, "
                f"p={p_text(rho_test['p_value'])}"
            ),
            (
                "Months with positive Spearman correlation: "
                f"{positive_rho_months} of {EXPECTED_OBSERVED_MONTHS}"
            ),
        ]

        lines += section("6. MULTIPLE-TESTING CONTROL FOR PRIMARY HYPOTHESES")
        primary_raw = {
            "WML mean vs zero": float(wml_metrics["t_p"]),
            "D10 excess vs SPY": float(d10_spy_metrics["t_p"]),
            "Cross-decile mean slope vs zero": float(slope_test["p_value"]),
        }
        primary_adjusted = holm_adjust(primary_raw)

        for name in (
            "WML mean vs zero",
            "D10 excess vs SPY",
            "Cross-decile mean slope vs zero",
        ):
            raw_p = primary_raw[name]
            adjusted_p = primary_adjusted[name]
            decision = (
                "REJECT H0"
                if adjusted_p < ALPHA
                else "DO NOT REJECT H0"
            )
            lines.append(
                f"{name}: raw p={p_text(raw_p)}, "
                f"Holm-adjusted p={p_text(adjusted_p)} -> {decision}"
            )

        lines += [
            "",
            (
                "Note: D10 minus D01 is not added as a separate primary "
                "hypothesis because it is mathematically the same monthly "
                "spread as WML."
            ),
        ]

        lines += section("7. INTERPRETATION CHECKPOINT")

        def robust_direction(
            metrics: dict[str, float],
        ) -> str:
            evidence = [
                metrics["t_p"] < ALPHA,
                metrics["wilcoxon_p"] < ALPHA,
                metrics["hac_p"] < ALPHA,
                metrics["bootstrap_low"] > 0.0
                or metrics["bootstrap_high"] < 0.0,
            ]
            return (
                "MULTIPLE METHODS SUPPORT A NONZERO MEAN"
                if sum(evidence) >= 3
                else "EVIDENCE IS MIXED / NOT ROBUST ACROSS METHODS"
            )

        lines += [
            f"WML robustness summary: {robust_direction(wml_metrics)}",
            f"D10-minus-SPY robustness summary: {robust_direction(d10_spy_metrics)}",
            (
                "Primary inference remains exploratory/post-selection because "
                "the descriptive performance results were reviewed before "
                "formal testing."
            ),
            (
                "A statistically significant result here should be documented "
                "as sample evidence, not as proof of a persistent anomaly."
            ),
            (
                "A nonsignificant result does not prove that the effect is zero; "
                f"with only {EXPECTED_OBSERVED_MONTHS} months, "
                "statistical power may still be limited."
            ),
            (
                "No risk-free-rate adjustment, Sharpe ratio, regression alpha, "
                "or transaction-cost adjustment is introduced by this script."
            ),
        ]

        lines += section("8. FINAL CONTROL")
        lines += [
            "Database modifications performed: 0",
            "Validated source rows modified: 0",
            "Statistical-testing output is a read-only analytical report.",
            "",
            "MOMENTUM_STATISTICAL_TESTING_COMPLETE",
            f"Report saved: {REPORT_PATH}",
        ]

        cursor.close()

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    report_text = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(
        report_text,
        encoding="utf-8",
    )
    print(report_text)


if __name__ == "__main__":
    main()
