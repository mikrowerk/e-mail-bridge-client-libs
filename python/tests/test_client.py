from __future__ import annotations

import pytest
import requests
import responses
from conftest import BASE_URL, MESSAGE_ID, TOKEN

from email_bridge_client import (
    ApiError,
    AuthenticationError,
    ForbiddenError,
    IngestionClient,
    NotFoundError,
    ServerError,
    TransportError,
)

MSG_URL = f"{BASE_URL}/messages/{MESSAGE_ID}"


class TestRequestBasics:
    @responses.activate
    def test_sends_bearer_token(self, client: IngestionClient, message_detail_payload: dict):
        responses.get(MSG_URL, json=message_detail_payload)
        client.get_message(MESSAGE_ID)
        assert responses.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"

    def test_repr_masks_token(self, client: IngestionClient):
        assert TOKEN not in repr(client)

    def test_retry_adapter_configured_for_gets_only(self, client: IngestionClient):
        retry = client._session.get_adapter(BASE_URL).max_retries
        assert retry.total == 3
        assert retry.allowed_methods == frozenset({"GET"})
        assert 429 in retry.status_forcelist and 503 in retry.status_forcelist

    def test_injected_session_is_not_closed(self, message_detail_payload: dict):
        session = requests.Session()
        with IngestionClient(BASE_URL, TOKEN, session=session):
            pass
        # Session still usable after the client is closed.
        assert session.adapters

    @responses.activate
    def test_connection_error_raises_transport_error(self, client: IngestionClient):
        responses.get(MSG_URL, body=requests.ConnectionError("boom"))
        with pytest.raises(TransportError):
            client.get_message(MESSAGE_ID)

    @responses.activate
    def test_message_id_is_path_quoted(self, client: IngestionClient):
        responses.get(f"{BASE_URL}/messages/..%2Fadmin", json={}, status=404)
        with pytest.raises(NotFoundError):
            client.get_message("../admin")


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("status", "exc"),
        [
            (400, ApiError),
            (401, AuthenticationError),
            (403, ForbiddenError),
            (404, NotFoundError),
            (500, ServerError),
            (503, ServerError),
        ],
    )
    @responses.activate
    def test_status_to_exception(
        self, client: IngestionClient, error_payload: dict, status: int, exc: type
    ):
        responses.get(MSG_URL, json=error_payload, status=status)
        with pytest.raises(exc) as excinfo:
            client.get_message(MESSAGE_ID)
        assert excinfo.value.status_code == status
        assert excinfo.value.body == error_payload
        assert "message not found" in str(excinfo.value)

    @responses.activate
    def test_non_json_error_body(self, client: IngestionClient):
        responses.get(MSG_URL, body="plain text failure", status=500)
        with pytest.raises(ServerError) as excinfo:
            client.get_message(MESSAGE_ID)
        assert excinfo.value.body == "plain text failure"


class TestEndpoints:
    @responses.activate
    def test_get_message(self, client: IngestionClient, message_detail_payload: dict):
        responses.get(MSG_URL, json=message_detail_payload)
        m = client.get_message(MESSAGE_ID)
        assert m.subject == "Invoice 2026-0815"

    @responses.activate
    def test_list_parsed_documents(self, client: IngestionClient, parsed_document_payload: dict):
        responses.get(f"{MSG_URL}/parsed-documents", json=[parsed_document_payload])
        docs = client.list_parsed_documents(MESSAGE_ID)
        assert len(docs) == 1 and docs[0].id == 42

    @responses.activate
    def test_get_parsed_document(self, client: IngestionClient, parsed_document_payload: dict):
        responses.get(f"{MSG_URL}/parsed-documents/42", json=parsed_document_payload)
        assert client.get_parsed_document(MESSAGE_ID, 42).document_type == "invoice"

    @responses.activate
    def test_list_attachments(self, client: IngestionClient, attachment_payload: dict):
        responses.get(f"{MSG_URL}/attachments", json=[attachment_payload])
        atts = client.list_attachments(MESSAGE_ID)
        assert len(atts) == 1 and atts[0].id == 7

    @responses.activate
    def test_get_attachment(self, client: IngestionClient, attachment_payload: dict):
        responses.get(f"{MSG_URL}/attachments/7", json=attachment_payload)
        assert client.get_attachment(MESSAGE_ID, 7).filename == "invoice.pdf"

    @responses.activate
    def test_download_attachment(self, client: IngestionClient):
        responses.get(
            f"{MSG_URL}/attachments/7/content",
            body=b"%PDF-1.7 fake",
            content_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="invoice.pdf"'},
        )
        content = client.download_attachment(MESSAGE_ID, 7)
        assert content.content == b"%PDF-1.7 fake"
        assert content.filename == "invoice.pdf"
        assert content.mime_type == "application/pdf"

    @responses.activate
    def test_download_attachment_without_disposition(self, client: IngestionClient):
        responses.get(
            f"{MSG_URL}/attachments/7/content",
            body=b"bytes",
            content_type="application/octet-stream",
        )
        content = client.download_attachment(MESSAGE_ID, 7)
        assert content.filename is None
        assert content.content == b"bytes"


class TestConsumerStatus:
    @responses.activate
    def test_report_status_posts_expected_body(
        self, client: IngestionClient, consumer_status_payload: dict
    ):
        rsp = responses.post(f"{MSG_URL}/consumer_status", json=consumer_status_payload, status=201)
        cs = client.report_status(MESSAGE_ID, "imported", consumer_name="odoo-prod")
        assert cs.status == "imported"
        assert rsp.calls[0].request.headers["Content-Type"] == "application/json"
        import json

        assert json.loads(rsp.calls[0].request.body) == {
            "consumer_name": "odoo-prod",
            "consumer_type": "odoo-email-bridge",
            "status": "imported",
        }

    def test_report_status_rejects_unknown_value(self, client: IngestionClient):
        with pytest.raises(ValueError):
            client.report_status(MESSAGE_ID, "pending", consumer_name="odoo-prod")

    @responses.activate
    def test_list_consumer_status(self, client: IngestionClient, consumer_status_payload: dict):
        responses.get(f"{MSG_URL}/consumer_status", json=[consumer_status_payload])
        items = client.list_consumer_status(MESSAGE_ID)
        assert len(items) == 1 and items[0].consumer_name == "odoo-prod"
