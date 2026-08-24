"""
Persistence helpers for DevGenius: DynamoDB (conversations, sessions, feedback)
and S3 (generated artifacts + downloadable zip bundles).
"""

import datetime
import glob
import json
import os
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

REGION = os.environ.get("AWS_REGION", "us-east-1")

# All timestamps are recorded in US Eastern Time (handles EST/EDT) as
# "yyyy-mm-dd hh:mm:ss".
try:
    from zoneinfo import ZoneInfo

    _ET = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 - IANA tz db unavailable on the runtime
    _ET = None


def _et_now():
    """Current time as an aware datetime in US Eastern Time."""
    if _ET is not None:
        return datetime.datetime.now(_ET)
    # Fallback: compute US Eastern manually (DST: 2nd Sun Mar - 1st Sun Nov).
    utc = datetime.datetime.now(datetime.timezone.utc)
    year = utc.year

    def _nth_sunday(month, n):
        first = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
        day = 1 + (6 - first.weekday()) % 7 + (n - 1) * 7
        return day

    dst_start = datetime.datetime(year, 3, _nth_sunday(3, 2), 7, tzinfo=datetime.timezone.utc)
    dst_end = datetime.datetime(year, 11, _nth_sunday(11, 1), 6, tzinfo=datetime.timezone.utc)
    offset = -4 if dst_start <= utc < dst_end else -5
    return (utc + datetime.timedelta(hours=offset)).replace(tzinfo=datetime.timezone(datetime.timedelta(hours=offset)))

CONVERSATION_TABLE = os.environ.get("CONVERSATION_TABLE_NAME", "")
SESSION_TABLE = os.environ.get("SESSION_TABLE_NAME", "")
FEEDBACK_TABLE = os.environ.get("FEEDBACK_TABLE_NAME", "")
JOBS_TABLE = os.environ.get("JOBS_TABLE_NAME", "")
BUCKET = os.environ.get("ARTIFACTS_BUCKET_NAME", "")

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_s3 = boto3.client("s3", region_name=REGION)
_s3_resource = boto3.resource("s3", region_name=REGION)


def _now():
    return _et_now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# DynamoDB
# --------------------------------------------------------------------------- #
def save_conversation(conversation_id, user_id, user_name, user_message, assistant_message):
    if not CONVERSATION_TABLE:
        return
    _dynamodb.Table(CONVERSATION_TABLE).put_item(
        Item={
            "conversation_id": conversation_id,
            "uuid": str(uuid.uuid4()),
            "user_id": user_id or "",
            "user_name": user_name or "",
            "user_response": user_message or "",
            "assistant_response": assistant_message or "",
            "conversation_time": _now(),
        }
    )


def touch_conversation(conversation_id, user_email, user_name, title_hint=""):
    """Upsert the conversation's session row: bump ``updated`` and set the title
    from the first user message. Backs the left-rail conversation list (queried
    through the ``by-user`` GSI)."""
    if not SESSION_TABLE:
        return
    title = (title_hint or "").strip().replace("\n", " ")
    if len(title) > 80:
        title = title[:77] + "..."
    _dynamodb.Table(SESSION_TABLE).update_item(
        Key={"conversation_id": conversation_id},
        UpdateExpression=(
            "SET user_email = :e, user_name = :n, updated = :u, "
            "title = if_not_exists(title, :t), created = if_not_exists(created, :u)"
        ),
        ExpressionAttributeValues={
            ":e": user_email or "unknown",
            ":n": user_name or "",
            ":u": _now(),
            ":t": title or "New conversation",
        },
    )


def list_conversations(user_email, limit=50):
    """Return the user's conversations, most recently updated first."""
    if not SESSION_TABLE or not user_email:
        return []
    resp = _dynamodb.Table(SESSION_TABLE).query(
        IndexName="by-user",
        KeyConditionExpression=Key("user_email").eq(user_email),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [
        {
            "conversationId": item["conversation_id"],
            "title": item.get("title", "Conversation"),
            "updated": item.get("updated", ""),
        }
        for item in resp.get("Items", [])
    ]


def update_session(conversation_id, presigned_url):
    if not SESSION_TABLE:
        return
    _dynamodb.Table(SESSION_TABLE).update_item(
        Key={"conversation_id": conversation_id},
        UpdateExpression="SET presigned_url = :url, session_update_time = :t",
        ExpressionAttributeValues={":url": presigned_url, ":t": _now()},
    )


def save_feedback(conversation_id, sentiment, explanation, response, use_case, model_id):
    if not FEEDBACK_TABLE:
        return
    _dynamodb.Table(FEEDBACK_TABLE).put_item(
        Item={
            "conversation_id": conversation_id,
            "uuid": str(uuid.uuid4()),
            "feedback": sentiment,
            "feedback_explanation": explanation or "",
            "response": response or "",
            "use_case": use_case or "",
            "bedrock_model": model_id or "",
            "conversation_time": _now(),
        }
    )


# --------------------------------------------------------------------------- #
# S3
# --------------------------------------------------------------------------- #
def store_artifact(conversation_id, content_type, content, extension="md"):
    """Store a generated artifact under the conversation prefix. Returns the key."""
    if not BUCKET:
        return None
    ts = _et_now().strftime("%Y%m%d-%H%M%S")  # ET, colon-free for S3 keys
    key = f"{conversation_id}/{content_type}-{ts}.{extension}"
    _s3.put_object(Body=content.encode("utf-8"), Bucket=BUCKET, Key=key)
    return key


def store_named(conversation_id, filename, content):
    """Store an object at a fixed name (e.g. template.yaml) and return its key."""
    if not BUCKET:
        return None
    key = f"{conversation_id}/{filename}"
    _s3.put_object(Body=content.encode("utf-8"), Bucket=BUCKET, Key=key)
    return key


def put_image(conversation_id, filename, data: bytes, content_type="image/png"):
    if not BUCKET:
        return None
    key = f"{conversation_id}/uploaded/{filename}"
    _s3.put_object(Body=data, Bucket=BUCKET, Key=key, ContentType=content_type)
    return key


def store_artifact_result(conversation_id, artifact, result):
    """Persist a generated artifact's full result so it can be reloaded later.
    Keyed per artifact, so concurrent 'Generate all' writes never clobber."""
    if not BUCKET:
        return
    _s3.put_object(
        Body=json.dumps(result).encode("utf-8"),
        Bucket=BUCKET,
        Key=f"conversations/{conversation_id}/artifacts/{artifact}.json",
        ContentType="application/json",
    )


def load_messages(conversation_id):
    """Reconstruct the chat transcript (excluding artifact-generation turns)."""
    if not CONVERSATION_TABLE:
        return []
    table = _dynamodb.Table(CONVERSATION_TABLE)
    items = []
    kwargs = {"KeyConditionExpression": Key("conversation_id").eq(conversation_id)}
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" in resp:
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        else:
            break
    items.sort(key=lambda x: x.get("conversation_time", ""))
    messages = []
    for item in items:
        user = item.get("user_response", "")
        assistant = item.get("assistant_response", "")
        if user.startswith("generate:"):
            continue  # artifact turn, not part of the chat
        if user:
            messages.append({"role": "user", "content": user})
        if assistant:
            messages.append({"role": "assistant", "content": assistant})
    return messages


def delete_conversation(conversation_id, user_email):
    """Delete a conversation and everything tied to it (turns, feedback, session
    row, and all S3 artifacts). Returns False if the caller doesn't own it."""
    if SESSION_TABLE:
        session = _dynamodb.Table(SESSION_TABLE).get_item(
            Key={"conversation_id": conversation_id}
        ).get("Item")
        owner = (session or {}).get("user_email")
        if session and user_email and owner not in (user_email, "", "unknown"):
            return False  # not the owner - refuse

    _delete_rows(CONVERSATION_TABLE, conversation_id)
    _delete_rows(FEEDBACK_TABLE, conversation_id)
    if SESSION_TABLE:
        _dynamodb.Table(SESSION_TABLE).delete_item(Key={"conversation_id": conversation_id})

    if BUCKET:
        bucket = _s3_resource.Bucket(BUCKET)
        for prefix in (f"{conversation_id}/", f"conversations/{conversation_id}/"):
            bucket.objects.filter(Prefix=prefix).delete()
    return True


def _delete_rows(table_name, conversation_id):
    """Delete every item (all sort keys) for a conversation from a table."""
    if not table_name:
        return
    table = _dynamodb.Table(table_name)
    items = []
    kwargs = {"KeyConditionExpression": Key("conversation_id").eq(conversation_id)}
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" in resp:
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        else:
            break
    if not items:
        return
    with table.batch_writer() as writer:
        for item in items:
            key = {"conversation_id": conversation_id}
            if "uuid" in item:
                key["uuid"] = item["uuid"]
            writer.delete_item(Key=key)


def load_artifacts(conversation_id):
    """Return the previously generated artifacts, keyed by artifact name."""
    if not BUCKET:
        return {}
    prefix = f"conversations/{conversation_id}/artifacts/"
    out = {}
    for obj in _s3_resource.Bucket(BUCKET).objects.filter(Prefix=prefix):
        if not obj.key.endswith(".json"):
            continue
        try:
            data = json.loads(_s3.get_object(Bucket=BUCKET, Key=obj.key)["Body"].read())
            name = data.get("artifact") or obj.key.rsplit("/", 1)[-1][:-5]
            out[name] = data
        except Exception:  # noqa: BLE001
            continue
    return out


def public_template_url(key):
    """Path-style S3 URL used as the CloudFormation ``templateURL`` for launch."""
    return f"https://s3.{REGION}.amazonaws.com/{BUCKET}/{key}"


def presign(key, expires=3600):
    return _s3.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=expires
    )


# --------------------------------------------------------------------------- #
# Async jobs (long-running chat/generate handled off the API request path)
# --------------------------------------------------------------------------- #
def create_job(job_id):
    _dynamodb.Table(JOBS_TABLE).put_item(
        Item={"job_id": job_id, "status": "pending", "ttl": int(time.time()) + 3600}
    )


def put_job_input(job_id, body):
    """Stash the job's request body in S3 so the async worker invocation only
    needs to carry the job id (async Event payloads are capped at ~256KB, and an
    attached image easily exceeds that)."""
    _s3.put_object(
        Body=json.dumps(body).encode("utf-8"),
        Bucket=BUCKET,
        Key=f"_jobs/{job_id}.input.json",
        ContentType="application/json",
    )


def get_job_input(job_id):
    obj = _s3.get_object(Bucket=BUCKET, Key=f"_jobs/{job_id}.input.json")
    return json.loads(obj["Body"].read())


def delete_job_input(job_id):
    try:
        _s3.delete_object(Bucket=BUCKET, Key=f"_jobs/{job_id}.input.json")
    except Exception:  # noqa: BLE001
        pass


def finish_job(job_id, result):
    key = f"_jobs/{job_id}.json"
    _s3.put_object(
        Body=json.dumps(result).encode("utf-8"),
        Bucket=BUCKET,
        Key=key,
        ContentType="application/json",
    )
    _dynamodb.Table(JOBS_TABLE).update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, result_key = :k",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "done", ":k": key},
    )


def fail_job(job_id, error):
    _dynamodb.Table(JOBS_TABLE).update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, error_msg = :e",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "error", ":e": str(error)[:1500]},
    )


def update_partial(job_id, text):
    """Persist the latest partial output for a running job (for live streaming)."""
    try:
        _s3.put_object(
            Body=text.encode("utf-8"),
            Bucket=BUCKET,
            Key=f"_jobs/{job_id}.partial.txt",
            ContentType="text/plain",
        )
    except Exception:  # noqa: BLE001 - streaming progress is best-effort
        pass


def get_job(job_id):
    item = _dynamodb.Table(JOBS_TABLE).get_item(Key={"job_id": job_id}).get("Item")
    if not item:
        return None
    status = item.get("status")
    out = {"status": status}
    if status == "done" and item.get("result_key"):
        obj = _s3.get_object(Bucket=BUCKET, Key=item["result_key"])
        out["result"] = json.loads(obj["Body"].read())
    elif status == "error":
        out["error"] = item.get("error_msg", "Generation failed")
    elif status == "pending":
        try:
            obj = _s3.get_object(Bucket=BUCKET, Key=f"_jobs/{job_id}.partial.txt")
            out["partial"] = obj["Body"].read().decode("utf-8")
        except Exception:  # noqa: BLE001 - no partial yet
            pass
    return out


def bundle_artifacts(conversation_id):
    """Zip every artifact for a conversation, upload it, and return a presigned URL."""
    if not BUCKET:
        return None
    tmpdir = tempfile.mkdtemp()
    local_dir = Path(tmpdir) / conversation_id
    local_dir.mkdir(parents=True, exist_ok=True)

    bucket = _s3_resource.Bucket(BUCKET)
    for obj in bucket.objects.filter(Prefix=f"{conversation_id}/"):
        if obj.key.endswith("/") or obj.key.endswith(".zip"):
            continue
        out = local_dir / obj.key.split("/")[-1]
        bucket.download_file(obj.key, str(out))

    zip_name = f"devgenius-{conversation_id}.zip"
    zip_path = Path(tmpdir) / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in glob.glob(str(local_dir / "*")):
            zf.write(f, arcname=os.path.basename(f))

    key = f"{conversation_id}/{zip_name}"
    _s3.upload_file(str(zip_path), BUCKET, key)
    url = presign(key)
    update_session(conversation_id, url)
    return url
