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


def _auto_chart(df: pd.DataFrame) -> bool:
    """Detect data shape and render the best chart. Returns True if a chart was rendered."""
    if df is None or df.empty or len(df) < 2:
        return False

    def _to_num(series):
        return pd.to_numeric(
            series.astype(str).str.replace(r"[\$,%\s]", "", regex=True).str.replace(",", ""),
            errors="coerce"
        )

    cols = list(df.columns)

    # Classify each column as numeric or text
    numeric_cols, text_cols = [], []
    for col in cols:
        converted = _to_num(df[col])
        (numeric_cols if converted.notna().mean() > 0.6 else text_cols).append(col)

    if not numeric_cols:
        return False

    date_kw   = ["date", "month", "week", "day", "period", "year", "quarter", "time"]
    date_cols = [c for c in text_cols if any(k in c.lower() for k in date_kw)]
    cat_cols  = [c for c in text_cols if c not in date_cols]

    # Build a clean numeric dataframe
    num_df = pd.DataFrame({col: _to_num(df[col]) for col in numeric_cols})

    # Time series → line chart
    if date_cols:
        idx = date_cols[0]
        chart_df = num_df[numeric_cols[:3]].copy()
        chart_df.index = df[idx].astype(str)
        chart_df.index.name = idx
        st.line_chart(chart_df)
        return True

    # Category + numeric → bar chart
    if cat_cols:
        idx     = cat_cols[0]
        num_col = numeric_cols[0]
        chart_df = num_df[[num_col]].copy()
        chart_df.index = df[idx].astype(str)
        chart_df.index.name = idx
        chart_df = chart_df.dropna().sort_values(num_col, ascending=False).head(15)
        st.bar_chart(chart_df)
        return True

    # Pure numeric (no labels) → line chart on index
    if len(numeric_cols) >= 1:
        st.line_chart(num_df[numeric_cols[:3]])
        return True

    return False




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
        _auto_chart(df)
        st.dataframe(df, use_container_width=True, hide_index=True)

    if sql:
        with st.expander("View SQL", expanded=False):
            st.code(sql, language="sql")

    if not error:
        _, _rec_col = st.columns([7, 3])
        with _rec_col:
            if st.button("💡 Get recommendations", key=f"rec_{_hidx}", use_container_width=True):
                _rec_q = "Based on the data above, give me 2-3 specific, actionable recommendations I should focus on to improve my results."
                with st.spinner("Thinking…"):
                    _res = _call_genie(_rec_q)
                st.session_state.ai_history.insert(0, {"q": _rec_q, **_res})
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
