#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("align_final_captions.py")
SPEC = importlib.util.spec_from_file_location("align_final_captions", SCRIPT)
assert SPEC and SPEC.loader
align = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = align
SPEC.loader.exec_module(align)


def transcript(text: str, tokens: list[str], step: float = 0.24) -> dict[str, object]:
    segments = []
    now = 0.2
    for token in tokens:
        segments.append({"text": token, "start": now, "end": now + step})
        now += step
    return {"text": text, "segments": segments}


class AlignFinalCaptionsTests(unittest.TestCase):
    def test_uses_exact_final_audio_timestamps_and_drops_fillers(self) -> None:
        data = transcript("今天，嗯我们讲AI。", ["今", "天", "嗯", "我", "们", "讲", "AI"])
        captions, report = align.build_captions(data, protected_terms=["AI"])
        shown = "".join("".join(caption.lines) for caption in captions)
        self.assertNotIn("嗯", shown)
        self.assertIn("AI", shown)
        self.assertAlmostEqual(captions[0].start, 0.2)
        self.assertAlmostEqual(captions[-1].end, data["segments"][-1]["end"])
        self.assertEqual(report["overlap_count"], 0)

    def test_protected_terms_never_split_across_caption_or_line(self) -> None:
        tokens = list("尤其是陶哲轩他在去年开始研究形式化证明")
        data = transcript("尤其是陶哲轩，他在去年开始研究形式化证明。", tokens)
        captions, report = align.build_captions(
            data,
            protected_terms=["陶哲轩", "形式化证明"],
            max_chars_per_line=6,
            max_duration=2.2,
        )
        lines = [line for caption in captions for line in caption.lines]
        self.assertTrue(any("陶哲轩" in line for line in lines))
        self.assertTrue(any("形式化证明" in line for line in lines))
        self.assertEqual(report["protected_term_violations"], [])
        self.assertLessEqual(max(len(caption.lines) for caption in captions), 2)

    def test_replacement_inherits_source_time_range(self) -> None:
        data = transcript("其中一位就是Jacob。", list("其中一位就是") + ["Jacob"])
        captions, _ = align.build_captions(
            data,
            protected_terms=["Jacob"],
            replacements={"Jacob": "Jacob Tsimerman"},
        )
        self.assertIn("Jacob Tsimerman", "".join(captions[-1].lines))
        self.assertAlmostEqual(captions[-1].end, data["segments"][-1]["end"])

    def test_repairs_asr_punctuation_before_particle(self) -> None:
        data = transcript("今年的菲尔兹奖。的得主。", list("今年的菲尔兹奖的得主"))
        captions, _ = align.build_captions(data, protected_terms=["菲尔兹奖"])
        shown = "".join("".join(caption.lines) for caption in captions)
        self.assertIn("菲尔兹奖的得主", shown)
        self.assertNotIn("奖。的", shown)

    def test_preserves_sentence_break_before_lexical_deque(self) -> None:
        data = transcript("这是最后一年。的确很快。", list("这是最后一年的确很快"))
        captions, _ = align.build_captions(data)
        shown = "".join("".join(caption.lines) for caption in captions)
        self.assertIn("一年。的确", shown)

    def test_cli_protects_existing_output(self) -> None:
        data = transcript("测试。", list("测试"))
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript_path = Path(temp_dir, "transcript.json")
            output = Path(temp_dir, "captions.srt")
            transcript_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            output.write_text("keep", encoding="utf-8")
            with self.assertRaises(SystemExit):
                align.main(["--transcript", str(transcript_path), "--output", str(output)])
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
