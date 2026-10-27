"""Editing and re-running a film, without FilmCraft: stable ids and frames, provenance gates, the diff/reconcile helpers,
and the speech QC alignment."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from showrig import plan, qc, readback, reconcile, sources
from showrig.board import normalize
from showrig.project import Film


def film_with(board: dict) -> tuple[Film, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory(prefix="showrig-contract-")
    root = Path(tmp.name)
    (root / "showrig.json").write_text(json.dumps(normalize(board, draft=True)))
    return Film.load(root), tmp


BOARD = {"title": "T", "format": "1080p30", "voice": {"source": "tts"},
         "scenes": [{"kind": "card", "id": "a", "title": "A", "lines": ["One line."],
                     "image": {"file": "pic.png"}},
                    {"kind": "segment", "id": "b", "title": "B", "lines": ["Two."], "shots": [{"file": "x.mp4"}]}]}


class IdsAndFrames(unittest.TestCase):
    def sample(self) -> dict:
        return {"video": [{"kind": "backdrop", "scene": "a", "start": 0.0, "in": 0.0, "duration": 4.0133},
                          {"kind": "footage", "scene": "b", "shot": 1, "start": 4.0133, "in": 1.5, "duration": 3.3},
                          {"kind": "footage", "scene": "b", "shot": 2, "start": 7.3133, "in": 0.0, "duration": 2.0}],
                "titles": [{"scene": "a", "start": 0.3, "duration": 3.4}],
                "narration": [{"id": "a-01", "scene": "a", "start": 0.8, "duration": 1.9},
                              {"id": "b-01", "scene": "b", "start": 4.8, "duration": 1.0},
                              {"id": "b-02", "scene": "b", "start": 6.2, "duration": 1.0}],
                "captions": [{"scene": "a", "text": "x", "start": 0.8, "duration": 1.9}],
                "notes": [{"scene": "b", "text": "n", "start": 4.3, "duration": 2.0}],
                "images": [{"scene": "a", "start": 0.3, "duration": 3.4}]}

    def test_ids_come_from_scene_and_role_only(self):
        p = self.sample()
        plan.identify(p, 30)
        self.assertEqual([e["id"] for e in p["video"]], ["a/backdrop", "b/shot1", "b/shot2"])
        self.assertEqual([e["id"] for e in p["narration"]], ["a/voice1", "b/voice1", "b/voice2"])
        self.assertEqual(p["narration"][0]["line"], "a-01")
        self.assertEqual((p["titles"][0]["id"], p["notes"][0]["id"], p["images"][0]["id"], p["captions"][0]["id"]),
                         ("a/title", "b/note", "a/image", "a/cap1"))
        q = self.sample()
        for e in q["video"]:
            e["start"] += 0.5  # different timing, same ids
        plan.identify(q, 30)
        self.assertEqual([e["id"] for e in q["video"]], [e["id"] for e in p["video"]])

    def test_frames_are_whole_and_neighbours_stay_contiguous(self):
        p = self.sample()
        plan.identify(p, 30)
        v = p["video"]
        for a, b in zip(v, v[1:]):
            self.assertEqual(a["start_f"] + a["dur_f"], b["start_f"])
        self.assertTrue(all(isinstance(e["start_f"], int) and isinstance(e["dur_f"], int) for e in v))
        self.assertEqual(v[1]["in_f"], 45)
        self.assertEqual(v[1]["start"], v[1]["start_f"] / 30)

    def test_duplicate_ids_are_refused(self):
        p = self.sample()
        p["video"].append(dict(p["video"][1]))
        with self.assertRaises(SystemExit):
            plan.identify(p, 30)


class Provenance(unittest.TestCase):
    def test_supplied_media_without_licence_is_flagged_and_generated_is_not(self):
        film, tmp = film_with(BOARD)
        self.addCleanup(tmp.cleanup)
        got = {s["ref"]: s["status"] for s in sources.collect(film)}
        self.assertEqual(got["a/image"], "FLAG")
        self.assertEqual(got["b/shot1"], "FLAG")
        self.assertEqual(got["generated:voice"], "ok")

    def test_strict_gate_blocks_only_the_final_render(self):
        film, tmp = film_with({**BOARD, "provenance": {"gate": "strict"}})
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(SystemExit) as e:
            sources.gate(film, final=True)
        self.assertIn("a/image", str(e.exception))
        with mock.patch("builtins.print"):
            sources.gate(film, final=False)  # a draft only warns

    def test_set_licence_resolves_a_flag(self):
        film, tmp = film_with({**BOARD, "provenance": {"gate": "strict"}})
        self.addCleanup(tmp.cleanup)
        sources.set_licence(film, "a/image", "CC0-1.0", "me", None)
        sources.set_licence(film, "b/shot1", "own work", None, None)
        again = Film.load(film.root)
        again.board = normalize(again.board, draft=True)
        self.assertEqual(sources.flags(again), [])
        sources.gate(again, final=True)

    def test_unknown_ref_is_a_useful_error(self):
        film, tmp = film_with(BOARD)
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(SystemExit):
            sources.set_licence(film, "zzz/shot1", "x", None, None)


class Readback(unittest.TestCase):
    def test_beat_id_is_the_front_of_the_clip_name(self):
        self.assertEqual(readback.beat_id("clip/shot1 · clip.mp4"), "clip/shot1")
        self.assertEqual(readback.beat_id("music · score (calm)"), "music")
        self.assertIsNone(readback.beat_id("image.png"))
        self.assertIsNone(readback.beat_id("my edit · v2"))

    def test_srt_parsing(self):
        cues = readback.parse_srt("1\n00:00:00,800 --> 00:00:03,867\nHello there.\n\n2\n00:00:05,500 --> 00:00:09,267\nTwo\nlines\n")
        self.assertEqual(cues, [{"text": "Hello there.", "start": 0.8, "end": 3.867},
                                {"text": "Two lines", "start": 5.5, "end": 9.267}])

    def test_overlap_rule(self):
        self.assertTrue(reconcile._overlaps((0, 10), (9, 20)))
        self.assertFalse(reconcile._overlaps((0, 10), (10, 20)))  # touching is not overlapping


class SpeechQC(unittest.TestCase):
    def test_a_masked_word_fails_and_a_deleted_line_is_not_expected(self):
        film, tmp = film_with({**BOARD, "qc": {"asr": "fail", "minRecall": 0.8},
                               "scenes": [{"kind": "card", "id": "a", "title": "A",
                                           "lines": ["The quick brown fox jumps over the lazy dog."]},
                                          {"kind": "card", "id": "b", "title": "B", "lines": ["Nothing to see here."]}]})
        self.addCleanup(tmp.cleanup)
        video = film.root / "out.mp4"
        video.write_bytes(b"")
        heard = "The quick brown fox over the dog. Nothing to see here."  # "jumps" and "lazy" masked
        with mock.patch.object(qc, "asr", return_value=(heard, "fake")):
            r = qc.speech(film, video)
        self.assertFalse(r["ok"])
        a = next(line for line in r["lines"] if line["id"] == "a/voice1")
        self.assertEqual(a["missing"], ["jumps", "lazy"])
        (film.out).mkdir(exist_ok=True)
        (film.out / "manifest.json").write_text(json.dumps({"deleted": ["a/voice1"], "beats": []}))
        with mock.patch.object(qc, "asr", return_value=("Nothing to see here.", "fake")):
            self.assertTrue(qc.speech(film, video)["ok"])

    def test_digits_and_number_words_compare_equal(self):
        self.assertEqual(qc.words("Install 7-Zip, 7zip.7zip!"), qc.words("install seven zip seven zip seven zip"))

    def test_no_transcriber_skips(self):
        film, tmp = film_with(BOARD)
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(qc, "asr", return_value=None):
            self.assertIn("skipped", qc.speech(film, film.root / "x.mp4"))


if __name__ == "__main__":
    unittest.main()
