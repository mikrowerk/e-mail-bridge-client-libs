"""Exception hierarchy for the E-Mail-Bridge client.

Everything raised by this library derives from :class:`IngestionClientError`;
exceptions from the underlying ``requests`` library never leak to callers.
"""

from __future__ import annotations


class IngestionClientError(Exception):
    """Base class for all errors raised by this library."""


class TransportError(IngestionClientError):
    """A network-level failure (connection error, timeout, DNS, ...).

    The original ``requests`` exception is available as ``__cause__``.
    """


class InvalidWebhookPayload(IngestionClientError):
    """The webhook request body is not a valid ``{"uuids": [...]}`` payload."""


class ApiError(IngestionClientError):
    """The API answered with a non-2xx status code.

    Attributes:
        status_code: HTTP status code of the response.
        body: Decoded JSON error body (usually ``{"code": ..., "message": ...}``)
            or the raw response text when the body is not JSON.
    """

    def __init__(self, message: str, status_code: int, body: object = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class AuthenticationError(ApiError):
    """401 — missing, expired, or invalid bearer token."""


class ForbiddenError(ApiError):
    """403 — the token lacks the required role or tenant/mailbox scope."""


class NotFoundError(ApiError):
    """404 — message, attachment, or parsed document does not exist."""


class ServerError(ApiError):
    """5xx — the API failed internally."""
