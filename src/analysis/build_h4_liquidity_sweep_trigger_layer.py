from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_VERSION = "2026-08-28-v1-h4-liquidity-sweep-trigger-pre-outcome"

BAR5_INPUT = Path(
    "data/interim/h4_spy_5min_sip_primary_eligible_preoutcome.csv.gz"
)
ZONE_INPUT = Path(
    "data/interim/h4_spy_5min_location_zones_preoutcome.csv"
)
CONTACT_INPUT = Path(
    "data/interim/h4_spy_5min_first_contacts_preoutcome.csv"
)
LOCATION_MANIFEST = Path(
    "data/interim/h4_spy_5min_location_layer_manifest.json"
)
LOCATION_AUDIT = Path(
    "reports/data_quality/h4_spy_5min_location_layer_integrity_audit.txt"
)
LOCATION_AUDIT_MANIFEST = Path(
    "data/interim/h4_spy_5min_location_layer_audit_manifest.json"
)

TRIGGER_OUTPUT = Path(
    "data/interim/h4_spy_liquidity_sweep_triggers_preoutcome.csv"
)
TRIGGER_MANIFEST = Path(
    "data/interim/h4_spy_liquidity_sweep_trigger_manifest.json"
)
TRIGGER_REPORT = Path(
    "reports/data_quality/h4_spy_liquidity_sweep_trigger_build.txt"
)

REQUIRED_LOCATION_TOKENS = [
    "H4_5MIN_LOCATION_LAYER_INTEGRITY_AUDIT_PASSED",
    "H4_LIQUIDITY_SWEEP_TRIGGER_CONSTRUCTION_AUTHORIZED",
]

SWEEP_PENETRATION_ATR = 0.02
PRIMARY_HORIZON_MINUTES = 30
SECONDARY_HORIZONS_MINUTES = [15, 60]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_location_authorization() -> None:
    required = [
        BAR5_INPUT,
        ZONE_INPUT,
        CONTACT_INPUT,
        LOCATION_MANIFEST,
        LOCATION_AUDIT,
        LOCATION_AUDIT_MANIFEST,
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Missing required location-layer input: {path}")

    audit_text = LOCATION_AUDIT.read_text(encoding="utf-8")
    for token in REQUIRED_LOCATION_TOKENS:
        if token not in audit_text:
            raise RuntimeError(
                f"Required location-layer authorization token absent: {token}"
            )

    manifest = json.loads(LOCATION_MANIFEST.read_text(encoding="utf-8"))
    expected = {
        BAR5_INPUT: str(manifest.get("bar5_output_sha256") or ""),
        ZONE_INPUT: str(manifest.get("zone_output_sha256") or ""),
        CONTACT_INPUT: str(manifest.get("contact_output_sha256") or ""),
    }
    for path, expected_sha in expected.items():
        actual_sha = sha256_file(path)
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"Location-layer SHA-256 mismatch for {path}. "
                "Trigger construction is not authorized."
            )

    print("PASS: Audited five-minute location layer authorization verified.")


def parse_constituent_levels(value: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for part in str(value).split("|"):
        family, level = part.split(":", 1)
        out.append((family, float(level)))
    if not out:
        raise RuntimeError("Merged zone has no constituent levels.")
    return out


def qualifying_levels(
    *,
    direction: str,
    bar_high: float,
    bar_low: float,
    bar_close: float,
    atr14_prior: float,
    constituents: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    penetration = SWEEP_PENETRATION_ATR * atr14_prior
    hits: list[tuple[str, float]] = []

    if direction == "RESISTANCE":
        for family, level in constituents:
            if (
                bar_high >= level + penetration
                and bar_close < level
            ):
                hits.append((family, level))
    elif direction == "SUPPORT":
        for family, level in constituents:
            if (
                bar_low <= level - penetration
                and bar_close > level
            ):
                hits.append((family, level))
    else:
        raise RuntimeError(f"Unexpected zone direction: {direction}")

    return hits


def select_reference_level(
    direction: str,
    hits: list[tuple[str, float]],
) -> tuple[str, float] | tuple[None, None]:
    if not hits:
        return None, None

    if direction == "RESISTANCE":
        # Most extreme qualifying resistance = highest qualifying level.
        return max(hits, key=lambda x: (x[1], x[0]))

    # Most extreme qualifying support = lowest qualifying level.
    return min(hits, key=lambda x: (x[1], x[0]))


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("H4 LIQUIDITY SWEEP / REJECTION TRIGGER BUILD — PRE-OUTCOME")
    print("=" * 124)
    print("15/30/60-minute forward returns calculated: NO")
    print("Directional hit rate calculated: NO")
    print("MFE / MAE calculated: NO")
    print()

    verify_location_authorization()

    bar5 = pd.read_csv(BAR5_INPUT)
    zones = pd.read_csv(ZONE_INPUT)
    contacts = pd.read_csv(CONTACT_INPUT)

    if zones["zone_id"].duplicated().any():
        raise RuntimeError("Zone IDs are not unique.")
    if contacts["zone_id"].duplicated().any():
        raise RuntimeError("Contact IDs are not unique.")

    zone_map = zones.set_index("zone_id")
    bar5["bar_start_et"] = pd.to_datetime(
        bar5["bar_start_et"], utc=True
    ).dt.tz_convert("America/New_York")
    bar5["bar_end_et"] = pd.to_datetime(
        bar5["bar_end_et"], utc=True
    ).dt.tz_convert("America/New_York")
    bar5["session_close_et"] = pd.to_datetime(
        bar5["session_close_et"], utc=True
    ).dt.tz_convert("America/New_York")

    bar_key = bar5.set_index(["session_date", "bar_index"])

    rows: list[dict] = []

    contacted = contacts[contacts["contacted"] == 1].copy()

    for c in contacted.itertuples(index=False):
        z = zone_map.loc[c.zone_id]

        session_date = str(c.session_date)
        bar_index = int(float(c.first_contact_bar_index))
        try:
            b = bar_key.loc[(session_date, bar_index)]
        except KeyError as exc:
            raise RuntimeError(
                f"First-contact bar missing from 5-minute layer: "
                f"{session_date}, bar_index={bar_index}"
            ) from exc

        if isinstance(b, pd.DataFrame):
            raise RuntimeError(
                f"5-minute key is not unique: {session_date}, {bar_index}"
            )

        direction = str(z["direction"])
        constituents = parse_constituent_levels(
            str(z["constituent_levels"])
        )

        hits = qualifying_levels(
            direction=direction,
            bar_high=float(b["high"]),
            bar_low=float(b["low"]),
            bar_close=float(b["close"]),
            atr14_prior=float(z["atr14_prior"]),
            constituents=constituents,
        )

        reference_family, reference_level = select_reference_level(
            direction,
            hits,
        )
        is_trigger = int(len(hits) > 0)

        penetration_price = (
            SWEEP_PENETRATION_ATR * float(z["atr14_prior"])
        )

        if is_trigger:
            if direction == "RESISTANCE":
                signed_penetration_atr = (
                    float(b["high"]) - float(reference_level)
                ) / float(z["atr14_prior"])
                rejection_close_distance_atr = (
                    float(reference_level) - float(b["close"])
                ) / float(z["atr14_prior"])
                expected_direction = "DOWN"
            else:
                signed_penetration_atr = (
                    float(reference_level) - float(b["low"])
                ) / float(z["atr14_prior"])
                rejection_close_distance_atr = (
                    float(b["close"]) - float(reference_level)
                ) / float(z["atr14_prior"])
                expected_direction = "UP"
        else:
            signed_penetration_atr = np.nan
            rejection_close_distance_atr = np.nan
            expected_direction = ""

        bar_end = b["bar_end_et"]
        session_close = b["session_close_et"]

        horizon_flags = {
            f"horizon_{minutes}m_clock_eligible": int(
                bar_end + timedelta(minutes=minutes) <= session_close
            )
            for minutes in [15, 30, 60]
        }

        event_id = (
            f"H4_{session_date}_{c.zone_id}_"
            f"{'TRIGGER' if is_trigger else 'NO_TRIGGER'}"
        )

        rows.append(
            {
                "event_id": event_id,
                "zone_id": c.zone_id,
                "session_date": session_date,
                "direction": direction,
                "expected_rejection_direction": expected_direction,
                "confluence_status": str(z["confluence_status"]),
                "confluence_count": int(z["confluence_count"]),
                "families": str(z["families"]),
                "constituent_levels": str(z["constituent_levels"]),
                "atr14_prior": float(z["atr14_prior"]),
                "sweep_penetration_threshold_atr": SWEEP_PENETRATION_ATR,
                "sweep_penetration_threshold_price": penetration_price,
                "first_contact_bar_index": bar_index,
                "first_contact_bar_start_et": b["bar_start_et"].isoformat(),
                "first_contact_bar_end_et": b["bar_end_et"].isoformat(),
                "session_close_et": session_close.isoformat(),
                "first_contact_open": float(b["open"]),
                "first_contact_high": float(b["high"]),
                "first_contact_low": float(b["low"]),
                "first_contact_close": float(b["close"]),
                "first_contact_volume": float(b["volume"]),
                "first_contact_vwap": float(b["vwap"]),
                "session_vwap_through_bar": float(
                    b["session_vwap_through_bar"]
                ),
                "rvol": (
                    np.nan if pd.isna(b["rvol"]) else float(b["rvol"])
                ),
                "rvol_elevated": (
                    np.nan
                    if pd.isna(b["rvol_elevated"])
                    else int(b["rvol_elevated"])
                ),
                "distance_from_session_vwap_atr": (
                    np.nan
                    if pd.isna(b["distance_from_session_vwap_atr"])
                    else float(b["distance_from_session_vwap_atr"])
                ),
                "realized_vol_30m": (
                    np.nan
                    if pd.isna(b["realized_vol_30m"])
                    else float(b["realized_vol_30m"])
                ),
                "realized_vol_30m_ratio": (
                    np.nan
                    if pd.isna(b["realized_vol_30m_ratio"])
                    else float(b["realized_vol_30m_ratio"])
                ),
                "opening_range_extension_atr": (
                    np.nan
                    if pd.isna(b["opening_range_extension_atr"])
                    else float(b["opening_range_extension_atr"])
                ),
                "displacement_3bar_atr": (
                    np.nan
                    if pd.isna(b["displacement_3bar_atr"])
                    else float(b["displacement_3bar_atr"])
                ),
                "price_discovery_close": int(b["price_discovery_close"]),
                "ath_break_intrabar": int(b["ath_break_intrabar"]),
                "liquidity_sweep_trigger": is_trigger,
                "qualifying_constituent_count": len(hits),
                "qualifying_families": (
                    "|".join(family for family, _ in hits)
                    if hits
                    else ""
                ),
                "qualifying_levels": (
                    "|".join(f"{level:.12g}" for _, level in hits)
                    if hits
                    else ""
                ),
                "trigger_reference_family": (
                    "" if reference_family is None else reference_family
                ),
                "trigger_reference_level": reference_level,
                "penetration_atr": signed_penetration_atr,
                "rejection_close_distance_atr": rejection_close_distance_atr,
                **horizon_flags,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError(
            "No contacted zones were available for trigger construction."
        )

    if out["event_id"].duplicated().any():
        raise RuntimeError("Trigger-layer event IDs are not unique.")

    # No outcome-like fields may appear.
    forbidden_fragments = [
        "forward_return",
        "signed_forward",
        "future_return",
        "hit_rate",
        "mfe",
        "mae",
        "outcome_",
    ]
    lower_cols = [str(x).lower() for x in out.columns]
    for frag in forbidden_fragments:
        if any(frag in col for col in lower_cols):
            raise RuntimeError(
                f"Forbidden outcome-like field detected: {frag}"
            )

    TRIGGER_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    TRIGGER_REPORT.parent.mkdir(parents=True, exist_ok=True)

    out.to_csv(TRIGGER_OUTPUT, index=False)

    trigger_rows = out[out["liquidity_sweep_trigger"] == 1].copy()
    primary_clock_eligible = trigger_rows[
        trigger_rows["horizon_30m_clock_eligible"] == 1
    ]

    counts_by_direction = (
        trigger_rows.groupby("direction")
        .size()
        .to_dict()
    )
    counts_by_confluence = (
        trigger_rows.groupby("confluence_status")
        .size()
        .to_dict()
    )
    counts_by_reference_family = (
        trigger_rows.groupby("trigger_reference_family")
        .size()
        .to_dict()
    )

    manifest = {
        "script_version": SCRIPT_VERSION,
        "location_manifest": str(LOCATION_MANIFEST).replace("\\", "/"),
        "location_manifest_sha256": sha256_file(LOCATION_MANIFEST),
        "location_audit": str(LOCATION_AUDIT).replace("\\", "/"),
        "location_audit_sha256": sha256_file(LOCATION_AUDIT),
        "bar5_input_sha256": sha256_file(BAR5_INPUT),
        "zone_input_sha256": sha256_file(ZONE_INPUT),
        "contact_input_sha256": sha256_file(CONTACT_INPUT),
        "trigger_output": str(TRIGGER_OUTPUT).replace("\\", "/"),
        "trigger_output_sha256": sha256_file(TRIGGER_OUTPUT),
        "contacted_zone_rows": len(out),
        "trigger_rows": len(trigger_rows),
        "primary_30m_clock_eligible_trigger_rows": len(
            primary_clock_eligible
        ),
        "trigger_counts_by_direction": counts_by_direction,
        "trigger_counts_by_confluence": counts_by_confluence,
        "trigger_counts_by_reference_family": counts_by_reference_family,
        "frozen_trigger_rule": {
            "eligible_population": (
                "first-contact bars from the independently audited "
                "merged S/R location layer"
            ),
            "penetration_threshold_atr": SWEEP_PENETRATION_ATR,
            "resistance_rule": (
                "first-contact high >= constituent resistance level + "
                "0.02*prior_ATR14 AND same bar close < that level"
            ),
            "support_rule": (
                "first-contact low <= constituent support level - "
                "0.02*prior_ATR14 AND same bar close > that level"
            ),
            "merged_zone_rule": (
                "zone triggers if at least one constituent level qualifies"
            ),
            "multi_level_reference_rule": (
                "if multiple constituent levels qualify, use highest "
                "qualifying resistance or lowest qualifying support as "
                "the deterministic reference level"
            ),
            "one_event_per_merged_zone": True,
            "later_revisits_eligible": False,
            "trigger_time": "close of first-contact 5-minute bar",
            "primary_horizon_minutes": PRIMARY_HORIZON_MINUTES,
            "secondary_horizons_minutes": SECONDARY_HORIZONS_MINUTES,
            "horizon_clock_eligibility": (
                "trigger-bar end plus horizon must be <= official session close"
            ),
        },
        "forward_outcomes_calculated": False,
        "directional_success_calculated": False,
        "mfe_mae_calculated": False,
    }

    TRIGGER_MANIFEST.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    report_lines = [
        f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
        "=" * 124,
        "H4 LIQUIDITY SWEEP / REJECTION TRIGGER BUILD — PRE-OUTCOME",
        "=" * 124,
        f"Contacted merged zones evaluated: {len(out):,}",
        f"Qualifying sweep/rejection triggers: {len(trigger_rows):,}",
        f"30-minute clock-eligible triggers: "
        f"{len(primary_clock_eligible):,}",
        f"Resistance triggers: "
        f"{counts_by_direction.get('RESISTANCE', 0):,}",
        f"Support triggers: "
        f"{counts_by_direction.get('SUPPORT', 0):,}",
        f"Confluence triggers: "
        f"{counts_by_confluence.get('CONFLUENCE', 0):,}",
        f"Single-source triggers: "
        f"{counts_by_confluence.get('SINGLE_SOURCE', 0):,}",
        f"Sweep threshold: {SWEEP_PENETRATION_ATR:.2f} × prior ATR(14)",
        "Merged-zone trigger rule: ANY constituent level may qualify.",
        "Multiple qualifying levels: highest resistance / lowest support "
        "is the deterministic reference.",
        "Later revisits after a failed first contact: NOT ELIGIBLE.",
        "15/30/60-minute forward returns calculated: NO",
        "Directional success calculated: NO",
        "MFE / MAE calculated: NO",
        "",
        "Trigger build complete. Independent trigger audit required.",
        "",
        "H4_LIQUIDITY_SWEEP_TRIGGER_BUILD_COMPLETE",
    ]

    TRIGGER_REPORT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )
    print()
    print(TRIGGER_REPORT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
