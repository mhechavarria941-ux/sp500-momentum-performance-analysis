from __future__ import annotations

import gzip
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

SCRIPT_VERSION = "2026-08-28-v1-h4-alpaca-sip-missing-minute-trade-diagnostic"

SYMBOL = "SPY"
FEED = "sip"
DATA_BASE_URL = "https://data.alpaca.markets"

RAW_DIR = Path("data/raw/source/intraday/alpaca/spy_1min_sip")
CALENDAR_PATH = RAW_DIR / "alpaca_market_calendar_2021_2025.json"
ACQUISITION_MANIFEST_PATH = Path(
    "data/interim/h4_spy_alpaca_1min_acquisition_manifest.json"
)

REPORT_PATH = Path(
    "reports/data_quality/h4_spy_alpaca_missing_minute_trade_diagnostic.txt"
)
JSON_PATH = Path(
    "reports/data_quality/h4_spy_alpaca_missing_minute_trade_diagnostic.json"
)

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

REQUEST_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 6
PAGE_LIMIT = 10000


def credentials() -> tuple[str, str]:
    key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in the local "
            "environment before running this diagnostic."
        )
    return key.strip(), secret.strip()


def headers(key: str, secret: str) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }


def request_json(
    url: str,
    *,
    hdrs: dict[str, str],
    params: dict[str, Any],
) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers=hdrs,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                sleep_seconds = (
                    float(retry_after)
                    if retry_after
                    else min(60.0, 2.0 ** attempt)
                )
                print(
                    f"  HTTP 429 rate limit; retrying after "
                    f"{sleep_seconds:.1f}s."
                )
                time.sleep(sleep_seconds)
                continue

            if 500 <= response.status_code < 600:
                sleep_seconds = min(60.0, 2.0 ** attempt)
                print(
                    f"  HTTP {response.status_code}; retrying after "
                    f"{sleep_seconds:.1f}s."
                )
                time.sleep(sleep_seconds)
                continue

            if response.status_code != 200:
                raise RuntimeError(
                    f"HTTP {response.status_code} for {response.url}: "
                    f"{response.text[:1000]}"
                )

            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Unexpected non-object JSON response.")
            return payload

        except (requests.RequestException, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if (
                isinstance(exc, RuntimeError)
                and "HTTP 4" in str(exc)
                and "429" not in str(exc)
            ):
                raise
            if attempt < MAX_ATTEMPTS:
                sleep_seconds = min(60.0, 2.0 ** attempt)
                print(
                    f"  Request error: {exc}. Retrying after "
                    f"{sleep_seconds:.1f}s."
                )
                time.sleep(sleep_seconds)

    raise RuntimeError(
        f"Request failed after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_calendar_time(session_date: str, hhmm: str) -> datetime:
    hour, minute = map(int, hhmm.split(":")[:2])
    d = datetime.fromisoformat(session_date)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=ET)


def expected_rth_minutes() -> set[datetime]:
    rows = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Missing or invalid Alpaca market calendar.")

    expected: set[datetime] = set()

    for row in rows:
        session_date = str(row["date"])
        start = parse_calendar_time(session_date, str(row["open"]))
        end = parse_calendar_time(session_date, str(row["close"]))

        t = start
        while t < end:
            expected.add(t)
            t += timedelta(minutes=1)

    return expected


def observed_rth_minutes() -> set[datetime]:
    manifest = json.loads(
        ACQUISITION_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    rows = manifest.get("months") or []
    if len(rows) != 60:
        raise RuntimeError(
            "Expected exactly 60 monthly acquisition-manifest rows."
        )

    observed: set[datetime] = set()

    calendar_rows = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    calendar = {str(r["date"]): r for r in calendar_rows}

    for rec in rows:
        path = Path(str(rec["file"]))
        if not path.exists():
            raise RuntimeError(f"Missing monthly raw file: {path}")

        with gzip.open(path, "rt", encoding="utf-8") as f:
            payload = json.load(f)

        for bar in payload.get("bars") or []:
            ts_raw = bar.get("t")
            if ts_raw is None:
                continue

            ts_et = parse_rfc3339(str(ts_raw)).astimezone(ET)
            session_date = ts_et.date().isoformat()
            session = calendar.get(session_date)
            if session is None:
                continue

            start = parse_calendar_time(session_date, str(session["open"]))
            end = parse_calendar_time(session_date, str(session["close"]))

            if start <= ts_et < end:
                observed.add(ts_et.replace(second=0, microsecond=0))

    return observed


def minute_bounds_utc(minute_et: datetime) -> tuple[str, str]:
    start_utc = minute_et.astimezone(UTC)
    end_utc = (
        minute_et + timedelta(minutes=1) - timedelta(microseconds=1)
    ).astimezone(UTC)

    return (
        start_utc.isoformat().replace("+00:00", "Z"),
        end_utc.isoformat().replace("+00:00", "Z"),
    )


def get_all_trades_for_minute(
    hdrs: dict[str, str],
    minute_et: datetime,
) -> list[dict[str, Any]]:
    start_utc, end_utc = minute_bounds_utc(minute_et)
    url = f"{DATA_BASE_URL}/v2/stocks/{SYMBOL}/trades"

    page_token: str | None = None
    trades: list[dict[str, Any]] = []

    while True:
        params: dict[str, Any] = {
            "start": start_utc,
            "end": end_utc,
            "limit": PAGE_LIMIT,
            "feed": FEED,
            "sort": "asc",
        }
        if page_token:
            params["page_token"] = page_token

        payload = request_json(url, hdrs=hdrs, params=params)

        page = payload.get("trades") or []
        if not isinstance(page, list):
            raise RuntimeError(
                "Unexpected Alpaca historical-trades payload."
            )

        trades.extend(page)
        page_token = payload.get("next_page_token")

        if not page_token:
            break

    return trades


def normalize_conditions(trade: dict[str, Any]) -> tuple[str, ...]:
    raw = trade.get("c")
    if raw is None:
        return tuple()
    if isinstance(raw, list):
        return tuple(str(x) for x in raw)
    return (str(raw),)


def summarize_trades(
    minute_et: datetime,
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    condition_counter: Counter[str] = Counter()
    tape_counter: Counter[str] = Counter()
    exchange_counter: Counter[str] = Counter()

    total_size = 0
    prices: list[float] = []
    earliest_trade: str | None = None
    latest_trade: str | None = None

    for trade in trades:
        conds = normalize_conditions(trade)
        cond_key = "|".join(conds) if conds else "<NO_CONDITION>"
        condition_counter[cond_key] += 1

        tape_counter[str(trade.get("z") or "<NONE>")] += 1
        exchange_counter[str(trade.get("x") or "<NONE>")] += 1

        size = trade.get("s")
        if size is not None:
            total_size += int(size)

        price = trade.get("p")
        if price is not None:
            prices.append(float(price))

        ts = trade.get("t")
        if ts is not None:
            ts_s = str(ts)
            if earliest_trade is None:
                earliest_trade = ts_s
            latest_trade = ts_s

    return {
        "minute_et": minute_et.isoformat(),
        "trade_count": len(trades),
        "total_reported_share_size": total_size,
        "min_trade_price": min(prices) if prices else None,
        "max_trade_price": max(prices) if prices else None,
        "earliest_trade_timestamp": earliest_trade,
        "latest_trade_timestamp": latest_trade,
        "condition_sets": dict(
            sorted(
                condition_counter.items(),
                key=lambda kv: (-kv[1], kv[0]),
            )
        ),
        "tapes": dict(tape_counter),
        "exchanges": dict(exchange_counter),
    }


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 120)
    print("H4 ALPACA SIP MISSING-MINUTE UNDERLYING-TRADE DIAGNOSTIC")
    print("=" * 120)
    print("H4 event triggers calculated: NO")
    print("H4 forward outcomes calculated: NO")
    print()

    for path in [CALENDAR_PATH, ACQUISITION_MANIFEST_PATH]:
        if not path.exists():
            raise RuntimeError(f"Missing required input: {path}")

    expected = expected_rth_minutes()
    observed = observed_rth_minutes()
    missing = sorted(expected - observed)

    print(f"Expected RTH minutes: {len(expected):,}")
    print(f"Observed RTH minutes: {len(observed):,}")
    print(f"Missing RTH minutes: {len(missing):,}")

    if not missing:
        raise RuntimeError(
            "No missing RTH minutes were discovered. "
            "This diagnostic is unnecessary."
        )

    key, secret = credentials()
    hdrs = headers(key, secret)

    results: list[dict[str, Any]] = []

    for i, minute_et in enumerate(missing, start=1):
        print(
            f"[{i:02d}/{len(missing):02d}] Querying underlying SIP trades for "
            f"{minute_et.isoformat()} ..."
        )
        trades = get_all_trades_for_minute(hdrs, minute_et)
        summary = summarize_trades(minute_et, trades)
        results.append(summary)
        print(
            f"  trades={summary['trade_count']:,}, "
            f"shares={summary['total_reported_share_size']:,}, "
            f"price_range=[{summary['min_trade_price']}, "
            f"{summary['max_trade_price']}]"
        )

    all_have_trades = all(int(r["trade_count"]) > 0 for r in results)
    total_trades = sum(int(r["trade_count"]) for r in results)
    total_size = sum(int(r["total_reported_share_size"]) for r in results)

    report_lines = [
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 120,
        "H4 ALPACA SIP MISSING-MINUTE UNDERLYING-TRADE DIAGNOSTIC",
        "=" * 120,
        f"Expected RTH minutes: {len(expected):,}",
        f"Observed RTH minutes: {len(observed):,}",
        f"Missing RTH minutes: {len(missing):,}",
        f"Missing minutes with at least one underlying SIP trade: "
        f"{sum(int(r['trade_count']) > 0 for r in results):,}",
        f"Total underlying trades across missing minutes: {total_trades:,}",
        f"Total reported share size across missing minutes: {total_size:,}",
        "H4 event triggers calculated: NO",
        "H4 forward outcomes calculated: NO",
        "",
    ]

    for r in results:
        report_lines.extend(
            [
                "-" * 120,
                f"Minute ET: {r['minute_et']}",
                f"Underlying SIP trades: {r['trade_count']:,}",
                f"Reported share size: {r['total_reported_share_size']:,}",
                f"Trade-price range: "
                f"[{r['min_trade_price']}, {r['max_trade_price']}]",
                f"Earliest trade: {r['earliest_trade_timestamp']}",
                f"Latest trade: {r['latest_trade_timestamp']}",
                "Condition-set counts:",
            ]
        )

        condition_items = list(r["condition_sets"].items())
        for cond, count in condition_items[:25]:
            report_lines.append(f"  {cond}: {count:,}")
        if len(condition_items) > 25:
            report_lines.append(
                f"  ... {len(condition_items) - 25} additional condition sets"
            )

    report_lines.extend(
        [
            "",
            "=" * 120,
            "DIAGNOSTIC DECISION",
            "=" * 120,
        ]
    )

    if all_have_trades:
        report_lines.extend(
            [
                "All missing minute-bar intervals contain underlying Alpaca SIP trades.",
                "",
                "Interpretation:",
                "The nine gaps are provider minute-aggregate omissions, not genuine no-trade minutes.",
                "",
                "H4_ALPACA_MISSING_MINUTES_HAVE_UNDERLYING_SIP_TRADES",
                "H4_SAME_PROVIDER_TRADE_RECONSTRUCTION_REVIEW_AUTHORIZED",
            ]
        )
    else:
        report_lines.extend(
            [
                "At least one missing minute contains no returned underlying SIP trades.",
                "",
                "Do not reconstruct missing bars yet.",
                "Cross-source or provider-support review remains required.",
                "",
                "H4_ALPACA_MISSING_MINUTE_TRADE_DIAGNOSTIC_REVIEW_REQUIRED",
            ]
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    REPORT_PATH.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )
    JSON_PATH.write_text(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "symbol": SYMBOL,
                "feed": FEED,
                "expected_rth_minutes": len(expected),
                "observed_rth_minutes": len(observed),
                "missing_rth_minutes": len(missing),
                "all_missing_minutes_have_trades": all_have_trades,
                "results": results,
                "h4_event_triggers_calculated": False,
                "h4_forward_outcomes_calculated": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(REPORT_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
