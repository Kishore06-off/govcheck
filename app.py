import streamlit as st
import time
import json
import random
import requests
import os
import uuid
import pandas as pd
import re

API_URL = os.getenv("API_URL", "http://localhost:8000")

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GovCheck AI",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "ui_theme" not in st.session_state:
    st.session_state.ui_theme = "dark"

# ── Global CSS ────────────────────────────────────────────────────────────────
if st.session_state.ui_theme == "light":
    theme_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Root & base (LIGHT) ── */
:root {
    --teal:        #00a884;
    --teal-dim:    rgba(0,168,132,0.18);
    --teal-glow:   rgba(0,168,132,0.06);
    --blue:        #2563eb;
    --blue-dim:    rgba(37,99,235,0.18);
    --amber:       #d97706;
    --amber-dim:   rgba(217,119,6,0.18);
    --purple:      #9333ea;
    --purple-dim:  rgba(147,51,234,0.18);
    --coral:       #e11d48;
    --coral-dim:   rgba(225,29,72,0.18);
    --glass-bg:    rgba(255,255,255,0.7);
    --glass-bdr:   rgba(0,0,0,0.10);
    --glass-bdr2:  rgba(0,0,0,0.16);
    --text-pri:    rgba(15,23,42,0.95);
    --text-sec:    rgba(15,23,42,0.65);
    --text-ter:    rgba(15,23,42,0.40);
    --sidebar-bg:  rgba(255,255,255,0.70);
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: #eef2f6 !important;
    font-family: 'Outfit', sans-serif !important;
    color: var(--text-pri) !important;
}

/* Mesh gradient background (LIGHT) */
[data-testid="stAppViewContainer"]::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 80% 60% at 10% 0%,   rgba(37,99,235,0.05) 0%, transparent 60%),
        radial-gradient(ellipse 60% 50% at 90% 10%,  rgba(0,168,132,0.05) 0%, transparent 60%),
        radial-gradient(ellipse 50% 60% at 50% 100%, rgba(217,119,6,0.05) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
}
"""
else:
    theme_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Root & base ── */
:root {
    --teal:        #0ff2c8;
    --teal-dim:    rgba(15,242,200,0.18);
    --teal-glow:   rgba(15,242,200,0.06);
    --blue:        #5b8ef0;
    --blue-dim:    rgba(91,142,240,0.18);
    --amber:       #f5c542;
    --amber-dim:   rgba(245,197,66,0.18);
    --purple:      #c084fc;
    --purple-dim:  rgba(192,132,252,0.18);
    --coral:       #fb7185;
    --coral-dim:   rgba(251,113,133,0.18);
    --glass-bg:    rgba(255,255,255,0.04);
    --glass-bdr:   rgba(255,255,255,0.10);
    --glass-bdr2:  rgba(255,255,255,0.16);
    --text-pri:    rgba(255,255,255,0.95);
    --text-sec:    rgba(255,255,255,0.55);
    --text-ter:    rgba(255,255,255,0.30);
    --sidebar-bg:  rgba(6,12,24,0.7);
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: #060c18 !important;
    font-family: 'Outfit', sans-serif !important;
    color: var(--text-pri) !important;
}

/* Mesh gradient background (DARK) */
[data-testid="stAppViewContainer"]::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
        radial-gradient(ellipse 80% 60% at 10% 0%,   rgba(15,242,200,0.12) 0%, transparent 60%),
        radial-gradient(ellipse 60% 50% at 90% 10%,  rgba(91,142,240,0.14) 0%, transparent 60%),
        radial-gradient(ellipse 50% 60% at 50% 100%, rgba(192,132,252,0.10) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
}
"""

st.markdown(theme_css + """
/* Kill default streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stSidebarCollapseButton"] { display: none; }
section[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

/* ── Sidebar glass ── */
section[data-testid="stSidebar"] {
    background: var(--sidebar-bg) !important;
    backdrop-filter: blur(24px) !important;
    border-right: 1px solid var(--glass-bdr) !important;
}
section[data-testid="stSidebar"] * { color: var(--text-pri) !important; }

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: var(--glass-bg) !important;
    border: 1.5px dashed var(--teal-dim) !important;
    border-radius: 16px !important;
    backdrop-filter: blur(12px) !important;
    transition: border-color 0.2s, background 0.2s !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--teal) !important;
    background: var(--teal-glow) !important;
}
[data-testid="stFileUploader"] label { color: var(--text-sec) !important; }
[data-testid="stFileUploader"] button {
    background: var(--teal-dim) !important;
    border: 1px solid rgba(15,242,200,0.3) !important;
    color: var(--teal) !important;
    border-radius: 8px !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
}

/* ── Selectbox ── */
[data-testid="stSelectbox"] > div > div {
    background: var(--glass-bg) !important;
    border: 1px solid var(--glass-bdr) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(12px) !important;
    color: var(--text-pri) !important;
}
[data-testid="stSelectbox"] svg { fill: var(--text-sec) !important; }

/* ── Text input ── */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
    background: var(--glass-bg) !important;
    border: 1px solid var(--glass-bdr) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(12px) !important;
    color: var(--text-pri) !important;
    font-family: 'Outfit', sans-serif !important;
}
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus {
    border-color: rgba(15,242,200,0.5) !important;
    box-shadow: 0 0 0 3px rgba(15,242,200,0.08) !important;
}

/* ── Progress bar ── */
[data-testid="stProgress"] > div > div > div {
    background: linear-gradient(90deg, var(--teal), var(--blue)) !important;
    border-radius: 99px !important;
}
[data-testid="stProgress"] > div > div {
    background: rgba(255,255,255,0.08) !important;
    border-radius: 99px !important;
}

/* ── Buttons ── */
.stButton > button {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    border-radius: 10px !important;
    transition: all 0.2s !important;
    border: 1px solid var(--glass-bdr2) !important;
    background: var(--glass-bg) !important;
    color: var(--text-pri) !important;
    backdrop-filter: blur(12px) !important;
}
.stButton > button:hover {
    background: rgba(255,255,255,0.10) !important;
    border-color: var(--teal) !important;
    color: var(--teal) !important;
    box-shadow: 0 0 16px rgba(15,242,200,0.15) !important;
}

/* Primary action button */
button[kind="primary"] {
    background: linear-gradient(135deg, rgba(15,242,200,0.25), rgba(91,142,240,0.20)) !important;
    border-color: rgba(15,242,200,0.5) !important;
    color: var(--teal) !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
}
button[kind="primary"]:hover {
    background: linear-gradient(135deg, rgba(15,242,200,0.35), rgba(91,142,240,0.30)) !important;
    box-shadow: 0 0 24px rgba(15,242,200,0.25) !important;
}

/* Export buttons */
[data-testid="stDownloadButton"] button {
    font-size: 13px !important;
    padding: 6px 14px !important;
    height: auto !important;
}

/* ── Checkbox ── */
[data-testid="stCheckbox"] label span { color: var(--text-sec) !important; font-size: 13px !important; }
[data-testid="stCheckbox"] input:checked + div {
    background: var(--teal) !important;
    border-color: var(--teal) !important;
}

/* ── Divider ── */
hr { border-color: var(--glass-bdr) !important; margin: 12px 0 !important; }

/* ── Metric ── */
[data-testid="stMetric"] {
    background: var(--glass-bg) !important;
    border: 1px solid var(--glass-bdr) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(16px) !important;
    padding: 16px 20px !important;
}
[data-testid="stMetricLabel"] { color: var(--text-sec) !important; font-size: 11px !important; letter-spacing: 0.5px !important; }
[data-testid="stMetricValue"] { color: var(--text-pri) !important; font-family: 'Outfit', sans-serif !important; font-weight: 600 !important; }
[data-testid="stMetricDelta"] { font-size: 11px !important; }

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    background: var(--glass-bg) !important;
    border: 1px solid var(--glass-bdr) !important;
    border-radius: 12px !important;
    padding: 4px !important;
    backdrop-filter: blur(12px) !important;
    gap: 2px !important;
}
[data-testid="stTabs"] button[role="tab"] {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    color: var(--text-sec) !important;
    border: none !important;
    background: transparent !important;
    transition: all 0.2s !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: rgba(255,255,255,0.10) !important;
    color: var(--text-pri) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: var(--glass-bg) !important;
    border: 1px solid var(--glass-bdr) !important;
    border-radius: 12px !important;
    backdrop-filter: blur(12px) !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    color: var(--text-pri) !important;
    font-weight: 500 !important;
    font-size: 13px !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    background: var(--glass-bg) !important;
    border: 1px solid var(--glass-bdr) !important;
    border-radius: 12px !important;
    backdrop-filter: blur(12px) !important;
    overflow: hidden !important;
}

/* ── Custom glass card ── */
.glass-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 16px;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    padding: 20px 22px;
    margin-bottom: 12px;
    position: relative;
    overflow: hidden;
}
.glass-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent);
}
.glass-card-teal  { border-color: rgba(15,242,200,0.22);  background: rgba(15,242,200,0.04); }
.glass-card-blue  { border-color: rgba(91,142,240,0.22);  background: rgba(91,142,240,0.04); }
.glass-card-amber { border-color: rgba(245,197,66,0.22);  background: rgba(245,197,66,0.04); }
.glass-card-purple{ border-color: rgba(192,132,252,0.22); background: rgba(192,132,252,0.04); }
.glass-card-coral { border-color: rgba(251,113,133,0.22); background: rgba(251,113,133,0.04); }

/* ── Badge ── */
.badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
    padding: 2px 8px;
    border-radius: 20px;
    font-family: 'JetBrains Mono', monospace;
    text-transform: lowercase;
}
.badge-teal   { background: rgba(15,242,200,0.15);  color: #0ff2c8; border: 1px solid rgba(15,242,200,0.3); }
.badge-blue   { background: rgba(91,142,240,0.15);  color: #8ab4f8; border: 1px solid rgba(91,142,240,0.3); }
.badge-amber  { background: rgba(245,197,66,0.15);  color: #f5c542; border: 1px solid rgba(245,197,66,0.3); }
.badge-purple { background: rgba(192,132,252,0.15); color: #c084fc; border: 1px solid rgba(192,132,252,0.3); }
.badge-coral  { background: rgba(251,113,133,0.15); color: #fb7185; border: 1px solid rgba(251,113,133,0.3); }

/* ── Topbar ── */
.gov-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    margin-bottom: 20px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    backdrop-filter: blur(20px);
    position: relative;
    overflow: hidden;
}
.gov-topbar::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(15,242,200,0.4), rgba(91,142,240,0.4), transparent);
}
.gov-logo-text {
    font-size: 20px;
    font-weight: 700;
    background: linear-gradient(135deg, #0ff2c8, #5b8ef0);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.5px;
}
.gov-session {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: rgba(255,255,255,0.35);
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px;
    padding: 5px 12px;
}

/* ── Pipeline step ── */
.pipeline-step {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 10px;
    border-radius: 8px;
    margin-bottom: 4px;
    font-size: 12px;
}
.pipeline-step.done    { background: rgba(15,242,200,0.08);  color: #0ff2c8; }
.pipeline-step.active  { background: rgba(245,197,66,0.10); color: #f5c542; }
.pipeline-step.pending { color: rgba(255,255,255,0.30); }
.step-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
.dot-done    { background: #0ff2c8; box-shadow: 0 0 6px rgba(15,242,200,0.6); }
.dot-active  { background: #f5c542; box-shadow: 0 0 6px rgba(245,197,66,0.6); animation: pulse 1s ease-in-out infinite; }
.dot-pending { background: rgba(255,255,255,0.18); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

/* ── Domain pill ── */
.domain-pill {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-radius: 10px;
    border: 1px solid transparent;
    cursor: pointer;
    margin-bottom: 4px;
    transition: all 0.15s;
    background: rgba(255,255,255,0.02);
}
.domain-pill:hover { border-color: rgba(255,255,255,0.12); background: rgba(255,255,255,0.05); }
.domain-pill.active-domain { border-color: rgba(15,242,200,0.3); background: rgba(15,242,200,0.07); }
.domain-count-pill {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    background: rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 1px 7px;
    color: rgba(255,255,255,0.45);
}

/* ── Checklist row ── */
.checklist-row {
    display: grid;
    grid-template-columns: 24px 1fr 110px 80px;
    gap: 12px;
    align-items: center;
    padding: 11px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    transition: background 0.12s;
    font-size: 12.5px;
}
.checklist-row:hover { background: rgba(255,255,255,0.03); }
.checklist-row.header {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.6px;
    color: rgba(255,255,255,0.3);
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding: 8px 14px;
}

/* ── Chunk card ── */
.chunk-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 8px;
    transition: border-color 0.15s;
}
.chunk-card:hover { border-color: rgba(255,255,255,0.16); }
.chunk-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 7px;
    flex-wrap: wrap;
}
.chunk-source {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: rgba(255,255,255,0.3);
}
.chunk-score {
    margin-left: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: #0ff2c8;
    font-weight: 500;
}
.chunk-text {
    font-size: 12px;
    color: rgba(255,255,255,0.55);
    line-height: 1.6;
    font-style: italic;
}

/* ── Sidebar labels ── */
.sidebar-label {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.25) !important;
    margin: 16px 0 8px;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Status glow ── */
.status-glow {
    font-size: 10px;
    font-family: 'JetBrains Mono', monospace;
    color: #0ff2c8;
    background: rgba(15,242,200,0.10);
    border: 1px solid rgba(15,242,200,0.25);
    border-radius: 20px;
    padding: 3px 10px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
}
.live-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: #0ff2c8;
    box-shadow: 0 0 5px rgba(15,242,200,0.8);
    display: inline-block;
    animation: pulse 1.5s ease-in-out infinite;
}

.col-label { color: rgba(255,255,255,0.40) !important; font-size: 11px !important; }
.mono { font-family: 'JetBrains Mono', monospace; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "checklist" not in st.session_state:
    st.session_state.checklist = []
    
if "doc_meta" not in st.session_state:
    st.session_state.doc_meta = {"name": "", "chunks": 0, "reqs": 0, "docs": []}

if "pipeline_progress" not in st.session_state:
    st.session_state.pipeline_progress = 0.0

if "active_domain" not in st.session_state:
    st.session_state.active_domain = "all"
    
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
    
if "docs" not in st.session_state:
    st.session_state.docs = []    

# ── Topbar ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="gov-topbar">
  <div style="display:flex;align-items:center;gap:14px">
    <div style="width:36px;height:36px;background:linear-gradient(135deg,rgba(15,242,200,0.3),rgba(91,142,240,0.3));border:1px solid rgba(15,242,200,0.4);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px">🏛️</div>
    <div>
      <div class="gov-logo-text">GovCheck AI</div>
      <div style="font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:0.5px;margin-top:1px">Hybrid RAG · Compliance Intelligence</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <span class="status-glow"><span class="live-dot"></span>Session active</span>
    <span class="gov-session">{st.session_state.user_id}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Functions ───────────────────────────────────────────────────────────────
def get_badge_info(domain):
    badge_map = {
        "data_privacy"        : ("badge-teal",   "Data Privacy"),
        "security"            : ("badge-blue",   "Security"),
        "audit"               : ("badge-purple", "Audit"),
        "risk_mgmt"           : ("badge-amber",  "Risk Mgmt"),
        "hr_policy"           : ("badge-coral",  "HR Policy"),
        # Generator valid domains
        "board_governance"    : ("badge-blue",   "Board Governance"),
        "risk_management"     : ("badge-amber",  "Risk Management"),
        "audit_compliance"    : ("badge-purple", "Audit Compliance"),
        "shareholder_rights"  : ("badge-teal",   "Shareholder Rights"),
        "csr"                 : ("badge-coral",  "CSR"),
        "financial_compliance": ("badge-amber",  "Financial Compliance"),
    }
    return badge_map.get(str(domain).lower(), ("badge-teal", str(domain).title().replace("_", " ")))


def checklist_rows_for_csv(checklist: list) -> tuple[list[dict], list[str]]:
    """Stable columns aligned with API checklist items + UI fields."""
    cols = [
        "id",
        "requirement",
        "domain",
        "source_section",
        "priority",
        "action_type",
        "evidence_required",
        "chunk_id",
        "source_url",
        "compliance_framework",
        "done",
        "rt_score",
        "rt_risk",
    ]
    rows = []
    for r in checklist:
        req = r.get("req") or r.get("item") or r.get("requirement") or ""
        src = (
            r.get("source_section")
            or r.get("sourceSection")
            or r.get("source")
            or ""
        )
        rows.append(
            {
                "id": r.get("id", ""),
                "requirement": req,
                "domain": r.get("domain", ""),
                "source_section": src,
                "priority": r.get("priority", ""),
                "action_type": r.get("action_type", ""),
                "evidence_required": r.get("evidence_required", ""),
                "chunk_id": r.get("chunk_id", ""),
                "source_url": r.get("source_url", ""),
                "compliance_framework": r.get("compliance_framework", ""),
                "done": r.get("done", ""),
                "rt_score": r.get("rt_score", ""),
                "rt_risk": r.get("rt_risk", ""),
            }
        )
    return rows, cols

def _extract_citations(text: str) -> list[str]:
    """Extract chunk_id citations in format [chunk_id:<id>]."""
    return re.findall(r"\[chunk_id:([a-zA-Z0-9_\-]+)\]", text or "")

def _render_citation_chips(citations: list[str]) -> None:
    if not citations:
        return
    chips = " ".join([f'<span class="badge badge-teal">chunk {c}</span>' for c in citations[:12]])
    st.markdown(f'<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:6px">{chips}</div>', unsafe_allow_html=True)

def _build_audit_report_md(checklist: list[dict]) -> str:
    lines = []
    lines.append("# GovCheck AI — Audit Report")
    lines.append("")
    lines.append(f"- Total checklist items: {len(checklist)}")
    done_count = sum(1 for x in checklist if x.get("done"))
    lines.append(f"- Completed: {done_count}")
    lines.append("")
    lines.append("## Checklist")
    lines.append("")
    for i, it in enumerate(checklist, 1):
        req = it.get("req") or it.get("item") or it.get("requirement") or ""
        domain = it.get("domain", "")
        priority = it.get("priority", "")
        chunk_id = it.get("chunk_id", "")
        src = it.get("source_section") or it.get("source") or ""
        score = it.get("retrieval_score", "")
        lines.append(f"{i}. **{req}**")
        meta = []
        if domain:
            meta.append(f"domain: `{domain}`")
        if priority:
            meta.append(f"priority: `{priority}`")
        if chunk_id:
            meta.append(f"citation: `[chunk_id:{chunk_id}]`")
        if src:
            meta.append(f"section: {src}")
        if score != "" and score is not None:
            try:
                meta.append(f"retrieval_score: `{float(score):.4f}`")
            except Exception:
                meta.append(f"retrieval_score: `{score}`")
        if meta:
            lines.append(f"   - " + " | ".join(meta))
        lines.append("")
    return "\n".join(lines)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    sc1, sc2 = st.columns([4, 1])
    with sc1:
        st.markdown('<div style="padding:16px 0 8px"><div class="gov-logo-text" style="font-size:15px">⬆ Ingestion</div></div>', unsafe_allow_html=True)
    with sc2:
        st.write("") # small padding
        if st.button("☀️" if st.session_state.ui_theme == "dark" else "🌙", key="theme_toggle"):
            st.session_state.ui_theme = "light" if st.session_state.ui_theme == "dark" else "dark"
            st.rerun()

    uploaded = st.file_uploader(
        "Upload governance documents",
        type=["pdf", "docx", "xlsx", "csv", "txt"],
        accept_multiple_files=False,
        label_visibility="collapsed",
        help="Supports PDF, Word, Excel, CSV, TXT",
    )

    st.markdown("""
    <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:8px;margin-bottom:4px">
      <span class="badge badge-teal">.pdf</span>
      <span class="badge badge-blue">.docx</span>
      <span class="badge badge-amber">.xlsx</span>
      <span class="badge badge-purple">.csv</span>
      <span class="badge" style="background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.4);border:1px solid rgba(255,255,255,0.12)">.txt</span>
      <span class="badge" style="background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.4);border:1px solid rgba(255,255,255,0.12)">URL</span>
    </div>
    """, unsafe_allow_html=True)

    url_input = st.text_input("Or paste a URL / Web link", placeholder="https://...", label_visibility="visible")

    if uploaded or url_input:
        process_btn = st.button("▶  Process documents", type="primary", use_container_width=True, key="process_btn")
        
        if process_btn:
            with st.spinner("Processing..."):
                if uploaded:
                    files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type)}
                    data = {"user_id": st.session_state["user_id"]}
                    st.session_state.doc_meta["name"] = uploaded.name
                    res = requests.post(f"{API_URL}/api/upload", files=files, data=data)
                    st.session_state.docs.append((uploaded.name, uploaded.type, "uploaded"))
                elif url_input:
                    data = {"link": url_input.strip(), "user_id": st.session_state["user_id"]}
                    st.session_state.doc_meta["name"] = str(url_input).split("/")[-1][:30] or "Cloud Document"
                    res = requests.post(f"{API_URL}/api/upload", data=data)
                    st.session_state.docs.append((url_input, "URL", "link"))
                
                if res.status_code == 200:
                    job_id = res.json()["job_id"]
                    prog_bar = st.progress(0.0, text="")
                    
                    db_completed = False
                    poll_error = None
                    poll_ms = float(os.getenv("STREAMLIT_STATUS_POLL_SEC", "0.35"))
                    while not db_completed:
                        time.sleep(poll_ms)
                        try:
                            status_res = requests.get(f"{API_URL}/api/status/{job_id}")
                            if status_res.status_code != 200:
                                poll_error = f"Status HTTP {status_res.status_code}"
                                break
                            status_data = status_res.json()
                            st.session_state.pipeline_progress = status_data["progress"] / 100.0
                            prog_bar.progress(st.session_state.pipeline_progress)
                            if status_data["status"] == "error":
                                poll_error = status_data.get("message", "Pipeline failed")
                                break
                            if status_data["status"] == "completed" or status_data["progress"] == 100:
                                db_completed = True
                        except Exception as ex:
                            poll_error = str(ex)
                            break

                    if poll_error:
                        st.error(f"Ingestion failed: {poll_error}")
                    else:
                        st.success("Pipeline complete!", icon="✅")

                    # Fetch initial checklist (backend truth only; no mock injection)
                    if not poll_error:
                        payload_data = {
                            "query": "Extract all compliance policies, requirements, and checklist items. Strictly format as JSON.",
                            "domain": "all",
                            "user_id": st.session_state["user_id"],
                        }
                        chat_res = requests.post(f"{API_URL}/api/chat", json=payload_data)
                        if chat_res.status_code == 200:
                            payload = chat_res.json()
                            raw_data = payload.get("raw_data")
                            st.session_state.checklist = raw_data if raw_data is not None else []
                            # Ensure domain filter stays valid across new uploads.
                            domains_now = {str(x.get("domain", "general")) for x in st.session_state.checklist}
                            if st.session_state.active_domain != "all" and st.session_state.active_domain not in domains_now:
                                st.session_state.active_domain = "all"

                            st.session_state.doc_meta["reqs"] = len(st.session_state.checklist)
                            # Re-format checklist to match the new UI's expected format if needed
                            for i, c in enumerate(st.session_state.checklist):
                                if "id" not in c:
                                    c["id"] = f"{i+1:02d}"
                                if "req" not in c:
                                    c["req"] = c.get("requirement", c.get("item", "Unknown requirement"))
                                if "done" not in c:
                                    c["done"] = False
                                domain_str = str(c.get("domain", "")).lower().replace(" ", "_")
                                if "badge" not in c:
                                    c["badge"], _ = get_badge_info(domain_str)
                                if "source" not in c:
                                    c["source"] = c.get(
                                        "sourceSection",
                                        c.get("source_section", c.get("source", "N/A")),
                                    )
                        else:
                            st.session_state.checklist = []
                else:
                    st.error(f"Error {res.status_code}: {res.text}")

    # Pipeline status
    st.markdown('<div class="sidebar-label">ETL pipeline</div>', unsafe_allow_html=True)
    progress = st.session_state.pipeline_progress

    steps = [
        ("Extracting text",       1.0 if progress > 0 else 0.0),
        ("Chunking & metadata",   1.0 if progress >= 0.25 else 0.0),
        ("Domain classification", 1.0 if progress >= 0.50 else 0.0),
        ("Embedding vectors",     1.0 if progress >= 0.75 else (progress if progress > 0.50 else 0.0)),
        ("BM25 indexing",         1.0 if progress >= 1.0 else 0.0),
    ]

    for label, done_frac in steps:
        if done_frac >= 1.0:
            state, dot_cls, cls = "done",    "dot-done",    "done"
        elif done_frac > 0.0:
            state, dot_cls, cls = "active",  "dot-active",  "active"
        else:
            state, dot_cls, cls = "pending", "dot-pending", "pending"
        st.markdown(f"""
        <div class="pipeline-step {cls}">
          <span class="step-dot {dot_cls}"></span>
          {label}
        </div>
        """, unsafe_allow_html=True)

    st.progress(min(progress, 1.0))
    chunks_done = int(progress * 458)  # Dummy approx number or actual
    st.markdown(f'<div style="font-size:10px;color:rgba(255,255,255,0.3);text-align:right;margin-top:2px;font-family:JetBrains Mono,monospace">{int(progress*100)}%</div>', unsafe_allow_html=True)

    # Domain filter
    st.markdown('<div class="sidebar-label">Filter by domain</div>', unsafe_allow_html=True)

    all_domains = list(set([x.get("domain", "general") for x in st.session_state.checklist]))
    
    # Calculate counts dynamically
    dom_counts = {"all": len(st.session_state.checklist)}
    for d in all_domains:
        dom_counts[d] = len([x for x in st.session_state.checklist if x.get("domain") == d])

    domains = [
        ("all",          "All domains",     "rgba(255,255,255,0.45)", dom_counts["all"]),
    ]
    
    color_map = {
        "data_privacy"        : "#0ff2c8",
        "security"            : "#5b8ef0",
        "risk_mgmt"           : "#f5c542",
        "audit"               : "#c084fc",
        "hr_policy"           : "#fb7185",
        # Generator valid domains
        "board_governance"    : "#5b8ef0",
        "risk_management"     : "#f5c542",
        "audit_compliance"    : "#c084fc",
        "shareholder_rights"  : "#0ff2c8",
        "csr"                 : "#fb7185",
        "financial_compliance": "#f5c542",
    }
    for d in all_domains:
        label = d.replace("_", " ").title()
        color = color_map.get(d, "#0ff2c8")
        domains.append((d, label, color, dom_counts[d]))

    for key, label, color, count in domains:
        active_cls = "active-domain" if st.session_state.active_domain == key else ""
        st.markdown(f"""
        <div class="domain-pill {active_cls}">
          <div style="display:flex;align-items:center;gap:8px">
            <span style="width:8px;height:8px;border-radius:2px;background:{color};display:inline-block;box-shadow:0 0 5px {color}55"></span>
            <span style="font-size:12px;color:rgba(255,255,255,0.75)">{label}</span>
          </div>
          <span class="domain-count-pill">{count}</span>
        </div>
        """, unsafe_allow_html=True)
        if st.button(label, key=f"dom_{key}", use_container_width=True):
            st.session_state.active_domain = key
            st.rerun()

    st.markdown('<div class="sidebar-label">Session</div>', unsafe_allow_html=True)
    if st.button(
        "⟳ Start Over",
        use_container_width=True,
        key="sidebar_start_over",
        help="Reset session: clear checklist, chat, uploads, and pipeline progress for a new document.",
    ):
        st.session_state.clear()
        st.rerun()

# ── Main content ──────────────────────────────────────────────────────────────
done_count = sum(1 for item in st.session_state.checklist if item.get("done", False))
total      = len(st.session_state.checklist)

# Metrics
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Ingested docs", str(len(st.session_state.docs)), "Session active")
with c2:
    st.metric("Checklist items", str(total), f"{total} extracted")
with c3:
    pct = int(done_count / total * 100) if total > 0 else 0
    st.metric("Completed", f"{done_count}/{total}", f"{pct}% compliance rate")
with c4:
    # Computed from retrieval scores if present; otherwise show N/A.
    scores = []
    for it in st.session_state.checklist:
        s = it.get("retrieval_score") or it.get("rt_score")
        try:
            if s is not None and str(s) != "":
                scores.append(float(s))
        except Exception:
            pass
    avg = (sum(scores) / len(scores)) if scores else None
    st.metric("Avg retrieval score", f"{avg:.3f}" if avg is not None else "N/A", "RRF fused")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# Tabs
tab1, tab2, tab3 = st.tabs(["📋  Checklist", "🔍  RAG Chat", "📊  Analytics"])

# ── TAB 1: Checklist ──────────────────────────────────────────────────────────
with tab1:
    # Export row
    ec1, ec2, ec3, ec4, ec5 = st.columns([1.5, 1.5, 1.5, 2.5, 2.0])
    
    has_data = len(st.session_state.checklist) > 0

    with ec1:
        if has_data:
            csv_rows, csv_cols = checklist_rows_for_csv(st.session_state.checklist)
            csv_data = pd.DataFrame(csv_rows, columns=csv_cols).to_csv(index=False).encode("utf-8")
        else:
            csv_data = b""
        st.download_button("⬇ CSV", data=csv_data, file_name="checklist.csv", mime="text/csv", use_container_width=True, disabled=not has_data, type="primary")
    with ec2:
        json_data = json.dumps(st.session_state.checklist, indent=2) if has_data else "{}"
        st.download_button("⬇ JSON", data=json_data, file_name="checklist.json", mime="application/json", use_container_width=True, disabled=not has_data, type="primary")
    with ec3:
        import io
        buf = io.BytesIO()
        if has_data:
            pd.DataFrame(st.session_state.checklist).to_excel(buf, index=False, engine='openpyxl')
        st.download_button("⬇ Excel", data=buf.getvalue(), file_name="checklist.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, disabled=not has_data, type="primary")
    with ec4:
        report_md = _build_audit_report_md(st.session_state.checklist) if has_data else ""
        st.download_button(
            "⬇ Audit Report (MD)",
            data=report_md,
            file_name="audit_report.md",
            mime="text/markdown",
            use_container_width=True,
            disabled=not has_data,
            type="primary",
        )
    with ec5:
        if st.button("⟳ Start Over", type="primary", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    filtered_checklist = [c for c in st.session_state.checklist if st.session_state.active_domain == "all" or c.get("domain") == st.session_state.active_domain]
    # Fallback if current filter yields nothing but checklist has data.
    if not filtered_checklist and st.session_state.checklist:
        st.session_state.active_domain = "all"
        filtered_checklist = list(st.session_state.checklist)
    if not filtered_checklist:
        st.info("No checklist items to display for the selected domain.")
    else:
        # Sortable, sticky-header table via Streamlit editor (supports checkbox column)
        df = pd.DataFrame(
            [
                {
                    "done": bool(it.get("done", False)),
                    "priority": it.get("priority", ""),
                    "domain": it.get("domain", ""),
                    "requirement": it.get("req") or it.get("item") or it.get("requirement") or "",
                    "source_section": it.get("source_section") or it.get("source") or "",
                    "chunk_id": it.get("chunk_id", ""),
                    "retrieval_score": it.get("retrieval_score", it.get("rt_score", "")),
                    "__key": f"{it.get('chunk_id','')}|{(it.get('req') or it.get('item') or '')[:80]}",
                }
                for it in filtered_checklist
            ]
        )
        edited = st.data_editor(
            df.drop(columns=["__key"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "done": st.column_config.CheckboxColumn("Done"),
                "retrieval_score": st.column_config.NumberColumn("Retrieval score", format="%.4f"),
            },
            disabled=["priority", "domain", "requirement", "source_section", "chunk_id", "retrieval_score"],
            key="checklist_editor",
        )
        # Persist checkbox edits back to session_state.checklist (best-effort mapping by chunk_id+requirement prefix)
        done_map = {}
        for _, row in edited.iterrows():
            done_map[f"{row.get('chunk_id','')}|{str(row.get('requirement',''))[:80]}"] = bool(row.get("done", False))
        for it in st.session_state.checklist:
            k = f"{it.get('chunk_id','')}|{str((it.get('req') or it.get('item') or it.get('requirement') or ''))[:80]}"
            if k in done_map:
                it["done"] = done_map[k]

# ── TAB 2: RAG Query ──────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="glass-card glass-card-teal">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:11px;color:rgba(15,242,200,0.7);font-weight:600;letter-spacing:0.5px;margin-bottom:10px">HYBRID RAG INTERFACE</div>', unsafe_allow_html=True)

    # Controls row
    ctl1, ctl2, ctl3 = st.columns([1.4, 1.4, 3.2])
    with ctl1:
        retry = st.button("↻ Retry last", use_container_width=True, disabled=not st.session_state["chat_history"])
    with ctl2:
        regen = st.button("⟳ Regenerate", use_container_width=True, disabled=not st.session_state["chat_history"])
    with ctl3:
        st.markdown('<div style="font-size:11px;color:rgba(255,255,255,0.35);padding-top:8px">Citations appear as chips when the model returns <code>[chunk_id:...]</code>.</div>', unsafe_allow_html=True)

    if retry and st.session_state["chat_history"]:
        # Re-run last user prompt by popping last assistant if present
        if st.session_state["chat_history"] and st.session_state["chat_history"][-1]["role"] == "assistant":
            st.session_state["chat_history"].pop()
        st.rerun()

    if regen and st.session_state["chat_history"]:
        # Regenerate means: if last is assistant, remove it; if last is user, just rerun
        if st.session_state["chat_history"][-1]["role"] == "assistant":
            st.session_state["chat_history"].pop()
        st.rerun()

    chat_container = st.container(height=350)
    with chat_container:
        for msg in st.session_state["chat_history"]:
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            role_color = "#8ab4f8" if msg["role"] == "user" else "#0ff2c8"
            content = msg.get("content", "")
            st.markdown(
                f'<div style="margin-bottom:14px;"><strong style="color:{role_color};">{role_emoji} {msg["role"].title()}</strong>'
                f'<div style="font-size:13px; color:rgba(255,255,255,0.8); margin-top:4px;">{content}</div></div>',
                unsafe_allow_html=True,
            )
            if msg["role"] == "assistant":
                cites = _extract_citations(content)
                _render_citation_chips(cites)

    query = st.chat_input("Ask about the policies...")

    if query:
        st.session_state["chat_history"].append({"role": "user", "content": query})
        st.rerun()

    # Process AI if last is user
    if st.session_state["chat_history"] and st.session_state["chat_history"][-1]["role"] == "user":
        query_text = st.session_state["chat_history"][-1]["content"]
        with chat_container:
            st.markdown(f'<div style="margin-bottom:8px;"><strong style="color:#0ff2c8;">🤖 Assistant</strong>', unsafe_allow_html=True)
            payload_data = {
                "query": query_text,
                "domain": st.session_state["active_domain"],
                "user_id": st.session_state["user_id"],
                "history": st.session_state["chat_history"][-8:],
            }
            
            with st.spinner("Thinking..."):
                try:
                    def stream_res():
                        connect_timeout = float(os.getenv("STREAM_CONNECT_TIMEOUT_SEC", "10"))
                        read_timeout = float(os.getenv("STREAM_READ_TIMEOUT_SEC", "120"))
                        with requests.post(
                            f"{API_URL}/api/chat/stream",
                            json=payload_data,
                            stream=True,
                            timeout=(connect_timeout, read_timeout),
                        ) as response:
                            if response.status_code == 200:
                                for line in response.iter_content(chunk_size=1024, decode_unicode=True):
                                    if line:
                                        yield line
                            else:
                                yield "Backend stream error."
                    reply = st.write_stream(stream_res())
                    # Weak-evidence banner when the model abstains
                    if str(reply).strip() == "I cannot verify this from the provided documents.":
                        st.warning("Weak evidence: the assistant abstained because it could not support an answer with citations.")
                    st.session_state["chat_history"].append({"role": "assistant", "content": reply})
                    st.rerun()
                except Exception as e:
                    st.error(f"Connection failed: {e}")
                    st.session_state["chat_history"].append({"role": "assistant", "content": f"Error: {e}"})
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ── TAB 3: Analytics ──────────────────────────────────────────────────────────
with tab3:
    has_data = len(st.session_state.checklist) > 0
    rows, cols = checklist_rows_for_csv(st.session_state.checklist) if has_data else ([], [])
    df_items = pd.DataFrame(rows, columns=cols) if has_data else pd.DataFrame()

    # Export analytics CSV
    exp1, exp2 = st.columns([2.0, 5.0])
    with exp1:
        analytics_csv = b""
        if has_data:
            analytics_csv = df_items.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇ Analytics CSV",
            data=analytics_csv,
            file_name="analytics.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not has_data,
            type="primary",
        )
    with exp2:
        st.markdown('<div style="font-size:11px;color:rgba(255,255,255,0.35);padding-top:10px">Analytics are computed from the current checklist/session state.</div>', unsafe_allow_html=True)

    a1, a2 = st.columns(2)

    with a1:
        st.markdown('<div class="glass-card glass-card-blue" style="height:220px">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:11px;font-weight:600;color:rgba(91,142,240,0.8);letter-spacing:0.5px;margin-bottom:12px">COMPLIANCE RATE BY DOMAIN</div>', unsafe_allow_html=True)

        for d in list(set([x.get("domain", "general") for x in st.session_state.checklist])):
            label = d.replace("_", " ").title()
            colr = color_map.get(d, "#0ff2c8")
            d_items = [x for x in st.session_state.checklist if x.get("domain", "general") == d]
            d_done = len([x for x in d_items if x.get("done", False)])
            d_tot = len(d_items)
            pct_d = int(d_done / max(d_tot, 1) * 100)
            
            st.markdown(f"""
            <div style="margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;font-size:11px;color:rgba(255,255,255,0.55);margin-bottom:4px">
                <span>{label} ({d_done}/{d_tot})</span><span style="color:{colr};font-family:JetBrains Mono,monospace">{pct_d}%</span>
              </div>
              <div style="height:4px;background:rgba(255,255,255,0.08);border-radius:4px;overflow:hidden">
                <div style="height:100%;width:{pct_d}%;background:{colr};border-radius:4px;box-shadow:0 0 6px {colr}55"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with a2:
        st.markdown('<div class="glass-card glass-card-purple" style="height:220px">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:11px;font-weight:600;color:rgba(192,132,252,0.8);letter-spacing:0.5px;margin-bottom:12px">INSIGHTS</div>', unsafe_allow_html=True)

        if not has_data:
            st.markdown('<div style="color:rgba(255,255,255,0.45);font-size:12px">No data yet. Ingest a document to see insights.</div>', unsafe_allow_html=True)
        else:
            # Priority mix + top sources
            pr_counts = df_items["priority"].fillna("").value_counts().to_dict() if "priority" in df_items else {}
            top_sources = df_items["source_url"].fillna("").value_counts().head(3).to_dict() if "source_url" in df_items else {}
            avg_score = None
            if "rt_score" in df_items:
                try:
                    s = pd.to_numeric(df_items["rt_score"], errors="coerce").dropna()
                    avg_score = float(s.mean()) if len(s) else None
                except Exception:
                    avg_score = None

            def _row(label: str, val: str, color: str):
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05)">'
                    f'<span style="font-size:11px;color:rgba(255,255,255,0.45)">{label}</span>'
                    f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:12px;color:{color};font-weight:500">{val}</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

            _row("Priority (High/Med/Low)", f"{pr_counts.get('High',0)}/{pr_counts.get('Medium',0)}/{pr_counts.get('Low',0)}", "#c084fc")
            _row("Avg retrieval score", f"{avg_score:.3f}" if avg_score is not None else "N/A", "#5b8ef0")
            if top_sources:
                _row("Top source", next(iter(top_sources.keys()))[:38] or "N/A", "#f5c542")

        st.markdown("</div>", unsafe_allow_html=True)

