from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_VERSION = "2026-08-28-v1-h4-primary-outcome-join"

PREREG_PATH = Path(
    "data/reference/h4/h4_primary_liquidity_sweep_inference_v1.json"
)
BAR5_INPUT = Path(
    "data/interim/h4_spy_5min_sip_primary_eligible_preoutcome.csv.gz"
)
TRIGGER_INPUT = Path(
    "data/interim/h4_spy_liquidity_sweep_triggers_preoutcome.csv"
)
TRIGGER_MANIFEST = Path(
    "data/interim/h4_spy_liquidity_sweep_trigger_manifest.json"
)
TRIGGER_AUDIT = Path(
    "reports/data_quality/h4_spy_liquidity_sweep_trigger_integrity_audit.txt"
)
TRIGGER_AUDIT_MANIFEST = Path(
    "data/interim/h4_spy_liquidity_sweep_trigger_audit_manifest.json"
)

OUTPUT_PATH = Path(
    "data/interim/h4_spy_primary_liquidity_sweep_outcome_join.csv"
)
OUTPUT_MANIFEST = Path(
    "data/interim/h4_spy_primary_liquidity_sweep_outcome_join_manifest.json"
)
OUTPUT_REPORT = Path(
    "reports/data_quality/h4_spy_primary_liquidity_sweep_outcome_join.txt"
)

REQUIRED_TRIGGER_TOKENS = [
    "H4_LIQUIDITY_SWEEP_TRIGGER_INTEGRITY_AUDIT_PASSED",
    "H4_PRIMARY_OUTCOME_JOIN_SPECIFICATION_AUTHORIZED",
]

HORIZON_TO_OFFSET = {15: 3, 30: 6, 60: 12}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_authorization() -> dict:
    required = [
        PREREG_PATH,
        BAR5_INPUT,
        TRIGGER_INPUT,
        TRIGGER_MANIFEST,
        TRIGGER_AUDIT,
        TRIGGER_AUDIT_MANIFEST,
    ]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Missing required input: {path}")

    audit_text = TRIGGER_AUDIT.read_text(encoding="utf-8")
    for token in REQUIRED_TRIGGER_TOKENS:
        if token not in audit_text:
            raise RuntimeError(
                f"Required trigger authorization token absent: {token}"
            )

    manifest = json.loads(TRIGGER_MANIFEST.read_text(encoding="utf-8"))
    if str(manifest.get("trigger_output_sha256") or "") != sha256_file(
        TRIGGER_INPUT
    ):
        raise RuntimeError("Trigger input SHA-256 no longer matches manifest.")

    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if prereg.get("preregistration_name") != "H4_PRIMARY_LIQUIDITY_SWEEP_INFERENCE_V1":
        raise RuntimeError("Unexpected H4 primary preregistration.")

    return prereg


def direction_sign(direction: str) -> int:
    if direction == "SUPPORT":
        return 1
    if direction == "RESISTANCE":
        return -1
    raise RuntimeError(f"Unexpected direction: {direction}")


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")
    print("=" * 124)
    print("H4 PRIMARY LIQUIDITY-SWEEP OUTCOME JOIN")
    print("=" * 124)
    print("Inference calculated: NO")
    print()

    prereg = verify_authorization()

    bars = pd.read_csv(BAR5_INPUT)
    triggers = pd.read_csv(TRIGGER_INPUT)

    bars["bar_start_et"] = pd.to_datetime(
        bars["bar_start_et"], utc=True
    ).dt.tz_convert("America/New_York")
    bars["bar_end_et"] = pd.to_datetime(
        bars["bar_end_et"], utc=True
    ).dt.tz_convert("America/New_York")

    bar_map = bars.set_index(["session_date", "bar_index"])

    primary_candidates = triggers[
        (triggers["liquidity_sweep_trigger"] == 1)
        & (triggers["horizon_30m_clock_eligible"] == 1)
    ].copy()

    if primary_candidates.empty:
        raise RuntimeError("No H4 primary-eligible trigger events.")

    rows: list[dict] = []

    for t in primary_candidates.itertuples(index=False):
        session_date = str(t.session_date)
        trigger_index = int(t.first_contact_bar_index)
        sign = direction_sign(str(t.direction))
        trigger_close = float(t.first_contact_close)

        try:
            trigger_bar = bar_map.loc[(session_date, trigger_index)]
        except KeyError as exc:
            raise RuntimeError(
                f"Trigger bar absent: {session_date}/{trigger_index}"
            ) from exc

        if isinstance(trigger_bar, pd.DataFrame):
            raise RuntimeError(
                f"Non-unique trigger bar: {session_date}/{trigger_index}"
            )

        if not np.isclose(
            float(trigger_bar["close"]),
            trigger_close,
            rtol=1e-12,
            atol=1e-12,
        ):
            raise RuntimeError(
                f"Trigger close mismatch for event {t.event_id}"
            )

        out = dict(t._asdict())
        out["direction_sign"] = sign

        for minutes, offset in HORIZON_TO_OFFSET.items():
            clock_flag = int(
                getattr(t, f"horizon_{minutes}m_clock_eligible")
            )

            if clock_flag != 1:
                out[f"endpoint_{minutes}m_bar_index"] = np.nan
                out[f"endpoint_{minutes}m_close"] = np.nan
                out[f"raw_forward_return_{minutes}m"] = np.nan
                out[f"signed_forward_return_{minutes}m"] = np.nan
                out[f"directional_success_{minutes}m"] = np.nan
                continue

            target_index = trigger_index + offset

            try:
                endpoint = bar_map.loc[(session_date, target_index)]
            except KeyError as exc:
                raise RuntimeError(
                    f"Missing same-session {minutes}m endpoint for "
                    f"{t.event_id}: target bar_index={target_index}"
                ) from exc

            if isinstance(endpoint, pd.DataFrame):
                raise RuntimeError(
                    f"Non-unique endpoint bar: "
                    f"{session_date}/{target_index}"
                )

            raw_ret = float(endpoint["close"]) / trigger_close - 1.0
            signed_ret = sign * raw_ret

            out[f"endpoint_{minutes}m_bar_index"] = target_index
            out[f"endpoint_{minutes}m_close"] = float(endpoint["close"])
            out[f"raw_forward_return_{minutes}m"] = raw_ret
            out[f"signed_forward_return_{minutes}m"] = signed_ret
            out[f"directional_success_{minutes}m"] = int(
                signed_ret > 0
            )

        # 30-minute path = six complete bars strictly after trigger bar.
        future = []
        for idx in range(trigger_index + 1, trigger_index + 7):
            try:
                b = bar_map.loc[(session_date, idx)]
            except KeyError as exc:
                raise RuntimeError(
                    f"Missing bar inside 30m excursion window for "
                    f"{t.event_id}: bar_index={idx}"
                ) from exc
            if isinstance(b, pd.DataFrame):
                raise RuntimeError(
                    f"Non-unique 30m path bar: {session_date}/{idx}"
                )
            future.append(b)

        if sign == 1:
            favorable = max(
                float(b["high"]) / trigger_close - 1.0
                for b in future
            )
            adverse = min(
                float(b["low"]) / trigger_close - 1.0
                for b in future
            )
        else:
            favorable = max(
                -(float(b["low"]) / trigger_close - 1.0)
                for b in future
            )
            adverse = min(
                -(float(b["high"]) / trigger_close - 1.0)
                for b in future
            )

        out["mfe_30m"] = favorable
        out["mae_30m"] = adverse

        rows.append(out)

    joined = pd.DataFrame(rows)

    required_primary = [
        "signed_forward_return_30m",
        "raw_forward_return_30m",
        "endpoint_30m_close",
    ]
    if joined[required_primary].isna().any().any():
        raise RuntimeError(
            "Primary 30-minute outcome join contains missing required values."
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)

    joined.to_csv(OUTPUT_PATH, index=False)

    manifest = {
        "script_version": SCRIPT_VERSION,
        "preregistration": str(PREREG_PATH).replace("\\", "/"),
        "preregistration_sha256": sha256_file(PREREG_PATH),
        "trigger_input": str(TRIGGER_INPUT).replace("\\", "/"),
        "trigger_input_sha256": sha256_file(TRIGGER_INPUT),
        "bar5_input": str(BAR5_INPUT).replace("\\", "/"),
        "bar5_input_sha256": sha256_file(BAR5_INPUT),
        "outcome_join_output": str(OUTPUT_PATH).replace("\\", "/"),
        "outcome_join_output_sha256": sha256_file(OUTPUT_PATH),
        "primary_rows": len(joined),
        "primary_session_clusters": int(joined["session_date"].nunique()),
        "support_rows": int((joined["direction"] == "SUPPORT").sum()),
        "resistance_rows": int((joined["direction"] == "RESISTANCE").sum()),
        "horizon_15m_complete_rows": int(
            joined["signed_forward_return_15m"].notna().sum()
        ),
        "horizon_30m_complete_rows": int(
            joined["signed_forward_return_30m"].notna().sum()
        ),
        "horizon_60m_complete_rows": int(
            joined["signed_forward_return_60m"].notna().sum()
        ),
        "inference_calculated": False,
        "summary_performance_statistics_calculated": False,
    }
    OUTPUT_MANIFEST.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    report = "\n".join(
        [
            f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}",
            "=" * 124,
            "H4 PRIMARY LIQUIDITY-SWEEP OUTCOME JOIN",
            "=" * 124,
            f"Primary 30-minute eligible event rows: {len(joined):,}",
            f"Unique session clusters: "
            f"{joined['session_date'].nunique():,}",
            f"Support-event rows: "
            f"{(joined['direction'] == 'SUPPORT').sum():,}",
            f"Resistance-event rows: "
            f"{(joined['direction'] == 'RESISTANCE').sum():,}",
            f"15-minute complete outcomes: "
            f"{joined['signed_forward_return_15m'].notna().sum():,}",
            f"30-minute complete outcomes: "
            f"{joined['signed_forward_return_30m'].notna().sum():,}",
            f"60-minute complete outcomes: "
            f"{joined['signed_forward_return_60m'].notna().sum():,}",
            "Inference calculated: NO",
            "Mean returns printed: NO",
            "Directional success rates printed: NO",
            "MFE/MAE summaries printed: NO",
            "",
            "H4_PRIMARY_OUTCOME_JOIN_COMPLETE",
            "H4_PRIMARY_OUTCOME_JOIN_AUDIT_REQUIRED",
        ]
    ) + "\n"

    OUTPUT_REPORT.write_text(report, encoding="utf-8")
    print()
    print(report)


if __name__ == "__main__":
    main()
