#!/usr/bin/env python3
"""Render a local HTML document to an exact-size PNG using Chrome, Chromium, or Edge."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (AttributeError, ValueError) as error:
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT") from error
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size values must be positive")
    return width, height


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"not a valid PNG with an IHDR header: {path}")
    return struct.unpack(">II", header[16:24])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_browser(explicit: str | None = None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"browser executable not found: {candidate}")

    candidates: list[Path] = []
    for command in ("chrome", "google-chrome", "google-chrome-stable", "chromium", "msedge"):
        located = shutil.which(command)
        if located:
            candidates.append(Path(located))
    for environment, suffix in (
        ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
        ("PROGRAMFILES(X86)", "Google/Chrome/Application/chrome.exe"),
        ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"),
        ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
        ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
        ("LOCALAPPDATA", "Microsoft/Edge/Application/msedge.exe"),
    ):
        base = os.environ.get(environment)
        if base:
            candidates.append(Path(base) / suffix)
    candidates.extend(
        [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("Chrome, Chromium, or Edge not found; pass --browser with an absolute path")


def browser_version(browser: Path) -> str:
    try:
        result = subprocess.run(
            [str(browser), "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    lines = (result.stdout or result.stderr).strip().splitlines()
    candidate = lines[0] if result.returncode == 0 and lines else ""
    return candidate if re.search(r"\d", candidate) else "unknown"


def render(
    html: Path,
    output: Path,
    size: tuple[int, int],
    browser: Path,
    *,
    overwrite: bool,
    timeout: int,
) -> None:
    html = html.expanduser().resolve()
    output = output.expanduser().resolve()
    browser = browser.expanduser().resolve()
    if not html.is_file():
        raise FileNotFoundError(f"HTML input not found: {html}")
    if output.suffix.lower() != ".png":
        raise ValueError("output filename must end in .png")
    if output.exists() and not overwrite:
        raise FileExistsError(f"output exists; pass --overwrite to replace it: {output}")
    if not browser.is_file():
        raise FileNotFoundError(f"browser executable not found: {browser}")
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = size

    with tempfile.TemporaryDirectory(prefix="codex-exact-render-") as profile_name:
        temporary = output.parent / f".{output.name}.{os.getpid()}.tmp.png"
        if temporary.exists():
            temporary.unlink()
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1500",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile_name}",
            f"--window-size={width},{height}",
            f"--screenshot={temporary}",
            html.as_uri(),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip().splitlines()
                raise RuntimeError(
                    f"browser render failed with exit code {result.returncode}: "
                    f"{detail[-1] if detail else 'no diagnostic output'}"
                )
            if not temporary.is_file():
                raise RuntimeError("browser returned success but produced no PNG")
            actual = png_size(temporary)
            if actual != size:
                raise ValueError(
                    f"PNG IHDR mismatch: expected {width}x{height}, got {actual[0]}x{actual[1]}"
                )
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("html", type=Path)
    command.add_argument("output", type=Path)
    command.add_argument("--size", type=parse_size, default=(1440, 900), metavar="WIDTHxHEIGHT")
    command.add_argument("--browser", help="absolute Chrome, Chromium, or Edge executable")
    command.add_argument("--overwrite", action="store_true")
    command.add_argument("--timeout", type=positive_int, default=60)
    args = command.parse_args(argv)
    try:
        browser = discover_browser(args.browser)
        render(args.html, args.output, args.size, browser, overwrite=args.overwrite, timeout=args.timeout)
        output = args.output.expanduser().resolve()
        print(
            f"OK output={output} pixels={args.size[0]}x{args.size[1]} "
            f"sha256={sha256(output)} browser={browser} version={browser_version(browser)}"
        )
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
