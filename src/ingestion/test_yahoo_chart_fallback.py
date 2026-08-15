import requests
import pandas as pd


# --------------------------------------------------
# Test configuration
# --------------------------------------------------

ticker = "ATVI"

start_date = pd.Timestamp(
    "2021-01-01",
    tz="UTC",
)

end_date = pd.Timestamp(
    "2023-10-13",
    tz="UTC",
)


period1 = int(
    start_date.timestamp()
)

period2 = int(
    end_date.timestamp()
)


url = (
    f"https://query1.finance.yahoo.com/"
    f"v8/finance/chart/{ticker}"
)


params = {
    "period1": period1,
    "period2": period2,
    "interval": "1d",
    "events": "div,splits",
    "includeAdjustedClose": "true",
}


headers = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64)"
    )
}


print("Testing direct Yahoo chart endpoint")
print(f"Ticker: {ticker}")
print(f"Start: {start_date.date()}")
print(f"End exclusive: {end_date.date()}")


response = requests.get(
    url,
    params=params,
    headers=headers,
    timeout=30,
)


print(
    f"\nHTTP status: "
    f"{response.status_code}"
)


response.raise_for_status()


payload = response.json()


chart = payload.get(
    "chart",
    {}
)


chart_error = chart.get(
    "error"
)


if chart_error is not None:

    print("\nYahoo chart error:")
    print(chart_error)

    raise SystemExit(1)


results = chart.get(
    "result"
)


if not results:

    print(
        "\nYahoo returned no chart result."
    )

    raise SystemExit(1)


result = results[0]


timestamps = result.get(
    "timestamp",
    []
)


if not timestamps:

    print(
        "\nYahoo returned no timestamps."
    )

    raise SystemExit(1)


quote = (
    result
    .get("indicators", {})
    .get("quote", [{}])[0]
)


adjclose_data = (
    result
    .get("indicators", {})
    .get("adjclose", [{}])[0]
    .get("adjclose", [])
)


dates = (
    pd.to_datetime(
        timestamps,
        unit="s",
        utc=True,
    )
    .tz_convert(
        "America/New_York"
    )
)


data = pd.DataFrame(
    {
        "Date": dates.date,
        "Open": quote.get(
            "open",
            []
        ),
        "High": quote.get(
            "high",
            []
        ),
        "Low": quote.get(
            "low",
            []
        ),
        "Close": quote.get(
            "close",
            []
        ),
        "Adj Close": adjclose_data,
        "Volume": quote.get(
            "volume",
            []
        ),
    }
)


print(
    f"\nRows returned: "
    f"{len(data)}"
)


print(
    "\nColumns:"
)

print(
    data.columns.tolist()
)


print(
    "\nFirst 5 rows:"
)

print(
    data.head()
    .to_string(
        index=False
    )
)


print(
    "\nLast 5 rows:"
)

print(
    data.tail()
    .to_string(
        index=False
    )
)


print(
    f"\nFirst date: "
    f"{data['Date'].min()}"
)

print(
    f"Last date: "
    f"{data['Date'].max()}"
)


events = result.get(
    "events",
    {}
)


print(
    "\nDividend events:"
)

print(
    len(
        events.get(
            "dividends",
            {}
        )
    )
)


print(
    "Split events:"
)

print(
    len(
        events.get(
            "splits",
            {}
        )
    )
)