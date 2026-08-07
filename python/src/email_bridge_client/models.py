"""Typed models mirroring the API's response schemas.

Field names keep the API's snake_case (``from`` becomes ``from_`` because it
is a Python keyword). Unknown JSON fields are ignored for forward
compatibility with newer spec versions. Timestamps are parsed to
timezone-aware :class:`datetime.datetime`.

The spec source of truth is ``spec/business-document-api.yaml`` (validated by
the contract tests). Since spec 0.13.0 the ``ParsedDocument.data`` payload of
JSON records is the canonical :class:`BusinessDocument` schema (EN 16931) —
``ParsedDocument.data`` stays the raw ``dict`` and
:meth:`ParsedDocument.business_document` returns the typed view with monetary
amounts as :class:`decimal.Decimal`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    # Go emits RFC 3339; fromisoformat handles offsets and (3.11+) "Z".
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def _parse_decimal(value: Any) -> Decimal | None:
    """Parse a decimal amount; the API encodes decimals as JSON strings."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


@dataclass(frozen=True, slots=True)
class StageMetadataInfo:
    """Processing provenance for a single pipeline stage."""

    parser: str | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    llm_model_name: str | None = None
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    llm_inference_time_ms: int | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> StageMetadataInfo:
        return cls(
            parser=d.get("parser"),
            completed_at=_parse_datetime(d.get("completed_at")),
            duration_seconds=d.get("duration_seconds"),
            llm_model_name=d.get("llm_model_name"),
            llm_input_tokens=d.get("llm_input_tokens"),
            llm_output_tokens=d.get("llm_output_tokens"),
            llm_inference_time_ms=d.get("llm_inference_time_ms"),
        )


def _stage_metadata(d: Mapping[str, Any] | None) -> StageMetadataInfo | None:
    return StageMetadataInfo.from_dict(d) if d is not None else None


@dataclass(frozen=True, slots=True)
class ClassificationEntry:
    """Per-part classification (part -1 = email body)."""

    part: int
    confidence: float
    document_type: str
    name: str | None = None
    summary: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ClassificationEntry:
        return cls(
            part=d["part"],
            confidence=d["confidence"],
            document_type=d["document_type"],
            name=d.get("name"),
            summary=d.get("summary"),
        )


@dataclass(frozen=True, slots=True)
class AttachmentSummary:
    """Abbreviated attachment record embedded in a message detail."""

    filename: str
    mime_type: str
    content_disposition: str | None = None
    storage_key: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> AttachmentSummary:
        return cls(
            filename=d["filename"],
            mime_type=d["mime_type"],
            content_disposition=d.get("content_disposition"),
            storage_key=d.get("storage_key"),
        )


@dataclass(frozen=True, slots=True)
class StageResultClassification:
    """Classification section of the pipeline stage result."""

    document_types: list[str] = field(default_factory=list)
    contact_type: str | None = None
    confidence: float | None = None
    short_summary: str | None = None
    stage_metadata: StageMetadataInfo | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> StageResultClassification:
        return cls(
            document_types=list(d.get("document_types") or []),
            contact_type=d.get("contact_type"),
            confidence=d.get("confidence"),
            short_summary=d.get("short_summary"),
            stage_metadata=_stage_metadata(d.get("stage_metadata")),
        )


@dataclass(frozen=True, slots=True)
class StageResultDocument:
    """Parsed-document summary within the stage result.

    Entries with ``deduplicated_by_index`` set (spec 0.15.0) are placeholders
    for attachments that were skipped because a canonical duplicate (typically
    an XML equivalent of a PDF) was parsed instead. They carry no document
    payload fields and must not be imported as documents; an absent
    ``deduplicated_by_index`` means the entry is not a duplicate.
    """

    attachment_id: int | None = None
    attachment_name: str | None = None
    deduplicated_by_index: int | None = None
    deduplicated_by_name: str | None = None
    deduplicated_by_attachment_id: int | None = None
    document_type_code: str | None = None
    document_type_name: str | None = None
    document_date: date | None = None
    document_number: str | None = None
    summary: str | None = None
    stage_metadata: StageMetadataInfo | None = None

    @property
    def is_duplicate(self) -> bool:
        """True when this entry is a dedup placeholder, not a document."""
        return self.deduplicated_by_index is not None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> StageResultDocument:
        return cls(
            attachment_id=d.get("attachment_id"),
            attachment_name=d.get("attachment_name"),
            deduplicated_by_index=d.get("deduplicated_by_index"),
            deduplicated_by_name=d.get("deduplicated_by_name"),
            deduplicated_by_attachment_id=d.get("deduplicated_by_attachment_id"),
            document_type_code=d.get("document_type_code"),
            document_type_name=d.get("document_type_name"),
            document_date=_parse_date(d.get("document_date")),
            document_number=d.get("document_number"),
            summary=d.get("summary"),
            stage_metadata=_stage_metadata(d.get("stage_metadata")),
        )


@dataclass(frozen=True, slots=True)
class MessageStageResult:
    """Pipeline processing result returned alongside a message detail."""

    classification: StageResultClassification | None = None
    documents: list[StageResultDocument] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> MessageStageResult:
        classification = d.get("classification")
        return cls(
            classification=(
                StageResultClassification.from_dict(classification)
                if classification is not None
                else None
            ),
            documents=[StageResultDocument.from_dict(x) for x in d.get("documents") or []],
        )


@dataclass(frozen=True, slots=True)
class MessageSummary:
    """Abbreviated message record (spec: MessageResponse) as returned by list
    endpoints such as ``GET /messages/{messageId}/thread``.

    ``thread_id`` groups the messages of one conversation; it equals the id
    of the thread's root message, and a standalone message is a thread of
    size 1 (``thread_id == id``). ``is_thread`` is True when the message
    belongs to a thread with more than one ingested member (spec 0.14.0).
    """

    id: str
    tenant_id: str
    mailbox_id: str
    source: str
    received_at: datetime
    from_: str
    subject: str
    pipeline_status: str
    external_msg_id: str | None = None
    to: list[str] = field(default_factory=list)
    is_forwarded: bool = False
    original_from: str | None = None
    attachment_count: int = 0
    deleted_at: datetime | None = None
    classifications: list[ClassificationEntry] = field(default_factory=list)
    is_thread: bool = False
    thread_id: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> MessageSummary:
        return cls(
            id=d["id"],
            tenant_id=d["tenant_id"],
            mailbox_id=d["mailbox_id"],
            source=d["source"],
            received_at=_parse_datetime(d["received_at"]),
            from_=d["from"],
            subject=d["subject"],
            pipeline_status=d["pipeline_status"],
            external_msg_id=d.get("external_msg_id"),
            to=list(d.get("to") or []),
            is_forwarded=d.get("is_forwarded", False),
            original_from=d.get("original_from"),
            attachment_count=d.get("attachment_count", 0),
            deleted_at=_parse_datetime(d.get("deleted_at")),
            classifications=[
                ClassificationEntry.from_dict(x) for x in d.get("classifications") or []
            ],
            is_thread=d.get("is_thread", False),
            thread_id=d.get("thread_id"),
        )


@dataclass(frozen=True, slots=True)
class MessageDetail:
    """Full message detail (``GET /messages/{messageId}``).

    The thread/correlation fields (spec 0.14.0) let a consumer group
    messages by conversation (``thread_id``) or correlate them against its
    own mail archive via the RFC 5322 identifiers (``message_id_hdr``,
    ``in_reply_to``, ``references``).
    """

    id: str
    tenant_id: str
    mailbox_id: str
    source: str
    received_at: datetime
    from_: str
    subject: str
    pipeline_status: str
    external_msg_id: str | None = None
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    body_text: str | None = None
    body_html: str | None = None
    is_forwarded: bool = False
    original_from: str | None = None
    original_to: str | None = None
    forwarders: str | None = None
    attachment_count: int = 0
    deleted_at: datetime | None = None
    classifications: list[ClassificationEntry] = field(default_factory=list)
    attachments: list[AttachmentSummary] = field(default_factory=list)
    stage_result: MessageStageResult | None = None
    is_thread: bool = False
    thread_id: str | None = None
    message_id_hdr: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    provider_thread_id: str | None = None
    parent_id: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> MessageDetail:
        stage_result = d.get("stage_result")
        return cls(
            id=d["id"],
            tenant_id=d["tenant_id"],
            mailbox_id=d["mailbox_id"],
            source=d["source"],
            received_at=_parse_datetime(d["received_at"]),
            from_=d["from"],
            subject=d["subject"],
            pipeline_status=d["pipeline_status"],
            external_msg_id=d.get("external_msg_id"),
            to=list(d.get("to") or []),
            cc=list(d.get("cc") or []),
            body_text=d.get("body_text"),
            body_html=d.get("body_html"),
            is_forwarded=d.get("is_forwarded", False),
            original_from=d.get("original_from"),
            original_to=d.get("original_to"),
            forwarders=d.get("forwarders"),
            attachment_count=d.get("attachment_count", 0),
            deleted_at=_parse_datetime(d.get("deleted_at")),
            classifications=[
                ClassificationEntry.from_dict(x) for x in d.get("classifications") or []
            ],
            attachments=[AttachmentSummary.from_dict(x) for x in d.get("attachments") or []],
            stage_result=(
                MessageStageResult.from_dict(stage_result) if stage_result is not None else None
            ),
            is_thread=d.get("is_thread", False),
            thread_id=d.get("thread_id"),
            message_id_hdr=d.get("message_id_hdr"),
            in_reply_to=d.get("in_reply_to"),
            references=list(d.get("references") or []),
            provider_thread_id=d.get("provider_thread_id"),
            parent_id=d.get("parent_id"),
        )


@dataclass(frozen=True, slots=True)
class Attachment:
    """Full attachment metadata record."""

    id: int
    message_id: str
    position: int
    filename: str
    mime_type: str
    content_disposition: str | None = None
    storage_key: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Attachment:
        return cls(
            id=d["id"],
            message_id=d["message_id"],
            position=d["position"],
            filename=d["filename"],
            mime_type=d["mime_type"],
            content_disposition=d.get("content_disposition"),
            storage_key=d.get("storage_key"),
        )


@dataclass(frozen=True, slots=True)
class AttachmentContent:
    """Raw attachment bytes from the download endpoint, plus header metadata."""

    content: bytes
    filename: str | None
    mime_type: str | None


#: DocumentSource values (spec: DocumentSource). ``xml-*`` sources are
#: faithful EN 16931 representations; ``llm-*`` sources are best-effort
#: extractions — apply your own validation before booking.
DOCUMENT_SOURCE_VALUES = ("xml-cii", "xml-ubl", "xml-zugferd", "llm-pdf", "llm-body")

#: Deterministic token appended to ``BusinessDocument.payment_terms`` when the
#: source document was marked as paid (LLM sources only).
PAID_TOKEN = "[PAID]"


@dataclass(frozen=True, slots=True)
class BusinessParty:
    """A trading partner — seller or buyer (spec: BusinessParty)."""

    name: str | None = None
    street_name: str | None = None
    postal_zone: str | None = None
    city_name: str | None = None
    country_code: str | None = None
    vat_id: str | None = None
    tax_registration_id: str | None = None
    company_registration_id: str | None = None
    electronic_mail: str | None = None
    telephone: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> BusinessParty:
        return cls(
            name=d.get("name"),
            street_name=d.get("street_name"),
            postal_zone=d.get("postal_zone"),
            city_name=d.get("city_name"),
            country_code=d.get("country_code"),
            vat_id=d.get("vat_id"),
            tax_registration_id=d.get("tax_registration_id"),
            company_registration_id=d.get("company_registration_id"),
            electronic_mail=d.get("electronic_mail"),
            telephone=d.get("telephone"),
        )


@dataclass(frozen=True, slots=True)
class BusinessPrice:
    """Unit price information (spec: BusinessPrice)."""

    item_net_price: Decimal | None = None
    base_quantity: Decimal | None = None
    base_quantity_unit_code: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> BusinessPrice:
        return cls(
            item_net_price=_parse_decimal(d.get("item_net_price")),
            base_quantity=_parse_decimal(d.get("base_quantity")),
            base_quantity_unit_code=d.get("base_quantity_unit_code"),
        )


@dataclass(frozen=True, slots=True)
class BusinessTaxCategory:
    """VAT category of a line or totals row (spec: BusinessTaxCategory)."""

    id: str | None = None
    percent: Decimal | None = None
    tax_scheme_id: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> BusinessTaxCategory:
        return cls(
            id=d.get("id"),
            percent=_parse_decimal(d.get("percent")),
            tax_scheme_id=d.get("tax_scheme_id"),
        )


@dataclass(frozen=True, slots=True)
class BusinessDocumentLine:
    """A single line item (spec: BusinessDocumentLine)."""

    id: str | None = None
    item_name: str | None = None
    description: str | None = None
    invoiced_quantity: Decimal | None = None
    unit_code: str | None = None
    standard_item_identification: str | None = None
    sellers_item_identification: str | None = None
    buyers_item_identification: str | None = None
    order_line_reference: str | None = None
    project_reference_line: str | None = None
    price: BusinessPrice | None = None
    allowance_charge_amount: Decimal | None = None
    line_extension_amount: Decimal | None = None
    total_amount: Decimal | None = None
    classified_tax_category: BusinessTaxCategory | None = None
    vat_amount: Decimal | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> BusinessDocumentLine:
        price = d.get("price")
        tax = d.get("classified_tax_category")
        return cls(
            id=d.get("id"),
            item_name=d.get("item_name"),
            description=d.get("description"),
            invoiced_quantity=_parse_decimal(d.get("invoiced_quantity")),
            unit_code=d.get("unit_code"),
            standard_item_identification=d.get("standard_item_identification"),
            sellers_item_identification=d.get("sellers_item_identification"),
            buyers_item_identification=d.get("buyers_item_identification"),
            order_line_reference=d.get("order_line_reference"),
            project_reference_line=d.get("project_reference_line"),
            price=BusinessPrice.from_dict(price) if price is not None else None,
            allowance_charge_amount=_parse_decimal(d.get("allowance_charge_amount")),
            line_extension_amount=_parse_decimal(d.get("line_extension_amount")),
            total_amount=_parse_decimal(d.get("total_amount")),
            classified_tax_category=(
                BusinessTaxCategory.from_dict(tax) if tax is not None else None
            ),
            vat_amount=_parse_decimal(d.get("vat_amount")),
        )


@dataclass(frozen=True, slots=True)
class TaxSubtotal:
    """One row of the document-level VAT breakdown (spec: TaxSubtotal)."""

    tax_category_id: str | None = None
    tax_category_percent: Decimal | None = None
    tax_scheme_id: str | None = None
    taxable_amount: Decimal | None = None
    tax_amount: Decimal | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> TaxSubtotal:
        return cls(
            tax_category_id=d.get("tax_category_id"),
            tax_category_percent=_parse_decimal(d.get("tax_category_percent")),
            tax_scheme_id=d.get("tax_scheme_id"),
            taxable_amount=_parse_decimal(d.get("taxable_amount")),
            tax_amount=_parse_decimal(d.get("tax_amount")),
        )


@dataclass(frozen=True, slots=True)
class MonetaryTotal:
    """Document-level monetary summary (spec: MonetaryTotal)."""

    line_extension_amount: Decimal | None = None
    allowance_total_amount: Decimal | None = None
    tax_exclusive_amount: Decimal | None = None
    tax_inclusive_amount: Decimal | None = None
    prepaid_amount: Decimal | None = None
    payable_amount: Decimal | None = None
    document_currency_code: str | None = None
    tax_subtotal: tuple[TaxSubtotal, ...] = ()

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> MonetaryTotal:
        return cls(
            line_extension_amount=_parse_decimal(d.get("line_extension_amount")),
            allowance_total_amount=_parse_decimal(d.get("allowance_total_amount")),
            tax_exclusive_amount=_parse_decimal(d.get("tax_exclusive_amount")),
            tax_inclusive_amount=_parse_decimal(d.get("tax_inclusive_amount")),
            prepaid_amount=_parse_decimal(d.get("prepaid_amount")),
            payable_amount=_parse_decimal(d.get("payable_amount")),
            document_currency_code=d.get("document_currency_code"),
            tax_subtotal=tuple(TaxSubtotal.from_dict(s) for s in d.get("tax_subtotal") or ()),
        )


@dataclass(frozen=True, slots=True)
class BusinessPaymentMeans:
    """One payment channel of the supplier (spec: BusinessPaymentMeans)."""

    payee_financial_account: str | None = None
    bic_id: str | None = None
    financial_institution_name: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> BusinessPaymentMeans:
        return cls(
            payee_financial_account=d.get("payee_financial_account"),
            bic_id=d.get("bic_id"),
            financial_institution_name=d.get("financial_institution_name"),
        )


@dataclass(frozen=True, slots=True)
class BusinessDocument:
    """Canonical parsed business document (spec: BusinessDocument, EN 16931).

    Single export schema for JSON parse results since spec 0.13.0. Check
    :attr:`document_source`: ``xml-*`` documents are legally reliable XML
    parses, ``llm-*`` documents are best-effort extractions.
    """

    document_source: str | None = None
    document_type_name: str | None = None
    document_type_code: str | None = None
    id: str | None = None
    buyer_reference: str | None = None
    project_reference: str | None = None
    contract_reference: str | None = None
    issue_date: datetime | None = None
    due_date: datetime | None = None
    note: str | None = None
    additional_document_ref: str | None = None
    document_summary: str | None = None
    accounting_supplier_party: BusinessParty | None = None
    accounting_customer_party: BusinessParty | None = None
    business_document_lines: tuple[BusinessDocumentLine, ...] = ()
    legal_monetary_total: MonetaryTotal | None = None
    payment_terms: str | None = None
    payment_means_code: str | None = None
    payment_means: tuple[BusinessPaymentMeans, ...] = ()

    @property
    def is_paid(self) -> bool:
        """True when payment_terms carries the deterministic ``[PAID]`` token."""
        return self.payment_terms is not None and self.payment_terms.endswith(PAID_TOKEN)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> BusinessDocument:
        supplier = d.get("accounting_supplier_party")
        customer = d.get("accounting_customer_party")
        total = d.get("legal_monetary_total")
        return cls(
            document_source=d.get("document_source"),
            document_type_name=d.get("document_type_name"),
            document_type_code=d.get("document_type_code"),
            id=d.get("id"),
            buyer_reference=d.get("buyer_reference"),
            project_reference=d.get("project_reference"),
            contract_reference=d.get("contract_reference"),
            issue_date=_parse_datetime(d.get("issue_date")),
            due_date=_parse_datetime(d.get("due_date")),
            note=d.get("note"),
            additional_document_ref=d.get("additional_document_ref"),
            document_summary=d.get("document_summary"),
            accounting_supplier_party=(
                BusinessParty.from_dict(supplier) if supplier is not None else None
            ),
            accounting_customer_party=(
                BusinessParty.from_dict(customer) if customer is not None else None
            ),
            business_document_lines=tuple(
                BusinessDocumentLine.from_dict(x) for x in d.get("business_document_lines") or ()
            ),
            legal_monetary_total=MonetaryTotal.from_dict(total) if total is not None else None,
            payment_terms=d.get("payment_terms"),
            payment_means_code=d.get("payment_means_code"),
            payment_means=tuple(
                BusinessPaymentMeans.from_dict(x) for x in d.get("payment_means") or ()
            ),
        )


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Parsed document record; ``data`` is the raw payload (see
    :meth:`business_document` for the typed view of JSON records).

    Since spec 0.15.0 duplicates are signalled by the presence of
    ``deduplicated_by_index`` (replacing the former ``is_deduplicated_by``
    boolean): an absent value means the record is not a duplicate.
    """

    id: int
    message_id: str
    attachment_index: int
    document_type: str
    data_type: str
    is_fully_parsed: bool
    created_at: datetime
    attachment_name: str | None = None
    data: Any = None
    stage_parser: str | None = None
    stage_completed_at: datetime | None = None
    stage_duration_s: float | None = None
    llm_model_name: str | None = None
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    llm_inference_time_ms: int | None = None
    deduplicated_by_index: int | None = None
    deduplicated_by_name: str | None = None

    @property
    def is_duplicate(self) -> bool:
        """True when this record is a dedup placeholder, not a document."""
        return self.deduplicated_by_index is not None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ParsedDocument:
        return cls(
            id=d["id"],
            message_id=d["message_id"],
            attachment_index=d["attachment_index"],
            document_type=d["document_type"],
            data_type=d["data_type"],
            is_fully_parsed=d["is_fully_parsed"],
            created_at=_parse_datetime(d["created_at"]),
            attachment_name=d.get("attachment_name"),
            data=d.get("data"),
            stage_parser=d.get("stage_parser"),
            stage_completed_at=_parse_datetime(d.get("stage_completed_at")),
            stage_duration_s=d.get("stage_duration_s"),
            llm_model_name=d.get("llm_model_name"),
            llm_input_tokens=d.get("llm_input_tokens"),
            llm_output_tokens=d.get("llm_output_tokens"),
            llm_inference_time_ms=d.get("llm_inference_time_ms"),
            deduplicated_by_index=d.get("deduplicated_by_index"),
            deduplicated_by_name=d.get("deduplicated_by_name"),
        )

    def business_document(self) -> BusinessDocument | None:
        """Typed view of the ``data`` payload (spec ≥ 0.13.0).

        Returns None for binary records or when ``data`` is not a JSON
        object. The raw payload stays available in :attr:`data`.
        """
        if self.data_type != "json" or not isinstance(self.data, Mapping):
            return None
        return BusinessDocument.from_dict(self.data)


#: Status values accepted by ``report_status`` (spec: ConsumerStatusValue).
#: ``related`` means the message was matched to an existing record in the
#: external system rather than imported as a new one.
CONSUMER_STATUS_VALUES = ("imported", "failed", "skipped", "related")

#: Per-backlink status values (spec: BacklinkStatus).
BACKLINK_STATUS_VALUES = ("imported", "related")


@dataclass(frozen=True, slots=True)
class Backlink:
    """Hyperlink to the record a consumer imported or matched in the external
    system (spec: ConsumerStatusBacklink)."""

    url: str
    status: str
    title: str | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Backlink:
        return cls(url=d["url"], status=d["status"], title=d.get("title"))

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"url": self.url, "status": self.status}
        if self.title is not None:
            out["title"] = self.title
        return out


@dataclass(frozen=True, slots=True)
class ClientConfig:
    """OIDC client configuration from the public discovery endpoint
    ``GET /.well-known/client-config`` (spec 0.14.0: ClientConfigResponse).

    ``scope`` is composed server-side from the configured audience — use it
    verbatim when requesting tokens. All OIDC fields are ``None`` when
    ``auth_provider_type`` is ``"local_jwt"`` (no OIDC provider configured).
    """

    auth_provider_type: str
    issuer: str | None = None
    token_endpoint: str | None = None
    grant_type: str | None = None
    audience: str | None = None
    scope: str | None = None

    @property
    def is_remote(self) -> bool:
        """True when the server validates tokens against an OIDC provider."""
        return self.auth_provider_type == "remote"

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ClientConfig:
        return cls(
            auth_provider_type=d["auth_provider_type"],
            issuer=d.get("issuer"),
            token_endpoint=d.get("token_endpoint"),
            grant_type=d.get("grant_type"),
            audience=d.get("audience"),
            scope=d.get("scope"),
        )


@dataclass(frozen=True, slots=True)
class ConsumerStatus:
    """One append-only consumer-status audit entry."""

    id: str
    tenant_id: str
    message_id: str
    mailbox_id: str
    consumer_name: str
    consumer_type: str
    status: str
    created_by_user_id: str
    created_at: datetime
    backlinks: tuple[Backlink, ...] = ()

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ConsumerStatus:
        return cls(
            id=d["id"],
            tenant_id=d["tenant_id"],
            message_id=d["message_id"],
            mailbox_id=d["mailbox_id"],
            consumer_name=d["consumer_name"],
            consumer_type=d["consumer_type"],
            status=d["status"],
            created_by_user_id=d["created_by_user_id"],
            created_at=_parse_datetime(d["created_at"]),
            backlinks=tuple(Backlink.from_dict(b) for b in d.get("backlinks") or ()),
        )
