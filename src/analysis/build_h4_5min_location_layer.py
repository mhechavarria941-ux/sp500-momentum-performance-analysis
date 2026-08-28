from __future__ import annotations

import hashlib
import json
import math
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

SCRIPT_VERSION = "2026-08-28-v2-h4-5min-location-layer-serialization-order-fix"

SYMBOL = "SPY"
FEED = "sip"
ADJUSTMENT = "raw"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

MINUTE_INPUT = Path(
    "data/interim/h4_spy_1min_sip_2021_2025_primary_eligible.csv.gz"
)
MINUTE_MANIFEST = Path(
    "data/interim/h4_spy_1min_sip_primary_eligible_manifest.json"
)
MINUTE_AUDIT = Path(
    "reports/data_quality/h4_spy_1min_sip_integrity_audit_v2.txt"
)
EXCEPTION_POLICY = Path(
    "data/reference/h4/h4_intraday_data_exceptions_v1.json"
)

DAILY_RAW_DIR = Path(
    "data/raw/source/intraday/alpaca/spy_daily_sip"
)
DAILY_RAW_PATH = DAILY_RAW_DIR / "h4_spy_daily_sip_2020_11_2025_12.json"
SUPPORT_CALENDAR_PATH = (
    DAILY_RAW_DIR / "h4_spy_calendar_2020_11_2025_12.json"
)

DAILY_OUTPUT = Path(
    "data/interim/h4_spy_daily_sip_support_levels_2020_2025.csv"
)
BAR5_OUTPUT = Path(
    "data/interim/h4_spy_5min_sip_primary_eligible_preoutcome.csv.gz"
)
ZONE_OUTPUT = Path(
    "data/interim/h4_spy_5min_location_zones_preoutcome.csv"
)
CONTACT_OUTPUT = Path(
    "data/interim/h4_spy_5min_first_contacts_preoutcome.csv"
)
MANIFEST_OUTPUT = Path(
    "data/interim/h4_spy_5min_location_layer_manifest.json"
)
REPORT_OUTPUT = Path(
    "reports/data_quality/h4_spy_5min_location_layer_build.txt"
)

DATA_URL = f"https://data.alpaca.markets/v2/stocks/{SYMBOL}/bars"
CALENDAR_URL = "https://paper-api.alpaca.markets/v2/calendar"

DAILY_SUPPORT_START = date(2020, 11, 1)
DAILY_SUPPORT_END = date(2025, 12, 31)

REQUEST_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 6
PAGE_LIMIT = 10000

ATR_PERIOD = 14
ZONE_HALF_WIDTH_ATR = 0.10
RVOL_LOOKBACK_SESSIONS = 20
RVOL_ELEVATED_THRESHOLD = 1.50
REALIZED_VOL_BARS = 6
DISPLACEMENT_BARS = 3
OPENING_RANGE_BARS = 6

REQUIRED_MINUTE_AUDIT_TOKENS = [
    "H4_SPY_ALPACA_SIP_PRIMARY_ELIGIBLE_MINUTE_HISTORY_AUDIT_PASSED",
    "H4_5MIN_LOCATION_LAYER_CONSTRUCTION_AUTHORIZED",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_credentials() -> tuple[str, str]:
    key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in the local "
            "environment. Do not commit either value."
        )
    return key.strip(), secret.strip()


def auth_headers(key: str, secret: str) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }


def request_json(
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any],
) -> dict[str, Any] | list[Any]:
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
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

            return response.json()

        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_error = exc
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


def verify_minute_gate() -> dict[str, Any]:
    required = [
        MINUTE_INPUT,
        MINUTE_MANIFEST,
        MINUTE_AUDIT,
        EXCEPTION_POLICY,
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Missing required pre-outcome input: {path}")

    audit_text = MINUTE_AUDIT.read_text(encoding="utf-8")
    for token in REQUIRED_MINUTE_AUDIT_TOKENS:
        if token not in audit_text:
            raise RuntimeError(
                f"Required minute-history authorization token absent: {token}"
            )

    manifest = json.loads(MINUTE_MANIFEST.read_text(encoding="utf-8"))

    expected_sha = str(
        manifest.get("canonical_primary_eligible_output_sha256") or ""
    )
    actual_sha = sha256_file(MINUTE_INPUT)
    if expected_sha != actual_sha:
        raise RuntimeError(
            "Canonical primary-eligible minute file SHA-256 no longer matches "
            "the passed V2 minute-history manifest."
        )

    exception_policy = json.loads(
        EXCEPTION_POLICY.read_text(encoding="utf-8")
    )
    exception_dates = sorted(
        str(x["session_date"])
        for x in exception_policy.get("exceptions") or []
        if bool(x.get("exclude_entire_session"))
    )

    if exception_dates != ["2021-05-05", "2023-06-05"]:
        raise RuntimeError(
            "Frozen H4 infrastructure-exception dates changed."
        )

    print("PASS: V2 exception-aware minute-history authorization verified.")
    return manifest


def download_support_calendar(
    headers: dict[str, str]
) -> list[dict[str, Any]]:
    DAILY_RAW_DIR.mkdir(parents=True, exist_ok=True)

    if SUPPORT_CALENDAR_PATH.exists():
        rows = json.loads(
            SUPPORT_CALENDAR_PATH.read_text(encoding="utf-8")
        )
        if isinstance(rows, list) and rows:
            return rows
        raise RuntimeError(
            f"Existing support calendar is invalid: {SUPPORT_CALENDAR_PATH}"
        )

    payload = request_json(
        CALENDAR_URL,
        headers=headers,
        params={
            "start": DAILY_SUPPORT_START.isoformat(),
            "end": DAILY_SUPPORT_END.isoformat(),
        },
    )

    if not isinstance(payload, list) or not payload:
        raise RuntimeError("Alpaca support calendar returned no sessions.")

    SUPPORT_CALENDAR_PATH.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return payload


def download_daily_bars(
    headers: dict[str, str]
) -> dict[str, Any]:
    DAILY_RAW_DIR.mkdir(parents=True, exist_ok=True)

    if DAILY_RAW_PATH.exists():
        payload = json.loads(
            DAILY_RAW_PATH.read_text(encoding="utf-8")
        )
        if (
            isinstance(payload, dict)
            and payload.get("request", {}).get("symbol") == SYMBOL
            and payload.get("request", {}).get("feed") == FEED
            and payload.get("request", {}).get("adjustment") == ADJUSTMENT
        ):
            return payload
        raise RuntimeError(
            f"Existing daily raw file metadata mismatch: {DAILY_RAW_PATH}"
        )

    start_utc = "2020-11-01T00:00:00Z"
    end_utc = "2026-01-01T23:59:59Z"
    page_token: str | None = None
    bars: list[dict[str, Any]] = []
    pages = 0

    while True:
        params: dict[str, Any] = {
            "timeframe": "1Day",
            "start": start_utc,
            "end": end_utc,
            "limit": PAGE_LIMIT,
            "adjustment": ADJUSTMENT,
            "feed": FEED,
            "sort": "asc",
        }
        if page_token:
            params["page_token"] = page_token

        payload = request_json(
            DATA_URL,
            headers=headers,
            params=params,
        )
        if not isinstance(payload, dict):
            raise RuntimeError(
                "Unexpected Alpaca daily-bars response type."
            )

        page = payload.get("bars") or []
        if not isinstance(page, list):
            raise RuntimeError(
                "Unexpected Alpaca daily-bars payload."
            )

        bars.extend(page)
        pages += 1
        page_token = payload.get("next_page_token")

        if not page_token:
            break

    out = {
        "script_version": SCRIPT_VERSION,
        "downloaded_utc": datetime.now(tz=UTC).isoformat(),
        "request": {
            "symbol": SYMBOL,
            "feed": FEED,
            "timeframe": "1Day",
            "adjustment": ADJUSTMENT,
            "start": start_utc,
            "end": end_utc,
            "sort": "asc",
        },
        "provider_page_count": pages,
        "bar_count": len(bars),
        "bars": bars,
    }

    DAILY_RAW_PATH.write_text(
        json.dumps(out, separators=(",", ":")),
        encoding="utf-8",
    )
    return out


def build_daily_support(
    payload: dict[str, Any],
    calendar_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    bars = payload.get("bars") or []
    if not bars:
        raise RuntimeError("No Alpaca daily bars available.")

    rows = []
    for b in bars:
        ts = pd.Timestamp(str(b["t"]))
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        ts_et = ts.tz_convert("America/New_York")
        rows.append(
            {
                "session_date": ts_et.date().isoformat(),
                "open": float(b["o"]),
                "high": float(b["h"]),
                "low": float(b["l"]),
                "close": float(b["c"]),
                "volume": float(b["v"]),
                "vwap": np.nan if b.get("vw") is None else float(b["vw"]),
                "transactions": (
                    np.nan if b.get("n") is None else int(b["n"])
                ),
            }
        )

    daily = pd.DataFrame(rows).drop_duplicates(
        subset=["session_date"],
        keep=False,
    )

    calendar_dates = {
        str(x["date"])
        for x in calendar_rows
        if DAILY_SUPPORT_START <= date.fromisoformat(str(x["date"])) <= DAILY_SUPPORT_END
    }

    observed_dates = set(daily["session_date"])
    missing = sorted(calendar_dates - observed_dates)
    extras = sorted(observed_dates - calendar_dates)

    if missing:
        raise RuntimeError(
            f"Alpaca daily SIP support layer is missing calendar sessions. "
            f"Count={len(missing)}, sample={missing[:10]}"
        )

    if extras:
        daily = daily[daily["session_date"].isin(calendar_dates)].copy()

    daily = daily.sort_values("session_date").reset_index(drop=True)

    if (
        (daily[["open", "high", "low", "close"]] <= 0).any().any()
        or (daily["volume"] <= 0).any()
    ):
        raise RuntimeError("Daily SIP support layer contains nonpositive values.")

    invalid_ohlc = (
        (daily["high"] < daily[["open", "low", "close"]].max(axis=1))
        | (daily["low"] > daily[["open", "high", "close"]].min(axis=1))
    )
    if invalid_ohlc.any():
        raise RuntimeError(
            "Daily SIP support layer contains invalid OHLC rows."
        )

    prev_close = daily["close"].shift(1)
    tr = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = pd.Series(np.nan, index=daily.index, dtype=float)
    if len(daily) < ATR_PERIOD:
        raise RuntimeError("Insufficient daily support history for ATR(14).")

    atr.iloc[ATR_PERIOD - 1] = tr.iloc[:ATR_PERIOD].mean()
    for i in range(ATR_PERIOD, len(daily)):
        atr.iloc[i] = (
            atr.iloc[i - 1] * (ATR_PERIOD - 1) + tr.iloc[i]
        ) / ATR_PERIOD

    daily["true_range"] = tr
    daily["atr14"] = atr
    daily["atr14_prior"] = daily["atr14"].shift(1)
    daily["pdh"] = daily["high"].shift(1)
    daily["pdl"] = daily["low"].shift(1)
    daily["prior_all_time_high"] = (
        daily["high"].expanding().max().shift(1)
    )
    daily["prior_all_time_low"] = (
        daily["low"].expanding().min().shift(1)
    )

    dts = pd.to_datetime(daily["session_date"])
    daily["week_start"] = (
        dts - pd.to_timedelta(dts.dt.weekday, unit="D")
    ).dt.date.astype(str)
    daily["month_key"] = dts.dt.to_period("M").astype(str)

    weekly = (
        daily.groupby("week_start", as_index=False)
        .agg(
            current_week_high=("high", "max"),
            current_week_low=("low", "min"),
        )
        .sort_values("week_start")
    )
    weekly["pwh"] = weekly["current_week_high"].shift(1)
    weekly["pwl"] = weekly["current_week_low"].shift(1)
    week_map = weekly.set_index("week_start")[["pwh", "pwl"]]
    daily = daily.join(week_map, on="week_start")

    monthly = (
        daily.groupby("month_key", as_index=False)
        .agg(
            current_month_high=("high", "max"),
            current_month_low=("low", "min"),
        )
        .sort_values("month_key")
    )
    monthly["pmh"] = monthly["current_month_high"].shift(1)
    monthly["pml"] = monthly["current_month_low"].shift(1)
    month_map = monthly.set_index("month_key")[["pmh", "pml"]]
    daily = daily.join(month_map, on="month_key")

    daily.to_csv(DAILY_OUTPUT, index=False)
    return daily


def load_primary_minute_data() -> pd.DataFrame:
    df = pd.read_csv(MINUTE_INPUT)
    required = {
        "timestamp_utc",
        "timestamp_et",
        "session_date",
        "session_open_et",
        "session_close_et",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "vwap",
        "transactions",
    }
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(
            f"Canonical minute input missing columns: {sorted(missing)}"
        )

    df["timestamp_et"] = pd.to_datetime(
        df["timestamp_et"],
        utc=True,
    ).dt.tz_convert("America/New_York")
    df["session_open_et"] = pd.to_datetime(
        df["session_open_et"],
        utc=True,
    ).dt.tz_convert("America/New_York")
    df["session_close_et"] = pd.to_datetime(
        df["session_close_et"],
        utc=True,
    ).dt.tz_convert("America/New_York")

    df = df.sort_values(["session_date", "timestamp_et"]).reset_index(drop=True)

    minute_offset = (
        (df["timestamp_et"] - df["session_open_et"])
        .dt.total_seconds()
        .div(60)
    )

    if not np.allclose(minute_offset, np.round(minute_offset)):
        raise RuntimeError(
            "Minute timestamps are not aligned to exact minute offsets."
        )

    df["minute_offset"] = minute_offset.astype(int)
    df["bar_index"] = (df["minute_offset"] // 5).astype(int)
    df["bar_start_et"] = (
        df["session_open_et"]
        + pd.to_timedelta(df["bar_index"] * 5, unit="m")
    )
    return df


def build_5min_bars(minute: pd.DataFrame) -> pd.DataFrame:
    counts = (
        minute.groupby(["session_date", "bar_index"])
        .size()
        .rename("minute_count")
    )
    bad = counts[counts != 5]
    if not bad.empty:
        raise RuntimeError(
            "Primary-eligible minute layer cannot be partitioned into "
            f"complete 5-minute bars. Bad buckets={len(bad)}."
        )

    minute = minute.copy()
    minute["vwap_dollar_weight"] = minute["vwap"] * minute["volume"]

    g = minute.groupby(
        ["session_date", "bar_index", "bar_start_et"],
        sort=True,
    )

    bar5 = g.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        vwap_numerator=("vwap_dollar_weight", "sum"),
        transactions=("transactions", "sum"),
        minute_count=("timestamp_et", "size"),
        session_open_et=("session_open_et", "first"),
        session_close_et=("session_close_et", "first"),
    ).reset_index()

    bar5["vwap"] = bar5["vwap_numerator"] / bar5["volume"]
    bar5 = bar5.drop(columns=["vwap_numerator"])

    bar5["bar_end_et"] = (
        bar5["bar_start_et"] + pd.Timedelta(minutes=5)
    )

    # Cumulative session VWAP through each completed 5-minute bar.
    bar5["bar_vwap_dollar_weight"] = bar5["vwap"] * bar5["volume"]
    bar5["cum_vwap_num"] = (
        bar5.groupby("session_date")["bar_vwap_dollar_weight"].cumsum()
    )
    bar5["cum_volume"] = (
        bar5.groupby("session_date")["volume"].cumsum()
    )
    bar5["session_vwap_through_bar"] = (
        bar5["cum_vwap_num"] / bar5["cum_volume"]
    )

    bar5 = bar5.drop(
        columns=["bar_vwap_dollar_weight", "cum_vwap_num"]
    )

    return bar5


def attach_daily_and_context(
    bar5: pd.DataFrame,
    daily: pd.DataFrame,
) -> pd.DataFrame:
    daily_cols = [
        "session_date",
        "atr14_prior",
        "pdh",
        "pdl",
        "pwh",
        "pwl",
        "pmh",
        "pml",
        "prior_all_time_high",
        "prior_all_time_low",
    ]
    daily_map = daily[daily_cols].copy()

    bar5 = bar5.merge(
        daily_map,
        on="session_date",
        how="left",
        validate="many_to_one",
    )

    required_levels = [
        "atr14_prior",
        "pdh",
        "pdl",
        "pwh",
        "pwl",
        "pmh",
        "pml",
        "prior_all_time_high",
    ]
    if bar5[required_levels].isna().any().any():
        bad_sessions = (
            bar5.loc[
                bar5[required_levels].isna().any(axis=1),
                "session_date",
            ]
            .drop_duplicates()
            .tolist()
        )
        raise RuntimeError(
            "Missing frozen location inputs for primary sessions. "
            f"Sample={bad_sessions[:10]}"
        )

    bar5 = bar5.sort_values(
        ["session_date", "bar_index"]
    ).reset_index(drop=True)

    # Time-of-day-adjusted RVOL using prior 20 valid sessions only.
    bar5["rvol_prior20_median"] = np.nan
    bar5["rvol"] = np.nan

    for bar_index, idx in bar5.groupby("bar_index").groups.items():
        positions = list(idx)
        vols = bar5.loc[positions, "volume"].astype(float)
        prior_median = vols.shift(1).rolling(
            RVOL_LOOKBACK_SESSIONS,
            min_periods=RVOL_LOOKBACK_SESSIONS,
        ).median()
        bar5.loc[positions, "rvol_prior20_median"] = prior_median.values
        bar5.loc[positions, "rvol"] = (
            vols.values / prior_median.values
        )

    bar5["rvol_elevated"] = (
        bar5["rvol"] >= RVOL_ELEVATED_THRESHOLD
    ).astype("Int64")

    bar5["distance_from_session_vwap_atr"] = (
        (bar5["close"] - bar5["session_vwap_through_bar"])
        / bar5["atr14_prior"]
    )

    bar5["extension_above_prior_ath_atr"] = (
        (bar5["close"] - bar5["prior_all_time_high"])
        / bar5["atr14_prior"]
    )
    bar5["price_discovery_close"] = (
        bar5["close"] > bar5["prior_all_time_high"]
    ).astype(int)
    bar5["ath_break_intrabar"] = (
        bar5["high"] > bar5["prior_all_time_high"]
    ).astype(int)

    # Within-session close-to-close log returns.
    bar5["log_return_5m"] = (
        bar5.groupby("session_date")["close"]
        .transform(lambda s: np.log(s / s.shift(1)))
    )

    bar5["realized_vol_30m"] = (
        bar5.groupby("session_date")["log_return_5m"]
        .transform(
            lambda s: np.sqrt(
                s.pow(2).rolling(
                    REALIZED_VOL_BARS,
                    min_periods=REALIZED_VOL_BARS,
                ).sum()
            )
        )
    )

    bar5["realized_vol_30m_prior20_median"] = np.nan
    bar5["realized_vol_30m_ratio"] = np.nan

    for bar_index, idx in bar5.groupby("bar_index").groups.items():
        positions = list(idx)
        rv = bar5.loc[positions, "realized_vol_30m"].astype(float)
        prior_median = rv.shift(1).rolling(
            RVOL_LOOKBACK_SESSIONS,
            min_periods=RVOL_LOOKBACK_SESSIONS,
        ).median()
        bar5.loc[
            positions, "realized_vol_30m_prior20_median"
        ] = prior_median.values
        bar5.loc[positions, "realized_vol_30m_ratio"] = (
            rv.values / prior_median.values
        )

    close_lag3 = (
        bar5.groupby("session_date")["close"]
        .shift(DISPLACEMENT_BARS)
    )
    bar5["displacement_3bar_atr"] = (
        (bar5["close"] - close_lag3)
        / bar5["atr14_prior"]
    )

    # Opening range is frozen after the first 30 minutes.
    first6 = (
        bar5[bar5["bar_index"] < OPENING_RANGE_BARS]
        .groupby("session_date", as_index=False)
        .agg(
            opening_range_30m_high=("high", "max"),
            opening_range_30m_low=("low", "min"),
        )
    )
    bar5 = bar5.merge(
        first6,
        on="session_date",
        how="left",
        validate="many_to_one",
    )

    after_or = bar5["bar_index"] >= OPENING_RANGE_BARS
    bar5["opening_range_extension_atr"] = np.nan

    above = bar5["close"] > bar5["opening_range_30m_high"]
    below = bar5["close"] < bar5["opening_range_30m_low"]

    bar5.loc[after_or & above, "opening_range_extension_atr"] = (
        (
            bar5.loc[after_or & above, "close"]
            - bar5.loc[after_or & above, "opening_range_30m_high"]
        )
        / bar5.loc[after_or & above, "atr14_prior"]
    )
    bar5.loc[after_or & below, "opening_range_extension_atr"] = (
        (
            bar5.loc[after_or & below, "close"]
            - bar5.loc[after_or & below, "opening_range_30m_low"]
        )
        / bar5.loc[after_or & below, "atr14_prior"]
    )
    bar5.loc[
        after_or & ~(above | below),
        "opening_range_extension_atr",
    ] = 0.0

    return bar5


def build_zones(bar5: pd.DataFrame) -> pd.DataFrame:
    session_levels = (
        bar5.groupby("session_date", as_index=False)
        .first()[
            [
                "session_date",
                "atr14_prior",
                "pdh",
                "pdl",
                "pwh",
                "pwl",
                "pmh",
                "pml",
            ]
        ]
    )

    zone_rows: list[dict[str, Any]] = []

    for row in session_levels.itertuples(index=False):
        half_width = ZONE_HALF_WIDTH_ATR * float(row.atr14_prior)

        for direction, definitions in [
            (
                "RESISTANCE",
                [
                    ("PDH", float(row.pdh)),
                    ("PWH", float(row.pwh)),
                    ("PMH", float(row.pmh)),
                ],
            ),
            (
                "SUPPORT",
                [
                    ("PDL", float(row.pdl)),
                    ("PWL", float(row.pwl)),
                    ("PML", float(row.pml)),
                ],
            ),
        ]:
            candidates = []
            for family, level in definitions:
                candidates.append(
                    {
                        "family": family,
                        "level": level,
                        "lower": level - half_width,
                        "upper": level + half_width,
                    }
                )

            candidates.sort(
                key=lambda x: (x["lower"], x["level"], x["family"])
            )

            merged: list[list[dict[str, Any]]] = []
            for cand in candidates:
                if not merged:
                    merged.append([cand])
                    continue

                current = merged[-1]
                current_upper = max(x["upper"] for x in current)

                if cand["lower"] <= current_upper:
                    current.append(cand)
                else:
                    merged.append([cand])

            for j, group in enumerate(merged, start=1):
                families = [x["family"] for x in group]
                levels = [float(x["level"]) for x in group]
                lower = min(float(x["lower"]) for x in group)
                upper = max(float(x["upper"]) for x in group)

                zone_rows.append(
                    {
                        "session_date": row.session_date,
                        "direction": direction,
                        "zone_sequence": j,
                        "zone_id": (
                            f"{row.session_date}_"
                            f"{'RES' if direction == 'RESISTANCE' else 'SUP'}_"
                            f"{j:02d}"
                        ),
                        "zone_lower": lower,
                        "zone_upper": upper,
                        "atr14_prior": float(row.atr14_prior),
                        "zone_half_width_atr": ZONE_HALF_WIDTH_ATR,
                        "confluence_count": len(group),
                        "confluence_status": (
                            "CONFLUENCE"
                            if len(group) >= 2
                            else "SINGLE_SOURCE"
                        ),
                        "families": "|".join(families),
                        "constituent_levels": "|".join(
                            f"{fam}:{level:.12g}"
                            for fam, level in zip(families, levels)
                        ),
                        "min_constituent_level": min(levels),
                        "max_constituent_level": max(levels),
                    }
                )

    zones = pd.DataFrame(zone_rows)
    if zones.empty:
        raise RuntimeError("No H4 location zones were constructed.")
    return zones


def build_first_contacts(
    bar5: pd.DataFrame,
    zones: pd.DataFrame,
) -> pd.DataFrame:
    bars_by_session = {
        session: group.sort_values("bar_index").copy()
        for session, group in bar5.groupby("session_date")
    }

    contacts: list[dict[str, Any]] = []

    for z in zones.itertuples(index=False):
        bars = bars_by_session.get(z.session_date)
        if bars is None:
            raise RuntimeError(
                f"Zone session absent from 5-minute layer: {z.session_date}"
            )

        touched = bars[
            (bars["high"] >= float(z.zone_lower))
            & (bars["low"] <= float(z.zone_upper))
        ]

        if touched.empty:
            contacts.append(
                {
                    "zone_id": z.zone_id,
                    "session_date": z.session_date,
                    "direction": z.direction,
                    "confluence_status": z.confluence_status,
                    "families": z.families,
                    "contacted": 0,
                    "first_contact_bar_index": np.nan,
                    "first_contact_bar_start_et": "",
                    "first_contact_bar_end_et": "",
                    "first_contact_open": np.nan,
                    "first_contact_high": np.nan,
                    "first_contact_low": np.nan,
                    "first_contact_close": np.nan,
                    "first_contact_volume": np.nan,
                    "first_contact_rvol": np.nan,
                    "first_contact_session_vwap": np.nan,
                    "first_contact_price_discovery_close": np.nan,
                }
            )
            continue

        first = touched.iloc[0]
        contacts.append(
            {
                "zone_id": z.zone_id,
                "session_date": z.session_date,
                "direction": z.direction,
                "confluence_status": z.confluence_status,
                "families": z.families,
                "contacted": 1,
                "first_contact_bar_index": int(first["bar_index"]),
                "first_contact_bar_start_et": first["bar_start_et"].isoformat(),
                "first_contact_bar_end_et": first["bar_end_et"].isoformat(),
                "first_contact_open": float(first["open"]),
                "first_contact_high": float(first["high"]),
                "first_contact_low": float(first["low"]),
                "first_contact_close": float(first["close"]),
                "first_contact_volume": float(first["volume"]),
                "first_contact_rvol": (
                    np.nan
                    if pd.isna(first["rvol"])
                    else float(first["rvol"])
                ),
                "first_contact_session_vwap": float(
                    first["session_vwap_through_bar"]
                ),
                "first_contact_price_discovery_close": int(
                    first["price_discovery_close"]
                ),
            }
        )

    return pd.DataFrame(contacts)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("H4 SPY 5-MINUTE LOCATION LAYER — PRE-OUTCOME")
    print("=" * 124)
    print("Liquidity-sweep trigger calculated: NO")
    print("H4 forward-return outcomes calculated: NO")
    print()

    minute_manifest = verify_minute_gate()

    key, secret = get_credentials()
    headers = auth_headers(key, secret)

    calendar_rows = download_support_calendar(headers)
    daily_payload = download_daily_bars(headers)

    print("Building daily PIT support/resistance inputs ...")
    daily = build_daily_support(daily_payload, calendar_rows)

    print("Loading canonical primary-eligible 1-minute layer ...")
    minute = load_primary_minute_data()

    expected_rows = int(
        minute_manifest.get("canonical_primary_eligible_rows", -1)
    )
    if len(minute) != expected_rows:
        raise RuntimeError(
            f"Minute-row count changed: manifest={expected_rows:,}, "
            f"current={len(minute):,}"
        )

    print("Aggregating deterministic 5-minute bars ...")
    bar5 = build_5min_bars(minute)

    print("Attaching PIT daily levels and pre-outcome context ...")
    bar5 = attach_daily_and_context(bar5, daily)

    print("Constructing merged deterministic S/R zones ...")
    zones = build_zones(bar5)

    # IMPORTANT:
    # First-contact construction requires timezone-aware datetime objects
    # because the contact layer serializes the first-contact timestamps with
    # .isoformat().  Do not convert the 5-minute timestamp columns to strings
    # until after the contact layer has been built.
    print("Identifying first contact with each merged zone ...")
    contacts = build_first_contacts(bar5, zones)

    # Serialize datetimes consistently only after all in-memory pre-outcome
    # calculations that require datetime semantics have completed.
    for col in [
        "bar_start_et",
        "bar_end_et",
        "session_open_et",
        "session_close_et",
    ]:
        bar5[col] = bar5[col].map(lambda x: x.isoformat())

    BAR5_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    bar5.to_csv(
        BAR5_OUTPUT,
        index=False,
        compression="gzip",
    )
    zones.to_csv(ZONE_OUTPUT, index=False)
    contacts.to_csv(CONTACT_OUTPUT, index=False)

    session_count = int(bar5["session_date"].nunique())
    expected_bar5_rows = len(minute) // 5
    contacted_count = int(contacts["contacted"].sum())
    zone_count = len(zones)
    confluence_count = int(
        (zones["confluence_status"] == "CONFLUENCE").sum()
    )
    price_discovery_sessions = int(
        bar5.loc[
            bar5["price_discovery_close"] == 1,
            "session_date",
        ].nunique()
    )

    manifest = {
        "script_version": SCRIPT_VERSION,
        "implementation_note": (
            "V2 changes only timestamp serialization order: first-contact "
            "construction occurs before datetime columns are converted to ISO "
            "strings. No H4 definition, threshold, input population, trigger, "
            "or outcome rule changed."
        ),
        "source_minute_manifest": str(MINUTE_MANIFEST).replace("\\", "/"),
        "source_minute_manifest_sha256": sha256_file(MINUTE_MANIFEST),
        "source_minute_audit": str(MINUTE_AUDIT).replace("\\", "/"),
        "source_minute_audit_sha256": sha256_file(MINUTE_AUDIT),
        "exception_policy": str(EXCEPTION_POLICY).replace("\\", "/"),
        "exception_policy_sha256": sha256_file(EXCEPTION_POLICY),
        "daily_raw": str(DAILY_RAW_PATH).replace("\\", "/"),
        "daily_raw_sha256": sha256_file(DAILY_RAW_PATH),
        "support_calendar": str(SUPPORT_CALENDAR_PATH).replace("\\", "/"),
        "support_calendar_sha256": sha256_file(SUPPORT_CALENDAR_PATH),
        "daily_support_output": str(DAILY_OUTPUT).replace("\\", "/"),
        "daily_support_output_sha256": sha256_file(DAILY_OUTPUT),
        "bar5_output": str(BAR5_OUTPUT).replace("\\", "/"),
        "bar5_output_sha256": sha256_file(BAR5_OUTPUT),
        "zone_output": str(ZONE_OUTPUT).replace("\\", "/"),
        "zone_output_sha256": sha256_file(ZONE_OUTPUT),
        "contact_output": str(CONTACT_OUTPUT).replace("\\", "/"),
        "contact_output_sha256": sha256_file(CONTACT_OUTPUT),
        "primary_sessions": session_count,
        "minute_rows": len(minute),
        "expected_bar5_rows_from_complete_minutes": expected_bar5_rows,
        "bar5_rows": len(bar5),
        "zone_rows": zone_count,
        "contact_rows": len(contacts),
        "contacted_zone_rows": contacted_count,
        "confluence_zone_rows": confluence_count,
        "price_discovery_sessions": price_discovery_sessions,
        "frozen_parameters": {
            "atr_period": ATR_PERIOD,
            "atr_method": "Wilder",
            "zone_half_width_atr": ZONE_HALF_WIDTH_ATR,
            "major_levels": ["PDH", "PDL", "PWH", "PWL", "PMH", "PML"],
            "same_direction_zone_merge": "overlapping volatility-scaled intervals",
            "first_contact": (
                "earliest 5-minute bar whose high-low range intersects "
                "the merged zone"
            ),
            "rvol_lookback_sessions": RVOL_LOOKBACK_SESSIONS,
            "rvol_denominator": (
                "median same 5-minute bar index across prior 20 valid sessions"
            ),
            "rvol_elevated_threshold": RVOL_ELEVATED_THRESHOLD,
            "realized_vol_30m": (
                "sqrt(sum squared within-session 5-minute log returns "
                "over six completed returns)"
            ),
            "displacement_bars": DISPLACEMENT_BARS,
            "opening_range_bars": OPENING_RANGE_BARS,
            "price_discovery_state": (
                "5-minute close strictly above prior completed-session "
                "historical all-time high"
            ),
        },
        "liquidity_sweep_trigger_calculated": False,
        "h4_forward_outcomes_calculated": False,
    }

    MANIFEST_OUTPUT.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    report = "\n".join(
        [
            f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
            "=" * 124,
            "H4 SPY 5-MINUTE LOCATION LAYER BUILD — PRE-OUTCOME",
            "=" * 124,
            f"Primary-eligible sessions: {session_count:,}",
            f"Canonical 1-minute rows: {len(minute):,}",
            f"Expected 5-minute rows: {expected_bar5_rows:,}",
            f"Constructed 5-minute rows: {len(bar5):,}",
            f"Merged support/resistance zones: {zone_count:,}",
            f"Zones contacted at least once: {contacted_count:,}",
            f"Confluence zones: {confluence_count:,}",
            f"Sessions entering price-discovery state: "
            f"{price_discovery_sessions:,}",
            f"ATR: Wilder({ATR_PERIOD}), prior completed session only",
            f"Zone half-width: {ZONE_HALF_WIDTH_ATR:.2f} × prior ATR(14)",
            "Primary level families: PDH/PDL/PWH/PWL/PMH/PML",
            "Excluded intraday infrastructure sessions remain excluded.",
            "Complete daily SIP bars from excluded sessions remain eligible "
            "for later higher-timeframe levels.",
            "Liquidity-sweep trigger calculated: NO",
            "15/30/60-minute forward returns calculated: NO",
            "Directional hit rate calculated: NO",
            "MFE/MAE calculated: NO",
            "",
            "Build complete. Independent location-layer audit is required.",
            "",
            "H4_5MIN_LOCATION_LAYER_BUILD_COMPLETE",
        ]
    ) + "\n"

    REPORT_OUTPUT.write_text(report, encoding="utf-8")
    print()
    print(report)


if __name__ == "__main__":
    main()
