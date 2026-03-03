

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import os
from datetime import datetime, timedelta, date

# ==========================================================
# CONFIG — CSV (dev) or Databricks (prod)
# Set NEXOBI_DATA_MODE=databricks in Databricks Apps env vars
# ==========================================================
CSV_PATH = "data.csv"   # used when DATA_MODE == "csv"

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
SOFT     = "#EEF2F7"

# Industry benchmarks — healthcare marketing averages
BENCH_ROAS      = 2.8    # Avg paid media ROAS for healthcare
BENCH_CPL       = 45.0   # Avg cost per lead ($)
BENCH_SHOW_RATE = 78.0   # Avg appointment show rate (%)

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


# ---- Load data based on mode (with automatic CSV fallback) ----
# Handle query-param navigation from AI Agent fixed "← Dashboard" button
if st.query_params.get("_nav") == "dash":
    st.query_params.clear()
    st.session_state["nav"] = "Dashboard"

# Default to CSV every fresh session; only go live when user explicitly switches
if "force_live_mode" not in st.session_state:
    st.session_state["force_live_mode"] = False   # CSV is always the default on open

_force_live    = st.session_state["force_live_mode"]
_ACTIVE_MODE   = "databricks" if _force_live else "csv"   # always CSV unless user switches
_FALLBACK_WARN = None               # banner message shown in sidebar

try:
    if _ACTIVE_MODE == "databricks":
        DATA = load_data_databricks(DBX_CATALOG, DBX_SCHEMA, DBX_TABLE)
    else:
        DATA = load_data(CSV_PATH)
except Exception as _dbx_err:
    if _ACTIVE_MODE == "databricks":
        # Databricks unavailable — silently fall back to local CSV
        try:
            DATA = load_data(CSV_PATH)
            _ACTIVE_MODE   = "csv"
            _FALLBACK_WARN = str(_dbx_err)
        except Exception as _csv_err:
            st.error(
                f"⚠️ Databricks unreachable **and** local CSV failed to load.\n\n"
                f"• Databricks error: `{_dbx_err}`\n"
                f"• CSV error: `{_csv_err}`\n\n"
                f"Place `data.csv` next to `app.py` and retry."
            )
            st.stop()
    else:
        st.error(f"Could not load `{CSV_PATH}`. Place data.csv next to app.py. Error: {_dbx_err}")
        st.stop()

MIN_DATE = DATA["date"].min()
MAX_DATE = DATA["date"].max()

# Show data source badge in header area + refresh button (Databricks mode only)
_DBX_MODE = (_ACTIVE_MODE == "databricks")

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


/* Signal pill colours (used by Top Signals in Command Center) */
.sb-pill-red{background:rgba(239,68,68,.10);color:#EF4444;}
.sb-pill-amber{background:rgba(245,158,11,.12);color:#D97706;}
.sb-pill-green{background:rgba(0,192,107,.10);color:#009952;}

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

    # --- Data mode badge + one-click switch ---
    _is_live = st.session_state.get("force_live_mode", False) and not bool(_FALLBACK_WARN)
    if _FALLBACK_WARN:
        _badge_label  = "⚠ Live unavailable"
        _badge_detail = "Fell back to local CSV"
        _badge_bg, _badge_bd, _badge_fc = "#FFF7ED", "#FED7AA", "#C2410C"
    elif _is_live:
        _badge_label  = "🌐 Live · Databricks"
        _badge_detail = "AI Agent active"
        _badge_bg, _badge_bd, _badge_fc = "#F0FDF4", "#BBF7D0", "#15803D"
    else:
        _badge_label  = "📁 Local CSV"
        _badge_detail = "AI Agent unavailable"
        _badge_bg, _badge_bd, _badge_fc = "#F8FAFC", "#E2E8F0", "#475569"

    st.markdown(
        f'<div style="background:{_badge_bg};border:1px solid {_badge_bd};border-radius:8px;'
        f'padding:7px 10px;margin-bottom:5px;">'
        f'<div style="font-size:.71rem;font-weight:700;color:{_badge_fc};">{_badge_label}</div>'
        f'<div style="font-size:.63rem;color:#94A3B8;margin-top:1px;">{_badge_detail}</div>'
        f'</div>',
        unsafe_allow_html=True
    )
    st.markdown('<div class="sb-reset-wrap">', unsafe_allow_html=True)
    _switch_lbl = "Switch to Local CSV →" if _is_live else "Switch to Live →"
    if st.button(_switch_lbl, key="mode_switch_btn", use_container_width=True):
        st.session_state["force_live_mode"] = not _is_live
        try:
            load_data_databricks.clear()
        except Exception:
            pass
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Navigation ---
    page = st.radio("Navigation", ["Dashboard", "AI Agent"], key="nav")

    st.markdown("---")
    # --------------------------------------------------
    # State init (kept here for stability)
    # --------------------------------------------------
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

# ── Configurable view — block visibility ───────────────────────
for _b in BLOCK_REGISTRY:
    if f"blk_{_b['id']}" not in st.session_state:
        st.session_state[f"blk_{_b['id']}"] = True  # all on by default

visible_blocks = {
    b["id"] for b in BLOCK_REGISTRY
    if st.session_state.get(f"blk_{b['id']}", True)
}

# ── Sidebar "Your View" picker (shown only on Dashboard page) ──
if page == "Dashboard":
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        '<div style="font-size:.7rem;font-weight:700;color:#94A3B8;'
        'letter-spacing:.07em;text-transform:uppercase;margin-bottom:.3rem;">'
        '◈&nbsp; Your View</div>',
        unsafe_allow_html=True
    )
    for _b in BLOCK_REGISTRY:
        _applies = (
            "both" in _b["modes"]
            or ("practice" in _b["modes"] and practice_mode)
            or ("marketing" in _b["modes"] and not practice_mode)
        )
        if _applies:
            st.sidebar.checkbox(f"{_b['icon']}  {_b['label']}", key=f"blk_{_b['id']}")
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
def plot_forecast(df: pd.DataFrame, col: str = "total_revenue",
                  title: str = "Revenue Forecast — 30-Day Projection",
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

    # ── Health banner (toggleable) ────────────────────────
    if "banner" in visible_blocks:
        if practice_mode:
            # CRM view: Revenue · New Patients · Show Rate · Total Appointments
            new_patients  = float(base["conversions"].sum() or 0)
            total_appts   = float(base["booked"].sum() or 0)
            p_patients    = float(prev_b["conversions"].sum() or 0)
            p_appts       = float(prev_b["booked"].sum() or 0)
            pat_growth    = safe_div(new_patients - p_patients, max(abs(p_patients), 0.01)) * 100
            appt_growth   = safe_div(total_appts - p_appts, max(abs(p_appts), 0.01)) * 100
            show_clr      = '#009952' if show_rate >= BENCH_SHOW_RATE else '#D97706'
            banner_stats  = f'''
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Revenue</div>
    <div class="cmd-health-val">{money(rev)}</div>
    <div class="cmd-health-sub">{delta_html(rev_growth, has_prev)}</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">New Patients</div>
    <div class="cmd-health-val">{fmt(new_patients)}</div>
    <div class="cmd-health-sub">{delta_html(pat_growth, has_prev)}</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Show Rate</div>
    <div class="cmd-health-val">{pct(show_rate)}</div>
    <div class="cmd-health-sub" style="color:{show_clr};">{'▲ Above' if show_rate>=BENCH_SHOW_RATE else '▼ Below'} {BENCH_SHOW_RATE:.0f}% avg</div>
  </div>
  <div class="cmd-health-stat">
    <div class="cmd-health-label">Total Appointments</div>
    <div class="cmd-health-val">{fmt(total_appts)}</div>
    <div class="cmd-health-sub">{delta_html(appt_growth, has_prev)}</div>
  </div>'''
        else:
            # Marketing view: Revenue · ROAS · Cost/Lead · Show Rate
            banner_stats = f'''
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
  </div>'''
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
  {banner_stats}
</div>
''', unsafe_allow_html=True)

    # ── Top Signals (toggleable) ───────────────────────────
    if "signals" in visible_blocks:
        st.markdown('<div class="section-title" style="margin-top:.5rem;">Top Signals</div>', unsafe_allow_html=True)
        _cls_map = {
            "sb-pill-red":   ("sig-red",   "sig-sev-red"),
            "sb-pill-amber": ("sig-amber", "sig-sev-amber"),
            "sb-pill-green": ("sig-green", "sig-sev-green"),
        }
        _s1, _s2, _s3 = st.columns(3, gap="small")
        for col, (sev, pill_cls, title, detail, action) in zip([_s1, _s2, _s3], _alerts[:3]):
            sig_cls, sev_cls = _cls_map.get(pill_cls, ("sig-green", "sig-sev-green"))
            with col:
                st.markdown(f'''<div class="sig-card {sig_cls}">
  <div class="sig-head"><div class="sig-title">{title}</div><div class="sig-sev {sev_cls}">{sev}</div></div>
  <div class="sig-detail">{detail}</div>
  <div class="sig-action"><b>Action:</b> {action}</div>
</div>''', unsafe_allow_html=True)
        st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

    # ── Dual Forecasts (toggleable) ────────────────────────
    if "forecasts" in visible_blocks:
        st.markdown('<div class="section-title" style="margin-top:.2rem;">30-Day Forecasts</div>', unsafe_allow_html=True)
        _f1, _f2 = st.columns(2, gap="medium")
        with _f1:
            fig_rev, proj_rev = plot_forecast(
                base, col="total_revenue",
                title="Revenue Forecast — 30-Day Projection",
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
                st.info("Not enough data for revenue forecast.")
        with _f2:
            fig_bk, proj_bk = plot_forecast(
                base, col="booked",
                title="Booked Appointments — 30-Day Projection",
                color=PURPLE, is_money=False
            )
            if fig_bk:
                st.markdown(
                    f'<div style="font-size:.76rem;color:{MUTED};margin-bottom:5px;">'
                    f'Projected: <b style="color:{TEXT};font-size:.85rem;">{fmt(proj_bk)} appts</b>'
                    f' &nbsp;·&nbsp; next 30 days</div>',
                    unsafe_allow_html=True
                )
                st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                st.plotly_chart(fig_bk, use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info("Not enough data for appointments forecast.")



# ==========================================================
# DASHBOARD
# ==========================================================
def render_marketing():
    base = CUR_MKT if not practice_mode else CUR

    with st.expander("Patient Journey by Source", expanded=False):
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
                Booked=("booked",        "sum"),
                Attended=("attended",    "sum"),
                Revenue=("total_revenue","sum"),
            )
            grp["Show Rate"]    = grp.apply(lambda r: safe_div(r["Attended"], r["Booked"]) * 100, axis=1)
            grp["Rev/Patient"]  = grp.apply(lambda r: safe_div(r["Revenue"],  r["Patients"]),     axis=1)

            # Prior-period Rev/Patient for delta
            if len(prev_t) > 0:
                prev_g = prev_t.groupby("treatment", as_index=False).agg(
                    Revenue_p=("total_revenue","sum"),
                    Patients_p=("conversions","sum"),
                )
                prev_g["RevPat_p"] = prev_g.apply(lambda r: safe_div(r["Revenue_p"], r["Patients_p"]), axis=1)
                grp = grp.merge(prev_g[["treatment","RevPat_p"]], on="treatment", how="left")
                grp["Δ Rev/Patient"] = grp.apply(
                    lambda r: safe_div(r["Rev/Patient"] - r["RevPat_p"],
                                       max(abs(r["RevPat_p"]), 0.01)) * 100
                    if pd.notna(r.get("RevPat_p")) else np.nan, axis=1)
            else:
                grp["Δ Rev/Patient"] = np.nan

            grp = grp.sort_values("Revenue", ascending=False).head(20)

            out = grp.rename(columns={"treatment": "Treatment"})[
                ["Treatment", "Patients", "Show Rate", "Rev/Patient", "Δ Rev/Patient", "Revenue"]
            ].copy()
            out["Patients"]      = out["Patients"].apply(fmt)
            out["Show Rate"]     = out["Show Rate"].apply(lambda x: f"{float(x or 0):.1f}%")
            out["Rev/Patient"]   = out["Rev/Patient"].apply(money)
            out["Δ Rev/Patient"] = out["Δ Rev/Patient"].apply(
                lambda x: f"{x:+.0f}%" if pd.notna(x) else "—")
            out["Revenue"]       = out["Revenue"].apply(money)

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
# Model endpoint confirmed available in this workspace
_MODEL_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"


def ai_query_csv(question: str) -> dict:
    """Answer questions directly from the loaded CSV — no Databricks needed."""
    q   = question.lower()
    df  = DATA.copy()
    df["date"] = pd.to_datetime(df["date"])
    today = pd.to_datetime(MAX_DATE)

    # ── Time range ────────────────────────────────────────────
    if any(x in q for x in ["last 7", "past 7", "last week", "7 day"]):
        days, plabel = 7, "last 7 days"
    elif any(x in q for x in ["last 90", "quarter", "3 month", "90 day"]):
        days, plabel = 90, "last 90 days"
    else:
        days, plabel = 30, "last 30 days"

    cutoff  = today - pd.Timedelta(days=days)
    d       = df[df["date"] >= cutoff]
    prior_d = df[(df["date"] >= cutoff - pd.Timedelta(days=days)) & (df["date"] < cutoff)]

    def _s(frame, col):
        return float(frame[col].sum()) if col in frame.columns else 0.0

    rev    = _s(d, "total_revenue");  p_rev  = _s(prior_d, "total_revenue")
    cost   = _s(d, "total_cost");     p_cost = _s(prior_d, "total_cost")
    leads  = _s(d, "leads");          p_leads= _s(prior_d, "leads")
    booked = _s(d, "booked")
    att    = _s(d, "attended")
    roas   = rev  / max(cost,  0.01)
    cpl    = cost / max(leads, 1)
    show   = att  / max(booked, 1) * 100
    book_r = booked / max(leads, 1) * 100

    def _chg(curr, prev):
        return (curr - prev) / abs(prev) * 100 if prev else None

    def _badge(pct):
        if pct is None: return ""
        arrow = "▲" if pct >= 0 else "▼"
        clr   = "#15803D" if pct >= 0 else "#DC2626"
        return f' <span style="color:{clr};font-size:.78rem;font-weight:700;">{arrow} {abs(pct):.1f}%</span>'

    # ── Compare two sources (e.g. "Google vs Facebook") ──────
    _src_map = {
        "google":    ["google"],
        "facebook":  ["facebook", "meta", "fb"],
        "instagram": ["instagram"],
        "linkedin":  ["linkedin"],
        "email":     ["email"],
        "organic":   ["organic"],
    }
    found_srcs = [k for k, aliases in _src_map.items() if any(a in q for a in aliases)]

    if len(found_srcs) >= 2:
        rows = []
        for src in found_srcs[:2]:
            aliases = _src_map[src]
            mask = d["data_source"].str.lower().apply(lambda x: any(a in x for a in aliases))
            sd   = d[mask]
            s_rev  = _s(sd, "total_revenue"); s_cost = _s(sd, "total_cost")
            s_leads= _s(sd, "leads");         s_roas = s_rev / max(s_cost, 0.01)
            rows.append({"_src": src.title(), "rev": s_rev, "cost": s_cost,
                         "leads": s_leads, "roas": s_roas})
        a, b = rows[0], rows[1]
        winner_rev  = a["_src"] if a["rev"]  >= b["rev"]  else b["_src"]
        winner_roas = a["_src"] if a["roas"] >= b["roas"] else b["_src"]
        html = (
            f'<b>{a["_src"]} vs {b["_src"]}</b> — {plabel}<br><br>'
            '<table style="width:100%;border-collapse:collapse;font-size:.82rem;">'
            '<thead><tr style="border-bottom:1.5px solid #E2E8F0;">'
            + "".join(f'<th style="text-align:{"left" if i==0 else "right"};padding:4px 8px;'
                      f'color:#64748B;font-size:.72rem;">{h}</th>'
                      for i, h in enumerate(["Source","Revenue","Spend","ROAS","Leads"]))
            + '</tr></thead><tbody>'
        )
        for r in rows:
            rclr = "#15803D" if r["roas"] >= 3 else ("#DC2626" if r["roas"] < 1.5 else "#0F172A")
            html += (f'<tr style="border-bottom:1px solid #F1F5F9;">'
                     f'<td style="padding:5px 8px;font-weight:700;color:#0F172A;">{r["_src"]}</td>'
                     f'<td style="text-align:right;padding:5px 8px;color:#0F172A;">${r["rev"]:,.0f}</td>'
                     f'<td style="text-align:right;padding:5px 8px;color:#64748B;">${r["cost"]:,.0f}</td>'
                     f'<td style="text-align:right;padding:5px 8px;font-weight:700;color:{rclr};">{r["roas"]:.2f}x</td>'
                     f'<td style="text-align:right;padding:5px 8px;color:#0F172A;">{r["leads"]:,.0f}</td>'
                     f'</tr>')
        html += ('</tbody></table><br>'
                 f'<span style="color:#64748B;font-size:.8rem;">'
                 f'📊 <b>{winner_rev}</b> leads on revenue · <b>{winner_roas}</b> leads on ROAS</span>')
        return {"text": html, "sql": None, "df": None, "error": None}

    # ── Grouped by source or campaign ────────────────────────
    grp = None
    if any(x in q for x in ["by source", "per source", "by channel", "per channel"]):
        grp = "data_source"
    elif any(x in q for x in ["by campaign", "per campaign", "top campaign"]):
        grp = "campaign"

    if grp:
        agg = (d.groupby(grp)
               .agg(total_revenue=("total_revenue","sum"), total_cost=("total_cost","sum"),
                    leads=("leads","sum"), booked=("booked","sum"))
               .reset_index())
        agg["roas"] = agg["total_revenue"] / agg["total_cost"].replace(0, 0.01)
        sort_col = ("roas"          if any(x in q for x in ["roas","return"]) else
                    "leads"         if any(x in q for x in ["lead","conversion"]) else
                    "total_cost"    if any(x in q for x in ["spend","cost"]) else
                    "total_revenue")
        col_label = {"roas":"ROAS","leads":"Leads","total_cost":"Spend",
                     "total_revenue":"Revenue"}.get(sort_col,"Revenue")
        agg  = agg.sort_values(sort_col, ascending=False).head(8)
        top  = agg.iloc[0]
        html = (f'<b>{col_label} by {grp.replace("_"," ").title()}</b> — {plabel}<br><br>'
                '<table style="width:100%;border-collapse:collapse;font-size:.82rem;">'
                '<thead><tr style="border-bottom:1.5px solid #E2E8F0;">'
                f'<th style="text-align:left;padding:4px 8px;color:#64748B;font-size:.72rem;">'
                f'{grp.replace("_"," ").title()}</th>'
                '<th style="text-align:right;padding:4px 8px;color:#64748B;font-size:.72rem;">Revenue</th>'
                '<th style="text-align:right;padding:4px 8px;color:#64748B;font-size:.72rem;">ROAS</th>'
                '<th style="text-align:right;padding:4px 8px;color:#64748B;font-size:.72rem;">Leads</th>'
                '</tr></thead><tbody>')
        for _, row in agg.iterrows():
            rclr = "#15803D" if row["roas"] >= 3 else ("#DC2626" if row["roas"] < 1.5 else "#0F172A")
            html += (f'<tr style="border-bottom:1px solid #F1F5F9;">'
                     f'<td style="padding:5px 8px;font-weight:600;color:#0F172A;">{row[grp]}</td>'
                     f'<td style="text-align:right;padding:5px 8px;color:#0F172A;">${row["total_revenue"]:,.0f}</td>'
                     f'<td style="text-align:right;padding:5px 8px;font-weight:700;color:{rclr};">{row["roas"]:.2f}x</td>'
                     f'<td style="text-align:right;padding:5px 8px;color:#0F172A;">{row["leads"]:,.0f}</td>'
                     f'</tr>')
        html += (f'</tbody></table><br>'
                 f'<span style="color:#64748B;font-size:.8rem;">'
                 f'🏆 <b>{top[grp]}</b> is the top performer by {col_label.lower()}.</span>')
        return {"text": html, "sql": None, "df": None, "error": None}

    # ── Single metric summary ─────────────────────────────────
    if any(x in q for x in ["roas", "return on ad"]):
        p_roas = _s(prior_d,"total_revenue") / max(_s(prior_d,"total_cost"), 0.01)
        html = (f'<b>ROAS</b> — {plabel}<br>'
                f'<span style="font-size:1.5rem;font-weight:900;color:#0F172A;">{roas:.2f}x</span>'
                f'{_badge(_chg(roas, p_roas))}<br><br>'
                f'<span style="color:#64748B;font-size:.82rem;">'
                f'Revenue: <b>${rev:,.0f}</b> &nbsp;·&nbsp; Spend: <b>${cost:,.0f}</b></span>')
    elif any(x in q for x in ["lead", "conversion"]):
        html = (f'<b>Leads</b> — {plabel}<br>'
                f'<span style="font-size:1.5rem;font-weight:900;color:#0F172A;">{leads:,.0f}</span>'
                f'{_badge(_chg(leads, p_leads))}<br><br>'
                f'<span style="color:#64748B;font-size:.82rem;">'
                f'Booked: <b>{booked:,.0f}</b> ({book_r:.1f}%) &nbsp;·&nbsp; CPL: <b>${cpl:,.0f}</b></span>')
    elif any(x in q for x in ["spend", "cost", "budget"]):
        html = (f'<b>Ad Spend</b> — {plabel}<br>'
                f'<span style="font-size:1.5rem;font-weight:900;color:#0F172A;">${cost:,.0f}</span>'
                f'{_badge(_chg(cost, p_cost))}<br><br>'
                f'<span style="color:#64748B;font-size:.82rem;">'
                f'Revenue: <b>${rev:,.0f}</b> &nbsp;·&nbsp; ROAS: <b>{roas:.2f}x</b></span>')
    elif any(x in q for x in ["show rate", "attendance", "attended", "no show", "no-show"]):
        html = (f'<b>Show Rate</b> — {plabel}<br>'
                f'<span style="font-size:1.5rem;font-weight:900;color:#0F172A;">{show:.1f}%</span><br><br>'
                f'<span style="color:#64748B;font-size:.82rem;">'
                f'Booked: <b>{booked:,.0f}</b> &nbsp;·&nbsp; Attended: <b>{att:,.0f}</b> &nbsp;·&nbsp; '
                f'No-shows: <b>{booked-att:,.0f}</b></span>')
    elif any(x in q for x in ["book", "appointment"]):
        html = (f'<b>Bookings</b> — {plabel}<br>'
                f'<span style="font-size:1.5rem;font-weight:900;color:#0F172A;">{booked:,.0f}</span><br><br>'
                f'<span style="color:#64748B;font-size:.82rem;">'
                f'From <b>{leads:,.0f}</b> leads ({book_r:.1f}% book rate) &nbsp;·&nbsp; '
                f'Show rate: <b>{show:.1f}%</b></span>')
    else:
        html = (f'<b>Revenue</b> — {plabel}<br>'
                f'<span style="font-size:1.5rem;font-weight:900;color:#0F172A;">${rev:,.0f}</span>'
                f'{_badge(_chg(rev, p_rev))}<br><br>'
                f'<span style="color:#64748B;font-size:.82rem;">'
                f'Spend: <b>${cost:,.0f}</b> &nbsp;·&nbsp; ROAS: <b>{roas:.2f}x</b> &nbsp;·&nbsp; '
                f'Leads: <b>{leads:,.0f}</b></span>')

    return {"text": html, "sql": None, "df": None, "error": None}


def ai_query_ask(question: str) -> dict:
    """
    Answer a question using Databricks ai_query() SQL function.
    Returns a graceful offline message when Databricks is unavailable.
    """
    # If we're running in CSV fallback mode, skip the call entirely
    if _ACTIVE_MODE != "databricks":
        return {
            "text": "",
            "sql": "",
            "df": None,
            "error": "offline",
        }

    from databricks import sql as _dbsql

    endpoint = _MODEL_ENDPOINT
    prompt = (
        "You are a concise marketing analytics assistant for a healthcare practice. "
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
        pool += ["Break down revenue by source", "Revenue trend last 90 days", "Best revenue day this month?"]
    if any(x in q_low for x in ["roas", "return on ad", "spend", "cost per"]):
        pool += ["Compare ROAS: Google vs Facebook", "Which campaign has the best ROI?"]
    if any(x in q_low for x in ["show rate", "attendance", "attended", "no-show"]):
        pool += ["Which treatment has the best show rate?", "Compare show rate by source"]
    if any(x in q_low for x in ["patient", "new patient", "lead"]):
        pool += ["What's my cost per new patient?", "New patient trend last 90 days"]
    if any(x in q_low for x in ["google", "facebook", "instagram", "meta", "source", "campaign"]):
        pool += ["Which campaign drove the most revenue?", "Top 5 campaigns by ROAS"]
    if any(x in q_low for x in ["treatment", "procedure", "service"]):
        pool += ["Which treatment drives the most revenue?", "Show rate by treatment"]
    if not pool:
        pool = ["What drove revenue this month?", "Which source has the best ROAS?", "Show my top campaigns"]
    seen, chips = set(), []
    for c in pool:
        if c not in seen:
            seen.add(c); chips.append(c)
        if len(chips) == 3:
            break
    return chips


def render_ai():
    # ── Session state init ───────────────────────────────────
    if "ai_history" not in st.session_state:
        st.session_state.ai_history = []
    if "ai_nonce" not in st.session_state:
        st.session_state.ai_nonce = 0
    has_history = len(st.session_state.ai_history) > 0
    _csv_mode   = (_ACTIVE_MODE != "databricks")

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
    "What was my revenue last month?",
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
            result = ai_query_csv(run_q) if _csv_mode else ai_query_ask(run_q)
        st.session_state.ai_history.insert(0, {"q": run_q, **result})
        if len(st.session_state.ai_history) > 10:
            st.session_state.ai_history = st.session_state.ai_history[:10]
        st.rerun()

    # ── Chat history ─────────────────────────────────────────
    for _hidx, item in enumerate(st.session_state.ai_history):
        q     = item.get("q", "")
        text  = item.get("text", "")
        df    = item.get("df")
        error = item.get("error")

        # User bubble
        st.markdown(f'<div class="ai-bubble-user"><span>{q}</span></div>', unsafe_allow_html=True)

        if error == "offline":
            st.markdown(
                '<div class="ai-msg-label">NexoBI AI</div>'
                '<div class="ai-bubble-ai" style="border-left:3px solid #F59E0B!important;background:#FFFBEB!important;">'
                '<span style="font-weight:700;color:#92400E;">AI Agent offline</span> — '
                '<span style="color:#78716C;">Databricks is currently unreachable. '
                'Dashboard data is fully available via CSV.</span>'
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

        if error:
            st.error(f"AI error: {error}")
            continue

        # AI response
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

        # Data table
        if df is not None and not df.empty:
            st.dataframe(
                df_light(df),
                use_container_width=True,
                hide_index=True,
                height=df_height(len(df))
            )

        # ── Follow-up suggestion chips ───────────────────────
        if not error:
            _chips = _followup_chips(q)
            st.markdown('<div class="ai-followup-marker"></div>', unsafe_allow_html=True)
            _chip_cols = st.columns(len(_chips))
            for _ci, (_chip_col, _chip) in enumerate(zip(_chip_cols, _chips)):
                with _chip_col:
                    if st.button(_chip, key=f"ai_chip_{_hidx}_{_ci}", use_container_width=True):
                        with st.spinner("Thinking…"):
                            _chip_res = ai_query_csv(_chip) if _csv_mode else ai_query_ask(_chip)
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
                st.session_state.ai_history = []
                st.session_state.ai_nonce  += 1
                st.rerun()

# ==========================================================
# ROUTER
# ==========================================================

if page == "Dashboard":
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
/* Fixed full-page aurora orbs */
.ai-page-orbs{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;}
.ai-page-orbs .op1{position:absolute;width:520px;height:520px;background:rgba(0,192,107,.13);border-radius:50%;filter:blur(90px);top:-140px;right:-80px;animation:floatA 9s ease-in-out infinite;}
.ai-page-orbs .op2{position:absolute;width:420px;height:420px;background:rgba(14,165,233,.10);border-radius:50%;filter:blur(90px);bottom:-100px;left:-60px;animation:floatB 13s ease-in-out infinite;}
.ai-page-orbs .op3{position:absolute;width:300px;height:300px;background:rgba(139,92,246,.08);border-radius:50%;filter:blur(80px);top:42%;right:-50px;animation:floatA 17s ease-in-out infinite reverse;}
/* ── Dashboard pill — fixed top-left anchor link ─────── */
#nexobi-dash-pill{
  position:fixed;top:14px;left:14px;z-index:10000;
  background:transparent;border:1px solid rgba(255,255,255,.13);
  border-radius:999px;padding:4px 13px;
  color:rgba(255,255,255,.36);font-size:.68rem;font-weight:500;
  cursor:pointer;font-family:inherit;letter-spacing:.02em;
  text-decoration:none;display:inline-block;
  transition:all .18s;
}
#nexobi-dash-pill:hover{background:rgba(255,255,255,.06);color:rgba(255,255,255,.7);border-color:rgba(255,255,255,.22);}
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
  line-height:1.5!important;resize:none!important;box-shadow:none!important;
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

    # ── Full-page aurora orbs ─────────────────────────────────
    st.markdown('<div class="ai-page-orbs"><div class="op1"></div><div class="op2"></div><div class="op3"></div></div>', unsafe_allow_html=True)

    # ── Dashboard pill — simple anchor, query-param nav ───────
    st.markdown('<a id="nexobi-dash-pill" href="?_nav=dash" target="_self">← Dashboard</a>', unsafe_allow_html=True)

    # Note: AI Agent uses DATA (full dataset) — sidebar filters have no effect
    render_ai()
