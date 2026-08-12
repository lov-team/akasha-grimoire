#!/usr/bin/env python3
"""Local-only contract tests for shared Akasha device credentials."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("akasha_credentials.py")
SPEC = importlib.util.spec_from_file_location("akasha_credentials_tested", MODULE_PATH)
assert SPEC and SPEC.loader
credentials = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = credentials
SPEC.loader.exec_module(credentials)

DEVICE_CODE = "D" * 43
API_KEY = "fixture-key-never-print"


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    token_steps = ["authorization_pending", "slow_down", "success"]
    requests: list[tuple[str, dict, dict]] = []

    def log_message(self, _format, *_args):
        return

    def _json(self, status: int, payload: dict) -> None:
        payload = {**payload, "timestamp": 1_786_265_286_488}
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = json.loads(raw or b"{}")
        type(self).requests.append((self.path, body, dict(self.headers)))
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == credentials.START_PATH:
            self._json(200, {"code": 200, "message": "success", "data": {
                "version": credentials.VERSION, "deviceCode": DEVICE_CODE,
                "userCode": "ABCD-EFGH", "verificationUri": origin + "/akasha/device",
                "verificationUriComplete": origin + "/akasha/device?user_code=ABCD-EFGH",
                "expiresIn": 600, "interval": 5,
            }})
            return
        if self.path == credentials.TOKEN_PATH:
            step = type(self).token_steps.pop(0)
            if step != "success":
                self._json(400, {"code": 400, "message": "wait", "data": {"error": step}})
                return
            self._json(200, {"code": 200, "message": "success", "data": {
                "version": credentials.VERSION, "origin": origin, "apiKey": API_KEY,
                "baseUrl": origin + "/v1", "account_flow": "existing_login",
            }})
            return
        self._json(404, {"data": {"error": "invalid_request"}})

    def do_GET(self):
        type(self).requests.append((self.path, {}, dict(self.headers)))
        if self.path == "/v1/models" and self.headers.get("Authorization") == f"Bearer {API_KEY}":
            self._json(200, {"object": "list", "data": []})
            return
        self._json(401, {"error": {"message": "bad auth"}})


@contextlib.contextmanager
def fixture_server():
    FixtureHandler.requests = []
    FixtureHandler.token_steps = ["authorization_pending", "slow_down", "success"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


class CredentialDiscoveryTests(unittest.TestCase):
    def setUp(self):
        credentials._ACTIVE_CREDENTIAL = None
        credentials._VALIDATED_CREDENTIALS.clear()

    def test_priority_openai_new_file_and_ignores_media_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"AKASHA_CONFIG_DIR": tmp, "SPECIAL_KEY": "special", "LOVBROWSER_API_KEY": "new", "OPENAI_API_KEY": "openai"}
            self.assertEqual(credentials.discover_credential(environ=env).api_key, "openai")
            env.pop("OPENAI_API_KEY")
            self.assertEqual(credentials.discover_credential(environ=env).api_key, "new")
            env.pop("LOVBROWSER_API_KEY")
            credentials.save_credential("stored", credentials.OFFICIAL_NEWAPI_BASE_URL, environ=env)
            self.assertEqual(credentials.discover_credential(environ=env).api_key, "stored")

    def test_media_specific_key_is_never_a_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "AKASHA_CONFIG_DIR": tmp,
                "IMAGE_PROXY_API_KEY": "media-only",
                "GROK_MEDIA_API_KEY": "media-only",
            }
            self.assertIsNone(credentials.discover_credential(environ=env))
            self.assertEqual(credentials.credential_candidates(environ=env), ())

    def test_atomic_backup_permissions_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"AKASHA_CONFIG_DIR": tmp}
            path = credentials.save_credential("old", credentials.OFFICIAL_NEWAPI_BASE_URL, environ=env)
            credentials.save_credential("new", credentials.OFFICIAL_NEWAPI_BASE_URL, environ=env)
            self.assertEqual(stat.S_IMODE(Path(tmp).stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotIn("old", path.read_text())
            self.assertTrue(credentials.rollback(environ=env))
            self.assertIn("old", path.read_text())

    def test_runtime_candidates_try_local_openai_before_configured_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "AKASHA_CONFIG_DIR": tmp,
                "LOVBROWSER_API_KEY": "new",
                "OPENAI_API_KEY": "openai",
                "OPENAI_BASE_URL": "https://openai.example/v1",
            }
            candidates = credentials.credential_candidates(
                base_url="https://skill.example/v1",
                environ=env,
            )
            self.assertEqual(
                [
                    (candidate.api_key, candidate.base_url, candidate.source)
                    for candidate in candidates
                ],
                [
                    ("openai", "https://skill.example/v1", "env:OPENAI_API_KEY"),
                    ("new", "https://skill.example/v1", "env:LOVBROWSER_API_KEY"),
                ],
            )

    def test_unreachable_local_openai_falls_back_to_configured_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "AKASHA_CONFIG_DIR": tmp,
                "LOVBROWSER_API_KEY": "configured",
                "OPENAI_API_KEY": "local-openai",
                "OPENAI_BASE_URL": "https://openai.example/v1",
            }
            attempts: list[tuple[str, str]] = []

            def probe(api_key: str, base_url: str, **_kwargs):
                attempts.append((api_key, base_url))
                if api_key == "local-openai":
                    raise credentials.CredentialError("fixture unavailable")

            with mock.patch.object(credentials, "validate_credential", side_effect=probe):
                found = credentials.resolve_usable_credential(
                    base_url="https://skill.example/v1", environ=env
                )
            self.assertEqual(found.api_key, "configured")
            self.assertEqual(attempts, [
                ("local-openai", "https://skill.example/v1"),
                ("configured", "https://skill.example/v1"),
            ])

    def test_local_openai_key_ignores_openai_base_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "AKASHA_CONFIG_DIR": tmp,
                "LOVBROWSER_API_KEY": "configured",
                "NEW_API_BASE_URL": "https://configured.example/v1",
                "OPENAI_API_KEY": "local-openai",
                "OPENAI_BASE_URL": "https://openai.example/v1",
            }
            with mock.patch.object(credentials, "validate_credential"):
                found = credentials.bootstrap(
                    base_url="https://skill.example/v1", environ=env
                )
            self.assertEqual(found.source, "env:OPENAI_API_KEY")
            self.assertEqual(found.base_url, "https://skill.example/v1")
            self.assertEqual(
                credentials.resolve_base_url(environ=env),
                "https://configured.example/v1",
            )
            self.assertEqual(
                credentials.resolve_base_url(
                    explicit="https://command.example/v1", environ=env
                ),
                "https://command.example/v1",
            )

    def test_all_configured_candidates_failing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "AKASHA_CONFIG_DIR": tmp,
                "LOVBROWSER_API_KEY": "configured",
                "OPENAI_API_KEY": "local-openai",
            }
            with mock.patch.object(
                credentials,
                "validate_credential",
                side_effect=credentials.CredentialError("fixture unavailable"),
            ):
                self.assertIsNone(credentials.resolve_usable_credential(environ=env))

    def test_working_local_openai_skips_configured_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "AKASHA_CONFIG_DIR": tmp,
                "LOVBROWSER_API_KEY": "configured",
                "OPENAI_API_KEY": "local-openai",
                "OPENAI_BASE_URL": "https://openai.example/v1",
            }
            attempts: list[str] = []

            def probe(api_key: str, _base_url: str, **_kwargs):
                attempts.append(api_key)

            with mock.patch.object(credentials, "validate_credential", side_effect=probe):
                found = credentials.resolve_usable_credential(
                    base_url="https://skill.example/v1", environ=env
                )
            self.assertEqual(found.api_key, "local-openai")
            self.assertEqual(found.base_url, "https://skill.example/v1")
            self.assertEqual(attempts, ["local-openai"])

    def test_explicit_base_probes_selected_key_at_that_base(self):
        with tempfile.TemporaryDirectory() as tmp, fixture_server() as origin:
            env = {
                "AKASHA_CONFIG_DIR": tmp,
                "LOVBROWSER_API_KEY": API_KEY,
                "AKASHA_ALLOW_TEST_HTTP": "1",
            }
            found = credentials.select_credential(
                explicit_base_url=origin + "/v1",
                environ=env,
            )
            self.assertEqual(found.api_key, API_KEY)
            self.assertEqual(found.base_url, origin + "/v1")
            self.assertEqual(
                credentials.resolve_base_url(environ=env),
                credentials.OFFICIAL_NEWAPI_BASE_URL,
            )

    def test_concurrent_writes_remain_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"AKASHA_CONFIG_DIR": tmp}
            threads = [threading.Thread(target=credentials.save_credential, args=(f"key-{i}", credentials.OFFICIAL_NEWAPI_BASE_URL), kwargs={"environ": env}) for i in range(12)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            found = credentials.discover_credential(environ=env)
            self.assertRegex(found.api_key, r"^key-\d+$")

    def test_rejects_permissive_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "credentials.env")
            path.write_text("LOVBROWSER_API_KEY=x\n")
            path.chmod(0o644)
            with self.assertRaisesRegex(credentials.CredentialError, "0600"):
                credentials.discover_credential(environ={"AKASHA_CONFIG_DIR": tmp})


class DeviceFlowTests(unittest.TestCase):
    def setUp(self):
        credentials._ACTIVE_CREDENTIAL = None
        credentials._VALIDATED_CREDENTIALS.clear()

    def test_standard_api_response_timestamp_is_accepted(self):
        payload = {
            "code": 200,
            "message": "success",
            "data": {"version": credentials.VERSION},
            "timestamp": 1_786_265_286_488,
        }
        data, error = credentials._envelope(
            200, payload, {"Cache-Control": "no-store"}
        )
        self.assertEqual(data, {"version": credentials.VERSION})
        self.assertIsNone(error)

    def test_http_403_access_denied_remains_a_protocol_error_code(self):
        payload = {
            "code": 403,
            "message": "denied",
            "data": {"error": "access_denied"},
            "timestamp": 1_786_265_286_488,
        }
        data, error = credentials._envelope(
            403, payload, {"Cache-Control": "no-store"}
        )
        self.assertIsNone(data)
        self.assertEqual(error, "access_denied")

    def test_unknown_envelope_fields_are_still_rejected(self):
        payload = {
            "code": 200,
            "message": "success",
            "data": {},
            "unexpected": "field",
        }
        with self.assertRaisesRegex(credentials.CredentialError, "invalid envelope"):
            credentials._envelope(200, payload, {"Cache-Control": "no-store"})

    def test_start_poll_validate_save_and_no_output_leak(self):
        with tempfile.TemporaryDirectory() as tmp, fixture_server() as origin:
            env = {"AKASHA_CONFIG_DIR": tmp}
            started = credentials.start_device_flow(origin=origin, environ=env, allow_test_http=True)
            self.assertEqual(started.user_code, "ABCD-EFGH")
            self.assertTrue(started.qr_png_path.is_absolute())
            self.assertEqual(started.qr_png_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertGreater(started.qr_png_path.stat().st_size, 100)
            self.assertEqual(stat.S_IMODE(started.qr_png_path.stat().st_mode), 0o600)
            state = credentials.state_path(env)
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
            sleeps: list[float] = []
            result = credentials.finish_device_flow(environ=env, sleep=sleeps.append)
            self.assertEqual(sleeps, [5, 5, 10])
            self.assertEqual(result.account_flow, "existing_login")
            self.assertFalse(state.exists())
            stored = credentials.credentials_path(env)
            self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)
            self.assertIn(API_KEY, stored.read_text())
            models = [entry for entry in FixtureHandler.requests if entry[0] == "/v1/models"]
            self.assertEqual(len(models), 1)

    def test_events_do_not_include_device_secret_or_key(self):
        fake_start = credentials.DeviceStart("ABCD-EFGH", "https://lovbrowser.com/akasha/device?user_code=ABCD-EFGH", Path("/tmp/akasha-device.png"), 600, 5)
        fake_result = credentials.DeviceResult(credentials.Credential(API_KEY, credentials.OFFICIAL_NEWAPI_BASE_URL, "akasha-device"), "existing_login")
        output = io.StringIO()
        with mock.patch.object(credentials, "resolve_usable_credential", return_value=None), mock.patch.object(credentials, "start_device_flow", return_value=fake_start), mock.patch.object(credentials, "finish_device_flow", return_value=fake_result):
            credentials.bootstrap(event_file=output)
        rendered = output.getvalue()
        self.assertNotIn(API_KEY, rendered)
        self.assertNotIn(DEVICE_CODE, rendered)
        self.assertIn("ABCD-EFGH", rendered)

    def test_bootstrap_guides_after_local_and_configured_keys_fail(self):
        fake_start = credentials.DeviceStart("ABCD-EFGH", "https://lovbrowser.com/akasha/device?user_code=ABCD-EFGH", Path("/tmp/akasha-device.png"), 600, 5)
        fake_result = credentials.DeviceResult(credentials.Credential(API_KEY, credentials.OFFICIAL_NEWAPI_BASE_URL, "akasha-device"), "existing_login")
        output = io.StringIO()
        with mock.patch.object(credentials, "resolve_usable_credential", return_value=None) as resolve, mock.patch.object(credentials, "start_device_flow", return_value=fake_start) as start, mock.patch.object(credentials, "finish_device_flow", return_value=fake_result):
            result = credentials.bootstrap(event_file=output)
        self.assertEqual(result, fake_result.credential)
        resolve.assert_called_once_with(base_url=None, environ=None)
        start.assert_called_once_with(environ=None)
        self.assertIn("verificationUriComplete", output.getvalue())

    def test_expired_state_is_cleaned(self):
        with tempfile.TemporaryDirectory() as tmp, fixture_server() as origin:
            env = {"AKASHA_CONFIG_DIR": tmp}
            credentials.start_device_flow(origin=origin, environ=env, allow_test_http=True, now=lambda: 10)
            with self.assertRaisesRegex(credentials.CredentialError, "expired"):
                credentials.finish_device_flow(environ=env, now=lambda: 700)
            self.assertFalse(credentials.state_path(env).exists())

    def test_validation_failure_preserves_existing_credential(self):
        with tempfile.TemporaryDirectory() as tmp, fixture_server() as origin:
            env = {"AKASHA_CONFIG_DIR": tmp}
            path = credentials.save_credential(
                "known-good", credentials.OFFICIAL_NEWAPI_BASE_URL, environ=env
            )
            credentials.start_device_flow(
                origin=origin, environ=env, allow_test_http=True
            )
            FixtureHandler.token_steps = ["success"]
            with mock.patch.object(
                credentials,
                "validate_credential",
                side_effect=credentials.CredentialError("fixture validation failed"),
            ), self.assertRaisesRegex(credentials.CredentialError, "fixture validation failed"):
                credentials.finish_device_flow(environ=env, sleep=lambda _seconds: None)
            self.assertIn("known-good", path.read_text())
            self.assertTrue(credentials.state_path(env).exists())

    def test_redirect_is_rejected_without_following(self):
        request = urllib.request.Request("https://lovbrowser.com/start")
        error = urllib.error.HTTPError(request.full_url, 302, "redirect", {"Location": "https://evil.invalid"}, io.BytesIO(b"{}"))
        with self.assertRaisesRegex(credentials.CredentialError, "redirect"):
            credentials._http_json("POST", request.full_url, {}, timeout=1, urlopen=lambda *_a, **_k: (_ for _ in ()).throw(error))

    def test_official_allowlist_rejects_injection(self):
        for origin in ("http://lovbrowser.com", "https://user@lovbrowser.com", "https://lovbrowser.com.evil.invalid", "https://lovbrowser.com?next=evil"):
            with self.subTest(origin=origin), self.assertRaises(credentials.CredentialError):
                credentials._endpoint(origin, credentials.START_PATH, allow_test_http=False)


class MediaIntegrationTests(unittest.TestCase):
    def setUp(self):
        credentials._ACTIVE_CREDENTIAL = None
        credentials._VALIDATED_CREDENTIALS.clear()

    def test_all_six_media_entries_use_the_shared_bootstrap(self):
        root = Path(__file__).resolve().parents[1]
        cases = [
            ("gpt_image_bootstrap_test", root / "skills/gpt-image-generation/scripts/generate_openai_image.py", "_api_key"),
            ("grok_bootstrap_test", root / "skills/grok-media-generation/scripts/grok_media.py", "read_api_key"),
            ("seedance_bootstrap_test", root / "skills/seedance-video-generation/scripts/seedance_video.py", "read_api_key"),
            ("h3_kling_video_bootstrap_test", root / "skills/h3-kling-video-generation/scripts/video_generation.py", "read_api_key"),
            ("fish_bootstrap_test", root / "skills/fish-audio-speech/scripts/fish_audio.py", "_api_key"),
            ("suno_bootstrap_test", root / "skills/suno-music-generation/scripts/suno_music.py", "_api_key"),
        ]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"AKASHA_CONFIG_DIR": tmp}, clear=True
        ):
            for module_name, script, function_name in cases:
                with self.subTest(script=script.parent.parent.name):
                    spec = importlib.util.spec_from_file_location(module_name, script)
                    self.assertIsNotNone(spec)
                    self.assertIsNotNone(spec.loader)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    recharge = module._load_akasha_recharge()
                    shared = recharge.load_akasha_credentials_module(script)
                    fixture = shared.Credential("media-fixture-key", shared.OFFICIAL_NEWAPI_BASE_URL, "fixture")
                    with mock.patch.object(shared, "bootstrap", return_value=fixture) as start:
                        self.assertEqual(getattr(module, function_name)(), "media-fixture-key")
                    start.assert_called_once_with(
                        base_url=None,
                        environ=None,
                        event_file=None,
                    )


if __name__ == "__main__":
    unittest.main()
