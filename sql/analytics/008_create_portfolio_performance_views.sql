SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_monthly_return_panel
AS
SELECT
    decile.analysis_month_number,
    decile.ranking_month_start_date,
    decile.ranking_month_end_date,
    decile.target_holding_end_date AS return_period_end_date,
    CAST(
        'D' + RIGHT(
            '0' + CAST(decile.momentum_decile AS varchar(2)),
            2
        )
        AS varchar(16)
    ) AS series_code,
    CAST(
        CASE
            WHEN decile.momentum_decile = 1
            THEN 'Loser Decile'
            WHEN decile.momentum_decile = 10
            THEN 'Winner Decile'
            ELSE
                'Momentum Decile '
                + CAST(decile.momentum_decile AS varchar(2))
        END
        AS varchar(64)
    ) AS series_name,
    CAST('DECILE' AS varchar(32)) AS series_type,
    decile.momentum_decile,
    decile.momentum_decile AS series_sort_order,
    decile.equal_weight_forward_return_1m
        AS monthly_return,
    decile.forward_return_1m_complete AS return_complete
FROM analytics.v_momentum_decile_forward_return_1m
    AS decile
WHERE decile.forward_return_1m_complete = 1

UNION ALL

SELECT
    long_short.analysis_month_number,
    long_short.ranking_month_start_date,
    long_short.ranking_month_end_date,
    long_short.target_holding_end_date AS return_period_end_date,
    CAST('WML' AS varchar(16)) AS series_code,
    CAST('Winner Minus Loser' AS varchar(64)) AS series_name,
    CAST('LONG_SHORT' AS varchar(32)) AS series_type,
    CAST(NULL AS int) AS momentum_decile,
    11 AS series_sort_order,
    long_short.winner_minus_loser_forward_return_1m
        AS monthly_return,
    long_short.forward_return_1m_complete AS return_complete
FROM analytics.v_momentum_long_short_forward_return_1m
    AS long_short
WHERE long_short.forward_return_1m_complete = 1

UNION ALL

SELECT
    benchmark.analysis_month_number,
    benchmark.ranking_month_start_date,
    benchmark.ranking_month_end_date,
    benchmark.target_holding_end_date AS return_period_end_date,
    CAST(
        CASE
            WHEN benchmark.series_type = 'ETF'
            THEN 'SPY'
            ELSE 'SP500'
        END
        AS varchar(16)
    ) AS series_code,
    CAST(
        CASE
            WHEN benchmark.series_type = 'ETF'
            THEN 'SPDR S&P 500 ETF Trust'
            ELSE 'S&P 500 Index'
        END
        AS varchar(64)
    ) AS series_name,
    CAST('BENCHMARK' AS varchar(32)) AS series_type,
    CAST(NULL AS int) AS momentum_decile,
    CASE
        WHEN benchmark.series_type = 'ETF'
        THEN 12
        ELSE 13
    END AS series_sort_order,
    benchmark.forward_return_1m AS monthly_return,
    benchmark.forward_return_1m_complete AS return_complete
FROM analytics.v_benchmark_monthly_forward_return_1m
    AS benchmark
WHERE benchmark.forward_return_1m_complete = 1;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_cumulative_wealth
AS
WITH sequenced AS (
    SELECT
        panel.*,
        ROW_NUMBER() OVER (
            PARTITION BY panel.series_code
            ORDER BY panel.analysis_month_number
        ) AS return_sequence,
        COUNT_BIG(*) OVER (
            PARTITION BY panel.series_code
        ) AS return_period_count,
        SUM(
            LOG(
                1.0 + CAST(panel.monthly_return AS float)
            )
        ) OVER (
            PARTITION BY panel.series_code
            ORDER BY panel.analysis_month_number
            ROWS BETWEEN UNBOUNDED PRECEDING
                AND CURRENT ROW
        ) AS cumulative_log_return,
        SUM(
            LOG(
                1.0 + CAST(panel.monthly_return AS float)
            )
        ) OVER (
            PARTITION BY panel.series_code
            ORDER BY panel.analysis_month_number
            ROWS BETWEEN UNBOUNDED PRECEDING
                AND 1 PRECEDING
        ) AS prior_cumulative_log_return
    FROM analytics.v_momentum_monthly_return_panel
        AS panel
)
SELECT
    sequenced.analysis_month_number,
    sequenced.ranking_month_start_date,
    sequenced.ranking_month_end_date,
    sequenced.return_period_end_date,
    sequenced.series_code,
    sequenced.series_name,
    sequenced.series_type,
    sequenced.momentum_decile,
    sequenced.series_sort_order,
    sequenced.return_sequence,
    sequenced.return_period_count,
    sequenced.monthly_return,
    CAST(
        EXP(
            COALESCE(
                sequenced.prior_cumulative_log_return,
                0.0
            )
        )
        AS decimal(38, 18)
    ) AS beginning_wealth,
    CAST(
        EXP(sequenced.cumulative_log_return)
        AS decimal(38, 18)
    ) AS ending_wealth
FROM sequenced;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_wealth_drawdown
AS
WITH peaks AS (
    SELECT
        wealth.*,
        MAX(
            CASE
                WHEN wealth.ending_wealth > 1
                THEN wealth.ending_wealth
                ELSE CAST(1 AS decimal(38, 18))
            END
        ) OVER (
            PARTITION BY wealth.series_code
            ORDER BY wealth.analysis_month_number
            ROWS BETWEEN UNBOUNDED PRECEDING
                AND CURRENT ROW
        ) AS running_peak_wealth
    FROM analytics.v_momentum_cumulative_wealth
        AS wealth
)
SELECT
    peaks.analysis_month_number,
    peaks.ranking_month_start_date,
    peaks.ranking_month_end_date,
    peaks.return_period_end_date,
    peaks.series_code,
    peaks.series_name,
    peaks.series_type,
    peaks.momentum_decile,
    peaks.series_sort_order,
    peaks.return_sequence,
    peaks.return_period_count,
    peaks.monthly_return,
    peaks.beginning_wealth,
    peaks.ending_wealth,
    peaks.running_peak_wealth,
    CAST(
        CAST(peaks.ending_wealth AS float)
        / CAST(peaks.running_peak_wealth AS float)
        - 1.0
        AS decimal(38, 18)
    ) AS drawdown
FROM peaks;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_performance_summary
AS
WITH active_returns AS (
    SELECT
        panel.series_code,
        panel.series_name,
        panel.series_type,
        panel.momentum_decile,
        panel.series_sort_order,
        panel.analysis_month_number,
        panel.monthly_return,
        CAST(
            CAST(panel.monthly_return AS float)
            - CAST(spy.monthly_return AS float)
            AS decimal(38, 18)
        ) AS active_return_vs_spy
    FROM analytics.v_momentum_monthly_return_panel
        AS panel
    INNER JOIN analytics.v_momentum_monthly_return_panel
        AS spy
      ON spy.analysis_month_number
       = panel.analysis_month_number
     AND spy.series_code = 'SPY'
),
return_statistics AS (
    SELECT
        active.series_code,
        MAX(active.series_name) AS series_name,
        MAX(active.series_type) AS series_type,
        MAX(active.momentum_decile) AS momentum_decile,
        MAX(active.series_sort_order) AS series_sort_order,
        COUNT_BIG(*) AS observed_months,
        MIN(active.analysis_month_number)
            AS first_analysis_month_number,
        MAX(active.analysis_month_number)
            AS last_analysis_month_number,
        AVG(CAST(active.monthly_return AS float))
            AS arithmetic_mean_monthly_return,
        STDEV(CAST(active.monthly_return AS float))
            AS monthly_volatility,
        MIN(CAST(active.monthly_return AS float))
            AS worst_monthly_return,
        MAX(CAST(active.monthly_return AS float))
            AS best_monthly_return,
        SUM(
            CASE
                WHEN active.monthly_return > 0
                THEN 1
                ELSE 0
            END
        ) AS positive_months,
        AVG(CAST(active.active_return_vs_spy AS float))
            AS mean_monthly_active_return_vs_spy,
        STDEV(CAST(active.active_return_vs_spy AS float))
            AS monthly_tracking_error_vs_spy
    FROM active_returns AS active
    GROUP BY active.series_code
),
wealth_statistics AS (
    SELECT
        drawdown.series_code,
        MAX(
            CASE
                WHEN drawdown.return_sequence
                    = drawdown.return_period_count
                THEN drawdown.ending_wealth
            END
        ) AS final_wealth,
        MIN(drawdown.drawdown) AS maximum_drawdown
    FROM analytics.v_momentum_wealth_drawdown
        AS drawdown
    GROUP BY drawdown.series_code
)
SELECT
    returns.series_code,
    returns.series_name,
    returns.series_type,
    returns.momentum_decile,
    returns.series_sort_order,
    returns.observed_months,
    returns.first_analysis_month_number,
    returns.last_analysis_month_number,
    wealth.final_wealth,
    CAST(
        CAST(wealth.final_wealth AS float) - 1.0
        AS decimal(38, 18)
    ) AS cumulative_return,
    CAST(
        returns.arithmetic_mean_monthly_return
        AS decimal(38, 18)
    ) AS arithmetic_mean_monthly_return,
    CAST(
        POWER(
            CAST(wealth.final_wealth AS float),
            1.0 / CAST(returns.observed_months AS float)
        ) - 1.0
        AS decimal(38, 18)
    ) AS geometric_mean_monthly_return,
    CAST(
        POWER(
            CAST(wealth.final_wealth AS float),
            12.0 / CAST(returns.observed_months AS float)
        ) - 1.0
        AS decimal(38, 18)
    ) AS annualized_return,
    CAST(
        returns.monthly_volatility
        AS decimal(38, 18)
    ) AS monthly_volatility,
    CAST(
        returns.monthly_volatility * SQRT(12.0)
        AS decimal(38, 18)
    ) AS annualized_volatility,
    CAST(
        returns.worst_monthly_return
        AS decimal(38, 18)
    ) AS worst_monthly_return,
    CAST(
        returns.best_monthly_return
        AS decimal(38, 18)
    ) AS best_monthly_return,
    returns.positive_months,
    CAST(
        CAST(returns.positive_months AS float)
        / CAST(returns.observed_months AS float)
        AS decimal(38, 18)
    ) AS positive_month_frequency,
    wealth.maximum_drawdown,
    CAST(
        returns.mean_monthly_active_return_vs_spy
        AS decimal(38, 18)
    ) AS mean_monthly_active_return_vs_spy,
    CAST(
        returns.mean_monthly_active_return_vs_spy * 12.0
        AS decimal(38, 18)
    ) AS annualized_active_return_vs_spy,
    CAST(
        returns.monthly_tracking_error_vs_spy
        * SQRT(12.0)
        AS decimal(38, 18)
    ) AS annualized_tracking_error_vs_spy,
    CAST(
        CASE
            WHEN returns.monthly_tracking_error_vs_spy = 0
            THEN NULL
            ELSE
                returns.mean_monthly_active_return_vs_spy
                / returns.monthly_tracking_error_vs_spy
                * SQRT(12.0)
        END
        AS decimal(38, 18)
    ) AS information_ratio_vs_spy
FROM return_statistics AS returns
INNER JOIN wealth_statistics AS wealth
  ON wealth.series_code = returns.series_code;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_decile_turnover
AS
WITH ranking_months AS (
    SELECT
        portfolio.analysis_month_number,
        MIN(portfolio.month_start_date) AS month_start_date,
        MAX(portfolio.month_end_date) AS month_end_date
    FROM analytics.v_security_monthly_momentum_portfolio
        AS portfolio
    GROUP BY portfolio.analysis_month_number
),
month_pairs AS (
    SELECT
        current_month.analysis_month_number,
        current_month.month_start_date,
        current_month.month_end_date,
        previous_month.analysis_month_number
            AS previous_analysis_month_number,
        previous_month.month_end_date
            AS previous_month_end_date
    FROM ranking_months AS current_month
    INNER JOIN ranking_months AS previous_month
      ON previous_month.analysis_month_number
       = current_month.analysis_month_number - 1
),
portfolio_keys AS (
    SELECT
        pair.analysis_month_number,
        current_portfolio.momentum_decile,
        current_portfolio.security_key
    FROM month_pairs AS pair
    INNER JOIN analytics.v_security_monthly_momentum_portfolio
        AS current_portfolio
      ON current_portfolio.analysis_month_number
       = pair.analysis_month_number

    UNION

    SELECT
        pair.analysis_month_number,
        previous_portfolio.momentum_decile,
        previous_portfolio.security_key
    FROM month_pairs AS pair
    INNER JOIN analytics.v_security_monthly_momentum_portfolio
        AS previous_portfolio
      ON previous_portfolio.analysis_month_number
       = pair.previous_analysis_month_number
),
weight_changes AS (
    SELECT
        pair.analysis_month_number,
        pair.month_start_date,
        pair.month_end_date,
        pair.previous_analysis_month_number,
        pair.previous_month_end_date,
        keys.momentum_decile,
        keys.security_key,
        current_portfolio.equal_weight AS current_weight,
        previous_portfolio.equal_weight AS previous_weight
    FROM portfolio_keys AS keys
    INNER JOIN month_pairs AS pair
      ON pair.analysis_month_number
       = keys.analysis_month_number
    LEFT JOIN analytics.v_security_monthly_momentum_portfolio
        AS current_portfolio
      ON current_portfolio.analysis_month_number
       = keys.analysis_month_number
     AND current_portfolio.momentum_decile
       = keys.momentum_decile
     AND current_portfolio.security_key
       = keys.security_key
    LEFT JOIN analytics.v_security_monthly_momentum_portfolio
        AS previous_portfolio
      ON previous_portfolio.analysis_month_number
       = pair.previous_analysis_month_number
     AND previous_portfolio.momentum_decile
       = keys.momentum_decile
     AND previous_portfolio.security_key
       = keys.security_key
)
SELECT
    changes.analysis_month_number,
    MAX(changes.month_start_date) AS month_start_date,
    MAX(changes.month_end_date) AS month_end_date,
    MAX(changes.previous_analysis_month_number)
        AS previous_analysis_month_number,
    MAX(changes.previous_month_end_date)
        AS previous_month_end_date,
    changes.momentum_decile,
    CAST(
        CASE
            WHEN changes.momentum_decile = 1
            THEN 'LOSER'
            WHEN changes.momentum_decile = 10
            THEN 'WINNER'
            ELSE 'MIDDLE'
        END
        AS varchar(16)
    ) AS momentum_portfolio,
    SUM(
        CASE
            WHEN changes.current_weight IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS current_security_count,
    SUM(
        CASE
            WHEN changes.previous_weight IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS previous_security_count,
    SUM(
        CASE
            WHEN changes.current_weight IS NOT NULL
             AND changes.previous_weight IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS retained_security_count,
    SUM(
        CASE
            WHEN changes.current_weight IS NOT NULL
             AND changes.previous_weight IS NULL
            THEN 1
            ELSE 0
        END
    ) AS entered_security_count,
    SUM(
        CASE
            WHEN changes.current_weight IS NULL
             AND changes.previous_weight IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS exited_security_count,
    CAST(
        CAST(
            SUM(
                CASE
                    WHEN changes.current_weight IS NOT NULL
                     AND changes.previous_weight IS NOT NULL
                    THEN 1
                    ELSE 0
                END
            )
            AS float
        )
        / NULLIF(
            CAST(
                SUM(
                    CASE
                        WHEN changes.previous_weight IS NOT NULL
                        THEN 1
                        ELSE 0
                    END
                )
                AS float
            ),
            0.0
        )
        AS decimal(38, 18)
    ) AS security_overlap_rate,
    CAST(
        0.5
        * SUM(
            ABS(
                CAST(
                    COALESCE(
                        changes.current_weight,
                        CAST(0 AS decimal(38, 18))
                    )
                    AS float
                )
                - CAST(
                    COALESCE(
                        changes.previous_weight,
                        CAST(0 AS decimal(38, 18))
                    )
                    AS float
                )
            )
        )
        AS decimal(38, 18)
    ) AS target_weight_one_way_turnover
FROM weight_changes AS changes
GROUP BY
    changes.analysis_month_number,
    changes.momentum_decile;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_turnover_summary
AS
SELECT
    turnover.momentum_decile,
    MAX(turnover.momentum_portfolio) AS momentum_portfolio,
    COUNT_BIG(*) AS observed_rebalances,
    CAST(
        AVG(
            CAST(
                turnover.target_weight_one_way_turnover
                AS float
            )
        )
        AS decimal(38, 18)
    ) AS average_monthly_target_weight_turnover,
    CAST(
        AVG(
            CAST(
                turnover.target_weight_one_way_turnover
                AS float
            )
        ) * 12.0
        AS decimal(38, 18)
    ) AS annualized_target_weight_turnover,
    MIN(turnover.target_weight_one_way_turnover)
        AS minimum_monthly_target_weight_turnover,
    MAX(turnover.target_weight_one_way_turnover)
        AS maximum_monthly_target_weight_turnover,
    CAST(
        AVG(CAST(turnover.security_overlap_rate AS float))
        AS decimal(38, 18)
    ) AS average_security_overlap_rate,
    SUM(turnover.entered_security_count)
        AS total_security_entries,
    SUM(turnover.exited_security_count)
        AS total_security_exits
FROM analytics.v_momentum_decile_turnover
    AS turnover
GROUP BY turnover.momentum_decile;
GO