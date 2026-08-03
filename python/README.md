# email_bridge_client

Python client for the E-Mail-Bridge (AI Documents Ingestion) REST API — built
for external message consumers such as an Odoo 17 addon: receive the webhook,
fetch the parsed e-mail and its attachments, report the import outcome.

- Python ≥ 3.10, single runtime dependency: `requests`.
- Covers the simplified `/messages/{messageId}` endpoint family plus
  `consumer_status`; see `spec/business-document-api.yaml` (the vendored
  OpenAPI spec this release is verified against — `SPEC_VERSION`).
- Since spec 0.13.0 the `data` payload of JSON parsed-document records is the
  canonical **BusinessDocument** schema (EN 16931);
  `ParsedDocument.business_document()` returns the typed view with monetary
  amounts as `decimal.Decimal`. Check `document_source`: `xml-*` documents
  are faithful XML parses, `llm-*` documents are best-effort extractions —
  apply your own validation before booking. A paid invoice carries the
  deterministic `[PAID]` suffix on `payment_terms` (`BusinessDocument.is_paid`).
- Since spec 0.14.0 messages carry **thread fields** (`thread_id` groups a
  conversation; `message_id_hdr`/`in_reply_to`/`references` for own
  correlation), `client.list_thread(uuid)` returns all members of a
  conversation, and the public **discovery endpoint** provides the OAuth
  client configuration (`fetch_client_config`, see below).

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
    for record in client.list_parsed_documents(uuid):
        invoice = record.business_document()      # typed EN 16931 view, None for binary
        if invoice is not None:
            total = invoice.legal_monetary_total.payable_amount  # decimal.Decimal
    for attachment in client.list_attachments(uuid):
        content = client.download_attachment(uuid, attachment.id)
        save(content.filename, content.content)
    client.report_status(uuid, "imported", consumer_name="odoo-prod")
```

`token` is a personal access token of a service account with role
`mailbox_user`. All errors derive from `IngestionClientError`
(`ApiError` with `status_code`/`body`, or `TransportError`).

### E-mail threads

A reply usually quotes the whole prior conversation. Use the thread fields to
avoid importing the same content once per reply — e.g. import the newest
member and mark the older ones `related`:

```python
message = client.get_message(uuid)
if message.is_thread:
    members = client.list_thread(uuid)            # oldest first, all mailboxes of the tenant
    newest = members[-1]
    if message.id != newest.id:
        client.report_status(uuid, "related", consumer_name="odoo-prod",
                             backlinks=[...])     # link to the record of the thread root
```

### Discovering the OAuth client configuration

The server publishes the values needed to obtain API tokens (token endpoint,
grant type, audience, the exact scope string) on a **public** endpoint — no
token required, ideal for bootstrap/self-configuration:

```python
from email_bridge_client import fetch_client_config

cfg = fetch_client_config("https://host/api/v1")
if cfg.is_remote:
    request_token(cfg.token_endpoint, grant_type=cfg.grant_type, scope=cfg.scope)
```

Use `cfg.scope` verbatim — it is composed server-side from the configured
audience (see the server repo's
`.features/.specs/odoo-client-config-discovery.md` for the recommended
caching / 401-self-healing behaviour in Odoo).

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
