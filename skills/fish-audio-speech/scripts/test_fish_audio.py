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
    clone_body = b""
    clone_content_type = ""

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
        elif self.path == "/gateway/v1/audio/voice-models":
            type(self).clone_body = body
            type(self).clone_content_type = self.headers.get("Content-Type", "")
            response = json.dumps(
                {"_id": "private-voice-id", "title": "角色声线", "state": "trained"}
            ).encode()
            content_type = "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self) -> None:
        if self.headers.get("Authorization") != "Bearer local-test-key":
            self.send_error(401)
            return
        if self.path != "/gateway/v1/audio/voice-models/private-voice-id":
            self.send_error(404)
            return
        response = json.dumps({"_id": "private-voice-id", "state": "trained"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_DELETE(self) -> None:
        if self.headers.get("Authorization") != "Bearer local-test-key":
            self.send_error(401)
            return
        if self.path != "/gateway/v1/audio/voice-models/private-voice-id":
            self.send_error(404)
            return
        self.send_response(204)
        self.end_headers()


class FishAudioTests(unittest.TestCase):
    def setUp(self) -> None:
        _FishHandler.tts_payload = None
        _FishHandler.stt_body = b""
        _FishHandler.stt_content_type = ""
        _FishHandler.clone_body = b""
        _FishHandler.clone_content_type = ""
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

    def test_base_url_default_and_override_precedence(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(fish_audio._base_url(None), "https://newapi.1234bot.com/v1")
        with mock.patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://openai.example/v1",
                "NEW_API_BASE_URL": "https://new-api.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(fish_audio._base_url(None), "https://new-api.example/v1")
            self.assertEqual(
                fish_audio._base_url("https://cli.example/v1"),
                "https://cli.example/v1",
            )

    def test_missing_key_message_links_lovbrowser_and_payment_flow(self) -> None:
        message = fish_audio._missing_key_message()
        self.assertIn("https://lovbrowser.com", message)
        self.assertIn("QR code", message)
        self.assertIn("akasha_credentials.py finish", message)

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
            self.assertEqual(payload["model"], "fish-s2.1-pro")
            self.assertEqual(payload["input"], "欢迎回来")
            references = payload["extra_body"]["references"]  # type: ignore[index]
            self.assertEqual(references[0]["text"], "参考语音")
            self.assertNotIn("reference-wave", stdout.getvalue())

    def test_public_voice_search_filters_and_prints_reference_id_without_api_key(self) -> None:
        response = {
            "items": [
                {
                    "_id": "voice-good",
                    "type": "tts",
                    "title": "温暖旁白",
                    "description": "克制的人文纪录片男声",
                    "state": "trained",
                    "visibility": "public",
                    "dmca_taken_down": False,
                    "languages": ["zh"],
                    "tags": ["warm", "narration"],
                    "task_count": 4321,
                    "like_count": 88,
                },
                {
                    "_id": "voice-private",
                    "type": "tts",
                    "title": "不可用",
                    "state": "trained",
                    "visibility": "private",
                    "languages": ["zh"],
                    "tags": ["warm"],
                    "task_count": 9999,
                },
                {
                    "_id": "",
                    "type": "tts",
                    "title": "缺少标识",
                    "state": "trained",
                    "visibility": "public",
                    "languages": ["zh"],
                    "tags": ["warm"],
                    "task_count": 9999,
                },
            ]
        }
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            fish_audio, "_open_public_json", return_value=response
        ), contextlib.redirect_stdout(stdout):
            rc = fish_audio.main(
                ["voices", "--query", "旁白", "--tag", "warm", "--min-uses", "100"]
            )
        self.assertEqual(rc, 0)
        self.assertIn("reference_id=voice-good", stdout.getvalue())
        self.assertNotIn("voice-private", stdout.getvalue())
        self.assertNotIn("缺少标识", stdout.getvalue())

    def test_tts_with_public_reference_id_sends_voice_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"NEW_API_API_KEY": "local-test-key"}, clear=False
        ):
            output = Path(temp_dir, "smoke.wav")
            rc = fish_audio.main(
                [
                    "--base-url",
                    self.base_url,
                    "tts",
                    "--text",
                    "菲尔兹奖与脑类器官",
                    "--voice",
                    "public-reference-id",
                    "--format",
                    "wav",
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(rc, 0)
        assert _FishHandler.tts_payload is not None
        self.assertEqual(_FishHandler.tts_payload["voice"], "public-reference-id")
        self.assertNotIn("extra_body", _FishHandler.tts_payload)

    def test_tts_style_wraps_input_for_s2_1_natural_language_control(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"NEW_API_API_KEY": "local-test-key"}, clear=False
        ):
            output = Path(temp_dir, "styled.wav")
            rc = fish_audio.main(
                [
                    "--base-url",
                    self.base_url,
                    "tts",
                    "--text",
                    "规律一直都在那里。",
                    "--voice",
                    "private-reference-id",
                    "--style",
                    "warm and reflective",
                    "--format",
                    "wav",
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(rc, 0)
        assert _FishHandler.tts_payload is not None
        self.assertEqual(_FishHandler.tts_payload["model"], "fish-s2.1-pro")
        self.assertEqual(
            _FishHandler.tts_payload["input"],
            "[warm and reflective] 规律一直都在那里。",
        )

    def test_tts_style_rejects_nested_brackets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"NEW_API_API_KEY": "local-test-key"}, clear=False
        ), self.assertRaises(SystemExit) as caught:
            fish_audio.main(
                [
                    "--base-url",
                    self.base_url,
                    "tts",
                    "--text",
                    "test",
                    "--voice",
                    "voice-id",
                    "--style",
                    "[whispering]",
                    "--output",
                    str(Path(temp_dir, "bad.mp3")),
                ]
            )
        self.assertIn("bracket-free", str(caught.exception))

    def test_character_binding_resolves_to_reference_id_for_tts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"NEW_API_API_KEY": "local-test-key"}, clear=False
        ):
            registry = Path(temp_dir, "voices.json")
            rc = fish_audio.main(
                [
                    "bind",
                    "--character",
                    "守夜人",
                    "--voice",
                    "bound-reference-id",
                    "--registry",
                    str(registry),
                ]
            )
            self.assertEqual(rc, 0)
            output = Path(temp_dir, "line.wav")
            rc = fish_audio.main(
                [
                    "--base-url",
                    self.base_url,
                    "tts",
                    "--text",
                    "今夜由我守望。",
                    "--character",
                    "守夜人",
                    "--registry",
                    str(registry),
                    "--format",
                    "wav",
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(rc, 0)
        assert _FishHandler.tts_payload is not None
        self.assertEqual(_FishHandler.tts_payload["voice"], "bound-reference-id")

    def test_explicit_tts_model_overrides_character_binding_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"NEW_API_API_KEY": "local-test-key"}, clear=False
        ):
            registry = Path(temp_dir, "voices.json")
            fish_audio.main(
                [
                    "bind",
                    "--character",
                    "守夜人",
                    "--voice",
                    "bound-reference-id",
                    "--model",
                    "fish-s2-pro",
                    "--registry",
                    str(registry),
                ]
            )
            fish_audio.main(
                [
                    "--base-url",
                    self.base_url,
                    "tts",
                    "--text",
                    "今夜由我守望。",
                    "--character",
                    "守夜人",
                    "--registry",
                    str(registry),
                    "--model",
                    "fish-s1",
                    "--output",
                    str(Path(temp_dir, "line.mp3")),
                ]
            )
        assert _FishHandler.tts_payload is not None
        self.assertEqual(_FishHandler.tts_payload["model"], "fish-s1")

    def test_character_search_uses_character_name_as_title_query(self) -> None:
        with mock.patch.object(
            fish_audio,
            "_open_public_json",
            return_value={"items": []},
        ) as open_public:
            rc = fish_audio.main(["voices", "--character", "守夜人", "--language", "zh"])
        self.assertEqual(rc, 0)
        requested_url = open_public.call_args.args[0]
        self.assertIn("title=%E5%AE%88%E5%A4%9C%E4%BA%BA", requested_url)

    def test_clone_status_and_delete_use_new_api_voice_model_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ, {"NEW_API_API_KEY": "local-test-key"}, clear=False
        ):
            sample = Path(temp_dir, "sample.wav")
            sample.write_bytes(b"authorized-voice")
            metadata = Path(temp_dir, "voice.json")
            rc = fish_audio.main(
                [
                    "--base-url",
                    self.base_url,
                    "clone",
                    "--title",
                    "角色声线",
                    "--audio",
                    str(sample),
                    "--text",
                    "授权参考文本",
                    "--json-output",
                    str(metadata),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(metadata.read_text())["_id"], "private-voice-id")
            self.assertIn(b'name="model"', _FishHandler.clone_body)
            self.assertIn(b"fish-voice-clone-1", _FishHandler.clone_body)
            self.assertIn(b'name="visibility"', _FishHandler.clone_body)
            self.assertIn(b"private", _FishHandler.clone_body)
            self.assertIn(b"authorized-voice", _FishHandler.clone_body)

            rc = fish_audio.main(
                ["--base-url", self.base_url, "clone-status", "private-voice-id"]
            )
            self.assertEqual(rc, 0)
            rc = fish_audio.main(
                [
                    "--base-url",
                    self.base_url,
                    "clone-delete",
                    "private-voice-id",
                    "--confirm-delete",
                ]
            )
            self.assertEqual(rc, 0)

    def test_clone_delete_requires_explicit_confirmation(self) -> None:
        args = mock.Mock(reference_id="private-voice-id", confirm_delete=False, timeout_seconds=1)
        with mock.patch.object(fish_audio, "_open_api_request") as request, self.assertRaises(
            SystemExit
        ):
            fish_audio._delete_voice_model(args, "key", "https://example.com")
        request.assert_not_called()

    def test_clone_status_rejects_unknown_state(self) -> None:
        args = mock.Mock(
            reference_id="private-voice-id", timeout_seconds=1, json_output=None, overwrite=False
        )
        response = b'{"_id":"private-voice-id","state":"unknown"}'
        with mock.patch.object(
            fish_audio, "_open_api_request", return_value=(response, "application/json")
        ), self.assertRaises(SystemExit):
            fish_audio._voice_model_status(args, "key", "https://example.com")

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
            character=None,
            registry=None,
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

    def test_tts_json_body_with_binary_content_type_is_rejected(self) -> None:
        args = mock.Mock(
            model="fish-s2-pro",
            format="mp3",
            voice="voice-id",
            character=None,
            registry=None,
            reference_audio=None,
            reference_text=None,
            text="hello",
            text_file=None,
            timeout_seconds=1,
            output="out.mp3",
            overwrite=False,
        )
        with mock.patch.object(
            fish_audio,
            "_open_api_request",
            return_value=(b'{"error":"bad"}', "application/octet-stream"),
        ), self.assertRaises(SystemExit):
            fish_audio._tts(args, "key", "https://example.com")

    def test_loader_identity_and_controller_catches_quota_from_real_loader(self) -> None:
        a = fish_audio._load_akasha_recharge()
        b = fish_audio._load_akasha_recharge()
        self.assertIs(a, b)
        self.assertIs(a.InsufficientUserQuotaError, b.InsufficientUserQuotaError)
        body = (
            b'{"error":{"code":"insufficient_user_quota","metadata":'
            b'{"recharge":{"supported":true,"ticket_endpoint":"/v1/tooling/recharge-ticket"}}}}'
        )
        performed: list[int] = []

        def fake_perform(**kwargs: object) -> object:
            performed.append(1)
            return a.RechargeSessionView(
                public_id="f1",
                status="SUCCEEDED",
                face_value_usd_cent=1000,
                currency="USD",
                expire_time=0,
                public_page_url="https://lovbrowser.example/pay/f1",
                status_url="https://lovbrowser.example/status/f1",
            )

        controller = a.RechargeController(
            api_key="k",
            base_url="https://newapi.1234bot.com/v1",
            allow_http_endpoints=True,
        )
        n = {"v": 0}

        def op() -> str:
            n["v"] += 1
            if n["v"] == 1:
                fish_audio._load_akasha_recharge().raise_quota_if_applicable(
                    403, body, base_url="https://newapi.1234bot.com/v1"
                )
            return "ok"

        with mock.patch.object(a, "perform_recharge", side_effect=fake_perform):
            self.assertEqual(controller.run(op), "ok")
        self.assertEqual(performed, [1])
        self.assertTrue(controller._recharge_attempted)

    def test_recharge_usd_accepted_before_and_after_subcommand(self) -> None:
        parser = fish_audio._parser()
        a = parser.parse_args(
            ["--recharge-usd", "8", "tts", "--text", "hi", "--voice", "v1", "--output", "/tmp/a.wav"]
        )
        self.assertEqual(a.recharge_usd, "8")
        b = parser.parse_args(
            ["tts", "--recharge-usd", "9", "--text", "hi", "--voice", "v1", "--output", "/tmp/a.wav"]
        )
        self.assertEqual(b.recharge_usd, "9")

    def test_private_base_keeps_original_error_with_bad_recharge_env(self) -> None:
        with mock.patch.dict(os.environ, {"AKASHA_RECHARGE_USD": "bad-env", "NEW_API_API_KEY": "k"}, clear=False):
            # voices path does not use new-api; success path unaffected by bad env
            with mock.patch.object(
                fish_audio,
                "_open_public_json",
                return_value={"items": []},
            ):
                rc = fish_audio.main(["voices", "--query", "x", "--limit", "1"])
            self.assertEqual(rc, 0)
        # Authenticated request on private base: ordinary 403 stays ordinary
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002
                return

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(n)
                body = b'{"error":{"code":"rate_limit"}}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
                os.environ,
                {"NEW_API_API_KEY": "k", "AKASHA_RECHARGE_USD": "not-a-number"},
                clear=False,
            ):
                with self.assertRaises(SystemExit) as caught:
                    fish_audio.main(
                        [
                            "--base-url",
                            f"http://127.0.0.1:{server.server_port}/v1",
                            "tts",
                            "--text",
                            "hi",
                            "--voice",
                            "v1",
                            "--output",
                            f"{tmp}/o.wav",
                        ]
                    )
                self.assertIn("HTTP 403", str(caught.exception))
                self.assertNotIn("not-a-number", str(caught.exception))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_api_error_exposes_allowlisted_fields_without_metadata(self) -> None:
        from email.message import Message
        from io import BytesIO
        from urllib.error import HTTPError

        body = json.dumps(
            {
                "error": {
                    "code": "model_price_error",
                    "type": "new_api_error",
                    "message": "model needs pricing",
                    "metadata": {"api_key": "secret-key", "audio": "base64-payload"},
                }
            }
        ).encode()

        class FakeOpener:
            def open(self, req: object, timeout: float = 0) -> object:
                raise HTTPError(
                    "https://newapi.1234bot.com/v1/audio/speech",
                    400,
                    "Bad Request",
                    Message(),
                    BytesIO(body),
                )

        request = fish_audio.urllib.request.Request(
            "https://newapi.1234bot.com/v1/audio/speech",
            data=b"{}",
            method="POST",
        )
        with mock.patch.object(
            fish_audio.urllib.request, "build_opener", return_value=FakeOpener()
        ), self.assertRaises(SystemExit) as caught:
            fish_audio._open_api_request(
                request,
                5,
                base_url="https://newapi.1234bot.com/v1",
                api_key="key",
            )
        message = str(caught.exception)
        self.assertIn("code=model_price_error", message)
        self.assertIn("type=new_api_error", message)
        self.assertIn("message=model needs pricing", message)
        self.assertNotIn("secret-key", message)
        self.assertNotIn("base64-payload", message)


    def test_real_open_api_request_catches_quota_via_same_controller(self) -> None:
        from email.message import Message
        from io import BytesIO
        from urllib.error import HTTPError
        import urllib.request

        recharge = fish_audio._load_akasha_recharge()
        controller = recharge.RechargeController(
            api_key="k",
            base_url="https://newapi.1234bot.com/v1",
            allow_http_endpoints=True,
            request_timeout=5,
        )
        quota = json.dumps(
            {
                "error": {
                    "code": "insufficient_user_quota",
                    "metadata": {
                        "recharge": {
                            "supported": True,
                            "ticket_endpoint": "/v1/tooling/recharge-ticket",
                        }
                    },
                }
            }
        ).encode()
        ok = b"audio-bytes"
        state = {"n": 0}

        class FakeOpener:
            def open(self, req: object, timeout: float = 0) -> object:
                state["n"] += 1
                if state["n"] == 1:
                    raise HTTPError("https://newapi.1234bot.com/v1/x", 403, "Forbidden", Message(), BytesIO(quota))
                class Resp:
                    def __enter__(self):
                        return self
                    def __exit__(self, *args: object) -> bool:
                        return False
                    def read(self) -> bytes:
                        return ok
                    headers = {"Content-Type": "audio/wav"}
                return Resp()

        performed: list[int] = []

        def fake_perform(**kwargs: object) -> object:
            performed.append(1)
            return recharge.RechargeSessionView(
                public_id="w1",
                status="SUCCEEDED",
                face_value_usd_cent=1000,
                currency="USD",
                expire_time=0,
                public_page_url="https://lovbrowser.example/pay/w1",
                status_url="https://lovbrowser.example/status/w1",
            )

        req = urllib.request.Request(
            "https://newapi.1234bot.com/v1/audio/speech",
            data=b"{}",
            headers={"Authorization": "Bearer k", "Content-Type": "application/json"},
            method="POST",
        )
        with mock.patch.object(recharge, "perform_recharge", side_effect=fake_perform):
            with mock.patch.object(urllib.request, "build_opener", return_value=FakeOpener()):
                body, ct = fish_audio._open_api_request(
                    req, 5, base_url="https://newapi.1234bot.com/v1", api_key="k", controller=controller
                )
        self.assertEqual(body, ok)
        self.assertEqual(performed, [1])
        self.assertTrue(controller._recharge_attempted)


if __name__ == "__main__":
    unittest.main()
