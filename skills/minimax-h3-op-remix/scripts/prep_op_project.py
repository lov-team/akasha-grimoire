#!/usr/bin/env python3
"""Stage-0 OP Remix Project Initializer:
1. prep-video : Normalize raw OP video into frame-accurate source_24fps.mp4 + full_audio.m4a,
                detect candidate scene cuts via FFmpeg scdet, and export burned-in F=%{n} boundary grids.
2. prep-refs  : Strip header/footer text labels from 3-view character turnaround sheets into 960px *_3view.png
                and top-padded compact 448x672/736 *_sm.png cards (preventing tall-hat/ear clipping).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from PIL import Image


def run_cmd(cmd: list[str | Path]) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{proc.stderr[-2000:]}")
    return proc


def cmd_prep_video(args: argparse.Namespace) -> None:
    src = Path(args.source)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    master = out_dir / "source_24fps.mp4"
    audio = out_dir / "full_audio.m4a"

    vf = "fps=24,setsar=1"
    if args.max_seconds > 0:
        vf = f"trim=0:{args.max_seconds},setpts=PTS-STARTPTS," + vf
    run_cmd([
        args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
        "-vf", vf, "-an", "-r", "24", "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", master,
    ])
    af_args = ["-t", str(args.max_seconds)] if args.max_seconds > 0 else []
    run_cmd([
        args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
        *af_args, "-vn", "-c:a", "aac", "-b:a", "192k", audio,
    ])

    # Detect scene cuts on normalized 24fps master
    proc = subprocess.run(
        [args.ffmpeg, "-hide_banner", "-i", str(master), "-vf", f"scdet=threshold={args.threshold}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    times = [float(m.group(1)) for m in re.finditer(r"lavfi\.scd\.time:\s*([0-9.]+)", proc.stderr)]
    cut_frames = sorted({0, *[int(round(t * 24)) for t in times]})
    cuts_json = out_dir / "candidate_cuts.json"
    cuts_json.write_text(json.dumps({"fps": 24, "cut_frames": cut_frames}, indent=2), encoding="utf-8")
    print(f"[prep-video] Normalized {master} + {audio}; detected {len(cut_frames)} cut points -> {cuts_json}")

    # Export boundary verification sheets (drawtext BEFORE select so %{n} is true master frame index!)
    sample_frames = sorted({max(0, f + d) for f in cut_frames[1:] for d in (-2, -1, 0, 1)})
    chunk = 48
    for page, i in enumerate(range(0, len(sample_frames), chunk)):
        sub_f = sample_frames[i : i + chunk]
        rows = (len(sub_f) + 5) // 6
        sel = "+".join(f"eq(n,{f})" for f in sub_f)
        sheet = out_dir / f"cut_audit_page_{page:02d}.jpg"
        run_cmd([
            args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", master,
            "-vf", f"drawtext=text='F=%{{n}}':x=8:y=8:fontsize=30:fontcolor=yellow:box=1:boxcolor=black@0.85,select='{sel}',scale=320:180,tile=6x{rows}",
            "-vsync", "0", "-frames:v", "1", "-q:v", "2", sheet,
        ])
        print(f"[audit-sheet] {sheet}")


def cmd_prep_refs(args: argparse.Namespace) -> None:
    in_p = Path(args.sheet)
    out_dir = Path(args.out_dir)
    clean_dir = out_dir / "clean_refs"
    sm_dir = out_dir / "sm_front"
    clean_dir.mkdir(parents=True, exist_ok=True)
    sm_dir.mkdir(parents=True, exist_ok=True)

    im = Image.open(in_p).convert("RGB")
    w, h = im.size
    y0 = int(h * args.crop_top_ratio)
    y1 = int(h * args.crop_bottom_ratio)
    cw = w // 3
    px = int(cw * 0.05)
    panels = [im.crop((i * cw + px, y0, (i + 1) * cw - px, y1)) for i in range(3)]

    # Top-pad front panel with pure white so hats/ears never clip in 4-ref shots or MOSS edits
    p0 = panels[0]
    padded = Image.new("RGB", (p0.width, p0.height + args.top_pad_px), (255, 255, 255))
    padded.paste(p0, (0, args.top_pad_px))
    front_out = clean_dir / f"{args.name}_front.png"
    padded.save(front_out)

    sm_h = 736 if args.top_pad_px >= 80 else 672
    sm_out = sm_dir / f"{args.name}_sm.png"
    padded.resize((448, sm_h), Image.LANCZOS).save(sm_out)

    gap = 16
    pw, ph = p0.size
    canvas = Image.new("RGB", (pw * 3 + gap * 2, ph), (255, 255, 255))
    for idx, pnl in enumerate(panels):
        canvas.paste(pnl, (idx * (pw + gap), 0))
    if canvas.width > 960:
        canvas = canvas.resize((960, int(canvas.height * (960 / canvas.width))), Image.LANCZOS)
    v3_out = clean_dir / f"{args.name}_3view.png"
    canvas.save(v3_out)
    print(f"[prep-refs] {args.name}: 3view={v3_out.name}, front={front_out.name}, sm={sm_out.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage-0 OP Remix video normalizer, cut auditor, and sheet cleaner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("prep-video")
    pv.add_argument("--source", required=True)
    pv.add_argument("--out-dir", required=True)
    pv.add_argument("--max-seconds", type=float, default=0.0)
    pv.add_argument("--threshold", type=float, default=12.0)
    pv.add_argument("--ffmpeg", default="ffmpeg")

    pr = sub.add_parser("prep-refs")
    pr.add_argument("--sheet", required=True, help="3-view character turnaround sheet image")
    pr.add_argument("--name", required=True, help="Short character slug, e.g. deepseek")
    pr.add_argument("--out-dir", required=True)
    pr.add_argument("--crop-top-ratio", type=float, default=0.105, help="Fraction cropped off top header labels")
    pr.add_argument("--crop-bottom-ratio", type=float, default=0.945, help="Bottom keep fraction excluding caption")
    pr.add_argument("--top-pad-px", type=int, default=100, help="Extra white top margin above hats/ears")

    args = ap.parse_args()
    if args.cmd == "prep-video":
        cmd_prep_video(args)
    elif args.cmd == "prep-refs":
        cmd_prep_refs(args)


if __name__ == "__main__":
    main()
