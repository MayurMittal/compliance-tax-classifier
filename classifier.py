import sys
import json
import httpx
from bs4 import BeautifulSoup
from model_config import get_completion

TAXONOMY = [
    "VAT",
    "GST",
    "SALES_TAX",
    "CUSTOMS_DUTY",
    "EXCISE_TAX",
    "INCOME_TAX",
    "TRANSFER_PRICING",
    "WITHHOLDING_TAX",
    "PAYROLL_TAX",
    "COMPLIANCE_NOTICE",
    "TAX_TREATY",
    "GENERAL_TAX",
    "NOT_TAX_RELATED",
]

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_label": {
            "type": "string",
            "enum": TAXONOMY,
            "description": "The single best-fitting tax/compliance category for this content.",
        },
        "secondary_labels": {
            "type": "array",
            "items": {"type": "string", "enum": TAXONOMY},
            "description": "Additional categories present in the content, if any.",
        },
        "jurisdiction": {
            "type": "string",
            "description": "Country, region, or regulatory body if identifiable, otherwise empty string.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Confidence in the primary classification.",
        },
        "summary": {
            "type": "string",
            "description": "One-sentence explanation of why this classification was chosen.",
        },
    },
    "required": ["primary_label", "secondary_labels", "jurisdiction", "confidence", "summary"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are a tax and compliance content classifier with deep knowledge of global tax systems.

Given webpage text or document content, identify what type of tax or regulatory content it
contains using the taxonomy the user will supply in their message.

Rules:
- Pick the MOST SPECIFIC primary label. If the content clearly discusses VAT, use VAT not GENERAL_TAX.
- Add secondary labels only when other tax types are also meaningfully discussed.
- If the content has no tax or compliance relevance, use NOT_TAX_RELATED.
- Base jurisdiction on explicit mentions (country names, tax authority names, currency, etc.).
- Keep the summary under 25 words.\
"""


def fetch_text(url: str, max_chars: int = 10_000) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TaxClassifier/1.0)"}
    response = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text[:max_chars]


def classify(content: str) -> dict:
    taxonomy_list = "\n".join(f"  - {t}" for t in TAXONOMY)
    user_message = f"""\
Classify the following content using this taxonomy:
{taxonomy_list}

--- CONTENT START ---
{content}
--- CONTENT END ---\
"""
    result_text = get_completion(
        user_message,
        system_prompt=SYSTEM_PROMPT,
        schema=OUTPUT_SCHEMA,
        max_tokens=1024,
        effort="high",
    )
    return json.loads(result_text)


def print_result(result: dict) -> None:
    print("\n=== Tax / Compliance Classification ===")
    print(f"  Primary label   : {result['primary_label']}")
    if result["secondary_labels"]:
        print(f"  Secondary labels: {', '.join(result['secondary_labels'])}")
    if result["jurisdiction"]:
        print(f"  Jurisdiction    : {result['jurisdiction']}")
    print(f"  Confidence      : {result['confidence']}")
    print(f"  Summary         : {result['summary']}")
    print("=======================================\n")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python classifier.py <url-or-text>")
        print("  URL example : python classifier.py https://example.com/vat-guide")
        print("  Text example: python classifier.py \"GST registration requirements in India\"")
        sys.exit(1)

    input_arg = " ".join(sys.argv[1:])

    if input_arg.startswith("http://") or input_arg.startswith("https://"):
        print(f"Fetching URL: {input_arg}")
        try:
            content = fetch_text(input_arg)
        except httpx.HTTPError as exc:
            print(f"Error fetching URL: {exc}")
            sys.exit(1)
        print(f"Fetched {len(content)} characters. Classifying...")
    else:
        content = input_arg
        print("Classifying provided text...")

    result = classify(content)
    print_result(result)


if __name__ == "__main__":
    main()
