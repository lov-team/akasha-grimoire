#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("video_generation.py")
SKILL_DIR = SCRIPT.parent.parent
PROMPT_GUIDE = SKILL_DIR / "references" / "h3-context-ir-prompting.md"
MP4 = b"\x00\x00\x00\x18ftypisomfixture"

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("video_generation_under_test", SCRIPT)
assert SPEC and SPEC.loader
VIDEO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VIDEO)

EXAMPLE_RE = re.compile(
    r"^### (T2VA|I2VA|FL2VA|Ref2VA) 示例（(\d+) 秒([^）]*)）$\s*^请求：`([^`]*)`$.*?^```text\n(.*?)^```$",
    re.M | re.S,
)
EXAMPLE_MODES = {"T2VA": "t2va", "I2VA": "i2va", "FL2VA": "fl2va", "Ref2VA": "ref2va"}
EXAMPLE_IMAGES = {"T2VA": 0, "I2VA": 1, "FL2VA": 2}


class Example(NamedTuple):
    name: str
    seconds: int
    images: int
    videos: int
    audios: int
    request: str
    prompt: str


def documented_examples() -> dict[str, Example]:
    examples = {}
    for name, seconds, extra, request, prompt in EXAMPLE_RE.findall(PROMPT_GUIDE.read_text(encoding="utf-8")):
        if name == "Ref2VA":
            images, videos, audios = (
                int(match.group(1)) if (match := re.search(rf"(\d+) {unit}", extra)) else 0
                for unit in ("张图片", "段视频", "段音频")
            )
        else:
            images, videos, audios = EXAMPLE_IMAGES[name], 0, 0
        examples[name] = Example(name, int(seconds), images, videos, audios, request, prompt)
    return examples


def request_argv(request: str) -> list[str]:
    """Documented request flags with placeholder media replaced by HTTPS URLs."""
    argv = shlex.split(request)
    for index, value in enumerate(argv[:-1]):
        if value in ("--image", "--reference-video", "--reference-audio"):
            argv[index + 1] = f"https://media.example/{argv[index + 1].lower()}"
    return argv


def t2va(description: str, soundscape: str = "Soft rain falls on the pavement.") -> str:
    return (
        f"integrated_multimodal_description: {description}\n\n"
        f"overall_soundscape: {soundscape}\n\n"
        "non_diegetic_music: N/A"
    )


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
        self.send_json({"id": "task-video-123", "status": "queued"})

    def do_GET(self) -> None:
        self.requests.append((self.command, self.path, b""))
        if self.path == "/v1/models":
            self.send_json({"object": "list", "data": []})
        elif self.path == "/v1/video/generations/task-video-123":
            self.send_json({"data": {"task_id": "task-video-123", "status": "SUCCESS"}})
        elif self.path == "/v1/videos/task-video-123/content":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(MP4)))
            self.end_headers()
            self.wfile.write(MP4)
        else:
            self.send_response(404)
            self.end_headers()


class VideoGenerationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self) -> None:
        Handler.requests.clear()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def invoke(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["LOVBROWSER_API_KEY"] = "test-key"
        env["AKASHA_ALLOW_TEST_HTTP"] = "1"
        return subprocess.run(
            ["python3", str(SCRIPT), "--base-url", self.base_url, "--timeout", "5", *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def output(self, name: str) -> str:
        return str(Path(self.temp_dir.name) / name)

    def submit_payload(self) -> dict:
        method, path, body = [request for request in Handler.requests if request[1] != "/v1/models"][0]
        self.assertEqual((method, path), ("POST", "/v1/video/generations"))
        return json.loads(body)

    def test_base_url_precedence(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://compatible.example/v1",
                "H3_KLING_VIDEO_BASE_URL": "https://video.example/v1",
            },
            clear=True,
        ):
            self.assertEqual(VIDEO.resolve_base_url(None), "https://video.example/v1")
            self.assertEqual(VIDEO.resolve_base_url("https://cli.example"), "https://cli.example/v1")

    def test_minimax_h3_payload_and_download(self) -> None:
        output = self.output("h3.mp4")
        result = self.invoke(
            "generate", "--model", "minimax-h3", "--prompt", "a cat on a beach",
            "--duration", "15", "--aspect-ratio", "21:9", "--resolution", "768P",
            "--poll-interval", "0.01", "--output", output,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(output).read_bytes(), MP4)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "minimax-h3/text-to-video")
        self.assertEqual(payload["duration"], 15)
        self.assertEqual(payload["metadata"], {
            "aspect_ratio": "21:9", "duration": 15, "resolution": "768P"
        })

    def test_h3_max_is_the_default_model(self) -> None:
        result = self.invoke(
            "generate", "--prompt", "a cat on a beach",
            "--poll-interval", "0.01", "--output", self.output("h3-max-default.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "h3-max")
        self.assertEqual(payload["duration"], 5)
        self.assertEqual(payload["metadata"], {
            "aspect_ratio": "16:9", "duration": 5, "resolution": "768P"
        })

    def test_h3_max_generic_image_request_keeps_images_for_new_api_routing(self) -> None:
        image = "https://media.example/first.png"
        result = self.invoke(
            "generate", "--model", "h3-max", "--prompt", "subtle motion",
            "--image", image, "--poll-interval", "0.01", "--output", self.output("h3-max-i2v.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "h3-max")
        self.assertEqual(payload["images"], [image])
        self.assertNotIn("aspect_ratio", payload["metadata"])

    def test_h3_max_i2v_uses_native_frame_fields_without_aspect_ratio(self) -> None:
        first = "https://media.example/first.png"
        last = "https://media.example/last.png"
        result = self.invoke(
            "generate", "--model", "h3-max-i2v", "--prompt", "the subject looks up",
            "--image", first, "--image", last, "--resolution", "480P",
            "--poll-interval", "0.01", "--output", self.output("h3-max-explicit-i2v.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "minimax/h3-max/image-to-video")
        self.assertEqual(payload["metadata"]["image_url"], first)
        self.assertEqual(payload["metadata"]["end_image_url"], last)
        self.assertNotIn("aspect_ratio", payload["metadata"])

    def test_h3_max_reference_video_and_audio_select_reference_sku(self) -> None:
        video = "https://media.example/reference.mp4"
        audio = "https://media.example/reference.mp3"
        result = self.invoke(
            "generate", "--model", "h3-max", "--prompt", "preserve the reference mood",
            "--reference-video", video, "--reference-audio", audio,
            "--poll-interval", "0.01", "--output", self.output("h3-max-reference.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "minimax/h3-max/reference-to-video")
        self.assertEqual(payload["reference_video_urls"], [video])
        self.assertEqual(payload["reference_audio_urls"], [audio])
        self.assertEqual(payload["metadata"]["reference_video_urls"], [video])
        self.assertEqual(payload["metadata"]["reference_audio_urls"], [audio])

    def test_fal_ai_h3_max_sku_aliases_are_accepted(self) -> None:
        result = self.invoke(
            "generate", "--model", "fal-ai/minimax/h3-max/text-to-video",
            "--prompt", "a quiet sunrise", "--duration", "5", "--resolution", "480P",
            "--poll-interval", "0.01", "--output", self.output("h3-max-fal-alias.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.submit_payload()["model"], "minimax/h3-max/text-to-video")

    def test_minimax_h3_image_to_video_first_and_last_frame_payload(self) -> None:
        first = "https://media.example/first.png"
        last = "https://media.example/last.png"
        result = self.invoke(
            "generate", "--model", "h3-i2v", "--prompt", "grass sways in a light breeze",
            "--duration", "10", "--resolution", "2K",
            "--image", first, "--image", last,
            "--poll-interval", "0.01", "--output", self.output("h3-i2v.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "minimax-h3/image-to-video")
        self.assertEqual(payload["duration"], 10)
        self.assertEqual(payload["images"], [first, last])
        self.assertEqual(payload["metadata"], {
            "duration": 10,
            "resolution": "2K",
            "image_url": first,
            "end_image_url": last,
        })

    def test_minimax_h3_image_to_video_requires_reference_frame(self) -> None:
        result = self.invoke(
            "generate", "--model", "minimax-h3/image-to-video", "--prompt", "subtle motion",
            "--duration", "10", "--output", self.output("missing-frame.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires at least one", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])

    def test_kling_25_uses_string_duration_and_native_options(self) -> None:
        result = self.invoke(
            "generate", "--model", "kling-2.5-t2v", "--prompt", "camera dolly",
            "--duration", "10", "--negative-prompt", "blur", "--cfg-scale", "0.7",
            "--poll-interval", "0.01", "--output", self.output("k25.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["model"], "kling/v2-5-turbo-text-to-video-pro")
        self.assertEqual(payload["metadata"]["duration"], "10")
        self.assertEqual(payload["metadata"]["negative_prompt"], "blur")
        self.assertEqual(payload["metadata"]["cfg_scale"], 0.7)

    def test_kling_25_uses_five_second_model_default(self) -> None:
        result = self.invoke(
            "generate", "--model", "kling-2.5-t2v", "--prompt", "camera dolly",
            "--poll-interval", "0.01", "--output", self.output("k25-default.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        self.assertEqual(payload["duration"], 5)
        self.assertEqual(payload["metadata"]["duration"], "5")

    def test_kling_3_images_sound_mode_and_advanced_metadata(self) -> None:
        image = "https://media.example/first.png"
        result = self.invoke(
            "generate", "--model", "kling-3", "--prompt", "the subject turns",
            "--duration", "7", "--image", image, "--mode", "4K", "--no-sound",
            "--metadata-json", '{"kling_elements":[{"name":"subject"}]}' ,
            "--poll-interval", "0.01", "--output", self.output("k3.mp4"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.submit_payload()
        metadata = payload["metadata"]
        self.assertEqual(metadata["image_urls"], [image])
        self.assertEqual(metadata["duration"], "7")
        self.assertEqual(metadata["mode"], "4K")
        self.assertFalse(metadata["sound"])
        self.assertEqual(metadata["kling_elements"], [{"name": "subject"}])

    def test_rejects_model_specific_invalid_values_before_request(self) -> None:
        result = self.invoke(
            "generate", "--model", "minimax-h3", "--prompt", "x",
            "--duration", "3", "--output", self.output("bad.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("4-15", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])

        result = self.invoke(
            "generate", "--model", "kling-2.5-t2v", "--prompt", "x",
            "--duration", "5", "--cfg-scale", "0.65", "--output", self.output("bad-scale.mp4"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("increments of 0.1", result.stderr)
        self.assertFalse([request for request in Handler.requests if request[1] != "/v1/models"])


class ContextIrLintTest(unittest.TestCase):
    """The lint needs no network; these tests run in-process."""

    def lint(self, prompt: str, **kwargs: object):
        return VIDEO.lint_context_ir(prompt, **kwargs)

    def assertError(self, report, fragment: str) -> None:
        self.assertTrue(any(fragment in error for error in report.errors), report.errors)

    def test_documented_examples_are_clean(self) -> None:
        examples = documented_examples()
        self.assertEqual(list(examples), ["T2VA", "I2VA", "FL2VA", "Ref2VA"])
        for example in examples.values():
            with self.subTest(example.name):
                report = self.lint(
                    example.prompt,
                    mode=EXAMPLE_MODES[example.name],
                    duration=example.seconds,
                    images=example.images,
                    videos=example.videos,
                    audios=example.audios,
                )
                self.assertEqual(report.mode, EXAMPLE_MODES[example.name])
                self.assertEqual(report.errors, [])
                self.assertEqual(report.warnings, [])

    def test_templates_are_rejected_until_filled(self) -> None:
        templates = sorted((SKILL_DIR / "assets").glob("h3-prompt-*.txt"))
        self.assertEqual(len(templates), 4)
        for template in templates:
            with self.subTest(template.name):
                report = self.lint(template.read_text(encoding="utf-8"))
                self.assertError(report, "unfilled template placeholders")
                self.assertEqual(report.mode, template.stem.removeprefix("h3-prompt-"))

    def test_prompt_mode_must_match_request(self) -> None:
        prompt = documented_examples()["I2VA"].prompt
        report = self.lint(prompt, mode="fl2va", duration=5)
        self.assertTrue(report.errors[0].startswith("the prompt is written for I2VA but the request is FL2VA"))
        report = self.lint(prompt, mode="t2va", duration=5)
        self.assertIn("send exactly one --image", report.errors[0])

    def test_i2va_alignment_line_is_exact(self) -> None:
        prompt = documented_examples()["I2VA"].prompt.replace("is fully referenced", "is referenced")
        self.assertError(self.lint(prompt, mode="i2va"), "I2VA alignment line must read exactly")

    def test_fl2va_alignment_checks_mark_and_last_shot(self) -> None:
        example = documented_examples()["FL2VA"]
        self.assertError(self.lint(example.prompt, duration=10), "must align with the 10.00-second mark")
        moved = example.prompt.replace("Picture 2 (from Shot 1)", "Picture 2 (from Shot 2)")
        self.assertError(self.lint(moved, duration=example.seconds), "must come from the last shot (Shot 1), not Shot 2")
        hyphen = example.prompt.replace("target video — Picture 1", "target video - Picture 1")
        self.assertError(self.lint(hyphen, duration=example.seconds), "FL2VA alignment line must read exactly")
        report = self.lint(example.prompt)
        self.assertEqual(report.errors, [])
        self.assertTrue(any("pass --duration" in warning for warning in report.warnings))

    def test_shot_timestamps(self) -> None:
        opening = "[Shot 1] Live-action, cinematic, a woman walks through the rain."
        cases = {
            "needs a timestamp": (f"{opening} [Shot 2] The camera cuts to her face.", None),
            "must not have a timestamp": ("[Shot 1] At 00:00.000, a woman walks through the rain.", None),
            "at or after the end of the 5-second video": (
                f"{opening} [Shot 2] At 00:06.000, the camera cuts to her face.", 5,
            ),
            "must come after the previous shot": (
                f"{opening} [Shot 2] At 00:03.000, the camera cuts to her face. "
                "[Shot 3] At 00:02.000, the camera cuts to her hands.",
                8,
            ),
            "number shots [Shot 1], [Shot 2], ... in order": (
                f"{opening} [Shot 3] At 00:03.000, the camera cuts to her face.", 8,
            ),
            "must start with [Shot 1]": ("Live-action, a woman walks. [Shot 1] She stops.", None),
        }
        for fragment, (description, duration) in cases.items():
            with self.subTest(fragment):
                self.assertError(self.lint(t2va(description), duration=duration), fragment)
        report = self.lint(t2va(f"{opening} [Shot 2] At 00:04.000, the camera cuts to her face."), duration=5)
        self.assertEqual(report.errors, [])
        self.assertTrue(any("[Shot 2] lasts 1.00 s" in warning for warning in report.warnings), report.warnings)

    def test_fields_and_sound(self) -> None:
        swapped = (
            "overall_soundscape: Rain.\n\n"
            "integrated_multimodal_description: [Shot 1] Live-action, a woman walks.\n\n"
            "non_diegetic_music: N/A"
        )
        self.assertError(self.lint(swapped), "fields must appear in this order")
        missing = "integrated_multimodal_description: [Shot 1] Live-action, a woman walks.\n\nnon_diegetic_music: N/A"
        self.assertError(self.lint(missing), "missing field overall_soundscape:")
        empty = t2va("[Shot 1] Live-action, a woman walks.", soundscape="")
        self.assertError(self.lint(empty), "overall_soundscape: is empty")
        self.assertError(self.lint("A woman walks through the rain at night."), "no Context-IR fields found")

    def test_chinese_only_allowed_in_dialogue_and_quoted_text(self) -> None:
        report = self.lint(t2va("[Shot 1] Live-action, cinematic, 一个女人在雨中行走。"))
        self.assertError(report, "non-English text outside <d>...</d>")
        allowed = t2va(
            '[Shot 1] Live-action, cinematic, a neon sign above the door reads "营业中". '
            "The old shopkeeper (S1) says: <d>[Chinese] 欢迎光临。</d>"
        )
        report = self.lint(allowed)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_dialogue_needs_language_tag_and_speaker(self) -> None:
        report = self.lint(t2va("[Shot 1] Live-action, a man looks up and says: <d>Hello.</d>"))
        self.assertTrue(any("no language tag" in warning for warning in report.warnings), report.warnings)
        self.assertTrue(any("no speaker ID" in warning for warning in report.warnings), report.warnings)
        self.assertError(self.lint(t2va("[Shot 1] Live-action, (S1) says: <d>[English] Hello.")), "unbalanced dialogue tags")

    def test_instruction_wording_is_flagged(self) -> None:
        report = self.lint(t2va("[Shot 1] Live-action, a woman walks. Do not let her blink. Make sure it rains."))
        self.assertEqual(report.errors, [])
        self.assertTrue(any("instruction wording (do not, make sure)" in warning for warning in report.warnings))

    def test_ref2va_labels_match_reference_counts(self) -> None:
        example = documented_examples()["Ref2VA"]
        report = self.lint(example.prompt, duration=example.seconds, images=1, videos=0, audios=1)
        self.assertError(report, "<Picture 2> has no matching reference; the request has 1 --image file(s)")
        report = self.lint(example.prompt, duration=example.seconds, images=2, videos=0, audios=0)
        self.assertError(report, "<Audio 1> has no matching reference")
        # A reference video's soundtrack can be labelled as an <Audio N>.
        report = self.lint(example.prompt, duration=example.seconds, images=2, videos=1, audios=0)
        self.assertFalse([error for error in report.errors if "<Audio 1>" in error], report.errors)

    def test_ref2va_structure(self) -> None:
        example = documented_examples()["Ref2VA"]
        undefined = example.prompt.replace("walking through <Subject 2>", "walking through <Subject 3>")
        self.assertError(self.lint(undefined), "summary: <Subject 3> is not introduced")
        self.assertError(self.lint(undefined), "<Subject 3> is used but never defined")
        tagged = example.prompt.replace("[reference generation + audio reference]", "[reference generation + remix]")
        self.assertError(self.lint(tagged), "summary: unknown task tag 'remix'")
        mixed = example.prompt.replace("detailed_description:", "integrated_multimodal_description:")
        self.assertError(self.lint(mixed), "mixes integrated_multimodal_description: with Ref2VA sections")

    def test_is_context_ir(self) -> None:
        for example in documented_examples().values():
            self.assertTrue(VIDEO.is_context_ir(example.prompt), example.name)
        self.assertFalse(VIDEO.is_context_ir("A cat naps on a sunny windowsill. Summary: calm."))


class RequestPreparationTest(unittest.TestCase):
    """prepare_request validates and builds the payload without any network call."""

    def prepare(self, *argv: str):
        args = VIDEO.build_parser().parse_args(["generate", *argv, "--output", "unused.mp4"])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            model, metadata, payload, warnings = VIDEO.prepare_request(args)
        return model, metadata, payload, warnings, stderr.getvalue()

    def assertRejected(self, fragment: str, *argv: str) -> None:
        with self.assertRaises(VIDEO.VideoGenerationError) as caught, contextlib.redirect_stderr(io.StringIO()):
            self.prepare(*argv)
        self.assertIn(fragment, str(caught.exception))

    def test_documented_requests_accept_their_examples(self) -> None:
        for example in documented_examples().values():
            with self.subTest(example.name):
                model, metadata, payload, warnings, stderr = self.prepare(
                    *request_argv(example.request), "--prompt", example.prompt
                )
                self.assertEqual(warnings, [])
                self.assertNotIn("WARNING", stderr)
                self.assertEqual(metadata["prompt_expansion_mode"], "disabled")
                self.assertEqual(payload["duration"], example.seconds)
                self.assertEqual(len(payload.get("images", [])), example.images)

    def test_prompt_expansion_auto_only_disables_for_context_ir(self) -> None:
        _, metadata, _, _, stderr = self.prepare("--prompt", "a cat naps on a sunny windowsill")
        self.assertNotIn("prompt_expansion_mode", metadata)
        self.assertIn("balanced prompt expansion rewrites it", stderr)
        _, metadata, _, _, stderr = self.prepare(
            "--prompt", "a cat naps", "--metadata-json", '{"prompt_expansion_mode": "quality"}'
        )
        self.assertEqual(metadata["prompt_expansion_mode"], "quality")

    def test_explicit_prompt_expansion_and_seed_pass_through(self) -> None:
        _, metadata, _, _, _ = self.prepare("--prompt", "a cat naps", "--prompt-expansion", "quality", "--seed", "42")
        self.assertEqual((metadata["prompt_expansion_mode"], metadata["seed"]), ("quality", 42))
        prompt = documented_examples()["T2VA"].prompt
        _, metadata, _, _, stderr = self.prepare("--prompt", prompt, "--duration", "8", "--prompt-expansion", "balanced")
        self.assertEqual(metadata["prompt_expansion_mode"], "balanced")
        self.assertIn("will rewrite this Context-IR prompt", stderr)

    def test_expansion_and_seed_are_h3_max_only(self) -> None:
        self.assertRejected("H3 Max only", "--model", "kling-3", "--prompt", "x", "--seed", "1")
        self.assertRejected("H3 Max only", "--model", "minimax-h3", "--prompt", "x", "--prompt-expansion", "disabled")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.prepare("--prompt", "x", "--seed", "-1")

    def test_legacy_h3_lints_context_ir_without_expansion_field(self) -> None:
        prompt = documented_examples()["T2VA"].prompt
        _, metadata, _, _, _ = self.prepare("--model", "minimax-h3", "--prompt", prompt, "--duration", "8")
        self.assertNotIn("prompt_expansion_mode", metadata)
        self.assertRejected("nothing was submitted", "--model", "minimax-h3", "--prompt", prompt, "--duration", "4")

    def test_text_to_video_aspect_ratio(self) -> None:
        _, metadata, _, _, _ = self.prepare("--model", "h3-max-t2v", "--prompt", "x")
        self.assertEqual(metadata["aspect_ratio"], "16:9")
        self.assertRejected("does not support adaptive", "--model", "h3-max-t2v", "--prompt", "x", "--aspect-ratio", "adaptive")
        self.assertRejected("does not support adaptive", "--prompt", "x", "--aspect-ratio", "adaptive")
        _, metadata, _, _, _ = self.prepare("--model", "h3-max-reference", "--prompt", "x", "--image", "https://media.example/a.png")
        self.assertEqual(metadata["aspect_ratio"], "adaptive")

    def test_image_to_video_ignores_aspect_ratio(self) -> None:
        _, metadata, _, _, stderr = self.prepare(
            "--model", "h3-max-i2v", "--prompt", "x", "--image", "https://media.example/a.png", "--aspect-ratio", "9:16"
        )
        self.assertNotIn("aspect_ratio", metadata)
        self.assertIn("--aspect-ratio is ignored for image-to-video", stderr)

    def test_generic_h3_max_routing(self) -> None:
        images = ["--image", "https://media.example/a.png", "--image", "https://media.example/b.png"]
        self.assertRejected("h3-max with two or more images is ambiguous", "--prompt", "x", *images)
        model, metadata, payload, _, _ = self.prepare(
            "--prompt", "x", "--image", "https://media.example/a.png",
            "--metadata-json", '{"reference_audio_urls": ["https://media.example/voice.mp3"]}',
        )
        self.assertEqual(model, "minimax/h3-max/reference-to-video")
        self.assertEqual(payload["reference_audio_urls"], ["https://media.example/voice.mp3"])
        self.assertEqual(metadata["reference_audio_urls"], ["https://media.example/voice.mp3"])

    def test_reference_limits(self) -> None:
        _, _, _, _, stderr = self.prepare(
            "--model", "h3-max-reference", "--prompt", "x", "--reference-audio", "https://media.example/voice.mp3"
        )
        self.assertIn("reference audio without an image or video", stderr)
        ten = [value for index in range(10) for value in ("--image", f"https://media.example/{index}.png")]
        _, _, _, _, stderr = self.prepare("--model", "h3-max-reference", "--prompt", "x", *ten)
        self.assertIn("10 images: fal's H3 overview allows at most 9", stderr)
        thirteen = ten + [value for index in range(3) for value in ("--reference-video", f"https://media.example/{index}.mp4")]
        self.assertRejected("accepts at most 12 reference files", "--model", "h3-max-reference", "--prompt", "x", *thirteen)

    def test_resolutions(self) -> None:
        for model in ("h3-max", "h3-max-t2v"):
            _, metadata, _, _, _ = self.prepare("--model", model, "--prompt", "x", "--resolution", "1080P")
            self.assertEqual(metadata["resolution"], "1080P")
        self.assertRejected("resolution must be one of: 480P, 768P, 1080P", "--prompt", "x", "--resolution", "2K")

    def test_lint_errors_block_submission_unless_skipped(self) -> None:
        prompt = documented_examples()["I2VA"].prompt
        self.assertRejected("Context-IR lint failed (nothing was submitted)", "--prompt", prompt)
        _, metadata, _, warnings, stderr = self.prepare("--prompt", prompt, "--skip-lint")
        self.assertEqual(warnings, [])
        self.assertIn("--skip-lint", stderr)
        self.assertEqual(metadata["prompt_expansion_mode"], "disabled")

    def test_chinese_plain_prompt_warns(self) -> None:
        _, _, _, _, stderr = self.prepare("--prompt", "镜头一：少女在雨夜的屋顶花园中行走")
        self.assertIn("Chinese/Japanese/Korean text", stderr)

    def test_prompt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            valid = root / "shot.txt"
            valid.write_bytes("﻿".encode() + b"  [Shot 1] text \n")
            args = argparse.Namespace(prompt=None, prompt_file=str(valid))
            self.assertEqual(VIDEO.resolve_prompt(args), "[Shot 1] text")
            (root / "empty.txt").write_text(" \n", encoding="utf-8")
            (root / "latin1.txt").write_bytes(b"caf\xe9")
            (root / "large.txt").write_bytes(b"a" * (VIDEO.MAX_PROMPT_FILE_BYTES + 1))
            cases = {
                "missing.txt": "cannot read prompt file",
                ".": "prompt file is not a regular file",
                "empty.txt": "prompt file is empty",
                "latin1.txt": "cannot read UTF-8 prompt file",
                "large.txt": f"prompt file exceeds {VIDEO.MAX_PROMPT_FILE_BYTES} bytes",
            }
            for name, fragment in cases.items():
                with self.subTest(name), self.assertRaises(VIDEO.VideoGenerationError) as caught:
                    VIDEO.resolve_prompt(argparse.Namespace(prompt=None, prompt_file=str(root / name)))
                self.assertIn(fragment, str(caught.exception))
        with self.assertRaises(VIDEO.VideoGenerationError) as caught:
            VIDEO.resolve_prompt(argparse.Namespace(prompt="  ", prompt_file=None))
        self.assertIn("prompt is empty", str(caught.exception))


class ResultHandlingTest(unittest.TestCase):
    def test_summarize_probe(self) -> None:
        probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720, "avg_frame_rate": "24/1"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
            "format": {"duration": "5.041667"},
        }
        self.assertEqual(
            VIDEO.summarize_probe(probe),
            {"codec": "h264", "width": 1280, "height": 720, "fps": 24.0, "duration": 5.042, "audio_streams": 1},
        )
        self.assertIsNone(VIDEO.summarize_probe({"streams": [{"codec_type": "audio"}]}))
        self.assertEqual(VIDEO.parse_rate("24000/1001"), 23.976)
        self.assertIsNone(VIDEO.parse_rate("0/0"))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe are required")
    def test_probe_media_reads_a_real_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clip = Path(temp) / "probe.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=24:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(clip),
                ],
                check=True,
                capture_output=True,
            )
            media = VIDEO.probe_media(clip)
        self.assertEqual(
            {key: media[key] for key in ("codec", "width", "height", "fps", "audio_streams")},
            {"codec": "mpeg4", "width": 160, "height": 120, "fps": 24.0, "audio_streams": 1},
        )
        self.assertAlmostEqual(media["duration"], 1.0, delta=0.1)

    def test_without_urls_and_find_value(self) -> None:
        value = {"image_url": "https://media.example/a.png", "refs": ["data:image/png;base64,AA", "keep"], "seed": 3}
        self.assertEqual(
            VIDEO.without_urls(value),
            {"image_url": "<url omitted>", "refs": ["<url omitted>", "keep"], "seed": 3},
        )
        nested = {"expanded_prompt": "", "data": {"status": "SUCCESS", "data": {"expanded_prompt": "IR", "seed": 0}}}
        self.assertEqual(VIDEO.find_value(nested, "expanded_prompt"), "IR")
        self.assertEqual(VIDEO.find_value(nested, "seed"), 0)
        self.assertIsNone(VIDEO.find_value(nested, "missing"))

    def test_generate_writes_sidecar(self) -> None:
        example = documented_examples()["I2VA"]
        image = "https://media.example/first.png"
        calls: list[tuple[str, dict | None]] = []

        def fake_request(base_url, api_key, path, timeout, payload=None, *, controller=None):
            calls.append((path, payload))
            if path == "/video/generations":
                return json.dumps({"id": "task-1"}).encode(), "application/json"
            if path == "/video/generations/task-1":
                result = {"data": {"status": "SUCCESS", "data": {"expanded_prompt": "EXPANDED IR", "seed": 7}}}
                return json.dumps(result).encode(), "application/json"
            if path == "/videos/task-1/content":
                return MP4, "video/mp4"
            raise AssertionError(path)

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "shot-01.mp4"
            prompt_file = Path(temp) / "shot-01.txt"
            prompt_file.write_text(example.prompt, encoding="utf-8")
            args = VIDEO.build_parser().parse_args([
                "generate", "--model", "h3-max-i2v", "--prompt-file", str(prompt_file), "--image", image,
                "--duration", "5", "--seed", "7", "--output", str(output),
            ])
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                patch.object(VIDEO, "resolve_base_url", return_value="https://gateway.example/v1"),
                patch.object(VIDEO, "read_api_key", return_value="test-key"),
                patch.object(VIDEO, "request", side_effect=fake_request),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                VIDEO.run_generate(args)
            self.assertEqual(output.read_bytes(), MP4)
            lines = stdout.getvalue().splitlines()
            self.assertTrue(lines[0].startswith("OK task_id=task-1 "), lines)
            self.assertEqual(lines[1], "MEDIA unavailable (ffprobe not found or failed)")
            self.assertTrue(lines[2].startswith("SIDECAR ") and lines[2].endswith("shot-01.mp4.json"), lines)
            self.assertEqual(lines[3], "EXPANDED_PROMPT chars=11 (saved in the sidecar)")
            submitted = calls[0][1]
            self.assertEqual(submitted["metadata"]["prompt_expansion_mode"], "disabled")
            self.assertEqual(submitted["metadata"]["seed"], 7)
            self.assertEqual(submitted["images"], [image])
            sidecar = json.loads((Path(temp) / "shot-01.mp4.json").read_text(encoding="utf-8"))
            self.assertEqual(sidecar["task_id"], "task-1")
            self.assertEqual(sidecar["seed"], 7)
            self.assertEqual(sidecar["expanded_prompt"], "EXPANDED IR")
            self.assertEqual(sidecar["prompt"], example.prompt.strip())
            self.assertEqual(sidecar["prompt_file"], str(prompt_file.resolve()))
            self.assertEqual(sidecar["request"]["metadata"]["image_url"], "<url omitted>")
            self.assertEqual(sidecar["request"]["metadata"]["prompt_expansion_mode"], "disabled")
            self.assertEqual(sidecar["request"]["images"], 1)
            self.assertIsNone(sidecar["media"])
            self.assertEqual(sidecar["lint_warnings"], [])
            self.assertNotIn(image, json.dumps(sidecar))

            request_mock = patch.object(VIDEO, "request", side_effect=AssertionError("no request expected"))
            with (
                request_mock,
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(VIDEO.VideoGenerationError) as caught,
            ):
                VIDEO.run_generate(VIDEO.build_parser().parse_args([
                    "generate", "--prompt", "x", "--output", str(output),
                ]))
            self.assertIn("pass --overwrite", str(caught.exception))


class CommandLineTest(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["LOVBROWSER_API_KEY"] = "test-key"
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], env=env, text=True, capture_output=True, check=False
        )

    def test_lint_exit_codes(self) -> None:
        example = documented_examples()["I2VA"]
        with tempfile.TemporaryDirectory() as temp:
            prompt_file = Path(temp) / "shot.txt"
            prompt_file.write_text(example.prompt, encoding="utf-8")
            result = self.run_script(
                "lint", "--prompt-file", str(prompt_file), "--model", "h3-max-i2v", "--images", "1", "--duration", "5"
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LINT OK mode=I2VA errors=0 warnings=0", result.stdout)
        result = self.run_script("lint", "--prompt-file", str(SKILL_DIR / "assets" / "h3-prompt-t2va.txt"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("error: unfilled template placeholders", result.stdout)
        self.assertIn("LINT FAILED mode=T2VA", result.stdout)
        result = self.run_script("lint", "--prompt", "x", "--model", "kling-3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not an H3 model", result.stderr)

    def test_generate_rejects_bad_context_ir_before_any_request(self) -> None:
        prompt = documented_examples()["I2VA"].prompt
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_script(
                "--base-url", "http://127.0.0.1:9", "generate", "--prompt", prompt,
                "--output", str(Path(temp) / "never.mp4"),
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing was submitted", result.stderr)
        self.assertIn("the prompt is written for I2VA but the request is T2VA", result.stderr)


if __name__ == "__main__":
    unittest.main()
