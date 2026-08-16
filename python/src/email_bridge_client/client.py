"""HTTP client for the E-Mail-Bridge (AI Documents Ingestion) REST API.

Covers the simplified ``/messages/{messageId}`` endpoint family designed for
external message consumers (see the server repo's
``docs/specs/external-message-consumers-api.md``): the webhook delivers
message UUIDs, and this client fetches details, parsed documents, attachment
binaries, and reports the import outcome back.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    LINK_KIND_VALUES,
    Attachment,
    AttachmentContent,
    ClientConfig,
    ConnectedSystem,
    ConnectedSystemStatus,
    MessageDetail,
    MessageSummary,
    ParsedDocument,
    RecordLink,
    TenantMasterData,
)

#: Default per-request timeout in seconds (connect and read).
DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class RetryConfig:
    """Automatic retry policy for idempotent GET requests.

    POSTs (``report_imported``, ``add_links``, ``remove_links``) are never
    retried automatically — the caller decides about re-submission.
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

    # ── connected system status ───────────────────────────────────────────

    @staticmethod
    def _validated_links(links: Iterable[RecordLink]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, link in enumerate(links):
            if not link.url:
                raise ValueError(f"links[{i}]: url must be non-empty")
            if link.kind not in LINK_KIND_VALUES:
                raise ValueError(
                    f"links[{i}]: kind must be one of {LINK_KIND_VALUES}, got {link.kind!r}"
                )
            out.append(link.to_dict())
        return out

    def report_imported(
        self,
        message_id: str,
        external_uuid: str,
        links: Iterable[RecordLink] = (),
    ) -> ConnectedSystemStatus:
        """``POST /messages/{messageId}/connected_system_status`` — report
        that this connected system processed the message.

        Full-state semantics: an existing report of the same system and ALL
        of its links are replaced by this call. ``links`` may be empty
        (processing without record creation). Link URLs must be absolute and
        match the system's registered ``base_web_url``. Not retried
        automatically.
        """
        body: dict[str, Any] = {
            "external_uuid": external_uuid,
            "status": "imported",
            "links": self._validated_links(links),
        }
        resp = self._request(
            "POST",
            f"/messages/{_seg(message_id)}/connected_system_status",
            json=body,
        )
        return ConnectedSystemStatus.from_dict(resp.json())

    def list_status(self, message_id: str) -> list[ConnectedSystemStatus]:
        """``GET /messages/{messageId}/connected_system_status`` — the
        current report of every connected system (at most one each)."""
        items = self._get_json(f"/messages/{_seg(message_id)}/connected_system_status")
        return [ConnectedSystemStatus.from_dict(x) for x in items]

    def add_links(
        self,
        message_id: str,
        external_uuid: str,
        links: Iterable[RecordLink],
    ) -> ConnectedSystemStatus:
        """``POST /messages/{messageId}/connected_system_links`` —
        idempotently add record links.

        Re-adding an existing path updates title and kind (last write wins).
        A missing status report is created automatically, so this may be
        called without a prior :meth:`report_imported`.
        """
        body: dict[str, Any] = {
            "external_uuid": external_uuid,
            "links": self._validated_links(links),
        }
        resp = self._request(
            "POST",
            f"/messages/{_seg(message_id)}/connected_system_links",
            json=body,
        )
        return ConnectedSystemStatus.from_dict(resp.json())

    def remove_links(
        self,
        message_id: str,
        external_uuid: str,
        paths: Iterable[str],
    ) -> None:
        """``POST /messages/{messageId}/connected_system_links/remove`` —
        idempotently remove record links by their stored paths. Removing a
        non-existent path is a no-op."""
        self._request(
            "POST",
            f"/messages/{_seg(message_id)}/connected_system_links/remove",
            json={"external_uuid": external_uuid, "paths": list(paths)},
        )

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

    # ── connected systems ─────────────────────────────────────────────────

    def list_connected_systems(self, tenant_id: str) -> list[ConnectedSystem]:
        """``GET /tenants/{tenantId}/connected_systems`` — ordered by name.

        Requires role ``tenant_admin`` (own tenant) or ``global_tenant_admin``
        and spec 0.17.0+ on the server.
        """
        items = self._get_json(f"/tenants/{_seg(tenant_id)}/connected_systems")
        return [ConnectedSystem.from_dict(x) for x in items]

    def create_connected_system(
        self,
        tenant_id: str,
        *,
        name: str,
        external_uuid: str,
        base_web_url: str,
        description: str | None = None,
    ) -> ConnectedSystem:
        """``POST /tenants/{tenantId}/connected_systems`` — register a system.

        ``external_uuid`` is supplied by the external system, must be unique
        across all tenants of the bridge, and is immutable afterwards.
        ``base_web_url`` must be scheme + host only (port allowed, no path);
        the server validates DNS resolution and normalizes the value.
        """
        body: dict[str, Any] = {
            "name": name,
            "external_uuid": external_uuid,
            "base_web_url": base_web_url,
        }
        if description is not None:
            body["description"] = description
        resp = self._request(
            "POST", f"/tenants/{_seg(tenant_id)}/connected_systems", json=body
        )
        return ConnectedSystem.from_dict(resp.json())

    def get_connected_system(self, tenant_id: str, connected_system_id: str) -> ConnectedSystem:
        """``GET /tenants/{tenantId}/connected_systems/{connectedSystemId}``."""
        return ConnectedSystem.from_dict(
            self._get_json(
                f"/tenants/{_seg(tenant_id)}/connected_systems/{_seg(connected_system_id)}"
            )
        )

    def update_connected_system(
        self,
        tenant_id: str,
        connected_system_id: str,
        *,
        name: str,
        base_web_url: str,
        description: str | None = None,
        external_uuid: str | None = None,
    ) -> ConnectedSystem:
        """``PUT /tenants/{tenantId}/connected_systems/{connectedSystemId}``.

        ``external_uuid`` may be echoed unchanged for round-trip safety; a
        value different from the stored one is rejected with 400 — the field
        is immutable.
        """
        body: dict[str, Any] = {"name": name, "base_web_url": base_web_url}
        if description is not None:
            body["description"] = description
        if external_uuid is not None:
            body["external_uuid"] = external_uuid
        resp = self._request(
            "PUT",
            f"/tenants/{_seg(tenant_id)}/connected_systems/{_seg(connected_system_id)}",
            json=body,
        )
        return ConnectedSystem.from_dict(resp.json())

    def delete_connected_system(self, tenant_id: str, connected_system_id: str) -> None:
        """``DELETE /tenants/{tenantId}/connected_systems/{connectedSystemId}``."""
        self._request(
            "DELETE",
            f"/tenants/{_seg(tenant_id)}/connected_systems/{_seg(connected_system_id)}",
        )

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
