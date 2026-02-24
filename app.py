
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
import difflib
import hashlib
import os
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
[data-testid="stSidebar"] label{font-size:.68rem!important;font-weight:800!important;text-transform:uppercase!important;letter-spacing:.5px!important;color:#64748B!important;}
[data-testid="stSidebar"] [data-baseweb="select"]>div{background:#F5F7FA!important;border:1px solid #E2E8F0!important;border-radius:10px!important;}
[data-testid="stSidebar"] input{background:#F5F7FA!important;border:1px solid #E2E8F0!important;border-radius:10px!important;}
[data-testid="stSidebar"] span[data-baseweb="tag"]{background:#E6F9F0!important;border:1px solid #00C06B!important;color:#009952!important;}
[data-testid="stSidebar"] .stRadio>div{gap:.3rem!important;flex-direction:column!important;}
[data-testid="stSidebar"] .stRadio label{background:#F5F7FA!important;border:1px solid #E2E8F0!important;border-radius:10px!important;padding:7px 14px!important;font-size:.85rem!important;font-weight:700!important;text-transform:none!important;letter-spacing:0!important;}
[data-testid="stSidebar"] .stRadio label:has(input:checked){background:#E6F9F0!important;border-color:#00C06B!important;color:#009952!important;}

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

/* Buttons */
.stButton>button{background:#00C06B!important;color:#fff!important;border:none!important;border-radius:12px!important;font-weight:900!important;padding:.62rem 1rem!important;}
.stButton>button:hover{background:#009952!important;}
.stButton>button:focus{outline:none!important;box-shadow:0 0 0 3px rgba(0,192,107,.22)!important;}

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

/* AI preset buttons */
.ai-presets .stButton>button{background:var(--nexo-green)!important;color:#fff!important;border:none!important;border-radius:12px!important;font-weight:900!important;padding:.45rem .75rem!important;font-size:.82rem!important;height:40px!important;line-height:1.05!important;}
.ai-row-spacer{height:.25rem;}

/* AI input */
.stTextInput>div>div>input{background:#FFFFFF!important;color:#0F172A!important;border:1.5px solid #E2E8F0!important;border-radius:12px!important;padding:.72rem .9rem!important;}

/* Reset button (secondary) */
.reset-wrap .stButton>button{background:#F5F7FA!important;color:#0F172A!important;border:1px solid #E2E8F0!important;}
.reset-wrap .stButton>button:hover{background:#E6F9F0!important;border-color:#00C06B!important;}

/* AI answer cards */
.ai-answer{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:16px;padding:14px 16px;margin:.45rem 0;box-shadow:0 2px 12px rgba(0,0,0,.04);}
.ai-kpi-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;}
.ai-kpi{flex:1;min-width:180px;background:#F5F7FA;border:1px solid #E2E8F0;border-radius:14px;padding:10px 12px;min-height:70px;}
.ai-kpi .k{font-size:.68rem;font-weight:900;color:#64748B;text-transform:uppercase;letter-spacing:.08em;}
.ai-kpi .v{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.25rem;font-weight:900;color:#0F172A;margin-top:4px;}

.ai-pill{display:inline-block;background:#E6F9F0;color:#009952;border:1px solid #00C06B;border-radius:999px;font-weight:900;font-size:.72rem;padding:4px 10px;margin-right:6px;}
.ai-pill-muted{background:#F5F7FA;color:#0F172A;border:1px solid #E2E8F0;}

.ai-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px;}
@media(max-width:900px){.ai-actions{grid-template-columns:1fr;}}
.ai-action{background:#F5F7FA;border:1px solid #FFFFFF;border-radius:14px;padding:12px 12px;}
.ai-action .t{font-weight:900;}
.ai-action .d{color:#64748B;font-size:.88rem;margin-top:3px;}



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
   SIDEBAR — TIGHTER TOP + TIGHTER CONTROL SPACING
   (this overrides your global .block-container padding)
   ========================================================== */

/* Sidebar internal padding (this is the big one) */
section[data-testid="stSidebar"] .block-container {
  padding: .35rem .75rem .75rem !important;  /* top, sides, bottom */
}

/* Remove extra top gap Streamlit sometimes adds */
section[data-testid="stSidebar"] > div:first-child {
  padding-top: 0 !important;
}

/* Tighten spacing between widgets */
section[data-testid="stSidebar"] .element-container {
  margin: 0 0 .22rem 0 !important;
}

/* Tighten labels a bit */
section[data-testid="stSidebar"] label {
  margin-bottom: .15rem !important;
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

    # --- Environment / Mode Banner (TOP OF SIDEBAR) ---
    _mode_label = "Databricks · Delta" if _DBX_MODE else "Demo · CSV"
    _mode_detail = f"{DBX_CATALOG}.{DBX_SCHEMA}.{DBX_TABLE}" if _DBX_MODE else "5 Sources"
    _border_color = BLUE if _DBX_MODE else GREEN
    _bg_lt = "rgba(59,130,246,.07)" if _DBX_MODE else GREEN_LT
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {_bg_lt}, #ffffff);
            border-left: 4px solid {_border_color};
            border-radius: 14px;
            padding: 14px;
            margin: 0 0 18px 0;">
            <div style="font-weight: 700; font-size: 0.95rem;">
                Attribution Intelligence · {_mode_label}
            </div>
            <div style="font-size: 0.80rem; color: {MUTED}; margin-top: 4px;">
                {_mode_detail}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    # Refresh button (Databricks mode) — clears cache and reloads from Delta
    if _DBX_MODE:
        if st.button("🔄 Refresh Data", use_container_width=True, key="refresh_data"):
            load_data_databricks.clear()
            st.rerun()

    # --- Navigation ---
    st.markdown(
        f'<p style="font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.5px;color:{MUTED};margin-bottom:4px;">Navigation</p>',
        unsafe_allow_html=True
    )
    page = st.radio("", ["Dashboard", "AI Agent"], key="nav")
 
    st.markdown("---")
    # --------------------------------------------------
    # State init (kept here for stability)
    # --------------------------------------------------
    if "demo_scenario" not in st.session_state:
        st.session_state["demo_scenario"] = "None"
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
    if "dismiss_quick" not in st.session_state:
        st.session_state["dismiss_quick"] = False

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    st.markdown(f'<p style="font-size:.68rem;font-weight:900;text-transform:uppercase;letter-spacing:.5px;color:{MUTED};margin-bottom:4px;">Filters</p>', unsafe_allow_html=True)
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



    with st.expander("Data Health (Demo Check)", expanded=False):
        total_rows = len(DATA)
        src_count = int(DATA["data_source"].nunique()) if "data_source" in DATA.columns else 0
        crm_rows = int((DATA["data_source"].astype(str) == "Practice CRM").sum()) if "data_source" in DATA.columns else 0

        def _cov(col: str) -> float:
            if col not in DATA.columns or total_rows == 0:
                return 0.0
            s = pd.to_numeric(DATA[col], errors="coerce").fillna(0)
            return float((s != 0).mean())

        rev_cov = _cov("total_revenue")
        spend_cov = _cov("total_cost")
        leads_cov = _cov("leads") if "leads" in DATA.columns else _cov("conversions")
        sess_cov = _cov("sessions")

        treat_cov = 0.0
        if crm_rows > 0 and "treatment" in DATA.columns:
            crm = DATA[DATA["data_source"].astype(str) == "Practice CRM"].copy()
            if len(crm):
                treat_cov = float((crm["treatment"].astype(str).str.strip() != "").mean())

        flags = []
        if total_rows < 100:
            flags.append("Low row count")
        if rev_cov < 0.30:
            flags.append("Revenue mostly 0")
        if spend_cov < 0.30:
            flags.append("Spend mostly 0")
        if leads_cov < 0.20:
            flags.append("Leads mostly 0")
        if sess_cov < 0.20:
            flags.append("Sessions mostly 0")
        if crm_rows > 0 and treat_cov < 0.30:
            flags.append("Treatment mostly blank (CRM)")

        if len(flags) >= 3:
            status = "❌ Risk"
        elif len(flags) >= 1:
            status = "⚠️ Partial"
        else:
            status = " Healthy"

        st.markdown(f"**Status:** {status}")
        st.write(f"- Rows: **{total_rows:,}**")
        st.write(f"- Sources: **{src_count}**")
        st.write(f"- Practice CRM rows: **{crm_rows:,}**")
        st.write(f"- Date range: **{MIN_DATE} → {MAX_DATE}**")

        st.markdown("**Coverage (non-zero %)**")
        st.write(f"- Revenue: **{rev_cov*100:.0f}%**")
        st.write(f"- Spend: **{spend_cov*100:.0f}%**")
        st.write(f"- Leads: **{leads_cov*100:.0f}%**")
        st.write(f"- Sessions: **{sess_cov*100:.0f}%**")
        if crm_rows > 0:
            st.write(f"- Treatment filled (CRM): **{treat_cov*100:.0f}%**")

        if flags:
            st.markdown("**What to fix**")
            for f in flags[:6]:
                st.write(f"- {f}")

    
    # --------------------------------------------------
    # Alerts (dropdown)
    # --------------------------------------------------
    with st.expander("Alerts", expanded=False):
        _alerts_slot = st.empty()

    # --------------------------------------------------
    # Scenarios (dropdown)
    # --------------------------------------------------
    with st.expander("Scenarios", expanded=False):
        SCENARIOS = {
            "None": None,
            "ROAS drop week": {
                "start_offset_days": 14,
                "end_offset_days": 0,
                "sources": ["All"],
                "channel": "All",
                "campaign": "All",
            },
            "Revenue growth month": {
                "start_offset_days": 30,
                "end_offset_days": 0,
                "sources": ["All"],
                "channel": "All",
                "campaign": "All",
            },
            "Show rate risk (CRM)": {
                "start_offset_days": 21,
                "end_offset_days": 0,
                "sources": ["Practice CRM"],
                "channel": "All",
                "campaign": "All",
            },
        }

        scenario_name = st.selectbox("Scenario", options=list(SCENARIOS.keys()), key="demo_scenario")

        def _clear_demo_scenario():
            st.session_state["demo_scenario"] = "None"
            st.session_state["f_start"] = MIN_DATE
            st.session_state["f_end"] = MAX_DATE
            st.session_state["f_sources"] = ["All"]
            st.session_state["f_channel"] = "All"
            st.session_state["f_campaign"] = "All"

        cA, cB = st.columns(2)
        if cA.button("Apply", use_container_width=True, key="apply_scn"):
            scn = SCENARIOS.get(scenario_name)
            if scn and scenario_name != "None":
                st.session_state["f_start"] = MAX_DATE - timedelta(days=int(scn["start_offset_days"]))
                st.session_state["f_end"]   = MAX_DATE - timedelta(days=int(scn.get("end_offset_days", 0)))
                st.session_state["f_sources"]  = scn["sources"]
                st.session_state["f_channel"]  = scn["channel"]
                st.session_state["f_campaign"] = scn["campaign"]
                st.session_state["demo_scenario"] = scenario_name
                st.rerun()
        if cB.button("Clear", use_container_width=True, key="clear_scn"):
            _clear_demo_scenario()
            st.rerun()

    # --------------------------------------------------
    # Export (dropdown)
    # --------------------------------------------------
    with st.expander("Export", expanded=False):
        _export_slot = st.empty()
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
        with _export_slot.container():
            st.download_button("⬇ Download CSV", data=csv_bytes,
                               file_name=f"nexobi_export_{datetime.now().strftime('%Y%m%d')}.csv",
                               mime="text/csv", use_container_width=True)
            st.download_button("⬇ Download PDF", data=pdf_bytes,
                               file_name=f"nexobi_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                               mime="application/pdf", use_container_width=True)
    except Exception:
        st.sidebar.download_button("⬇ Download CSV", data=csv_bytes,
                                   file_name=f"nexobi_export_{datetime.now().strftime('%Y%m%d')}.csv",
                                   mime="text/csv", use_container_width=True)
        st.sidebar.download_button("⬇ Download PDF", data=pdf_bytes,
                                   file_name=f"nexobi_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                                   mime="application/pdf", use_container_width=True)

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

    st.markdown('<div class="section-title">Top Campaigns</div>', unsafe_allow_html=True)
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
        g1 = cur.groupby(dim).apply(lambda x: metric_value(x, metric_key)).reset_index(name="value")
        g2 = prev.groupby(dim).apply(lambda x: metric_value(x, metric_key)).reset_index(name="value_prev")
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

def render_ai():
    st.markdown('<div class="section-title">AI Agent</div>', unsafe_allow_html=True)
    st.markdown(f'<p style="color:{MUTED};font-size:.92rem;margin:.2rem 0 .6rem;">Ask simple questions now — ask the harder ones live during the demo.</p>', unsafe_allow_html=True)

    if "ai_history" not in st.session_state:
        st.session_state.ai_history = []
    if "ai_nonce" not in st.session_state:
        st.session_state.ai_nonce = 0
    if "ai_preset" not in st.session_state:
        st.session_state.ai_preset = None

    # 6 presets showcasing all query types — 2 rows of 3
    presets = [
        "What was revenue last 30 days?",
        "ROAS by source MTD",
        "Show rate this month",
        "Which source has best ROAS?",
        "Show rate trend last 30 days",
        "Compare Google vs Facebook",
    ]

    st.markdown('<div class="ai-presets">', unsafe_allow_html=True)
    _pr1, _pr2, _pr3 = st.columns(3)
    _pr4, _pr5, _pr6 = st.columns(3)
    for col, p in zip([_pr1, _pr2, _pr3, _pr4, _pr5, _pr6], presets):
        with col:
            if st.button(p, use_container_width=True, key=f"ai_p_{p}"):
                st.session_state.ai_preset = p
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="ai-row-spacer"></div>', unsafe_allow_html=True)

    # input + ask + reset aligned
    qcol, askcol, resetcol = st.columns([6,2,1.6])
    with qcol:
        user_q = st.text_input(
            "",
            placeholder="Ask away — I’m here to help",
            label_visibility="collapsed",
            key=f"ai_input_{st.session_state.ai_nonce}"
        )
    with askcol:
        ask = st.button("Ask AI Agent", use_container_width=True, key="ai_ask")
    with resetcol:
        # Secondary: visually distinct + avoids weird wrapper spacing
        reset = st.button("Reset", use_container_width=True, key="ai_reset", type="secondary")

    if reset:
        st.session_state.ai_history = []
        st.session_state.ai_nonce += 1
        st.session_state.ai_preset = None
        st.rerun()

    run_q = None
    if st.session_state.ai_preset:
        run_q = st.session_state.ai_preset
        st.session_state.ai_preset = None
    elif ask and user_q.strip():
        run_q = user_q.strip()

    # Use marketing-safe base (exclude Practice CRM unless explicitly selected)
    base_df = CUR_MKT.copy() if not include_practice_in_marketing else CUR.copy()

    if run_q:
        gmin, gmax = MIN_DATE, MAX_DATE
        s_d, e_d, note = parse_dates(run_q, gmin, gmax)
        if not s_d:
            s_d, e_d, note = start, end, "Selected range"

        mk = fuzzy_metric(run_q)
        ql = norm(run_q)

        # ---- Detect query intent ----
        _by_source   = "by source" in ql
        _by_channel  = "by channel" in ql
        _by_campaign = "by campaign" in ql
        _is_trend    = any(w in ql for w in ["trend","over time","daily","weekly","per day","by day","by week"])
        _is_rank     = bool(re.search(r'\b(best|worst|top|highest|lowest)\b', ql)) and bool(re.search(r'\b(source|channel|campaign)\b', ql))
        _compare_m   = re.search(r'\bcompare\s+(.+?)\s+(?:vs?\.?|versus|and)\s+(.+)', ql)
        _is_why      = ql.startswith("why") or any(p in ql for p in ["why did","why is","why are","why has","why have"])

        fdf = base_df[(base_df["date"] >= s_d) & (base_df["date"] <= e_d)]

        def _safe_groupby(df, dim, metric_key):
            """Pandas 2.x-compatible groupby for any metric."""
            meta = METRICS.get(metric_key, {})
            if meta.get("kind") == "sum" and meta.get("num") in df.columns:
                return df.groupby(dim, as_index=False).agg(value=(meta["num"], "sum"))
            g = df.groupby(dim).apply(lambda x: metric_value(x, metric_key))
            return g.reset_index(name="value")

        if _compare_m:
            payload = {
                "type": "compare_two", "q": run_q, "metric": mk, "note": note,
                "period": f"{s_d} → {e_d}",
                "a": _compare_m.group(1).strip(), "b": _compare_m.group(2).strip(),
                "df": fdf, "s_d": s_d, "e_d": e_d,
            }
        elif _is_trend:
            meta = METRICS.get(mk, {})
            if meta.get("kind") == "sum" and meta.get("num") in fdf.columns:
                ts = fdf.groupby("date", as_index=False).agg(value=(meta["num"], "sum"))
            else:
                ts = fdf.groupby("date").apply(lambda x: metric_value(x, mk)).reset_index(name="value")
            ts["date"] = pd.to_datetime(ts["date"])
            ts = ts.sort_values("date")
            payload = {"type": "trend", "q": run_q, "metric": mk, "note": note,
                       "period": f"{s_d} → {e_d}", "df": ts}

        elif _is_rank:
            rank_dim = "campaign" if "campaign" in ql else ("channel_group" if "channel" in ql else "data_source")
            asc = bool(re.search(r'\b(worst|lowest|least|bottom)\b', ql))
            g = _safe_groupby(fdf, rank_dim, mk)
            g = g.sort_values("value", ascending=asc).head(10)
            payload = {"type": "rank", "q": run_q, "metric": mk, "note": note,
                       "period": f"{s_d} → {e_d}", "dim": rank_dim, "df": g, "ascending": asc}

        elif _by_source:
            fdf_s = fdf[fdf["data_source"].str.lower() != "practice crm"] if mk == "roas" else fdf
            g = _safe_groupby(fdf_s, "data_source", mk).sort_values("value", ascending=False).head(25)
            payload = {"type": "bar", "q": run_q, "metric": mk, "note": note,
                       "period": f"{s_d} → {e_d}", "dim": "data_source", "df": g, "s_d": s_d, "e_d": e_d}

        elif _by_channel:
            g = _safe_groupby(fdf, "channel_group", mk).sort_values("value", ascending=False).head(20)
            payload = {"type": "bar", "q": run_q, "metric": mk, "note": note,
                       "period": f"{s_d} → {e_d}", "dim": "channel_group", "df": g, "s_d": s_d, "e_d": e_d}

        elif _by_campaign:
            g = _safe_groupby(fdf, "campaign", mk)
            g = g[g["campaign"].astype(str).str.strip().ne("")]
            g = g.sort_values("value", ascending=False).head(15)
            payload = {"type": "bar", "q": run_q, "metric": mk, "note": note,
                       "period": f"{s_d} → {e_d}", "dim": "campaign", "df": g, "s_d": s_d, "e_d": e_d}

        elif _is_why:
            payload = {"type": "why", "q": run_q, "metric": mk, "note": note,
                       "data": compute_why(mk, s_d, e_d, note, base_df)}

        else:
            cmp = compute_compare(mk, s_d, e_d, base_df)
            payload = {
                "type": "metric", "q": run_q, "metric": mk, "note": note,
                "period": f"{s_d} → {e_d}",
                "value": metric_value(fdf, mk),
                "compare": cmp,
            }

        st.session_state.ai_history.insert(0, payload)
        # Cap history to avoid unbounded session state growth
        if len(st.session_state.ai_history) > 20:
            st.session_state.ai_history = st.session_state.ai_history[:20]
        st.rerun()

    # ---- Render history (show latest 6) ----
    for item in st.session_state.ai_history[:6]:
        q   = item.get("q", "")
        mk  = item.get("metric", "revenue")
        note = item.get("note", "")
        typ = item.get("type", "metric")

        st.markdown(f'''
        <div class="ai-answer">
          <div style="font-size:.72rem;font-weight:900;color:{GREEN_DK};text-transform:uppercase;letter-spacing:.08em;">✦ Question</div>
          <div style="font-family:'Plus Jakarta Sans',sans-serif;font-weight:900;font-size:1.35rem;margin-top:.15rem;color:{TEXT};">{q}</div>
          <div style="color:{MUTED};font-size:.9rem;margin-top:.25rem;">{note}</div>
        ''', unsafe_allow_html=True)

        if typ == "metric":
            v   = float(item.get("value", 0))
            cmp = item.get("compare")
            st.markdown(f'''
              <div class="ai-kpi-row">
                <div class="ai-kpi"><div class="k">Metric</div><div class="v">{mk.replace("_"," ").title()}</div></div>
                <div class="ai-kpi"><div class="k">Value</div><div class="v">{metric_format(mk, v)}</div></div>
              </div>
            ''', unsafe_allow_html=True)
            if cmp:
                st.markdown(f'''
                  <div class="ai-kpi-row" style="margin-top:10px;">
                    <div class="ai-kpi"><div class="k">Prior</div><div class="v">{metric_format(mk, cmp["prior"])}</div></div>
                    <div class="ai-kpi"><div class="k">Delta</div><div class="v">{metric_format(mk, cmp["delta"])} ({cmp["pct"]:+.1f}%)</div></div>
                    <div class="ai-kpi"><div class="k">Window</div><div class="v" style="font-size:1rem;">{cmp["period"]}</div></div>
                  </div>
                ''', unsafe_allow_html=True)
                st.markdown(f'<div style="margin-top:10px;"><span class="ai-pill">Recommendations</span><span class="ai-pill ai-pill-muted">Confidence: {cmp["confidence"]}</span></div>', unsafe_allow_html=True)
                st.markdown('<div class="ai-actions">', unsafe_allow_html=True)
                for _t, _desc in quick_recos(mk, cmp["direction"])[:3]:
                    st.markdown(f'<div class="ai-action"><div class="t">🎯 {_t}</div><div class="d">{_desc}</div></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

        elif typ == "bar":
            _dim_col   = item.get("dim", "data_source")
            _dim_label = _dim_col.replace("_", " ").title()
            df = item["df"].copy()
            df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)
            # Rename the dimension column to "dim" for the chart helper
            df_chart = df.rename(columns={_dim_col: "dim"}) if _dim_col in df.columns else df.rename(columns={df.columns[0]: "dim"})
            st.markdown('<div class="chart-card" style="margin-top:10px;">', unsafe_allow_html=True)
            st.plotly_chart(
                plot_bar_multi(df_chart, "dim", "value", f"{mk.replace('_',' ').title()} by {_dim_label}"),
                use_container_width=True, config={"displayModeBar": False}
            )
            st.markdown('</div>', unsafe_allow_html=True)
            # Formatted display table
            _val_col = mk.replace("_", " ").title()
            show_df = df_chart.rename(columns={"dim": _dim_label}).copy()
            show_df["value"] = show_df["value"].apply(lambda x: metric_format(mk, x))
            show_df = show_df.rename(columns={"value": _val_col})
            st.dataframe(df_light(show_df), use_container_width=True, hide_index=True, height=df_height(len(show_df)))
            # Mover recommendations (only works for data_source dim)
            if _dim_col == "data_source":
                win_s = item.get("s_d", start)
                win_e = item.get("e_d", end)
                cmp = compute_compare(mk, win_s, win_e, base_df, dim="data_source")
                movers = cmp.get("movers")
                if movers is not None and len(movers) > 0:
                    st.markdown(f'<div style="margin-top:10px;"><span class="ai-pill">Recommendations</span><span class="ai-pill ai-pill-muted">Confidence: {cmp["confidence"]}</span></div>', unsafe_allow_html=True)
                    mm = movers.sort_values("impact", ascending=(cmp["delta"] < 0)).head(2)
                    lines = []
                    for _, r in mm.iterrows():
                        _n = str(r.get("data_source", r.iloc[0]))
                        imp = float(r["impact"])
                        imp_s = f"{imp:+.2f}x" if mk == "roas" else (f"{imp:+.2f}%" if mk in ["cvr","show_rate"] else (money(imp) if mk in ["revenue","spend","cpa"] else f"{imp:+,.0f}"))
                        lines.append(f"<li><b>{_n}</b>: {imp_s}</li>")
                    st.markdown(f"<ul style='margin:6px 0 0 18px;color:{TEXT};'>"+"".join(lines)+"</ul>", unsafe_allow_html=True)
                    st.markdown('<div class="ai-actions">', unsafe_allow_html=True)
                    for _t, _desc in quick_recos(mk, cmp["direction"])[:3]:
                        st.markdown(f'<div class="ai-action"><div class="t">🎯 {_t}</div><div class="d">{_desc}</div></div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

        elif typ == "trend":
            df = item["df"].copy()
            df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)
            st.markdown('<div class="chart-card" style="margin-top:10px;">', unsafe_allow_html=True)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["value"], mode="lines",
                line=dict(color=GREEN, width=2.5),
                fill="tozeroy", fillcolor="rgba(0,192,107,0.08)",
                hovertemplate="<b>%{y:,.1f}</b><extra></extra>",
            ))
            fig.update_layout(**base_layout(f"{mk.replace('_',' ').title()} Over Time", 280))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)

        elif typ == "rank":
            _dim_col   = item.get("dim", "data_source")
            _dim_label = _dim_col.replace("_", " ").title()
            _asc       = item.get("ascending", False)
            df = item["df"].copy()
            df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)
            _rank_title = f"{'Lowest' if _asc else 'Best'} {_dim_label} by {mk.replace('_',' ').title()}"
            df_chart = df.rename(columns={_dim_col: "dim"}) if _dim_col in df.columns else df.rename(columns={df.columns[0]: "dim"})
            st.markdown('<div class="chart-card" style="margin-top:10px;">', unsafe_allow_html=True)
            st.plotly_chart(
                plot_bar_multi(df_chart, "dim", "value", _rank_title),
                use_container_width=True, config={"displayModeBar": False}
            )
            st.markdown('</div>', unsafe_allow_html=True)
            _val_col = mk.replace("_", " ").title()
            show_df = df_chart.rename(columns={"dim": _dim_label}).copy()
            show_df["value"] = show_df["value"].apply(lambda x: metric_format(mk, x))
            show_df = show_df.rename(columns={"value": _val_col})
            st.dataframe(df_light(show_df), use_container_width=True, hide_index=True, height=df_height(len(show_df)))

        elif typ == "compare_two":
            df       = item.get("df", pd.DataFrame())
            name_a   = item.get("a", "")
            name_b   = item.get("b", "")
            all_opts = []
            for _c in ["data_source", "channel_group", "campaign"]:
                if _c in df.columns:
                    all_opts += df[_c].astype(str).unique().tolist()

            def _best_match(name, options):
                n = norm(name)
                for o in options:
                    if n in norm(o) or norm(o) in n:
                        return o
                return max(options, key=lambda o: difflib.SequenceMatcher(None, n, norm(o)).ratio()) if options else None

            match_a = _best_match(name_a, all_opts)
            match_b = _best_match(name_b, all_opts)

            def _seg_val(df, name):
                if not name:
                    return 0.0
                n = norm(name)
                for _c in ["data_source", "channel_group", "campaign"]:
                    if _c in df.columns:
                        seg = df[df[_c].astype(str).apply(norm) == n]
                        if len(seg):
                            return metric_value(seg, mk)
                return 0.0

            val_a  = _seg_val(df, match_a)
            val_b  = _seg_val(df, match_b)
            winner = (match_a or name_a) if val_a >= val_b else (match_b or name_b)
            diff_p = safe_div(abs(val_a - val_b), max(abs(min(val_a, val_b)), 0.01)) * 100
            st.markdown(f'''
              <div class="ai-kpi-row" style="margin-top:10px;">
                <div class="ai-kpi"><div class="k">{match_a or name_a}</div><div class="v">{metric_format(mk, val_a)}</div></div>
                <div class="ai-kpi"><div class="k">{match_b or name_b}</div><div class="v">{metric_format(mk, val_b)}</div></div>
                <div class="ai-kpi"><div class="k">Winner</div><div class="v" style="font-size:1rem;">{winner} (+{diff_p:.0f}%)</div></div>
              </div>
            ''', unsafe_allow_html=True)
            st.markdown(f'<div style="margin-top:10px;"><span class="ai-pill">Recommendations</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="ai-actions">', unsafe_allow_html=True)
            for _t, _desc in quick_recos(mk, "up" if val_a >= val_b else "down")[:3]:
                st.markdown(f'<div class="ai-action"><div class="t">🎯 {_t}</div><div class="d">{_desc}</div></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        elif typ == "why":
            d = item["data"]
            st.markdown(f'''
              <div style="margin-top:10px;">
                <span class="ai-pill">Insights</span>
                <span class="ai-pill ai-pill-muted">Confidence: {d["confidence"]}</span>
              </div>
              <div class="ai-kpi-row">
                <div class="ai-kpi"><div class="k">Current</div><div class="v">{metric_format(mk, d["current"])}</div></div>
                <div class="ai-kpi"><div class="k">Prior</div><div class="v">{metric_format(mk, d["prior"])}</div></div>
                <div class="ai-kpi"><div class="k">Delta</div><div class="v">{metric_format(mk, d["delta"])} ({d["pct"]:+.1f}%)</div></div>
              </div>
            ''', unsafe_allow_html=True)
            st.markdown('<div style="margin-top:10px;"><span class="ai-pill">Drivers</span></div>', unsafe_allow_html=True)
            for dim, table in d["drivers"]:
                t = table[[dim, "impact"]].copy()
                if mk in ["revenue","spend","cpa"]:
                    t["impact"] = t["impact"].apply(money)
                elif mk == "roas":
                    t["impact"] = t["impact"].apply(lambda x: f"{float(x):+.2f}x")
                elif mk in ["cvr","show_rate"]:
                    t["impact"] = t["impact"].apply(lambda x: f"{float(x):+.2f}%")
                else:
                    t["impact"] = t["impact"].apply(lambda x: f"{float(x):+,.0f}")
                t = t.rename(columns={dim: dim.replace("_"," ").title(), "impact": "Impact"})
                st.dataframe(df_light(t), use_container_width=True, hide_index=True, height=df_height(len(t)))
            st.markdown('<div style="margin-top:10px;"><span class="ai-pill">Actions</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="ai-actions">', unsafe_allow_html=True)
            for _t, _desc in d["actions"][:4]:
                st.markdown(f'<div class="ai-action"><div class="t">🎯 {_t}</div><div class="d">{_desc}</div></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

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
