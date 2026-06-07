import streamlit as st
from classifier import classify, fetch_text

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
st.caption("Paste text, enter a URL, or upload a file — the classifier will identify the type of tax or compliance content.")

input_mode = st.radio("Input type", ["Paste text", "Web page URL", "Upload file"], horizontal=True)

content = None
error = None

if input_mode == "Paste text":
    text_input = st.text_area("Paste your content here", height=200, placeholder="e.g. VAT registration requirements for EU businesses...")
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
    conf_color = CONFIDENCE_COLORS.get(conf, "grey")
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
