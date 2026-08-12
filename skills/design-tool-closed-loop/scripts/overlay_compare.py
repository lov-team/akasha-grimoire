#!/usr/bin/env python3
"""Create overlays, a heat map, and a machine-readable image-difference report."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops


def unit_float(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def byte_value(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 255.0:
        raise argparse.ArgumentTypeError("must be between 0 and 255")
    return number


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mean_from_histogram(histogram: list[int]) -> float:
    count = sum(histogram)
    return sum(level * frequency for level, frequency in enumerate(histogram)) / count if count else 0.0


def compare(
    current_path: Path,
    reference_path: Path,
    output_dir: Path,
    *,
    alpha: float,
    grid: int,
    threshold: float,
    resize_reference: bool,
) -> dict[str, object]:
    current_path = current_path.expanduser().resolve()
    reference_path = reference_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not current_path.is_file():
        raise FileNotFoundError(f"current image not found: {current_path}")
    if not reference_path.is_file():
        raise FileNotFoundError(f"reference image not found: {reference_path}")

    with Image.open(current_path) as opened:
        current = opened.convert("RGB")
    with Image.open(reference_path) as opened:
        reference = opened.convert("RGB")
    current_size = current.size
    reference_size = reference.size
    resized = False
    if reference_size != current_size:
        if not resize_reference:
            raise ValueError(
                "image dimensions differ: "
                f"current={current_size[0]}x{current_size[1]} "
                f"reference={reference_size[0]}x{reference_size[1]}; "
                "capture the same viewport or pass --resize-reference explicitly"
            )
        reference = reference.resize(current_size, Image.Resampling.LANCZOS)
        resized = True

    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_alphas = sorted({0.3, 0.7, alpha})
    overlay_files: list[str] = []
    for overlay_alpha in overlay_alphas:
        filename = f"overlay_{round(overlay_alpha * 100):02d}.png"
        Image.blend(current, reference, overlay_alpha).save(output_dir / filename)
        overlay_files.append(filename)

    difference = ImageChops.difference(current, reference).convert("L")
    zero = Image.new("L", current_size, 0)
    heat = Image.merge("RGB", (difference, zero, zero))
    Image.blend(current, heat, 0.6).save(output_dir / "diff_heat.png")

    cells: list[dict[str, int | float]] = []
    width, height = current_size
    for top in range(0, height, grid):
        for left in range(0, width, grid):
            right, bottom = min(left + grid, width), min(top + grid, height)
            cell_mean = mean_from_histogram(difference.crop((left, top, right, bottom)).histogram())
            if cell_mean > threshold:
                cells.append(
                    {
                        "x": left,
                        "y": top,
                        "w": right - left,
                        "h": bottom - top,
                        "diff": round(cell_mean, 3),
                    }
                )
    cells.sort(key=lambda item: (-float(item["diff"]), int(item["y"]), int(item["x"])))
    overall = mean_from_histogram(difference.histogram())
    report: dict[str, object] = {
        "current": {
            "path": str(current_path),
            "sha256": sha256(current_path),
            "original_size": list(current_size),
        },
        "reference": {
            "path": str(reference_path),
            "sha256": sha256(reference_path),
            "original_size": list(reference_size),
        },
        "comparison_size": list(current_size),
        "reference_resized": resized,
        "alpha": alpha,
        "grid": grid,
        "threshold": threshold,
        "overall_mean_diff": round(overall, 6),
        "high_diff_cells": len(cells),
        "top_cells": cells[:10],
        "overlay_files": overlay_files,
        "heatmap_file": "diff_heat.png",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "diff_grid.txt").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f"overall_mean_diff={overall:.6f} size={width}x{height} "
            f"grid={grid} threshold={threshold:g} reference_resized={str(resized).lower()}\n"
        )
        for cell in cells[:200]:
            stream.write(
                f"({cell['x']},{cell['y']}) {cell['w']}x{cell['h']} diff={cell['diff']}\n"
            )
    return report


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("current", type=Path)
    command.add_argument("reference", type=Path)
    command.add_argument("output_dir", type=Path)
    command.add_argument("--alpha", type=unit_float, default=0.5)
    command.add_argument("--grid", type=positive_int, default=40)
    command.add_argument("--threshold", type=byte_value, default=12.0)
    command.add_argument(
        "--resize-reference",
        action="store_true",
        help="explicitly resize the reference to the current image dimensions",
    )
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = compare(
            args.current,
            args.reference,
            args.output_dir,
            alpha=args.alpha,
            grid=args.grid,
            threshold=args.threshold,
            resize_reference=args.resize_reference,
        )
    except (OSError, ValueError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1
    print(
        "OK "
        f"size={report['comparison_size'][0]}x{report['comparison_size'][1]} "
        f"overall_mean_diff={report['overall_mean_diff']} "
        f"high_diff_cells={report['high_diff_cells']} "
        f"reference_resized={str(report['reference_resized']).lower()} "
        f"out={args.output_dir.expanduser().resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
