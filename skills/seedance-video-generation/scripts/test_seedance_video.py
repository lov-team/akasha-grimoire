#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("seedance_video.py")
MP4 = b"\x00\x00\x00\x18ftypisomfixture"

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("seedance_video_under_test", SCRIPT)
assert SPEC and SPEC.loader
SEEDANCE_VIDEO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEEDANCE_VIDEO)


class Handler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, bytes]] = []

    def log_message(self, *_args: object) -> None:
        pass

    def send_json(self, value: dict) -> None:
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.requests.append((self.command, self.path, body))
        self.send_json({"id": "task-seedance-123", "status": "queued"})

    def do_GET(self) -> None:
        self.requests.append((self.command, self.path, b""))
        if self.path == "/v1/video/generations/task-seedance-123":
            self.send_json({"code": "success", "data": {"task_id": "task-seedance-123", "status": "SUCCESS"}})
        elif self.path == "/v1/videos/task-seedance-123/content":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(MP4)))
            self.end_headers()
            self.wfile.write(MP4)
        else:
            self.send_response(404)
            self.end_headers()


class SeedanceVideoScriptTest(unittest.TestCase):
    def test_base_url_default_and_override_precedence(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                SEEDANCE_VIDEO.resolve_base_url(None),
                "https://newapi.1234bot.com/v1",
            )
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/v1",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(
                SEEDANCE_VIDEO.resolve_base_url(None),
                "https://new-api.example/v1",
            )
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/v1",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
                "SEEDANCE_VIDEO_BASE_URL": "https://seedance.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(
                SEEDANCE_VIDEO.resolve_base_url(None),
                "https://seedance.example/v1",
            )
            self.assertEqual(
                SEEDANCE_VIDEO.resolve_base_url("https://cli.example/custom"),
                "https://cli.example/custom/v1",
            )

    def test_missing_key_message_links_lovbrowser_and_payment_flow(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(
            SEEDANCE_VIDEO.SeedanceVideoError
        ) as caught:
            SEEDANCE_VIDEO.read_api_key()
        message = str(caught.exception)
        self.assertIn("https://lovbrowser.com", message)
        self.assertIn("payment", message)
        self.assertIn("NEW_API_API_KEY", message)

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join()

    def setUp(self) -> None:
        Handler.requests.clear()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["SEEDANCE_VIDEO_API_KEY"] = "test-key"
        return subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--timeout", "5", *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_generate_preserves_references_and_downloads_completed_video(self) -> None:
        output = Path(self.temp_dir.name) / "result.mp4"
        result = self.invoke(
            "generate",
            "--prompt", "wave to camera",
            "--duration", "10",
            "--first-frame", "https://media.example/first.png",
            "--reference-video", "https://media.example/reference.mp4",
            "--no-generate-audio",
            "--poll-interval", "0.01",
            "--output", str(output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_bytes(), MP4)
        method, path, body = Handler.requests[0]
        self.assertEqual((method, path), ("POST", "/v1/video/generations"))
        payload = json.loads(body)
        self.assertEqual(payload["duration"], 10)
        self.assertEqual(payload["metadata"]["duration"], 10)
        self.assertFalse(payload["metadata"]["generate_audio"])
        self.assertEqual(payload["metadata"]["content"][0]["role"], "first_frame")
        self.assertEqual(payload["metadata"]["content"][1]["type"], "video_url")
        self.assertEqual(payload["metadata"]["content"][1]["role"], "reference_video")

    def test_seedance_1_pro_uses_ark_model_and_twelve_second_limit(self) -> None:
        output = Path(self.temp_dir.name) / "pro.mp4"
        result = self.invoke(
            "generate",
            "--model", "seedance-1.0-pro",
            "--prompt", "camera pans across a garden",
            "--duration", "12",
            "--poll-interval", "0.01",
            "--output", str(output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(Handler.requests[0][2])
        self.assertEqual(payload["model"], "doubao-seedance-1-0-pro-250528")
        self.assertFalse(payload["metadata"]["generate_audio"])

    def test_seedance_1_lite_alias_selects_t2v_or_i2v(self) -> None:
        text_output = Path(self.temp_dir.name) / "lite-text.mp4"
        text_result = self.invoke(
            "generate",
            "--model", "seedance-1.0-lite",
            "--prompt", "clouds move over a lake",
            "--poll-interval", "0.01",
            "--output", str(text_output),
        )
        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        text_payload = json.loads(Handler.requests[0][2])
        self.assertEqual(text_payload["model"], "doubao-seedance-1-0-lite-t2v-250428")

        Handler.requests.clear()
        image_output = Path(self.temp_dir.name) / "lite-image.mp4"
        image_result = self.invoke(
            "generate",
            "--model", "seedance-1.0-lite",
            "--prompt", "the character waves",
            "--first-frame", "https://media.example/character.png",
            "--poll-interval", "0.01",
            "--output", str(image_output),
        )
        self.assertEqual(image_result.returncode, 0, image_result.stderr)
        image_payload = json.loads(Handler.requests[0][2])
        self.assertEqual(image_payload["model"], "doubao-seedance-1-0-lite-i2v-250428")

    def test_rejects_unsupported_seedance_1_inputs_before_request(self) -> None:
        output = Path(self.temp_dir.name) / "invalid.mp4"
        result = self.invoke(
            "generate",
            "--model", "seedance-1.5-pro",
            "--prompt", "wave",
            "--reference-video", "https://media.example/reference.mp4",
            "--output", str(output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not accept video or audio references", result.stderr)
        self.assertFalse(Handler.requests)
        self.assertFalse(output.exists())

    def test_seedance_1_5_enables_native_audio_generation(self) -> None:
        output = Path(self.temp_dir.name) / "seedance-15.mp4"
        result = self.invoke(
            "generate",
            "--model", "doubao-seedance-1-5-pro-251215",
            "--prompt", "a singer performs on stage",
            "--poll-interval", "0.01",
            "--output", str(output),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(Handler.requests[0][2])
        self.assertTrue(payload["metadata"]["generate_audio"])

    def test_explicit_lite_modes_validate_image_input(self) -> None:
        output = Path(self.temp_dir.name) / "invalid-lite.mp4"
        i2v_result = self.invoke(
            "generate",
            "--model", "doubao-seedance-1-0-lite-i2v-250428",
            "--prompt", "wave",
            "--output", str(output),
        )
        self.assertNotEqual(i2v_result.returncode, 0)
        self.assertIn("requires an image reference", i2v_result.stderr)

        t2v_result = self.invoke(
            "generate",
            "--model", "doubao-seedance-1-0-lite-t2v-250428",
            "--prompt", "wave",
            "--first-frame", "https://media.example/character.png",
            "--output", str(output),
        )
        self.assertNotEqual(t2v_result.returncode, 0)
        self.assertIn("does not accept image references", t2v_result.stderr)
        self.assertFalse(Handler.requests)
        self.assertFalse(output.exists())

    def test_rejects_duration_above_model_limit_before_request(self) -> None:
        output = Path(self.temp_dir.name) / "too-long.mp4"
        result = self.invoke(
            "generate",
            "--model", "seedance-1.0-pro",
            "--prompt", "wave",
            "--duration", "13",
            "--output", str(output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("between 4 and 12 seconds", result.stderr)
        self.assertFalse(Handler.requests)
        self.assertFalse(output.exists())

    def test_rejects_non_https_reference_before_request(self) -> None:
        output = Path(self.temp_dir.name) / "result.mp4"
        result = self.invoke(
            "generate",
            "--prompt", "wave",
            "--first-frame", "http://media.example/first.png",
            "--output", str(output),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(Handler.requests)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
