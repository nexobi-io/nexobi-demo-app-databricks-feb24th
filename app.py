
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import difflib
import hashlib
import os
import time
import requests
from datetime import datetime, timedelta, date

# ==========================================================
# CONFIG — CSV (dev) or Databricks (prod)
# Set NEXOBI_DATA_MODE=databricks in Databricks Apps env vars
# ==========================================================
CSV_PATH = "data.csv"   # used when DATA_MODE == "csv"

DATA_MODE = os.getenv("NEXOBI_DATA_MODE", "databricks").lower()   # "csv" | "databricks"

# Unity Catalog coordinates — set these as Databricks Apps env vars
DBX_CATALOG = os.getenv("NEXOBI_CATALOG", "workspace")
DBX_SCHEMA  = os.getenv("NEXOBI_SCHEMA",  "silver")
DBX_TABLE   = os.getenv("NEXOBI_TABLE",   "DemoData-marketing-crm")

# Databricks SQL Warehouse connection (used as fallback when SparkSession unavailable)
# Values must be set as environment variables — never hardcoded here.
DATABRICKS_HOST      = os.getenv("DATABRICKS_HOST",      "")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH", "")

# Databricks AI — conversational analytics via ai_query() SQL function

# ==========================================================
# THEME TOKENS
# ==========================================================
GREEN    = "#00C06B"
GREEN_DK = "#009952"
GREEN_LT = "#E6F9F0"
TEXT     = "#0F172A"
MUTED    = "#64748B"
BORDER   = "#E2E8F0"
BG       = "#F5F7FA"
PANEL    = "#FFFFFF"
RED      = "#EF4444"
BLUE     = "#3B82F6"
AMBER    = "#F59E0B"
PURPLE   = "#8B5CF6"
INK      = "#111827"
SOFT     = "#EEF2F7"

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


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

# ==========================================================
# LOAD CSV
# ==========================================================
REQUIRED_COLS = [
    "date","data_source","channel_group","campaign",
    "total_cost","total_revenue","sessions","conversions",
    "booked","attended"
]
EXTRA_COLS = [
    "source_medium","total_users","new_users","clicks","impressions",
    "leads","roi","roas","conversion_rate","treatment"
]

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Shared normalization applied regardless of data source (CSV or Delta)."""
    df.columns = [c.strip() for c in df.columns]

    if "date" not in df.columns:
        raise ValueError("Data missing 'date' column.")

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"]).copy()

    for c in REQUIRED_COLS:
        if c not in df.columns:
            raise ValueError(f"Data missing required column: {c}")

    for c in EXTRA_COLS:
        if c not in df.columns:
            df[c] = 0

    num_cols = [
        "total_cost","total_revenue","sessions","conversions","booked","attended",
        "total_users","new_users","clicks","impressions","leads","roi","roas","conversion_rate"
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    for c in ["data_source","channel_group","campaign","source_medium","treatment"]:
        df[c] = df[c].astype(str).fillna("")

    # Leads normalization — if leads mostly zero but conversions have signal, alias
    leads_signal = (df["leads"] > 0).mean() if "leads" in df.columns else 0.0
    conv_signal  = (df["conversions"] > 0).mean()
    if ("leads" not in df.columns) or (leads_signal < 0.15 and conv_signal > 0.15):
        df["leads"] = df["conversions"]

    if (df["conversion_rate"] == 0).mean() > 0.60:
        df["conversion_rate"] = np.where(df["sessions"] > 0, (df["leads"]/df["sessions"])*100.0, 0.0)
    if (df["roas"] == 0).mean() > 0.60:
        df["roas"] = np.where(df["total_cost"] > 0, df["total_revenue"]/df["total_cost"], 0.0)

    return df


@st.cache_data(ttl=3600)
def load_data(path: str) -> pd.DataFrame:
    """CSV mode — used during local development or Streamlit Cloud."""
    df = pd.read_csv(path)
    return _normalize_df(df)


@st.cache_data(ttl=3600)
def load_data_databricks(catalog: str, schema: str, table: str) -> pd.DataFrame:
    """
    Databricks mode — reads a Delta table from Unity Catalog.

    On Databricks Apps the SparkSession is pre-created by the platform.
    Falls back to databricks-sql-connector if Spark is unavailable
    (e.g. local dev pointing at a SQL Warehouse).

    Table names with hyphens (e.g. DemoData-marketing-crm) are safely
    handled via backtick-quoting in both execution paths.
    """
    full_name = f"`{catalog}`.`{schema}`.`{table}`"
    try:
        # Prefer the active Spark session (available on Databricks Apps clusters)
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()
        if spark is None:
            spark = SparkSession.builder.getOrCreate()
        # Use spark.sql() instead of spark.table() — handles backtick-quoted
        # names with hyphens and other special characters reliably.
        df = spark.sql(f"SELECT * FROM {full_name}").toPandas()
    except Exception:
        # Fallback: Databricks SQL connector
        # DATABRICKS_TOKEN is auto-injected by Databricks Apps at runtime.
        from databricks import sql as _dbsql
        host      = DATABRICKS_HOST
        http_path = DATABRICKS_HTTP_PATH
        token     = os.environ["DATABRICKS_TOKEN"]   # auto-provided by Apps
        with _dbsql.connect(server_hostname=host,
                            http_path=http_path,
                            access_token=token) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {full_name}")
                df = cur.fetchall_arrow().to_pandas()

    return _normalize_df(df)


# ---- Load data based on mode ----
try:
    if DATA_MODE == "databricks":
        DATA = load_data_databricks(DBX_CATALOG, DBX_SCHEMA, DBX_TABLE)
    else:
        DATA = load_data(CSV_PATH)
except Exception as e:
    if DATA_MODE == "databricks":
        st.error(
            f"Could not load Delta table `{DBX_CATALOG}.{DBX_SCHEMA}.{DBX_TABLE}`. "
            f"Check that the table exists and env vars are set correctly. Error: {e}"
        )
    else:
        st.error(f"Could not load {CSV_PATH}. Put data.csv next to this file. Error: {e}")
    st.stop()

MIN_DATE = DATA["date"].min()
MAX_DATE = DATA["date"].max()

# Show data source badge in header area + refresh button (Databricks mode only)
_DBX_MODE = DATA_MODE == "databricks"

# ==========================================================
# PLOTLY HELPERS
# ==========================================================
def base_layout(title: str = "", height: int = 260):
    return dict(
        paper_bgcolor=PANEL,
        plot_bgcolor=PANEL,
        font=dict(family="DM Sans, sans-serif", color=TEXT, size=12),
        height=height,
        margin=dict(l=8, r=8, t=44 if title else 16, b=8),
        title=dict(text=f"<b>{title}</b>", font=dict(size=13, color=TEXT), x=0, xanchor="left") if title else None,
        xaxis=dict(showgrid=False, linecolor=BORDER, tickcolor=BORDER, tickfont=dict(color=MUTED, size=11)),
        yaxis=dict(gridcolor=SOFT, gridwidth=1, linecolor=BORDER, tickcolor=BORDER, tickfont=dict(color=MUTED, size=11), zerolinecolor=BORDER),
        legend=dict(bgcolor=PANEL, bordercolor=BORDER, borderwidth=1, font=dict(color=TEXT, size=11)),
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

def plot_bar(df: pd.DataFrame, x: str, y: str, title: str, color: str = GREEN, height: int = 260):
    fig = go.Figure(go.Bar(
        x=df[x], y=df[y],
        marker_color=color, marker_line_width=0,
        hovertemplate="%{x}<br><b>%{y:,.0f}</b><extra></extra>",
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
  --nexo-green:#00C06B;--nexo-green-dk:#009952;--nexo-green-lt:#E6F9F0;
  --nexo-text:#0F172A;--nexo-muted:#64748B;--nexo-border:#E2E8F0;
  --nexo-bg:#F5F7FA;--nexo-panel:#FFFFFF;--nexo-red:#EF4444;
  --nexo-blue:#3B82F6;--nexo-amber:#F59E0B;--nexo-purple:#8B5CF6;
  --nexo-ink:#111827;--nexo-soft:#EEF2F7;
}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;color:#0F172A!important;}
.stApp{background:#F5F7FA!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{max-width:1480px;padding:.75rem 1.25rem 2.2rem;} /* condensed */

[data-testid="stSidebar"]{background:#FFFFFF!important;border-right:1px solid #E2E8F0!important;}
[data-testid="stSidebar"] *{color:#0F172A!important;}
[data-testid="stSidebar"] label{font-size:.72rem!important;font-weight:600!important;text-transform:none!important;letter-spacing:0!important;color:#64748B!important;}
[data-testid="stSidebar"] [data-baseweb="select"]>div{background:#F5F7FA!important;border:1px solid #E2E8F0!important;border-radius:8px!important;font-size:.82rem!important;}
[data-testid="stSidebar"] input{background:#F5F7FA!important;border:1px solid #E2E8F0!important;border-radius:8px!important;font-size:.82rem!important;}
[data-testid="stSidebar"] [data-baseweb="base-input"]{background:#F5F7FA!important;border:1px solid #E2E8F0!important;border-radius:8px!important;box-shadow:none!important;}
[data-testid="stSidebar"] [data-baseweb="base-input"]:focus-within{border-color:#00C06B!important;box-shadow:none!important;}
[data-testid="stSidebar"] [data-baseweb="input"]{background:#F5F7FA!important;border:1px solid #E2E8F0!important;border-radius:8px!important;box-shadow:none!important;}
[data-testid="stSidebar"] div[data-testid="stDateInput"] input{font-size:.82rem!important;}
[data-testid="stSidebar"] span[data-baseweb="tag"]{background:#E6F9F0!important;border:1px solid #00C06B!important;color:#009952!important;font-size:.75rem!important;}
[data-testid="stSidebar"] .stRadio>div{gap:.2rem!important;flex-direction:column!important;}
[data-testid="stSidebar"] .stRadio label{background:transparent!important;border:none!important;border-radius:8px!important;padding:5px 10px!important;font-size:.84rem!important;font-weight:500!important;color:#64748B!important;text-transform:none!important;letter-spacing:0!important;}
[data-testid="stSidebar"] .stRadio label:has(input:checked){background:#E6F9F0!important;color:#009952!important;font-weight:600!important;}
[data-testid="stSidebar"] .stRadio label:hover{background:#F5F7FA!important;}

.nexo-header{display:flex;align-items:center;justify-content:space-between;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:16px;padding:12px 18px;margin-bottom:.9rem;box-shadow:0 2px 12px rgba(0,0,0,.05);}
.nexo-brand-name{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.15rem;font-weight:900;color:#0F172A;}
.nexo-brand-sub{font-size:.8rem;color:#64748B;}
.nexo-badge{background:#E6F9F0;color:#009952;border:1px solid #00C06B;border-radius:999px;font-size:.72rem;font-weight:900;padding:4px 14px;}

.section-title{font-family:'Plus Jakarta Sans',sans-serif;font-size:.78rem;font-weight:900;color:#009952;text-transform:uppercase;letter-spacing:.12em;margin:.9rem 0 .55rem;display:flex;align-items:center;gap:8px;}
.section-title::before{content:'';display:block;width:3px;height:16px;background:#00C06B;border-radius:4px;}

.metric-card{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;padding:14px 16px;position:relative;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.04);}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#00C06B,#009952);}
.metric-label{font-size:.68rem;font-weight:800;color:#64748B;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;}
.metric-value{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.55rem;font-weight:900;color:#0F172A;line-height:1.1;margin-bottom:4px;}
.metric-meta{font-size:.78rem;color:#64748B;}

.chart-card{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;padding:12px 16px 6px;margin-bottom:.65rem;}

/* Force LIGHT dataframe look */
[data-testid="stDataFrame"]{background:#FFFFFF!important;border:1px solid #E2E8F0!important;border-radius:14px!important;}
[data-testid="stDataFrame"] *{color:#0F172A!important;}
[data-testid="stDataFrame"] div[role="grid"]{background:#FFFFFF!important;}
[data-testid="stDataFrame"] div[role="row"]{background:#FFFFFF!important;}
[data-testid="stDataFrame"] div[role="columnheader"]{background:#F5F7FA!important;color:#64748B!important;font-weight:900!important;}
[data-testid="stDataFrame"] div[role="gridcell"]{background:#FFFFFF!important;}

/* Download buttons — force white label text (robust selectors) */
[data-testid="stDownloadButton"] button,
[data-testid="stDownloadButton"] button * ,
.stDownloadButton button,
.stDownloadButton button * {
  color: #FFFFFF !important;
  fill: #FFFFFF !important;
}

/* Keep your dark background too (optional) */
[data-testid="stDownloadButton"] button,
.stDownloadButton button {
  background: #2F3241 !important;
  border: none !important;
  border-radius: 12px !important;
  font-weight: 900 !important;
}

/* Buttons — main content */
.stButton>button{background:#00C06B!important;color:#fff!important;border:none!important;border-radius:12px!important;font-weight:900!important;padding:.62rem 1rem!important;}
.stButton>button:hover{background:#009952!important;}
.stButton>button:focus{outline:none!important;box-shadow:0 0 0 3px rgba(0,192,107,.22)!important;}

/* Sidebar buttons — subtle ghost style */
section[data-testid="stSidebar"] .stButton>button{background:#F5F7FA!important;color:#64748B!important;border:1px solid #E2E8F0!important;border-radius:8px!important;font-weight:500!important;font-size:.80rem!important;padding:.4rem .75rem!important;}
section[data-testid="stSidebar"] .stButton>button:hover{background:#E6F9F0!important;border-color:#00C06B!important;color:#009952!important;}

/* Reset filters — extra subtle, text-link feel */
.sb-reset-wrap .stButton>button{background:transparent!important;color:#94A3B8!important;border:none!important;font-size:.72rem!important;font-weight:400!important;padding:.2rem .5rem!important;text-decoration:underline!important;text-underline-offset:3px!important;box-shadow:none!important;}
.sb-reset-wrap .stButton>button:hover{color:#64748B!important;background:transparent!important;}

/* ---- Expander Container (Closed + Open) ---- */
[data-testid="stExpander"] {
    background: #FFFFFF !important;
    border: 1px solid rgba(15,23,42,.08) !important;
    border-radius: 14px !important;
    box-shadow: none !important;
    overflow: hidden !important;
}

/* ---- Expander Header ---- */
[data-testid="stExpander"] summary {
    background: #FFFFFF !important;
    font-weight: 600 !important;
    color: #0F172A !important;
}

/* ---- Expander Body When Open ---- */
[data-testid="stExpander"] > div {
    background: #FFFFFF !important;
}

/* Remove dark gradient when open */
[data-testid="stExpander"] div[role="region"] {
    background: #FFFFFF !important;
}

/* AI row — all buttons same subtle ghost style */
.ai-presets .stButton>button{background:#F8FAFC!important;color:#64748B!important;border:1px solid #E9EEF4!important;border-radius:999px!important;font-weight:400!important;padding:.3rem .7rem!important;font-size:.78rem!important;height:32px!important;line-height:1!important;transition:all .15s ease!important;box-shadow:none!important;}
.ai-presets .stButton>button:hover{background:#EEF2F7!important;border-color:#CBD5E1!important;color:#334155!important;}
/* Ask button — slightly more visible but still subtle */
.ai-presets [data-testid="stButton"]:nth-last-child(2) button{background:#F1F5F9!important;color:#1E293B!important;border:1px solid #CBD5E1!important;border-radius:999px!important;font-weight:600!important;}
.ai-row-spacer{height:.6rem;}

/* AI input — remove black baseweb accent */
.stTextInput>div>[data-baseweb="base-input"]{border:1.5px solid #E2E8F0!important;border-radius:12px!important;background:#FFFFFF!important;box-shadow:none!important;}
.stTextInput>div>[data-baseweb="base-input"]:focus-within{border-color:#00C06B!important;box-shadow:0 0 0 3px rgba(0,192,107,.10)!important;outline:none!important;}
.stTextInput>div>div>input{background:transparent!important;color:#0F172A!important;border:none!important;padding:.72rem .9rem!important;font-size:.92rem!important;box-shadow:none!important;outline:none!important;}

/* Reset button */
.reset-wrap .stButton>button{background:#F5F7FA!important;color:#64748B!important;border:1px solid #E2E8F0!important;font-weight:500!important;}
.reset-wrap .stButton>button:hover{background:#F1F5F9!important;}

/* Export icon buttons — all sidebar download buttons */
[data-testid="stSidebar"] [data-testid="stDownloadButton"]>button{background:transparent!important;border:1px solid #E2E8F0!important;border-radius:8px!important;color:#64748B!important;font-size:.75rem!important;font-weight:500!important;padding:3px 10px!important;min-height:0!important;height:26px!important;line-height:1!important;width:auto!important;}
[data-testid="stSidebar"] [data-testid="stDownloadButton"]>button:hover{border-color:#00C06B!important;color:#00C06B!important;background:transparent!important;}

/* Refresh button — subtle green, compact */
.refresh-wrap .stButton>button{background:transparent!important;border:1px solid #00C06B!important;border-radius:8px!important;color:#00C06B!important;font-size:.75rem!important;font-weight:500!important;padding:3px 10px!important;min-height:0!important;height:26px!important;width:auto!important;}
.refresh-wrap .stButton>button:hover{background:#E6F9F0!important;}

/* AI answer cards — minimal genie style */
.ai-answer{background:#FAFBFC;border:1px solid #EEF2F7;border-radius:14px;padding:16px 18px;margin:.5rem 0;box-shadow:none;}

/* KPI row — inline, no boxes */
.ai-kpi-row{display:flex;gap:28px;flex-wrap:wrap;margin-top:10px;padding-top:10px;border-top:1px solid #F1F5F9;}
.ai-kpi{flex:1;min-width:100px;}
.ai-kpi .k{font-size:.68rem;font-weight:400;color:#94A3B8;letter-spacing:.03em;}
.ai-kpi .v{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.15rem;font-weight:600;color:#1E293B;margin-top:2px;}

/* Pills — very subtle */
.ai-pill{display:inline-block;background:#F1F5F9;color:#475569;border:none;border-radius:999px;font-weight:500;font-size:.68rem;padding:2px 9px;margin-right:4px;}
.ai-pill-muted{background:#F8FAFC;color:#94A3B8;}

/* Action items — minimal left-border list */
.ai-actions{display:flex;flex-direction:column;gap:4px;margin-top:8px;}
.ai-action{background:transparent;border-left:2px solid #E2E8F0;padding:5px 10px;}
.ai-action .t{font-weight:500;font-size:.85rem;color:#334155;}
.ai-action .d{color:#94A3B8;font-size:.80rem;margin-top:1px;line-height:1.35;}



/* Sidebar Alerts (better UI) */
.sb-alerts{margin-top:10px;}
.sb-alerts h3{margin:.4rem 0 .35rem;font-family:'Plus Jakarta Sans',sans-serif;font-size:1.05rem;font-weight:900;color:var(--nexo-text);}

.sb-alerts-title{margin:.4rem 0 .35rem;font-family:'Plus Jakarta Sans',sans-serif;font-size:1.05rem;font-weight:900;color:var(--nexo-text);}

.sb-alert{background:var(--nexo-panel);border:1px solid var(--nexo-border);border-radius:14px;padding:12px 12px;margin:10px 0;box-shadow:0 2px 10px rgba(0,0,0,.04);position:relative;overflow:hidden;border-left:6px solid var(--nexo-border);}
.sb-alert:hover{transform:translateY(-1px);transition:transform .12s ease;}
.sb-alert.sev-green{border-left-color:var(--nexo-green);background:linear-gradient(0deg,rgba(0,192,107,.07),rgba(0,192,107,.07)),var(--nexo-panel);}
.sb-alert.sev-amber{border-left-color:var(--nexo-amber);background:linear-gradient(0deg,rgba(245,158,11,.08),rgba(245,158,11,.08)),var(--nexo-panel);}
.sb-alert.sev-red{border-left-color:var(--nexo-red);background:linear-gradient(0deg,rgba(239,68,68,.08),rgba(239,68,68,.08)),var(--nexo-panel);}

.sb-alert-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:6px;}
.sb-alert-left{display:flex;align-items:center;gap:10px;min-width:0;}
.sb-alert-dot{width:10px;height:10px;border-radius:999px;flex:0 0 auto;box-shadow:0 0 0 4px rgba(0,0,0,.03);}
.sb-alert-dot.dot-green{background:var(--nexo-green);box-shadow:0 0 0 4px rgba(0,192,107,.14);}
.sb-alert-dot.dot-amber{background:var(--nexo-amber);box-shadow:0 0 0 4px rgba(245,158,11,.16);}
.sb-alert-dot.dot-red{background:var(--nexo-red);box-shadow:0 0 0 4px rgba(239,68,68,.16);}

.sb-alert-name{font-weight:900;font-size:.95rem;color:var(--nexo-text);line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sb-alert-detail{font-size:.90rem;color:var(--nexo-muted);line-height:1.35;}
.sb-alert-action{margin-top:8px;font-size:.90rem;color:var(--nexo-text);background:rgba(255,255,255,.55);border:1px dashed var(--nexo-border);border-radius:12px;padding:10px;}
.sb-alert-action b{font-weight:900;}

.sb-alert-pill{font-size:.70rem;font-weight:900;padding:2px 10px;border-radius:999px;border:1px solid var(--nexo-border);background:var(--nexo-bg);color:var(--nexo-muted);white-space:nowrap;}
.sb-pill-red{background:rgba(239,68,68,.10);border-color:rgba(239,68,68,.35);color:var(--nexo-red);}
.sb-pill-amber{background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.35);color:var(--nexo-amber);}
.sb-pill-green{background:rgba(0,192,107,.10);border-color:rgba(0,192,107,.35);color:var(--nexo-green-dk);}
.sb-alert-desc{color:var(--nexo-muted);font-size:.86rem;line-height:1.25;margin:4px 0 0 0;}
.sb-alert-action{margin-top:8px;border-top:1px dashed var(--nexo-border);padding-top:8px;font-size:.86rem;line-height:1.25;}
.sb-alert-action b{font-weight:900;color:var(--nexo-text);}

/* ==========================================================
   SIDEBAR — CLEAN, COMPACT, SUBTLE
   ========================================================== */

/* Sidebar internal padding */
section[data-testid="stSidebar"] .block-container {
  padding: .5rem .85rem 1rem !important;
}

/* Remove extra top gap */
section[data-testid="stSidebar"] > div:first-child {
  padding-top: 0 !important;
}

/* Tight widget spacing */
section[data-testid="stSidebar"] .element-container {
  margin: 0 0 .18rem 0 !important;
}

/* Subtle labels */
section[data-testid="stSidebar"] label {
  margin-bottom: .1rem !important;
}
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
  <span class="nexo-badge">Healthcare Analytics</span>
</div>
''', unsafe_allow_html=True)

# ==========================================================
# SIDEBAR + FILTERS
# ==========================================================
def list_unique(col: str):
    return sorted(DATA[col].dropna().astype(str).unique().tolist())

with st.sidebar:

    # --- Navigation ---
    page = st.radio("Navigation", ["Dashboard", "AI Agent"], key="nav")

    # --- Export icons (top of sidebar, filled after data loads) ---
    _exp_row = st.columns([1, 1, 3])
    with _exp_row[0]:
        _export_csv_slot = st.empty()
    with _exp_row[1]:
        _export_pdf_slot = st.empty()

    st.markdown("---")
    # --------------------------------------------------
    # State init (kept here for stability)
    # --------------------------------------------------
    if "demo_scenario" not in st.session_state:
        st.session_state["demo_scenario"] = "None"
    if "dismiss_quick" not in st.session_state:
        st.session_state["dismiss_quick"] = False

    # --------------------------------------------------
    # Reset flag — must be checked BEFORE widgets render
    # so Streamlit allows overwriting widget-bound keys
    # --------------------------------------------------
    if st.session_state.pop("_reset_filters", False):
        st.session_state["f_start"]   = MIN_DATE
        st.session_state["f_end"]     = MAX_DATE
        st.session_state["f_sources"] = ["All"]
        st.session_state["f_channel"] = "All"
        st.session_state["f_campaign"] = "All"

    # Init filter keys only if not already set
    if "f_start" not in st.session_state:
        st.session_state["f_start"] = MIN_DATE
    if "f_end" not in st.session_state:
        st.session_state["f_end"] = MAX_DATE
    if "f_sources" not in st.session_state:
        st.session_state["f_sources"] = ["All"]
    if "f_channel" not in st.session_state:
        st.session_state["f_channel"] = "All"
    if "f_campaign" not in st.session_state:
        st.session_state["f_campaign"] = "All"

    d1, d2 = st.columns(2)
    with d1:
        start = st.date_input("Start Date", value=st.session_state["f_start"], key="f_start")
    with d2:
        end   = st.date_input("End Date",   value=st.session_state["f_end"],   key="f_end")

    sources = ["All"] + list_unique("data_source")
    if "Practice CRM" not in sources:
        sources.append("Practice CRM")
    sources_selected = st.multiselect("Data Source", options=sources, default=st.session_state["f_sources"], key="f_sources")
    if "All" in sources_selected:
        sources_selected = []
    c1, c2 = st.columns(2)
    with c1:
        channel_opts = ["All"] + list_unique("channel_group")
        channel = st.selectbox("Channel", channel_opts, index=(channel_opts.index(st.session_state["f_channel"]) if st.session_state["f_channel"] in channel_opts else 0), key="f_channel")
    with c2:
        camp_opts = ["All"] + list_unique("campaign")
        campaign = st.selectbox("Campaign", camp_opts, index=(camp_opts.index(st.session_state["f_campaign"]) if st.session_state["f_campaign"] in camp_opts else 0), key="f_campaign")

    # --------------------------------------------------
    # Reset filters — sets flag, reruns, flag clears
    # values BEFORE widgets render on next run
    # --------------------------------------------------
    st.markdown('<div class="sb-reset-wrap">', unsafe_allow_html=True)
    if st.button("Reset filters", use_container_width=True, key="reset_filters"):
        st.session_state["_reset_filters"] = True
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # --------------------------------------------------
    # Alerts (dropdown)
    # --------------------------------------------------
    with st.expander("Alerts", expanded=False):
        _alerts_slot = st.empty()

    # --------------------------------------------------
    # Refresh button — bottom of sidebar (Databricks only)
    # --------------------------------------------------
    if _DBX_MODE:
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="refresh-wrap">', unsafe_allow_html=True)
        if st.button("↺ Refresh", key="refresh_data"):
            load_data_databricks.clear()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

def apply_filters(df: pd.DataFrame, s: date, e: date, srcs, ch: str, camp: str) -> pd.DataFrame:
    out = df[(df["date"] >= s) & (df["date"] <= e)].copy()
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

CUR = apply_filters(DATA, start, end, sources_selected, channel, campaign)
PREV = apply_filters(DATA, prev_start, prev_end, sources_selected, channel, campaign)

practice_mode = (len(sources_selected) == 1 and str(sources_selected[0]).strip() == "Practice CRM")

# Marketing visuals should NOT include Practice CRM unless explicitly selected.
include_practice_in_marketing = practice_mode or ("Practice CRM" in [str(x).strip() for x in (sources_selected or [])])
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
    cur_rev   = _sum_col(cur_df, "total_revenue")
    prev_rev  = _sum_col(prev_df, "total_revenue")
    cur_spend = _sum_col(cur_df, "total_cost")
    prev_spend= _sum_col(prev_df, "total_cost")
    cur_leads = _sum_col(cur_df, "leads")
    prev_leads= _sum_col(prev_df, "leads")
    cur_book  = _sum_col(cur_df, "booked")
    prev_book = _sum_col(prev_df, "booked")
    cur_att   = _sum_col(cur_df, "attended")
    prev_att  = _sum_col(prev_df, "attended")

    cur_roas  = (cur_rev / cur_spend) if cur_spend > 0 else None
    prev_roas = (prev_rev / prev_spend) if prev_spend > 0 else None

    cur_show  = (cur_att / cur_book) if cur_book > 0 else None
    prev_show = (prev_att / prev_book) if prev_book > 0 else None

    alerts = []

    # 1) ROAS drop (spend-based)
    if (prev_roas is not None) and (cur_roas is not None) and prev_roas > 0:
        drop = (cur_roas - prev_roas) / prev_roas
        if drop <= -0.15:
            alerts.append((
                "Quick response", "sb-pill-red",
                "ROAS dropped",
                f"Down {abs(drop)*100:.0f}% vs prior period.",
                "Shift budget toward higher-return sources/campaigns and pause the lowest ROAS segments."
            ))

    # 2) Spend up while Leads down
    if prev_spend > 0 and prev_leads > 0:
        spend_up = (cur_spend - prev_spend) / prev_spend
        leads_dn = (cur_leads - prev_leads) / prev_leads
        if spend_up >= 0.12 and leads_dn <= -0.10:
            alerts.append((
                "Quick response", "sb-pill-amber",
                "Spend up, leads down",
                f"Spend up {spend_up*100:.0f}% while leads down {abs(leads_dn)*100:.0f}%.",
                "Audit targeting + landing pages, check tracking, and cap bids until CPL stabilizes."
            ))

    # 3) Show rate risk (booked → attended)
    if (cur_show is not None) and (prev_show is not None):
        delta = cur_show - prev_show
        if delta <= -0.07 or cur_show < 0.75:
            alerts.append((
                "Quick response", "sb-pill-amber",
                "Show rate risk",
                f"Show rate {cur_show*100:.0f}% (Δ {delta*100:+.0f} pts).",
                "Tighten confirmations/reminders, add 2-touch SMS, and verify scheduling capacity."
            ))

    # 4) Best ROAS channel to scale (exclude Practice CRM)
    try:
        s = cur_df.groupby("data_source", as_index=False).agg(
            total_revenue=("total_revenue","sum"),
            total_cost=("total_cost","sum")
        )
        s["roas"] = s.apply(lambda r: (r["total_revenue"]/r["total_cost"]) if r["total_cost"]>0 else 0.0, axis=1)
        s = s[s["data_source"].astype(str).str.lower() != "practice crm"]
        if len(s):
            best = s.sort_values("roas", ascending=False).iloc[0]
            if best["roas"] > 0:
                alerts.append((
                    "Opportunity", "sb-pill-green",
                    "Best channel to scale",
                    f"{best['data_source']} leads at {best['roas']:.2f}x ROAS.",
                    "Increase budget 10–20% and monitor ROAS + lead volume for 3–5 days."
                ))
    except Exception:
        pass

    # 5) Highest revenue campaign to protect
    try:
        c = cur_df.groupby("campaign", as_index=False).agg(total_revenue=("total_revenue","sum"), leads=("leads","sum"))
        if len(c):
            topc = c.sort_values("total_revenue", ascending=False).iloc[0]
            alerts.append((
                "Opportunity", "sb-pill-green",
                "Top campaign to protect",
                f"'{topc['campaign']}' is highest revenue in the range.",
                "Keep budget stable, refresh creatives if fatigue shows, and protect impression share."
            ))
    except Exception:
        pass

    while len(alerts) < 3:
        alerts.append((
            "Info", "sb-pill-green",
            "Healthy performance",
            "No major anomalies detected in the selected range.",
            "Keep monitoring ROAS, CPL, and show rate weekly."
        ))

    return alerts[:5]



# ---- Build alerts with safe fallback ----
try:
    _alerts = build_sidebar_alerts(CUR_MKT, PREV_MKT)
except Exception:
    _alerts = [("Info", "sb-pill-green", "Healthy", "No anomalies detected.", "Keep monitoring weekly.")]

# ---- Quick response banner ----
_quick = [a for a in _alerts if str(a[0]).lower().startswith("quick")]
if _quick and not st.session_state.get("dismiss_quick", False):
    _qt = _quick[0][2] if len(_quick[0]) > 2 else "Quick response needed"
    _qd = _quick[0][3] if len(_quick[0]) > 3 else ""
    _b1, _b2 = st.sidebar.columns([12, 1])
    with _b1:
        st.error(f"{_qt} — {_qd}".strip())
    with _b2:
        if st.button("✕", key="dismiss_quick_btn"):
            st.session_state["dismiss_quick"] = True
            st.rerun()

# ---- Alert HTML — always renders ----
_alert_html_parts = ['<div class="sb-alerts">', '<div class="sb-alerts-title">Alerts</div>']
for _sev, _pill_cls, _title, _detail, _action in _alerts:
    _sev_cls = "sev-green" if _pill_cls == "sb-pill-green" else ("sev-amber" if _pill_cls == "sb-pill-amber" else "sev-red")
    _dot_cls = "dot-green" if _pill_cls == "sb-pill-green" else ("dot-amber" if _pill_cls == "sb-pill-amber" else "dot-red")
    _alert_html_parts.append(
        f'<div class="sb-alert {_sev_cls}">'
        f'  <div class="sb-alert-head">'
        f'    <div class="sb-alert-left"><span class="sb-alert-dot {_dot_cls}"></span><div class="sb-alert-name">{_title}</div></div>'
        f'    <div class="sb-alert-pill {_pill_cls}">{_sev}</div>'
        f'  </div>'
        f'  <div class="sb-alert-detail">{_detail}</div>'
        f'  <div class="sb-alert-action"><b>Action:</b> {_action}</div>'
        f'</div>'
    )
_alert_html_parts.append("</div>")
_alert_html_str = "".join(_alert_html_parts)
try:
    _alerts_slot.markdown(_alert_html_str, unsafe_allow_html=True)
except Exception:
    st.sidebar.markdown(_alert_html_str, unsafe_allow_html=True)

# ---- Export: CSV immediately, PDF cached on filter state ----
try:
    import io as _io

    @st.cache_data(show_spinner=False)
    def _build_pdf_cached(_df_bytes: bytes, _start, _end, _sources, _channel, _campaign,
                          _practice: bool, _page: str):
        """PDF generation — cached per filter combination, never reruns on same filters."""
        import io
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd

        export_df = pd.read_csv(io.StringIO(_df_bytes.decode("utf-8")))
        if "date" in export_df.columns:
            export_df["date"] = pd.to_datetime(export_df["date"], errors="coerce").dt.date

        view_title = "Practice CRM View" if _practice else ("AI Agent View" if _page.lower().startswith("ai") else "Dashboard View")

        def _fig_to_image(fig, width=7.2, height=2.2):
            buf_img = io.BytesIO()
            fig.set_size_inches(width, height)
            fig.tight_layout()
            fig.savefig(buf_img, format="png", dpi=180, bbox_inches="tight")
            plt.close(fig)
            buf_img.seek(0)
            return Image(buf_img, width=width*inch, height=height*inch)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, title="NexoBI Demo Export")
        styles = getSampleStyleSheet()
        elems = []
        elems.append(Paragraph(f"NexoBI — {view_title}", styles["Title"]))
        elems.append(Paragraph(f"Date range: {_start} → {_end}", styles["Normal"]))
        elems.append(Paragraph(f"Sources: {_sources or 'All'}", styles["Normal"]))
        elems.append(Paragraph(f"Channel: {_channel} | Campaign: {_campaign}", styles["Normal"]))
        elems.append(Spacer(1, 12))

        rev    = float(export_df["total_revenue"].sum()) if "total_revenue" in export_df.columns else 0.0
        spend  = float(export_df["total_cost"].sum())    if "total_cost"    in export_df.columns else 0.0
        leads  = float(export_df["leads"].sum())         if "leads"         in export_df.columns else 0.0
        booked = float(export_df["booked"].sum())        if "booked"        in export_df.columns else 0.0
        att    = float(export_df["attended"].sum())      if "attended"      in export_df.columns else 0.0
        roas   = (rev / spend) if spend > 0 else 0.0
        show   = (att / booked) if booked > 0 else 0.0

        elems.append(Paragraph("Performance Overview", styles["Heading2"]))
        kpi_data = [
            ["Metric", "Value"],
            ["Revenue", f"${rev:,.0f}"], ["Spend", f"${spend:,.0f}"],
            ["ROAS", f"{roas:.2f}x"],    ["Leads", f"{leads:,.0f}"],
            ["Booked", f"{booked:,.0f}"],["Attended", f"{att:,.0f}"],
            ["Show Rate", f"{show*100:.1f}%"],
        ]
        t = Table(kpi_data, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,0), colors.whitesmoke),
            ("GRID",       (0,0),(-1,-1), 0.5, colors.lightgrey),
            ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTNAME",   (0,0),(0,-1), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0),(-1,-1), 9),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.Color(0.97,0.97,0.97)]),
        ]))
        elems.append(t)
        elems.append(Spacer(1, 14))

        if "date" in export_df.columns:
            agg = export_df.groupby("date", as_index=False).agg(
                Revenue=("total_revenue","sum"), Leads=("leads","sum") if "leads" in export_df.columns else ("date","size"), Spend=("total_cost","sum")
            ).sort_values("date")
            if "total_revenue" in export_df.columns and len(agg) >= 2:
                fig = plt.figure(); plt.plot(agg["date"], agg["Revenue"]); plt.title("Revenue over time"); plt.xticks(rotation=25, ha="right"); elems.append(_fig_to_image(fig)); elems.append(Spacer(1,10))
            if len(agg) >= 2:
                fig = plt.figure(); plt.plot(agg["date"], agg["Leads"]); plt.title("Leads over time"); plt.xticks(rotation=25, ha="right"); elems.append(_fig_to_image(fig)); elems.append(Spacer(1,10))
            if "data_source" in export_df.columns and "total_cost" in export_df.columns:
                bys = export_df.groupby("data_source", as_index=False)["total_cost"].sum().sort_values("total_cost", ascending=False).head(10)
                if len(bys) >= 1:
                    fig = plt.figure(); plt.bar(bys["data_source"].astype(str), bys["total_cost"]); plt.title("Spend by Source"); plt.xticks(rotation=25, ha="right"); elems.append(_fig_to_image(fig, height=2.5)); elems.append(Spacer(1,14))

        if all(c in export_df.columns for c in ["data_source","sessions","leads","booked","attended","total_revenue","total_cost"]):
            elems.append(Paragraph("Patient Journey by Source", styles["Heading2"]))
            j = export_df.groupby("data_source", as_index=False).agg(Sessions=("sessions","sum"),Leads=("leads","sum"),Booked=("booked","sum"),Attended=("attended","sum"),Revenue=("total_revenue","sum"),Spend=("total_cost","sum"))
            j["Lead Rate"] = (j["Leads"]/j["Sessions"]).replace([float("inf")],0).fillna(0)*100
            j["Book Rate"] = (j["Booked"]/j["Leads"]).replace([float("inf")],0).fillna(0)*100
            j["Show Rate"] = (j["Attended"]/j["Booked"]).replace([float("inf")],0).fillna(0)*100
            j["ROAS"]      = (j["Revenue"]/j["Spend"]).replace([float("inf")],0).fillna(0)
            j = j.sort_values("Revenue", ascending=False).head(12)
            hdr = list(j.columns)
            rows = [[str(r["data_source"]),f"{r['Sessions']:.0f}",f"{r['Leads']:.0f}",f"{r['Booked']:.0f}",f"{r['Attended']:.0f}",f"${r['Revenue']:,.0f}",f"${r['Spend']:,.0f}",f"{r['Lead Rate']:.1f}%",f"{r['Book Rate']:.1f}%",f"{r['Show Rate']:.1f}%",f"{r['ROAS']:.2f}x"] for _,r in j.iterrows()]
            tbl = Table([hdr]+rows, hAlign="LEFT"); tbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),("GRID",(0,0),(-1,-1),0.4,colors.lightgrey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7.5)])); elems.append(tbl); elems.append(Spacer(1,14))

        if all(c in export_df.columns for c in ["campaign","total_revenue","total_cost","leads"]):
            elems.append(Paragraph("Top Campaigns", styles["Heading2"]))
            tc = export_df.groupby("campaign", as_index=False).agg(Revenue=("total_revenue","sum"),Spend=("total_cost","sum"),Leads=("leads","sum"))
            tc["ROAS"] = (tc["Revenue"]/tc["Spend"]).replace([float("inf")],0).fillna(0)
            tc = tc.sort_values("Revenue", ascending=False).head(12)
            rows2 = [["Campaign","Revenue","Spend","Leads","ROAS"]] + [[str(r["campaign"]),f"${r['Revenue']:,.0f}",f"${r['Spend']:,.0f}",f"{r['Leads']:,.0f}",f"{r['ROAS']:.2f}x"] for _,r in tc.iterrows()]
            tbl2 = Table(rows2, hAlign="LEFT"); tbl2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),("GRID",(0,0),(-1,-1),0.4,colors.lightgrey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8)])); elems.append(tbl2)

        doc.build(elems)
        return buf.getvalue()

    # CSV is always cheap — generate immediately
    csv_bytes = CUR.to_csv(index=False).encode("utf-8")
    # PDF is cached per filter state — only rebuilds when filters change
    _src_str = ",".join(sorted([str(x) for x in sources_selected])) if sources_selected else "All"
    pdf_bytes = _build_pdf_cached(
        csv_bytes, str(start), str(end), _src_str, channel, campaign, practice_mode, str(page)
    )

    try:
        _export_csv_slot.download_button(
            "↓ CSV", data=csv_bytes,
            file_name=f"nexobi_export_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv", use_container_width=True, key="dl_csv"
        )
        _export_pdf_slot.download_button(
            "↓ PDF", data=pdf_bytes,
            file_name=f"nexobi_report_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf", use_container_width=True, key="dl_pdf"
        )
    except Exception:
        st.sidebar.download_button("↓ CSV", data=csv_bytes,
                                   file_name=f"nexobi_export_{datetime.now().strftime('%Y%m%d')}.csv",
                                   mime="text/csv", key="dl_csv_fb")
        st.sidebar.download_button("↓ PDF", data=pdf_bytes,
                                   file_name=f"nexobi_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                                   mime="application/pdf", key="dl_pdf_fb")

except Exception:
    pass

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
# DASHBOARD
# ==========================================================
def render_marketing():
    # --- current + prior period totals (CSV mode) ---
    base = CUR_MKT if not practice_mode else CUR
    prev_base = PREV_MKT if not practice_mode else PREV


    has_prev = len(prev_base) > 0

    spend    = float(base["total_cost"].sum() or 0)
    revenue  = float(base["total_revenue"].sum() or 0)
    leads    = float(base["leads"].sum() or 0)
    sessions = float(base["sessions"].sum() or 0)
    booked   = float(base["booked"].sum() or 0)
    attended = float(base["attended"].sum() or 0)

    roas = safe_div(revenue, spend)
    show_rate = safe_div(attended, booked) * 100

    prev_rev   = float(prev_base["total_revenue"].sum() or 0)
    prev_leads = float(prev_base["leads"].sum() or 0)
    rev_chg = safe_div(revenue - prev_rev, max(abs(prev_rev), 0.01)) * 100
    lds_chg = safe_div(leads - prev_leads, max(abs(prev_leads), 0.01)) * 100

    st.markdown('<div class="section-title">Performance Overview</div>', unsafe_allow_html=True)
    for col,(label,value,meta) in zip(st.columns(5),[
        ("Revenue", money(revenue), delta_html(rev_chg, has_prev)),
        ("Ad Spend", money(spend), f'<span style="color:{MUTED};font-size:.8rem;">Total investment</span>'),
        ("ROAS", f"{roas:.2f}x", f'<span style="color:{MUTED};font-size:.8rem;">Return on ad spend</span>'),
        ("Leads", fmt(leads), delta_html(lds_chg, has_prev)),
        ("Show Rate", pct(show_rate), f'<span style="color:{MUTED};font-size:.8rem;">{fmt(attended)}/{fmt(booked)} booked</span>'),
    ]):
        with col:
            st.markdown(f'''
              <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
                <div class="metric-meta">{meta}</div>
              </div>
            ''', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Trends</div>', unsafe_allow_html=True)
    trend = base.groupby("date", as_index=False).agg(
        revenue=("total_revenue","sum"),
        leads=("leads","sum")
    ).sort_values("date")

    if len(trend) > 0:
        trend["date"] = pd.to_datetime(trend["date"])
        c1,c2 = st.columns(2)
        with c1:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.plotly_chart(plot_line(trend,"date","revenue","Revenue Over Time", color=GREEN), use_container_width=True, config={"displayModeBar":False})
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.plotly_chart(plot_line(trend,"date","leads","Leads Over Time", color=BLUE), use_container_width=True, config={"displayModeBar":False})
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Performance by Source</div>', unsafe_allow_html=True)
    mix = base.groupby("data_source", as_index=False).agg(
        revenue=("total_revenue","sum"),
        spend=("total_cost","sum"),
        leads=("leads","sum")
    ).sort_values("revenue", ascending=False)

    if len(mix) > 0:
        c1,c2,c3 = st.columns(3)
        with c1:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.plotly_chart(plot_bar(mix,"data_source","revenue","Revenue by Source",GREEN), use_container_width=True, config={"displayModeBar":False})
            st.markdown('</div>', unsafe_allow_html=True)
      
        with c2:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)

            # Remove Organic Search (robust version)
            mix_filtered = mix[
            ~mix["data_source"]
            .astype(str)
            .str.strip()
            .str.lower()
            .str.contains("organic")
        ]

            st.plotly_chart(
                plot_bar(
                    mix_filtered,
                    "data_source",
                    "spend",
                    "Spend by Source",
                    BLUE
                ),
                use_container_width=True,
                config={"displayModeBar": False}
    )

    st.markdown('</div>', unsafe_allow_html=True)
    
    with c3:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.plotly_chart(plot_bar(mix,"data_source","leads","Leads by Source",AMBER), use_container_width=True, config={"displayModeBar":False})
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Patient Journey by Source</div>', unsafe_allow_html=True)
    journey = base.groupby("data_source", as_index=False).agg(
        Sessions=("sessions","sum"),
        Leads=("leads","sum"),
        Booked=("booked","sum"),
        Attended=("attended","sum"),
        Revenue=("total_revenue","sum"),
        Spend=("total_cost","sum"),
    )
    journey["Lead Rate"] = np.where(journey["Sessions"]>0, journey["Leads"]/journey["Sessions"]*100, 0)
    journey["Book Rate"] = np.where(journey["Leads"]>0, journey["Booked"]/journey["Leads"]*100, 0)
    journey["Show Rate"] = np.where(journey["Booked"]>0, journey["Attended"]/journey["Booked"]*100, 0)
    journey["ROAS"] = np.where(journey["Spend"]>0, journey["Revenue"]/journey["Spend"], 0)
    journey = journey.sort_values("Revenue", ascending=False)

    jd = journey.copy()
    jd.insert(0, "Source", jd.pop("data_source"))
    jd["Sessions"]=jd["Sessions"].apply(fmt)
    jd["Leads"]=jd["Leads"].apply(fmt)
    jd["Booked"]=jd["Booked"].apply(fmt)
    jd["Attended"]=jd["Attended"].apply(fmt)
    jd["Lead Rate"]=jd["Lead Rate"].apply(lambda x: f"{x:.1f}%")
    jd["Book Rate"]=jd["Book Rate"].apply(lambda x: f"{x:.1f}%")
    jd["Show Rate"]=jd["Show Rate"].apply(lambda x: f"{x:.1f}%")
    jd["Revenue"]=jd["Revenue"].apply(money)
    jd["Spend"]=jd["Spend"].apply(money)
    jd["ROAS"]=jd["ROAS"].apply(lambda x: f"{x:.2f}x")
    st.dataframe(df_light(jd), use_container_width=True, hide_index=True, height=df_height(len(jd)))

    with st.expander("Top Campaigns", expanded=False):
        camps = base[base["campaign"].astype(str).str.strip().ne("")].groupby("campaign", as_index=False).agg(
            Revenue=("total_revenue","sum"),
            Spend=("total_cost","sum"),
            Leads=("leads","sum"),
        )
        camps["ROAS"] = np.where(camps["Spend"]>0, camps["Revenue"]/camps["Spend"], 0)
        camps = camps.sort_values("Revenue", ascending=False).head(15)
        if len(camps) > 0:
            out = camps.rename(columns={"campaign":"Campaign"}).copy()
            out["Revenue"]=out["Revenue"].apply(money)
            out["Spend"]=out["Spend"].apply(money)
            out["Leads"]=out["Leads"].apply(fmt)
            out["ROAS"]=out["ROAS"].apply(lambda x: f"{x:.2f}x")
            st.dataframe(df_light(out), use_container_width=True, hide_index=True, height=df_height(len(out)))

def render_practice():
    st.markdown('<div class="section-title">Practice CRM · Patient Dashboard</div>', unsafe_allow_html=True)

    # --- current + prior period totals (CSV mode) ---
    np_ = float(CUR["conversions"].sum() or 0)
    bk  = float(CUR["booked"].sum() or 0)
    at  = float(CUR["attended"].sum() or 0)
    rev = float(CUR["total_revenue"].sum() or 0)

    prev_p = float(PREV["conversions"].sum() or 0)
    prev_r = float(PREV["total_revenue"].sum() or 0)


    has_prev = len(PREV) > 0

    show = safe_div(at, bk) * 100
    book = safe_div(bk, np_) * 100

    rc = safe_div(rev - prev_r, max(abs(prev_r), 0.01))*100
    pc = safe_div(np_ - prev_p, max(abs(prev_p), 0.01))*100

    for col,(label,value,meta) in zip(st.columns(5),[
        ("New Patients", fmt(np_), delta_html(pc, has_prev)),
        ("Booked", fmt(bk), f'<span style="color:{MUTED};font-size:.8rem;">Book rate:{pct(book)}</span>'),
        ("Attended", fmt(at), f'<span style="color:{MUTED};font-size:.8rem;">Show rate:{pct(show)}</span>'),
        ("Revenue", money(rev), delta_html(rc, has_prev)),
        ("Rev/Patient", money(safe_div(rev,np_)), f'<span style="color:{MUTED};font-size:.8rem;">Per patient</span>'),
    ]):
        with col:
            st.markdown(f'''
              <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
                <div class="metric-meta">{meta}</div>
              </div>
            ''', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Attendance Trend</div>', unsafe_allow_html=True)
    trend = CUR.groupby("date", as_index=False).agg(booked=("booked","sum"), attended=("attended","sum")).sort_values("date")
    if len(trend) > 0:
        trend["date"] = pd.to_datetime(trend["date"])
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=trend["date"], y=trend["booked"], name="Booked", mode="lines", line=dict(color=BLUE, width=2.5)))
        fig.add_trace(go.Scatter(x=trend["date"], y=trend["attended"], name="Attended", mode="lines", line=dict(color=GREEN, width=2.5)))
        fig.update_layout(**base_layout("Booked vs Attended", 280))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
        st.markdown('</div>', unsafe_allow_html=True)

    
    # --- Treatment Movers (Phase 3B) ---
    if "treatment" in CUR.columns:
        cur_t = CUR.dropna(subset=["treatment"]).copy()
        prev_t = PREV.dropna(subset=["treatment"]).copy() if len(PREV) else pd.DataFrame(columns=cur_t.columns)
        if len(cur_t) > 0:
            cur_g = cur_t.groupby("treatment", as_index=False).agg(
                Patients=("conversions", "sum"),
                Booked=("booked", "sum"),
                Attended=("attended", "sum"),
                Revenue=("total_revenue", "sum"),
            )
            cur_g["Show Rate"] = cur_g.apply(lambda r: safe_div(r["Attended"], r["Booked"]) * 100, axis=1)
            cur_g["Rev/Patient"] = cur_g.apply(lambda r: safe_div(r["Revenue"], r["Patients"]), axis=1)

            if len(prev_t) > 0:
                prev_g = prev_t.groupby("treatment", as_index=False).agg(
                    Patients_p=("conversions", "sum"),
                    Booked_p=("booked", "sum"),
                    Attended_p=("attended", "sum"),
                    Revenue_p=("total_revenue", "sum"),
                )
                prev_g["Show Rate_p"] = prev_g.apply(lambda r: safe_div(r["Attended_p"], r["Booked_p"]) * 100, axis=1)
                prev_g["Rev/Patient_p"] = prev_g.apply(lambda r: safe_div(r["Revenue_p"], r["Patients_p"]), axis=1)
                movers = cur_g.merge(prev_g[["treatment","Show Rate_p","Rev/Patient_p","Patients_p"]], on="treatment", how="left")
            else:
                movers = cur_g.copy()
                movers["Show Rate_p"] = np.nan
                movers["Rev/Patient_p"] = np.nan
                movers["Patients_p"] = np.nan

            movers["Δ Rev/Patient"] = movers.apply(lambda r: safe_div(r["Rev/Patient"] - (r["Rev/Patient_p"] if pd.notna(r["Rev/Patient_p"]) else 0), max(abs(r["Rev/Patient_p"]), 0.01)) * 100 if pd.notna(r["Rev/Patient_p"]) else np.nan, axis=1)
            movers["Δ Show Rate (pp)"] = movers.apply(lambda r: (r["Show Rate"] - r["Show Rate_p"]) if pd.notna(r["Show Rate_p"]) else np.nan, axis=1)

            # filter for meaningful sample
            movers_f = movers[movers["Patients"] >= 20].copy() if len(movers) else movers
            if len(movers_f) > 0:
                st.markdown('<div class="section-title">Treatment Movers</div>', unsafe_allow_html=True)

                # Capacity risk signal (simple)
                if len(PREV) > 0:
                    overall_book_chg = safe_div(bk - float(PREV["booked"].sum() or 0), max(abs(float(PREV["booked"].sum() or 0)), 0.01)) * 100
                    overall_show_pp = show - (safe_div(float(PREV["attended"].sum() or 0), float(PREV["booked"].sum() or 0)) * 100 if float(PREV["booked"].sum() or 0) > 0 else show)
                    if overall_book_chg >= 15 and overall_show_pp <= -5:
                        st.warning("Capacity risk: bookings are up while show rate is down. Consider tightening scheduling confirmation + resourcing high-demand treatments.")

                c1, c2 = st.columns(2)
                with c1:
                    top_up = movers_f.sort_values("Δ Rev/Patient", ascending=False).head(5)
                    top_dn = movers_f.sort_values("Δ Rev/Patient", ascending=True).head(5)
                    mini = pd.concat([top_up, top_dn], axis=0)
                    mini = mini.reset_index(drop=True)
                    mini = mini[["treatment","Rev/Patient","Rev/Patient_p","Δ Rev/Patient","Patients"]].rename(columns={"treatment":"Treatment"})
                    mini["Rev/Patient"] = mini["Rev/Patient"].apply(money)
                    mini["Rev/Patient_p"] = mini["Rev/Patient_p"].apply(lambda x: money(x) if pd.notna(x) else "—")
                    mini["Δ Rev/Patient"] = mini["Δ Rev/Patient"].apply(lambda x: f"{x:+.0f}%" if pd.notna(x) else "—")
                    mini["Patients"] = mini["Patients"].apply(fmt)
                    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                    st.markdown('<div style="font-weight:950;color:%s;margin-bottom:6px;">Rev/Patient movers (Top ±)</div>' % INK, unsafe_allow_html=True)
                    if mini.empty:
                        st.info('Not enough treatment volume in this window to compute movers. Try widening the date range.')
                    else:
                        st.dataframe(df_light(mini), use_container_width=True, hide_index=True, height=df_height(len(mini), max_h=360))
                    st.markdown('</div>', unsafe_allow_html=True)

                with c2:
                    top_up = movers_f.sort_values("Δ Show Rate (pp)", ascending=False).head(5)
                    top_dn = movers_f.sort_values("Δ Show Rate (pp)", ascending=True).head(5)
                    mini = pd.concat([top_up, top_dn], axis=0)
                    mini = mini.reset_index(drop=True)
                    mini = mini[["treatment","Show Rate","Show Rate_p","Δ Show Rate (pp)","Booked"]].rename(columns={"treatment":"Treatment"})
                    mini["Show Rate"] = mini["Show Rate"].apply(lambda x: f"{float(x or 0):.1f}%")
                    mini["Show Rate_p"] = mini["Show Rate_p"].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "—")
                    mini["Δ Show Rate (pp)"] = mini["Δ Show Rate (pp)"].apply(lambda x: f"{x:+.1f} pp" if pd.notna(x) else "—")
                    mini["Booked"] = mini["Booked"].apply(fmt)
                    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                    st.markdown('<div style="font-weight:950;color:%s;margin-bottom:6px;">Show rate movers (Top ±)</div>' % INK, unsafe_allow_html=True)
                    if mini.empty:
                        st.info('Not enough treatment volume in this window to compute movers. Try widening the date range.')
                    else:
                        st.dataframe(df_light(mini), use_container_width=True, hide_index=True, height=df_height(len(mini), max_h=360))
                    st.markdown('</div>', unsafe_allow_html=True)

    # --- Treatment table (Practice CRM only) ---
    if "treatment" in CUR.columns:
        st.markdown('<div class="section-title">Patient Journey by Treatment</div>', unsafe_allow_html=True)
        tj = CUR.dropna(subset=["treatment"]).copy()
        if len(tj) > 0:
            grp = tj.groupby("treatment", as_index=False).agg(
                Patients=("conversions","sum"),
                Booked=("booked","sum"),
                Attended=("attended","sum"),
                Revenue=("total_revenue","sum"),
                Spend=("total_cost","sum"),
            )
            grp["Book Rate"] = grp.apply(lambda r: safe_div(r["Booked"], r["Patients"]) * 100, axis=1)
            grp["Show Rate"] = grp.apply(lambda r: safe_div(r["Attended"], r["Booked"]) * 100, axis=1)
            grp["Rev/Patient"] = grp.apply(lambda r: safe_div(r["Revenue"], r["Patients"]), axis=1)
            grp = grp.sort_values("Revenue", ascending=False).head(25)

            show_df = grp.rename(columns={"treatment":"Treatment"}).copy()
            show_df["Patients"] = show_df["Patients"].apply(fmt)
            show_df["Booked"] = show_df["Booked"].apply(fmt)
            show_df["Attended"] = show_df["Attended"].apply(fmt)
            show_df["Revenue"] = show_df["Revenue"].apply(money)
            show_df["Spend"] = show_df["Spend"].apply(money)
            show_df["Book Rate"] = show_df["Book Rate"].apply(lambda x: f"{float(x or 0):.1f}%")
            show_df["Show Rate"] = show_df["Show Rate"].apply(lambda x: f"{float(x or 0):.1f}%")
            show_df["Rev/Patient"] = show_df["Rev/Patient"].apply(money)
            st.dataframe(df_light(show_df), use_container_width=True, hide_index=True, height=df_height(len(show_df)))
        else:
            st.info("No treatment rows available for the selected date range.")


# ==========================================================
# AI AGENT (DETERMINISTIC)
# ==========================================================
MONTHS={"january":1,"jan":1,"february":2,"feb":2,"march":3,"mar":3,"april":4,"apr":4,"may":5,"june":6,"jun":6,"july":7,"jul":7,"august":8,"aug":8,"september":9,"sep":9,"sept":9,"october":10,"oct":10,"november":11,"nov":11,"december":12,"dec":12}

def parse_dates(q: str, gmin: date, gmax: date):
    ql = norm(q)
    m = re.search(r"last\s+(\d+)\s+days?", ql)
    if m:
        n = max(1, min(3650, int(m.group(1))))
        return gmax - timedelta(days=n-1), gmax, f"Last {n} days"
    if "mtd" in ql or "month to date" in ql or "this month" in ql:
        s = gmax.replace(day=1)
        return s, gmax, "Month-to-date"
    if "last month" in ql:
        first = gmax.replace(day=1)
        prev_end = first - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        return prev_start, prev_end, "Last month"
    m2 = re.search(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(\s+\d{4})?\b", ql)
    if m2:
        mon = MONTHS.get(m2.group(1))
        yr = int(m2.group(2).strip()) if m2.group(2) else gmax.year
        if mon:
            from calendar import monthrange
            s = date(yr, mon, 1)
            e = date(yr, mon, monthrange(yr, mon)[1])
            return max(s, gmin), min(e, gmax), f"{datetime(yr,mon,1).strftime('%B')} {yr}"
    return None, None, None

METRICS = {
    "revenue": dict(words=["revenue","rev","sales","income"], kind="sum", num="total_revenue"),
    "spend": dict(words=["spend","cost","adspend","ad spend","investment"], kind="sum", num="total_cost"),
    "sessions": dict(words=["sessions","session","traffic","visits"], kind="sum", num="sessions"),
    "leads": dict(words=["leads","lead","conversions","conversion"], kind="sum", num="conversions"),
    "booked": dict(words=["booked","booking","appointments","appt"], kind="sum", num="booked"),
    "attended": dict(words=["attended","attendance"], kind="sum", num="attended"),
    "roas": dict(words=["roas","return on ad spend","return"], kind="ratio", num="total_revenue", den="total_cost"),
    "cpa": dict(words=["cpa","cost per lead","cpl"], kind="ratio", num="total_cost", den="conversions"),
    "cvr": dict(words=["conversion rate","cvr","lead rate"], kind="ratio", num="conversions", den="sessions", mult=100.0),
    "show_rate": dict(words=["show rate","attendance rate"], kind="ratio", num="attended", den="booked", mult=100.0),
}

def fuzzy_metric(q: str) -> str:
    ql = norm(q)
    if "show rate" in ql or "attendance rate" in ql:
        return "show_rate"
    for k, meta in METRICS.items():
        for w in sorted(meta["words"], key=lambda x: -len(x)):
            if w in ql:
                return k
    tokens = [t for t in ql.split() if len(t) >= 3]
    candidates = []
    for k, meta in METRICS.items():
        for w in meta["words"]:
            candidates.append((k, w))
    best_k, best_s = "revenue", 0.0
    for t in tokens:
        for k, w in candidates:
            s = difflib.SequenceMatcher(None, t, w.replace(" ", "")).ratio()
            if s > best_s:
                best_s, best_k = s, k
    return best_k if best_s >= 0.72 else "revenue"

def metric_value(df: pd.DataFrame, metric_key: str) -> float:
    meta = METRICS[metric_key]
    if meta["kind"] == "sum":
        return float(df[meta["num"]].sum())
    num = float(df[meta["num"]].sum())
    den = float(df[meta["den"]].sum())
    base = safe_div(num, den)
    if "mult" in meta:
        base *= float(meta["mult"])
    return float(base)

def metric_format(metric_key: str, v: float) -> str:
    if metric_key in ["revenue","spend","cpa"]:
        return money(v)
    if metric_key == "roas":
        return f"{v:.2f}x"
    if metric_key in ["cvr","show_rate"]:
        return f"{v:.1f}%"
    return fmt(v)

def actions_for(metric_key: str, direction: str):
    if metric_key == "roas" and direction == "down":
        return [
            ("Cut waste spend", "Pause/limit the lowest-ROAS campaigns for 48h and reallocate to top performers."),
            ("Fix conversion path", "Check landing pages + forms (mobile speed, booking friction) to recover CVR."),
            ("Tighten targeting", "Exclude low-intent keywords/audiences; focus on high-intent treatment terms."),
            ("Audit tracking", "Validate revenue attribution + conversion events (misfires can mimic ROAS drops)."),
        ]
    if metric_key == "show_rate" and direction == "down":
        return [
            ("Confirm reminders", "Enable SMS + email reminders 24h and 2h before appointment."),
            ("Reduce no-shows", "Add deposits for high-no-show segments; confirm appointments same day."),
            ("Shorten time-to-visit", "Offer earlier slots; long lead times drive cancellations."),
            ("Staff follow-up", "Call high-value treatments within 10 minutes of booking."),
        ]
    return [
        ("Focus on top drivers", "Scale segments with the strongest positive impact."),
        ("Fix the weakest links", "Target biggest negative movers first for fast lift."),
        ("Monitor daily", "Watch the same metric over time to confirm stabilization."),
    ]

def compute_why(metric_key: str, s_d: date, e_d: date, note: str, base_df: pd.DataFrame):
    days = (e_d - s_d).days + 1
    p_s = s_d - timedelta(days=days)
    p_e = e_d - timedelta(days=days)

    cur = base_df[(base_df["date"] >= s_d) & (base_df["date"] <= e_d)]
    prev = base_df[(base_df["date"] >= p_s) & (base_df["date"] <= p_e)]

    cur_v  = metric_value(cur, metric_key)
    prev_v = metric_value(prev, metric_key)
    delta  = cur_v - prev_v
    pct_ch = safe_div(delta, max(abs(prev_v), 0.01)) * 100
    direction = "down" if delta < 0 else "up" if delta > 0 else "flat"

    # Drivers by data_source + channel_group only (keeps demo clean)
    drivers = []
    for dim in ["data_source", "channel_group", "campaign"]:
        # Robust driver computation across pandas versions (avoid groupby(..., as_index=False).apply(...))
        g1 = cur.groupby(dim).apply(lambda x: metric_value(x, metric_key)).reset_index(name="value")
        g2 = prev.groupby(dim).apply(lambda x: metric_value(x, metric_key)).reset_index(name="value_prev")

        m = pd.merge(g1, g2, on=dim, how="outer").fillna(0)
        m["impact"] = m["value"] - m["value_prev"]

        # Limit rows for demo readability
        top_n = 5 if dim == "campaign" else 8
        m = m.sort_values("impact", ascending=True if delta < 0 else False).head(top_n).copy()
        drivers.append((dim, m))

    return {
        "current": cur_v, "prior": prev_v, "delta": delta, "pct": pct_ch,
        "direction": direction, "period": f"{s_d} → {e_d}", "note": note,
        "drivers": drivers,
        "actions": actions_for(metric_key, direction if direction != "flat" else "down"),
        "confidence": "High" if len(cur) > 20 else "Medium"
    }

def compute_compare(metric_key: str, s_d: date, e_d: date, base_df: pd.DataFrame, dim: str | None = None):
    """Generic current vs prior comparison. If dim is provided, returns movers by dim."""
    days = (e_d - s_d).days + 1
    p_s = s_d - timedelta(days=days)
    p_e = e_d - timedelta(days=days)
    cur = base_df[(base_df["date"] >= s_d) & (base_df["date"] <= e_d)]
    prev = base_df[(base_df["date"] >= p_s) & (base_df["date"] <= p_e)]

    cur_v  = metric_value(cur, metric_key)
    prev_v = metric_value(prev, metric_key)
    delta  = cur_v - prev_v
    pct_ch = safe_div(delta, max(abs(prev_v), 0.01)) * 100
    direction = "down" if delta < 0 else "up" if delta > 0 else "flat"

    movers = None
    if dim:
        # Pandas 2.x compatible — don't use reset_index(name=) on groupby result
        g1 = cur.groupby(dim).apply(lambda x: metric_value(x, metric_key)).reset_index()
        g1.columns = [dim, "value"]
        g2 = prev.groupby(dim).apply(lambda x: metric_value(x, metric_key)).reset_index()
        g2.columns = [dim, "value_prev"]
        m = pd.merge(g1, g2, on=dim, how="outer").fillna(0)
        m["impact"] = m["value"] - m["value_prev"]
        # If overall is down, show biggest negative movers first; else biggest positive movers first
        m = m.sort_values("impact", ascending=True if delta < 0 else False)
        movers = m

    return {
        "current": cur_v,
        "prior": prev_v,
        "delta": delta,
        "pct": pct_ch,
        "direction": direction,
        "period": f"{s_d} → {e_d}",
        "prior_period": f"{p_s} → {p_e}",
        "movers": movers,
        "confidence": "High" if len(cur) > 20 else "Medium",
    }

def quick_recos(metric_key: str, direction: str):
    """Short, executive recommendations for non-"why" answers."""
    direction = direction if direction in ("up","down") else "down"
    if metric_key == "revenue":
        return [
            ("Scale what works", "Shift budget toward the highest-ROAS sources/campaigns driving most revenue."),
            ("Protect conversion", "Spot-check landing pages + forms to avoid hidden CVR drops."),
            ("Prioritize high-value treatments", "Promote high Rev/Patient treatments to lift total revenue."),
        ]
    if metric_key == "spend":
        return [
            ("Re-balance budgets", "Cap spend on low-performing campaigns; set daily limits and reallocate."),
            ("Guardrails", "Add ROAS/CPA alerts + rules to prevent runaway spend."),
            ("Creative refresh", "If spend is rising without results, rotate creatives and audiences."),
        ]
    if metric_key == "roas":
        return actions_for("roas", direction)
    if metric_key == "cpa":
        if direction == "up":
            return [
                ("Reduce waste", "Tighten targeting and exclude low-intent queries/audiences."),
                ("Improve CVR", "Increase booking rate with shorter forms and faster follow-up."),
                ("Shift mix", "Reallocate budget to sources/campaigns with lower CPA."),
            ]
        return [
            ("Scale efficiently", "Increase budgets gradually on segments holding low CPA."),
            ("Keep quality", "Monitor show rate to ensure low CPA isn’t low-intent leads."),
            ("Expand winners", "Clone best campaigns into nearby geos / similar audiences."),
        ]
    if metric_key in ["cvr","show_rate"]:
        return actions_for("show_rate" if metric_key == "show_rate" else metric_key, direction)
    return actions_for(metric_key, direction)


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

        # Detect numeric columns available
        has = lambda c: c in df.columns and df[c].notna().any()

        # ---- helpers ----
        def _group_bar(group_col, val_col, title, fmt=","):
            if not (has(group_col) and has(val_col)):
                return None
            g = df.groupby(group_col)[val_col].sum().reset_index().sort_values(val_col, ascending=False).head(8)
            hover = "%{x}<br><b>$%{y:,.0f}</b><extra></extra>" if fmt == "$" else "%{x}<br><b>%{y:,.2f}</b><extra></extra>"
            palette = [GREEN, BLUE, AMBER, PURPLE, "#EC4899", "#14B8A6", "#F97316", RED]
            fig = go.Figure()
            for i, row in g.iterrows():
                fig.add_trace(go.Bar(
                    x=[str(row[group_col])], y=[row[val_col]],
                    name=str(row[group_col]),
                    marker_color=palette[list(g.index).index(i) % len(palette)],
                    marker_line_width=0,
                    showlegend=False,
                    hovertemplate=hover,
                ))
            fig.update_layout(**base_layout(title, 240))
            return fig

        def _line(val_col, title):
            if not (has("date") and has(val_col)):
                return None
            g = df.groupby("date")[val_col].sum().reset_index().sort_values("date")
            return plot_line(g, "date", val_col, title, height=240)

        # ---- Route by question intent ----
        if any(w in q for w in ["trend", "over time", "daily", "weekly", "by day", "by month", "timeline"]):
            col = "revenue" if "revenue" in q else ("ad_spend" if any(w in q for w in ["spend", "cost"]) else "revenue")
            title = "Revenue Over Time" if col == "revenue" else "Spend Over Time"
            return _line(col, title)

        if "roas" in q:
            if has("data_source") and has("roas"):
                g = df.groupby("data_source")["roas"].mean().reset_index().sort_values("roas", ascending=False).head(8)
                return plot_bar_multi(g, "data_source", "roas", "ROAS by Source")
            return None

        if any(w in q for w in ["spend", "cost", "budget"]):
            return _group_bar("data_source", "ad_spend", "Ad Spend by Source", "$")

        if any(w in q for w in ["lead", "patient", "appointment"]):
            col = "new_patients" if "patient" in q else ("appointments" if "appoint" in q else "leads")
            col = col if has(col) else ("leads" if has("leads") else None)
            if col:
                return _group_bar("data_source", col, f"{col.replace('_', ' ').title()} by Source")

        if any(w in q for w in ["channel"]):
            return _group_bar("channel_group", "revenue", "Revenue by Channel", "$")

        if any(w in q for w in ["compare", "vs", "versus", "google", "facebook", "meta"]):
            if has("data_source") and has("revenue"):
                g = df.groupby("data_source")["revenue"].sum().reset_index().sort_values("revenue", ascending=False).head(6)
                return plot_bar_multi(g, "data_source", "revenue", "Revenue Comparison by Source")

        # Default: revenue by source
        if has("data_source") and has("revenue"):
            return _group_bar("data_source", "revenue", "Revenue by Source", "$")

    except Exception:
        pass
    return None


# ==========================================================
# AI QUERY CLIENT  (uses existing SQL connector — no extra permissions)
# ==========================================================
def _build_data_context() -> str:
    """Return a compact summary of the loaded dataset for use as AI context."""
    try:
        df = DATA.copy()
        parts = []
        if "Date" in df.columns:
            parts.append(f"Date range: {df['Date'].min()} to {df['Date'].max()}, {len(df)} rows")
        num_cols = ["Revenue", "Ad Spend", "ROAS", "Leads", "New Patients", "Appointments"]
        for col in num_cols:
            if col in df.columns:
                parts.append(f"{col}: total={df[col].sum():,.1f}, avg={df[col].mean():,.2f}")
        if "Source" in df.columns:
            top = df.groupby("Source")["Revenue"].sum().nlargest(4).to_dict()
            parts.append("Revenue by source: " + ", ".join(f"{k}=${v:,.0f}" for k, v in top.items()))
        if "Channel" in df.columns:
            top_ch = df.groupby("Channel")["Revenue"].sum().nlargest(3).to_dict()
            parts.append("Revenue by channel: " + ", ".join(f"{k}=${v:,.0f}" for k, v in top_ch.items()))
        return "; ".join(parts) if parts else "Healthcare practice marketing analytics data"
    except Exception:
        return "Healthcare practice marketing analytics data"


# Model endpoint confirmed available in this workspace
_MODEL_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"


def ai_query_ask(question: str) -> dict:
    """
    Answer a question using Databricks ai_query() SQL function.
    Runs over the existing SQL connector — no Genie permissions needed.
    """
    from databricks import sql as _dbsql

    endpoint = _MODEL_ENDPOINT
    context  = _build_data_context()
    prompt = (
        "You are a concise marketing analytics assistant for a healthcare practice. "
        f"Current dataset summary: {context}. "
        f"Answer in 2-3 clear sentences: {question}"
    )
    prompt_sql = prompt.replace("'", "''")
    sql = f"SELECT ai_query('{endpoint}', '{prompt_sql}') AS answer"

    try:
        token = os.environ.get("DATABRICKS_TOKEN", "")
        with _dbsql.connect(
            server_hostname=DATABRICKS_HOST,
            http_path=DATABRICKS_HTTP_PATH,
            access_token=token
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                answer = rows[0][0] if rows else "No response received."

        return {"text": answer, "sql": sql, "df": None, "error": None}

    except Exception as exc:
        return {"text": "", "sql": sql, "df": None, "error": str(exc)}


def render_ai():
    st.markdown(f"""<p style="font-family:'Plus Jakarta Sans',sans-serif;font-size:1.3rem;font-weight:700;color:{TEXT};margin:0 0 .2rem;">Ask your data anything</p>""", unsafe_allow_html=True)
    st.markdown(f"""<p style="color:{MUTED};font-size:.88rem;margin:.0rem 0 .9rem;">Powered by Databricks AI &mdash; live queries on your data.</p>""", unsafe_allow_html=True)

    if "ai_history" not in st.session_state:
        st.session_state.ai_history = []
    if "ai_nonce" not in st.session_state:
        st.session_state.ai_nonce = 0
    if "ai_preset" not in st.session_state:
        st.session_state.ai_preset = None

    # 3 suggested prompts — pill style
    presets = [
        "Revenue last 30 days",
        "ROAS by source",
        "Compare Google vs Facebook",
    ]

    # Full-width input
    user_q = st.text_input(
        "",
        placeholder="e.g. What was ROAS last 30 days?",
        label_visibility="collapsed",
        key=f"ai_input_{st.session_state.ai_nonce}"
    )

    # Presets + Ask + Clear in one row below input
    st.markdown("<div class=\"ai-presets\">", unsafe_allow_html=True)
    _pr1, _pr2, _pr3, _askcol, _clearcol = st.columns([2.4, 2.4, 2.4, 1.6, 1.1])
    for col, p in zip([_pr1, _pr2, _pr3], presets):
        with col:
            if st.button(p, use_container_width=True, key=f"ai_p_{p}"):
                st.session_state.ai_preset = p
                st.rerun()
    with _askcol:
        ask = st.button("Ask", use_container_width=True, key="ai_ask")
    with _clearcol:
        reset = st.button("Clear", use_container_width=True, key="ai_reset", type="secondary")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class=\"ai-row-spacer\"></div>", unsafe_allow_html=True)

    if reset:
        st.session_state.ai_history = []
        st.session_state.ai_nonce  += 1
        st.session_state.ai_preset  = None
        st.rerun()

    run_q = None
    if st.session_state.ai_preset:
        run_q = st.session_state.ai_preset
        st.session_state.ai_preset = None
    elif ask and user_q.strip():
        run_q = user_q.strip()

    # ---- Call AI and store result ----
    if run_q:
        with st.spinner("Thinking..."):
            result = ai_query_ask(run_q)

        st.session_state.ai_history.insert(0, {"q": run_q, **result})
        if len(st.session_state.ai_history) > 10:
            st.session_state.ai_history = st.session_state.ai_history[:10]
        st.rerun()

    # ---- Render conversation history ----
    for item in st.session_state.ai_history:
        q     = item.get("q", "")
        text  = item.get("text", "")
        sql   = item.get("sql", "")
        df    = item.get("df")
        error = item.get("error")

        # Question header
        st.markdown(f"""
        <div class="ai-answer">
          <div style="font-size:.72rem;font-weight:600;color:{MUTED};letter-spacing:.03em;">You asked</div>
          <div style="font-family:'Plus Jakarta Sans',sans-serif;font-weight:700;font-size:1.1rem;margin-top:.1rem;color:{TEXT};">{q}</div>
        </div>
        """, unsafe_allow_html=True)

        if error:
            st.error(f"AI error: {error}")
            continue

        # Natural language answer
        if text:
            st.markdown(f"""
            <div style="color:{TEXT};font-size:.92rem;line-height:1.65;margin:.35rem 0 .5rem;
                        padding:12px 16px;background:#FAFBFC;border-radius:10px;
                        border-left:3px solid #E2E8F0;">
              {text}
            </div>
            """, unsafe_allow_html=True)

        # Auto-generated chart based on question
        chart = _ai_chart(q)
        if chart is not None:
            st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})

        # Data table from query result
        if df is not None and not df.empty:
            st.dataframe(
                df_light(df),
                use_container_width=True,
                hide_index=True,
                height=df_height(len(df))
            )

        # Collapsible SQL
        if sql:
            with st.expander("View SQL", expanded=False):
                st.code(sql, language="sql")

# ==========================================================
# ROUTER
# ==========================================================

# ==========================================================
# STORY MODE — Scenario banner (only when applied)
# ==========================================================
scn_active = st.session_state.get("demo_scenario", "None")
if scn_active and scn_active != "None":
    story_map = {
        "ROAS drop week": {
            "title": "Story Mode: ROAS Drop",
            "look": ["Performance Overview (ROAS + Spend)", "Performance by Source (find the drag)", "Top Campaigns (identify the culprit)"],
            "qs": ["Why did ROAS change last 30 days?", "ROAS by source MTD", "Why did leads drop last month?"],
        },
        "Revenue growth month": {
            "title": "Story Mode: Revenue Growth",
            "look": ["Revenue KPI (delta vs prior)", "Trends (revenue lift timing)", "Top Campaigns (what scaled)"],
            "qs": ["Why did revenue change MTD?", "Revenue by source last 30 days", "Why did ROAS change last 30 days?"],
        },
        "Show rate risk (CRM)": {
            "title": "Story Mode: Show Rate Risk",
            "look": ["Practice KPIs (Booked vs Attended)", "Booked vs Attended trend", "Treatment Movers (show-rate movers)"],
            "qs": ["Why did show rate change last 30 days?", "Why did booked change last 30 days?", "Why did revenue change last month?"],
        },
    }
    meta = story_map.get(scn_active, None)
    if meta:
        st.markdown(
            f"""
            <div style="background:{GREEN_LT};border:1px solid rgba(0,0,0,.06);border-left:5px solid {GREEN};border-radius:14px;padding:12px 14px;margin:6px 0 12px;">
              <div style="font-weight:900;letter-spacing:.2px;margin-bottom:4px;">{meta['title']}</div>
              <div style="color:{MUTED};font-size:.92rem;margin-bottom:8px;">
                <b>What to look at:</b> {' · '.join(meta['look'])}
              </div>
              <div style="font-size:.92rem;">
                <b>Great AI questions:</b> {' · '.join(meta['qs'])}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

if page == "Dashboard":
    if practice_mode:
        render_practice()
    else:
        render_marketing()
else:
    render_ai()
