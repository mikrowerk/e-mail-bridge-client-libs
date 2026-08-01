"""Typed models mirroring the API's response schemas.

Field names keep the API's snake_case (``from`` becomes ``from_`` because it
is a Python keyword). Unknown JSON fields are ignored for forward
compatibility with newer spec versions. Timestamps are parsed to
timezone-aware :class:`datetime.datetime`.

The spec source of truth is ``spec/business-document-api.yaml`` (validated by
the contract tests); the ``ParsedDocument.data`` payload is deliberately
untyped there, so it stays a plain ``dict``/``str`` here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
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
    """Parsed-document summary within the stage result."""

    attachment_id: int | None = None
    attachment_name: str | None = None
    document_type_code: str | None = None
    document_type_name: str | None = None
    document_date: date | None = None
    document_number: str | None = None
    summary: str | None = None
    stage_metadata: StageMetadataInfo | None = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> StageResultDocument:
        return cls(
            attachment_id=d.get("attachment_id"),
            attachment_name=d.get("attachment_name"),
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
class MessageDetail:
    """Full message detail (``GET /messages/{messageId}``)."""

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


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Parsed document record; ``data`` is untyped by design (see spec)."""

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
    is_deduplicated_by: bool = False

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
            is_deduplicated_by=d.get("is_deduplicated_by", False),
        )


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
