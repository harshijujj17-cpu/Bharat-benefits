import logging
from typing import Any

# Patch sqlite3 for Streamlit Cloud deployment with ChromaDB
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

import html
import streamlit as st

from agent.recommendation import recommend_schemes
from agent.profile_extractor import extract_profile
from agent.agent_loop import run_agent
from rag.retriever import SchemeRetriever
from voice.speech_to_text import (
    SUPPORTED_LANGUAGES,
    SpeechToTextError,
    transcribe_audio,
)
from voice.text_to_speech import TextToSpeechError, synthesize_speech


@st.cache_resource(show_spinner=False)
def get_scheme_retriever() -> SchemeRetriever:
    return SchemeRetriever()


st.set_page_config(
    page_title="SevaSetu AI | National Government Scheme Intelligence",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: radial-gradient(circle at 10% 15%, #161938 0%, #0d1026 40%, #080a18 100%) !important;
    color: #e2e8f0 !important;
    min-height: 100vh;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

#MainMenu, footer, header, [data-testid="stToolbar"] {
    visibility: hidden !important;
    display: none !important;
}

.glass-panel {
    background: rgba(22, 27, 54, 0.65) !important;
    backdrop-filter: blur(16px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 18px !important;
    padding: 24px !important;
    box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.4), inset 0 1px 0 0 rgba(255, 255, 255, 0.1) !important;
    margin-bottom: 24px !important;
    transition: all 0.25s ease;
}

.glass-panel:hover {
    border-color: rgba(99, 102, 241, 0.28) !important;
    box-shadow: 0 16px 36px -4px rgba(99, 102, 241, 0.15) !important;
}

.hero-header {
    background: linear-gradient(135deg, rgba(30, 27, 75, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(129, 140, 248, 0.2);
    border-radius: 20px;
    padding: 30px 36px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 20px 40px -15px rgba(79, 70, 229, 0.25);
}

.hero-tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 9999px;
    background: rgba(99, 102, 241, 0.15);
    border: 1px solid rgba(99, 102, 241, 0.35);
    color: #a5b4fc;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 10px;
}

.hero-title {
    font-size: 2.2rem;
    font-weight: 800;
    background: linear-gradient(to right, #ffffff, #c7d2fe, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
    letter-spacing: -0.02em;
}

.hero-subtitle {
    color: #94a3b8;
    font-size: 1.02rem;
    max-width: 820px;
    line-height: 1.55;
    margin: 0;
}

.stepper-container {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 14px 24px;
    margin-bottom: 24px;
    backdrop-filter: blur(12px);
}

.step-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    flex: 1;
    position: relative;
}

.step-item:not(:last-child)::after {
    content: '';
    position: absolute;
    top: 15px;
    left: calc(50% + 18px);
    right: calc(-50% + 18px);
    height: 2px;
    background: rgba(255, 255, 255, 0.1);
    z-index: 1;
}

.step-item.completed:not(:last-child)::after {
    background: linear-gradient(90deg, #6366f1, #10b981);
}

.step-circle {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    font-weight: 700;
    background: rgba(30, 41, 59, 0.8);
    border: 2px solid rgba(255, 255, 255, 0.15);
    color: #94a3b8;
    z-index: 2;
    transition: all 0.3s ease;
}

.step-item.active .step-circle {
    background: #4f46e5;
    border-color: #818cf8;
    color: #ffffff;
    box-shadow: 0 0 16px rgba(99, 102, 241, 0.6);
}

.step-item.completed .step-circle {
    background: #059669;
    border-color: #34d399;
    color: #ffffff;
    box-shadow: 0 0 12px rgba(16, 185, 129, 0.4);
}

.step-label {
    font-size: 0.76rem;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.step-item.active .step-label {
    color: #e0e7ff;
}

.step-item.completed .step-label {
    color: #a7f3d0;
}

.rec-card {
    background: rgba(26, 31, 62, 0.7) !important;
    backdrop-filter: blur(20px) !important;
    border: 1px solid rgba(99, 102, 241, 0.2) !important;
    border-radius: 20px !important;
    padding: 26px !important;
    margin-bottom: 24px !important;
    position: relative;
    box-shadow: 0 14px 34px -8px rgba(0, 0, 0, 0.5) !important;
    transition: transform 0.2s ease, border-color 0.2s ease;
}

.rec-card:hover {
    border-color: rgba(129, 140, 248, 0.45) !important;
    box-shadow: 0 20px 42px -6px rgba(79, 70, 229, 0.25) !important;
}

.rec-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 18px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 14px;
}

.rec-title {
    font-size: 1.45rem;
    font-weight: 700;
    color: #f8fafc;
    margin: 0;
    letter-spacing: -0.01em;
}

.badge-eligible {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(5, 150, 105, 0.35));
    border: 1px solid #10b981;
    color: #6ee7b7;
    padding: 5px 14px;
    border-radius: 9999px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    box-shadow: 0 0 12px rgba(16, 185, 129, 0.25);
}

.badge-general {
    background: linear-gradient(135deg, rgba(100, 116, 139, 0.2), rgba(71, 85, 105, 0.35));
    border: 1px solid #94a3b8;
    color: #cbd5e1;
    padding: 5px 14px;
    border-radius: 9999px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

.field-block {
    margin-bottom: 16px;
}

.field-title {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #818cf8;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
}

.field-content {
    color: #cbd5e1;
    font-size: 0.95rem;
    line-height: 1.6;
}

.pill-tag {
    display: inline-block;
    background: rgba(99, 102, 241, 0.12);
    border: 1px solid rgba(129, 140, 248, 0.25);
    color: #c7d2fe;
    padding: 3px 10px;
    border-radius: 8px;
    font-size: 0.83rem;
    margin-right: 6px;
    margin-bottom: 6px;
}

.doc-checklist {
    list-style: none;
    padding-left: 0;
    margin: 6px 0;
}

.doc-checklist li {
    position: relative;
    padding-left: 24px;
    margin-bottom: 5px;
    color: #cbd5e1;
    font-size: 0.93rem;
}

.doc-checklist li::before {
    content: "✓";
    position: absolute;
    left: 4px;
    color: #34d399;
    font-weight: 800;
}

.helpline-box {
    background: rgba(59, 130, 246, 0.08);
    border: 1px dashed rgba(96, 165, 250, 0.35);
    border-radius: 12px;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #93c5fd;
    font-weight: 600;
    font-size: 0.92rem;
}

.notice-warning {
    background: rgba(245, 158, 11, 0.08);
    border-left: 4px solid #f59e0b;
    border-radius: 4px 10px 10px 4px;
    padding: 10px 16px;
    margin-top: 14px;
    color: #fde68a;
    font-size: 0.85rem;
    line-height: 1.5;
}

div[data-testid="stForm"] {
    background: rgba(22, 27, 54, 0.65) !important;
    backdrop-filter: blur(16px) saturate(180%) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 20px !important;
    padding: 28px !important;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4) !important;
}

div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div {
    background-color: rgba(15, 23, 42, 0.75) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 12px !important;
    color: #f1f5f9 !important;
}

div[data-baseweb="input"]:focus-within > div, div[data-baseweb="select"]:focus-within > div {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25) !important;
}

label p {
    color: #94a3b8 !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
}

button[kind="primary"] {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
    border: none !important;
    border-radius: 14px !important;
    padding: 14px 28px !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
    letter-spacing: 0.02em !important;
    color: #ffffff !important;
    box-shadow: 0 10px 24px -4px rgba(79, 70, 229, 0.5) !important;
    transition: all 0.25s ease !important;
    width: 100% !important;
}

button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 14px 28px -2px rgba(124, 58, 237, 0.6) !important;
}

div[data-testid="stLinkButton"] a {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(129, 140, 248, 0.25)) !important;
    border: 1px solid rgba(129, 140, 248, 0.4) !important;
    color: #e0e7ff !important;
    border-radius: 12px !important;
    padding: 10px 20px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
    text-decoration: none !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
}

div[data-testid="stLinkButton"] a:hover {
    background: rgba(99, 102, 241, 0.35) !important;
    border-color: #818cf8 !important;
    box-shadow: 0 0 16px rgba(99, 102, 241, 0.3) !important;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown(
    """
    <div class="hero-header">
        <div class="hero-tag">🏛️ National Citizen Welfare • AI Recommendation Engine</div>
        <h1 class="hero-title">Government Scheme Recommendation Agent</h1>
        <p class="hero-subtitle">
            Instant multi-tier eligibility verification powered by semantic vector retrieval
            and verified official schemes. Enter your background to find schemes crafted for you.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


def render_stepper(current_step: int) -> None:
    steps = [
        ("1", "Profile"),
        ("2", "Retrieval"),
        ("3", "Eligibility"),
        ("4", "Documents"),
        ("5", "Results"),
    ]
    html_parts = ['<div class="stepper-container">']
    for idx, (num, label) in enumerate(steps, start=1):
        status_class = ""
        icon = num
        if idx < current_step:
            status_class = "completed"
            icon = "✓"
        elif idx == current_step:
            status_class = "active"
        html_parts.append(
            f'<div class="step-item {status_class}">'
            f'<div class="step-circle">{icon}</div>'
            f'<div class="step-label">{label}</div>'
            f'</div>'
        )
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def show_value(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            st.markdown(f"- {item}")
    else:
        st.write(value)


def show_recommendation(recommendation: dict[str, Any]) -> None:
    is_citizen_eligible = recommendation.get("citizen_eligible", True)
    scheme_name = (
        recommendation.get("scheme_name")
        or recommendation.get("name")
        or recommendation.get("id")
        or "Unknown Scheme"
    )

    if is_citizen_eligible is False:
        st.markdown(
            f"""
            <div class="rec-card" style="border-color: rgba(148, 163, 184, 0.25);">
                <div class="rec-card-header">
                    <h3 class="rec-title">ℹ️ {html.escape(scheme_name)}</h3>
                    <div class="badge-general">🏛️ General Information Only</div>
                </div>
                <div class="field-block">
                    <div class="field-title">Program Description</div>
                    <div class="field-content">{html.escape(str(recommendation.get("relevance_explanation") or recommendation.get("description") or "Macro infrastructure or institutional scheme."))}</div>
                </div>
                <div class="notice-warning">
                    <strong>Notice:</strong> This scheme operates at an institutional, community, or state infrastructure level and is not directly applied for by individual citizens.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    relevance = recommendation.get("relevance_explanation", "Identified as matching your profile criteria.")
    eligibility = recommendation.get("eligibility")
    benefits = recommendation.get("benefits", "Not included in retrieved scheme data.")
    required_docs = recommendation.get("required_documents") or recommendation.get("documents")
    app_process = recommendation.get("application_process", "Not included in retrieved scheme data.")
    source_url = recommendation.get("official_source") or recommendation.get("apply_url")
    helpline = recommendation.get("helpline")
    missing_info = recommendation.get("missing_information", [])
    eligibility_notice = recommendation.get(
        "eligibility_notice",
        "Based on the information provided, this scheme may be relevant to you. Please verify the latest eligibility criteria and application details on the official government portal before applying.",
    )

    elig_html = ""
    if eligibility:
        if isinstance(eligibility, list):
            pills = "".join(f'<span class="pill-tag">{html.escape(str(e))}</span>' for e in eligibility)
            elig_html = f'<div class="field-block"><div class="field-title">🎯 Targeted Eligibility</div><div>{pills}</div></div>'
        else:
            elig_html = f'<div class="field-block"><div class="field-title">🎯 Targeted Eligibility</div><div class="field-content">{html.escape(str(eligibility))}</div></div>'

    docs_html = ""
    if required_docs and isinstance(required_docs, list) and len(required_docs) > 0:
        items = "".join(f'<li>{html.escape(str(d))}</li>' for d in required_docs)
        docs_html = f'<div class="field-block"><div class="field-title">📑 Required Documents Checklist</div><ul class="doc-checklist">{items}</ul></div>'
    elif required_docs:
        docs_html = f'<div class="field-block"><div class="field-title">📑 Required Documents</div><div class="field-content">{html.escape(str(required_docs))}</div></div>'
    else:
        docs_html = '<div class="field-block"><div class="field-title">📑 Required Documents</div><div class="field-content">Not available in scheme data.</div></div>'

    helpline_html = ""
    if helpline:
        helpline_html = f'<div class="field-block"><div class="helpline-box">📞 <strong>Official Support:</strong> {html.escape(str(helpline))}</div></div>'

    missing_html = ""
    if missing_info:
        missing_text = "; ".join(html.escape(str(m)) for m in missing_info)
        missing_html = f'<div class="notice-warning"><strong>Information to Confirm:</strong> {missing_text}</div>'

    card_html = f"""
    <div class="rec-card">
        <div class="rec-card-header">
            <h3 class="rec-title">{html.escape(scheme_name)}</h3>
            <div class="badge-eligible">✨ Direct Citizen Benefit</div>
        </div>
        <div class="field-block">
            <div class="field-title">💡 Why It Is Relevant to You</div>
            <div class="field-content">{html.escape(str(relevance))}</div>
        </div>
        {elig_html}
        <div class="field-block">
            <div class="field-title">💰 Key Benefits & Subsidies</div>
            <div class="field-content">{html.escape(str(benefits))}</div>
        </div>
        {docs_html}
        <div class="field-block">
            <div class="field-title">🧭 Application Process</div>
            <div class="field-content">{html.escape(str(app_process))}</div>
        </div>
        {helpline_html}
        {missing_html}
        <div class="notice-warning" style="background: rgba(99, 102, 241, 0.08); border-left-color: #818cf8; color: #c7d2fe;">
            <strong>Verification Notice:</strong> {html.escape(str(eligibility_notice))}
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    if source_url:
        st.link_button(
            f"Open Official Government Portal for {scheme_name}",
            source_url,
            icon=":material/open_in_new:",
        )
    st.markdown("<br>", unsafe_allow_html=True)


def build_recommendation_narration(recommendations: list[dict[str, Any]]) -> str:
    sections = []
    for recommendation in recommendations:
        lines = [
            recommendation["scheme_name"],
            f"Why it may be relevant: {recommendation['relevance_explanation']}",
            f"Eligibility information: {recommendation.get('eligibility', 'Not provided.')}",
            f"Benefits: {recommendation.get('benefits', 'Not provided.')}",
            "Required documents: "
            + str(recommendation.get("required_documents", "Not provided.")),
            "Application process: "
            + str(recommendation.get("application_process", "Not provided.")),
            "The official source link is displayed on screen.",
        ]
        if recommendation.get("helpline"):
            lines.append(f"Helpline: {recommendation['helpline']}")
        lines.append(recommendation["eligibility_notice"])
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


if "other_relevant_information" not in st.session_state:
    st.session_state["other_relevant_information"] = ""
if "extracted_profile" not in st.session_state:
    st.session_state["extracted_profile"] = {}

ep = st.session_state["extracted_profile"]


def get_idx(options: list[str], val: Any, default: int = 0) -> int:
    return options.index(val) if val in options else default


# Dynamic Horizontal Stepper Progression
if "recommendation_result" in st.session_state and st.session_state["recommendation_result"]:
    render_stepper(5)
elif "profile" in st.session_state:
    render_stepper(3)
else:
    render_stepper(1)


# Profile Extraction (Voice & Text)
with st.container():
    st.markdown(
        """
        <div style="margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 1.25rem;">✨</span>
            <span style="font-weight: 700; font-size: 1.15rem; color: #f1f5f9;">Instant AI Profile Extraction</span>
            <span style="background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.3); color: #a5b4fc; font-size: 0.75rem; padding: 2px 8px; border-radius: 6px; font-weight: 600;">Optional</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.write("Describe your background in your own words, or speak in your preferred Indian language.")
        col1, col2 = st.columns([1, 1], gap="large")
        with col1:
            st.markdown("**🎙️ Audio Input**")
            transcription_language = st.selectbox(
                "Recording language",
                SUPPORTED_LANGUAGES,
                key="transcription_language",
            )
            recording = st.audio_input("Record voice summary", sample_rate=16000)
        with col2:
            st.markdown("**✍️ Natural Text Input**")
            free_text = st.text_area(
                "Or enter your details freely:",
                key="free_text_input",
                placeholder="e.g. I am a 21-year-old student from Telangana studying B.Tech. Family income is ₹2.5 lakh...",
                height=130,
            )

        extract_clicked = st.button("Extract Profile with AI", icon=":material/auto_awesome:")
        if extract_clicked:
            text_to_extract = st.session_state.get("free_text_input", "")
            if recording is not None:
                try:
                    with st.spinner("Transcribing speech audio with neural STT..."):
                        text_to_extract = transcribe_audio(
                            recording.getvalue(),
                            recording.type or "audio/wav",
                            language=transcription_language,
                        )
                    st.info(f"Transcript: {text_to_extract}")
                except Exception as error:
                    st.error(f"🎤 Transcription error: {error}")
                    text_to_extract = ""

            if text_to_extract.strip():
                try:
                    with st.spinner("Analyzing and parsing profile structure..."):
                        extracted = extract_profile(text_to_extract)
                        st.session_state["extracted_profile"] = extracted
                    st.success("Citizen profile structured successfully! Values populated below.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Extraction error: {error}")


# Citizen Profile Form in Glassmorphism Card
st.markdown("<br>", unsafe_allow_html=True)
with st.form("citizen_profile"):
    st.markdown(
        """
        <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 1.25rem;">📋</span>
            <span style="font-weight: 700; font-size: 1.2rem; color: #f1f5f9;">Citizen Profile Details</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        age = st.number_input("Age", min_value=0, max_value=120, value=ep.get("age") or 18, step=1)
        edu_opts = [
            "No formal schooling", "Primary", "Middle school", "Secondary",
            "Higher secondary", "Diploma", "Bachelor's degree", "Postgraduate",
            "Other", "Prefer not to say"
        ]
        education = st.selectbox("Education Level", edu_opts, index=get_idx(edu_opts, ep.get("education"), 9))
        other_education = ""
        if education == "Other":
            other_education = st.text_input("Specify Education")

    with fcol2:
        gender_opts = ["Woman", "Man", "Non-binary", "Other", "Prefer not to say"]
        gender = st.selectbox("Gender", gender_opts, index=get_idx(gender_opts, ep.get("gender"), 4))
        occupation = st.text_input("Occupation", value=ep.get("occupation") or "", placeholder="e.g. Student, Farmer, Self-employed")
        farmer_opts = ["Not sure", "Yes", "No"]
        farmer_status = st.selectbox("Farmer Status", farmer_opts, index=get_idx(farmer_opts, ep.get("farmer_status"), 0))

    with fcol3:
        state = st.text_input("State or UT", value=ep.get("state") or "", placeholder="e.g. Telangana, Maharashtra")
        annual_income = st.number_input(
            "Annual Household Income (INR)",
            min_value=0,
            max_value=100_000_000,
            value=ep.get("annual_household_income_inr") or 0,
            step=10_000,
        )
        cat_opts = ["Not specified", "General", "SC", "ST", "OBC", "EWS", "Other"]
        category = st.selectbox("Social Category", cat_opts, index=get_idx(cat_opts, ep.get("category"), 0))
        other_category = ""
        if category == "Other":
            other_category = st.text_input("Specify Category")

    scol1, scol2 = st.columns([1, 2])
    with scol1:
        dis_opts = ["Not specified", "Yes", "No"]
        disability_status = st.selectbox("Disability Status", dis_opts, index=get_idx(dis_opts, ep.get("disability_status"), 0))
        disability_details = ""
        if disability_status == "Yes":
            disability_details = st.text_input("Disability details (optional)")

    with scol2:
        other_information = st.text_area(
            "Other Relevant Details",
            value=st.session_state["other_relevant_information"],
            placeholder="e.g. Landholding size, family members, specific welfare goals...",
            height=70,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    submitted = st.form_submit_button(
        "Find My Schemes ⚡",
        type="primary",
        icon=":material/search:",
    )

if submitted:
    st.session_state.pop("profile", None)
    st.session_state["retrieved_schemes"] = []
    st.session_state["recommendation_result"] = None
    st.session_state["recommendation_error"] = None
    st.session_state["recommendation_audio"] = None

    if not state.strip():
        st.error("Please enter a state or union territory to continue.")
    elif not occupation.strip():
        st.error("Please enter an occupation to continue.")
    else:
        profile = {
            "age": age,
            "gender": gender,
            "state": state.strip(),
            "education": other_education.strip() if other_education else education,
            "occupation": occupation.strip(),
            "annual_household_income_inr": annual_income,
            "category": other_category.strip() if other_category else category,
            "disability_status": disability_status,
            "farmer_status": farmer_status,
            "other_relevant_information": other_information.strip(),
        }
        if disability_details.strip():
            profile["disability_details"] = disability_details.strip()

        st.session_state["profile"] = profile
        st.session_state["retrieved_schemes"] = []
        st.session_state["recommendation_result"] = None
        st.session_state["recommendation_error"] = None
        st.session_state["agent_status"] = []
        st.session_state["agent_followup"] = None

        try:
            with st.spinner("Agentic AI inspecting profile, querying ChromaDB vector store, and evaluating eligibility..."):
                agent_result = run_agent(profile, get_scheme_retriever())
                st.session_state["agent_status"] = agent_result.status_lines
                if agent_result.needs_followup:
                    st.session_state["agent_followup"] = agent_result.followup_question
                else:
                    st.session_state["recommendation_result"] = agent_result.recommendation

                st.session_state["retrieved_schemes"] = agent_result.raw_state.get("retrieved_schemes", [])
        except Exception as error:
            st.session_state["recommendation_error"] = str(error)


# Results & Presentation Area
if "profile" in st.session_state:
    st.markdown("---")

    agent_status = st.session_state.get("agent_status", [])
    if agent_status:
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="font-size: 1.2rem;">🤖</span>
                <span style="font-weight: 700; font-size: 1.15rem; color: #f1f5f9;">Autonomous Agent Execution Log</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        status_items = "".join(f'<span class="pill-tag" style="background: rgba(16, 185, 129, 0.15); border-color: rgba(52, 211, 153, 0.4); color: #6ee7b7;">{html.escape(line)}</span>' for line in agent_status)
        st.markdown(f'<div style="margin-bottom: 20px;">{status_items}</div>', unsafe_allow_html=True)

    agent_followup = st.session_state.get("agent_followup")
    if agent_followup:
        st.warning(f"**Agent Follow-up Required:** {agent_followup}")
        st.info("Please update your profile details in the form above and submit again.")

    retrieved_schemes = st.session_state.get("retrieved_schemes", [])
    with st.expander(f"🔍 Vector Candidates Retrieved from ChromaDB ({len(retrieved_schemes)} schemes)", expanded=False):
        if retrieved_schemes:
            st.caption("Semantically retrieved scheme records before grounded eligibility synthesis.")
            for scheme in retrieved_schemes:
                s_name = (
                    scheme.get("scheme_name")
                    or scheme.get("name")
                    or scheme.get("id")
                    or "Unknown Scheme"
                )
                cat = scheme.get("category", "General")
                st.markdown(f"**{s_name}** `({cat})` — {scheme.get('description', 'No description.')}")
        else:
            st.write("No candidate schemes retrieved.")

    recommendation_error = st.session_state.get("recommendation_error")
    if recommendation_error:
        st.error(f"Error during recommendation: {recommendation_error}")

    recommendation_result = st.session_state.get("recommendation_result")
    if recommendation_result is not None:
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 24px; margin-bottom: 18px;">
                <span style="font-size: 1.35rem;">🏆</span>
                <span style="font-weight: 800; font-size: 1.35rem; color: #f1f5f9;">Personalised Scheme Recommendations</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        recommendations = recommendation_result.get("recommendations", [])
        if recommendations:
            for rec in recommendations:
                show_recommendation(rec)

            st.markdown(
                """
                <div class="glass-panel" style="margin-top: 20px;">
                    <div style="font-weight: 700; font-size: 1.1rem; color: #f1f5f9; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                        <span>🔊</span> Accessibility & Audio Narration
                    </div>
                """,
                unsafe_allow_html=True,
            )

            acol1, acol2 = st.columns([2, 1])
            with acol1:
                spoken_language = st.selectbox(
                    "Read recommendations aloud in",
                    SUPPORTED_LANGUAGES,
                    key="spoken_language",
                )
            with acol2:
                st.write("")
                st.write("")
                play_clicked = st.button("Generate Audio Narration", icon=":material/volume_up:")

            if st.session_state.get("recommendation_audio_language") != spoken_language:
                st.session_state["recommendation_audio"] = None

            if play_clicked:
                try:
                    with st.spinner("Synthesizing neural voice stream..."):
                        narration_text = build_recommendation_narration(recommendations)
                        st.session_state["recommendation_audio"] = synthesize_speech(
                            narration_text,
                            language=spoken_language,
                        )
                        st.session_state["recommendation_audio_language"] = spoken_language
                except TextToSpeechError as error:
                    st.error(str(error))

            recommendation_audio = st.session_state.get("recommendation_audio")
            if recommendation_audio:
                st.audio(recommendation_audio, format="audio/wav")

            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info(recommendation_result.get("notice", "No recommendations available."))