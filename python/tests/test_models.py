from __future__ import annotations

from datetime import date, datetime, timezone

from email_bridge_client import Backlink, ConsumerStatus, MessageDetail, ParsedDocument


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

    def test_unknown_fields_ignored(self, message_detail_payload: dict):
        payload = {**message_detail_payload, "added_in_future_spec": {"x": 1}}
        m = MessageDetail.from_dict(payload)
        assert m.id == message_detail_payload["id"]


class TestParsedDocument:
    def test_json_data_stays_untyped(self, parsed_document_payload: dict):
        p = ParsedDocument.from_dict(parsed_document_payload)
        assert p.data_type == "json"
        assert isinstance(p.data, dict)
        assert p.data["document_type_code"] == "string"
        assert p.is_fully_parsed is True
        assert p.created_at.tzinfo is not None

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


class TestConsumerStatus:
    def test_from_dict(self, consumer_status_payload: dict):
        cs = ConsumerStatus.from_dict(consumer_status_payload)
        assert cs.status == "imported"
        assert cs.consumer_type == "odoo-email-bridge"
        assert cs.created_at.tzinfo is not None
        assert cs.backlinks == (
            Backlink(
                url="https://odoo.example.com/odoo/invoices/42",
                status="imported",
                title="Invoice INV/2026/0042",
            ),
            Backlink(url="https://odoo.example.com/odoo/contacts/7", status="related"),
        )

    def test_from_dict_without_backlinks(self, consumer_status_payload: dict):
        payload = {k: v for k, v in consumer_status_payload.items() if k != "backlinks"}
        cs = ConsumerStatus.from_dict(payload)
        assert cs.backlinks == ()


class TestBacklink:
    def test_to_dict_omits_absent_title(self):
        assert Backlink(url="https://x/1", status="related").to_dict() == {
            "url": "https://x/1",
            "status": "related",
        }
        assert Backlink(url="https://x/1", status="imported", title="Rec").to_dict() == {
            "url": "https://x/1",
            "status": "imported",
            "title": "Rec",
        }
