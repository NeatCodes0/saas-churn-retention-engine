-- Triangular Cohort Retention & Net Revenue Retention (NRR) Engine
-- Computes customer logo survival and revenue expansion/contraction across monthly tenure intervals

WITH CUSTOMER_FIRST_COHORT AS (
    SELECT
        CUSTOMER_ID,
        MIN(COHORT_MONTH) AS COHORT_MONTH
    FROM
        SUBSCRIPTION_EVENTS
    GROUP BY
        CUSTOMER_ID
), MONTHLY_ACTIVITY AS (
    SELECT
        E.CUSTOMER_ID,
        C.COHORT_MONTH,
        STRFTIME(E.EVENT_DATE, '%Y-%m')                                               AS ACTIVITY_MONTH,
        (EXTRACT(YEAR FROM E.EVENT_DATE) - EXTRACT(YEAR FROM CAST(C.COHORT_MONTH
                                                                  || '-01' AS DATE))) * 12 + (EXTRACT(MONTH FROM E.EVENT_DATE) - EXTRACT(MONTH FROM CAST(C.COHORT_MONTH
                                                                  || '-01' AS DATE))) AS TENURE_MONTH,
        E.MRR,
        E.EVENT_TYPE
    FROM
        SUBSCRIPTION_EVENTS   E
        INNER JOIN CUSTOMER_FIRST_COHORT C
        ON E.CUSTOMER_ID = C.CUSTOMER_ID
    WHERE
        E.MRR > 0
        AND E.EVENT_TYPE != 'churn'
), COHORT_SIZES AS (
    SELECT
        COHORT_MONTH,
        COUNT(DISTINCT CUSTOMER_ID) AS INITIAL_USERS,
        ROUND(SUM(MRR), 2)          AS INITIAL_MRR
    FROM
        MONTHLY_ACTIVITY
    WHERE
        TENURE_MONTH = 0
    GROUP BY
        COHORT_MONTH
), COHORT_TENURE_AGGREGATED AS (
    SELECT
        A.COHORT_MONTH,
        A.TENURE_MONTH,
        COUNT(DISTINCT A.CUSTOMER_ID) AS ACTIVE_USERS,
        ROUND(SUM(A.MRR), 2)          AS ACTIVE_MRR
    FROM
        MONTHLY_ACTIVITY A
    GROUP BY
        A.COHORT_MONTH,
        A.TENURE_MONTH
)
SELECT
    T.COHORT_MONTH,
    S.INITIAL_USERS,
    T.TENURE_MONTH,
    T.ACTIVE_USERS,
    ROUND((T.ACTIVE_USERS * 100.0) / S.INITIAL_USERS, 2) AS USER_RETENTION_PCT,
    T.ACTIVE_MRR,
    ROUND((T.ACTIVE_MRR * 100.0) / S.INITIAL_MRR, 2)     AS NRR_PCT
FROM
    COHORT_TENURE_AGGREGATED T
    INNER JOIN COHORT_SIZES S
    ON T.COHORT_MONTH = S.COHORT_MONTH
ORDER BY
    T.COHORT_MONTH ASC,
    T.TENURE_MONTH ASC;