#!/usr/bin/env python3
"""Single-shot ComfyUI MiniMaxH3ReferenceToVideo runner with frame-grid mapping,
exact frame-count restoration (including >95f slow-motion orbital shots), and 4-frame QC strip export.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKFLOW = SKILL_ROOT / "assets" / "h3_ref2va_comfy_workflow.json"


def snap_frames(n: int) -> int:
    """MiniMax H3 requires 17k + 5 frames (minimum 56)."""
    return max(56, 5 + math.ceil(max(0, n - 5) / 17) * 17)


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


def prepare_clip(
    ffmpeg: str,
    master: Path,
    start_frame: int,
    end_frame: int,
    out_mp4: Path,
    width: int = 1024,
    height: int = 576,
    mode: str = "auto",
    forced_gen_n: int = 0,
) -> tuple[int, int, str]:
    orig_n = end_frame - start_frame
    if orig_n <= 0:
        raise ValueError(f"end_frame ({end_frame}) must be greater than start_frame ({start_frame})")
    gen_n = forced_gen_n if forced_gen_n > 0 else (90 if orig_n > 95 else snap_frames(orig_n))
    if mode == "auto":
        mode = "pad" if orig_n < 24 else "stretch"

    scale_vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    if mode == "stretch":
        pts_factor = (gen_n - 1) / max(1, orig_n - 1) if orig_n > 1 else 1.0
        vf = f"trim=start_frame={start_frame}:end_frame={end_frame},setpts=(PTS-STARTPTS)*{pts_factor:.6f},fps=24,{scale_vf}"
    else:
        vf = f"trim=start_frame={start_frame}:end_frame={end_frame},setpts=N/(24*TB),fps=24,{scale_vf},tpad=stop_mode=clone:stop_duration=16"

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    run_cmd([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", master, "-vf", vf, "-an", "-frames:v", str(gen_n), "-r", "24",
        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", out_mp4,
    ])
    return orig_n, gen_n, mode


def restore_frame_count(ffmpeg: str, raw_mp4: Path, out_mp4: Path, orig_n: int, gen_n: int, mode: str) -> None:
    if mode == "pad":
        vf = f"trim=start_frame=0:end_frame={orig_n},setpts=N/(24*TB)"
    elif gen_n < orig_n:
        pts_up = (orig_n - 1) / max(1, gen_n - 1)
        vf = f"setpts=(PTS-STARTPTS)*{pts_up:.6f},fps=24"
    else:
        indices = sorted({int(math.floor(i * (gen_n - 1) / max(1, orig_n - 1) + 0.5)) for i in range(orig_n)})
        expr = "+".join(f"eq(n\\,{idx})" for idx in indices)
        vf = f"select='{expr}',setpts=N/(24*TB)"
    run_cmd([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", raw_mp4, "-vf", vf, "-an", "-frames:v", str(orig_n), "-r", "24",
        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", out_mp4,
    ])


def export_qc_strip(ffmpeg: str, qc_master: Path, start_frame: int, end_frame: int, gen_mp4: Path, out_jpg: Path) -> None:
    orig_tmp = out_jpg.with_suffix(".orig_tmp.mp4")
    run_cmd([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", qc_master,
        "-vf", f"trim=start_frame={start_frame}:end_frame={end_frame},setpts=N/(24*TB)",
        "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", orig_tmp,
    ])
    n = end_frame - start_frame
    if n <= 4:
        fidxs = list(range(n))
    else:
        fidxs = [0, max(1, int(n * 0.33)), max(2, int(n * 0.66)), max(3, n - 2)]
    cols = len(fidxs)
    sel = "+".join(f"eq(n,{i})" for i in fidxs)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    run_cmd([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", orig_tmp, "-i", gen_mp4,
        "-filter_complex",
        f"[0:v]select='{sel}',scale=360:202,tile={cols}x1[top];"
        f"[1:v]select='{sel}',scale=360:202,tile={cols}x1[bot];"
        f"[top][bot]vstack=inputs=2",
        "-vsync", "0", "-frames:v", "1", "-q:v", "2", out_jpg,
    ])
    orig_tmp.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a single MiniMax H3 Ref2VA OP-remix shot against local ComfyUI.")
    ap.add_argument("--shot", required=True, help="Unique shot ID, e.g. sop_130_208")
    ap.add_argument("--master", required=True, help="Input video path (source_24fps.mp4 or Pass-1 mp4 for cascade)")
    ap.add_argument("--start", type=int, required=True, help="Start frame (inclusive, 24fps)")
    ap.add_argument("--end", type=int, required=True, help="End frame (exclusive, 24fps)")
    ap.add_argument("--refs", nargs="+", required=True, help="1 to 4 clean character reference image paths")
    ap.add_argument("--prompt-file", required=True, help="Path to 6-section H3 Context-IR prompt .txt")
    ap.add_argument("--out-dir", required=True, help="Output directory for prepared, workflow, and final shot files")
    ap.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    ap.add_argument("--comfy-input", required=True, help="ComfyUI input directory path")
    ap.add_argument("--comfy-output", required=True, help="ComfyUI output directory path")
    ap.add_argument("--workflow", default=str(DEFAULT_WORKFLOW))
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=576)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260001)
    ap.add_argument("--mode", choices=["auto", "stretch", "pad"], default="auto")
    ap.add_argument("--gen-frames", type=int, default=0, help="Optional explicit 17k+5 H3 frame length (e.g. 90)")
    ap.add_argument("--qc-strip", default="", help="Optional output path for 4-frame orig-vs-gen QC strip .jpg")
    ap.add_argument("--qc-master", default="", help="Optional original master video for Pass-2 cascade QC comparison")
    ap.add_argument("--qc-start", type=int, default=-1)
    ap.add_argument("--qc-end", type=int, default=-1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    shot_dir = Path(args.out_dir) / f"shot_{args.shot}"
    shot_dir.mkdir(parents=True, exist_ok=True)
    prep_mp4 = shot_dir / f"prep_{args.shot}.mp4"
    orig_n, gen_n, used_mode = prepare_clip(
        args.ffmpeg, Path(args.master), args.start, args.end, prep_mp4,
        args.width, args.height, args.mode, args.gen_frames,
    )
    print(f"[prep] shot={args.shot} orig_frames={orig_n} -> gen_frames={gen_n} mode={used_mode}")

    wf = json.loads(Path(args.workflow).read_text(encoding="utf-8"))
    wf["9"]["inputs"]["steps"] = args.steps
    wf["15"]["inputs"]["noise_seed"] = args.seed
    wf["92"]["inputs"]["filename_prefix"] = f"video/op_remix/shot_{args.shot}"

    comfy_in = Path(args.comfy_input)
    comfy_out = Path(args.comfy_output)
    vid_name = f"op_shot_{args.shot}.mp4"
    shutil.copy2(prep_mp4, comfy_in / vid_name)
    wf["210"]["inputs"]["file"] = vid_name

    for k in list(wf["104"]["inputs"].keys()):
        if k.startswith("ref_images."):
            del wf["104"]["inputs"][k]
    for idx, ref in enumerate(args.refs):
        p = Path(ref)
        if not p.exists():
            raise FileNotFoundError(f"Reference image not found: {p}")
        dst_name = f"op_ref_{args.shot}_{idx}_{p.name}"
        shutil.copy2(p, comfy_in / dst_name)
        node_id = str(200 + idx)
        wf[node_id] = {"class_type": "LoadImage", "inputs": {"image": dst_name}}
        wf["104"]["inputs"][f"ref_images.ref_image_{idx}"] = [node_id, 0]

    wf["104"]["inputs"]["prompt"] = Path(args.prompt_file).read_text(encoding="utf-8")
    wf["104"]["inputs"]["width"] = args.width
    wf["104"]["inputs"]["height"] = args.height
    wf["104"]["inputs"]["length"] = gen_n

    wf_out = shot_dir / f"workflow_{args.shot}.json"
    wf_out.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.dry_run:
        print(f"[dry-run] workflow written to {wf_out}")
        return

    t0 = time.time()
    req = urllib.request.Request(
        f"{args.comfy_url.rstrip('/')}/prompt",
        data=json.dumps({"prompt": wf}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pid = json.loads(r.read().decode("utf-8"))["prompt_id"]
    print(f"[comfy] submitted prompt_id={pid}, polling...")

    while True:
        with urllib.request.urlopen(f"{args.comfy_url.rstrip('/')}/history/{pid}", timeout=30) as r:
            hist = json.loads(r.read().decode("utf-8"))
        if pid in hist:
            entry = hist[pid]
            break
        time.sleep(5)
    print(f"[comfy] finished in {time.time() - t0:.1f}s")

    outs = entry.get("outputs", {}).get("92", {})
    files = outs.get("images") or outs.get("videos") or outs.get("gifs") or []
    if not files:
        raise RuntimeError(f"ComfyUI job {pid} produced no output video: {entry}")
    finfo = files[0]
    raw_path = comfy_out / finfo.get("subfolder", "") / finfo["filename"]
    final_mp4 = shot_dir / f"final_{args.shot}.mp4"
    restore_frame_count(args.ffmpeg, raw_path, final_mp4, orig_n, gen_n, used_mode)
    print(f"[done] restored({orig_n}f)={final_mp4}")

    if args.qc_strip:
        qm = Path(args.qc_master) if args.qc_master else Path(args.master)
        qs = args.qc_start if args.qc_start >= 0 else args.start
        qe = args.qc_end if args.qc_end >= 0 else args.end
        export_qc_strip(args.ffmpeg, qm, qs, qe, final_mp4, Path(args.qc_strip))
        print(f"[qc] saved {args.qc_strip}")


if __name__ == "__main__":
    main()
