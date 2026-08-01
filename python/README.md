# email_bridge_client

Python client for the E-Mail-Bridge (AI Documents Ingestion) REST API — built
for external message consumers such as an Odoo 17 addon: receive the webhook,
fetch the parsed e-mail and its attachments, report the import outcome.

- Python ≥ 3.10, single runtime dependency: `requests`.
- Covers the simplified `/messages/{messageId}` endpoint family plus
  `consumer_status`; see `spec/business-document-api.yaml` (the vendored
  OpenAPI spec this release is verified against — `SPEC_VERSION`).

## Install

Until the package is published to PyPI, install from git:

```sh
pip install "git+https://<host>/<org>/e-mail-bridge-client-libs.git@<tag>#subdirectory=python"
```

## Usage

### Receiving the webhook

The dispatcher POSTs `{"uuids": ["<message-uuid>", ...]}` (up to 50 per
batch) and sends validation pings as `?mode=test` with an empty array.
Acknowledge fast (2xx), persist the UUIDs, process asynchronously.

```python
from email_bridge_client import parse_webhook_payload, is_test_mode, verify_bearer_token

def handle_webhook(request):  # framework-agnostic sketch
    if not verify_bearer_token(request.headers.get("Authorization"), SHARED_TOKEN):
        return 401
    uuids = parse_webhook_payload(request.body)   # raises InvalidWebhookPayload
    if is_test_mode(request.query_string):
        return 200                                # validation ping
    queue_for_import(uuids)                       # idempotent: unique constraint on uuid
    return 200
```

### Fetching and reporting (async worker)

```python
from email_bridge_client import IngestionClient

with IngestionClient("https://host/api/v1", token=PAT) as client:
    message = client.get_message(uuid)
    documents = client.list_parsed_documents(uuid)
    for attachment in client.list_attachments(uuid):
        content = client.download_attachment(uuid, attachment.id)
        save(content.filename, content.content)
    client.report_status(uuid, "imported", consumer_name="odoo-prod")
```

`token` is a personal access token of a service account with role
`mailbox_user`. All errors derive from `IngestionClientError`
(`ApiError` with `status_code`/`body`, or `TransportError`).

## Development

```sh
cd python
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check src tests
```

The contract tests in `tests/test_contract.py` validate the test fixtures
against the vendored OpenAPI spec; update `spec/business-document-api.yaml`
and `SPEC_VERSION` together, deliberately, per release.
