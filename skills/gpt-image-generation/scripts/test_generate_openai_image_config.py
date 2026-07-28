#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("generate_openai_image.py")
SPEC = importlib.util.spec_from_file_location("generate_openai_image_under_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ImageConfigTest(unittest.TestCase):
    def test_base_url_default_and_override_precedence(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(MODULE._base_url(), "https://newapi.1234bot.com/v1")
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/v1",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(MODULE._base_url(), "https://new-api.example/v1")
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/v1",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
                "IMAGE_PROXY_BASE_URL": "https://image.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(MODULE._base_url(), "https://image.example/v1")

    def test_env_file_can_override_default_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=True
        ):
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "NEW_API_BASE_URL=https://env-file.example/v1\n",
                encoding="utf-8",
            )
            MODULE._load_env_file(str(env_file))
            self.assertEqual(MODULE._base_url(), "https://env-file.example/v1")

    def test_missing_key_message_links_lovbrowser_and_payment_flow(self) -> None:
        message = MODULE._missing_key_message()
        self.assertIn("https://lovbrowser.com", message)
        self.assertIn("payment", message)
        self.assertIn("NEW_API_API_KEY", message)


if __name__ == "__main__":
    unittest.main()
