"""Real offline integration tests. Run with SHOWRIG_RENDER_TESTS=1."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from showrig.project import probe
from showrig.web import create_app
from tests.test_studio import BACKEND, HEADERS


@unittest.skipUnless(os.environ.get("SHOWRIG_RENDER_TESTS") == "1", "Set SHOWRIG_RENDER_TESTS=1 to run real media exports")
class RenderTests(unittest.TestCase):
    """Exercise uploads, preview/export, failure preservation, and cancellation."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="showrig-render-tests-"))
        cls.app = create_app(cls.root / "films")
        cls.client = TestClient(cls.app, backend_options=BACKEND)
        cls.client.__enter__()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=480x270:r=30:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.root / "clip.mp4")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cls.root / "clip.mp4"), "-frames:v", "1", str(cls.root / "picture.png")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=4", "-ar", "48000", str(cls.root / "recording.wav")], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        print(f"\nRender verification artifacts: {cls.root}")

    def create(self, title):
        response = self.client.post("/api/projects", headers=HEADERS, json={"title": title, "template": "demo"})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def save(self, project, board):
        response = self.client.put(f"/api/projects/{project}/", headers=HEADERS, json=board)
        self.assertEqual(response.status_code, 200, response.text)

    def upload(self, project, filename):
        with (self.root / filename).open("rb") as source:
            response = self.client.post(f"/api/projects/{project}/assets", headers=HEADERS, files={"file": (filename, source)})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["path"]

    def render(self, project, mode="preview"):
        response = self.client.post(f"/api/projects/{project}/render", headers=HEADERS, json={"mode": mode})
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def wait(self, job, success=True):
        deadline = time.time() + 300
        while time.time() < deadline:
            status = self.client.get(f"/api/jobs/{job['id']}").json()
            if status["status"] not in ("starting", "running", "cancelling"):
                if success:
                    self.assertEqual(status["status"], "succeeded", json.dumps(status, indent=2))
                while self.app.state.jobs.process is not None:
                    time.sleep(.05)
                return status
            time.sleep(.3)
        self.app.state.jobs.cancel(job["id"])
        self.fail("Render exceeded five minutes")

    def test_01_text_only_preview_and_final_in_three_shapes(self):
        for shape, width, height in (("landscape", 640, 360), ("portrait", 360, 640), ("square", 480, 480)):
            with self.subTest(shape=shape):
                project = self.create("Verification " + shape)
                board = project["board"]
                board["format"] = {"width": width, "height": height, "fps": 30}
                board["scenes"] = [{"kind": "card", "id": "card", "title": "A clear idea, beautifully told", "tagline": "Every frame is made on this computer.", "lines": []}]
                if shape == "portrait":
                    board["style"].update(design="terminal", titles="typewriter")
                self.save(project["id"], board)
                preview = self.wait(self.render(project["id"]))
                self.assertEqual(preview["output"]["format"]["width"], width // 2)
                final = self.wait(self.render(project["id"], "final"))
                self.assertEqual(final["output"]["format"]["width"], width)
                movie = self.root / "films" / project["id"] / final["output"]["files"]["mp4"]
                info = probe(movie)
                self.assertEqual((info["width"], info["height"]), (width, height))
                self.assertTrue(info["audio"])
                response = self.client.get(f"/api/projects/{project['id']}/outputs/final/mp4", headers={"Range": "bytes=0-31"})
                self.assertEqual(response.status_code, 206)
                self.assertEqual(len(response.content), 32)

    def test_02_mixed_media_recording_captions_and_preserved_export(self):
        project = self.create("Mixed media verification")
        pid, board = project["id"], project["board"]
        image = self.upload(pid, "picture.png")
        video = self.upload(pid, "clip.mp4")
        recording = self.upload(pid, "recording.wav")
        board["format"] = {"width": 640, "height": 360, "fps": 30}
        board["voice"]["source"] = "files"
        board["scenes"] = [{"kind": "segment", "id": "media", "title": "Images, clips, and your own sound", "tagline": "A complete local production.", "lines": ["A test recording checks the timing of this caption."], "voice": [recording], "duration": 10,
                            "shots": [{"file": image, "in": 0, "weight": 1}, {"file": video, "in": 0, "weight": 2}]}]
        self.save(pid, board)
        job = self.render(pid, "final")
        duplicate = self.client.post(f"/api/projects/{pid}/render", headers=HEADERS, json={"mode": "preview"})
        self.assertEqual(duplicate.status_code, 409)
        result = self.wait(job)
        self.assertIn("srt", result["output"]["files"])
        root = self.root / "films" / pid
        edit = (root / result["output"]["files"]["fcproj"]).read_text()
        sizes = re.findall(r'"caption_tracks":\s*\[\s*\{.*?"style":\s*\{.*?"size":\s*([\d.]+)', edit, re.S)
        self.assertEqual([float(s) for s in sizes], [34.0], "FilmCraft scales caption size by frame height")
        previous = (root / "out" / "final.json").read_bytes()
        board["scenes"][0]["shots"][0]["in"] = 999
        self.save(pid, board)
        failed = self.wait(self.render(pid, "final"), success=False)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual((root / "out" / "final.json").read_bytes(), previous)

    def test_03_cancel_and_resume(self):
        project = self.create("Cancellation verification")
        pid, board = project["id"], project["board"]
        board["format"] = {"width": 640, "height": 360, "fps": 30}
        board["scenes"] = [{"kind": "card", "id": "card", "title": "Cancellation test", "tagline": "The next render should still work.", "lines": []}]
        self.save(pid, board)
        job = self.render(pid)
        response = self.client.post(f"/api/jobs/{job['id']}/cancel", headers=HEADERS, json={})
        self.assertEqual(response.status_code, 200)
        result = self.wait(job, success=False)
        self.assertEqual(result["status"], "cancelled")
        self.wait(self.render(pid))


if __name__ == "__main__":
    unittest.main()
