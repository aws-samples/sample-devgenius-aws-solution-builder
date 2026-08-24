"""
Client for the Amazon Bedrock AgentCore Gateway "web-search" connector.

The Gateway exposes web search as a standard MCP (Model Context Protocol) tool
over Streamable-HTTP / JSON-RPC. Requests are authenticated with SigV4 against
the ``bedrock-agentcore`` service - no third-party search API keys, and queries
stay inside AWS. This module:

  * SigV4-signs every JSON-RPC call to the Gateway MCP endpoint,
  * performs the MCP handshake (``initialize`` + ``notifications/initialized``)
    and threads the ``Mcp-Session-Id`` header through subsequent calls,
  * discovers the web-search tool name via ``tools/list`` (Gateway tool names
    are namespaced by target, e.g. ``websearch___WebSearch``),
  * invokes the tool and normalises the result into a simple list of
    ``{title, url, snippet, published_date}`` dicts.

Docs: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-web-search-tool.html
"""

import json
import os
import urllib.error
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

REGION = os.environ.get("AWS_REGION", "us-east-1")
# Full MCP endpoint URL of the AgentCore Gateway, e.g.
# https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp
GATEWAY_URL = os.environ.get("GATEWAY_URL", "")
SERVICE = "bedrock-agentcore"
PROTOCOL_VERSION = "2025-06-18"

_session = boto3.session.Session()
_credentials = _session.get_credentials()

# Per-container caches.
_session_id = None
_initialized = False
_tool_name_cache = None
_rpc_id = 0


class WebSearchError(Exception):
    """Raised when the Gateway cannot be reached or returns an error."""


def _next_id():
    global _rpc_id
    _rpc_id += 1
    return _rpc_id


def _signed_post(payload: dict, timeout: int = 30):
    """POST a JSON-RPC payload, SigV4-signed. Returns ``(message|None, headers)``.

    A ``None`` message means the server returned an empty body (e.g. 202 Accepted
    for a notification), which is valid.
    """
    if not GATEWAY_URL:
        raise WebSearchError("GATEWAY_URL is not configured")

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _session_id:
        headers["Mcp-Session-Id"] = _session_id

    aws_request = AWSRequest(method="POST", url=GATEWAY_URL, data=body, headers=headers)
    SigV4Auth(_credentials, SERVICE, REGION).add_auth(aws_request)

    http_request = urllib.request.Request(
        GATEWAY_URL, data=body, headers=dict(aws_request.headers.items()), method="POST"
    )
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise WebSearchError(f"Gateway HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise WebSearchError(f"Gateway unreachable: {exc.reason}") from exc

    return _parse_jsonrpc(raw), resp_headers


def _parse_jsonrpc(raw: str):
    """Parse a JSON-RPC response, tolerating SSE framing and empty bodies."""
    text = (raw or "").strip()
    if not text:
        return None

    # Streamable-HTTP may return Server-Sent Events; take the last ``data:`` line.
    if text.startswith("event:") or "\ndata:" in text or text.startswith("data:"):
        data_lines = [
            line[len("data:"):].strip()
            for line in text.splitlines()
            if line.startswith("data:")
        ]
        if data_lines:
            text = data_lines[-1]

    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WebSearchError(f"Invalid JSON-RPC response: {text[:500]}") from exc

    if isinstance(message, dict) and message.get("error"):
        raise WebSearchError(f"JSON-RPC error: {message['error']}")
    return message


def _ensure_initialized():
    """Run the MCP handshake once per container."""
    global _session_id, _initialized
    if _initialized:
        return

    _, headers = _signed_post(
        {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "devgenius", "version": "2.0"},
            },
        }
    )
    session_id = headers.get("mcp-session-id")
    if session_id:
        _session_id = session_id

    # Best-effort "initialized" notification; a stateless server may 202/empty.
    try:
        _signed_post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    except WebSearchError:
        pass

    _initialized = True


def _resolve_tool_name() -> str:
    """Discover the web-search tool name exposed by the Gateway."""
    global _tool_name_cache
    if _tool_name_cache:
        return _tool_name_cache

    override = os.environ.get("WEB_SEARCH_TOOL_NAME")
    if override:
        _tool_name_cache = override
        return override

    listing, _ = _signed_post({"jsonrpc": "2.0", "id": _next_id(), "method": "tools/list"})
    tools = ((listing or {}).get("result") or {}).get("tools", [])
    for tool in tools:
        if "search" in tool.get("name", "").lower():
            _tool_name_cache = tool["name"]
            return _tool_name_cache
    if tools:
        _tool_name_cache = tools[0]["name"]
        return _tool_name_cache
    raise WebSearchError("No tools exposed by the Gateway")


def search(query: str, max_results: int = 8) -> list:
    """Run a web search and return a list of ``{title, url, snippet, published_date}``."""
    query = (query or "")[:200]
    max_results = max(1, min(int(max_results or 8), 25))

    _ensure_initialized()
    tool_name = _resolve_tool_name()

    response, _ = _signed_post(
        {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": {"query": query, "maxResults": max_results},
            },
        }
    )
    return _normalise_results(response or {})


def _normalise_results(response: dict) -> list:
    """Flatten the MCP tool response into simple result dicts."""
    result = response.get("result") or {}
    if result.get("isError"):
        raise WebSearchError(f"Web search failed: {result.get('content')}")

    # Prefer structured content when present.
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and "results" in structured:
        return [_coerce_item(i) for i in structured["results"]]

    results = []
    for block in result.get("content", []):
        if block.get("type") != "text":
            continue
        parsed = _try_json(block.get("text", ""))
        if isinstance(parsed, dict) and "results" in parsed:
            results.extend(_coerce_item(i) for i in parsed["results"])
        elif isinstance(parsed, list):
            results.extend(_coerce_item(i) for i in parsed)
        else:
            results.append(
                {"title": "", "url": "", "snippet": block.get("text", ""), "published_date": None}
            )
    return results


def _coerce_item(item: dict) -> dict:
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "snippet": item.get("text") or item.get("snippet") or item.get("content", ""),
        "published_date": item.get("publishedDate") or item.get("published_date"),
    }


def _try_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
