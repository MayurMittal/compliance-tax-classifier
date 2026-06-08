# Tax & Compliance Classifier

An AI-powered tool that reads any webpage, text, or file and does two things automatically:

1. **Classifies** the content across 13 tax/compliance categories with jurisdiction detection and confidence scoring
2. **Researches** the relevant rules, recent changes, deadlines, and penalties by fetching live data from curated official sources

Built with [Claude Sonnet 4.6](https://www.anthropic.com/claude) and [Streamlit](https://streamlit.io/).

---

## What It Does

### Step 1 — Tax & Compliance Classification

Given any input (URL, pasted text, or uploaded file), the classifier:

- Fetches and cleans the content (strips scripts, navigation, footers)
- Sends it to Claude Sonnet 4.6 with a structured JSON schema enforced
- Returns a classification with:
  - **Primary label** — the dominant tax/compliance category (e.g. GST, VAT, SALES_TAX)
  - **Secondary labels** — any additional categories also present
  - **Jurisdiction** — country or regulatory body, if detectable (e.g. India, United Kingdom)
  - **Confidence** — `high`, `medium`, or `low`
  - **Summary** — one-sentence explanation of the classification

### Step 2 — Compliance Research Agent

Immediately after classification, the app automatically:

- Looks up the matched tax type and jurisdiction in `sources_config.json`
- Fetches live content from each configured trusted URL using `httpx` + `BeautifulSoup`
- Sends the combined content to Claude Sonnet 4.6 and extracts:
  - **Current rates** — specific percentages and thresholds
  - **Recent changes** — rule updates from the last 90 days
  - **Key deadlines** — filing dates, registration thresholds
  - **Penalties** — consequences for non-compliance
- Displays results in an expandable **"Relevant Rules & Recent Changes"** panel with clickable source links

If no sources are configured for a given tax type or jurisdiction, a friendly message prompts you to add them in `sources_config.json`.

---

## Supported Tax & Compliance Categories

| Label | Description |
|---|---|
| `VAT` | Value Added Tax |
| `GST` | Goods and Services Tax |
| `SALES_TAX` | US-style retail sales tax |
| `CUSTOMS_DUTY` | Import / export duties |
| `EXCISE_TAX` | Excise / sin tax (alcohol, tobacco, fuel) |
| `INCOME_TAX` | Corporate or individual income tax |
| `TRANSFER_PRICING` | Cross-border related-party transactions |
| `WITHHOLDING_TAX` | Tax withheld at source |
| `PAYROLL_TAX` | Employer / employee payroll levies |
| `COMPLIANCE_NOTICE` | Filing deadlines, penalties, audits |
| `TAX_TREATY` | International double-taxation agreements |
| `GENERAL_TAX` | Tax-related content that doesn't fit a specific bucket |
| `NOT_TAX_RELATED` | No tax or compliance content detected |

---

## Project Structure

```
compliance-tax-classifier/
├── classifier.py        # Core classification logic + CLI
├── agent.py             # Compliance research agent
├── app.py               # Streamlit web UI
├── sources_config.json  # Trusted source URLs by tax type and jurisdiction
├── requirements.txt     # Python dependencies
└── .env                 # API key (not committed — see setup)
```

---

## Architecture — Agent Flow

```
Input (URL / pasted text / uploaded file)
              │
              ▼
    ┌─────────────────────┐
    │   Content Fetcher   │  httpx GET → BeautifulSoup (strip tags)
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────────────────┐
    │   Step 1: Classifier            │
    │   Claude Sonnet 4.6             │
    │   Structured JSON output        │
    │   → primary_label               │
    │   → jurisdiction                │
    │   → confidence, summary         │
    └─────────────────────────────────┘
              │
              │  primary_label + jurisdiction
              ▼
    ┌─────────────────────────────────┐
    │   sources_config.json lookup    │
    │   {"GST": {"India": [url1,...]}}│
    └─────────────────────────────────┘
              │
              │  trusted URLs
              ▼
    ┌─────────────────────────────────┐
    │   Step 2: Research Agent        │
    │   Fetch each URL (httpx + BS4)  │
    │   Claude Sonnet 4.6             │
    │   Structured JSON output        │
    │   → current_rates               │
    │   → recent_changes (90 days)    │
    │   → key_deadlines               │
    │   → penalties                   │
    └─────────────────────────────────┘
              │
              ▼
    Streamlit UI — Classification badge
                 + Expandable research panel
```

---

## Configuring Trusted Sources

`sources_config.json` maps tax categories to jurisdictions and their official source URLs:

```json
{
  "GST": {
    "India": [
      "https://www.gst.gov.in/",
      "https://cbic-gst.gov.in/gst-goods-services-rates.html"
    ]
  },
  "VAT": {
    "United Kingdom": [
      "https://www.gov.uk/vat-rates",
      "https://www.gov.uk/guidance/vat-registration-thresholds"
    ]
  }
}
```

- The top-level key must match a label from the taxonomy above (e.g. `GST`, `VAT`, `SALES_TAX`)
- The second-level key must match the jurisdiction string returned by the classifier (e.g. `India`, `United Kingdom`, `United States`)
- Add as many URLs per jurisdiction as needed — all are fetched and combined before analysis

**Pre-configured sources:**

| Tax Type | Jurisdiction | Sources |
|---|---|---|
| `GST` | India | gst.gov.in, cbic-gst.gov.in |
| `VAT` | European Union | taxation-customs.ec.europa.eu |
| `VAT` | United Kingdom | gov.uk/vat-rates, gov.uk/vat-registration-thresholds |
| `SALES_TAX` | United States | irs.gov |
| `INCOME_TAX` | India | incometax.gov.in, incometaxindia.gov.in |
| `INCOME_TAX` | United States | irs.gov (business taxes + inflation adjustments) |
| `COMPLIANCE_NOTICE` | India | incometax.gov.in, gst.gov.in |

---

## Setup

### Prerequisites

- Python 3.9+
- An [Anthropic API key](https://console.anthropic.com/settings/keys)

### 1. Clone the repository

```bash
git clone https://github.com/MayurMittal/compliance-tax-classifier.git
cd compliance-tax-classifier
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure your API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

> The `.env` file is listed in `.gitignore` and will never be committed.

---

## Usage

### Web UI (Streamlit)

```bash
python -m streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

The UI offers three input modes:

| Mode | How to use |
|---|---|
| **Paste text** | Copy and paste any tax-related content directly |
| **Web page URL** | Enter a URL — the app fetches and parses the page automatically |
| **Upload file** | Upload a `.txt` or `.html` file from your computer |

Click **Classify** to run both the classification and the research agent. Results appear in two sections:
- A color-coded classification badge with confidence and jurisdiction
- An expandable **"Relevant Rules & Recent Changes"** panel with live data from official sources

---

### Command Line (Classifier only)

```bash
# Classify a URL
python classifier.py https://www.irs.gov/businesses/small-businesses-self-employed/sales-tax

# Classify raw text
python classifier.py "GST registration requirements for e-commerce sellers in India"
```

**Example output:**

```
=== Tax / Compliance Classification ===
  Primary label   : GST
  Jurisdiction    : India
  Confidence      : high
  Summary         : Content specifically addresses GST registration obligations
                    for e-commerce sellers operating in India.
=======================================
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `anthropic` | Official Anthropic Python SDK |
| `httpx` | HTTP client for fetching URLs (classifier + agent) |
| `beautifulsoup4` | HTML parsing and tag stripping |
| `python-dotenv` | Loads `ANTHROPIC_API_KEY` from `.env` |
| `streamlit` | Web UI framework |

Install all at once:

```bash
pip install -r requirements.txt
```

---

## Example Classifications

| Input | Primary Label | Jurisdiction | Confidence |
|---|---|---|---|
| IRS sales tax guide page | `SALES_TAX` | United States | high |
| EU VAT registration FAQ | `VAT` | European Union | high |
| India GST e-commerce article | `GST` | India | high |
| HMRC PAYE employer guidance | `PAYROLL_TAX` | United Kingdom | high |
| Python language Wikipedia page | `NOT_TAX_RELATED` | — | high |

---

## Application Screenshots

<img width="1577" height="839" alt="image" src="https://github.com/user-attachments/assets/6d5da962-4529-48dc-b15e-09381b25bcc7" />
<img width="1513" height="1027" alt="image" src="https://github.com/user-attachments/assets/3f20e1c3-f85f-454e-b02b-b4dd31ec811b" />

---

## License

MIT
