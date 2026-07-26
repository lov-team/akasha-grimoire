#!/usr/bin/env python3
"""No-network behavior tests for fish_audio.py."""

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


SCRIPT = Path(__file__).with_name("fish_audio.py")
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("fish_audio", SCRIPT)
assert SPEC and SPEC.loader
fish_audio = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fish_audio)


class _FishHandler(BaseHTTPRequestHandler):
    tts_payload: dict[str, object] | None = None
    stt_body = b""
    stt_content_type = ""

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        if self.headers.get("Authorization") != "Bearer local-test-key":
            self.send_error(401)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/gateway/v1/audio/speech":
            type(self).tts_payload = json.loads(body)
            response = b"fake-wave"
            content_type = "audio/wav"
        elif self.path == "/gateway/v1/audio/transcriptions":
            type(self).stt_body = body
            type(self).stt_content_type = self.headers.get("Content-Type", "")
            response = json.dumps({"text": "你好，世界。", "language": "zh"}).encode()
            content_type = "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


class FishAudioTests(unittest.TestCase):
    def setUp(self) -> None:
        _FishHandler.tts_payload = None
        _FishHandler.stt_body = b""
        _FishHandler.stt_content_type = ""
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FishHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/gateway/v1"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_base_url_normalization_and_sensitive_rejection(self) -> None:
        self.assertEqual(
            fish_audio._api_url("https://example.com", "/audio/speech"),
            "https://example.com/v1/audio/speech",
        )
        self.assertEqual(
            fish_audio._api_url("https://example.com/gateway/v1/", "/audio/speech"),
            "https://example.com/gateway/v1/audio/speech",
        )
        for value, secret in [
            ("https://user:password@example.com/v1", "password"),
            ("https://example.com/v1?token=secret", "secret"),
        ]:
            with self.assertRaises(SystemExit) as caught:
                fish_audio._api_url(value, "/audio/speech")
            self.assertNotIn(secret, str(caught.exception))

    def test_tts_with_reference_audio_saves_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"NEW_API_API_KEY": "local-test-key"}, clear=False
        ):
            reference = Path(temp_dir, "reference.wav")
            reference.write_bytes(b"reference-wave")
            output = Path(temp_dir, "voice.wav")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = fish_audio.main(
                    [
                        "--base-url",
                        self.base_url,
                        "tts",
                        "--text",
                        "欢迎回来",
                        "--reference-audio",
                        str(reference),
                        "--reference-text",
                        "参考语音",
                        "--format",
                        "wav",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertEqual(output.read_bytes(), b"fake-wave")
            self.assertIn("OK mode=tts", stdout.getvalue())
            payload = _FishHandler.tts_payload
            assert payload is not None
            self.assertEqual(payload["model"], "fish-s2-pro")
            self.assertEqual(payload["input"], "欢迎回来")
            references = payload["extra_body"]["references"]  # type: ignore[index]
            self.assertEqual(references[0]["text"], "参考语音")
            self.assertNotIn("reference-wave", stdout.getvalue())

    def test_stt_uploads_multipart_and_saves_text_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"NEW_API_API_KEY": "local-test-key"}, clear=False
        ):
            audio = Path(temp_dir, "recording.mp3")
            audio.write_bytes(b"fake-mp3")
            output = Path(temp_dir, "transcript.txt")
            json_output = Path(temp_dir, "transcript.json")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = fish_audio.main(
                    [
                        "--base-url",
                        self.base_url,
                        "stt",
                        str(audio),
                        "--language",
                        "zh",
                        "--output",
                        str(output),
                        "--json-output",
                        str(json_output),
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "你好，世界。")
            self.assertEqual(json.loads(json_output.read_text())["language"], "zh")
            self.assertIn("multipart/form-data; boundary=", _FishHandler.stt_content_type)
            self.assertIn(b' name="model"', _FishHandler.stt_body)
            self.assertIn(b"fish-transcribe-1", _FishHandler.stt_body)
            self.assertIn(b' name="language"', _FishHandler.stt_body)
            self.assertIn(b"fake-mp3", _FishHandler.stt_body)
            self.assertNotIn("你好，世界。", stdout.getvalue())

    def test_tts_json_response_is_not_reported_as_ok(self) -> None:
        request = mock.Mock()
        args = mock.Mock(
            model="fish-s2-pro",
            format="mp3",
            voice="voice-id",
            reference_audio=None,
            reference_text=None,
            text="hello",
            text_file=None,
            timeout_seconds=1,
            output="out.mp3",
            overwrite=False,
        )
        stdout = io.StringIO()
        with mock.patch.object(fish_audio, "_open_api_request", return_value=(b'{"error":"bad"}', "application/json")), mock.patch.object(
            fish_audio.urllib.request, "Request", return_value=request
        ), contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit):
            fish_audio._tts(args, "key", "https://example.com")
        self.assertNotIn("OK", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
