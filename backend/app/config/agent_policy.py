"""Shared agent policy text and prompt builders."""

from collections.abc import Iterable


RESPONSE_FORMAT_POLICY = """

## Response Format

For every model response, return ONLY one valid JSON object.

Use this exact shape when you need a tool:
{
  "response_type": "tool_call",
  "assistant_text": "",
  "turn_summary": "",
  "tool_call": {
    "name": "tool_name",
    "arguments": {
      "param1": "value1"
    }
  }
}

Use this exact shape when you are ready to answer the user:
{
  "response_type": "final",
  "assistant_text": "your full user-facing answer",
  "turn_summary": "a short plain-text summary of the answer for runtime memory",
  "tool_call": null
}

Important rules:
- Return ONLY JSON. No markdown fences. No prose outside the JSON object.
- `turn_summary` is internal runtime metadata. Keep it plain text, concise, and factual.
- If `response_type` is `tool_call`, leave `assistant_text` and `turn_summary` empty.
- If `response_type` is `final`, `assistant_text` must contain the full answer and `turn_summary` must be non-empty.
- Previous tool results may appear in the conversation as JSON user messages with a `tool_output` field.
"""


TOOL_USAGE_POLICY = """

## Available Tools

You have access to the following tools. **You should actively use tools** whenever a question involves:
- Looking up real-time or specific web page content
- Fetching official school/program/exam information from URLs
- Any task where accurate, up-to-date information is needed rather than relying on your training data

Important rules:
- When you want to use a tool, respond with the JSON `response_type="tool_call"` format
- You may call ONE tool per response
- After you receive a `tool_output`, you can call another tool or give your final answer
- When you have enough information, respond with the JSON `response_type="final"` format
- If the user explicitly asks you to fetch a URL or use a specific tool, you MUST use it
- NEVER invent, guess, or handcraft new URLs based on patterns such as /admission, /exam, /guide, /index, or filename guesses
- When navigating a website, only fetch:
  1. a URL explicitly provided by the user,
  2. a URL returned by lookup_source,
  3. a URL discovered in links or pdf_links from a previous tool result
- If a fetched page fails or is irrelevant, do not keep guessing nearby URLs on the same site; instead, go back to a known page and choose from actual discovered links
- Prefer official PDFs or pages that are directly linked from known official pages over guessed HTML paths
- If you cannot find a relevant link from known sources, stop exploring and explain what URL is still needed

Tools:
{tool_list}"""


def build_tool_policy(tool_schemas: Iterable[dict]) -> str:
    """Build the injected tool usage policy from tool schemas."""
    tool_descriptions: list[str] = []

    for schema in tool_schemas:
        params = schema.get("parameters", [])
        usage_guidelines = schema.get("usage_guidelines", [])
        params_desc = ""
        if params:
            parts = ", ".join(
                f'{param["name"]} ({param["type"]}, '
                f'{"required" if param["required"] else "optional"}): '
                f'{param["description"]}'
                for param in params
            )
            params_desc = f"  Parameters: {parts}"
        guideline_desc = ""
        if usage_guidelines:
            guideline_desc = "\n  Usage: " + " ".join(f"- {rule}" for rule in usage_guidelines)
        tool_descriptions.append(
            f'- **{schema["name"]}**: {schema["description"]}\n{params_desc}{guideline_desc}'
        )

    tool_list = "\n".join(tool_descriptions)
    return TOOL_USAGE_POLICY.format(tool_list=tool_list)


def build_response_format_policy() -> str:
    """Build the stable JSON response contract used by the native runtime."""
    return RESPONSE_FORMAT_POLICY.strip()
