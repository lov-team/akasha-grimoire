#!/usr/bin/env python3
"""Render one local HTML card to an exact-size PNG with Chromium."""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_SIZE = "1080x1440"


def parse_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (ValueError, AttributeError) as exc:
        raise ValueError("size must use WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise ValueError("size must use positive WIDTHxHEIGHT")
    return width, height


def png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"renderer did not create a PNG: {path}")
    return struct.unpack(">II", header[16:24])


def discover_browser(explicit: str | None = None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
        raise FileNotFoundError(f"browser is not executable: {candidate}")
    candidates: list[Path] = []
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
        "msedge",
    ):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    candidates.extend(
        [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    )
    for variable, suffix in (
        ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
        ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
    ):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / suffix)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise FileNotFoundError("Chromium browser not found; pass --browser /absolute/path")


def browser_version(browser: Path) -> str:
    try:
        completed = subprocess.run(
            [str(browser), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        line = (completed.stdout or completed.stderr).strip().splitlines()
        return line[0] if completed.returncode == 0 and line else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def build_command(
    browser: Path, html: Path, output: Path, width: int, height: int
) -> list[str]:
    return [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=1500",
        "--no-first-run",
        "--no-default-browser-check",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        f"--screenshot={output}",
        html.as_uri(),
    ]


def render(
    html: Path,
    output: Path,
    size: tuple[int, int],
    browser: Path,
    overwrite: bool = False,
    timeout: int = 60,
) -> None:
    html = html.expanduser().resolve()
    output = output.expanduser().resolve()
    if not html.is_file():
        raise FileNotFoundError(f"HTML input not found: {html}")
    if output.suffix.lower() != ".png":
        raise ValueError("output must end in .png")
    if output.exists() and not overwrite:
        raise FileExistsError(f"output exists; pass --overwrite to replace it: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}.", suffix=".tmp.png", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        completed = subprocess.run(
            build_command(browser, html, temporary, width, height),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()[-1:]
            raise RuntimeError(
                f"browser render failed ({completed.returncode}): {' '.join(detail)}"
            )
        if not temporary.is_file():
            raise RuntimeError("browser returned success without output")
        actual = png_dimensions(temporary)
        if actual != size:
            raise ValueError(f"output size mismatch: expected {size}, got {actual}")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", help="local HTML file")
    parser.add_argument("output", help="output PNG path")
    parser.add_argument("--size", default=DEFAULT_SIZE, help="WIDTHxHEIGHT")
    parser.add_argument("--browser", help="absolute Chromium/Chrome/Edge executable")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        size = parse_size(args.size)
        browser = discover_browser(args.browser)
        render(
            Path(args.html),
            Path(args.output),
            size,
            browser,
            overwrite=args.overwrite,
            timeout=args.timeout,
        )
        print(
            f"OK output={Path(args.output).expanduser().resolve()} "
            f"pixels={size[0]}x{size[1]} browser={browser} "
            f"version={browser_version(browser)}"
        )
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
