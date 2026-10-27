"""HTTP contract pinned to PowerContext 31ecdd61beadb7ac8de5da20998dead9a9e07845.

No extraction/model calls: explicit Source capture and Atomic Memory remember only.
An unknown write outcome is deliberately not retried by this adapter.
"""
import hashlib
import json

import httpx


class ProtocolError(ValueError):
    pass


class PowerContext:
    def __init__(self, url, token, transport=None):
        self.client = httpx.Client(base_url=url.rstrip("/"), headers={"Authorization": f"Bearer {token}"} if token else {}, timeout=httpx.Timeout(8.0, connect=2.0), transport=transport)

    def post(self, path, body):
        response = self.client.post(path, json=body)
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as error:
            raise ProtocolError("PowerContext returned invalid JSON") from error
        if not isinstance(data, dict):
            raise ProtocolError("PowerContext response must be an object")
        return data

    def create_scope(self, user):
        key = "pawnshop-" + hashlib.sha256(user.encode()).hexdigest()
        data = self.post("/v1/scopes", {"title": "烦恼典当行 " + key[-12:], "summary": "pawnshop fictional item stories and explicitly reported player experiences", "idempotency_key": key})
        if not isinstance(data.get("scope_id"), str) or not data["scope_id"]:
            raise ProtocolError("missing scope_id")
        return data["scope_id"]

    def prepare(self, scope, query):
        data = self.post("/v1/context/prepare", {"scope_id": scope, "query": "pawnshop " + query, "max_bytes": 8000})
        if data.get("schema") != "powercontext.prepared-context.v1" or data.get("status") not in ("ready", "empty"):
            raise ProtocolError("unexpected PreparedContext schema/status")
        content = data.get("content")
        if data["status"] == "ready" and (not isinstance(content, str) or not content):
            raise ProtocolError("ready context has no content")
        return data["status"], content or ""

    def capture(self, scope, event_id, content):
        data = self.post("/v1/sources/content", {"scope_id": scope, "source_id": "pawnshop-" + event_id, "content": content, "metadata": {"integration": "pawnshop", "event_id": event_id}})
        source = data.get("source")
        if data.get("status") != "accepted" or not isinstance(source, dict) or source.get("name") != "content" or source.get("source_id") != "pawnshop-" + event_id or type(data.get("position")) is not int or data["position"] < 1:
            raise ProtocolError("missing or mismatched Source receipt")
        return data

    def remember(self, scope, text, source):
        # Legacy remember has no source_refs field. Embed the actual captured Source
        # citation in text and persist both service receipts in the local audit log.
        citation = json.dumps({"source": {"name": source["source"]["name"], "source_id": source["source"]["source_id"]}, "position": source["position"]}, ensure_ascii=False, separators=(",", ":"))
        data = self.post("/v1/memory/remember", {"scope_id": scope, "kind": "fact", "text": text + "\nSource audit citation: " + citation})
        records = data.get("records")
        if not isinstance(records, list) or not records:
            raise ProtocolError("remember returned no Atomic Memory records")
        refs = []
        for record in records:
            ref = record.get("artifact") if isinstance(record, dict) else None
            if not isinstance(ref, dict) or ref.get("family") != "atomic-memory" or not isinstance(ref.get("artifact_id"), str) or type(ref.get("revision")) is not int or ref["revision"] < 1:
                raise ProtocolError("invalid Atomic Memory reference")
            refs.append(ref)
        return refs, data
