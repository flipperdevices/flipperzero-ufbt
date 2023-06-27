import json
import subprocess
import unittest


# ufbt invokation & json status output
def ufbt_status() -> dict:
    # Call "ufbt status --json" and return the parsed json
    try:
        status = subprocess.check_output(["ufbt", "status", "--json"])
    except subprocess.CalledProcessError as e:
        status = e.output
    return json.loads(status)


def ufbt_exec(args):
    # Call "ufbt" with the given args and return the parsed json
    return subprocess.check_output(["ufbt"] + args)


# Test initial deployment
class TestInitialDeployment(unittest.TestCase):
    def test_default_deployment(self):
        ufbt_exec(["clean"])
        status = ufbt_status()
        self.assertEqual(status.get("error"), "SDK is not deployed")

        ufbt_exec(["update"])
        status = ufbt_status()
        self.assertIsNone(status.get("error"))
        self.assertEqual(status.get("target"), "f7")
        self.assertEqual(status.get("mode"), "channel")
        self.assertEqual(status.get("details", {}).get("channel"), "release")

    def test_customized_deployment(self):
        ufbt_exec(["clean"])
        status = ufbt_status()
        self.assertEqual(status.get("error"), "SDK is not deployed")

        ufbt_exec(["update", "-t", "f18", "-c", "rc"])
        status = ufbt_status()
        self.assertIsNone(status.get("error"))
        self.assertEqual(status.get("target"), "f18")
        self.assertEqual(status.get("mode"), "channel")
        self.assertEqual(status.get("details", {}).get("channel"), "rc")
        self.assertIn("rc", status.get("version", ""))

    def test_target_switch(self):
        ufbt_exec(["clean"])
        status = ufbt_status()
        self.assertEqual(status.get("error"), "SDK is not deployed")

        ufbt_exec(["update"])
        status = ufbt_status()
        self.assertEqual(status.get("target"), "f7")

        ufbt_exec(["update", "-t", "f18"])
        status = ufbt_status()
        self.assertEqual(status.get("target"), "f18")
        self.assertEqual(status.get("mode"), "channel")
        self.assertEqual(status.get("details", {}).get("channel"), "release")

    def test_target_mode_switches(self):
        ufbt_exec(["clean"])
        status = ufbt_status()
        self.assertEqual(status.get("error"), "SDK is not deployed")

        ufbt_exec(["update"])
        status = ufbt_status()
        self.assertEqual(status.get("target"), "f7")

        ufbt_exec(["update", "-t", "f18"])
        status = ufbt_status()
        self.assertEqual(status.get("target"), "f18")
        self.assertEqual(status.get("mode"), "channel")

        ufbt_exec(["update", "-b", "dev"])
        status = ufbt_status()
        self.assertEqual(status.get("target"), "f18")
        self.assertEqual(status.get("mode"), "branch")
        self.assertEqual(status.get("details", {}).get("branch"), "dev")

        previous_status = status
        ufbt_exec(["update"])
        status = ufbt_status()
        self.assertEqual(previous_status, status)
