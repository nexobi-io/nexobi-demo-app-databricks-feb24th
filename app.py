import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

# set_page_config MUST be the first Streamlit command
st.set_page_config(
    page_title="NexoBI Agent",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ----------------------------------------------------------
# Configuration
# ----------------------------------------------------------
def _secret(key: str, default: str = "") -> str:
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    try:
        return st.secrets[key]
    except Exception:
        return default


def _bool_env(key: str, default: bool = False) -> bool:
    raw = _secret(key, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


GENIE_SPACE_ID = _secret("NEXOBI_GENIE_SPACE_ID", "")
LLM_ENDPOINT = _secret("NEXOBI_LLM_ENDPOINT", "databricks-meta-llama-3-1-70b-instruct")
ENABLE_LLM = _bool_env("NEXOBI_ENABLE_LLM", True)
PLAYBOOK_VS_ENDPOINT = _secret("NEXOBI_PLAYBOOK_VS_ENDPOINT", "")
PLAYBOOK_INDEX_NAME = _secret("NEXOBI_PLAYBOOK_INDEX_NAME", "")
PLAYBOOK_TEXT_COLUMN = _secret("NEXOBI_PLAYBOOK_TEXT_COLUMN", "content")
PLAYBOOK_ID_COLUMN = _secret("NEXOBI_PLAYBOOK_ID_COLUMN", "id")
PLAYBOOK_K = int(_secret("NEXOBI_PLAYBOOK_K", "4"))
MAX_HISTORY = int(_secret("NEXOBI_MAX_HISTORY", "12"))
MAX_TOOL_STEPS = int(_secret("NEXOBI_MAX_TOOL_STEPS", "5"))
GENIE_TIMEOUT_SEC = int(_secret("NEXOBI_GENIE_TIMEOUT_SEC", "90"))
GENIE_POLL_SEC = int(_secret("NEXOBI_GENIE_POLL_SEC", "2"))


# ----------------------------------------------------------
# Logging
# ----------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexobi_agent")


def _log(event: str, request_id: str, **kwargs: Any) -> None:
    payload = {"event": event, "request_id": request_id, **kwargs}
    logger.info(json.dumps(payload, default=str))


# ----------------------------------------------------------
# UI style (safe: only static HTML/CSS)
# ----------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@700;900&family=DM+Sans:wght@400;500;600&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;}
.stApp{background:#060D1A!important;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{max-width:820px;padding:1rem 1.5rem 3rem;}
.ai-title{font-family:'Plus Jakarta Sans',sans-serif;font-size:2.6rem;font-weight:900;color:#fff;line-height:1.05;margin:1.8rem 0 .4rem;}
.ai-sub{color:rgba(255,255,255,.62);margin-bottom:1.2rem;}
[data-testid="stTextArea"] textarea{background:#fff!important;color:#000!important;border-radius:14px!important;}
.stButton>button{border-radius:12px!important;}
</style>
""",
    unsafe_allow_html=True,
)


# ----------------------------------------------------------
# Databricks wrappers
# ----------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _workspace_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def _dbx_do(method: str, path: str, request_id: str, body: Optional[dict] = None, retries: int = 4) -> dict:
    w = _workspace_client()
    backoff = 1.0
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            started = time.time()
            response = w.api_client.do(method, path, body=body)
            _log("dbx_call_ok", request_id, method=method, path=path, attempt=attempt, ms=int((time.time() - started) * 1000))
            return response
        except Exception as exc:
            last_exc = exc
            retriable = any(token in str(exc).lower() for token in ["429", "timeout", "tempor", "503", "502", "504"])
            _log(
                "dbx_call_err",
                request_id,
                method=method,
                path=path,
                attempt=attempt,
                retriable=retriable,
                error=str(exc),
            )
            if attempt == retries or not retriable:
                break
            time.sleep(backoff)
            backoff = min(backoff * 2, 8)
    raise RuntimeError(f"Databricks API call failed: {method} {path} :: {last_exc}")


def _typed_cell(v: dict) -> Any:
    if "null" in v:
        return None
    if "long" in v:
        return int(v["long"])
    if "int" in v:
        return int(v["int"])
    if "double" in v:
        return float(v["double"])
    if "float" in v:
        return float(v["float"])
    if "bool" in v:
        return bool(v["bool"])
    if "str" in v:
        return str(v["str"])
    return next((x for x in v.values() if x is not None), None)


def _fetch_query_df(poll_path: str, request_id: str, row_limit: int = 200) -> pd.DataFrame:
    rdata = _dbx_do("GET", f"{poll_path}/query-result", request_id=request_id)
    cols = [c["name"] for c in rdata.get("manifest", {}).get("schema", {}).get("columns", [])]
    raw_rows = rdata.get("result", {}).get("data_typed_array", [])
    rows = [[_typed_cell(v) for v in r.get("values", [])] for r in raw_rows[:row_limit]]
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=cols)


def _tool_ask_genie(question: str, request_id: str) -> Dict[str, Any]:
    if not GENIE_SPACE_ID:
        return {"ok": False, "error": "Genie is not configured. Set NEXOBI_GENIE_SPACE_ID."}

    base = f"/api/2.0/genie/spaces/{GENIE_SPACE_ID}"
    conv_id = st.session_state.get("genie_conversation_id")

    if conv_id:
        data = _dbx_do(
            "POST",
            f"{base}/conversations/{conv_id}/messages",
            request_id=request_id,
            body={"content": question},
        )
    else:
        data = _dbx_do(
            "POST",
            f"{base}/start-conversation",
            request_id=request_id,
            body={"content": question},
        )

    conv_id = data.get("conversation_id", conv_id)
    msg_id = data.get("message_id") or data.get("id")
    st.session_state["genie_conversation_id"] = conv_id

    poll_path = f"{base}/conversations/{conv_id}/messages/{msg_id}"
    status = "PENDING"
    payload: Dict[str, Any] = {}
    elapsed = 0

    while status not in ("COMPLETED", "FAILED") and elapsed < GENIE_TIMEOUT_SEC:
        time.sleep(GENIE_POLL_SEC)
        elapsed += GENIE_POLL_SEC
        payload = _dbx_do("GET", poll_path, request_id=request_id)
        status = payload.get("status", "PENDING")

    if status != "COMPLETED":
        return {"ok": False, "error": payload.get("error", "Genie timed out or failed.")}

    answer_text = ""
    answer_sql = ""
    answer_desc = ""
    for att in payload.get("attachments", []):
        if "text" in att:
            answer_text = att["text"].get("content", "")
        if "query" in att:
            answer_sql = att["query"].get("query", "")
            answer_desc = att["query"].get("description", "")

    if not answer_text and answer_desc:
        answer_text = answer_desc

    df = pd.DataFrame()
    if answer_sql:
        try:
            df = _fetch_query_df(poll_path, request_id=request_id)
        except Exception as exc:
            _log("genie_result_parse_err", request_id, error=str(exc))

    preview = df.head(20).to_dict(orient="records") if not df.empty else []
    return {
        "ok": True,
        "conversation_id": conv_id,
        "message_id": msg_id,
        "text": answer_text,
        "sql": answer_sql,
        "columns": list(df.columns),
        "preview": preview,
        "row_count": int(len(df)),
        "df": df,
    }


@st.cache_resource(show_spinner=False)
def _vector_search_client():
    from databricks.vector_search.client import VectorSearchClient

    return VectorSearchClient()


def _extract_vs_rows(raw: dict) -> List[dict]:
    # Support common response layouts across SDK versions.
    manifest_cols = raw.get("manifest", {}).get("columns", [])
    col_names = [c.get("name") if isinstance(c, dict) else str(c) for c in manifest_cols]

    data_array = raw.get("result", {}).get("data_array")
    if data_array and col_names:
        return [{col_names[i]: row[i] for i in range(min(len(col_names), len(row)))} for row in data_array]

    docs = raw.get("result", {}).get("docs")
    if isinstance(docs, list):
        return docs

    if isinstance(raw.get("results"), list):
        return raw["results"]

    if isinstance(raw.get("data"), list):
        return raw["data"]

    return []


def _tool_retrieve_playbook(query: str, request_id: str, k: Optional[int] = None) -> Dict[str, Any]:
    if not PLAYBOOK_VS_ENDPOINT or not PLAYBOOK_INDEX_NAME:
        return {
            "ok": False,
            "error": "Playbook retrieval is not configured. Set NEXOBI_PLAYBOOK_VS_ENDPOINT and NEXOBI_PLAYBOOK_INDEX_NAME.",
        }

    top_k = max(1, min(int(k or PLAYBOOK_K), 10))
    try:
        client = _vector_search_client()
        index = client.get_index(endpoint_name=PLAYBOOK_VS_ENDPOINT, index_name=PLAYBOOK_INDEX_NAME)
        raw = index.similarity_search(
            query_text=query,
            columns=[PLAYBOOK_ID_COLUMN, PLAYBOOK_TEXT_COLUMN],
            num_results=top_k,
        )
        rows = _extract_vs_rows(raw if isinstance(raw, dict) else {})
        snippets: List[dict] = []
        for row in rows:
            doc_id = row.get(PLAYBOOK_ID_COLUMN) or row.get("id") or "unknown"
            text = str(row.get(PLAYBOOK_TEXT_COLUMN) or row.get("text") or row.get("content") or "").strip()
            if not text:
                continue
            snippets.append({"id": str(doc_id), "text": text[:1200]})

        if not snippets:
            return {"ok": True, "count": 0, "snippets": [], "summary": "No relevant playbook context found."}

        summary = " | ".join([f"{s['id']}: {s['text'][:200]}" for s in snippets[:3]])
        _log("playbook_retrieve_ok", request_id, count=len(snippets), index=PLAYBOOK_INDEX_NAME)
        return {"ok": True, "count": len(snippets), "snippets": snippets, "summary": summary}
    except Exception as exc:
        _log("playbook_retrieve_err", request_id, error=str(exc), index=PLAYBOOK_INDEX_NAME)
        return {"ok": False, "error": f"Playbook retrieval failed: {exc}"}


def _llm_invoke(messages: List[dict], request_id: str, tools: Optional[List[dict]] = None) -> dict:
    if not ENABLE_LLM or not LLM_ENDPOINT:
        raise RuntimeError("LLM disabled or missing endpoint")

    body: Dict[str, Any] = {
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 500,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    return _dbx_do(
        "POST",
        f"/serving-endpoints/{LLM_ENDPOINT}/invocations",
        request_id=request_id,
        body=body,
    )


def _extract_assistant_message(resp: dict) -> dict:
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return {
        "content": msg.get("content", ""),
        "tool_calls": msg.get("tool_calls") or [],
        "role": msg.get("role", "assistant"),
    }


def _agent_answer(question: str, request_id: str) -> Dict[str, Any]:
    tools: List[dict] = [
        {
            "type": "function",
            "function": {
                "name": "ask_genie",
                "description": "Query Databricks Genie for business metrics and SQL-backed answers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The exact analytics question to send to Genie.",
                        }
                    },
                    "required": ["question"],
                },
            },
        }
    ]
    if PLAYBOOK_VS_ENDPOINT and PLAYBOOK_INDEX_NAME:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "retrieve_playbook",
                    "description": "Retrieve SOP/playbook snippets relevant to the current question.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "What guidance to retrieve from the playbook index.",
                            },
                            "k": {
                                "type": "integer",
                                "description": "Number of snippets to retrieve (1-10).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        )

    messages: List[dict] = [
        {
            "role": "system",
            "content": (
                "You are NexoBI Agent for healthcare practices. Use ask_genie when a question needs factual data. "
                "Use retrieve_playbook for SOP/best-practice guidance when relevant. "
                "When tool data returns, provide a concise answer with: direct answer, key insight, and one action. "
                "If data is unavailable, explain clearly and ask one focused follow-up."
            ),
        },
    ]

    summary = st.session_state.get("memory_summary", "")
    if summary:
        messages.append({"role": "system", "content": f"Session summary: {summary}"})

    messages.extend(st.session_state.get("llm_messages", []))
    messages.append({"role": "user", "content": question})

    latest_df = pd.DataFrame()
    latest_sql = ""
    latest_tool_text = ""
    latest_playbook: List[dict] = []

    for step in range(MAX_TOOL_STEPS):
        resp = _llm_invoke(messages=messages, tools=tools, request_id=request_id)
        assistant = _extract_assistant_message(resp)
        content = assistant.get("content", "")
        tool_calls = assistant.get("tool_calls", [])

        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls if tool_calls else None,
        })

        if not tool_calls:
            if not content.strip() and latest_tool_text:
                content = latest_tool_text
            return {
                "ok": True,
                "answer": content.strip(),
                "sql": latest_sql,
                "df": latest_df,
                "playbook_snippets": latest_playbook,
                "used_tools": step > 0,
                "messages": messages,
            }

        for tc in tool_calls:
            call_id = tc.get("id", str(uuid.uuid4()))
            fn = (tc.get("function") or {}).get("name")
            args_raw = (tc.get("function") or {}).get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except Exception:
                args = {}

            if fn == "ask_genie":
                tool_q = args.get("question") or question
                tool_payload = _tool_ask_genie(tool_q, request_id=request_id)
                if tool_payload.get("ok"):
                    latest_df = tool_payload.get("df", pd.DataFrame())
                    latest_sql = tool_payload.get("sql", "")
                    latest_tool_text = tool_payload.get("text", "")
            elif fn == "retrieve_playbook":
                playbook_q = args.get("query") or question
                playbook_k = args.get("k")
                tool_payload = _tool_retrieve_playbook(playbook_q, request_id=request_id, k=playbook_k)
                if tool_payload.get("ok"):
                    latest_playbook = tool_payload.get("snippets", [])
            else:
                tool_payload = {"ok": False, "error": f"Unknown tool: {fn}"}

            tool_payload_for_llm = dict(tool_payload)
            if "df" in tool_payload_for_llm:
                del tool_payload_for_llm["df"]

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn,
                    "content": json.dumps(tool_payload_for_llm, default=str),
                }
            )

    return {
        "ok": False,
        "error": "Agent reached tool step limit before final answer.",
        "sql": latest_sql,
        "df": latest_df,
        "playbook_snippets": latest_playbook,
    }


def _chart_if_possible(df: pd.DataFrame) -> bool:
    if df is None or df.empty or len(df) < 2:
        return False

    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    for c in df.columns:
        if c in date_cols or c in numeric_cols:
            continue
        converted = pd.to_datetime(df[c], errors="coerce")
        if converted.notna().mean() > 0.7:
            df = df.copy()
            df[c] = converted
            date_cols.append(c)

    if date_cols and numeric_cols:
        idx = date_cols[0]
        chart_df = df[[idx] + numeric_cols[:3]].dropna().set_index(idx)
        if not chart_df.empty:
            st.line_chart(chart_df)
            return True

    if numeric_cols:
        first_num = numeric_cols[0]
        cat_cols = [c for c in df.columns if c not in numeric_cols]
        if cat_cols:
            idx = cat_cols[0]
            chart_df = df[[idx, first_num]].dropna().set_index(idx).sort_values(first_num, ascending=False).head(20)
            if not chart_df.empty:
                st.bar_chart(chart_df)
                return True
        st.line_chart(df[numeric_cols[:3]].dropna())
        return True

    return False


def _update_memory_summary() -> None:
    # Keep a compact summary to reduce prompt growth.
    history = st.session_state.get("chat_history", [])[-6:]
    if not history:
        st.session_state["memory_summary"] = ""
        return

    chunks = []
    for item in history:
        q = item.get("q", "")[:120]
        a = item.get("answer", "")[:180]
        chunks.append(f"Q:{q} | A:{a}")
    st.session_state["memory_summary"] = " || ".join(chunks)[:1200]


# ----------------------------------------------------------
# Session state
# ----------------------------------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "genie_conversation_id" not in st.session_state:
    st.session_state.genie_conversation_id = None
if "llm_messages" not in st.session_state:
    st.session_state.llm_messages = []
if "memory_summary" not in st.session_state:
    st.session_state.memory_summary = ""


# ----------------------------------------------------------
# UI
# ----------------------------------------------------------
st.markdown('<div class="ai-title">NexoBI Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="ai-sub">Genie-backed agent chat with tool calling, memory, and action-oriented answers.</div>', unsafe_allow_html=True)

col1, col2 = st.columns([8, 1])
with col1:
    user_q = st.text_area("", placeholder="Ask a business question...", label_visibility="collapsed", height=88)
with col2:
    st.markdown('<div style="height:1.3rem"></div>', unsafe_allow_html=True)
    ask = st.button("Ask", use_container_width=True, type="primary")

if ask:
    query = user_q.strip()
    if not query:
        st.warning("Please enter a question.")
    else:
        request_id = str(uuid.uuid4())
        _log("user_query", request_id, q_len=len(query))
        with st.spinner("Thinking..."):
            try:
                result = _agent_answer(query, request_id=request_id)
            except Exception as exc:
                _log("agent_error", request_id, error=str(exc))
                result = {"ok": False, "error": f"Request failed. Request ID: {request_id}"}

        if result.get("ok"):
            item = {
                "q": query,
                "answer": result.get("answer", ""),
                "sql": result.get("sql", ""),
                "df": result.get("df", pd.DataFrame()),
                "playbook_snippets": result.get("playbook_snippets", []),
                "request_id": request_id,
                "error": None,
            }

            new_llm_msgs = [
                {"role": "user", "content": query},
                {"role": "assistant", "content": item["answer"]},
            ]
            st.session_state.llm_messages.extend(new_llm_msgs)
            st.session_state.llm_messages = st.session_state.llm_messages[-20:]
        else:
            item = {
                "q": query,
                "answer": "",
                "sql": result.get("sql", ""),
                "df": result.get("df", pd.DataFrame()),
                "playbook_snippets": result.get("playbook_snippets", []),
                "request_id": request_id,
                "error": result.get("error", "Unknown error"),
            }

        st.session_state.chat_history.insert(0, item)
        st.session_state.chat_history = st.session_state.chat_history[:MAX_HISTORY]
        _update_memory_summary()
        st.rerun()


for item in st.session_state.chat_history:
    st.write(f"**You:** {item.get('q', '')}")

    if item.get("error"):
        st.error(item["error"])
        st.caption(f"Request ID: {item.get('request_id', '')}")
        continue

    st.write(item.get("answer", ""))
    st.caption(f"Request ID: {item.get('request_id', '')}")

    df = item.get("df")
    if isinstance(df, pd.DataFrame) and not df.empty:
        _chart_if_possible(df)
        with st.expander("View data", expanded=False):
            st.dataframe(df, use_container_width=True, hide_index=True)

    sql = item.get("sql", "")
    if sql:
        with st.expander("View SQL", expanded=False):
            st.code(sql, language="sql")

    snippets = item.get("playbook_snippets", [])
    if snippets:
        with st.expander("Playbook context", expanded=False):
            for s in snippets:
                st.markdown(f"**{s.get('id', 'doc')}**")
                st.write(s.get("text", ""))


controls = st.columns([1, 1, 5])
with controls[0]:
    if st.button("New chat"):
        st.session_state.chat_history = []
        st.session_state.llm_messages = []
        st.session_state.memory_summary = ""
        st.session_state.genie_conversation_id = None
        st.rerun()
with controls[1]:
    if st.button("Reset Genie"):
        st.session_state.genie_conversation_id = None
        st.rerun()

st.caption(
    "Runbook: configure Genie, LLM endpoint, optional Vector Search playbook index, and least-privilege Databricks auth."
)
