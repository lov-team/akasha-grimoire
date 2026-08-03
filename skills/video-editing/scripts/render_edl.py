#!/usr/bin/env python3
"""Render a sequential JSON edit decision list with FFmpeg."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class EdlError(RuntimeError):
    pass


@dataclass(frozen=True)
class Clip:
    clip_id: str
    shot_id: str
    path: Path
    source_in: float
    source_out: float
    fit: str
    volume: float
    has_audio: bool

    @property
    def duration(self) -> float:
        return self.source_out - self.source_in


@dataclass(frozen=True)
class Timeline:
    width: int
    height: int
    fps: float
    sample_rate: int
    background: str


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise EdlError(f"missing required tool: {name}")
    return executable


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2000:]
        raise EdlError(f"command failed ({command[0]}): {detail}")
    return completed


def parse_ratio(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: Path) -> dict[str, Any]:
    completed = run(
        [
            require_tool("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EdlError("ffprobe returned invalid JSON") from exc


def load_edl(path: Path) -> tuple[Timeline, list[Clip]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EdlError(f"could not read EDL: {path}") from exc
    if data.get("version") != 1:
        raise EdlError("EDL version must be 1")
    raw_timeline = data.get("timeline")
    raw_clips = data.get("clips")
    if not isinstance(raw_timeline, dict) or not isinstance(raw_clips, list) or not raw_clips:
        raise EdlError("EDL requires a timeline object and a non-empty clips array")
    try:
        timeline = Timeline(
            width=int(raw_timeline.get("width")),
            height=int(raw_timeline.get("height")),
            fps=float(raw_timeline.get("fps")),
            sample_rate=int(raw_timeline.get("sample_rate", 48000)),
            background=str(raw_timeline.get("background", "black")),
        )
    except (TypeError, ValueError) as exc:
        raise EdlError("timeline dimensions, fps, and sample_rate must be numeric") from exc
    if timeline.width <= 0 or timeline.height <= 0 or timeline.width % 2 or timeline.height % 2:
        raise EdlError("timeline width and height must be positive even integers")
    if not 0 < timeline.fps <= 120 or not 8000 <= timeline.sample_rate <= 192000:
        raise EdlError("timeline fps or sample_rate is outside supported range")
    color_pattern = r"(?:[A-Za-z]+|0x[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?|#[0-9A-Fa-f]{6})"
    if not re.fullmatch(color_pattern, timeline.background):
        raise EdlError("timeline background must be a named color, 0xRRGGBB[AA], or #RRGGBB")

    clips: list[Clip] = []
    seen: set[str] = set()
    base = path.parent
    for index, item in enumerate(raw_clips, start=1):
        if not isinstance(item, dict):
            raise EdlError(f"clip {index} must be an object")
        clip_id = str(item.get("clip_id", "")).strip()
        shot_id = str(item.get("shot_id", "")).strip()
        if not clip_id or not shot_id or clip_id in seen:
            raise EdlError(f"clip {index} has a missing or duplicate clip_id/shot_id")
        seen.add(clip_id)
        raw_path = Path(str(item.get("path", ""))).expanduser()
        media_path = raw_path.resolve() if raw_path.is_absolute() else (base / raw_path).resolve()
        if not media_path.is_file() or media_path.stat().st_size == 0:
            raise EdlError(f"clip source is missing or empty: {media_path}")
        try:
            source_in = float(item.get("source_in", 0))
            source_out = float(item["source_out"])
            volume = float(item.get("volume", 1.0))
        except (KeyError, TypeError, ValueError) as exc:
            raise EdlError(f"clip {clip_id} has invalid in/out/volume") from exc
        fit = str(item.get("fit", "cover"))
        if source_in < 0 or source_out <= source_in or volume < 0 or fit not in {"cover", "contain"}:
            raise EdlError(f"clip {clip_id} has invalid range, fit, or volume")
        media_probe = probe(media_path)
        streams = media_probe.get("streams") if isinstance(media_probe.get("streams"), list) else []
        if not any(stream.get("codec_type") == "video" for stream in streams):
            raise EdlError(f"clip {clip_id} has no video stream")
        duration = float(media_probe.get("format", {}).get("duration") or 0)
        if duration and source_out > duration + 0.05:
            raise EdlError(f"clip {clip_id} source_out exceeds source duration {duration:.3f}s")
        clips.append(
            Clip(
                clip_id=clip_id,
                shot_id=shot_id,
                path=media_path,
                source_in=source_in,
                source_out=source_out,
                fit=fit,
                volume=volume,
                has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
            )
        )
    return timeline, clips


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def build_command(
    timeline: Timeline,
    clips: list[Clip],
    output: Path,
    *,
    crf: int,
    preset: str,
) -> list[str]:
    command = [require_tool("ffmpeg"), "-hide_banner", "-nostdin", "-n"]
    for clip in clips:
        command.extend(["-i", str(clip.path)])
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, clip in enumerate(clips):
        duration = number(clip.duration)
        if clip.fit == "cover":
            scale = (
                f"scale={timeline.width}:{timeline.height}:force_original_aspect_ratio=increase,"
                f"crop={timeline.width}:{timeline.height}"
            )
        else:
            scale = (
                f"scale={timeline.width}:{timeline.height}:force_original_aspect_ratio=decrease,"
                f"pad={timeline.width}:{timeline.height}:(ow-iw)/2:(oh-ih)/2:color={timeline.background}"
            )
        filters.append(
            f"[{index}:v:0]trim=start={number(clip.source_in)}:end={number(clip.source_out)},"
            f"setpts=PTS-STARTPTS,{scale},setsar=1,fps={number(timeline.fps)},format=yuv420p[v{index}]"
        )
        if clip.has_audio:
            filters.append(
                f"[{index}:a:0]atrim=start={number(clip.source_in)}:end={number(clip.source_out)},"
                f"asetpts=PTS-STARTPTS,aresample={timeline.sample_rate},"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,volume={number(clip.volume)}[a{index}]"
            )
        else:
            filters.append(
                f"anullsrc=r={timeline.sample_rate}:cl=stereo,atrim=duration={duration},"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
        concat_inputs.append(f"[v{index}][a{index}]")
    filters.append(f"{''.join(concat_inputs)}concat=n={len(clips)}:v=1:a=1[outv][outa]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return command


def verify_output(path: Path, timeline: Timeline, expected_duration: float) -> dict[str, Any]:
    data = probe(path)
    streams = data.get("streams") if isinstance(data.get("streams"), list) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise EdlError("rendered output is missing video or audio")
    if video.get("width") != timeline.width or video.get("height") != timeline.height:
        raise EdlError("rendered output has unexpected resolution")
    actual_fps = parse_ratio(video.get("avg_frame_rate"))
    if abs(actual_fps - timeline.fps) > 0.01:
        raise EdlError(f"rendered output fps is {actual_fps:g}")
    actual_duration = float(data.get("format", {}).get("duration") or 0)
    tolerance = max(0.2, 2 / timeline.fps)
    if abs(actual_duration - expected_duration) > tolerance:
        raise EdlError(
            f"rendered duration {actual_duration:.3f}s differs from EDL {expected_duration:.3f}s"
        )
    return {
        "duration": actual_duration,
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": actual_fps,
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "bytes": path.stat().st_size,
    }


def atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edl", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="medium")
    args = parser.parse_args()
    try:
        if not 0 <= args.crf <= 51:
            raise EdlError("CRF must be between 0 and 51")
        edl = args.edl.expanduser().resolve()
        output = args.output.expanduser().resolve()
        if output.exists():
            raise EdlError(f"output already exists: {output}")
        timeline, clips = load_edl(edl)
        expected_duration = sum(clip.duration for clip in clips)
        preview_command = build_command(timeline, clips, output, crf=args.crf, preset=args.preset)
        if args.dry_run:
            print(
                json.dumps(
                    {"duration": expected_duration, "clips": len(clips), "command": preview_command},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
        if temporary.exists():
            raise EdlError(f"temporary output already exists: {temporary}")
        command = build_command(timeline, clips, temporary, crf=args.crf, preset=args.preset)
        try:
            completed = run(command)
            verification = verify_output(temporary, timeline, expected_duration)
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()
        record = {
            "ok": True,
            "edl": str(edl),
            "output": str(output),
            "expected_duration": expected_duration,
            "command": command,
            "exit_status": completed.returncode,
            "verification": verification,
        }
        encoded = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        if args.record:
            atomic_write(args.record.expanduser().resolve(), encoded)
        print(encoded, end="")
        return 0
    except (OSError, EdlError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
