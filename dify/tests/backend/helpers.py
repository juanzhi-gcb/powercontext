import json

import httpx


class PowerContextHTTP:
    """Wire-level fixture: no fake adapter is injected into the game."""
    def __init__(self):
        self.requests = []
        self.memories = {}
        self.offline = False
        self.ambiguous = False
        self.write_entered = None
        self.write_release = None
        self.bad_source_receipt = False

    def __call__(self, request):
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        assert request.headers["authorization"] == "Bearer pc-test"
        if request.url.path == "/v1/scopes":
            return httpx.Response(201, json={"scope_id": body["idempotency_key"]})
        if request.url.path == "/v1/sources/content":
            return httpx.Response(202, json={"status": "accepted" if not self.bad_source_receipt else "rejected", "source": {"name": "content", "source_id": body["source_id"]}, "position": 1})
        if request.url.path == "/v1/memory/remember":
            if self.write_entered is not None:
                self.write_entered.set()
                assert self.write_release.wait(5), "test did not release write"
            self.memories.setdefault(body["scope_id"], []).append(body["text"])
            if self.ambiguous:
                raise httpx.ReadTimeout("response lost after write", request=request)
            return httpx.Response(200, json={"changed": True, "records": [{"artifact": {"family": "atomic-memory", "artifact_id": f"m{len(self.memories[body['scope_id']])}", "revision": 1}}]})
        if request.url.path == "/v1/context/prepare":
            # Emulate the pinned server's lexical admission floor: a memory is
            # returned only when the query carries terms that occur in it. The
            # shared "pawnshop" anchor alone is not enough evidence, so it is
            # excluded just like the server's admission math requires several
            # distinct query terms.
            tokens = [token for token in body["query"].split() if token != "pawnshop"]
            admitted = [text for text in self.memories.get(body["scope_id"], [])
                        if any(len(token) >= 5 and token in text for token in tokens)]
            entries = [{"citation": {"artifact_ref": {"family": "atomic-memory",
                        "artifact_id": f"m{index + 1}", "revision": 1}}, "content": text}
                       for index, text in enumerate(admitted)]
            content = ("untrusted history\n\nBEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1\n"
                       + json.dumps({"trust": "untrusted_history", "items": entries}, ensure_ascii=False)
                       + "\nEND_POWERCONTEXT_PREPARED_CONTEXT_V1") if entries else ""
            assert body["query"].startswith("pawnshop ")
            return httpx.Response(200, json={"schema": "powercontext.prepared-context.v1", "status": "ready" if content else "empty", "content": content or None, "content_bytes": len(content.encode())})
        raise AssertionError(request.url.path)