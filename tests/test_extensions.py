"""Creative packs stay portable and cannot introduce executable operations."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from showrig.extensions import install, validate_pack
from showrig.studio import new_board, validate
from showrig.web import create_app

PACK = {"schema": 1, "id": "test-pack", "name": "Synthetic test pack", "author": "Tests", "license": "MIT",
        "templates": [{"id": "two-scenes", "name": "Two scenes", "prompts": ["First thought", "Second thought"]}],
        "themes": [{"id": "moss", "name": "Moss", "accent": "#A3CEB7", "background": "#182B28"}]}


class ExtensionsTests(unittest.TestCase):
    def test_rejects_code_paths_and_invalid_values(self):
        for change in ({"id": "../outside"}, {"command": "run"}, {"schema": 2}, {"templates": [None]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_pack({**PACK, **change})
        bad = copy.deepcopy(PACK)
        bad["themes"][0]["background"] = "url(https://remote)"
        with self.assertRaises(ValueError):
            validate_pack(bad)

    def test_existing_pack_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            install(Path(tmp), PACK)
            with self.assertRaises(ValueError):
                install(Path(tmp), PACK)

    @patch("showrig.web.subprocess.run")
    def test_pack_creation_selection_and_portability(self, run):
        run.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp))) as client:
            headers = {"X-Showrig-Request": "1"}
            self.assertEqual(client.post("/api/extensions", headers=headers, json=PACK).status_code, 201)
            template = next(t for t in client.get("/api/catalog").json()["templates"] if t.get("pack"))
            for indices in ([], [99], [0, 0], [{}], [True]):
                response = client.post("/api/projects", headers=headers, json={"title": "Test", "template": template["id"], "sceneIndices": indices})
                self.assertEqual(response.status_code, 422)
            response = client.post("/api/projects", headers=headers, json={"title": "Test", "template": template["id"], "sceneIndices": [1], "format": "square"})
            self.assertEqual(response.status_code, 201)
            board = response.json()["board"]
            self.assertEqual(len(board["scenes"]), 1)
            self.assertEqual(board["scenes"][0]["guidance"], "Second thought")
            self.assertEqual(board["format"]["width"], board["format"]["height"])
            board["style"].update(design="pack.test-pack.moss", accent="#A3CEB7", background="#182B28")
            with tempfile.TemporaryDirectory() as other:
                self.assertEqual(validate(board, Path(other), [Path(other)])["style"]["accent"], "#A3CEB7")

    def test_guidance_survives_reorder(self):
        board = new_board("Story", "demo")
        before = {s["id"]: s["guidance"] for s in board["scenes"]}
        board["scenes"].reverse()
        self.assertEqual(before, {s["id"]: s["guidance"] for s in board["scenes"]})
