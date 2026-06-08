"""
Provider abstraction layer.

Reads ENVIRONMENT from .env ("test" = Gemini 1.5 Flash, "prod" = Claude Sonnet 4.6).
Exposes get_completion() and search_web() so callers never import an SDK directly.
"""
import os
import re
from dotenv import load_dotenv

load_dotenv()

_env: str = os.getenv("ENVIRONMENT", "prod").lower()


# ── Public API ─────────────────────────────────────────────────────────────────

def set_environment(env: str) -> None:
    """Override the environment at runtime (used by the Streamlit sidebar toggle)."""
    global _env
    _env = env.lower()


def get_environment() -> str:
    return _env


def get_active_model_name() -> str:
    if _env == "test":
        return "Gemini 1.5 Flash (Test)"
    return "Claude Sonnet 4.6 (Production)"


def get_completion(
    prompt: str,
    system_prompt: str = "",
    schema: dict = None,
    max_tokens: int = 1024,
    effort: str = "high",
) -> str:
    """
    Single-turn text completion.

    - schema: optional JSON Schema dict for structured JSON output.
              When provided, the return value is a JSON string.
    - effort: only used in Anthropic mode; ignored for Gemini.
    Always returns a plain string (callers parse JSON themselves when needed).
    """
    if _env == "test":
        return _gemini_completion(prompt, system_prompt, schema, max_tokens)
    return _anthropic_completion(prompt, system_prompt, schema, max_tokens, effort)


def search_web(query: str) -> list[str]:
    """
    Run one search query and return a list of result URLs.
    In test mode (Gemini) returns [] — the caller falls back to curated sources.
    In prod mode runs the Anthropic web_search agentic loop.
    """
    if _env == "test":
        return []
    return _anthropic_search_web(query)


# ── Anthropic backend ──────────────────────────────────────────────────────────

def _anthropic_completion(
    prompt: str,
    system_prompt: str,
    schema: dict | None,
    max_tokens: int,
    effort: str,
) -> str:
    from anthropic import Anthropic
    client = Anthropic()
    kwargs: dict = {
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt
    if schema:
        kwargs["output_config"] = {
            "effort": effort,
            "format": {"type": "json_schema", "schema": schema},
        }
    response = client.messages.create(**kwargs)
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def _anthropic_search_web(query: str) -> list[str]:
    """Agentic loop using Anthropic's server-side web_search tool."""
    from anthropic import Anthropic
    client = Anthropic()
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
                found_urls.extend(re.findall(r"https?://[^\s\"'<>)\]]+", text))
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


# ── Gemini backend ─────────────────────────────────────────────────────────────

_GEMINI_TYPE_MAP = {
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def _to_gemini_schema(schema: dict) -> dict:
    """Convert a JSON Schema dict to Gemini's schema format (uppercase types)."""
    result: dict = {}
    if "type" in schema:
        result["type"] = _GEMINI_TYPE_MAP.get(schema["type"], schema["type"].upper())
    if "description" in schema:
        result["description"] = schema["description"]
    if "enum" in schema:
        result["enum"] = schema["enum"]
    if "properties" in schema:
        result["properties"] = {
            k: _to_gemini_schema(v) for k, v in schema["properties"].items()
        }
    if "required" in schema:
        result["required"] = schema["required"]
    if "items" in schema:
        result["items"] = _to_gemini_schema(schema["items"])
    # additionalProperties is not supported by Gemini — skip it
    return result


def _gemini_completion(
    prompt: str,
    system_prompt: str,
    schema: dict | None,
    max_tokens: int,
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    config_kwargs: dict = {"max_output_tokens": max_tokens}
    if system_prompt:
        config_kwargs["system_instruction"] = system_prompt
    if schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = _to_gemini_schema(schema)

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return response.text
