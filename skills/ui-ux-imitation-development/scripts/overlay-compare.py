#!/usr/bin/env python3
"""半透明叠加对比：把参考界面截图叠在现有界面截图上，输出叠加图与差异热区图。

用法:
  overlay-compare.py <current.png> <reference.png> <out_dir> [--alpha 0.5] [--grid 40]

输出（写入 out_dir）:
  overlay_50.png   参考图按 alpha 叠在现有图上（默认 0.5，另固定输出 0.3/0.7 两档）
  diff_heat.png    像素差异热区图（红色越深差异越大）
  diff_grid.txt    按网格聚合的差异报告：每个高差异网格的位置、差异强度
  summary.json     整体差异指标（对齐后差异均值、最大差异网格 Top10）

两图尺寸不同时，参考图按宽度等比缩放到现有图宽度后顶部对齐再比较；
不做智能配准，截图时应尽量使用相同视口宽度。
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops


def load_args():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 3:
        sys.exit(__doc__)
    opts = {"alpha": 0.5, "grid": 40}
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--alpha":
            opts["alpha"] = float(next(it))
        elif a == "--grid":
            opts["grid"] = int(next(it))
    return Path(args[0]), Path(args[1]), Path(args[2]), opts


def main():
    cur_p, ref_p, out_dir, opts = load_args()
    out_dir.mkdir(parents=True, exist_ok=True)

    cur = Image.open(cur_p).convert("RGB")
    ref = Image.open(ref_p).convert("RGB")

    # 按宽度等比缩放参考图，顶部对齐，高度取两者较小值
    if ref.width != cur.width:
        ref = ref.resize((cur.width, round(ref.height * cur.width / ref.width)))
    h = min(cur.height, ref.height)
    cur_c, ref_c = cur.crop((0, 0, cur.width, h)), ref.crop((0, 0, cur.width, h))

    for a in sorted({opts["alpha"], 0.3, 0.7}):
        Image.blend(cur_c, ref_c, a).save(out_dir / f"overlay_{int(a * 100)}.png")

    diff = ImageChops.difference(cur_c, ref_c).convert("L")
    heat = Image.merge("RGB", (diff, Image.new("L", diff.size), Image.new("L", diff.size)))
    Image.blend(cur_c, heat, 0.6).save(out_dir / "diff_heat.png")

    g = opts["grid"]
    cells = []
    for y in range(0, h, g):
        for x in range(0, cur.width, g):
            cell = diff.crop((x, y, min(x + g, cur.width), min(y + g, h)))
            hist = cell.histogram()
            n = sum(hist)
            mean = sum(i * c for i, c in enumerate(hist)) / n if n else 0
            if mean > 12:  # 忽略近似区域
                cells.append({"x": x, "y": y, "w": g, "h": g, "diff": round(mean, 1)})
    cells.sort(key=lambda c: -c["diff"])

    total_hist = diff.histogram()
    n = sum(total_hist)
    overall = sum(i * c for i, c in enumerate(total_hist)) / n if n else 0

    with open(out_dir / "diff_grid.txt", "w") as f:
        f.write(f"overall_mean_diff={overall:.1f} compared_height={h} grid={g}\n")
        for c in cells[:200]:
            f.write(f"({c['x']},{c['y']}) {c['w']}x{c['h']} diff={c['diff']}\n")

    (out_dir / "summary.json").write_text(json.dumps({
        "overall_mean_diff": round(overall, 1),
        "compared_size": [cur.width, h],
        "high_diff_cells": len(cells),
        "top_cells": cells[:10],
    }, ensure_ascii=False, indent=2))

    print(f"OK overall_mean_diff={overall:.1f} high_diff_cells={len(cells)} out={out_dir}")


if __name__ == "__main__":
    main()
