"""
DevGenius backend Lambda.

Fronted by an API Gateway HTTP API with a Cognito JWT authorizer (a Lambda
Function URL cannot be used in this account - an Organizations control blocks
Function URL invocation). Routes:

  POST /invoke        - actions: chat | generate | session | feedback | bundle
  GET  /job/{jobId}   - poll the result of an async chat/generate job

Because API Gateway caps a synchronous response at ~30s and generations (diagrams,
docs, IaC with live web search) can take longer, ``chat`` and ``generate`` run
asynchronously: /invoke returns a jobId immediately and the function re-invokes
itself (event mode) to do the work, writing the result for the client to poll.
"""

import base64
import json
import os
import re
import time
import urllib.parse
import uuid

import boto3

import bedrock
import prompts
import storage

REGION = os.environ.get("AWS_REGION", "us-east-1")
SELF_NAME = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")
_lambda = boto3.client("lambda", region_name=REGION)

ASYNC_ACTIONS = {"chat", "generate"}


def handler(event, context):
    # Background worker invocation (event mode) - do the heavy lifting. The input
    # was stashed in S3 (payloads with images exceed the async invoke limit).
    if isinstance(event, dict) and event.get("_asyncJob"):
        job_id = event["_asyncJob"]
        _run_worker(job_id, storage.get_job_input(job_id))
        return {}

    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    if method == "OPTIONS":
        return _resp(200, {})

    identity = _identity(event)
    path = event.get("rawPath", "")

    # Poll a job result.
    if method == "GET" and "/job/" in path:
        job_id = path.rsplit("/", 1)[-1]
        job = storage.get_job(job_id)
        return _resp(200, job) if job else _resp(404, {"error": "job not found"})

    try:
        body = json.loads(event.get("body") or "{}")
        if event.get("isBase64Encoded"):
            body = json.loads(base64.b64decode(event["body"]).decode("utf-8"))
    except (ValueError, TypeError):
        return _resp(400, {"error": "Invalid JSON body"})

    # Trust the JWT-verified identity over anything the client claims.
    body["userEmail"] = identity["email"] or body.get("userEmail", "")
    body["userName"] = (identity["email"] or identity["username"] or "user").split("@")[0]
    action = body.get("action")

    try:
        if action in ASYNC_ACTIONS:
            job_id = str(uuid.uuid4())
            storage.create_job(job_id)
            storage.put_job_input(job_id, body)  # keep the (possibly large) body out of the invoke payload
            _lambda.invoke(
                FunctionName=SELF_NAME,
                InvocationType="Event",
                Payload=json.dumps({"_asyncJob": job_id}).encode("utf-8"),
            )
            return _resp(202, {"jobId": job_id})
        if action == "session":
            return _resp(200, handle_session(body))
        if action == "listConversations":
            return _resp(200, {"conversations": storage.list_conversations(body["userEmail"])})
        if action == "loadConversation":
            return _resp(200, handle_load(body))
        if action == "deleteConversation":
            ok = storage.delete_conversation(body["conversationId"], body.get("userEmail", ""))
            return _resp(200 if ok else 403, {"ok": ok})
        if action == "feedback":
            return _resp(200, handle_feedback(body))
        if action == "bundle":
            return _resp(200, handle_bundle(body))
        return _resp(400, {"error": f"Unknown action: {action}"})
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR handling action={action}: {exc}")
        return _resp(500, {"error": str(exc)})


def _run_worker(job_id, body):
    # Throttled streaming callback: push partial output to S3 at most ~every 1.2s.
    last = [0.0]

    def on_delta(text):
        now = time.time()
        if now - last[0] > 1.2:
            last[0] = now
            storage.update_partial(job_id, text)

    try:
        action = body.get("action")
        if action == "chat":
            result = handle_chat(body, on_delta)
        elif action == "generate":
            result = handle_generate(body, on_delta)
        else:
            result = {"error": f"Unknown async action: {action}"}
        storage.finish_job(job_id, result)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR in async job {job_id}: {exc}")
        storage.fail_job(job_id, exc)
    finally:
        storage.delete_job_input(job_id)


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
def handle_chat(body, on_delta=None):
    conversation_id = body["conversationId"]
    history = body.get("messages", [])
    user_message = body.get("message", "")
    image_b64 = body.get("image")
    user_email = body.get("userEmail", "")
    user_name = body.get("userName", "")

    mode = body.get("mode", "build")
    messages = list(history)
    if image_b64:
        image_bytes = base64.b64decode(image_b64.split(",")[-1])
        fmt = body.get("imageFormat", "png")
        storage.put_image(conversation_id, f"diagram.{fmt}", image_bytes, f"image/{fmt}")
        messages.append(
            {
                "role": "user",
                "content": [
                    {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
                    {"text": user_message or "Analyze this architecture."},
                ],
            }
        )
        system_prompt = prompts.VISION_SYSTEM_PROMPT
        mode = "analyze"
    else:
        messages.append({"role": "user", "content": user_message})
        # In an analyze conversation, keep refining rather than restarting discovery.
        system_prompt = prompts.ANALYZE_REFINE_SYSTEM_PROMPT if mode == "analyze" else prompts.SYSTEM_PROMPT

    text, citations, _ = bedrock.converse(messages, system_prompt, on_delta=on_delta)

    # An analyzed/uploaded architecture is itself a ready solution, so unlock the
    # artifact generators immediately (in addition to the explicit marker).
    solution_ready = (prompts.SOLUTION_READY_MARKER in text) or (mode == "analyze")
    clean = text.replace(prompts.SOLUTION_READY_MARKER, "").strip()

    storage.save_conversation(conversation_id, user_email, user_name, user_message, clean)
    # First user message becomes the conversation title in the sidebar.
    storage.touch_conversation(conversation_id, user_email, user_name, user_message)
    return {"assistant": clean, "solutionReady": solution_ready, "citations": citations}


def handle_generate(body, on_delta=None):
    conversation_id = body["conversationId"]
    artifact = body.get("artifact")
    history = body.get("messages", [])
    user_email = body.get("userEmail", "")
    user_name = body.get("userName", "")

    prompt = prompts.ARTIFACT_PROMPTS.get(artifact)
    if not prompt:
        raise ValueError(f"Unknown artifact: {artifact}")

    messages = list(history) + [{"role": "user", "content": prompt}]
    # Larger per-call budget for long outputs reduces continuation round-trips.
    budget = 16000 if artifact in ("architecture", "documentation", "cdk", "cfn", "terraform") else None
    text, citations, _ = bedrock.converse(
        messages, prompts.SYSTEM_PROMPT, max_tokens=budget, on_delta=on_delta
    )

    result = {"artifact": artifact, "content": text, "citations": citations}

    if artifact in ("cost", "documentation"):
        # Safety net: if the model wrapped the whole markdown doc in a code fence,
        # unwrap it so it renders as formatted HTML instead of literal markdown.
        text = _unwrap_markdown(text)
        if artifact == "cost":
            text = text.replace("$", "USD ")
        result["content"] = text

    storage.store_artifact(conversation_id, artifact, text)

    if artifact == "architecture":
        xml = _extract_code(text, "xml") or _extract_diagram_xml(text)
        if xml:
            result["diagramXml"] = xml
    elif artifact == "cfn":
        yaml = _extract_code(text, "yaml") or _extract_code(text, "yml")
        if yaml:
            key = storage.store_named(conversation_id, "template.yaml", yaml)
            template_url = storage.presign(key, expires=86400)
            result["templateUrl"] = template_url
            result["launchStackUrl"] = (
                "https://console.aws.amazon.com/cloudformation/home"
                f"?region={REGION}#/stacks/quickcreate?stackName=devgenius-solution"
                f"&templateURL={urllib.parse.quote(template_url, safe='')}"
            )
    elif artifact == "cdk":
        code = _extract_code(text, "typescript") or _extract_code(text, "ts")
        if code:
            storage.store_named(conversation_id, "cdk-stack.ts", code)
    elif artifact == "terraform":
        code = _extract_code(text, "hcl") or _extract_code(text, "terraform")
        if code:
            storage.store_named(conversation_id, "main.tf", code)

    storage.save_conversation(conversation_id, user_email, user_name, f"generate:{artifact}", text)
    # Persist the full result so the artifact reloads with the conversation.
    storage.store_artifact_result(conversation_id, artifact, result)
    storage.touch_conversation(conversation_id, user_email, user_name)
    return result


def handle_session(body):
    storage.touch_conversation(body["conversationId"], body.get("userEmail", ""), body.get("userName", ""))
    return {"ok": True}


def handle_load(body):
    conversation_id = body["conversationId"]
    messages = storage.load_messages(conversation_id)
    artifacts = storage.load_artifacts(conversation_id)
    return {
        "messages": messages,
        "artifacts": artifacts,
        "solutionReady": bool(artifacts) or len(messages) >= 2,
    }


def handle_feedback(body):
    storage.save_feedback(
        body["conversationId"],
        body.get("sentiment"),
        body.get("explanation"),
        body.get("response"),
        body.get("useCase"),
        bedrock.MODEL_ID,
    )
    return {"ok": True}


def handle_bundle(body):
    return {"downloadUrl": storage.bundle_artifacts(body["conversationId"])}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _identity(event):
    claims = (
        (event.get("requestContext", {}).get("authorizer", {}) or {}).get("jwt", {}).get("claims", {})
        or {}
    )
    return {
        "email": claims.get("email", ""),
        "username": claims.get("cognito:username") or claims.get("username", ""),
    }


def _extract_code(markdown, language):
    # Preferred: a complete fenced block.
    match = re.search(rf"```{language}\s*\n(.*?)```", markdown, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: an opening fence with no closing fence (truncated output).
    match = re.search(rf"```{language}\s*\n(.*)$", markdown, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip("`").strip()
    return None


def _unwrap_markdown(text):
    """If the entire response is wrapped in one ```markdown/```md/``` fence,
    return the inner content so it renders as HTML rather than a code block."""
    stripped = text.strip()
    match = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", stripped, re.DOTALL)
    return match.group(1).strip() if match else text


def _extract_diagram_xml(markdown):
    """Fallback draw.io extraction: grab the mxfile/mxGraphModel document even if
    it isn't fenced as ```xml."""
    for tag in ("mxfile", "mxGraphModel"):
        match = re.search(rf"<{tag}.*?</{tag}>", markdown, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def _resp(status, payload):
    # CORS headers are added by the HTTP API's CORS configuration.
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(payload)}
