from pathlib import Path
import re
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DOWNLOAD_AUDIT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "market_price_download_audit.csv"
)

ACTION_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "info_corporate_actions.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "info_adjusted_price_reconstruction.csv"
)

VALIDATION_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "info_adjusted_price_validation.csv"
)


EXPECTED_ROWS = 543
EXPECTED_FIRST_DATE = pd.Timestamp("2020-01-02")
EXPECTED_LAST_DATE = pd.Timestamp("2022-02-25")
EXPECTED_ACTIONS = 9
EXPECTED_DIVIDENDS = 1.68


def normalize_dates(series):
    values = pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    )

    return (
        values
        .dt.tz_convert(None)
        .dt.normalize()
    )


def parse_number(value):
    if pd.isna(value):
        return None

    text = (
        str(value)
        .strip()
        .replace(",", "")
    )

    if text in {"", "-", "N/A"}:
        return None

    try:
        return float(text)

    except ValueError:
        return None


def parse_volume(value):
    if pd.isna(value):
        return None

    text = (
        str(value)
        .strip()
        .upper()
        .replace(",", "")
    )

    if text in {"", "-", "N/A"}:
        return None

    match = re.fullmatch(
        r"([0-9]*\.?[0-9]+)([KMB]?)",
        text,
    )

    if not match:
        return None

    multiplier = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
    }

    return int(
        round(
            float(match.group(1))
            * multiplier[match.group(2)]
        )
    )


def locate_raw_info_file():
    audit = pd.read_csv(
        DOWNLOAD_AUDIT_FILE
    )

    matches = audit[
        audit["security_key"]
        .astype(str)
        .eq("INFO")
        &
        audit["project_ticker"]
        .astype(str)
        .eq("INFO")
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one INFO audit row; "
            f"found {len(matches)}."
        )

    row = matches.iloc[0]

    if str(row["source"]) != "Investing.com":
        raise RuntimeError(
            "Unexpected INFO source: "
            f"{row['source']}"
        )

    raw_file = (
        PROJECT_ROOT
        / str(row["output_file"])
    )

    if not raw_file.exists():
        raise FileNotFoundError(
            raw_file
        )

    return raw_file


def load_raw_info(file_path):
    raw = pd.read_csv(
        file_path
    )

    required = {
        "Date",
        "Price",
        "Open",
        "High",
        "Low",
        "Vol.",
        "Change %",
    }

    missing = (
        required
        - set(raw.columns)
    )

    if missing:
        raise RuntimeError(
            "INFO raw file is missing columns: "
            f"{sorted(missing)}"
        )

    data = pd.DataFrame(
        {
            "date":
                normalize_dates(
                    raw["Date"]
                ),

            "open":
                raw["Open"]
                .apply(parse_number),

            "high":
                raw["High"]
                .apply(parse_number),

            "low":
                raw["Low"]
                .apply(parse_number),

            "close":
                raw["Price"]
                .apply(parse_number),

            "volume":
                raw["Vol."]
                .apply(parse_volume),
        }
    )

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    return (
        data
        .sort_values("date")
        .reset_index(drop=True)
    )


def load_actions():
    actions = pd.read_csv(
        ACTION_FILE
    )

    required = {
        "security_key",
        "project_ticker",
        "event_type",
        "ex_date",
        "cash_amount",
        "split_factor",
        "published_close",
        "published_adjusted_close",
        "evidence_status",
        "resolution_status",
    }

    missing = (
        required
        - set(actions.columns)
    )

    if missing:
        raise RuntimeError(
            "Action reference is missing columns: "
            f"{sorted(missing)}"
        )

    actions["ex_date"] = (
        pd.to_datetime(
            actions["ex_date"],
            errors="raise",
        )
        .dt.normalize()
    )

    for column in [
        "cash_amount",
        "split_factor",
        "published_close",
        "published_adjusted_close",
    ]:
        actions[column] = pd.to_numeric(
            actions[column],
            errors="raise",
        )

    return (
        actions
        .sort_values("ex_date")
        .reset_index(drop=True)
    )


def validate_inputs(
    data,
    actions,
):
    errors = []

    if len(data) != EXPECTED_ROWS:
        errors.append(
            f"Expected {EXPECTED_ROWS} INFO rows; "
            f"found {len(data)}."
        )

    if (
        data["date"].isna().any()
        or data["date"].duplicated().any()
    ):
        errors.append(
            "INFO dates contain nulls or duplicates."
        )

    if (
        not data.empty
        and data["date"].min()
        != EXPECTED_FIRST_DATE
    ):
        errors.append(
            "Unexpected first date: "
            f"{data['date'].min()}"
        )

    if (
        not data.empty
        and data["date"].max()
        != EXPECTED_LAST_DATE
    ):
        errors.append(
            "Unexpected last date: "
            f"{data['date'].max()}"
        )

    if (
        data[
            [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ]
        .isna()
        .any()
        .any()
    ):
        errors.append(
            "INFO contains required OHLCV nulls."
        )

    if (
        data[
            [
                "open",
                "high",
                "low",
                "close",
            ]
        ]
        <= 0
    ).any().any():
        errors.append(
            "INFO contains nonpositive prices."
        )

    if (
        data["volume"]
        < 0
    ).any():
        errors.append(
            "INFO contains negative volume."
        )

    if len(actions) != EXPECTED_ACTIONS:
        errors.append(
            f"Expected {EXPECTED_ACTIONS} actions; "
            f"found {len(actions)}."
        )

    if actions["ex_date"].duplicated().any():
        errors.append(
            "Duplicate INFO ex-dates found."
        )

    if (
        actions["event_type"]
        .ne("CASH_DIVIDEND")
        .any()
    ):
        errors.append(
            "Unexpected INFO action type."
        )

    if (
        actions["resolution_status"]
        .ne("VALIDATED")
        .any()
    ):
        errors.append(
            "An INFO action is not VALIDATED."
        )

    if (
        actions["evidence_status"]
        .ne("CORROBORATED")
        .any()
    ):
        errors.append(
            "An INFO action is not CORROBORATED."
        )

    if (
        actions["split_factor"]
        .ne(1.0)
        .any()
    ):
        errors.append(
            "Unexpected INFO split factor."
        )

    if (
        abs(
            float(
                actions["cash_amount"].sum()
            )
            - EXPECTED_DIVIDENDS
        )
        > 1e-12
    ):
        errors.append(
            "INFO dividends do not total $1.68."
        )

    missing_ex_dates = actions.loc[
        ~actions["ex_date"].isin(
            data["date"]
        ),
        "ex_date",
    ]

    if not missing_ex_dates.empty:
        errors.append(
            "Price history is missing ex-dates: "
            + ", ".join(
                str(value.date())
                for value in missing_ex_dates
            )
        )

    if errors:
        raise RuntimeError(
            "\n".join(errors)
        )


def reconstruct(
    data,
    actions,
):
    result = data.copy()

    result["dividend"] = 0.0
    result["split_factor"] = 1.0
    result["adjustment_factor"] = 1.0

    checks = []

    for _, action in actions.iterrows():
        ex_date = action["ex_date"]
        dividend = float(
            action["cash_amount"]
        )

        prior_rows = result[
            result["date"] < ex_date
        ]

        if prior_rows.empty:
            raise RuntimeError(
                "No prior INFO session exists for "
                f"{ex_date.date()}."
            )

        prior_row = prior_rows.iloc[-1]

        prior_close = float(
            prior_row["close"]
        )

        event_factor = (
            prior_close - dividend
        ) / prior_close

        if not 0 < event_factor < 1:
            raise RuntimeError(
                "Invalid adjustment factor on "
                f"{ex_date.date()}."
            )

        result.loc[
            result["date"] < ex_date,
            "adjustment_factor",
        ] *= event_factor

        result.loc[
            result["date"] == ex_date,
            "dividend",
        ] = dividend

        checks.append(
            {
                "ex_date":
                    ex_date,

                "cash_amount":
                    dividend,

                "prior_trading_date":
                    prior_row["date"],

                "prior_close":
                    prior_close,

                "event_factor":
                    event_factor,

                "published_close":
                    float(
                        action["published_close"]
                    ),

                "published_adjusted_close":
                    float(
                        action[
                            "published_adjusted_close"
                        ]
                    ),
            }
        )

    result["adj_close"] = (
        result["close"]
        * result["adjustment_factor"]
    )

    result["source_component"] = (
        "Investing.com INFO_OLD + "
        "documented dividend reconstruction"
    )

    validation = pd.DataFrame(
        checks
    )

    validation = validation.merge(
        result[
            [
                "date",
                "close",
                "adj_close",
                "adjustment_factor",
            ]
        ]
        .rename(
            columns={
                "date": "ex_date"
            }
        ),
        on="ex_date",
        how="left",
        validate="one_to_one",
    )

    validation["close_difference"] = (
        validation["close"]
        - validation["published_close"]
    ).abs()

    validation["adjusted_difference"] = (
        validation["adj_close"]
        - validation[
            "published_adjusted_close"
        ]
    ).abs()

    validation["close_anchor_pass"] = (
        validation["close_difference"]
        <= 0.02
    )

    validation["adjusted_anchor_pass"] = (
        validation["adjusted_difference"]
        <= 0.06
    )

    validation["validation_status"] = "PASS"

    validation.loc[
        ~(
            validation["close_anchor_pass"]
            & validation[
                "adjusted_anchor_pass"
            ]
        ),
        "validation_status",
    ] = "FAIL"

    return result, validation


def validate_result(
    result,
    validation,
):
    errors = []

    if (
        result["adj_close"].isna().any()
        or (
            result["adj_close"]
            <= 0
        ).any()
    ):
        errors.append(
            "Reconstructed adjusted close "
            "contains null or nonpositive values."
        )

    if not (
        result["adjustment_factor"]
        .between(
            0,
            1,
            inclusive="both",
        )
        .all()
    ):
        errors.append(
            "Adjustment factors fall outside (0, 1]."
        )

    factor_changes = (
        result["adjustment_factor"]
        .diff()
        .dropna()
    )

    if (
        factor_changes
        < -1e-12
    ).any():
        errors.append(
            "Adjustment factors decrease "
            "moving forward."
        )

    terminal = result.iloc[-1]

    if (
        abs(
            float(
                terminal["adjustment_factor"]
            )
            - 1.0
        )
        > 1e-12
    ):
        errors.append(
            "Terminal adjustment factor is not 1.0."
        )

    if (
        abs(
            float(
                terminal["adj_close"]
                - terminal["close"]
            )
        )
        > 1e-12
    ):
        errors.append(
            "Terminal adjusted close does "
            "not equal close."
        )

    if (
        int(
            (
                result["dividend"]
                > 0
            ).sum()
        )
        != EXPECTED_ACTIONS
    ):
        errors.append(
            "Not all nine dividends were applied."
        )

    if (
        abs(
            float(
                result["dividend"].sum()
            )
            - EXPECTED_DIVIDENDS
        )
        > 1e-12
    ):
        errors.append(
            "Applied dividends do not total $1.68."
        )

    if (
        validation["validation_status"]
        .ne("PASS")
        .any()
    ):
        failed = validation.loc[
            validation[
                "validation_status"
            ].ne("PASS"),
            "ex_date",
        ]

        errors.append(
            "Published anchor validation failed on: "
            + ", ".join(
                str(value.date())
                for value in failed
            )
        )

    if errors:
        raise RuntimeError(
            "\n".join(errors)
        )


def main():
    required_files = [
        DOWNLOAD_AUDIT_FILE,
        ACTION_FILE,
    ]

    for required in required_files:
        if not required.exists():
            print(
                "ERROR: Required file missing:"
            )

            print(required)

            sys.exit(1)

    try:
        raw_file = locate_raw_info_file()

        data = load_raw_info(
            raw_file
        )

        actions = load_actions()

        validate_inputs(
            data,
            actions,
        )

        result, validation = reconstruct(
            data,
            actions,
        )

        validate_result(
            result,
            validation,
        )

    except Exception as error:
        print(
            "INFO ADJUSTED-PRICE "
            "RECONSTRUCTION FAILED"
        )

        print(error)

        sys.exit(2)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = result.copy()

    output["date"] = (
        output["date"]
        .dt.strftime("%Y-%m-%d")
    )

    output.to_csv(
        OUTPUT_FILE,
        index=False,
        float_format="%.12g",
    )

    validation_output = validation.copy()

    for column in [
        "ex_date",
        "prior_trading_date",
    ]:
        validation_output[column] = (
            validation_output[column]
            .dt.strftime("%Y-%m-%d")
        )

    validation_output.to_csv(
        VALIDATION_FILE,
        index=False,
        float_format="%.12g",
    )

    print(
        "INFO ADJUSTED-PRICE "
        "RECONSTRUCTION PASSED"
    )

    print(
        f"Rows: {len(output)}"
    )

    print(
        f"First date: "
        f"{output['date'].min()}"
    )

    print(
        f"Last date: "
        f"{output['date'].max()}"
    )

    print(
        "Dividend events applied: "
        f"{int((output['dividend'] > 0).sum())}"
    )

    print(
        "Total dividends: "
        f"${output['dividend'].sum():.2f}"
    )

    print(
        "Published adjusted-price anchors passed: "
        f"{int(validation['adjusted_anchor_pass'].sum())}"
        f"/{len(validation)}"
    )

    print(
        "Saved reconstructed series:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        "Saved validation:"
    )

    print(
        VALIDATION_FILE
    )


if __name__ == "__main__":
    main()