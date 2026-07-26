#!/usr/bin/env python3
"""Run Fish Audio TTS or STT through new-api's OpenAI-compatible routes."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


TTS_MODELS = {"fish-s2-pro", "fish-s1"}
STT_MODEL = "fish-transcribe-1"
OUTPUT_FORMATS = {"mp3", "wav", "opus"}


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _api_key() -> str:
    return os.environ.get("NEW_API_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""


def _base_url(value: str | None) -> str:
    return value or os.environ.get("NEW_API_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or ""


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


def _open_api_request(request: urllib.request.Request, timeout: float) -> tuple[bytes, str]:
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        body = exc.read()
        raise SystemExit(f"new-api request failed: HTTP {exc.code}; body_bytes={len(body)}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit("new-api request failed: network error") from exc


def _tts(args: argparse.Namespace, api_key: str, base_url: str) -> None:
    if args.model not in TTS_MODELS:
        raise SystemExit(f"unsupported Fish Audio TTS model: {args.model}")
    if args.format not in OUTPUT_FORMATS:
        raise SystemExit(f"unsupported TTS format: {args.format}")
    if not args.voice and not args.reference_audio:
        raise SystemExit("provide --voice or --reference-audio with --reference-text")
    if bool(args.reference_audio) != bool(args.reference_text):
        raise SystemExit("--reference-audio and --reference-text must be provided together")

    payload: dict[str, Any] = {
        "model": args.model,
        "input": _read_text(args),
        "response_format": args.format,
    }
    if args.voice:
        payload["voice"] = args.voice
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
    body, content_type = _open_api_request(request, args.timeout_seconds)
    if not body:
        raise SystemExit("Fish Audio TTS returned an empty body")
    if content_type.lower().split(";", 1)[0].strip() in {"application/json", "text/json"}:
        raise SystemExit(f"Fish Audio TTS returned JSON instead of audio; body_bytes={len(body)}")

    output = Path(args.output).expanduser().resolve()
    _atomic_write(output, body, args.overwrite)
    print(f"OK mode=tts model={args.model} output={output} bytes={len(body)}")


def _multipart_stt_body(args: argparse.Namespace) -> tuple[bytes, str]:
    audio_path = Path(args.audio).expanduser().resolve()
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


def _stt(args: argparse.Namespace, api_key: str, base_url: str) -> None:
    if args.model != STT_MODEL:
        raise SystemExit(f"unsupported Fish Audio STT model: {args.model}")
    body, content_type = _multipart_stt_body(args)
    request = urllib.request.Request(
        _api_url(base_url, "/audio/transcriptions"),
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": content_type,
            "User-Agent": "fish-audio-speech/1.0",
        },
        method="POST",
    )
    raw, _ = _open_api_request(request, args.timeout_seconds)
    try:
        response = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Fish Audio STT response is not JSON; body_bytes={len(raw)}") from exc
    if not isinstance(response, dict):
        raise SystemExit(f"Fish Audio STT response is not an object: {type(response).__name__}")
    transcript = response.get("text")
    if not isinstance(transcript, str):
        raise SystemExit(f"Fish Audio STT response is missing string text; keys={sorted(response.keys())}")

    output = Path(args.output).expanduser().resolve()
    _atomic_write(output, transcript.encode("utf-8"), args.overwrite)
    if args.json_output:
        json_output = Path(args.json_output).expanduser().resolve()
        encoded = (json.dumps(response, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _atomic_write(json_output, encoded, args.overwrite)
    print(
        f"OK mode=stt model={args.model} output={output} "
        f"characters={len(transcript)} json_saved={bool(args.json_output)}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="new-api host root or a URL ending in /v1")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--overwrite", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tts = subparsers.add_parser("tts", help="synthesize speech")
    text_source = tts.add_mutually_exclusive_group(required=True)
    text_source.add_argument("--text")
    text_source.add_argument("--text-file")
    tts.add_argument("--voice", help="Fish Audio reference_id")
    tts.add_argument("--reference-audio", help="local authorized reference audio")
    tts.add_argument("--reference-text", help="exact transcript for the reference audio")
    tts.add_argument("--model", default="fish-s2-pro")
    tts.add_argument("--format", default="mp3")
    tts.add_argument("--output", required=True)

    stt = subparsers.add_parser("stt", help="transcribe speech")
    stt.add_argument("audio")
    stt.add_argument("--model", default=STT_MODEL)
    stt.add_argument("--language")
    stt.add_argument("--ignore-timestamps", action="store_true")
    stt.add_argument("--output", required=True)
    stt.add_argument("--json-output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.timeout_seconds <= 0:
        raise SystemExit("timeout must be positive")
    api_key = _api_key()
    if not api_key:
        raise SystemExit("missing API key: set NEW_API_API_KEY or OPENAI_API_KEY")
    base_url = _base_url(args.base_url)
    if not base_url:
        raise SystemExit("missing base URL: set NEW_API_BASE_URL, OPENAI_BASE_URL, or --base-url")
    if args.command == "tts":
        _tts(args, api_key, base_url)
    else:
        _stt(args, api_key, base_url)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Fish Audio request interrupted", file=sys.stderr)
        raise SystemExit(130)
