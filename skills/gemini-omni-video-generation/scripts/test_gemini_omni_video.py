#!/usr/bin/env python3

from __future__ import annotations

import argparse
import email.message
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).with_name("gemini_omni_video.py")
SPEC = importlib.util.spec_from_file_location("gemini_omni_video", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "model": "gemini-omni-video",
        "prompt": "a blue sphere",
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "generate_audio": False,
        "duration": 4,
        "start": 0.0,
        "end": 4.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class GeminiOmniVideoTest(unittest.TestCase):
    def test_shared_key_and_skill_url_ignore_openai_url_and_media_key(self) -> None:
        credential = type("Credential", (), {"api_key": "shared-key"})()
        credentials = type(
            "Credentials",
            (),
            {
                "CredentialError": RuntimeError,
                "select_credential": staticmethod(lambda **_kwargs: credential),
            },
        )()
        recharge = type(
            "Recharge",
            (),
            {"load_akasha_credentials_module": staticmethod(lambda _path: credentials)},
        )()
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "local-openai",
                "LOVBROWSER_API_KEY": "lovbrowser",
                "GEMINI_OMNI_VIDEO_API_KEY": "media-key",
                "OPENAI_BASE_URL": "https://openai.example/v1",
            },
            clear=True,
        ), patch.object(MODULE, "_load_akasha_recharge", return_value=recharge):
            self.assertEqual(MODULE.read_api_key(), "shared-key")
            self.assertEqual(MODULE.resolve_base_url(None), MODULE.DEFAULT_BASE_URL)
        with patch.dict(
            os.environ,
            {"LOVBROWSER_API_KEY": "lovbrowser", "GEMINI_OMNI_VIDEO_API_KEY": "media-key"},
            clear=True,
        ), patch.object(MODULE, "_load_akasha_recharge", return_value=recharge):
            self.assertEqual(MODULE.read_api_key(), "shared-key")

    def test_normalize_base_url(self) -> None:
        self.assertEqual(MODULE.normalize_base_url("https://example.com"), "https://example.com/v1")
        self.assertEqual(MODULE.normalize_base_url("https://example.com/v1/"), "https://example.com/v1")
        with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, "userinfo"):
            MODULE.normalize_base_url("https://user:pass@example.com")

    def test_generation_payload_uses_async_gemini_contract(self) -> None:
        payload = MODULE.build_payload(args(duration=8, resolution="1080p"))

        self.assertEqual(payload["model"], "gemini-omni-video")
        self.assertEqual(payload["seconds"], "8")
        self.assertEqual(payload["size"], "1080p")
        self.assertEqual(payload["metadata"]["duration"], "8")
        self.assertFalse(payload["metadata"]["generate_audio"])

    def test_edit_payload_uses_one_official_video_list_item(self) -> None:
        payload = MODULE.build_payload(args(start=1.0, end=7.0), "https://media.example/input.mp4")

        self.assertNotIn("seconds", payload)
        self.assertEqual(
            payload["metadata"]["video_list"],
            [{"url": "https://media.example/input.mp4", "start": 1.0, "ends": 7.0}],
        )

    def test_edit_rejects_reference_clip_over_ten_seconds(self) -> None:
        with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, "0 <= start < end <= 10"):
            MODULE.build_payload(args(start=0.0, end=11.0), "https://media.example/input.mp4")

        with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, "0 <= start < end <= 10"):
            MODULE.build_payload(args(start=float("nan"), end=4.0), "https://media.example/input.mp4")

    def test_reference_task_requires_public_https_metadata_url(self) -> None:
        self.assertEqual(
            MODULE.reference_url_from_task(
                {
                    "status": "completed",
                    "model": "gemini-omni-video",
                    "metadata": {"url": "https://media.example/input.mp4"},
                }
            ),
            "https://media.example/input.mp4",
        )
        with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, "metadata.url"):
            MODULE.reference_url_from_task({"status": "completed", "metadata": {}})
        with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, "not completed"):
            MODULE.reference_url_from_task({"status": "queued", "metadata": {}})

    def test_task_state_accepts_transient_unknown(self) -> None:
        self.assertEqual(MODULE.task_state({}), ("unknown", "", None))
        self.assertEqual(MODULE.task_state({"status": "completed", "progress": 100}), ("completed", "", 100))

    def test_wait_for_task_survives_unknown_then_completes(self) -> None:
        responses = [
            (json.dumps({"status": "unknown"}).encode(), "application/json"),
            (json.dumps({"status": "queued", "progress": 10}).encode(), "application/json"),
            (json.dumps({"status": "completed", "progress": 100}).encode(), "application/json"),
        ]
        captured = io.StringIO()
        with patch.object(MODULE, "request", side_effect=responses), patch.object(MODULE.time, "sleep"), redirect_stdout(captured):
            result = MODULE.wait_for_task("https://example.com/v1", "key", "task-1", 1, 10, 0.01, object())

        self.assertEqual(result["status"], "completed")
        self.assertIn("status=unknown", captured.getvalue())
        self.assertIn("status=completed", captured.getvalue())

    def test_write_output_requires_mp4_and_refuses_overwrite(self) -> None:
        valid_mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 20
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            MODULE.write_output(output, valid_mp4, overwrite=False)
            self.assertEqual(output.read_bytes(), valid_mp4)
            with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, "already exists"):
                MODULE.write_output(output, valid_mp4, overwrite=False)
            with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, "not an MP4"):
                MODULE.write_output(Path(directory) / "bad.mp4", b"not-video", overwrite=False)
            with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, r"\.mp4 extension"):
                MODULE.write_output(Path(directory) / "wrong.mov", valid_mp4, overwrite=False)

    def test_verified_output_is_committed_only_after_probe_passes(self) -> None:
        valid_mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 20
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.mp4"
            with patch.object(MODULE, "probe_video") as probe:
                MODULE.write_verified_output(output, valid_mp4, False, False, "720p", 4.0)
            self.assertTrue(output.is_file())
            probe.assert_called_once()

            failed_output = Path(directory) / "failed.mp4"
            with patch.object(
                MODULE,
                "probe_video",
                side_effect=MODULE.GeminiOmniVideoError("resolution mismatch"),
            ):
                with self.assertRaisesRegex(MODULE.GeminiOmniVideoError, "resolution mismatch"):
                    MODULE.write_verified_output(failed_output, valid_mp4, False, False, "720p", 4.0)
            self.assertFalse(failed_output.exists())
            self.assertEqual(list(Path(directory).glob(".failed.*.mp4")), [])

    def test_reference_url_rejects_local_hosts(self) -> None:
        for value in (
            "https://localhost/input.mp4",
            "https://127.0.0.1/input.mp4",
            "https://192.168.1.2/input.mp4",
            "https://host.local/input.mp4",
        ):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                MODULE.validate_public_https_url(value)

    def test_user_agent_avoids_python_default_signature(self) -> None:
        self.assertEqual(MODULE.USER_AGENT, "akasha-gemini-omni-video/1.0")
        self.assertNotIn("Python-urllib", MODULE.USER_AGENT)

    def test_request_sends_explicit_user_agent(self) -> None:
        captured: list[object] = []

        class Response:
            headers = email.message.Message()

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self, _limit: int) -> bytes:
                return b"{}"

        class Controller:
            def run(self, operation: object) -> object:
                return operation()

        def urlopen(request: object, timeout: float) -> Response:
            captured.append((request, timeout))
            return Response()

        with patch.object(MODULE.urllib.request, "urlopen", side_effect=urlopen):
            MODULE.request(
                "https://example.com/v1",
                "secret",
                "/videos",
                3,
                {"model": "gemini-omni-video"},
                controller=Controller(),
            )

        request, timeout = captured[0]
        self.assertEqual(timeout, 3)
        self.assertEqual(request.get_header("User-agent"), MODULE.USER_AGENT)
        self.assertEqual(request.full_url, "https://example.com/v1/videos")

    def test_recharge_amount_works_before_or_after_subcommand(self) -> None:
        parser = MODULE.build_parser()
        root_value = parser.parse_args(
            ["--recharge-usd", "12", "generate", "--prompt", "test", "--output", "/tmp/a.mp4"]
        )
        subcommand_value = parser.parse_args(
            ["generate", "--recharge-usd", "13", "--prompt", "test", "--output", "/tmp/a.mp4"]
        )

        self.assertEqual(root_value.recharge_usd, "12")
        self.assertEqual(subcommand_value.recharge_usd, "13")


if __name__ == "__main__":
    unittest.main()
