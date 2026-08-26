# H4 Intraday Price-Location and Market-Structure Preregistration — V1

## Status

`PRE-OUTCOME DESIGN — NO H4 FORWARD-RETURN RESULTS OBSERVED`

Date: `2026-08-26`

Project: `S&P 500 Momentum & Performance Analytics`

## Research Direction

H4 moves the project from monthly cross-sectional momentum/attention analysis into short-horizon intraday market structure.

The design deliberately separates:

1. **Location** — where price is relative to pre-existing deterministic support/resistance or price-discovery state.
2. **Trigger** — what price does when it reaches that location.
3. **Outcome** — what happens after the trigger.

The location engine is frozen before any H4 forward-return relationship is inspected.

No hand-drawn chart levels are permitted.

---

# 1. Primary Instrument and Market Session

Primary instrument:

`SPY`

Reason:

- direct investable S&P 500 proxy;
- extremely liquid;
- avoids security-identity and cross-sectional complications in the first intraday experiment;
- keeps the first market-structure hypothesis tractable.

Primary raw frequency:

`1-minute consolidated U.S. equity bars`

Primary analytical frequency:

`5-minute bars derived deterministically from 1-minute bars`

Primary session:

`regular U.S. equity trading session only`

Use the official session schedule for each date, including early-close sessions.

Premarket and after-hours observations are excluded from the primary H4 test.

Timezone:

`America/New_York`

---

# 2. Source Requirement

Primary H4 data must represent consolidated U.S. trading rather than one exchange only.

Minimum required raw fields:

- timestamp
- open
- high
- low
- close
- volume

Preferred additional fields:

- trade-based VWAP
- transaction count

Candidate primary source:

`Massive / Polygon U.S. Stocks aggregate bars`

The source-feasibility gate must demonstrate historical access to the required 2021–2025 period before acquisition is authorized.

A free IEX-only feed is not acceptable for the primary H4 volume/liquidity analysis because it is not consolidated U.S. market volume.

No H4 inference is authorized until the source gate passes.

---

# 3. H4 Sample Architecture

Historical research interval:

`2021-01-01 through 2025-12-31`

The complete interval may be acquired, but event definitions and transformations must be frozen before H4 forward-return results are inspected.

Primary unit of observation:

`one qualifying first interaction between SPY and one merged deterministic location zone on a trading day`

Repeated hits of the same merged zone on the same session are not treated as independent primary events.

---

# 4. Deterministic Location Engine

## 4.1 Daily Volatility Scale

Use the prior completed daily observations only.

Primary volatility normalizer:

`ATR(14)`

ATR must use the standard true-range definition and Wilder smoothing.

For trading day `d`, the ATR value available to the intraday engine is the ATR calculated through trading day `d-1`.

No current-day high/low is allowed to enter the daily ATR used to define that day's zones.

---

## 4.2 Primary Major Support / Resistance Levels

The primary confirmatory location engine uses only completed higher-timeframe extremes.

Resistance candidates:

1. previous trading-day high (`PDH`);
2. previous completed trading-week high (`PWH`);
3. previous completed calendar-month high (`PMH`).

Support candidates:

1. previous trading-day low (`PDL`);
2. previous completed trading-week low (`PWL`);
3. previous completed calendar-month low (`PML`).

These levels are known before the current session begins.

No future intraday bar is used to create them.

---

## 4.3 Zone Width

Each level is converted from a line into a volatility-scaled zone.

Primary zone half-width:

`0.10 × prior-day ATR(14)`

For level `L`:

`zone_lower = L - 0.10 × ATR14`

`zone_upper = L + 0.10 × ATR14`

The level itself remains the center used for sweep/rejection logic.

---

## 4.4 Confluence / Zone Merging

If two or more same-direction level zones overlap, they are merged into one location zone for event counting.

A merged zone records every contributing source:

- day
- week
- month

Confluence count:

`number of distinct level families contributing to the merged zone`

Primary classification:

- `SINGLE_SOURCE`: one contributing level family;
- `CONFLUENCE`: two or more contributing level families.

A merged zone generates no more than one primary first-contact event per session.

---

# 5. Primary ICT-Style Trigger: Liquidity Sweep / Rejection

The first H4 trigger is intentionally narrow.

No FVG, market-structure-shift, order block, or discretionary candle interpretation is included in the primary H4A test.

## 5.1 Bearish Resistance Sweep

For a resistance level `L`, using the 5-minute trigger bar and the prior-day ATR:

1. price trades above the level by at least:

   `0.02 × ATR14`

2. the same 5-minute bar closes below `L`.

Formally:

`bar_high >= L + 0.02 × ATR14`

and:

`bar_close < L`

Trigger time:

`close of that 5-minute bar`

Expected subsequent direction:

`DOWN`

---

## 5.2 Bullish Support Sweep

For a support level `L`:

1. price trades below the level by at least:

   `0.02 × ATR14`

2. the same 5-minute bar closes above `L`.

Formally:

`bar_low <= L - 0.02 × ATR14`

and:

`bar_close > L`

Trigger time:

`close of that 5-minute bar`

Expected subsequent direction:

`UP`

---

## 5.3 First-Interaction Rule

Only the first interaction with a merged zone during the regular session is eligible for the primary test.

If the first interaction does not produce a same-bar sweep/rejection, later revisits of the same merged zone on that day do not become primary H4A events.

This prevents repeated probing of one level from being counted as multiple independent opportunities.

Later-contact analyses require a separate robustness specification.

---

# 6. Primary Outcome

Primary horizon:

`30 minutes after trigger-bar close`

Raw forward return:

`close_(t+30m) / trigger_close - 1`

For bullish support sweeps:

`signed_forward_return_30m = raw_forward_return_30m`

For bearish resistance sweeps:

`signed_forward_return_30m = -raw_forward_return_30m`

Therefore:

`positive signed return = movement in the preregistered rejection direction`

Primary H4A estimand:

`mean signed_forward_return_30m`

Primary hypothesis:

`H0: mean signed_forward_return_30m = 0`

`H1: mean signed_forward_return_30m > 0`

Primary inference remains to be finalized only after source/event-count feasibility is known, but it must account for same-day dependence.

No result-based choice among covariance estimators is permitted.

---

# 7. Secondary Descriptive Horizons

Secondary horizons:

- 15 minutes
- 60 minutes

These are descriptive/robustness horizons and do not replace the 30-minute primary horizon.

Also report:

- maximum favorable excursion over the next 30 minutes;
- maximum adverse excursion over the next 30 minutes;
- directional success indicator;
- event counts by resistance/support;
- event counts by level family;
- event counts by confluence status;
- year-by-year event counts.

No secondary horizon can upgrade a failed primary result.

---

# 8. Price-Discovery / No-Prior-Resistance State

Historical resistance must never be invented above price.

A session enters the price-discovery branch when current price is above every historical completed-session high available before that observation.

Reference boundary:

`prior historical all-time high`

This branch is separate from the S/R sweep hypothesis.

No resistance level is projected above price.

## 8.1 Deterministic Price-Discovery Context Variables

When no historical overhead resistance exists, characterize the state using only values observable at that time:

1. extension above prior all-time high, normalized by ATR(14);
2. distance from session VWAP, normalized by ATR(14);
3. time-of-day-adjusted relative volume;
4. opening-range extension;
5. rolling intraday realized-volatility ratio;
6. return/displacement over the immediately preceding bars.

These are context variables, not assumed signals.

The price-discovery branch requires a separate frozen inference specification before any predictive result is inspected.

---

# 9. Volume Context

Raw volume is not treated as order flow.

Primary relative-volume definition:

For each 5-minute regular-session bucket:

`RVOL = current_bucket_volume / median(volume for same bucket across prior 20 valid sessions)`

Only prior sessions may enter the denominator.

Primary elevated-volume diagnostic threshold:

`RVOL >= 1.50`

Volume is initially a context/stratification variable.

It is not allowed to alter the H4A primary sweep definition after results are observed.

---

# 10. Session VWAP

If reliable trade-based minute VWAP is available from the approved consolidated source:

`session_VWAP_t = cumulative(sum(minute_VWAP × minute_volume)) / cumulative(sum(minute_volume))`

using regular-session observations only through time `t`.

If trade-based VWAP is unavailable, the project will not silently substitute an OHLC typical-price approximation in the primary specification.

Any approximation would require an explicit documented amendment before H4 outcome testing.

---

# 11. Intraday Volatility Context

Primary short-horizon volatility context:

rolling 30-minute realized volatility from completed 5-minute log returns.

Time-of-day normalization:

compare the current measure with the historical distribution for the same regular-session time bucket across prior sessions.

No forward observations may enter the volatility state.

---

# 12. Future Market-Structure Extensions — Not Yet Primary

The following are deliberately deferred until H4A is built and audited:

- fair value gaps;
- market structure shifts / breaks of structure;
- displacement candles;
- volume-confirmed breakouts;
- prior-session VWAP retests;
- anchored VWAP;
- volume profile / high-volume nodes;
- low-volume nodes;
- true trade/quote order imbalance;
- Level II/order-book imbalance.

They may be tested later only under separately frozen rules.

This prevents combinatorial pattern mining.

---

# 13. Risk and Implementation Boundary

No market structure setup is assumed to be safe.

The project objective is to estimate conditional probabilities and expected returns, not to claim guaranteed prediction.

Before any strategy claim:

- transaction costs must be modeled;
- spread/slippage must be addressed;
- event overlap must be controlled;
- multiple testing must be controlled;
- time stability must be examined;
- an untouched validation period should be preserved where practical.

---

# 14. Outcome Firewall

Before H4A event definitions are finalized and audited, scripts may inspect:

- raw intraday OHLCV structure;
- timestamps;
- session completeness;
- daily/weekly/monthly historical levels;
- ATR distributions;
- volume distributions;
- VWAP availability;
- counts of candidate locations and trigger events.

They may NOT inspect:

- post-trigger forward returns;
- H4A mean signed returns;
- success rates;
- MFE/MAE;
- threshold performance comparisons.

Thresholds in this document may not be tuned by inspecting H4 forward outcomes.

---

# 15. Immediate Stage — H4 Source Feasibility Gate

Before full acquisition:

1. verify consolidated minute history is accessible for representative dates in every study year;
2. verify regular-session completeness;
3. verify OHLC integrity;
4. verify positive/nonmissing volume;
5. record whether trade-based VWAP and transaction count are available;
6. verify timestamps can be converted deterministically to America/New_York;
7. confirm no duplicate minute bars;
8. document API/subscription constraints;
9. freeze the approved source route;
10. only then acquire the full SPY 2021–2025 minute history.

Initial source-probe script:

`src/analysis/probe_h4_intraday_data_source.py`

Expected data-quality report:

`reports/data_quality/h4_intraday_source_feasibility.txt`

---

# 16. Current H4 Status

Location hierarchy:

`FROZEN V1`

Primary instrument:

`SPY`

Primary analytical bar:

`5 MINUTES`

Primary location families:

`PDH / PDL / PWH / PWL / PMH / PML`

Primary trigger:

`SAME-BAR LIQUIDITY SWEEP / REJECTION`

Primary outcome horizon:

`30 MINUTES`

Price-discovery fallback:

`DEFINED, INFERENCE NOT YET AUTHORIZED`

H4 forward outcomes observed:

`NO`

Full intraday acquisition:

`NOT AUTHORIZED UNTIL SOURCE FEASIBILITY PASSES`
