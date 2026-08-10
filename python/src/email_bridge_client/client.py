"""HTTP client for the E-Mail-Bridge (AI Documents Ingestion) REST API.

Covers the simplified ``/messages/{messageId}`` endpoint family designed for
external message consumers (see the server repo's
``docs/specs/external-message-consumers-api.md``): the webhook delivers
message UUIDs, and this client fetches details, parsed documents, attachment
binaries, and reports the import outcome back.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import Message
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import (
    ApiError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    ServerError,
    TransportError,
)
from .models import (
    BACKLINK_STATUS_VALUES,
    CONSUMER_STATUS_VALUES,
    Attachment,
    AttachmentContent,
    Backlink,
    ClientConfig,
    ConsumerStatus,
    MessageDetail,
    MessageSummary,
    ParsedDocument,
    TenantMasterData,
)

#: Default per-request timeout in seconds (connect and read).
DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class RetryConfig:
    """Automatic retry policy for idempotent GET requests.

    POSTs (``report_status``) are never retried automatically — they create
    append-only audit rows, so the caller decides about re-submission.
    """

    attempts: int = 3
    backoff_factor: float = 0.5
    status_forcelist: tuple[int, ...] = (429, 502, 503, 504)


def _error_class(status_code: int) -> type[ApiError]:
    if status_code == 401:
        return AuthenticationError
    if status_code == 403:
        return ForbiddenError
    if status_code == 404:
        return NotFoundError
    if status_code >= 500:
        return ServerError
    return ApiError


def _filename_from_disposition(content_disposition: str | None) -> str | None:
    if not content_disposition:
        return None
    msg = Message()
    msg["Content-Disposition"] = content_disposition
    return msg.get_filename()


class IngestionClient:
    """Client for the simplified external-consumer API.

    Args:
        base_url: API base including the version prefix,
            e.g. ``"https://host/api/v1"``.
        token: Bearer token — a personal access token of a service account
            with role ``mailbox_user``.
        timeout: Per-request timeout in seconds; always applied.
        session: Optional pre-configured :class:`requests.Session` (mainly for
            testing). The client only mounts its retry adapter and closes the
            session on :meth:`close` when it created the session itself.
        retries: Retry policy for GET requests.

    Usable as a context manager::

        with IngestionClient(base_url, token) as client:
            message = client.get_message(uuid)
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
        retries: RetryConfig | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._owns_session = session is None
        self._session = session if session is not None else requests.Session()
        if self._owns_session:
            retries = retries if retries is not None else RetryConfig()
            retry = Retry(
                total=retries.attempts,
                backoff_factor=retries.backoff_factor,
                status_forcelist=list(retries.status_forcelist),
                allowed_methods=frozenset({"GET"}),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

    def __repr__(self) -> str:  # token deliberately masked
        return f"IngestionClient(base_url={self._base_url!r}, token='***')"

    def __enter__(self) -> IngestionClient:  # noqa: PYI034 — Self needs Python ≥3.11, we support 3.10
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying session if this client created it."""
        if self._owns_session:
            self._session.close()

    # ── messages ──────────────────────────────────────────────────────────

    def get_message(self, message_id: str) -> MessageDetail:
        """``GET /messages/{messageId}`` — full message detail."""
        return MessageDetail.from_dict(self._get_json(f"/messages/{_seg(message_id)}"))

    def list_thread(self, message_id: str) -> list[MessageSummary]:
        """``GET /messages/{messageId}/thread`` — all messages of the
        conversation this message belongs to, oldest first (thread root
        first). A standalone message yields a single-element list.
        """
        items = self._get_json(f"/messages/{_seg(message_id)}/thread")
        return [MessageSummary.from_dict(x) for x in items]

    def list_parsed_documents(self, message_id: str) -> list[ParsedDocument]:
        """``GET /messages/{messageId}/parsed-documents``."""
        items = self._get_json(f"/messages/{_seg(message_id)}/parsed-documents")
        return [ParsedDocument.from_dict(x) for x in items]

    def get_parsed_document(self, message_id: str, parsed_document_id: int) -> ParsedDocument:
        """``GET /messages/{messageId}/parsed-documents/{parsedDocumentId}``."""
        return ParsedDocument.from_dict(
            self._get_json(f"/messages/{_seg(message_id)}/parsed-documents/{parsed_document_id:d}")
        )

    def list_attachments(self, message_id: str) -> list[Attachment]:
        """``GET /messages/{messageId}/attachments`` — metadata only."""
        items = self._get_json(f"/messages/{_seg(message_id)}/attachments")
        return [Attachment.from_dict(x) for x in items]

    def get_attachment(self, message_id: str, attachment_id: int) -> Attachment:
        """``GET /messages/{messageId}/attachments/{attachmentId}`` — metadata only."""
        return Attachment.from_dict(
            self._get_json(f"/messages/{_seg(message_id)}/attachments/{attachment_id:d}")
        )

    def download_attachment(self, message_id: str, attachment_id: int) -> AttachmentContent:
        """``GET /messages/{messageId}/attachments/{attachmentId}/content``.

        Returns the original attachment binary as stored at ingest time.
        """
        resp = self._request(
            "GET", f"/messages/{_seg(message_id)}/attachments/{attachment_id:d}/content"
        )
        return AttachmentContent(
            content=resp.content,
            filename=_filename_from_disposition(resp.headers.get("Content-Disposition")),
            mime_type=resp.headers.get("Content-Type"),
        )

    # ── consumer status ───────────────────────────────────────────────────

    def report_status(
        self,
        message_id: str,
        status: str,
        *,
        consumer_name: str,
        consumer_type: str = "odoo-email-bridge",
        backlinks: list[Backlink] | tuple[Backlink, ...] | None = None,
    ) -> ConsumerStatus:
        """``POST /messages/{messageId}/consumer_status`` — report the outcome.

        ``status`` must be one of ``imported``, ``failed``, ``skipped``,
        ``related``. ``backlinks`` optionally points to the imported or
        related records in the external system.
        Not retried automatically (append-only audit log).
        """
        if status not in CONSUMER_STATUS_VALUES:
            raise ValueError(f"status must be one of {CONSUMER_STATUS_VALUES}, got {status!r}")
        body: dict[str, Any] = {
            "consumer_name": consumer_name,
            "consumer_type": consumer_type,
            "status": status,
        }
        if backlinks is not None:
            for i, b in enumerate(backlinks):
                if not b.url:
                    raise ValueError(f"backlinks[{i}]: url must be non-empty")
                if b.status not in BACKLINK_STATUS_VALUES:
                    raise ValueError(
                        f"backlinks[{i}]: status must be one of "
                        f"{BACKLINK_STATUS_VALUES}, got {b.status!r}"
                    )
            body["backlinks"] = [b.to_dict() for b in backlinks]
        resp = self._request(
            "POST",
            f"/messages/{_seg(message_id)}/consumer_status",
            json=body,
        )
        return ConsumerStatus.from_dict(resp.json())

    def list_consumer_status(self, message_id: str) -> list[ConsumerStatus]:
        """``GET /messages/{messageId}/consumer_status`` — prior reports."""
        items = self._get_json(f"/messages/{_seg(message_id)}/consumer_status")
        return [ConsumerStatus.from_dict(x) for x in items]

    # ── tenants ───────────────────────────────────────────────────────────

    def list_own_tenants(self) -> list[TenantMasterData]:
        """``GET /tenants/self`` — master data of the caller's own tenants.

        Currently always at most one element (the token's home tenant); the
        list form is future-proofing for multi-tenant grants. Empty when the
        home tenant is soft-deleted or cannot be resolved. Requires spec
        0.16.0+ on the server (older bridges return 404).
        """
        items = self._get_json("/tenants/self")
        return [TenantMasterData.from_dict(x) for x in items]

    # ── discovery ─────────────────────────────────────────────────────────

    def get_client_config(self) -> ClientConfig:
        """``GET /.well-known/client-config`` — OIDC client configuration.

        The endpoint is public; see :func:`fetch_client_config` for calling
        it before a token is available.
        """
        return ClientConfig.from_dict(self._get_json("/.well-known/client-config"))

    # ── internals ─────────────────────────────────────────────────────────

    def _get_json(self, path: str) -> Any:
        return self._request("GET", path).json()

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = self._base_url + path
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            resp = self._session.request(
                method, url, headers=headers, timeout=self._timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise TransportError(f"{method} {path}: {exc}") from exc
        if not resp.ok:
            self._raise_api_error(method, path, resp)
        return resp

    @staticmethod
    def _raise_api_error(method: str, path: str, resp: requests.Response) -> None:
        try:
            body: object = resp.json()
        except ValueError:
            body = resp.text
        message = body.get("message") if isinstance(body, dict) else None
        raise _error_class(resp.status_code)(
            f"{method} {path}: HTTP {resp.status_code}" + (f": {message}" if message else ""),
            status_code=resp.status_code,
            body=body,
        )


def _seg(value: str) -> str:
    """Quote a value for safe use as a single URL path segment."""
    return quote(str(value), safe="")


def fetch_client_config(
    base_url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    session: requests.Session | None = None,
) -> ClientConfig:
    """Fetch ``GET {base_url}/.well-known/client-config`` without a token.

    The discovery endpoint is public by design, so a consumer can obtain the
    token endpoint, audience and exact scope string *before* it has any
    credentials — the intended bootstrap for self-configuration (see the
    server repo's ``.features/.specs/odoo-client-config-discovery.md``).

    Args:
        base_url: API base including the version prefix,
            e.g. ``"https://host/api/v1"``.
        timeout: Per-request timeout in seconds.
        session: Optional :class:`requests.Session`; a one-shot request is
            made when omitted.
    """
    url = base_url.rstrip("/") + "/.well-known/client-config"
    http = session if session is not None else requests
    try:
        resp = http.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise TransportError(f"GET /.well-known/client-config: {exc}") from exc
    if not resp.ok:
        IngestionClient._raise_api_error("GET", "/.well-known/client-config", resp)
    return ClientConfig.from_dict(resp.json())
