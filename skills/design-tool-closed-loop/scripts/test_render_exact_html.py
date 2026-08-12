#!/usr/bin/env python3
"""Tests for render_exact_html.py, including a real-browser smoke test when available."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("render_exact_html.py")
SPEC = importlib.util.spec_from_file_location("render_exact_html", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RenderExactHtmlTests(unittest.TestCase):
    def test_parse_size(self) -> None:
        self.assertEqual(MODULE.parse_size("1440x900"), (1440, 900))
        for value in ("bad", "0x900", "100x-1"):
            with self.subTest(value=value), self.assertRaises(Exception):
                MODULE.parse_size(value)

    def test_png_header_validation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "bad.png"
            path.write_bytes(b"not a png")
            with self.assertRaises(ValueError):
                MODULE.png_size(path)

    def test_real_browser_exact_dimensions(self) -> None:
        try:
            browser = MODULE.discover_browser()
        except FileNotFoundError as error:
            self.skipTest(str(error))
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            html = root / "screen.html"
            output = root / "screen.png"
            html.write_text(
                "<!doctype html><meta charset='utf-8'><style>"
                "html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#f5f8fb}"
                ".card{margin:40px;padding:24px;background:white;color:#16324f;font:24px Arial}"
                "</style><div class='card'>Finance Agent</div>",
                encoding="utf-8",
            )
            MODULE.render(html, output, (640, 360), browser, overwrite=False, timeout=60)
            self.assertEqual(MODULE.png_size(output), (640, 360))
            with self.assertRaises(FileExistsError):
                MODULE.render(html, output, (640, 360), browser, overwrite=False, timeout=60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
