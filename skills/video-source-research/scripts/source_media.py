#!/usr/bin/env python3
"""Inspect, download, verify, hash, and register source media."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SourceMediaError(RuntimeError):
    pass


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1600:]
        raise SourceMediaError(f"command failed ({command[0]}): {detail}")
    return completed


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise SourceMediaError(f"missing required tool: {name}")
    return executable


def safe_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def parse_ratio(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return None


def probe_media(path: Path) -> dict[str, Any]:
    ffprobe = require_tool("ffprobe")
    completed = run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SourceMediaError("ffprobe returned invalid JSON") from exc
    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video and not audio:
        raise SourceMediaError(f"ffprobe found no audio or video stream: {path}")
    fmt = data.get("format") if isinstance(data.get("format"), dict) else {}
    return {
        "duration": float(fmt.get("duration") or 0),
        "format": fmt.get("format_name"),
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "fps": parse_ratio(video.get("avg_frame_rate")) if video else None,
        "video_codec": video.get("codec_name") if video else None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "sample_rate": int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        "channels": audio.get("channels") if audio else None,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "assets": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceMediaError(f"manifest is invalid JSON: {path}") from exc
    if data.get("version") != 1 or not isinstance(data.get("assets"), list):
        raise SourceMediaError("manifest must contain version=1 and an assets array")
    return data


def save_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def register_asset(
    *,
    file_path: Path,
    manifest_path: Path,
    shot_id: str,
    source_url: str,
    source_page: str,
    creator: str,
    license_name: str,
    notes: str,
    status: str,
) -> dict[str, Any]:
    resolved = file_path.expanduser().resolve()
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise SourceMediaError(f"media file does not exist or is empty: {resolved}")
    media = probe_media(resolved)
    checksum = sha256(resolved)
    asset_id = f"A-{shot_id}-{checksum[:8].upper()}"
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = {
        "asset_id": asset_id,
        "shot_id": shot_id,
        "status": status,
        "source_url": source_url,
        "source_page": source_page or source_url,
        "creator": creator,
        "license": license_name,
        "retrieved_at": now,
        "local_path": str(resolved),
        "sha256": checksum,
        "bytes": resolved.stat().st_size,
        "media": media,
        "notes": notes,
    }
    manifest = load_manifest(manifest_path)
    assets = manifest["assets"]
    previous = next((item for item in assets if item.get("asset_id") == asset_id), None)
    if previous and previous.get("retrieved_at"):
        record["retrieved_at"] = previous["retrieved_at"]
    manifest["assets"] = [item for item in assets if item.get("asset_id") != asset_id] + [record]
    save_manifest(manifest_path, manifest)
    return record


def sanitize_filename(value: str, fallback: str = "source-media") -> str:
    name = Path(urllib.parse.unquote(value)).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return name or fallback


def download_direct(url: str, output_dir: Path, filename: str | None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed_name = Path(urllib.parse.urlsplit(url).path).name
    target = output_dir / sanitize_filename(filename or parsed_name)
    if target.exists():
        raise SourceMediaError(f"output already exists: {target}")
    fd, temporary = tempfile.mkstemp(prefix=".download-", suffix=".part", dir=output_dir)
    os.close(fd)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AkashaVideoSource/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response, open(temporary, "wb") as handle:
            shutil.copyfileobj(response, handle)
        temp_path = Path(temporary)
        if temp_path.stat().st_size == 0:
            raise SourceMediaError("direct download returned an empty file")
        probe_media(temp_path)
        os.replace(temp_path, target)
        return target
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def download_ytdlp(url: str, output_dir: Path, filename: str | None) -> Path:
    ytdlp = require_tool("yt-dlp")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".yt-dlp-", dir=output_dir) as temporary:
        temp_dir = Path(temporary)
        output_template = str(temp_dir / "%(title).80s-%(id)s.%(ext)s")
        completed = run(
            [
                ytdlp,
                "--no-playlist",
                "--no-overwrites",
                "--restrict-filenames",
                "--merge-output-format",
                "mp4",
                "-f",
                "bv*+ba/b",
                "-o",
                output_template,
                "--print",
                "after_move:filepath",
                "--",
                url,
            ]
        )
        candidates = [Path(line.strip()) for line in completed.stdout.splitlines() if line.strip()]
        source = next((item for item in reversed(candidates) if item.is_file()), None)
        if source is None:
            files = [item for item in temp_dir.iterdir() if item.is_file()]
            source = files[0] if len(files) == 1 else None
        if source is None:
            raise SourceMediaError("yt-dlp did not produce exactly one media file")
        probe_media(source)
        target_name = sanitize_filename(filename or source.name)
        target = output_dir / target_name
        if target.exists():
            raise SourceMediaError(f"output already exists: {target}")
        os.replace(source, target)
        return target


def inspect_url(url: str) -> dict[str, Any]:
    ytdlp = require_tool("yt-dlp")
    completed = run([ytdlp, "--dump-single-json", "--no-playlist", "--no-warnings", "--", url])
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SourceMediaError("yt-dlp returned invalid JSON") from exc
    keys = ("id", "title", "duration", "uploader", "webpage_url", "ext", "width", "height", "fps")
    return {key: raw.get(key) for key in keys}


def common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--shot-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-page", default="")
    parser.add_argument("--creator", default="")
    parser.add_argument("--license", dest="license_name", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--status", choices=("candidate", "selected", "rejected"), default="candidate")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect-url", help="Inspect a URL through yt-dlp without downloading")
    inspect_parser.add_argument("--url", required=True)

    download_parser = subparsers.add_parser("download", help="Download and register one URL")
    download_parser.add_argument("--url", required=True)
    download_parser.add_argument("--output-dir", type=Path, required=True)
    download_parser.add_argument("--filename")
    download_parser.add_argument("--direct", action="store_true")
    common_arguments(download_parser)

    local_parser = subparsers.add_parser("add-local", help="Verify and register an existing local media file")
    local_parser.add_argument("--file", type=Path, required=True)
    local_parser.add_argument("--source-url", default="")
    common_arguments(local_parser)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "inspect-url":
            print(json.dumps(inspect_url(args.url), ensure_ascii=False, indent=2))
            return 0

        if args.command == "download":
            print(f"downloading: {safe_url(args.url)}", file=sys.stderr)
            output_dir = args.output_dir.expanduser().resolve()
            path = (
                download_direct(args.url, output_dir, args.filename)
                if args.direct
                else download_ytdlp(args.url, output_dir, args.filename)
            )
            source_url = args.url
        else:
            path = args.file
            source_url = args.source_url

        record = register_asset(
            file_path=path,
            manifest_path=args.manifest.expanduser().resolve(),
            shot_id=args.shot_id,
            source_url=source_url,
            source_page=args.source_page,
            creator=args.creator,
            license_name=args.license_name,
            notes=args.notes,
            status=args.status,
        )
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    except (OSError, SourceMediaError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
