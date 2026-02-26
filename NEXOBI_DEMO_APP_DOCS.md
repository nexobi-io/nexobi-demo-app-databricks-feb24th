# NexoBI Demo App — Full Documentation

> **Purpose:** This document covers everything needed to understand, replicate, maintain, and evolve the NexoBI Demo App — a Streamlit-based healthcare marketing analytics dashboard.

---

## Table of Contents

1. [App Overview](#1-app-overview)
2. [Tech Stack & Dependencies](#2-tech-stack--dependencies)
3. [File Structure](#3-file-structure)
4. [Data Schema](#4-data-schema)
5. [Configuration Reference](#5-configuration-reference)
6. [Dashboard Sections](#6-dashboard-sections)
7. [Data Mode Architecture](#7-data-mode-architecture)
8. [CSV Deploy Approach (Local / Demo)](#8-csv-deploy-approach-local--demo)
9. [Databricks Deploy Approach (Production)](#9-databricks-deploy-approach-production)
10. [AI Agent](#10-ai-agent)
11. [Story Mode / Guided Demo Flows](#11-story-mode--guided-demo-flows)
12. [Industry Benchmarks](#12-industry-benchmarks)
13. [Theme & Design Tokens](#13-theme--design-tokens)
14. [High-Impact Ideas](#14-high-impact-ideas)

---

## 1. App Overview

NexoBI Demo App is a single-page Streamlit application that gives healthcare/dental practices a unified view of their marketing performance and patient journey. It is designed as both a functional analytics tool and a sales demo vehicle.

**Two main pages:**
- **Dashboard** — KPIs, funnel, signals, forecast, campaign breakdowns
- **AI Agent** — conversational analytics (live via Databricks AI, or offline via CSV engine)

**Two data modes:**
- **Local CSV** — default on every fresh session; loads `data.csv` from the project directory. Zero cloud dependency, fully self-contained.
- **Live (Databricks)** — activated by the user via "Switch to Live →" in the sidebar. Pulls from a Unity Catalog Delta table and enables the full AI Agent.

---

## 2. Tech Stack & Dependencies

| Library | Purpose |
|---|---|
| `streamlit` | Web framework, UI components, session state |
| `pandas` | Data loading, filtering, aggregation |
| `numpy` | Numeric helpers (regression, safe division) |
| `plotly` | All charts (Scatter, Funnel, Bar, Pie) |
| `databricks-sql-connector` | Databricks SQL Warehouse connection (live mode only) |
| `re` | Text normalization |

**Python version:** 3.9+

**Install dependencies:**
```bash
pip install streamlit pandas numpy plotly databricks-sql-connector
```

---

## 3. File Structure

```
NEXOBI - Website/
├── app.py                  # Main application (single file)
├── data.csv                # Demo dataset (CSV mode data source)
└── NEXOBI_DEMO_APP_DOCS.md # This file

Desktop/newapp/             # Git repository (synced from above)
├── app.py
├── config.toml             # Streamlit theme + server config
└── data.csv
```

**Important:** All edits go to `NEXOBI - Website/app.py` first, then synced to the git repo:
```bash
cp "/Users/juanpabloveloz/NEXOBI - Website/app.py" "/Users/juanpabloveloz/Desktop/newapp/app.py"
cd /Users/juanpabloveloz/Desktop/newapp
git add app.py && git commit -m "your message"
```

---

## 4. Data Schema

### Required Columns

| Column | Type | Description |
|---|---|---|
| `date` | date | Row date (daily granularity) |
| `data_source` | string | Traffic/lead source (e.g. "Google Ads", "Facebook", "Practice CRM") |
| `channel_group` | string | Channel category (e.g. "Paid Search", "Social") |
| `campaign` | string | Campaign name |
| `total_cost` | float | Ad spend |
| `total_revenue` | float | Revenue attributed |
| `sessions` | int | Website sessions |
| `conversions` | int | Conversion events |
| `booked` | int | Appointments booked |
| `attended` | int | Appointments attended (show rate numerator) |

### Optional / Extra Columns

| Column | Type | Description |
|---|---|---|
| `source_medium` | string | GA4-style source/medium |
| `total_users` | int | Unique users |
| `new_users` | int | New visitors |
| `clicks` | int | Ad clicks |
| `impressions` | int | Ad impressions |
| `leads` | int | Leads (falls back to `conversions` if mostly zero) |
| `roi` | float | Pre-computed ROI |
| `roas` | float | Pre-computed ROAS (overridden by computed value) |
| `conversion_rate` | float | Pre-computed CVR |
| `treatment` | string | A/B test label |

### Special Source: `Practice CRM`

Rows with `data_source = "Practice CRM"` are handled separately and trigger **Practice Mode** (CRM view). They are excluded from marketing aggregations by default unless explicitly selected.

### Normalization (`_normalize_df`)

Every data load (CSV or Databricks) runs through `_normalize_df()`:
- Strips whitespace from column names
- Coerces `date` to `datetime.date`
- Fills missing extra columns with `0`
- Auto-aliases `leads` from `conversions` if leads signal is weak
- Computes `conversion_rate` from `conversions / sessions` if mostly zero

---

## 5. Configuration Reference

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NEXOBI_DATA_MODE` | `"csv"` | Base data mode. Set to `"databricks"` in Databricks Apps env |
| `NEXOBI_CATALOG` | `"workspace"` | Unity Catalog name |
| `NEXOBI_SCHEMA` | `"silver"` | Schema name inside the catalog |
| `NEXOBI_TABLE` | `"DemoData-marketing-crm"` | Table name |
| `DATABRICKS_HOST` | `""` | Databricks workspace URL (e.g. `https://adb-xxx.azuredatabricks.net`) |
| `DATABRICKS_HTTP_PATH` | `""` | SQL Warehouse HTTP path |

### Streamlit Config (`config.toml`)

```toml
[theme]
base                    = "light"
primaryColor            = "#00C06B"
backgroundColor         = "#f7f8fc"
secondaryBackgroundColor = "#ffffff"
textColor               = "#1a1a2e"
font                    = "sans serif"

[server]
headless             = true
enableCORS           = false
enableXsrfProtection = false
maxUploadSize        = 50

[browser]
gatherUsageStats = false
```

---

## 6. Dashboard Sections

### Page Router

```
Sidebar → "Dashboard" → render_command_center()
                      → render_practice()   (if Practice CRM selected alone)
                      → render_marketing()  (all other sources)

Sidebar → "AI Agent"  → render_ai()
```

---

### 6.1 Command Center (`render_command_center`)

The top section of every dashboard view. Gives a one-glance health summary.

**Components:**

#### Platform Health Score
- **Score: 0–100** computed from 4 weighted signals (25 pts each):
  - ROAS vs benchmark (2.8x)
  - CPL vs benchmark ($45)
  - Show Rate vs benchmark (78%)
  - Revenue growth vs prior period
- Displayed as a color-coded ring: 🟢 ≥70 · 🟡 40–69 · 🔴 <40
- Four stat pills next to the ring: Revenue, ROAS, CPL, Show Rate

#### Growth Tiles (4 KPI cards)
Period-over-period growth metrics:
| Tile | Formula | Benchmark |
|---|---|---|
| Revenue Growth | `(cur_rev - prev_rev) / prev_rev * 100` | None (vs prior) |
| Lead Growth | `(cur_leads - prev_leads) / prev_leads * 100` | Industry avg: +10% |
| Booked Growth | `(cur_booked - prev_booked) / prev_booked * 100` | None |
| Spend Growth | `(cur_spend - prev_spend) / prev_spend * 100` | None (inverted — less is better) |

#### Revenue Forecast (chart)
- Linear regression on daily revenue (`numpy.polyfit`)
- Extends 14 days into the future as a dotted projection line
- Shown in left column at ratio `[1.45, 1]`

#### Top Signals (right column)
- Up to 3 intelligent alerts computed by `build_sidebar_alerts()`
- Signal types: ROAS drop, CPL spike, show rate risk, revenue growth flag
- Color-coded pills: green (good), amber (warning), red (alert)

---

### 6.2 Marketing Dashboard (`render_marketing`)

Detailed breakdowns for paid and organic marketing sources.

**Components:**

#### Story Cards
Three guided demo scenarios rendered at top:
- ROAS Drop (week-over-week)
- Revenue Growth (month)
- Show Rate Risk (CRM)

When a scenario is active, a contextual banner appears below the cards with "What to look at" and "AI questions to try."

#### Patient Acquisition Funnel
- **Left:** Plotly `go.Funnel` chart — Leads → Booked → Attended
- **Right:** HTML table showing stage counts and conversion rates
  - Green rates for good conversion
  - Amber callout for total funnel drop-off %

#### Patient Journey by Source (collapsed by default)
- Bar chart: revenue by data source
- Expander, `expanded=False`

#### Top Campaigns (collapsed by default)
- Table of campaigns sorted by revenue
- Columns: Campaign, Revenue, ROAS, Leads, Spend
- Expander, `expanded=False`

---

### 6.3 Practice CRM View (`render_practice`)

Activated when **only** "Practice CRM" is selected in the Data Source filter.

Shows CRM-specific metrics:
- Appointment volume
- Show rate trends
- No-show analysis
- Patient source breakdown (referral vs marketing)

---

### 6.4 Sidebar Filters

Applied globally to all dashboard views:

| Filter | Key | Description |
|---|---|---|
| Date Range | `f_start`, `f_end` | Start/end date pickers |
| Data Source | `f_source` | Multi-select of unique `data_source` values |
| Channel Group | `f_channel` | Dropdown of unique `channel_group` values |
| Campaign | `f_campaign` | Dropdown of unique `campaign` values |

**Period logic:**
- `CUR` = rows within `[f_start, f_end]`
- `PREV` = equal-length period immediately before `f_start`
- `CUR_MKT` / `PREV_MKT` = `CUR` / `PREV` with `Practice CRM` excluded (unless in practice mode)

---

### 6.5 Connected Platforms (sidebar)

Static display of integrated data sources with green status dots:
- Google Ads
- Meta Ads
- GA4
- LinkedIn
- Dentrix

---

## 7. Data Mode Architecture

### Mode Decision Flow

```
On every page load:
  if "force_live_mode" not in session_state:
      session_state["force_live_mode"] = False   ← always CSV on fresh open

  _force_live  = session_state["force_live_mode"]
  _ACTIVE_MODE = "databricks" if _force_live else "csv"
```

### Data Loading

```python
if _ACTIVE_MODE == "databricks":
    DATA = load_data_databricks(catalog, schema, table)
else:
    DATA = load_data("data.csv")

# If Databricks fails → silent fallback to CSV + show warning badge
```

### Sidebar Mode Badge

| State | Badge | Badge color |
|---|---|---|
| CSV (default) | 📁 Local CSV · AI Agent unavailable | Slate/neutral |
| Live (switched) | 🌐 Live · Databricks · AI Agent active | Green |
| Live failed (auto fallback) | ⚠ Live unavailable · Fell back to local CSV | Amber |

Button label always shows the action ("Switch to Live →" or "Switch to Local CSV →").

### AI Routing

```python
result = ai_query_csv(question)   if _ACTIVE_MODE == "csv"
result = ai_query_ask(question)   if _ACTIVE_MODE == "databricks"
```

---

## 8. CSV Deploy Approach (Local / Demo)

This is the default mode — no cloud account required.

### Setup

```bash
# 1. Clone or copy the project
cd "/path/to/NEXOBI - Website"

# 2. Install dependencies
pip install streamlit pandas numpy plotly

# 3. Place your data file
# → data.csv must be in the same directory as app.py

# 4. Run
streamlit run app.py
```

### data.csv Requirements

- Must include all **Required Columns** (see Section 4)
- Date format: `YYYY-MM-DD` (ISO 8601)
- At least 60 days of daily data recommended for the forecast chart
- Include `Practice CRM` rows if you want to demo the CRM view
- Numeric columns should be clean (no currency symbols, no commas)

### What works in CSV mode

| Feature | CSV mode |
|---|---|
| Command Center | ✅ Full |
| Marketing Dashboard | ✅ Full |
| Practice CRM view | ✅ Full |
| Growth tiles | ✅ Full |
| Revenue Forecast | ✅ Full |
| Patient Funnel | ✅ Full |
| Top Signals | ✅ Full |
| Story Mode | ✅ Full |
| AI Agent chat | ✅ Local engine (pattern-matched from CSV) |
| AI Agent SQL | ❌ Requires Live mode |
| AI Agent LLM | ❌ Requires Live mode |

### Sharing the CSV Demo

The simplest way to share the demo without Databricks:

1. Package `app.py` + `data.csv` + `config.toml` together
2. Deploy to **Streamlit Community Cloud** (free):
   - Push to a public GitHub repo
   - Go to share.streamlit.io → New app → connect repo → set `app.py` as entrypoint
   - No env vars needed — it defaults to CSV mode

---

## 9. Databricks Deploy Approach (Production)

### Prerequisites

- Databricks workspace (AWS, Azure, or GCP)
- Unity Catalog enabled
- A SQL Warehouse (Serverless 2X-Small is sufficient for demos)
- A Delta table matching the schema in Section 4
- Databricks Apps feature enabled in your workspace

### Step 1 — Prepare the Delta table

```sql
-- Example: create the table in Unity Catalog
CREATE TABLE workspace.silver.`DemoData-marketing-crm` (
  date          DATE,
  data_source   STRING,
  channel_group STRING,
  campaign      STRING,
  total_cost    DOUBLE,
  total_revenue DOUBLE,
  sessions      BIGINT,
  conversions   BIGINT,
  booked        BIGINT,
  attended      BIGINT,
  leads         BIGINT,
  roas          DOUBLE,
  conversion_rate DOUBLE
)
USING DELTA;

-- Load from CSV
COPY INTO workspace.silver.`DemoData-marketing-crm`
FROM '/path/to/data.csv'
FILEFORMAT = CSV
FORMAT_OPTIONS ('header' = 'true', 'inferSchema' = 'true');
```

### Step 2 — Configure environment variables

In **Databricks Apps → your app → Environment variables**, set:

| Variable | Value |
|---|---|
| `NEXOBI_DATA_MODE` | `databricks` |
| `NEXOBI_CATALOG` | your catalog name |
| `NEXOBI_SCHEMA` | your schema name |
| `NEXOBI_TABLE` | your table name |
| `DATABRICKS_HOST` | `https://adb-XXXX.azuredatabricks.net` |
| `DATABRICKS_HTTP_PATH` | `/sql/1.0/warehouses/XXXX` |

### Step 3 — Deploy the app

```bash
# From the newapp git repo
cd /Users/juanpabloveloz/Desktop/newapp

# Push to remote (GitHub/GitLab)
git push origin main

# In Databricks workspace:
# Apps → Create App → Connect to repo → set app.py as entrypoint
```

### Step 4 — Verify connection

The app uses two connection strategies in order:

1. **SparkSession** (preferred when running inside Databricks cluster):
   ```python
   from pyspark.sql import SparkSession
   spark = SparkSession.builder.getOrCreate()
   df = spark.table(f"{catalog}.{schema}.{table}").toPandas()
   ```

2. **SQL Warehouse connector** (fallback — works from Databricks Apps):
   ```python
   from databricks import sql
   conn = sql.connect(
       server_hostname = DATABRICKS_HOST,
       http_path       = DATABRICKS_HTTP_PATH,
       credentials_provider = lambda: ...  # OAuth via env token
   )
   ```

### AI Agent in Live mode

The AI Agent uses `ai_query()` — Databricks' built-in LLM SQL function — routed through a SQL Warehouse:

```sql
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  'Answer this question about our marketing data: {question}\n\nData context: ...'
) AS answer
```

Model: **Llama 3.3 70B Instruct** (via Databricks Model Serving endpoint).

### Databricks Free Tier Limitations

| Resource | Limit |
|---|---|
| Compute | Serverless only, small clusters |
| SQL Warehouse | 1 warehouse, max 2X-Small |
| Concurrent tasks | 5 per account |
| Quota | Daily fair-use (no published DBU number) |
| DBU cost (serverless) | ~$0.70–$0.75 / DBU |

The app defaults to CSV on every fresh session to avoid burning quota unintentionally. Users must explicitly click **Switch to Live →** to activate Databricks.

---

## 10. AI Agent

### CSV Mode (Offline Engine — `ai_query_csv`)

Fully functional offline (~173 lines). Answers computed directly from `DATA` using pattern matching — no LLM involved.

**Supported question patterns:**

| Intent | Example questions |
|---|---|
| Revenue summary | "Revenue last 30 days", "How much did we make?" |
| ROAS | "What's our ROAS?", "ROAS last 7 days" |
| Leads | "How many leads?", "Lead volume this month" |
| Spend | "How much did we spend?", "Total ad cost" |
| Show rate | "Show rate", "Attendance rate", "No-show count" |
| Bookings | "Appointments booked", "Booking rate" |
| By source | "Revenue by source", "ROAS by channel" |
| By campaign | "Top campaigns", "Leads by campaign" |
| Comparison | "Google vs Facebook", "Meta vs LinkedIn" |

**Time ranges parsed:** last 7 days · last 30 days (default) · last 90 days / quarter

**Response format:** HTML bubble with large metric number + growth badge + supporting stats. Tables rendered inline for grouped results.

> **Production note:** Once fully deployed on Databricks, `ai_query_csv` and the `_csv_mode` routing branch in `render_ai()` can be removed (~173 lines). Also flip the default: `force_live_mode = True` based on an env var (e.g. `DATABRICKS_HOST` being set). See Section 9 for the recommended pattern.

### Live Mode (Databricks AI — `ai_query_ask`)

Full natural language SQL generation using Llama 3.3 70B. Answers any question about the data, generates charts, and returns the underlying SQL.

**Visual question detection (`_is_visual_question`):**
Charts only render when the question explicitly contains visual intent:
`chart · graph · plot · show me · trend · over time · daily · weekly · monthly · by source · compare · vs · breakdown · last 30 · mtd · traffic`

---

## 11. Story Mode / Guided Demo Flows

Three pre-built scenarios guide demo conversations:

| Scenario | Key | Story |
|---|---|---|
| ROAS Drop (week) | `"ROAS drop week"` | Paid media efficiency fell — diagnose which source |
| Revenue Growth (month) | `"Revenue growth month"` | Strong month — attribute to channels |
| Show Rate Risk (CRM) | `"Show rate risk (CRM)"` | Attendance declining — CRM data context |

Each scenario card shows:
- **Title** of the business problem
- **"What to look at"** — sections to navigate
- **"AI questions to try"** — copy-paste prompts for the AI Agent

Activated via the card buttons in the sidebar/dashboard. Only one active at a time. Story banner appears below the card row.

---

## 12. Industry Benchmarks

Used in Growth tiles and the Health Score:

| Metric | Benchmark | Source |
|---|---|---|
| ROAS | 2.8x | Healthcare paid media average |
| CPL | $45 | Healthcare lead generation average |
| Show Rate | 78% | Appointment attendance average |
| Lead Growth | +10% | Expected monthly growth |

To update benchmarks, edit these constants near the top of `app.py`:

```python
BENCH_ROAS      = 2.8
BENCH_CPL       = 45.0
BENCH_SHOW_RATE = 78.0
BENCH_LEAD_GRO  = 10.0
```

---

## 13. Theme & Design Tokens

All colors are defined as module-level constants:

```python
GREEN    = "#00C06B"   # Primary brand green
GREEN_DK = "#009952"   # Darker green (hover, delta up)
GREEN_LT = "#E6F9F0"   # Light green background
TEXT     = "#0F172A"   # Primary text (near-black)
MUTED    = "#64748B"   # Secondary text
BORDER   = "#E2E8F0"   # Dividers
BG       = "#F5F7FA"   # Page background
PANEL    = "#FFFFFF"   # Card background
RED      = "#EF4444"   # Negative delta
BLUE     = "#3B82F6"   # Informational
AMBER    = "#F59E0B"   # Warning
PURPLE   = "#8B5CF6"   # Accent
```

Streamlit theme (`config.toml`) matches these: `primaryColor = "#00C06B"`, `backgroundColor = "#f7f8fc"`.

Typography: **Plus Jakarta Sans** (imported via Google Fonts in CSS).

---

## 14. High-Impact Ideas

### Look & Feel

| Idea | Impact | Effort |
|---|---|---|
| **Animated KPI number reveals** | Numbers count up on load — makes data feel live and impressive in demos | Low |
| **Mobile / iPad layout** | Sales demos often happen on a tablet. Current layout breaks below 900px | Medium |
| **Dark mode toggle** | Especially impactful for exec demos in low-light environments | Medium |
| **Chart hover tooltips standardization** | All Plotly charts use different tooltip formats — unifying them feels more polished | Low |
| **Skeleton loading states** | Instead of a blank screen while data loads, show gray placeholder cards | Medium |
| **Micro-animations on tiles** | Subtle green pulse on positive deltas draws the eye to wins | Low |
| **Logo / branding in sidebar header** | Replace plain text "NexoBI" with the actual logo SVG for client-facing demos | Low |
| **Custom favicon** | Currently generic Streamlit icon in browser tab | Low |
| **Print / PDF view** | A "Export as PDF" button that captures the dashboard as a single-page report | High |
| **Story card redesign** | Current cards are functional but plain — a more visual card with a chart thumbnail preview would stand out | Medium |

### Business & Product

| Idea | Impact | Effort |
|---|---|---|
| **"What should I focus on today?" AI prompt** | A single-click answer that surfaces the highest-priority action from the data — most impressive demo moment | High |
| **Follow-up suggestions after AI answers** | After each response, show 2–3 "You might also ask…" chips — keeps demos flowing without presenter scrambling | Medium |
| **Goal tracking** | Let the practice set revenue / lead targets and show progress toward them. Creates urgency in the product | High |
| **Multi-practice view** | A rollup dashboard across multiple locations — essential for DSO (Dental Service Organization) clients | High |
| **Patient LTV estimate** | If `total_revenue` and `attended` are present, compute estimated lifetime value per acquired patient | Medium |
| **Campaign recommender** | "Based on current ROAS trends, shift $X from Facebook to Google" — AI-generated budget reallocation | High |
| **Weekly email digest** | Auto-generated "your week in numbers" email from the data — drives habitual engagement | High |
| **Benchmark customization** | Let practices set their own targets (not just industry averages) — makes the product feel tailored | Medium |
| **Alerting / Slack integration** | Push a Slack message when ROAS drops >20% week-over-week — transforms from reporting to monitoring | High |
| **CRM deeper integration** | Pull appointment no-show reasons from Dentrix — closes the loop between marketing and ops | High |
| **Attribution model selector** | Let users switch between first-touch, last-touch, and linear attribution to see different stories | Medium |
| **Competitive benchmarking** | Show how this practice compares to similar practices in the same market (anonymized) | High |

### Highest ROI Quick Wins (do these first)

1. **Animated number reveals** — one CSS/JS change, dramatic visual impact
2. **"What should I focus on today?"** AI button — single most impressive demo moment
3. **Follow-up suggestion chips** — makes the AI feel smarter, keeps demos on track
4. **Goal tracking tiles** — simple session state + one new input, transforms the product story from "reporting" to "accountability"
5. **Custom logo/favicon** — 30 minutes of work, immediately more professional

---

## 15. Code Cleanup Log

### Completed (February 2026)

**~325 lines removed — commit `2477c67`:**

| Category | What was removed |
|---|---|
| Imports | `difflib`, `hashlib`, `time`, `requests` |
| Variable | `DATA_MODE` (env var, never read) |
| Functions | `plot_bar()`, `render_signals()` |
| Dead AI pipeline | `MONTHS`, `parse_dates`, `METRICS`, `fuzzy_metric`, `metric_value`, `metric_format`, `actions_for`, `compute_why`, `compute_compare`, `quick_recos` (~207 lines — replaced deterministic engine) |
| Dead variables | `rev_chg`, `lds_chg`, `_go_dashboard` pop, `dismiss_quick` |
| Dead CSS | `@keyframes aurora`, `@keyframes shimmer`, `@keyframes suggFade`, `.ai-suggestions`, `.ai-kpi-row/.ai-kpi`, `.ai-pill`, `.ai-actions`, `.reset-wrap`, `.integ-strip/.integ-badge/.integ-dot` |
| Simplified | `_build_data_context()` → one-liner (column names never matched actual schema) |

---

### Further Trimming Opportunities

**1. Production-only trim — remove CSV AI engine (~173 lines)**
- Remove `ai_query_csv()` entirely
- Remove `_csv_mode` branch in `render_ai()` — always call `ai_query_ask()`
- Remove "Switch to Live/CSV" toggle in sidebar (optional)
- Flip default: `force_live_mode = True` when `DATABRICKS_HOST` env var is set
- **Requires:** App is always deployed on Databricks; no offline/demo use case needed

**2. Dead function: `norm()` (~2 lines)**
- Defined at line ~120 as `re.sub(r"[^a-z0-9]+"…)`
- Was used by the removed deterministic AI pipeline — now has zero callers
- Safe to delete

**3. Dead CSS: `.ai-orb`, `.ai-noise` (1 line)**
- `display:none!important` rule for elements that no longer exist in the HTML
- Can be deleted outright

**4. Dead CSS: `.metric-bench` (1 line)**
- Defined but never applied to any HTML element
- Safe to delete

**5. Dead CSS: alert/pill/severity classes (~25 lines)**
- `.nexo-alert`, `.nexo-alert-row`, `.nexo-alert-title`, `.nexo-alert-pill`, `.nexo-alert-detail`
- `.sb-pill-red/amber/green`, `.sc-pill-red/amber/green`, `.sig-sev-red/amber/green`
- These ARE referenced as string values in Python logic — verify before removing that none map to active HTML
- If `render_signals()` is already gone (it is), these become fully orphaned

**6. `plot_bar_multi()` — consider inlining (~14 lines)**
- Only called once in `_ai_chart()`
- Could be inlined to remove the indirection — minor cleanup

**Total further savings:** ~215 lines (mostly from #1), or ~40 lines without the CSV engine removal.

---

*Document version: February 2026 · NexoBI Demo App*
