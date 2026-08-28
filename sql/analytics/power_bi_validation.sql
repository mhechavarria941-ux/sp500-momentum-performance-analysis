-- Power BI validation checkpoints
-- Run in Azure SQL and compare with the Power BI cards/measures.

SELECT COUNT_BIG(*) AS h2_months
FROM bi.fact_h2_monthly;
-- expected: 59

SELECT
    SUM(CASE WHEN h3a_h3c_eligible = 1 THEN 1 ELSE 0 END) AS h3a_h3c_rows,
    SUM(CASE WHEN h3b_eligible = 1 THEN 1 ELSE 0 END) AS h3b_rows
FROM bi.fact_h3_panel;
-- expected: 29114, 26139

SELECT
    COUNT_BIG(*) AS h4_events,
    COUNT(DISTINCT session_date) AS h4_sessions,
    AVG(signed_forward_return_30m) AS mean_signed_return_30m
FROM bi.fact_h4_events
WHERE
    liquidity_sweep_trigger = 1
    AND horizon_30m_clock_eligible = 1;
-- expected: 164, 156, approximately -0.000613142249862

SELECT
    hypothesis_id,
    component,
    estimate,
    raw_p_value,
    adjusted_p_value,
    decision,
    primary_secondary
FROM bi.fact_results
ORDER BY hypothesis_id, component;
