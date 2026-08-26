from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_VERSION = "2026-08-25-v1-h3-exact-name-transition-resolution-audit"

H3_DIR = (
    ROOT / "reports" / "exploratory"
    / "h3_attention_feasibility"
)

TRANSITIONS_PATH = H3_DIR / "h3_pit_name_transition_candidates.csv"
RESOLUTIONS_PATH = H3_DIR / "h3_exact_name_transition_resolutions.csv"
UNRESOLVED_PATH = H3_DIR / "h3_exact_name_transition_unresolved.csv"
RESEARCH_MANIFEST_PATH = H3_DIR / "h3_exact_name_transition_research_manifest.csv"

AUDIT_PATH = (
    ROOT / "reports" / "data_quality"
    / "h3_exact_name_transition_resolution_integrity_audit.txt"
)

EXACT_SOURCE = "PROJECT_SECURITY_ALIASES_EXACT_EVENT"


def normalize_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)


def main() -> None:
    print(f"RUNNING SCRIPT VERSION: {SCRIPT_VERSION}")

    for path in (
        TRANSITIONS_PATH,
        RESOLUTIONS_PATH,
        UNRESOLVED_PATH,
        RESEARCH_MANIFEST_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    transitions = pd.read_csv(
        TRANSITIONS_PATH, dtype=str, keep_default_na=False
    )
    resolutions = pd.read_csv(
        RESOLUTIONS_PATH, dtype=str, keep_default_na=False
    )
    unresolved = pd.read_csv(
        UNRESOLVED_PATH, dtype=str, keep_default_na=False
    )
    research = pd.read_csv(
        RESEARCH_MANIFEST_PATH, dtype=str, keep_default_na=False
    )

    failures = []
    passed = 0

    lines = [
        "=" * 118,
        "H3 STAGE 3C — EXACT NAME-TRANSITION RESOLUTION INTEGRITY AUDIT",
        "=" * 118,
        "Production alias intervals authorized: NO",
        "Full-history GDELT extraction authorized: NO",
        "H3 outcome analysis authorized: NO",
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

    check(
        len(resolutions) + len(unresolved) == len(transitions),
        (
            "Every bounded NPORT transition is classified as either "
            "exact-resolved or unresolved."
        ),
        (
            f"Classified transitions={len(resolutions)+len(unresolved)}, "
            f"source transitions={len(transitions)}."
        ),
    )

    if not resolutions.empty:
        check(
            resolutions["resolution_status"].eq("RESOLVED_EXACT").all(),
            "Every resolution row is explicitly RESOLVED_EXACT.",
            "Unexpected resolution status found.",
        )

        check(
            resolutions["resolution_source"].eq(EXACT_SOURCE).all(),
            (
                "Every automatic exact date comes only from the frozen "
                "explicit project security_aliases event source."
            ),
            "An automatic exact date uses an unauthorized source.",
        )

        exact_dates = normalize_date_series(
            resolutions["exact_effective_date"]
        )
        last_old = normalize_date_series(
            resolutions["last_observed_old_state_date"]
        )
        first_new = normalize_date_series(
            resolutions["first_observed_new_state_date"]
        )

        check(
            (
                (last_old.isna() | (exact_dates > last_old))
                & (first_new.isna() | (exact_dates <= first_new))
            ).all(),
            (
                "Every exact event date lies inside its NPORT "
                "old/new observation bound."
            ),
            "An exact event date falls outside its NPORT transition bound.",
        )
    else:
        check(True, "No transition qualified for automatic exact resolution.", "")
        check(True, "No unauthorized exact-resolution source exists.", "")
        check(True, "No exact-date bound check required.", "")

    if not unresolved.empty:
        check(
            unresolved["resolution_status"].eq(
                "UNRESOLVED_EXACT_DATE"
            ).all(),
            "Every nonresolved transition remains explicitly unresolved.",
            "Unexpected unresolved-transition status found.",
        )
    else:
        check(True, "No bounded transition remains unresolved.", "")

    unresolved_keys = set(
        unresolved["security_key"].astype(str)
    )

    research_exact_keys = set(
        research.loc[
            research["research_type"].eq("EXACT_RENAME_DATE"),
            "security_key",
        ].astype(str)
    )

    check(
        unresolved_keys.issubset(research_exact_keys),
        (
            "Every unresolved bounded transition is represented in the "
            "authoritative research manifest."
        ),
        "An unresolved bounded transition is absent from research manifest.",
    )

    forbidden_fragments = (
        "return",
        "momentum",
        "winner",
        "commonality_factor",
        "outcome",
    )

    cols = {
        str(c).casefold()
        for c in (
            list(resolutions.columns)
            + list(unresolved.columns)
            + list(research.columns)
        )
    }

    bad = [
        c for c in cols
        if any(fragment in c for fragment in forbidden_fragments)
    ]

    check(
        not bad,
        "Stage 3C outputs contain no return/momentum/Winner/outcome fields.",
        "Prohibited outcome-like fields found: " + ", ".join(sorted(bad)),
    )

    if failures:
        gate = "H3_EXACT_NAME_TRANSITION_RESOLUTION_INTEGRITY_AUDIT_FAILED"
    else:
        gate = "H3_EXACT_NAME_TRANSITION_RESOLUTION_INTEGRITY_AUDIT_PASSED"

    lines += [
        "",
        f"Passed checks: {passed}",
        f"Failed checks: {len(failures)}",
        f"Exact-resolved bounded transitions: {len(resolutions)}",
        f"Unresolved bounded transitions: {len(unresolved)}",
        f"Targeted research manifest rows: {len(research)}",
        "",
        gate,
        "",
        (
            "Passing this audit authorizes authoritative research for the "
            "remaining manifest rows and no broader inference."
        ),
        (
            "Production PIT alias intervals remain unauthorized until the "
            "remaining exact-name/date cases are resolved."
        ),
    ]

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    AUDIT_PATH.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
