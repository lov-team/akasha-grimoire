#!/usr/bin/env python3
"""Regression tests for overlay_compare.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).with_name("overlay_compare.py")


class OverlayCompareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def image(self, name: str, size: tuple[int, int], color: str) -> Path:
        path = self.root / name
        Image.new("RGB", size, color).save(path)
        return path

    def run_script(self, *arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *(str(item) for item in arguments)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_identical_images_have_zero_difference_and_alpha_works(self) -> None:
        current = self.image("current.png", (120, 80), "#174A7E")
        reference = self.image("reference.png", (120, 80), "#174A7E")
        output = self.root / "out"
        result = self.run_script(current, reference, output, "--alpha", "0.4", "--grid", "16")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(report["overall_mean_diff"], 0)
        self.assertEqual(report["high_diff_cells"], 0)
        self.assertFalse(report["reference_resized"])
        self.assertTrue((output / "overlay_40.png").is_file())
        self.assertEqual(len(report["current"]["sha256"]), 64)

    def test_different_sizes_fail_by_default(self) -> None:
        current = self.image("current.png", (120, 80), "white")
        reference = self.image("reference.png", (60, 40), "white")
        result = self.run_script(current, reference, self.root / "out")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dimensions differ", result.stderr)

    def test_explicit_reference_resize_succeeds(self) -> None:
        current = self.image("current.png", (120, 80), "white")
        reference = self.image("reference.png", (60, 40), "white")
        output = self.root / "out"
        result = self.run_script(current, reference, output, "--resize-reference")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        self.assertTrue(report["reference_resized"])
        self.assertEqual(report["reference"]["original_size"], [60, 40])
        self.assertEqual(report["comparison_size"], [120, 80])

    def test_invalid_alpha_and_grid_fail(self) -> None:
        current = self.image("current.png", (20, 20), "white")
        reference = self.image("reference.png", (20, 20), "white")
        for arguments in (("--alpha", "1.1"), ("--grid", "0"), ("--grid", "nope")):
            with self.subTest(arguments=arguments):
                result = self.run_script(current, reference, self.root / "out", *arguments)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
