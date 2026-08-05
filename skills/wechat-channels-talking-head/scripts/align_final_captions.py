#!/usr/bin/env python3
"""Create phrase-safe SRT captions from final-audio word timestamps."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PUNCTUATION = "，。！？；：、,.!?;:“”‘’（）()《》…—-"
STRONG_PUNCTUATION = "。！？!?；;"
SOFT_PUNCTUATION = "，、,：:"
DEFAULT_FILLERS = {"嗯", "呃", "啊"}
PARTICLES = "的地得着过"
NO_BREAK_BIGRAMS = {
    "一个",
    "这个",
    "那个",
    "今年",
    "去年",
    "目前",
    "开始",
    "非常",
    "极大",
    "很多",
}


@dataclass
class Unit:
    source: str
    display: str
    start: float
    end: float
    trailing: str = ""


@dataclass
class Caption:
    start: float
    end: float
    lines: list[str]


def _display_width(text: str) -> float:
    width = 0.0
    for char in text:
        if char.isspace():
            width += 0.35
        elif unicodedata.east_asian_width(char) in {"W", "F", "A"}:
            width += 1.0
        elif char in PUNCTUATION:
            width += 0.5
        else:
            width += 0.58
    return width


def _format_srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _validate_transcript(data: object) -> tuple[str, list[dict[str, object]]]:
    if not isinstance(data, dict):
        raise ValueError("transcript must be a JSON object")
    text = data.get("text")
    segments = data.get("segments")
    if not isinstance(text, str) or not isinstance(segments, list) or not segments:
        raise ValueError("transcript requires non-empty text and segments")
    previous_end = -math.inf
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(f"segment {index} must be an object")
        value = segment.get("text")
        start = segment.get("start")
        end = segment.get("end")
        if not isinstance(value, str) or not value:
            raise ValueError(f"segment {index} has invalid text")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError(f"segment {index} has invalid timestamps")
        if start < 0 or end < start or start + 1e-6 < previous_end:
            raise ValueError(f"segment {index} timestamps are not monotonic")
        previous_end = float(end)
    return text, segments


def _split_segment(segment: dict[str, object]) -> list[Unit]:
    text = "".join(
        char for char in str(segment["text"]) if not char.isspace() and char not in PUNCTUATION
    )
    start = float(segment["start"])
    end = float(segment["end"])
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+\-/]*", text):
        return [Unit(text, text, start, end)]
    chars = list(text)
    if not chars:
        return []
    duration = max(0.0, end - start)
    return [
        Unit(
            char,
            char,
            start + duration * index / len(chars),
            start + duration * (index + 1) / len(chars),
        )
        for index, char in enumerate(chars)
    ]


def _punctuation_after(text: str, source: str) -> dict[int, str]:
    """Map punctuation to a consumed non-punctuation character position."""
    clean_source = "".join(char for char in source if not char.isspace())
    source_index = 0
    after: dict[int, str] = {}
    pending_prefix = ""
    for char in text:
        if char.isspace():
            continue
        if char in PUNCTUATION:
            if source_index == 0:
                pending_prefix += char
            else:
                after[source_index] = after.get(source_index, "") + char
            continue
        if source_index >= len(clean_source) or char != clean_source[source_index]:
            raise ValueError("top-level text does not match concatenated segment text")
        source_index += 1
        if pending_prefix:
            after[source_index] = pending_prefix + after.get(source_index, "")
            pending_prefix = ""
    if source_index != len(clean_source):
        raise ValueError("top-level text is shorter than concatenated segment text")
    return after


def _attach_punctuation(units: list[Unit], transcript_text: str) -> None:
    source = "".join(unit.source for unit in units)
    punctuation = _punctuation_after(transcript_text, source)
    consumed = 0
    for unit in units:
        consumed += len(unit.source)
        unit.trailing = punctuation.get(consumed, "")
    for index in range(len(units) - 1):
        suffix = "".join(unit.source for unit in units[index + 1 : index + 3])
        lexical_exception = suffix.startswith(("的确", "地道", "得到"))
        if (
            units[index].trailing
            and units[index + 1].source[0] in PARTICLES
            and not lexical_exception
        ):
            units[index].trailing = re.sub(r"[。！？；，、,.!?;]+$", "", units[index].trailing)


def _load_terms(path: Path | None) -> tuple[list[str], dict[str, str]]:
    if path is None:
        return [], {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("terms file must be a JSON object")
    protected = data.get("protected_terms", [])
    replacements = data.get("replacements", {})
    if not isinstance(protected, list) or not all(isinstance(term, str) and term for term in protected):
        raise ValueError("protected_terms must be an array of non-empty strings")
    if not isinstance(replacements, dict) or not all(
        isinstance(source, str) and source and isinstance(display, str) and display
        for source, display in replacements.items()
    ):
        raise ValueError("replacements must map non-empty strings to non-empty strings")
    return list(dict.fromkeys(protected)), dict(replacements)


def _merge_phrases(
    units: list[Unit], protected: Iterable[str], replacements: dict[str, str]
) -> list[Unit]:
    phrases = sorted(set(protected) | set(replacements), key=len, reverse=True)
    if not phrases:
        return units
    output: list[Unit] = []
    index = 0
    while index < len(units):
        matched: tuple[str, int] | None = None
        for phrase in phrases:
            value = ""
            end_index = index
            while end_index < len(units) and len(value) < len(phrase):
                value += units[end_index].source
                end_index += 1
            if value == phrase:
                matched = phrase, end_index
                break
        if matched is None:
            output.append(units[index])
            index += 1
            continue
        phrase, end_index = matched
        group = units[index:end_index]
        output.append(
            Unit(
                source=phrase,
                display=replacements.get(phrase, phrase),
                start=group[0].start,
                end=group[-1].end,
                trailing=group[-1].trailing,
            )
        )
        index = end_index
    return output


def _drop_fillers(units: list[Unit], fillers: set[str]) -> list[Unit]:
    output: list[Unit] = []
    for unit in units:
        if unit.source in fillers:
            if unit.trailing and output:
                output[-1].trailing = _merge_trailing(output[-1].trailing, unit.trailing)
            continue
        output.append(unit)
    return output


def _merge_trailing(existing: str, incoming: str) -> str:
    combined = existing + incoming
    strong = [char for char in combined if char in STRONG_PUNCTUATION]
    if strong:
        return strong[0]
    soft = [char for char in combined if char in SOFT_PUNCTUATION]
    return soft[0] if soft else combined[:1]


def _caption_text(units: list[Unit]) -> str:
    return "".join(unit.display + unit.trailing for unit in units).strip()


def _candidate_score(units: list[Unit], cut: int, target_width: float) -> float:
    left = units[:cut]
    right = units[cut:]
    punctuation = left[-1].trailing
    gap = right[0].start - left[-1].end if right else 0.0
    score = -abs(_display_width(_caption_text(left)) - target_width)
    if any(char in STRONG_PUNCTUATION for char in punctuation):
        score += 120
    elif any(char in SOFT_PUNCTUATION for char in punctuation):
        score += 75
    score += min(max(gap, 0.0), 1.5) * 45
    next_text = right[0].display if right else ""
    if next_text in {"所以", "但是", "然而", "然后", "而且", "因为", "包括", "例如", "其实"}:
        score += 30
    if len(left) <= 2 or len(right) <= 1:
        score -= 25
    left_text = _caption_text(left).rstrip(PUNCTUATION)
    if left_text in {"因为", "所以", "但是", "然后", "而且", "包括", "例如"}:
        score -= 120
    if right and (left[-1].display[-1] + right[0].display[0]) in NO_BREAK_BIGRAMS:
        score -= 80
    if right and right[0].display[0] in PARTICLES:
        score -= 60
    return score


def _split_caption_units(
    units: list[Unit], max_width: float, max_duration: float
) -> list[list[Unit]]:
    chunks: list[list[Unit]] = []
    remaining = units
    while remaining:
        limit = 0
        for index in range(1, len(remaining) + 1):
            width = _display_width(_caption_text(remaining[:index]))
            duration = remaining[index - 1].end - remaining[0].start
            if index > 1 and (width > max_width or duration > max_duration):
                break
            limit = index
            if any(char in STRONG_PUNCTUATION for char in remaining[index - 1].trailing):
                break
        if limit >= len(remaining):
            chunks.append(remaining)
            break
        candidates = list(range(max(1, limit - 8), limit + 1))
        non_orphans = [
            value
            for value in candidates
            if _display_width(_caption_text(remaining[:value])) >= 4
            or any(char in STRONG_PUNCTUATION for char in remaining[value - 1].trailing)
        ]
        if non_orphans:
            candidates = non_orphans
        cut = max(candidates, key=lambda value: _candidate_score(remaining, value, max_width * 0.82))
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    return chunks


def _line_break(units: list[Unit], max_line_width: float) -> list[str]:
    text = _caption_text(units)
    if _display_width(text) <= max_line_width or len(units) == 1:
        return [text]
    candidates = []
    for cut in range(1, len(units)):
        left = _caption_text(units[:cut])
        right = _caption_text(units[cut:])
        left_width = _display_width(left)
        right_width = _display_width(right)
        if left_width <= max_line_width and right_width <= max_line_width:
            score = abs(left_width - right_width)
            if any(char in SOFT_PUNCTUATION + STRONG_PUNCTUATION for char in units[cut - 1].trailing):
                score -= 3
            if (units[cut - 1].display[-1] + units[cut].display[0]) in NO_BREAK_BIGRAMS:
                score += 20
            if units[cut].display[0] in PARTICLES or units[cut - 1].display[-1] in "从向对把被在和与或":
                score += 12
            candidates.append((score, left, right))
    if not candidates:
        return [text]
    _, left, right = min(candidates, key=lambda item: item[0])
    return [left, right]


def build_captions(
    transcript: dict[str, object],
    protected_terms: list[str] | None = None,
    replacements: dict[str, str] | None = None,
    fillers: set[str] | None = None,
    max_chars_per_line: float = 15.0,
    max_duration: float = 4.8,
) -> tuple[list[Caption], dict[str, object]]:
    text, segments = _validate_transcript(transcript)
    units = [unit for segment in segments for unit in _split_segment(segment)]
    _attach_punctuation(units, text)
    protected = protected_terms or []
    replacement_map = replacements or {}
    units = _merge_phrases(units, protected, replacement_map)
    units = _drop_fillers(units, fillers or DEFAULT_FILLERS)
    if not units:
        raise ValueError("no displayable caption units remain")

    chunks: list[list[Unit]] = []
    sentence: list[Unit] = []
    for index, unit in enumerate(units):
        sentence.append(unit)
        if any(char in STRONG_PUNCTUATION for char in unit.trailing):
            chunks.extend(_split_caption_units(sentence, max_chars_per_line * 2, max_duration))
            sentence = []
    if sentence:
        chunks.extend(_split_caption_units(sentence, max_chars_per_line * 2, max_duration))

    captions = [
        Caption(chunk[0].start, chunk[-1].end, _line_break(chunk, max_chars_per_line))
        for chunk in chunks
    ]
    overlaps = sum(
        1 for previous, current in zip(captions, captions[1:]) if current.start < previous.end - 1e-6
    )
    too_many_lines = sum(1 for caption in captions if len(caption.lines) > 2)
    display = "".join("".join(caption.lines) for caption in captions)
    protected_violations = []
    for term in protected:
        expected = replacement_map.get(term, term)
        containing = [caption for caption in captions if expected in "".join(caption.lines)]
        if expected in display and not containing:
            protected_violations.append(expected)
    report = {
        "method": "final-audio timestamp alignment with phrase-safe semantic wrapping",
        "source_segments": len(segments),
        "caption_count": len(captions),
        "first_caption_start": captions[0].start,
        "last_caption_end": captions[-1].end,
        "overlap_count": overlaps,
        "max_display_lines": max(len(caption.lines) for caption in captions),
        "max_line_width": max(_display_width(line) for caption in captions for line in caption.lines),
        "line_width_violation_count": sum(
            1
            for caption in captions
            for line in caption.lines
            if _display_width(line) > max_chars_per_line + 1e-6
        ),
        "max_caption_seconds": max(caption.end - caption.start for caption in captions),
        "protected_term_violations": protected_violations,
        "removed_fillers": sorted(fillers or DEFAULT_FILLERS),
    }
    if overlaps or too_many_lines or protected_violations:
        raise ValueError(f"caption validation failed: {report}")
    return captions, report


def write_srt(captions: list[Caption], path: Path) -> None:
    blocks = []
    for index, caption in enumerate(captions, start=1):
        blocks.append(
            f"{index}\n{_format_srt_time(caption.start)} --> {_format_srt_time(caption.end)}\n"
            + "\n".join(caption.lines)
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--terms", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--max-chars-per-line", type=float, default=15.0)
    parser.add_argument("--max-duration", type=float, default=4.8)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    for path in [args.output, args.report]:
        if path and path.exists() and not args.overwrite:
            raise SystemExit(f"output already exists: {path}; pass --overwrite to replace it")
    if args.max_chars_per_line <= 0 or args.max_duration <= 0:
        raise SystemExit("line width and duration must be positive")
    try:
        transcript = json.loads(args.transcript.read_text(encoding="utf-8"))
        protected, replacements = _load_terms(args.terms)
        captions, report = build_captions(
            transcript,
            protected_terms=protected,
            replacements=replacements,
            max_chars_per_line=args.max_chars_per_line,
            max_duration=args.max_duration,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_srt(captions, args.output)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"caption alignment failed: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {len(captions)} captions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
