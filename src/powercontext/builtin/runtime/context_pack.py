# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Prefix-reusing transport for prepared context bodies."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass

PACK_SCHEMA = "powercontext.context-pack.v1"
DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
DEFAULT_CHUNK_BYTES = 512

_PACK_FIELDS = frozenset({"schema", "items", "digest", "byte_count"})
_DELTA_FIELDS = frozenset({"schema", "base_digest", "target_digest", "prefix_items", "appended"})


class ContextPackError(Exception):
    """Report a Context Pack protocol or chunking violation."""


@dataclass(frozen=True, slots=True)
class ContextPack:
    """A complete context body as validated, transport-ready chunks."""

    items: tuple[bytes, ...]
    digest: str
    byte_count: int

    @classmethod
    def build(cls, items: tuple[bytes, ...], /) -> ContextPack:
        """Assemble a pack from already-chunked bytes."""

        normalized = tuple(_as_bytes(item) for item in items)
        digest = _digest_for(normalized)
        return cls(items=normalized, digest=digest, byte_count=_settled_byte_count(normalized, digest))

    @classmethod
    def from_content(cls, content: str, /, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> ContextPack:
        """Split a context body into deterministic chunks, each valid UTF-8."""

        if isinstance(chunk_bytes, bool) or not isinstance(chunk_bytes, int) or chunk_bytes < 1:
            raise ContextPackError("chunk_bytes must be a positive integer")
        return cls.build(_chunk(content.encode("utf-8"), chunk_bytes))

    def to_bytes(self) -> bytes:
        """Serialize this pack as the interoperable wire document."""

        return _serialize_pack(self.items, self.digest, self.byte_count)

    @classmethod
    def from_bytes(cls, raw: bytes, /) -> ContextPack:
        """Decode and fully verify a wire pack."""

        payload = _load_object(raw, _PACK_FIELDS, PACK_SCHEMA)
        items = _decode_items(payload["items"])
        digest = payload["digest"]
        if not isinstance(digest, str) or digest != _digest_for(items):
            raise ContextPackError("pack digest does not match its items")
        byte_count = payload["byte_count"]
        if type(byte_count) is not int or byte_count != len(raw):
            raise ContextPackError("pack byte_count does not match its encoding")
        return cls(items=items, digest=digest, byte_count=byte_count)


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """The suffix one receiver must append to a retained base prefix."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    @property
    def byte_count(self) -> int:
        """Return the exact wire size of this delta."""

        return len(self.to_bytes())

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack, /) -> ContextPackDelta:
        """Reuse the longest common chunk prefix and carry the target suffix."""

        shared = 0
        for left, right in zip(base.items, target.items, strict=False):
            if left != right:
                break
            shared += 1
        return cls(
            base_digest=base.digest,
            target_digest=target.digest,
            prefix_items=shared,
            appended=target.items[shared:],
        )

    def to_bytes(self) -> bytes:
        """Serialize this delta as the interoperable wire document."""

        return json.dumps(
            {
                "schema": DELTA_SCHEMA,
                "base_digest": self.base_digest,
                "target_digest": self.target_digest,
                "prefix_items": self.prefix_items,
                "appended": [_encode(item) for item in self.appended],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def from_bytes(cls, raw: bytes, /) -> ContextPackDelta:
        """Decode and verify a wire delta."""

        payload = _load_object(raw, _DELTA_FIELDS, DELTA_SCHEMA)
        base_digest = _as_digest(payload["base_digest"], "base_digest")
        target_digest = _as_digest(payload["target_digest"], "target_digest")
        prefix_items = payload["prefix_items"]
        if type(prefix_items) is not int or prefix_items < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")
        return cls(
            base_digest=base_digest,
            target_digest=target_digest,
            prefix_items=prefix_items,
            appended=_decode_items(payload["appended"]),
        )


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta, /) -> ContextPack:
    """Rebuild the target pack from a base pack and one delta."""

    if base.digest != delta.base_digest:
        raise ContextPackError("delta was produced against a different base pack")
    if delta.prefix_items > len(base.items):
        raise ContextPackError("prefix_items exceeds the base chunk count")
    target = ContextPack.build((*base.items[: delta.prefix_items], *delta.appended))
    if target.digest != delta.target_digest:
        raise ContextPackError("rebuilt pack does not match the delta target digest")
    return target


def _chunk(encoded: bytes, chunk_bytes: int) -> tuple[bytes, ...]:
    chunks: list[bytes] = []
    start = 0
    while start < len(encoded):
        end = min(start + chunk_bytes, len(encoded))
        while end > start and end < len(encoded) and encoded[end] & 0xC0 == 0x80:
            end -= 1
        if end == start:
            raise ContextPackError("chunk_bytes cannot hold one UTF-8 character")
        try:
            encoded[start:end].decode("utf-8")
        except UnicodeDecodeError as error:  # pragma: no cover - guarded by the boundary scan
            raise ContextPackError("chunk boundaries must split valid UTF-8") from error
        chunks.append(encoded[start:end])
        start = end
    return tuple(chunks)


def _digest_for(items: tuple[bytes, ...]) -> str:
    canonical = json.dumps(
        {"schema": PACK_SCHEMA, "items": [_encode(item) for item in items]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _serialize_pack(items: tuple[bytes, ...], digest: str, byte_count: int) -> bytes:
    return json.dumps(
        {
            "schema": PACK_SCHEMA,
            "items": [_encode(item) for item in items],
            "digest": digest,
            "byte_count": byte_count,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _settled_byte_count(items: tuple[bytes, ...], digest: str) -> int:
    """Find the byte_count that also counts its own decimal digits."""

    byte_count = 0
    for _ in range(8):
        length = len(_serialize_pack(items, digest, byte_count))
        if length == byte_count:
            return byte_count
        byte_count = length
    raise ContextPackError("pack byte_count did not settle")


def _encode(item: bytes) -> str:
    return base64.b64encode(item).decode("ascii")


def _as_bytes(item: object) -> bytes:
    if not isinstance(item, bytes):
        raise ContextPackError("pack items must be bytes")
    return item


def _decode_items(value: object) -> tuple[bytes, ...]:
    if not isinstance(value, list):
        raise ContextPackError("pack items must be a list")
    items: list[bytes] = []
    for entry in value:
        if not isinstance(entry, str):
            raise ContextPackError("pack items must be Base64 strings")
        try:
            items.append(base64.b64decode(entry.encode("ascii"), validate=True))
        except (binascii.Error, UnicodeEncodeError) as error:
            raise ContextPackError("pack items must be valid Base64") from error
    return tuple(items)


def _as_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        raise ContextPackError(f"{field} must be a sha256 digest")
    return value


def _load_object(raw: bytes, fields: frozenset[str], schema: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContextPackError("wire payload must be UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ContextPackError("wire payload must be a JSON object")
    if set(payload) != fields:
        raise ContextPackError("wire payload fields do not match the schema")
    if payload.get("schema") != schema:
        raise ContextPackError("wire payload schema is not supported")
    return payload


__all__ = [
    "DEFAULT_CHUNK_BYTES",
    "DELTA_SCHEMA",
    "PACK_SCHEMA",
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]