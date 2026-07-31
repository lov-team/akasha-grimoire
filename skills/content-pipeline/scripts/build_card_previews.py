#!/usr/bin/env python3
"""Build deterministic grid and mobile-strip previews for final card PNGs."""

from __future__ import annotations

import argparse
import html
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from render_html_card import (
    browser_version,
    discover_browser,
    parse_size,
    png_dimensions,
    render,
)


CARD_PATTERN = re.compile(r"^xhs-\d{2}-.+\.png$")


def find_cards(cards_dir: Path) -> list[Path]:
    cards = sorted(
        path.resolve()
        for path in cards_dir.expanduser().resolve().iterdir()
        if path.is_file() and CARD_PATTERN.match(path.name)
    )
    if not cards:
        raise FileNotFoundError(f"no xhs-NN-*.png cards found: {cards_dir}")
    return cards


def preview_sizes(count: int) -> tuple[tuple[int, int], tuple[int, int]]:
    if count <= 0:
        raise ValueError("card count must be positive")
    gap = 24
    columns = min(3, count)
    rows = math.ceil(count / columns)
    grid = (columns * 270 + (columns + 1) * gap, rows * 360 + (rows + 1) * gap)
    mobile = (408, count * 480 + (count + 1) * gap)
    return grid, mobile


def build_html(cards: list[Path], mode: str) -> str:
    if mode not in {"grid", "mobile"}:
        raise ValueError("mode must be grid or mobile")
    width, height = preview_sizes(len(cards))[0 if mode == "grid" else 1]
    if mode == "grid":
        columns = min(3, len(cards))
        body = f"display:grid;grid-template-columns:repeat({columns},270px);gap:24px;padding:24px;align-content:start"
        image = "width:270px;height:360px"
    else:
        body = "display:flex;flex-direction:column;gap:24px;padding:24px"
        image = "width:360px;height:480px"
    images = "\n".join(
        f'<img src="../output/{quote(card.name)}" alt="{html.escape(card.name)}">'
        for card in cards
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{{width:{width}px;height:{height}px;margin:0;overflow:hidden;background:#d9d9d9}}
body{{box-sizing:border-box;{body}}}
img{{display:block;object-fit:contain;background:white;box-shadow:0 2px 10px #0002;{image}}}
</style></head><body>{images}</body></html>
"""


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".tmp.html", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def reserve_temporary_path(parent: Path, prefix: str, suffix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=parent)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path


def build_previews(
    cards_dir: Path,
    expected_card_size: tuple[int, int],
    browser: Path,
    overwrite: bool = False,
    timeout: int = 60,
) -> tuple[Path, Path]:
    cards_dir = cards_dir.expanduser().resolve()
    cards = find_cards(cards_dir)
    for card in cards:
        actual = png_dimensions(card)
        if actual != expected_card_size:
            raise ValueError(
                f"card size mismatch: expected {expected_card_size}, got {actual}: {card}"
            )
    html_dir = cards_dir.parent / "html"
    sizes = preview_sizes(len(cards))
    targets = [
        (
            mode,
            size,
            html_dir / f"preview-{mode}.html",
            cards_dir / f"preview-{mode}.png",
        )
        for mode, size in zip(("grid", "mobile"), sizes)
    ]
    if not overwrite:
        existing = [
            path
            for _, _, html_path, output in targets
            for path in (html_path, output)
            if path.exists()
        ]
        if existing:
            raise FileExistsError(
                f"preview exists; pass --overwrite to replace it: {existing[0]}"
            )
    staged: list[tuple[Path, Path]] = []
    temporary_paths: list[Path] = []
    try:
        for mode, size, html_path, output in targets:
            temporary_html = reserve_temporary_path(
                html_dir, f".preview-{mode}.", ".tmp.html"
            )
            temporary_output = reserve_temporary_path(
                cards_dir, f".preview-{mode}.", ".tmp.png"
            )
            temporary_paths.extend((temporary_html, temporary_output))
            write_text_atomic(temporary_html, build_html(cards, mode))
            render(
                temporary_html,
                temporary_output,
                size,
                browser,
                overwrite=False,
                timeout=timeout,
            )
            staged.extend(((temporary_html, html_path), (temporary_output, output)))
        for temporary, final in staged:
            os.replace(temporary, final)
        return targets[0][3], targets[1][3]
    finally:
        for temporary in temporary_paths:
            if temporary.exists():
                temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cards_dir", help="cards/output directory")
    parser.add_argument("--card-size", default="1080x1440", help="WIDTHxHEIGHT")
    parser.add_argument("--browser", help="absolute Chromium/Chrome/Edge executable")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        browser = discover_browser(args.browser)
        grid, mobile = build_previews(
            Path(args.cards_dir),
            parse_size(args.card_size),
            browser,
            overwrite=args.overwrite,
            timeout=args.timeout,
        )
        print(
            f"OK grid={grid} mobile={mobile} browser={browser} "
            f"version={browser_version(browser)}"
        )
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
