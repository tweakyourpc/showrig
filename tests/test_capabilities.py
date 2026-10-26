"""Doctor's capability catalog: states, profiles, exit codes and the machine inventory, without real tools."""
from __future__ import annotations

import json
import subprocess
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from showrig import capabilities, cli, inventory


def nothing_found():
    return mock.patch.multiple(capabilities, CATALOG=[
        capabilities.Capability(c.id, c.profile, c.unlocks, lambda: None, c.remedy) for c in capabilities.CATALOG])


class CapabilityTests(unittest.TestCase):
    def test_every_profile_names_catalog_entries(self):
        ids = {c.id for c in capabilities.CATALOG}
        for name, members in capabilities.PROFILES.items():
            self.assertTrue(set(members) <= ids, name)
        self.assertEqual(set(capabilities.PROFILES["studio"]), ids - {"ollama"})

    def test_missing_core_tools_fail_with_remedies_and_exit_1(self):
        with nothing_found():
            rep = capabilities.report(None, deep=False)
            self.assertEqual(rep["summary"]["unavailable"], capabilities.PROFILES["core"])
            self.assertTrue(all(c["remedy"] for c in rep["capabilities"]))
            args = Namespace(profile=None, deep=False, json=True, out=None)
            with mock.patch("builtins.print"):
                self.assertEqual(cli.doctor(args), 1)

    def test_optional_tools_do_not_fail_the_core_profile(self):
        with mock.patch.object(capabilities, "check", lambda ids, deep: [
                capabilities.Result(i, "missing" if i == "ollama" else "not-tested", "/x") for i in ids]):
            self.assertEqual(capabilities.report(None, deep=False)["summary"]["unavailable"], [])

    def test_found_is_not_ready_until_probed(self):
        cap = capabilities.Capability("x", "core", "", lambda: "/bin/x", "fix", probe=lambda p, t: ("ready", {}))
        with mock.patch.object(capabilities, "CATALOG", [cap]):
            self.assertEqual(capabilities.check(["x"], deep=False)[0].state, "not-tested")
            self.assertEqual(capabilities.check(["x"], deep=True)[0].state, "ready")

    def test_a_probe_that_times_out_is_failed_not_missing(self):
        def slow(path, tmp):
            raise subprocess.TimeoutExpired("x", 5)
        cap = capabilities.Capability("x", "core", "", lambda: "/bin/x", "fix", probe=slow)
        with mock.patch.object(capabilities, "CATALOG", [cap]):
            res = capabilities.check(["x"], deep=True)[0]
        self.assertEqual((res.state, res.remedy), ("failed", "fix"))
        self.assertIn("timed out", res.evidence["error"])

    def test_silent_failures_still_explain_themselves(self):
        r = subprocess.CompletedProcess([], 1, "", "")
        self.assertEqual(capabilities._why(r), "exited with code 1 and printed nothing")

    def test_a_broken_diagnostic_exits_3(self):
        args = Namespace(profile=None, deep=False, json=False, out=None)
        with mock.patch.object(capabilities, "report", side_effect=RuntimeError("boom")), \
                mock.patch("builtins.print"):
            self.assertEqual(cli.doctor(args), 3)


class InventoryTests(unittest.TestCase):
    def test_inventory_is_json_and_keeps_the_home_directory_out(self):
        data = inventory.collect()
        text = json.dumps(data)
        self.assertEqual((data["schema"], data["kind"]), (1, "showrig-inventory"))
        self.assertNotIn(str(Path.home()) + "/", text)
        for key in ("os", "cpu", "memory_gb", "disk", "graphics", "tools"):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()
