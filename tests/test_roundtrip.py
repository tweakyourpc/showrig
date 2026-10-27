"""The round trip, for real: build, edit the FilmCraft project by hand (headless), change the storyboard, rebuild,
and check every hand edit survived. Run with SHOWRIG_RENDER_TESTS=1 (needs FilmCraft, EffectCraft and ffmpeg)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from showrig import cli, diff, manifest, reconcile, tools
from showrig.board import normalize
from showrig.project import Film

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "acceptance"
TICKS = 254016000000


@unittest.skipUnless(os.environ.get("SHOWRIG_RENDER_TESTS") == "1", "Set SHOWRIG_RENDER_TESTS=1 to run real builds")
class RoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="showrig-roundtrip-"))
        cls.root = cls.tmp / "film"
        with redirect_stdout(StringIO()):
            cli.main(["new", str(cls.root), "--answers", str(EXAMPLE / "core.json")])
            cls.make()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def make(cls, *extra):
        film = Film.load(cls.root)
        film.board = normalize(film.board)
        with redirect_stdout(StringIO()):
            cli.make(film, "render", False, **dict(extra))

    def film(self) -> Film:
        f = Film.load(self.root)
        f.board = normalize(f.board)
        return f

    def run_fc(self, commands: list[dict]) -> None:
        m = manifest.load(self.film())
        script = self.tmp / "edits.jsonl"
        script.write_text("".join(json.dumps(c) + "\n" for c in commands))
        r = subprocess.run([tools.filmcraft(), "--compact", "--project", str(self.root / m["project"]["path"]), "--save",
                            "run", str(script)], capture_output=True, text=True)
        self.assertTrue(all(json.loads(x)["ok"] for x in r.stdout.splitlines()), r.stdout + r.stderr)

    def test_round_trip(self):
        film = self.film()
        m = manifest.load(film)
        self.assertTrue(diff.compute(film)["unchanged"])
        self.assertTrue((film.out / f"{film.name}.otio").exists() and (film.out / "sources.lock").exists())
        beat = {b["id"]: b for b in m["beats"]}
        per = TICKS // m["fps"]
        self.run_fc([
            {"id": "timeline.move", "params": {"moves": [{"clip": beat["clip/title"]["clip"], "track": "V2",
                                                           "time": (beat["clip/title"]["start_f"] + 15) * per}], "insert": False}},
            {"id": "timeline.trim", "params": {"clip": beat["end/title"]["clip"], "edge": "out", "mode": "regular",
                                               "deltaFrames": -20}},
            {"id": "edit.clear", "params": {"clips": [beat["end/voice1"]["clip"]]}},
            {"id": "edit.label.rose", "params": {"clips": [beat["title/backdrop"]["clip"]]}},
        ])
        d = diff.compute(film)
        self.assertEqual({k: [c["change"] for c in v] for k, v in d["beats"].items()},
                         {"clip/title": ["moved"], "end/title": ["retimed"], "end/voice1": ["deleted"],
                          "title/backdrop": ["relabelled"]})
        with redirect_stdout(StringIO()):
            reconcile.lock(self.film(), "title/title", True)
        board = json.loads((self.root / "showrig.json").read_text())
        board["music"]["mood"] = "bright"
        next(s for s in board["scenes"] if s["id"] == "end")["duration"] = 8
        (self.root / "showrig.json").write_text(json.dumps(board, indent=2))
        self.make()
        film = self.film()
        m2 = manifest.load(film)
        b2 = {b["id"]: b for b in m2["beats"]}
        self.assertEqual(b2["clip/title"]["start_f"], beat["clip/title"]["start_f"] + 15)
        self.assertEqual(b2["end/title"]["dur_f"], beat["end/title"]["dur_f"] - 20)
        self.assertNotIn("end/voice1", b2)
        self.assertIn("end/voice1", m2["deleted"])
        self.assertEqual(b2["title/backdrop"]["label"], "Rose")
        self.assertIsNotNone(b2["title/title"]["lock"])
        self.assertGreater(b2["end/backdrop"]["dur_f"], beat["end/backdrop"]["dur_f"])  # untouched: retimed
        report = json.loads((film.out / "reconcile-report.json").read_text())
        self.assertIn("end/title", {c["id"] for c in report["conflicts"]})
        self.assertTrue((film.out / f"{film.name}.mp4").exists())
        with self.assertRaises(SystemExit):
            self.make(("fresh", True))  # a locked beat is never discarded silently
        with redirect_stdout(StringIO()):
            reconcile.lock(self.film(), "title/title", False)
        self.make(("restore", ("end/voice1",)))
        b3 = {b["id"]: b for b in manifest.load(self.film())["beats"]}
        self.assertIn("end/voice1", b3)
        self.assertIsNone(b3["title/title"]["lock"])


if __name__ == "__main__":
    unittest.main()
