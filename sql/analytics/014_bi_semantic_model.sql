/*
014_bi_semantic_model.sql

Purpose
-------
Create the curated SQL contract for Power BI after the H1-H4 research-data
binding gate has passed.

Design rule:
- SQL owns analytical facts, official results, and provenance.
- DAX owns filter-context/presentation measures only.
- Power BI should normally connect only to objects in the bi schema.

Version: 2026-08-28-v1
*/

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

CREATE OR ALTER VIEW bi.dim_hypothesis
AS
SELECT
    hypothesis_id,
    parent_hypothesis_id,
    hypothesis_name,
    research_question,
    primary_outcome,
    primary_test,
    alpha,
    status,
    sample_start,
    sample_end,
    preregistration_version,
    preregistration_sha256,
    notes
FROM ref.hypothesis;
GO

CREATE OR ALTER VIEW bi.dim_variable
AS
SELECT
    variable_id,
    variable_name,
    display_name,
    description,
    grain,
    unit,
    formula_description,
    lookahead_safe,
    source_object,
    source_column,
    educational_notes
FROM ref.variable_catalog;
GO

CREATE OR ALTER VIEW bi.bridge_hypothesis_variable
AS
SELECT
    m.hypothesis_id,
    m.variable_id,
    m.variable_role,
    m.notes
FROM ref.hypothesis_variable_map AS m;
GO

CREATE OR ALTER VIEW bi.dim_date
AS
WITH dates AS
(
    SELECT session_date AS [date]
    FROM research.h4_daily_level

    UNION

    SELECT ranking_month_end_date
    FROM research.v_h1_monthly_performance

    UNION

    SELECT ranking_month_end_date
    FROM research.v_h2_primary_monthly

    UNION

    SELECT predictor_month_end
    FROM research.v_h3_panel

    UNION

    SELECT outcome_month_end
    FROM research.v_h3_panel
)
SELECT
    [date],
    YEAR([date]) AS [year],
    DATEPART(QUARTER, [date]) AS quarter_number,
    CONCAT('Q', DATEPART(QUARTER, [date])) AS quarter_label,
    MONTH([date]) AS month_number,
    DATENAME(MONTH, [date]) AS month_name,
    CONVERT(char(7), [date], 126) AS year_month,
    DATEFROMPARTS(YEAR([date]), MONTH([date]), 1) AS month_start,
    EOMONTH([date]) AS month_end,
    DATEPART(ISO_WEEK, [date]) AS iso_week,
    DATENAME(WEEKDAY, [date]) AS weekday_name
FROM dates
WHERE [date] IS NOT NULL;
GO

CREATE OR ALTER VIEW bi.fact_results
AS
SELECT
    r.result_id,
    r.hypothesis_id,
    h.hypothesis_name,
    r.component,
    r.result_version,
    r.sample_start,
    r.sample_end,
    r.estimand,
    r.estimate,
    r.standard_error,
    r.ci_low,
    r.ci_high,
    r.test_statistic,
    r.reference_df,
    r.raw_p_value,
    r.adjusted_p_value,
    COALESCE(r.adjusted_p_value, r.raw_p_value) AS decision_p_value,
    CASE
        WHEN COALESCE(r.adjusted_p_value, r.raw_p_value) < 0.05 THEN 1
        WHEN COALESCE(r.adjusted_p_value, r.raw_p_value) IS NULL THEN NULL
        ELSE 0
    END AS significant_05,
    r.multiple_testing_method,
    r.n_observations,
    r.n_clusters_primary,
    r.n_clusters_secondary,
    r.economic_effect,
    r.economic_effect_unit,
    r.decision,
    r.primary_secondary,
    r.covariance_method,
    r.source_report_path,
    r.source_report_sha256,
    r.preregistration_sha256,
    r.frozen,
    r.recorded_at_utc
FROM results.hypothesis_result AS r
JOIN ref.hypothesis AS h
  ON h.hypothesis_id = r.hypothesis_id;
GO

CREATE OR ALTER VIEW bi.fact_result_breakdown
AS
SELECT
    b.breakdown_id,
    b.hypothesis_id,
    h.hypothesis_name,
    b.result_version,
    b.breakdown_type,
    b.breakdown_value,
    b.metric_name,
    b.metric_value,
    b.n_observations,
    b.notes
FROM results.result_breakdown AS b
JOIN ref.hypothesis AS h
  ON h.hypothesis_id = b.hypothesis_id;
GO

CREATE OR ALTER VIEW bi.fact_h1_monthly
AS
SELECT
    analysis_month_number,
    ranking_month_start_date,
    ranking_month_end_date,
    return_period_end_date,
    series_code,
    series_name,
    series_type,
    momentum_decile,
    series_sort_order,
    monthly_return,
    return_complete
FROM research.v_h1_monthly_performance;
GO

CREATE OR ALTER VIEW bi.fact_h1_summary
AS
SELECT
    series_code,
    series_name,
    series_type,
    momentum_decile,
    series_sort_order,
    observed_months,
    first_analysis_month_number,
    last_analysis_month_number,
    final_wealth,
    cumulative_return,
    arithmetic_mean_monthly_return,
    geometric_mean_monthly_return,
    annualized_return,
    monthly_volatility,
    annualized_volatility,
    worst_monthly_return,
    best_monthly_return,
    positive_months,
    positive_month_frequency,
    maximum_drawdown,
    mean_monthly_active_return_vs_spy,
    annualized_active_return_vs_spy,
    annualized_tracking_error_vs_spy,
    information_ratio_vs_spy
FROM research.v_h1_performance_summary;
GO

CREATE OR ALTER VIEW bi.fact_h1_primary_monthly
AS
SELECT
    component,
    analysis_month_number,
    ranking_month_end_date,
    value
FROM research.v_h1_primary_monthly;
GO

CREATE OR ALTER VIEW bi.fact_h2_monthly
AS
SELECT
    analysis_month_number,
    ranking_month_end_date,
    value AS sector_neutral_wml_return
FROM research.v_h2_primary_monthly;
GO

CREATE OR ALTER VIEW bi.fact_h3_panel
AS
SELECT
    predictor_month,
    predictor_month_end,
    outcome_month,
    outcome_month_end,
    security_key,
    issuer_id,
    attention_z,
    attention_log,
    attention_percentile_midrank,
    structural_ambiguity_tier,
    pit_alias_transition_month_flag,
    analysis_month_number,
    gics_sector,
    current_momentum_decile,
    current_winner,
    forward_return_1m,
    forward_return_1m_complete,
    sector_valid_security_count,
    leave_one_out_sector_peers,
    sector_peer_mean_excl,
    sector_relative_return_1m,
    attention_x_current_winner,
    h3a_h3c_eligible,
    next_momentum_decile,
    winner_entry,
    h3b_eligible
FROM research.v_h3_panel;
GO

CREATE OR ALTER VIEW bi.dim_h4_session
AS
SELECT
    session_date,
    [open],
    high,
    low,
    [close],
    volume,
    true_range,
    atr14,
    atr14_prior,
    pdh,
    pdl,
    pwh,
    pwl,
    pmh,
    pml,
    prior_all_time_high,
    prior_all_time_low,
    week_start,
    month_key
FROM research.h4_daily_level;
GO

CREATE OR ALTER VIEW bi.fact_h4_events
AS
SELECT *
FROM bi.vw_h4_events;
GO

CREATE OR ALTER VIEW bi.fact_h4_yearly
AS
SELECT *
FROM bi.vw_h4_yearly;
GO

CREATE OR ALTER VIEW bi.fact_data_quality
AS
SELECT *
FROM bi.vw_data_quality;
GO

CREATE OR ALTER VIEW bi.fact_exclusions
AS
SELECT
    exclusion_id,
    hypothesis_id,
    exclusion_scope,
    entity_key,
    start_date,
    end_date,
    reason_code,
    reason_description,
    source_reference,
    frozen
FROM audit.exclusion;
GO

CREATE OR ALTER VIEW bi.fact_artifacts
AS
SELECT
    artifact_id,
    run_id,
    hypothesis_id,
    artifact_name,
    artifact_type,
    repository_path,
    sha256,
    description,
    created_at_utc
FROM audit.artifact;
GO
