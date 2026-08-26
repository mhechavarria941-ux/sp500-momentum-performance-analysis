from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


SCRIPT_VERSION = "2026-08-26-v1-h3-june-2025-outcome-blind-tracer"

ROOT = Path(__file__).resolve().parents[2]

TARGET_MONTH = pd.Period("2025-06", freq="M")
NEIGHBOR_MONTHS = (
    pd.Period("2025-05", freq="M"),
    TARGET_MONTH,
    pd.Period("2025-07", freq="M"),
)

# This diagnostic is deliberately restricted to pre-outcome H3 attention
# artifacts. Filename screening occurs before any CSV data are opened.
SAFE_PATH_HINTS = (
    "h3",
    "attention",
    "gdelt",
    "issuer",
    "preregister",
    "preregistration",
)

FORBIDDEN_PATH_TOKENS = (
    "outcome",
    "return",
    "performance",
    "winner",
    "loser",
    "momentum",
    "forward",
    "holding",
    "excess",
    "wml",
)

FORBIDDEN_COLUMN_TOKENS = (
    "outcome",
    "return",
    "performance",
    "winner",
    "loser",
    "momentum",
    "forward",
    "holding_return",
    "excess_return",
    "wml",
)

TIME_COLUMN_PRIORITY = (
    "month",
    "predictor_month",
    "issuer_month",
    "attention_month",
    "year_month",
    "date",
    "event_date",
    "day",
    "issuer_date",
    "article_date",
    "document_date",
    "publication_date",
    "published_date",
    "datetime",
    "timestamp",
)

INTERESTING_COLUMN_TOKENS = (
    "eligible",
    "eligibility",
    "status",
    "reason",
    "attention",
    "document",
    "doc",
    "article",
    "count",
    "query",
    "alias",
    "issuer",
    "security",
    "cik",
)

SOURCE_SCRIPT_CANDIDATES = (
    ROOT / "src" / "analysis" / "prepare_h3_preregistered_attention_predictor.py",
    ROOT / "src" / "analysis" / "audit_h3_statistical_preregistration.py",
    ROOT / "src" / "analysis" / "audit_h3_statistical_preregistration_v2.py",
)


def line(width: int = 132) -> str:
    return "=" * width


def normalize(value: str) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def safe_filename(path: Path) -> bool:
    normalized = normalize(path.name)
    if any(token in normalized for token in FORBIDDEN_PATH_TOKENS):
        return False
    return any(token in normalized for token in SAFE_PATH_HINTS)


def forbidden_columns(columns: list[str]) -> list[str]:
    hits: set[str] = set()
    for col in columns:
        n = normalize(col)
        for token in FORBIDDEN_COLUMN_TOKENS:
            if token in n:
                hits.add(col)
    return sorted(hits)


def discover_csvs() -> list[Path]:
    out: list[Path] = []

    excluded_dir_names = {
        ".git",
        ".venv",
        "venv",
        "myvenv",
        "__pycache__",
        "node_modules",
    }

    for path in ROOT.rglob("*.csv"):
        if not path.is_file():
            continue

        try:
            parts = {normalize(x) for x in path.relative_to(ROOT).parts[:-1]}
        except ValueError:
            parts = set()

        if parts & excluded_dir_names:
            continue

        # Filename screening BEFORE opening.
        if not safe_filename(path):
            continue

        out.append(path.resolve())

    return sorted(set(out), key=lambda p: str(p).lower())


def parse_period_series(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    parsed: list[object] = []

    for raw in text.tolist():
        if pd.isna(raw) or str(raw).strip() == "":
            parsed.append(pd.NaT)
            continue

        value = str(raw).strip()

        # Canonical YYYY-MM
        if re.fullmatch(r"\d{4}-\d{2}", value):
            try:
                parsed.append(pd.Period(value, freq="M"))
                continue
            except Exception:
                pass

        # Compact YYYYMM
        if re.fullmatch(r"\d{6}", value):
            try:
                parsed.append(pd.Period(f"{value[:4]}-{value[4:6]}", freq="M"))
                continue
            except Exception:
                pass

        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            parsed.append(pd.NaT)
        else:
            parsed.append(dt.to_period("M"))

    return pd.Series(parsed, index=series.index, dtype="period[M]")


def choose_time_column(columns: list[str]) -> str | None:
    normalized_to_original = {normalize(c): c for c in columns}

    for preferred in TIME_COLUMN_PRIORITY:
        if preferred in normalized_to_original:
            return normalized_to_original[preferred]

    # Conservative fallback: only obvious date/month names.
    candidates = []
    for c in columns:
        n = normalize(c)
        if (
            n.endswith("_date")
            or n.endswith("_month")
            or n == "date"
            or n == "month"
        ):
            candidates.append(c)

    return candidates[0] if len(candidates) == 1 else None


def choose_interesting_columns(columns: list[str], time_col: str) -> list[str]:
    chosen = [time_col]

    for c in columns:
        if c == time_col:
            continue
        n = normalize(c)
        if any(token in n for token in INTERESTING_COLUMN_TOKENS):
            chosen.append(c)

    # Keep the read bounded.
    return chosen[:30]


def month_counts(periods: pd.Series) -> dict[str, int]:
    return {
        str(month): int((periods == month).sum())
        for month in NEIGHBOR_MONTHS
    }


def unique_days_for_target(df: pd.DataFrame, time_col: str, target_mask: pd.Series) -> tuple[int | None, str | None, str | None]:
    n = normalize(time_col)
    if "month" in n and "date" not in n:
        return None, None, None

    raw = pd.to_datetime(df.loc[target_mask, time_col], errors="coerce").dropna()
    if raw.empty:
        return 0, None, None

    days = raw.dt.normalize().drop_duplicates().sort_values()
    return (
        int(len(days)),
        str(days.iloc[0].date()),
        str(days.iloc[-1].date()),
    )


def top_value_counts(
    df: pd.DataFrame,
    target_mask: pd.Series,
    columns: list[str],
    limit_columns: int = 8,
    limit_values: int = 8,
) -> list[str]:
    out: list[str] = []

    inspected = 0
    for c in columns:
        if inspected >= limit_columns:
            break

        n = normalize(c)
        if not any(
            token in n
            for token in (
                "eligible",
                "eligibility",
                "status",
                "reason",
                "attention",
                "document",
                "doc_count",
                "article",
                "query",
                "alias",
            )
        ):
            continue

        subset = df.loc[target_mask, c]
        if subset.empty:
            continue

        inspected += 1

        # Numeric attention/count columns: concise summary.
        numeric = pd.to_numeric(subset, errors="coerce")
        if numeric.notna().sum() >= max(1, int(0.90 * len(subset))):
            usable = numeric.dropna()
            if usable.empty:
                out.append(f"      {c}: all missing")
            else:
                out.append(
                    f"      {c}: n={len(usable):,}, "
                    f"nonzero={(usable != 0).sum():,}, "
                    f"min={usable.min():.12g}, "
                    f"median={usable.median():.12g}, "
                    f"max={usable.max():.12g}"
                )
            continue

        counts = (
            subset.astype("string")
            .fillna("<NA>")
            .value_counts(dropna=False)
            .head(limit_values)
        )
        rendered = "; ".join(f"{idx}={int(val):,}" for idx, val in counts.items())
        out.append(f"      {c}: {rendered}")

    return out


def inspect_csv(path: Path) -> dict:
    try:
        header = list(pd.read_csv(path, nrows=0).columns)
    except Exception as exc:
        return {
            "path": path,
            "state": "HEADER_READ_FAILED",
            "error": repr(exc),
        }

    forbidden = forbidden_columns(header)
    if forbidden:
        return {
            "path": path,
            "state": "REJECTED_FORBIDDEN_COLUMNS",
            "forbidden": forbidden,
        }

    time_col = choose_time_column(header)
    if time_col is None:
        return {
            "path": path,
            "state": "NO_UNAMBIGUOUS_TIME_COLUMN",
            "columns": header,
        }

    usecols = choose_interesting_columns(header, time_col)

    try:
        df = pd.read_csv(path, usecols=usecols, low_memory=False)
    except Exception as exc:
        return {
            "path": path,
            "state": "DATA_READ_FAILED",
            "time_col": time_col,
            "error": repr(exc),
        }

    periods = parse_period_series(df[time_col])
    parseable = int(periods.notna().sum())

    if parseable == 0:
        return {
            "path": path,
            "state": "TIME_UNPARSEABLE",
            "time_col": time_col,
            "rows": len(df),
        }

    counts = month_counts(periods)
    target_mask = periods == TARGET_MONTH
    unique_days, first_day, last_day = unique_days_for_target(df, time_col, target_mask)

    observed = periods.dropna()
    observed_months = sorted(observed.unique())

    details = top_value_counts(
        df=df,
        target_mask=target_mask,
        columns=usecols,
    )

    return {
        "path": path,
        "state": "OK",
        "time_col": time_col,
        "rows": len(df),
        "parseable": parseable,
        "counts": counts,
        "unique_days": unique_days,
        "first_day": first_day,
        "last_day": last_day,
        "min_month": str(observed_months[0]) if observed_months else None,
        "max_month": str(observed_months[-1]) if observed_months else None,
        "details": details,
        "columns": header,
    }


def scan_source_scripts() -> list[str]:
    lines: list[str] = []
    patterns = (
        "2025-06",
        "202506",
        "2025-05",
        "2025-07",
        "2025-11",
        "2021-01",
        "predictor_month",
        "issuer_month",
        "attention_eligible",
        "eligibility",
        "date_range",
        "start_month",
        "end_month",
    )

    existing = [p for p in SOURCE_SCRIPT_CANDIDATES if p.exists()]

    if not existing:
        lines.append("No expected H3 preparation/audit source scripts found at known paths.")
        return lines

    for path in existing:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        matches: list[tuple[int, str]] = []

        for i, source_line in enumerate(text, start=1):
            low = source_line.lower()
            if any(pattern.lower() in low for pattern in patterns):
                matches.append((i, source_line.rstrip()))

        lines.append(f"{rel(path)}")
        if not matches:
            lines.append("  No relevant literal/date/filter lines found.")
            continue

        for i, source_line in matches[:80]:
            lines.append(f"  L{i}: {source_line}")

        if len(matches) > 80:
            lines.append(f"  ... {len(matches) - 80} additional matches omitted.")

    return lines


def infer_first_break(results: list[dict]) -> list[str]:
    usable = [r for r in results if r.get("state") == "OK"]

    with_target = [
        r for r in usable
        if r["counts"][str(TARGET_MONTH)] > 0
    ]
    without_target = [
        r for r in usable
        if (
            r["counts"]["2025-05"] > 0
            and r["counts"]["2025-06"] == 0
            and r["counts"]["2025-07"] > 0
        )
    ]

    lines: list[str] = []

    if not usable:
        lines.append("No usable safe H3 attention CSVs could be time-profiled.")
        return lines

    if not with_target:
        lines.append(
            "June 2025 is absent from EVERY time-profiled safe H3 attention CSV."
        )
        lines.append(
            "Interpretation: the break is upstream of the final issuer-month/predictor "
            "construction, likely in the extracted attention source or an earlier "
            "preprocessing stage. Do not amend the predictor until the upstream source "
            "coverage is identified."
        )
        return lines

    lines.append(
        f"Safe files containing June 2025 rows: {len(with_target)}"
    )
    for r in with_target:
        lines.append(f"  PRESENT: {rel(r['path'])}")

    if without_target:
        lines.append("")
        lines.append(
            "Files with May and July present but June absent:"
        )
        for r in without_target:
            lines.append(f"  BREAK/ABSENCE: {rel(r['path'])}")

        lines.append("")
        lines.append(
            "Interpretation: June exists somewhere upstream but disappears in one or "
            "more downstream stages. The earliest such stage should be repaired under "
            "the frozen eligibility/aggregation rules, then all downstream predictor "
            "artifacts and checksums must be regenerated before outcome exposure."
        )
    else:
        lines.append("")
        lines.append(
            "No profiled file shows the exact May-present / June-absent / July-present "
            "pattern. Review files with missing/ambiguous time columns and the source "
            "script scan below."
        )

    return lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Outcome-blind tracer for the missing June 2025 H3 attention predictor month."
        )
    )
    parser.parse_args()

    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print(line())
    print("H3 JUNE-2025 MISSING-PREDICTOR TRACE — OUTCOME BLIND")
    print(line())
    print("Target month: 2025-06")
    print("Neighbor controls: 2025-05 and 2025-07")
    print("Return/outcome analysis permitted: NO")
    print("Outcome/return data intentionally read: 0")
    print(
        "Purpose: locate the first pre-outcome attention stage where June 2025 "
        "is absent."
    )

    candidates = discover_csvs()

    print("")
    print(line())
    print("1. SAFE H3 / ATTENTION CSV DISCOVERY")
    print(line())
    print(f"Safe filename candidates discovered: {len(candidates)}")
    for path in candidates:
        print(f"  {rel(path)}")

    results: list[dict] = []
    for path in candidates:
        results.append(inspect_csv(path))

    print("")
    print(line())
    print("2. MAY / JUNE / JULY 2025 COVERAGE BY SAFE FILE")
    print(line())

    ok_count = 0
    rejected_count = 0
    unresolved_count = 0

    for r in results:
        print("")
        print(f"FILE: {rel(r['path'])}")
        print(f"STATE: {r['state']}")

        if r["state"] == "REJECTED_FORBIDDEN_COLUMNS":
            rejected_count += 1
            print(
                "  Rejected before data read because forbidden outcome-like "
                "columns were detected in the header."
            )
            print("  Forbidden columns: " + ", ".join(r["forbidden"]))
            continue

        if r["state"] != "OK":
            unresolved_count += 1
            if "time_col" in r:
                print(f"  Time column: {r['time_col']}")
            if "rows" in r:
                print(f"  Rows: {r['rows']:,}")
            if "error" in r:
                print(f"  Error: {r['error']}")
            if r["state"] == "NO_UNAMBIGUOUS_TIME_COLUMN":
                print("  Columns: " + ", ".join(r["columns"]))
            continue

        ok_count += 1
        print(f"  Time column: {r['time_col']}")
        print(f"  Rows: {r['rows']:,}")
        print(f"  Parseable time rows: {r['parseable']:,}")
        print(f"  Observed month range: {r['min_month']} through {r['max_month']}")
        print(f"  2025-05 rows: {r['counts']['2025-05']:,}")
        print(f"  2025-06 rows: {r['counts']['2025-06']:,}")
        print(f"  2025-07 rows: {r['counts']['2025-07']:,}")

        if r["unique_days"] is not None:
            print(f"  2025-06 unique dates: {r['unique_days']:,}")
            if r["first_day"] is not None:
                print(f"  2025-06 first date: {r['first_day']}")
                print(f"  2025-06 last date: {r['last_day']}")

        if r["details"]:
            print("  2025-06 selected field diagnostics:")
            for detail in r["details"]:
                print(detail)

    print("")
    print(line())
    print("3. FIRST-BREAK INTERPRETATION")
    print(line())
    for text in infer_first_break(results):
        print(text)

    print("")
    print(line())
    print("4. PREPARATION-SOURCE FILTER / DATE-LITERAL SCAN")
    print(line())
    print(
        "This section reads Python source only. It does not execute H3 preparation "
        "and does not access outcome data."
    )
    for text in scan_source_scripts():
        print(text)

    print("")
    print(line())
    print("5. TRACE SUMMARY")
    print(line())
    print(f"Safe CSVs discovered: {len(candidates)}")
    print(f"Successfully time-profiled: {ok_count}")
    print(f"Rejected on forbidden columns before data read: {rejected_count}")
    print(f"Unresolved/no usable time profile: {unresolved_count}")
    print("Outcome/return data intentionally read: 0")
    print("H3_OUTCOME_JOIN_REMAINS_BLOCKED")
    print("H3_JUNE_2025_OUTCOME_BLIND_TRACE_COMPLETE")


if __name__ == "__main__":
    main()
