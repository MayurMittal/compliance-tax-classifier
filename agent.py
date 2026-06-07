import json
from pathlib import Path
from anthropic import Anthropic
from classifier import fetch_text

SOURCES_CONFIG_PATH = Path(__file__).parent / "sources_config.json"

RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "current_rates": {
            "type": "string",
            "description": "Current tax rates mentioned in the sources. Be specific with percentages. Use 'Not mentioned in sources' if absent.",
        },
        "recent_changes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Rule changes or updates from the last 90 days mentioned in the sources. Empty array if none found.",
        },
        "key_deadlines": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Filing dates, registration thresholds, or compliance deadlines mentioned. Empty array if none found.",
        },
        "penalties": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Penalties or consequences for non-compliance mentioned. Empty array if none found.",
        },
        "summary": {
            "type": "string",
            "description": "2-3 sentence summary of the key compliance requirements from the sources.",
        },
    },
    "required": ["current_rates", "recent_changes", "key_deadlines", "penalties", "summary"],
    "additionalProperties": False,
}

RESEARCH_SYSTEM_PROMPT = """\
You are a tax compliance research assistant. Your job is to extract structured,
actionable information from official tax authority sources.

Be precise:
- Quote specific rates, thresholds, and dates when the sources mention them.
- For recent_changes, only include items explicitly described as new or updated — do not invent changes.
- If information is not present in the provided sources, say so clearly rather than guessing.
- Keep each list item concise (one fact per item, under 20 words).\
"""


def _load_sources() -> dict:
    if not SOURCES_CONFIG_PATH.exists():
        return {}
    with open(SOURCES_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def research_compliance(primary_label: str, jurisdiction: str) -> dict:
    """
    Returns a research result dict with keys:
      sources_used, current_rates, recent_changes, key_deadlines, penalties, summary
    Or {"no_sources": True} if no URLs are configured or all fetches failed.
    """
    sources = _load_sources()

    urls = sources.get(primary_label, {}).get(jurisdiction, [])
    if not urls:
        return {"no_sources": True}

    fetched_chunks = []
    sources_used = []
    for url in urls:
        try:
            text = fetch_text(url, max_chars=4000)
            fetched_chunks.append(f"=== SOURCE: {url} ===\n{text}")
            sources_used.append(url)
        except Exception:
            pass

    if not fetched_chunks:
        return {"no_sources": True, "fetch_failed": True}

    combined_content = "\n\n".join(fetched_chunks)

    client = Anthropic()
    user_message = f"""\
Analyze the following content from official sources about {primary_label.replace("_", " ")} in {jurisdiction}.

Extract current rates, recent rule changes (last 90 days), key compliance deadlines, and penalties.

{combined_content}
"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=RESEARCH_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        output_config={
            "effort": "high",
            "format": {
                "type": "json_schema",
                "schema": RESEARCH_SCHEMA,
            },
        },
    )

    for block in response.content:
        if block.type == "text":
            result = json.loads(block.text)
            result["sources_used"] = sources_used
            return result

    raise RuntimeError("No text block in response")
