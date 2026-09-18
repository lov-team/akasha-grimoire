#!/usr/bin/env python3
"""Generate MiniMax H3 Max lip-sync (talking-head) videos through an asynchronous video API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAX_RESPONSE_BYTES = 256 * 1024 * 1024
DEFAULT_BASE_URL = "https://newapi.1234bot.com/v1"
SUCCESS_STATES = {"success", "succeeded", "completed"}
FAILURE_STATES = {"failure", "failed", "expired", "cancelled", "canceled"}

LIP_SYNC_MODEL = "minimax/h3-max/lip-sync/image-to-video"
LIP_SYNC_FAL_MODEL = "fal-ai/minimax/h3-max/lip-sync/image-to-video"

MODEL_ALIASES = {
    "lip-sync": LIP_SYNC_MODEL,
    "h3-lip-sync": LIP_SYNC_MODEL,
    "minimax-h3-lip-sync": LIP_SYNC_MODEL,
    LIP_SYNC_MODEL: LIP_SYNC_MODEL,
    "fal-ai/lip-sync": LIP_SYNC_FAL_MODEL,
    LIP_SYNC_FAL_MODEL: LIP_SYNC_FAL_MODEL,
}

MODEL_PROFILES = {
    LIP_SYNC_MODEL: {
        "durations": range(5, 16),
        "default_duration": 5,
        "aspect_ratios": (),
        "resolutions": ("480P", "768P", "1080P", "2K"),
        "default_resolution": "768P",
        "supports_images": True,
        "duration_as_string": False,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": True,
        "requires_audio": True,
        "max_images": 1,
        "uses_aspect_ratio": False,
        "max_references": 1,
    },
    LIP_SYNC_FAL_MODEL: {
        "durations": range(5, 16),
        "default_duration": 5,
        "aspect_ratios": (),
        "resolutions": ("480P", "768P", "1080P", "2K"),
        "default_resolution": "768P",
        "supports_images": True,
        "duration_as_string": False,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": True,
        "requires_audio": True,
        "max_images": 1,
        "uses_aspect_ratio": False,
        "max_references": 1,
    },
}


class VideoGenerationError(RuntimeError):
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
        raise VideoGenerationError(
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
        raise VideoGenerationError(
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
        raise VideoGenerationError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VideoGenerationError("base URL must not contain userinfo, query, or fragment")
    path = parsed.path.rstrip("/")
    if path.rsplit("/", 1)[-1] != "v1":
        path += "/v1"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def resolve_base_url(explicit: str | None) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    raw = credentials.resolve_base_url(
        ("MINIMAX_H3_LIP_SYNC_BASE_URL",), explicit=explicit, default=DEFAULT_BASE_URL
    )
    return normalize_base_url(raw)


def read_api_key(explicit_base_url: str | None = None, timeout: float = 10) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    try:
        found = credentials.select_credential(
            explicit_base_url=explicit_base_url,
            timeout=timeout,
        )
    except credentials.CredentialError as exc:
        raise VideoGenerationError(str(exc)) from exc
    return found.api_key


def read_response(response: object) -> tuple[bytes, str]:
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise VideoGenerationError("endpoint response exceeds 256 MiB")
    return data, response.headers.get("Content-Type", "")


def request(
    base_url: str,
    api_key: str,
    path: str,
    timeout: float,
    payload: dict | None = None,
    *,
    controller: Any | None = None,
) -> tuple[bytes, str]:
    recharge = _load_akasha_recharge()
    body = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "akasha-minimax-h3-lip-sync/1.0",
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    http_request = urllib.request.Request(
        base_url + path,
        data=body,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )

    def once() -> tuple[bytes, str]:
        try:
            with urllib.request.urlopen(http_request, timeout=timeout) as response:
                return read_response(response)
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
                error = parsed.get("error")
                if isinstance(error, dict):
                    message = str(error.get("message") or "")
                message = message or str(parsed.get("message") or "")
            except (json.JSONDecodeError, AttributeError):
                pass
            raise VideoGenerationError(f"HTTP {exc.code}: {message or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise VideoGenerationError(f"request failed: {exc.reason}") from exc

    if controller is None:
        controller = recharge.RechargeController(
            api_key=api_key,
            base_url=base_url,
            request_timeout=timeout,
        )
    try:
        return controller.run(once)
    except recharge.AkashaRechargeError as exc:
        raise VideoGenerationError(str(exc)) from exc


def parse_json(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VideoGenerationError("endpoint returned non-JSON data") from exc
    if not isinstance(value, dict):
        raise VideoGenerationError("endpoint returned an unexpected JSON shape")
    return value


def task_id_from(response: dict) -> str:
    data = response.get("data")
    nested = data if isinstance(data, dict) else {}
    value = response.get("task_id") or response.get("id") or response.get("request_id") or nested.get("task_id")
    if not isinstance(value, str) or not value.strip():
        raise VideoGenerationError("task submission returned no task ID")
    return value.strip()


def task_state(response: dict) -> tuple[str, str]:
    data = response.get("data")
    nested = data if isinstance(data, dict) else {}
    state = str(nested.get("status") or response.get("status") or "").strip().lower()
    error = response.get("error")
    message = nested.get("fail_reason") or response.get("message") or ""
    if isinstance(error, dict):
        message = error.get("message") or message
    return state, str(message)


def wait_for_task(
    base_url: str,
    api_key: str,
    task_id: str,
    request_timeout: float,
    poll_timeout: float,
    poll_interval: float,
    controller: Any,
) -> None:
    deadline = time.monotonic() + poll_timeout
    quoted_id = urllib.parse.quote(task_id, safe="")
    while True:
        response = parse_json(
            request(
                base_url,
                api_key,
                f"/video/generations/{quoted_id}",
                request_timeout,
                controller=controller,
            )[0]
        )
        state, message = task_state(response)
        if state in SUCCESS_STATES:
            return
        if state in FAILURE_STATES:
            raise VideoGenerationError(f"video task {state}: {message or 'upstream returned no reason'}")
        if time.monotonic() >= deadline:
            raise VideoGenerationError(f"video task did not finish within {poll_timeout:g} seconds")
        time.sleep(poll_interval)


def validate_public_https_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError("reference media must use an absolute public HTTPS URL without userinfo")
    return value


def validate_mp4(data: bytes, content_type: str) -> None:
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise VideoGenerationError(f"video result is not an MP4 (content-type={content_type or 'unknown'})")


def write_output(path: Path, data: bytes, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise VideoGenerationError(f"output already exists: {path}")
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


def resolve_model(args: argparse.Namespace) -> tuple[str, dict]:
    raw_model = args.model.strip()
    model = MODEL_ALIASES.get(raw_model.lower(), raw_model)
    metadata_refs: dict[str, Any] = {}
    if args.metadata_json:
        try:
            loaded_metadata = json.loads(args.metadata_json)
        except json.JSONDecodeError:
            loaded_metadata = {}
        if isinstance(loaded_metadata, dict):
            metadata_refs = loaded_metadata
    metadata_audio = metadata_refs.get("audio_url")
    profile = MODEL_PROFILES.get(model)
    if profile is None:
        supported = ", ".join(MODEL_PROFILES)
        raise VideoGenerationError(f"unsupported video model: {raw_model}; choose one of: {supported}")

    if profile["requires_images"] and not args.image:
        raise VideoGenerationError(f"{model} requires a --image reference frame")
    if len(args.image) > profile["max_images"]:
        raise VideoGenerationError(
            f"{model} accepts at most {profile['max_images']} --image value (one talking-head portrait)"
        )
    if profile.get("requires_audio") and not (args.audio or metadata_audio):
        raise VideoGenerationError(f"{model} requires --audio or metadata.audio_url")
    if args.resolution and args.resolution not in profile["resolutions"]:
        allowed = ", ".join(profile["resolutions"]) or "not configurable"
        raise VideoGenerationError(f"{model} resolution must be one of: {allowed}")
    return model, profile


def metadata_from(args: argparse.Namespace, model: str, profile: dict) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if args.metadata_json:
        try:
            loaded = json.loads(args.metadata_json)
        except json.JSONDecodeError as exc:
            raise VideoGenerationError(f"--metadata-json is invalid JSON: {exc.msg}") from exc
        if not isinstance(loaded, dict):
            raise VideoGenerationError("--metadata-json must decode to an object")
        metadata.update(loaded)

    resolution = args.resolution or profile["default_resolution"]
    if resolution:
        metadata["resolution"] = resolution
    if args.seed is not None:
        metadata["seed"] = args.seed
    if args.no_transcription:
        metadata["enable_transcription"] = False
    if args.no_safety_checker:
        metadata["enable_safety_checker"] = False
    if args.image:
        metadata["image_url"] = args.image[0]
    if args.audio:
        metadata["audio_url"] = args.audio
        # Lets the server resolve the real audio duration for billing
        # estimates; the upstream call itself uses audio_url only.
        metadata["reference_audio_urls"] = [args.audio]
    return metadata


def run_generate(args: argparse.Namespace) -> None:
    base_url = resolve_base_url(args.base_url)
    api_key = read_api_key(base_url, args.timeout)
    recharge = _load_akasha_recharge()
    recharge.validate_cli_recharge_usd(getattr(args, "recharge_usd", None))
    controller = recharge.RechargeController(
        api_key=api_key,
        base_url=base_url,
        cli_recharge_usd=getattr(args, "recharge_usd", None),
        request_timeout=args.timeout,
    )
    model, profile = resolve_model(args)
    metadata = metadata_from(args, model, profile)
    payload = {
        "model": model,
        "metadata": metadata,
        "images": args.image,
        "audio_url": args.audio,
    }
    response = parse_json(
        request(
            base_url,
            api_key,
            "/video/generations",
            args.timeout,
            payload,
            controller=controller,
        )[0]
    )
    task_id = task_id_from(response)
    wait_for_task(
        base_url,
        api_key,
        task_id,
        args.timeout,
        args.poll_timeout,
        args.poll_interval,
        controller,
    )
    raw, content_type = request(
        base_url,
        api_key,
        f"/videos/{urllib.parse.quote(task_id, safe='')}/content",
        args.download_timeout,
        controller=controller,
    )
    validate_mp4(raw, content_type)
    output = Path(args.output).expanduser().resolve()
    write_output(output, raw, args.overwrite)
    print(f"OK task_id={task_id} output={output} bytes={len(raw)}")


def build_parser() -> argparse.ArgumentParser:
    recharge = _load_akasha_recharge()
    recharge_parent = recharge.recharge_parent_parser()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        help=f"OpenAI-compatible host or /v1 API root (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument("--timeout", type=float, default=30)
    recharge.add_recharge_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", parents=[recharge_parent])
    generate.add_argument(
        "--model",
        default=LIP_SYNC_MODEL,
        help=f"model ID or alias (default: {LIP_SYNC_MODEL})",
    )
    generate.add_argument("--image", required=True, action="append", default=[], type=validate_public_https_url,
                          help="public HTTPS portrait image (aspect ratio 0.4-2.5)")
    generate.add_argument("--audio", required=True, type=validate_public_https_url,
                          help="public HTTPS audio at least 5s; output length follows the audio, clipped at 15s")
    generate.add_argument("--resolution", choices=("480P", "768P", "1080P", "2K"), default="768P")
    generate.add_argument("--seed", type=int)
    generate.add_argument("--no-transcription", action="store_true", help="disable audio transcription guidance")
    generate.add_argument("--no-safety-checker", action="store_true", help="disable content safety checks")
    generate.add_argument(
        "--metadata-json",
        help="advanced model-native input object; validated core fields override duplicates",
    )
    generate.add_argument("--poll-timeout", type=float, default=1800)
    generate.add_argument("--poll-interval", type=float, default=5)
    generate.add_argument("--download-timeout", type=float, default=120)
    generate.add_argument("--output", required=True)
    generate.add_argument("--overwrite", action="store_true")
    generate.set_defaults(handler=run_generate)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.handler(args)
        return 0
    except (VideoGenerationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
