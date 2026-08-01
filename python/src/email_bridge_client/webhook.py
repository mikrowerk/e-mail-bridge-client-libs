"""Receiver-side helpers for the E-Mail-Bridge webhook.

Framework-free pure functions, usable from any HTTP receiver (Odoo
``http.Controller``, Flask, tests). The dispatcher POSTs
``{"uuids": ["<message-uuid>", ...]}`` (up to 50 per batch) and sends
validation pings as ``?mode=test`` with an empty ``uuids`` array; when the
Action is configured with bearer/JWT auth it adds
``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import hmac
import json
import uuid as uuidlib
from collections.abc import Mapping
from urllib.parse import parse_qs

from .exceptions import InvalidWebhookPayload


def parse_webhook_payload(body: bytes | str) -> list[str]:
    """Validate a webhook request body and return the message UUIDs.

    An empty list is a valid result (test ping). Raises
    :class:`InvalidWebhookPayload` for anything that is not a JSON object
    with a ``uuids`` array of UUID strings.
    """
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidWebhookPayload(f"body is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("uuids"), list):
        raise InvalidWebhookPayload('body must be a JSON object with a "uuids" array')
    uuids: list[str] = []
    for item in data["uuids"]:
        if not isinstance(item, str):
            raise InvalidWebhookPayload(f"uuids entries must be strings, got {type(item).__name__}")
        try:
            uuidlib.UUID(item)
        except ValueError as exc:
            raise InvalidWebhookPayload(f"invalid UUID {item!r}") from exc
        uuids.append(item)
    return uuids


def is_test_mode(query: str | Mapping[str, object] | None) -> bool:
    """Detect the dispatcher's validation ping (``?mode=test``).

    Accepts a raw query string (``"mode=test"``, with or without leading
    ``?``) or a parsed parameter mapping whose values may be strings or lists
    of strings (as produced by common web frameworks).
    """
    if query is None:
        return False
    if isinstance(query, str):
        values = parse_qs(query.lstrip("?")).get("mode", [])
        return "test" in values
    value = query.get("mode")
    if isinstance(value, (list, tuple)):
        return "test" in value
    return value == "test"


def verify_bearer_token(authorization_header: str | None, expected_token: str) -> bool:
    """Constant-time check of an ``Authorization: Bearer <token>`` header."""
    if not authorization_header or not expected_token:
        return False
    scheme, _, token = authorization_header.strip().partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    return hmac.compare_digest(token.strip().encode(), expected_token.encode())
