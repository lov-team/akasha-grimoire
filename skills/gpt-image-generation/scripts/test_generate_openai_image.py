#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("generate_openai_image.py")
SPEC = importlib.util.spec_from_file_location("generate_openai_image", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RequestFormatTest(unittest.TestCase):
    def test_generation_request_is_always_b64_json(self) -> None:
        args = argparse.Namespace(
            model="gpt-image-2",
            prompt="test",
            size="1024x1024",
            response_format="url",
        )

        payload = json.loads(MODULE._json_body(args))

        self.assertEqual(payload["response_format"], "b64_json")

    def test_edit_request_is_always_b64_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "reference.png"
            image_path.write_bytes(b"fake-png")
            args = argparse.Namespace(
                model="gpt-image-2",
                prompt="test",
                size="1024x1024",
                response_format="url",
                image=[str(image_path)],
            )

            body, _content_type = MODULE._multipart_body(args)

        self.assertIn(b'name="response_format"\r\n\r\nb64_json\r\n', body)
        self.assertNotIn(b'name="response_format"\r\n\r\nurl\r\n', body)
        self.assertIn(b'name="image"; filename="reference.png"', body)
        self.assertNotIn(b'name="image[]"', body)

    def test_multi_image_edit_uses_repeated_image_array_parts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.png"
            second = Path(directory) / "second.png"
            first.write_bytes(b"first-image")
            second.write_bytes(b"second-image")
            args = argparse.Namespace(
                model="gpt-image-2",
                prompt="combine",
                size="1024x1024",
                image=[str(first), str(second)],
            )

            body, _content_type = MODULE._multipart_body(args)

        self.assertEqual(body.count(b'name="image[]"; filename='), 2)
        self.assertIn(b'filename="first.png"', body)
        self.assertIn(b'filename="second.png"', body)
        self.assertIn(b"first-image", body)
        self.assertIn(b"second-image", body)

    def test_edit_rejects_more_than_five_images(self) -> None:
        args = argparse.Namespace(
            model="gpt-image-2",
            prompt="combine",
            size="1024x1024",
            image=[f"reference-{index}.png" for index in range(6)],
        )

        with self.assertRaisesRegex(SystemExit, "at most 5"):
            MODULE._multipart_body(args)

    def test_url_response_is_rejected_as_contract_violation(self) -> None:
        payload = {
            "created": 1,
            "data": [{"url": "https://example.invalid/image.png"}],
        }

        with self.assertRaisesRegex(SystemExit, "requested b64_json"):
            MODULE._summarize_success(payload, 0.1)


if __name__ == "__main__":
    unittest.main()
