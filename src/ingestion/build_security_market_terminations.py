from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "securities"
    / "security_market_terminations.csv"
)


TERMINATIONS = [
    {
        "security_key": "CXO",
        "project_ticker": "CXO",
        "company_name": "Concho Resources Inc.",
        "corporate_event_date": "2021-01-15",
        "last_valid_trading_date": "2021-01-15",
        "accepted_effective_end_exclusive": "2021-01-19",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "ConocoPhillips",
        "trading_suspension_date": "2021-01-19",
        "termination_basis": "FIRST_SESSION_AFTER_LAST_VALID_TRADE",
        "evidence_status": "CORROBORATED",
        "provider_terminal_date": "2021-01-15",
        "provider_terminal_action": "KEEP",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "1358071/000110465921004795/tm213218d6_8k.htm"
        ),
        "notes": (
            "Acquisition completed January 15, 2021. "
            "Tiingo terminal observation is retained. "
            "No price is expected beginning with the next "
            "NYSE session on January 19."
        ),
    },
    {
        "security_key": "VAR",
        "project_ticker": "VAR",
        "company_name": "Varian Medical Systems, Inc.",
        "corporate_event_date": "2021-04-15",
        "last_valid_trading_date": "2021-04-15",
        "accepted_effective_end_exclusive": "2021-04-16",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "Siemens Healthineers",
        "trading_suspension_date": "2021-04-16",
        "termination_basis": "FORMAL_TRADING_BOUNDARY",
        "evidence_status": "CORROBORATED",
        "provider_terminal_date": "2021-04-16",
        "provider_terminal_action": "EXCLUDE_PROVIDER_ARTIFACT",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "203527/000119312521117256/"
            "0001193125-21-117256-index.htm"
        ),
        "notes": (
            "Acquisition and delisting process occurred April 15. "
            "The Tiingo observation dated April 16 is not accepted "
            "as an independent trading observation. The analytical "
            "history ends after April 15."
        ),
    },
    {
        "security_key": "INFO",
        "project_ticker": "INFO",
        "company_name": "IHS Markit Ltd.",
        "corporate_event_date": "2022-02-28",
        "last_valid_trading_date": "2022-02-25",
        "accepted_effective_end_exclusive": "2022-02-28",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "S&P Global Inc.",
        "trading_suspension_date": "2022-02-28",
        "termination_basis": "SUSPENDED_BEFORE_MARKET_OPEN",
        "evidence_status": "VERIFIED",
        "provider_terminal_date": "2022-02-25",
        "provider_terminal_action": "KEEP",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "1598014/000119312522056012/d315930d8k.htm"
        ),
        "notes": (
            "NYSE trading was suspended before the opening on "
            "February 28, 2022. February 25 is the final valid "
            "trading date."
        ),
    },
    {
        "security_key": "TWTR",
        "project_ticker": "TWTR",
        "company_name": "Twitter, Inc.",
        "corporate_event_date": "2022-10-27",
        "last_valid_trading_date": "2022-10-27",
        "accepted_effective_end_exclusive": "2022-10-28",
        "event_type": "MERGER_PRIVATIZATION",
        "acquirer": "X Holdings I, Inc.",
        "trading_suspension_date": "2022-10-28",
        "termination_basis": "SUSPENDED_BEFORE_MARKET_OPEN",
        "evidence_status": "VERIFIED",
        "provider_terminal_date": "2022-10-28",
        "provider_terminal_action": "EXCLUDE_PROVIDER_ARTIFACT",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "1418091/000119312522272772/d411753d8k.htm"
        ),
        "notes": (
            "The merger closed October 27. NYSE trading was "
            "suspended before the opening on October 28. The "
            "Tiingo row dated October 28 is excluded."
        ),
    },
    {
        "security_key": "ATVI",
        "project_ticker": "ATVI",
        "company_name": "Activision Blizzard, Inc.",
        "corporate_event_date": "2023-10-13",
        "last_valid_trading_date": "2023-10-12",
        "accepted_effective_end_exclusive": "2023-10-13",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "Microsoft Corporation",
        "trading_suspension_date": "2023-10-13",
        "termination_basis": "SUSPENDED_BEFORE_MARKET_OPEN",
        "evidence_status": "VERIFIED",
        "provider_terminal_date": "2023-10-13",
        "provider_terminal_action": "EXCLUDE_PROVIDER_ARTIFACT",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "718877/000110465923108985/tm2328253d1_8k.htm"
        ),
        "notes": (
            "Nasdaq was requested to halt trading before the "
            "opening on October 13, 2023. The Tiingo row dated "
            "October 13 is excluded."
        ),
    },
    {
        "security_key": "PXD",
        "project_ticker": "PXD",
        "company_name": "Pioneer Natural Resources Company",
        "corporate_event_date": "2024-05-03",
        "last_valid_trading_date": "2024-05-02",
        "accepted_effective_end_exclusive": "2024-05-03",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "Exxon Mobil Corporation",
        "trading_suspension_date": "2024-05-03",
        "termination_basis": "MERGER_EFFECTIVE_BOUNDARY",
        "evidence_status": "CORROBORATED",
        "provider_terminal_date": "2024-05-03",
        "provider_terminal_action": "EXCLUDE_PROVIDER_ARTIFACT",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "34088/000095010324006322/dp210867_8k.htm"
        ),
        "notes": (
            "ExxonMobil completed the acquisition on May 3, 2024. "
            "The same-day provider row is excluded pending any "
            "contrary exchange-level evidence."
        ),
    },
    {
        "security_key": "MRO",
        "project_ticker": "MRO",
        "company_name": "Marathon Oil Corporation",
        "corporate_event_date": "2024-11-22",
        "last_valid_trading_date": "2024-11-21",
        "accepted_effective_end_exclusive": "2024-11-22",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "ConocoPhillips",
        "trading_suspension_date": "2024-11-22",
        "termination_basis": "SUSPENDED_BEFORE_MARKET_OPEN",
        "evidence_status": "VERIFIED",
        "provider_terminal_date": "2024-11-22",
        "provider_terminal_action": "EXCLUDE_PROVIDER_ARTIFACT",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "101778/000087666124001100/ruleprovisionnotice.htm"
        ),
        "notes": (
            "The merger became effective before market open on "
            "November 22, 2024, and NYSE trading was suspended "
            "that day. The Tiingo row dated November 22 is excluded."
        ),
    },
    {
        "security_key": "CTLT",
        "project_ticker": "CTLT",
        "company_name": "Catalent, Inc.",
        "corporate_event_date": "2024-12-18",
        "last_valid_trading_date": "2024-12-17",
        "accepted_effective_end_exclusive": "2024-12-18",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "Novo Holdings A/S",
        "trading_suspension_date": "2024-12-18",
        "termination_basis": "SUSPENDED_BEFORE_MARKET_OPEN",
        "evidence_status": "VERIFIED",
        "provider_terminal_date": "2024-12-18",
        "provider_terminal_action": "EXCLUDE_PROVIDER_ARTIFACT",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "1596783/000119312524280922/d902883d8k.htm"
        ),
        "notes": (
            "NYSE trading was suspended before the opening on "
            "December 18, 2024. The Tiingo row dated December 18 "
            "is excluded."
        ),
    },
    {
        "security_key": "JNPR",
        "project_ticker": "JNPR",
        "company_name": "Juniper Networks, Inc.",
        "corporate_event_date": "2025-07-02",
        "last_valid_trading_date": "2025-07-01",
        "accepted_effective_end_exclusive": "2025-07-02",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "Hewlett Packard Enterprise Company",
        "trading_suspension_date": "2025-07-02",
        "termination_basis": "SUSPENDED_BEFORE_MARKET_OPEN",
        "evidence_status": "VERIFIED",
        "provider_terminal_date": "2025-07-02",
        "provider_terminal_action": "EXCLUDE_PROVIDER_ARTIFACT",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "1043604/000119312525154400/d912160d8k.htm"
        ),
        "notes": (
            "NYSE was requested to suspend trading before the "
            "opening on July 2, 2025. The Tiingo row dated July 2 "
            "is excluded."
        ),
    },
    {
        "security_key": "HES",
        "project_ticker": "HES",
        "company_name": "Hess Corporation",
        "corporate_event_date": "2025-07-18",
        "last_valid_trading_date": "2025-07-17",
        "accepted_effective_end_exclusive": "2025-07-18",
        "event_type": "MERGER_ACQUISITION",
        "acquirer": "Chevron Corporation",
        "trading_suspension_date": "2025-07-18",
        "termination_basis": "SUSPENDED_BEFORE_MARKET_OPEN",
        "evidence_status": "VERIFIED",
        "provider_terminal_date": "2025-07-18",
        "provider_terminal_action": "EXCLUDE_PROVIDER_ARTIFACT",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/"
            "4447/000095014225001950/eh250651090_8k.htm"
        ),
        "notes": (
            "NYSE trading was suspended before the opening on "
            "July 18, 2025. The Tiingo row dated July 18 is excluded."
        ),
    },
]


def main() -> None:
    termination = pd.DataFrame(TERMINATIONS)

    date_columns = [
        "corporate_event_date",
        "last_valid_trading_date",
        "accepted_effective_end_exclusive",
        "trading_suspension_date",
        "provider_terminal_date",
    ]

    for column in date_columns:
        termination[column] = pd.to_datetime(
            termination[column],
            errors="raise",
        )

    if termination["security_key"].duplicated().any():
        duplicates = termination.loc[
            termination["security_key"].duplicated(False),
            "security_key",
        ].tolist()

        raise ValueError(
            f"Duplicate security keys: {duplicates}"
        )

    invalid_boundaries = termination[
        termination["accepted_effective_end_exclusive"]
        <= termination["last_valid_trading_date"]
    ]

    if not invalid_boundaries.empty:
        raise ValueError(
            "End-exclusive dates must occur after the "
            "last valid trading date."
        )

    verified_values = {
        "VERIFIED",
        "CORROBORATED",
    }

    invalid_evidence = termination[
        ~termination["evidence_status"].isin(
            verified_values
        )
    ]

    if not invalid_evidence.empty:
        raise ValueError(
            "Invalid evidence status detected."
        )

    expected_securities = {
        "ATVI",
        "CTLT",
        "CXO",
        "HES",
        "INFO",
        "JNPR",
        "MRO",
        "PXD",
        "TWTR",
        "VAR",
    }

    actual_securities = set(
        termination["security_key"]
    )

    if actual_securities != expected_securities:
        raise ValueError(
            "Termination security set does not match "
            "the ten diagnosed terminal cases."
        )

    for column in date_columns:
        termination[column] = (
            termination[column]
            .dt.strftime("%Y-%m-%d")
        )

    termination = (
        termination
        .sort_values(
            [
                "accepted_effective_end_exclusive",
                "security_key",
            ]
        )
        .reset_index(drop=True)
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    termination.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print(
        termination[
            [
                "security_key",
                "last_valid_trading_date",
                "accepted_effective_end_exclusive",
                "provider_terminal_date",
                "provider_terminal_action",
                "evidence_status",
            ]
        ].to_string(index=False)
    )

    print(
        f"\nRows: {len(termination)}"
    )

    print(
        "\nProvider terminal actions:"
    )

    print(
        termination[
            "provider_terminal_action"
        ]
        .value_counts()
        .to_string()
    )

    print(
        f"\nSaved:\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()