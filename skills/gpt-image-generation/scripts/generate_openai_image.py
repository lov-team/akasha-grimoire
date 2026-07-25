#!/usr/bin/env python3
"""Generate or edit images through an OpenAI-compatible GPT Image endpoint."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_PROMPT = (
    "A tiny red square app icon on a clean white background, "
    "simple vector style, no text."
)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class HttpOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        try:
            _validated_result_url(newurl)
        except SystemExit:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _api_key() -> str:
    return os.environ.get("IMAGE_PROXY_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""


def _load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise SystemExit(f"env file does not exist: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            os.environ[key] = value


def _parsed_http_url(value: str, label: str, allow_query: bool) -> urllib.parse.SplitResult:
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"invalid {label}: require an absolute HTTP(S) URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise SystemExit(f"invalid {label}: require an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise SystemExit(f"invalid {label}: userinfo is not allowed")
    if parsed.fragment:
        raise SystemExit(f"invalid {label}: fragment is not allowed")
    if parsed.query and not allow_query:
        raise SystemExit(f"invalid {label}: query is not allowed")
    return parsed


def _url(base_url: str, endpoint: str) -> str:
    if endpoint not in {"edits", "generations"}:
        raise SystemExit("invalid image endpoint")
    parsed = _parsed_http_url(base_url, "base URL", allow_query=False)
    base_path = parsed.path.rstrip("/")
    if not base_path:
        api_path = "/v1"
    elif base_path.rsplit("/", 1)[-1] == "v1":
        api_path = base_path
    else:
        api_path = f"{base_path}/v1"
    result_path = f"{api_path}/images/{endpoint}"
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc, result_path, "", ""))


def _validated_result_url(value: str) -> urllib.parse.SplitResult:
    return _parsed_http_url(value, "result URL", allow_query=True)


def _json_body(args: argparse.Namespace) -> bytes:
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "n": 1,
        "size": args.size,
        "response_format": args.response_format,
    }
    return json.dumps(payload).encode("utf-8")


def _multipart_body(args: argparse.Namespace) -> tuple[bytes, str]:
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        raise SystemExit(f"image file does not exist: {image_path}")

    boundary = f"----gpt-image-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
    fields = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "response_format": args.response_format,
    }
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        (
            f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(image_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _build_request(args: argparse.Namespace) -> urllib.request.Request:
    key = _api_key()
    if not key:
        raise SystemExit("missing API key: set IMAGE_PROXY_API_KEY or OPENAI_API_KEY")

    endpoint = "edits" if args.image else "generations"
    if args.image:
        body, content_type = _multipart_body(args)
    else:
        body = _json_body(args)
        content_type = "application/json"

    return urllib.request.Request(
        _url(args.base_url, endpoint),
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "gpt-image-generation/1.0",
        },
        method="POST",
    )


def _read_json(response_body: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(response_body.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"response is not JSON: {exc}; body_bytes={len(response_body)}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"response JSON is not an object: {type(parsed).__name__}")
    return parsed


def _summarize_success(data: dict[str, Any], elapsed: float) -> dict[str, Any]:
    if "created" not in data:
        raise SystemExit(f"missing created field; response_keys={sorted(data.keys())}")
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise SystemExit(f"missing non-empty data array; response_keys={sorted(data.keys())}")

    first = items[0]
    if not isinstance(first, dict):
        raise SystemExit("first data item is not an object")

    if "url" in first:
        raw_url = first["url"]
        if not isinstance(raw_url, str) or not raw_url:
            raise SystemExit("result URL is empty")
        parsed_url = _validated_result_url(raw_url)
        result_summary = f"first_url_host={parsed_url.hostname} first_url_length={len(raw_url)}"
    elif "b64_json" in first:
        value = first["b64_json"]
        if not isinstance(value, str) or not value:
            raise SystemExit("b64_json image data is empty")
        result_summary = f"first_b64_length={len(value)}"
    else:
        raise SystemExit("first data item has neither url nor b64_json")

    print(f"OK status=200 elapsed={elapsed:.1f}s items={len(items)}")
    print(f"created={data.get('created')}")
    print(result_summary)
    return first


def _save_result(first: dict[str, Any], output_value: str, timeout: float, overwrite: bool) -> None:
    output_path = Path(output_value).expanduser().resolve()
    if output_path.exists() and not overwrite:
        raise SystemExit(f"output already exists; pass --overwrite to replace it: {output_path}")

    if "b64_json" in first:
        try:
            image_bytes = base64.b64decode(str(first["b64_json"]), validate=True)
        except Exception as exc:
            raise SystemExit(f"invalid b64_json image data: {exc}") from exc
    else:
        result_url = first.get("url")
        if not isinstance(result_url, str) or not result_url:
            raise SystemExit("missing result URL")
        _validated_result_url(result_url)
        request = urllib.request.Request(result_url, headers={"User-Agent": "gpt-image-generation/1.0"})
        download_opener = urllib.request.build_opener(HttpOnlyRedirectHandler)
        with download_opener.open(request, timeout=timeout) as response:
            image_bytes = response.read()

    if not image_bytes:
        raise SystemExit("generated image payload is empty")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_bytes(image_bytes)
        temporary_path.replace(output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    print(f"saved_output={output_path} bytes={len(image_bytes)}")


def _one_line(value: Any, limit: int = 300) -> str:
    return " ".join(str(value).split())[:limit]


def _summarize_error_body(response_body: bytes) -> str:
    try:
        parsed = json.loads(response_body.decode("utf-8"))
    except Exception:
        return f"error_body_bytes={len(response_body)} format=non-json"

    if not isinstance(parsed, dict):
        return f"error_body_bytes={len(response_body)} json_type={type(parsed).__name__}"
    error = parsed.get("error")
    if isinstance(error, dict):
        parts = []
        for key in ("type", "code", "message"):
            if error.get(key) is not None:
                parts.append(f"{key}={_one_line(error[key])}")
        if parts:
            return "error_" + " ".join(parts)
    return f"error_body_bytes={len(response_body)} response_keys={sorted(parsed.keys())}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("IMAGE_PROXY_BASE_URL"))
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--size", default="1024x1024", choices=["auto", "1024x1024", "1536x1024", "1024x1536"])
    parser.add_argument("--response-format", default="b64_json", choices=["url", "b64_json"])
    parser.add_argument("--image", help="Optional reference image path. When set, calls /v1/images/edits.")
    parser.add_argument("--output", help="Optional path for the generated image. Existing files are preserved by default.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing --output file.")
    parser.add_argument("--env-file", default=os.environ.get("IMAGE_PROXY_ENV_FILE"), help="Optional .env file to load API keys from.")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    if not args.base_url:
        parser.error("provide --base-url or set IMAGE_PROXY_BASE_URL")

    _load_env_file(args.env_file)
    request = _build_request(args)
    opener = urllib.request.build_opener(NoRedirectHandler)
    started = time.monotonic()
    print(f"POST {request.full_url}")
    try:
        with opener.open(request, timeout=args.timeout) as response:
            elapsed = time.monotonic() - started
            body = response.read()
            payload = _read_json(body)
            if response.status < 200 or response.status >= 300:
                print(f"FAIL status={response.status} elapsed={elapsed:.1f}s")
                print(_summarize_error_body(body))
                return 1
            first = _summarize_success(payload, elapsed)
            if args.output:
                _save_result(first, args.output, args.timeout, args.overwrite)
            return 0
    except urllib.error.HTTPError as exc:
        elapsed = time.monotonic() - started
        location = exc.headers.get("Location", "")
        body = exc.read(4096)
        print(f"FAIL status={exc.code} elapsed={elapsed:.1f}s")
        if location:
            parsed_location = urllib.parse.urlparse(location)
            print(
                f"redirect_host={parsed_location.netloc or '<relative>'} "
                f"redirect_path={parsed_location.path or '/'}"
            )
        if body:
            print(_summarize_error_body(body))
        return 1
    except Exception as exc:
        elapsed = time.monotonic() - started
        print(f"FAIL error={type(exc).__name__} elapsed={elapsed:.1f}s")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
