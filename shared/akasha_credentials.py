#!/usr/bin/env python3
"""Akasha shared credentials and LovBrowser AKASHA_DEVICE_V1 bootstrap.

Secrets are accepted only from environment, a 0600 user file, or HTTPS JSON
bodies.  They are never accepted as CLI arguments and are never included in
events, exceptions, URLs, QR payloads, or logs.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, TextIO

VERSION = "AKASHA_DEVICE_V1"
OFFICIAL_ORIGIN = "https://lovbrowser.com"
OFFICIAL_NEWAPI_BASE_URL = "https://llmapi.lovbrowser.com/v1"
START_PATH = "/api/v1/tooling/akasha-device-authorizations"
TOKEN_PATH = "/api/v1/tooling/akasha-device-token"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
STATE_TTL = 600
DEFAULT_INTERVAL = 5
MAX_HTTP_BODY = 64 * 1024
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_USER_CODE = re.compile(r"^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$")
_ACCOUNT_FLOWS = {"new_registration", "existing_login"}
_ERROR_CODES = {
    "invalid_request", "invalid_grant", "authorization_pending", "slow_down",
    "access_denied", "expired_token", "consumed", "rate_limited",
    "provisioning_failed",
}


class CredentialError(RuntimeError):
    """Sanitized user-facing bootstrap error."""


@dataclass(frozen=True)
class Credential:
    api_key: str
    base_url: str
    source: str


@dataclass(frozen=True)
class DeviceStart:
    user_code: str
    verification_uri_complete: str
    qr_png_path: Path
    expires_in: int
    interval: int


@dataclass(frozen=True)
class DeviceResult:
    credential: Credential
    account_flow: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def bootstrap_instructions() -> str:
    return (
        "No API key is configured. Run `python3 shared/akasha_credentials.py start`, "
        "open https://lovbrowser.com through the emitted device link or QR code, "
        "then run `python3 shared/akasha_credentials.py finish`."
    )


def config_dir(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = env.get("AKASHA_CONFIG_DIR", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".config" / "akasha"


def credentials_path(environ: Mapping[str, str] | None = None) -> Path:
    return config_dir(environ) / "credentials.env"


def state_path(environ: Mapping[str, str] | None = None) -> Path:
    return config_dir(environ) / "device-state.json"


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise CredentialError("Akasha credential file permissions must be 0600")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CredentialError("Akasha credential file is malformed")
        name, value = line.split("=", 1)
        if name not in {"NEW_API_API_KEY", "NEW_API_BASE_URL"} or name in values:
            raise CredentialError("Akasha credential file contains unsupported or duplicate fields")
        if not value or "\n" in value or "\r" in value:
            raise CredentialError("Akasha credential file contains an invalid value")
        values[name] = value
    return values


def discover_credential(
    specialized_names: tuple[str, ...] = (),
    *,
    environ: Mapping[str, str] | None = None,
) -> Credential | None:
    env = os.environ if environ is None else environ
    for name in (*specialized_names, "NEW_API_API_KEY"):
        value = env.get(name, "")
        if isinstance(value, str) and value.strip():
            return Credential(value.strip(), env.get("NEW_API_BASE_URL", "").strip() or OFFICIAL_NEWAPI_BASE_URL, f"env:{name}")
    stored = _read_env_file(credentials_path(env))
    if stored.get("NEW_API_API_KEY"):
        return Credential(stored["NEW_API_API_KEY"], stored.get("NEW_API_BASE_URL", OFFICIAL_NEWAPI_BASE_URL), "akasha-user-file")
    compatible = env.get("OPENAI_API_KEY", "")
    if isinstance(compatible, str) and compatible.strip():
        return Credential(compatible.strip(), env.get("OPENAI_BASE_URL", "").strip() or OFFICIAL_NEWAPI_BASE_URL, "env:OPENAI_API_KEY")
    return None


def resolve_base_url(
    specialized_names: tuple[str, ...] = (),
    *,
    explicit: str | None = None,
    default: str = OFFICIAL_NEWAPI_BASE_URL,
    environ: Mapping[str, str] | None = None,
) -> str:
    if explicit:
        return explicit
    env = os.environ if environ is None else environ
    for name in (*specialized_names, "NEW_API_BASE_URL"):
        value = env.get(name, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    stored = _read_env_file(credentials_path(env))
    if stored.get("NEW_API_BASE_URL"):
        return stored["NEW_API_BASE_URL"]
    compatible = env.get("OPENAI_BASE_URL", "")
    return compatible.strip() if isinstance(compatible, str) and compatible.strip() else default


@contextlib.contextmanager
def _locked(directory: Path):
    _ensure_private_dir(directory)
    lock = directory / ".credentials.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    _ensure_private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        os.chmod(path, mode)
        dirfd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(dirfd)
        finally: os.close(dirfd)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(name)


def save_credential(
    api_key: str,
    base_url: str,
    *,
    environ: Mapping[str, str] | None = None,
    allow_test_base: bool = False,
) -> Path:
    if not api_key or any(c in api_key for c in "\r\n\0"):
        raise CredentialError("received credential is malformed")
    if not allow_test_base:
        _require_exact_url(base_url, OFFICIAL_NEWAPI_BASE_URL, "new-api base URL")
    target = credentials_path(environ)
    with _locked(target.parent):
        if target.exists():
            _atomic_bytes(target.with_suffix(".env.bak"), target.read_bytes())
        body = f"NEW_API_API_KEY={api_key}\nNEW_API_BASE_URL={base_url}\n".encode()
        _atomic_bytes(target, body)
    return target


def rollback(*, environ: Mapping[str, str] | None = None) -> bool:
    target = credentials_path(environ)
    backup = target.with_suffix(".env.bak")
    with _locked(target.parent):
        if not backup.exists():
            return False
        current = target.read_bytes() if target.exists() else None
        _atomic_bytes(target, backup.read_bytes())
        if current is None:
            backup.unlink(missing_ok=True)
        else:
            _atomic_bytes(backup, current)
    return True


def _require_exact_url(value: str, expected: str, label: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise CredentialError(f"invalid {label}") from exc
    if value != expected or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CredentialError(f"unexpected {label}")


def _endpoint(origin: str, path: str, *, allow_test_http: bool) -> str:
    parsed = urllib.parse.urlsplit(origin)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise CredentialError("invalid bootstrap origin")
    if not allow_test_http:
        _require_exact_url(origin, OFFICIAL_ORIGIN, "bootstrap origin")
    elif parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CredentialError("invalid test bootstrap origin")
    return origin.rstrip("/") + path


def _http_json(
    method: str,
    url: str,
    payload: Mapping[str, Any] | None,
    *,
    timeout: float,
    urlopen: Callable[..., Any] | None = None,
) -> tuple[int, dict[str, Any], Mapping[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method, headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "akasha-device/1"})
    opener = urlopen or urllib.request.build_opener(_NoRedirect()).open
    try:
        response = opener(request, timeout=timeout)
        try:
            raw = response.read(MAX_HTTP_BODY + 1)
            status = int(getattr(response, "status", response.getcode()))
            headers = response.headers
        finally:
            response.close()
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            exc.close()
            raise CredentialError("bootstrap protocol refused an HTTP redirect") from None
        try:
            raw = exc.read(MAX_HTTP_BODY + 1)
            status, headers = exc.code, exc.headers
        finally:
            exc.close()
    except (OSError, TimeoutError, urllib.error.URLError):
        raise CredentialError("bootstrap network request failed") from None
    if len(raw) > MAX_HTTP_BODY:
        raise CredentialError("bootstrap response is too large")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CredentialError("bootstrap response is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise CredentialError("bootstrap response has an invalid envelope")
    return status, parsed, headers


def _envelope(status: int, payload: dict[str, Any], headers: Mapping[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    cache = headers.get("Cache-Control", "") if headers else ""
    if "no-store" not in cache.lower():
        raise CredentialError("bootstrap response is missing Cache-Control: no-store")
    if (
        set(payload) != {"code", "message", "data"}
        or payload.get("code") != status
        or not isinstance(payload.get("message"), str)
        or len(payload["message"]) > 256
    ):
        raise CredentialError("bootstrap response has an invalid envelope")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise CredentialError(f"bootstrap request failed (HTTP {status})")
    error = data.get("error")
    if error is not None and error not in _ERROR_CODES:
        raise CredentialError("bootstrap response has an invalid error code")
    if status >= 400:
        return None, error or "request_failed"
    return data, None


def _load_qr_writer():
    import importlib.util
    path = Path(__file__).with_name("qr_png.py")
    spec = importlib.util.spec_from_file_location("akasha_qr_png", path)
    if spec is None or spec.loader is None: raise CredentialError("local QR encoder is unavailable")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.write_png


def start_device_flow(
    *,
    origin: str = OFFICIAL_ORIGIN,
    timeout: float = 30,
    qr_dir: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    urlopen: Callable[..., Any] | None = None,
    now: Callable[[], float] = time.time,
    allow_test_http: bool = False,
) -> DeviceStart:
    verifier = secrets.token_urlsafe(64)[:86]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    status, payload, headers = _http_json("POST", _endpoint(origin, START_PATH, allow_test_http=allow_test_http), {"version": VERSION, "codeChallenge": challenge, "codeChallengeMethod": "S256"}, timeout=timeout, urlopen=urlopen)
    data, error = _envelope(status, payload, headers)
    if error or data is None: raise CredentialError(f"device authorization start failed: {error}")
    allowed = {"version", "deviceCode", "userCode", "verificationUri", "verificationUriComplete", "expiresIn", "interval"}
    if set(data) != allowed or data.get("version") != VERSION:
        raise CredentialError("device authorization response fields are invalid")
    device_code, user_code = data.get("deviceCode"), data.get("userCode")
    complete, verification = data.get("verificationUriComplete"), data.get("verificationUri")
    expires, interval = data.get("expiresIn"), data.get("interval")
    if not isinstance(device_code, str) or len(device_code) < 43 or len(device_code) > 128 or not _BASE64URL.fullmatch(device_code): raise CredentialError("device authorization response has an invalid device code")
    if not isinstance(user_code, str) or not _USER_CODE.fullmatch(user_code): raise CredentialError("device authorization response has an invalid user code")
    expected_verification = origin.rstrip("/") + "/akasha/device"
    expected_complete = expected_verification + "?user_code=" + user_code
    if verification != expected_verification or complete != expected_complete: raise CredentialError("device authorization response has an unexpected verification URL")
    if expires != STATE_TTL or not isinstance(interval, int) or isinstance(interval, bool) or interval < 1 or interval > 60: raise CredentialError("device authorization response has invalid timing")
    created_at = now()
    state = {"version": VERSION, "device_code": device_code, "code_verifier": verifier, "created_at": created_at, "expires_at": created_at + expires, "interval": interval, "origin": origin, "allow_test_http": allow_test_http}
    target = state_path(environ)
    with _locked(target.parent):
        _atomic_bytes(target, json.dumps(state, separators=(",", ":")).encode())
    try:
        directory = Path(qr_dir).expanduser() if qr_dir else target.parent / "qr"
        _ensure_private_dir(directory)
        qr = _load_qr_writer()(complete, directory / "akasha-device.png")
        os.chmod(qr, 0o600)
    except Exception:
        target.unlink(missing_ok=True)
        raise CredentialError("failed to create the local device QR PNG") from None
    return DeviceStart(user_code, complete, qr, expires, interval)


def _read_state(environ: Mapping[str, str] | None, now: Callable[[], float]) -> dict[str, Any]:
    path = state_path(environ)
    if not path.exists(): raise CredentialError("no active Akasha device authorization")
    if stat.S_IMODE(path.stat().st_mode) & 0o077: raise CredentialError("device state file permissions must be 0600")
    try: state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): raise CredentialError("device state is malformed") from None
    required = {"version", "device_code", "code_verifier", "created_at", "expires_at", "interval", "origin", "allow_test_http"}
    if not isinstance(state, dict) or set(state) != required or state.get("version") != VERSION: raise CredentialError("device state is malformed")
    if (
        not isinstance(state.get("device_code"), str)
        or not 43 <= len(state["device_code"]) <= 128
        or not _BASE64URL.fullmatch(state["device_code"])
        or not isinstance(state.get("code_verifier"), str)
        or not 43 <= len(state["code_verifier"]) <= 128
        or not _BASE64URL.fullmatch(state["code_verifier"])
        or not isinstance(state.get("expires_at"), (int, float))
        or isinstance(state.get("expires_at"), bool)
        or not isinstance(state.get("interval"), int)
        or isinstance(state.get("interval"), bool)
        or not 1 <= state["interval"] <= 60
        or not isinstance(state.get("origin"), str)
        or not isinstance(state.get("allow_test_http"), bool)
    ):
        raise CredentialError("device state is malformed")
    if now() >= state["expires_at"]:
        cancel(environ=environ)
        raise CredentialError("device authorization expired; start a new flow")
    return state


def cancel(*, environ: Mapping[str, str] | None = None) -> None:
    state_path(environ).unlink(missing_ok=True)
    qr = config_dir(environ) / "qr" / "akasha-device.png"
    qr.unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        qr.parent.rmdir()


def validate_credential(api_key: str, base_url: str, *, timeout: float = 30, urlopen: Callable[..., Any] | None = None, allow_test_http: bool = False) -> None:
    if not allow_test_http: _require_exact_url(base_url, OFFICIAL_NEWAPI_BASE_URL, "new-api base URL")
    request = urllib.request.Request(base_url.rstrip("/") + "/models", method="GET", headers={"Accept":"application/json", "Authorization":f"Bearer {api_key}", "User-Agent":"akasha-device/1"})
    opener = urlopen or urllib.request.build_opener(_NoRedirect()).open
    try:
        response = opener(request, timeout=timeout)
        try:
            raw = response.read(MAX_HTTP_BODY + 1)
            code = int(getattr(response, "status", response.getcode()))
        finally:
            response.close()
    except urllib.error.HTTPError as exc:
        try:
            code = exc.code; raw = exc.read(MAX_HTTP_BODY + 1)
        finally:
            exc.close()
    except (OSError, TimeoutError, urllib.error.URLError): raise CredentialError("credential validation request failed") from None
    if code != 200 or len(raw) > MAX_HTTP_BODY:
        raise CredentialError(f"credential validation failed (HTTP {code})")
    try: parsed = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError): raise CredentialError("credential validation returned invalid JSON") from None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("data"), list): raise CredentialError("credential validation returned an invalid models response")


def finish_device_flow(
    *, timeout: float = 30, poll_timeout: float = STATE_TTL,
    environ: Mapping[str, str] | None = None, urlopen: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.time,
    monotonic: Callable[[], float] = time.monotonic,
) -> DeviceResult:
    if timeout <= 0 or poll_timeout <= 0:
        raise CredentialError("device polling timeouts must be positive")
    state = _read_state(environ, now)
    deadline, interval = monotonic() + poll_timeout, state["interval"]
    sleep(interval)
    while True:
        if monotonic() >= deadline:
            cancel(environ=environ); raise CredentialError("device authorization polling timed out")
        status, payload, headers = _http_json("POST", _endpoint(state["origin"], TOKEN_PATH, allow_test_http=state["allow_test_http"]), {"version":VERSION,"grantType":GRANT_TYPE,"deviceCode":state["device_code"],"codeVerifier":state["code_verifier"]}, timeout=timeout, urlopen=urlopen)
        data, error = _envelope(status, payload, headers)
        if error == "authorization_pending": sleep(interval); continue
        if error == "slow_down": interval += 5; sleep(interval); continue
        if error in {"access_denied", "expired_token", "invalid_grant", "consumed"}:
            cancel(environ=environ); raise CredentialError(f"device authorization failed: {error}")
        if error: raise CredentialError(f"device token request failed: {error}")
        assert data is not None
        if set(data) != {"version","origin","apiKey","baseUrl","account_flow"} or data.get("version") != VERSION: raise CredentialError("device token response fields are invalid")
        _require_exact_url(data.get("origin"), OFFICIAL_ORIGIN if not state["allow_test_http"] else state["origin"], "bootstrap origin")
        base_url, api_key, flow = data.get("baseUrl"), data.get("apiKey"), data.get("account_flow")
        if state["allow_test_http"]:
            if not isinstance(base_url, str) or not base_url.startswith(state["origin"]): raise CredentialError("unexpected test new-api base URL")
        else: _require_exact_url(base_url, OFFICIAL_NEWAPI_BASE_URL, "new-api base URL")
        if not isinstance(api_key, str) or not api_key or len(api_key) > 4096 or flow not in _ACCOUNT_FLOWS: raise CredentialError("device token response is malformed")
        validate_credential(api_key, base_url, timeout=timeout, urlopen=urlopen, allow_test_http=state["allow_test_http"])
        save_credential(api_key, base_url, environ=environ, allow_test_base=state["allow_test_http"])
        cancel(environ=environ)
        return DeviceResult(Credential(api_key, base_url, "akasha-device"), flow)


def bootstrap(*, specialized_names: tuple[str, ...] = (), environ: Mapping[str, str] | None = None, event_file: TextIO | None = None) -> Credential:
    existing = discover_credential(specialized_names, environ=environ)
    if existing: return existing
    values = os.environ if environ is None else environ
    if values.get("AKASHA_DISABLE_AUTO_BOOTSTRAP") == "1":
        raise CredentialError("automatic bootstrap is disabled; " + bootstrap_instructions())
    output = event_file or sys.stderr
    started = start_device_flow(environ=environ)
    print(json.dumps({"event":"akasha.device_authorization","version":VERSION,"userCode":started.user_code,"verificationUriComplete":started.verification_uri_complete,"qrPngPath":str(started.qr_png_path),"expiresIn":started.expires_in,"interval":started.interval}, ensure_ascii=False, separators=(",", ":")), file=output, flush=True)
    print(f"AKASHA_DEVICE 请扫码或打开 {started.verification_uri_complete}，确认短码 {started.user_code}；二维码：{started.qr_png_path}", file=output, flush=True)
    try: result = finish_device_flow(environ=environ)
    except KeyboardInterrupt:
        cancel(environ=environ); raise CredentialError("device authorization cancelled") from None
    print(f"AKASHA_DEVICE_CONFIGURED source={result.credential.source} validation=/v1/models account_flow={result.account_flow}", file=output, flush=True)
    return result.credential


def status(*, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    credential = discover_credential(environ=environ)
    active = state_path(environ).exists()
    return {"configured": credential is not None, "source": credential.source if credential else None, "baseUrl": credential.base_url if credential else None, "deviceAuthorizationActive": active}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure shared Akasha new-api credentials with LovBrowser device authorization")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status"); sub.add_parser("start"); sub.add_parser("finish"); sub.add_parser("cancel"); sub.add_parser("rollback")
    args = parser.parse_args(argv)
    try:
        if args.command == "status": print(json.dumps(status(), ensure_ascii=False)); return 0
        if args.command == "start":
            started = start_device_flow(); print(json.dumps({"event":"akasha.device_authorization","version":VERSION,"userCode":started.user_code,"verificationUriComplete":started.verification_uri_complete,"qrPngPath":str(started.qr_png_path),"expiresIn":started.expires_in,"interval":started.interval}, ensure_ascii=False)); return 0
        if args.command == "finish":
            result = finish_device_flow(); print(json.dumps({"event":"akasha.device_configured","source":result.credential.source,"baseUrl":result.credential.base_url,"account_flow":result.account_flow})); return 0
        if args.command == "cancel": cancel(); print('{"event":"akasha.device_cancelled"}'); return 0
        changed = rollback(); print(json.dumps({"event":"akasha.credentials_rollback","restored":changed})); return 0
    except CredentialError as exc:
        print(f"AKASHA_CREDENTIALS_FAIL {exc}", file=sys.stderr); return 1
    except KeyboardInterrupt:
        cancel()
        print("AKASHA_CREDENTIALS_FAIL device authorization cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__": raise SystemExit(main())
