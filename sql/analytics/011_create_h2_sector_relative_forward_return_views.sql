/*
011_create_h2_sector_relative_forward_return_views.sql

Purpose
-------
Join the independently validated H2 sector-relative portfolio assignments to
the already validated security-level one-month holding-return layer, then
construct sector/quintile sleeves, sector-neutral Winner and Loser legs, and
the aggregate sector-neutral Winner-minus-Loser series.

Important:
- H2 ranking assignments are already fixed before this migration.
- Security holding returns come from the validated H1-independent security
  forward-return object; no H1 decile return is reused.
- Sector aggregation is equal-weight within each sector/quintile sleeve.
- Aggregate Winner and Loser legs give each of the 11 GICS sectors equal
  influence.
- December 2025 remains right-censored.
- No statistical inference, risk metrics, turnover, costs, or interpretation
  is performed here.
- No core table is modified.
*/

CREATE OR ALTER VIEW analytics.v_h2_security_monthly_forward_return_1m
AS
SELECT
    h2.analysis_month_number,
    h2.month_start_date
        AS ranking_month_start_date,
    h2.month_end_date
        AS ranking_month_end_date,
    h2.security_key,
    h2.project_ticker,
    h2.gics_sector,
    h2.momentum_12_1,
    h2.sector_eligible_count,
    h2.sector_momentum_rank_asc,
    h2.sector_momentum_quintile,
    h2.sector_momentum_portfolio,
    h2.sector_quintile_security_count,
    h2.sector_equal_weight,
    h2.sector_neutral_leg_weight,

    fwd.target_holding_end_date,
    fwd.holding_end_status,
    fwd.holding_end_is_exact_month_end,
    fwd.holding_end_is_early_exit,
    fwd.holding_end_is_immediate_exit,
    fwd.forward_return_1m,
    fwd.forward_return_1m_complete,
    fwd.out_of_scope_right_censored

FROM analytics.v_security_monthly_sector_momentum_portfolio
    AS h2
INNER JOIN analytics.v_security_monthly_forward_return_1m
    AS fwd
  ON fwd.analysis_month_number
   = h2.analysis_month_number
 AND fwd.security_key
   = h2.security_key;
GO

CREATE OR ALTER VIEW analytics.v_h2_sector_quintile_forward_return_1m
AS
SELECT
    h2.analysis_month_number,
    MIN(h2.ranking_month_start_date)
        AS ranking_month_start_date,
    MIN(h2.ranking_month_end_date)
        AS ranking_month_end_date,
    MAX(h2.target_holding_end_date)
        AS target_holding_end_date,
    h2.gics_sector,
    h2.sector_momentum_quintile,
    MIN(h2.sector_momentum_portfolio)
        AS sector_momentum_portfolio,

    COUNT_BIG(*) AS security_count,

    SUM(
        CASE
            WHEN h2.forward_return_1m_complete = 1
                THEN 1
            ELSE 0
        END
    ) AS complete_security_count,

    SUM(h2.sector_equal_weight)
        AS sector_equal_weight_sum,

    CASE
        WHEN SUM(
            CASE
                WHEN h2.forward_return_1m_complete = 1
                    THEN 1
                ELSE 0
            END
        ) = COUNT_BIG(*)
        THEN SUM(
            CAST(h2.sector_equal_weight AS FLOAT)
            * CAST(h2.forward_return_1m AS FLOAT)
        )
        ELSE NULL
    END AS equal_weight_forward_return_1m,

    CAST(
        CASE
            WHEN SUM(
                CASE
                    WHEN h2.forward_return_1m_complete = 1
                        THEN 1
                    ELSE 0
                END
            ) = COUNT_BIG(*)
                THEN 1
            ELSE 0
        END
        AS BIT
    ) AS forward_return_1m_complete,

    CAST(
        CASE
            WHEN SUM(
                CASE
                    WHEN h2.out_of_scope_right_censored = 1
                        THEN 1
                    ELSE 0
                END
            ) = COUNT_BIG(*)
                THEN 1
            ELSE 0
        END
        AS BIT
    ) AS out_of_scope_right_censored

FROM analytics.v_h2_security_monthly_forward_return_1m
    AS h2
GROUP BY
    h2.analysis_month_number,
    h2.gics_sector,
    h2.sector_momentum_quintile;
GO

CREATE OR ALTER VIEW analytics.v_h2_sector_extreme_forward_return_1m
AS
SELECT
    sector_return.analysis_month_number,
    sector_return.ranking_month_start_date,
    sector_return.ranking_month_end_date,
    sector_return.target_holding_end_date,
    sector_return.gics_sector,
    sector_return.sector_momentum_quintile,
    sector_return.sector_momentum_portfolio,
    sector_return.security_count,
    sector_return.complete_security_count,
    sector_return.sector_equal_weight_sum,
    sector_return.equal_weight_forward_return_1m,
    sector_return.forward_return_1m_complete,
    sector_return.out_of_scope_right_censored

FROM analytics.v_h2_sector_quintile_forward_return_1m
    AS sector_return
WHERE sector_return.sector_momentum_quintile IN (1, 5);
GO

CREATE OR ALTER VIEW analytics.v_h2_sector_neutral_leg_forward_return_1m
AS
SELECT
    extreme.analysis_month_number,
    MIN(extreme.ranking_month_start_date)
        AS ranking_month_start_date,
    MIN(extreme.ranking_month_end_date)
        AS ranking_month_end_date,
    MAX(extreme.target_holding_end_date)
        AS target_holding_end_date,
    extreme.sector_momentum_portfolio,

    COUNT_BIG(*) AS sector_count,

    SUM(
        CASE
            WHEN extreme.forward_return_1m_complete = 1
                THEN 1
            ELSE 0
        END
    ) AS complete_sector_count,

    CASE
        WHEN COUNT_BIG(*) = 11
         AND SUM(
                CASE
                    WHEN extreme.forward_return_1m_complete = 1
                        THEN 1
                    ELSE 0
                END
             ) = 11
        THEN AVG(
            CAST(
                extreme.equal_weight_forward_return_1m
                AS FLOAT
            )
        )
        ELSE NULL
    END AS sector_neutral_forward_return_1m,

    CAST(
        CASE
            WHEN COUNT_BIG(*) = 11
             AND SUM(
                    CASE
                        WHEN extreme.forward_return_1m_complete = 1
                            THEN 1
                        ELSE 0
                    END
                 ) = 11
                THEN 1
            ELSE 0
        END
        AS BIT
    ) AS forward_return_1m_complete,

    CAST(
        CASE
            WHEN COUNT_BIG(*) = 11
             AND SUM(
                    CASE
                        WHEN extreme.out_of_scope_right_censored = 1
                            THEN 1
                        ELSE 0
                    END
                 ) = 11
                THEN 1
            ELSE 0
        END
        AS BIT
    ) AS out_of_scope_right_censored

FROM analytics.v_h2_sector_extreme_forward_return_1m
    AS extreme
GROUP BY
    extreme.analysis_month_number,
    extreme.sector_momentum_portfolio;
GO

CREATE OR ALTER VIEW analytics.v_h2_sector_neutral_wml_forward_return_1m
AS
SELECT
    winner.analysis_month_number,
    winner.ranking_month_start_date,
    winner.ranking_month_end_date,
    winner.target_holding_end_date,

    winner.sector_count
        AS winner_sector_count,
    loser.sector_count
        AS loser_sector_count,

    winner.sector_neutral_forward_return_1m
        AS winner_forward_return_1m,
    loser.sector_neutral_forward_return_1m
        AS loser_forward_return_1m,

    CASE
        WHEN winner.forward_return_1m_complete = 1
         AND loser.forward_return_1m_complete = 1
        THEN
            CAST(
                winner.sector_neutral_forward_return_1m
                AS FLOAT
            )
            -
            CAST(
                loser.sector_neutral_forward_return_1m
                AS FLOAT
            )
        ELSE NULL
    END AS winner_minus_loser_forward_return_1m,

    CAST(
        CASE
            WHEN winner.forward_return_1m_complete = 1
             AND loser.forward_return_1m_complete = 1
                THEN 1
            ELSE 0
        END
        AS BIT
    ) AS forward_return_1m_complete,

    CAST(
        CASE
            WHEN winner.out_of_scope_right_censored = 1
             AND loser.out_of_scope_right_censored = 1
                THEN 1
            ELSE 0
        END
        AS BIT
    ) AS out_of_scope_right_censored

FROM analytics.v_h2_sector_neutral_leg_forward_return_1m
    AS winner
INNER JOIN analytics.v_h2_sector_neutral_leg_forward_return_1m
    AS loser
  ON loser.analysis_month_number
   = winner.analysis_month_number
 AND loser.sector_momentum_portfolio = N'LOSER'
WHERE winner.sector_momentum_portfolio = N'WINNER';
GO
