import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location(
    "build_card_previews", SCRIPT_DIR / "build_card_previews.py"
)
build_card_previews = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_card_previews)


class BuildCardPreviewsTest(unittest.TestCase):
    @staticmethod
    def _png_header(width=1080, height=1440):
        return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(
            ">II", width, height
        )

    def test_preview_sizes_are_deterministic(self):
        self.assertEqual(
            build_card_previews.preview_sizes(6), ((906, 792), (408, 3048))
        )

    def test_build_html_contains_every_card_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards = [Path(tmp) / f"xhs-{index:02d}-card.png" for index in (1, 2)]
            result = build_card_previews.build_html(cards, "grid")
            for card in cards:
                self.assertIn(f"../output/{card.name}", result)
            self.assertNotIn(tmp, result)
            self.assertIn("width:612px", result)
            self.assertIn("height:408px", result)
            self.assertIn("repeat(2,270px)", result)

    def test_find_cards_uses_numbered_final_cards_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "xhs-02-body.png",
                "xhs-01-cover.png",
                "preview-grid.png",
                "draft.png",
            ):
                (root / name).write_bytes(b"x")
            self.assertEqual(
                [path.name for path in build_card_previews.find_cards(root)],
                ["xhs-01-cover.png", "xhs-02-body.png"],
            )

    def test_second_preview_failure_preserves_existing_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_dir = Path(tmp) / "cards" / "output"
            html_dir = cards_dir.parent / "html"
            cards_dir.mkdir(parents=True)
            html_dir.mkdir()
            (cards_dir / "xhs-01-cover.png").write_bytes(self._png_header())
            grid = cards_dir / "preview-grid.png"
            mobile = cards_dir / "preview-mobile.png"
            grid_html = html_dir / "preview-grid.html"
            mobile_html = html_dir / "preview-mobile.html"
            for path, value in (
                (grid, b"old-grid"),
                (mobile, b"old-mobile"),
                (grid_html, b"old-grid-html"),
                (mobile_html, b"old-mobile-html"),
            ):
                path.write_bytes(value)

            calls = 0

            def fake_render(_html, output, *_args, **_kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("mobile failed")
                output.write_bytes(b"new-grid")

            with mock.patch.object(build_card_previews, "render", side_effect=fake_render):
                with self.assertRaisesRegex(RuntimeError, "mobile failed"):
                    build_card_previews.build_previews(
                        cards_dir,
                        (1080, 1440),
                        Path("browser"),
                        overwrite=True,
                    )
            self.assertEqual(grid.read_bytes(), b"old-grid")
            self.assertEqual(mobile.read_bytes(), b"old-mobile")
            self.assertEqual(grid_html.read_bytes(), b"old-grid-html")
            self.assertEqual(mobile_html.read_bytes(), b"old-mobile-html")
            self.assertFalse(list(cards_dir.glob(".*.tmp.png")))
            self.assertFalse(list(html_dir.glob(".*.tmp.html")))


if __name__ == "__main__":
    unittest.main()
