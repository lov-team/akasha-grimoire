#!/usr/bin/env python3
"""Shared LovBrowser official new-api balance recharge helper.

Only the official new-api origin may trigger automatic recharge. Private or
third-party OpenAI-compatible gateways keep their original error semantics even
if they forge recharge metadata.

Top-level rule: each CLI command creates one RechargeController. At most one
ticket/session is created for the whole command. After that single recharge,
any further insufficient_user_quota stops without another payment attempt.

Protocol (stable server contract):
  1. Detect HTTP 403 + error.code == insufficient_user_quota
     + error.metadata.recharge.supported is true, on official origin only.
  2. POST /v1/tooling/recharge-ticket with Authorization: Bearer <API key>
     against the official HTTPS origin only.
  3. POST lovbrowser_session_endpoint with JSON {"ticket": "..."} only (no key).
  4. Download qrPngUrl to a unique outside-repo temp path; emit one-line event.
  5. Poll GET session/{publicId} until SUCCEEDED / EXPIRED / FAILED / timeout.
  6. On SUCCEEDED, retry only the failed HTTP closure once.

Stdlib-only. Import via resolved path so Skill scripts remain runnable as
absolute/relative files and via symlink installs that resolve into this monorepo.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, TextIO, TypeVar

T = TypeVar("T")

OFFICIAL_NEWAPI_HOST = "newapi.1234bot.com"
OFFICIAL_NEWAPI_BASE_URL = "https://newapi.1234bot.com/v1"
DEFAULT_FACE_VALUE_USD_CENT = 1000  # product default 10 USD
MIN_FACE_VALUE_USD_CENT = 100  # 1 USD
MAX_FACE_VALUE_USD_CENT = 1_000_000  # 10000 USD
INSUFFICIENT_CODE = "insufficient_user_quota"
DEFAULT_TICKET_ENDPOINT = "/v1/tooling/recharge-ticket"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EVENT_NAME = "akasha.recharge"

_TERMINAL_SUCCESS = "SUCCEEDED"
_TERMINAL_FAILURE = frozenset({"EXPIRED", "FAILED"})
_WAIT_STATES = frozenset({"PENDING_PAYMENT", "CREDITING"})
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class AkashaRechargeError(RuntimeError):
    """User-facing recharge failure without secrets."""


class InsufficientUserQuotaError(Exception):
    """Raised by adapters when a request should enter the one-shot recharge path."""

    def __init__(self, status_code: int, body: bytes, hint: "RechargeHint") -> None:
        super().__init__(f"HTTP {status_code}: insufficient_user_quota")
        self.status_code = status_code
        self.body = body
        self.hint = hint


@dataclass(frozen=True)
class RechargeHint:
    ticket_endpoint: str
    default_face_value_usd_cent: int | None = None


@dataclass
class RechargeSessionView:
    public_id: str
    status: str
    face_value_usd_cent: int
    currency: str
    expire_time: Any
    public_page_url: str
    status_url: str
    qr_png_url: str = ""
    qr_png_path: str | None = None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse all redirects so Authorization/ticket cannot be cross-origin replayed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _default_urlopen(request: urllib.request.Request, timeout: float = 60.0):
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout)


def is_official_newapi_base_url(base_url: str) -> bool:
    """Return True only for the official LovBrowser new-api origin."""
    if not isinstance(base_url, str) or not base_url.strip():
        return False
    try:
        parsed = urllib.parse.urlsplit(base_url.strip())
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if parsed.scheme.lower() != "https":
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if not hostname or hostname.lower() != OFFICIAL_NEWAPI_HOST:
        return False
    if port not in (None, 443):
        return False
    return True


def usd_to_cents(usd: Decimal) -> int:
    if not isinstance(usd, Decimal):
        usd = Decimal(usd)
    if not usd.is_finite():
        raise AkashaRechargeError("recharge amount must be a finite number of USD")
    try:
        quantized = usd.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise AkashaRechargeError("recharge amount must be a finite number of USD") from exc
    if quantized != usd:
        raise AkashaRechargeError(
            "recharge amount must convert to an integer number of USD cents "
            "(at most two decimal places)"
        )
    cents = int(quantized * 100)
    if cents < MIN_FACE_VALUE_USD_CENT or cents > MAX_FACE_VALUE_USD_CENT:
        raise AkashaRechargeError(
            "recharge amount must be between 1 and 10000 USD inclusive"
        )
    return cents


def resolve_face_value_usd_cent(
    cli_value: str | float | int | None = None,
    *,
    env: Mapping[str, str] | None = None,
    use_env: bool = True,
) -> int:
    """Resolve face value cents.

    CLI wins over AKASHA_RECHARGE_USD; default is 10 USD.
    Callers that must preserve private-gateway behavior should only resolve
    environment values when a recharge is actually triggered (use_env=True at
    trigger time). Explicit CLI values may be validated early.
    """
    environ = env if env is not None else os.environ
    if cli_value is not None and str(cli_value).strip() != "":
        raw: str | None = str(cli_value).strip()
    elif use_env:
        env_raw = environ.get("AKASHA_RECHARGE_USD")
        raw = env_raw.strip() if isinstance(env_raw, str) and env_raw.strip() else None
    else:
        raw = None
    if raw is None:
        return DEFAULT_FACE_VALUE_USD_CENT
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise AkashaRechargeError(
            f"invalid recharge amount {raw!r}: require a decimal USD value"
        ) from exc
    return usd_to_cents(amount)


def validate_cli_recharge_usd(cli_value: str | float | int | None) -> None:
    """Validate explicit CLI --recharge-usd early without reading env."""
    if cli_value is None or str(cli_value).strip() == "":
        return
    resolve_face_value_usd_cent(cli_value, use_env=False)


def _parse_json_object(body: bytes | str | dict[str, Any] | None) -> dict[str, Any] | None:
    if body is None:
        return None
    if isinstance(body, dict):
        return body
    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return None
    else:
        text = body
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def detect_insufficient_user_quota(
    status_code: int,
    body: bytes | str | dict[str, Any] | None,
    *,
    base_url: str,
) -> RechargeHint | None:
    """Return a recharge hint only when all three conditions hold on official origin."""
    if not is_official_newapi_base_url(base_url):
        return None
    if status_code != 403:
        return None
    payload = _parse_json_object(body)
    if not payload:
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    if error.get("code") != INSUFFICIENT_CODE:
        return None
    metadata = error.get("metadata")
    if not isinstance(metadata, dict):
        return None
    recharge_meta = metadata.get("recharge")
    if not isinstance(recharge_meta, dict):
        return None
    if recharge_meta.get("supported") is not True:
        return None
    endpoint = recharge_meta.get("ticket_endpoint") or DEFAULT_TICKET_ENDPOINT
    if not isinstance(endpoint, str) or not endpoint.strip():
        endpoint = DEFAULT_TICKET_ENDPOINT
    endpoint = endpoint.strip()
    if not endpoint.startswith("/"):
        return None
    default_cents = recharge_meta.get("default_face_value_usd_cent")
    if isinstance(default_cents, bool) or not isinstance(default_cents, int):
        default_cents = None
    return RechargeHint(ticket_endpoint=endpoint, default_face_value_usd_cent=default_cents)


def build_recharge_event(
    *,
    public_id: str,
    status: str,
    face_value_usd_cent: int,
    currency: str,
    expire_time: Any,
    qr_png_path: str | None,
    public_page_url: str,
    status_url: str,
) -> dict[str, Any]:
    """Structured one-line event fields safe for Agent consumption.

    Intentionally omits payUrl and any ticket/credential fields. Consumers must
    render qrPngPath in the Codex conversation and offer publicPageUrl.
    """
    return {
        "event": EVENT_NAME,
        "publicId": public_id,
        "status": status,
        "faceValueUsdCent": face_value_usd_cent,
        "currency": currency,
        "expireTime": expire_time,
        "qrPngPath": qr_png_path,
        "publicPageUrl": public_page_url,
        "statusUrl": status_url,
    }


def emit_recharge_event(event: Mapping[str, Any], file: TextIO | None = None) -> None:
    target = file if file is not None else sys.stdout
    print(json.dumps(dict(event), ensure_ascii=False, separators=(",", ":")), file=target, flush=True)


def _origin_only(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _ticket_url(ticket_endpoint: str, *, ticket_base_url: str | None = None) -> str:
    endpoint = ticket_endpoint if ticket_endpoint.startswith("/") else f"/{ticket_endpoint}"
    # Production always signs tickets against the official HTTPS origin.
    # Offline tests may inject ticket_base_url explicitly.
    root = ticket_base_url or OFFICIAL_NEWAPI_BASE_URL
    return _origin_only(root) + endpoint


def _require_https_url(url: str, label: str, *, allow_http: bool = False) -> urllib.parse.SplitResult:
    try:
        parsed = urllib.parse.urlsplit(url)
        _ = parsed.hostname
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise AkashaRechargeError(f"invalid {label}") from exc
    scheme = parsed.scheme.lower()
    if allow_http:
        if scheme not in {"http", "https"} or not parsed.hostname:
            raise AkashaRechargeError(f"invalid {label}: require absolute HTTP(S) URL")
    else:
        if scheme != "https" or not parsed.hostname:
            raise AkashaRechargeError(f"invalid {label}: require absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise AkashaRechargeError(f"invalid {label}: userinfo is not allowed")
    return parsed


def _safe_status_detail(status: int, payload: dict[str, Any] | None) -> str:
    """Local fixed wording + optional whitelist code only. Never echo server messages."""
    code: str | None = None
    if isinstance(payload, dict):
        error = payload.get("error")
        candidate = None
        if isinstance(error, dict):
            candidate = error.get("code")
        if candidate is None:
            candidate = payload.get("code")
        if isinstance(candidate, str) and _SAFE_CODE_RE.fullmatch(candidate.strip()):
            code = candidate.strip()
    if code:
        return f"HTTP {status}; code={code}"
    return f"HTTP {status}"


def _looks_like_enterprise_rejection(status: int, payload: dict[str, Any] | None) -> bool:
    if status not in {401, 403, 422}:
        return False
    # Only inspect code field, never free-form message content in user output.
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    code = ""
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        code = error["code"].lower()
    elif isinstance(payload.get("code"), str):
        code = payload["code"].lower()
    needles = (
        "enterprise",
        "org_member",
        "organization_member",
        "member_key",
        "enterprise_member",
    )
    return any(item in code for item in needles)


def _read_http_error_body(exc: urllib.error.HTTPError, limit: int = 1024 * 1024) -> bytes:
    try:
        return exc.read(limit)
    finally:
        try:
            exc.close()
        except Exception:
            pass


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
    urlopen: Callable[..., Any] | None = None,
) -> tuple[int, dict[str, Any] | None, bytes]:
    opener = urlopen or _default_urlopen
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request_headers = {"Accept": "application/json", "User-Agent": "akasha-recharge/1.1"}
    if headers:
        request_headers.update(headers)
    if body is not None and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024)
            status = getattr(response, "status", None) or response.getcode()
            parsed = _parse_json_object(raw)
            return int(status), parsed, raw
    except urllib.error.HTTPError as exc:
        if 300 <= int(exc.code) < 400:
            # Redirects are refused; never follow with Authorization/ticket.
            _read_http_error_body(exc, 4096)
            raise AkashaRechargeError(
                f"recharge protocol refused HTTP redirect ({exc.code}); "
                "Authorization and ticket are never replayed across redirects"
            ) from exc
        raw = _read_http_error_body(exc)
        parsed = _parse_json_object(raw)
        return int(exc.code), parsed, raw


def _http_bytes(
    url: str,
    *,
    timeout: float = 60.0,
    urlopen: Callable[..., Any] | None = None,
) -> bytes:
    opener = urlopen or _default_urlopen
    request = urllib.request.Request(
        url,
        headers={"Accept": "image/png,application/octet-stream", "User-Agent": "akasha-recharge/1.1"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            return response.read(8 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        _read_http_error_body(exc, 64 * 1024)
        if 300 <= code < 400:
            raise AkashaRechargeError(
                f"recharge QR download refused HTTP redirect ({code})"
            ) from exc
        raise AkashaRechargeError(f"failed to download recharge QR image: HTTP {code}") from exc
    except urllib.error.URLError as exc:
        raise AkashaRechargeError("failed to download recharge QR image: network error") from exc


def _session_from_payload(
    payload: dict[str, Any],
    session_endpoint: str,
    *,
    allow_http: bool = False,
) -> RechargeSessionView:
    public_id = payload.get("publicId") or payload.get("public_id")
    if not isinstance(public_id, str) or not public_id.strip():
        raise AkashaRechargeError("recharge session response missing publicId")
    public_id = public_id.strip()
    status = str(payload.get("status") or "").strip().upper()
    if not status:
        raise AkashaRechargeError("recharge session response missing status")
    face = payload.get("faceValueUsdCent", payload.get("face_value_usd_cent"))
    if isinstance(face, bool) or not isinstance(face, int):
        face = DEFAULT_FACE_VALUE_USD_CENT
    currency = payload.get("currency") or "USD"
    if not isinstance(currency, str) or not currency.strip():
        currency = "USD"
    expire_time = payload.get("expireTime", payload.get("expire_time"))
    public_page_url = str(payload.get("publicPageUrl") or payload.get("public_page_url") or "")
    qr_png_url = str(payload.get("qrPngUrl") or payload.get("qr_png_url") or "")
    if public_page_url:
        _require_https_url(public_page_url, "publicPageUrl", allow_http=allow_http)
    if qr_png_url:
        _require_https_url(qr_png_url, "qrPngUrl", allow_http=allow_http)
    status_url = session_endpoint.rstrip("/") + "/" + urllib.parse.quote(public_id, safe="")
    _require_https_url(status_url, "statusUrl", allow_http=allow_http)
    return RechargeSessionView(
        public_id=public_id,
        status=status,
        face_value_usd_cent=face,
        currency=currency.strip(),
        expire_time=expire_time,
        public_page_url=public_page_url,
        status_url=status_url,
        qr_png_url=qr_png_url,
    )


def _download_qr_png(
    qr_url: str,
    public_id: str,
    qr_parent_dir: str | Path | None,
    urlopen: Callable[..., Any] | None,
    *,
    allow_http: bool = False,
) -> str:
    if not qr_url:
        raise AkashaRechargeError("recharge session missing qrPngUrl")
    _require_https_url(qr_url, "qrPngUrl", allow_http=allow_http)
    parent = Path(qr_parent_dir) if qr_parent_dir is not None else Path(tempfile.mkdtemp(prefix="akasha-recharge-"))
    parent.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in public_id)[:80] or "session"
    target = parent / f"akasha-recharge-{safe_id}.png"
    if target.exists():
        raise AkashaRechargeError(f"refusing to overwrite existing QR file: {target}")
    data = _http_bytes(qr_url, urlopen=urlopen)
    if not data:
        raise AkashaRechargeError("recharge QR image is empty")
    if not data.startswith(PNG_SIGNATURE):
        raise AkashaRechargeError("recharge QR image is not a PNG")
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".part", dir=str(parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return str(target.resolve())


def _safe_links(session: RechargeSessionView | None) -> str:
    if session is None:
        return "publicPageUrl=<none> statusUrl=<none>"
    return (
        f"publicPageUrl={session.public_page_url or '<none>'} "
        f"statusUrl={session.status_url or '<none>'}"
    )


def perform_recharge(
    *,
    api_key: str,
    base_url: str,
    face_value_usd_cent: int,
    ticket_endpoint: str = DEFAULT_TICKET_ENDPOINT,
    poll_interval: float = 2.0,
    poll_timeout: float = 900.0,
    qr_parent_dir: str | Path | None = None,
    event_file: TextIO | None = None,
    urlopen: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    request_timeout: float = 60.0,
    ticket_base_url: str | None = None,
    allow_non_official_base: bool = False,
    allow_http_endpoints: bool = False,
) -> RechargeSessionView:
    """Issue ticket, create session, download QR, poll until SUCCEEDED or stop.

    allow_http_endpoints / ticket_base_url are test-only injections. Production
    callers must leave them at defaults so official HTTPS is enforced.
    """
    if not allow_non_official_base and not is_official_newapi_base_url(base_url):
        raise AkashaRechargeError("automatic recharge is only available on the official LovBrowser new-api")
    if not isinstance(api_key, str) or not api_key.strip():
        raise AkashaRechargeError("missing API key for recharge ticket request")
    if (
        not isinstance(face_value_usd_cent, int)
        or isinstance(face_value_usd_cent, bool)
        or face_value_usd_cent < MIN_FACE_VALUE_USD_CENT
        or face_value_usd_cent > MAX_FACE_VALUE_USD_CENT
    ):
        raise AkashaRechargeError("recharge face value cents out of allowed range")

    ticket_url = _ticket_url(ticket_endpoint, ticket_base_url=ticket_base_url)
    if not allow_http_endpoints:
        _require_https_url(ticket_url, "ticket URL", allow_http=False)
        # Production ticket host must remain official.
        host = urllib.parse.urlsplit(ticket_url).hostname or ""
        if host.lower() != OFFICIAL_NEWAPI_HOST:
            raise AkashaRechargeError("ticket requests are only allowed against the official new-api origin")

    status, ticket_payload, _raw = _http_json(
        "POST",
        ticket_url,
        headers={"Authorization": f"Bearer {api_key.strip()}"},
        payload={"face_value_usd_cent": face_value_usd_cent},
        timeout=request_timeout,
        urlopen=urlopen,
    )
    if status >= 400 or not ticket_payload:
        raise AkashaRechargeError(
            f"failed to issue recharge ticket: {_safe_status_detail(status, ticket_payload)}"
        )
    ticket = ticket_payload.get("ticket")
    session_endpoint = ticket_payload.get("lovbrowser_session_endpoint")
    if not isinstance(ticket, str) or not ticket.strip():
        raise AkashaRechargeError("recharge ticket response missing ticket")
    if not isinstance(session_endpoint, str) or not session_endpoint.strip():
        raise AkashaRechargeError("recharge ticket response missing lovbrowser_session_endpoint")
    session_endpoint = session_endpoint.strip()
    _require_https_url(session_endpoint, "lovbrowser_session_endpoint", allow_http=allow_http_endpoints)

    # Session create: ticket only — never send API key / Authorization.
    status, session_payload, _raw = _http_json(
        "POST",
        session_endpoint,
        payload={"ticket": ticket},
        timeout=request_timeout,
        urlopen=urlopen,
    )
    # Drop ticket reference ASAP; never log it.
    del ticket
    if _looks_like_enterprise_rejection(status, session_payload):
        raise AkashaRechargeError(
            "LovBrowser 拒绝企业成员 Key 自助充值（enterprise member key cannot create a personal "
            "recharge session）。请联系企业管理员分配额度 / contact your organization admin to allocate quota."
        )
    if status >= 400 or not session_payload:
        raise AkashaRechargeError(
            f"failed to create recharge session: {_safe_status_detail(status, session_payload)}"
        )

    view = _session_from_payload(session_payload, session_endpoint, allow_http=allow_http_endpoints)
    view.qr_png_path = _download_qr_png(
        view.qr_png_url,
        view.public_id,
        qr_parent_dir,
        urlopen,
        allow_http=allow_http_endpoints,
    )
    event = build_recharge_event(
        public_id=view.public_id,
        status=view.status,
        face_value_usd_cent=view.face_value_usd_cent,
        currency=view.currency,
        expire_time=view.expire_time,
        qr_png_path=view.qr_png_path,
        public_page_url=view.public_page_url,
        status_url=view.status_url,
    )
    emit_recharge_event(event, file=event_file)
    print(
        f"AKASHA_RECHARGE status={view.status} publicId={view.public_id} "
        f"qrPngPath={view.qr_png_path} publicPageUrl={view.public_page_url} "
        f"statusUrl={view.status_url}",
        file=event_file if event_file is not None else sys.stderr,
        flush=True,
    )

    deadline = monotonic() + max(poll_timeout, 0.1)
    while True:
        if view.status == _TERMINAL_SUCCESS:
            return view
        if view.status in _TERMINAL_FAILURE:
            raise AkashaRechargeError(
                f"recharge session ended with status={view.status}; {_safe_links(view)}"
            )
        if monotonic() >= deadline:
            raise AkashaRechargeError(
                f"recharge session timed out while status={view.status}; {_safe_links(view)}"
            )
        sleep(max(poll_interval, 0.01))
        status, polled, _raw = _http_json(
            "GET",
            view.status_url,
            timeout=request_timeout,
            urlopen=urlopen,
        )
        if status >= 400 or not polled:
            raise AkashaRechargeError(
                f"recharge status poll failed: {_safe_status_detail(status, polled)}; "
                f"{_safe_links(view)}"
            )
        view = _session_from_payload(polled, session_endpoint, allow_http=allow_http_endpoints)
        view.qr_png_path = event["qrPngPath"]  # type: ignore[assignment]
        progress = build_recharge_event(
            public_id=view.public_id,
            status=view.status,
            face_value_usd_cent=view.face_value_usd_cent,
            currency=view.currency,
            expire_time=view.expire_time,
            qr_png_path=view.qr_png_path,
            public_page_url=view.public_page_url,
            status_url=view.status_url,
        )
        emit_recharge_event(progress, file=event_file)


@dataclass
class RechargeController:
    """Command-scoped recharge budget: at most one ticket/session per CLI run."""

    api_key: str
    base_url: str
    cli_recharge_usd: str | float | int | None = None
    poll_interval: float = 2.0
    poll_timeout: float = 900.0
    qr_parent_dir: str | Path | None = None
    event_file: TextIO | None = None
    urlopen: Callable[..., Any] | None = None
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    request_timeout: float = 60.0
    ticket_base_url: str | None = None
    allow_non_official_base: bool = False
    allow_http_endpoints: bool = False
    _recharge_attempted: bool = field(default=False, init=False, repr=False)
    _session: RechargeSessionView | None = field(default=None, init=False, repr=False)

    def run(self, operation: Callable[[], T]) -> T:
        """Execute operation with command-level single recharge budget."""
        try:
            return operation()
        except InsufficientUserQuotaError as first:
            return self._handle_quota(operation, first)

    def _handle_quota(self, operation: Callable[[], T], first: InsufficientUserQuotaError) -> T:
        if self._recharge_attempted:
            raise AkashaRechargeError(
                "余额不足且本命令已完成过一次自动充值，已停止且不会再次签票或创建会话 "
                "(quota still insufficient after the single command-level recharge). "
                f"{_safe_links(self._session)}"
            ) from first
        if not self.allow_non_official_base and not is_official_newapi_base_url(self.base_url):
            raise first
        # Mark budget consumed before side effects so concurrent failures cannot double-pay.
        self._recharge_attempted = True
        # Env amount is resolved only at real trigger time so private/non-quota paths
        # are unaffected by invalid AKASHA_RECHARGE_USD.
        face_value_usd_cent = resolve_face_value_usd_cent(self.cli_recharge_usd, use_env=True)
        self._session = perform_recharge(
            api_key=self.api_key,
            base_url=self.base_url,
            face_value_usd_cent=face_value_usd_cent,
            ticket_endpoint=first.hint.ticket_endpoint,
            poll_interval=self.poll_interval,
            poll_timeout=self.poll_timeout,
            qr_parent_dir=self.qr_parent_dir,
            event_file=self.event_file,
            urlopen=self.urlopen,
            sleep=self.sleep,
            monotonic=self.monotonic,
            request_timeout=self.request_timeout,
            ticket_base_url=self.ticket_base_url,
            allow_non_official_base=self.allow_non_official_base,
            allow_http_endpoints=self.allow_http_endpoints,
        )
        try:
            return operation()
        except InsufficientUserQuotaError as second:
            raise AkashaRechargeError(
                "余额在充值入账后仍然不足，已停止自动续跑且不会再次充值 "
                "(quota still insufficient after one recharge; not retrying again). "
                f"{_safe_links(self._session)}"
            ) from second


def call_with_single_recharge(
    operation: Callable[[], T],
    *,
    base_url: str,
    api_key: str,
    face_value_usd_cent: int | None = None,
    cli_recharge_usd: str | float | int | None = None,
    controller: RechargeController | None = None,
    poll_interval: float = 2.0,
    poll_timeout: float = 900.0,
    qr_parent_dir: str | Path | None = None,
    event_file: TextIO | None = None,
    urlopen: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    request_timeout: float = 60.0,
    ticket_base_url: str | None = None,
    allow_non_official_base: bool = False,
    allow_http_endpoints: bool = False,
) -> T:
    """Backward-compatible wrapper. Prefer a shared RechargeController per command.

    If face_value_usd_cent is provided without a controller, it is treated as an
    explicit CLI-equivalent amount (env is not consulted for that call).
    """
    if controller is not None:
        return controller.run(operation)
    explicit = cli_recharge_usd
    if explicit is None and face_value_usd_cent is not None:
        # Preserve prior tests that pass cents directly.
        if face_value_usd_cent % 100 == 0:
            explicit = str(face_value_usd_cent // 100)
        else:
            explicit = f"{face_value_usd_cent / 100:.2f}"
    ctrl = RechargeController(
        api_key=api_key,
        base_url=base_url,
        cli_recharge_usd=explicit,
        poll_interval=poll_interval,
        poll_timeout=poll_timeout,
        qr_parent_dir=qr_parent_dir,
        event_file=event_file,
        urlopen=urlopen,
        sleep=sleep,
        monotonic=monotonic,
        request_timeout=request_timeout,
        ticket_base_url=ticket_base_url,
        allow_non_official_base=allow_non_official_base,
        allow_http_endpoints=allow_http_endpoints,
    )
    return ctrl.run(operation)


def raise_quota_if_applicable(
    status_code: int,
    body: bytes,
    *,
    base_url: str,
) -> None:
    """Helper for adapters: raise InsufficientUserQuotaError when recharge applies."""
    hint = detect_insufficient_user_quota(status_code, body, base_url=base_url)
    if hint is not None:
        raise InsufficientUserQuotaError(status_code, body, hint)


_STABLE_MODULE_NAME = "akasha_grimoire_shared_akasha_recharge"
# Process-level path -> module cache (identity-stable across skill entry loaders).
_PATH_MODULE_CACHE: dict[str, Any] = {}


def resolve_akasha_recharge_path(caller_file: str | Path) -> Path:
    """Locate shared/akasha_recharge.py relative to a skill script (symlink-safe)."""
    here = Path(caller_file).resolve().parent
    candidates = [
        here / "akasha_recharge.py",
        # skills/<skill>/scripts -> repo root shared/
        here.parents[3] / "shared" / "akasha_recharge.py" if len(here.parents) > 3 else Path(),
        here.parents[2] / "shared" / "akasha_recharge.py" if len(here.parents) > 2 else Path(),
        here.parents[1] / "shared" / "akasha_recharge.py" if len(here.parents) > 1 else Path(),
        Path(__file__).resolve(),
    ]
    for path in candidates:
        if path and path.is_file() and path.name == "akasha_recharge.py":
            return path.resolve()
    raise AkashaRechargeError(
        "shared akasha_recharge helper not found; install from the monorepo so "
        "shared/akasha_recharge.py is reachable via symlink resolution"
    )


def _module_file_matches(module: Any, path: Path) -> bool:
    try:
        file_value = getattr(module, "__file__", None)
        if not file_value:
            return False
        return Path(file_value).resolve() == path.resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def load_akasha_recharge_module(caller_file: str | Path | None = None):
    """Process-level singleton load of this module (exception classes stay stable).

    Skill scripts must use path-verified caching so a controller created from
    load #1 catches InsufficientUserQuotaError raised after load #2. Modules
    already registered under a colliding name are not reused unless ``__file__``
    matches the resolved shared path for this worktree.
    """
    import importlib.util

    if caller_file is None:
        path = Path(__file__).resolve()
    else:
        path = resolve_akasha_recharge_path(caller_file)
    key = str(path)

    cached = _PATH_MODULE_CACHE.get(key)
    if cached is not None and _module_file_matches(cached, path):
        return cached

    current = sys.modules.get(__name__)
    if current is not None and _module_file_matches(current, path):
        _PATH_MODULE_CACHE[key] = current
        return current

    for existing in list(sys.modules.values()):
        if existing is None or not hasattr(existing, "RechargeController"):
            continue
        if _module_file_matches(existing, path):
            _PATH_MODULE_CACHE[key] = existing
            return existing

    stable = sys.modules.get(_STABLE_MODULE_NAME)
    if stable is not None and _module_file_matches(stable, path):
        _PATH_MODULE_CACHE[key] = stable
        return stable

    module_name = _STABLE_MODULE_NAME
    if stable is not None and not _module_file_matches(stable, path):
        module_name = f"{_STABLE_MODULE_NAME}_{abs(hash(key)) & 0xFFFFFFFF:x}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AkashaRechargeError(f"unable to load shared recharge helper from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    path_cache = getattr(module, "_PATH_MODULE_CACHE", None)
    if isinstance(path_cache, dict):
        path_cache[key] = module
    _PATH_MODULE_CACHE[key] = module
    return module


def add_recharge_argument(parser: Any, *, suppress_default: bool = False) -> None:
    """Attach unified --recharge-usd flag to an argparse parser (root or subcommand).

    When attached both to the root parser and to subcommands, subcommand parents
    should use suppress_default=True so a root-level value is not overwritten by
    the subparser default of None.
    """
    import argparse

    kwargs: dict[str, Any] = {
        "dest": "recharge_usd",
        "help": (
            "USD face value for automatic official new-api recharge when balance is "
            "insufficient (default: 10, or AKASHA_RECHARGE_USD). CLI overrides env. "
            "With subcommands, place before or after the subcommand name."
        ),
    }
    if suppress_default:
        kwargs["default"] = argparse.SUPPRESS
    else:
        kwargs["default"] = None
    parser.add_argument("--recharge-usd", **kwargs)


def recharge_parent_parser() -> Any:
    """ArgumentParser parent so subcommands also accept --recharge-usd."""
    import argparse

    parent = argparse.ArgumentParser(add_help=False)
    # SUPPRESS so root-level --recharge-usd is kept when subcommand is parsed.
    add_recharge_argument(parent, suppress_default=True)
    return parent
