from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

STANDARDIZED_PATH = ROOT / "data" / "interim" / "standardized_price_history.csv.gz"
MANIFEST_PATH = ROOT / "data" / "interim" / "standardized_price_history_manifest.csv"
MEMBERSHIP_PATH = ROOT / "data" / "interim" / "sp500_membership_intervals_2021_2025.csv"
TICKER_HISTORY_PATH = ROOT / "data" / "interim" / "sp500_ticker_history_2021_2025.csv"

REPORT_PATH = (
    ROOT
    / "reports"
    / "data_quality"
    / "momentum_lookback_scope_correction_inspection.txt"
)
MONTHLY_COVERAGE_PATH = (
    ROOT / "data" / "interim" / "momentum_lookback_scope_monthly_coverage.csv"
)
INCOMPLETE_PATH = (
    ROOT / "data" / "interim" / "momentum_lookback_scope_incomplete.csv"
)
DUPLICATE_CONFLICT_PATH = (
    ROOT / "data" / "interim" / "momentum_lookback_scope_duplicate_conflicts.csv"
)

EXPECTED_STANDARDIZED_ROWS = 783_086
EXPECTED_MANIFEST_ROWS = 596
EXPECTED_MEMBERSHIP_ROWS = 593
EXPECTED_TICKER_ROWS = 594
EXPECTED_RANKING_MONTHS = 60

# Already-validated snapshot-only counts. The inspection must reproduce these
# before the corrected pre-membership support logic is trusted.
CURRENT_STYLE_EXPECTED = {
    1: 29_623,
    3: 28_464,
    6: 26_752,
    12: 23_401,
}
CURRENT_STYLE_MOMENTUM_EXPECTED = 23_401
CURRENT_STYLE_RANKING_MONTHS = 48

PRICE_RTOL = 1e-10
PRICE_ATOL = 1e-10


def section(title: str) -> list[str]:
    rule = "=" * 108
    return [rule, title, rule]


def require_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    label: str,
) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise RuntimeError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def month_end_map(spy: pd.DataFrame) -> dict[pd.Period, pd.Timestamp]:
    working = spy[["date"]].copy()
    working["month"] = working["date"].dt.to_period("M")
    return working.groupby("month", sort=True)["date"].max().to_dict()


def active_ticker_for_month(
    membership: pd.DataFrame,
    ticker_history: pd.DataFrame,
    ranking_date: pd.Timestamp,
) -> pd.DataFrame:
    active_membership = membership[
        (membership["valid_from"] <= ranking_date)
        & (membership["valid_to_exclusive"] > ranking_date)
    ][["security_key"]].copy()

    active_ticker = ticker_history[
        (ticker_history["ticker_valid_from"] <= ranking_date)
        & (ticker_history["ticker_valid_to_exclusive"] > ranking_date)
    ][["security_key", "ticker"]].copy()

    result = active_membership.merge(
        active_ticker,
        on="security_key",
        how="left",
        validate="one_to_one",
    )

    missing = result[result["ticker"].isna()]
    if not missing.empty:
        raise RuntimeError(
            "Active membership rows without an active ticker on "
            f"{ranking_date.date()}: "
            + ", ".join(missing["security_key"].astype(str).head(20))
        )

    return result


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MONTHLY_COVERAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    failures: list[str] = []
    passed = 0

    def check(condition: bool, success: str, failure: str) -> None:
        nonlocal passed
        if condition:
            lines.append(f"PASS: {success}")
            passed += 1
        else:
            lines.append(f"FAIL: {failure}")
            failures.append(failure)

    try:
        lines += section(
            "MOMENTUM LOOKBACK SCOPE CORRECTION — READ-ONLY INSPECTION"
        )
        lines += [
            "Purpose: quantify the effect of restoring validated pre-membership price history to feature construction.",
            "Database modifications: 0",
            "Azure SQL connection required: NO",
            "",
        ]

        for path in (
            STANDARDIZED_PATH,
            MANIFEST_PATH,
            MEMBERSHIP_PATH,
            TICKER_HISTORY_PATH,
        ):
            if not path.exists():
                raise FileNotFoundError(f"Required input not found: {path}")

        print("Loading standardized price history...")
        prices = pd.read_csv(STANDARDIZED_PATH, low_memory=False)
        manifest = pd.read_csv(MANIFEST_PATH, low_memory=False)
        membership = pd.read_csv(MEMBERSHIP_PATH, low_memory=False)
        ticker_history = pd.read_csv(TICKER_HISTORY_PATH, low_memory=False)

        require_columns(
            prices,
            ("security_key", "project_ticker", "date", "adjusted_close"),
            "standardized price history",
        )
        require_columns(
            manifest,
            (
                "security_key",
                "project_ticker",
                "first_date",
                "last_date",
                "effective_expected_start",
                "effective_expected_end_exclusive",
            ),
            "standardized manifest",
        )
        require_columns(
            membership,
            ("security_key", "valid_from", "valid_to_exclusive"),
            "membership intervals",
        )
        require_columns(
            ticker_history,
            (
                "security_key",
                "ticker",
                "ticker_valid_from",
                "ticker_valid_to_exclusive",
            ),
            "ticker history",
        )

        prices["security_key"] = prices["security_key"].astype(str).str.strip()
        prices["project_ticker"] = prices["project_ticker"].astype(str).str.strip()
        prices["date"] = pd.to_datetime(prices["date"], errors="raise")
        prices["adjusted_close"] = pd.to_numeric(
            prices["adjusted_close"], errors="raise"
        )

        membership["security_key"] = membership["security_key"].astype(str).str.strip()
        membership["valid_from"] = pd.to_datetime(
            membership["valid_from"], errors="raise"
        )
        membership["valid_to_exclusive"] = pd.to_datetime(
            membership["valid_to_exclusive"], errors="raise"
        )

        ticker_history["security_key"] = ticker_history["security_key"].astype(str).str.strip()
        ticker_history["ticker"] = ticker_history["ticker"].astype(str).str.strip()
        ticker_history["ticker_valid_from"] = pd.to_datetime(
            ticker_history["ticker_valid_from"], errors="raise"
        )
        ticker_history["ticker_valid_to_exclusive"] = pd.to_datetime(
            ticker_history["ticker_valid_to_exclusive"], errors="raise"
        )

        lines += section("1. INPUT ANCHORS")
        check(
            len(prices) == EXPECTED_STANDARDIZED_ROWS,
            f"Standardized price history contains {len(prices):,} rows.",
            f"Standardized price history contains {len(prices):,} rows; expected {EXPECTED_STANDARDIZED_ROWS:,}.",
        )
        check(
            len(manifest) == EXPECTED_MANIFEST_ROWS,
            f"Standardized manifest contains {len(manifest):,} rows.",
            f"Standardized manifest contains {len(manifest):,} rows; expected {EXPECTED_MANIFEST_ROWS:,}.",
        )
        check(
            len(membership) == EXPECTED_MEMBERSHIP_ROWS,
            f"Membership interval table contains {len(membership):,} rows.",
            f"Membership interval table contains {len(membership):,} rows; expected {EXPECTED_MEMBERSHIP_ROWS:,}.",
        )
        check(
            len(ticker_history) == EXPECTED_TICKER_ROWS,
            f"Ticker-history table contains {len(ticker_history):,} rows.",
            f"Ticker-history table contains {len(ticker_history):,} rows; expected {EXPECTED_TICKER_ROWS:,}.",
        )
        check(
            prices["adjusted_close"].notna().all()
            and (prices["adjusted_close"] > 0).all(),
            "All standardized adjusted-close values are positive and non-null.",
            "Standardized adjusted-close contains null or nonpositive values.",
        )

        if failures:
            raise RuntimeError("Input anchor validation failed.")

        lines.append("")
        lines += section("2. SPY CALENDAR AND SUPPORT WINDOW")

        spy = prices[prices["project_ticker"] == "SPY"].copy()
        check(
            not spy.empty,
            f"SPY standardized history is present with {len(spy):,} rows.",
            "SPY is missing from standardized price history.",
        )

        spy_month_ends = month_end_map(spy)
        support_periods = pd.period_range("2020-01", "2025-12", freq="M")
        ranking_periods = pd.period_range("2021-01", "2025-12", freq="M")

        missing_support_months = [
            str(period) for period in support_periods if period not in spy_month_ends
        ]
        check(
            not missing_support_months,
            "SPY provides an exact month-end trading anchor for every month from 2020-01 through 2025-12.",
            "Missing SPY support months: " + ", ".join(missing_support_months),
        )
        check(
            len(ranking_periods) == EXPECTED_RANKING_MONTHS,
            "The intended ranking calendar contains exactly 60 months (2021-01 through 2025-12).",
            f"Ranking calendar contains {len(ranking_periods)} months.",
        )

        if failures:
            raise RuntimeError("SPY support calendar validation failed.")

        lines.append("")
        lines += section("3. SECURITY-IDENTITY PRICE SUPPORT")

        constituent_prices = prices[
            ~prices["project_ticker"].isin({"SPY", "^GSPC"})
        ][["security_key", "project_ticker", "date", "adjusted_close"]].copy()

        duplicate_mask = constituent_prices.duplicated(
            ["security_key", "date"], keep=False
        )
        duplicate_rows = constituent_prices[duplicate_mask].copy()
        conflict_groups: list[pd.DataFrame] = []
        duplicate_groups = 0

        if not duplicate_rows.empty:
            for _, group in duplicate_rows.groupby(
                ["security_key", "date"], sort=False
            ):
                duplicate_groups += 1
                values = group["adjusted_close"].to_numpy(dtype=float)
                if not np.allclose(
                    values,
                    values[0],
                    rtol=PRICE_RTOL,
                    atol=PRICE_ATOL,
                ):
                    conflict_groups.append(group.copy())

        if conflict_groups:
            conflicts = pd.concat(conflict_groups, ignore_index=True)
            conflicts.to_csv(DUPLICATE_CONFLICT_PATH, index=False)
            check(
                False,
                "",
                f"{len(conflict_groups):,} security/date duplicate groups contain conflicting adjusted-close values. See {DUPLICATE_CONFLICT_PATH.relative_to(ROOT)}.",
            )
            raise RuntimeError(
                "Conflicting permanent-identity price support must be resolved before feature correction."
            )

        check(
            True,
            (
                f"Permanent-identity support contains {duplicate_groups:,} duplicate security/date group(s), all price-consistent."
                if duplicate_groups
                else "Permanent-identity support contains no duplicate security/date groups."
            ),
            "",
        )

        canonical_support = (
            constituent_prices.sort_values(
                ["security_key", "date", "project_ticker"]
            )
            .drop_duplicates(["security_key", "date"], keep="first")
            .reset_index(drop=True)
        )

        support_price = {
            (str(row.security_key), pd.Timestamp(row.date)): float(row.adjusted_close)
            for row in canonical_support.itertuples(index=False)
        }
        exact_ticker_price = {
            (
                str(row.security_key),
                str(row.project_ticker),
                pd.Timestamp(row.date),
            ): float(row.adjusted_close)
            for row in constituent_prices.itertuples(index=False)
        }

        lines.append("")
        lines += section("4. RECONSTRUCT CURRENT SNAPSHOT-ONLY FEATURE LOGIC")
        print("Reconstructing 60 point-in-time ranking months...")

        snapshot_rows: list[dict[str, object]] = []

        for analysis_month_number, period in enumerate(ranking_periods, start=1):
            ranking_date = pd.Timestamp(spy_month_ends[period])
            active = active_ticker_for_month(
                membership, ticker_history, ranking_date
            )

            for row in active.itertuples(index=False):
                key = (str(row.security_key), str(row.ticker), ranking_date)
                current_price = exact_ticker_price.get(key)
                if current_price is None:
                    # Membership alone is not enough. This mirrors the bridge:
                    # a usable exact-date market price must also exist.
                    continue

                snapshot_rows.append(
                    {
                        "analysis_month_number": analysis_month_number,
                        "ranking_period": str(period),
                        "ranking_date": ranking_date,
                        "security_key": str(row.security_key),
                        "project_ticker": str(row.ticker),
                        "adjusted_close": current_price,
                    }
                )

        snapshot = pd.DataFrame(snapshot_rows).sort_values(
            ["analysis_month_number", "security_key"]
        )

        check(
            len(snapshot) == 30_211,
            "Local reconstruction reproduces the validated 30,211 constituent month-end snapshot rows.",
            f"Local reconstruction produced {len(snapshot):,} snapshot rows; expected 30,211.",
        )
        check(
            not snapshot.duplicated(
                ["analysis_month_number", "security_key"]
            ).any(),
            "Reconstructed month/security snapshot keys are unique.",
            "Duplicate month/security keys exist in reconstructed snapshot.",
        )

        snapshot_lookup = {
            (str(row.security_key), int(row.analysis_month_number)): float(
                row.adjusted_close
            )
            for row in snapshot.itertuples(index=False)
        }

        current_style_complete: dict[int, int] = {}
        for horizon in (1, 3, 6, 12):
            count = 0
            for row in snapshot.itertuples(index=False):
                lag_month = int(row.analysis_month_number) - horizon
                if (
                    lag_month >= 1
                    and (str(row.security_key), lag_month) in snapshot_lookup
                ):
                    count += 1
            current_style_complete[horizon] = count
            expected = CURRENT_STYLE_EXPECTED[horizon]
            check(
                count == expected,
                f"Current snapshot-only {horizon}-month completeness reproduced exactly: {count:,} rows.",
                f"Current snapshot-only {horizon}-month completeness is {count:,}; expected {expected:,}.",
            )

        current_style_momentum_by_month: dict[int, int] = {}
        current_style_momentum = 0

        for row in snapshot.itertuples(index=False):
            month_no = int(row.analysis_month_number)
            security_key = str(row.security_key)
            complete = (
                month_no - 1 >= 1
                and month_no - 12 >= 1
                and (security_key, month_no - 1) in snapshot_lookup
                and (security_key, month_no - 12) in snapshot_lookup
            )
            if complete:
                current_style_momentum += 1
                current_style_momentum_by_month[month_no] = (
                    current_style_momentum_by_month.get(month_no, 0) + 1
                )

        check(
            current_style_momentum == CURRENT_STYLE_MOMENTUM_EXPECTED,
            f"Current snapshot-only canonical 12-1 momentum population reproduced exactly: {current_style_momentum:,} rows.",
            f"Current-style momentum population is {current_style_momentum:,}; expected {CURRENT_STYLE_MOMENTUM_EXPECTED:,}.",
        )

        old_ranking_months = [
            month
            for month, count in current_style_momentum_by_month.items()
            if count > 0
        ]
        check(
            len(old_ranking_months) == CURRENT_STYLE_RANKING_MONTHS
            and min(old_ranking_months, default=0) == 13
            and max(old_ranking_months, default=0) == 60,
            "Current snapshot-only momentum correctly reproduces 48 ranking months spanning analysis months 13 through 60.",
            "Current-style ranking-month reconstruction differs from the validated 48-month / analysis-month 13-60 state.",
        )

        if failures:
            raise RuntimeError(
                "Current-state reconciliation failed. Do not modify Azure SQL."
            )

        lines.append("")
        lines += section("5. CORRECTED PRE-MEMBERSHIP LOOKBACK FEATURE LOGIC")

        corrected_complete = {1: 0, 3: 0, 6: 0, 12: 0}
        corrected_momentum = 0
        corrected_rows: list[dict[str, object]] = []
        incomplete_rows: list[dict[str, object]] = []

        for row in snapshot.itertuples(index=False):
            month_no = int(row.analysis_month_number)
            ranking_period = pd.Period(str(row.ranking_period), freq="M")
            ranking_date = pd.Timestamp(row.ranking_date)
            security_key = str(row.security_key)

            lag_dates: dict[int, pd.Timestamp | None] = {}
            lag_prices: dict[int, float | None] = {}

            for horizon in (1, 3, 6, 12):
                lag_period = ranking_period - horizon
                lag_date = spy_month_ends.get(lag_period)
                lag_dates[horizon] = (
                    pd.Timestamp(lag_date) if lag_date is not None else None
                )
                lag_price = (
                    support_price.get((security_key, pd.Timestamp(lag_date)))
                    if lag_date is not None
                    else None
                )
                lag_prices[horizon] = lag_price
                if lag_price is not None:
                    corrected_complete[horizon] += 1

            lag_1 = lag_prices[1]
            lag_12 = lag_prices[12]
            momentum_complete = lag_1 is not None and lag_12 is not None

            if momentum_complete:
                corrected_momentum += 1
                momentum_value = float(lag_1 / lag_12 - 1.0)
            else:
                momentum_value = None

            old_complete = (
                month_no - 1 >= 1
                and month_no - 12 >= 1
                and (security_key, month_no - 1) in snapshot_lookup
                and (security_key, month_no - 12) in snapshot_lookup
            )

            corrected_rows.append(
                {
                    "analysis_month_number": month_no,
                    "ranking_period": str(ranking_period),
                    "ranking_date": ranking_date.date(),
                    "security_key": security_key,
                    "project_ticker": str(row.project_ticker),
                    "current_adjusted_close": float(row.adjusted_close),
                    "lag_1_date": (
                        lag_dates[1].date() if lag_dates[1] is not None else None
                    ),
                    "lag_1_adjusted_close": lag_1,
                    "lag_3_available": int(lag_prices[3] is not None),
                    "lag_6_available": int(lag_prices[6] is not None),
                    "lag_12_date": (
                        lag_dates[12].date()
                        if lag_dates[12] is not None
                        else None
                    ),
                    "lag_12_adjusted_close": lag_12,
                    "momentum_12_1_complete": int(momentum_complete),
                    "momentum_12_1": momentum_value,
                    "current_snapshot_style_complete": int(old_complete),
                    "restored_by_support_history": int(
                        momentum_complete and not old_complete
                    ),
                }
            )

            if not momentum_complete:
                missing_parts: list[str] = []
                if lag_1 is None:
                    missing_parts.append("month_minus_1")
                if lag_12 is None:
                    missing_parts.append("month_minus_12")
                incomplete_rows.append(
                    {
                        "analysis_month_number": month_no,
                        "ranking_period": str(ranking_period),
                        "ranking_date": ranking_date.date(),
                        "security_key": security_key,
                        "project_ticker": str(row.project_ticker),
                        "missing_anchor": "+".join(missing_parts),
                        "lag_1_date": (
                            lag_dates[1].date()
                            if lag_dates[1] is not None
                            else None
                        ),
                        "lag_12_date": (
                            lag_dates[12].date()
                            if lag_dates[12] is not None
                            else None
                        ),
                    }
                )

        corrected = pd.DataFrame(corrected_rows)
        incomplete = pd.DataFrame(incomplete_rows)

        monthly_records: list[dict[str, object]] = []
        for month_no, period in enumerate(ranking_periods, start=1):
            month_rows = corrected[
                corrected["analysis_month_number"] == month_no
            ]
            corrected_count = int(month_rows["momentum_12_1_complete"].sum())
            restored_count = int(month_rows["restored_by_support_history"].sum())
            current_count = int(
                month_rows["current_snapshot_style_complete"].sum()
            )

            monthly_records.append(
                {
                    "analysis_month_number": month_no,
                    "ranking_period": str(period),
                    "ranking_date": pd.Timestamp(spy_month_ends[period]).date(),
                    "ranking_eligible_rows": len(month_rows),
                    "current_snapshot_style_momentum": current_count,
                    "corrected_support_style_momentum": corrected_count,
                    "restored_by_support_history": restored_count,
                    "corrected_incomplete": len(month_rows) - corrected_count,
                }
            )

        monthly = pd.DataFrame(monthly_records)
        monthly.to_csv(MONTHLY_COVERAGE_PATH, index=False)
        incomplete.to_csv(INCOMPLETE_PATH, index=False)

        corrected_ranking_months = int(
            (monthly["corrected_support_style_momentum"] > 0).sum()
        )
        restored_total = int(corrected["restored_by_support_history"].sum())

        check(
            corrected_ranking_months == 60,
            "Corrected momentum support produces eligible signals in all 60 ranking months from 2021-01 through 2025-12.",
            f"Corrected momentum support produces signals in only {corrected_ranking_months} of 60 months.",
        )
        check(
            corrected_momentum >= current_style_momentum,
            f"Corrected momentum population is {corrected_momentum:,} rows, restoring {restored_total:,} previously excluded signals.",
            "Corrected momentum population is unexpectedly smaller than the current snapshot-only population.",
        )

        lines += [
            "",
            "Corrected constituent feature completeness:",
            f"  1-month:  {corrected_complete[1]:,}",
            f"  3-month:  {corrected_complete[3]:,}",
            f"  6-month:  {corrected_complete[6]:,}",
            f"  12-month: {corrected_complete[12]:,}",
            f"  12-1 momentum: {corrected_momentum:,}",
            f"  Signals restored by support history: {restored_total:,}",
            f"  Corrected incomplete 12-1 rows: {len(incomplete):,}",
        ]

        lines.append("")
        lines += section("6. 2021 MONTH-BY-MONTH CORRECTION")

        for row in monthly[
            monthly["analysis_month_number"].between(1, 12)
        ].itertuples(index=False):
            lines.append(
                f"{row.ranking_period} | "
                f"ranking eligible {row.ranking_eligible_rows:>3} | "
                f"old complete {row.current_snapshot_style_momentum:>3} | "
                f"corrected complete {row.corrected_support_style_momentum:>3} | "
                f"restored {row.restored_by_support_history:>3} | "
                f"still incomplete {row.corrected_incomplete:>3}"
            )

        lines.append("")
        lines += section("7. BENCHMARK SUPPORT COVERAGE")

        benchmark_rows: list[dict[str, object]] = []
        for benchmark_ticker in ("SPY", "^GSPC"):
            benchmark = prices[
                prices["project_ticker"] == benchmark_ticker
            ][["date", "adjusted_close"]].copy()
            benchmark_lookup = {
                pd.Timestamp(row.date): float(row.adjusted_close)
                for row in benchmark.itertuples(index=False)
            }

            for month_no, period in enumerate(ranking_periods, start=1):
                ranking_date = pd.Timestamp(spy_month_ends[period])
                current = benchmark_lookup.get(ranking_date)

                record: dict[str, object] = {
                    "benchmark": benchmark_ticker,
                    "analysis_month_number": month_no,
                    "ranking_period": str(period),
                    "current_available": int(current is not None),
                }

                for horizon in (1, 3, 6, 12):
                    lag_period = period - horizon
                    lag_date = spy_month_ends.get(lag_period)
                    available = (
                        lag_date is not None
                        and benchmark_lookup.get(pd.Timestamp(lag_date)) is not None
                    )
                    record[f"lag_{horizon}_available"] = int(available)

                lag1_date = spy_month_ends.get(period - 1)
                lag12_date = spy_month_ends.get(period - 12)
                momentum_complete = (
                    current is not None
                    and lag1_date is not None
                    and lag12_date is not None
                    and benchmark_lookup.get(pd.Timestamp(lag1_date)) is not None
                    and benchmark_lookup.get(pd.Timestamp(lag12_date)) is not None
                )
                record["momentum_12_1_complete"] = int(momentum_complete)
                benchmark_rows.append(record)

        benchmark_df = pd.DataFrame(benchmark_rows)
        benchmark_counts = {
            horizon: int(benchmark_df[f"lag_{horizon}_available"].sum())
            for horizon in (1, 3, 6, 12)
        }
        benchmark_momentum = int(
            benchmark_df["momentum_12_1_complete"].sum()
        )

        lines += [
            f"Benchmark feature rows: {len(benchmark_df):,}",
            f"Corrected benchmark 1-month complete rows: {benchmark_counts[1]:,}",
            f"Corrected benchmark 3-month complete rows: {benchmark_counts[3]:,}",
            f"Corrected benchmark 6-month complete rows: {benchmark_counts[6]:,}",
            f"Corrected benchmark 12-month complete rows: {benchmark_counts[12]:,}",
            f"Corrected benchmark 12-1 momentum rows: {benchmark_momentum:,}",
        ]
        check(
            len(benchmark_df) == 120,
            "Benchmark ranking panel contains exactly 120 rows (2 series x 60 months).",
            f"Benchmark ranking panel contains {len(benchmark_df)} rows.",
        )

        lines.append("")
        lines += section("8. CORRECTION DIAGNOSIS")
        lines += [
            "CONFIRMED DESIGN ISSUE:",
            "The existing SQL feature layer uses the membership-clipped month-end snapshot as both the ranking-date source and the historical lag-price source.",
            "That correctly restricts the ranking universe, but it also removes validated pre-membership prices that were acquired specifically for trailing feature construction.",
            "",
            "CORRECT DESIGN:",
            "1. Ranking-date eligibility remains point-in-time, membership/ticker/tradability constrained.",
            "2. Historical lag anchors use validated standardized price support by permanent security identity, even when the lag date precedes S&P 500 membership.",
            "3. Support rows never become portfolio members merely because their prices exist.",
            "4. 2020 remains feature-support history only; the analytical ranking window remains 2021-2025.",
            "",
            "IMPORTANT: the correction is broader than adding the twelve 2021 ranking months. It can also restore momentum signals for securities newly added to the S&P 500 during 2021-2025 when their validated pre-membership price history is complete.",
            "",
            f"Monthly coverage file: {MONTHLY_COVERAGE_PATH.relative_to(ROOT)}",
            f"Incomplete-signal file: {INCOMPLETE_PATH.relative_to(ROOT)}",
        ]

        if failures:
            lines += [
                "",
                "MOMENTUM_LOOKBACK_SCOPE_CORRECTION_INSPECTION_FAILED",
                f"Passed checks: {passed}",
                f"Failed checks: {len(failures)}",
            ]
        else:
            lines += [
                "",
                "MOMENTUM_LOOKBACK_SCOPE_CORRECTION_INSPECTION_PASSED",
                f"Passed checks: {passed}",
                "Database modifications performed: 0",
                "Existing Azure SQL analytical objects modified: 0",
                "Next action: create a corrective feature-support migration using the exact counts reported above.",
            ]

    except Exception as error:
        failures.append(str(error))
        lines += [
            "",
            *section("INSPECTION EXECUTION FAILED"),
            type(error).__name__,
            str(error),
            "MOMENTUM_LOOKBACK_SCOPE_CORRECTION_INSPECTION_FAILED",
        ]

    finally:
        REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = "\n".join(lines) + "\n"
        print(report, end="")
        print(f"Report saved: {REPORT_PATH}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
