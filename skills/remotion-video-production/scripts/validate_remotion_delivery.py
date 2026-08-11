#!/usr/bin/env python3
"""Validate a recoverable Remotion delivery and its rendered media."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import subprocess
import sys
from typing import Any

REQUIRED_FILES = ("package.json", "brief.md", "design.md", "storyboard.md", "timeline.json", "commands.md")
REQUIRED_DIRS = ("src", "public", "render", "qa")
SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
BANNED = ("Date.now()", "Math.random()")


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"command failed ({' '.join(command)}): {detail}")
    return result.stdout


def parse_json_output(output: str) -> Any:
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("command returned no JSON")


def parse_compositions_output(output: str) -> list[dict[str, Any]]:
    try:
        value = parse_json_output(output)
        if isinstance(value, list):
            return value
    except ValueError:
        pass
    pattern = re.compile(r"^\s*(\S+)\s+([0-9.]+)\s+(\d+)x(\d+)\s+(\d+)\s+\(")
    compositions = []
    for line in output.splitlines():
        match = pattern.match(line)
        if match:
            identifier, fps, width, height, frames = match.groups()
            compositions.append({
                "id": identifier, "fps": float(fps), "width": int(width),
                "height": int(height), "durationInFrames": int(frames),
            })
    if not compositions:
        raise ValueError("Remotion returned no parseable compositions")
    return compositions


def fps_value(value: str) -> float:
    numerator, denominator = value.split("/", 1)
    denominator_value = float(denominator)
    if denominator_value == 0:
        raise ValueError(f"invalid video frame rate: {value}")
    result = float(numerator) / denominator_value
    if result <= 0:
        raise ValueError(f"invalid video frame rate: {value}")
    return result


def probe_video(path: Path, cwd: Path) -> dict[str, Any]:
    payload = parse_json_output(run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
    ], cwd))
    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video is None:
        raise ValueError(f"video stream missing: {path}")
    duration = float(video.get("duration") or payload.get("format", {}).get("duration") or 0)
    fps = fps_value(video.get("avg_frame_rate", "0/1"))
    raw_frames = video.get("nb_frames")
    frames = int(raw_frames) if raw_frames and raw_frames != "N/A" else round(duration * fps)
    return {
        "path": str(path),
        "codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name") if audio else None,
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": fps,
        "duration": duration,
        "frames": frames,
    }


def validate(args: argparse.Namespace) -> dict[str, Any]:
    project = args.project.resolve()
    errors: list[str] = []

    for name in REQUIRED_FILES:
        if not (project / name).is_file():
            errors.append(f"required file missing: {name}")
    for name in REQUIRED_DIRS:
        if not (project / name).is_dir():
            errors.append(f"required directory missing: {name}/")

    timeline: list[dict[str, Any]] = []
    timeline_path = project / "timeline.json"
    if timeline_path.is_file():
        try:
            value = json.loads(timeline_path.read_text(encoding="utf-8"))
            if not isinstance(value, list) or not value:
                raise ValueError("timeline.json must be a non-empty array")
            timeline = value
            cursor = 0
            for scene in timeline:
                scene_id = scene.get("id")
                if not isinstance(scene_id, str) or not scene_id.strip():
                    errors.append("timeline scene id must be a non-empty string")
                    scene_id = "?"
                start = int(scene["from"])
                duration = int(scene["durationInFrames"])
                if start != cursor:
                    errors.append(f"timeline gap or overlap before {scene_id}: expected {cursor}, got {start}")
                if duration <= 0:
                    errors.append(f"timeline duration must be positive: {scene_id}")
                cursor = start + duration
            if cursor != args.duration_frames:
                errors.append(f"timeline ends at {cursor}, expected {args.duration_frames}")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"invalid timeline.json: {exc}")

    for path in (project / "src").rglob("*") if (project / "src").is_dir() else ():
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in BANNED:
                if token in text:
                    errors.append(f"nondeterministic token {token} in {path.relative_to(project)}")

    composition: dict[str, Any] = {"id": args.composition}
    try:
        compositions = parse_compositions_output(run([
            "npx", "remotion", "compositions", "src/index.ts"
        ], project))
        match = next((item for item in compositions if item.get("id") == args.composition), None)
        if match is None:
            errors.append(f"composition missing: {args.composition}")
        else:
            composition = match
            expected = {
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
                "durationInFrames": args.duration_frames,
            }
            for field, value in expected.items():
                if float(match.get(field, -1)) != float(value):
                    errors.append(f"composition {field} expected {value}, got {match.get(field)}")
    except (RuntimeError, ValueError, TypeError) as exc:
        errors.append(str(exc))

    videos: list[dict[str, Any]] = []
    for path in filter(None, (args.video, args.sfx_only_video)):
        resolved = path.resolve()
        if not resolved.is_file():
            errors.append(f"video missing: {resolved}")
            continue
        try:
            media = probe_video(resolved, project)
            videos.append(media)
            expected = {
                "width": args.width,
                "height": args.height,
                "frames": args.duration_frames,
            }
            for field, value in expected.items():
                if media[field] != value:
                    errors.append(f"video {field} expected {value}, got {media[field]}: {resolved.name}")
            if abs(media["fps"] - args.fps) > 0.001:
                errors.append(f"video fps expected {args.fps}, got {media['fps']}: {resolved.name}")
            if media["codec"] != "h264":
                errors.append(f"video codec expected h264, got {media['codec']}: {resolved.name}")
            if media["audio_codec"] != "aac":
                errors.append(f"audio codec expected aac, got {media['audio_codec']}: {resolved.name}")
            try:
                run(["ffmpeg", "-v", "error", "-i", str(resolved), "-f", "null", "-"], project)
            except RuntimeError as exc:
                errors.append(str(exc))
        except (RuntimeError, ValueError, TypeError) as exc:
            errors.append(str(exc))

    if len(videos) == 2:
        for field in ("width", "height", "fps", "frames"):
            if videos[0][field] != videos[1][field]:
                errors.append(f"BGM/SFX-only mismatch: {field}")
        try:
            hashes = [
                run(["ffmpeg", "-v", "error", "-i", video["path"], "-map", "0:v:0", "-f", "framemd5", "-"], project)
                for video in videos
            ]
            if hashes[0] != hashes[1]:
                errors.append("BGM/SFX-only decoded video frames differ")
        except RuntimeError as exc:
            errors.append(str(exc))

    directory = args.keyframes_dir.resolve() if args.keyframes_dir else project / "qa/keyframes"
    if not directory.is_dir():
        errors.append(f"keyframes missing: {directory}")
    else:
        for scene in timeline:
            scene_id = scene.get("id")
            if isinstance(scene_id, str) and scene_id and not any(directory.glob(f"{scene_id}-*.png")):
                errors.append(f"keyframe missing for scene {scene_id}")
    if args.captions and not args.captions.resolve().is_file():
        errors.append(f"captions missing: {args.captions.resolve()}")

    return {"ok": not errors, "errors": errors, "timeline": timeline, "composition": composition, "videos": videos}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("project", type=Path)
    result.add_argument("--composition", required=True)
    result.add_argument("--video", required=True, type=Path)
    result.add_argument("--width", required=True, type=int)
    result.add_argument("--height", required=True, type=int)
    result.add_argument("--fps", required=True, type=float)
    result.add_argument("--duration-frames", required=True, type=int)
    result.add_argument("--report", required=True, type=Path)
    result.add_argument("--sfx-only-video", type=Path)
    result.add_argument("--keyframes-dir", type=Path)
    result.add_argument("--captions", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    report = validate(args)
    destination = args.report.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
