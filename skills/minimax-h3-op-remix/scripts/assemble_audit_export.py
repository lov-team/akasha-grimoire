#!/usr/bin/env python3
"""Stage-4 Deterministic OP Timeline Assembler, OpenCV MAD Leak Scanner & Multi-Platform Exporter.
Reads a JSON timeline:
  {"total_frames": 2161, "segments": [{"start": 0, "end": 57, "kind": "orig"}, {"start": 57, "end": 90, "kind": "file", "path": "..."}]}
Outputs:
  1. Gapless 16:9 Master MP4 + Horizontal SBS MP4
  2. OpenCV per-frame Mean Absolute Difference (MAD) leak report catching unreplaced frames / watermark leaks
  3. WeChat Channels (微信视频号) 1080x1920 9:16 safe-zone vertical comparison MP4 & pure 1080x1216 Top-Bottom MP4
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def run_cmd(cmd: list[str | Path]) -> None:
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{proc.stderr[-2000:]}")


def probe_video(ffprobe: str, p: Path) -> tuple[int, int, int]:
    raw = subprocess.check_output(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames,width,height", "-of", "json", str(p)],
        text=True,
    )
    st = json.loads(raw)["streams"][0]
    return int(st["nb_frames"]), int(st["width"]), int(st["height"])


def scan_mad_leaks(master_p: Path, gen_p: Path, orig_ranges: list[tuple[int, int]], mad_thresh: float = 12.0) -> list[dict]:
    cap_m = cv2.VideoCapture(str(master_p))
    cap_g = cv2.VideoCapture(str(gen_p))
    leaks = []
    idx = 0
    while True:
        rm, fm = cap_m.read()
        rg, fg = cap_g.read()
        if not rm or not rg:
            break
        in_orig = any(s <= idx < e for s, e in orig_ranges)
        if not in_orig:
            if fm.shape != fg.shape:
                fm = cv2.resize(fm, (fg.shape[1], fg.shape[0]), interpolation=cv2.INTER_AREA)
            h, w, _ = fg.shape
            bm = fm[int(h * 0.15) : int(h * 0.88), : int(w * 0.80)].astype(np.float32)
            bg = fg[int(h * 0.15) : int(h * 0.88), : int(w * 0.80)].astype(np.float32)
            mad = float(np.mean(np.abs(bm - bg)))
            if mad < mad_thresh:
                leaks.append({"frame": idx, "time_s": round(idx / 24.0, 3), "body_mad": round(mad, 2)})
        idx += 1
    cap_m.release()
    cap_g.release()
    return leaks


def export_wechat_vertical(ffmpeg: str, orig_v: Path, gen_v: Path, audio_p: Path, out_dir: Path, title: str, subtitle: str, font_bold: str, font_reg: str) -> None:
    tb_pure = out_dir / "OP_Remix_TopBottom_Pure.mp4"
    run_cmd([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", orig_v, "-i", gen_v, "-i", audio_p,
        "-filter_complex",
        "[0:v]scale=1080:608:flags=lanczos,setsar=1[top];"
        "[1:v]scale=1080:608:flags=lanczos,setsar=1[bot];"
        "[top][bot]vstack=inputs=2[v]",
        "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-shortest", tb_pure,
    ])

    ov_png = out_dir / "_wechat_overlay.png"
    ov = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    dr.rectangle([0, 233, 1080, 236], fill=(255, 255, 255, 110))
    dr.rectangle([0, 844, 1080, 848], fill=(255, 255, 255, 180))
    dr.rectangle([0, 1456, 1080, 1459], fill=(255, 255, 255, 110))
    fb = ImageFont.truetype(font_bold, 44)
    fr = ImageFont.truetype(font_reg, 26)
    ft = ImageFont.truetype(font_bold, 24)
    tw = dr.textbbox((0, 0), title, font=fb)[2]
    sw = dr.textbbox((0, 0), subtitle, font=fr)[2]
    dr.text(((1080 - tw) // 2 + 2, 110), title, font=fb, fill=(0, 0, 0, 180))
    dr.text(((1080 - tw) // 2, 108), title, font=fb, fill=(255, 255, 255, 245))
    dr.text(((1080 - sw) // 2, 172), subtitle, font=fr, fill=(215, 225, 245, 220))
    for x, y, txt, col in [(18, 252, "原版 OP", (255, 200, 90, 210)), (18, 864, "AI 重制版", (100, 220, 255, 220))]:
        pw = dr.textbbox((0, 0), txt, font=ft)[2] + 28
        dr.rounded_rectangle([x, y, x + pw, y + 38], radius=10, fill=(12, 16, 26, 170), outline=col, width=2)
        dr.text((x + 14, y + 4), txt, font=ft, fill=(255, 255, 255, 245))
    ov.save(ov_png)

    tb_9x16 = out_dir / "OP_Remix_WeChat_9x16.mp4"
    run_cmd([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", orig_v, "-i", gen_v, "-i", ov_png, "-i", audio_p,
        "-filter_complex",
        "[1:v]scale=270:480,gblur=sigma=24,eq=brightness=-0.38:saturation=0.85,scale=1080:1920:flags=bilinear,setsar=1[bg];"
        "[0:v]scale=1080:608:flags=lanczos[top];"
        "[1:v]scale=1080:608:flags=lanczos[bot];"
        "[bg][top]overlay=0:236[t1];[t1][bot]overlay=0:848[t2];[t2][2:v]overlay=0:0[v]",
        "-map", "[v]", "-map", "3:a",
        "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-shortest", tb_9x16,
    ])
    print(f"[wechat] Exported {tb_pure} and {tb_9x16}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble OP timeline, run MAD leak scan, and export horizontal/WeChat vertical videos.")
    ap.add_argument("--timeline", required=True, help="Path to timeline JSON")
    ap.add_argument("--master", required=True, help="Path to source_24fps.mp4")
    ap.add_argument("--audio", required=True, help="Path to full_audio.m4a")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=576)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--wechat", action="store_true", help="Also export WeChat Channels 9:16 & pure Top-Bottom MP4s")
    ap.add_argument("--title", default="AI 角色全片替换 OP 对比")
    ap.add_argument("--subtitle", default="上：番剧原片   |   下：MiniMax H3 角色重制")
    ap.add_argument("--font-bold", default=r"C:\Windows\Fonts\msyhbd.ttc")
    ap.add_argument("--font-reg", default=r"C:\Windows\Fonts\msyh.ttc")
    args = ap.parse_args()

    tl = json.loads(Path(args.timeline).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    seg_cache = out_dir / "_seg_norm"
    seg_cache.mkdir(parents=True, exist_ok=True)

    cur = 0
    seg_files = []
    orig_ranges = []
    for seg in tl["segments"]:
        s, e, kind = int(seg["start"]), int(seg["end"]), seg["kind"]
        if s != cur:
            raise ValueError(f"Timeline discontinuity at {s} (expected {cur})")
        cur = e
        exp_n = e - s
        if kind == "orig":
            orig_ranges.append((s, e))
            sp = seg_cache / f"orig_{s}_{e}.mp4"
            run_cmd([
                args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", args.master,
                "-vf", f"trim=start_frame={s}:end_frame={e},setpts=N/(24*TB),scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-an", "-frames:v", str(exp_n), "-r", "24", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", sp,
            ])
        elif kind == "white":
            orig_ranges.append((s, e))
            sp = seg_cache / f"white_{exp_n}f.mp4"
            run_cmd([
                args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c=white:s={args.width}x{args.height}:r=24",
                "-frames:v", str(exp_n), "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", sp,
            ])
        else:
            sp = Path(seg["path"])
            nf, w, h = probe_video(args.ffprobe, sp)
            if nf != exp_n or w != args.width or h != args.height:
                np_out = seg_cache / f"norm_{s}_{e}.mp4"
                run_cmd([
                    args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", sp,
                    "-vf", f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
                    "-an", "-frames:v", str(exp_n), "-r", "24", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", np_out,
                ])
                sp = np_out
        seg_files.append(sp)

    if "total_frames" in tl and cur != int(tl["total_frames"]):
        raise ValueError(f"Expected total_frames={tl['total_frames']}, got {cur}")

    concat_txt = out_dir / "concat_list.txt"
    concat_txt.write_text("\n".join(f"file '{p.as_posix()}'" for p in seg_files), encoding="utf-8")
    vid_only = out_dir / "full_video_silent.mp4"
    run_cmd([
        args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-r", "24", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", vid_only,
    ])

    final_mp4 = out_dir / "OP_Remix_Master.mp4"
    run_cmd([
        args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", vid_only, "-i", args.audio,
        "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", final_mp4,
    ])

    orig_trim = seg_cache / f"orig_0_{cur}.mp4"
    run_cmd([
        args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", args.master,
        "-vf", f"trim=start_frame=0:end_frame={cur},setpts=N/(24*TB),scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-an", "-frames:v", str(cur), "-r", "24", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", orig_trim,
    ])
    sbs_mp4 = out_dir / "OP_Remix_SBS.mp4"
    run_cmd([
        args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", orig_trim, "-i", vid_only, "-i", args.audio,
        "-filter_complex", "[0:v]scale=640:360[l];[1:v]scale=640:360[r];[l][r]hstack=inputs=2[v]",
        "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-shortest", sbs_mp4,
    ])

    leaks = scan_mad_leaks(orig_trim, vid_only, orig_ranges)
    report_p = out_dir / "mad_leak_report.json"
    report_p.write_text(json.dumps({"suspect_low_mad_frames": leaks}, indent=2), encoding="utf-8")
    print(f"[audit] Assembled {final_mp4} ({cur}f); MAD suspect unreplaced frames: {len(leaks)} -> {report_p}")

    if args.wechat:
        export_wechat_vertical(args.ffmpeg, orig_trim, vid_only, Path(args.audio), out_dir, args.title, args.subtitle, args.font_bold, args.font_reg)


if __name__ == "__main__":
    main()
