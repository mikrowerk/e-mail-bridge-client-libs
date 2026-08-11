"""Contract tests: the fixtures used by the unit tests are validated against
the vendored OpenAPI spec (spec/business-document-api.yaml).

If the hand-written models drift from the spec — or the spec is updated
without adjusting the fixtures/models — these tests fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import BASE_URL, MESSAGE_ID
from openapi_core import OpenAPI
from openapi_core.testing import MockRequest, MockResponse

SPEC_PATH = Path(__file__).parent.parent / "spec" / "business-document-api.yaml"

# MockRequest joins host_url + path into the full URL that is matched against
# the spec's servers, so the /api/v1 prefix goes into the path.
HOST_URL = "https://api.test"
PREFIX = "/api/v1"
assert BASE_URL == HOST_URL + PREFIX


@pytest.fixture(scope="session")
def openapi() -> OpenAPI:
    spec = yaml.safe_load(SPEC_PATH.read_text())
    # The spec's server entry is a bare host ("localhost:8080/api/v1");
    # pin it to the test base URL so request/server matching works.
    spec["servers"] = [{"url": BASE_URL}]
    return OpenAPI.from_dict(spec)


def _get(path: str) -> MockRequest:
    return MockRequest(
        host_url=HOST_URL,
        method="GET",
        path=PREFIX + path,
        headers={"Authorization": "Bearer test-token"},
    )


def _json_response(payload: object, status: int = 200) -> MockResponse:
    return MockResponse(
        data=json.dumps(payload).encode(),
        status_code=status,
        content_type="application/json",
    )


class TestResponseContracts:
    def test_message_detail(self, openapi: OpenAPI, message_detail_payload: dict):
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}"),
            _json_response(message_detail_payload),
        )

    def test_parsed_document_list(self, openapi: OpenAPI, parsed_document_payload: dict):
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}/parsed-documents"),
            _json_response([parsed_document_payload]),
        )

    def test_parsed_document_single(self, openapi: OpenAPI, parsed_document_payload: dict):
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}/parsed-documents/42"),
            _json_response(parsed_document_payload),
        )

    def test_attachment_list(self, openapi: OpenAPI, attachment_payload: dict):
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}/attachments"),
            _json_response([attachment_payload]),
        )

    def test_attachment_single(self, openapi: OpenAPI, attachment_payload: dict):
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}/attachments/7"),
            _json_response(attachment_payload),
        )

    def test_attachment_content_download(self, openapi: OpenAPI):
        response = MockResponse(
            data=b"%PDF-1.7 fake",
            status_code=200,
            content_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="invoice.pdf"'},
        )
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}/attachments/7/content"),
            response,
        )

    def test_consumer_status_create(self, openapi: OpenAPI, consumer_status_payload: dict):
        request = MockRequest(
            host_url=HOST_URL,
            method="POST",
            path=f"{PREFIX}/messages/{MESSAGE_ID}/consumer_status",
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
            data=json.dumps(
                {
                    "consumer_name": "odoo-prod",
                    "consumer_type": "odoo-email-bridge",
                    "status": "imported",
                    "backlinks": [
                        {
                            "url": "https://odoo.example.com/odoo/invoices/42",
                            "title": "Invoice INV/2026/0042",
                            "status": "imported",
                        }
                    ],
                }
            ).encode(),
        )
        openapi.validate_request(request)
        openapi.validate_response(request, _json_response(consumer_status_payload, status=201))

    def test_consumer_status_list(self, openapi: OpenAPI, consumer_status_payload: dict):
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}/consumer_status"),
            _json_response([consumer_status_payload]),
        )

    def test_error_body(self, openapi: OpenAPI, error_payload: dict):
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}"),
            _json_response(error_payload, status=404),
        )

    def test_thread_list(self, openapi: OpenAPI, thread_payload: list[dict]):
        openapi.validate_response(
            _get(f"/messages/{MESSAGE_ID}/thread"),
            _json_response(thread_payload),
        )

    def test_client_config(self, openapi: OpenAPI, client_config_payload: dict):
        # The discovery endpoint is public (security: []) — no Authorization
        # header on the request.
        request = MockRequest(
            host_url=HOST_URL,
            method="GET",
            path=f"{PREFIX}/.well-known/client-config",
        )
        openapi.validate_request(request)
        openapi.validate_response(request, _json_response(client_config_payload))

    def test_client_config_local_jwt(self, openapi: OpenAPI):
        request = MockRequest(
            host_url=HOST_URL,
            method="GET",
            path=f"{PREFIX}/.well-known/client-config",
        )
        openapi.validate_response(request, _json_response({"auth_provider_type": "local_jwt"}))

    def test_tenants_self(self, openapi: OpenAPI, tenant_master_data_payload: dict):
        openapi.validate_response(
            _get("/tenants/self"),
            _json_response([tenant_master_data_payload]),
        )

    def test_tenants_self_without_address(
        self, openapi: OpenAPI, tenant_master_data_payload: dict
    ):
        payload = {k: v for k, v in tenant_master_data_payload.items() if k != "address"}
        openapi.validate_response(_get("/tenants/self"), _json_response([payload]))

    def test_tenants_self_empty_list(self, openapi: OpenAPI):
        openapi.validate_response(_get("/tenants/self"), _json_response([]))
