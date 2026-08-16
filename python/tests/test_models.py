from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from email_bridge_client import (
    ClientConfig,
    ConnectedSystem,
    ConnectedSystemStatus,
    MessageDetail,
    MessageSummary,
    ParsedDocument,
    RecordLink,
    TenantMasterData,
)


class TestMessageDetail:
    def test_full_payload(self, message_detail_payload: dict):
        m = MessageDetail.from_dict(message_detail_payload)
        assert m.id == message_detail_payload["id"]
        assert m.from_ == "supplier@example.com"
        assert m.received_at == datetime(2026, 7, 27, 10, 15, tzinfo=timezone.utc)
        assert m.received_at.tzinfo is not None
        assert m.classifications[0].document_type == "invoice"
        assert m.attachments[0].filename == "invoice.pdf"
        assert m.stage_result.classification.stage_metadata.llm_input_tokens == 1200
        assert m.stage_result.documents[0].document_date == date(2026, 7, 20)
        assert m.stage_result.documents[0].document_type_code == "380"

    def test_stage_result_dedup_placeholder(self, message_detail_payload: dict):
        docs = MessageDetail.from_dict(message_detail_payload).stage_result.documents
        assert docs[0].is_duplicate is False
        assert docs[0].deduplicated_by_index is None
        dup = docs[1]
        assert dup.is_duplicate is True
        assert dup.deduplicated_by_index == 0
        assert dup.deduplicated_by_name == "invoice.pdf"
        assert dup.deduplicated_by_attachment_id == 7
        assert dup.document_type_code is None

    def test_thread_and_correlation_fields(self, message_detail_payload: dict):
        m = MessageDetail.from_dict(message_detail_payload)
        assert m.is_thread
        assert m.thread_id == message_detail_payload["thread_id"]
        assert m.parent_id == message_detail_payload["thread_id"]
        assert m.message_id_hdr == "reply-1@supplier.example"
        assert m.in_reply_to == "root@supplier.example"
        assert m.references == ["root@supplier.example"]
        assert m.provider_thread_id == "AAQkAGconv1"

    def test_minimal_payload_only_required_fields(self):
        m = MessageDetail.from_dict(
            {
                "id": "01890a5d-ac96-774b-bcce-b302099a8057",
                "tenant_id": "t",
                "mailbox_id": "m",
                "source": "imap",
                "received_at": "2026-07-27T10:15:00+02:00",
                "from": "a@b.c",
                "subject": "s",
                "pipeline_status": "stored",
            }
        )
        assert m.to == [] and m.cc == [] and m.attachments == []
        assert m.stage_result is None and m.deleted_at is None
        assert m.received_at.tzinfo is not None
        # Pre-0.14.0 servers: thread fields default to standalone semantics.
        assert m.is_thread is False and m.thread_id is None
        assert m.references == []

    def test_unknown_fields_ignored(self, message_detail_payload: dict):
        payload = {**message_detail_payload, "added_in_future_spec": {"x": 1}}
        m = MessageDetail.from_dict(payload)
        assert m.id == message_detail_payload["id"]


class TestParsedDocument:
    def test_json_data_stays_untyped(self, parsed_document_payload: dict):
        p = ParsedDocument.from_dict(parsed_document_payload)
        assert p.data_type == "json"
        assert isinstance(p.data, dict)
        assert p.data["document_type_code"] == "380"
        assert p.is_fully_parsed is True
        assert p.created_at.tzinfo is not None
        assert p.is_duplicate is False and p.deduplicated_by_index is None

    def test_dedup_placeholder(self):
        p = ParsedDocument.from_dict(
            {
                "id": 2,
                "message_id": "m",
                "attachment_index": 1,
                "attachment_name": "invoice-copy.pdf",
                "document_type": "invoice",
                "data_type": "binary",
                "is_fully_parsed": False,
                "deduplicated_by_index": 0,
                "deduplicated_by_name": "invoice.pdf",
                "created_at": "2026-07-27T10:17:30Z",
            }
        )
        assert p.is_duplicate is True
        assert p.deduplicated_by_index == 0
        assert p.deduplicated_by_name == "invoice.pdf"
        assert p.business_document() is None

    def test_business_document_typed_view(self, parsed_document_payload: dict):
        doc = ParsedDocument.from_dict(parsed_document_payload).business_document()
        assert doc is not None
        assert doc.document_source == "llm-pdf"
        assert doc.document_type_code == "380"
        assert doc.id == "RE-2026-100"
        assert doc.buyer_reference == "04011000-12345-67"
        assert doc.additional_document_ref == "BEST-77"
        assert doc.issue_date.tzinfo is not None
        assert doc.accounting_supplier_party.name == "ACME GmbH"
        assert doc.accounting_supplier_party.company_registration_id == "HRB 12345"
        assert doc.accounting_customer_party.vat_id == "DE987654321"

        line = doc.business_document_lines[0]
        assert line.item_name == "Consulting Basic"
        assert line.sellers_item_identification == "ART-77"
        assert line.invoiced_quantity == Decimal(8)
        assert line.price.item_net_price == Decimal(150)
        assert line.classified_tax_category.id == "S"
        assert line.classified_tax_category.percent == Decimal(19)
        assert line.vat_amount == Decimal(228)

        total = doc.legal_monetary_total
        assert total.tax_exclusive_amount == Decimal(1100)
        assert total.tax_inclusive_amount == Decimal(1428)
        assert total.payable_amount == Decimal(1428)
        assert total.document_currency_code == "EUR"
        assert total.tax_subtotal[0].tax_amount == Decimal(228)
        assert total.tax_subtotal[0].tax_category_id is None

        assert doc.payment_means[0].payee_financial_account == "DE44500105175407324931"
        assert doc.is_paid is True

    def test_business_document_none_for_binary(self):
        p = ParsedDocument.from_dict(
            {
                "id": 1,
                "message_id": "m",
                "attachment_index": 0,
                "document_type": "invoice",
                "data_type": "binary",
                "is_fully_parsed": False,
                "created_at": "2026-07-27T10:17:30Z",
            }
        )
        assert p.business_document() is None

    def test_business_document_unpaid(self, business_doc_data: dict):
        data = dict(business_doc_data, payment_terms="30 days net")
        p = ParsedDocument.from_dict(
            {
                "id": 1,
                "message_id": "m",
                "attachment_index": 0,
                "document_type": "invoice",
                "data_type": "json",
                "is_fully_parsed": True,
                "created_at": "2026-07-27T10:17:30Z",
                "data": data,
            }
        )
        assert p.business_document().is_paid is False

    def test_minimal(self):
        p = ParsedDocument.from_dict(
            {
                "id": 1,
                "message_id": "m",
                "attachment_index": -1,
                "document_type": "other",
                "data_type": "json",
                "is_fully_parsed": False,
                "created_at": "2026-07-27T10:17:31Z",
            }
        )
        assert p.data is None and p.attachment_index == -1


class TestConnectedSystemStatus:
    def test_from_dict(self, connected_system_status_payload: dict):
        cs = ConnectedSystemStatus.from_dict(connected_system_status_payload)
        assert cs.status == "imported"
        assert cs.connected_system_name == "Odoo Prod"
        assert cs.external_uuid == connected_system_status_payload["external_uuid"]
        assert cs.created_at.tzinfo is not None
        assert cs.links == (
            RecordLink(
                url="https://odoo.example.com/odoo/invoices/42",
                kind="created",
                title="Invoice INV/2026/0042",
                path="/odoo/invoices/42",
            ),
            RecordLink(
                url="https://odoo.example.com/odoo/contacts/7",
                kind="related",
                title=None,
                path="/odoo/contacts/7",
            ),
        )

    def test_from_dict_without_links(self, connected_system_status_payload: dict):
        payload = {k: v for k, v in connected_system_status_payload.items() if k != "links"}
        cs = ConnectedSystemStatus.from_dict(payload)
        assert cs.links == ()


class TestRecordLink:
    def test_to_dict_omits_absent_title_and_path(self):
        assert RecordLink(url="https://x/1", kind="related").to_dict() == {
            "url": "https://x/1",
            "kind": "related",
        }
        assert RecordLink(url="https://x/1", kind="created", title="Rec").to_dict() == {
            "url": "https://x/1",
            "kind": "created",
            "title": "Rec",
        }


class TestMessageSummary:
    def test_thread_member(self, thread_payload: list[dict]):
        root = MessageSummary.from_dict(thread_payload[0])
        assert root.is_thread and root.thread_id == root.id
        assert root.received_at.tzinfo is not None

    def test_minimal_without_thread_fields(self):
        m = MessageSummary.from_dict(
            {
                "id": "x",
                "tenant_id": "t",
                "mailbox_id": "m",
                "source": "gmail",
                "received_at": "2026-07-27T10:15:00Z",
                "from": "a@b.c",
                "subject": "s",
                "pipeline_status": "stored",
            }
        )
        assert m.is_thread is False and m.thread_id is None


class TestClientConfig:
    def test_remote(self, client_config_payload: dict):
        cfg = ClientConfig.from_dict(client_config_payload)
        assert cfg.is_remote
        assert cfg.grant_type == "urn:ietf:params:oauth:grant-type:jwt-bearer"
        assert cfg.audience in cfg.scope

    def test_local_jwt_reduction(self):
        cfg = ClientConfig.from_dict({"auth_provider_type": "local_jwt"})
        assert not cfg.is_remote
        assert cfg.issuer is None and cfg.scope is None and cfg.audience is None


class TestTenantMasterData:
    def test_with_address(self, tenant_master_data_payload: dict):
        t = TenantMasterData.from_dict(tenant_master_data_payload)
        assert t.id == tenant_master_data_payload["id"]
        assert t.name == "Gammadata Systeme und Software GmbH"
        assert t.active
        assert t.address is not None
        assert t.address.tenant_id == t.id
        assert t.address.mailbox_id is None
        assert t.address.vat_id == "DE128237446"
        assert t.address.country == "DE"
        assert t.address.created_at == datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)

    def test_without_address(self, tenant_master_data_payload: dict):
        payload = {**tenant_master_data_payload, "address": None}
        t = TenantMasterData.from_dict(payload)
        assert t.address is None

    def test_address_key_absent(self, tenant_master_data_payload: dict):
        payload = {k: v for k, v in tenant_master_data_payload.items() if k != "address"}
        t = TenantMasterData.from_dict(payload)
        assert t.address is None

    def test_unknown_fields_ignored(self, tenant_master_data_payload: dict):
        payload = {**tenant_master_data_payload, "future_field": 42}
        t = TenantMasterData.from_dict(payload)
        assert t.name == "Gammadata Systeme und Software GmbH"


class TestConnectedSystem:
    def test_from_dict_full(self, connected_system_payload: dict):
        cs = ConnectedSystem.from_dict(connected_system_payload)
        assert cs.id == connected_system_payload["id"]
        assert cs.tenant_id == connected_system_payload["tenant_id"]
        assert cs.external_uuid == connected_system_payload["external_uuid"]
        assert cs.name == "Odoo Prod"
        assert cs.description == "Company ERP"
        assert cs.base_web_url == "https://odoo.example.com"
        assert cs.created_at is not None and cs.created_at.tzinfo is not None
        assert cs.updated_at is not None

    def test_from_dict_defaults(self, connected_system_payload: dict):
        payload = {
            k: v
            for k, v in connected_system_payload.items()
            if k not in ("description", "created_at", "updated_at")
        }
        cs = ConnectedSystem.from_dict(payload)
        assert cs.description == ""
        assert cs.created_at is None
        assert cs.updated_at is None
