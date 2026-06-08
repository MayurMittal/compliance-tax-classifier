import streamlit as st
from classifier import classify, fetch_text
from agent import research_compliance
from sourcing_agent import research_topic, get_all_jurisdictions

LABEL_COLORS = {
    "VAT": "#4A90D9",
    "GST": "#7B68EE",
    "SALES_TAX": "#5BA85A",
    "CUSTOMS_DUTY": "#E8A838",
    "EXCISE_TAX": "#D96B4A",
    "INCOME_TAX": "#4ABFBF",
    "TRANSFER_PRICING": "#A678D9",
    "WITHHOLDING_TAX": "#D9A84A",
    "PAYROLL_TAX": "#6BAF8C",
    "COMPLIANCE_NOTICE": "#D94A4A",
    "TAX_TREATY": "#4A7BD9",
    "GENERAL_TAX": "#8CA0B0",
    "NOT_TAX_RELATED": "#B0B0B0",
}

CONFIDENCE_COLORS = {"high": "green", "medium": "orange", "low": "red"}

st.set_page_config(page_title="Tax & Compliance Classifier", page_icon="🔍", layout="centered")

st.title("Tax & Compliance Classifier")

tab_classify, tab_research = st.tabs(["Classify Content", "Research Topic"])


# ── Tab 1: Classifier ──────────────────────────────────────────────────────────
with tab_classify:
    st.caption("Paste text, enter a URL, or upload a file — the classifier will identify the type of tax or compliance content.")

    input_mode = st.radio("Input type", ["Paste text", "Web page URL", "Upload file"], horizontal=True)

    content = None
    error = None

    if input_mode == "Paste text":
        text_input = st.text_area(
            "Paste your content here", height=200,
            placeholder="e.g. VAT registration requirements for EU businesses...",
        )
        if st.button("Classify", type="primary"):
            if text_input.strip():
                content = text_input.strip()
            else:
                error = "Please paste some text before classifying."

    elif input_mode == "Web page URL":
        url_input = st.text_input("Enter URL", placeholder="https://example.com/tax-guide")
        if st.button("Classify", type="primary"):
            if url_input.strip():
                with st.spinner("Fetching page..."):
                    try:
                        content = fetch_text(url_input.strip())
                        st.caption(f"Fetched {len(content):,} characters from {url_input}")
                    except Exception as exc:
                        error = f"Could not fetch URL: {exc}"
            else:
                error = "Please enter a URL before classifying."

    elif input_mode == "Upload file":
        uploaded = st.file_uploader("Upload a .txt or .html file", type=["txt", "html", "htm"])
        if st.button("Classify", type="primary"):
            if uploaded is not None:
                raw = uploaded.read().decode("utf-8", errors="ignore")
                if uploaded.name.endswith((".html", ".htm")):
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer", "header"]):
                        tag.decompose()
                    content = soup.get_text(separator=" ", strip=True)[:10_000]
                else:
                    content = raw[:10_000]
                st.caption(f"Read {len(content):,} characters from {uploaded.name}")
            else:
                error = "Please upload a file before classifying."

    if error:
        st.error(error)

    if content:
        with st.spinner("Classifying..."):
            try:
                result = classify(content)
            except Exception as exc:
                st.error(f"Classification failed: {exc}")
                st.stop()

        st.divider()
        st.subheader("Classification Result")

        primary = result["primary_label"]
        color = LABEL_COLORS.get(primary, "#888")
        st.markdown(
            f"<div style='background:{color};color:white;padding:12px 20px;border-radius:8px;"
            f"font-size:1.4rem;font-weight:700;display:inline-block;margin-bottom:12px'>"
            f"{primary.replace('_', ' ')}</div>",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        conf = result["confidence"]
        col1.metric("Confidence", conf.upper())
        col2.metric("Jurisdiction", result["jurisdiction"] or "—")

        if result["secondary_labels"]:
            st.markdown("**Also detected:**")
            cols = st.columns(len(result["secondary_labels"]))
            for col, label in zip(cols, result["secondary_labels"]):
                c = LABEL_COLORS.get(label, "#888")
                col.markdown(
                    f"<span style='background:{c};color:white;padding:4px 10px;border-radius:4px;"
                    f"font-size:0.85rem;font-weight:600'>{label.replace('_', ' ')}</span>",
                    unsafe_allow_html=True,
                )

        st.info(f"**Summary:** {result['summary']}")

        # ── Research section ─────────────────────────────────────────────────
        if primary != "NOT_TAX_RELATED":
            jurisdiction = result["jurisdiction"]
            with st.spinner("Researching compliance rules from official sources..."):
                try:
                    research = research_compliance(primary, jurisdiction)
                except Exception as exc:
                    research = {"error": str(exc)}

            with st.expander("📋 Relevant Rules & Recent Changes", expanded=True):
                if research.get("error"):
                    st.error(f"Research failed: {research['error']}")

                elif research.get("no_sources"):
                    if research.get("fetch_failed"):
                        st.warning(
                            "Sources are configured but could not be fetched. "
                            "Check your internet connection or update the URLs in `sources_config.json`."
                        )
                    else:
                        st.info(
                            "No curated sources configured for this jurisdiction yet. "
                            "You can add them in `sources_config.json`"
                        )

                else:
                    if research.get("current_rates"):
                        st.markdown("**Current Rates**")
                        st.markdown(research["current_rates"])

                    if research.get("recent_changes"):
                        st.markdown("**Recent Changes (last 90 days)**")
                        for item in research["recent_changes"]:
                            st.markdown(f"- {item}")

                    if research.get("key_deadlines"):
                        st.markdown("**Key Compliance Deadlines**")
                        for item in research["key_deadlines"]:
                            st.markdown(f"- {item}")

                    if research.get("penalties"):
                        st.markdown("**Penalties**")
                        for item in research["penalties"]:
                            st.markdown(f"- {item}")

                    if research.get("summary"):
                        st.caption(research["summary"])

                    if research.get("sources_used"):
                        st.markdown("---")
                        st.markdown("**Sources**")
                        for url in research["sources_used"]:
                            st.markdown(f"- [{url}]({url})")


# ── Tab 2: Research Topic ──────────────────────────────────────────────────────
with tab_research:
    st.caption(
        "Enter any tax topic and jurisdiction — the agent will search the web for relevant "
        "official sources, fetch their content, and synthesise a structured summary."
    )

    jurisdictions = get_all_jurisdictions()

    topic_input = st.text_input(
        "Tax topic",
        placeholder="e.g. GST rate changes, VAT registration threshold, income tax deadlines",
    )
    jurisdiction_input = st.selectbox(
        "Jurisdiction",
        options=jurisdictions,
        index=None,
        placeholder="Select a jurisdiction...",
    )

    if st.button("Research", type="primary"):
        if not topic_input.strip():
            st.error("Please enter a tax topic.")
        elif not jurisdiction_input:
            st.error("Please select a jurisdiction.")
        else:
            with st.spinner("Generating search queries and fetching sources — this may take a moment..."):
                try:
                    report = research_topic(topic_input.strip(), jurisdiction_input)
                except Exception as exc:
                    st.error(f"Research failed: {exc}")
                    st.stop()

            st.divider()
            st.subheader(f"Research Report: {topic_input}")
            st.caption(f"Jurisdiction: {jurisdiction_input}")

            if report.get("no_sources"):
                st.info(report.get("summary", "No sources found or could not be fetched."))
            else:
                if report.get("used_fallback"):
                    st.warning(
                        "Web search returned no results — results below are from curated sources "
                        "in `sources_config.json`."
                    )

                if report.get("summary"):
                    st.info(report["summary"])

                if report.get("current_rates_or_rules"):
                    st.markdown("**Current Rates & Rules**")
                    st.markdown(report["current_rates_or_rules"])

                if report.get("key_findings"):
                    st.markdown("**Key Findings**")
                    for item in report["key_findings"]:
                        st.markdown(f"- {item}")

                if report.get("recent_changes"):
                    st.markdown("**Recent Changes (last 90 days)**")
                    for item in report["recent_changes"]:
                        st.markdown(f"- {item}")

                if report.get("important_deadlines"):
                    st.markdown("**Important Deadlines**")
                    for item in report["important_deadlines"]:
                        st.markdown(f"- {item}")

                if report.get("conflicting_information"):
                    st.markdown("**Conflicting Information Across Sources**")
                    for item in report["conflicting_information"]:
                        st.markdown(f"- {item}")

                if report.get("sources_used"):
                    st.markdown("---")
                    st.markdown("**Sources**")
                    for url in report["sources_used"]:
                        st.markdown(f"- [{url}]({url})")
