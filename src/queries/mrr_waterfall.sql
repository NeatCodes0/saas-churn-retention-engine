-- Monthly Recurring Revenue (MRR) Waterfall Engine
-- Classifies monthly movements into New, Expansion, Contraction, and Churned MRR

WITH CUSTOMER_MONTHLY_LEDGER AS (
    SELECT
        CUSTOMER_ID,
        STRFTIME(EVENT_DATE, '%Y-%m')                                          AS ACTIVITY_MONTH,
        MRR                                                                    AS CURRENT_MRR,
        EVENT_TYPE,
 
        -- Window function: Retrieve previous period MRR per customer
        LAG(MRR, 1, 0.0) OVER ( PARTITION BY CUSTOMER_ID ORDER BY EVENT_DATE ) AS PREVIOUS_MRR
    FROM
        SUBSCRIPTION_EVENTS
), MRR_MOVEMENT_CLASSIFICATION AS (
    SELECT
        CUSTOMER_ID,
        ACTIVITY_MONTH,
        PREVIOUS_MRR,
        CURRENT_MRR,
        EVENT_TYPE,
 
        -- New MRR: First acquisition or zero-baseline activation
        CASE
            WHEN (PREVIOUS_MRR = 0.0
            OR PREVIOUS_MRR IS NULL) AND CURRENT_MRR > 0.0
            THEN
                CURRENT_MRR
            ELSE
                0.0
        END            AS NEW_MRR,
 
        -- Expansion MRR: Existing active account upgrade
        CASE
            WHEN CURRENT_MRR > PREVIOUS_MRR AND PREVIOUS_MRR > 0.0
            THEN
                (CURRENT_MRR - PREVIOUS_MRR)
            ELSE
                0.0
        END            AS EXPANSION_MRR,
 
        -- Contraction MRR: Existing active account downgrade
        CASE
            WHEN CURRENT_MRR < PREVIOUS_MRR AND CURRENT_MRR > 0.0
            THEN
                (PREVIOUS_MRR - CURRENT_MRR)
            ELSE
                0.0
        END            AS CONTRACTION_MRR,
 
        -- Churned MRR: Cancellation or dropped to 0
        CASE
            WHEN CURRENT_MRR = 0.0 OR EVENT_TYPE = 'churn'
            THEN
                PREVIOUS_MRR
            ELSE
                0.0
        END            AS CHURNED_MRR
    FROM
        CUSTOMER_MONTHLY_LEDGER
)
SELECT
    ACTIVITY_MONTH,
    ROUND(SUM(NEW_MRR), 2)                                                                  AS TOTAL_NEW_MRR,
    ROUND(SUM(EXPANSION_MRR), 2)                                                            AS TOTAL_EXPANSION_MRR,
    ROUND(SUM(CONTRACTION_MRR), 2)                                                          AS TOTAL_CONTRACTION_MRR,
    ROUND(SUM(CHURNED_MRR), 2)                                                              AS TOTAL_CHURNED_MRR,
    ROUND( SUM(NEW_MRR) + SUM(EXPANSION_MRR) - SUM(CONTRACTION_MRR) - SUM(CHURNED_MRR), 2 ) AS NET_NEW_MRR,
    ROUND(SUM(CURRENT_MRR), 2)                                                              AS ENDING_MRR
FROM
    MRR_MOVEMENT_CLASSIFICATION
GROUP BY
    ACTIVITY_MONTH
ORDER BY
    ACTIVITY_MONTH ASC;