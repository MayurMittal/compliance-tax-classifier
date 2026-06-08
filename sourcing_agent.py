import re
import json
from pathlib import Path
from anthropic import Anthropic
from classifier import fetch_text

SOURCES_CONFIG_PATH = Path(__file__).parent / "sources_config.json"

SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "key_findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Main facts, rules, and requirements found across sources. One fact per item.",
        },
        "recent_changes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Rule changes or updates from the last 90 days explicitly mentioned. Empty if none found.",
        },
        "current_rates_or_rules": {
            "type": "string",
            "description": "Specific rates, thresholds, and rules with percentages/amounts where available. 'Not mentioned in sources' if absent.",
        },
        "important_deadlines": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Filing dates, registration thresholds, or compliance deadlines. Empty if none found.",
        },
        "conflicting_information": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Contradictions or inconsistencies found across sources. Empty if all sources agree.",
        },
        "sources_used": {
            "type": "array",
            "items": {"type": "string"},
            "description": "URLs of sources that contained useful information.",
        },
        "summary": {
            "type": "string",
            "description": "3-sentence executive summary of the key compliance requirements.",
        },
    },
    "required": [
        "key_findings", "recent_changes", "current_rates_or_rules",
        "important_deadlines", "conflicting_information", "sources_used", "summary",
    ],
    "additionalProperties": False,
}

SYNTHESIS_SYSTEM = """\
You are a tax compliance research analyst. Synthesize information from multiple sources
accurately and concisely. Only report what is explicitly stated in the provided sources.
Do not invent facts, rates, or deadlines not mentioned in the text.\
"""


def _load_sources() -> dict:
    if not SOURCES_CONFIG_PATH.exists():
        return {}
    with open(SOURCES_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_all_jurisdictions() -> list[str]:
    """Return sorted unique list of all jurisdictions in sources_config.json."""
    sources = _load_sources()
    jurs: set[str] = set()
    for tax_data in sources.values():
        jurs.update(tax_data.keys())
    return sorted(jurs)


def _generate_queries(topic: str, jurisdiction: str) -> list[str]:
    """Ask Claude to produce 3-5 targeted search queries for the topic."""
    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Generate 3 to 5 focused web search queries for researching this tax/compliance topic.\n"
                f"Topic: {topic}\n"
                f"Jurisdiction: {jurisdiction}\n\n"
                f"Return ONLY a JSON array of query strings, nothing else.\n"
                f"Prefer queries that target official government sites, tax authority publications, "
                f"or authoritative legal references.\n"
                f"Example: [\"India GST rate 2025 official\", \"CBIC GST recent amendments\"]"
            ),
        }],
    )
    for block in response.content:
        if hasattr(block, "text") and block.text:
            match = re.search(r"\[.*?\]", block.text, re.DOTALL)
            if match:
                try:
                    queries = json.loads(match.group())
                    if isinstance(queries, list) and queries:
                        return queries[:5]
                except json.JSONDecodeError:
                    pass
    # fallback queries if Claude response can't be parsed
    return [
        f"{topic} {jurisdiction} official",
        f"{topic} {jurisdiction} tax authority rules",
        f"{topic} {jurisdiction} recent changes 2025",
    ]


def _search_single_query(client: Anthropic, query: str) -> list[str]:
    """
    Run one search query via Anthropic's web_search tool.
    Returns a list of URLs extracted from Claude's final response.
    """
    messages = [{
        "role": "user",
        "content": (
            f"Search the web for: {query}\n"
            f"Find official or authoritative tax/government sources. "
            f"List the URLs of the most relevant results you find."
        ),
    }]

    found_urls: list[str] = []

    for _ in range(8):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )

        # Extract URLs from any text blocks in this response
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                urls = re.findall(r"https?://[^\s\"'<>)\]]+", text)
                found_urls.extend(urls)

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            # Acknowledge each tool_use block so the loop can continue
            tool_results = [
                {"type": "tool_result", "tool_use_id": block.id, "content": ""}
                for block in response.content
                if getattr(block, "type", None) == "tool_use"
            ]
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

    return found_urls


def _collect_urls_via_search(queries: list[str]) -> list[str]:
    """Run all search queries. Returns deduplicated list of URLs."""
    client = Anthropic()
    all_urls: list[str] = []
    for query in queries:
        try:
            all_urls.extend(_search_single_query(client, query))
        except Exception:
            continue
    # deduplicate, preserve order, cap at 10
    seen: set[str] = set()
    unique: list[str] = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique[:10]


def _fallback_urls(jurisdiction: str) -> list[str]:
    """Return all curated URLs for any tax type matching this jurisdiction."""
    sources = _load_sources()
    seen: set[str] = set()
    urls: list[str] = []
    for tax_data in sources.values():
        for jur, jur_urls in tax_data.items():
            if jur.lower() == jurisdiction.lower():
                for url in jur_urls:
                    if url not in seen:
                        seen.add(url)
                        urls.append(url)
    return urls


def _synthesise(topic: str, jurisdiction: str, fetched_chunks: list[str], sources_used: list[str]) -> dict:
    """Send all fetched content to Claude and return structured synthesis."""
    client = Anthropic()
    combined = "\n\n".join(fetched_chunks)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=SYNTHESIS_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Research topic: {topic}\n"
                f"Jurisdiction: {jurisdiction}\n\n"
                f"Synthesise the following sources and extract:\n"
                f"- key findings and rules\n"
                f"- recent changes in the last 90 days (only if explicitly mentioned)\n"
                f"- current rates or rules with specific figures\n"
                f"- important deadlines\n"
                f"- any conflicting information across sources\n"
                f"- a 3-sentence executive summary\n\n"
                f"{combined}"
            ),
        }],
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": SYNTHESIS_SCHEMA},
        },
    )
    for block in response.content:
        if getattr(block, "type", None) == "text":
            result = json.loads(block.text)
            result["sources_used"] = sources_used
            return result
    raise RuntimeError("No text block in synthesis response")


def research_topic(topic: str, jurisdiction: str) -> dict:
    """
    Main entry point for the sourcing agent.

    Returns a dict with keys:
      key_findings, recent_changes, current_rates_or_rules, important_deadlines,
      conflicting_information, sources_used, summary, used_fallback, no_sources
    """
    # Step 1: Generate search queries
    queries = _generate_queries(topic, jurisdiction)

    # Step 2: Run web search for each query
    used_fallback = False
    try:
        candidate_urls = _collect_urls_via_search(queries)
    except Exception:
        candidate_urls = []

    # Step 3: Fall back to curated sources if web search yielded nothing
    if not candidate_urls:
        candidate_urls = _fallback_urls(jurisdiction)
        used_fallback = True

    if not candidate_urls:
        return {
            "key_findings": [],
            "recent_changes": [],
            "current_rates_or_rules": "No sources available.",
            "important_deadlines": [],
            "conflicting_information": [],
            "sources_used": [],
            "summary": (
                f"No sources found for '{topic}' in {jurisdiction}. "
                f"Add URLs to sources_config.json to enable research for this jurisdiction."
            ),
            "used_fallback": False,
            "no_sources": True,
        }

    # Step 4: Fetch and clean content from each URL
    fetched_chunks: list[str] = []
    sources_used: list[str] = []
    for url in candidate_urls:
        try:
            text = fetch_text(url, max_chars=3000)
            fetched_chunks.append(f"=== SOURCE: {url} ===\n{text}")
            sources_used.append(url)
        except Exception:
            continue

    if not fetched_chunks:
        return {
            "key_findings": [],
            "recent_changes": [],
            "current_rates_or_rules": "Sources found but could not be fetched.",
            "important_deadlines": [],
            "conflicting_information": [],
            "sources_used": candidate_urls,
            "summary": "Candidate URLs were found but none could be fetched. Check connectivity.",
            "used_fallback": used_fallback,
            "no_sources": True,
        }

    # Step 5: Synthesise across all fetched documents
    result = _synthesise(topic, jurisdiction, fetched_chunks, sources_used)
    result["used_fallback"] = used_fallback
    result["no_sources"] = False
    return result
