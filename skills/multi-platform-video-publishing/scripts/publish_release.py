#!/usr/bin/env python3
"""Validate, plan and resume one-platform-at-a-time video publishing via mpau."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLATFORMS = ("douyin", "xiaohongshu", "bilibili", "tencent")
FINAL_STATES = {"submitted", "reviewing", "published"}
BLOCKING_STATES = FINAL_STATES | {"uploading", "unknown"}
RECORD_STATES = ("planned", "uploading", "submitted", "reviewing", "published", "unknown", "failed")
DEFAULT_RUNTIME = Path.home() / ".local/share/multi-platform-auto-upload"


class ContractError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_path(value: str, config_dir: Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else config_dir / path).resolve()


def load_config(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"配置读取失败：{exc}") from exc

    if config.get("version") != 1:
        raise ContractError("配置 version 必须为 1")
    for key in ("release_id", "video", "video_sha256", "platforms"):
        if key not in config:
            raise ContractError(f"配置缺少字段：{key}")
    if not re.fullmatch(r"[0-9a-f]{64}", str(config["video_sha256"])):
        raise ContractError("video_sha256 必须是 64 位小写十六进制")
    if not isinstance(config["platforms"], dict):
        raise ContractError("platforms 必须是对象")

    config_dir = config_path.parent
    config["_config_path"] = str(config_path)
    config["video"] = str(resolve_path(str(config["video"]), config_dir))
    for platform, item in config["platforms"].items():
        if platform not in PLATFORMS:
            raise ContractError(f"不支持的平台：{platform}")
        if not isinstance(item, dict):
            raise ContractError(f"{platform} 配置必须是对象")
        if not item.get("enabled", True):
            continue
        for key in ("account", "title"):
            if not item.get(key):
                raise ContractError(f"{platform} 缺少字段：{key}")
        if platform == "bilibili" and not item.get("tid"):
            raise ContractError("bilibili 缺少字段：tid")
        if not isinstance(item.get("tags", []), list):
            raise ContractError(f"{platform}.tags 必须是数组")
        if item.get("browser_mode", "headed") not in ("headed", "headless"):
            raise ContractError(f"{platform}.browser_mode 只能是 headed 或 headless")
        for key in ("thumbnail", "thumbnail_portrait", "thumbnail_landscape"):
            if item.get(key):
                item[key] = str(resolve_path(str(item[key]), config_dir))
    return config


def enabled_platforms(config: dict[str, Any], selected: list[str] | None = None) -> list[str]:
    requested = selected or list(PLATFORMS)
    return [p for p in requested if config["platforms"].get(p, {}).get("enabled", True)]


def validate_local(config: dict[str, Any], full_decode: bool = False) -> dict[str, Any]:
    video = Path(config["video"])
    if not video.is_file():
        raise ContractError(f"视频不存在：{video}")
    actual_sha = sha256(video)
    if actual_sha != config["video_sha256"]:
        raise ContractError(f"视频 SHA-256 不匹配：{actual_sha}")

    for platform in enabled_platforms(config):
        item = config["platforms"][platform]
        for key in ("thumbnail", "thumbnail_portrait", "thumbnail_landscape"):
            if item.get(key) and not Path(item[key]).is_file():
                raise ContractError(f"{platform}.{key} 不存在：{item[key]}")

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ContractError("未找到 ffprobe")
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if probe.returncode != 0:
        raise ContractError(f"ffprobe 失败：{probe.stderr.strip()}")
    metadata = json.loads(probe.stdout)
    stream_types = {stream.get("codec_type") for stream in metadata.get("streams", [])}
    if "video" not in stream_types or "audio" not in stream_types:
        raise ContractError("最终视频必须同时包含画面流和音频流")

    decode_result = None
    if full_decode:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ContractError("未找到 ffmpeg")
        decoded = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(video), "-map", "0:v:0?", "-map", "0:a:0?", "-f", "null", "-"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        decode_result = {"exit": decoded.returncode, "stderr_bytes": len(decoded.stderr)}
        if decoded.returncode != 0:
            raise ContractError(f"完整解码失败，stderr 字节：{len(decoded.stderr)}")

    return {
        "video": str(video),
        "bytes": video.stat().st_size,
        "sha256": actual_sha,
        "probe": metadata,
        "full_decode": decode_result,
    }


def runtime_path(value: str | None) -> Path:
    runtime = Path(value or os.environ.get("MPAU_RUNTIME", DEFAULT_RUNTIME)).expanduser().resolve()
    if not (runtime / "pyproject.toml").is_file():
        raise ContractError(f"mpau 运行时不存在：{runtime}")
    if not shutil.which("uv"):
        raise ContractError("未找到 uv")
    return runtime


def mpau_prefix(runtime: Path) -> list[str]:
    return ["uv", "run", "--project", str(runtime), "mpau"]


def add_optional(command: list[str], flag: str, value: Any) -> None:
    if value not in (None, "", [], False):
        command.extend([flag, str(value)])


def check_command(runtime: Path, platform: str, item: dict[str, Any]) -> list[str]:
    return [*mpau_prefix(runtime), platform, "check", "--account", str(item["account"])]


def upload_command(runtime: Path, config: dict[str, Any], platform: str) -> list[str]:
    item = config["platforms"][platform]
    command = [
        *mpau_prefix(runtime),
        platform,
        "upload-video",
        "--account",
        str(item["account"]),
        "--file",
        str(config["video"]),
        "--title",
        str(item["title"]),
    ]
    add_optional(command, "--desc", item.get("desc"))
    add_optional(command, "--tags", ",".join(str(tag) for tag in item.get("tags", [])))
    add_optional(command, "--schedule", item.get("schedule"))

    if platform == "douyin":
        add_optional(command, "--thumbnail-portrait", item.get("thumbnail_portrait"))
        add_optional(command, "--thumbnail-landscape", item.get("thumbnail_landscape"))
    elif platform == "xiaohongshu":
        add_optional(command, "--thumbnail", item.get("thumbnail"))
    elif platform == "bilibili":
        command.extend(["--tid", str(item["tid"])])
    elif platform == "tencent":
        add_optional(command, "--thumbnail", item.get("thumbnail"))
        add_optional(command, "--short-title", item.get("short_title"))
        add_optional(command, "--category", item.get("category"))

    if platform in ("douyin", "xiaohongshu", "tencent"):
        command.append("--headless" if item.get("browser_mode") == "headless" else "--headed")
    return command


def report_path(config: dict[str, Any]) -> Path:
    config_path = Path(config["_config_path"])
    safe_id = re.sub(r"[^0-9A-Za-z._-]+", "-", str(config["release_id"])).strip("-") or "release"
    return config_path.parent / "reports" / f"{safe_id}.json"


def empty_report(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "release_id": config["release_id"],
        "video": config["video"],
        "video_sha256": config["video_sha256"],
        "updated_at": now_iso(),
        "platforms": {},
    }


def load_report(config: dict[str, Any]) -> dict[str, Any]:
    path = report_path(config)
    if not path.exists():
        return empty_report(config)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"发布台账读取失败：{exc}") from exc
    if report.get("video_sha256") != config["video_sha256"]:
        raise ContractError("发布台账的视频 SHA 与当前配置不一致")
    return report


def save_report(config: dict[str, Any], report: dict[str, Any]) -> Path:
    path = report_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    report["updated_at"] = now_iso()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def update_platform(config: dict[str, Any], platform: str, **fields: Any) -> Path:
    report = load_report(config)
    entry = report.setdefault("platforms", {}).setdefault(platform, {})
    entry.update(fields)
    entry["updated_at"] = now_iso()
    return save_report(config, report)


def run_check(command: list[str], timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        valid = completed.returncode == 0 and any(line.strip() == "valid" for line in output.splitlines())
        return {"status": "valid" if valid else "invalid", "exit": completed.returncode, "output": output}
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return {"status": "timeout", "exit": None, "output": output.strip()}


def run_upload_process(
    platform: str,
    command: list[str],
    process_registry: dict[str, subprocess.Popen[str]],
    registry_lock: threading.Lock,
) -> dict[str, Any]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    with registry_lock:
        process_registry[platform] = process
    output_lines: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            clean = line.rstrip("\r\n")
            output_lines.append(clean)
            print(f"[{platform}] {clean}", flush=True)
        exit_code = process.wait()
        return {"exit": exit_code, "output": "\n".join(output_lines)}
    finally:
        with registry_lock:
            process_registry.pop(platform, None)


def stop_processes(process_registry: dict[str, subprocess.Popen[str]], registry_lock: threading.Lock) -> None:
    with registry_lock:
        processes = list(process_registry.items())
    for platform, process in processes:
        if process.poll() is None:
            print(f"[{platform}] 收到中断，正在停止该上传进程", file=sys.stderr, flush=True)
            process.terminate()
    for _, process in processes:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def command_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = validate_local(config, full_decode=args.full_decode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_plan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    validate_local(config, full_decode=False)
    runtime = runtime_path(args.runtime)
    print(f"release_id={config['release_id']}")
    print(f"video_sha256={config['video_sha256']}")
    for platform in enabled_platforms(config, args.platform):
        print(f"{platform}: {shlex.join(upload_command(runtime, config, platform))}")
    return 0


def command_check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    runtime = runtime_path(args.runtime)
    if args.max_workers < 1:
        raise ContractError("max-workers 必须大于 0")
    overall = 0
    selected = enabled_platforms(config, args.platform)
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(args.max_workers, len(selected) or 1)) as executor:
        futures = {
            executor.submit(
                run_check,
                check_command(runtime, platform, config["platforms"][platform]),
                args.timeout,
            ): platform
            for platform in selected
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    for platform in selected:
        result = results[platform]
        update_platform(config, platform, account_check={**result, "checked_at": now_iso()})
        print(f"[{platform}] {result['status']}")
        if result["output"]:
            print(result["output"])
        if result["status"] != "valid":
            overall = 1
    print(f"report={report_path(config)}")
    return overall


def command_publish(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    validate_local(config, full_decode=False)
    if args.max_workers < 1:
        raise ContractError("max-workers 必须大于 0")
    if args.confirm_sha != config["video_sha256"]:
        raise ContractError("确认 SHA 与配置不一致")
    report = load_report(config)
    runtime = runtime_path(args.runtime)
    selected = enabled_platforms(config, args.platform)
    runnable: list[str] = []
    for platform in selected:
        existing = report.get("platforms", {}).get(platform, {})
        if existing.get("status") in BLOCKING_STATES:
            print(f"[{platform}] 跳过：台账状态为 {existing['status']}，先核验远端", flush=True)
            continue
        runnable.append(platform)
    if not runnable:
        print(f"report={report_path(config)}")
        return 0

    check_results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(args.max_workers, len(runnable))) as executor:
        futures = {
            executor.submit(
                run_check,
                check_command(runtime, platform, config["platforms"][platform]),
                args.check_timeout,
            ): platform
            for platform in runnable
        }
        for future in as_completed(futures):
            check_results[futures[future]] = future.result()

    ready: list[str] = []
    overall = 0
    for platform in runnable:
        check = check_results[platform]
        update_platform(config, platform, account_check={**check, "checked_at": now_iso()})
        print(f"[{platform}] 账号校验：{check['status']}", flush=True)
        if check["status"] == "valid":
            ready.append(platform)
        else:
            update_platform(config, platform, status="failed", evidence=f"账号校验：{check['status']}")
            overall = 1
    if not ready:
        print(f"report={report_path(config)}")
        return overall or 1

    commands: dict[str, list[str]] = {}
    for platform in ready:
        item = config["platforms"][platform]
        command = upload_command(runtime, config, platform)
        commands[platform] = command
        update_platform(
            config,
            platform,
            status="uploading",
            title=item["title"],
            started_at=now_iso(),
            command=command,
        )
        print(f"[{platform}] START {shlex.join(command)}", flush=True)

    process_registry: dict[str, subprocess.Popen[str]] = {}
    registry_lock = threading.Lock()
    try:
        with ThreadPoolExecutor(max_workers=min(args.max_workers, len(ready))) as executor:
            futures = {
                executor.submit(run_upload_process, platform, commands[platform], process_registry, registry_lock): platform
                for platform in ready
            }
            for future in as_completed(futures):
                platform = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {"exit": None, "output": f"{type(exc).__name__}: {exc}"}
                if result["exit"] == 0:
                    update_platform(
                        config,
                        platform,
                        status="submitted",
                        exit=0,
                        completed_at=now_iso(),
                        evidence="上传命令退出 0；等待远端作品管理页核验",
                        output_tail=result["output"].splitlines()[-100:],
                    )
                    print(f"[{platform}] SUBMITTED", flush=True)
                else:
                    update_platform(
                        config,
                        platform,
                        status="unknown",
                        exit=result["exit"],
                        completed_at=now_iso(),
                        evidence="上传进程未正常完成；先核验远端再决定重试",
                        output_tail=result["output"].splitlines()[-100:],
                    )
                    overall = 1
                    print(f"[{platform}] UNKNOWN exit={result['exit']}", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        stop_processes(process_registry, registry_lock)
        for platform in ready:
            current = load_report(config).get("platforms", {}).get(platform, {}).get("status")
            if current == "uploading":
                update_platform(config, platform, status="unknown", evidence="并行发布被中断；先核验远端再决定重试")
        raise
    print(f"report={report_path(config)}")
    return overall


def command_record(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    fields: dict[str, Any] = {"status": args.status, "evidence": args.evidence}
    if args.remote_id:
        fields["remote_id"] = args.remote_id
    if args.url:
        fields["url"] = args.url
    path = update_platform(config, args.platform, **fields)
    print(f"report={path}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = load_report(config)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("config", type=Path)


def add_runtime_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime", help="mpau 项目目录；默认读取 MPAU_RUNTIME 或 ~/.local/share/multi-platform-auto-upload")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逐平台、可恢复的视频发布编排器")
    subparsers = parser.add_subparsers(dest="action", required=True)

    validate_parser = subparsers.add_parser("validate")
    add_config_argument(validate_parser)
    validate_parser.add_argument("--full-decode", action="store_true")
    validate_parser.set_defaults(handler=command_validate)

    plan_parser = subparsers.add_parser("plan")
    add_config_argument(plan_parser)
    add_runtime_argument(plan_parser)
    plan_parser.add_argument("--platform", action="append", choices=PLATFORMS)
    plan_parser.set_defaults(handler=command_plan)

    check_parser = subparsers.add_parser("check")
    add_config_argument(check_parser)
    add_runtime_argument(check_parser)
    check_parser.add_argument("--platform", action="append", choices=PLATFORMS)
    check_parser.add_argument("--timeout", type=int, default=90)
    check_parser.add_argument("--max-workers", type=int, default=4)
    check_parser.set_defaults(handler=command_check)

    publish_parser = subparsers.add_parser("publish")
    add_config_argument(publish_parser)
    add_runtime_argument(publish_parser)
    publish_parser.add_argument("--platform", action="append", choices=PLATFORMS)
    publish_parser.add_argument("--confirm-sha", required=True)
    publish_parser.add_argument("--check-timeout", type=int, default=90)
    publish_parser.add_argument("--max-workers", type=int, default=4)
    publish_parser.set_defaults(handler=command_publish)

    record_parser = subparsers.add_parser("record")
    add_config_argument(record_parser)
    record_parser.add_argument("--platform", required=True, choices=PLATFORMS)
    record_parser.add_argument("--status", required=True, choices=RECORD_STATES)
    record_parser.add_argument("--evidence", required=True)
    record_parser.add_argument("--remote-id")
    record_parser.add_argument("--url")
    record_parser.set_defaults(handler=command_record)

    status_parser = subparsers.add_parser("status")
    add_config_argument(status_parser)
    status_parser.set_defaults(handler=command_status)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except ContractError as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
