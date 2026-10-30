"""Regression checks for guided navigation and authoritative export readiness."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from showrig.studio import new_board, readiness_issues, validate
from showrig.web import create_app


class ReadinessTests(unittest.TestCase):
    """Exercise blank scenes, stable targets and optional media through the API."""

    def test_empty_middle_and_end_are_collected_and_follow_ids_after_reorder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = new_board('A draft', 'demo')
            issues = readiness_issues(board, root, [root])
            empty_ids = {scene['id'] for scene in board['scenes'][1:]}
            self.assertEqual({i['sceneId'] for i in issues}, empty_ids)
            self.assertIn('Scene 2 is empty', issues[0]['message'])
            board['scenes'].reverse()
            self.assertEqual({i['sceneId'] for i in readiness_issues(board, root, [root])}, empty_ids)
            self.assertEqual(validate(board, root, [root]), board)
            with self.assertRaisesRegex(ValueError, 'Scene 1 is empty'):
                validate(board, root, [root], render=True)

    def test_text_only_is_ready_and_missing_recordings_are_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = new_board('A film', 'demo')
            for scene in board['scenes']:
                scene['title'] = 'Visible text'
                scene['lines'] = ['Optional caption']
            board['voice']['source'] = 'none'
            self.assertFalse(readiness_issues(board, root, [root]))
            board['voice']['source'] = 'files'
            issues = readiness_issues(board, root, [root])
            self.assertEqual(len(issues), len(board['scenes']))
            self.assertTrue(all(i['code'] == 'missing-recording' for i in issues))
            self.assertIn('narration line 1', issues[0]['message'])

    def test_missing_files_and_music_point_to_owning_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = new_board('A film', 'demo')
            board['scenes'] = board['scenes'][:1]
            board['scenes'][0]['image'] = {'file': 'assets/moved.png'}
            board['music'].update(source='file', file=None)
            issues = readiness_issues(board, root, [root])
            self.assertEqual([i['field'] for i in issues], ['scene.image', 'music.file'])
            self.assertEqual(issues[0]['sceneId'], board['scenes'][0]['id'])

    @patch('showrig.web.subprocess.run')
    def test_preflight_and_render_share_blockers_and_never_start_bad_jobs(self, run):
        run.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as directory, TestClient(create_app(Path(directory))) as client:
            headers = {'X-Showrig-Request': '1'}
            project = client.post('/api/projects', headers=headers, json={'title': 'Readiness test'}).json()
            endpoint = '/api/projects/' + project['id']
            report = client.get(endpoint + '/preflight').json()
            self.assertFalse(report['ready'])
            response = client.post(endpoint + '/render', headers=headers, json={'mode': 'preview'})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['detail']['issues'], report['issues'])
            self.assertIsNone(client.get(endpoint).json()['job'])


if __name__ == '__main__':
    unittest.main()
