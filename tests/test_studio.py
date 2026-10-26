"""Regression coverage for the local studio's data and job boundaries."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from showrig.board import normalize
from showrig.plan import build, caption_chunks
from showrig.project import Film, film_lock
from showrig.studio import estimate, new_board, validate
from showrig.web import create_app

HEADERS = {"X-Showrig-Request": "1"}
BACKEND = {"use_uvloop": True} if importlib.util.find_spec("uvloop") else {}


class StudioTests(unittest.TestCase):
    """Exercise the same HTTP interface used by the browser without a server."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="showrig-tests-")
        self.root = Path(self.temp.name) / "films"
        self.app = create_app(self.root)
        self.client = TestClient(self.app, backend_options=BACKEND)
        self.client.__enter__()
        response = self.client.post("/api/projects", headers=HEADERS, json={"title": "A real film", "template": "demo"})
        self.assertEqual(response.status_code, 201)
        self.project = response.json()
        self.id = self.project["id"]
        self.board = self.project["board"]

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def save(self, board):
        return self.client.put(f"/api/projects/{self.id}", headers=HEADERS, json=board)

    def test_identity_and_all_static_assets_are_local(self):
        identity = self.client.get("/whoami").json()
        self.assertEqual(identity["service"], "showrig")
        self.assertEqual(set(identity), {"service", "version", "pid", "startedAt", "host", "port"})
        html = self.client.get("/").text
        self.assertNotIn("https://", html)
        for resource in ("app.js", "style.css", "fonts/DejaVuSans.ttf"):
            self.assertEqual(self.client.get(f"/static/{resource}").status_code, 200)

    def test_save_reopen_and_reorder(self):
        self.board["scenes"][1]["title"] = "A useful detail"
        self.board["scenes"].reverse()
        response = self.save(self.board)
        self.assertEqual(response.status_code, 200, response.text)
        reopened = self.client.get(f"/api/projects/{self.id}").json()
        self.assertEqual(reopened["board"]["scenes"][0]["id"], "outro")
        self.assertEqual(reopened["board"]["scenes"][1]["title"], "A useful detail")
        self.assertGreater(reopened["estimate"]["seconds"], 0)

    def test_incomplete_recording_draft_can_be_saved_but_not_rendered(self):
        self.board["voice"]["source"] = "files"
        self.board["scenes"][0]["lines"] = ["One spoken line."]
        self.assertEqual(self.save(self.board).status_code, 200)
        response = self.client.post(f"/api/projects/{self.id}/render", headers=HEADERS, json={"mode": "preview"})
        self.assertEqual(response.status_code, 422)

    def test_path_and_scene_id_traversal_rejected(self):
        for sid in ("../escape", "/tmp/escape", "bad/id"):
            board = copy.deepcopy(self.board)
            board["scenes"][0]["id"] = sid
            self.assertEqual(self.save(board).status_code, 422)
        board = copy.deepcopy(self.board)
        board["music"].update(source="file", file="/etc/passwd")
        self.assertEqual(self.save(board).status_code, 422)
        response = self.client.get(f"/api/projects/{self.id}/media", params={"path": "../../etc/passwd"})
        self.assertEqual(response.status_code, 404)

    def test_bad_values_are_useful_errors(self):
        mutations = [("format", {"width": 0, "height": 1080, "fps": 30}), ("credits", {"enabled": True, "lines": ["bad"]}),
                     ("kind", 3), ("scenes", ["not a scene"])]
        for key, value in mutations:
            with self.subTest(key=key):
                board = copy.deepcopy(self.board)
                board[key] = value
                response = self.save(board)
                self.assertEqual(response.status_code, 422, response.text)
        board = copy.deepcopy(self.board)
        board["style"]["accent"] = "red;movie=/etc/passwd"
        self.assertEqual(self.save(board).status_code, 422)

    def test_online_capture_refused(self):
        self.board["scenes"][1].update(kind="segment", shots=[{"capture": {"url": "https://example.com", "actions": ["wait 1"]}}])
        response = self.save(self.board)
        self.assertEqual(response.status_code, 422)
        self.assertIn("local HTML", response.json()["detail"])

    def test_cross_origin_mutation_refused(self):
        self.assertEqual(self.client.put(f"/api/projects/{self.id}", json=self.board).status_code, 403)
        headers = {**HEADERS, "Origin": "https://unrelated.example"}
        self.assertEqual(self.client.put(f"/api/projects/{self.id}", headers=headers, json=self.board).status_code, 403)

    def test_missing_media_can_be_replaced(self):
        self.board["music"].update(source="file", file="assets/moved.wav")
        self.assertEqual(self.save(self.board).status_code, 200)
        reopened = self.client.get(f"/api/projects/{self.id}").json()
        self.assertEqual(reopened["missing"], ["assets/moved.wav"])
        self.board["music"].update(source="none", file=None)
        self.assertEqual(self.save(self.board).status_code, 200)
        self.assertFalse(self.client.get(f"/api/projects/{self.id}").json()["missing"])

    def test_unsupported_upload_rejected(self):
        response = self.client.post(f"/api/projects/{self.id}/assets", headers=HEADERS, files={"file": ("run.py", b"print('no')")})
        self.assertEqual(response.status_code, 422)

    def test_render_lock_blocks_save_and_second_producer(self):
        root = self.root / self.id
        with film_lock(root):
            self.assertEqual(self.save(self.board).status_code, 409)
            with self.assertRaises(SystemExit):
                with film_lock(root):
                    pass

    def test_legacy_export_stays_downloadable(self):
        out = self.root / self.id / "out"
        out.mkdir()
        (out / "a-real-film.mp4").write_bytes(b"test video fixture")
        response = self.client.get(f"/api/projects/{self.id}/outputs/final/mp4")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"test video fixture")
        self.assertEqual(self.client.get(f"/api/projects/{self.id}/outputs/preview/mp4").status_code, 404)


class TimingTests(unittest.TestCase):
    """Prevent short footage and long text from breaking the timeline."""

    def test_caption_chunks_handle_empty_and_unpunctuated_text(self):
        self.assertEqual(caption_chunks("", 0, 2), [])
        chunks = caption_chunks("a readable caption " * 20, 1, 12)
        self.assertTrue(all(len(c["text"]) <= 58 for c in chunks))
        self.assertAlmostEqual(sum(c["duration"] for c in chunks), 12, places=2)

    def test_content_timing_preserves_narration(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "work").mkdir()
            board = new_board("Test", "demo")
            board["scenes"] = [{"id": "segment", "kind": "segment", "title": "Picture", "tagline": "", "lines": ["Long narration"], "color": "#46d9b0", "shots": [{"file": "short.mp4", "in": 0, "weight": 1}]}]
            film = Film(root, board)
            with patch("showrig.plan.probe", return_value={"duration": 2}), patch("showrig.stages.footage.extend_clip", return_value=root / "held.mp4") as extend:
                plan = build(film, [{"scene": "segment", "text": "Long narration", "path": "voice.wav", "duration": 12}])
            self.assertGreaterEqual(plan["duration"], 13.5)
            self.assertGreaterEqual(plan["video"][-1]["duration"], 13.5)
            self.assertTrue(extend.called)

    def test_no_media_does_not_invoke_blender(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "work").mkdir()
            board = new_board("Test", "demo")
            board["style"]["showcase3d"] = True
            plan = build(Film(root, board), [])
            self.assertEqual(plan["stage"], [])


if __name__ == "__main__":
    unittest.main()
