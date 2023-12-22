import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


# ufbt invokation & json status output
def ufbt_status(cwd=None) -> dict:
    # Call "ufbt status --json" and return the parsed json
    try:
        status = subprocess.check_output(["ufbt", "status", "--json"], cwd=cwd)
    except subprocess.CalledProcessError as e:
        status = e.output
    return json.loads(status)


def ufbt_exec(args, cwd=None):
    # Call "ufbt" with the given args and return the parsed json
    return subprocess.check_output(["ufbt"] + args, cwd=cwd)


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

    def test_dotenv_basic(self):
        ufbt_exec(["clean"])
        status = ufbt_status()
        self.assertEqual(status.get("error"), "SDK is not deployed")

        ufbt_exec(["update", "-t", "f7"])
        status = ufbt_status()
        self.assertEqual(status.get("target"), "f7")
        self.assertEqual(status.get("mode"), "channel")
        self.assertEqual(status.get("details", {}).get("channel"), "release")

        with TemporaryDirectory() as tmpdir:
            local_dir = Path(tmpdir) / "local_env"
            local_dir.mkdir(exist_ok=False)

            ufbt_exec(["dotenv_create"], cwd=local_dir)
            status = ufbt_status(cwd=local_dir)
            self.assertEqual(status.get("target"), None)
            self.assertIn(
                str(local_dir.absolute()), str(Path(status.get("state_dir")).absolute())
            )
            self.assertEqual(status.get("error"), "SDK is not deployed")

            ufbt_exec(["update", "-b", "dev"], cwd=local_dir)
            status = ufbt_status(cwd=local_dir)
            self.assertEqual(status.get("target"), "f7")
            self.assertEqual(status.get("mode"), "branch")
            self.assertEqual(status.get("details", {}).get("branch", ""), "dev")

        status = ufbt_status()
        self.assertEqual(status.get("target"), "f7")
        self.assertEqual(status.get("mode"), "channel")

    def test_dotenv_notoolchain(self):
        with TemporaryDirectory() as tmpdir:
            local_dir = Path(tmpdir) / "local_env"
            local_dir.mkdir(exist_ok=False)

            ufbt_exec(["dotenv_create"], cwd=local_dir)
            status = ufbt_status(cwd=local_dir)

            toolchain_path_local = status.get("toolchain_dir", "")
            self.assertTrue(Path(toolchain_path_local).is_symlink())

            # 2nd env
            local_dir2 = Path(tmpdir) / "local_env2"
            local_dir2.mkdir(exist_ok=False)

            ufbt_exec(["dotenv_create", "--no-link-toolchain"], cwd=local_dir2)
            status = ufbt_status(cwd=local_dir2)

            toolchain_path_local2 = status.get("toolchain_dir", "")
            self.assertFalse(Path(toolchain_path_local2).exists())

    def test_path_with_spaces(self):
        ufbt_exec(["clean"])
        status = ufbt_status()
        self.assertEqual(status.get("error"), "SDK is not deployed")

        with TemporaryDirectory() as tmpdir:
            local_dir = Path(tmpdir) / "path with spaces"
            local_dir.mkdir(exist_ok=False)

            ufbt_exec(["dotenv_create"], cwd=local_dir)
            ufbt_exec(["update"], cwd=local_dir)
            status = ufbt_status(cwd=local_dir)
            self.assertNotIn("error", status)

            ufbt_exec(["create", "APPID=myapp"], cwd=local_dir)
            ufbt_exec(["faps"], cwd=local_dir)
