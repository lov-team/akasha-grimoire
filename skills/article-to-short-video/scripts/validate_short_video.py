#!/usr/bin/env python3
"""Validate a vertical short video, its audio, black frames, and optional SRT."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()[-1200:]
        raise SystemExit(f"command failed ({command[0]}): {message}")
    return completed.stdout


def require_tools() -> None:
    missing = [name for name in ("ffprobe", "ffmpeg") if not shutil.which(name)]
    if missing:
        raise SystemExit(f"missing required tool(s): {', '.join(missing)}")


def probe_video(path: Path) -> dict[str, Any]:
    raw = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ]
    )
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise SystemExit("ffprobe returned a non-object JSON value")
    return result


def ratio(value: str) -> float:
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator)


def analyze_loudness(path: Path) -> dict[str, float]:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit("ffmpeg loudness analysis failed")
    matches = re.findall(r"\{\s*\"input_i\".*?\}", completed.stderr, re.DOTALL)
    if not matches:
        raise SystemExit("could not parse loudnorm analysis")
    data = json.loads(matches[-1])
    return {
        "integrated_lufs": float(data["input_i"]),
        "true_peak_dbfs": float(data["input_tp"]),
        "loudness_range_lu": float(data["input_lra"]),
    }


def detect_black(path: Path, duration: float) -> list[dict[str, float]]:
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            f"blackdetect=d={duration}:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit("ffmpeg black-frame analysis failed")
    results = []
    pattern = re.compile(
        r"black_start:(?P<start>[0-9.]+)\s+black_end:(?P<end>[0-9.]+)\s+black_duration:(?P<duration>[0-9.]+)"
    )
    for match in pattern.finditer(completed.stderr):
        results.append({key: float(value) for key, value in match.groupdict().items()})
    return results


def srt_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def validate_srt(path: Path, video_duration: float) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig").strip()
    blocks = re.split(r"\n\s*\n", text) if text else []
    entries = []
    errors = []
    previous_end = 0.0
    for expected_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3:
            errors.append(f"block {expected_index} has fewer than three lines")
            continue
        try:
            actual_index = int(lines[0])
            start_text, end_text = lines[1].split(" --> ")
            start, end = srt_seconds(start_text), srt_seconds(end_text)
        except (ValueError, IndexError):
            errors.append(f"block {expected_index} has invalid numbering or timing")
            continue
        caption_lines = lines[2:]
        if actual_index != expected_index:
            errors.append(f"subtitle index {actual_index} should be {expected_index}")
        if start < previous_end - 0.001:
            errors.append(f"subtitle {actual_index} overlaps the previous subtitle")
        if end <= start:
            errors.append(f"subtitle {actual_index} has non-positive duration")
        if end > video_duration + 0.05:
            errors.append(f"subtitle {actual_index} exceeds video duration")
        if len(caption_lines) > 2:
            errors.append(f"subtitle {actual_index} exceeds two lines")
        previous_end = end
        entries.append({"index": actual_index, "start": start, "end": end, "lines": len(caption_lines)})
    return {"entries": len(entries), "last_end": previous_end, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--srt", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument("--duration-tolerance", type=float, default=0.05)
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--min-lufs", type=float, default=-18.0)
    parser.add_argument("--max-lufs", type=float, default=-13.0)
    parser.add_argument("--max-true-peak", type=float, default=-1.0)
    parser.add_argument("--black-duration", type=float, default=0.4)
    args = parser.parse_args()

    require_tools()
    video = args.video.expanduser().resolve()
    if not video.is_file() or video.stat().st_size == 0:
        raise SystemExit(f"video does not exist or is empty: {video}")
    if args.duration <= 0 or args.fps <= 0 or args.black_duration <= 0:
        raise SystemExit("duration, fps, and black duration must be positive")

    probe = probe_video(video)
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    errors = []
    if not video_streams:
        errors.append("missing video stream")
    if not audio_streams:
        errors.append("missing audio stream")

    actual_duration = float(probe.get("format", {}).get("duration", 0))
    if abs(actual_duration - args.duration) > args.duration_tolerance:
        errors.append(f"duration {actual_duration:.3f}s is outside tolerance")

    expected_frames = round(args.duration * args.fps)
    if video_streams:
        stream = video_streams[0]
        if stream.get("width") != args.width or stream.get("height") != args.height:
            errors.append(f"resolution is {stream.get('width')}x{stream.get('height')}")
        actual_fps = ratio(stream.get("r_frame_rate", "0/1"))
        if abs(actual_fps - args.fps) > 0.001:
            errors.append(f"frame rate is {actual_fps:g}")
        frames = int(stream.get("nb_read_frames") or 0)
        if frames != expected_frames:
            errors.append(f"frame count is {frames}, expected {expected_frames}")

    loudness = analyze_loudness(video) if audio_streams else None
    if loudness:
        if not args.min_lufs <= loudness["integrated_lufs"] <= args.max_lufs:
            errors.append(f"integrated loudness {loudness['integrated_lufs']:.2f} LUFS is outside range")
        if loudness["true_peak_dbfs"] > args.max_true_peak:
            errors.append(f"true peak {loudness['true_peak_dbfs']:.2f} dBFS exceeds limit")

    black_frames = detect_black(video, args.black_duration)
    if black_frames:
        errors.append(f"detected {len(black_frames)} black segment(s)")

    subtitle = None
    if args.srt:
        srt = args.srt.expanduser().resolve()
        if not srt.is_file():
            errors.append(f"SRT does not exist: {srt}")
        else:
            subtitle = validate_srt(srt, actual_duration)
            errors.extend(subtitle["errors"])

    report = {
        "ok": not errors,
        "video": str(video),
        "duration": actual_duration,
        "expected_frames": expected_frames,
        "probe": probe,
        "loudness": loudness,
        "black_segments": black_frames,
        "subtitles": subtitle,
        "errors": errors,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        report_path = args.report.expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("validation interrupted", file=sys.stderr)
        raise SystemExit(130)
