# NexoBI Genie Agent — Product & Deployment Guide

> **This is NexoBI's signature product.** The Genie Agent is the primary AI interface delivered to every client. It must be deployed correctly and look premium from day one.

---

## Table of Contents

1. [What It Is](#1-what-it-is)
2. [App Features & Design](#2-app-features--design)
3. [Architecture](#3-architecture)
4. [Repository Structure & Full Code](#4-repository-structure--full-code)
5. [Per-Client Deployment Checklist](#5-per-client-deployment-checklist)
6. [Step-by-Step Deployment](#6-step-by-step-deployment)
7. [Environment Variables Reference](#7-environment-variables-reference)
8. [Troubleshooting](#8-troubleshooting)
9. [Security Rules](#9-security-rules)

---

## 1. What It Is

The NexoBI Genie Agent is a **natural language interface to the client's Databricks data**. It allows practice owners and marketing managers to ask plain-English questions about their business — production, leads, campaigns, appointments — and get instant answers backed by live data.

**It replaces dashboards.** Instead of building charts for every metric, clients type a question and the AI answers it using their actual data.

### Key Capabilities

| Capability | Details |
|---|---|
| Natural language queries | Ask anything: "What drove production last month?" |
| Live data responses | Answers come from real Unity Catalog tables via Genie |
| SQL transparency | Users can expand to see the exact SQL that ran |
| Data tables | Query results render as formatted data grids |
| Conversation memory | Follow-up questions use the same Genie conversation thread |
| Follow-up chips | Context-aware suggested next questions after each answer |
| Typewriter placeholders | Animated question suggestions guide new users |
| Enter-to-send | Keyboard shortcut (Enter key) for fast interaction |
| New chat reset | One-click to start a fresh conversation |

### Why It's the Signature Product

- Zero-training required for the client — it's just a text box
- Branded NexoBI UI, not generic Databricks
- Runs entirely inside the client's Databricks workspace — data never leaves
- No tokens, no API keys managed by the client — fully automated auth
- Scales to any client: one Genie Space ID is all that changes per deployment

---

## 2. App Features & Design

### Visual Design

The app uses a custom dark theme built entirely in CSS injected via Streamlit's `unsafe_allow_html`. No external UI framework.

| Element | Design |
|---|---|
| Background | Deep navy `#060D1A` — premium, data-forward |
| Primary color | `#00C06B` (NexoBI green) |
| Fonts | Plus Jakarta Sans (headings, 900 weight) + DM Sans (body) |
| Layout | Centered, max 720px wide — focused, not cluttered |
| Streamlit chrome | Completely hidden (menu, footer, header) |

### Animated Elements

| Animation | Element | Purpose |
|---|---|---|
| `floatA` / `floatB` | Aurora orbs (blurred green blobs) | Alive, premium background feel |
| `breathe` | Orbs scale pulse | Subtle life in the background |
| `drift1` / `drift2` | Floating particle dots | Adds depth to the background |
| `twinkle` | Particle dots opacity | Stars effect |
| `shimmer` | Hero headline gradient | Eye-catching on first load |
| `slideUp` | Chat bubbles | Messages feel natural, not jarring |
| `inputGlow` | Text input border | Draws attention to the input |
| `pulseRing` | Live status dot | Shows system is active |

### UI Sections

**Hero (empty state only):**
- "Genie · Live" status pill with animated green dot
- Large headline: "Ask anything about **your practice.**" (shimmer gradient on "your practice")
- Subtext: "Get straight answers from your data. No dashboards needed."

**Input row:**
- Full-width textarea (11:1 column split with send button)
- Animated typewriter placeholder cycles through example questions
- Circular green send button (↑)
- Enter key submits (Shift+Enter for new line)

**Chat history:**
- User messages: right-aligned dark bubble
- AI responses: left-aligned white card with green left border, "NexoBI AI" label
- Data table: `st.dataframe` with dark styling, hidden index
- SQL expander: collapsed by default, reveals raw SQL on demand
- Follow-up chips: 3 context-aware suggested questions as pill buttons

**Footer (after first message):**
- "↺ New chat" button — resets history, nonce (forces new input), and Genie conversation ID

### Follow-up Chip Logic

Chips are context-aware based on keywords in the question:

| Keywords in question | Suggested chips |
|---|---|
| revenue, sales, production | "Break down production by source", "Production trend last 90 days", "Best day this month?" |
| lead, patient, appointment | "What's my cost per new patient?", "New patient trend last 90 days" |
| google, facebook, meta, source, campaign | "Which campaign drove the most production?", "Top 5 campaigns by leads" |
| treatment, procedure | "Which treatment drives the most production?", "Top treatments by revenue" |
| (anything else) | "What drove production this month?", "Which source has the best conversion?", "Show my top campaigns" |

Always returns exactly 3 unique chips.

### Genie API Flow

```
User types question → Enter or ↑ button
        │
        ▼
_call_genie(question)
        │
        ├── No existing conversation? → POST /start-conversation
        └── Existing conversation?   → POST /conversations/{id}/messages
                │
                ▼
        Poll GET /conversations/{id}/messages/{msg_id}
        every 2s, up to 90s timeout
                │
                ▼
        Parse attachments:
          - "text"  → answer_text (narrative response)
          - "query" → answer_sql + answer_desc
                │
                ▼
        If SQL present → GET /query-result → build DataFrame
                │
                ▼
        Return {text, sql, df, error}
```

The conversation ID is stored in `st.session_state["genie_conversation_id"]` so follow-up questions use the same thread and Genie understands context.

---

## 3. Architecture

```
Client Browser
     │
     ▼
Databricks Apps (free edition)
     │  hosts Streamlit on port 8080
     │  auto-injects: DATABRICKS_HOST, DATABRICKS_TOKEN,
     │                DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET
     │
     ▼
app.py  ──  WorkspaceClient()  ──▶  Genie REST API (/api/2.0/genie/...)
                                          │
                                          ▼
                                   Unity Catalog Tables
                                   (workspace.gold.*)
                                          ▲
                                          │
                            Service Principal: app-XXXXX nexo-agent
                            (auto-created by Databricks Apps)
                            must have: USE CATALOG, USE SCHEMA, SELECT
```

**Authentication chain:**
1. Databricks Apps creates a service principal for the app automatically
2. It injects OAuth credentials as environment variables at runtime
3. `WorkspaceClient()` (no arguments) picks these up automatically
4. All Genie API calls run as the service principal
5. Unity Catalog enforces table-level permissions on that principal

**No tokens are stored anywhere in the codebase.**

---

## 4. Repository Structure & Full Code

```
your-repo/
├── app.py                  ← Main app (do not rename)
├── app.yaml                ← Databricks Apps entrypoint
├── requirements.txt        ← Python dependencies
└── .streamlit/
    ├── config.toml         ← Streamlit server config (required)
    └── secrets.toml        ← Empty file (suppresses warning)
```

---

### `app.py` — Full Source

```python
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os
import requests
import time

# set_page_config MUST be the very first Streamlit command
st.set_page_config(
    page_title="NexoBI · Genie",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==========================================================
# CONFIG — os.environ first (Databricks Apps), fallback to st.secrets (Streamlit Cloud)
# ==========================================================
def _secret(key: str, default: str = "") -> str:
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    try:
        return st.secrets[key]
    except Exception:
        return default

_raw_host       = _secret("DATABRICKS_HOST", "dbc-51730115-505d.cloud.databricks.com")
DATABRICKS_HOST = _raw_host.replace("https://", "").replace("http://", "").rstrip("/")
GENIE_SPACE_ID  = _secret("NEXOBI_GENIE_SPACE_ID", "01f1180e851210c6bf3967bf360cecef")

# ==========================================================
# CSS
# ==========================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@700;900&family=DM+Sans:wght@400;500;600&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;}
.stApp{background:#060D1A!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{max-width:720px;padding:1rem 1.5rem 3rem;}

/* Header */
.nexo-header{display:flex;align-items:center;gap:12px;padding:14px 0 18px;}
.nexo-brand{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.1rem;font-weight:900;color:#F1F5F9;}
.nexo-sub{font-size:.75rem;color:#475569;}

/* Keyframes */
@keyframes floatA{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(28px,-22px) scale(1.08)}}
@keyframes floatB{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-22px,20px) scale(.94)}}
@keyframes breathe{0%,100%{opacity:.9;transform:scale(1)}50%{opacity:1;transform:scale(1.08)}}
@keyframes drift1{0%{transform:translate(0,0)}25%{transform:translate(18px,-24px)}50%{transform:translate(-12px,-40px)}75%{transform:translate(22px,-14px)}100%{transform:translate(0,0)}}
@keyframes drift2{0%{transform:translate(0,0)}33%{transform:translate(-20px,14px)}66%{transform:translate(12px,28px)}100%{transform:translate(0,0)}}
@keyframes twinkle{0%,100%{opacity:.25;transform:scale(1)}50%{opacity:.75;transform:scale(1.5)}}
@keyframes shimmer{0%{background-position:-200% center}100%{background-position:200% center}}
@keyframes slideUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes inputGlow{0%,100%{box-shadow:0 0 0 0 rgba(0,192,107,0)}50%{box-shadow:0 0 22px 4px rgba(0,192,107,.16)}}
@keyframes pulseRing{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.55;transform:scale(1.5)}}

/* Aurora orbs */
.page-orbs{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;}
.page-orbs .op1{position:absolute;width:560px;height:560px;background:rgba(0,192,107,.12);border-radius:50%;filter:blur(95px);top:-160px;right:-90px;animation:floatA 9s ease-in-out infinite,breathe 7s ease-in-out infinite;}
.page-orbs .op2{position:absolute;width:440px;height:440px;background:rgba(0,153,82,.08);border-radius:50%;filter:blur(90px);bottom:-110px;left:-70px;animation:floatB 13s ease-in-out infinite,breathe 10s ease-in-out infinite reverse;}
.page-orbs .op3{position:absolute;width:280px;height:280px;background:rgba(0,192,107,.05);border-radius:50%;filter:blur(75px);top:40%;right:-40px;animation:floatA 17s ease-in-out infinite reverse;}
.page-orbs .pt{position:absolute;border-radius:50%;pointer-events:none;}
.page-orbs .pt1{width:3px;height:3px;background:rgba(0,192,107,.7);top:18%;left:12%;animation:drift1 9s ease-in-out infinite,twinkle 3.2s ease-in-out infinite;}
.page-orbs .pt2{width:2px;height:2px;background:rgba(0,192,107,.5);top:35%;left:72%;animation:drift2 11s ease-in-out infinite,twinkle 4.1s ease-in-out .8s infinite;}
.page-orbs .pt3{width:4px;height:4px;background:rgba(0,212,120,.6);top:62%;left:28%;animation:drift1 8s ease-in-out infinite,twinkle 2.8s ease-in-out 1.5s infinite;}
.page-orbs .pt4{width:2px;height:2px;background:rgba(0,192,107,.4);top:78%;left:58%;animation:drift2 14s ease-in-out infinite,twinkle 5s ease-in-out infinite;}

/* Hero */
.ai-hero-wrap{text-align:center;padding:3rem 1rem 2rem;}
.ai-catch{font-family:'Plus Jakarta Sans',sans-serif;font-size:3rem;font-weight:900;color:#FFFFFF;line-height:1.08;margin-bottom:.6rem;}
.ai-catch-hi{background:linear-gradient(120deg,#00C06B 0%,#38BDF8 40%,#00C06B 80%);background-size:250% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;animation:shimmer 4s linear infinite;}
.ai-catch-sub{font-size:.85rem;color:rgba(255,255,255,.45);max-width:400px;margin:0 auto 2rem;}
.ai-status-pill{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:5px 16px;font-size:.7rem;font-weight:700;color:rgba(255,255,255,.75);letter-spacing:.07em;text-transform:uppercase;margin-bottom:1.5rem;}
.ai-pulse{width:7px;height:7px;background:#00C06B;border-radius:50%;display:inline-block;animation:pulseRing 1.8s ease-in-out infinite;}

/* Chat bubbles */
.ai-bubble-user{display:flex;justify-content:flex-end;margin:.8rem 0 .15rem;animation:slideUp .18s ease-out;}
.ai-bubble-user span{background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);color:#F1F5F9;border-radius:18px 18px 4px 18px;padding:11px 16px;font-size:.87rem;font-weight:500;max-width:80%;display:inline-block;box-shadow:0 4px 18px rgba(0,0,0,.18);}
.ai-msg-label{display:flex;align-items:center;gap:6px;font-size:.68rem;font-weight:700;color:#00C06B;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px;margin-top:.9rem;}
.ai-msg-label::before{content:'◆';font-size:.6rem;background:linear-gradient(135deg,#00C06B,#38BDF8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.ai-bubble-ai{background:rgba(255,255,255,.95)!important;border:none!important;border-left:3px solid #00C06B!important;border-radius:4px 18px 18px 18px!important;padding:14px 18px!important;margin:0 0 .3rem!important;font-size:.88rem!important;color:#1E293B!important;line-height:1.7!important;box-shadow:0 6px 28px rgba(0,0,0,.07)!important;animation:slideUp .2s ease-out;}
.ai-bubble-ai *{color:#334155!important;}
.ai-bubble-ai b,.ai-bubble-ai strong{color:#0F172A!important;}

/* Input */
html body textarea,[data-testid="stTextArea"] textarea{color:#000!important;-webkit-text-fill-color:#000!important;caret-color:#00C06B!important;background:#fff!important;border:1.5px solid rgba(0,192,107,.35)!important;border-radius:16px!important;padding:13px 16px!important;font-size:.9rem!important;line-height:1.5!important;resize:none!important;animation:inputGlow 3.5s ease-in-out infinite!important;}
html body textarea::placeholder{color:#475569!important;-webkit-text-fill-color:#475569!important;}
[data-testid="stTextArea"]>div,[data-testid="stTextArea"]>div>div{border:none!important;background:transparent!important;}

/* Primary button */
html body [data-testid="stBaseButton-primary"]{border-radius:50%!important;width:46px!important;min-width:46px!important;height:46px!important;padding:0!important;font-size:1.1rem!important;background:linear-gradient(135deg,#00C06B,#00875A)!important;color:#fff!important;border:none!important;box-shadow:0 4px 18px rgba(0,192,107,.35)!important;}
html body [data-testid="stBaseButton-primary"]:hover{box-shadow:0 6px 26px rgba(0,192,107,.5)!important;transform:scale(1.07)!important;}

/* Secondary / new chat button */
.stButton>button{background:rgba(255,255,255,.07)!important;color:#CBD5E1!important;border:1px solid rgba(255,255,255,.12)!important;border-radius:12px!important;font-weight:600!important;}

/* Follow-up chips */
[data-testid="stMarkdownContainer"]:has(.ai-followup-marker)+[data-testid="stHorizontalBlock"] .stButton>button{background:rgba(0,192,107,.08)!important;border:1px solid rgba(0,192,107,.22)!important;border-radius:999px!important;padding:.18rem .7rem!important;min-height:0!important;height:auto!important;font-size:.68rem!important;font-weight:500!important;color:rgba(255,255,255,.65)!important;white-space:nowrap!important;width:100%!important;}
[data-testid="stMarkdownContainer"]:has(.ai-followup-marker)+[data-testid="stHorizontalBlock"] .stButton>button:hover{background:rgba(0,192,107,.18)!important;color:#fff!important;}

/* Expander / DataFrame */
[data-testid="stExpander"]{background:rgba(255,255,255,.05)!important;border:1px solid rgba(255,255,255,.09)!important;border-radius:12px!important;}
[data-testid="stExpander"] summary{color:#CBD5E1!important;}
[data-testid="stDataFrame"]{background:rgba(255,255,255,.06)!important;border:1px solid rgba(255,255,255,.1)!important;border-radius:12px!important;}
[data-testid="stDataFrame"] *{color:#CBD5E1!important;}
.stMarkdownContainer p{color:rgba(255,255,255,.3)!important;}
</style>
""", unsafe_allow_html=True)

# Aurora background
st.markdown("""
<div class="page-orbs">
  <div class="op1"></div><div class="op2"></div><div class="op3"></div>
  <div class="pt pt1"></div><div class="pt pt2"></div>
  <div class="pt pt3"></div><div class="pt pt4"></div>
</div>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="nexo-header">
  <img src="https://images.squarespace-cdn.com/content/v1/68daa6f79c8c695a65a1d1bd/1759160060457-MMX5Q30RNSVGDEWNRL0S/nexobi_logo_transparent_background.png?format=1500w"
       width="34" style="border-radius:8px;" alt="NexoBI">
  <div>
    <div class="nexo-brand">NexoBI</div>
    <div class="nexo-sub">Attribution Intelligence</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ==========================================================
# GENIE CLIENT
# ==========================================================
def _call_genie(question: str) -> dict:
    if not GENIE_SPACE_ID:
        return {"text": "", "sql": "", "df": None, "error": "no_genie_space"}

    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        base = f"/api/2.0/genie/spaces/{GENIE_SPACE_ID}"

        conv_id = st.session_state.get("genie_conversation_id")
        if conv_id:
            data = w.api_client.do("POST", f"{base}/conversations/{conv_id}/messages",
                                   body={"content": question})
        else:
            data = w.api_client.do("POST", f"{base}/start-conversation",
                                   body={"content": question})

        conv_id = data.get("conversation_id", conv_id)
        msg_id  = data.get("message_id") or data.get("id")
        st.session_state["genie_conversation_id"] = conv_id

        poll = f"{base}/conversations/{conv_id}/messages/{msg_id}"
        status, payload, elapsed = "PENDING", {}, 0
        while status not in ("COMPLETED", "FAILED") and elapsed < 90:
            time.sleep(2)
            elapsed += 2
            payload = w.api_client.do("GET", poll)
            status  = payload.get("status", "PENDING")

        if status == "FAILED":
            return {"text": "", "sql": "", "df": None,
                    "error": payload.get("error", "Genie query failed.")}

        answer_text, answer_sql, answer_desc = "", "", ""
        for att in payload.get("attachments", []):
            if "text" in att:
                answer_text = att["text"].get("content", "")
            if "query" in att:
                answer_sql  = att["query"].get("query", "")
                answer_desc = att["query"].get("description", "")

        if not answer_text and answer_desc:
            answer_text = answer_desc

        df = None
        if answer_sql:
            try:
                rdata = w.api_client.do("GET", f"{poll}/query-result")
                cols  = [c["name"] for c in rdata.get("manifest", {}).get("schema", {}).get("columns", [])]
                rows  = [r.get("values", []) for r in rdata.get("result", {}).get("data_typed_array", [])]
                if cols and rows:
                    df = pd.DataFrame([[v.get("str", "") for v in row] for row in rows], columns=cols)
            except Exception:
                pass

        return {"text": answer_text, "sql": answer_sql, "df": df, "error": None}

    except Exception as exc:
        return {"text": "", "sql": "", "df": None, "error": str(exc)}


def _followup_chips(q: str) -> list:
    q_low = q.lower()
    pool  = []
    if any(x in q_low for x in ["revenue", "sales", "production"]):
        pool += ["Break down production by source", "Production trend last 90 days", "Best day this month?"]
    if any(x in q_low for x in ["lead", "patient", "appointment"]):
        pool += ["What's my cost per new patient?", "New patient trend last 90 days"]
    if any(x in q_low for x in ["google", "facebook", "meta", "source", "campaign"]):
        pool += ["Which campaign drove the most production?", "Top 5 campaigns by leads"]
    if any(x in q_low for x in ["treatment", "procedure"]):
        pool += ["Which treatment drives the most production?", "Top treatments by revenue"]
    if not pool:
        pool = ["What drove production this month?", "Which source has the best conversion?", "Show my top campaigns"]
    seen, chips = set(), []
    for c in pool:
        if c not in seen:
            seen.add(c)
            chips.append(c)
        if len(chips) == 3:
            break
    return chips


# ==========================================================
# MAIN
# ==========================================================
if "ai_history"            not in st.session_state: st.session_state.ai_history = []
if "ai_nonce"              not in st.session_state: st.session_state.ai_nonce = 0
if "genie_conversation_id" not in st.session_state: st.session_state.genie_conversation_id = None

has_history = len(st.session_state.ai_history) > 0

if not has_history:
    st.markdown("""
<div class="ai-hero-wrap">
  <div class="ai-status-pill"><span class="ai-pulse"></span>Genie · Live</div>
  <div class="ai-catch">Ask anything about<br><span class="ai-catch-hi">your practice.</span></div>
  <div class="ai-catch-sub">Get straight answers from your data. No dashboards needed.</div>
</div>
""", unsafe_allow_html=True)

# Input row
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

# Typewriter + Enter-to-send
components.html("""<script>
(function(){
  var Q=["What was my production last month?","Which treatments have the highest show rate?","How many new patients this week?","Compare Google vs Facebook"],
      qi=0,ci=0,del=false;
  function ta(){return window.parent.document.querySelector('[data-testid="stTextArea"] textarea');}
  function tick(){
    var t=ta();if(!t||t.value.length>0){setTimeout(tick,400);return;}
    var q=Q[qi];
    if(del){ci=Math.max(0,ci-1);t.setAttribute("placeholder",q.slice(0,ci));if(ci===0){del=false;qi=(qi+1)%Q.length;setTimeout(tick,480);}else setTimeout(tick,28);}
    else{ci=Math.min(q.length,ci+1);t.setAttribute("placeholder",q.slice(0,ci));if(ci===q.length){del=true;setTimeout(tick,2200);}else setTimeout(tick,65);}
  }
  setTimeout(tick,900);
})();
(function(){
  var _b=null;
  function bind(){
    var t=window.parent.document.querySelector('[data-testid="stTextArea"] textarea');
    if(!t){setTimeout(bind,300);return;}if(t===_b){setTimeout(bind,600);return;}_b=t;
    t.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();var btn=window.parent.document.querySelector('[data-testid="stBaseButton-primary"]');if(btn)btn.click();}});
    setTimeout(bind,600);
  }
  setTimeout(bind,600);
})();
</script>""", height=0)

# Submit
run_q = user_q.strip() if ask and user_q.strip() else None
if run_q:
    with st.spinner("Thinking…"):
        result = _call_genie(run_q)
    st.session_state.ai_history.insert(0, {"q": run_q, **result})
    if len(st.session_state.ai_history) > 10:
        st.session_state.ai_history = st.session_state.ai_history[:10]
    st.rerun()

# Chat history
for _hidx, item in enumerate(st.session_state.ai_history):
    q     = item.get("q", "")
    text  = item.get("text", "")
    sql   = item.get("sql", "")
    df    = item.get("df")
    error = item.get("error")

    st.markdown(f'<div class="ai-bubble-user"><span>{q}</span></div>', unsafe_allow_html=True)

    if error == "no_genie_space":
        st.markdown(
            '<div class="ai-msg-label">NexoBI AI</div>'
            '<div class="ai-bubble-ai" style="border-left:3px solid #F59E0B!important;">'
            '<b style="color:#92400E!important;">Genie not configured</b> — '
            'Set <code>NEXOBI_GENIE_SPACE_ID</code> in your Databricks Apps environment variables.'
            '</div>', unsafe_allow_html=True)
        continue

    if error:
        st.markdown(
            '<div class="ai-msg-label">NexoBI AI</div>'
            f'<div class="ai-bubble-ai" style="border-left:3px solid #EF4444!important;">'
            f'<b style="color:#991B1B!important;">Error</b> — {error}</div>',
            unsafe_allow_html=True)
        continue

    if text:
        st.markdown(
            '<div class="ai-msg-label">NexoBI AI</div>'
            f'<div class="ai-bubble-ai">{text}</div>',
            unsafe_allow_html=True)

    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)

    if sql:
        with st.expander("View SQL", expanded=False):
            st.code(sql, language="sql")

    if not error:
        _chips = _followup_chips(q)
        st.markdown('<div class="ai-followup-marker"></div>', unsafe_allow_html=True)
        _chip_cols = st.columns(len(_chips))
        for _ci, (_cc, _chip) in enumerate(zip(_chip_cols, _chips)):
            with _cc:
                if st.button(_chip, key=f"chip_{_hidx}_{_ci}", use_container_width=True):
                    with st.spinner("Thinking…"):
                        _res = _call_genie(_chip)
                    st.session_state.ai_history.insert(0, {"q": _chip, **_res})
                    st.rerun()

# New chat
if has_history:
    st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)
    _, _nc = st.columns([8, 2])
    with _nc:
        if st.button("↺  New chat", key="ai_reset", use_container_width=True):
            st.session_state.ai_history            = []
            st.session_state.ai_nonce             += 1
            st.session_state.genie_conversation_id = None
            st.rerun()
```

---

### `app.yaml`

```yaml
command:
  - python
  - -m
  - streamlit
  - run
  - app.py
```

> **Never add `--server.*` flags here.** All server config lives in `.streamlit/config.toml`. Mixing both causes "App not available" errors.
> **Never add `env:` with tokens here.** Databricks Apps handles auth automatically.

---

### `requirements.txt`

```
streamlit>=1.35.0
pandas>=2.0.0
requests>=2.31.0
databricks-sdk>=0.20.0
```

---

### `.streamlit/config.toml`

```toml
[server]
enableCORS = false
enableXsrfProtection = false
headless = true
port = 8080
address = "0.0.0.0"

[browser]
gatherUsageStats = false
```

> `port = 8080` and `address = "0.0.0.0"` are required by Databricks Apps proxy.
> `enableCORS = false` and `enableXsrfProtection = false` are required or the proxy blocks requests.

---

### `.streamlit/secrets.toml`

```toml
# intentionally empty — suppresses Streamlit's "no secrets found" warning
```

---

## 5. Per-Client Deployment Checklist

Copy this checklist for each new client:

```
Client name: ___________________________
Databricks workspace URL: _______________
Genie Space ID: _________________________
SP Application ID: ______________________
Deployment date: ________________________

PRE-DEPLOY
[ ] Client has Databricks workspace with Apps enabled
[ ] Genie Space created and tested (works in Genie UI)
[ ] Genie Space has correct tables configured
[ ] Repo forked/copied to client git provider

DEPLOY
[ ] Updated GENIE_SPACE_ID in app.py (or set as env var in App settings)
[ ] App created in Databricks Apps (Compute → Apps → Create)
[ ] Git repo connected, branch selected, app deployed
[ ] Noted the auto-created SP name: app-XXXXX nexo-agent

PERMISSIONS
[ ] Found SP Application ID UUID (Configurations tab)
[ ] GRANT USE CATALOG ran successfully
[ ] GRANT USE SCHEMA ran successfully
[ ] GRANT SELECT on all required tables ran successfully

VERIFY
[ ] App loads (no "App not available")
[ ] No 401 / 403 errors in logs
[ ] Test question returns a real answer
[ ] Data table renders (if question produces SQL)
[ ] Follow-up chips appear
[ ] "New chat" resets conversation

HANDOFF
[ ] App URL shared with client
[ ] Client can log in and ask questions
```

---

## 6. Step-by-Step Deployment

### Step 1 — Prepare the Repo

Copy the full repo structure (Section 4) into a new git repository on GitHub or any git provider the client uses.

Update one value in `app.py`:
```python
GENIE_SPACE_ID = _secret("NEXOBI_GENIE_SPACE_ID", "REPLACE_WITH_CLIENT_SPACE_ID")
```

Get the Genie Space ID from the URL when viewing the space:
`/genie/spaces/01f1180e851210c6bf3967bf360cecef` → ID is everything after `/spaces/`

### Step 2 — Create the App

1. Databricks → **Compute** → **Apps** → **Create App**
2. Choose **Custom app**
3. Connect the git repo (authorize GitHub if needed)
4. Select branch (`main`)
5. Click **Deploy**

Databricks installs requirements and starts the app. This takes ~2 minutes.

### Step 3 — Find the Service Principal

After deploy, go to:
**Settings → Identity & Access → Service Principals**

Find `app-XXXXX nexo-agent` → click it → **Configurations** tab → copy the **Application ID** (UUID).

### Step 4 — Grant Table Permissions

In **SQL Editor**, run (replace `<APP_UUID>` and table paths):

```sql
GRANT USE CATALOG ON CATALOG workspace TO `<APP_UUID>`;
GRANT USE SCHEMA ON SCHEMA workspace.gold TO `<APP_UUID>`;
GRANT SELECT ON TABLE workspace.gold.acquisition TO `<APP_UUID>`;
```

> Use the UUID in backticks. The display name (`app-XXXXX nexo-agent`) does **not** work — only the Application ID UUID works in SQL GRANT statements.

Repeat `GRANT SELECT` for every table the Genie Space queries.

### Step 5 — Test

Open the app URL → type a question → verify you get a real data-backed answer.

---

## 7. Environment Variables Reference

### Auto-injected by Databricks Apps (do not set manually)

| Variable | Value |
|---|---|
| `DATABRICKS_HOST` | Workspace URL (no https://) |
| `DATABRICKS_TOKEN` | OAuth access token |
| `DATABRICKS_CLIENT_ID` | Service principal client ID |
| `DATABRICKS_CLIENT_SECRET` | Service principal client secret |

`WorkspaceClient()` (no arguments) reads these automatically.

### Optional overrides (set in App environment settings)

| Variable | Purpose |
|---|---|
| `NEXOBI_GENIE_SPACE_ID` | Override Genie Space ID without changing code |

To set: Databricks → Apps → your app → **Settings** → **Environment variables**

---

## 8. Troubleshooting

### "App not available"
- Check app logs for Python errors
- Confirm `.streamlit/config.toml` exists with `port = 8080`
- Remove any `--server.*` flags from `app.yaml`
- Wait 60s after deploy before testing — cold starts take time

### `set_page_config` error on startup
- `st.set_page_config()` must be the absolute first Streamlit call
- Accessing `st.secrets` before it triggers this — `_secret()` checks `os.environ` first to avoid this
- Never move `set_page_config` below any other `st.*` call

### 401 Unauthorized
- Do not put a PAT token as `DATABRICKS_TOKEN` in `app.yaml` — Databricks Apps overrides it
- Use `WorkspaceClient()` with no arguments

### 403 Forbidden
- The service principal lacks permission to call the Genie API
- In the App's resource settings, confirm the Genie Space is linked

### `TABLES_MISSING_EXCEPTION`
- The service principal cannot access the data tables
- Run the GRANT statements in Step 4 using the Application ID UUID

### `PRINCIPAL_DOES_NOT_EXIST` on GRANT
- Use the **Application ID UUID** from Configurations tab, not the display name
- Wrap in backticks: `` `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` ``

### "Multiple auth methods" SDK error
- Do not pass `token=` or `host=` to `WorkspaceClient()` when env vars exist
- Always call `WorkspaceClient()` with no arguments inside Databricks Apps

### Genie returns no answer / empty text
- The question may be outside the Genie Space's configured scope
- Check the Genie Space in the Databricks UI directly and test the same question there

---

## 9. Security Rules

- **No tokens in code or `app.yaml`.** Databricks Apps handles auth.
- **No tokens in git.** GitHub flags them and they may be auto-revoked.
- Grant the service principal only the tables it needs — minimum access.
- If a token was accidentally committed: rotate it immediately in **Settings → Developer → Access tokens**, then remove it from git history.
- The app runs inside the client's Databricks workspace — data never leaves their environment.

---

*NexoBI — Attribution Intelligence*
*Last updated: March 2026*
