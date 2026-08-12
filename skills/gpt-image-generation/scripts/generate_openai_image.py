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

IMAGE_EXTENSIONS = {
    "png": {".png"},
    "jpeg": {".jpg", ".jpeg"},
    "gif": {".gif"},
    "webp": {".webp"},
}
PREFERRED_IMAGE_EXTENSION = {"png": ".png", "jpeg": ".jpg", "gif": ".gif", "webp": ".webp"}


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
        raise SystemExit(
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
        raise SystemExit(
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


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _api_key(explicit_base_url: str | None = None, timeout: float = 10) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    try:
        found = credentials.select_credential(
            specialized_names=("IMAGE_PROXY_API_KEY",),
            explicit_base_url=explicit_base_url,
            timeout=timeout,
        )
    except credentials.CredentialError as exc:
        raise SystemExit(str(exc)) from exc
    return found.api_key


def _base_url() -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    return credentials.resolve_base_url(("IMAGE_PROXY_BASE_URL",), default=DEFAULT_BASE_URL)


def _missing_key_message() -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    return credentials.bootstrap_instructions()


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


def _build_request(args: argparse.Namespace, key: str | None = None) -> urllib.request.Request:
    key = key or _api_key()

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
    results: list[dict[str, Any]], output_value: str, overwrite: bool, requested_size: str = "auto"
) -> list[Path]:
    decoded_results: list[bytes] = []
    image_infos: list[tuple[str, int, int, bool]] = []
    for index, result in enumerate(results, start=1):
        try:
            image_bytes = base64.b64decode(str(result["b64_json"]), validate=True)
        except Exception as exc:
            raise SystemExit(f"invalid b64_json image data at item {index}: {exc}") from exc
        if not image_bytes:
            raise SystemExit(f"generated image payload is empty at item {index}")
        decoded_results.append(image_bytes)
        try:
            image_infos.append(_image_info(image_bytes))
        except ValueError as exc:
            raise SystemExit(f"generated image payload has an unsupported or invalid signature at item {index}: {exc}") from exc

    requested_path = Path(output_value).expanduser().resolve()
    requested_paths = (
        [requested_path]
        if len(results) == 1
        else [
            requested_path.with_name(f"{requested_path.stem}-{index}{requested_path.suffix}")
            for index in range(1, len(results) + 1)
        ]
    )
    output_paths: list[Path] = []
    for path, (image_format, _width, _height, _alpha) in zip(requested_paths, image_infos):
        valid_suffixes = IMAGE_EXTENSIONS[image_format]
        if path.suffix.lower() in valid_suffixes:
            output_paths.append(path)
            continue
        corrected = path.with_suffix(PREFERRED_IMAGE_EXTENSION[image_format])
        print(
            f"WARN output_extension_corrected requested={path} actual_format={image_format} "
            f"saved_as={corrected}"
        )
        output_paths.append(corrected)

    existing_paths = [path for path in output_paths if path.exists()]
    if existing_paths and not overwrite:
        raise SystemExit(
            "output already exists; pass --overwrite to replace it: "
            + ", ".join(str(path) for path in existing_paths)
        )

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

    for output_path, image_bytes, image_info in zip(output_paths, decoded_results, image_infos):
        image_format, width, height, alpha = image_info
        print(
            f"saved_output={output_path} bytes={len(image_bytes)} format={image_format} "
            f"pixels={width}x{height} alpha={'yes' if alpha else 'no'}"
        )
        if requested_size != "auto" and requested_size != f"{width}x{height}":
            print(
                f"WARN output_size_mismatch requested={requested_size} "
                f"actual={width}x{height} output={output_path}"
            )
    return output_paths


def _image_info(data: bytes) -> tuple[str, int, int, bool]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 26 and data[12:16] == b"IHDR":
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        color_type = data[25]
        if width <= 0 or height <= 0:
            raise ValueError("invalid PNG dimensions")
        return "png", width, height, color_type in {4, 6}

    if data.startswith(b"\xff\xd8"):
        position = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while position + 4 <= len(data):
            if data[position] != 0xFF:
                position += 1
                continue
            while position < len(data) and data[position] == 0xFF:
                position += 1
            if position >= len(data):
                break
            marker = data[position]
            position += 1
            if marker in {0xD8, 0xD9}:
                continue
            if position + 2 > len(data):
                break
            segment_length = int.from_bytes(data[position:position + 2], "big")
            if segment_length < 2 or position + segment_length > len(data):
                break
            if marker in sof_markers and segment_length >= 7:
                height = int.from_bytes(data[position + 3:position + 5], "big")
                width = int.from_bytes(data[position + 5:position + 7], "big")
                if width <= 0 or height <= 0:
                    raise ValueError("invalid JPEG dimensions")
                return "jpeg", width, height, False
            position += segment_length
        raise ValueError("JPEG dimensions not found")

    if data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        width = int.from_bytes(data[6:8], "little")
        height = int.from_bytes(data[8:10], "little")
        if width <= 0 or height <= 0:
            raise ValueError("invalid GIF dimensions")
        transparency_marker = data.find(b"\x21\xf9\x04")
        alpha = transparency_marker >= 0 and transparency_marker + 3 < len(data) and bool(data[transparency_marker + 3] & 1)
        return "gif", width, height, alpha

    if data.startswith(b"RIFF") and len(data) >= 30 and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return "webp", width, height, bool(data[20] & 0x10)
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
            if width > 0 and height > 0:
                return "webp", width, height, False
        if chunk == b"VP8L" and data[20] == 0x2F:
            width = 1 + data[21] + ((data[22] & 0x3F) << 8)
            height = 1 + ((data[22] & 0xC0) >> 6) + (data[23] << 2) + ((data[24] & 0x0F) << 10)
            return "webp", width, height, bool(data[24] & 0x10)
        raise ValueError("unsupported WebP bitstream")

    raise ValueError("expected PNG, JPEG, GIF, or WebP image data")


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
    recharge_mod = _load_akasha_recharge()
    recharge_mod.add_recharge_argument(parser)
    args = parser.parse_args()

    if args.image and args.n != 1:
        parser.error("--n greater than 1 is only supported for image generations")

    _load_env_file(args.env_file)
    api_key = _api_key(args.base_url, args.timeout)
    args.base_url = args.base_url or _base_url()
    try:
        # Explicit CLI amount only; env is resolved lazily if/when recharge triggers.
        recharge_mod.validate_cli_recharge_usd(getattr(args, "recharge_usd", None))
    except recharge_mod.AkashaRechargeError as exc:
        print(f"FAIL error=AkashaRechargeError message={_one_line(exc)}")
        return 1

    request = _build_request(args, api_key)
    opener = urllib.request.build_opener(NoRedirectHandler)
    print(f"POST {request.full_url}")
    controller = recharge_mod.RechargeController(
        api_key=api_key,
        base_url=args.base_url,
        cli_recharge_usd=getattr(args, "recharge_usd", None),
        request_timeout=args.timeout,
    )

    def once() -> int:
        started = time.monotonic()
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
                    _save_results(results, args.output, args.overwrite, requested_size=args.size)
                return 0
        except urllib.error.HTTPError as exc:
            elapsed = time.monotonic() - started
            location = exc.headers.get("Location", "")
            body = exc.read(65536)
            try:
                exc.close()
            except Exception:
                pass
            recharge_mod.raise_quota_if_applicable(exc.code, body, base_url=args.base_url)
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

    try:
        return controller.run(once)
    except recharge_mod.AkashaRechargeError as exc:
        print(f"FAIL error=AkashaRechargeError message={_one_line(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
