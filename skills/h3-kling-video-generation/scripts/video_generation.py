#!/usr/bin/env python3
"""Generate MiniMax H3 and Kling videos through an asynchronous video API."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_RESPONSE_BYTES = 256 * 1024 * 1024
MAX_PROMPT_FILE_BYTES = 1024 * 1024
DEFAULT_BASE_URL = "https://llmapi.lovbrowser.com/v1"
SUCCESS_STATES = {"success", "succeeded", "completed"}
FAILURE_STATES = {"failure", "failed", "expired", "cancelled", "canceled"}
PROMPT_GUIDE = "references/h3-context-ir-prompting.md"

MINIMAX_H3_MODEL = "minimax-h3/text-to-video"
MINIMAX_H3_I2V_MODEL = "minimax-h3/image-to-video"
H3_MAX_MODEL = "h3-max"
H3_MAX_T2V_MODEL = "minimax/h3-max/text-to-video"
H3_MAX_I2V_MODEL = "minimax/h3-max/image-to-video"
H3_MAX_REFERENCE_MODEL = "minimax/h3-max/reference-to-video"
KLING_3_MODEL = "kling-3.0/video"
KLING_25_T2V_MODEL = "kling/v2-5-turbo-text-to-video-pro"

H3_MAX_FAMILY = frozenset({H3_MAX_MODEL, H3_MAX_T2V_MODEL, H3_MAX_I2V_MODEL, H3_MAX_REFERENCE_MODEL})
H3_FAMILY = H3_MAX_FAMILY | {MINIMAX_H3_MODEL, MINIMAX_H3_I2V_MODEL}
H3_TEXT_ASPECT_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
H3_MAX_RESOLUTIONS = ("480P", "768P", "1080P")

MODEL_ALIASES = {
    "minimax-h3": MINIMAX_H3_MODEL,
    "h3": MINIMAX_H3_MODEL,
    "minimax-h3-i2v": MINIMAX_H3_I2V_MODEL,
    "h3-i2v": MINIMAX_H3_I2V_MODEL,
    "h3-max": H3_MAX_MODEL,
    "minimax-h3-max": H3_MAX_MODEL,
    "h3-max-t2v": H3_MAX_T2V_MODEL,
    "minimax-h3-max-t2v": H3_MAX_T2V_MODEL,
    "fal-ai/minimax/h3-max/text-to-video": H3_MAX_T2V_MODEL,
    "h3-max-i2v": H3_MAX_I2V_MODEL,
    "minimax-h3-max-i2v": H3_MAX_I2V_MODEL,
    "fal-ai/minimax/h3-max/image-to-video": H3_MAX_I2V_MODEL,
    "h3-max-reference": H3_MAX_REFERENCE_MODEL,
    "minimax-h3-max-reference": H3_MAX_REFERENCE_MODEL,
    "fal-ai/minimax/h3-max/reference-to-video": H3_MAX_REFERENCE_MODEL,
    "kling-3": KLING_3_MODEL,
    "kling-3.0": KLING_3_MODEL,
    "kling-2.5-t2v": KLING_25_T2V_MODEL,
}

MODEL_PROFILES = {
    MINIMAX_H3_MODEL: {
        "durations": range(4, 16),
        "default_duration": 6,
        "aspect_ratios": H3_TEXT_ASPECT_RATIOS,
        "resolutions": ("768P", "2K"),
        "default_resolution": "2K",
        "supports_images": False,
        "duration_as_string": False,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": False,
        "max_images": 0,
        "uses_aspect_ratio": True,
        "prompt_limit": 7000,
    },
    MINIMAX_H3_I2V_MODEL: {
        "durations": range(4, 16),
        "default_duration": 6,
        "aspect_ratios": (),
        "resolutions": ("768P", "2K"),
        "default_resolution": "2K",
        "supports_images": True,
        "duration_as_string": False,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": True,
        "max_images": 2,
        "uses_aspect_ratio": False,
        "prompt_limit": 7000,
    },
    H3_MAX_MODEL: {
        "durations": range(5, 16),
        "default_duration": 5,
        # Without images this is text-to-video (no adaptive, checked in
        # resolve_model); one image makes it image-to-video, where the frame
        # sets the ratio. Two or more images are rejected by route_h3_model.
        "aspect_ratios": ("adaptive",) + H3_TEXT_ASPECT_RATIOS,
        "default_aspect_ratio": "16:9",
        "resolutions": H3_MAX_RESOLUTIONS,
        "default_resolution": "768P",
        "supports_images": True,
        "duration_as_string": False,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": False,
        "max_images": 1,
        "uses_aspect_ratio": True,
        "max_references": 1,
        "prompt_limit": 50000,
    },
    H3_MAX_T2V_MODEL: {
        "durations": range(5, 16),
        "default_duration": 5,
        "aspect_ratios": H3_TEXT_ASPECT_RATIOS,
        "default_aspect_ratio": "16:9",
        "resolutions": H3_MAX_RESOLUTIONS,
        "default_resolution": "768P",
        "supports_images": False,
        "duration_as_string": False,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": False,
        "max_images": 0,
        "uses_aspect_ratio": True,
        "max_references": 0,
        "prompt_limit": 50000,
    },
    H3_MAX_I2V_MODEL: {
        "durations": range(5, 16),
        "default_duration": 5,
        "aspect_ratios": (),
        "resolutions": H3_MAX_RESOLUTIONS,
        "default_resolution": "768P",
        "supports_images": True,
        "duration_as_string": False,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": True,
        "max_images": 2,
        # The image determines the output ratio for this SKU.
        "uses_aspect_ratio": False,
        "max_references": 2,
        "prompt_limit": 50000,
    },
    H3_MAX_REFERENCE_MODEL: {
        "durations": range(5, 16),
        "default_duration": 5,
        "aspect_ratios": ("adaptive",) + H3_TEXT_ASPECT_RATIOS,
        "default_aspect_ratio": "adaptive",
        "resolutions": H3_MAX_RESOLUTIONS,
        "default_resolution": "768P",
        "supports_images": True,
        "duration_as_string": False,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": False,
        "requires_references": True,
        "max_images": 12,
        "uses_aspect_ratio": True,
        "max_references": 12,
        "prompt_limit": 50000,
    },
    KLING_25_T2V_MODEL: {
        "durations": (5, 10),
        "default_duration": 5,
        "aspect_ratios": ("16:9", "9:16", "1:1"),
        "resolutions": (),
        "default_resolution": None,
        "supports_images": False,
        "duration_as_string": True,
        "supports_sound": False,
        "supports_mode": False,
        "requires_images": False,
        "max_images": 0,
        "uses_aspect_ratio": True,
        "prompt_limit": 2500,
    },
    KLING_3_MODEL: {
        "durations": range(3, 16),
        "default_duration": 5,
        "aspect_ratios": ("16:9", "9:16", "1:1"),
        "resolutions": (),
        "default_resolution": None,
        "supports_images": True,
        "duration_as_string": True,
        "supports_sound": True,
        "supports_mode": True,
        "requires_images": False,
        "max_images": 2,
        "uses_aspect_ratio": True,
        "prompt_limit": None,
    },
}

# Official MiniMax H3 Context-IR prompt format (base and ref writing guides).
BASE_FIELDS = ("integrated_multimodal_description", "overall_soundscape", "non_diegetic_music")
REF_SECTIONS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)
KNOWN_FIELDS = frozenset(BASE_FIELDS + REF_SECTIONS)
REF_ONLY_FIELDS = frozenset(REF_SECTIONS) - frozenset(BASE_FIELDS)
CONTEXT_IR_MARKERS = KNOWN_FIELDS - {"summary"}
SOUND_SENTENCE_LIMITS = {"overall_soundscape": 4, "non_diegetic_music": 3}
I2VA_PREFIX = "For the target video,"
I2VA_ALIGNMENT = (
    "For the target video, at 0.00 seconds into the target video, "
    "<Picture 1> (from [Shot 1]) is fully referenced."
)
FL2VA_PREFIX = "How the reference pictures align with the target video"
FL2VA_ALIGNMENT = (
    "How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with "
    "the 0.00-second mark of the target video; Picture 2 (from Shot {shot}) aligns with the "
    "{seconds}-second mark of the target video."
)
FL2VA_ALIGNMENT_RE = re.compile(
    r"How the reference pictures align with the target video — Picture 1 \(from Shot 1\) aligns with "
    r"the 0\.00-second mark of the target video; Picture 2 \(from Shot (?P<shot>\d+)\) aligns with the "
    r"(?P<seconds>\d+\.\d{2})-second mark of the target video\."
)
SUMMARY_TAGS = (
    "keyframe completion",
    "reference generation",
    "video editing",
    "video continuation",
    "audio reuse",
    "audio reference",
)
VISUAL_RETENTION = ("fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference")
AUDIO_RETENTION = ("fully_copy", "partially_copy", "reference", "weak_reference")
LABEL_KINDS = ("Subject", "Picture", "Video", "Audio")
MODE_NAMES = {"t2va": "T2VA", "i2va": "I2VA", "fl2va": "FL2VA", "ref2va": "Ref2VA"}
MODE_FORMATS = {
    "t2va": "T2VA starts directly with integrated_multimodal_description:",
    "i2va": "I2VA starts with the I2VA alignment line",
    "fl2va": "FL2VA starts with the FL2VA alignment line",
    "ref2va": "Ref2VA uses six sections starting with subject_definitions:",
}
MODE_REQUESTS = {
    "t2va": "send no --image (h3-max or h3-max-t2v)",
    "i2va": "send exactly one --image (h3-max-i2v)",
    "fl2va": "send the first and last frames as two --image values (h3-max-i2v)",
    "ref2va": "use --model h3-max-reference with the reference files",
}

FIELD_RE = re.compile(r"([a-z]+(?:_[a-z]+)*):(.*)")
SHOT_RE = re.compile(r"\[Shot (\d+)\]")
CUT_RE = re.compile(r" ?At (\d{2}):([0-5]\d)\.(\d{3}),")
LABEL_RE = re.compile(r"<(Subject|Picture|Video|Audio) (\d+)>")
DEFINITION_RE = re.compile(r"<(Subject|Picture|Video|Audio) (\d+)> is \S")
RETENTION_VISUAL_RE = re.compile(r"<(Subject|Picture|Video) (\d+)> \(appears in ([^)]*)\): ([a-z_]+) - \S")
RETENTION_AUDIO_RE = re.compile(r"<Audio (\d+)>: ([a-z_]+) - \S")
DIALOGUE_RE = re.compile(r"<d>(.*?)</d>", re.S)
LANGUAGE_TAG_RE = re.compile(r"\s*\[[A-Z][A-Za-z -]*\]")
SPEAKER_RE = re.compile(r"\(S\d+(?:, ?S\d+)*\)[^<]*$")
SPEAKER_CONTEXT_RE = re.compile(r"<(?:Subject|Picture|Video|Audio) \d+>|</?scenetrans>|<cutoff>")
QUOTED_RE = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”")
CJK_RE = re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿가-힯＀-￯]")
DIRECTIVE_RE = re.compile(r"\b(?:do not|don['’]t|make sure|ensure|must|should|avoid|please|strictly)\b", re.I)
PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}|\{\{|\}\}")
SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")


class VideoGenerationError(RuntimeError):
    pass


class PromptField:
    """One Context-IR field: its label line plus the raw lines that follow it."""

    def __init__(self, name: str, line: int, inline: str) -> None:
        self.name = name
        self.line = line
        self.inline = inline
        self.body: list[tuple[int, str]] = []

    @property
    def numbered_lines(self) -> list[tuple[int, str]]:
        lines = [(self.line, self.inline)] if self.inline else []
        lines.extend((number, text.strip()) for number, text in self.body if text.strip())
        return lines

    @property
    def text(self) -> str:
        return "\n".join(text for _, text in self.numbered_lines)


class LintReport:
    def __init__(self) -> None:
        self.mode: str | None = None
        self.errors: list[str] = []
        self.warnings: list[str] = []


def notice(kind: str, message: str) -> None:
    print(f"{kind}: {message}", file=sys.stderr)


def normalize_space(text: str) -> str:
    return " ".join(text.split())


def shorten(text: str, limit: int = 40) -> str:
    flat = normalize_space(text)
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def format_timestamp(seconds: float) -> str:
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes):02d}:{rest:06.3f}"


def label_key(label: tuple[str, int]) -> tuple[int, int]:
    return LABEL_KINDS.index(label[0]), label[1]


def first_fields(fields: list[PromptField]) -> dict[str, PromptField]:
    sections: dict[str, PromptField] = {}
    for item in fields:
        sections.setdefault(item.name, item)
    return sections


def split_prompt_fields(
    lines: list[str], report: LintReport
) -> tuple[list[tuple[int, str]], list[PromptField]]:
    preamble: list[tuple[int, str]] = []
    fields: list[PromptField] = []
    for number, raw in enumerate(lines, 1):
        match = FIELD_RE.match(raw.lstrip())
        if match and match.group(1) in KNOWN_FIELDS:
            fields.append(PromptField(match.group(1), number, match.group(2).strip()))
            continue
        if match and "_" in match.group(1):
            report.warnings.append(f"line {number}: unknown field '{match.group(1)}:'")
        (fields[-1].body if fields else preamble).append((number, raw))
    return preamble, fields


def is_context_ir(prompt: str) -> bool:
    """Whether the prompt is written in (or attempts) the Context-IR format."""
    for raw in prompt.splitlines():
        line = raw.strip()
        match = FIELD_RE.match(line)
        if match and match.group(1) in CONTEXT_IR_MARKERS:
            return True
        if line.startswith((I2VA_PREFIX, FL2VA_PREFIX)):
            return True
    return "[Shot 1]" in prompt


def lint_context_ir(
    prompt: str,
    *,
    mode: str | None = None,
    duration: int | None = None,
    images: int | None = None,
    videos: int | None = None,
    audios: int | None = None,
) -> LintReport:
    """Check a prompt against the official H3 Context-IR format.

    ``mode`` is the mode the request implies (see expected_h3_mode); media
    counts and duration are skipped when None.
    """
    report = LintReport()
    placeholders = list(dict.fromkeys(PLACEHOLDER_RE.findall(prompt)))
    if placeholders:
        shown = ", ".join(placeholders[:5]) + (", ..." if len(placeholders) > 5 else "")
        report.errors.append(f"unfilled template placeholders: {shown}")
    text = prompt.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    lines = text.split("\n")
    preamble, fields = split_prompt_fields(lines, report)
    names = {item.name for item in fields}
    if not fields:
        report.errors.append(
            "no Context-IR fields found; T2VA/I2VA/FL2VA prompts use integrated_multimodal_description:, "
            "Ref2VA prompts start with subject_definitions:"
        )
    elif names & REF_ONLY_FIELDS and "integrated_multimodal_description" in names:
        report.errors.append(
            "the prompt mixes integrated_multimodal_description: with Ref2VA sections; use one format"
        )
    elif names & REF_ONLY_FIELDS:
        report.mode = "ref2va"
        lint_ref_sections(lines, preamble, fields, report, duration, images, videos, audios)
    else:
        report.mode, alignment = base_mode(preamble, report)
        lint_base_fields(lines, fields, report, report.mode, alignment, duration)
    if mode and report.mode and report.mode != mode:
        report.errors.insert(
            0,
            f"the prompt is written for {MODE_NAMES[report.mode]} but the request is {MODE_NAMES[mode]}; "
            f"either {MODE_REQUESTS[report.mode]}, or rewrite the prompt ({MODE_FORMATS[mode]})",
        )
    lint_language(text, report)
    return report


def base_mode(
    preamble: list[tuple[int, str]], report: LintReport
) -> tuple[str | None, tuple[int, str] | None]:
    content = [(number, raw.strip()) for number, raw in preamble if raw.strip()]
    if not content:
        return "t2va", None
    number, line = content[0]
    if len(content) > 1:
        report.errors.append(
            f"line {content[1][0]}: only the alignment line may come before integrated_multimodal_description:"
        )
    if line.startswith(I2VA_PREFIX):
        if normalize_space(line) != I2VA_ALIGNMENT:
            report.errors.append(f"line {number}: I2VA alignment line must read exactly: {I2VA_ALIGNMENT}")
        mode = "i2va"
    elif line.startswith(FL2VA_PREFIX):
        mode = "fl2va"
    else:
        report.errors.append(
            f"line {number}: text before integrated_multimodal_description: must be the I2VA or FL2VA "
            f"alignment line ({PROMPT_GUIDE} section 6)"
        )
        return None, None
    blanks = sum(1 for other, raw in preamble if other > number and not raw.strip())
    if len(content) == 1 and blanks != 1:
        report.warnings.append(
            f"line {number}: leave exactly one blank line between the alignment line and "
            "integrated_multimodal_description:"
        )
    return mode, (number, line)


def check_field_order(fields: list[PromptField], expected: tuple[str, ...], report: LintReport) -> None:
    names = [item.name for item in fields]
    for name in expected:
        count = names.count(name)
        if count == 0:
            report.errors.append(f"missing field {name}:")
        elif count > 1:
            report.errors.append(f"field {name}: appears {count} times")
    first_seen = list(dict.fromkeys(names))
    if first_seen != [name for name in expected if name in first_seen]:
        report.errors.append("fields must appear in this order: " + ", ".join(f"{name}:" for name in expected))


def lint_base_fields(
    lines: list[str],
    fields: list[PromptField],
    report: LintReport,
    mode: str | None,
    alignment: tuple[int, str] | None,
    duration: int | None,
) -> None:
    check_field_order(fields, BASE_FIELDS, report)
    for index, item in enumerate(fields):
        if index and lines[item.line - 2].strip():
            report.warnings.append(f"line {item.line}: put a blank line before {item.name}:")
        extra = [number for number, text in item.body if text.strip()]
        if not item.inline and extra:
            report.warnings.append(f"line {item.line}: start the {item.name}: text on the same line as the field name")
        elif item.inline and extra:
            report.warnings.append(f"line {extra[0]}: keep {item.name}: on one line")
    sections = first_fields(fields)
    shot_count = 0
    description = sections.get("integrated_multimodal_description")
    if description is not None:
        text = description.text
        if not text:
            report.errors.append("integrated_multimodal_description: is empty")
        else:
            if not text.startswith("[Shot 1]"):
                report.errors.append("integrated_multimodal_description: must start with [Shot 1]")
            shot_count = check_shots(text, "integrated_multimodal_description", report, duration)
    check_sound_fields(sections, report)
    if mode == "fl2va" and alignment is not None:
        check_fl2va_alignment(alignment, shot_count, duration, report)


def check_shots(text: str, where: str, report: LintReport, duration: int | None) -> int:
    markers = list(SHOT_RE.finditer(text))
    if not markers:
        report.errors.append(f"{where}: no [Shot 1] marker")
        return 0
    numbers = [int(marker.group(1)) for marker in markers]
    valid = numbers == list(range(1, len(numbers) + 1))
    if not valid:
        report.errors.append(
            f"{where}: number shots [Shot 1], [Shot 2], ... in order (found {', '.join(map(str, numbers))})"
        )
    starts = [0.0]
    for index, marker in enumerate(markers):
        label = marker.group(1)
        cut = CUT_RE.match(text, marker.end())
        if index == 0:
            if cut:
                report.errors.append(
                    f"{where}: [Shot {label}] must not have a timestamp; the first shot starts at 00:00.000"
                )
            continue
        if cut is None:
            report.errors.append(
                f"{where}: [Shot {label}] needs a timestamp: '[Shot {label}] At MM:SS.mmm, the camera cuts to ...'"
            )
            valid = False
            continue
        start = int(cut.group(1)) * 60 + int(cut.group(2)) + int(cut.group(3)) / 1000
        if start <= starts[-1]:
            report.errors.append(
                f"{where}: [Shot {label}] at {format_timestamp(start)} must come after the previous shot "
                f"at {format_timestamp(starts[-1])}"
            )
            valid = False
        elif duration is not None and start >= duration:
            report.errors.append(
                f"{where}: [Shot {label}] at {format_timestamp(start)} is at or after the end of the "
                f"{duration}-second video"
            )
            valid = False
        starts.append(max(start, starts[-1]))
    if valid:
        ends = starts[1:] + ([float(duration)] if duration is not None else [])
        for index, (start, end) in enumerate(zip(starts, ends), 1):
            if end - start < 1.5:
                report.warnings.append(
                    f"{where}: [Shot {index}] lasts {end - start:.2f} s; shots shorter than about 1.5 s "
                    "are often skipped or smeared"
                )
    return len(markers)


def check_sound_fields(sections: dict[str, PromptField], report: LintReport) -> None:
    for name, limit in SOUND_SENTENCE_LIMITS.items():
        item = sections.get(name)
        if item is None:
            continue
        text = item.text
        if not text:
            report.errors.append(f"{name}: is empty; describe the sound or write N/A")
            continue
        if re.fullmatch(r"N/A\.?", text):
            continue
        if "<d>" in text:
            report.warnings.append(f"{name}: contains dialogue; dialogue belongs in the description with a speaker ID")
        sentences = len(SENTENCE_END_RE.findall(text)) or 1
        if sentences > limit:
            report.warnings.append(f"{name}: has {sentences} sentences; keep it to 1-{limit}")


def check_fl2va_alignment(
    alignment: tuple[int, str], shot_count: int, duration: int | None, report: LintReport
) -> None:
    number, line = alignment
    expected = FL2VA_ALIGNMENT.format(
        shot=shot_count or "N",
        seconds=f"{duration:.2f}" if duration is not None else "S.SS",
    )
    match = FL2VA_ALIGNMENT_RE.fullmatch(normalize_space(line))
    if match is None:
        report.errors.append(f"line {number}: FL2VA alignment line must read exactly: {expected}")
        return
    shot, seconds = int(match.group("shot")), match.group("seconds")
    if shot_count and shot != shot_count:
        report.errors.append(
            f"line {number}: Picture 2 must come from the last shot (Shot {shot_count}), not Shot {shot}"
        )
    if duration is None:
        report.warnings.append(
            f"line {number}: pass --duration to check that Picture 2 aligns with the end of the video "
            f"(the prompt says {seconds} seconds)"
        )
    elif seconds != f"{duration:.2f}":
        report.errors.append(
            f"line {number}: Picture 2 must align with the {duration:.2f}-second mark, the end of the "
            f"requested {duration}-second video (the prompt says {seconds})"
        )
    if shot_count > 1:
        report.warnings.append(
            "FL2VA works best as one continuous shot; when the frames need a cut, generate two I2VA shots instead"
        )


def lint_ref_sections(
    lines: list[str],
    preamble: list[tuple[int, str]],
    fields: list[PromptField],
    report: LintReport,
    duration: int | None,
    images: int | None,
    videos: int | None,
    audios: int | None,
) -> None:
    stray = [number for number, raw in preamble if raw.strip()]
    if stray:
        report.errors.append(
            f"line {stray[0]}: a Ref2VA prompt starts with subject_definitions:; move or delete the text before it"
        )
    check_field_order(fields, REF_SECTIONS, report)
    for index, item in enumerate(fields):
        if index and lines[item.line - 2].strip():
            report.warnings.append(f"line {item.line}: put a blank line before {item.name}:")
        if item.inline:
            report.warnings.append(f"line {item.line}: start the {item.name}: content on the next line")
    sections = first_fields(fields)
    defined, mentioned = check_definitions(sections.get("subject_definitions"), report)
    tags = check_summary(sections.get("summary"), mentioned, report)
    shot_count = 0
    detail = sections.get("detailed_description")
    if detail is not None:
        text = detail.text
        if not text:
            report.errors.append("detailed_description: is empty")
        else:
            if text.startswith("[Shot 1]"):
                report.warnings.append(
                    "detailed_description: open with one or two overall style sentences before [Shot 1]"
                )
            words = len(text.split())
            if words < 300 and "video editing" not in tags:
                report.warnings.append(
                    f"detailed_description: has {words} words; generation prompts work best with about 350-500"
                )
            shot_count = check_shots(text, "detailed_description", report, duration)
    check_retention(sections.get("retention_analysis"), defined, shot_count, report)
    check_sound_fields(sections, report)
    check_labels("\n".join(lines), defined, report, images, videos, audios)


def check_definitions(
    item: PromptField | None, report: LintReport
) -> tuple[set[tuple[str, int]], set[tuple[str, int]]]:
    defined: set[tuple[str, int]] = set()
    mentioned: set[tuple[str, int]] = set()
    if item is None:
        return defined, mentioned
    for number, line in item.numbered_lines:
        match = DEFINITION_RE.match(line)
        if match:
            defined.add((match.group(1), int(match.group(2))))
        else:
            report.warnings.append(f"line {number}: definitions read '<Subject N> is ...', one per line")
        mentioned.update((kind, int(value)) for kind, value in LABEL_RE.findall(line))
    if not defined:
        report.errors.append(
            "subject_definitions: defines no labels; write lines such as '<Subject 1> is the ... in <Picture 1>.'"
        )
    return defined, mentioned


def check_summary(item: PromptField | None, mentioned: set[tuple[str, int]], report: LintReport) -> list[str]:
    if item is None:
        return []
    text = item.text
    if not text:
        report.errors.append("summary: is empty")
        return []
    match = re.match(r"\[([^\]]*)\]", text)
    if not match:
        report.errors.append("summary: must start with bracketed task tags, for example [reference generation]")
        return []
    tags = [tag.strip() for tag in match.group(1).split("+")]
    unknown = [tag for tag in tags if tag not in SUMMARY_TAGS]
    if unknown:
        report.errors.append(
            "summary: unknown task tag " + ", ".join(repr(tag) for tag in unknown)
            + "; use " + ", ".join(SUMMARY_TAGS)
        )
    repeated = sorted({tag for tag in tags if tags.count(tag) > 1})
    if repeated:
        report.errors.append("summary: repeated task tag " + ", ".join(repr(tag) for tag in repeated))
    for kind, value in dict.fromkeys(LABEL_RE.findall(text)):
        if (kind, int(value)) not in mentioned:
            report.errors.append(f"summary: <{kind} {value}> is not introduced in subject_definitions:")
    return tags


def check_retention(
    item: PromptField | None, defined: set[tuple[str, int]], shot_count: int, report: LintReport
) -> None:
    if item is None:
        return
    lines = item.numbered_lines
    if not lines:
        report.errors.append("retention_analysis: is empty")
        return
    if re.search(r"\(S\d", item.text):
        report.warnings.append("retention_analysis: leave out speaker IDs such as (S1)")
    covered: set[tuple[str, int]] = set()
    for number, line in lines:
        visual = RETENTION_VISUAL_RE.match(line)
        audio = RETENTION_AUDIO_RE.match(line)
        if visual:
            kind, value, shots, marker = visual.groups()
            covered.add((kind, int(value)))
            if marker not in VISUAL_RETENTION:
                report.warnings.append(
                    f"line {number}: '{marker}' is not a visual retention marker; use {', '.join(VISUAL_RETENTION)}"
                )
            for shot in SHOT_RE.findall(shots):
                if shot_count and int(shot) > shot_count:
                    report.warnings.append(f"line {number}: [Shot {shot}] is not in detailed_description:")
        elif audio:
            value, marker = audio.groups()
            covered.add(("Audio", int(value)))
            if marker not in AUDIO_RETENTION:
                report.warnings.append(
                    f"line {number}: '{marker}' is not an audio retention marker; use {', '.join(AUDIO_RETENTION)}"
                )
        else:
            report.warnings.append(
                f"line {number}: retention lines read '<Subject N> (appears in [Shot 1]): fully_preserved - ...' "
                "or '<Audio N>: reference - ...'"
            )
    missing = sorted(defined - covered, key=label_key)
    if missing:
        report.warnings.append(
            "retention_analysis: no line for " + ", ".join(f"<{kind} {value}>" for kind, value in missing)
        )


def check_labels(
    text: str,
    defined: set[tuple[str, int]],
    report: LintReport,
    images: int | None,
    videos: int | None,
    audios: int | None,
) -> None:
    used: dict[str, set[int]] = {kind: set() for kind in LABEL_KINDS}
    for kind, value in LABEL_RE.findall(text):
        used[kind].add(int(value))
    for value in sorted(used["Subject"]):
        if ("Subject", value) not in defined:
            report.errors.append(f"<Subject {value}> is used but never defined in subject_definitions:")
    subjects = sorted(used["Subject"])
    if subjects and subjects != list(range(1, len(subjects) + 1)):
        report.warnings.append("number Subject labels <Subject 1>, <Subject 2>, ... without gaps")
    # A reference video's soundtrack may be labelled as its own <Audio N>.
    audio_sources = None if audios is None or videos is None else audios + videos
    limits = (
        ("Picture", images, "--image", "--image file(s)"),
        ("Video", videos, "--reference-video", "--reference-video file(s)"),
        (
            "Audio",
            audio_sources,
            "--reference-audio",
            "audio source(s) (--reference-audio files plus --reference-video soundtracks)",
        ),
    )
    for kind, limit, flag, source in limits:
        if limit is None:
            continue
        for value in sorted(used[kind]):
            if not 1 <= value <= limit:
                report.errors.append(f"<{kind} {value}> has no matching reference; the request has {limit} {source}")
        if kind == "Audio" and videos:
            continue
        unused = [value for value in range(1, limit + 1) if value not in used[kind]]
        if unused:
            report.warnings.append(
                ", ".join(f"<{kind} {value}>" for value in unused)
                + f" never referenced; label every {flag} file in request order"
            )


def lint_language(text: str, report: LintReport) -> None:
    opens, closes = text.count("<d>"), text.count("</d>")
    if opens != closes:
        report.errors.append(f"unbalanced dialogue tags: {opens} <d> and {closes} </d>")
    for match in DIALOGUE_RE.finditer(text):
        spoken = match.group(1)
        if not LANGUAGE_TAG_RE.match(spoken):
            report.warnings.append(f"dialogue {shorten(spoken)!r} has no language tag; write <d>[English] ...</d>")
        context = SPEAKER_CONTEXT_RE.sub("", text[max(0, match.start() - 200) : match.start()])
        if not SPEAKER_RE.search(context):
            report.warnings.append(
                f"dialogue {shorten(spoken)!r} has no speaker ID; write '... (S1) says: <d>...</d>'"
            )
    prose = QUOTED_RE.sub(" ", DIALOGUE_RE.sub(" ", text))
    found = CJK_RE.search(prose)
    if found:
        snippet = normalize_space(prose[max(0, found.start() - 12) : found.start() + 24])
        report.errors.append(
            f"non-English text outside <d>...</d> and quoted on-screen text near {snippet!r}; "
            "write the prompt in English"
        )
    directives = sorted({normalize_space(match.group(0).lower()) for match in DIRECTIVE_RE.finditer(prose)})
    if directives:
        report.warnings.append(
            "instruction wording (" + ", ".join(directives) + "); H3 reads the prompt as a description of the "
            "video, so describe what is seen and heard instead"
        )


def expected_h3_mode(model: str, images: int | None, videos: int | None = 0, audios: int | None = 0) -> str | None:
    """Context-IR mode implied by an H3 request, or None when it cannot be told."""
    if model == H3_MAX_REFERENCE_MODEL:
        return "ref2va"
    if model in (H3_MAX_T2V_MODEL, MINIMAX_H3_MODEL):
        return "t2va"
    if model == H3_MAX_MODEL and (videos or audios):
        return "ref2va"
    if images is None:
        return None
    if model in (H3_MAX_I2V_MODEL, MINIMAX_H3_I2V_MODEL):
        return {1: "i2va", 2: "fl2va"}.get(images)
    if model == H3_MAX_MODEL:
        return {0: "t2va", 1: "i2va"}.get(images)
    return None


def route_h3_model(model: str, images: int, videos: int, audios: int) -> str:
    """Resolve the generic H3 Max SKU to the one its media implies."""
    if model != H3_MAX_MODEL:
        return model
    # Explicit reference media needs the reference SKU because there may be no
    # image in the request to trigger new-api's mode inference.
    if videos or audios:
        return H3_MAX_REFERENCE_MODEL
    if images >= 2:
        raise VideoGenerationError(
            "h3-max with two or more images is ambiguous; use --model h3-max-i2v for first/last frames "
            "or --model h3-max-reference for reference images"
        )
    return model


def _load_akasha_recharge() -> Any:
    """Process-level path-verified singleton for shared/akasha_recharge.py."""
    import importlib.util

    cache_attr = "_akasha_recharge_singleton"
    cached = globals().get(cache_attr)
    here = Path(__file__).resolve().parent
    candidates = [
        here / "akasha_recharge.py",
        here.parents[3] / "shared" / "akasha_recharge.py",
        here.parents[2] / "shared" / "akasha_recharge.py",
    ]
    path: Path | None = None
    for candidate in candidates:
        try:
            if candidate.is_file():
                path = candidate.resolve()
                break
        except OSError:
            continue
    if path is None:
        raise VideoGenerationError(
            "shared akasha_recharge helper not found; install from monorepo so "
            "shared/akasha_recharge.py resolves via symlink"
        )

    def _matches(module: Any) -> bool:
        try:
            file_value = getattr(module, "__file__", None)
            return bool(file_value) and Path(file_value).resolve() == path
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    if cached is not None and _matches(cached) and hasattr(cached, "RechargeController"):
        return cached

    for existing in list(sys.modules.values()):
        if existing is None or not hasattr(existing, "RechargeController"):
            continue
        if _matches(existing):
            globals()[cache_attr] = existing
            return existing

    for existing in list(sys.modules.values()):
        loader = getattr(existing, "load_akasha_recharge_module", None)
        if callable(loader) and _matches(existing):
            module = loader(Path(__file__))
            globals()[cache_attr] = module
            return module

    stable_name = "akasha_grimoire_shared_akasha_recharge"
    stable = sys.modules.get(stable_name)
    if stable is not None and _matches(stable):
        globals()[cache_attr] = stable
        return stable
    module_name = stable_name
    if stable is not None and not _matches(stable):
        module_name = f"{stable_name}_{abs(hash(str(path))) & 0xFFFFFFFF:x}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise VideoGenerationError(
            "shared akasha_recharge helper not found; install from monorepo so "
            "shared/akasha_recharge.py resolves via symlink"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    loader = getattr(module, "load_akasha_recharge_module", None)
    if callable(loader):
        module = loader(Path(__file__))
    globals()[cache_attr] = module
    return module


def normalize_base_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VideoGenerationError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VideoGenerationError("base URL must not contain userinfo, query, or fragment")
    path = parsed.path.rstrip("/")
    if path.rsplit("/", 1)[-1] != "v1":
        path += "/v1"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def resolve_base_url(explicit: str | None) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    raw = credentials.resolve_base_url(
        ("H3_KLING_VIDEO_BASE_URL",), explicit=explicit, default=DEFAULT_BASE_URL
    )
    return normalize_base_url(raw)


def read_api_key(explicit_base_url: str | None = None, timeout: float = 10) -> str:
    credentials = _load_akasha_recharge().load_akasha_credentials_module(Path(__file__))
    try:
        found = credentials.select_credential(
            explicit_base_url=explicit_base_url,
            timeout=timeout,
        )
    except credentials.CredentialError as exc:
        raise VideoGenerationError(str(exc)) from exc
    return found.api_key


def read_response(response: object) -> tuple[bytes, str]:
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise VideoGenerationError("endpoint response exceeds 256 MiB")
    return data, response.headers.get("Content-Type", "")


def request(
    base_url: str,
    api_key: str,
    path: str,
    timeout: float,
    payload: dict | None = None,
    *,
    controller: Any | None = None,
) -> tuple[bytes, str]:
    recharge = _load_akasha_recharge()
    body = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "akasha-h3-kling-video/1.0",
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    http_request = urllib.request.Request(
        base_url + path,
        data=body,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )

    def once() -> tuple[bytes, str]:
        try:
            with urllib.request.urlopen(http_request, timeout=timeout) as response:
                return read_response(response)
        except urllib.error.HTTPError as exc:
            raw = exc.read(64 * 1024)
            try:
                exc.close()
            except Exception:
                pass
            recharge.raise_quota_if_applicable(exc.code, raw, base_url=base_url)
            message = ""
            try:
                parsed = json.loads(raw)
                error = parsed.get("error")
                if isinstance(error, dict):
                    message = str(error.get("message") or "")
                message = message or str(parsed.get("message") or "")
            except (json.JSONDecodeError, AttributeError):
                pass
            raise VideoGenerationError(f"HTTP {exc.code}: {message or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise VideoGenerationError(f"request failed: {exc.reason}") from exc

    if controller is None:
        controller = recharge.RechargeController(
            api_key=api_key,
            base_url=base_url,
            request_timeout=timeout,
        )
    try:
        return controller.run(once)
    except recharge.AkashaRechargeError as exc:
        raise VideoGenerationError(str(exc)) from exc


def parse_json(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VideoGenerationError("endpoint returned non-JSON data") from exc
    if not isinstance(value, dict):
        raise VideoGenerationError("endpoint returned an unexpected JSON shape")
    return value


def task_id_from(response: dict) -> str:
    data = response.get("data")
    nested = data if isinstance(data, dict) else {}
    value = response.get("task_id") or response.get("id") or response.get("request_id") or nested.get("task_id")
    if not isinstance(value, str) or not value.strip():
        raise VideoGenerationError("task submission returned no task ID")
    return value.strip()


def task_state(response: dict) -> tuple[str, str]:
    data = response.get("data")
    nested = data if isinstance(data, dict) else {}
    state = str(nested.get("status") or response.get("status") or "").strip().lower()
    error = response.get("error")
    message = nested.get("fail_reason") or response.get("message") or ""
    if isinstance(error, dict):
        message = error.get("message") or message
    return state, str(message)


def wait_for_task(
    base_url: str,
    api_key: str,
    task_id: str,
    request_timeout: float,
    poll_timeout: float,
    poll_interval: float,
    controller: Any,
) -> dict:
    """Poll until the task succeeds and return the final task response."""
    deadline = time.monotonic() + poll_timeout
    quoted_id = urllib.parse.quote(task_id, safe="")
    while True:
        response = parse_json(
            request(
                base_url,
                api_key,
                f"/video/generations/{quoted_id}",
                request_timeout,
                controller=controller,
            )[0]
        )
        state, message = task_state(response)
        if state in SUCCESS_STATES:
            return response
        if state in FAILURE_STATES:
            raise VideoGenerationError(f"video task {state}: {message or 'upstream returned no reason'}")
        if time.monotonic() >= deadline:
            raise VideoGenerationError(f"video task did not finish within {poll_timeout:g} seconds")
        time.sleep(poll_interval)


def validate_public_https_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError("reference media must use an absolute public HTTPS URL without userinfo")
    return value


def non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a non-negative integer, got {value!r}") from None
    if number < 0:
        raise argparse.ArgumentTypeError(f"expected a non-negative integer, got {value!r}")
    return number


def validate_mp4(data: bytes, content_type: str) -> None:
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise VideoGenerationError(f"video result is not an MP4 (content-type={content_type or 'unknown'})")


def write_output(path: Path, data: bytes, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise VideoGenerationError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def resolve_prompt(args: argparse.Namespace) -> str:
    if args.prompt is not None:
        prompt = args.prompt.strip()
        if not prompt:
            raise VideoGenerationError("prompt is empty")
        return prompt
    path = Path(args.prompt_file).expanduser()
    try:
        info = path.stat()
    except OSError as exc:
        raise VideoGenerationError(f"cannot read prompt file: {path}: {exc.strerror or exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise VideoGenerationError(f"prompt file is not a regular file: {path}")
    if info.st_size > MAX_PROMPT_FILE_BYTES:
        raise VideoGenerationError(f"prompt file exceeds {MAX_PROMPT_FILE_BYTES} bytes: {path}")
    try:
        prompt = path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise VideoGenerationError(f"cannot read UTF-8 prompt file: {path}") from exc
    if not prompt:
        raise VideoGenerationError(f"prompt file is empty: {path}")
    return prompt


def reference_media(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """Effective reference video/audio URLs: CLI values, else --metadata-json lists."""
    loaded: dict = {}
    if args.metadata_json:
        try:
            value = json.loads(args.metadata_json)
        except json.JSONDecodeError:
            value = {}  # metadata_from reports the parse error
        if isinstance(value, dict):
            loaded = value

    def pick(cli_values: list[str], key: str) -> list[str]:
        if cli_values:
            return list(cli_values)
        raw = loaded.get(key)
        return [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []

    return (
        pick(args.reference_video, "reference_video_urls"),
        pick(args.reference_audio, "reference_audio_urls"),
    )


def sends_aspect_ratio(model: str, profile: dict, args: argparse.Namespace) -> bool:
    # One image on the generic H3 Max SKU makes it image-to-video, where the
    # frame sets the ratio.
    return profile["uses_aspect_ratio"] and not (model == H3_MAX_MODEL and len(args.image) == 1)


def resolve_model(
    args: argparse.Namespace, reference_video: list[str], reference_audio: list[str]
) -> tuple[str, dict]:
    raw_model = args.model.strip()
    model = MODEL_ALIASES.get(raw_model.lower(), raw_model)
    model = route_h3_model(model, len(args.image), len(reference_video), len(reference_audio))
    profile = MODEL_PROFILES.get(model)
    if profile is None:
        supported = ", ".join(MODEL_PROFILES)
        raise VideoGenerationError(f"unsupported video model: {raw_model}; choose one of: {supported}")

    requested_aspect_ratio = args.aspect_ratio
    text_only = model == H3_MAX_T2V_MODEL or (model == H3_MAX_MODEL and not args.image)
    if text_only and args.aspect_ratio == "adaptive":
        raise VideoGenerationError(
            f"{model} text-to-video does not support adaptive; choose one of: {', '.join(H3_TEXT_ASPECT_RATIOS)}"
        )
    if args.aspect_ratio is None:
        args.aspect_ratio = profile.get("default_aspect_ratio", "16:9")
    if args.duration is None:
        args.duration = profile["default_duration"]
    if args.duration not in profile["durations"]:
        allowed = list(profile["durations"])
        summary = f"{allowed[0]}-{allowed[-1]}" if allowed == list(range(allowed[0], allowed[-1] + 1)) else ", ".join(map(str, allowed))
        raise VideoGenerationError(f"{model} duration must be one of: {summary} seconds")
    if profile["uses_aspect_ratio"] and args.aspect_ratio not in profile["aspect_ratios"]:
        raise VideoGenerationError(
            f"{model} aspect ratio must be one of: {', '.join(profile['aspect_ratios'])}"
        )
    if requested_aspect_ratio is not None and not sends_aspect_ratio(model, profile, args):
        notice("WARNING", "--aspect-ratio is ignored for image-to-video; the first frame sets the aspect ratio")
    if args.image and not profile["supports_images"]:
        raise VideoGenerationError(f"{model} is text-to-video and does not accept --image")
    if profile["requires_images"] and not args.image:
        raise VideoGenerationError(f"{model} requires at least one --image reference frame")
    if len(args.image) > profile["max_images"]:
        frames = " (first and last frame)" if profile["max_images"] == 2 else ""
        raise VideoGenerationError(f"{model} accepts at most {profile['max_images']} --image values{frames}")
    reference_count = len(args.image) + len(reference_video) + len(reference_audio)
    if profile.get("requires_references") and reference_count == 0:
        raise VideoGenerationError(f"{model} requires at least one reference image, video, or audio")
    if reference_count > profile.get("max_references", profile["max_images"]):
        raise VideoGenerationError(
            f"{model} accepts at most {profile.get('max_references', profile['max_images'])} reference files"
        )
    if (reference_video or reference_audio) and model != H3_MAX_REFERENCE_MODEL:
        raise VideoGenerationError(f"{model} does not accept reference video/audio files")
    if model == H3_MAX_REFERENCE_MODEL:
        # Limits from fal's H3 overview; the H3 Max page only states 12 files in total.
        for label, count, limit in (
            ("images", len(args.image), 9),
            ("reference videos", len(reference_video), 3),
            ("reference audios", len(reference_audio), 3),
        ):
            if count > limit:
                notice("WARNING", f"{count} {label}: fal's H3 overview allows at most {limit}; the request may be rejected")
        if reference_audio and not (args.image or reference_video):
            notice(
                "WARNING",
                "reference audio without an image or video: fal requires H3 audio references to be paired "
                "with at least one image or video",
            )
    if args.resolution and args.resolution not in profile["resolutions"]:
        allowed = ", ".join(profile["resolutions"]) or "not configurable"
        raise VideoGenerationError(f"{model} resolution must be one of: {allowed}")
    if args.mode and not profile["supports_mode"]:
        raise VideoGenerationError(f"{model} does not accept --mode")
    if args.sound is not None and not profile["supports_sound"]:
        raise VideoGenerationError(f"{model} does not accept --sound/--no-sound")
    prompt_limit = profile.get("prompt_limit")
    if prompt_limit and len(args.prompt) > prompt_limit:
        raise VideoGenerationError(f"{model} prompt must not exceed {prompt_limit} characters")
    if (args.negative_prompt or args.cfg_scale is not None) and model != KLING_25_T2V_MODEL:
        raise VideoGenerationError(f"{model} does not accept --negative-prompt or --cfg-scale")
    if args.cfg_scale is not None:
        if not 0 <= args.cfg_scale <= 1 or abs(args.cfg_scale * 10 - round(args.cfg_scale * 10)) > 1e-9:
            raise VideoGenerationError("--cfg-scale must be between 0 and 1 in increments of 0.1")
    if model not in H3_MAX_FAMILY and (args.prompt_expansion != "auto" or args.seed is not None):
        raise VideoGenerationError(f"{model} does not accept --prompt-expansion or --seed (H3 Max only)")
    return model, profile


def metadata_from(
    args: argparse.Namespace,
    model: str,
    profile: dict,
    reference_video: list[str],
    reference_audio: list[str],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if args.metadata_json:
        try:
            loaded = json.loads(args.metadata_json)
        except json.JSONDecodeError as exc:
            raise VideoGenerationError(f"--metadata-json is invalid JSON: {exc.msg}") from exc
        if not isinstance(loaded, dict):
            raise VideoGenerationError("--metadata-json must decode to an object")
        metadata.update(loaded)

    duration: int | str = str(args.duration) if profile["duration_as_string"] else args.duration
    metadata["duration"] = duration
    if sends_aspect_ratio(model, profile, args):
        metadata["aspect_ratio"] = args.aspect_ratio
    resolution = args.resolution or profile["default_resolution"]
    if resolution:
        metadata["resolution"] = resolution
    if args.negative_prompt:
        metadata["negative_prompt"] = args.negative_prompt
    if args.cfg_scale is not None:
        metadata["cfg_scale"] = args.cfg_scale
    if model in (MINIMAX_H3_I2V_MODEL, H3_MAX_I2V_MODEL):
        metadata["image_url"] = args.image[0]
        if len(args.image) == 2:
            metadata["end_image_url"] = args.image[1]
    if model == H3_MAX_REFERENCE_MODEL:
        if reference_video:
            metadata["reference_video_urls"] = reference_video
        if reference_audio:
            metadata["reference_audio_urls"] = reference_audio
    if model in H3_MAX_FAMILY:
        if args.prompt_expansion != "auto":
            metadata["prompt_expansion_mode"] = args.prompt_expansion
        elif "prompt_expansion_mode" not in metadata and is_context_ir(args.prompt):
            # A Context-IR prompt is already in the expander's output format;
            # the gateway default (balanced) would rewrite it again.
            metadata["prompt_expansion_mode"] = "disabled"
        if args.seed is not None:
            metadata["seed"] = args.seed
    if model == KLING_3_MODEL:
        metadata["mode"] = args.mode or "pro"
        metadata["sound"] = args.sound if args.sound is not None else False
        metadata.setdefault("multi_shots", False)
        if args.image:
            metadata["image_urls"] = args.image
    return metadata


def preflight_prompt(
    args: argparse.Namespace,
    model: str,
    metadata: dict[str, Any],
    reference_video: list[str],
    reference_audio: list[str],
) -> list[str]:
    """Lint H3 Context-IR prompts before submission; returns the lint warnings."""
    if model not in H3_FAMILY:
        return []
    expansion = metadata.get("prompt_expansion_mode")
    if not is_context_ir(args.prompt):
        if CJK_RE.search(QUOTED_RE.sub(" ", DIALOGUE_RE.sub(" ", args.prompt))):
            notice(
                "WARNING",
                "the prompt contains Chinese/Japanese/Korean text; H3 follows English Context-IR prompts, "
                f"so keep production notes in the local shot plan and send an English prompt ({PROMPT_GUIDE})",
            )
        if model not in H3_MAX_FAMILY:
            notice("NOTE", f"plain-text prompt: {model} follows English Context-IR prompts most closely ({PROMPT_GUIDE})")
        elif expansion == "disabled":
            notice(
                "NOTE",
                "plain-text prompt with prompt expansion disabled: H3 Max expects Context-IR, so expect weak "
                f"prompt adherence ({PROMPT_GUIDE})",
            )
        else:
            notice(
                "NOTE",
                f"plain-text prompt: the gateway's {expansion or 'balanced'} prompt expansion rewrites it into "
                "Context-IR before generation (saved in the sidecar when the gateway returns expanded_prompt); "
                f"production shots should send their own Context-IR ({PROMPT_GUIDE})",
            )
        return []
    if expansion in ("balanced", "quality"):
        notice(
            "NOTE",
            f"prompt expansion {expansion} will rewrite this Context-IR prompt; leave --prompt-expansion at auto "
            "or pass disabled to send it verbatim",
        )
    if args.skip_lint:
        notice("WARNING", "--skip-lint: submitting without the local Context-IR check")
        return []
    images, videos, audios = len(args.image), len(reference_video), len(reference_audio)
    report = lint_context_ir(
        args.prompt,
        mode=expected_h3_mode(model, images, videos, audios),
        duration=args.duration,
        images=images,
        videos=videos,
        audios=audios,
    )
    if report.errors:
        details = "\n".join(f"  - {error}" for error in report.errors)
        raise VideoGenerationError(
            f"Context-IR lint failed (nothing was submitted):\n{details}\n"
            "fix the prompt, or pass --skip-lint to submit anyway"
        )
    for warning in report.warnings:
        notice("WARNING", warning)
    return report.warnings


def prepare_request(args: argparse.Namespace) -> tuple[str, dict[str, Any], dict[str, Any], list[str]]:
    """Validate everything that can be checked offline and build the payload."""
    args.prompt = resolve_prompt(args)
    reference_video, reference_audio = reference_media(args)
    model, profile = resolve_model(args, reference_video, reference_audio)
    metadata = metadata_from(args, model, profile, reference_video, reference_audio)
    lint_warnings = preflight_prompt(args, model, metadata, reference_video, reference_audio)
    payload: dict[str, Any] = {
        "model": model,
        "prompt": args.prompt,
        "duration": args.duration,
        "metadata": metadata,
    }
    if model in {H3_MAX_MODEL, H3_MAX_I2V_MODEL, H3_MAX_REFERENCE_MODEL, MINIMAX_H3_I2V_MODEL}:
        # Keep image references in the standard task envelope so new-api can
        # classify generic H3 Max image/reference requests before mapping
        # model-native metadata.
        payload["images"] = list(args.image)
    if reference_video:
        payload["reference_video_urls"] = reference_video
    if reference_audio:
        payload["reference_audio_urls"] = reference_audio
    return model, metadata, payload, lint_warnings


def parse_rate(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    numerator, _, denominator = value.partition("/")
    try:
        rate = float(numerator) / float(denominator or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return round(rate, 3) if rate > 0 else None


def _int_or_zero(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def summarize_probe(probe: object) -> dict[str, Any] | None:
    if not isinstance(probe, dict):
        return None
    streams = [stream for stream in probe.get("streams") or () if isinstance(stream, dict)]
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        return None
    format_info = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    try:
        duration = round(float(format_info.get("duration")), 3)
    except (TypeError, ValueError):
        duration = None
    return {
        "codec": str(video.get("codec_name") or "unknown"),
        "width": _int_or_zero(video.get("width")),
        "height": _int_or_zero(video.get("height")),
        "fps": parse_rate(video.get("avg_frame_rate")),
        "duration": duration,
        "audio_streams": sum(1 for stream in streams if stream.get("codec_type") == "audio"),
    }


def probe_media(path: Path) -> dict[str, Any] | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        return summarize_probe(json.loads(completed.stdout))
    except json.JSONDecodeError:
        return None


def report_media(path: Path, requested_duration: int) -> dict[str, Any] | None:
    media = probe_media(path)
    if media is None:
        print("MEDIA unavailable (ffprobe not found or failed)")
        return None
    fps = f"{media['fps']:g}" if media["fps"] else "unknown"
    duration = f"{media['duration']:.2f}" if media["duration"] is not None else "unknown"
    print(
        f"MEDIA codec={media['codec']} pixels={media['width']}x{media['height']} fps={fps} "
        f"duration={duration} audio_streams={media['audio_streams']}"
    )
    if media["duration"] is not None and abs(media["duration"] - requested_duration) > 1:
        notice(
            "WARNING",
            f"output duration {media['duration']:.2f} s differs from the requested {requested_duration} s",
        )
    return media


def find_value(value: object, key: str, depth: int = 0) -> Any:
    """First non-empty value stored under ``key`` in a nested response."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        found = value.get(key)
        if found is not None and found != "" and found != [] and found != {}:
            return found
        children = list(value.values())
    elif isinstance(value, list):
        children = value
    else:
        return None
    for child in children:
        found = find_value(child, key, depth + 1)
        if found is not None:
            return found
    return None


def without_urls(value: Any) -> Any:
    """Copy of a request value with media URLs replaced, for the sidecar."""
    if isinstance(value, dict):
        return {key: without_urls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [without_urls(item) for item in value]
    if isinstance(value, str) and value.lower().startswith(("http:", "https:", "data:")):
        return "<url omitted>"
    return value


def run_generate(args: argparse.Namespace) -> None:
    model, metadata, payload, lint_warnings = prepare_request(args)
    output = Path(args.output).expanduser().resolve()
    if output.exists() and not args.overwrite:
        raise VideoGenerationError(f"output already exists: {output} (pass --overwrite to replace it)")
    base_url = resolve_base_url(args.base_url)
    api_key = read_api_key(base_url, args.timeout)
    recharge = _load_akasha_recharge()
    recharge.validate_cli_recharge_usd(getattr(args, "recharge_usd", None))
    controller = recharge.RechargeController(
        api_key=api_key,
        base_url=base_url,
        cli_recharge_usd=getattr(args, "recharge_usd", None),
        request_timeout=args.timeout,
    )
    submitted = parse_json(
        request(
            base_url,
            api_key,
            "/video/generations",
            args.timeout,
            payload,
            controller=controller,
        )[0]
    )
    task_id = task_id_from(submitted)
    final = wait_for_task(
        base_url,
        api_key,
        task_id,
        args.timeout,
        args.poll_timeout,
        args.poll_interval,
        controller,
    )
    raw, content_type = request(
        base_url,
        api_key,
        f"/videos/{urllib.parse.quote(task_id, safe='')}/content",
        args.download_timeout,
        controller=controller,
    )
    validate_mp4(raw, content_type)
    write_output(output, raw, args.overwrite)
    print(f"OK task_id={task_id} output={output} bytes={len(raw)}")

    media = report_media(output, args.duration)
    expanded = find_value(final, "expanded_prompt") or find_value(submitted, "expanded_prompt")
    if expanded is not None and not isinstance(expanded, str):
        expanded = json.dumps(expanded, ensure_ascii=False)
    result_seed = find_value(final, "seed")
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task_id": task_id,
        "model": model,
        "output": str(output),
        "prompt_file": str(Path(args.prompt_file).expanduser().resolve()) if args.prompt_file else None,
        "prompt": args.prompt,
        "duration": args.duration,
        "request": {
            "metadata": without_urls(metadata),
            "images": len(args.image),
            "reference_videos": len(payload.get("reference_video_urls", [])),
            "reference_audios": len(payload.get("reference_audio_urls", [])),
        },
        "seed": result_seed if result_seed is not None else args.seed,
        "expanded_prompt": expanded,
        "media": media,
        "lint_warnings": lint_warnings,
    }
    sidecar = output.with_name(output.name + ".json")
    try:
        write_output(sidecar, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode(), True)
    except OSError as exc:
        notice("WARNING", f"could not write sidecar {sidecar}: {exc}")
        if expanded:
            print(f"EXPANDED_PROMPT chars={len(expanded)} (sidecar not written; printed below)")
            print(expanded)
        return
    print(f"SIDECAR {sidecar}")
    if expanded:
        print(f"EXPANDED_PROMPT chars={len(expanded)} (saved in the sidecar)")


def run_lint(args: argparse.Namespace) -> None:
    prompt = resolve_prompt(args)
    counts = [args.images, args.reference_videos, args.reference_audios]
    if any(count is not None for count in counts):
        # Describing any media describes the request: unlisted kinds are absent.
        counts = [count or 0 for count in counts]
    images, videos, audios = counts
    model = None
    mode = None
    if args.model:
        raw_model = args.model.strip()
        model = MODEL_ALIASES.get(raw_model.lower(), raw_model)
        if model not in H3_FAMILY:
            raise VideoGenerationError(f"lint checks MiniMax H3 Context-IR prompts; {raw_model} is not an H3 model")
        model = route_h3_model(model, images or 0, videos or 0, audios or 0)
        mode = expected_h3_mode(model, images, videos, audios)
    report = lint_context_ir(prompt, mode=mode, duration=args.duration, images=images, videos=videos, audios=audios)
    if model and args.duration is not None and args.duration not in MODEL_PROFILES[model]["durations"]:
        durations = MODEL_PROFILES[model]["durations"]
        report.errors.insert(0, f"{model} duration must be {durations[0]}-{durations[-1]} seconds")
    for error in report.errors:
        print(f"error: {error}")
    for warning in report.warnings:
        print(f"warning: {warning}")
    status = "FAILED" if report.errors else "OK"
    print(
        f"LINT {status} mode={MODE_NAMES.get(report.mode or '', 'unknown')} "
        f"errors={len(report.errors)} warnings={len(report.warnings)}"
    )
    if report.errors:
        raise VideoGenerationError("Context-IR lint failed; fix the errors above")


def add_prompt_source(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="prompt text")
    source.add_argument(
        "--prompt-file",
        metavar="PATH",
        help="UTF-8 prompt file; use this for H3 Context-IR prompts",
    )


def build_parser() -> argparse.ArgumentParser:
    recharge = _load_akasha_recharge()
    recharge_parent = recharge.recharge_parent_parser()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        help=f"OpenAI-compatible host or /v1 API root (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument("--timeout", type=float, default=30)
    recharge.add_recharge_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser(
        "generate",
        parents=[recharge_parent],
        help="submit a video task (billed), wait for it, and download the MP4",
    )
    generate.add_argument(
        "--model",
        default=H3_MAX_MODEL,
        help=(
            "model ID or alias (default: h3-max; legacy H3: h3/minimax-h3; "
            "H3 Max: h3-max-t2v, h3-max-i2v, h3-max-reference; Kling: kling-3, kling-2.5-t2v)"
        ),
    )
    add_prompt_source(generate)
    generate.add_argument("--duration", type=int, metavar="SECONDS", help="model default: H3 Max=5, H3=6, Kling=5")
    generate.add_argument(
        "--aspect-ratio",
        default=None,
        help=(
            "H3 Max text-to-video defaults to 16:9 (no adaptive); reference defaults to adaptive; "
            "image-to-video uses the frame's ratio"
        ),
    )
    generate.add_argument("--resolution", help="MiniMax H3: 768P or 2K; H3 Max: 480P, 768P, or 1080P")
    generate.add_argument(
        "--image",
        action="append",
        default=[],
        type=validate_public_https_url,
        help="public HTTPS image URL; repeat in order (first/last frame, or reference images)",
    )
    generate.add_argument("--reference-video", action="append", default=[], type=validate_public_https_url)
    generate.add_argument("--reference-audio", action="append", default=[], type=validate_public_https_url)
    generate.add_argument("--mode", choices=("std", "pro", "4K"))
    generate.add_argument("--sound", action=argparse.BooleanOptionalAction, default=None)
    generate.add_argument("--negative-prompt")
    generate.add_argument("--cfg-scale", type=float)
    generate.add_argument(
        "--prompt-expansion",
        choices=("auto", "disabled", "balanced", "quality"),
        default="auto",
        help=(
            "H3 Max prompt_expansion_mode; auto sends disabled for Context-IR prompts and leaves plain "
            "prompts to the gateway default (balanced)"
        ),
    )
    generate.add_argument("--seed", type=non_negative_int, help="H3 Max seed for reproducible A/B runs")
    generate.add_argument(
        "--skip-lint",
        action="store_true",
        help="submit an H3 Context-IR prompt even when the local lint finds errors",
    )
    generate.add_argument(
        "--metadata-json",
        help="advanced model-native input object; validated core fields override duplicates",
    )
    generate.add_argument("--poll-timeout", type=float, default=1800)
    generate.add_argument("--poll-interval", type=float, default=5)
    generate.add_argument("--download-timeout", type=float, default=120)
    generate.add_argument("--output", required=True)
    generate.add_argument("--overwrite", action="store_true")
    generate.set_defaults(handler=run_generate)

    lint = subparsers.add_parser(
        "lint",
        help="check an H3 Context-IR prompt locally (no network, no billing)",
        description=(
            "Check an H3 prompt against the official Context-IR format. Pass --model, --duration and the "
            f"media counts to also check it against the request. Writing guide: {PROMPT_GUIDE}"
        ),
    )
    add_prompt_source(lint)
    lint.add_argument("--model", help="H3 model or alias the prompt will be sent to")
    lint.add_argument("--duration", type=int, metavar="SECONDS", help="requested duration in seconds")
    lint.add_argument("--images", type=non_negative_int, metavar="N", help="number of --image files")
    lint.add_argument("--reference-videos", type=non_negative_int, metavar="N", help="number of --reference-video files")
    lint.add_argument("--reference-audios", type=non_negative_int, metavar="N", help="number of --reference-audio files")
    lint.set_defaults(handler=run_lint)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.handler(args)
        return 0
    except (VideoGenerationError, OSError, ValueError) as exc:
        sys.stdout.flush()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
