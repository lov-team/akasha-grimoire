#!/usr/bin/env python3
"""Generate or edit Gemini Omni videos through new-api's asynchronous video API."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://newapi.1234bot.com/v1"
DEFAULT_MODEL = "gemini-omni-video"
MAX_RESPONSE_BYTES = 256 * 1024 * 1024
USER_AGENT = "akasha-gemini-omni-video/1.0"
SUCCESS_STATES = {"success", "succeeded", "completed"}
FAILURE_STATES = {"failure", "failed", "expired", "cancelled", "canceled", "error"}


class GeminiOmniVideoError(RuntimeError):
    pass


def _load_akasha_recharge() -> Any:
    import importlib.util

    cache_attr = "_akasha_recharge_singleton"
    cached = globals().get(cache_attr)
    here = Path(__file__).resolve().parent
    candidates = [
        here / "akasha_recharge.py",
        here.parents[3] / "shared" / "akasha_recharge.py",
        here.parents[2] / "shared" / "akasha_recharge.py",
    ]
    path = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise GeminiOmniVideoError("shared akasha_recharge helper not found")

    def matches(module: Any) -> bool:
        try:
            return Path(getattr(module, "__file__", "")).resolve() == path
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    if cached is not None and matches(cached) and hasattr(cached, "RechargeController"):
        return cached
    stable_name = "akasha_grimoire_shared_akasha_recharge"
    stable = sys.modules.get(stable_name)
    if stable is not None and matches(stable):
        globals()[cache_attr] = stable
        return stable
    module_name = stable_name if stable is None else f"{stable_name}_{abs(hash(str(path))) & 0xFFFFFFFF:x}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise GeminiOmniVideoError("failed to load shared akasha_recharge helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    loader = getattr(module, "load_akasha_recharge_module", None)
    if callable(loader):
        module = loader(Path(__file__))
    globals()[cache_attr] = module
    return module


def load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise GeminiOmniVideoError(f"env file does not exist: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("'").strip('"')


def normalize_base_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise GeminiOmniVideoError("base URL must be an absolute HTTP(S) URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GeminiOmniVideoError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GeminiOmniVideoError("base URL must not contain userinfo, query, or fragment")
    path = parsed.path.rstrip("/")
    if path.rsplit("/", 1)[-1] != "v1":
        path += "/v1"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def resolve_base_url(explicit: str | None) -> str:
    return normalize_base_url(
        explicit
        or os.environ.get("GEMINI_OMNI_VIDEO_BASE_URL")
        or os.environ.get("NEW_API_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    )


def read_api_key() -> str:
    key = (
        os.environ.get("GEMINI_OMNI_VIDEO_API_KEY")
        or os.environ.get("NEW_API_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    if not key:
        raise GeminiOmniVideoError(
            "missing API key; create a new-api key at https://lovbrowser.com, "
            "set NEW_API_API_KEY, and never commit the key"
        )
    return key


def parse_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GeminiOmniVideoError("endpoint returned non-JSON data") from exc
    if not isinstance(value, dict):
        raise GeminiOmniVideoError("endpoint returned an unexpected JSON shape")
    return value


def request(
    base_url: str,
    api_key: str,
    path: str,
    timeout: float,
    payload: dict[str, Any] | None = None,
    *,
    controller: Any,
) -> tuple[bytes, str]:
    recharge = _load_akasha_recharge()
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json, video/mp4",
        "User-Agent": USER_AGENT,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    http_request = urllib.request.Request(
        base_url + path,
        data=body,
        headers=headers,
        method="POST" if body is not None else "GET",
    )

    def once() -> tuple[bytes, str]:
        try:
            with urllib.request.urlopen(http_request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise GeminiOmniVideoError("endpoint response exceeds 256 MiB")
                return raw, response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            raw = exc.read(64 * 1024)
            try:
                exc.close()
            except Exception:
                pass
            recharge.raise_quota_if_applicable(exc.code, raw, base_url=base_url)
            message = ""
            try:
                parsed = parse_json(raw)
                error = parsed.get("error")
                if isinstance(error, dict):
                    message = str(error.get("message") or error.get("detail") or "")
                message = message or str(parsed.get("message") or parsed.get("detail") or "")
            except GeminiOmniVideoError:
                pass
            raise GeminiOmniVideoError(f"HTTP {exc.code}: {message or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise GeminiOmniVideoError(f"request failed: {exc.reason}") from exc

    try:
        return controller.run(once)
    except recharge.AkashaRechargeError as exc:
        raise GeminiOmniVideoError(str(exc)) from exc


def task_id_from(response: dict[str, Any]) -> str:
    nested = response.get("data") if isinstance(response.get("data"), dict) else {}
    value = response.get("id") or response.get("task_id") or nested.get("task_id")
    if not isinstance(value, str) or not value.strip():
        raise GeminiOmniVideoError("task submission returned no task ID")
    return value.strip()


def task_state(response: dict[str, Any]) -> tuple[str, str, Any]:
    nested = response.get("data") if isinstance(response.get("data"), dict) else {}
    state = str(response.get("status") or nested.get("status") or "unknown").strip().lower()
    progress = response.get("progress") if response.get("progress") is not None else nested.get("progress")
    error = response.get("error")
    message = response.get("reason") or nested.get("reason") or response.get("message") or ""
    if isinstance(error, dict):
        message = error.get("message") or message
    return state, str(message), progress


def wait_for_task(
    base_url: str,
    api_key: str,
    task_id: str,
    request_timeout: float,
    poll_timeout: float,
    poll_interval: float,
    controller: Any,
) -> dict[str, Any]:
    deadline = time.monotonic() + poll_timeout
    quoted_id = urllib.parse.quote(task_id, safe="")
    last_marker: tuple[str, Any] | None = None
    while True:
        response = parse_json(
            request(
                base_url,
                api_key,
                f"/videos/{quoted_id}",
                request_timeout,
                controller=controller,
            )[0]
        )
        state, message, progress = task_state(response)
        marker = (state, progress)
        if marker != last_marker:
            print(f"POLL task_id={task_id} status={state} progress={progress}")
            last_marker = marker
        if state in SUCCESS_STATES:
            return response
        if state in FAILURE_STATES:
            raise GeminiOmniVideoError(f"video task {state}: {message or 'upstream returned no reason'}")
        if time.monotonic() >= deadline:
            raise GeminiOmniVideoError(f"video task did not finish within {poll_timeout:g} seconds")
        time.sleep(poll_interval)


def validate_public_https_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise argparse.ArgumentTypeError("reference video must use a valid public HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("reference video must use an absolute public HTTPS URL without userinfo")
    if hostname.lower() == "localhost" or hostname.lower().endswith(".localhost") or hostname.lower().endswith(".local"):
        raise argparse.ArgumentTypeError("reference video host must be public")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise argparse.ArgumentTypeError("reference video host must be a public IP address")
    return value


def reference_url_from_task(response: dict[str, Any]) -> str:
    state, message, _progress = task_state(response)
    if state not in SUCCESS_STATES:
        raise GeminiOmniVideoError(
            f"reference task is not completed: status={state} reason={message or 'none'}"
        )
    model = response.get("model")
    if model is not None and model != DEFAULT_MODEL:
        raise GeminiOmniVideoError(f"reference task model is {model}, expected {DEFAULT_MODEL}")
    metadata = response.get("metadata")
    value = metadata.get("url") if isinstance(metadata, dict) else None
    if not isinstance(value, str):
        raise GeminiOmniVideoError("reference task has no metadata.url")
    try:
        return validate_public_https_url(value)
    except argparse.ArgumentTypeError as exc:
        raise GeminiOmniVideoError(str(exc)) from exc


def build_payload(args: argparse.Namespace, reference_url: str | None = None) -> dict[str, Any]:
    if args.model != DEFAULT_MODEL:
        raise GeminiOmniVideoError(f"unsupported model: {args.model}; expected {DEFAULT_MODEL}")
    if not args.prompt.strip():
        raise GeminiOmniVideoError("prompt must not be empty")
    metadata: dict[str, Any] = {
        "resolution": args.resolution,
        "aspect_ratio": args.aspect_ratio,
        "generate_audio": args.generate_audio,
    }
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.resolution,
        "metadata": metadata,
    }
    if reference_url is None:
        payload["seconds"] = str(args.duration)
        metadata["duration"] = str(args.duration)
    else:
        if (
            not math.isfinite(args.start)
            or not math.isfinite(args.end)
            or args.end <= args.start
            or args.start < 0
            or args.end > 10
            or args.end - args.start > 10
        ):
            raise GeminiOmniVideoError("reference clip must satisfy 0 <= start < end <= 10 seconds")
        metadata["video_list"] = [{"url": reference_url, "start": args.start, "ends": args.end}]
    return payload


def write_output(path: Path, data: bytes, overwrite: bool) -> None:
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise GeminiOmniVideoError("video result is not an MP4")
    if path.suffix.lower() != ".mp4":
        raise GeminiOmniVideoError("output path must use the .mp4 extension")
    if path.exists() and not overwrite:
        raise GeminiOmniVideoError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def validate_output_target(path: Path, overwrite: bool) -> None:
    if path.suffix.lower() != ".mp4":
        raise GeminiOmniVideoError("output path must use the .mp4 extension")
    if path.exists() and not overwrite:
        raise GeminiOmniVideoError(f"output already exists: {path}")


def probe_video(
    path: Path,
    generate_audio: bool,
    expected_resolution: str | None = None,
    expected_duration: float | None = None,
) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        raise GeminiOmniVideoError("ffprobe is required to verify the downloaded MP4")
    result = subprocess.run(
        [
            executable,
            "-v", "error",
            "-show_entries", "format=duration,size,format_name:stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of", "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not isinstance(video_stream, dict):
        raise GeminiOmniVideoError("downloaded MP4 has no video stream")
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    format_data = data.get("format") if isinstance(data.get("format"), dict) else {}
    print(
        "MEDIA "
        f"codec={video_stream.get('codec_name')} pixels={video_stream.get('width')}x{video_stream.get('height')} "
        f"fps={video_stream.get('r_frame_rate')} duration={format_data.get('duration')} "
        f"audio_streams={len(audio_streams)}"
    )
    width = video_stream.get("width")
    height = video_stream.get("height")
    expected_short_edge = {"720p": 720, "1080p": 1080, "4k": 2160}.get(expected_resolution or "")
    if (
        expected_short_edge is not None
        and isinstance(width, int)
        and isinstance(height, int)
        and min(width, height) != expected_short_edge
    ):
        raise GeminiOmniVideoError(
            f"output resolution mismatch: requested={expected_resolution} actual={width}x{height}"
        )
    try:
        actual_duration = float(format_data.get("duration"))
    except (TypeError, ValueError):
        actual_duration = 0.0
    if expected_duration is not None and (
        actual_duration <= 0
        or abs(actual_duration - expected_duration) > max(0.5, expected_duration * 0.1)
    ):
        raise GeminiOmniVideoError(
            f"output duration mismatch: requested={expected_duration:g}s actual={actual_duration:g}s"
        )
    if not generate_audio and audio_streams:
        print("WARN unexpected_audio_stream requested_generate_audio=false")
    return data


def write_verified_output(
    path: Path,
    data: bytes,
    overwrite: bool,
    generate_audio: bool,
    expected_resolution: str,
    expected_duration: float,
) -> None:
    validate_output_target(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.mp4")
    try:
        write_output(temporary_path, data, overwrite=False)
        probe_video(
            temporary_path,
            generate_audio,
            expected_resolution=expected_resolution,
            expected_duration=expected_duration,
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def run(args: argparse.Namespace) -> None:
    if args.timeout <= 0 or args.poll_timeout <= 0 or args.poll_interval <= 0 or args.download_timeout <= 0:
        raise GeminiOmniVideoError("timeouts and poll interval must be positive")
    load_env_file(args.env_file)
    base_url = resolve_base_url(args.base_url)
    api_key = read_api_key()
    output = Path(args.output).expanduser().resolve()
    validate_output_target(output, args.overwrite)
    if not shutil.which("ffprobe"):
        raise GeminiOmniVideoError("ffprobe is required to verify the downloaded MP4")
    recharge = _load_akasha_recharge()
    recharge.validate_cli_recharge_usd(args.recharge_usd)
    controller = recharge.RechargeController(
        api_key=api_key,
        base_url=base_url,
        cli_recharge_usd=args.recharge_usd,
        request_timeout=args.timeout,
    )

    reference_url: str | None = None
    if args.command == "edit":
        if args.reference_video:
            reference_url = args.reference_video
        else:
            quoted = urllib.parse.quote(args.reference_task_id, safe="")
            task = parse_json(request(base_url, api_key, f"/videos/{quoted}", args.timeout, controller=controller)[0])
            reference_url = reference_url_from_task(task)
            print(f"REFERENCE task_id={args.reference_task_id} host={urllib.parse.urlsplit(reference_url).netloc}")

    payload = build_payload(args, reference_url)
    response = parse_json(request(base_url, api_key, "/videos", args.timeout, payload, controller=controller)[0])
    task_id = task_id_from(response)
    print(f"SUBMIT command={args.command} task_id={task_id} status={response.get('status', 'unknown')}")
    wait_for_task(
        base_url,
        api_key,
        task_id,
        args.timeout,
        args.poll_timeout,
        args.poll_interval,
        controller,
    )
    quoted = urllib.parse.quote(task_id, safe="")
    raw, content_type = request(
        base_url,
        api_key,
        f"/videos/{quoted}/content",
        args.download_timeout,
        controller=controller,
    )
    expected_duration = float(args.duration if args.command == "generate" else args.end - args.start)
    write_verified_output(
        output,
        raw,
        args.overwrite,
        args.generate_audio,
        args.resolution,
        expected_duration,
    )
    print(f"OK task_id={task_id} output={output} bytes={len(raw)} content_type={content_type or 'unknown'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--env-file", default=os.environ.get("GEMINI_OMNI_VIDEO_ENV_FILE"))
    parser.add_argument("--timeout", type=float, default=120.0)
    recharge = _load_akasha_recharge()
    recharge.add_recharge_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--model", default=DEFAULT_MODEL)
        subparser.add_argument("--prompt", required=True)
        subparser.add_argument("--resolution", choices=("720p", "1080p", "4k"), default="720p")
        subparser.add_argument("--aspect-ratio", default="16:9")
        subparser.add_argument("--generate-audio", action=argparse.BooleanOptionalAction, default=False)
        subparser.add_argument("--poll-timeout", type=float, default=900.0)
        subparser.add_argument("--poll-interval", type=float, default=10.0)
        subparser.add_argument("--download-timeout", type=float, default=180.0)
        subparser.add_argument("--output", required=True)
        subparser.add_argument("--overwrite", action="store_true")
        recharge.add_recharge_argument(subparser, suppress_default=True)

    generate = subparsers.add_parser("generate")
    add_common(generate)
    generate.add_argument("--duration", type=int, choices=(4, 6, 8, 10), default=4)

    edit = subparsers.add_parser("edit")
    add_common(edit)
    source = edit.add_mutually_exclusive_group(required=True)
    source.add_argument("--reference-video", type=validate_public_https_url)
    source.add_argument("--reference-task-id")
    edit.add_argument("--start", type=float, default=0.0)
    edit.add_argument("--end", type=float, default=4.0)
    return parser


def main() -> int:
    try:
        run(build_parser().parse_args())
        return 0
    except (GeminiOmniVideoError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"FAIL error={type(exc).__name__} message={' '.join(str(exc).split())[:500]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
