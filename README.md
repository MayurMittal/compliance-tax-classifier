# Tax & Compliance Classifier

An AI-powered tool that reads any webpage or text and instantly identifies the type of tax or compliance content it contains — VAT, GST, Sales Tax, Customs Duty, Income Tax, and more.

Built with [Claude Sonnet 4.6](https://www.anthropic.com/claude) and [Streamlit](https://streamlit.io/).

---

## What It Does

Given a URL, pasted text, or an uploaded file, the classifier:

1. Fetches and cleans the content (strips navigation, scripts, footers)
2. Sends it to Claude Sonnet 4.6 with structured JSON output enforced
3. Returns a structured classification with:
   - **Primary label** — the dominant tax/compliance category
   - **Secondary labels** — any additional categories also present
   - **Jurisdiction** — country or regulatory body, if detectable
   - **Confidence** — `high`, `medium`, or `low`
   - **Summary** — one-sentence explanation of the classification

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
├── classifier.py      # Core classification logic + CLI
├── app.py             # Streamlit web UI
├── requirements.txt   # Python dependencies
└── .env               # API key (not committed — see setup)
```

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

Click **Classify** to run the analysis. Results appear below the button with color-coded labels.

---

### Command Line

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

## How It Works

### Architecture

```
Input (URL / text / file)
         │
         ▼
  app.py or classifier.py
         │
         ├─ URL  → httpx GET → BeautifulSoup (strip tags) → clean text
         ├─ File → read + BeautifulSoup if HTML → clean text
         └─ Text → use as-is
                │
                ▼
       Claude Sonnet 4.6
       output_config: JSON schema (structured output)
       effort: high
                │
                ▼
       ClassificationResult
         primary_label, secondary_labels,
         jurisdiction, confidence, summary
```

### Model & Configuration

| Setting | Value |
|---|---|
| Model | `claude-sonnet-4-6` |
| Effort | `high` (maximum for Sonnet) |
| Output | Structured JSON schema — enforces valid labels every time |
| Max content | 10,000 characters (truncated after stripping HTML) |

Structured output (`output_config.format`) is used instead of prompt-only JSON extraction to guarantee that labels always match the taxonomy and the response is always machine-parseable — no regex or fallback parsing needed.

---

## Dependencies

| Package | Purpose |
|---|---|
| `anthropic` | Official Anthropic Python SDK |
| `httpx` | Async-capable HTTP client for fetching URLs |
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

## License

MIT
