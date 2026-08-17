from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "market_data"
    / "info_corporate_actions.csv"
)

HISTORICAL_SOURCE = "https://www.digrin.com/stocks/detail/INFO/"

# declaration date, ex-date, record date, payment date,
# dividend, close anchor, adjusted-close anchor, evidence
ACTIONS = [
    (
        "2020-01-17",
        "2020-02-05",
        "2020-02-06",
        "2020-02-14",
        0.17,
        80.36,
        79.08,
        "https://www.sec.gov/Archives/edgar/data/1598014/000159801420000160/q2202010q.htm",
    ),
    (
        "2020-04-16",
        "2020-04-29",
        "2020-04-30",
        "2020-05-15",
        0.17,
        68.29,
        67.37,
        "https://www.sec.gov/Archives/edgar/data/1598014/000159801420000160/q2202010q.htm",
    ),
    (
        "2020-07-14",
        "2020-07-30",
        "2020-07-31",
        "2020-08-14",
        0.17,
        80.13,
        79.22,
        "https://www.businesswire.com/news/home/20200714005823/en/IHS-Markit-Declares-Quarterly-Cash-Dividend-in-Third-Quarter-2020",
    ),
    (
        "2020-10-15",
        "2020-10-29",
        "2020-10-30",
        "2020-11-16",
        0.17,
        80.43,
        79.68,
        "https://www.sec.gov/Archives/edgar/data/1598014/000119312521014742/d22887ddefm14a.htm",
    ),
    (
        "2021-01-15",
        "2021-01-28",
        "2021-01-29",
        "2021-02-12",
        0.20,
        87.80,
        87.19,
        "https://www.sec.gov/Archives/edgar/data/1598014/000119312521014742/d22887ddefm14a.htm",
    ),
    (
        "2021-04-22",
        "2021-04-30",
        "2021-05-03",
        "2021-05-17",
        0.20,
        107.58,
        107.03,
        "https://www.gurufocus.com/news/1404313/ihs-markit-declares-quarterly-cash-dividend-in-second-quarter-2021",
    ),
    (
        "2021-07-13",
        "2021-07-29",
        "2021-07-30",
        "2021-08-13",
        0.20,
        115.33,
        114.94,
        "https://www.businesswire.com/news/home/20210713006018/en/IHS-Markit-Declares-Quarterly-Cash-Dividend-in-Third-Quarter-2021",
    ),
    (
        "2021-10-12",
        "2021-10-28",
        "2021-10-29",
        "2021-11-12",
        0.20,
        129.24,
        129.01,
        "https://www.businesswire.com/news/home/20211012006173/en/IHS-Markit-Declares-Quarterly-Cash-Dividend-in-Fourth-Quarter-2021",
    ),
    (
        "2022-01-17",
        "2022-01-27",
        "2022-01-28",
        "2022-02-11",
        0.20,
        111.36,
        111.36,
        "https://www.sec.gov/Archives/edgar/data/1598014/000159801422000011/info-20211130.htm",
    ),
]


def main():
    columns = [
        "declaration_date",
        "ex_date",
        "record_date",
        "payment_date",
        "cash_amount",
        "published_close",
        "published_adjusted_close",
        "primary_source_url",
    ]

    actions = pd.DataFrame(
        ACTIONS,
        columns=columns,
    )

    actions.insert(
        0,
        "security_key",
        "INFO",
    )

    actions.insert(
        1,
        "project_ticker",
        "INFO",
    )

    actions.insert(
        2,
        "event_type",
        "CASH_DIVIDEND",
    )

    actions["split_factor"] = 1.0
    actions["evidence_status"] = "CORROBORATED"
    actions["resolution_status"] = "VALIDATED"
    actions["validation_source_url"] = HISTORICAL_SOURCE

    actions["notes"] = (
        "Corporate filing or company release confirms the cash "
        "dividend; historical market data corroborates the "
        "ex-date and price anchor."
    )

    date_columns = [
        "declaration_date",
        "ex_date",
        "record_date",
        "payment_date",
    ]

    for column in date_columns:
        actions[column] = pd.to_datetime(
            actions[column],
            errors="raise",
        )

    errors = []

    if len(actions) != 9:
        errors.append(
            "Expected exactly nine INFO dividends."
        )

    if actions["ex_date"].duplicated().any():
        errors.append(
            "Duplicate INFO ex-dates found."
        )

    if (
        abs(
            float(actions["cash_amount"].sum())
            - 1.68
        )
        > 1e-12
    ):
        errors.append(
            "INFO dividends must total $1.68."
        )

    if (
        actions["ex_date"]
        >= actions["record_date"]
    ).any():
        errors.append(
            "Each ex-date must precede its record date."
        )

    if (
        actions["record_date"]
        >= actions["payment_date"]
    ).any():
        errors.append(
            "Each record date must precede payment."
        )

    if errors:
        print(
            "INFO CORPORATE-ACTION REFERENCE FAILED"
        )

        for error in errors:
            print(f"- {error}")

        sys.exit(1)

    actions = (
        actions
        .sort_values("ex_date")
        .reset_index(drop=True)
    )

    for column in date_columns:
        actions[column] = (
            actions[column]
            .dt.strftime("%Y-%m-%d")
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    actions.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print(
        "INFO CORPORATE-ACTION REFERENCE PASSED"
    )

    print(
        f"Rows: {len(actions)}"
    )

    print(
        "Total cash dividends: "
        f"${actions['cash_amount'].sum():.2f}"
    )

    print(
        "Split events: 0"
    )

    print(
        f"Saved: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()