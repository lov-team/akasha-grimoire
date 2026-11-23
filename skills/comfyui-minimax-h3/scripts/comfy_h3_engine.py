#!/usr/bin/env python3
"""Unified Local ComfyUI MiniMax H3 + MOSS-Image CLI Engine.
Subcommands:
  - free        : POST /free to unload models & free VRAM/RAM before switching pipeline families
  - t2v         : FastH3 8+4 step 2-pass text-to-video with audio (1344x768)
  - i2v         : MiniMaxH3ImageToVideo first-frame animation
  - ref2va      : MiniMaxH3ReferenceToVideo multi-image + video reference generation
  - regen2k     : MinimaxH3LatentUpscaler3D + Regenerate-2K 3-step HD upscale
  - moss-sheet  : Padded single-image TextEncodeQwenImageEdit for pure-white costume reference sheets
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
from PIL import Image

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"


def snap_h3_frames(n: int) -> int:
    return max(56, 5 + math.ceil(max(0, n - 5) / 17) * 17)


def gpu_thermal_guard(max_temp: int = 79) -> None:
    while True:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                text=True,
                timeout=5,
            )
            temps = [int(x.strip()) for x in out.strip().splitlines() if x.strip()]
            if not temps or max(temps) <= max_temp:
                return
            print(f"[thermal_guard] GPU temps {temps} > {max_temp}C, cooling 20s...", flush=True)
            time.sleep(20)
        except Exception:
            return


def comfy_free(comfy_url: str) -> None:
    req = urllib.request.Request(
        f"{comfy_url.rstrip('/')}/free",
        data=json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()
    print(f"[free] Unloaded models & freed memory on {comfy_url}")


def submit_and_wait(comfy_url: str, wf: dict, poll_sec: int = 4) -> dict:
    gpu_thermal_guard()
    base = comfy_url.rstrip("/")
    req = urllib.request.Request(
        f"{base}/prompt",
        data=json.dumps({"prompt": wf}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pid = json.loads(r.read().decode("utf-8"))["prompt_id"]
    t0 = time.time()
    print(f"[comfy] submitted prompt_id={pid}, waiting...", flush=True)
    while True:
        with urllib.request.urlopen(f"{base}/history/{pid}", timeout=30) as r:
            hist = json.loads(r.read().decode("utf-8"))
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution failed: {status.get('messages')}")
            print(f"[comfy] completed in {time.time() - t0:.1f}s", flush=True)
            return entry
        time.sleep(poll_sec)


def copy_first_output(entry: dict, node_id: str, comfy_output: Path, dst: Path) -> None:
    outs = entry.get("outputs", {}).get(node_id, {})
    files = outs.get("images") or outs.get("videos") or outs.get("gifs") or []
    if not files:
        raise RuntimeError(f"No output found on node {node_id}: {entry.get('outputs')}")
    finfo = files[0]
    src = comfy_output / finfo.get("subfolder", "") / finfo["filename"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[saved] {dst} ({dst.stat().st_size // 1024} KB)")


def cmd_t2v(args: argparse.Namespace) -> None:
    wf = json.loads((ASSETS / "h3_fp8_2pass_clean.json").read_text(encoding="utf-8"))
    wf["4"]["inputs"]["text"] = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    wf["6"]["inputs"]["width"] = args.base_width
    wf["6"]["inputs"]["height"] = args.base_height
    wf["6"]["inputs"]["length"] = snap_h3_frames(args.frames)
    wf["9"]["inputs"]["seed"] = args.seed
    wf["10"]["inputs"]["noise_seed"] = args.seed + 1
    wf["21"]["inputs"]["filename_prefix"] = f"video/h3_t2v_{int(time.time())}"
    entry = submit_and_wait(args.comfy_url, wf)
    copy_first_output(entry, "21", Path(args.comfy_output), Path(args.out))


def cmd_i2v(args: argparse.Namespace) -> None:
    wf = json.loads((ASSETS / "h3_i2v_first_frame.json").read_text(encoding="utf-8"))
    comfy_in = Path(args.comfy_input)
    img_p = Path(args.image)
    dst_in = f"h3_i2v_{int(time.time())}_{img_p.name}"
    shutil.copy2(img_p, comfy_in / dst_in)
    wf["200"]["inputs"]["image"] = dst_in
    wf["104"]["inputs"]["prompt"] = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    wf["104"]["inputs"]["width"] = args.width
    wf["104"]["inputs"]["height"] = args.height
    wf["104"]["inputs"]["length"] = snap_h3_frames(args.frames)
    wf["9"]["inputs"]["steps"] = args.steps
    wf["15"]["inputs"]["noise_seed"] = args.seed
    wf["92"]["inputs"]["filename_prefix"] = f"video/h3_i2v_{int(time.time())}"
    entry = submit_and_wait(args.comfy_url, wf)
    copy_first_output(entry, "92", Path(args.comfy_output), Path(args.out))


def cmd_ref2va(args: argparse.Namespace) -> None:
    wf = json.loads((ASSETS / "h3_ref2va.json").read_text(encoding="utf-8"))
    comfy_in = Path(args.comfy_input)
    for k in list(wf["104"]["inputs"].keys()):
        if k.startswith("ref_images.") or k.startswith("ref_videos."):
            del wf["104"]["inputs"][k]
    wf.pop("210", None)
    wf.pop("211", None)

    ts = int(time.time())
    if args.video:
        vp = Path(args.video)
        vname = f"h3_refv_{ts}_{vp.name}"
        shutil.copy2(vp, comfy_in / vname)
        wf["210"] = {"class_type": "LoadVideo", "inputs": {"file": vname}}
        wf["211"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["210", 0]}}
        wf["104"]["inputs"]["ref_videos.ref_video_0"] = ["211", 0]

    for idx, rf in enumerate(args.refs):
        rp = Path(rf)
        rname = f"h3_refi_{ts}_{idx}_{rp.name}"
        shutil.copy2(rp, comfy_in / rname)
        nid = str(200 + idx)
        wf[nid] = {"class_type": "LoadImage", "inputs": {"image": rname}}
        wf["104"]["inputs"][f"ref_images.ref_image_{idx}"] = [nid, 0]

    wf["104"]["inputs"]["prompt"] = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    wf["104"]["inputs"]["width"] = args.width
    wf["104"]["inputs"]["height"] = args.height
    wf["104"]["inputs"]["length"] = snap_h3_frames(args.frames)
    wf["9"]["inputs"]["steps"] = args.steps
    wf["15"]["inputs"]["noise_seed"] = args.seed
    wf["92"]["inputs"]["filename_prefix"] = f"video/h3_ref2va_{ts}"
    entry = submit_and_wait(args.comfy_url, wf)
    copy_first_output(entry, "92", Path(args.comfy_output), Path(args.out))


def cmd_regen2k(args: argparse.Namespace) -> None:
    if args.free_first:
        comfy_free(args.comfy_url)
    wf = json.loads((ASSETS / "h3_regen2k.json").read_text(encoding="utf-8"))
    vp = Path(args.video)
    vname = f"h3_up_{int(time.time())}_{vp.name}"
    shutil.copy2(vp, Path(args.comfy_input) / vname)
    wf["1"]["inputs"]["file"] = vname
    # Critical flat keys required by MinimaxH3LatentUpscaler3D API
    wf["5"]["inputs"]["mode"] = "target dimensions"
    wf["5"]["inputs"]["mode.width"] = args.width
    wf["5"]["inputs"]["mode.height"] = args.height
    wf["10"]["inputs"]["value"] = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    wf["11"]["inputs"]["width"] = args.width
    wf["11"]["inputs"]["height"] = args.height
    wf["11"]["inputs"]["length"] = snap_h3_frames(args.frames)
    wf["17"]["inputs"]["noise_seed"] = args.seed
    wf["22"]["inputs"]["filename_prefix"] = f"video/h3_regen2k_{int(time.time())}"
    entry = submit_and_wait(args.comfy_url, wf)
    copy_first_output(entry, "22", Path(args.comfy_output), Path(args.out))


def cmd_moss_sheet(args: argparse.Namespace) -> None:
    if args.free_first:
        comfy_free(args.comfy_url)
    im = Image.open(args.image).convert("RGB")
    canvas = Image.new("RGB", (im.width + args.pad_side * 2, im.height + args.pad_top + 60), (255, 255, 255))
    canvas.paste(im, (args.pad_side, args.pad_top))
    pname = f"moss_pad_{int(time.time())}.png"
    canvas.save(Path(args.comfy_input) / pname)

    wf = json.loads((ASSETS / "moss_costume_edit.json").read_text(encoding="utf-8"))
    wf["20"]["inputs"]["image"] = pname
    wf["6"]["inputs"]["prompt"] = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    wf["7"]["inputs"]["width"] = args.width
    wf["7"]["inputs"]["height"] = args.height
    wf["9"]["inputs"]["seed"] = args.seed
    wf["11"]["inputs"]["filename_prefix"] = f"moss_sheet_{int(time.time())}"
    entry = submit_and_wait(args.comfy_url, wf, poll_sec=2)
    out_p = Path(args.out)
    copy_first_output(entry, "11", Path(args.comfy_output), out_p)
    if args.save_sm:
        sm_p = out_p.with_name(f"{out_p.stem}_sm.png")
        Image.open(out_p).convert("RGB").resize((448, 736), Image.LANCZOS).save(sm_p)
        print(f"[saved_sm] {sm_p}")
    if args.free_after:
        comfy_free(args.comfy_url)


def main() -> None:
    ap = argparse.ArgumentParser(description="Unified Local ComfyUI MiniMax H3 + MOSS-Image CLI Engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_free = sub.add_parser("free")
    p_free.add_argument("--comfy-url", default="http://127.0.0.1:8188")

    p_t2v = sub.add_parser("t2v")
    p_t2v.add_argument("--prompt", default="")
    p_t2v.add_argument("--prompt-file", default="")
    p_t2v.add_argument("--base-width", type=int, default=672)
    p_t2v.add_argument("--base-height", type=int, default=384)
    p_t2v.add_argument("--frames", type=int, default=73)
    p_t2v.add_argument("--seed", type=int, default=42)
    p_t2v.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    p_t2v.add_argument("--comfy-output", required=True)
    p_t2v.add_argument("--out", required=True)

    p_i2v = sub.add_parser("i2v")
    p_i2v.add_argument("--image", required=True)
    p_i2v.add_argument("--prompt", default="")
    p_i2v.add_argument("--prompt-file", default="")
    p_i2v.add_argument("--width", type=int, default=1024)
    p_i2v.add_argument("--height", type=int, default=576)
    p_i2v.add_argument("--frames", type=int, default=56)
    p_i2v.add_argument("--steps", type=int, default=20)
    p_i2v.add_argument("--seed", type=int, default=20260001)
    p_i2v.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    p_i2v.add_argument("--comfy-input", required=True)
    p_i2v.add_argument("--comfy-output", required=True)
    p_i2v.add_argument("--out", required=True)

    p_ref = sub.add_parser("ref2va")
    p_ref.add_argument("--refs", nargs="+", required=True)
    p_ref.add_argument("--video", default="")
    p_ref.add_argument("--prompt", default="")
    p_ref.add_argument("--prompt-file", default="")
    p_ref.add_argument("--width", type=int, default=1024)
    p_ref.add_argument("--height", type=int, default=576)
    p_ref.add_argument("--frames", type=int, default=56)
    p_ref.add_argument("--steps", type=int, default=20)
    p_ref.add_argument("--seed", type=int, default=20260001)
    p_ref.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    p_ref.add_argument("--comfy-input", required=True)
    p_ref.add_argument("--comfy-output", required=True)
    p_ref.add_argument("--out", required=True)

    p_r2k = sub.add_parser("regen2k")
    p_r2k.add_argument("--video", required=True)
    p_r2k.add_argument("--prompt", default="Crisp 2D television anime cel-shaded linework, sharp details, clean colors")
    p_r2k.add_argument("--prompt-file", default="")
    p_r2k.add_argument("--width", type=int, default=1920)
    p_r2k.add_argument("--height", type=int, default=1080)
    p_r2k.add_argument("--frames", type=int, default=56)
    p_r2k.add_argument("--seed", type=int, default=42)
    p_r2k.add_argument("--free-first", action="store_true", default=True)
    p_r2k.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    p_r2k.add_argument("--comfy-input", required=True)
    p_r2k.add_argument("--comfy-output", required=True)
    p_r2k.add_argument("--out", required=True)

    p_ms = sub.add_parser("moss-sheet")
    p_ms.add_argument("--image", required=True)
    p_ms.add_argument("--prompt", default="")
    p_ms.add_argument("--prompt-file", default="")
    p_ms.add_argument("--pad-top", type=int, default=240)
    p_ms.add_argument("--pad-side", type=int, default=120)
    p_ms.add_argument("--width", type=int, default=768)
    p_ms.add_argument("--height", type=int, default=1280)
    p_ms.add_argument("--seed", type=int, default=202701)
    p_ms.add_argument("--save-sm", action="store_true", default=True)
    p_ms.add_argument("--free-first", action="store_true", default=True)
    p_ms.add_argument("--free-after", action="store_true", default=True)
    p_ms.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    p_ms.add_argument("--comfy-input", required=True)
    p_ms.add_argument("--comfy-output", required=True)
    p_ms.add_argument("--out", required=True)

    args = ap.parse_args()
    if args.cmd == "free":
        comfy_free(args.comfy_url)
    elif args.cmd == "t2v":
        cmd_t2v(args)
    elif args.cmd == "i2v":
        cmd_i2v(args)
    elif args.cmd == "ref2va":
        cmd_ref2va(args)
    elif args.cmd == "regen2k":
        cmd_regen2k(args)
    elif args.cmd == "moss-sheet":
        cmd_moss_sheet(args)


if __name__ == "__main__":
    main()
