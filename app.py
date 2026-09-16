import os
import time
import json
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from tools import global_logger, create_notion_page
from agents import run_leadsignal_pipeline

# Page Config
st.set_page_config(
    page_title="LeadSignal | Multi-Agent B2B Opportunity Radar",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== DYNAMIC FONT & HIGH-END AGENCY THEME ====================

def inject_agency_css(font_family: str):
    font_css_name = {
        "Inter": "'Inter', sans-serif",
        "Geist": "'Geist', sans-serif",
        "Plus Jakarta Sans": "'Plus Jakarta Sans', sans-serif",
        "Outfit": "'Outfit', sans-serif",
        "Space Grotesk": "'Space Grotesk', sans-serif",
    }.get(font_family, "'Inter', sans-serif")

    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"], div, span, p, label {{
        font-family: {font_css_name} !important;
    }}

    /* Deep Cyber Dark Theme */
    .stApp {{
        background: radial-gradient(circle at 50% -20%, #161D2F 0%, #080B11 75%, #05070A 100%) !important;
        color: #E2E8F0 !important;
    }}

    /* Hide standard Streamlit header & footer */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{background: transparent !important;}}

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {{
        background-color: #0B0E17 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }}

    /* Glassmorphic Cards */
    .agency-card {{
        background: rgba(17, 24, 39, 0.7);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }}

    .agency-card:hover {{
        border-color: rgba(99, 102, 241, 0.4);
        transform: translateY(-2px);
        box-shadow: 0 16px 40px -12px rgba(99, 102, 241, 0.25);
    }}

    /* Neon Lighting Highlights */
    .accent-glow {{
        background: linear-gradient(135deg, #6366F1 0%, #A855F7 50%, #EC4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }}

    .accent-badge {{
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(168, 85, 247, 0.15));
        border: 1px solid rgba(99, 102, 241, 0.3);
        color: #A5B4FC;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}

    /* Source Status Badges */
    .status-healthy {{
        color: #10B981;
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }}
    .status-degraded {{
        color: #F59E0B;
        background: rgba(245, 158, 11, 0.12);
        border: 1px solid rgba(245, 158, 11, 0.3);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }}
    .status-fallback {{
        color: #3B82F6;
        background: rgba(59, 130, 246, 0.12);
        border: 1px solid rgba(59, 130, 246, 0.3);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }}
    .status-failed {{
        color: #EF4444;
        background: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }}

    /* Custom Input Fields */
    .stTextInput > div > div > input {{
        background-color: #0F172A !important;
        color: #F8FAFC !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
        font-size: 1rem !important;
    }}
    .stTextInput > div > div > input:focus {{
        border-color: #6366F1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25) !important;
    }}

    /* Custom Primary Button */
    .stButton > button {{
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 14px 0 rgba(79, 70, 229, 0.39) !important;
        transition: all 0.2s ease !important;
    }}
    .stButton > button:hover {{
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px 0 rgba(79, 70, 229, 0.55) !important;
    }}

    /* Email Draft Container */
    .email-container {{
        background: #090D16;
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-radius: 10px;
        padding: 16px;
        font-family: 'Courier New', Courier, monospace;
        color: #CBD5E1;
        font-size: 0.88rem;
        white-space: pre-wrap;
        margin-top: 10px;
        margin-bottom: 10px;
    }}

    /* Agent Stepper */
    .agent-step {{
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 16px;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.03);
        margin-bottom: 8px;
        border-left: 3px solid #334155;
    }}
    .agent-step.active {{
        border-left-color: #6366F1;
        background: rgba(99, 102, 241, 0.1);
    }}
    .agent-step.done {{
        border-left-color: #10B981;
        background: rgba(16, 185, 129, 0.08);
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# Initialize Session State
if "pipeline_results" not in st.session_state:
    st.session_state["pipeline_results"] = None
if "selected_font" not in st.session_state:
    st.session_state["selected_font"] = "Inter"

# Sidebar Font & Source Status Controls
with st.sidebar:
    st.markdown("### 🎨 UI Typography Agency Style")
    font_choice = st.selectbox(
        "Select Font Family",
        ["Inter", "Geist", "Plus Jakarta Sans", "Outfit", "Space Grotesk"],
        index=0
    )
    st.session_state["selected_font"] = font_choice
    inject_agency_css(font_choice)

    st.markdown("---")
    st.markdown("### 🔌 Connected Sources (Live Status)")
    st.caption("Real-time network ping & response latency from last execution.")

    # Query source status from global logger or default state
    current_status = global_logger.get_source_status()
    
    source_icons = {
        "HackerNews": "🟠 HN Algolia",
        "GitHub": "🐙 GitHub Public",
        "YC_OSS": "🚀 YC Startups",
        "ProductHunt": "😸 Product Hunt",
        "Reddit": "🔴 Reddit Public",
        "DevTo": "👩‍💻 Dev.to API",
        "Jobicy": "💼 Jobicy Remote",
        "Notion": "📓 Notion API"
    }

    for src_key, label in source_icons.items():
        st_data = current_status.get(src_key, {"status": "UNKNOWN", "latency_ms": 0, "details": "Not called"})
        status_val = st_data.get("status", "UNKNOWN")
        lat = st_data.get("latency_ms", 0)
        
        css_class = {
            "HEALTHY": "status-healthy",
            "DEGRADED": "status-degraded",
            "FALLBACK": "status-fallback",
            "FAILED": "status-failed"
        }.get(status_val, "status-degraded")
        
        col_a, col_b = st.columns([0.65, 0.35])
        with col_a:
            st.markdown(f"**{label}**")
        with col_b:
            st.markdown(f"<span class='{css_class}'>{status_val}</span>", unsafe_allow_html=True)
        if status_val != "UNKNOWN":
            st.caption(f"Latency: {lat}ms | {st_data.get('details', '')}")
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### ⚙️ Source Toggles")
    hn_on = st.checkbox("HackerNews", value=True)
    gh_on = st.checkbox("GitHub Public", value=True)
    yc_on = st.checkbox("YC Company Dataset", value=True)
    ph_on = st.checkbox("Product Hunt RSS", value=True)
    rd_on = st.checkbox("Reddit Public JSON", value=True)
    dev_on = st.checkbox("Dev.to Articles", value=True)
    job_on = st.checkbox("Jobicy B2B Jobs", value=True)

    sources_config = {
        "HackerNews": hn_on, "GitHub": gh_on, "YC_OSS": yc_on,
        "ProductHunt": ph_on, "Reddit": rd_on, "DevTo": dev_on, "Jobicy": job_on
    }

# ==================== MAIN APPLICATION UI ====================

st.markdown("""
<div style="text-align: center; padding: 20px 0 10px 0;">
    <span class="accent-badge">AI Multi-Agent B2B Opportunity Radar</span>
    <h1 style="font-size: 2.75rem; margin-top: 12px; margin-bottom: 8px;">
        Lead<span class="accent-glow">Signal</span>
    </h1>
    <p style="color: #94A3B8; font-size: 1.1rem; max-width: 680px; margin: 0 auto;">
        Filter noise from 7 free public sources. Discover high-converting B2B intent signals, audit quality, and generate actionable Notion profiles & outreach drafts.
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Search Bar & Control Section
col_search, col_btn = st.columns([0.8, 0.2])

with col_search:
    target_niche = st.text_input(
        "Search B2B Niche or Offer",
        placeholder="e.g. Next.js Developer, AI Agent Consulting, Mobile App Design, B2B SaaS",
        value="Next.js Developer"
    )

with col_btn:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    run_button = st.button("🚀 Launch Radar")

# Input Validation
if run_button:
    if not target_niche.strip():
        st.error("⚠️ Please enter a target niche or keyword before running the pipeline.")
    else:
        # Reset previous logs
        global_logger.clear()

        # Visual Agent Execution Tracker
        status_box = st.empty()
        
        with status_box.container():
            st.markdown("<div class='agency-card'>", unsafe_allow_html=True)
            st.markdown("#### ⚡ Active CrewAI Agents Pipeline Progress")
            
            step1 = st.empty()
            step2 = st.empty()
            step3 = st.empty()
            step4 = st.empty()

            step1.markdown("<div class='agent-step active'>🔎 <b>Agent 1: Lead Signal Scout</b> — Aggregating public opportunities...</div>", unsafe_allow_html=True)
            step2.markdown("<div class='agent-step'>🧹 <b>Agent 2: Signal Noise Screener</b> — Waiting...</div>", unsafe_allow_html=True)
            step3.markdown("<div class='agent-step'>🎯 <b>Agent 3: Lead Qualifier & Drafter</b> — Waiting...</div>", unsafe_allow_html=True)
            step4.markdown("<div class='agent-step'>🛡️ <b>Agent 4: Quality Watcher Critic</b> — Waiting...</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with st.spinner("CrewAI Agents collaborating in real-time..."):
            results = run_leadsignal_pipeline(target_niche.strip(), sources_config)
            st.session_state["pipeline_results"] = results
            
        status_box.empty()
        st.rerun()

# Display Results if Available
results = st.session_state.get("pipeline_results")

if results:
    qualified_leads = results.get("qualified_leads", [])
    quality_score = results.get("quality_score", 0)
    rationale = results.get("quality_rationale", "")
    re_research = results.get("triggered_re_research", False)

    # Top Metric Header Row
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Qualified Leads", len(qualified_leads))
    with m2:
        st.metric("Watcher Quality Score", f"{quality_score}/100")
    with m3:
        st.metric("Self-Correction Loop", "1 Re-Research" if re_research else "0 (First Pass)")
    with m4:
        st.metric("Human In The Loop", "Manual Action Required")

    if re_research:
        st.warning(f"🔄 **Watcher Self-Correction Triggered**: First pass quality was low. Automatically executed exactly 1 re-research loop with refined query: `{results.get('re_research_query')}`")

    st.markdown("---")

    # Tabs for Results, Notion Sync, and Reliability Log
    tab_results, tab_logs, tab_architecture = st.tabs(["🔥 B2B Opportunity Cards & Drafts", "🛡️ Reliability & Observability Log", "🏗️ System Design & Security"])

    with tab_results:
        if not qualified_leads:
            st.info("No qualified leads matched the criteria. Try broadening your search query or enabling more sources.")
        else:
            for idx, lead in enumerate(qualified_leads):
                with st.container():
                    st.markdown("<div class='agency-card'>", unsafe_allow_html=True)
                    
                    c_head, c_score = st.columns([0.8, 0.2])
                    with c_head:
                        st.markdown(f"### {idx+1}. {lead.get('title')}")
                        st.markdown(f"**Source**: `{lead.get('source')}` | **Author/User**: `{lead.get('author')}` | **Target Persona**: `{lead.get('decision_maker')}`")
                    with c_score:
                        score = lead.get('relevance_score', 80)
                        st.markdown(f"<div style='text-align:right;'><span class='accent-badge'>Relevance: {score}/100</span></div>", unsafe_allow_html=True)

                    st.markdown(f"**Intent Signal**: {lead.get('intent_signal')}")
                    st.markdown(f"**Pain Point**: {lead.get('pain_point')}")
                    st.markdown(f"🔗 [View Original Source Post]({lead.get('url')})")

                    st.markdown("<h4 style='margin-top:16px;'>✉️ Personalised Outreach Email Draft</h4>", unsafe_allow_html=True)
                    
                    email_subj = lead.get("email_subject", "Outreach")
                    email_body = lead.get("email_body", "")

                    st.text_input(f"Subject Line (Lead #{idx+1})", value=email_subj, key=f"subj_{idx}")
                    
                    # Display Email Body in Code container
                    st.markdown(f"<div class='email-container'>{email_body}</div>", unsafe_allow_html=True)

                    # Interactive Copy & Notion Buttons
                    col_copy, col_notion, col_space = st.columns([0.3, 0.3, 0.4])
                    
                    with col_copy:
                        # Copy button using Streamlit code snippet or text copy block
                        if st.button(f"📋 Copy Email Draft", key=f"copy_btn_{idx}"):
                            st.code(f"Subject: {email_subj}\n\n{email_body}", language="text")
                            st.toast("✅ Email draft formatted and ready to copy!", icon="📋")

                    with col_notion:
                        if st.button(f"📓 Push to Notion", key=f"notion_btn_{idx}"):
                            with st.spinner("Creating Notion page..."):
                                n_res = create_notion_page(lead, f"Subject: {email_subj}\n\n{email_body}")
                                if n_res.get("success"):
                                    st.success("✅ Page created in Notion!")
                                    st.markdown(f"👉 [Open Notion Page]({n_res.get('page_url')})")
                                else:
                                    st.error(f"❌ Notion Sync Error: {n_res.get('error')}")

                    st.markdown("</div>", unsafe_allow_html=True)

    with tab_logs:
        st.markdown("### 📊 Agent Observability & Reliability Log")
        st.caption("Complete timestamped execution trace of agent tool calls, network retries, and quality scoring.")

        logs = results.get("logs", [])
        
        # Display Watcher Score Audit Table
        st.markdown("#### 🛡️ Watcher Agent Quality Audit Trace")
        watcher_history = results.get("watcher_history", [])
        if watcher_history:
            st.dataframe(watcher_history, use_container_width=True)

        st.markdown("#### 📜 Execution Trace Logs")
        
        log_filter = st.selectbox("Filter Logs by Stage", ["ALL", "ScoutAgent", "FilterAgent", "QualifierAgent", "WatcherAgent", "HTTP", "Notion"])
        
        filtered_logs = logs if log_filter == "ALL" else [l for l in logs if log_filter.lower() in l.get("stage", "").lower()]
        
        for l in reversed(filtered_logs):
            st_class = "status-healthy" if l.get("status") in ["SUCCESS", "INFO"] else ("status-degraded" if l.get("status") == "RETRY" else "status-failed")
            st.markdown(
                f"`{l.get('timestamp')}` | <span class='{st_class}'>{l.get('status')}</span> | **[{l.get('stage')}]** {l.get('message')}",
                unsafe_allow_html=True
            )

    with tab_architecture:
        st.markdown("""
        ### 🛡️ Reliability & Fault-Tolerant System Design
        
        - **Hard-Capped Self-Correction Loop**: The Watcher agent audits lead quality scores after the first pass. If score < 70, exactly **ONE** automatic re-research loop executes with query expansion. Retry count is strictly capped at `1` in code to prevent infinite recursion.
        - **Groq API Rate-Limit Protection**: LLM prompts are batched into candidate arrays per agent phase (1 call for screening, 1 call for email drafting). This minimizes token usage and prevents 429 rate limit exceptions.
        - **Transient Network Fault Isolation**: Every external API call (HackerNews, GitHub, YC, ProductHunt, Reddit, Dev.to, Jobicy) features automatic 1-retry backoff. If Reddit or any individual source fails or rate limits, it is gracefully isolated while the rest of the research pipeline completes.
        - **Strict Human-In-The-Loop Safety**: No emails are auto-sent. Notion export and email copying require explicit user interaction.
        """)

# Footer Requirement: "Reliability design inspired by agent-observability practices"
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #64748B; font-size: 0.85rem; padding: 15px 0;'>"
    "Reliability design inspired by agent-observability practices"
    "</div>",
    unsafe_allow_html=True
)
