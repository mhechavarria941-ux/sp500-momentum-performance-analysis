/*
013_research_bindings.sql

Purpose
-------
Bind the completed H1-H4 research into the new research/results/bi warehouse
without replacing the validated core/analytics layer.

H1-H3 remain sourced from existing validated Azure SQL objects.
H4 is materialized into relational research tables by load_research_data.py.

Version: 2026-08-28-v1
*/

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

/* -------------------------------------------------------------------------
   H1 educational views
   ------------------------------------------------------------------------- */

CREATE OR ALTER VIEW research.v_h1_monthly_performance
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
FROM analytics.v_momentum_monthly_return_panel;
GO

CREATE OR ALTER VIEW research.v_h1_performance_summary
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
FROM analytics.v_momentum_performance_summary;
GO

CREATE OR ALTER VIEW research.v_h1_primary_monthly
AS
WITH complete AS
(
    SELECT
        analysis_month_number,
        ranking_month_end_date,
        series_code,
        momentum_decile,
        monthly_return
    FROM analytics.v_momentum_monthly_return_panel
    WHERE return_complete = 1
),
d10_spy AS
(
    SELECT
        d.analysis_month_number,
        d.ranking_month_end_date,
        d.monthly_return - s.monthly_return AS value
    FROM complete AS d
    JOIN complete AS s
      ON s.analysis_month_number = d.analysis_month_number
     AND s.series_code = 'SPY'
    WHERE d.series_code = 'D10'
),
decile_stats AS
(
    SELECT
        analysis_month_number,
        ranking_month_end_date,
        COUNT(*) AS decile_count,
        AVG(CAST(momentum_decile AS float)) AS mean_x,
        AVG(monthly_return) AS mean_y
    FROM complete
    WHERE series_type = 'DECILE'
    GROUP BY
        analysis_month_number,
        ranking_month_end_date
),
slopes AS
(
    SELECT
        c.analysis_month_number,
        c.ranking_month_end_date,
        SUM(
            (CAST(c.momentum_decile AS float) - s.mean_x)
            * (c.monthly_return - s.mean_y)
        )
        / NULLIF(
            SUM(
                POWER(
                    CAST(c.momentum_decile AS float) - s.mean_x,
                    2
                )
            ),
            0
        ) AS value
    FROM complete AS c
    JOIN decile_stats AS s
      ON s.analysis_month_number = c.analysis_month_number
    WHERE
        c.series_type = 'DECILE'
        AND s.decile_count = 10
    GROUP BY
        c.analysis_month_number,
        c.ranking_month_end_date
)
SELECT
    'H1_WML' AS component,
    analysis_month_number,
    ranking_month_end_date,
    monthly_return AS value
FROM complete
WHERE series_code = 'WML'

UNION ALL

SELECT
    'H1_D10_EXCESS_SPY',
    analysis_month_number,
    ranking_month_end_date,
    value
FROM d10_spy

UNION ALL

SELECT
    'H1_DECILE_SLOPE',
    analysis_month_number,
    ranking_month_end_date,
    value
FROM slopes;
GO

/* -------------------------------------------------------------------------
   H3 educational views
   ------------------------------------------------------------------------- */

CREATE OR ALTER VIEW research.v_h3_panel
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
FROM analytics.h3_preregistered_predictor_outcome_panel;
GO

CREATE OR ALTER VIEW research.v_h3_results
AS
SELECT
    component,
    estimand_term,
    estimate,
    cluster_se,
    ci_low,
    ci_high,
    t_stat,
    reference_df,
    raw_p_value,
    holm_adjusted_p_value,
    economic_effect_pp,
    sample_rows,
    security_fixed_effects,
    issuer_clusters,
    month_clusters,
    intersection_clusters,
    decision,
    expected_sign,
    inference_method,
    preregistration_id,
    script_version
FROM analytics.h3_primary_confirmatory_results;
GO

/* -------------------------------------------------------------------------
   H4 relational model
   ------------------------------------------------------------------------- */

IF OBJECT_ID(N'research.h4_minute', N'U') IS NULL
BEGIN
    CREATE TABLE research.h4_minute
    (
        session_date        date         NOT NULL,
        minute_index        smallint     NOT NULL,
        timestamp_utc       datetime2(0) NOT NULL,
        timestamp_et        datetime2(0) NOT NULL,
        session_open_et     datetime2(0) NOT NULL,
        session_close_et    datetime2(0) NOT NULL,
        [open]              float        NOT NULL,
        high                float        NOT NULL,
        low                 float        NOT NULL,
        [close]             float        NOT NULL,
        volume              bigint       NOT NULL,
        vwap                float        NOT NULL,
        transactions        bigint       NOT NULL,

        CONSTRAINT PK_research_h4_minute
            PRIMARY KEY CLUSTERED (session_date, minute_index)
    );

    CREATE INDEX IX_research_h4_minute_timestamp
        ON research.h4_minute(timestamp_et);
END;
GO

IF OBJECT_ID(N'research.h4_daily_level', N'U') IS NULL
BEGIN
    CREATE TABLE research.h4_daily_level
    (
        session_date            date         NOT NULL,
        [open]                  float        NOT NULL,
        high                    float        NOT NULL,
        low                     float        NOT NULL,
        [close]                 float        NOT NULL,
        volume                  bigint       NOT NULL,
        true_range              float        NULL,
        atr14                   float        NULL,
        atr14_prior             float        NULL,
        pdh                     float        NULL,
        pdl                     float        NULL,
        pwh                     float        NULL,
        pwl                     float        NULL,
        pmh                     float        NULL,
        pml                     float        NULL,
        prior_all_time_high     float        NULL,
        prior_all_time_low      float        NULL,
        week_start              date         NULL,
        month_key               char(7)      NULL,

        CONSTRAINT PK_research_h4_daily_level
            PRIMARY KEY (session_date)
    );
END;
GO

IF OBJECT_ID(N'research.h4_bar_5m', N'U') IS NULL
BEGIN
    CREATE TABLE research.h4_bar_5m
    (
        session_date                        date         NOT NULL,
        bar_index                           smallint     NOT NULL,
        bar_start_et                        datetime2(0) NOT NULL,
        bar_end_et                          datetime2(0) NOT NULL,
        [open]                              float        NOT NULL,
        high                                float        NOT NULL,
        low                                 float        NOT NULL,
        [close]                             float        NOT NULL,
        volume                              bigint       NOT NULL,
        vwap                                float        NOT NULL,
        transactions                        bigint       NOT NULL,
        session_vwap_through_bar            float        NOT NULL,
        atr14_prior                         float        NULL,
        pdh                                 float        NULL,
        pdl                                 float        NULL,
        pwh                                 float        NULL,
        pwl                                 float        NULL,
        pmh                                 float        NULL,
        pml                                 float        NULL,
        prior_all_time_high                 float        NULL,
        rvol_prior20_median                 float        NULL,
        rvol                                float        NULL,
        rvol_elevated                       bit          NULL,
        distance_from_session_vwap_atr      float        NULL,
        extension_above_prior_ath_atr       float        NULL,
        price_discovery_close               bit          NULL,
        ath_break_intrabar                  bit          NULL,
        log_return_5m                       float        NULL,
        realized_vol_30m                    float        NULL,
        realized_vol_30m_prior20_median     float        NULL,
        realized_vol_30m_ratio              float        NULL,
        displacement_3bar_atr               float        NULL,
        opening_range_30m_high              float        NULL,
        opening_range_30m_low               float        NULL,
        opening_range_extension_atr         float        NULL,

        CONSTRAINT PK_research_h4_bar_5m
            PRIMARY KEY CLUSTERED (session_date, bar_index)
    );

    CREATE INDEX IX_research_h4_bar_5m_time
        ON research.h4_bar_5m(bar_start_et);
END;
GO

IF OBJECT_ID(N'research.h4_zone', N'U') IS NULL
BEGIN
    CREATE TABLE research.h4_zone
    (
        zone_id                  nvarchar(80)  NOT NULL,
        session_date             date          NOT NULL,
        direction                varchar(16)   NOT NULL,
        zone_sequence            smallint      NOT NULL,
        zone_lower               float         NOT NULL,
        zone_upper               float         NOT NULL,
        atr14_prior              float         NOT NULL,
        zone_half_width_atr      float         NOT NULL,
        confluence_count         tinyint       NOT NULL,
        confluence_status        varchar(32)   NOT NULL,
        families                 nvarchar(100) NOT NULL,
        constituent_levels       nvarchar(500) NOT NULL,
        min_constituent_level    float         NOT NULL,
        max_constituent_level    float         NOT NULL,

        CONSTRAINT PK_research_h4_zone
            PRIMARY KEY (zone_id)
    );

    CREATE INDEX IX_research_h4_zone_session
        ON research.h4_zone(session_date, direction);
END;
GO

IF OBJECT_ID(N'research.h4_trigger', N'U') IS NULL
BEGIN
    CREATE TABLE research.h4_trigger
    (
        event_id                         nvarchar(180) NOT NULL,
        zone_id                          nvarchar(80)  NOT NULL,
        session_date                     date          NOT NULL,
        direction                        varchar(16)   NOT NULL,
        expected_rejection_direction     varchar(8)    NULL,
        confluence_status                varchar(32)   NOT NULL,
        confluence_count                 tinyint       NOT NULL,
        families                         nvarchar(100) NOT NULL,
        atr14_prior                      float         NOT NULL,
        sweep_penetration_threshold_atr  float         NOT NULL,
        first_contact_bar_index          smallint      NOT NULL,
        first_contact_bar_start_et       datetime2(0)  NOT NULL,
        first_contact_bar_end_et         datetime2(0)  NOT NULL,
        first_contact_open               float         NOT NULL,
        first_contact_high               float         NOT NULL,
        first_contact_low                float         NOT NULL,
        first_contact_close              float         NOT NULL,
        first_contact_volume             bigint        NOT NULL,
        session_vwap_through_bar         float         NULL,
        rvol                             float         NULL,
        rvol_elevated                    bit           NULL,
        distance_from_session_vwap_atr   float         NULL,
        realized_vol_30m                 float         NULL,
        realized_vol_30m_ratio           float         NULL,
        opening_range_extension_atr      float         NULL,
        displacement_3bar_atr            float         NULL,
        price_discovery_close            bit           NULL,
        liquidity_sweep_trigger          bit           NOT NULL,
        qualifying_constituent_count     tinyint       NOT NULL,
        qualifying_families              nvarchar(100) NULL,
        trigger_reference_family         varchar(16)   NULL,
        trigger_reference_level          float         NULL,
        penetration_atr                  float         NULL,
        rejection_close_distance_atr     float         NULL,
        horizon_15m_clock_eligible       bit           NOT NULL,
        horizon_30m_clock_eligible       bit           NOT NULL,
        horizon_60m_clock_eligible       bit           NOT NULL,

        CONSTRAINT PK_research_h4_trigger
            PRIMARY KEY (event_id),

        CONSTRAINT FK_research_h4_trigger_zone
            FOREIGN KEY (zone_id)
            REFERENCES research.h4_zone(zone_id)
    );

    CREATE INDEX IX_research_h4_trigger_primary
        ON research.h4_trigger
        (liquidity_sweep_trigger, horizon_30m_clock_eligible, session_date);
END;
GO

IF OBJECT_ID(N'research.h4_outcome', N'U') IS NULL
BEGIN
    CREATE TABLE research.h4_outcome
    (
        event_id                    nvarchar(180) NOT NULL,
        raw_forward_return_15m      float         NULL,
        signed_forward_return_15m   float         NULL,
        directional_success_15m     bit           NULL,
        raw_forward_return_30m      float         NOT NULL,
        signed_forward_return_30m   float         NOT NULL,
        directional_success_30m     bit           NOT NULL,
        raw_forward_return_60m      float         NULL,
        signed_forward_return_60m   float         NULL,
        directional_success_60m     bit           NULL,
        mfe_30m                     float         NOT NULL,
        mae_30m                     float         NOT NULL,

        CONSTRAINT PK_research_h4_outcome
            PRIMARY KEY (event_id),

        CONSTRAINT FK_research_h4_outcome_trigger
            FOREIGN KEY (event_id)
            REFERENCES research.h4_trigger(event_id)
    );
END;
GO

/* -------------------------------------------------------------------------
   H4 + unified BI views
   ------------------------------------------------------------------------- */

CREATE OR ALTER VIEW bi.vw_h1_monthly_performance
AS
SELECT *
FROM research.v_h1_monthly_performance;
GO

CREATE OR ALTER VIEW bi.vw_h1_summary
AS
SELECT *
FROM research.v_h1_performance_summary;
GO

CREATE OR ALTER VIEW bi.vw_h3_panel
AS
SELECT *
FROM research.v_h3_panel;
GO

CREATE OR ALTER VIEW bi.vw_h3_results
AS
SELECT *
FROM research.v_h3_results;
GO

CREATE OR ALTER VIEW bi.vw_h4_events
AS
SELECT
    t.event_id,
    t.zone_id,
    t.session_date,
    t.direction,
    t.expected_rejection_direction,
    t.confluence_status,
    t.confluence_count,
    t.families,
    t.atr14_prior,
    t.first_contact_bar_index,
    t.first_contact_bar_start_et,
    t.first_contact_bar_end_et,
    t.first_contact_open,
    t.first_contact_high,
    t.first_contact_low,
    t.first_contact_close,
    t.first_contact_volume,
    t.session_vwap_through_bar,
    t.rvol,
    t.rvol_elevated,
    t.distance_from_session_vwap_atr,
    t.realized_vol_30m,
    t.realized_vol_30m_ratio,
    t.opening_range_extension_atr,
    t.displacement_3bar_atr,
    t.price_discovery_close,
    t.liquidity_sweep_trigger,
    t.trigger_reference_family,
    t.trigger_reference_level,
    t.penetration_atr,
    t.rejection_close_distance_atr,
    t.horizon_15m_clock_eligible,
    t.horizon_30m_clock_eligible,
    t.horizon_60m_clock_eligible,
    o.raw_forward_return_15m,
    o.signed_forward_return_15m,
    o.directional_success_15m,
    o.raw_forward_return_30m,
    o.signed_forward_return_30m,
    o.directional_success_30m,
    o.raw_forward_return_60m,
    o.signed_forward_return_60m,
    o.directional_success_60m,
    o.mfe_30m,
    o.mae_30m
FROM research.h4_trigger AS t
LEFT JOIN research.h4_outcome AS o
  ON o.event_id = t.event_id;
GO

CREATE OR ALTER VIEW bi.vw_h4_yearly
AS
SELECT
    YEAR(t.session_date) AS [year],
    COUNT_BIG(*) AS eligible_events,
    COUNT_BIG(DISTINCT t.session_date) AS sessions,
    AVG(o.signed_forward_return_30m) AS mean_signed_return_30m,
    AVG(CAST(o.directional_success_30m AS float)) AS directional_success_rate_30m,
    AVG(o.mfe_30m) AS mean_mfe_30m,
    AVG(o.mae_30m) AS mean_mae_30m
FROM research.h4_trigger AS t
JOIN research.h4_outcome AS o
  ON o.event_id = t.event_id
WHERE
    t.liquidity_sweep_trigger = 1
    AND t.horizon_30m_clock_eligible = 1
GROUP BY YEAR(t.session_date);
GO

CREATE OR ALTER VIEW bi.vw_result_breakdown
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

CREATE OR ALTER VIEW bi.vw_data_quality
AS
SELECT
    r.run_id,
    r.pipeline_name,
    r.script_version,
    r.git_commit,
    r.started_at_utc,
    r.completed_at_utc,
    r.status,
    q.check_name,
    q.expected_value,
    q.observed_value,
    q.passed,
    q.details
FROM audit.pipeline_run AS r
LEFT JOIN audit.quality_check AS q
  ON q.run_id = r.run_id;
GO
