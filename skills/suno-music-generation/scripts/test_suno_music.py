#!/usr/bin/env python3
"""No-network behavior tests for suno_music.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("suno_music.py")
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("suno_music", SCRIPT)
assert SPEC and SPEC.loader
suno_music = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suno_music)


class _SunoHandler(BaseHTTPRequestHandler):
    polls = 0
    payload: dict[str, object] | None = None

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, data: dict[str, object]) -> None:
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/gateway/suno/submit/MUSIC":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != "Bearer local-test-key":
            self.send_error(401)
            return
        length = int(self.headers.get("Content-Length", "0"))
        type(self).payload = json.loads(self.rfile.read(length))
        self._json({"code": "success", "data": "task_public"})

    def do_GET(self) -> None:
        if self.path == "/gateway/suno/fetch/task_public":
            type(self).polls += 1
            if type(self).polls == 1:
                self._json({"code": "success", "data": {"status": "IN_PROGRESS"}})
                return
            host = f"http://127.0.0.1:{self.server.server_port}"
            self._json(
                {
                    "code": "success",
                    "data": {
                        "status": "SUCCESS",
                        "data": [
                            {
                                "audio_url": f"{host}/files/song.mp3?signature=secret",
                                "image_url": f"{host}/files/cover.jpg?signature=secret",
                            }
                        ],
                    },
                }
            )
            return
        if self.path.startswith("/files/song.mp3"):
            body = b"fake-mp3"
            content_type = "audio/mpeg"
        elif self.path.startswith("/files/cover.jpg"):
            body = b"fake-jpeg"
            content_type = "image/jpeg"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SunoMusicTests(unittest.TestCase):
    def test_base_url_normalization_and_sensitive_rejection(self) -> None:
        self.assertEqual(
            suno_music._api_url("https://example.com", "/suno/submit/MUSIC"),
            "https://example.com/suno/submit/MUSIC",
        )
        self.assertEqual(
            suno_music._api_url("https://example.com/gateway/v1/", "/suno/submit/MUSIC"),
            "https://example.com/gateway/suno/submit/MUSIC",
        )
        for value, secret in [
            ("https://user:password@example.com/v1", "password"),
            ("https://example.com/v1?token=secret", "secret"),
        ]:
            with self.assertRaises(SystemExit) as caught:
                suno_music._api_url(value, "/suno/submit/MUSIC")
            self.assertNotIn(secret, str(caught.exception))

    def test_submit_wait_and_download_stay_quiet_until_success(self) -> None:
        _SunoHandler.polls = 0
        _SunoHandler.payload = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), _SunoHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
                os.environ,
                {"NEW_API_API_KEY": "local-test-key", "NEW_API_BASE_URL": ""},
                clear=False,
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    rc = suno_music.main(
                        [
                            "--description",
                            "warm acoustic city folk",
                            "--base-url",
                            f"http://127.0.0.1:{server.server_port}/gateway/v1",
                            "--output-dir",
                            temp_dir,
                            "--poll-seconds",
                            "0.01",
                            "--timeout-seconds",
                            "2",
                        ]
                    )
                self.assertEqual(rc, 0)
                output = stdout.getvalue()
                self.assertTrue(output.startswith("OK task_id=task_public songs=1 files=2\n"))
                self.assertNotIn("signature=secret", output)
                self.assertNotIn("IN_PROGRESS", output)
                self.assertEqual(Path(temp_dir, "suno-song-1.mp3").read_bytes(), b"fake-mp3")
                self.assertEqual(Path(temp_dir, "suno-song-1-cover.jpg").read_bytes(), b"fake-jpeg")
                self.assertEqual(
                    _SunoHandler.payload,
                    {
                        "make_instrumental": False,
                        "gpt_description_prompt": "warm acoustic city folk",
                    },
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_malformed_success_has_no_ok_output(self) -> None:
        responses = [
            {"code": "success", "data": {"status": "SUCCESS", "data": []}}
        ]
        stdout = io.StringIO()
        with mock.patch.object(suno_music, "_request_json", side_effect=responses):
            with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit):
                suno_music._wait_for_result("task", "key", "https://example.com", 1, 0.01)
        self.assertNotIn("OK", stdout.getvalue())

    def test_non_http_result_url_is_rejected_without_reading_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir, "secret.txt")
            source.write_text("sensitive", encoding="utf-8")
            destination = Path(temp_dir, "out.mp3")
            with self.assertRaises(SystemExit):
                suno_music._download(source.as_uri(), destination, False)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
