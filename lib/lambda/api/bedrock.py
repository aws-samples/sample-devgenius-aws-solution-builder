"""
Bedrock Converse engine for DevGenius.

Runs an agentic loop with a single tool - ``web_search`` - backed by the
AgentCore Gateway web-search connector (see ``websearch.py``). The model decides
when to search; we execute the search, feed results back, and continue until the
model produces its final answer. This replaces the old Bedrock Agent +
Knowledge Base + OpenSearch retrieval path.
"""

import os

import boto3
from botocore.config import Config

import websearch

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-sonnet-4-6",
)
MAX_TOKENS = int(os.environ.get("BEDROCK_MAX_TOKENS", "8192"))
# Total Converse round-trips per request: covers web-search tool calls plus
# multiple continuations when a long answer exceeds maxTokens.
MAX_ITERATIONS = int(os.environ.get("MAX_ITERATIONS", "16"))

CONTINUE_PROMPT = (
    "Continue the previous response exactly where you left off. Output only the "
    "continuation - do not repeat any earlier content, and do not add any preamble, "
    "explanation, or a new code fence."
)

_config = Config(read_timeout=900, retries={"max_attempts": 4, "mode": "adaptive"})
_bedrock = boto3.client("bedrock-runtime", region_name=REGION, config=_config)

WEB_SEARCH_TOOL = {
    "toolSpec": {
        "name": "web_search",
        "description": (
            "Search the public web for up-to-date information: latest AWS "
            "services and features, current pricing, region availability, "
            "reference architectures, best practices, docs, and blog posts. "
            "Returns titles, URLs, snippets, and publication dates."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, 200 characters or fewer.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (1-25).",
                    },
                },
                "required": ["query"],
            }
        },
    }
}

TOOL_CONFIG = {"tools": [WEB_SEARCH_TOOL]}


def converse(messages, system_prompt, max_tokens=None, temperature=0, on_delta=None):
    """Run the tool-augmented, streaming Converse loop.

    Uses ``converse_stream`` so partial output can be surfaced live via the
    ``on_delta`` callback (called with the growing answer text). Handles the
    web-search tool and continues past ``max_tokens`` truncation, stitching the
    segments into one answer.

    Args:
        messages: Bedrock Converse ``messages`` list.
        system_prompt: system prompt string.
        max_tokens: optional per-call output token budget.
        temperature: sampling temperature.
        on_delta: optional callback ``fn(text_so_far)`` for streaming.

    Returns:
        ``(text, citations, stop_reason)``.
    """
    working = [_normalise_message(m) for m in messages]
    system = [{"text": system_prompt}]
    inference_config = {"maxTokens": max_tokens or MAX_TOKENS, "temperature": temperature}
    citations = []
    stop_reason = "end_turn"
    answer = ""

    for _ in range(MAX_ITERATIONS):
        message, stop_reason, answer = _stream_once(
            working, system, inference_config, on_delta, answer
        )
        working.append(message)

        if stop_reason == "tool_use":
            # Text before a tool call is preamble ("let me search..."); drop it
            # from the final answer, run the tool(s), and continue.
            answer = ""
            tool_results = [
                _run_tool(block["toolUse"], citations)
                for block in message.get("content", [])
                if block.get("toolUse")
            ]
            working.append({"role": "user", "content": tool_results})
            continue

        if stop_reason == "max_tokens":
            working.append({"role": "user", "content": [{"text": CONTINUE_PROMPT}]})
            continue

        break  # end_turn / stop_sequence - complete

    return answer.strip(), _dedupe_citations(citations), stop_reason


def _stream_once(working, system, inference_config, on_delta, answer_prefix):
    """Stream one Converse turn. Returns ``(assistant_message, stop_reason, answer)``."""
    response = _bedrock.converse_stream(
        modelId=MODEL_ID,
        messages=working,
        system=system,
        inferenceConfig=inference_config,
        toolConfig=TOOL_CONFIG,
    )

    blocks = {}  # contentBlockIndex -> {"type": "text"|"tool", ...}
    answer = answer_prefix
    stop_reason = "end_turn"

    for event in response["stream"]:
        if "contentBlockStart" in event:
            idx = event["contentBlockStart"]["contentBlockIndex"]
            start = event["contentBlockStart"].get("start", {})
            if "toolUse" in start:
                tu = start["toolUse"]
                blocks[idx] = {"type": "tool", "id": tu["toolUseId"], "name": tu["name"], "input": ""}
            else:
                blocks[idx] = {"type": "text", "text": ""}
        elif "contentBlockDelta" in event:
            idx = event["contentBlockDelta"]["contentBlockIndex"]
            delta = event["contentBlockDelta"]["delta"]
            block = blocks.setdefault(idx, {"type": "text", "text": ""})
            if "text" in delta:
                block.setdefault("text", "")
                block["text"] += delta["text"]
                answer += delta["text"]
                if on_delta:
                    on_delta(answer)
            elif "toolUse" in delta:
                block["type"] = "tool"
                block["input"] = block.get("input", "") + delta["toolUse"].get("input", "")
        elif "messageStop" in event:
            stop_reason = event["messageStop"].get("stopReason", "end_turn")

    content = []
    for idx in sorted(blocks):
        block = blocks[idx]
        if block["type"] == "text" and block.get("text"):
            content.append({"text": block["text"]})
        elif block["type"] == "tool":
            content.append(
                {
                    "toolUse": {
                        "toolUseId": block["id"],
                        "name": block["name"],
                        "input": _safe_json(block.get("input", "")),
                    }
                }
            )
    return {"role": "assistant", "content": content}, stop_reason, answer


def _safe_json(text):
    import json

    try:
        return json.loads(text) if text else {}
    except json.JSONDecodeError:
        return {}


def _run_tool(tool_use, citations):
    """Execute a single ``web_search`` tool call and build a tool result block."""
    tool_use_id = tool_use["toolUseId"]
    args = tool_use.get("input", {}) or {}
    query = args.get("query", "")
    max_results = args.get("max_results", 8)

    try:
        results = websearch.search(query, max_results)
        for r in results:
            if r.get("url"):
                citations.append({"title": r.get("title", ""), "url": r["url"]})
        payload = {"query": query, "results": results}
        return {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"json": payload}],
            }
        }
    except Exception as exc:  # noqa: BLE001 - surface a graceful tool error
        return {
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"text": f"web_search failed: {exc}"}],
                "status": "error",
            }
        }


def _normalise_message(message):
    """Accept both plain-text messages and Converse content-block messages."""
    content = message.get("content")
    if isinstance(content, str):
        return {"role": message["role"], "content": [{"text": content}]}
    return {"role": message["role"], "content": content}


def _dedupe_citations(citations):
    seen = set()
    unique = []
    for c in citations:
        url = c.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(c)
    return unique
