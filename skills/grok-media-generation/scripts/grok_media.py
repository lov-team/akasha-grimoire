#!/usr/bin/env python3
"""Generate and edit Grok images/videos through a new-api endpoint."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
DEFAULT_BASE_URL = "https://newapi.1234bot.com/v1"
TERMINAL_VIDEO_STATES = {"completed", "failed", "expired", "cancelled"}


class GrokMediaError(RuntimeError):
    pass


def _load_akasha_recharge() -> Any:
    """Process-level path-verified singleton for shared/akasha_recharge.py."""
    import importlib.util

    cache_attr = "_akasha_recharge_singleton"
    cached = globals().get(cache_attr)
    here = Path(__file__).resolve().parent
    candidates = [
        here / "akasha_recharge.py",
        here.parents[3] / "shared" / "akasha_recharge.py",
        here.parents[2] / "shared" / "akasha_recharge.py",
    ]
    path: Path | None = None
    for candidate in candidates:
        try:
            if candidate.is_file():
                path = candidate.resolve()
                break
        except OSError:
            continue
    if path is None:
        raise GrokMediaError(
            "shared akasha_recharge helper not found; install from monorepo so "
            "shared/akasha_recharge.py resolves via symlink"
        )

    def _matches(module: Any) -> bool:
        try:
            file_value = getattr(module, "__file__", None)
            return bool(file_value) and Path(file_value).resolve() == path
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    if cached is not None and _matches(cached) and hasattr(cached, "RechargeController"):
        return cached

    for existing in list(sys.modules.values()):
        if existing is None or not hasattr(existing, "RechargeController"):
            continue
        if _matches(existing):
            globals()[cache_attr] = existing
            return existing

    for existing in list(sys.modules.values()):
        loader = getattr(existing, "load_akasha_recharge_module", None)
        if callable(loader) and _matches(existing):
            module = loader(Path(__file__))
            globals()[cache_attr] = module
            return module

    stable_name = "akasha_grimoire_shared_akasha_recharge"
    stable = sys.modules.get(stable_name)
    if stable is not None and _matches(stable):
        globals()[cache_attr] = stable
        return stable
    module_name = stable_name
    if stable is not None and not _matches(stable):
        module_name = f"{stable_name}_{abs(hash(str(path))) & 0xFFFFFFFF:x}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise GrokMediaError(
            "shared akasha_recharge helper not found; install from monorepo so "
            "shared/akasha_recharge.py resolves via symlink"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    loader = getattr(module, "load_akasha_recharge_module", None)
    if callable(loader):
        module = loader(Path(__file__))
    globals()[cache_attr] = module
    return module


def normalize_base_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GrokMediaError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GrokMediaError("base URL must not contain userinfo, query, or fragment")
    path = parsed.path.rstrip("/")
    if path.rsplit("/", 1)[-1] != "v1":
        path += "/v1"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def resolve_base_url(explicit: str | None) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    raw = credentials.resolve_base_url(
        ("GROK_MEDIA_BASE_URL",), explicit=explicit, default=DEFAULT_BASE_URL
    )
    return normalize_base_url(raw)


def read_api_key() -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    found = credentials.discover_credential(("GROK_MEDIA_API_KEY",))
    if found is None:
        try:
            found = credentials.bootstrap(specialized_names=("GROK_MEDIA_API_KEY",))
        except credentials.CredentialError as exc:
            raise GrokMediaError(str(exc)) from exc
    return found.api_key


def api_request(
    base_url: str,
    api_key: str,
    path: str,
    timeout: float,
    *,
    payload: dict | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
    controller: Any | None = None,
) -> tuple[bytes, str]:
    recharge = _load_akasha_recharge()
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        content_type = "application/json"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(base_url + path, data=body, headers=headers, method="POST" if body is not None else "GET")

    def once() -> tuple[bytes, str]:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise GrokMediaError("endpoint response exceeds 256 MiB")
                return data, response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            raw = exc.read(64 * 1024)
            try:
                exc.close()
            except Exception:
                pass
            recharge.raise_quota_if_applicable(exc.code, raw, base_url=base_url)
            message = ""
            try:
                parsed = json.loads(raw)
                message = str(parsed.get("error", {}).get("message") or parsed.get("message") or "")
            except (json.JSONDecodeError, AttributeError):
                pass
            raise GrokMediaError(f"HTTP {exc.code}: {message or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise GrokMediaError(f"request failed: {exc.reason}") from exc

    if controller is None:
        controller = recharge.RechargeController(
            api_key=api_key,
            base_url=base_url,
            request_timeout=timeout,
        )
    try:
        return controller.run(once)
    except recharge.AkashaRechargeError as exc:
        raise GrokMediaError(str(exc)) from exc


def parse_json(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GrokMediaError("endpoint returned non-JSON data") from exc
    if not isinstance(value, dict):
        raise GrokMediaError("endpoint returned an unexpected JSON shape")
    return value


def multipart_image_body(model: str, prompt: str, image_path: Path) -> tuple[bytes, str]:
    if image_path.stat().st_size > MAX_DOWNLOAD_BYTES:
        raise GrokMediaError("reference image exceeds 256 MiB")
    boundary = "----grok-media-" + secrets.token_hex(16)
    chunks: list[bytes] = []
    for name, value in (("model", model), ("prompt", prompt), ("response_format", "url")):
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode(),
            b"\r\n",
        ])
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n'.encode(),
        f"Content-Type: {mime_type}\r\n\r\n".encode(),
        image_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def validate_public_https_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise GrokMediaError("video URL must be an absolute public HTTPS URL without userinfo")


def download_public_url(url: str, timeout: float) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise GrokMediaError("media URL must be an absolute HTTP(S) URL without userinfo")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
    except urllib.error.URLError as exc:
        raise GrokMediaError(f"media download failed: {exc.reason}") from exc
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise GrokMediaError("media download exceeds 256 MiB")
    return data


def image_bytes(response: dict, timeout: float) -> bytes:
    data = response.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise GrokMediaError("image response does not contain data[0]")
    item = data[0]
    encoded = item.get("b64_json")
    if isinstance(encoded, str) and encoded:
        try:
            return base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise GrokMediaError("image response contains invalid b64_json") from exc
    url = item.get("url")
    if isinstance(url, str) and url:
        return download_public_url(url, timeout)
    raise GrokMediaError("image response contains neither url nor b64_json")


def validate_image(data: bytes) -> None:
    is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = data.startswith(b"\xff\xd8\xff")
    is_gif = data.startswith((b"GIF87a", b"GIF89a"))
    is_webp = len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if not any((is_png, is_jpeg, is_gif, is_webp)):
        raise GrokMediaError("image result does not have a supported image signature")


def validate_video(data: bytes) -> None:
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise GrokMediaError("video result does not have an MP4 signature")


def write_output(path: Path, data: bytes, overwrite: bool) -> None:
    if not data:
        raise GrokMediaError("refusing to write an empty output")
    if path.exists() and not overwrite:
        raise GrokMediaError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def wait_for_video(
    base_url: str,
    api_key: str,
    task_id: str,
    request_timeout: float,
    poll_timeout: float,
    poll_interval: float,
    controller: Any,
) -> dict:
    deadline = time.monotonic() + poll_timeout
    while True:
        response = parse_json(
            api_request(
                base_url,
                api_key,
                f"/videos/{urllib.parse.quote(task_id, safe='')}",
                request_timeout,
                controller=controller,
            )[0]
        )
        state = str(response.get("status") or "").lower()
        if state in TERMINAL_VIDEO_STATES:
            if state != "completed":
                error = response.get("error") or {}
                message = error.get("message") if isinstance(error, dict) else ""
                raise GrokMediaError(f"video task {state}: {message or 'no error message'}")
            return response
        if time.monotonic() >= deadline:
            raise GrokMediaError(f"video task did not complete within {poll_timeout:g} seconds")
        time.sleep(poll_interval)


def run(args: argparse.Namespace) -> None:
    api_key = read_api_key()
    base_url = resolve_base_url(args.base_url)
    recharge = _load_akasha_recharge()
    recharge.validate_cli_recharge_usd(getattr(args, "recharge_usd", None))
    controller = recharge.RechargeController(
        api_key=api_key,
        base_url=base_url,
        cli_recharge_usd=getattr(args, "recharge_usd", None),
        request_timeout=args.timeout,
    )
    output = Path(args.output).expanduser().resolve()

    if args.command == "image-generate":
        payload = {"model": args.model, "prompt": args.prompt, "n": 1, "size": args.size, "response_format": "url"}
        response = parse_json(
            api_request(
                base_url,
                api_key,
                "/images/generations",
                args.timeout,
                payload=payload,
                controller=controller,
            )[0]
        )
        media = image_bytes(response, args.timeout)
        validate_image(media)
        write_output(output, media, args.overwrite)
    elif args.command == "image-edit":
        image_path = Path(args.image).expanduser().resolve()
        if not image_path.is_file():
            raise GrokMediaError(f"reference image not found: {image_path}")
        body, content_type = multipart_image_body(args.model, args.prompt, image_path)
        response = parse_json(
            api_request(
                base_url,
                api_key,
                "/images/edits",
                args.timeout,
                body=body,
                content_type=content_type,
                controller=controller,
            )[0]
        )
        media = image_bytes(response, args.timeout)
        validate_image(media)
        write_output(output, media, args.overwrite)
    else:
        if args.command == "video-generate":
            path = "/videos/generations"
            payload = {"model": args.model, "prompt": args.prompt, "duration": args.duration}
        else:
            path = "/videos/edits"
            if args.video_url:
                validate_public_https_url(args.video_url)
            video_input = {"file_id": args.video_file_id} if args.video_file_id else {"url": args.video_url}
            payload = {"model": args.model, "prompt": args.prompt, "video": video_input}
        submitted = parse_json(
            api_request(
                base_url,
                api_key,
                path,
                args.timeout,
                payload=payload,
                controller=controller,
            )[0]
        )
        task_id = submitted.get("request_id") or submitted.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise GrokMediaError("video submit response does not contain request_id")
        wait_for_video(
            base_url,
            api_key,
            task_id,
            args.timeout,
            args.poll_timeout,
            args.poll_interval,
            controller,
        )
        content_path = f"/videos/{urllib.parse.quote(task_id, safe='')}/content"
        video, _ = api_request(
            base_url,
            api_key,
            content_path,
            args.timeout,
            controller=controller,
        )
        validate_video(video)
        write_output(output, video, args.overwrite)
        print(f"task_id={task_id}")

    print(f"OK output={output} bytes={output.stat().st_size}")


def parser() -> argparse.ArgumentParser:
    recharge = _load_akasha_recharge()
    recharge_parent = recharge.recharge_parent_parser()
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument(
        "--base-url",
        help=f"new-api host or /v1 API root (default: {DEFAULT_BASE_URL})",
    )
    root.add_argument("--timeout", type=float, default=180, help="per-request timeout in seconds")
    recharge.add_recharge_argument(root)
    subparsers = root.add_subparsers(dest="command", required=True)

    def common_media(command: str, *, video: bool) -> argparse.ArgumentParser:
        sub = subparsers.add_parser(command, parents=[recharge_parent])
        sub.add_argument("--prompt", required=True)
        sub.add_argument("--output", required=True)
        sub.add_argument("--overwrite", action="store_true")
        if video:
            sub.add_argument("--model", default="grok-imagine-video")
            sub.add_argument("--poll-timeout", type=float, default=600)
            sub.add_argument("--poll-interval", type=float, default=5)
        else:
            sub.add_argument("--model", default="grok-imagine-image")
        return sub

    image_generate = common_media("image-generate", video=False)
    image_generate.add_argument("--size", default="1024x1024")
    image_edit = common_media("image-edit", video=False)
    image_edit.add_argument("--image", required=True)
    video_generate = common_media("video-generate", video=True)
    video_generate.add_argument("--duration", type=int, default=4)
    video_edit = common_media("video-edit", video=True)
    video_source = video_edit.add_mutually_exclusive_group(required=True)
    video_source.add_argument("--video-url")
    video_source.add_argument("--video-file-id")
    return root


def main() -> int:
    try:
        args = parser().parse_args()
        if args.timeout <= 0:
            raise GrokMediaError("timeout must be positive")
        if hasattr(args, "poll_timeout") and (args.poll_timeout <= 0 or args.poll_interval <= 0):
            raise GrokMediaError("poll timeout and interval must be positive")
        if getattr(args, "duration", 1) <= 0:
            raise GrokMediaError("duration must be positive")
        run(args)
        return 0
    except GrokMediaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
