

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os
from datetime import datetime, timedelta, date

# ==========================================================
# CONFIG — Databricks connection
# Set these as Databricks Apps environment variables
# ==========================================================
# Unity Catalog coordinates — set these as Databricks Apps env vars
DBX_CATALOG = os.getenv("NEXOBI_CATALOG", "workspace")
DBX_SCHEMA  = os.getenv("NEXOBI_SCHEMA",  "gold")
DBX_TABLE   = os.getenv("NEXOBI_TABLE",   "acquisition")

# Databricks SQL Warehouse connection
DATABRICKS_HOST      = os.getenv("DATABRICKS_HOST",      "dbc-51730115-505d.cloud.databricks.com")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/b3342784cd85850e")

# Databricks Genie — conversational analytics against gold layer tables
# Set NEXOBI_GENIE_SPACE_ID in the client's Databricks Apps env vars.
# The Genie Space must be pre-configured in the client's workspace pointing
# at their gold.nexobi_unified (or equivalent) table(s).
GENIE_SPACE_ID = os.getenv("NEXOBI_GENIE_SPACE_ID", "")

# ==========================================================
# THEME TOKENS
# ==========================================================
GREEN    = "#00C06B"
GREEN_DK = "#009952"
GREEN_LT = "#E6F9F0"
TEXT     = "#E2E8F0"
MUTED    = "#94A3B8"
BORDER   = "rgba(255,255,255,.1)"
BG       = "#060D1A"
PANEL    = "rgba(255,255,255,.05)"
RED      = "#F87171"
BLUE     = "#60A5FA"
AMBER    = "#FBBF24"
PURPLE   = "#A78BFA"
SOFT     = "rgba(255,255,255,.06)"

# Industry benchmarks — digital marketing / healthcare
BENCH_ENGAGEMENT_RATE = 55.0   # % engaged sessions (Healthcare digital avg)
BENCH_CONV_RATE       = 2.5    # % lead conversion rate (leads / sessions × 100)
BENCH_NEW_USER_RATE   = 45.0   # % of total users who are new (acquisition health)

# Dashboard block registry — drives the "Your View" sidebar picker
BLOCK_REGISTRY = [
    {"id": "banner",     "icon": "▣", "label": "Health Banner & KPIs", "modes": {"both"}},
    {"id": "signals",    "icon": "◆", "label": "Top Signals",           "modes": {"both"}},
    {"id": "forecasts",  "icon": "↗", "label": "30-Day Forecasts",      "modes": {"both"}},
    {"id": "journey",    "icon": "▸", "label": "Patient Journey",       "modes": {"marketing"}},
    {"id": "treatments", "icon": "✦", "label": "Top Treatments",        "modes": {"practice"}},
]

st.set_page_config(
    page_title="NexoBI · Attribution Intelligence",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================================
# UTIL
# ==========================================================
def safe_div(a, b) -> float:
    try:
        a = float(a or 0)
        b = float(b or 0)
        return a / b if b != 0 else 0.0
    except Exception:
        return 0.0

def fmt(val) -> str:
    try:
        v = float(val or 0)
        if abs(v) >= 1_000_000: return f"{v/1_000_000:.1f}M"
        if abs(v) >= 1_000: return f"{v/1_000:.1f}K"
        return f"{v:,.0f}"
    except Exception:
        return "0"

def money(val) -> str:
    try:
        return f"${float(val or 0):,.0f}"
    except Exception:
        return "$0"

def pct(val) -> str:
    try:
        return f"{float(val or 0):.1f}%"
    except Exception:
        return "0.0%"

def delta_html(val_pct: float, has_prev: bool = True) -> str:
    """Delta label for KPI cards.
    If previous-period data is missing, show n/a instead of 'flat' to avoid misleading demos.
    """
    if not has_prev:
        return f'<span style="color:{MUTED};font-size:.8rem;">— n/a</span>'
    try:
        v = float(val_pct or 0)
        if v > 0:
            return f'<span style="color:{GREEN_DK};font-weight:800;font-size:.8rem;">▲ +{v:.1f}% vs prior</span>'
        if v < 0:
            return f'<span style="color:{RED};font-weight:800;font-size:.8rem;">▼ {v:.1f}% vs prior</span>'
        return f'<span style="color:{MUTED};font-size:.8rem;">— flat</span>'
    except Exception:
        return f'<span style="color:{MUTED};font-size:.8rem;">—</span>'


def df_height(n_rows: int, *, row_h: int = 36, header_h: int = 38, min_h: int = 180, max_h: int = 520) -> int:
    """Compute a good Streamlit dataframe height to avoid empty black grid space."""
    try:
        n = int(n_rows)
    except Exception:
        n = 0
    n = max(1, n)
    h = header_h + row_h * n
    h = max(min_h, min(max_h, h))
    return h


# ==========================================================
# DATA LOADING
# ==========================================================
def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Delta table output to a consistent internal schema."""
    df.columns = [c.strip() for c in df.columns]

    if "date" not in df.columns:
        raise ValueError("Data missing 'date' column.")

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"]).copy()

    # Ensure all expected numeric columns exist (fill with 0 if absent)
    num_cols = [
        "total_cost", "total_revenue", "sessions", "conversions",
        "booked", "attended", "total_users", "new_users", "clicks",
        "impressions", "leads", "roi", "roas", "conversion_rate",
        "pageviews", "signups", "engagement_rate_pct", "avg_session_secs",
        "revenue_per_user",
    ]
    for c in num_cols:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Ensure string columns exist
    for c in ["data_source", "channel_group", "campaign", "source_medium", "treatment"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).fillna("")

    # Derive conversion_rate from leads/sessions when not already present
    if (df["conversion_rate"] == 0).all():
        df["conversion_rate"] = np.where(
            df["sessions"] > 0, (df["leads"] / df["sessions"]) * 100.0, 0.0
        )

    return df




@st.cache_data(ttl=3600)
def load_data_databricks(catalog: str, schema: str, table: str) -> pd.DataFrame:
    """
    Load the acquisition gold table, aliasing columns to NexoBI's internal schema.
    Tries SparkSession first (Databricks Apps), falls back to SQL connector.
    """
    sql = f"""
    SELECT
        date,
        channel_group,
        traffic_source                              AS data_source,
        COALESCE(traffic_campaign, 'unknown')       AS campaign,
        COALESCE(traffic_medium, '')                AS source_medium,
        COALESCE(CAST(sessions          AS BIGINT), 0)  AS sessions,
        COALESCE(CAST(users             AS BIGINT), 0)  AS total_users,
        COALESCE(CAST(new_users         AS BIGINT), 0)  AS new_users,
        COALESCE(CAST(pageviews         AS BIGINT), 0)  AS pageviews,
        COALESCE(CAST(leads             AS BIGINT), 0)  AS leads,
        COALESCE(CAST(signups           AS BIGINT), 0)  AS signups,
        COALESCE(CAST(purchases         AS BIGINT), 0)  AS booked,
        COALESCE(CAST(revenue_usd       AS DOUBLE),  0) AS total_revenue,
        COALESCE(CAST(revenue_per_user  AS DOUBLE),  0) AS revenue_per_user,
        COALESCE(CAST(avg_session_secs  AS DOUBLE),  0) AS avg_session_secs,
        COALESCE(CAST(engagement_rate_pct AS DOUBLE),0) AS engagement_rate_pct,
        0.0  AS total_cost,
        0    AS attended,
        0.0  AS total_cost_placeholder
    FROM `{catalog}`.`{schema}`.`{table}`
    """
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
        df = spark.sql(sql).toPandas()
    except Exception:
        from databricks import sql as _dbsql
        token = os.environ.get("DATABRICKS_TOKEN", "")
        with _dbsql.connect(
            server_hostname=DATABRICKS_HOST,
            http_path=DATABRICKS_HTTP_PATH,
            access_token=token
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                df = cur.fetchall_arrow().to_pandas()

    return _normalize_df(df)


# Handle query-param navigation from AI Agent fixed "← Dashboard" button
if st.query_params.get("_nav") == "dash":
    st.query_params.clear()
    st.session_state["nav"] = "Dashboard"

# ── Load from Databricks ────────────────────────────────────────
_ACTIVE_MODE = "databricks"
_DBX_MODE    = True
_FALLBACK_WARN = None

try:
    DATA = load_data_databricks(DBX_CATALOG, DBX_SCHEMA, DBX_TABLE)
except Exception as _dbx_err:
    st.error(
        f"⚠️ Could not connect to Databricks.\n\n"
        f"**Error:** `{_dbx_err}`\n\n"
        f"Check that `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, and `DATABRICKS_TOKEN` "
        f"are set correctly in your Databricks Apps environment variables."
    )
    st.stop()

MIN_DATE = DATA["date"].min()
MAX_DATE = DATA["date"].max()

# ==========================================================
# PLOTLY HELPERS
# ==========================================================
def base_layout(title: str = "", height: int = 260):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color="#CBD5E1", size=12),
        height=height,
        margin=dict(l=8, r=8, t=44 if title else 16, b=8),
        title=dict(text=f"<b>{title}</b>", font=dict(size=13, color="#E2E8F0"), x=0, xanchor="left") if title else None,
        xaxis=dict(showgrid=False, linecolor="rgba(255,255,255,.1)", tickcolor="rgba(255,255,255,.1)", tickfont=dict(color="#64748B", size=11)),
        yaxis=dict(gridcolor="rgba(255,255,255,.06)", gridwidth=1, linecolor="rgba(255,255,255,.1)", tickcolor="rgba(255,255,255,.1)", tickfont=dict(color="#64748B", size=11), zerolinecolor="rgba(255,255,255,.1)"),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(255,255,255,.1)", borderwidth=1, font=dict(color="#94A3B8", size=11)),
        hovermode="x unified",
    )

def plot_line(df: pd.DataFrame, x: str, y: str, title: str, height: int = 260, color: str = GREEN):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x], y=df[y], mode="lines",
        line=dict(color=color, width=2.5),
        fill="tozeroy",
        fillcolor="rgba(0,192,107,0.08)" if color == GREEN else "rgba(59,130,246,0.08)",
        hovertemplate="<b>%{y:,.0f}</b><extra></extra>",
    ))
    fig.update_layout(**base_layout(title, height))
    return fig

def plot_bar_multi(df: pd.DataFrame, x: str, y: str, title: str, height: int = 260):
    palette = [GREEN, BLUE, AMBER, PURPLE, "#EC4899", "#14B8A6", "#F97316"]
    fig = go.Figure()
    for i, (_, row) in enumerate(df.iterrows()):
        fig.add_trace(go.Bar(
            x=[str(row[x])], y=[row[y]],
            name=str(row[x]),
            marker_color=palette[i % len(palette)],
            marker_line_width=0,
            showlegend=False,
            hovertemplate=f"{row[x]}<br><b>%{{y:,.2f}}</b><extra></extra>",
        ))
    fig.update_layout(**base_layout(title, height), barmode="group")
    return fig

# ==========================================================
# CSS (LIGHT TABLES + CONDENSED SPACING + AI LAYOUT)
# ==========================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800;900&family=DM+Sans:wght@400;500;600&display=swap');
:root{
  --nexo-green:#00C06B;--nexo-green-dk:#009952;--nexo-green-lt:rgba(0,192,107,.12);
  --nexo-text:#E2E8F0;--nexo-muted:#94A3B8;--nexo-border:rgba(255,255,255,.1);
  --nexo-bg:#060D1A;--nexo-panel:rgba(255,255,255,.05);--nexo-red:#F87171;
  --nexo-blue:#60A5FA;--nexo-amber:#FBBF24;--nexo-ink:#E2E8F0;--nexo-soft:rgba(255,255,255,.06);
}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;color:#E2E8F0!important;}
.stApp{background:#060D1A!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{max-width:1480px;padding:.75rem 1.25rem 2.2rem;}

/* ── Sidebar — dark glass ─────────────────────────────── */
[data-testid="stSidebar"]{background:rgba(6,13,26,.97)!important;border-right:1px solid rgba(255,255,255,.07)!important;}
[data-testid="stSidebar"] *{color:#94A3B8!important;}
[data-testid="stSidebar"] label{font-size:.7rem!important;font-weight:500!important;color:#64748B!important;text-transform:none!important;letter-spacing:0!important;}

/* Inputs / selects */
[data-testid="stSidebar"] [data-baseweb="select"]>div{background:rgba(255,255,255,.06)!important;border:1px solid rgba(255,255,255,.1)!important;border-radius:8px!important;font-size:.8rem!important;box-shadow:none!important;color:#CBD5E1!important;}
[data-testid="stSidebar"] [data-baseweb="base-input"]{background:rgba(255,255,255,.06)!important;border:1px solid rgba(255,255,255,.1)!important;border-radius:8px!important;box-shadow:none!important;}
[data-testid="stSidebar"] [data-baseweb="base-input"]:focus-within{border-color:#00C06B!important;box-shadow:0 0 0 2px rgba(0,192,107,.15)!important;}
[data-testid="stSidebar"] [data-baseweb="input"]{background:rgba(255,255,255,.06)!important;border:1px solid rgba(255,255,255,.1)!important;border-radius:8px!important;box-shadow:none!important;}
[data-testid="stSidebar"] input{background:transparent!important;border:none!important;box-shadow:none!important;font-size:.8rem!important;color:#E2E8F0!important;}
[data-testid="stSidebar"] div[data-testid="stDateInput"] input{font-size:.8rem!important;}
[data-testid="stSidebar"] span[data-baseweb="tag"]{background:rgba(0,192,107,.15)!important;border:1px solid rgba(0,192,107,.3)!important;color:#00C06B!important;font-size:.72rem!important;}

/* Nav radio */
[data-testid="stSidebar"] .stRadio>div{gap:.15rem!important;flex-direction:column!important;}
[data-testid="stSidebar"] .stRadio label{background:transparent!important;border:none!important;border-radius:8px!important;padding:6px 10px!important;font-size:.83rem!important;font-weight:500!important;color:#64748B!important;text-transform:none!important;letter-spacing:0!important;}
[data-testid="stSidebar"] .stRadio label:has(input:checked){background:rgba(0,192,107,.12)!important;color:#00C06B!important;font-weight:600!important;}
[data-testid="stSidebar"] .stRadio label:hover{background:rgba(255,255,255,.05)!important;color:#CBD5E1!important;}

/* Checkboxes */
[data-testid="stSidebar"] .stCheckbox label{font-size:.78rem!important;font-weight:400!important;color:#64748B!important;}
[data-testid="stSidebar"] .stCheckbox label:has(input:checked){color:#CBD5E1!important;font-weight:500!important;}

/* ── Header ───────────────────────────────────────────── */
.nexo-header{display:flex;align-items:center;justify-content:space-between;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.13);border-radius:16px;padding:12px 18px;margin-bottom:.9rem;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);}
.nexo-brand-name{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.15rem;font-weight:900;color:#F1F5F9;}
.nexo-brand-sub{font-size:.8rem;color:#64748B;}

/* ── Section titles ───────────────────────────────────── */
.section-title{font-family:'Plus Jakarta Sans',sans-serif;font-size:.78rem;font-weight:900;color:#00C06B;text-transform:uppercase;letter-spacing:.12em;margin:1.4rem 0 .55rem;display:flex;align-items:center;gap:8px;}
.section-title::before{content:'';display:block;width:3px;height:16px;background:#00C06B;border-radius:4px;}

/* ── Cards — frosted glass ────────────────────────────── */
.metric-card{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:14px 16px;position:relative;overflow:hidden;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#00C06B,#009952);}
.metric-label{font-size:.68rem;font-weight:800;color:#64748B;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;}
.metric-value{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.55rem;font-weight:900;color:#F1F5F9;line-height:1.1;margin-bottom:4px;}
.metric-meta{font-size:.78rem;color:#94A3B8;}

.chart-card{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:12px 16px 6px;margin-bottom:.65rem;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);}

/* ── DataFrames — dark ────────────────────────────────── */
[data-testid="stDataFrame"]{background:rgba(255,255,255,.08)!important;border:1px solid rgba(255,255,255,.12)!important;border-radius:14px!important;}
[data-testid="stDataFrame"] *{color:#CBD5E1!important;}
[data-testid="stDataFrame"] div[role="grid"]{background:transparent!important;}
[data-testid="stDataFrame"] div[role="row"]{background:transparent!important;}
[data-testid="stDataFrame"] div[role="columnheader"]{background:rgba(255,255,255,.1)!important;color:#94A3B8!important;font-weight:900!important;}
[data-testid="stDataFrame"] div[role="gridcell"]{background:transparent!important;}

/* ── Buttons ──────────────────────────────────────────── */
[data-testid="stDownloadButton"] button,[data-testid="stDownloadButton"] button *,.stDownloadButton button,.stDownloadButton button *{color:#FFFFFF!important;fill:#FFFFFF!important;}
[data-testid="stDownloadButton"] button,.stDownloadButton button{background:rgba(255,255,255,.1)!important;border:1px solid rgba(255,255,255,.15)!important;border-radius:12px!important;font-weight:700!important;}

.stButton>button{background:rgba(255,255,255,.07)!important;color:#CBD5E1!important;border:1px solid rgba(255,255,255,.12)!important;border-radius:12px!important;font-weight:600!important;padding:.6rem 1rem!important;box-shadow:none!important;transition:all .14s!important;}
.stButton>button:hover{background:rgba(255,255,255,.12)!important;border-color:rgba(255,255,255,.2)!important;color:#F1F5F9!important;}
.stButton>button:focus{outline:none!important;box-shadow:0 0 0 3px rgba(0,192,107,.2)!important;}
[data-testid="baseButton-primary"]{background:#00C06B!important;color:#fff!important;border:none!important;box-shadow:0 2px 12px rgba(0,192,107,.35)!important;}
[data-testid="baseButton-primary"]:hover{background:#009952!important;}

section[data-testid="stSidebar"] .stButton>button{background:transparent!important;color:#64748B!important;border:1px solid rgba(255,255,255,.1)!important;border-radius:8px!important;font-weight:400!important;font-size:.78rem!important;padding:.35rem .75rem!important;box-shadow:none!important;}
section[data-testid="stSidebar"] .stButton>button:hover{background:rgba(0,192,107,.1)!important;border-color:rgba(0,192,107,.3)!important;color:#00C06B!important;}

.sb-reset-wrap .stButton>button{background:transparent!important;color:#475569!important;border:none!important;font-size:.72rem!important;font-weight:400!important;padding:.2rem .5rem!important;text-decoration:underline!important;text-underline-offset:3px!important;box-shadow:none!important;}
.sb-reset-wrap .stButton>button:hover{color:#94A3B8!important;background:transparent!important;}

/* ── Expander — frosted ───────────────────────────────── */
[data-testid="stExpander"]{background:rgba(255,255,255,.08)!important;border:1px solid rgba(255,255,255,.12)!important;border-radius:14px!important;box-shadow:none!important;overflow:hidden!important;backdrop-filter:blur(12px)!important;}
[data-testid="stExpander"] summary{background:transparent!important;font-weight:600!important;color:#CBD5E1!important;}
[data-testid="stExpander"]>div,[data-testid="stExpander"] div[role="region"]{background:transparent!important;}

/* ── Command center ───────────────────────────────────── */
.cmd-health{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.14);border-radius:16px;padding:24px 28px;display:flex;align-items:center;gap:28px;margin-bottom:.75rem;flex-wrap:wrap;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);}
.cmd-score-ring{display:flex;flex-direction:column;align-items:center;justify-content:center;width:82px;height:82px;border-radius:50%;border:4px solid #00C06B;flex-shrink:0;}
.cmd-score-num{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.7rem;font-weight:900;line-height:1;}
.cmd-score-den{font-size:.65rem;color:#64748B;font-weight:500;}
.cmd-health-stat{flex:1;min-width:110px;border-left:1px solid rgba(255,255,255,.08);padding-left:22px;}
.cmd-health-label{font-size:.72rem;font-weight:700;color:#CBD5E1;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;}
.cmd-health-val{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.18rem;font-weight:800;color:#F1F5F9;}
.cmd-health-sub{font-size:.73rem;color:#94A3B8;margin-top:3px;}

/* ── Tabs ─────────────────────────────────────────────── */
.stTabs [data-baseweb="tab"]{color:#64748B!important;font-weight:500!important;font-size:.88rem!important;}
.stTabs [data-baseweb="tab"][aria-selected="true"]{color:#00C06B!important;font-weight:700!important;}
.stTabs [data-baseweb="tab-highlight"]{background:#00C06B!important;}
.stTabs [data-baseweb="tab-border"]{background:rgba(255,255,255,.1)!important;}

/* ── Sidebar layout ───────────────────────────────────── */
section[data-testid="stSidebar"] .block-container{padding:.5rem .85rem 1rem!important;}
section[data-testid="stSidebar"]>div:first-child{padding-top:0!important;}
section[data-testid="stSidebar"] .element-container{margin:0 0 .18rem 0!important;}
section[data-testid="stSidebar"] label{margin-bottom:.1rem!important;}

/* ── Refresh button ───────────────────────────────────── */
.refresh-wrap .stButton>button{background:transparent!important;border:1px solid rgba(0,192,107,.4)!important;border-radius:8px!important;color:#00C06B!important;font-size:.75rem!important;font-weight:500!important;padding:3px 10px!important;min-height:0!important;height:26px!important;width:auto!important;}
.refresh-wrap .stButton>button:hover{background:rgba(0,192,107,.1)!important;}

/* ── Dashboard aurora background ─────────────────────── */
.dash-orbs{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;}
.dash-orbs .do1{position:absolute;width:600px;height:600px;background:rgba(0,192,107,.09);border-radius:50%;filter:blur(110px);top:-180px;right:-100px;animation:floatA 11s ease-in-out infinite;}
.dash-orbs .do2{position:absolute;width:480px;height:480px;background:rgba(0,153,82,.06);border-radius:50%;filter:blur(100px);bottom:-120px;left:-80px;animation:floatB 15s ease-in-out infinite;}
.dash-orbs .do3{position:absolute;width:320px;height:320px;background:rgba(0,192,107,.05);border-radius:50%;filter:blur(80px);top:45%;left:30%;animation:floatA 19s ease-in-out infinite reverse;}

/* === AI AGENT — ultra-modern redesign === */

/* Keyframes */
@keyframes floatA{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(28px,-22px) scale(1.08)}}
@keyframes floatB{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-22px,20px) scale(.94)}}
@keyframes pulseRing{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.55;transform:scale(1.5)}}
@keyframes slideUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}

/* ── Hero — transparent, sits on full-page aurora ────────── */
.ai-hero-wrap{
  position:relative;text-align:center;
  padding:3.5rem 1rem 2.5rem;
  background:transparent;
}
/* No card bg — aurora bleeds from page-level fixed orbs */
.ai-orb,.ai-noise{display:none!important;}
/* Status pill — dark glass */
.ai-status-pill{
  display:inline-flex;align-items:center;gap:7px;
  background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  border-radius:999px;padding:5px 16px;
  font-size:.7rem;font-weight:700;color:rgba(255,255,255,.82);
  letter-spacing:.07em;text-transform:uppercase;margin-bottom:1.5rem;
}
.ai-pulse{width:7px;height:7px;background:#00C06B;border-radius:50%;display:inline-block;animation:pulseRing 1.8s ease-in-out infinite;}
/* White headline */
.ai-catch{font-family:'Plus Jakarta Sans',sans-serif;font-size:3.4rem;font-weight:900;color:#FFFFFF;line-height:1.08;margin-bottom:.7rem;}
/* Green → sky-blue gradient tagline */
.ai-catch-hi{background:linear-gradient(120deg,#00C06B 0%,#38BDF8 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.ai-catch-sub{font-size:.85rem;color:rgba(255,255,255,.52);font-weight:400;max-width:440px;margin:0 auto 2rem;}
/* ── Preset chips — frosted pill buttons ─────────────────── */
[data-testid="stMarkdownContainer"]:has(#ai-cards-marker)+[data-testid="stHorizontalBlock"] .stButton>button{
  background:rgba(255,255,255,.62)!important;
  backdrop-filter:blur(12px)!important;-webkit-backdrop-filter:blur(12px)!important;
  border:1px solid rgba(255,255,255,.85)!important;
  border-radius:999px!important;padding:.5rem 1.4rem!important;
  min-height:0!important;height:auto!important;text-align:center!important;
  font-size:.83rem!important;font-weight:600!important;color:#334155!important;
  box-shadow:0 2px 12px rgba(0,0,0,.08)!important;
  transition:all .16s ease!important;line-height:1.4!important;white-space:nowrap!important;width:100%!important;
}
[data-testid="stMarkdownContainer"]:has(#ai-cards-marker)+[data-testid="stHorizontalBlock"] .stButton>button:hover{
  background:rgba(255,255,255,.92)!important;
  box-shadow:0 4px 18px rgba(0,0,0,.13)!important;
  transform:translateY(-2px)!important;color:#0F172A!important;
}
/* remove per-chip colour overrides — all chips same style */

/* ── Follow-up suggestion chips ──────────────────────────── */
[data-testid="stMarkdownContainer"]:has(.ai-followup-marker)+[data-testid="stHorizontalBlock"] .stButton>button{
  background:rgba(0,192,107,.08)!important;
  border:1px solid rgba(0,192,107,.22)!important;
  border-radius:999px!important;padding:.18rem .7rem!important;
  min-height:0!important;height:auto!important;
  font-size:.68rem!important;font-weight:500!important;
  color:rgba(255,255,255,.65)!important;
  box-shadow:none!important;transition:all .15s!important;
  white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;width:100%!important;
}
[data-testid="stMarkdownContainer"]:has(.ai-followup-marker)+[data-testid="stHorizontalBlock"] .stButton>button:hover{
  background:rgba(0,192,107,.18)!important;border-color:rgba(0,192,107,.5)!important;
  color:#ffffff!important;transform:translateY(-1px)!important;
}

/* ── "New chat" button ───────────────────────────────────── */
[data-testid="stColumn"]:has(#ai-newchat-marker) .stButton>button{background:transparent!important;border:1px solid #E2E8F0!important;border-radius:8px!important;color:#64748B!important;font-size:.74rem!important;font-weight:400!important;padding:.2rem .65rem!important;height:auto!important;min-height:0!important;box-shadow:none!important;}
[data-testid="stColumn"]:has(#ai-newchat-marker) .stButton>button:hover{border-color:#CBD5E1!important;color:#475569!important;background:#F8FAFC!important;}

/* ── Chat bubbles ───────────────────────────────────────── */
.ai-bubble-user{display:flex;justify-content:flex-end;margin:.8rem 0 .15rem;animation:slideUp .18s ease-out;}
.ai-bubble-user span{
  background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);
  color:#F1F5F9;border-radius:18px 18px 4px 18px;
  padding:11px 16px;font-size:.87rem;font-weight:500;max-width:72%;line-height:1.5;
  display:inline-block;box-shadow:0 4px 18px rgba(0,0,0,.18);
}
/* AI label + bubble */
.ai-msg-label{
  display:flex;align-items:center;gap:6px;
  font-size:.68rem;font-weight:700;color:#00C06B;
  letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px;margin-top:.9rem;
}
.ai-msg-label::before{
  content:'◆';font-size:.6rem;
  background:linear-gradient(135deg,#00C06B,#38BDF8);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.ai-bubble-ai{
  background:rgba(255,255,255,.97)!important;
  border:1px solid rgba(0,192,107,.18)!important;
  border-left:3px solid #00C06B!important;
  border-radius:4px 20px 20px 20px!important;
  padding:16px 20px!important;margin:0 0 .3rem!important;
  font-size:.88rem!important;color:#1E293B!important;line-height:1.7!important;
  box-shadow:0 6px 28px rgba(0,0,0,.07)!important;
  animation:slideUp .2s ease-out;
}

/* ── Input bar ──────────────────────────────────────────── */
.stTextInput [data-baseweb="base-input"],
.stTextInput [data-baseweb="input"],
div[data-baseweb="base-input"],
div[data-baseweb="input"]{
  border:1.5px solid #E2E8F0!important;border-radius:16px!important;
  background:#FFFFFF!important;box-shadow:0 2px 12px rgba(0,0,0,.05)!important;
  outline:none!important;transition:all .2s!important;
}
.stTextInput [data-baseweb="base-input"]:focus-within,
div[data-baseweb="base-input"]:focus-within{
  border-color:#00C06B!important;
  box-shadow:0 0 0 4px rgba(0,192,107,.1),0 2px 12px rgba(0,0,0,.06)!important;
  background:#FFFFFF!important;
}
.stTextInput input,.stTextInput textarea{background:transparent!important;color:#0F172A!important;border:none!important;outline:none!important;box-shadow:none!important;padding:.78rem 1rem!important;font-size:.93rem!important;}
/* Align send button */
[data-testid="stMarkdownContainer"]:has(#ai-send-row)+[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child{display:flex!important;flex-direction:column!important;justify-content:flex-end!important;}
/* Send button — glowing green */
[data-testid="baseButton-primary"]{
  height:46px!important;min-height:46px!important;font-size:.88rem!important;font-weight:700!important;
  border-radius:14px!important;letter-spacing:.02em!important;padding:0 1.1rem!important;
  background:linear-gradient(135deg,#00C06B 0%,#009952 100%)!important;
  box-shadow:0 4px 18px rgba(0,192,107,.35)!important;
  transition:all .2s!important;
}
[data-testid="baseButton-primary"]:hover{
  box-shadow:0 6px 26px rgba(0,192,107,.5)!important;
  transform:translateY(-1px)!important;
}

/* Export icon buttons — all sidebar download buttons */
[data-testid="stSidebar"] [data-testid="stDownloadButton"]>button{background:transparent!important;border:1px solid #E2E8F0!important;border-radius:8px!important;color:#64748B!important;font-size:.75rem!important;font-weight:500!important;padding:3px 10px!important;min-height:0!important;height:26px!important;line-height:1!important;width:auto!important;}
[data-testid="stSidebar"] [data-testid="stDownloadButton"]>button:hover{border-color:#00C06B!important;color:#00C06B!important;background:transparent!important;}

/* Refresh button — subtle green, compact */
.refresh-wrap .stButton>button{background:transparent!important;border:1px solid #00C06B!important;border-radius:8px!important;color:#00C06B!important;font-size:.75rem!important;font-weight:500!important;padding:3px 10px!important;min-height:0!important;height:26px!important;width:auto!important;}
.refresh-wrap .stButton>button:hover{background:#E6F9F0!important;}



</style>
""", unsafe_allow_html=True)

# ==========================================================
# HEADER
# ==========================================================
max_d = pd.to_datetime(MAX_DATE).strftime("%b %d, %Y") if MAX_DATE else "—"
st.markdown(f'''
<div class="nexo-header">
  <div style="display:flex;align-items:center;gap:12px;">
    <img src="https://images.squarespace-cdn.com/content/v1/68daa6f79c8c695a65a1d1bd/1759160060457-MMX5Q30RNSVGDEWNRL0S/nexobi_logo_transparent_background.png?format=1500w"
         width="38" style="border-radius:8px;" alt="NexoBI">
    <div>
      <div class="nexo-brand-name">NexoBI</div>
      <div class="nexo-brand-sub">Attribution Intelligence · Last data: {max_d}</div>
    </div>
  </div>
</div>
''', unsafe_allow_html=True)

# ==========================================================
# SIDEBAR + FILTERS
# ==========================================================
def list_unique(col: str):
    return sorted(DATA[col].dropna().astype(str).unique().tolist())

with st.sidebar:

    # --- Data mode indicator ---
    _dot_color = "#15803D"
    _dot_label = "Live · Databricks"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:5px;padding:2px 0 10px;">'
        f'<span style="width:5px;height:5px;border-radius:50%;background:{_dot_color};'
        f'display:inline-block;flex-shrink:0;"></span>'
        f'<span style="font-size:.63rem;color:#CBD5E1;font-weight:400;letter-spacing:.02em;">{_dot_label}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    # --- Navigation ---
    page = st.radio("", ["Dashboard", "AI Agent"], key="nav", label_visibility="collapsed")

    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    st.markdown('<div style="height:1px;background:#F1F5F9;margin:0 0 10px;"></div>', unsafe_allow_html=True)

    # --- Section label: Filters ---
    st.markdown(
        '<div style="font-size:.6rem;font-weight:700;color:#CBD5E1;letter-spacing:.1em;'
        'text-transform:uppercase;margin-bottom:6px;">Filters</div>',
        unsafe_allow_html=True
    )

    # --------------------------------------------------
    # State init
    # --------------------------------------------------
    _today        = date.today()
    _pm_end       = _today.replace(day=1) - timedelta(days=1)
    _pm_start     = _pm_end.replace(day=1)
    _default_start = max(_pm_start, pd.to_datetime(MIN_DATE).date())
    _default_end   = min(_pm_end,   pd.to_datetime(MAX_DATE).date())

    if st.session_state.pop("_reset_filters", False):
        st.session_state["f_start"]    = _default_start
        st.session_state["f_end"]      = _default_end
        st.session_state["f_sources"]  = ["All"]
        st.session_state["f_channel"]  = "All"
        st.session_state["f_campaign"] = "All"

    if "f_start"    not in st.session_state: st.session_state["f_start"]    = _default_start
    if "f_end"      not in st.session_state: st.session_state["f_end"]      = _default_end
    if "f_sources"  not in st.session_state: st.session_state["f_sources"]  = ["All"]
    if "f_channel"  not in st.session_state: st.session_state["f_channel"]  = "All"
    if "f_campaign" not in st.session_state: st.session_state["f_campaign"] = "All"
    # --- Location selector (multi-location support) ---
    _has_locations = "location" in DATA.columns and DATA["location"].nunique() > 1
    _loc_opts = (
        ["All Locations"] + sorted(DATA["location"].dropna().astype(str).unique().tolist())
        if _has_locations
        else ["All Locations", "Main · Demo", "North · Demo", "South · Demo"]
    )
    locations_selected = st.multiselect(
        "Location", options=_loc_opts, default=["All Locations"]
    )
    if not locations_selected or "All Locations" in locations_selected:
        locations_selected = []
    st.markdown('<div style="height:1px;background:rgba(255,255,255,.07);margin:8px 0 10px;"></div>', unsafe_allow_html=True)

    d1, d2 = st.columns(2)
    with d1:
        start = st.date_input("Start", value=st.session_state["f_start"], key="f_start")
    with d2:
        end   = st.date_input("End",   value=st.session_state["f_end"],   key="f_end")

    sources = ["All"] + list_unique("data_source")
    if "Practice CRM" not in sources:
        sources.append("Practice CRM")
    sources_selected = st.multiselect("Source", options=sources, default=st.session_state["f_sources"], key="f_sources")
    if "All" in sources_selected:
        sources_selected = []

    c1, c2 = st.columns(2)
    with c1:
        channel_opts = ["All"] + list_unique("channel_group")
        channel = st.selectbox("Channel", channel_opts,
            index=(channel_opts.index(st.session_state["f_channel"]) if st.session_state["f_channel"] in channel_opts else 0),
            key="f_channel")
    with c2:
        camp_opts = ["All"] + list_unique("campaign")
        campaign = st.selectbox("Campaign", camp_opts,
            index=(camp_opts.index(st.session_state["f_campaign"]) if st.session_state["f_campaign"] in camp_opts else 0),
            key="f_campaign")

    st.markdown('<div class="sb-reset-wrap">', unsafe_allow_html=True)
    if st.button("Reset filters", use_container_width=True, key="reset_filters"):
        st.session_state["_reset_filters"] = True
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if _DBX_MODE:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="refresh-wrap">', unsafe_allow_html=True)
        if st.button("↺ Refresh", key="refresh_data"):
            load_data_databricks.clear()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

def apply_filters(df: pd.DataFrame, s: date, e: date, srcs, ch: str, camp: str, locs=None) -> pd.DataFrame:
    out = df[(df["date"] >= s) & (df["date"] <= e)].copy()
    if locs and "location" in out.columns:
        out = out[out["location"].astype(str).isin([str(x) for x in locs])]
    if srcs:
        out = out[out["data_source"].astype(str).isin([str(x) for x in srcs])]
    if ch != "All":
        out = out[out["channel_group"].astype(str) == str(ch)]
    if camp != "All":
        out = out[out["campaign"].astype(str) == str(camp)]
    return out


if start > end:
    st.error("Start date must be before end date.")
    st.stop()

period_days = (end - start).days + 1
prev_start  = start - timedelta(days=period_days)
prev_end    = end - timedelta(days=period_days)

CUR = apply_filters(DATA, start, end, sources_selected, channel, campaign, locations_selected)
PREV = apply_filters(DATA, prev_start, prev_end, sources_selected, channel, campaign, locations_selected)

practice_mode = (len(sources_selected) == 1 and str(sources_selected[0]).strip() == "Practice CRM")

# Marketing visuals should NOT include Practice CRM unless explicitly selected.
include_practice_in_marketing = practice_mode or ("Practice CRM" in [str(x).strip() for x in (sources_selected or [])])

# ── Block visibility — all applicable blocks always shown ──────
visible_blocks = {
    b["id"] for b in BLOCK_REGISTRY
    if (
        "both" in b["modes"]
        or ("practice" in b["modes"] and practice_mode)
        or ("marketing" in b["modes"] and not practice_mode)
    )
}
CUR_MKT  = CUR.copy()
PREV_MKT = PREV.copy()
if not include_practice_in_marketing:
    CUR_MKT  = CUR_MKT[CUR_MKT["data_source"].astype(str) != "Practice CRM"].copy()
    PREV_MKT = PREV_MKT[PREV_MKT["data_source"].astype(str) != "Practice CRM"].copy()

# ==========================================================
# STEP 3 — DEMO GUARDRAILS
# - Practice CRM selection guidance
# - Friendly empty states (avoid blank charts)
# ==========================================================
_selected_has_crm = any(str(x).strip() == "Practice CRM" for x in (sources_selected or []))

# If CRM is selected with other sources, explain the behavior (CRM view only triggers when CRM is the ONLY source)
if _selected_has_crm and (not practice_mode):
    st.info("Practice CRM is selected along with other sources. **CRM view only appears when Practice CRM is the ONLY selected source.** To see the CRM dashboard, select only **Practice CRM** in the Data Source filter.")

# Empty-state guardrails (client-safe)
if practice_mode and CUR.empty:
    st.warning("No Practice CRM data for this selection. Try widening the date range or resetting Channel/Campaign to **All**.")
    st.stop()

if (not practice_mode) and CUR_MKT.empty:
    st.warning("No marketing data for this selection. Suggestions: choose **All** sources (or remove narrow selections), reset Channel/Campaign to **All**, and widen the date range.")
    st.stop()

# ==========================================================
# SIDEBAR — ALERTS (at least 3)
# Action-oriented flags based on selected date range
# ==========================================================
def _safe_float(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return default
        return float(x)
    except Exception:
        return default

def _sum_col(df, col):
    try:
        return _safe_float(df[col].sum() if (df is not None and len(df) and col in df.columns) else 0.0)
    except Exception:
        return 0.0

def build_sidebar_alerts(cur_df, prev_df):
    """Returns list of tuples: (sev_label, pill_cls, title, detail, action)."""
    cur_rev      = _sum_col(cur_df,  "total_revenue")
    prev_rev     = _sum_col(prev_df, "total_revenue")
    cur_leads    = _sum_col(cur_df,  "leads")
    prev_leads   = _sum_col(prev_df, "leads")
    cur_sessions = max(_sum_col(cur_df,  "sessions"), 1)
    prev_sessions= max(_sum_col(prev_df, "sessions"), 1)
    cur_new_u    = _sum_col(cur_df,  "new_users")
    prev_new_u   = _sum_col(prev_df, "new_users")

    # Engagement rate — weighted avg by sessions
    def _eng(df):
        s = max(_sum_col(df, "sessions"), 1)
        if "engagement_rate_pct" in df.columns:
            return float((df["engagement_rate_pct"] * df["sessions"]).sum() / s)
        return 0.0

    cur_eng  = _eng(cur_df)
    prev_eng = _eng(prev_df)

    cur_conv  = (cur_leads  / cur_sessions)  * 100
    prev_conv = (prev_leads / prev_sessions) * 100

    alerts = []

    # 1) Engagement rate drop (quality signal)
    if prev_eng > 0 and (cur_eng - prev_eng) / prev_eng <= -0.10:
        drop_pts = prev_eng - cur_eng
        alerts.append((
            "Quick response", "sb-pill-red",
            "Engagement dropping",
            f"Engagement rate down {drop_pts:.1f} pts vs prior period.",
            "Audit landing page load speed, content relevance, and ad-to-page message match."
        ))

    # 2) Lead conversion rate drop (sessions up, leads not following)
    if prev_conv > 0 and (cur_conv - prev_conv) / prev_conv <= -0.15:
        alerts.append((
            "Quick response", "sb-pill-amber",
            "Leads / sessions declining",
            f"Conversion rate {cur_conv:.1f}% vs {prev_conv:.1f}% prior period.",
            "Review form UX, CTA placement, and check for traffic source quality shift."
        ))

    # 3) Revenue drop
    if prev_rev > 0 and cur_rev < prev_rev:
        rev_drop = (prev_rev - cur_rev) / prev_rev * 100
        if rev_drop >= 10:
            alerts.append((
                "Quick response", "sb-pill-amber",
                "Revenue declined",
                f"Down {rev_drop:.0f}% vs prior period.",
                "Identify which channels or campaigns drove the drop and reallocate budget."
            ))

    # 4) Best channel by leads (exclude Practice CRM)
    try:
        s = cur_df[cur_df["data_source"].astype(str).str.lower() != "practice crm"]
        s = s.groupby("channel_group", as_index=False).agg(
            leads=("leads", "sum"),
            sessions=("sessions", "sum")
        )
        s = s[s["sessions"] > 0].copy()
        s["conv_rate"] = s["leads"] / s["sessions"] * 100
        if len(s):
            best = s.sort_values("leads", ascending=False).iloc[0]
            alerts.append((
                "Opportunity", "sb-pill-green",
                "Best channel to scale",
                f"{best['channel_group']} — {best['leads']:,.0f} leads ({best['conv_rate']:.1f}% conv).",
                "Increase investment in this channel and test expanded audiences or keywords."
            ))
    except Exception:
        pass

    # 5) Top campaign by revenue
    try:
        c = cur_df.groupby("campaign", as_index=False).agg(
            total_revenue=("total_revenue", "sum"),
            leads=("leads", "sum")
        )
        c = c[c["campaign"].astype(str).str.lower() != "unknown"]
        if len(c):
            topc = c.sort_values("total_revenue", ascending=False).iloc[0]
            alerts.append((
                "Opportunity", "sb-pill-green",
                "Top campaign to protect",
                f"'{topc['campaign']}' is highest-revenue in the range.",
                "Keep budget stable, refresh creatives if fatigue shows."
            ))
    except Exception:
        pass

    while len(alerts) < 3:
        alerts.append((
            "Info", "sb-pill-green",
            "Healthy performance",
            "No major anomalies detected in the selected range.",
            "Keep monitoring engagement, conversion rate, and new user growth weekly."
        ))

    return alerts[:5]



# ---- Build alerts with safe fallback ----
try:
    _alerts = build_sidebar_alerts(CUR_MKT, PREV_MKT)
except Exception:
    _alerts = [("Info", "sb-pill-green", "Healthy", "No anomalies detected.", "Keep monitoring weekly.")]

# (Alerts shown inline via render_command_center)

def df_light(df: pd.DataFrame):
    """Force a light theme for st.dataframe across Streamlit versions."""
    try:
        return df.style.set_properties(**{
            "background-color": PANEL,
            "color": TEXT,
            "border-color": BORDER,
            "font-size": "0.85rem",
        }).set_table_styles([
            {"selector": "th", "props": [("background-color", BG), ("color", MUTED), ("font-weight", "800")]},
            {"selector": "td", "props": [("background-color", PANEL), ("color", TEXT)]},
        ])
    except Exception:
        return df

# ==========================================================
# PLATFORM HEALTH SCORE
# ==========================================================
def compute_health_score(cur_df: pd.DataFrame, prev_df: pd.DataFrame) -> int:
    """0–100 health score: Engagement 30 · Lead Conversion 30 · Revenue Growth 30 · New User Rate 10."""
    try:
        rev      = float(cur_df["total_revenue"].sum() or 0)
        p_rev    = float(prev_df["total_revenue"].sum() or 0)
        sessions = max(float(cur_df["sessions"].sum() or 0), 1)
        leads    = float(cur_df["leads"].sum() or 0)
        users    = max(float(cur_df["total_users"].sum() or 0), 1)
        new_u    = float(cur_df["new_users"].sum() or 0)

        # Weighted avg engagement rate (weighted by sessions)
        if "engagement_rate_pct" in cur_df.columns and sessions > 0:
            eng_rate = float((cur_df["engagement_rate_pct"] * cur_df["sessions"]).sum() / sessions)
        else:
            eng_rate = 0.0

        conv_rate  = (leads / sessions) * 100
        new_u_rate = (new_u / users) * 100
        rev_growth = safe_div(rev - p_rev, max(abs(p_rev), 0.01)) * 100

        # weights: Engagement 30 · Lead Conversion 30 · Revenue Growth 30 · New User Rate 10
        eng_score  = min(30, max(0, (eng_rate / BENCH_ENGAGEMENT_RATE) * 30))
        conv_score = min(30, max(0, (conv_rate / BENCH_CONV_RATE) * 30))
        rev_score  = min(30, max(0, 15.0 + rev_growth * 0.78))
        new_score  = min(10, max(0, (new_u_rate / BENCH_NEW_USER_RATE) * 10))

        return min(100, int(eng_score + conv_score + rev_score + new_score))
    except Exception:
        return 72


# ==========================================================
# REVENUE FORECAST  (linear extrapolation, 30-day horizon)
# ==========================================================
def plot_forecast(df: pd.DataFrame, col: str = "total_revenue",
                  title: str = "Production Forecast — 30-Day Projection",
                  color: str = GREEN, is_money: bool = True,
                  days_ahead: int = 30):
    """Generic 30-day linear forecast. Returns (fig, projected_total) or (None, 0)."""
    try:
        daily = (df.groupby("date")[col].sum()
                   .reset_index()
                   .sort_values("date"))
        daily["date"] = pd.to_datetime(daily["date"])
        if len(daily) < 5:
            return None, 0

        x = np.array([(d - daily["date"].iloc[0]).days for d in daily["date"]])
        y = daily[col].values

        coeffs = np.polyfit(x, y, 1)

        last_x    = x[-1]
        fut_x     = np.arange(last_x + 1, last_x + days_ahead + 1)
        fut_dates = [daily["date"].iloc[-1] + timedelta(days=int(i - last_x)) for i in fut_x]
        fut_y     = np.maximum(0, np.polyval(coeffs, fut_x))

        residuals = y - np.polyval(coeffs, x)
        band      = np.std(residuals) * 1.5
        upper     = fut_y + band
        lower     = np.maximum(0, fut_y - band)

        # fill colour derived from line colour
        r, g, b_  = int(color[1:3],16), int(color[3:5],16), int(color[5:7],16)
        fill_actual   = f"rgba({r},{g},{b_},0.06)"
        fill_band     = f"rgba({r},{g},{b_},0.07)"
        hover_fmt     = "<b>$%{y:,.0f}</b>" if is_money else "<b>%{y:,.0f}</b>"

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=fut_dates + fut_dates[::-1],
            y=np.concatenate([upper, lower[::-1]]).tolist(),
            fill="toself", fillcolor=fill_band,
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip", name="band",
        ))
        fig.add_trace(go.Scatter(
            x=daily["date"], y=y,
            name="Actual", mode="lines",
            line=dict(color=color, width=2.5),
            fill="tozeroy", fillcolor=fill_actual,
            hovertemplate=hover_fmt + "<extra>Actual</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=fut_dates, y=fut_y.tolist(),
            name="Forecast", mode="lines",
            line=dict(color=BLUE, width=2, dash="dash"),
            hovertemplate=hover_fmt + "<extra>Forecast</extra>",
        ))

        fig.update_layout(**base_layout(title, 280))
        return fig, float(fut_y.sum())
    except Exception:
        return None, 0


# ==========================================================
# COMMAND CENTER — executive view
# ==========================================================
def render_command_center():
    base     = CUR_MKT if not practice_mode else CUR
    prev_b   = PREV_MKT if not practice_mode else PREV
    has_prev = len(prev_b) > 0

    rev      = float(base["total_revenue"].sum() or 0)
    leads    = max(float(base["leads"].sum() or 0), 0.01)
    sessions = max(float(base["sessions"].sum() or 0), 1)
    new_u    = float(base["new_users"].sum() or 0)
    p_rev    = float(prev_b["total_revenue"].sum() or 0)
    p_leads  = max(float(prev_b["leads"].sum() or 0), 0.01)
    p_sess   = max(float(prev_b["sessions"].sum() or 0), 1)

    # Engagement rate — weighted avg by sessions
    if "engagement_rate_pct" in base.columns and sessions > 0:
        eng_rate = float((base["engagement_rate_pct"] * base["sessions"]).sum() / sessions)
    else:
        eng_rate = 0.0

    conv_rate   = safe_div(leads, sessions) * 100
    rev_growth  = safe_div(rev - p_rev, max(abs(p_rev), 0.01)) * 100
    lead_growth = safe_div(leads - p_leads, p_leads) * 100
    sess_growth = safe_div(sessions - p_sess, p_sess) * 100

    score = compute_health_score(base, prev_b)
    sc_color = GREEN if score >= 80 else (AMBER if score >= 60 else RED)
    sc_label = "Strong" if score >= 80 else ("Moderate" if score >= 60 else "Needs Attention")

    period_label = f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    _loc_label   = " &nbsp;·&nbsp; " + " + ".join(locations_selected) if locations_selected else ""

    # ── Section title ─────────────────────────────────────
    st.markdown('<div class="section-title">Intelligence Score</div>', unsafe_allow_html=True)

    # ── Health banner (toggleable) ────────────────────────
    if "banner" in visible_blocks:
        _eng_clr  = '#009952' if eng_rate >= BENCH_ENGAGEMENT_RATE else '#D97706'
        _conv_clr = '#009952' if conv_rate >= BENCH_CONV_RATE else '#D97706'
        if practice_mode:
            # CRM view: Revenue · Sessions · Engagement Rate · New Users
            banner_stats  = f'''
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Production</div>
    <div class="cmd-health-val">{money(rev)}</div>
    <div class="cmd-health-sub">{delta_html(rev_growth, has_prev)}</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Sessions</div>
    <div class="cmd-health-val">{fmt(sessions)}</div>
    <div class="cmd-health-sub">{delta_html(sess_growth, has_prev)}</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Engagement Rate</div>
    <div class="cmd-health-val">{pct(eng_rate)}</div>
    <div class="cmd-health-sub" style="color:{_eng_clr};">{'▲ Above' if eng_rate>=BENCH_ENGAGEMENT_RATE else '▼ Below'} {BENCH_ENGAGEMENT_RATE:.0f}% avg</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">New Users</div>
    <div class="cmd-health-val">{fmt(new_u)}</div>
    <div class="cmd-health-sub">{delta_html(safe_div(new_u - _sum_col(prev_b,"new_users"), max(abs(_sum_col(prev_b,"new_users")),0.01))*100, has_prev)}</div>
  </div>'''
        else:
            # Marketing view: Revenue · Sessions · Engagement Rate · Lead Conv. Rate
            banner_stats = f'''
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Revenue</div>
    <div class="cmd-health-val">{money(rev)}</div>
    <div class="cmd-health-sub">{delta_html(rev_growth, has_prev)}</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Sessions</div>
    <div class="cmd-health-val">{fmt(sessions)}</div>
    <div class="cmd-health-sub">{delta_html(sess_growth, has_prev)}</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Engagement Rate</div>
    <div class="cmd-health-val">{pct(eng_rate)}</div>
    <div class="cmd-health-sub" style="color:{_eng_clr};">{'▲ Above' if eng_rate>=BENCH_ENGAGEMENT_RATE else '▼ Below'} {BENCH_ENGAGEMENT_RATE:.0f}% avg</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Lead Conv. Rate</div>
    <div class="cmd-health-val">{pct(conv_rate)}</div>
    <div class="cmd-health-sub" style="color:{_conv_clr};">{'▲ Above' if conv_rate>=BENCH_CONV_RATE else '▼ Below'} {BENCH_CONV_RATE:.1f}% avg</div>
  </div>'''
        st.markdown(f'''
<div class="cmd-health">
  <div class="cmd-score-ring" style="border-color:{sc_color};">
    <div class="cmd-score-num" style="color:{sc_color};">{score}</div>
    <div class="cmd-score-den">/100</div>
  </div>
  <div style="flex:2;min-width:160px;">
    <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:.95rem;font-weight:800;margin-bottom:2px;">
      <span style="color:{sc_color};">{sc_label}</span>
    </div>
    <div style="font-size:.74rem;color:#64748B;">{period_label} &nbsp;·&nbsp; {period_days}-day window{_loc_label} &nbsp;·&nbsp; {len(base):,} records</div>
  </div>
  {banner_stats}
</div>
''', unsafe_allow_html=True)

    # ── Top Signals (toggleable) — 3-column cards ──────────
    if "signals" in visible_blocks:
        st.markdown('<div class="section-title">Signals</div>', unsafe_allow_html=True)
        _dot_map = {"sb-pill-red": "#EF4444", "sb-pill-amber": "#F59E0B", "sb-pill-green": "#00C06B"}
        _sc1, _sc2, _sc3 = st.columns(3, gap="small")
        for _col, (sev, pill_cls, title, detail, action) in zip([_sc1, _sc2, _sc3], _alerts[:3]):
            _dc = _dot_map.get(pill_cls, "#00C06B")
            with _col:
                st.markdown(
                    f'<div style="background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.13);'
                    f'border-left:3px solid {_dc};border-radius:10px;padding:11px 14px;'
                    f'backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);">'
                    f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;">'
                    f'<span style="width:6px;height:6px;border-radius:50%;background:{_dc};'
                    f'flex-shrink:0;display:inline-block;"></span>'
                    f'<span style="font-size:.79rem;font-weight:700;color:#E2E8F0;">{title}</span>'
                    f'</div>'
                    f'<div style="font-size:.73rem;color:#94A3B8;line-height:1.45;">{detail}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

    # ── Dual Forecasts (toggleable) ────────────────────────
    if "forecasts" in visible_blocks:
        st.markdown('<div class="section-title">30-Day Forecasts</div>', unsafe_allow_html=True)
        _f1, _f2 = st.columns(2, gap="medium")
        with _f1:
            fig_rev, proj_rev = plot_forecast(
                base, col="total_revenue",
                title="Production Forecast — 30-Day Projection",
                color=GREEN, is_money=True
            )
            if fig_rev:
                st.markdown(
                    f'<div style="font-size:.76rem;color:{MUTED};margin-bottom:5px;">'
                    f'Projected: <b style="color:{TEXT};font-size:.85rem;">{money(proj_rev)}</b>'
                    f' &nbsp;·&nbsp; next 30 days</div>',
                    unsafe_allow_html=True
                )
                st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                st.plotly_chart(fig_rev, use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info("Not enough data for production forecast.")
        with _f2:
            try:
                _bk_daily = (base.groupby("date")["booked"].sum()
                               .reset_index().sort_values("date"))
                _bk_daily["date"] = pd.to_datetime(_bk_daily["date"])
                _bk_weekly = (_bk_daily.set_index("date")
                                .resample("W-MON")["booked"].sum()
                                .reset_index())
                if len(_bk_weekly) >= 2:
                    # Linear forecast — 4 future weeks
                    _x = np.arange(len(_bk_weekly))
                    _y = _bk_weekly["booked"].values
                    _coeffs = np.polyfit(_x, _y, 1)
                    _last_date = _bk_weekly["date"].iloc[-1]
                    _fut_dates = [_last_date + timedelta(weeks=i+1) for i in range(4)]
                    _fut_y = np.maximum(0, np.polyval(_coeffs, np.arange(len(_bk_weekly), len(_bk_weekly)+4)))
                    _proj_bk = int(_fut_y.sum())
                    st.markdown(
                        f'<div style="font-size:.76rem;color:{MUTED};margin-bottom:5px;">'
                        f'Projected: <b style="color:{TEXT};font-size:.85rem;">{fmt(_proj_bk)} appts</b>'
                        f' &nbsp;·&nbsp; next 30 days</div>',
                        unsafe_allow_html=True
                    )

                    _fig_bk = go.Figure()
                    # Actual bars — solid blue
                    _fig_bk.add_trace(go.Bar(
                        x=_bk_weekly["date"],
                        y=_bk_weekly["booked"],
                        marker_color="#3B82F6",
                        marker_opacity=0.85,
                        marker_line_width=0,
                        hovertemplate="Week of %{x|%b %d}<br><b>%{y:,.0f} appts</b><extra>Actual</extra>",
                        name="Actual",
                    ))
                    # Forecast bars — lighter, hatched feel via opacity
                    _fig_bk.add_trace(go.Bar(
                        x=_fut_dates,
                        y=_fut_y.tolist(),
                        marker_color="#93C5FD",
                        marker_opacity=0.6,
                        marker_line_color="#3B82F6",
                        marker_line_width=1.5,
                        hovertemplate="Week of %{x|%b %d}<br><b>%{y:,.0f} projected</b><extra>Forecast</extra>",
                        name="Forecast",
                    ))
                    _fig_bk.update_layout(**base_layout("Booked Appointments — Weekly + Forecast", 280), barmode="group", bargap=0.18)
                    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                    st.plotly_chart(_fig_bk, use_container_width=True, config={"displayModeBar": False})
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("Not enough data for appointments chart.")
            except Exception:
                st.info("Not enough data for appointments chart.")



# ==========================================================
# DASHBOARD
# ==========================================================
def render_marketing():
    base = CUR_MKT if not practice_mode else CUR

    with st.expander("Traffic & Conversion by Source", expanded=False):
        journey = base.groupby("data_source", as_index=False).agg(
            Sessions=("sessions",      "sum"),
            New_Users=("new_users",    "sum"),
            Leads=("leads",            "sum"),
            Signups=("signups",        "sum"),
            Revenue=("total_revenue",  "sum"),
        )
        # Weighted engagement rate per source
        _eng = (
            base.assign(_ex=base["engagement_rate_pct"] * base["sessions"])
            .groupby("data_source", as_index=False)
            .agg(_ex=("_ex","sum"), _s=("sessions","sum"))
        )
        _eng["Eng Rate"] = _eng["_ex"] / _eng["_s"].replace(0, 1)
        journey = journey.merge(_eng[["data_source","Eng Rate"]], on="data_source", how="left")
        journey["Lead Rate"]  = np.where(journey["Sessions"]>0, journey["Leads"]/journey["Sessions"]*100, 0)
        journey["Rev/User"]   = np.where(journey["Sessions"]>0, journey["Revenue"]/journey["Sessions"], 0)
        journey = journey.sort_values("Revenue", ascending=False)

        jd = journey.copy()
        jd.insert(0, "Source", jd.pop("data_source"))
        jd["Sessions"]  = jd["Sessions"].apply(fmt)
        jd["New Users"] = jd.pop("New_Users").apply(fmt)
        jd["Leads"]     = jd["Leads"].apply(fmt)
        jd["Lead Rate"] = jd["Lead Rate"].apply(lambda x: f"{x:.1f}%")
        jd["Eng Rate"]  = jd["Eng Rate"].apply(lambda x: f"{x:.1f}%")
        jd["Signups"]   = jd["Signups"].apply(fmt)
        jd["Revenue"]   = jd["Revenue"].apply(money)
        jd["Rev/User"]  = jd["Rev/User"].apply(lambda x: f"${x:.2f}")
        out_cols = ["Source","Sessions","New Users","Leads","Lead Rate","Eng Rate","Signups","Revenue","Rev/User"]
        st.dataframe(df_light(jd[out_cols]), use_container_width=True, hide_index=True, height=df_height(len(jd)))

def render_practice():
    has_prev = len(PREV) > 0
    # ── Top Treatments ─────────────────────────────────────
    st.markdown('<div class="section-title">Top Treatments</div>', unsafe_allow_html=True)
    if "treatment" in CUR.columns:
        cur_t  = CUR.dropna(subset=["treatment"]).copy()
        prev_t = PREV.dropna(subset=["treatment"]).copy() if has_prev else pd.DataFrame(columns=cur_t.columns)

        if len(cur_t) > 0:
            grp = cur_t.groupby("treatment", as_index=False).agg(
                Patients=("conversions", "sum"),
                Booked=("booked",           "sum"),
                Production=("total_revenue","sum"),
            )
            grp["Book Rate"]    = grp.apply(lambda r: safe_div(r["Booked"], max(r["Patients"],1)) * 100, axis=1)
            grp["Prod/Patient"] = grp.apply(lambda r: safe_div(r["Production"], r["Patients"]), axis=1)

            # Prior-period Prod/Patient for delta
            if len(prev_t) > 0:
                prev_g = prev_t.groupby("treatment", as_index=False).agg(
                    Revenue_p=("total_revenue","sum"),
                    Patients_p=("conversions","sum"),
                )
                prev_g["RevPat_p"] = prev_g.apply(lambda r: safe_div(r["Revenue_p"], r["Patients_p"]), axis=1)
                grp = grp.merge(prev_g[["treatment","RevPat_p"]], on="treatment", how="left")
                grp["Δ Prod/Patient"] = grp.apply(
                    lambda r: safe_div(r["Prod/Patient"] - r["RevPat_p"],
                                       max(abs(r["RevPat_p"]), 0.01)) * 100
                    if pd.notna(r.get("RevPat_p")) else np.nan, axis=1)
            else:
                grp["Δ Prod/Patient"] = np.nan

            grp = grp.sort_values("Production", ascending=False).head(20)

            out = grp.rename(columns={"treatment": "Treatment"})[
                ["Treatment", "Patients", "Book Rate", "Prod/Patient", "Δ Prod/Patient", "Production"]
            ].copy()
            out["Patients"]        = out["Patients"].apply(fmt)
            out["Book Rate"]       = out["Book Rate"].apply(lambda x: f"{float(x or 0):.1f}%")
            out["Prod/Patient"]    = out["Prod/Patient"].apply(money)
            out["Δ Prod/Patient"]  = out["Δ Prod/Patient"].apply(
                lambda x: f"{x:+.0f}%" if pd.notna(x) else "—")
            out["Production"]      = out["Production"].apply(money)

            st.dataframe(df_light(out), use_container_width=True,
                         hide_index=True, height=df_height(len(out)))
        else:
            st.info("No treatment data available for the selected range.")
    else:
        st.info("No treatment column found in the data.")



# ==========================================================
# AI CHART GENERATOR
# ==========================================================
def _ai_chart(question: str) -> "go.Figure | None":
    """Return a relevant Plotly chart for the question, or None."""
    try:
        df = CUR.copy()
        if df.empty:
            return None
        q = question.lower()

        # Column aliases — map logical names to actual schema columns
        REV  = "total_revenue"
        COST = "total_cost"
        has  = lambda c: c in df.columns and df[c].notna().any()

        # ---- helpers ----
        def _group_bar(group_col, val_col, title, fmt="$"):
            if not (has(group_col) and has(val_col)):
                return None
            g = (df.groupby(group_col)[val_col].sum()
                   .reset_index()
                   .sort_values(val_col, ascending=False)
                   .head(8))
            hover = "%{x}<br><b>$%{y:,.0f}</b><extra></extra>" if fmt == "$" else "%{x}<br><b>%{y:,.2f}</b><extra></extra>"
            palette = [GREEN, BLUE, AMBER, PURPLE, "#EC4899", "#14B8A6", "#F97316", RED]
            fig = go.Figure()
            for idx, (_, row) in enumerate(g.iterrows()):
                fig.add_trace(go.Bar(
                    x=[str(row[group_col])], y=[row[val_col]],
                    name=str(row[group_col]),
                    marker_color=palette[idx % len(palette)],
                    marker_line_width=0, showlegend=False,
                    hovertemplate=hover,
                ))
            fig.update_layout(**base_layout(title, 260))
            return fig

        def _line(val_col, title):
            if not (has("date") and has(val_col)):
                return None
            g = (df.groupby("date")[val_col].sum()
                   .reset_index()
                   .sort_values("date"))
            return plot_line(g, "date", val_col, title, height=260)

        # ---- Route by question intent ----
        # Trend / over time
        if any(w in q for w in ["trend", "over time", "daily", "weekly", "by day", "by month", "timeline", "last 30", "mtd", "30 days"]):
            if any(w in q for w in ["spend", "cost"]):
                return _line(COST, "Spend Over Time")
            return _line(REV, "Production Over Time")

        # ROAS — computed per source (no roas column in schema)
        if "roas" in q:
            if has("data_source") and has(REV) and has(COST):
                g = df.groupby("data_source", as_index=False).agg(
                    Revenue=(REV, "sum"), Cost=(COST, "sum")
                )
                g["ROAS"] = g.apply(lambda r: safe_div(r["Revenue"], r["Cost"]), axis=1)
                g = g.sort_values("ROAS", ascending=False).head(8)
                return plot_bar_multi(g, "data_source", "ROAS", "ROAS by Source")
            return None

        # Spend / cost
        if any(w in q for w in ["spend", "cost", "budget"]):
            return _group_bar("data_source", COST, "Ad Spend by Source", "$")

        # Leads / patients / appointments
        if any(w in q for w in ["lead", "patient", "appointment", "booked", "booking"]):
            col = ("booked" if any(w in q for w in ["appointment", "booked", "booking"])
                   else ("conversions" if has("conversions") else "leads"))
            col = col if has(col) else ("leads" if has("leads") else None)
            if col:
                return _group_bar("data_source", col, f"{col.replace('_',' ').title()} by Source", ",")

        # Channel breakdown
        if any(w in q for w in ["channel"]):
            return _group_bar("channel_group", REV, "Production by Channel", "$")

        # Compare sources / platform comparison
        if any(w in q for w in ["compare", "vs", "versus", "google", "facebook", "meta", "source"]):
            return _group_bar("data_source", REV, "Production by Source", "$")

        # Bar chart catch-all
        if any(w in q for w in ["bar", "chart", "breakdown"]):
            return _group_bar("data_source", REV, "Production by Source", "$")

        # Default: revenue over time if date available, else by source
        if has("date"):
            return _line(REV, "Production Over Time")
        return _group_bar("data_source", REV, "Production by Source", "$")

    except Exception:
        pass
    return None


# ==========================================================
# AI QUERY CLIENT  (uses existing SQL connector — no extra permissions)
# ==========================================================
# Model endpoint confirmed available in this workspace
_MODEL_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"

def _call_genie(question: str) -> dict:
    """
    Send a question to Databricks Genie and return the answer.

    Genie flow:
      1. Start conversation (or continue existing one stored in session state)
      2. Poll until status == COMPLETED or FAILED (max 90 s)
      3. Extract natural-language answer + SQL from attachments
      4. Fetch query result rows via the result endpoint → return as DataFrame

    Returns dict: {text, sql, df, error}
    """
    import requests, time

    if not GENIE_SPACE_ID:
        return {"text": "", "sql": "", "df": None, "error": "no_genie_space"}

    token    = os.environ.get("DATABRICKS_TOKEN", "")
    base_url = f"https://{DATABRICKS_HOST.rstrip('/')}/api/2.0/genie/spaces/{GENIE_SPACE_ID}"
    headers  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        # ── 1. Start or continue conversation ──────────────────
        conv_id = st.session_state.get("genie_conversation_id")
        if conv_id:
            resp = requests.post(
                f"{base_url}/conversations/{conv_id}/messages",
                headers=headers,
                json={"content": question},
                timeout=30
            )
        else:
            resp = requests.post(
                f"{base_url}/start-conversation",
                headers=headers,
                json={"content": question},
                timeout=30
            )

        resp.raise_for_status()
        data    = resp.json()
        conv_id = data.get("conversation_id", conv_id)
        msg_id  = data.get("message_id") or data.get("id")
        st.session_state["genie_conversation_id"] = conv_id

        # ── 2. Poll until COMPLETED ─────────────────────────────
        poll_url = f"{base_url}/conversations/{conv_id}/messages/{msg_id}"
        status, payload, elapsed = "PENDING", {}, 0
        while status not in ("COMPLETED", "FAILED") and elapsed < 90:
            time.sleep(2); elapsed += 2
            pr = requests.get(poll_url, headers=headers, timeout=30)
            pr.raise_for_status()
            payload = pr.json()
            status  = payload.get("status", "PENDING")

        if status == "FAILED":
            return {"text": "", "sql": "", "df": None,
                    "error": payload.get("error", "Genie query failed.")}

        # ── 3. Extract text answer + SQL from attachments ───────
        answer_text, answer_sql, answer_desc = "", "", ""
        for att in payload.get("attachments", []):
            if "text" in att:
                answer_text = att["text"].get("content", "")
            if "query" in att:
                answer_sql  = att["query"].get("query", "")
                answer_desc = att["query"].get("description", "")

        if not answer_text and answer_desc:
            answer_text = answer_desc

        # ── 4. Fetch query result rows → DataFrame ──────────────
        df = None
        if answer_sql:
            try:
                res_url = f"{poll_url}/query-result"
                rr = requests.get(res_url, headers=headers, timeout=30)
                if rr.status_code == 200:
                    rdata  = rr.json()
                    cols   = [c["name"] for c in rdata.get("manifest", {}).get("schema", {}).get("columns", [])]
                    rows   = [r.get("values", []) for r in rdata.get("result", {}).get("data_typed_array", [])]
                    if cols and rows:
                        df = pd.DataFrame([[v.get("str", "") for v in row] for row in rows], columns=cols)
            except Exception:
                pass  # result table is optional — text answer is enough

        return {"text": answer_text, "sql": answer_sql, "df": df, "error": None}

    except Exception as exc:
        return {"text": "", "sql": "", "df": None, "error": str(exc)}


def _is_visual_question(q: str) -> bool:
    """Returns True only when the question explicitly asks for a chart/visual or a breakdown."""
    ql = q.lower()
    return any(w in ql for w in [
        "chart", "graph", "plot", "show me", "visuali",
        "trend", "over time", "daily", "weekly", "monthly", "timeline",
        "by source", "by channel", "by campaign",
        "compare", " vs ", "versus",
        "breakdown", "roas by", "spend by", "revenue by", "leads by",
        "last 30", "mtd", "traffic",
    ])


def _followup_chips(q: str) -> list:
    """Return up to 3 contextual follow-up questions based on what was asked."""
    q_low = q.lower()
    pool  = []
    if any(x in q_low for x in ["revenue", "sales", "income", "money"]):
        pool += ["Break down production by source", "Production trend last 90 days", "Best production day this month?"]
    if any(x in q_low for x in ["roas", "return on ad", "spend", "cost per"]):
        pool += ["Compare ROAS: Google vs Facebook", "Which campaign has the best ROI?"]
    if any(x in q_low for x in ["show rate", "attendance", "attended", "no-show"]):
        pool += ["Which treatment has the best show rate?", "Compare show rate by source"]
    if any(x in q_low for x in ["patient", "new patient", "lead"]):
        pool += ["What's my cost per new patient?", "New patient trend last 90 days"]
    if any(x in q_low for x in ["google", "facebook", "instagram", "meta", "source", "campaign"]):
        pool += ["Which campaign drove the most production?", "Top 5 campaigns by ROAS"]
    if any(x in q_low for x in ["treatment", "procedure", "service"]):
        pool += ["Which treatment drives the most production?", "Show rate by treatment"]
    if not pool:
        pool = ["What drove production this month?", "Which source has the best ROAS?", "Show my top campaigns"]
    seen, chips = set(), []
    for c in pool:
        if c not in seen:
            seen.add(c); chips.append(c)
        if len(chips) == 3:
            break
    return chips


def _run_query(question: str) -> dict:
    """Route question to Databricks Genie."""
    if GENIE_SPACE_ID:
        return _call_genie(question)
    return {"text": "", "sql": "", "df": None, "error": "no_genie_space"}


def render_ai():
    # ── Session state init ───────────────────────────────────
    if "ai_history"             not in st.session_state: st.session_state.ai_history = []
    if "ai_nonce"               not in st.session_state: st.session_state.ai_nonce = 0
    if "genie_conversation_id"  not in st.session_state: st.session_state.genie_conversation_id = None
    has_history = len(st.session_state.ai_history) > 0

    # ── EMPTY STATE: hero only ───────────────────────────────
    if not has_history:
        st.markdown('''
<div class="ai-hero-wrap">
  <div class="ai-catch">Ask anything about<br><span class="ai-catch-hi">your practice.</span></div>
  <div class="ai-catch-sub">Get straight answers from your data. No dashboards needed.</div>
</div>
''', unsafe_allow_html=True)

    # ── Chat input (always rendered) ─────────────────────────
    st.markdown('<div id="ai-send-row"></div>', unsafe_allow_html=True)
    _icol, _scol = st.columns([11, 1])
    with _icol:
        user_q = st.text_area(
            "", placeholder="Ask anything about your data…",
            label_visibility="collapsed",
            key=f"ai_input_{st.session_state.ai_nonce}",
            height=80
        )
    with _scol:
        st.markdown('<div style="height:1.55rem"></div>', unsafe_allow_html=True)
        ask = st.button("↑", use_container_width=True, key="ai_ask", type="primary")

    # ── Typewriter placeholder animation ─────────────────────
    components.html("""
<script>
(function () {
  var QUESTIONS = [
    "What was my production last month?",
    "Which treatments have the highest show rate?",
    "How many new patients did we see this week?",
    "What\u2019s my ROAS across all campaigns?",
    "Compare Google vs Facebook performance"
  ];
  var qIdx = 0, cIdx = 0, deleting = false;
  var T_TYPE = 65, T_DEL = 28, T_PAUSE_END = 2200, T_PAUSE_START = 480;

  function getTA() {
    return window.parent.document.querySelector('[data-testid="stTextArea"] textarea');
  }

  function tick() {
    var ta = getTA();
    if (!ta || ta.value.length > 0) { setTimeout(tick, 400); return; }
    var q = QUESTIONS[qIdx];
    if (deleting) {
      cIdx = Math.max(0, cIdx - 1);
      ta.setAttribute("placeholder", q.slice(0, cIdx));
      if (cIdx === 0) {
        deleting = false;
        qIdx = (qIdx + 1) % QUESTIONS.length;
        setTimeout(tick, T_PAUSE_START);
      } else { setTimeout(tick, T_DEL); }
    } else {
      cIdx = Math.min(q.length, cIdx + 1);
      ta.setAttribute("placeholder", q.slice(0, cIdx));
      if (cIdx === q.length) {
        deleting = true;
        setTimeout(tick, T_PAUSE_END);
      } else { setTimeout(tick, T_TYPE); }
    }
  }
  setTimeout(tick, 900);
})();

/* ── Enter to send, Shift+Enter for new line ── */
(function () {
  var _bound = null;
  function bindEnter() {
    var ta = window.parent.document.querySelector('[data-testid="stTextArea"] textarea');
    if (!ta) { setTimeout(bindEnter, 300); return; }
    if (ta === _bound) { setTimeout(bindEnter, 600); return; }
    _bound = ta;
    ta.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        var btn = window.parent.document.querySelector('[data-testid="stBaseButton-primary"]');
        if (btn) btn.click();
      }
    });
    setTimeout(bindEnter, 600);
  }
  setTimeout(bindEnter, 600);
})();
</script>
""", height=0)

    # ── Resolve question ─────────────────────────────────────
    run_q = user_q.strip() if ask and user_q.strip() else None

    if run_q:
        with st.spinner("Thinking…"):
            result = _run_query(run_q)
        st.session_state.ai_history.insert(0, {"q": run_q, **result})
        if len(st.session_state.ai_history) > 10:
            st.session_state.ai_history = st.session_state.ai_history[:10]
        st.rerun()

    # ── Chat history ─────────────────────────────────────────
    for _hidx, item in enumerate(st.session_state.ai_history):
        q     = item.get("q", "")
        text  = item.get("text", "")
        sql   = item.get("sql", "")
        df    = item.get("df")
        error = item.get("error")

        # User bubble
        st.markdown(f'<div class="ai-bubble-user"><span>{q}</span></div>', unsafe_allow_html=True)

        # ── Error states ────────────────────────────────────
        if error == "offline":
            st.markdown(
                '<div class="ai-msg-label">NexoBI AI</div>'
                '<div class="ai-bubble-ai" style="border-left:3px solid #F59E0B!important;background:#FFFBEB!important;">'
                '<span style="font-weight:700;color:#92400E;">AI Agent offline</span> — '
                '<span style="color:#78716C;">Databricks Genie is currently unreachable. '
                'Dashboard metrics are still available above.</span>'
                '</div>',
                unsafe_allow_html=True
            )
            if _is_visual_question(q):
                chart = _ai_chart(q)
                if chart is not None:
                    st.markdown('<div class="chart-card" style="margin-top:.4rem;">', unsafe_allow_html=True)
                    st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})
                    st.markdown('</div>', unsafe_allow_html=True)
            continue

        if error == "no_genie_space":
            st.markdown(
                '<div class="ai-msg-label">NexoBI AI</div>'
                '<div class="ai-bubble-ai" style="border-left:3px solid #F59E0B!important;background:#FFFBEB!important;">'
                '<span style="font-weight:700;color:#92400E;">Genie not configured</span> — '
                '<span style="color:#78716C;">Set <code>NEXOBI_GENIE_SPACE_ID</code> in your '
                'Databricks Apps environment variables to enable conversational analytics '
                'against your gold layer tables.</span>'
                '</div>',
                unsafe_allow_html=True
            )
            continue

        if error:
            st.markdown(
                '<div class="ai-msg-label">NexoBI AI</div>'
                f'<div class="ai-bubble-ai" style="border-left:3px solid #EF4444!important;">'
                f'<span style="font-weight:700;color:#991B1B;">Error</span> — '
                f'<span style="color:#78716C;">{error}</span></div>',
                unsafe_allow_html=True
            )
            continue

        # ── AI response ─────────────────────────────────────
        if text:
            st.markdown(
                '<div class="ai-msg-label">NexoBI AI</div>'
                f'<div class="ai-bubble-ai">{text}</div>',
                unsafe_allow_html=True
            )

        # Auto chart — only for explicitly visual questions
        if _is_visual_question(q):
            chart = _ai_chart(q)
            if chart is not None:
                st.markdown('<div class="chart-card" style="margin-top:.4rem;">', unsafe_allow_html=True)
                st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)

        # Data table (from Genie query result)
        if df is not None and not df.empty:
            st.dataframe(
                df_light(df),
                use_container_width=True,
                hide_index=True,
                height=df_height(len(df))
            )

        # SQL expander — show what Genie actually ran
        if sql:
            with st.expander("View SQL", expanded=False):
                st.code(sql, language="sql")

        # ── Follow-up suggestion chips ───────────────────────
        if not error:
            _chips = _followup_chips(q)
            st.markdown('<div class="ai-followup-marker"></div>', unsafe_allow_html=True)
            _chip_cols = st.columns(len(_chips))
            for _ci, (_chip_col, _chip) in enumerate(zip(_chip_cols, _chips)):
                with _chip_col:
                    if st.button(_chip, key=f"ai_chip_{_hidx}_{_ci}", use_container_width=True):
                        with st.spinner("Thinking…"):
                            _chip_res = _run_query(_chip)
                        st.session_state.ai_history.insert(0, {"q": _chip, **_chip_res})
                        if len(st.session_state.ai_history) > 10:
                            st.session_state.ai_history = st.session_state.ai_history[:10]
                        st.rerun()

    # ── New chat — below dialogue, only when history exists ──
    if has_history:
        st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)
        _nc_gap, _nc_col = st.columns([8, 2])
        with _nc_col:
            if st.button("↺  New chat", key="ai_reset_compact", use_container_width=True):
                st.session_state.ai_history            = []
                st.session_state.ai_nonce             += 1
                st.session_state.genie_conversation_id = None  # start fresh Genie conversation
                st.rerun()

# ==========================================================
# ROUTER
# ==========================================================

if page == "Dashboard":
    st.markdown('<div class="dash-orbs"><div class="do1"></div><div class="do2"></div><div class="do3"></div></div>', unsafe_allow_html=True)
    render_command_center()
    if practice_mode:
        if "treatments" in visible_blocks:
            render_practice()
    else:
        if "journey" in visible_blocks:
            render_marketing()

elif page == "AI Agent":
    # ── Full-bleed dark navy aurora — hide everything, bleed full page ──
    st.markdown("""<style>
[data-testid="stSidebar"]{display:none!important;}
[data-testid="stHeader"]{display:none!important;}
[data-testid="stToolbar"]{display:none!important;}
header{display:none!important;}footer{display:none!important;}
.nexo-header{display:none!important;}
section.main{margin-left:0!important;}
.stApp{
  --background-color:#060D1A!important;
  --secondary-background-color:rgba(255,255,255,.07)!important;
  --text-color:#CBD5E1!important;
  background:#060D1A!important;min-height:100vh!important;
}
.block-container{max-width:680px!important;margin:0 auto!important;padding-top:1rem!important;padding-bottom:3rem!important;background:transparent!important;}
/* ── Aurora orbs + particles + grid ──────────────────────── */
@keyframes breathe{0%,100%{opacity:.9;transform:scale(1)}50%{opacity:1;transform:scale(1.08)}}
@keyframes drift1{0%{transform:translate(0,0)}25%{transform:translate(18px,-24px)}50%{transform:translate(-12px,-40px)}75%{transform:translate(22px,-14px)}100%{transform:translate(0,0)}}
@keyframes drift2{0%{transform:translate(0,0)}33%{transform:translate(-20px,14px)}66%{transform:translate(12px,28px)}100%{transform:translate(0,0)}}
@keyframes drift3{0%{transform:translate(0,0)}50%{transform:translate(28px,20px)}100%{transform:translate(0,0)}}
@keyframes drift4{0%{transform:translate(0,0)}40%{transform:translate(-15px,-18px)}80%{transform:translate(10px,8px)}100%{transform:translate(0,0)}}
@keyframes twinkle{0%,100%{opacity:.25;transform:scale(1)}50%{opacity:.75;transform:scale(1.5)}}
@keyframes twinkle2{0%,100%{opacity:.15;transform:scale(1)}50%{opacity:.55;transform:scale(1.3)}}
@keyframes gridShift{0%{background-position:0 0}100%{background-position:48px 48px}}
@keyframes scanPulse{0%,100%{opacity:0}10%,90%{opacity:1}50%{opacity:.6}}
@keyframes shimmer{0%{background-position:-200% center}100%{background-position:200% center}}
@keyframes inputGlow{0%,100%{box-shadow:0 0 0 0 rgba(0,192,107,0),0 2px 10px rgba(0,0,0,.05)}50%{box-shadow:0 0 22px 4px rgba(0,192,107,.16),0 2px 10px rgba(0,0,0,.05)}}
/* ── Shimmer on gradient headline ─────────────────────── */
.ai-catch-hi{background:linear-gradient(120deg,#00C06B 0%,#38BDF8 40%,#00C06B 80%)!important;background-size:250% auto!important;-webkit-background-clip:text!important;-webkit-text-fill-color:transparent!important;background-clip:text!important;animation:shimmer 4s linear infinite!important;}
/* ── Top accent line ──────────────────────────────────── */
.ai-top-line{position:fixed;top:0;left:0;right:0;height:2px;z-index:99999;pointer-events:none;
  background:linear-gradient(90deg,transparent 0%,rgba(0,192,107,.8) 35%,rgba(56,189,248,.55) 65%,transparent 100%);}

.ai-page-orbs{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;}

/* Grid overlay — very subtle green mesh */
.ai-page-orbs .ai-grid{
  position:absolute;inset:0;
  background-image:linear-gradient(rgba(0,192,107,.028) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(0,192,107,.028) 1px,transparent 1px);
  background-size:48px 48px;
  animation:gridShift 24s linear infinite;
}

/* Main aurora orbs */
.ai-page-orbs .op1{position:absolute;width:560px;height:560px;background:rgba(0,192,107,.14);border-radius:50%;filter:blur(95px);top:-160px;right:-90px;animation:floatA 9s ease-in-out infinite,breathe 7s ease-in-out infinite;}
.ai-page-orbs .op2{position:absolute;width:440px;height:440px;background:rgba(0,153,82,.09);border-radius:50%;filter:blur(90px);bottom:-110px;left:-70px;animation:floatB 13s ease-in-out infinite,breathe 10s ease-in-out infinite reverse;}
.ai-page-orbs .op3{position:absolute;width:280px;height:280px;background:rgba(0,192,107,.06);border-radius:50%;filter:blur(75px);top:40%;right:-40px;animation:floatA 17s ease-in-out infinite reverse,breathe 8s ease-in-out infinite;}
.ai-page-orbs .op4{position:absolute;width:200px;height:200px;background:rgba(0,212,120,.07);border-radius:50%;filter:blur(60px);top:55%;left:10%;animation:floatB 11s ease-in-out infinite,breathe 9s ease-in-out 2s infinite;}

/* Floating particles — tiny glowing dots */
.ai-page-orbs .pt{position:absolute;border-radius:50%;pointer-events:none;}
.ai-page-orbs .pt1{width:3px;height:3px;background:rgba(0,192,107,.7);top:18%;left:12%;animation:drift1 9s ease-in-out infinite,twinkle 3.2s ease-in-out infinite;}
.ai-page-orbs .pt2{width:2px;height:2px;background:rgba(0,192,107,.5);top:35%;left:72%;animation:drift2 11s ease-in-out infinite,twinkle 4.1s ease-in-out .8s infinite;}
.ai-page-orbs .pt3{width:4px;height:4px;background:rgba(0,212,120,.6);top:62%;left:28%;animation:drift3 8s ease-in-out infinite,twinkle 2.8s ease-in-out 1.5s infinite;}
.ai-page-orbs .pt4{width:2px;height:2px;background:rgba(0,192,107,.4);top:78%;left:58%;animation:drift4 14s ease-in-out infinite,twinkle2 5s ease-in-out infinite;}
.ai-page-orbs .pt5{width:3px;height:3px;background:rgba(0,153,82,.55);top:25%;left:85%;animation:drift1 12s ease-in-out 1s infinite,twinkle 3.6s ease-in-out .4s infinite;}
.ai-page-orbs .pt6{width:2px;height:2px;background:rgba(0,192,107,.45);top:50%;left:5%;animation:drift2 10s ease-in-out .5s infinite,twinkle2 4.4s ease-in-out 2s infinite;}
.ai-page-orbs .pt7{width:3px;height:3px;background:rgba(0,212,120,.5);top:88%;left:40%;animation:drift3 13s ease-in-out .3s infinite,twinkle 3s ease-in-out 1s infinite;}
.ai-page-orbs .pt8{width:2px;height:2px;background:rgba(0,192,107,.35);top:10%;left:45%;animation:drift4 9s ease-in-out 2s infinite,twinkle2 5.2s ease-in-out infinite;}
/* ── Dashboard pill — fixed top-left anchor link ─────── */
#nexobi-dash-pill{
  position:fixed;top:14px;left:14px;z-index:10000;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.16);
  border-radius:999px;padding:5px 14px;
  color:rgba(255,255,255,.55);font-size:.69rem;font-weight:600;
  cursor:pointer;font-family:inherit;letter-spacing:.03em;
  text-decoration:none;display:inline-flex;align-items:center;gap:5px;
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
  transition:all .2s;
}
#nexobi-dash-pill:hover{background:rgba(0,192,107,.12);color:#00C06B;border-color:rgba(0,192,107,.35);}
/* ── Textarea — white bg, DARK text, visible cursor ─────── */
html body textarea,
[data-testid="stTextArea"] textarea,
.stTextArea textarea,
.stApp textarea{
  color:#000000!important;
  -webkit-text-fill-color:#000000!important;
  caret-color:#00C06B!important;
  background:#ffffff!important;
  border:1.5px solid rgba(0,192,107,.35)!important;
  border-radius:16px!important;
  padding:13px 16px!important;font-size:.9rem!important;
  line-height:1.5!important;resize:none!important;
  animation:inputGlow 3.5s ease-in-out infinite!important;
}
html body textarea::placeholder,
[data-testid="stTextArea"] textarea::placeholder{color:#475569!important;-webkit-text-fill-color:#475569!important;font-size:.97rem!important;}
html body textarea:focus,
[data-testid="stTextArea"] textarea:focus{
  border-color:#00C06B!important;
  box-shadow:0 0 0 3px rgba(0,192,107,.12)!important;
  caret-color:#00C06B!important;
}
[data-testid="stTextArea"]>div,[data-testid="stTextArea"]>div>div{border:none!important;background:transparent!important;}
/* ── Secondary buttons — frosted on dark bg ─────────────── */
html body [data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondary"]{
  background:rgba(255,255,255,.10)!important;
  border:1px solid rgba(255,255,255,.18)!important;
  color:rgba(255,255,255,.78)!important;
  box-shadow:none!important;border-radius:999px!important;
  padding:.3rem .95rem!important;font-size:.77rem!important;
  min-height:0!important;height:auto!important;letter-spacing:.01em!important;
  transition:all .16s!important;
}
html body [data-testid="stBaseButton-secondary"]:hover,
[data-testid="stBaseButton-secondary"]:hover{
  background:rgba(255,255,255,.18)!important;
  color:#ffffff!important;border-color:rgba(255,255,255,.32)!important;
}
/* ── Primary / Send — circular green ────────────────────── */
html body [data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primary"]{
  border-radius:50%!important;
  width:46px!important;min-width:46px!important;
  height:46px!important;min-height:46px!important;
  padding:0!important;font-size:1.1rem!important;
  background:linear-gradient(135deg,#00C06B,#00875A)!important;
  color:#fff!important;border:none!important;
  box-shadow:0 4px 18px rgba(0,192,107,.35)!important;
  transition:all .18s!important;
}
html body [data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primary"]:hover{
  box-shadow:0 6px 26px rgba(0,192,107,.5)!important;
  transform:scale(1.07)!important;
}
/* ── AI bubble — white card, DARK text ───────────────────── */
.ai-bubble-ai{
  background:rgba(255,255,255,.92)!important;
  border:none!important;border-left:3px solid #00C06B!important;
  border-radius:4px 18px 18px 18px!important;
  color:#1E293B!important;
}
.ai-bubble-ai *{color:#334155!important;}
.ai-bubble-ai b,.ai-bubble-ai strong,.ai-bubble-ai th{color:#0F172A!important;}
.ai-bubble-ai td{color:#334155!important;}
/* ── Misc ────────────────────────────────────────────────── */
.stMarkdownContainer p{color:rgba(255,255,255,.26)!important;}
</style>""", unsafe_allow_html=True)

    # ── Full-page aurora orbs + grid + particles ─────────────
    st.markdown(
        '<div class="ai-page-orbs">'
        '<div class="ai-grid"></div>'
        '<div class="op1"></div><div class="op2"></div><div class="op3"></div><div class="op4"></div>'
        '<div class="pt pt1"></div><div class="pt pt2"></div><div class="pt pt3"></div>'
        '<div class="pt pt4"></div><div class="pt pt5"></div><div class="pt pt6"></div>'
        '<div class="pt pt7"></div><div class="pt pt8"></div>'
        '</div>',
        unsafe_allow_html=True
    )

    # ── Dashboard pill — simple anchor, query-param nav ───────
    st.markdown('<div class="ai-top-line"></div>', unsafe_allow_html=True)
    st.markdown('<a id="nexobi-dash-pill" href="?_nav=dash" target="_self"><span style="color:#00C06B;font-size:.6rem;">◆</span> ← Dashboard</a>', unsafe_allow_html=True)

    # Note: AI Agent uses DATA (full dataset) — sidebar filters have no effect
    render_ai()
