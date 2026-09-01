#!/usr/bin/env python3
"""Run Fish Audio TTS or STT through new-api's OpenAI-compatible routes."""

from __future__ import annotations

import argparse
import array
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any


TTS_MODELS = {
    "fish-s2.1-pro",
    "fish-s2.1-pro-free",
    "fish-s2-pro",
    "fish-s1",
}
DEFAULT_TTS_MODEL = "fish-s2.1-pro"
STT_MODELS = {"fish-transcribe-1", "grok-stt"}
STT_MODEL = "fish-transcribe-1"
STT_TARGET_CHUNK_SECONDS = 30.0
STT_MAX_CHUNK_SECONDS = 35.0
STT_OVERLAP_SECONDS = 1.0
STT_SILENCE_RMS = 0.003
STT_SILENCE_PEAK = 0.01
VOICE_CLONE_MODEL = "fish-voice-clone-1"
VOICE_MODEL_STATES = {"created", "training", "trained", "failed"}
MAX_VOICE_SAMPLES = 10
OUTPUT_FORMATS = {"mp3", "wav", "opus"}
PUBLIC_MODELS_URL = "https://api.fish.audio/model"
DEFAULT_BASE_URL = "https://newapi.1234bot.com/v1"
VOICE_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "assets" / "voice-library" / "voices.v1.json"


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
        ("FISH_AUDIO_BASE_URL",), explicit=value, default=DEFAULT_BASE_URL
    )


def _missing_key_message() -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    return credentials.bootstrap_instructions()


def _parsed_base_url(value: str) -> urllib.parse.SplitResult:
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise SystemExit("invalid base URL: require an absolute HTTP(S) URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise SystemExit("invalid base URL: require an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise SystemExit("invalid base URL: userinfo is not allowed")
    if parsed.query:
        raise SystemExit("invalid base URL: query is not allowed")
    if parsed.fragment:
        raise SystemExit("invalid base URL: fragment is not allowed")
    return parsed


def _api_url(base_url: str, endpoint: str) -> str:
    parsed = _parsed_base_url(base_url)
    base_path = parsed.path.rstrip("/")
    if not base_path:
        api_path = "/v1"
    elif base_path.rsplit("/", 1)[-1] == "v1":
        api_path = base_path
    else:
        api_path = f"{base_path}/v1"
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, f"{api_path}{endpoint}", "", "")
    )


def _read_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        value = args.text
    else:
        path = Path(args.text_file).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"text file does not exist: {path}")
        value = path.read_text(encoding="utf-8")
    value = value.strip()
    if not value:
        raise SystemExit("TTS text must not be empty")
    return value


def _atomic_write(path: Path, data: bytes, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise SystemExit(f"output exists; use --overwrite to replace: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.", suffix=".part", dir=path.parent, delete=False
        ) as temp_file:
            temp_name = temp_file.name
            temp_file.write(data)
        Path(temp_name).replace(path)
        temp_name = None
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def _open_api_request(
    request: urllib.request.Request,
    timeout: float,
    *,
    base_url: str,
    api_key: str,
    controller: Any | None = None,
) -> tuple[bytes, str]:
    recharge = _load_akasha_recharge()
    opener = urllib.request.build_opener(NoRedirectHandler())

    def once() -> tuple[bytes, str]:
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                exc.close()
            except Exception:
                pass
            recharge.raise_quota_if_applicable(exc.code, body, base_url=base_url)
            detail = _safe_api_error_detail(body)
            suffix = f"; {detail}" if detail else f"; body_bytes={len(body)}"
            raise SystemExit(f"new-api request failed: HTTP {exc.code}{suffix}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit("new-api request failed: network error") from exc

    if controller is None:
        controller = recharge.RechargeController(
            api_key=api_key,
            base_url=base_url,
            request_timeout=timeout,
        )
    try:
        return controller.run(once)
    except recharge.AkashaRechargeError as exc:
        raise SystemExit(str(exc)) from exc


def _safe_api_error_detail(raw: bytes) -> str:
    """Return only allowlisted, bounded new-api error fields."""
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    error = parsed.get("error", parsed)
    if isinstance(error, str):
        error = {"message": error}
    if not isinstance(error, dict):
        return ""
    details: list[str] = []
    for name in ("code", "type", "message"):
        value = error.get(name)
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            continue
        compact = " ".join(str(value).split())[:512]
        if compact:
            details.append(f"{name}={compact}")
    return "; ".join(details)


def _decode_json_object(raw: bytes, operation: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{operation} response is not JSON; body_bytes={len(raw)}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"{operation} response is not an object")
    return parsed


def _open_public_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "fish-audio-speech/1.1"},
        method="GET",
    )
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        raise SystemExit(f"Fish public model search failed: HTTP {exc.code}; body_bytes={len(body)}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit("Fish public model search failed: network error") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Fish public model search returned invalid JSON; body_bytes={len(raw)}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit("Fish public model search response is not an object")
    return parsed


def _search_voices(args: argparse.Namespace) -> None:
    query_value = args.query or args.character
    fetch_size = min(max(args.limit * 5, 20), 100)
    query = urllib.parse.urlencode({"page_size": fetch_size, "title": query_value})
    response = _open_public_json(f"{PUBLIC_MODELS_URL}?{query}", args.timeout_seconds)
    items = response.get("items")
    if not isinstance(items, list):
        raise SystemExit("Fish public model search response is missing an items array")

    required_tags = {tag.casefold() for tag in args.tag}
    selected: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        reference_id = item.get("_id")
        if not isinstance(reference_id, str) or not reference_id.strip():
            continue
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        normalized_tags = {str(tag).casefold() for tag in tags}
        languages = item.get("languages") if isinstance(item.get("languages"), list) else []
        if item.get("type") != "tts" or item.get("state") != "trained":
            continue
        if item.get("visibility") != "public" or item.get("dmca_taken_down") is True:
            continue
        if args.language and args.language not in languages:
            continue
        if required_tags and not required_tags.issubset(normalized_tags):
            continue
        uses = item.get("task_count") if isinstance(item.get("task_count"), int) else 0
        if uses < args.min_uses:
            continue
        selected.append(item)

    sort_key = (
        (lambda item: item.get("like_count") if isinstance(item.get("like_count"), int) else 0)
        if args.sort == "likes"
        else (lambda item: item.get("task_count") if isinstance(item.get("task_count"), int) else 0)
    )
    selected.sort(key=sort_key, reverse=True)
    selected = selected[: args.limit]

    compact = []
    for item in selected:
        compact.append(
            {
                "reference_id": item.get("_id"),
                "title": item.get("title"),
                "description": item.get("description"),
                "languages": item.get("languages") or [],
                "tags": item.get("tags") or [],
                "uses": item.get("task_count") or 0,
                "likes": item.get("like_count") or 0,
            }
        )
    if args.json_output:
        output = Path(args.json_output).expanduser().resolve()
        encoded = (json.dumps(compact, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _atomic_write(output, encoded, args.overwrite)

    print(f"OK mode=voices query={query_value!r} matches={len(compact)}")
    for voice in compact:
        title = str(voice["title"] or "").replace("\t", " ").replace("\n", " ")
        languages = ",".join(str(value) for value in voice["languages"])
        tags = ",".join(str(value) for value in voice["tags"][:8])
        print(
            f"reference_id={voice['reference_id']}\ttitle={title}\tuses={voice['uses']}\t"
            f"likes={voice['likes']}\tlanguages={languages}\ttags={tags}"
        )


def _load_voice_library() -> dict[str, Any]:
    try:
        library = json.loads(VOICE_LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid voice library: {VOICE_LIBRARY_PATH}") from exc
    if not isinstance(library, dict) or not isinstance(library.get("voices"), list):
        raise SystemExit(f"invalid voice library structure: {VOICE_LIBRARY_PATH}")
    return library


def _library_voice(slug: str) -> dict[str, Any]:
    for voice in _load_voice_library()["voices"]:
        if isinstance(voice, dict) and voice.get("slug") == slug:
            if voice.get("review_status") != "approved":
                break
            return voice
    raise SystemExit(f"unknown voice library slug: {slug}")


def _voice_sample_path(voice: dict[str, Any]) -> Path:
    return VOICE_LIBRARY_PATH.parent / str(voice["sample"])


def _print_voice_library() -> None:
    voices = _load_voice_library()["voices"]
    print(f"OK mode=library voices={len(voices)}")
    for voice in voices:
        print(
            f"slug={voice['slug']}\tname={voice['display_name']}\t"
            f"scenes={','.join(voice['scenes'])}\ttags={','.join(voice['tags'])}\t"
            f"sample={_voice_sample_path(voice)}"
        )


def _tts(
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    controller: Any | None = None,
) -> None:
    if args.model is not None and args.model not in TTS_MODELS:
        raise SystemExit(f"unsupported Fish Audio TTS model: {args.model}")
    model = args.model or DEFAULT_TTS_MODEL
    if args.format not in OUTPUT_FORMATS:
        raise SystemExit(f"unsupported TTS format: {args.format}")
    voice = args.voice
    library_voice = vars(args).get("library_voice")
    if library_voice:
        selected = _library_voice(library_voice)
        voice = selected["reference_id"]
        if args.model is None:
            model = selected["model"]
    if args.character:
        registry = _load_voice_registry(_voice_registry_path(args.registry))
        binding = registry.get("characters", {}).get(args.character)
        if not isinstance(binding, dict) or not isinstance(binding.get("reference_id"), str):
            raise SystemExit(f"character is not bound to a Fish Audio voice: {args.character}")
        voice = binding["reference_id"]
        bound_model = binding.get("model")
        if args.model is None and isinstance(bound_model, str) and bound_model in TTS_MODELS:
            model = bound_model
    if not voice and not args.reference_audio:
        raise SystemExit("provide --voice, --character, or --reference-audio with --reference-text")
    if bool(args.reference_audio) != bool(args.reference_text):
        raise SystemExit("--reference-audio and --reference-text must be provided together")

    input_text = _read_text(args)
    # argparse stores declared options directly on the namespace. Reading from
    # ``vars`` also keeps direct unit-test callers that use a loose Mock from
    # fabricating a truthy ``style`` attribute.
    style = vars(args).get("style")
    if style is not None:
        style = style.strip()
        if not style:
            raise SystemExit("TTS style must not be empty")
        if len(style) > 128:
            raise SystemExit("TTS style must not exceed 128 characters")
        if any(value in style for value in ("[", "]", "\n", "\r")):
            raise SystemExit("TTS style must be a single bracket-free instruction")
        input_text = f"[{style}] {input_text}"

    payload: dict[str, Any] = {
        "model": model,
        "input": input_text,
        "response_format": args.format,
    }
    if voice:
        payload["voice"] = voice
    if args.reference_audio:
        audio_path = Path(args.reference_audio).expanduser().resolve()
        if not audio_path.is_file():
            raise SystemExit(f"reference audio does not exist: {audio_path}")
        audio_bytes = audio_path.read_bytes()
        if not audio_bytes:
            raise SystemExit("reference audio is empty")
        payload["extra_body"] = {
            "references": [
                {
                    "audio": base64.b64encode(audio_bytes).decode("ascii"),
                    "text": args.reference_text,
                }
            ]
        }

    request = urllib.request.Request(
        _api_url(base_url, "/audio/speech"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "audio/*, application/octet-stream",
            "Content-Type": "application/json",
            "User-Agent": "fish-audio-speech/1.0",
        },
        method="POST",
    )
    body, content_type = _open_api_request(
        request,
        args.timeout_seconds,
        base_url=base_url,
        api_key=api_key,
        controller=controller,
    )
    if not body:
        raise SystemExit("Fish Audio TTS returned an empty body")
    if content_type.lower().split(";", 1)[0].strip() in {"application/json", "text/json"}:
        raise SystemExit(f"Fish Audio TTS returned JSON instead of audio; body_bytes={len(body)}")
    try:
        json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    else:
        raise SystemExit(f"Fish Audio TTS returned JSON instead of audio; body_bytes={len(body)}")

    output = Path(args.output).expanduser().resolve()
    _atomic_write(output, body, args.overwrite)
    print(f"OK mode=tts model={model} output={output} bytes={len(body)}")


def _multipart_stt_body(args: argparse.Namespace, audio_path_value: str | Path | None = None) -> tuple[bytes, str]:
    audio_path = Path(audio_path_value or args.audio).expanduser().resolve()
    if not audio_path.is_file():
        raise SystemExit(f"audio file does not exist: {audio_path}")
    audio = audio_path.read_bytes()
    if not audio:
        raise SystemExit("audio file is empty")
    boundary = f"----fish-audio-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    add_field("model", args.model)
    if args.language:
        add_field("language", args.language)
    add_field("ignore_timestamps", "true" if args.ignore_timestamps else "false")
    if args.model == "grok-stt" and not args.ignore_timestamps:
        add_field("response_format", "verbose_json")
        add_field("timestamp_granularities[]", "word")
    elif args.model == "fish-transcribe-1" and not args.ignore_timestamps:
        # Fish accepts OpenAI's verbose shape through new-api and returns segments.
        add_field("response_format", "verbose_json")
        add_field("timestamp_granularities[]", "segment")
    suffix = audio_path.suffix.lower()
    safe_suffix = suffix if suffix and suffix[1:].isalnum() and len(suffix) <= 10 else ""
    safe_filename = f"audio{safe_suffix}"
    content_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(audio)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _run_quiet(command: list[str]) -> bytes:
    try:
        return subprocess.check_output(command, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return b""


def _audio_duration(path: Path) -> float:
    """Read duration without trusting user supplied metadata."""
    probe = _run_quiet([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        value = float(probe.decode().strip())
        if value >= 0:
            return value
    except (UnicodeDecodeError, ValueError):
        pass
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / float(handle.getframerate() or 1)
    except (OSError, wave.Error, ZeroDivisionError):
        return 0.0


def _pcm_mono(path: Path, sample_rate: int = 16000) -> tuple[bytes, int]:
    """Decode any supported input to mono signed 16-bit PCM for analysis."""
    raw = _run_quiet([
        "ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "-",
    ])
    if raw:
        return raw, sample_rate
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            channels, width, rate = handle.getnchannels(), handle.getsampwidth(), handle.getframerate()
            if width == 2 and channels == 1:
                return frames, rate
    except (OSError, wave.Error):
        pass
    return b"", sample_rate


def _energy_windows(path: Path, window_seconds: float = 0.1) -> list[tuple[float, float, float]]:
    raw, rate = _pcm_mono(path)
    if not raw or rate <= 0:
        return []
    samples = array.array("h")
    samples.frombytes(raw)
    size = max(1, int(rate * window_seconds))
    windows: list[tuple[float, float, float]] = []
    for index in range(0, len(samples), size):
        part = samples[index:index + size]
        if not part:
            continue
        peak = max(abs(value) for value in part) / 32768.0
        rms = (sum(value * value for value in part) / len(part)) ** 0.5 / 32768.0
        windows.append((index / rate, rms, peak))
    return windows


def _is_silent(path: Path) -> bool:
    windows = _energy_windows(path)
    if not windows:
        return False
    # Conservative: both metrics must be very low, so quiet singing is retained.
    return max(item[1] for item in windows) < STT_SILENCE_RMS and max(item[2] for item in windows) < STT_SILENCE_PEAK


def _find_low_energy_boundary(path: Path, target: float, radius: float = 3.0) -> float:
    duration = _audio_duration(path)
    target = max(0.0, min(target, duration))
    windows = _energy_windows(path)
    candidates = [item for item in windows if abs(item[0] - target) <= radius]
    if not candidates:
        return target
    # Prefer silence, otherwise the lowest RMS/peak weighted boundary.
    quiet = [item for item in candidates if item[1] < STT_SILENCE_RMS * 4 and item[2] < STT_SILENCE_PEAK * 4]
    selected = min(quiet or candidates, key=lambda item: (item[1] + item[2] * 0.25, abs(item[0] - target)))
    return max(0.0, min(selected[0], duration))


def _plan_audio_chunks(path: Path) -> list[tuple[float, float]]:
    duration = _audio_duration(path)
    if duration <= STT_MAX_CHUNK_SECONDS:
        return [(0.0, duration)] if duration > 0 else []
    result: list[tuple[float, float]] = []
    start = 0.0
    while start < duration - 1e-3:
        target = min(start + STT_TARGET_CHUNK_SECONDS, duration)
        end = duration if duration - start <= STT_MAX_CHUNK_SECONDS else _find_low_energy_boundary(path, target)
        # Never let a boundary search create a chunk outside the provider limit.
        if end - start > STT_MAX_CHUNK_SECONDS:
            end = start + STT_MAX_CHUNK_SECONDS
        if end <= start + 0.25:
            end = min(duration, start + STT_TARGET_CHUNK_SECONDS)
        result.append((start, end))
        if end >= duration:
            break
        start = max(0.0, end - STT_OVERLAP_SECONDS)
    return result


def _encode_stt_audio(path: Path, model: str, start: float | None = None, end: float | None = None, fmt: str = "mp3") -> Path:
    """Create a provider-compatible temporary file; caller removes it."""
    suffix = ".mp3" if fmt == "mp3" else ".wav"
    temp = tempfile.NamedTemporaryFile(prefix="fish-stt-", suffix=suffix, delete=False)
    temp.close()
    command = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        command += ["-ss", f"{start:.3f}"]
    command += ["-i", str(path)]
    if end is not None and start is not None:
        command += ["-t", f"{max(0.0, end - start):.3f}"]
    if fmt == "mp3":
        command += ["-ac", "1", "-ar", "44100", "-codec:a", "libmp3lame", "-b:a", "128k", temp.name]
    else:
        command += ["-ac", "1", "-ar", "16000", "-sample_fmt", "s16", temp.name]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        Path(temp.name).unlink(missing_ok=True)
        raise SystemExit(f"audio compatibility conversion failed ({fmt})") from exc
    return Path(temp.name)


def _response_has_content(response: dict[str, Any]) -> bool:
    text = response.get("text")
    if isinstance(text, str) and text.strip():
        return True
    for key in ("words", "segments"):
        value = response.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _response_text(response: dict[str, Any]) -> str:
    text = response.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    segments = response.get("segments")
    if isinstance(segments, list):
        values = [item.get("text") for item in segments if isinstance(item, dict)]
        merged = " ".join(value.strip() for value in values if isinstance(value, str) and value.strip())
        if merged:
            return merged
    words = response.get("words")
    if isinstance(words, list):
        values = [item.get("word", item.get("text")) for item in words if isinstance(item, dict)]
        return " ".join(value.strip() for value in values if isinstance(value, str) and value.strip())
    return ""


def _unlink_temporary(path: Path, source: Path) -> None:
    try:
        if path.resolve() == source.resolve():
            return
    except OSError:
        if path == source:
            return
    path.unlink(missing_ok=True)


def _normalise_items(response: dict[str, Any], offset: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    words: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    for key, target in (("words", words), ("segments", segments)):
        values = response.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            copy = dict(item)
            for field in ("start", "end"):
                if isinstance(copy.get(field), (int, float)):
                    copy[field] = float(copy[field]) + offset
            target.append(copy)
    return words, segments


def _dedupe_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in sorted(words, key=lambda value: float(value.get("start", 0))):
        token = str(item.get("word", item.get("text", ""))).strip().casefold()
        start = float(item.get("start", 0) or 0)
        end = float(item.get("end", start) or start)
        if token and any(
            token == str(previous.get("word", previous.get("text", ""))).strip().casefold()
            and start <= float(previous.get("end", previous.get("start", 0)) or 0) + 0.8
            and end >= float(previous.get("start", 0) or 0) - 0.8
            for previous in output[-12:]
        ):
            continue
        output.append(item)
    return output


def _merge_texts(texts: list[str]) -> str:
    """Join chunk text while removing a repeated suffix/prefix from overlap."""
    merged = ""
    for value in texts:
        text = value.strip()
        if not text:
            continue
        if not merged:
            merged = text
            continue
        left = re.sub(r"\s+", "", merged)
        right = re.sub(r"\s+", "", text)
        overlap = 0
        limit = min(len(left), len(right))
        for size in range(limit, 1, -1):
            if left[-size:].casefold() == right[:size].casefold():
                overlap = size
                break
        if overlap:
            text = right[overlap:]
            if text:
                separator = " " if merged[-1:].isascii() and merged[-1:].isalnum() and text[:1].isascii() and text[:1].isalnum() else ""
                merged += separator + text
        else:
            separator = "" if (merged[-1:].isspace() or text[:1] in "，。！？、.!?,") else " "
            merged += separator + text
    return merged.strip()


def _voice_registry_path(value: str | None) -> Path:
    configured = value or os.environ.get("FISH_AUDIO_VOICE_REGISTRY")
    if not configured:
        raise SystemExit("missing voice registry: pass --registry or set FISH_AUDIO_VOICE_REGISTRY")
    return Path(configured).expanduser().resolve()


def _load_voice_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "characters": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid voice registry: {path}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("characters"), dict):
        raise SystemExit(f"invalid voice registry structure: {path}")
    return parsed


def _bind_character(args: argparse.Namespace) -> None:
    registry_path = _voice_registry_path(args.registry)
    registry = _load_voice_registry(registry_path)
    selected = _library_voice(args.library_voice) if args.library_voice else None
    registry["characters"][args.character] = {
        "provider": "fish-audio",
        "reference_id": selected["reference_id"] if selected else args.voice,
        "model": selected["model"] if selected else args.model,
        "title": selected["display_name"] if selected else (args.title or ""),
    }
    encoded = (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write(registry_path, encoded, True)
    print(f"OK mode=bind character={args.character!r} registry={registry_path}")


def _multipart_clone_body(args: argparse.Namespace) -> tuple[bytes, str]:
    if len(args.audio) > MAX_VOICE_SAMPLES:
        raise SystemExit(f"Fish Audio voice clone accepts at most {MAX_VOICE_SAMPLES} samples")
    if args.text and len(args.text) != len(args.audio):
        raise SystemExit("repeat --text once per --audio, or omit all --text values")
    boundary = f"----fish-audio-clone-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    add_field("model", VOICE_CLONE_MODEL)
    add_field("title", args.title)
    add_field("visibility", "private")
    add_field("enhance_audio_quality", "true" if args.enhance_audio_quality else "false")
    add_field("generate_sample", "true" if args.generate_sample else "false")
    for tag in args.tag:
        add_field("tags", tag)
    for text in args.text:
        add_field("texts", text)
    for audio_value in args.audio:
        audio_path = Path(audio_value).expanduser().resolve()
        if not audio_path.is_file():
            raise SystemExit(f"voice sample does not exist: {audio_path}")
        audio = audio_path.read_bytes()
        if not audio:
            raise SystemExit(f"voice sample is empty: {audio_path}")
        suffix = audio_path.suffix.lower()
        safe_suffix = suffix if suffix and suffix[1:].isalnum() and len(suffix) <= 10 else ""
        safe_filename = f"voice{safe_suffix}"
        content_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            (
                f'Content-Disposition: form-data; name="voices"; filename="{safe_filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(audio)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _clone_voice(
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    controller: Any | None = None,
) -> None:
    body, content_type = _multipart_clone_body(args)
    request = urllib.request.Request(
        _api_url(base_url, "/audio/voice-models"),
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": content_type,
            "User-Agent": "fish-audio-speech/1.2",
        },
        method="POST",
    )
    raw, _ = _open_api_request(
        request,
        args.timeout_seconds,
        base_url=base_url,
        api_key=api_key,
        controller=controller,
    )
    response = _decode_json_object(raw, "Fish Audio voice clone")
    reference_id = response.get("_id")
    if not isinstance(reference_id, str) or not reference_id:
        raise SystemExit("Fish Audio voice clone response is missing _id")
    state = response.get("state")
    if state not in VOICE_MODEL_STATES:
        raise SystemExit("Fish Audio voice clone response has an invalid state")
    if args.json_output:
        output = Path(args.json_output).expanduser().resolve()
        encoded = (json.dumps(response, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _atomic_write(output, encoded, args.overwrite)
    if state == "failed":
        raise SystemExit(f"Fish Audio voice clone failed; reference_id={reference_id}")
    print(f"OK mode=clone reference_id={reference_id} state={state}")


def _voice_model_status(
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    controller: Any | None = None,
) -> None:
    endpoint = "/audio/voice-models/" + urllib.parse.quote(args.reference_id, safe="")
    request = urllib.request.Request(
        _api_url(base_url, endpoint),
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        method="GET",
    )
    raw, _ = _open_api_request(
        request,
        args.timeout_seconds,
        base_url=base_url,
        api_key=api_key,
        controller=controller,
    )
    response = _decode_json_object(raw, "Fish Audio voice model status")
    response_id = response.get("_id")
    if response_id != args.reference_id:
        raise SystemExit("Fish Audio voice model status response has an unexpected _id")
    state = response.get("state")
    if state not in VOICE_MODEL_STATES:
        raise SystemExit("Fish Audio voice model status response has an invalid state")
    if args.json_output:
        output = Path(args.json_output).expanduser().resolve()
        encoded = (json.dumps(response, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _atomic_write(output, encoded, args.overwrite)
    print(f"STATUS mode=clone-status reference_id={args.reference_id} state={state}")


def _delete_voice_model(
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    controller: Any | None = None,
) -> None:
    if not args.confirm_delete:
        raise SystemExit("refusing to delete voice model without --confirm-delete")
    endpoint = "/audio/voice-models/" + urllib.parse.quote(args.reference_id, safe="")
    request = urllib.request.Request(
        _api_url(base_url, endpoint),
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        method="DELETE",
    )
    _open_api_request(
        request,
        args.timeout_seconds,
        base_url=base_url,
        api_key=api_key,
        controller=controller,
    )
    print(f"OK mode=clone-delete reference_id={args.reference_id}")


def _stt(
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    controller: Any | None = None,
) -> None:
    if args.model not in STT_MODELS:
        raise SystemExit(f"unsupported STT model: {args.model}")
    source = Path(args.audio).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"audio file does not exist: {source}")
    duration = _audio_duration(source)
    # Keep compatibility with callers that provide an opaque stream to a mocked
    # gateway; real media is still duration-probed and chunked when possible.
    if duration <= 0:
        duration = 0.0

    chunks = _plan_audio_chunks(source) or [(0.0, 0.0)]
    raw_responses: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    errors: list[str] = []
    skipped: list[dict[str, Any]] = []

    for index, (start, end) in enumerate(chunks):
        # Grok is substantially more reliable with mono MP3 than float/stereo WAV.
        fmt = "mp3" if args.model == "grok-stt" else "wav"
        temporary: Path | None = None
        request_path = source
        try:
            if (len(chunks) > 1 or args.model == "grok-stt") and end > start:
                temporary = _encode_stt_audio(source, args.model, start, end, fmt)
                request_path = temporary
            if _is_silent(request_path):
                skipped.append({"index": index, "start": start, "end": end, "reason": "low_energy"})
                continue

            def request_once(upload_path: Path) -> dict[str, Any]:
                body, content_type = _multipart_stt_body(args, upload_path)
                request = urllib.request.Request(
                    _api_url(base_url, "/audio/transcriptions"),
                    data=body,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Accept": "application/json",
                        "Content-Type": content_type,
                        "User-Agent": "fish-audio-speech/1.3",
                    },
                    method="POST",
                )
                raw, _ = _open_api_request(request, args.timeout_seconds, base_url=base_url, api_key=api_key, controller=controller)
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise SystemExit(f"STT response is not JSON; body_bytes={len(raw)}") from exc
                if not isinstance(value, dict):
                    raise SystemExit(f"STT response is not an object: {type(value).__name__}")
                if not _response_has_content(value):
                    raise ValueError("HTTP 200 response contained no text, words, or segments")
                return value

            try:
                response = request_once(request_path)
            except ValueError:
                # One compatibility retry with stable mono PCM WAV.
                retry = _encode_stt_audio(source, args.model, start, end, "wav")
                try:
                    response = request_once(retry)
                finally:
                    _unlink_temporary(retry, source)
            raw_responses.append({"index": index, "start": start, "end": end, "response": response})
            chunk_words, chunk_segments = _normalise_items(response, start)
            words.extend(chunk_words)
            segments.extend(chunk_segments)
        except (SystemExit, ValueError) as exc:
            message = str(exc)
            if isinstance(exc, ValueError):
                message = "HTTP 200 empty response after compatibility retry"
            errors.append(f"chunk {index} [{start:.2f},{end:.2f}]: {message}")
        finally:
            if temporary:
                _unlink_temporary(temporary, source)

    if errors and not raw_responses and not skipped:
        raise SystemExit("STT failed: " + " | ".join(errors))

    words = _dedupe_words(words)
    texts = [_response_text(item.get("response", {})) for item in raw_responses]
    asr_text = _merge_texts(texts)
    transcript = asr_text
    lyrics_path = getattr(args, "lyrics_file", None)
    if lyrics_path:
        lyric_file = Path(lyrics_path).expanduser().resolve()
        if not lyric_file.is_file():
            raise SystemExit(f"lyrics file does not exist: {lyric_file}")
        transcript = lyric_file.read_text(encoding="utf-8").strip()
        if not transcript:
            raise SystemExit("lyrics file is empty")

    aggregate: dict[str, Any] = {
        "text": transcript,
        "asr_text": asr_text,
        "duration": duration,
        "provider": "grok" if args.model == "grok-stt" else "fish-audio",
        "model": args.model,
        "words": words,
        "segments": segments,
        "raw_responses": raw_responses,
        "skipped_chunks": skipped,
        "failures": errors,
    }
    if raw_responses:
        first_response = raw_responses[0].get("response", {})
        if isinstance(first_response, dict):
            for key in ("language", "task", "duration"):
                if key in first_response and key not in aggregate:
                    aggregate[key] = first_response[key]
    output = Path(args.output).expanduser().resolve()
    _atomic_write(output, transcript.encode("utf-8"), args.overwrite)
    if args.json_output:
        json_output = Path(args.json_output).expanduser().resolve()
        encoded = (json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _atomic_write(json_output, encoded, args.overwrite)
    print(f"OK mode=stt model={args.model} output={output} characters={len(transcript)} chunks={len(chunks)} skipped={len(skipped)} json_saved={bool(args.json_output)}")


def _parser() -> argparse.ArgumentParser:
    recharge = _load_akasha_recharge()
    recharge_parent = recharge.recharge_parent_parser()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        help=f"new-api host root or /v1 API root (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--overwrite", action="store_true")
    recharge.add_recharge_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    tts = subparsers.add_parser("tts", parents=[recharge_parent], help="synthesize speech")
    text_source = tts.add_mutually_exclusive_group(required=True)
    text_source.add_argument("--text")
    text_source.add_argument("--text-file")
    saved_voice = tts.add_mutually_exclusive_group()
    saved_voice.add_argument("--voice", help="Fish Audio reference_id")
    saved_voice.add_argument("--character", help="character/person name bound in the voice registry")
    saved_voice.add_argument("--library-voice", help="approved voice library slug")
    tts.add_argument("--registry", help="character voice registry JSON path")
    tts.add_argument("--reference-audio", help="local authorized reference audio")
    tts.add_argument("--reference-text", help="exact transcript for the reference audio")
    tts.add_argument(
        "--model",
        choices=sorted(TTS_MODELS),
        help=f"override the bound model; defaults to the registry model or {DEFAULT_TTS_MODEL}",
    )
    tts.add_argument(
        "--style",
        help="S2.1 natural-language emotion/style instruction, for example 'warm and reflective'",
    )
    tts.add_argument("--format", default="mp3")
    tts.add_argument("--output", required=True)

    stt = subparsers.add_parser("stt", parents=[recharge_parent], help="transcribe speech")
    stt.add_argument("audio")
    stt.add_argument("--model", choices=sorted(STT_MODELS), default=STT_MODEL)
    stt.add_argument("--language")
    stt.add_argument("--ignore-timestamps", action="store_true")
    stt.add_argument("--lyrics-file", help="official lyrics/LRC used as final text; ASR only supplies timing/reference")
    stt.add_argument("--output", required=True)
    stt.add_argument("--json-output")

    voices = subparsers.add_parser("voices", parents=[recharge_parent], help="search Fish Audio public reference voices")
    voice_query = voices.add_mutually_exclusive_group(required=True)
    voice_query.add_argument("--query", help="title keyword, for example 旁白")
    voice_query.add_argument("--character", help="specific person or character name")
    voices.add_argument("--language", default="zh")
    voices.add_argument("--tag", action="append", default=[], help="required tag; repeatable")
    voices.add_argument("--min-uses", type=int, default=0)
    voices.add_argument("--limit", type=int, default=10)
    voices.add_argument("--sort", choices=("uses", "likes"), default="uses")
    voices.add_argument("--json-output")

    subparsers.add_parser("library", help="list approved voices and local samples")

    bind = subparsers.add_parser("bind", parents=[recharge_parent], help="bind a character/person name to a Fish voice")
    bind.add_argument("--character", required=True)
    bind_voice = bind.add_mutually_exclusive_group(required=True)
    bind_voice.add_argument("--voice", help="Fish Audio reference_id")
    bind_voice.add_argument("--library-voice", help="approved voice library slug")
    bind.add_argument("--title")
    bind.add_argument("--model", choices=sorted(TTS_MODELS), default=DEFAULT_TTS_MODEL)
    bind.add_argument("--registry", help="character voice registry JSON path")

    clone = subparsers.add_parser("clone", parents=[recharge_parent], help="create a reusable private Fish voice model")
    clone.add_argument("--title", required=True)
    clone.add_argument("--audio", action="append", required=True, help="authorized voice sample; repeatable")
    clone.add_argument("--text", action="append", default=[], help="matching transcript; repeat once per audio")
    clone.add_argument("--tag", action="append", default=[])
    clone.add_argument("--enhance-audio-quality", action=argparse.BooleanOptionalAction, default=True)
    clone.add_argument("--generate-sample", action="store_true")
    clone.add_argument("--json-output")

    clone_status = subparsers.add_parser("clone-status", parents=[recharge_parent], help="get private Fish voice model state")
    clone_status.add_argument("reference_id")
    clone_status.add_argument("--json-output")

    clone_delete = subparsers.add_parser("clone-delete", parents=[recharge_parent], help="delete an owned private Fish voice model")
    clone_delete.add_argument("reference_id")
    clone_delete.add_argument(
        "--confirm-delete",
        action="store_true",
        help="confirm irreversible deletion of this private voice model",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.timeout_seconds <= 0:
        raise SystemExit("timeout must be positive")
    if args.command == "voices":
        query_value = args.query or args.character
        if not query_value.strip():
            raise SystemExit("voice search query must not be empty")
        if args.limit <= 0 or args.limit > 100:
            raise SystemExit("voice search limit must be between 1 and 100")
        if args.min_uses < 0:
            raise SystemExit("voice search min-uses must not be negative")
        _search_voices(args)
        return 0
    if args.command == "library":
        _print_voice_library()
        return 0
    if args.command == "bind":
        if not args.character.strip() or (args.voice is not None and not args.voice.strip()):
            raise SystemExit("character and voice must not be empty")
        _bind_character(args)
        return 0
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
        request_timeout=args.timeout_seconds,
    )
    if args.command == "tts":
        _tts(args, api_key, base_url, controller)
    elif args.command == "stt":
        _stt(args, api_key, base_url, controller)
    elif args.command == "clone":
        if len(args.title) > 256:
            raise SystemExit("voice model title must not exceed 256 characters")
        _clone_voice(args, api_key, base_url, controller)
    elif args.command == "clone-status":
        _voice_model_status(args, api_key, base_url, controller)
    else:
        _delete_voice_model(args, api_key, base_url, controller)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Fish Audio request interrupted", file=sys.stderr)
        raise SystemExit(130)
