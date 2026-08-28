# Student SQL Queries — H1 to H4

These queries are intended for teaching, result reproduction, and Power BI validation.

## H1 — What did momentum portfolios actually earn?

```sql
SELECT
    series_code,
    annualized_return,
    annualized_volatility,
    maximum_drawdown
FROM research.v_h1_performance_summary
ORDER BY series_sort_order;
```

## H1 — Reproduce the three monthly primary quantities

```sql
SELECT
    component,
    COUNT(*) AS months,
    AVG(value) AS mean_monthly_value
FROM research.v_h1_primary_monthly
GROUP BY component
ORDER BY component;
```

Expected interpretation:

- `H1_WML`: average D10-minus-D01 monthly return.
- `H1_D10_EXCESS_SPY`: D10 minus SPY.
- `H1_DECILE_SLOPE`: monthly return/decile slope.

The frozen inferential decisions are available from:

```sql
SELECT *
FROM results.hypothesis_result
WHERE hypothesis_id = 'H1'
  AND primary_secondary = 'PRIMARY'
ORDER BY component;
```

## H2 — Reproduce the aggregate sector-neutral result

```sql
SELECT
    COUNT(*) AS months,
    AVG(value) AS mean_sector_neutral_wml
FROM research.v_h2_primary_monthly;
```

Then inspect the frozen decision:

```sql
SELECT *
FROM results.hypothesis_result
WHERE hypothesis_id = 'H2';
```

## H2 — Explore sector/quintile observations

```sql
SELECT TOP (100) *
FROM bi.vw_h2_quintile;
```

## H3 — Attention and future return

```sql
SELECT
    CASE
        WHEN attention_z <= -1 THEN 'Low attention'
        WHEN attention_z >= 1 THEN 'High attention'
        ELSE 'Middle'
    END AS attention_group,
    COUNT(*) AS observations,
    AVG(sector_relative_return_1m) AS avg_sector_relative_return
FROM research.v_h3_panel
WHERE h3a_h3c_eligible = 1
GROUP BY
    CASE
        WHEN attention_z <= -1 THEN 'Low attention'
        WHEN attention_z >= 1 THEN 'High attention'
        ELSE 'Middle'
    END;
```

## H3 — Attention and Winner entry

```sql
SELECT
    CASE
        WHEN attention_z <= -1 THEN 'Low attention'
        WHEN attention_z >= 1 THEN 'High attention'
        ELSE 'Middle'
    END AS attention_group,
    COUNT(*) AS risk_set_rows,
    AVG(CAST(winner_entry AS float)) AS winner_entry_rate
FROM research.v_h3_panel
WHERE h3b_eligible = 1
GROUP BY
    CASE
        WHEN attention_z <= -1 THEN 'Low attention'
        WHEN attention_z >= 1 THEN 'High attention'
        ELSE 'Middle'
    END;
```

Official H3 regression results:

```sql
SELECT *
FROM research.v_h3_results
ORDER BY component;
```

## H4 — Reproduce the primary economic result entirely in SQL

```sql
SELECT
    COUNT(*) AS events,
    COUNT(DISTINCT session_date) AS sessions,
    AVG(signed_forward_return_30m) AS mean_signed_return_30m
FROM bi.vw_h4_events
WHERE
    liquidity_sweep_trigger = 1
    AND horizon_30m_clock_eligible = 1;
```

Expected:

- events = `164`
- sessions = `156`
- mean signed 30-minute return ≈ `-0.000613142249862`

Because positive signed return means movement in the preregistered rejection direction, the negative mean is movement opposite that hypothesis.

## H4 — Year-by-year stability

```sql
SELECT *
FROM bi.vw_h4_yearly
ORDER BY [year];
```

## H4 — Does confluence look different descriptively?

```sql
SELECT
    confluence_status,
    COUNT(*) AS events,
    AVG(signed_forward_return_30m) AS mean_signed_return_30m,
    AVG(CAST(directional_success_30m AS float)) AS success_rate_30m,
    AVG(mfe_30m) AS mean_mfe_30m,
    AVG(mae_30m) AS mean_mae_30m
FROM bi.vw_h4_events
WHERE
    liquidity_sweep_trigger = 1
    AND horizon_30m_clock_eligible = 1
GROUP BY confluence_status;
```

This is descriptive and does not alter the frozen H4A decision.

## Statistical lookup — Student-t p-value

```sql
SELECT ref.fn_student_t_two_sided_p(-2.12253472, 155) AS h4a_p_value;
```

## Statistical lookup — 95% critical value

```sql
SELECT ref.fn_student_t_critical(155, 0.05) AS t_critical_95;
```

## Unified final research table

```sql
SELECT
    hypothesis_id,
    hypothesis_name,
    component,
    estimand,
    estimate,
    raw_p_value,
    adjusted_p_value,
    economic_effect,
    economic_effect_unit,
    decision
FROM bi.vw_research_summary
ORDER BY hypothesis_id, component;
```

## Power BI principle

Power BI should read from the `bi` schema.

DAX should calculate presentation/filter-context measures, not redefine the project's official inferential tests.
