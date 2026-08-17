"""Shared fixtures.

The payload dicts here are used both by the unit tests (as mocked responses)
and by the contract tests (validated against spec/business-document-api.yaml)
— so any drift between the hand-written models and the spec fails CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from email_bridge_client import IngestionClient

BASE_URL = "https://api.test/api/v1"
TOKEN = "test-token"

MESSAGE_ID = "01890a5d-ac96-774b-bcce-b302099a8057"
TENANT_ID = "3f9c68e2-14f0-4c1f-9d3e-6a1f6f11a001"
MAILBOX_ID = "b7a2f0c4-52d1-4c8e-8f0a-9c7e2d5b1002"
THREAD_ID = "01890a5d-0000-774b-bcce-b302099a8000"


@pytest.fixture
def client() -> IngestionClient:
    with IngestionClient(BASE_URL, TOKEN) as c:
        yield c


@pytest.fixture(scope="session")
def business_doc_data() -> dict:
    return json.loads((Path(__file__).parent / "business_doc_sample.json").read_text())


@pytest.fixture(scope="session")
def message_detail_payload() -> dict:
    return {
        "id": MESSAGE_ID,
        "external_msg_id": "imap-uid-4711",
        "tenant_id": TENANT_ID,
        "mailbox_id": MAILBOX_ID,
        "source": "imap",
        "received_at": "2026-07-27T10:15:00Z",
        "from": "supplier@example.com",
        "to": ["inbox@customer.example"],
        "cc": ["cc@customer.example"],
        "subject": "Invoice 2026-0815",
        "body_text": "Please find the invoice attached.",
        "pipeline_status": "processed",
        "is_forwarded": False,
        "attachment_count": 1,
        "is_thread": True,
        "thread_id": THREAD_ID,
        "message_id_hdr": "reply-1@supplier.example",
        "in_reply_to": "root@supplier.example",
        "references": ["root@supplier.example"],
        "provider_thread_id": "AAQkAGconv1",
        "parent_id": THREAD_ID,
        "classifications": [
            {
                "part": 0,
                "name": "invoice.pdf",
                "confidence": 0.97,
                "document_type": "invoice",
                "summary": "Invoice for office supplies.",
            }
        ],
        "attachments": [
            {
                "filename": "invoice.pdf",
                "mime_type": "application/pdf",
                "content_disposition": "attachment",
                "storage_key": "local://t1/msg/invoice.pdf",
            }
        ],
        "stage_result": {
            "classification": {
                "document_types": ["invoice"],
                "contact_type": "supplier",
                "confidence": 0.97,
                "short_summary": "Invoice from a supplier.",
                "stage_metadata": {
                    "parser": "llm-classifier",
                    "completed_at": "2026-07-27T10:16:02Z",
                    "duration_seconds": 3.2,
                    "llm_model_name": "claude-sonnet-5",
                    "llm_input_tokens": 1200,
                    "llm_output_tokens": 80,
                    "llm_inference_time_ms": 900,
                },
            },
            "documents": [
                {
                    "attachment_id": 7,
                    "attachment_name": "invoice.pdf",
                    "document_type_code": "380",
                    "document_type_name": "Invoice",
                    "document_date": "2026-07-20",
                    "document_number": "2026-0815",
                    "summary": "Invoice for office supplies.",
                },
                # Dedup placeholder (spec 0.15.0): attachment skipped in
                # favor of the canonical attachment at position 0.
                {
                    "attachment_id": 8,
                    "attachment_name": "invoice-copy.pdf",
                    "deduplicated_by_index": 0,
                    "deduplicated_by_name": "invoice.pdf",
                    "deduplicated_by_attachment_id": 7,
                },
            ],
        },
    }


@pytest.fixture(scope="session")
def attachment_payload() -> dict:
    return {
        "id": 7,
        "message_id": MESSAGE_ID,
        "position": 0,
        "filename": "invoice.pdf",
        "mime_type": "application/pdf",
        "content_disposition": "attachment",
        "storage_key": "local://t1/msg/invoice.pdf",
    }


@pytest.fixture(scope="session")
def parsed_document_payload(business_doc_data: dict) -> dict:
    return {
        "id": 42,
        "message_id": MESSAGE_ID,
        "attachment_index": 0,
        "attachment_name": "invoice.pdf",
        "document_type": "invoice",
        "data_type": "json",
        "data": business_doc_data,
        "stage_parser": "parser/businessdocument/llmpdf/anthropic/claude-sonnet-4-6",
        "stage_completed_at": "2026-07-27T10:17:30Z",
        "stage_duration_s": 12.5,
        "llm_model_name": "claude-sonnet-5",
        "llm_input_tokens": 5000,
        "llm_output_tokens": 900,
        "llm_inference_time_ms": 8000,
        "is_fully_parsed": True,
        "created_at": "2026-07-27T10:17:31Z",
    }


EXTERNAL_UUID = "b7f0d1c2-4a5e-7f60-8123-456789abcdef"


@pytest.fixture(scope="session")
def connected_system_status_payload() -> dict:
    return {
        "id": "6c8f95a1-8e4b-4d59-9f3c-2b7f0e6a3003",
        "tenant_id": TENANT_ID,
        "message_id": MESSAGE_ID,
        "mailbox_id": MAILBOX_ID,
        "connected_system_id": "01890a5c-0000-7000-8000-00805f9b34fb",
        "external_uuid": EXTERNAL_UUID,
        "connected_system_name": "Odoo Prod",
        "status": "imported",
        "links": [
            {
                "path": "/odoo/invoices/42",
                "url": "https://odoo.example.com/odoo/invoices/42",
                "title": "Invoice INV/2026/0042",
                "kind": "created",
            },
            {
                "path": "/odoo/contacts/7",
                "url": "https://odoo.example.com/odoo/contacts/7",
                "title": "",
                "kind": "related",
            },
            {
                "path": "/odoo/mail/7",
                "url": "https://odoo.example.com/odoo/mail/7",
                "title": "Imported e-mail",
                "kind": "imported_message",
            },
        ],
        "created_by_user_id": "9d1e4b6f-7a25-49c8-8d3b-5e0c7f2a1004",
        "created_at": "2026-07-27T10:20:00Z",
    }


@pytest.fixture(scope="session")
def thread_payload() -> list[dict]:
    """Thread members (spec: MessageResponse[]), oldest first; the second
    entry is the message from ``message_detail_payload``."""
    return [
        {
            "id": THREAD_ID,
            "tenant_id": TENANT_ID,
            "mailbox_id": MAILBOX_ID,
            "source": "imap",
            "received_at": "2026-07-26T09:00:00Z",
            "from": "customer@example.com",
            "subject": "Request 2026-0815",
            "pipeline_status": "processed",
            "is_thread": True,
            "thread_id": THREAD_ID,
        },
        {
            "id": MESSAGE_ID,
            "tenant_id": TENANT_ID,
            "mailbox_id": MAILBOX_ID,
            "source": "imap",
            "received_at": "2026-07-27T10:15:00Z",
            "from": "supplier@example.com",
            "to": ["inbox@customer.example"],
            "subject": "Invoice 2026-0815",
            "pipeline_status": "processed",
            "attachment_count": 1,
            "is_thread": True,
            "thread_id": THREAD_ID,
        },
    ]


@pytest.fixture(scope="session")
def client_config_payload() -> dict:
    return {
        "auth_provider_type": "remote",
        "issuer": "https://auth.test",
        "token_endpoint": "https://auth.test/oauth/v2/token",
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "audience": "377549952068354051",
        "scope": (
            "openid urn:zitadel:iam:org:project:id:377549952068354051:aud "
            "urn:zitadel:iam:org:projects:roles"
        ),
    }


@pytest.fixture(scope="session")
def error_payload() -> dict:
    return {"code": "NOT_FOUND", "message": "message not found"}


@pytest.fixture(scope="session")
def tenant_master_data_payload() -> dict:
    return {
        "id": TENANT_ID,
        "name": "Gammadata Systeme und Software GmbH",
        "active": True,
        "address": {
            "id": "7d1f2a9c-3b44-4e0f-8a55-0c9e1d2b3f04",
            "tenant_id": TENANT_ID,
            "mailbox_id": None,
            "name": "Gammadata Systeme und Software GmbH",
            "street": "Geschwister-Scholl-Ring 17",
            "postal_code": "82110",
            "city": "Germering",
            "country": "DE",
            "vat_id": "DE128237446",
            "email": "email@gammadata.de",
            "phone": "",
            "created_at": "2026-08-10T09:00:00Z",
            "updated_at": "2026-08-10T09:00:00Z",
        },
    }


CONNECTED_SYSTEM_ID = "01890a5c-0000-7000-8000-00805f9b34fb"


@pytest.fixture(scope="session")
def connected_system_payload() -> dict:
    return {
        "id": CONNECTED_SYSTEM_ID,
        "tenant_id": TENANT_ID,
        "external_uuid": "b7f0d1c2-4a5e-7f60-8123-456789abcdef",
        "name": "Odoo Prod",
        "description": "Company ERP",
        "base_web_url": "https://odoo.example.com",
        "created_at": "2026-08-15T09:00:00Z",
        "updated_at": "2026-08-15T09:30:00Z",
    }
