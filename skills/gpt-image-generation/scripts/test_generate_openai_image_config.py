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
        self.assertIn("QR code", message)
        self.assertIn("akasha_credentials.py finish", message)

    def test_shared_recharge_helper_loads_and_exposes_flag(self) -> None:
        recharge = MODULE._load_akasha_recharge()
        self.assertTrue(callable(recharge.detect_insufficient_user_quota))
        self.assertTrue(hasattr(recharge, "RechargeController"))
        parser = __import__("argparse").ArgumentParser()
        recharge.add_recharge_argument(parser)
        args = parser.parse_args(["--recharge-usd", "12.5"])
        self.assertEqual(args.recharge_usd, "12.5")
        body = (
            b'{"error":{"code":"insufficient_user_quota","metadata":'
            b'{"recharge":{"supported":true,"ticket_endpoint":"/v1/tooling/recharge-ticket"}}}}'
        )
        self.assertIsNone(
            recharge.detect_insufficient_user_quota(
                403, body, base_url="https://private.example/v1"
            )
        )
        self.assertIsNotNone(
            recharge.detect_insufficient_user_quota(
                403, body, base_url="https://newapi.1234bot.com/v1"
            )
        )

    def test_loader_identity_stable_across_repeated_calls(self) -> None:
        a = MODULE._load_akasha_recharge()
        b = MODULE._load_akasha_recharge()
        self.assertIs(a, b)
        self.assertIs(a.InsufficientUserQuotaError, b.InsufficientUserQuotaError)
        self.assertTrue(str(Path(a.__file__).resolve()).endswith("shared/akasha_recharge.py"))

    def test_private_gateway_ignores_bad_recharge_env_and_keeps_original_403(self) -> None:
        """Private base + invalid AKASHA_RECHARGE_USD must not change non-quota path."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                body = json.dumps({"error": {"code": "rate_limit", "message": "slow down"}}).encode()
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(
                os.environ,
                {
                    "NEW_API_API_KEY": "private-key",
                    "AKASHA_RECHARGE_USD": "not-a-number",
                },
                clear=False,
            ):
                import subprocess
                from pathlib import Path

                result = subprocess.run(
                    [
                        "python3",
                        str(SCRIPT),
                        "--base-url",
                        f"http://127.0.0.1:{server.server_port}/v1",
                        "--prompt",
                        "x",
                        "--timeout",
                        "5",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL status=403", result.stdout)
            self.assertNotIn("AkashaRechargeError", result.stdout)
            self.assertNotIn("not-a-number", result.stdout + result.stderr)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
