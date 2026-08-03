#!/usr/bin/env python3
"""Run technical video QA and optionally extract representative frames."""

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
from pathlib import Path
from typing import Any


class VideoQcError(RuntimeError):
    pass


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise VideoQcError(f"missing required tool: {name}")
    return executable


def run(command: list[str], *, allow_stderr: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2000:]
        raise VideoQcError(f"command failed ({command[0]}): {detail}")
    if not allow_stderr and completed.stderr.strip():
        raise VideoQcError(f"command reported decode errors: {completed.stderr.strip()[-2000:]}")
    return completed


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ratio(value: str | None) -> float:
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
            "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise VideoQcError("ffprobe returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise VideoQcError("ffprobe returned a non-object value")
    return data


def decode_check(path: Path) -> None:
    run(
        [
            require_tool("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        allow_stderr=False,
    )


def filter_stderr(path: Path, *, video_filter: str | None = None, audio_filter: str | None = None) -> str:
    command = [require_tool("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(path)]
    if video_filter:
        command.extend(["-vf", video_filter, "-an"])
    if audio_filter:
        command.extend(["-af", audio_filter, "-vn"])
    command.extend(["-f", "null", "-"])
    return run(command).stderr


def detect_black(path: Path, minimum: float) -> list[dict[str, float]]:
    stderr = filter_stderr(path, video_filter=f"blackdetect=d={minimum}:pix_th=0.10")
    pattern = re.compile(
        r"black_start:(?P<start>[0-9.]+)\s+black_end:(?P<end>[0-9.]+)\s+black_duration:(?P<duration>[0-9.]+)"
    )
    return [{key: float(value) for key, value in match.groupdict().items()} for match in pattern.finditer(stderr)]


def detect_freeze(path: Path, minimum: float) -> list[dict[str, float | None]]:
    stderr = filter_stderr(path, video_filter=f"freezedetect=n=-50dB:d={minimum}")
    starts = [float(value) for value in re.findall(r"freeze_start:\s*([0-9.]+)", stderr)]
    durations = [float(value) for value in re.findall(r"freeze_duration:\s*([0-9.]+)", stderr)]
    ends = [float(value) for value in re.findall(r"freeze_end:\s*([0-9.]+)", stderr)]
    return [
        {
            "start": start,
            "end": ends[index] if index < len(ends) else None,
            "duration": durations[index] if index < len(durations) else None,
        }
        for index, start in enumerate(starts)
    ]


def detect_silence(path: Path, minimum: float) -> list[dict[str, float | None]]:
    stderr = filter_stderr(path, audio_filter=f"silencedetect=noise=-50dB:d={minimum}")
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", stderr)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*([0-9.]+)", stderr)]
    durations = [float(value) for value in re.findall(r"silence_duration:\s*([0-9.]+)", stderr)]
    return [
        {
            "start": start,
            "end": ends[index] if index < len(ends) else None,
            "duration": durations[index] if index < len(durations) else None,
        }
        for index, start in enumerate(starts)
    ]


def analyze_loudness(path: Path) -> dict[str, float]:
    stderr = filter_stderr(path, audio_filter="loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json")
    matches = re.findall(r'\{\s*"input_i".*?\}', stderr, re.DOTALL)
    if not matches:
        raise VideoQcError("could not parse loudnorm analysis")
    data = json.loads(matches[-1])
    return {
        "integrated_lufs": float(data["input_i"]),
        "true_peak_dbfs": float(data["input_tp"]),
        "loudness_range_lu": float(data["input_lra"]),
    }


def srt_seconds(value: str) -> float:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", value)
    if not match:
        raise ValueError(value)
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def validate_srt(path: Path, video_duration: float) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig").strip()
    blocks = re.split(r"\n\s*\n", text) if text else []
    errors: list[str] = []
    entries = 0
    previous_end = 0.0
    last_end = 0.0
    for expected_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3:
            errors.append(f"subtitle block {expected_index} has fewer than three lines")
            continue
        try:
            actual_index = int(lines[0])
            start_text, end_text = lines[1].split(" --> ")
            start, end = srt_seconds(start_text), srt_seconds(end_text)
        except (ValueError, IndexError):
            errors.append(f"subtitle block {expected_index} has invalid numbering or timing")
            continue
        entries += 1
        if actual_index != expected_index:
            errors.append(f"subtitle index {actual_index} should be {expected_index}")
        if start < previous_end - 0.001:
            errors.append(f"subtitle {actual_index} overlaps the previous subtitle")
        if end <= start:
            errors.append(f"subtitle {actual_index} has non-positive duration")
        if end > video_duration + 0.05:
            errors.append(f"subtitle {actual_index} exceeds video duration")
        if len(lines[2:]) > 2:
            errors.append(f"subtitle {actual_index} exceeds two lines")
        previous_end = end
        last_end = end
    return {"entries": entries, "last_end": last_end, "errors": errors}


def frame_positions(duration: float) -> list[float]:
    if duration <= 0.25:
        return [0.0]
    candidates = [0.1, duration * 0.25, duration * 0.5, duration * 0.75, max(0.0, duration - 0.1)]
    result: list[float] = []
    for value in candidates:
        rounded = round(min(max(value, 0.0), max(0.0, duration - 0.01)), 3)
        if not result or abs(rounded - result[-1]) > 0.05:
            result.append(rounded)
    return result


def extract_frames(path: Path, duration: float, output_dir: Path) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, timestamp in enumerate(frame_positions(duration), start=1):
        target = output_dir / f"frame-{index:02d}-{timestamp:010.3f}s.jpg"
        if target.exists():
            raise VideoQcError(f"representative frame already exists: {target}")
        run(
            [
                require_tool("ffmpeg"),
                "-hide_banner",
                "-nostdin",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(target),
            ]
        )
        if not target.is_file() or target.stat().st_size == 0:
            raise VideoQcError(f"failed to extract representative frame at {timestamp:.3f}s")
        results.append({"time": timestamp, "path": str(target.resolve()), "bytes": target.stat().st_size})
    return results


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--srt", type=Path)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--duration-tolerance", type=float, default=0.15)
    parser.add_argument("--min-duration", type=float)
    parser.add_argument("--max-duration", type=float)
    parser.add_argument("--allow-no-audio", action="store_true")
    parser.add_argument("--black-duration", type=float, default=0.5)
    parser.add_argument("--freeze-duration", type=float, default=2.0)
    parser.add_argument("--silence-duration", type=float, default=2.0)
    parser.add_argument("--fail-on-black", action="store_true")
    parser.add_argument("--fail-on-freeze", action="store_true")
    parser.add_argument("--fail-on-silence", action="store_true")
    parser.add_argument("--min-lufs", type=float)
    parser.add_argument("--max-lufs", type=float)
    parser.add_argument("--max-true-peak", type=float)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report: dict[str, Any] = {}
    exit_code = 1
    try:
        video_path = args.video.expanduser().resolve()
        if not video_path.is_file() or video_path.stat().st_size == 0:
            raise VideoQcError(f"video does not exist or is empty: {video_path}")
        for name in ("duration_tolerance", "black_duration", "freeze_duration", "silence_duration"):
            if getattr(args, name) <= 0:
                raise VideoQcError(f"{name.replace('_', '-')} must be positive")

        media_probe = probe(video_path)
        streams = media_probe.get("streams") if isinstance(media_probe.get("streams"), list) else []
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        errors: list[str] = []
        warnings: list[str] = []
        if not video_stream:
            errors.append("missing video stream")
        if not audio_stream and not args.allow_no_audio:
            errors.append("missing audio stream; pass --allow-no-audio only for an intentional silent video")
        duration = float(media_probe.get("format", {}).get("duration") or 0)
        if duration <= 0:
            errors.append("duration is missing or non-positive")
        if args.duration is not None and abs(duration - args.duration) > args.duration_tolerance:
            errors.append(f"duration {duration:.3f}s differs from expected {args.duration:.3f}s")
        if args.min_duration is not None and duration < args.min_duration:
            errors.append(f"duration {duration:.3f}s is below minimum {args.min_duration:.3f}s")
        if args.max_duration is not None and duration > args.max_duration:
            errors.append(f"duration {duration:.3f}s exceeds maximum {args.max_duration:.3f}s")
        if video_stream:
            if args.width is not None and video_stream.get("width") != args.width:
                errors.append(f"width is {video_stream.get('width')}, expected {args.width}")
            if args.height is not None and video_stream.get("height") != args.height:
                errors.append(f"height is {video_stream.get('height')}, expected {args.height}")
            actual_fps = ratio(video_stream.get("avg_frame_rate"))
            if args.fps is not None and abs(actual_fps - args.fps) > 0.01:
                errors.append(f"frame rate is {actual_fps:g}, expected {args.fps:g}")
            decode_check(video_path)

        black = detect_black(video_path, args.black_duration) if video_stream else []
        freeze = detect_freeze(video_path, args.freeze_duration) if video_stream else []
        silence = detect_silence(video_path, args.silence_duration) if audio_stream else []
        if black:
            (errors if args.fail_on_black else warnings).append(f"detected {len(black)} black segment(s)")
        if freeze:
            (errors if args.fail_on_freeze else warnings).append(f"detected {len(freeze)} freeze segment(s)")
        if silence:
            (errors if args.fail_on_silence else warnings).append(f"detected {len(silence)} silence segment(s)")

        loudness = analyze_loudness(video_path) if audio_stream else None
        if loudness:
            if args.min_lufs is not None and loudness["integrated_lufs"] < args.min_lufs:
                errors.append(f"integrated loudness {loudness['integrated_lufs']:.2f} LUFS is too low")
            if args.max_lufs is not None and loudness["integrated_lufs"] > args.max_lufs:
                errors.append(f"integrated loudness {loudness['integrated_lufs']:.2f} LUFS is too high")
            if args.max_true_peak is not None and loudness["true_peak_dbfs"] > args.max_true_peak:
                errors.append(f"true peak {loudness['true_peak_dbfs']:.2f} dBFS exceeds limit")

        subtitles = None
        if args.srt:
            srt_path = args.srt.expanduser().resolve()
            if not srt_path.is_file():
                errors.append(f"SRT does not exist: {srt_path}")
            else:
                subtitles = validate_srt(srt_path, duration)
                errors.extend(subtitles["errors"])

        frames = extract_frames(video_path, duration, args.frames_dir.expanduser().resolve()) if args.frames_dir else []
        report = {
            "ok": not errors,
            "video": str(video_path),
            "sha256": sha256(video_path),
            "bytes": video_path.stat().st_size,
            "duration": duration,
            "probe": media_probe,
            "decode": {"ok": video_stream is not None},
            "loudness": loudness,
            "black_segments": black,
            "freeze_segments": freeze,
            "silence_segments": silence,
            "subtitles": subtitles,
            "representative_frames": frames,
            "warnings": warnings,
            "errors": errors,
        }
        exit_code = 0 if report["ok"] else 1
    except (OSError, VideoQcError) as exc:
        report = {"ok": False, "errors": [str(exc)], "warnings": []}

    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        atomic_write(args.report.expanduser().resolve(), encoded)
    print(encoded, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
