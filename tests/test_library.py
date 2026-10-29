"""Library cleanup, portable exports, and explicit setup at the browser boundary."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from showrig import library, runtime
from showrig.assets.prepare_edit import prepare
from showrig.platforms import acquire_lock, process_exists, release_lock
from showrig.studio import TEMPLATES, new_board, validate
from showrig.web import create_app
from tests.test_studio import BACKEND, HEADERS


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "films"
        self.app = create_app(self.root)
        self.client = TestClient(self.app, backend_options=BACKEND)
        self.client.__enter__()
        self.project = self.client.post("/api/projects", headers=HEADERS, json={"title": "My film", "template": "demo"}).json()
        self.id = self.project["id"]
        self.film = self.root / self.id

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def action(self, name, ids=None):
        return self.client.post("/api/library/actions", headers=HEADERS, json={"action": name, "ids": ids or [self.id]})

    def test_archive_and_restore_keep_source_and_media(self):
        media = self.film / "assets/recording.wav"
        media.write_bytes(b"test recording fixture")
        before = (self.film / "showrig.json").read_bytes()
        self.assertEqual(self.action("archive").json()["changed"], [self.id])
        self.assertTrue(self.client.get("/api/projects").json()[0]["archived"])
        self.assertEqual(self.action("trash").json()["changed"], [self.id])
        self.assertEqual(self.client.get("/api/projects").json(), [])
        self.assertEqual(len(self.client.get("/api/trash").json()), 1)
        self.assertEqual(self.action("restore").json()["changed"], [self.id])
        self.assertEqual((self.film / "showrig.json").read_bytes(), before)
        self.assertEqual(media.read_bytes(), b"test recording fixture")
        self.assertFalse(self.client.get("/api/projects").json()[0]["archived"])

    def test_permanent_delete_requires_trash_confirmation_and_origin_header(self):
        endpoint = f"/api/trash/{self.id}"
        self.assertEqual(self.client.request("DELETE", endpoint, headers=HEADERS, json={"confirm": self.id}).status_code, 422)
        self.action("trash")
        self.assertEqual(self.client.request("DELETE", endpoint, json={"confirm": self.id}).status_code, 403)
        self.assertEqual(self.client.request("DELETE", endpoint, headers=HEADERS, json={"confirm": "wrong"}).status_code, 422)
        response = self.client.request("DELETE", endpoint, headers=HEADERS, json={"confirm": self.id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/trash").json(), [])

    def test_partial_bulk_errors_are_explicit(self):
        data = self.action("archive", [self.id, "not-a-film"]).json()
        self.assertEqual(data["changed"], [self.id])
        self.assertEqual(data["errors"][0]["id"], "not-a-film")

    def test_library_cleanup_respects_other_renderers(self):
        with (self.app.state.jobs.root / "render.lock").open("a") as handle:
            acquire_lock(handle)
            try:
                self.assertEqual(self.action("trash").status_code, 409)
            finally:
                release_lock(handle)
        self.assertTrue(self.film.exists())

    def test_trash_parent_alias_cannot_delete_an_external_film(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        external = outside / self.id
        external.mkdir()
        (external / "showrig.json").write_text(json.dumps(self.project["board"]))
        (self.root / ".trash").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.client.get("/api/trash").json(), [])
        response = self.client.request("DELETE", f"/api/trash/{self.id}", headers=HEADERS, json={"confirm": self.id})
        self.assertEqual(response.status_code, 422)
        self.assertTrue(external.exists())

    def test_portable_package_keeps_assets_and_rebases_project_only(self):
        asset = self.film / "assets/clip.mp4"
        asset.write_bytes(b"test video fixture")
        out = self.film / "out"
        out.mkdir()
        original = json.dumps({"project": {"media": [{"path": str(asset)}]}})
        (out / "film.fcproj").write_text(original)
        response = self.client.get(f"/api/projects/{self.id}/package")
        self.assertEqual(response.status_code, 200, response.text)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            data = json.loads(archive.read(f"{self.id}/out/film.fcproj"))
            self.assertEqual(data["project"]["media"][0]["path"], "../assets/clip.mp4")
            self.assertEqual(archive.read(f"{self.id}/assets/clip.mp4"), b"test video fixture")
        self.assertEqual((out / "film.fcproj").read_text(), original)

    def test_import_portable_package_adds_film_to_library(self):
        asset = self.film / "assets/clip.mp4"
        asset.write_bytes(b"test video fixture")
        out = self.film / "out"
        out.mkdir()
        (out / "film.fcproj").write_text(json.dumps({"path": str(asset)}))
        package = library.package(self.film)
        try:
            response = self.client.post("/api/library/import", headers=HEADERS,
                                        files={"file": ("film-editable.zip", package.read_bytes(), "application/zip")})
        finally:
            package.unlink()
        self.assertEqual(response.status_code, 201, response.text)
        imported = response.json()["id"]
        self.assertEqual(self.client.get(f"/api/projects/{imported}").status_code, 200)
        self.assertTrue((self.root / imported / "assets/clip.mp4").is_file())

    def test_draft_package_is_not_advertised_as_a_rendered_project(self):
        response = self.client.get(f"/api/projects/{self.id}/package")
        self.assertEqual(response.status_code, 422)

    def test_external_media_refused_instead_of_silently_missing(self):
        outside = Path(self.temp.name) / "external.wav"
        outside.write_bytes(b"external test fixture")
        out = self.film / "out"
        out.mkdir()
        (out / "film.fcproj").write_text(json.dumps({"path": str(outside)}))
        self.assertEqual(self.client.get(f"/api/projects/{self.id}/package").status_code, 422)

    def test_missing_media_refused_instead_of_packaging_a_broken_timeline(self):
        out = self.film / "out"
        out.mkdir()
        (out / "film.fcproj").write_text(json.dumps({"path": str(self.film / "assets/missing.mp4")}))
        self.assertEqual(self.client.get(f"/api/projects/{self.id}/package").status_code, 422)

    def test_preparation_after_two_moves_preserves_timeline_edits(self):
        asset = self.film / "assets/clip.mp4"
        asset.write_bytes(b"test video fixture")
        out = self.film / "out"
        out.mkdir()
        (out / "film.fcproj").write_text(json.dumps({"path": "../assets/clip.mp4", "cuts": [1, 2]}))
        archive_path = library.package(self.film)
        extracted = Path(self.temp.name) / "extracted"
        try:
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extracted)
        finally:
            archive_path.unlink()
        root = extracted / self.id
        project = prepare(root)
        data = json.loads(project.read_text())
        self.assertEqual(data["path"], str(root / "assets/clip.mp4"))
        data["cuts"] = [1, 3, 7]
        project.write_text(json.dumps(data))
        moved = extracted / "moved-film"
        root.rename(moved)
        prepared = prepare(moved)
        data = json.loads(prepared.read_text())
        self.assertEqual(data["path"], str(moved / "assets/clip.mp4"))
        self.assertEqual(data["cuts"], [1, 3, 7])

    def test_restore_does_not_overwrite_a_new_film(self):
        self.action("trash")
        self.film.mkdir()
        (self.film / "showrig.json").write_text(json.dumps(new_board("New film", "blank")))
        data = self.action("restore").json()
        self.assertEqual(len(data["errors"]), 1)
        self.assertTrue((self.root / ".trash" / self.id).exists())


class SetupTests(unittest.TestCase):
    def test_every_template_makes_a_valid_empty_story_structure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for template in TEMPLATES:
                with self.subTest(template=template["id"]):
                    board = new_board("A real title", template["id"])
                    self.assertEqual(len(board["scenes"]), len(template["prompts"]))
                    self.assertEqual(len({s["id"] for s in board["scenes"]}), len(board["scenes"]))
                    validate(board, root, [root])
                    self.assertTrue(all(not s["lines"] for s in board["scenes"]))
            self.assertEqual(new_board("Portrait", "social")["format"]["width"], 1080)

    def test_dry_run_never_installs_or_downloads(self):
        with patch("showrig.runtime.subprocess.run") as run, contextlib.redirect_stdout(io.StringIO()) as text:
            runtime.install_voices(dry_run=True)
        run.assert_not_called()
        data = json.loads(text.getvalue())
        self.assertIn("--check", data["commands"][-1])
        self.assertIn("voices/af_heart.pt", data["commands"][-2][-1])

    def test_setup_has_separate_os_specific_native_library_steps(self):
        data = runtime.setup_catalog()
        self.assertEqual(set(data["systems"]), {"linux", "darwin", "win32"})
        self.assertIn("winget", data["systems"]["win32"]["core"])
        self.assertIn("brew", data["systems"]["darwin"]["core"])
        self.assertIn("espeak-ng", data["systems"]["linux"]["voiceSystem"])

    def test_optional_runtime_adds_only_existing_local_bin_folders(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"SHOWRIG_RUNTIME": folder}):
            before = os.environ["PATH"]
            try:
                (Path(folder) / "bin").mkdir()
                runtime.activate()
                self.assertIn(str(Path(folder) / "bin"), os.environ["PATH"].split(os.pathsep))
            finally:
                os.environ["PATH"] = before

    def test_process_probe_does_not_signal_a_running_posix_process(self):
        self.assertTrue(process_exists(os.getpid()))


if __name__ == "__main__":
    unittest.main()
