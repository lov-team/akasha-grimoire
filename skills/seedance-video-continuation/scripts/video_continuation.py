#!/usr/bin/env python3
"""Extract a continuation frame, verify its public copy, and stitch video segments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


class ContinuationError(RuntimeError):
    pass


def run(command: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=capture, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-1600:]
        raise ContinuationError(f"command failed ({command[0]}): {detail}")
    return completed


def require_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise ContinuationError(f"missing required tool(s): {', '.join(missing)}")


def ensure_source(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ContinuationError(f"source does not exist or is empty: {resolved}")
    return resolved


def ensure_output(path: Path, overwrite: bool) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists() and not overwrite:
        raise ContinuationError(f"output already exists: {resolved}; pass --overwrite to replace it")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def temp_output(path: Path) -> Path:
    suffix = path.suffix or ".tmp"
    return path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp{suffix}")


def probe(path: Path) -> dict[str, Any]:
    raw = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ]
    ).stdout
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContinuationError("ffprobe returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ContinuationError("ffprobe returned a non-object response")
    return payload


def fraction(value: str) -> float:
    try:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError) as exc:
        raise ContinuationError(f"invalid frame rate: {value}") from exc


def video_facts(path: Path) -> dict[str, Any]:
    payload = probe(path)
    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not videos:
        raise ContinuationError(f"missing video stream: {path}")
    video = videos[0]
    duration = float(payload.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise ContinuationError(f"invalid video duration: {path}")
    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": fraction(str(video.get("avg_frame_rate") or "0/1")),
        "has_audio": bool(audios),
        "video_codec": video.get("codec_name"),
        "audio_codec": audios[0].get("codec_name") if audios else None,
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract(args: argparse.Namespace) -> None:
    require_tools()
    source = ensure_source(args.source)
    output = ensure_output(args.output, args.overwrite)
    facts = video_facts(source)
    seconds_before_end = args.seconds_before_end
    if seconds_before_end < 0:
        raise ContinuationError("--seconds-before-end must be non-negative")
    timestamp = max(0.0, facts["duration"] - seconds_before_end)
    temp = temp_output(output)
    try:
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-ss",
                f"{timestamp:.6f}",
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-y",
                str(temp),
            ]
        )
        data = temp.read_bytes() if temp.is_file() else b""
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ContinuationError("ffmpeg did not produce a valid PNG frame")
        os.replace(temp, output)
    finally:
        if temp.exists():
            temp.unlink()
    result = {
        "ok": True,
        "source": str(source),
        "output": str(output),
        "source_duration": facts["duration"],
        "timestamp": timestamp,
        "seconds_before_end": seconds_before_end,
        "sha256": sha256_bytes(output.read_bytes()),
        "width": facts["width"],
        "height": facts["height"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def validate_public_https_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError("URL must be an absolute public HTTPS URL without userinfo")
    return value.strip()


def verify_url(args: argparse.Namespace) -> None:
    frame = ensure_source(args.frame)
    local = frame.read_bytes()
    request = urllib.request.Request(args.url, headers={"User-Agent": "seedance-video-continuation/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            remote = response.read(args.max_bytes + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ContinuationError(f"could not download public frame URL: {exc}") from exc
    if len(remote) > args.max_bytes:
        raise ContinuationError(f"remote frame exceeds --max-bytes ({args.max_bytes})")
    local_hash = sha256_bytes(local)
    remote_hash = sha256_bytes(remote)
    if local_hash != remote_hash:
        raise ContinuationError(
            f"remote frame does not match local frame: local sha256={local_hash}, remote sha256={remote_hash}"
        )
    print(
        json.dumps(
            {
                "ok": True,
                "frame": str(frame),
                "url": args.url,
                "bytes": len(remote),
                "content_type": content_type,
                "sha256": local_hash,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def stitch(args: argparse.Namespace) -> None:
    require_tools()
    previous = ensure_source(args.previous)
    next_video = ensure_source(args.next)
    output = ensure_output(args.output, args.overwrite)
    first = video_facts(previous)
    second = video_facts(next_video)
    if (first["width"], first["height"]) != (second["width"], second["height"]):
        raise ContinuationError("segments must have the same resolution before stitching")
    if abs(first["fps"] - second["fps"]) > 0.01:
        raise ContinuationError("segments must have the same frame rate before stitching")
    if first["has_audio"] != second["has_audio"]:
        raise ContinuationError("segments must either both contain audio or both be silent")
    if args.trim_next_start < 0 or args.trim_next_start >= second["duration"]:
        raise ContinuationError("--trim-next-start must be non-negative and shorter than the next segment")

    video_filters = (
        "[0:v:0]setpts=PTS-STARTPTS[v0];"
        f"[1:v:0]trim=start={args.trim_next_start:.6f},setpts=PTS-STARTPTS[v1];"
    )
    if first["has_audio"]:
        filters = (
            video_filters
            + "[0:a:0]asetpts=PTS-STARTPTS[a0];"
            + f"[1:a:0]atrim=start={args.trim_next_start:.6f},asetpts=PTS-STARTPTS[a1];"
            + "[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]"
        )
        maps = ["-map", "[outv]", "-map", "[outa]", "-c:a", "aac", "-b:a", "192k"]
    else:
        filters = video_filters + "[v0][v1]concat=n=2:v=1:a=0[outv]"
        maps = ["-map", "[outv]"]

    temp = temp_output(output)
    try:
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(previous),
                "-i",
                str(next_video),
                "-filter_complex",
                filters,
                *maps,
                "-c:v",
                "libx264",
                "-preset",
                args.preset,
                "-crf",
                str(args.crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-y",
                str(temp),
            ]
        )
        data = temp.read_bytes() if temp.is_file() else b""
        if len(data) < 12 or b"ftyp" not in data[:32]:
            raise ContinuationError("ffmpeg did not produce a valid MP4")
        os.replace(temp, output)
    finally:
        if temp.exists():
            temp.unlink()
    combined = video_facts(output)
    expected = first["duration"] + second["duration"] - args.trim_next_start
    if abs(combined["duration"] - expected) > max(0.25, 2 / first["fps"]):
        raise ContinuationError(
            f"stitched duration {combined['duration']:.3f}s differs from expected {expected:.3f}s"
        )
    print(
        json.dumps(
            {
                "ok": True,
                "previous": str(previous),
                "next": str(next_video),
                "output": str(output),
                "trim_next_start": args.trim_next_start,
                "expected_duration": expected,
                "actual_duration": combined["duration"],
                "width": combined["width"],
                "height": combined["height"],
                "fps": combined["fps"],
                "has_audio": combined["has_audio"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="extract a frame near the end of a source MP4")
    extract_parser.add_argument("--source", required=True, type=Path)
    extract_parser.add_argument("--output", required=True, type=Path)
    extract_parser.add_argument("--seconds-before-end", type=float, default=0.04)
    extract_parser.add_argument("--overwrite", action="store_true")
    extract_parser.set_defaults(func=extract)

    verify_parser = subparsers.add_parser("verify-url", help="verify a public frame URL matches a local frame")
    verify_parser.add_argument("--frame", required=True, type=Path)
    verify_parser.add_argument("--url", required=True, type=validate_public_https_url)
    verify_parser.add_argument("--timeout", type=float, default=30)
    verify_parser.add_argument("--max-bytes", type=int, default=20 * 1024 * 1024)
    verify_parser.set_defaults(func=verify_url)

    stitch_parser = subparsers.add_parser("stitch", help="re-encode and concatenate two compatible MP4 segments")
    stitch_parser.add_argument("--previous", required=True, type=Path)
    stitch_parser.add_argument("--next", required=True, type=Path)
    stitch_parser.add_argument("--output", required=True, type=Path)
    stitch_parser.add_argument("--trim-next-start", type=float, default=0.0)
    stitch_parser.add_argument("--crf", type=int, choices=range(0, 52), default=18)
    stitch_parser.add_argument("--preset", default="medium")
    stitch_parser.add_argument("--overwrite", action="store_true")
    stitch_parser.set_defaults(func=stitch)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if getattr(args, "timeout", 1) <= 0 or getattr(args, "max_bytes", 1) <= 0:
        raise ContinuationError("timeouts and byte limits must be positive")
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContinuationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
