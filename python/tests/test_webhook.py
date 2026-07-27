from __future__ import annotations

import json

import pytest

from email_bridge_client import (
    InvalidWebhookPayload,
    is_test_mode,
    parse_webhook_payload,
    verify_bearer_token,
)

VALID_UUID = "01890a5d-ac96-774b-bcce-b302099a8057"


class TestParseWebhookPayload:
    @pytest.mark.parametrize(
        ("name", "body", "expected"),
        [
            ("single uuid", json.dumps({"uuids": [VALID_UUID]}), [VALID_UUID]),
            ("empty uuids (test ping)", json.dumps({"uuids": []}), []),
            ("bytes body", json.dumps({"uuids": [VALID_UUID]}).encode(), [VALID_UUID]),
            (
                "extra keys ignored",
                json.dumps({"uuids": [VALID_UUID], "future_field": 1}),
                [VALID_UUID],
            ),
        ],
    )
    def test_valid(self, name: str, body: bytes | str, expected: list[str]):
        assert parse_webhook_payload(body) == expected

    @pytest.mark.parametrize(
        ("name", "body"),
        [
            ("not json", "{nope"),
            ("not an object", json.dumps([VALID_UUID])),
            ("missing uuids", json.dumps({"ids": [VALID_UUID]})),
            ("uuids not a list", json.dumps({"uuids": VALID_UUID})),
            ("non-string entry", json.dumps({"uuids": [42]})),
            ("invalid uuid", json.dumps({"uuids": ["not-a-uuid"]})),
            ("invalid utf-8 bytes", b"\xff\xfe"),
        ],
    )
    def test_invalid(self, name: str, body: bytes | str):
        with pytest.raises(InvalidWebhookPayload):
            parse_webhook_payload(body)


class TestIsTestMode:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("mode=test", True),
            ("?mode=test", True),
            ("mode=test&x=1", True),
            ("mode=live", False),
            ("", False),
            (None, False),
            ({"mode": "test"}, True),
            ({"mode": ["test"]}, True),
            ({"mode": "live"}, False),
            ({}, False),
        ],
    )
    def test_cases(self, query, expected: bool):
        assert is_test_mode(query) is expected


class TestVerifyBearerToken:
    @pytest.mark.parametrize(
        ("header", "expected_token", "ok"),
        [
            ("Bearer s3cret", "s3cret", True),
            ("bearer s3cret", "s3cret", True),  # scheme is case-insensitive
            ("Bearer wrong", "s3cret", False),
            ("Basic s3cret", "s3cret", False),
            ("s3cret", "s3cret", False),  # missing scheme
            ("", "s3cret", False),
            (None, "s3cret", False),
            ("Bearer s3cret", "", False),  # empty expected token never matches
        ],
    )
    def test_cases(self, header, expected_token: str, ok: bool):
        assert verify_bearer_token(header, expected_token) is ok
