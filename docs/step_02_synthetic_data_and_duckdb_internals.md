# Step 2 Study Guide: Synthetic Data Simulation & DuckDB Architecture Internals

## 1. Problem Statement: Generating Realistic SaaS Subscription Events
In real-world data engineering, testing retention models on uniform random data generates misleading findings because real customers do not behave uniformly. Customer churn features distinct behavioral mechanics:
1. **Month-2 Churn Cliff**: A sharp initial spike in cancellations right after onboarding or trial expiration (buyer's remorse, poor setup).
2. **Tenure Decay Curve**: The probability of churn decreases significantly as a customer integrates the software into their ongoing workflow.
3. **Account Expansion / Contraction**: Active customers occasionally upgrade seat counts, switch tiers, or downgrade.

---

## 2. Event-Driven Data Model Schema

We model the subscription engine using an event-driven ledger rather than a static snapshot:

| Field Name        | Data Type | Description                                     | Example      |
| :---------------- | :-------- | :---------------------------------------------- | :----------- |
| `subscription_id` | `VARCHAR` | Primary Key for the subscription line           | `SUB-10492`  |
| `customer_id`     | `VARCHAR` | Foreign Key representing the company/user       | `CUST-8831`  |
| `signup_date`     | `DATE`    | Initial acquisition date (Cohort Anchor)        | `2024-01-15` |
| `event_date`      | `DATE`    | Date of invoice/billing status change           | `2024-02-15` |
| `tier`            | `VARCHAR` | Plan tier (`Starter`, `Pro`, `Enterprise`)      | `Pro`        |
| `mrr`             | `DOUBLE`  | Monthly Recurring Revenue for this period       | `199.0`      |
| `event_type`      | `VARCHAR` | `new`, `renew`, `upgrade`, `downgrade`, `churn` | `renew`      |

---

## 3. DuckDB Internals: Why It Powers Modern Analytical Engines

### 3.1 Columnar Storage vs. Row Storage (OLAP vs. OLTP)
* **OLTP (e.g., PostgreSQL, SQLite, MySQL)**: Stores data in row-tuples (`[id, name, date, mrr]`). Ideal for point updates and single-row transactional inserts (`INSERT`, `UPDATE`), but scanning single columns for aggregation requires loading unnecessary row data from disk into memory.
* **OLAP (DuckDB, ClickHouse, Snowflake)**: Stores data organized by column. If a query runs `SUM(mrr) WHERE event_date >= '2024-01-01'`, DuckDB only reads the `mrr` and `event_date` columns from disk, utilizing near-zero disk I/O on unreferenced fields.

### 3.2 Vectorized Execution Engine
Traditional engines process one row at a time using the Volcano iterator model (`next()` function call per row), incurring significant CPU branch misprediction overhead.
DuckDB processes **DataChunks** (fixed-size vectors of 2,048 values) in CPU cache (L1/L2), allowing compilers to utilize SIMD (Single Instruction, Multiple Data) processor instructions for fast aggregation and filtering.

### 3.3 Zero-Copy Ingestion with Apache Arrow & Parquet
DuckDB can execute queries directly on raw Parquet files without ingesting or copying them into an internal database file:
```sql
SELECT customer_id, SUM(mrr) 
FROM read_parquet('data/raw/subscription_events.parquet')
GROUP BY customer_id;