

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

# Industry benchmarks — healthcare marketing averages
BENCH_ROAS      = 2.8    # Avg paid media ROAS for healthcare
BENCH_CPL       = 45.0   # Avg cost per lead ($)
BENCH_SHOW_RATE = 78.0   # Avg appointment show rate (%)
BENCH_LEAD_GRO  = 10.0   # Expected lead growth % vs prior

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

/* Buttons — main content (neutral white base) */
.stButton>button{background:#FFFFFF!important;color:#0F172A!important;border:1.5px solid #E2E8F0!important;border-radius:12px!important;font-weight:600!important;padding:.6rem 1rem!important;box-shadow:0 1px 3px rgba(0,0,0,.04)!important;transition:all .14s!important;}
.stButton>button:hover{background:#F8FAFC!important;border-color:#CBD5E1!important;}
.stButton>button:focus{outline:none!important;box-shadow:0 0 0 3px rgba(0,192,107,.18)!important;}
/* Primary action buttons (Send, etc.) — explicitly green */
[data-testid="baseButton-primary"]{background:#00C06B!important;color:#fff!important;border:none!important;box-shadow:0 2px 8px rgba(0,192,107,.28)!important;}
[data-testid="baseButton-primary"]:hover{background:#009952!important;}

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

/* === AI AGENT — hero welcome screen === */
.ai-hero{position:relative;text-align:center;padding:3.2rem 0 2rem;overflow:hidden;}
.ai-hero::before{content:'';position:absolute;top:50%;left:50%;transform:translate(-50%,-56%);width:560px;height:260px;background:radial-gradient(ellipse at center,rgba(0,192,107,.08) 0%,rgba(59,130,246,.04) 55%,transparent 75%);pointer-events:none;border-radius:50%;}
/* Catchphrase main text */
.ai-catch{font-family:'Plus Jakarta Sans',sans-serif;font-size:3.5rem;font-weight:900;color:#0F172A;line-height:1.1;margin-bottom:.55rem;position:relative;}
.ai-catch-hi{background:linear-gradient(120deg,#00C06B 0%,#3B82F6 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.ai-catch-sub{font-size:.78rem;color:#94A3B8;font-weight:500;letter-spacing:.1em;text-transform:uppercase;position:relative;}
/* Preset cards — :has() sibling from marker */
[data-testid="stMarkdownContainer"]:has(#ai-cards-marker)+[data-testid="stHorizontalBlock"] .stButton>button{background:#FFFFFF!important;border:1.5px solid #E2E8F0!important;border-radius:16px!important;padding:1.15rem 1.1rem!important;min-height:90px!important;height:auto!important;text-align:left!important;font-size:.87rem!important;font-weight:600!important;box-shadow:0 2px 14px rgba(0,0,0,.05)!important;transition:all .16s!important;line-height:1.45!important;white-space:normal!important;width:100%!important;}
[data-testid="stMarkdownContainer"]:has(#ai-cards-marker)+[data-testid="stHorizontalBlock"] .stButton>button:hover{box-shadow:0 8px 28px rgba(0,0,0,.11)!important;transform:translateY(-2px)!important;}
[data-testid="stMarkdownContainer"]:has(#ai-cards-marker)+[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(1) .stButton>button{border-top:3px solid #00C06B!important;background:linear-gradient(155deg,#F0FDF4 0%,#FFFFFF 42%)!important;color:#065F46!important;}
[data-testid="stMarkdownContainer"]:has(#ai-cards-marker)+[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(2) .stButton>button{border-top:3px solid #3B82F6!important;background:linear-gradient(155deg,#EFF6FF 0%,#FFFFFF 42%)!important;color:#1E40AF!important;}
[data-testid="stMarkdownContainer"]:has(#ai-cards-marker)+[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:nth-child(3) .stButton>button{border-top:3px solid #8B5CF6!important;background:linear-gradient(155deg,#F5F3FF 0%,#FFFFFF 42%)!important;color:#4C1D95!important;}
/* "New chat" button in active header — scoped by column marker */
[data-testid="stColumn"]:has(#ai-newchat-marker) .stButton>button{background:transparent!important;border:1px solid #E2E8F0!important;border-radius:8px!important;color:#64748B!important;font-size:.74rem!important;font-weight:400!important;padding:.2rem .65rem!important;height:auto!important;min-height:0!important;box-shadow:none!important;}
[data-testid="stColumn"]:has(#ai-newchat-marker) .stButton>button:hover{border-color:#CBD5E1!important;color:#475569!important;background:#F8FAFC!important;}
/* Chat bubbles */
.ai-bubble-user{display:flex;justify-content:flex-end;margin:.65rem 0 .15rem;}
.ai-bubble-user span{background:#1E293B;color:#F1F5F9;border-radius:16px 16px 4px 16px;padding:9px 15px;font-size:.86rem;font-weight:500;max-width:75%;line-height:1.45;display:inline-block;}
.ai-bubble-ai{background:#FFFFFF;border:1px solid #F1F5F9;border-radius:4px 16px 16px 16px;padding:14px 17px;margin:.1rem 0 .55rem;font-size:.88rem;color:#1E293B;line-height:1.65;box-shadow:0 1px 6px rgba(0,0,0,.04);}

/* AI input — fully override baseweb (aggressive selectors to kill black border) */
.stTextInput [data-baseweb="base-input"],
.stTextInput [data-baseweb="input"],
div[data-baseweb="base-input"],
div[data-baseweb="input"]{border:1px solid #E8EEF4!important;border-radius:14px!important;background:#FAFBFC!important;box-shadow:none!important;outline:none!important;transition:border-color .15s!important;}
.stTextInput [data-baseweb="base-input"]:focus-within,
div[data-baseweb="base-input"]:focus-within{border-color:#00C06B!important;box-shadow:0 0 0 3px rgba(0,192,107,.07)!important;background:#FFFFFF!important;}
.stTextInput input,.stTextInput textarea{background:transparent!important;color:#0F172A!important;border:none!important;outline:none!important;box-shadow:none!important;padding:.72rem .9rem!important;font-size:.92rem!important;}
/* Align send button column to bottom of input row — scoped to AI input row only */
[data-testid="stMarkdownContainer"]:has(#ai-send-row)+[data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child{display:flex!important;flex-direction:column!important;justify-content:flex-end!important;}
/* Primary button height matches input */
[data-testid="baseButton-primary"]{height:44px!important;min-height:44px!important;font-size:.88rem!important;font-weight:700!important;border-radius:12px!important;letter-spacing:.01em!important;padding:0 1rem!important;}
/* Story card primary buttons — slightly compact */
[data-testid="stMarkdownContainer"]:has(#story-cards-row)+[data-testid="stHorizontalBlock"] [data-testid="baseButton-primary"]{height:36px!important;min-height:36px!important;font-size:.78rem!important;font-weight:600!important;}

/* Reset button */
.reset-wrap .stButton>button{background:#F5F7FA!important;color:#64748B!important;border:1px solid #E2E8F0!important;font-weight:500!important;}
.reset-wrap .stButton>button:hover{background:#F1F5F9!important;}

/* Export icon buttons — all sidebar download buttons */
[data-testid="stSidebar"] [data-testid="stDownloadButton"]>button{background:transparent!important;border:1px solid #E2E8F0!important;border-radius:8px!important;color:#64748B!important;font-size:.75rem!important;font-weight:500!important;padding:3px 10px!important;min-height:0!important;height:26px!important;line-height:1!important;width:auto!important;}
[data-testid="stSidebar"] [data-testid="stDownloadButton"]>button:hover{border-color:#00C06B!important;color:#00C06B!important;background:transparent!important;}

/* Refresh button — subtle green, compact */
.refresh-wrap .stButton>button{background:transparent!important;border:1px solid #00C06B!important;border-radius:8px!important;color:#00C06B!important;font-size:.75rem!important;font-weight:500!important;padding:3px 10px!important;min-height:0!important;height:26px!important;width:auto!important;}
.refresh-wrap .stButton>button:hover{background:#E6F9F0!important;}


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



/* Sidebar alert cards */
.nexo-alert{border-radius:10px;padding:9px 11px;margin:5px 0;border-left:4px solid #E2E8F0;background:#FAFBFC;}
.nexo-alert.sev-green{border-left-color:#00C06B;background:rgba(0,192,107,.05);}
.nexo-alert.sev-amber{border-left-color:#F59E0B;background:rgba(245,158,11,.06);}
.nexo-alert.sev-red{border-left-color:#EF4444;background:rgba(239,68,68,.06);}
.nexo-alert-row{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:3px;}
.nexo-alert-title{font-size:.8rem;font-weight:700;color:#0F172A;}
.nexo-alert-pill{font-size:.64rem;font-weight:700;padding:1px 7px;border-radius:999px;white-space:nowrap;}
.sb-pill-red{background:rgba(239,68,68,.10);color:#EF4444;}
.sb-pill-amber{background:rgba(245,158,11,.12);color:#D97706;}
.sb-pill-green{background:rgba(0,192,107,.10);color:#009952;}
.nexo-alert-detail{font-size:.76rem;color:#64748B;line-height:1.35;}
.nexo-alert-action{font-size:.73rem;color:#0F172A;margin-top:4px;padding-top:4px;border-top:1px solid rgba(0,0,0,.06);line-height:1.35;}
.nexo-alert-action b{font-weight:700;}

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

/* Tab text — always legible, green when active */
.stTabs [data-baseweb="tab"]{color:#0F172A!important;font-weight:500!important;font-size:.88rem!important;}
.stTabs [data-baseweb="tab"][aria-selected="true"]{color:#00C06B!important;font-weight:700!important;}
.stTabs [data-baseweb="tab-highlight"]{background:#00C06B!important;}
.stTabs [data-baseweb="tab-border"]{background:#E2E8F0!important;}

/* ===== STORY MODE CARDS ===== */
.story-card{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;padding:14px 16px 10px;position:relative;overflow:hidden;transition:box-shadow .18s,border-color .18s;margin-bottom:.3rem;}
.story-card.story-card-active{border-color:#00C06B!important;box-shadow:0 0 0 2.5px rgba(0,192,107,.18)!important;}
.story-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:#E2E8F0;}
.story-card.sc-red::before{background:#EF4444;}
.story-card.sc-green::before{background:#00C06B;}
.story-card.sc-amber::before{background:#F59E0B;}
.sc-pill{display:inline-block;font-size:.64rem;font-weight:800;padding:2px 8px;border-radius:999px;text-transform:uppercase;letter-spacing:.07em;}
.sc-pill-red{background:rgba(239,68,68,.10);color:#EF4444;}
.sc-pill-green{background:rgba(0,192,107,.10);color:#009952;}
.sc-pill-amber{background:rgba(245,158,11,.12);color:#D97706;}
.sc-title{font-family:'Plus Jakarta Sans',sans-serif;font-size:.88rem;font-weight:800;color:#0F172A;margin:6px 0 4px;line-height:1.25;}
.sc-desc{font-size:.75rem;color:#64748B;line-height:1.4;margin-bottom:4px;}
.sc-active-badge{display:inline-block;background:#E6F9F0;color:#009952;border:1px solid rgba(0,192,107,.25);border-radius:999px;font-size:.62rem;font-weight:800;padding:1px 8px;margin-left:5px;vertical-align:middle;}

/* ===== INTELLIGENCE SIGNALS ===== */
.sig-card{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:11px 14px;position:relative;overflow:hidden;}
.sig-card.sig-red{border-left:3.5px solid #EF4444;background:linear-gradient(90deg,rgba(239,68,68,.03) 0%,#FFFFFF 55%);}
.sig-card.sig-amber{border-left:3.5px solid #F59E0B;background:linear-gradient(90deg,rgba(245,158,11,.04) 0%,#FFFFFF 55%);}
.sig-card.sig-green{border-left:3.5px solid #00C06B;background:linear-gradient(90deg,rgba(0,192,107,.04) 0%,#FFFFFF 55%);}
.sig-head{display:flex;align-items:flex-start;justify-content:space-between;gap:6px;margin-bottom:3px;}
.sig-title{font-size:.8rem;font-weight:700;color:#0F172A;flex:1;line-height:1.3;}
.sig-sev{font-size:.61rem;font-weight:800;padding:1px 7px;border-radius:999px;white-space:nowrap;flex-shrink:0;}
.sig-sev-red{background:rgba(239,68,68,.10);color:#EF4444;}
.sig-sev-amber{background:rgba(245,158,11,.12);color:#D97706;}
.sig-sev-green{background:rgba(0,192,107,.10);color:#009952;}
.sig-detail{font-size:.73rem;color:#64748B;line-height:1.35;margin-bottom:4px;}
.sig-action{font-size:.71rem;color:#334155;line-height:1.35;padding-top:4px;border-top:1px solid rgba(0,0,0,.06);}

/* ===== COMPLIANCE BADGES (header) ===== */
.comply-badge{border-radius:999px;font-size:.63rem;font-weight:800;padding:2px 9px;letter-spacing:.04em;}
.comply-hipaa{background:#F0FDF4;color:#15803D;border:1px solid #BBF7D0;}
.comply-soc2{background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE;}

/* ===== COMMAND CENTER ===== */
.cmd-health{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:16px;padding:16px 20px;display:flex;align-items:center;gap:20px;margin-bottom:.75rem;flex-wrap:wrap;}
.cmd-score-ring{display:flex;flex-direction:column;align-items:center;justify-content:center;width:68px;height:68px;border-radius:50%;border:3.5px solid #00C06B;flex-shrink:0;}
.cmd-score-num{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.45rem;font-weight:900;line-height:1;}
.cmd-score-den{font-size:.6rem;color:#94A3B8;font-weight:500;}
.cmd-health-stat{flex:1;min-width:100px;border-left:1px solid #F1F5F9;padding-left:18px;}
.cmd-health-label{font-size:.63rem;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:2px;}
.cmd-health-val{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.05rem;font-weight:800;color:#0F172A;}
.cmd-health-sub{font-size:.70rem;color:#64748B;margin-top:1px;}

/* Benchmark tiles */
.bench-tile{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;padding:14px 16px;position:relative;overflow:hidden;}
.bench-tile::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.bt-good::before{background:#00C06B;} .bt-warn::before{background:#F59E0B;} .bt-bad::before{background:#EF4444;}
.bench-label{font-size:.65rem;font-weight:800;color:#94A3B8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px;}
.bench-val{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.4rem;font-weight:900;color:#0F172A;line-height:1.1;margin-bottom:3px;}
.bench-delta{font-size:.74rem;font-weight:700;}
.bench-avg{font-size:.69rem;color:#94A3B8;margin-top:2px;}

/* KPI benchmark row */
.metric-bench{font-size:.70rem;color:#94A3B8;margin-top:5px;padding-top:4px;border-top:1px solid rgba(0,0,0,.05);}

/* Integration strip */
.integ-strip{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:12px 16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:.55rem;}
.integ-badge{display:inline-flex;align-items:center;gap:5px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:4px 11px;font-size:.74rem;font-weight:600;color:#475569;}
.integ-dot{width:7px;height:7px;border-radius:50%;background:#00C06B;display:inline-block;flex-shrink:0;}
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
  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
    <span class="nexo-badge">Healthcare Analytics</span>
    <span class="comply-badge comply-hipaa">HIPAA</span>
    <span class="comply-badge comply-soc2">SOC 2</span>
  </div>
</div>
''', unsafe_allow_html=True)

# ==========================================================
# SIDEBAR + FILTERS
# ==========================================================
def list_unique(col: str):
    return sorted(DATA[col].dropna().astype(str).unique().tolist())

with st.sidebar:

    # --- Export downloads — very top of left panel ---
    _export_slot = st.empty()

    # --- Navigation ---
    page = st.radio("Navigation", ["Dashboard", "AI Agent"], key="nav")

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
    # Connected Platforms — seamless sidebar section
    # --------------------------------------------------
    st.markdown('''
<div style="margin-top:16px;padding-top:14px;border-top:1px solid #F1F5F9;">
  <div style="font-size:.64rem;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:.1em;margin-bottom:9px;">Connected Platforms</div>
  <div style="display:flex;flex-direction:column;gap:7px;">
    <div style="display:flex;align-items:center;gap:8px;">
      <div style="width:6px;height:6px;border-radius:50%;background:#00C06B;flex-shrink:0;"></div>
      <span style="font-size:.79rem;font-weight:500;color:#334155;">Google Ads</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <div style="width:6px;height:6px;border-radius:50%;background:#00C06B;flex-shrink:0;"></div>
      <span style="font-size:.79rem;font-weight:500;color:#334155;">Meta Ads</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <div style="width:6px;height:6px;border-radius:50%;background:#00C06B;flex-shrink:0;"></div>
      <span style="font-size:.79rem;font-weight:500;color:#334155;">GA4</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <div style="width:6px;height:6px;border-radius:50%;background:#00C06B;flex-shrink:0;"></div>
      <span style="font-size:.79rem;font-weight:500;color:#334155;">LinkedIn</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <div style="width:6px;height:6px;border-radius:50%;background:#00C06B;flex-shrink:0;"></div>
      <span style="font-size:.79rem;font-weight:500;color:#334155;">Dentrix</span>
    </div>
  </div>
</div>
''', unsafe_allow_html=True)

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

# ---- Alert HTML → sidebar slot ----
_alert_items = ""
for _sev, _pill_cls, _title, _detail, _action in _alerts:
    _sev_cls = "sev-green" if _pill_cls == "sb-pill-green" else ("sev-amber" if _pill_cls == "sb-pill-amber" else "sev-red")
    _alert_items += (
        f'<div class="nexo-alert {_sev_cls}">'
        f'  <div class="nexo-alert-row">'
        f'    <div class="nexo-alert-title">{_title}</div>'
        f'    <div class="nexo-alert-pill {_pill_cls}">{_sev}</div>'
        f'  </div>'
        f'  <div class="nexo-alert-detail">{_detail}</div>'
        f'  <div class="nexo-alert-action"><b>Action:</b> {_action}</div>'
        f'</div>'
    )
# (Alerts are now shown inline on the dashboard via render_signals / render_command_center)

# ---- Export: CSV only ----
csv_bytes = CUR.to_csv(index=False).encode("utf-8")

import base64 as _b64
_ico_down = ('<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:5px;">'
             '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>'
             '<polyline points="7 10 12 15 17 10"/>'
             '<line x1="12" y1="15" x2="12" y2="3"/></svg>')
_btn_style = ("display:inline-flex;align-items:center;padding:3px 10px;font-size:.73rem;font-weight:500;"
              "color:#64748B;border:1px solid #E2E8F0;border-radius:7px;"
              "text-decoration:none;background:#F8FAFC;font-family:'DM Sans',sans-serif;"
              "transition:border-color .15s,color .15s;")
_fname_csv = f"nexobi_export_{datetime.now().strftime('%Y%m%d')}.csv"
_csv_b64   = _b64.b64encode(csv_bytes).decode()
_csv_link  = (f'<a href="data:text/csv;base64,{_csv_b64}" download="{_fname_csv}" style="{_btn_style}">'
              f'{_ico_down}CSV</a>')
_export_slot.markdown(
    f'<div style="display:flex;justify-content:flex-start;align-items:center;'
    f'padding:4px 0 6px;border-bottom:1px solid #F1F5F9;margin-bottom:4px;">'
    f'{_csv_link}'
    f'</div>',
    unsafe_allow_html=True
)

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
    """0–100 health score weighted across ROAS, CPL, revenue growth, show rate."""
    try:
        rev   = float(cur_df["total_revenue"].sum() or 0)
        spend = float(cur_df["total_cost"].sum() or 0)
        leads = max(float(cur_df["leads"].sum() or 0), 0.01)
        att   = float(cur_df["attended"].sum() or 0)
        book  = max(float(cur_df["booked"].sum() or 0), 0.01)
        p_rev = float(prev_df["total_revenue"].sum() or 0)

        roas      = safe_div(rev, spend)
        cpl       = safe_div(spend, leads)
        show      = safe_div(att, book) * 100
        rev_growth = safe_div(rev - p_rev, max(abs(p_rev), 0.01)) * 100

        # 25 pts each
        roas_score = min(25, max(0, (roas / BENCH_ROAS) * 25))
        cpl_score  = min(25, max(0, (BENCH_CPL / max(cpl, 1)) * 25)) if cpl > 0 else 10
        show_score = min(25, max(0, (show / BENCH_SHOW_RATE) * 25))
        rev_score  = min(25, max(0, 12.5 + rev_growth * 0.65))

        return min(100, int(roas_score + cpl_score + show_score + rev_score))
    except Exception:
        return 72


# ==========================================================
# REVENUE FORECAST  (linear extrapolation, 30-day horizon)
# ==========================================================
def plot_forecast(df: pd.DataFrame, days_ahead: int = 30):
    """Returns (fig, projected_total) or (None, 0) if insufficient data."""
    try:
        daily = (df.groupby("date")["total_revenue"].sum()
                   .reset_index()
                   .sort_values("date"))
        daily["date"] = pd.to_datetime(daily["date"])
        if len(daily) < 5:
            return None, 0

        x = np.array([(d - daily["date"].iloc[0]).days for d in daily["date"]])
        y = daily["total_revenue"].values

        coeffs = np.polyfit(x, y, 1)

        # Future dates
        last_x    = x[-1]
        fut_x     = np.arange(last_x + 1, last_x + days_ahead + 1)
        fut_dates = [daily["date"].iloc[-1] + timedelta(days=int(i - last_x)) for i in fut_x]
        fut_y     = np.maximum(0, np.polyval(coeffs, fut_x))

        # Confidence band — ±1.5 residual std
        residuals = y - np.polyval(coeffs, x)
        band      = np.std(residuals) * 1.5
        upper     = fut_y + band
        lower     = np.maximum(0, fut_y - band)

        fig = go.Figure()

        # Confidence band
        fig.add_trace(go.Scatter(
            x=fut_dates + fut_dates[::-1],
            y=np.concatenate([upper, lower[::-1]]).tolist(),
            fill="toself",
            fillcolor="rgba(59,130,246,0.07)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip", name="band",
        ))
        # Actual revenue
        fig.add_trace(go.Scatter(
            x=daily["date"], y=y,
            name="Actual", mode="lines",
            line=dict(color=GREEN, width=2.5),
            fill="tozeroy", fillcolor="rgba(0,192,107,0.06)",
            hovertemplate="<b>$%{y:,.0f}</b><extra>Actual</extra>",
        ))
        # Forecast
        fig.add_trace(go.Scatter(
            x=fut_dates, y=fut_y.tolist(),
            name="Forecast", mode="lines",
            line=dict(color=BLUE, width=2, dash="dash"),
            hovertemplate="<b>$%{y:,.0f}</b><extra>Forecast</extra>",
        ))

        fig.update_layout(**base_layout("Revenue Forecast — 30-Day Projection", 280))
        return fig, float(fut_y.sum())
    except Exception:
        return None, 0


# ==========================================================
# STORY MODE CARDS — front and center demo navigation
# ==========================================================
def render_story_cards():
    """3 guided demo scenario cards shown prominently at the top of each dashboard view."""
    _sc = [
        {
            "key": "ROAS drop week",
            "pill": "Revenue Risk", "pill_cls": "sc-pill-red", "bar_cls": "sc-red",
            "title": "ROAS Drop Investigation",
            "desc": "Spend up, returns down. Trace the signal from source to campaign.",
        },
        {
            "key": "Revenue growth month",
            "pill": "Growth Story", "pill_cls": "sc-pill-green", "bar_cls": "sc-green",
            "title": "Revenue Growth Story",
            "desc": "Month-over-month lift. See what scaled and why it worked.",
        },
        {
            "key": "Show rate risk (CRM)",
            "pill": "CRM Risk", "pill_cls": "sc-pill-amber", "bar_cls": "sc-amber",
            "title": "Show Rate Risk (CRM)",
            "desc": "Bookings rising but fewer patients attend. Spot the friction.",
        },
    ]
    active = st.session_state.get("demo_scenario", "None")
    st.markdown('<div class="section-title">Guided Demo Flows</div>', unsafe_allow_html=True)
    st.markdown('<div id="story-cards-row"></div>', unsafe_allow_html=True)
    cols = st.columns(3, gap="small")
    for col, s in zip(cols, _sc):
        is_on = (active == s["key"])
        with col:
            badge = '<span class="sc-active-badge">Active</span>' if is_on else ''
            st.markdown(f'''<div class="story-card {s["bar_cls"]}{ " story-card-active" if is_on else ""}">
  <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;">
    <span class="sc-pill {s["pill_cls"]}">{s["pill"]}</span>{badge}
  </div>
  <div class="sc-title">{s["title"]}</div>
  <div class="sc-desc">{s["desc"]}</div>
</div>''', unsafe_allow_html=True)
            if is_on:
                if st.button("Exit scenario", key=f"sc_exit_{s['key']}", use_container_width=True):
                    st.session_state["demo_scenario"] = "None"
                    st.rerun()
            else:
                if st.button("Start demo", key=f"sc_start_{s['key']}", use_container_width=True, type="primary"):
                    st.session_state["demo_scenario"] = s["key"]
                    st.rerun()
    st.markdown('<div style="height:.4rem"></div>', unsafe_allow_html=True)


# ==========================================================
# INTELLIGENCE SIGNALS — proactive insights on dashboard
# ==========================================================
def render_signals(alerts_list, max_signals: int = 3):
    """Render top intelligence signals prominently inline on the dashboard."""
    if not alerts_list:
        return
    top = alerts_list[:max_signals]
    st.markdown('<div class="section-title" style="margin-top:.5rem;">Live Intelligence</div>', unsafe_allow_html=True)
    cols = st.columns(len(top), gap="small")
    _cls_map = {
        "sb-pill-red":   ("sig-red",   "sig-sev-red"),
        "sb-pill-amber": ("sig-amber", "sig-sev-amber"),
        "sb-pill-green": ("sig-green", "sig-sev-green"),
    }
    for col, (sev, pill_cls, title, detail, action) in zip(cols, top):
        sig_cls, sev_cls = _cls_map.get(pill_cls, ("sig-green", "sig-sev-green"))
        with col:
            st.markdown(f'''<div class="sig-card {sig_cls}">
  <div class="sig-head">
    <div class="sig-title">{title}</div>
    <div class="sig-sev {sev_cls}">{sev}</div>
  </div>
  <div class="sig-detail">{detail}</div>
  <div class="sig-action"><b>Action:</b> {action}</div>
</div>''', unsafe_allow_html=True)


# ==========================================================
# PATIENT ACQUISITION FUNNEL
# ==========================================================
def plot_patient_funnel(df: pd.DataFrame):
    """Patient acquisition funnel: Leads → Booked → Attended."""
    leads    = max(float(df["leads"].sum() or 0), 0)
    booked   = max(float(df["booked"].sum() or 0), 0)
    attended = max(float(df["attended"].sum() or 0), 0)

    pairs = [
        ("Leads",    leads,    AMBER),
        ("Booked",   booked,   GREEN),
        ("Attended", attended, GREEN_DK),
    ]
    pairs = [(s, v, c) for s, v, c in pairs if v > 0]
    if not pairs:
        return None

    stages, values, colors = zip(*pairs)
    fig = go.Figure(go.Funnel(
        y=list(stages),
        x=list(values),
        textposition="inside",
        textinfo="value+percent initial",
        marker=dict(color=list(colors), line=dict(width=0)),
        connector=dict(line=dict(color=BORDER, width=1.5), fillcolor=SOFT),
        hovertemplate="%{y}<br><b>%{x:,.0f}</b><br>%{percentInitial:.1%} of leads<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=PANEL,
        plot_bgcolor=PANEL,
        font=dict(family="DM Sans, sans-serif", color=TEXT, size=12),
        height=300,
        margin=dict(l=8, r=8, t=44, b=8),
        title=dict(text="<b>Patient Acquisition Funnel</b>", font=dict(size=13, color=TEXT), x=0, xanchor="left"),
    )
    return fig


# ==========================================================
# COMMAND CENTER — executive view
# ==========================================================
def render_command_center():
    base     = CUR_MKT if not practice_mode else CUR
    prev_b   = PREV_MKT if not practice_mode else PREV
    has_prev = len(prev_b) > 0

    rev      = float(base["total_revenue"].sum() or 0)
    spend    = float(base["total_cost"].sum() or 0)
    leads    = max(float(base["leads"].sum() or 0), 0.01)
    booked   = max(float(base["booked"].sum() or 0), 0.01)
    attended = float(base["attended"].sum() or 0)
    p_rev    = float(prev_b["total_revenue"].sum() or 0)
    p_leads  = max(float(prev_b["leads"].sum() or 0), 0.01)

    roas       = safe_div(rev, spend)
    cpl        = safe_div(spend, leads)
    show_rate  = safe_div(attended, booked) * 100
    rev_growth = safe_div(rev - p_rev, max(abs(p_rev), 0.01)) * 100
    lead_growth = safe_div(leads - p_leads, p_leads) * 100

    score = compute_health_score(base, prev_b)
    sc_color = GREEN if score >= 80 else (AMBER if score >= 60 else RED)
    sc_label = "Strong" if score >= 80 else ("Moderate" if score >= 60 else "Needs Attention")

    period_label = f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"

    # ── Section title ─────────────────────────────────────
    st.markdown('<div class="section-title">Command Center</div>', unsafe_allow_html=True)

    # ── Health banner ─────────────────────────────────────
    st.markdown(f'''
<div class="cmd-health">
  <div class="cmd-score-ring" style="border-color:{sc_color};">
    <div class="cmd-score-num" style="color:{sc_color};">{score}</div>
    <div class="cmd-score-den">/100</div>
  </div>
  <div style="flex:2;min-width:160px;">
    <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:.95rem;font-weight:800;color:#0F172A;margin-bottom:2px;">
      Platform Health &nbsp;<span style="color:{sc_color};font-size:.8rem;font-weight:700;">{sc_label}</span>
    </div>
    <div style="font-size:.74rem;color:#64748B;">{period_label} &nbsp;·&nbsp; {period_days}-day window &nbsp;·&nbsp; {len(base):,} records</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Revenue</div>
    <div class="cmd-health-val">{money(rev)}</div>
    <div class="cmd-health-sub">{delta_html(rev_growth, has_prev)}</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">ROAS</div>
    <div class="cmd-health-val">{roas:.2f}x</div>
    <div class="cmd-health-sub" style="color:{'#009952' if roas>=BENCH_ROAS else '#D97706'};">{'▲ Above' if roas>=BENCH_ROAS else '▼ Below'} {BENCH_ROAS}x avg</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Cost / Lead</div>
    <div class="cmd-health-val">{money(cpl)}</div>
    <div class="cmd-health-sub" style="color:{'#009952' if cpl<=BENCH_CPL else '#D97706'};">{'▲ Efficient' if cpl<=BENCH_CPL else '▼ Above'} ${BENCH_CPL:.0f} avg</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Show Rate</div>
    <div class="cmd-health-val">{pct(show_rate)}</div>
    <div class="cmd-health-sub" style="color:{'#009952' if show_rate>=BENCH_SHOW_RATE else '#D97706'};">{'▲ Above' if show_rate>=BENCH_SHOW_RATE else '▼ Below'} {BENCH_SHOW_RATE:.0f}% avg</div>
  </div>
</div>
''', unsafe_allow_html=True)

    # ── Benchmark tiles ────────────────────────────────────
    def _btile(label, val_str, bench_str, val_num, bench_num, higher_better=True):
        beat  = (val_num >= bench_num) if higher_better else (val_num <= bench_num)
        close = abs(val_num - bench_num) / max(bench_num, 0.01) < 0.12
        cls   = "bt-good" if beat else ("bt-warn" if close else "bt-bad")
        dc    = "#009952" if beat else ("#D97706" if close else "#DC2626")
        arrow = ("▲" if beat else "▼") if higher_better else ("▼" if beat else "▲")
        lbl   = "Above benchmark" if beat else ("Near benchmark" if close else "Below benchmark")
        return (f'<div class="bench-tile {cls}">'
                f'<div class="bench-label">{label}</div>'
                f'<div class="bench-val">{val_str}</div>'
                f'<div class="bench-delta" style="color:{dc};">{arrow} {lbl}</div>'
                f'<div class="bench-avg">Industry avg: {bench_str}</div>'
                f'</div>')

    b1, b2, b3, b4 = st.columns(4, gap="small")
    with b1:
        st.markdown(_btile("ROAS", f"{roas:.2f}x", f"{BENCH_ROAS}x", roas, BENCH_ROAS), unsafe_allow_html=True)
    with b2:
        st.markdown(_btile("Cost per Lead", money(cpl), f"${BENCH_CPL:.0f}", cpl, BENCH_CPL, higher_better=False), unsafe_allow_html=True)
    with b3:
        st.markdown(_btile("Show Rate", pct(show_rate), f"{BENCH_SHOW_RATE:.0f}%", show_rate, BENCH_SHOW_RATE), unsafe_allow_html=True)
    with b4:
        st.markdown(_btile("Lead Growth", f"{lead_growth:+.0f}%", f"+{BENCH_LEAD_GRO:.0f}%", lead_growth, BENCH_LEAD_GRO), unsafe_allow_html=True)

    st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

    # ── Forecast + Signals ─────────────────────────────────
    _fc, _sc = st.columns([1.65, 1], gap="medium")

    with _fc:
        st.markdown('<div class="section-title" style="margin-top:.2rem;">Revenue Forecast</div>', unsafe_allow_html=True)
        fig_fc, proj_total = plot_forecast(base)
        if fig_fc:
            st.markdown(
                f'<div style="font-size:.76rem;color:{MUTED};margin-bottom:5px;">'
                f'Projected next 30 days: <b style="color:{TEXT};font-size:.85rem;">{money(proj_total)}</b>'
                f' &nbsp;·&nbsp; Based on {period_days}-day trend</div>',
                unsafe_allow_html=True
            )
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.plotly_chart(fig_fc, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Not enough data for forecast. Widen the date range to at least 5 days.")

    with _sc:
        st.markdown('<div class="section-title" style="margin-top:.2rem;">Top Signals</div>', unsafe_allow_html=True)
        _cls_map = {
            "sb-pill-red":   ("sig-red",   "sig-sev-red"),
            "sb-pill-amber": ("sig-amber", "sig-sev-amber"),
            "sb-pill-green": ("sig-green", "sig-sev-green"),
        }
        for sev, pill_cls, title, detail, action in _alerts[:4]:
            sig_cls, sev_cls = _cls_map.get(pill_cls, ("sig-green", "sig-sev-green"))
            st.markdown(f'''<div class="sig-card {sig_cls}" style="margin-bottom:.4rem;">
  <div class="sig-head"><div class="sig-title">{title}</div><div class="sig-sev {sev_cls}">{sev}</div></div>
  <div class="sig-detail">{detail}</div>
  <div class="sig-action"><b>Action:</b> {action}</div>
</div>''', unsafe_allow_html=True)



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

    render_story_cards()
    st.markdown('<div class="section-title">Patient Funnel</div>', unsafe_allow_html=True)
    f_fig = plot_patient_funnel(base)
    if f_fig:
        _fc1, _fc2 = st.columns([1.6, 1], gap="medium")
        with _fc1:
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.plotly_chart(f_fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
        with _fc2:
            _leads = max(float(base["leads"].sum() or 0), 1)
            _book  = float(base["booked"].sum() or 0)
            _att   = float(base["attended"].sum() or 0)
            _fdf   = pd.DataFrame([
                {"Stage": "Leads",      "Count": fmt(_leads), "Conv. Rate": "100%"},
                {"Stage": "→ Booked",   "Count": fmt(_book),  "Conv. Rate": f"{_book/_leads*100:.1f}%"},
                {"Stage": "→ Attended", "Count": fmt(_att),   "Conv. Rate": f"{_att/max(_book,1)*100:.1f}%"},
            ])
            st.markdown('<div class="chart-card" style="margin-top:0;">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:.78rem;font-weight:700;color:#0F172A;margin-bottom:8px;">Stage Conversion Rates</div>', unsafe_allow_html=True)
            st.dataframe(df_light(_fdf), use_container_width=True, hide_index=True, height=df_height(3))
            total_drop = max(0.0, _leads - _att)
            drop_pct   = total_drop / _leads * 100 if _leads > 0 else 0.0
            st.markdown(
                f'<div style="margin-top:10px;padding:8px 10px;background:#FFF7ED;border-radius:8px;border-left:3px solid {AMBER};">'
                f'<div style="font-size:.72rem;font-weight:700;color:#92400E;">Leads never attended</div>'
                f'<div style="font-size:1.1rem;font-weight:900;color:#0F172A;">{pct(drop_pct)}</div>'
                f'<div style="font-size:.71rem;color:{MUTED};">{fmt(total_drop)} leads lost in funnel</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No funnel data available for this selection.")

    with st.expander("Patient Journey by Source", expanded=True):
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
    render_story_cards()
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


    # --- CRM Tabs: Treatment Movers | Patient Journey ---
    if "treatment" in CUR.columns:
        _crm_tab2, _crm_tab1 = st.tabs(["Patient Journey", "Treatment Movers"])

        # ── Tab 1 (2nd tab): Treatment Movers ───────────────────
        with _crm_tab1:
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

                movers_f = movers[movers["Patients"] >= 20].copy() if len(movers) else movers
                if len(movers_f) > 0:
                    # Capacity risk signal
                    if len(PREV) > 0:
                        overall_book_chg = safe_div(bk - float(PREV["booked"].sum() or 0), max(abs(float(PREV["booked"].sum() or 0)), 0.01)) * 100
                        overall_show_pp = show - (safe_div(float(PREV["attended"].sum() or 0), float(PREV["booked"].sum() or 0)) * 100 if float(PREV["booked"].sum() or 0) > 0 else show)
                        if overall_book_chg >= 15 and overall_show_pp <= -5:
                            st.warning("Capacity risk: bookings are up while show rate is down. Consider tightening scheduling confirmation + resourcing high-demand treatments.")

                    c1, c2 = st.columns(2)
                    with c1:
                        top_up = movers_f.sort_values("Δ Rev/Patient", ascending=False).head(5)
                        top_dn = movers_f.sort_values("Δ Rev/Patient", ascending=True).head(5)
                        mini = pd.concat([top_up, top_dn], axis=0).reset_index(drop=True)
                        mini = mini[["treatment","Rev/Patient","Rev/Patient_p","Δ Rev/Patient","Patients"]].rename(columns={"treatment":"Treatment"})
                        mini["Rev/Patient"] = mini["Rev/Patient"].apply(money)
                        mini["Rev/Patient_p"] = mini["Rev/Patient_p"].apply(lambda x: money(x) if pd.notna(x) else "—")
                        mini["Δ Rev/Patient"] = mini["Δ Rev/Patient"].apply(lambda x: f"{x:+.0f}%" if pd.notna(x) else "—")
                        mini["Patients"] = mini["Patients"].apply(fmt)
                        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                        st.markdown('<div style="font-weight:950;color:%s;margin-bottom:6px;">Rev/Patient movers (Top ±)</div>' % INK, unsafe_allow_html=True)
                        if mini.empty:
                            st.info('Not enough treatment volume in this window. Try widening the date range.')
                        else:
                            st.dataframe(df_light(mini), use_container_width=True, hide_index=True, height=df_height(len(mini), max_h=360))
                        st.markdown('</div>', unsafe_allow_html=True)

                    with c2:
                        top_up = movers_f.sort_values("Δ Show Rate (pp)", ascending=False).head(5)
                        top_dn = movers_f.sort_values("Δ Show Rate (pp)", ascending=True).head(5)
                        mini = pd.concat([top_up, top_dn], axis=0).reset_index(drop=True)
                        mini = mini[["treatment","Show Rate","Show Rate_p","Δ Show Rate (pp)","Booked"]].rename(columns={"treatment":"Treatment"})
                        mini["Show Rate"] = mini["Show Rate"].apply(lambda x: f"{float(x or 0):.1f}%")
                        mini["Show Rate_p"] = mini["Show Rate_p"].apply(lambda x: f"{float(x):.1f}%" if pd.notna(x) else "—")
                        mini["Δ Show Rate (pp)"] = mini["Δ Show Rate (pp)"].apply(lambda x: f"{x:+.1f} pp" if pd.notna(x) else "—")
                        mini["Booked"] = mini["Booked"].apply(fmt)
                        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                        st.markdown('<div style="font-weight:950;color:%s;margin-bottom:6px;">Show rate movers (Top ±)</div>' % INK, unsafe_allow_html=True)
                        if mini.empty:
                            st.info('Not enough treatment volume in this window. Try widening the date range.')
                        else:
                            st.dataframe(df_light(mini), use_container_width=True, hide_index=True, height=df_height(len(mini), max_h=360))
                        st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("Not enough treatment volume (min 20 patients) for movers. Try widening the date range.")
            else:
                st.info("No treatment rows available for the selected date range.")

        # ── Tab 2 (1st tab): Patient Journey ────────────────────
        with _crm_tab2:
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
            return _line(REV, "Revenue Over Time")

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
            return _group_bar("channel_group", REV, "Revenue by Channel", "$")

        # Compare sources / platform comparison
        if any(w in q for w in ["compare", "vs", "versus", "google", "facebook", "meta", "source"]):
            return _group_bar("data_source", REV, "Revenue by Source", "$")

        # Bar chart catch-all
        if any(w in q for w in ["bar", "chart", "breakdown"]):
            return _group_bar("data_source", REV, "Revenue by Source", "$")

        # Default: revenue over time if date available, else by source
        if has("date"):
            return _line(REV, "Revenue Over Time")
        return _group_bar("data_source", REV, "Revenue by Source", "$")

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
    # ── Session state init ───────────────────────────────────
    if "ai_history" not in st.session_state:
        st.session_state.ai_history = []
    if "ai_nonce" not in st.session_state:
        st.session_state.ai_nonce = 0
    if "ai_preset" not in st.session_state:
        st.session_state.ai_preset = None

    has_history = len(st.session_state.ai_history) > 0

    # ── EMPTY STATE: hero + preset cards ────────────────────
    if not has_history:
        st.markdown('''
<div class="ai-hero">
  <div class="ai-catch">Ask anything.<br><span class="ai-catch-hi">Clarity on Demand.</span></div>
  <div class="ai-catch-sub">Your live data &middot; Straight Talk</div>
</div>
''', unsafe_allow_html=True)

        # ── Preset cards ─────────────────────────────────────
        card_labels = [
            ("Revenue · last 30 days",  "Revenue last 30 days"),
            ("ROAS · by source",        "ROAS by source"),
            ("Google vs Facebook",      "Compare Google vs Facebook"),
        ]
        st.markdown('<div id="ai-cards-marker"></div>', unsafe_allow_html=True)
        _pc = st.columns(3, gap="medium")
        for col, (label, val) in zip(_pc, card_labels):
            with col:
                if st.button(label, key=f"ai_p_{val}", use_container_width=True):
                    st.session_state.ai_preset = val
                    st.rerun()

        st.markdown('<div style="height:1.4rem"></div>', unsafe_allow_html=True)

    # ── ACTIVE STATE: compact header ─────────────────────────
    else:
        _hcol, _ncol = st.columns([10, 1.8])
        with _hcol:
            st.markdown(
                f'<p style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:.94rem;'
                f'font-weight:700;color:{TEXT};margin:0 0 .5rem;">'
                f'<span style="color:#00C06B;margin-right:6px;">◆</span>NexoBI AI · Ask your data</p>',
                unsafe_allow_html=True
            )
        with _ncol:
            st.markdown('<div id="ai-newchat-marker"></div>', unsafe_allow_html=True)
            if st.button("New chat", key="ai_reset_compact", use_container_width=True):
                st.session_state.ai_history = []
                st.session_state.ai_nonce  += 1
                st.session_state.ai_preset  = None
                st.rerun()

    # ── Chat input (always rendered) ─────────────────────────
    st.markdown('<div id="ai-send-row"></div>', unsafe_allow_html=True)
    _icol, _scol = st.columns([8.5, 1.5])
    with _icol:
        user_q = st.text_input(
            "", placeholder="Ask anything about your data…",
            label_visibility="collapsed",
            key=f"ai_input_{st.session_state.ai_nonce}"
        )
    with _scol:
        ask = st.button("Send", use_container_width=True, key="ai_ask", type="primary")

    st.markdown(
        '<p style="font-size:.70rem;color:#CBD5E1;margin:.25rem 0 .7rem;text-align:right;">'
        'Powered by Databricks AI · Llama 3.3 70B</p>',
        unsafe_allow_html=True
    )

    # ── Resolve question ─────────────────────────────────────
    run_q = None
    if st.session_state.ai_preset:
        run_q = st.session_state.ai_preset
        st.session_state.ai_preset = None
    elif ask and user_q.strip():
        run_q = user_q.strip()

    if run_q:
        with st.spinner("Thinking…"):
            result = ai_query_ask(run_q)
        st.session_state.ai_history.insert(0, {"q": run_q, **result})
        if len(st.session_state.ai_history) > 10:
            st.session_state.ai_history = st.session_state.ai_history[:10]
        st.rerun()

    # ── Chat history ─────────────────────────────────────────
    for item in st.session_state.ai_history:
        q     = item.get("q", "")
        text  = item.get("text", "")
        sql   = item.get("sql", "")
        df    = item.get("df")
        error = item.get("error")

        # User bubble
        st.markdown(f'<div class="ai-bubble-user"><span>{q}</span></div>', unsafe_allow_html=True)

        if error:
            st.error(f"AI error: {error}")
            continue

        # AI response
        if text:
            st.markdown(f'<div class="ai-bubble-ai">{text}</div>', unsafe_allow_html=True)

        # Auto chart
        chart = _ai_chart(q)
        if chart is not None:
            st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})

        # Data table
        if df is not None and not df.empty:
            st.dataframe(
                df_light(df),
                use_container_width=True,
                hide_index=True,
                height=df_height(len(df))
            )

        # SQL expander
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
            <div style="background:{GREEN_LT};border:1px solid rgba(0,192,107,.2);border-left:5px solid {GREEN};border-radius:14px;padding:12px 16px;margin:6px 0 12px;">
              <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:.82rem;font-weight:800;color:#52796F;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">{meta['title']}</div>
              <div style="font-size:.82rem;color:#64748B;margin-bottom:5px;line-height:1.5;">
                <span style="font-weight:700;color:#52796F;">What to look at:</span>&nbsp; {' &middot; '.join(meta['look'])}
              </div>
              <div style="font-size:.82rem;color:#64748B;line-height:1.5;">
                <span style="font-weight:700;color:#52796F;">AI questions:</span>&nbsp; {' &middot; '.join(meta['qs'])}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

if page == "Dashboard":
    render_command_center()
    if practice_mode:
        render_practice()
    else:
        render_marketing()
else:
    render_ai()
