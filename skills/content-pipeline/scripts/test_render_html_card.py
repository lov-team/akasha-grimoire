import importlib.util
import os
import subprocess
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("render_html_card.py")
SPEC = importlib.util.spec_from_file_location("render_html_card", MODULE_PATH)
render_html_card = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render_html_card)


class RenderHtmlCardTest(unittest.TestCase):
    def test_parse_size_accepts_positive_dimensions(self):
        self.assertEqual(render_html_card.parse_size("1080x1440"), (1080, 1440))

    def test_parse_size_rejects_invalid_value(self):
        with self.assertRaisesRegex(ValueError, "WIDTHxHEIGHT"):
            render_html_card.parse_size("1080:1440")

    def test_png_dimensions_reads_ihdr(self):
        header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 1080, 1440)
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "card.png"
            image.write_bytes(header)
            self.assertEqual(render_html_card.png_dimensions(image), (1080, 1440))

    def test_build_command_locks_viewport_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html, output = root / "card.html", root / "card.png"
            command = render_html_card.build_command(
                root / "browser", html, output, 1080, 1440
            )
            self.assertIn("--window-size=1080,1440", command)
            self.assertIn("--force-device-scale-factor=1", command)
            self.assertIn(f"--screenshot={output}", command)
            self.assertEqual(command[-1], html.as_uri())

    def test_explicit_browser_path_is_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing-browser"
            with self.assertRaisesRegex(FileNotFoundError, "not executable"):
                render_html_card.discover_browser(str(missing))
            browser = root / "browser"
            browser.write_text("#!/bin/sh\n")
            os.chmod(browser, 0o755)
            self.assertEqual(
                render_html_card.discover_browser(str(browser)), browser.resolve()
            )

    @staticmethod
    def _png_header(width=1080, height=1440):
        return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(
            ">II", width, height
        )

    def test_failed_overwrite_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html, output = root / "card.html", root / "card.png"
            html.write_text("<p>card</p>")
            output.write_bytes(b"old-success")
            failed = subprocess.CompletedProcess([], 1, "", "render failed")
            with mock.patch.object(render_html_card.subprocess, "run", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, "render failed"):
                    render_html_card.render(
                        html, output, (1080, 1440), root / "browser", overwrite=True
                    )
            self.assertEqual(output.read_bytes(), b"old-success")
            self.assertFalse(list(root.glob(".*.tmp.png")))

    def test_size_mismatch_preserves_existing_output_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html, output = root / "card.html", root / "card.png"
            html.write_text("<p>card</p>")
            output.write_bytes(b"old-success")

            def fake_run(command, **_kwargs):
                screenshot = next(x.split("=", 1)[1] for x in command if x.startswith("--screenshot="))
                Path(screenshot).write_bytes(self._png_header(1, 1))
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(render_html_card.subprocess, "run", side_effect=fake_run):
                with self.assertRaisesRegex(ValueError, "size mismatch"):
                    render_html_card.render(
                        html, output, (1080, 1440), root / "browser", overwrite=True
                    )
            self.assertEqual(output.read_bytes(), b"old-success")
            self.assertFalse(list(root.glob(".*.tmp.png")))

    def test_success_atomically_replaces_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html, output = root / "card.html", root / "card.png"
            html.write_text("<p>card</p>")
            output.write_bytes(b"old-success")

            def fake_run(command, **_kwargs):
                screenshot = next(x.split("=", 1)[1] for x in command if x.startswith("--screenshot="))
                Path(screenshot).write_bytes(self._png_header())
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(render_html_card.subprocess, "run", side_effect=fake_run):
                render_html_card.render(
                    html, output, (1080, 1440), root / "browser", overwrite=True
                )
            self.assertEqual(render_html_card.png_dimensions(output), (1080, 1440))
            self.assertFalse(list(root.glob(".*.tmp.png")))


if __name__ == "__main__":
    unittest.main()
