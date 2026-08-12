#!/usr/bin/env python3
"""Submit, wait for, and download Suno songs through new-api."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


TERMINAL_SUCCESS = "SUCCESS"
TERMINAL_FAILURE = "FAILURE"
DEFAULT_TIMEOUT_SECONDS = 1200.0
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_MODEL = "V5_5"
DEFAULT_BASE_URL = "https://newapi.1234bot.com/v1"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


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


def _api_key(explicit_base_url: str | None = None, timeout: float = 10) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    try:
        found = credentials.select_credential(
            explicit_base_url=explicit_base_url,
            timeout=timeout,
        )
    except credentials.CredentialError as exc:
        raise SystemExit(str(exc)) from exc
    return found.api_key


def _base_url(value: str | None) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    return credentials.resolve_base_url(
        ("SUNO_BASE_URL",), explicit=value, default=DEFAULT_BASE_URL
    )


def _missing_key_message() -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    return credentials.bootstrap_instructions()


def _parsed_http_url(value: str, label: str, *, allow_query: bool) -> urllib.parse.SplitResult:
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


def _api_url(base_url: str, endpoint: str) -> str:
    parsed = _parsed_http_url(base_url, "base URL", allow_query=False)
    base_path = parsed.path.rstrip("/")
    if base_path.rsplit("/", 1)[-1] == "v1":
        base_path = base_path[: -len("/v1")]
    result_path = f"{base_path}{endpoint}"
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc, result_path, "", ""))


def _request_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
    base_url: str | None = None,
    controller: Any | None = None,
) -> dict[str, Any]:
    recharge = _load_akasha_recharge()
    effective_base = base_url or DEFAULT_BASE_URL
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "suno-music-generation/1.0",
        },
        method=method,
    )
    opener = urllib.request.build_opener(NoRedirectHandler())

    def once() -> dict[str, Any]:
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                exc.close()
            except Exception:
                pass
            recharge.raise_quota_if_applicable(exc.code, raw, base_url=effective_base)
            raise SystemExit(f"new-api request failed: HTTP {exc.code}; body_bytes={len(raw)}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit("new-api request failed: network error") from exc
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"new-api response is not JSON; body_bytes={len(raw)}") from exc
        if not isinstance(parsed, dict):
            raise SystemExit(f"new-api response JSON is not an object: {type(parsed).__name__}")
        return parsed

    if controller is None:
        controller = recharge.RechargeController(
            api_key=api_key,
            base_url=effective_base,
            request_timeout=timeout,
        )
    try:
        return controller.run(once)
    except recharge.AkashaRechargeError as exc:
        raise SystemExit(str(exc)) from exc


def _require_success_response(data: dict[str, Any], context: str) -> Any:
    code = data.get("code")
    if code != "success":
        message = _safe_message(data.get("message") or "unknown error")
        raise SystemExit(f"{context} failed: code={code!r} message={message}")
    return data.get("data")


def _safe_message(value: Any) -> str:
    message = str(value).replace("\r", " ").replace("\n", " ")[:300]
    message = re.sub(r"(?i)bearer\s+\S+", "Bearer <redacted>", message)
    return re.sub(r"https?://\S+", "<url>", message)


def _submit(
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    controller: Any | None = None,
) -> str:
    payload: dict[str, Any] = {"make_instrumental": args.instrumental}
    if args.description:
        payload["gpt_description_prompt"] = args.description
    else:
        lyrics_path = Path(args.lyrics_file).expanduser().resolve()
        if not lyrics_path.is_file():
            raise SystemExit(f"lyrics file does not exist: {lyrics_path}")
        lyrics = lyrics_path.read_text(encoding="utf-8").strip()
        if not lyrics:
            raise SystemExit("lyrics file is empty")
        payload["prompt"] = lyrics
        if args.title:
            payload["title"] = args.title
        if args.style:
            payload["tags"] = args.style
    if args.model:
        payload["mv"] = args.model

    response = _request_json(
        "POST",
        _api_url(base_url, "/suno/submit/MUSIC"),
        api_key,
        payload,
        base_url=base_url,
        controller=controller,
    )
    task_id = _require_success_response(response, "Suno submit")
    if not isinstance(task_id, str) or not task_id.strip():
        raise SystemExit("Suno submit response is missing a non-empty task id")
    task_id = task_id.strip()
    if len(task_id) > 200 or any(ord(char) < 33 or ord(char) == 127 for char in task_id):
        raise SystemExit("Suno submit response contains an invalid task id")
    return task_id


def _wait_for_result(
    task_id: str,
    api_key: str,
    base_url: str,
    timeout_seconds: float,
    poll_seconds: float,
    controller: Any | None = None,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last_status = "UNKNOWN"
    while True:
        response = _request_json(
            "GET",
            _api_url(base_url, f"/suno/fetch/{urllib.parse.quote(task_id, safe='')}"),
            api_key,
            base_url=base_url,
            controller=controller,
        )
        task = _require_success_response(response, "Suno fetch")
        if not isinstance(task, dict):
            raise SystemExit("Suno fetch response data is not an object")
        status = task.get("status")
        if not isinstance(status, str) or not status:
            raise SystemExit("Suno fetch response is missing task status")
        last_status = status.upper()
        if last_status == TERMINAL_FAILURE:
            reason = _safe_message(task.get("fail_reason") or "unknown failure")
            raise SystemExit(f"Suno task failed: task_id={task_id} reason={reason}")
        if last_status == TERMINAL_SUCCESS:
            songs = task.get("data")
            if not isinstance(songs, list) or not songs:
                raise SystemExit("Suno task succeeded without a non-empty song array")
            if not all(isinstance(song, dict) for song in songs):
                raise SystemExit("Suno task song array contains a non-object item")
            return songs
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"Suno task timed out: task_id={task_id} status={last_status} "
                f"timeout={timeout_seconds:g}s"
            )
        time.sleep(min(poll_seconds, max(0.0, deadline - time.monotonic())))


def _safe_basename(value: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value:
        raise SystemExit("basename must be a single non-empty filename component")
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not sanitized:
        raise SystemExit("basename has no usable filename characters")
    return sanitized


def _download(url: str, destination: Path, overwrite: bool) -> int:
    parsed = _parsed_http_url(url, "result URL", allow_query=True)
    if destination.exists() and not overwrite:
        raise SystemExit(f"output exists; use --overwrite to replace: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        urllib.parse.urlunsplit(parsed),
        headers={"User-Agent": "suno-music-generation/1.0"},
        method="GET",
    )
    temp_name: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            _parsed_http_url(response.geturl(), "redirected result URL", allow_query=True)
            with tempfile.NamedTemporaryFile(
                prefix=f".{destination.name}.", suffix=".part", dir=destination.parent, delete=False
            ) as temp_file:
                temp_name = temp_file.name
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    temp_file.write(chunk)
                    total += len(chunk)
        if total <= 0:
            raise SystemExit("downloaded result is empty")
        Path(temp_name).replace(destination)
        temp_name = None
        return total
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"result download failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit("result download failed: network error") from exc
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def _save_results(args: argparse.Namespace, task_id: str, songs: list[dict[str, Any]]) -> list[tuple[Path, int]]:
    output_dir = Path(args.output_dir).expanduser().resolve()
    basename = _safe_basename(args.basename)
    saved: list[tuple[Path, int]] = []
    for index, song in enumerate(songs, start=1):
        audio_url = song.get("audio_url")
        if not isinstance(audio_url, str) or not audio_url:
            raise SystemExit(f"Suno song {index} is missing audio_url")
        audio_path = output_dir / f"{basename}-{index}.mp3"
        saved.append((audio_path, _download(audio_url, audio_path, args.overwrite)))

        if not args.no_cover:
            cover_url = song.get("image_large_url") or song.get("image_url")
            if isinstance(cover_url, str) and cover_url:
                cover_path = output_dir / f"{basename}-{index}-cover.jpg"
                saved.append((cover_path, _download(cover_url, cover_path, args.overwrite)))
        if args.download_video:
            video_url = song.get("video_url")
            if isinstance(video_url, str) and video_url:
                video_path = output_dir / f"{basename}-{index}.mp4"
                saved.append((video_path, _download(video_url, video_path, args.overwrite)))
    if not saved:
        raise SystemExit("Suno task produced no downloadable files")
    print(f"OK task_id={task_id} songs={len(songs)} files={len(saved)}")
    for path, size in saved:
        print(f"saved={path} bytes={size}")
    return saved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    _load_akasha_recharge().add_recharge_argument(parser)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--description", help="natural-language song description")
    source.add_argument("--lyrics-file", help="UTF-8 custom lyrics file")
    parser.add_argument("--title", help="title for custom lyrics mode")
    parser.add_argument("--style", help="style/tags for custom lyrics mode")
    parser.add_argument("--instrumental", action="store_true")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"explicit upstream Suno model id (default: {DEFAULT_MODEL}; use server-default to omit mv)",
    )
    parser.add_argument(
        "--base-url",
        help=f"new-api host root or /v1 API root (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--basename", default="suno-song")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--download-video", action="store_true")
    parser.add_argument("--no-cover", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.description is not None and not args.description.strip():
        raise SystemExit("description must not be empty")
    if args.description and (args.title or args.style):
        raise SystemExit("title/style are only valid with --lyrics-file")
    if args.lyrics_file and (not args.title or not args.style):
        raise SystemExit("custom lyrics mode requires both --title and --style")
    if args.timeout_seconds <= 0 or args.poll_seconds <= 0:
        raise SystemExit("timeout and poll interval must be positive")
    if args.model == "server-default":
        args.model = None
    base_url = _base_url(args.base_url)
    api_key = _api_key(base_url, args.timeout_seconds)
    recharge = _load_akasha_recharge()
    try:
        recharge.validate_cli_recharge_usd(getattr(args, "recharge_usd", None))
    except recharge.AkashaRechargeError as exc:
        raise SystemExit(str(exc)) from exc
    controller = recharge.RechargeController(
        api_key=api_key,
        base_url=base_url,
        cli_recharge_usd=getattr(args, "recharge_usd", None),
        request_timeout=60.0,
    )
    task_id = _submit(args, api_key, base_url, controller)
    songs = _wait_for_result(
        task_id,
        api_key,
        base_url,
        args.timeout_seconds,
        args.poll_seconds,
        controller,
    )
    _save_results(args, task_id, songs)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Suno wait interrupted", file=sys.stderr)
        raise SystemExit(130)
