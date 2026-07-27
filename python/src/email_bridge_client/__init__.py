"""Python client for the E-Mail-Bridge (AI Documents Ingestion) REST API."""

from .client import DEFAULT_TIMEOUT, IngestionClient, RetryConfig
from .exceptions import (
    ApiError,
    AuthenticationError,
    ForbiddenError,
    IngestionClientError,
    InvalidWebhookPayload,
    NotFoundError,
    ServerError,
    TransportError,
)
from .models import (
    CONSUMER_STATUS_VALUES,
    Attachment,
    AttachmentContent,
    AttachmentSummary,
    ClassificationEntry,
    ConsumerStatus,
    MessageDetail,
    MessageStageResult,
    ParsedDocument,
    StageMetadataInfo,
    StageResultClassification,
    StageResultDocument,
)
from .webhook import is_test_mode, parse_webhook_payload, verify_bearer_token

__version__ = "0.1.0"

#: API spec version this release was verified against (spec/business-document-api.yaml).
SPEC_VERSION = "0.11.0"

__all__ = [
    "CONSUMER_STATUS_VALUES",
    "DEFAULT_TIMEOUT",
    "SPEC_VERSION",
    "ApiError",
    "Attachment",
    "AttachmentContent",
    "AttachmentSummary",
    "AuthenticationError",
    "ClassificationEntry",
    "ConsumerStatus",
    "ForbiddenError",
    "IngestionClient",
    "IngestionClientError",
    "InvalidWebhookPayload",
    "MessageDetail",
    "MessageStageResult",
    "NotFoundError",
    "ParsedDocument",
    "RetryConfig",
    "ServerError",
    "StageMetadataInfo",
    "StageResultClassification",
    "StageResultDocument",
    "TransportError",
    "is_test_mode",
    "parse_webhook_payload",
    "verify_bearer_token",
]
