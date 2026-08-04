#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPT = Path(__file__).with_name("render_cover.py")
SPEC = importlib.util.spec_from_file_location("render_cover", SCRIPT)
assert SPEC and SPEC.loader
render_cover = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_cover)


class RenderCoverTests(unittest.TestCase):
    def _background(self, directory: str) -> Path:
        path = Path(directory, "background.png")
        image = Image.new("RGB", (800, 1000), (24, 50, 76))
        draw = ImageDraw.Draw(image)
        draw.ellipse((260, 180, 560, 480), fill=(214, 167, 132))
        draw.rectangle((170, 500, 630, 1000), fill=(45, 72, 105))
        image.save(path)
        return path

    def test_renders_verified_3x4_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._background(temp_dir)
            output = Path(temp_dir, "cover.png")
            rc = render_cover.main(
                [
                    "--image",
                    str(source),
                    "--title",
                    "数学、道德经与AI",
                    "--subtitle",
                    "寻找世界背后的结构",
                    "--label",
                    "认知与技术",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(output.is_file())
            with Image.open(output) as image:
                self.assertEqual(image.size, (1080, 1440))
                self.assertEqual(image.format, "PNG")
                self.assertGreater(len(image.getcolors(maxcolors=2_000_000) or []), 10)

    def test_refuses_silent_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._background(temp_dir)
            output = Path(temp_dir, "cover.png")
            output.write_bytes(b"existing")
            with self.assertRaises(SystemExit) as caught:
                render_cover.main(
                    [
                        "--image",
                        str(source),
                        "--title",
                        "测试标题",
                        "--output",
                        str(output),
                    ]
                )
            self.assertIn("already exists", str(caught.exception))
            self.assertEqual(output.read_bytes(), b"existing")

    def test_balances_short_title_without_ai_orphan(self) -> None:
        image = Image.new("RGB", (1080, 1440), (20, 20, 20))
        draw = ImageDraw.Draw(image)
        font_path = render_cover._find_font(None)
        font, lines = render_cover._fit_title(
            draw,
            "数学、道德经与AI",
            font_path,
            930,
        )
        self.assertEqual(len(lines), 2)
        self.assertNotEqual(lines[-1], "AI")
        widths = [render_cover._text_width(draw, line, font) for line in lines]
        self.assertGreater(min(widths) / max(widths), 0.42)

    def test_explicit_title_break_preserves_terms(self) -> None:
        image = Image.new("RGB", (1080, 1440), (20, 20, 20))
        draw = ImageDraw.Draw(image)
        font_path = render_cover._find_font(None)
        _, lines = render_cover._fit_title(
            draw,
            "数学·道德经\nAI的底层联系",
            font_path,
            930,
        )
        self.assertEqual(lines, ["数学·道德经", "AI的底层联系"])

    def test_rejects_invalid_focus(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._background(temp_dir)
            with self.assertRaises(SystemExit) as caught:
                render_cover.main(
                    [
                        "--image",
                        str(source),
                        "--title",
                        "测试标题",
                        "--focus-x",
                        "1.5",
                        "--output",
                        str(Path(temp_dir, "cover.png")),
                    ]
                )
            self.assertIn("between 0 and 1", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
