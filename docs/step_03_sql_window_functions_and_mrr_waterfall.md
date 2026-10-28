# Step 3 Master Study Guide: SQL Window Functions & MRR Waterfall Decomposition Engine

---

## 1. Executive Summary & SaaS Business Problem Framing

In subscription businesses (B2B SaaS, consumer subscriptions, usage-based recurring models), the single most scrutinized financial dashboard is the **Monthly Recurring Revenue (MRR) Waterfall**.

Top-line revenue figures alone are deceptive. A company can show steady top-line growth while on the brink of failure if customer acquisition masks underlying attrition:
- If a business adds $60,000 in new recurring subscriptions but loses $55,000 to churn and downgrades, net growth is only $5,000.
- Customer Acquisition Cost (CAC) is depleted without generating compounding lifetime value.
- This dynamic is known as the **"Leaky Bucket Problem"**.

Transactional subscription databases store **ledger events** (e.g., invoices, upgrades, downgrades, cancellations) or monthly snapshots. Raw event records do not state *what kind* of dollar moved:
- Did a $99 payment come from a brand-new user?
- Was it an existing user upgrading from a $29 plan?
- Was it an enterprise customer downgrading from $299?
- Did an account churn completely?

To classify each transaction, the database engine must compare a customer's state at month $t$ directly against their state at month $t-1$. In relational databases (DuckDB, Snowflake, BigQuery, PostgreSQL), this requires **SQL Window Functions**.

---

## 2. SQL Architecture: GROUP BY vs. Window Functions

### 2.1 The Core Conceptual Distinction
* **`GROUP BY` (Collapsing Aggregation)**: Groups rows sharing identical keys and collapses them into a single summary row. Individual row identity, metadata, and timestamps are discarded.
* **`OVER (...)` (Non-Collapsing Window Transformation)**: Evaluates calculations across a defined slice of rows ("window frame") while **retaining every individual row and its original cardinality**.

```text
Input Rows:                     GROUP BY (Collapses):           WINDOW FUNCTION (Preserves):
[Cust A, Jan, $29]  ──┐         ┌────────────────────┐          ┌──────────────────────────────────┐
[Cust A, Feb, $99]  ──┼───────> │ Cust A | Total $128│          │ Cust A | Jan | $29 | Prev: $0    │
                      │         └────────────────────┘          │ Cust A | Feb | $99 | Prev: $29   │
                                                                └──────────────────────────────────┘
```

### 2.2 Physical Execution Order in SQL Query Engines
Understanding the sequence of query planning is critical for debugging complex analytical pipelines:

1. `FROM` & `JOIN` (Resolve data sources, cross joins, lateral joins)
2. `WHERE` (Filter base rows before any grouping occurs)
3. `GROUP BY` (Collapse grouped dimensions)
4. `HAVING` (Filter collapsed aggregate groups)
5. **`WINDOW` Functions** (Evaluated across the rows resulting from Step 4)
6. `SELECT` (Project expressions, calculations, and column aliases)
7. `DISTINCT` (Deduplicate projected tuples)
8. `UNION` / `INTERSECT` / `EXCEPT` (Set operations across query blocks)
9. `ORDER BY` (Final sort for display or serialization)
10. `OFFSET` (Skip leading records)
11. `LIMIT` / `FETCH FIRST` (Slice final output record batch)

> **Architectural Constraint**: A window function cannot be placed inside a `WHERE` or `HAVING` clause because filtering executes in Steps 2 and 4, before window functions evaluate in Step 5. To filter on the output of a window function, wrap it in a **Common Table Expression (CTE)** or subquery.

---

## 3. SQL Window Function Anatomy & Mechanics

Every window function requires the `OVER ()` clause, composed of three core parameters:

```sql
WINDOW_FUNCTION(...) OVER (
    PARTITION BY partition_column
    ORDER BY sort_column ASC|DESC
    ROWS BETWEEN frame_start AND frame_end
)
```

### 3.1 `PARTITION BY` (Logical Boundary Isolation)
* Divides the input table into logical slices called partitions.
* The calculation evaluates completely independently within each partition.
* When the engine reaches the end of a partition, the internal accumulator resets.
* If omitted (`OVER (ORDER BY ...)`), the entire table is treated as a single partition.

### 3.2 `ORDER BY` (Intra-Partition Sequencing)
* Determines the physical or logical sequence in which rows are processed within their respective partition.
* Essential for time-series computations such as event sequences, cumulative totals, and lag offsets.

### 3.3 Frame Specifications: `ROWS` vs. `RANGE` vs. `GROUPS`
When an `ORDER BY` clause is present without an explicit frame clause, SQL standard engines default to:
```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

* **`ROWS`**: Evaluates physical row offsets.
  * `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW` explicitly takes the previous row and the current row.
* **`RANGE`**: Evaluates logical value offsets based on the sorting key.
  * If two rows have identical timestamps or sorting values, `RANGE` treats them as duplicates and evaluates them together. In cumulative calculations, this causes sudden step-function jumps rather than clean incremental running totals.
* **Production Best Practice**: In financial event ledgers, always specify `ROWS BETWEEN ...` explicitly to avoid duplicate-timestamp aggregation bugs.

---

## 4. Key Window Functions in Subscription Analytics

### 4.1 Value Access Functions: `LAG()` and `LEAD()`
* **`LAG(column, [offset], [default_value])`**: Fetches a column value from $N$ rows prior to the current row within the active partition.
* **`LEAD(column, [offset], [default_value])`**: Fetches a column value from $N$ rows ahead.

```sql
LAG(mrr, 1, 0.0) OVER (
    PARTITION BY customer_id 
    ORDER BY event_date ASC
) AS previous_mrr
```
If a customer has no prior transaction, `LAG` defaults to `0.0`.

### 4.2 Ranking Functions: `ROW_NUMBER()`, `RANK()`, `DENSE_RANK()`
* `ROW_NUMBER()`: Assigns a strict sequential integer ($1, 2, 3, 4, \dots$). Identifies the exact first acquisition event (`ROW_NUMBER() = 1`).
* `RANK()`: Tied rows receive identical ranks, skipping subsequent numbers ($1, 2, 2, 4$).
* `DENSE_RANK()`: Tied rows receive identical ranks without skipping numbers ($1, 2, 2, 3$).

### 4.3 Running Aggregation: Cumulative Customer Spend (LTV Proxy)
```sql
SUM(mrr) OVER (
    PARTITION BY customer_id 
    ORDER BY event_date ASC 
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_cumulative_spend
```

---

## 5. Mathematical Decomposition of the MRR Waterfall

Let $M_t$ represent current month MRR and $M_{t-1}$ represent previous month MRR (`previous_mrr`).

```text
                             ┌────────────────────────┐
                             │     Current Event      │
                             │ (Customer at Month t)  │
                             └───────────┬────────────┘
                                         │
                   ┌─────────────────────┴─────────────────────┐
                   │                                           │
             Is Mt-1 = 0?                                Is Mt-1 > 0?
           (No Prior MRR)                              (Had Prior MRR)
            /          \                               /       │      \
           ▼            ▼                             ▼        │       ▼
       Mt > 0        Mt = 0                        Mt > Mt-1   │    Mt < Mt-1
     [NEW MRR]     [NO EVENT]                          │       │        │
                                                       ▼       │        ▼
                                                 [EXPANSION]   │   [CONTRACTION]
                                                               ▼
                                                        Mt = 0 or CHURN
                                                               │
                                                               ▼
                                                           [CHURNED]
```

### 5.1 Exact Classification Rules

| Category            | Mathematical Condition                                                 | Financial Impact   |
| :------------------ | :--------------------------------------------------------------------- | :----------------- |
| **New MRR**         | $(M_{t-1} = 0 \lor M_{t-1} \text{ IS NULL}) \land M_t > 0$             | $+M_t$             |
| **Expansion MRR**   | $M_t > M_{t-1} \land M_{t-1} > 0$                                      | $+(M_t - M_{t-1})$ |
| **Contraction MRR** | $M_t < M_{t-1} \land M_t > 0 \land M_{t-1} > 0$                        | $-(M_{t-1} - M_t)$ |
| **Churned MRR**     | $(M_t = 0 \lor \text{event\_type} = \text{'churn'}) \land M_{t-1} > 0$ | $-M_{t-1}$         |
| **Retained MRR**    | $M_t = M_{t-1}$                                                        | Flat               |

### 5.2 Balance & Reconciliation Formulas
* **Net New MRR**:
  $$\text{Net New MRR}_t = \text{New MRR}_t + \text{Expansion MRR}_t - \text{Contraction MRR}_t - \text{Churned MRR}_t$$

* **Ending MRR Reconciliation Check**:
  $$\text{Ending MRR}_t = \text{Ending MRR}_{t-1} + \text{Net New MRR}_t$$

If this balance check fails in any calendar month, the data pipeline has an integrity discrepancy (e.g., duplicate invoices, untracked mid-month tier alterations, or unhandled time-zone offsets).

---

## 6. Real-World Edge Cases & Advanced Production Considerations

### 6.1 Reactivation vs. New MRR
* **Scenario**: A customer cancels in March ($M_{\text{March}} = 0$). In October, they re-subscribe at $99/month.
* **Risk**: If the query only checks `LAG(mrr, 1)`, it observes $M_{t-1} = 0$ and classifies them as **New MRR**.
* **Impact**: Distorts Customer Acquisition Cost (CAC) metrics. The user was not acquired by top-of-funnel marketing; they were **reactivated**.
* **Production Fix**: Check whether the customer had historical events prior to the current window:
  ```sql
  CASE 
      WHEN previous_mrr = 0 AND MIN(event_date) OVER (PARTITION BY customer_id) = event_date 
          THEN 'new'
      WHEN previous_mrr = 0 AND MIN(event_date) OVER (PARTITION BY customer_id) < event_date 
          THEN 'reactivation'
  END
  ```

### 6.2 Calendar Gaps (The Inactive Account Problem)
* **Scenario**: Customers whose credit card fails or who pause their account for 60 days have no records during those months.
* **Risk**: A standard `LAG()` checks the immediate previous row, which could be 2 months old, misclassifying a dormant account as a continuous active subscription.
* **Production Fix**: Construct a continuous **Date Spine** using `GENERATE_SERIES()` left-joined against all active accounts to guarantee an explicit record for every single calendar month.

---

## 7. High-Frequency Staff & Senior Data Engineering Interview Questions

### Q1: Why use `LAG()` instead of an explicit self-join (`LEFT JOIN table b ON a.cust_id = b.cust_id AND a.month = b.month + 1`)?
> **Answer**: 
> A self-join forces the query optimizer to duplicate data streams, allocate hash tables, and evaluate join conditions—an operation that scales as $O(N \log N)$ or $O(N \times M)$ if timestamps skew. 
> In contrast, `LAG()` is an in-memory window operation. DuckDB sorts the partition once and sequentially steps through memory using an iterator offset. It runs in linear $O(N)$ time after sorting and avoids memory spikes.

### Q2: What is the exact difference between `ROWS BETWEEN` and `RANGE BETWEEN` in SQL window frames?
> **Answer**: 
> `ROWS` operates strictly on **physical row counts** relative to the current position (e.g., exactly 1 row back). 
> `RANGE` operates on the **logical values** of the column in the `ORDER BY` clause. If multiple rows share identical sorting keys (e.g., identical timestamps), `RANGE` lumps them into a single evaluation block. This causes cumulative calculations to jump unexpectedly rather than updating row-by-row.

### Q3: If Net New MRR is positive, can the company still be in danger of insolvency?
> **Answer**: 
> Yes. This is the hallmark of the "Leaky Bucket" syndrome. When a company spends heavily on paid ads, New MRR can outpace Churned MRR in the short term. However, if Logo Churn is high, customers leave before the business can recover its acquisition cost (CAC Payback period exceeds customer lifespan). The moment marketing spend is throttled, top-line MRR collapses.

### Q4: How do you mathematically decompose Expansion MRR into Seat Growth vs. Tier Upgrades?
> **Answer**: 
> In enterprise B2B SaaS, the subscription ledger tracks both `seat_count` and `unit_price_per_seat`. A multi-factor variance query isolates the true growth driver:
> * **Seat Expansion**: `(current_seats - previous_seats) * previous_unit_price`
> * **Tier Upgrade**: `current_seats * (current_unit_price - previous_unit_price)`
> * **Cross-Interaction**: `(current_seats - previous_seats) * (current_unit_price - previous_unit_price)`