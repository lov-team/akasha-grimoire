#!/usr/bin/env python3
"""Generate Seedance videos through new-api's asynchronous task API."""

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

SEEDANCE_1_PRO_MODEL = "doubao-seedance-1-0-pro-250528"
SEEDANCE_1_LITE_T2V_MODEL = "doubao-seedance-1-0-lite-t2v-250428"
SEEDANCE_1_LITE_I2V_MODEL = "doubao-seedance-1-0-lite-i2v-250428"
SEEDANCE_1_5_PRO_MODEL = "doubao-seedance-1-5-pro-251215"
SEEDANCE_2_PRO_MODEL = "doubao-seedance-2-0-260128"
SEEDANCE_2_FAST_MODEL = "doubao-seedance-2-0-fast-260128"

MODEL_ALIASES = {
    "seedance-1.0-pro": SEEDANCE_1_PRO_MODEL,
    "seedance-1.5-pro": SEEDANCE_1_5_PRO_MODEL,
    "seedance-2": SEEDANCE_2_PRO_MODEL,
    "seedance-2-fast": SEEDANCE_2_FAST_MODEL,
}
MODEL_PROFILES = {
    SEEDANCE_1_PRO_MODEL: {
        "max_duration": 12,
        "input_mode": "either",
        "reference_media": False,
        "generate_audio": False,
    },
    SEEDANCE_1_LITE_T2V_MODEL: {
        "max_duration": 12,
        "input_mode": "text",
        "reference_media": False,
        "generate_audio": False,
    },
    SEEDANCE_1_LITE_I2V_MODEL: {
        "max_duration": 12,
        "input_mode": "image",
        "reference_media": False,
        "generate_audio": False,
    },
    SEEDANCE_1_5_PRO_MODEL: {
        "max_duration": 12,
        "input_mode": "either",
        "reference_media": False,
        "generate_audio": True,
    },
    SEEDANCE_2_PRO_MODEL: {
        "max_duration": 15,
        "input_mode": "either",
        "reference_media": True,
        "generate_audio": True,
    },
    SEEDANCE_2_FAST_MODEL: {
        "max_duration": 15,
        "input_mode": "either",
        "reference_media": True,
        "generate_audio": True,
    },
}


class SeedanceVideoError(RuntimeError):
    pass


MAX_PROMPT_FILE_BYTES = 256 * 1024


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
        raise SeedanceVideoError(
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
        raise SeedanceVideoError(
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
        raise SeedanceVideoError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SeedanceVideoError("base URL must not contain userinfo, query, or fragment")
    path = parsed.path.rstrip("/")
    if path.rsplit("/", 1)[-1] != "v1":
        path += "/v1"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def resolve_base_url(explicit: str | None) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    raw = credentials.resolve_base_url(
        ("SEEDANCE_VIDEO_BASE_URL",), explicit=explicit, default=DEFAULT_BASE_URL
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
        raise SeedanceVideoError(str(exc)) from exc
    return found.api_key


def read_response(response: object) -> tuple[bytes, str]:
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise SeedanceVideoError("endpoint response exceeds 256 MiB")
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
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
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
            raise SeedanceVideoError(f"HTTP {exc.code}: {message or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise SeedanceVideoError(f"request failed: {exc.reason}") from exc

    if controller is None:
        controller = recharge.RechargeController(
            api_key=api_key,
            base_url=base_url,
            request_timeout=timeout,
        )
    try:
        return controller.run(once)
    except recharge.AkashaRechargeError as exc:
        raise SeedanceVideoError(str(exc)) from exc


def parse_json(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SeedanceVideoError("endpoint returned non-JSON data") from exc
    if not isinstance(value, dict):
        raise SeedanceVideoError("endpoint returned an unexpected JSON shape")
    return value


def task_id_from(response: dict) -> str:
    data = response.get("data")
    nested = data if isinstance(data, dict) else {}
    value = response.get("task_id") or response.get("id") or response.get("request_id") or nested.get("task_id")
    if not isinstance(value, str) or not value.strip():
        raise SeedanceVideoError("task submission returned no task ID")
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
            raise SeedanceVideoError(f"video task {state}: {message or 'upstream returned no reason'}")
        if time.monotonic() >= deadline:
            raise SeedanceVideoError(f"video task did not finish within {poll_timeout:g} seconds")
        time.sleep(poll_interval)


def validate_public_https_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError("reference media must use an absolute public HTTPS URL without userinfo")
    return value


def validate_mp4(data: bytes, content_type: str) -> None:
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise SeedanceVideoError(f"video result is not an MP4 (content-type={content_type or 'unknown'})")


def write_output(path: Path, data: bytes, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise SeedanceVideoError(f"output already exists: {path}")
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


def build_content(args: argparse.Namespace) -> list[dict]:
    content: list[dict] = []
    for role, urls in (("first_frame", args.first_frame), ("last_frame", args.last_frame), ("reference_image", args.reference_image)):
        for url in urls:
            content.append({"type": "image_url", "role": role, "image_url": {"url": url}})
    for url in args.reference_video:
        content.append({"type": "video_url", "role": "reference_video", "video_url": {"url": url}})
    for url in args.reference_audio:
        content.append({"type": "audio_url", "role": "reference_audio", "audio_url": {"url": url}})
    return content


def resolve_prompt(args: argparse.Namespace) -> str:
    if args.prompt is not None:
        prompt = args.prompt.strip()
        if not prompt:
            raise SeedanceVideoError("prompt is empty")
        return prompt

    path = Path(args.prompt_file).expanduser()
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SeedanceVideoError(f"cannot read prompt file: {path}: {exc}") from exc
    if not path.is_file():
        raise SeedanceVideoError(f"prompt file is not a regular file: {path}")
    if size > MAX_PROMPT_FILE_BYTES:
        raise SeedanceVideoError(
            f"prompt file exceeds {MAX_PROMPT_FILE_BYTES} bytes: {path}"
        )
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise SeedanceVideoError(f"cannot read UTF-8 prompt file: {path}: {exc}") from exc
    if not prompt:
        raise SeedanceVideoError(f"prompt file is empty: {path}")
    return prompt


def resolve_model(args: argparse.Namespace) -> tuple[str, dict]:
    image_references = args.first_frame + args.last_frame + args.reference_image
    raw_model = args.model.strip()
    if raw_model in {"seedance-1.0-lite", "seedance-1-lite"}:
        model = SEEDANCE_1_LITE_I2V_MODEL if image_references else SEEDANCE_1_LITE_T2V_MODEL
    else:
        model = MODEL_ALIASES.get(raw_model, raw_model)
    profile = MODEL_PROFILES.get(model)
    if profile is None:
        supported = ", ".join(MODEL_PROFILES)
        raise SeedanceVideoError(f"unsupported Seedance model: {raw_model}; choose one of: {supported}")

    if not 4 <= args.duration <= profile["max_duration"]:
        raise SeedanceVideoError(
            f"{model} duration must be between 4 and {profile['max_duration']} seconds"
        )
    if profile["input_mode"] == "text" and image_references:
        raise SeedanceVideoError(f"{model} is text-to-video and does not accept image references")
    if profile["input_mode"] == "image" and not image_references:
        raise SeedanceVideoError(f"{model} is image-to-video and requires an image reference")
    if not profile["reference_media"] and (args.reference_video or args.reference_audio):
        raise SeedanceVideoError(f"{model} does not accept video or audio references")
    if args.generate_audio is True and not profile["generate_audio"]:
        raise SeedanceVideoError(f"{model} does not support --generate-audio")
    return model, profile


def run_generate(args: argparse.Namespace) -> None:
    prompt = resolve_prompt(args)
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
    generate_audio = args.generate_audio if args.generate_audio is not None else profile["generate_audio"]
    metadata = {
        "content": build_content(args),
        "ratio": args.ratio,
        "resolution": args.resolution,
        "duration": args.duration,
        "generate_audio": generate_audio,
        "watermark": args.watermark,
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "duration": args.duration,
        "metadata": metadata,
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
        help=f"new-api host or /v1 API root (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument("--timeout", type=float, default=30)
    recharge.add_recharge_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", parents=[recharge_parent])
    generate.add_argument(
        "--model",
        default=SEEDANCE_2_PRO_MODEL,
        help="Seedance Ark model ID or alias (seedance-1.0-pro, seedance-1.0-lite, seedance-1.5-pro, seedance-2, seedance-2-fast)",
    )
    prompt_source = generate.add_mutually_exclusive_group(required=True)
    prompt_source.add_argument("--prompt", help="inline Seedance prompt")
    prompt_source.add_argument(
        "--prompt-file",
        help="read a long Seedance director prompt from a UTF-8 text file",
    )
    generate.add_argument("--duration", type=int, default=5, metavar="SECONDS")
    generate.add_argument("--resolution", choices=("480p", "720p", "1080p", "4k"), default="720p")
    generate.add_argument("--ratio", default="16:9")
    generate.add_argument("--first-frame", action="append", default=[], type=validate_public_https_url)
    generate.add_argument("--last-frame", action="append", default=[], type=validate_public_https_url)
    generate.add_argument("--reference-image", action="append", default=[], type=validate_public_https_url)
    generate.add_argument("--reference-video", action="append", default=[], type=validate_public_https_url)
    generate.add_argument("--reference-audio", action="append", default=[], type=validate_public_https_url)
    generate.add_argument("--generate-audio", action=argparse.BooleanOptionalAction, default=None)
    generate.add_argument("--watermark", action=argparse.BooleanOptionalAction, default=False)
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
    except (SeedanceVideoError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
