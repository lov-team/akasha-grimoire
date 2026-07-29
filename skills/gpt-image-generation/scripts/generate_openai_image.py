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
DEFAULT_BASE_URL = "https://newapi.1234bot.com/v1"
RESPONSE_FORMAT = "b64_json"
MAX_EDIT_IMAGES = 5
MAX_GENERATION_IMAGES = 10


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _api_key() -> str:
    return (
        os.environ.get("IMAGE_PROXY_API_KEY")
        or os.environ.get("NEW_API_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )


def _base_url() -> str:
    return (
        os.environ.get("IMAGE_PROXY_BASE_URL")
        or os.environ.get("NEW_API_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    )


def _missing_key_message() -> str:
    return (
        "missing API key. Get started with LovBrowser:\n"
        "1. Visit https://lovbrowser.com and register or sign in.\n"
        "2. Choose a plan or top up your balance and complete payment.\n"
        "3. Create a new-api key in the console.\n"
        "4. Set NEW_API_API_KEY, then run this command again.\n"
        "Default API: https://newapi.1234bot.com/v1. Never commit your key."
    )


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


def _json_body(args: argparse.Namespace) -> bytes:
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "n": args.n,
        "size": args.size,
        "response_format": RESPONSE_FORMAT,
    }
    return json.dumps(payload).encode("utf-8")


def _multipart_body(args: argparse.Namespace) -> tuple[bytes, str]:
    image_values = [args.image] if isinstance(args.image, str) else list(args.image or [])
    if not image_values:
        raise SystemExit("provide at least one --image for image edits")
    if len(image_values) > MAX_EDIT_IMAGES:
        raise SystemExit(f"image edits support at most {MAX_EDIT_IMAGES} reference images")

    image_paths = [Path(value).expanduser().resolve() for value in image_values]
    for image_path in image_paths:
        if not image_path.is_file():
            raise SystemExit(f"image file does not exist: {image_path}")

    boundary = f"----gpt-image-{uuid.uuid4().hex}"
    fields = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "response_format": RESPONSE_FORMAT,
    }
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    image_field = "image" if len(image_paths) == 1 else "image[]"
    for image_path in image_paths:
        content_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{image_field}"; filename="{image_path.name}"\r\n'
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
        raise SystemExit(_missing_key_message())

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


def _summarize_success(
    data: dict[str, Any], elapsed: float, expected_items: int
) -> list[dict[str, Any]]:
    if "created" not in data:
        raise SystemExit(f"missing created field; response_keys={sorted(data.keys())}")
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise SystemExit(f"missing non-empty data array; response_keys={sorted(data.keys())}")
    if len(items) != expected_items:
        raise SystemExit(f"requested {expected_items} image(s), received {len(items)}")

    results: list[dict[str, Any]] = []
    encoded_lengths: list[int] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"data item {index} is not an object")
        value = item.get("b64_json")
        if not isinstance(value, str) or not value:
            raise SystemExit(
                "provider did not honor requested b64_json response format; "
                f"item={index} data_fields={sorted(item.keys())}"
            )
        results.append(item)
        encoded_lengths.append(len(value))

    print(f"OK status=200 elapsed={elapsed:.1f}s items={len(items)}")
    print(f"created={data.get('created')}")
    print(f"b64_lengths={','.join(str(length) for length in encoded_lengths)}")
    return results


def _save_results(
    results: list[dict[str, Any]], output_value: str, overwrite: bool
) -> list[Path]:
    output_path = Path(output_value).expanduser().resolve()
    if len(results) == 1:
        output_paths = [output_path]
    else:
        output_paths = [
            output_path.with_name(f"{output_path.stem}-{index}{output_path.suffix}")
            for index in range(1, len(results) + 1)
        ]

    existing_paths = [path for path in output_paths if path.exists()]
    if existing_paths and not overwrite:
        raise SystemExit(
            "output already exists; pass --overwrite to replace it: "
            + ", ".join(str(path) for path in existing_paths)
        )

    decoded_results: list[bytes] = []
    for index, result in enumerate(results, start=1):
        try:
            image_bytes = base64.b64decode(str(result["b64_json"]), validate=True)
        except Exception as exc:
            raise SystemExit(f"invalid b64_json image data at item {index}: {exc}") from exc
        if not image_bytes:
            raise SystemExit(f"generated image payload is empty at item {index}")
        decoded_results.append(image_bytes)

    temporary_paths: list[Path] = []
    try:
        for output_path, image_bytes in zip(output_paths, decoded_results):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
            temporary_path.write_bytes(image_bytes)
            temporary_paths.append(temporary_path)
        for temporary_path, output_path in zip(temporary_paths, output_paths):
            temporary_path.replace(output_path)
    finally:
        for temporary_path in temporary_paths:
            if temporary_path.exists():
                temporary_path.unlink()

    for output_path, image_bytes in zip(output_paths, decoded_results):
        print(f"saved_output={output_path} bytes={len(image_bytes)}")
    return output_paths


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
    parser.add_argument(
        "--base-url",
        help=f"new-api host or /v1 API root (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        choices=range(1, MAX_GENERATION_IMAGES + 1),
        help=f"Number of generated images (1-{MAX_GENERATION_IMAGES}); edits require 1.",
    )
    parser.add_argument("--size", default="1024x1024", choices=["auto", "1024x1024", "1536x1024", "1024x1536"])
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help=f"Optional reference image path; repeat for up to {MAX_EDIT_IMAGES} images. When set, calls /v1/images/edits.",
    )
    parser.add_argument("--output", help="Optional path for the generated image. Existing files are preserved by default.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing --output file.")
    parser.add_argument("--env-file", default=os.environ.get("IMAGE_PROXY_ENV_FILE"), help="Optional .env file to load API keys from.")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    if args.image and args.n != 1:
        parser.error("--n greater than 1 is only supported for image generations")

    _load_env_file(args.env_file)
    args.base_url = args.base_url or _base_url()
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
            results = _summarize_success(payload, elapsed, expected_items=args.n)
            if args.output:
                _save_results(results, args.output, args.overwrite)
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
