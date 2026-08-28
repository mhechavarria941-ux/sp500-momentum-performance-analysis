# Power BI DAX Measures

Create a measure table named:

`_Measures`

Official inferential values come from SQL `bi.fact_results`.
The following measures are for presentation and interactive filtering.

## General research result measures

```DAX
Selected Estimate =
SELECTEDVALUE ( bi_fact_results[estimate] )
```

```DAX
Selected Economic Effect =
SELECTEDVALUE ( bi_fact_results[economic_effect] )
```

```DAX
Selected Raw P Value =
SELECTEDVALUE ( bi_fact_results[raw_p_value] )
```

```DAX
Selected Adjusted P Value =
SELECTEDVALUE ( bi_fact_results[adjusted_p_value] )
```

```DAX
Selected Decision =
SELECTEDVALUE ( bi_fact_results[decision] )
```

```DAX
Selected N =
SELECTEDVALUE ( bi_fact_results[n_observations] )
```

## H1

```DAX
H1 Monthly Return =
AVERAGE ( bi_fact_h1_monthly[monthly_return] )
```

```DAX
H1 Observed Months =
CALCULATE (
    DISTINCTCOUNT ( bi_fact_h1_monthly[analysis_month_number] ),
    bi_fact_h1_monthly[return_complete] = 1
)
```

```DAX
H1 Positive Month Rate =
DIVIDE (
    CALCULATE (
        COUNTROWS ( bi_fact_h1_monthly ),
        bi_fact_h1_monthly[return_complete] = 1,
        bi_fact_h1_monthly[monthly_return] > 0
    ),
    CALCULATE (
        COUNTROWS ( bi_fact_h1_monthly ),
        bi_fact_h1_monthly[return_complete] = 1
    )
)
```

For annualized return, volatility, maximum drawdown, and information ratio,
prefer the already validated SQL values from `bi.fact_h1_summary`.

## H2

```DAX
H2 Mean WML =
AVERAGE ( bi_fact_h2_monthly[sector_neutral_wml_return] )
```

```DAX
H2 Months =
DISTINCTCOUNT ( bi_fact_h2_monthly[analysis_month_number] )
```

## H3

```DAX
H3 Mean Attention Z =
AVERAGE ( bi_fact_h3_panel[attention_z] )
```

```DAX
H3 Mean Sector Relative Return =
CALCULATE (
    AVERAGE ( bi_fact_h3_panel[sector_relative_return_1m] ),
    bi_fact_h3_panel[h3a_h3c_eligible] = 1
)
```

```DAX
H3 Winner Entry Rate =
CALCULATE (
    AVERAGE ( bi_fact_h3_panel[winner_entry] ),
    bi_fact_h3_panel[h3b_eligible] = 1
)
```

```DAX
H3 Eligible A C Rows =
CALCULATE (
    COUNTROWS ( bi_fact_h3_panel ),
    bi_fact_h3_panel[h3a_h3c_eligible] = 1
)
```

```DAX
H3 Eligible B Rows =
CALCULATE (
    COUNTROWS ( bi_fact_h3_panel ),
    bi_fact_h3_panel[h3b_eligible] = 1
)
```

## H4

```DAX
H4 Events =
CALCULATE (
    COUNTROWS ( bi_fact_h4_events ),
    bi_fact_h4_events[liquidity_sweep_trigger] = 1,
    bi_fact_h4_events[horizon_30m_clock_eligible] = 1
)
```

```DAX
H4 Sessions =
CALCULATE (
    DISTINCTCOUNT ( bi_fact_h4_events[session_date] ),
    bi_fact_h4_events[liquidity_sweep_trigger] = 1,
    bi_fact_h4_events[horizon_30m_clock_eligible] = 1
)
```

```DAX
H4 Mean Signed Return 15m =
CALCULATE (
    AVERAGE ( bi_fact_h4_events[signed_forward_return_15m] ),
    bi_fact_h4_events[liquidity_sweep_trigger] = 1,
    bi_fact_h4_events[horizon_15m_clock_eligible] = 1
)
```

```DAX
H4 Mean Signed Return 30m =
CALCULATE (
    AVERAGE ( bi_fact_h4_events[signed_forward_return_30m] ),
    bi_fact_h4_events[liquidity_sweep_trigger] = 1,
    bi_fact_h4_events[horizon_30m_clock_eligible] = 1
)
```

```DAX
H4 Mean Signed Return 60m =
CALCULATE (
    AVERAGE ( bi_fact_h4_events[signed_forward_return_60m] ),
    bi_fact_h4_events[liquidity_sweep_trigger] = 1,
    bi_fact_h4_events[horizon_60m_clock_eligible] = 1
)
```

```DAX
H4 Directional Success Rate 30m =
CALCULATE (
    AVERAGE ( bi_fact_h4_events[directional_success_30m] ),
    bi_fact_h4_events[liquidity_sweep_trigger] = 1,
    bi_fact_h4_events[horizon_30m_clock_eligible] = 1
)
```

```DAX
H4 Mean MFE 30m =
CALCULATE (
    AVERAGE ( bi_fact_h4_events[mfe_30m] ),
    bi_fact_h4_events[liquidity_sweep_trigger] = 1,
    bi_fact_h4_events[horizon_30m_clock_eligible] = 1
)
```

```DAX
H4 Mean MAE 30m =
CALCULATE (
    AVERAGE ( bi_fact_h4_events[mae_30m] ),
    bi_fact_h4_events[liquidity_sweep_trigger] = 1,
    bi_fact_h4_events[horizon_30m_clock_eligible] = 1
)
```

```DAX
H4 Elevated RVOL Event Rate =
DIVIDE (
    CALCULATE (
        COUNTROWS ( bi_fact_h4_events ),
        bi_fact_h4_events[rvol_elevated] = 1,
        bi_fact_h4_events[liquidity_sweep_trigger] = 1,
        bi_fact_h4_events[horizon_30m_clock_eligible] = 1
    ),
    [H4 Events]
)
```

## Data quality

```DAX
Quality Checks =
COUNTROWS ( bi_fact_data_quality )
```

```DAX
Failed Quality Checks =
CALCULATE (
    COUNTROWS ( bi_fact_data_quality ),
    bi_fact_data_quality[passed] = 0
)
```

```DAX
Quality Pass Rate =
DIVIDE (
    [Quality Checks] - [Failed Quality Checks],
    [Quality Checks]
)
```

## Formatting

Recommended formats:

- returns/economic effects: percentage;
- p-values: 4 decimals;
- counts: whole number with thousands separator;
- ATR/RVOL/VWAP distances: 2-4 decimals depending on visual;
- decisions: text from SQL.
