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
                }
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
        "is_deduplicated_by": False,
        "created_at": "2026-07-27T10:17:31Z",
    }


@pytest.fixture(scope="session")
def consumer_status_payload() -> dict:
    return {
        "id": "6c8f95a1-8e4b-4d59-9f3c-2b7f0e6a3003",
        "tenant_id": TENANT_ID,
        "message_id": MESSAGE_ID,
        "mailbox_id": MAILBOX_ID,
        "consumer_name": "odoo-prod",
        "consumer_type": "odoo-email-bridge",
        "status": "imported",
        "backlinks": [
            {
                "url": "https://odoo.example.com/odoo/invoices/42",
                "title": "Invoice INV/2026/0042",
                "status": "imported",
            },
            {"url": "https://odoo.example.com/odoo/contacts/7", "status": "related"},
        ],
        "created_by_user_id": "9d1e4b6f-7a25-49c8-8d3b-5e0c7f2a1004",
        "created_at": "2026-07-27T10:20:00Z",
    }


@pytest.fixture(scope="session")
def error_payload() -> dict:
    return {"code": "NOT_FOUND", "message": "message not found"}
