import re
import json
from pathlib import Path
from anthropic import Anthropic
from classifier import fetch_text

SOURCES_CONFIG_PATH = Path(__file__).parent / "sources_config.json"

SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "direct_answer": {
            "type": "string",
            "description": "Direct, specific answer to the user's research question. Cite exact rates, dates, or rules from the sources. 'Not found in sources' if not mentioned.",
        },
        "key_findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Main facts, rules, and requirements found across sources. One fact per item.",
        },
        "recent_changes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Rule changes or updates explicitly mentioned in the sources. Empty if none found.",
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
        "direct_answer", "key_findings", "recent_changes", "current_rates_or_rules",
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
    """Return sorted unique list of all jurisdictions across sources_config.json."""
    sources = _load_sources()
    jurs: set[str] = set()
    for tax_data in sources.values():
        jurs.update(tax_data.keys())
    return sorted(jurs)


def get_all_tax_types() -> list[str]:
    """Return sorted list of tax type keys from sources_config.json."""
    sources = _load_sources()
    return sorted(sources.keys())


def _generate_queries(
    tax_type: str, jurisdiction: str, research_context: str, time_period: str
) -> list[str]:
    """Ask Claude to produce exactly 2 highly specific search queries."""
    recency_hint = {
        "Last 7 days": "Queries must target very recent news. Include the current month and year (e.g. 'June 2026').",
        "Last 30 days": "Queries should target recent updates. Include '2026' in each query.",
        "Last 90 days": "Queries should target recent changes. Include '2025' or '2026'.",
        "Any time": "",
    }.get(time_period, "")

    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Generate exactly 2 highly specific web search queries for this tax research task.\n\n"
                f"Tax type: {tax_type}\n"
                f"Jurisdiction: {jurisdiction}\n"
                f"Research question: {research_context}\n"
                f"Time period: {time_period}. {recency_hint}\n\n"
                f"Rules:\n"
                f"- Queries must be specific to the exact jurisdiction (include state/province if given)\n"
                f"- Include a year (2025 or 2026) in at least one query\n"
                f"- Address the research question directly — do not generate generic category queries\n"
                f"- Prefer queries likely to surface official government or tax authority pages\n\n"
                f"Example for 'What is the sales tax rate on grocery items in New York?':\n"
                f'["New York grocery items sales tax rate exemption 2026 official", '
                f'"New York sales tax food items SUT rate latest"]\n\n'
                f"Return ONLY a JSON array of exactly 2 query strings, nothing else."
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
                        return queries[:2]
                except json.JSONDecodeError:
                    pass
    # fallback
    return [
        f"{tax_type} {jurisdiction} {research_context[:50]} official 2026",
        f"{tax_type} {jurisdiction} rate rules latest",
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

        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                urls = re.findall(r"https?://[^\s\"'<>)\]]+", text)
                found_urls.extend(urls)

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = [
                {"type": "tool_result", "tool_use_id": block.id, "content": ""}
                for block in response.content
                if getattr(block, "type", None) == "tool_use"
            ]
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

    return found_urls


def _collect_urls_via_search(queries: list[str], max_sources: int = 2) -> list[str]:
    """Run up to 2 search queries, taking the top 1 URL per query. Returns deduplicated list."""
    client = Anthropic()
    seen: set[str] = set()
    unique: list[str] = []

    for query in queries[:2]:  # hard cap at 2 queries
        try:
            urls = _search_single_query(client, query)
            if urls:
                top = urls[0]  # take only the first URL per query
                if top not in seen:
                    seen.add(top)
                    unique.append(top)
        except Exception:
            continue

    return unique[:max_sources]


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


def _synthesise(
    tax_type: str,
    jurisdiction: str,
    research_context: str,
    fetched_chunks: list[str],
    sources_used: list[str],
) -> dict:
    """Send all fetched content to Claude and return structured synthesis."""
    client = Anthropic()
    combined = "\n\n".join(fetched_chunks)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYNTHESIS_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Tax type: {tax_type}\n"
                f"Jurisdiction: {jurisdiction}\n"
                f"Research question: {research_context}\n\n"
                f"IMPORTANT: In the 'direct_answer' field, answer the research question above "
                f"directly and specifically using the sources below. Cite exact rates, dates, "
                f"or rules. Write 'Not found in sources' if the answer is not present.\n\n"
                f"Then also extract: key findings, recent changes, current rates or rules, "
                f"important deadlines, conflicting information, and a 3-sentence executive summary.\n\n"
                f"{combined}"
            ),
        }],
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": SYNTHESIS_SCHEMA},
        },
    )
    for block in response.content:
        if getattr(block, "type", None) == "text":
            result = json.loads(block.text)
            result["sources_used"] = sources_used
            return result
    raise RuntimeError("No text block in synthesis response")


def research_topic(
    tax_type: str,
    jurisdiction: str,
    research_context: str,
    time_period: str = "Any time",
    max_sources: int = 2,
) -> dict:
    """
    Main entry point for the sourcing agent.

    Returns a dict with keys:
      direct_answer, key_findings, recent_changes, current_rates_or_rules,
      important_deadlines, conflicting_information, sources_used, summary,
      used_fallback, no_sources
    """
    # Step 1: Generate 2 specific search queries
    queries = _generate_queries(tax_type, jurisdiction, research_context, time_period)

    # Step 2: Run web search — max 2 queries, top 1 URL each
    used_fallback = False
    try:
        candidate_urls = _collect_urls_via_search(queries, max_sources=max_sources)
    except Exception:
        candidate_urls = []

    # Step 3: Fall back to curated sources if web search yielded nothing
    if not candidate_urls:
        candidate_urls = _fallback_urls(jurisdiction)
        used_fallback = True

    if not candidate_urls:
        return {
            "direct_answer": "No sources available to answer this question.",
            "key_findings": [],
            "recent_changes": [],
            "current_rates_or_rules": "No sources available.",
            "important_deadlines": [],
            "conflicting_information": [],
            "sources_used": [],
            "summary": (
                f"No sources found for '{tax_type}' in {jurisdiction}. "
                f"Add URLs to sources_config.json to enable research for this jurisdiction."
            ),
            "used_fallback": False,
            "no_sources": True,
        }

    # Step 4: Fetch and clean content — max 3,000 chars per URL
    fetched_chunks: list[str] = []
    sources_used: list[str] = []
    for url in candidate_urls[:max_sources]:
        try:
            text = fetch_text(url, max_chars=3000)
            fetched_chunks.append(f"=== SOURCE: {url} ===\n{text}")
            sources_used.append(url)
        except Exception:
            continue

    if not fetched_chunks:
        return {
            "direct_answer": "Sources were found but could not be fetched.",
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
    result = _synthesise(tax_type, jurisdiction, research_context, fetched_chunks, sources_used)
    result["used_fallback"] = used_fallback
    result["no_sources"] = False
    return result
