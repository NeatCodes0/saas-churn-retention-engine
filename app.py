"""
SaaS Churn & Cohort Retention Intelligence Engine.
Executive Command Center: In-Memory DuckDB OLAP + Out-of-Time XGBoost Inference.
"""

from pathlib import Path
import duckdb
import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# Command Center Theme & Global Stylesheet
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="RETENTION // OPS ENGINE",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --bg-primary: #090d16;
        --bg-surface: #0f172a;
        --bg-panel: #131c31;
        --border-subtle: #1e293b;
        --border-focus: #334155;
        --text-primary: #f8fafc;
        --text-secondary: #94a3b8;
        --text-muted: #64748b;
        --accent-cyan: #06b6d4;
        --accent-emerald: #10b981;
        --accent-amber: #f59e0b;
        --accent-rose: #f43f5e;
    }

    .stApp {
        background-color: var(--bg-primary);
        color: var(--text-primary);
        font-family: 'Inter', -apple-system, sans-serif;
    }

    /* Command Center Top Navigation Bar */
    .top-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px 20px;
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 8px;
        margin-bottom: 20px;
    }
    .brand-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.15rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .tag-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.68rem;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
        background: rgba(6, 182, 212, 0.12);
        color: var(--accent-cyan);
        border: 1px solid rgba(6, 182, 212, 0.3);
    }
    .status-live {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        color: var(--accent-emerald);
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .live-dot {
        width: 7px;
        height: 7px;
        background: var(--accent-emerald);
        border-radius: 50%;
        box-shadow: 0 0 8px var(--accent-emerald);
    }

    /* Metric Cards */
    .metric-panel {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 8px;
        padding: 16px 20px;
        height: 100%;
    }
    .metric-hdr {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 500;
        text-transform: uppercase;
        color: var(--text-muted);
        letter-spacing: 0.08em;
        margin-bottom: 6px;
    }
    .metric-num {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.8rem;
        font-weight: 700;
        color: var(--text-primary);
        letter-spacing: -0.03em;
    }
    .metric-delta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        margin-top: 4px;
    }

    /* Custom Container Blocks */
    .panel-block {
        background: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 16px;
    }
    .panel-header {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        font-weight: 600;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Clean Streamlit adjustments */
    header, footer { visibility: hidden !important; }
    div[data-testid="stToolbar"] { visibility: hidden !important; }
    .stSelectbox label, .stSlider label { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--text-secondary); }
    </style>
    """,
    unsafe_allow_html=True,
)

DB_PATH = "data/processed/analytics.duckdb"
MODEL_PATH = "models/churn_model.joblib"


# -----------------------------------------------------------------------------
# Data Retrieval & Model Artifact Pipeline
# -----------------------------------------------------------------------------
@st.cache_resource
def get_engine():
    db_file = Path(DB_PATH)
    if not db_file.exists():
        db_file.parent.mkdir(parents=True, exist_ok=True)
        from src.data.generate_events import generate_all_events
        generate_all_events()
    
    return duckdb.connect(DB_PATH, read_only=True)


@st.cache_resource
def get_model():
    p = Path(MODEL_PATH)
    return joblib.load(p) if p.exists() else None


@st.cache_data
def get_waterfall_data():
    con = get_engine()
    with open("src/queries/mrr_waterfall.sql", "r") as f:
        df = con.execute(f.read()).df()
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data
def get_cohort_matrix():
    con = get_engine()
    with open("src/queries/cohort_retention.sql", "r") as f:
        df = con.execute(f.read()).df()
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data
def get_live_scoring_table():
    con = get_engine()
    query = """
    WITH summary AS (
        SELECT 
            customer_id,
            MIN(event_date) AS first_date,
            MAX(event_date) AS last_date,
            MAX(tier) AS latest_tier,
            ROUND(AVG(mrr), 2) AS avg_mrr,
            ROUND(MAX(mrr), 2) AS max_mrr,
            ROUND(SUM(mrr), 2) AS lifetime_mrr,
            COALESCE(ROUND(STDDEV(mrr), 2), 0.0) AS mrr_stddev,
            COUNT(*) AS total_event_count,
            COUNT(CASE WHEN event_type = 'upgrade' THEN 1 END) AS total_upgrades,
            COUNT(CASE WHEN event_type = 'downgrade' THEN 1 END) AS total_downgrades
        FROM subscription_events
        GROUP BY customer_id
    ),
    state AS (
        SELECT s.customer_id, s.event_type, s.mrr AS current_mrr
        FROM subscription_events s
        INNER JOIN summary a ON s.customer_id = a.customer_id AND s.event_date = a.last_date
    )
    SELECT 
        a.customer_id,
        a.latest_tier,
        ROUND((EPOCH(CURRENT_DATE) - EPOCH(a.first_date)) / (86400 * 30.4375), 1) AS tenure_months,
        a.avg_mrr,
        a.max_mrr,
        a.lifetime_mrr,
        a.mrr_stddev,
        a.total_event_count,
        a.total_upgrades,
        a.total_downgrades,
        c.current_mrr
    FROM summary a
    JOIN state c ON a.customer_id = c.customer_id
    WHERE c.event_type != 'churn'
    """
    return con.execute(query).df()


# -----------------------------------------------------------------------------
# Compute & Inference Execution
# -----------------------------------------------------------------------------
df_waterfall = get_waterfall_data()
df_cohort = get_cohort_matrix()
df_active = get_live_scoring_table()
model_bundle = get_model()

if model_bundle:
    feats = model_bundle["feature_cols"]
    pipe = model_bundle["pipeline"]
    probs = pipe.predict_proba(df_active[feats])[:, 1]
    df_active["churn_prob"] = probs
    df_active["expected_loss"] = df_active["churn_prob"] * df_active["current_mrr"]
else:
    df_active["churn_prob"] = 0.0
    df_active["expected_loss"] = 0.0

# -----------------------------------------------------------------------------
# Top Navigation Bar
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="top-nav">
        <div class="brand-title">
            ⬡ RETENTION_ENGINE // OPS COMMAND
            <span class="tag-badge">OLAP: DUCKDB</span>
            <span class="tag-badge">INFERENCE: XGBOOST</span>
            <span class="tag-badge">AUDIT: 34.6K EVENTS</span>
        </div>
        <div class="status-live">
            <div class="live-dot"></div> TELEMETRY STREAM ACTIVE
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# High-Density Metric Grid
# -----------------------------------------------------------------------------
latest = df_waterfall.iloc[-1]
prev = df_waterfall.iloc[-2] if len(df_waterfall) > 1 else latest
mrr_delta = latest["ending_mrr"] - prev["ending_mrr"]
net_growth_pct = (mrr_delta / prev["ending_mrr"]) * 100 if prev["ending_mrr"] > 0 else 0

high_risk_subset = df_active[df_active["churn_prob"] >= 0.40]
total_exposure = high_risk_subset["expected_loss"].sum()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(
        f"""
        <div class="metric-panel">
            <div class="metric-hdr">ARR Run-Rate</div>
            <div class="metric-num">${(latest['ending_mrr'] * 12):,.0f}</div>
            <div class="metric-delta" style="color: {'#10b981' if mrr_delta >= 0 else '#f43f5e'};">
                {'+' if mrr_delta >= 0 else ''}{net_growth_pct:.1f}% MOM VELOCITY
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f"""
        <div class="metric-panel">
            <div class="metric-hdr">Ending GAAP MRR</div>
            <div class="metric-num">${latest['ending_mrr']:,.0f}</div>
            <div class="metric-delta" style="color: #94a3b8;">
                NET NEW: ${latest['net_new_mrr']:+,.0f}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        f"""
        <div class="metric-panel">
            <div class="metric-hdr">Expansion vs Gross Churn</div>
            <div class="metric-num">${latest['total_expansion_mrr']:,.0f} <span style="color: #64748b; font-size:1.1rem;">/</span> <span style="color:#f43f5e;">${latest['total_churned_mrr']:,.0f}</span></div>
            <div class="metric-delta" style="color: {'#10b981' if latest['total_expansion_mrr'] > latest['total_churned_mrr'] else '#f43f5e'};">
                {'+' if latest['total_expansion_mrr'] >= latest['total_churned_mrr'] else '-'}${abs(latest['total_expansion_mrr'] - latest['total_churned_mrr']):,.0f} SPREAD
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        f"""
        <div class="metric-panel">
            <div class="metric-hdr">At-Risk Capital Exposure</div>
            <div class="metric-num" style="color: #f43f5e;">${total_exposure:,.0f}</div>
            <div class="metric-delta" style="color: #94a3b8;">
                {len(high_risk_subset)} ACCOUNTS &ge; 40% PROB
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Row 2: Bi-Directional Financial Engine & Longitudinal Retention
# -----------------------------------------------------------------------------
col_left, col_right = st.columns([0.52, 0.48], gap="medium")

with col_left:
    st.markdown(
        """
        <div class="panel-header">
            <span>📊 GAAP MRR WATERFALL DYNAMICS</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    fig_waterfall = go.Figure()
    fig_waterfall.add_trace(go.Bar(
        x=df_waterfall["activity_month"], y=df_waterfall["total_new_mrr"],
        name="New Acquisition", marker_color="#10b981", marker_line_width=0
    ))
    fig_waterfall.add_trace(go.Bar(
        x=df_waterfall["activity_month"], y=df_waterfall["total_expansion_mrr"],
        name="Expansion", marker_color="#06b6d4", marker_line_width=0
    ))
    fig_waterfall.add_trace(go.Bar(
        x=df_waterfall["activity_month"], y=-df_waterfall["total_contraction_mrr"],
        name="Contraction", marker_color="#f59e0b", marker_line_width=0
    ))
    fig_waterfall.add_trace(go.Bar(
        x=df_waterfall["activity_month"], y=-df_waterfall["total_churned_mrr"],
        name="Gross Churn", marker_color="#f43f5e", marker_line_width=0
    ))
    fig_waterfall.add_trace(go.Scatter(
        x=df_waterfall["activity_month"], y=df_waterfall["ending_mrr"],
        name="Ending MRR", mode="lines",
        line=dict(color="#f8fafc", width=2.5, dash="solid")
    ))

    fig_waterfall.update_layout(
        barmode="relative",
        template="plotly_dark",
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        margin=dict(l=10, r=10, t=10, b=10),
        height=330,
        font=dict(family="JetBrains Mono", size=10, color="#94a3b8"),
        xaxis=dict(showgrid=False, showline=True, linecolor="#1e293b"),
        yaxis=dict(showgrid=True, gridcolor="#1e293b", title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_waterfall, width="stretch")

with col_right:
    matrix_opt = st.segmented_control(
        "Matrix Dimension",
        options=["User Logo Retention (%)", "Net Revenue Retention / NRR (%)"],
        default="User Logo Retention (%)",
        label_visibility="collapsed",
    )
    metric_key = "user_retention_pct" if "Logo" in matrix_opt else "nrr_pct"
    pivot_df = df_cohort.pivot(index="cohort_month", columns="tenure_month", values=metric_key)

    st.markdown(
        f"""
        <div class="panel-header">
            <span>📐 LONGITUDINAL COHORT TRIANGLE // {matrix_opt.upper()}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    fig_matrix = px.imshow(
        pivot_df,
        labels=dict(x="Tenure (Mo)", y="Cohort", color="%"),
        x=pivot_df.columns,
        y=pivot_df.index,
        color_continuous_scale="cividis" if "Logo" in matrix_opt else "spectral",
        text_auto=".1f",
        aspect="auto",
    )
    fig_matrix.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f172a",
        plot_bgcolor="#0f172a",
        margin=dict(l=10, r=10, t=10, b=10),
        height=330,
        font=dict(family="JetBrains Mono", size=9, color="#94a3b8"),
        xaxis=dict(showgrid=False, showline=True, linecolor="#1e293b"),
        yaxis=dict(showgrid=False),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig_matrix, width="stretch")

st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Row 3: Operational Decision Engine & CS Interventions
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="panel-header">
        <span>🎯 TARGETED CUSTOMER SUCCESS INTERVENTION QUEUE (ORDERED BY RISK EXPOSURE)</span>
    </div>
    """,
    unsafe_allow_html=True,
)

cs_col_queue, cs_col_desk = st.columns([0.65, 0.35], gap="medium")

with cs_col_queue:
    # Parametric Sliders
    f_c1, f_c2 = st.columns(2)
    threshold = f_c1.slider("Inference Risk Gate:", 0.05, 0.80, 0.25, 0.05)
    tier_pick = f_c2.multiselect("Active Tiers:", ["Starter", "Pro", "Enterprise"], default=["Pro", "Enterprise"])

    scoped = df_active[
        (df_active["churn_prob"] >= threshold) &
        (df_active["latest_tier"].isin(tier_pick))
    ].sort_values(by="expected_loss", ascending=False).copy()

    # Prescriptive Intervention Rules Engine
    def assign_playbook(row):
        if row["churn_prob"] >= 0.55 and row["current_mrr"] >= 200:
            return "EXECUTIVE SPONSOR RESCUE"
        elif row["total_downgrades"] > 0:
            return "VALUE RE-ALIGNMENT CADENCE"
        elif row["tenure_months"] <= 3:
            return "ONBOARDING ACTIVATION AUDIT"
        else:
            return "DISCOUNTED CONTRACT LOCK"

    scoped["playbook"] = scoped.apply(assign_playbook, axis=1)

    display_df = scoped[[
        "customer_id", "latest_tier", "tenure_months", "current_mrr", 
        "churn_prob", "expected_loss", "playbook"
    ]].head(25)

    display_df.columns = ["Account ID", "Tier", "Tenure", "Current MRR", "P(Churn)", "Loss Exposure", "Prescribed Action"]

    st.dataframe(
        display_df.style.format({
            "Tenure": "{:.1f} mo",
            "Current MRR": "${:,.2f}",
            "P(Churn)": "{:.1%}",
            "Loss Exposure": "${:,.2f}",
        }),
        width="stretch",
        height=360,
    )

with cs_col_desk:
    st.markdown("<p style='font-family:JetBrains Mono; font-size:0.75rem; color:#64748b; text-transform:uppercase;'>Parametric Scenario Simulator</p>", unsafe_allow_html=True)
    
    with st.container(border=True):
        sim_tier = st.selectbox("Customer Tier", ["Starter", "Pro", "Enterprise"], index=1)
        sim_tenure = st.slider("Tenure (Months)", 1.0, 18.0, 3.5, 0.5)
        sim_mrr = st.number_input("Monthly Spend ($)", 10.0, 500.0, 99.0, 10.0)
        sim_downs = st.slider("Past Downgrades", 0, 3, 1)

        sim_input = pd.DataFrame([{
            "latest_tier": sim_tier,
            "tenure_months": sim_tenure,
            "avg_mrr": sim_mrr,
            "max_mrr": sim_mrr,
            "lifetime_mrr": sim_mrr * sim_tenure,
            "mrr_stddev": 14.2 if sim_downs > 0 else 0.0,
            "total_event_count": int(sim_tenure),
            "total_upgrades": 0,
            "total_downgrades": sim_downs,
        }])

        if model_bundle:
            pred_prob = pipe.predict_proba(sim_input[feats])[0, 1]
            pred_loss = pred_prob * sim_mrr
        else:
            pred_prob, pred_loss = 0.0, 0.0

        p_color = "#f43f5e" if pred_prob >= 0.5 else ("#f59e0b" if pred_prob >= 0.25 else "#10b981")
        
        st.markdown(
            f"""
            <div style="background:#090d16; border:1px solid #1e293b; border-radius:6px; padding:12px; margin-top:8px;">
                <div style="font-family:'JetBrains Mono'; font-size:0.7rem; color:#64748b;">INFERRED CHURN RISK</div>
                <div style="font-family:'JetBrains Mono'; font-size:1.6rem; font-weight:700; color:{p_color};">
                    {pred_prob:.1%}
                </div>
                <div style="font-family:'JetBrains Mono'; font-size:0.75rem; color:#94a3b8; margin-top:2px;">
                    PROJECTED MONTHLY LOSS: <b style="color:#f8fafc;">${pred_loss:,.2f}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )