#!/usr/bin/env python3
"""Render deterministic Chinese title typography over a cover background."""

from __future__ import annotations

import argparse
import itertools
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFont, ImageOps


DEFAULT_FONTS = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
)


def _find_font(explicit: str | None) -> Path:
    candidates = (explicit,) if explicit else DEFAULT_FONTS
    for value in candidates:
        if value and Path(value).expanduser().is_file():
            return Path(value).expanduser().resolve()
    raise SystemExit("no CJK font found; provide --font /absolute/path/to/font.ttf")


def _parse_color(value: str) -> tuple[int, int, int]:
    try:
        return ImageColor.getrgb(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid color: {value}") from exc


def _font(path: Path, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size=size, index=index)
    except OSError as exc:
        raise SystemExit(f"failed to load font: {path}") from exc


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=font)


def _wrap_chars(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        current = ""
        for character in paragraph.strip():
            candidate = current + character
            if current and _text_width(draw, candidate, font) > max_width:
                lines.append(current.rstrip())
                current = character.lstrip()
            else:
                current = candidate
        if current:
            lines.append(current.rstrip())
    return lines


def _wrap_title(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    explicit = [line.strip() for line in text.splitlines() if line.strip()]
    if len(explicit) > 1:
        if len(explicit) <= max_lines and all(_text_width(draw, line, font) <= max_width for line in explicit):
            return explicit
        return _wrap_chars(draw, text, font, max_width)

    characters = list(text.strip())
    if len(characters) > 40:
        return _wrap_chars(draw, text, font, max_width)
    for line_count in range(1, max_lines + 1):
        best: tuple[float, list[str]] | None = None
        for breaks in itertools.combinations(range(1, len(characters)), line_count - 1):
            points = (0, *breaks, len(characters))
            lines = ["".join(characters[points[index] : points[index + 1]]).strip() for index in range(line_count)]
            if not all(lines):
                continue
            widths = [_text_width(draw, line, font) for line in lines]
            if any(width > max_width for width in widths):
                continue
            raggedness = sum((max(widths) - width) ** 2 for width in widths)
            orphan_penalty = max_width**2 if line_count > 1 and min(widths) < max(widths) * 0.42 else 0
            score = raggedness + orphan_penalty
            if best is None or score < best[0]:
                best = (score, lines)
        if best is not None:
            return best[1]
    return _wrap_chars(draw, text, font, max_width)


def _fit_title(
    draw: ImageDraw.ImageDraw,
    title: str,
    font_path: Path,
    max_width: int,
    max_lines: int = 3,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(128, 55, -4):
        font = _font(font_path, size)
        lines = _wrap_title(draw, title, font, max_width, max_lines)
        if 1 <= len(lines) <= max_lines:
            return font, lines
    raise SystemExit("title is too long for a readable 3:4 cover; shorten --title")


def _gradient_overlay(size: tuple[int, int], position: str) -> Image.Image:
    width, height = size
    gradient = Image.new("L", (1, height))
    pixels = gradient.load()
    assert pixels is not None
    for y in range(height):
        ratio = y / max(1, height - 1)
        strength = (1.0 - ratio) if position == "top" else ratio
        pixels[0, y] = int(225 * max(0.0, min(1.0, strength * 1.55)))
    alpha = gradient.resize((width, height))
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    overlay.putalpha(alpha)
    return overlay


def render_cover(args: argparse.Namespace) -> Path:
    source = Path(args.image).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"cover image does not exist: {source}")
    if output.exists() and not args.overwrite:
        raise SystemExit(f"output already exists: {output}; pass --overwrite to replace it")
    if not args.title.strip():
        raise SystemExit("--title must not be empty")

    font_path = _find_font(args.font)
    try:
        with Image.open(source) as opened:
            background = ImageOps.exif_transpose(opened).convert("RGB")
    except OSError as exc:
        raise SystemExit(f"failed to read cover image: {source}") from exc

    background = ImageOps.fit(
        background,
        (args.width, args.height),
        method=Image.Resampling.LANCZOS,
        centering=(args.focus_x, args.focus_y),
    )
    background = ImageEnhance.Brightness(background).enhance(args.brightness)
    canvas = background.convert("RGBA")
    canvas.alpha_composite(_gradient_overlay(canvas.size, args.position))
    draw = ImageDraw.Draw(canvas)

    margin = max(48, round(args.width * 0.07))
    max_width = args.width - margin * 2
    title_text = args.title.strip().replace("|", "\n")
    title_font, title_lines = _fit_title(draw, title_text, font_path, max_width)
    title_gap = max(10, round(title_font.size * 0.12))
    title_height = sum(
        draw.textbbox((0, 0), line, font=title_font, stroke_width=2)[3]
        for line in title_lines
    ) + title_gap * (len(title_lines) - 1)

    label_font = _font(font_path, 34)
    subtitle_font = _font(font_path, 42)
    label_height = 58 if args.label else 0
    subtitle_height = 58 if args.subtitle else 0
    block_height = label_height + title_height + subtitle_height + 44
    if args.position == "top":
        y = max(64, round(args.height * 0.075))
    else:
        y = args.height - max(70, round(args.height * 0.07)) - block_height

    accent = args.accent
    white = (255, 255, 255)
    shadow = (0, 0, 0)
    if args.label:
        label = args.label.strip()
        bbox = draw.textbbox((0, 0), label, font=label_font)
        pill_w = bbox[2] - bbox[0] + 40
        draw.rounded_rectangle((margin, y, margin + pill_w, y + 48), radius=18, fill=accent + (245,))
        draw.text((margin + 20, y + 5), label, font=label_font, fill=(20, 20, 20))
        y += label_height

    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font, stroke_width=3)
        line_height = bbox[3] - bbox[1]
        if args.align == "center":
            x = (args.width - _text_width(draw, line, title_font)) / 2
        else:
            x = margin
        draw.text(
            (x, y),
            line,
            font=title_font,
            fill=white,
            stroke_width=3,
            stroke_fill=shadow,
        )
        y += line_height + title_gap

    if args.subtitle:
        y += 14
        subtitle = args.subtitle.strip()
        subtitle_lines = _wrap_chars(draw, subtitle, subtitle_font, max_width)
        if len(subtitle_lines) > 2:
            raise SystemExit("subtitle is too long; keep it within two lines")
        for line in subtitle_lines:
            if args.align == "center":
                x = (args.width - _text_width(draw, line, subtitle_font)) / 2
            else:
                x = margin
            draw.text((x, y), line, font=subtitle_font, fill=(245, 245, 245), stroke_width=2, stroke_fill=shadow)
            y += 54

    output.parent.mkdir(parents=True, exist_ok=True)
    suffix = output.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise SystemExit("cover output must end in .png, .jpg, or .jpeg")
    file_format = "PNG" if suffix == ".png" else "JPEG"
    final_image = canvas.convert("RGB") if file_format == "JPEG" else canvas
    handle = tempfile.NamedTemporaryFile(prefix=f".{output.stem}-", suffix=suffix, dir=output.parent, delete=False)
    temp_path = Path(handle.name)
    handle.close()
    try:
        final_image.save(temp_path, format=file_format, quality=95)
        with Image.open(temp_path) as verified:
            if verified.size != (args.width, args.height):
                raise SystemExit(f"cover verification failed: pixels={verified.size}")
            verified.verify()
        os.replace(temp_path, output)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    print(f"OK output={output} pixels={args.width}x{args.height} format={file_format} font={font_path}")
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="background or selected talking-head frame")
    parser.add_argument("--title", required=True, help="main title; use | to force a semantic line break")
    parser.add_argument("--subtitle")
    parser.add_argument("--label")
    parser.add_argument("--output", required=True)
    parser.add_argument("--font", help="CJK .ttf/.otf/.ttc path")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1440)
    parser.add_argument("--position", choices=("top", "bottom"), default="bottom")
    parser.add_argument("--align", choices=("left", "center"), default="left")
    parser.add_argument("--focus-x", type=float, default=0.5)
    parser.add_argument("--focus-y", type=float, default=0.5)
    parser.add_argument("--brightness", type=float, default=0.86)
    parser.add_argument("--accent", type=_parse_color, default=_parse_color("#FFD54A"))
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.width < 320 or args.height < 320:
        raise SystemExit("cover dimensions must be at least 320x320")
    if not 0 <= args.focus_x <= 1 or not 0 <= args.focus_y <= 1:
        raise SystemExit("--focus-x and --focus-y must be between 0 and 1")
    if not 0.2 <= args.brightness <= 1.5:
        raise SystemExit("--brightness must be between 0.2 and 1.5")
    render_cover(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
