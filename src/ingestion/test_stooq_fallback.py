import io

import pandas as pd
import requests


ticker = "ATVI.US"

start_date = "20210101"
end_date = "20231012"

url = (
    "https://stooq.com/q/d/l/"
    f"?s={ticker}"
    f"&d1={start_date}"
    f"&d2={end_date}"
    "&i=d"
)

print("Testing Stooq historical data")
print(f"Ticker: {ticker}")
print(f"URL: {url}")

response = requests.get(
    url,
    timeout=30,
    headers={
        "User-Agent": "Mozilla/5.0"
    },
)

print(f"\nHTTP status: {response.status_code}")

response.raise_for_status()

text = response.text.strip()

print("\nFirst 300 response characters:")
print(text[:300])


if (
    "Exceeded" in text
    or "apikey" in text.lower()
):

    print(
        "\nStooq requires an API key "
        "or the request limit was reached."
    )

else:

    data = pd.read_csv(
        io.StringIO(text)
    )

    print("\nRows returned:")
    print(len(data))

    print("\nColumns:")
    print(data.columns.tolist())

    if not data.empty:

        print("\nFirst 5 rows:")
        print(
            data.head().to_string(
                index=False
            )
        )

        print("\nLast 5 rows:")
        print(
            data.tail().to_string(
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