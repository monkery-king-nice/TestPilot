import importlib.util
import io
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "dev.py"
SPEC = importlib.util.spec_from_file_location("testpilot_dev", SCRIPT)
dev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dev)


class StartupTests(unittest.TestCase):
    def test_missing_node_has_actionable_message_without_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "keep.sqlite3"
            database.write_bytes(b"existing database sentinel")
            with patch.object(dev.shutil, "which", return_value=None):
                with self.assertRaisesRegex(dev.StartError, "Install Node.js.*reopen PowerShell"):
                    dev.node_tools()
            self.assertEqual(database.read_bytes(), b"existing database sentinel")

    def test_missing_node_subprocess_exits_before_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "never-created.sqlite3"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--check", "--database", str(database)],
                env=dict(os.environ, PATH=""),
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("Node.js was not found", result.stdout)
            self.assertIn("reopen PowerShell", result.stdout)
            self.assertFalse(database.exists())

    def test_occupied_port_is_not_closed(self):
        with socket.socket() as owner:
            owner.bind(("127.0.0.1", 0))
            owner.listen()
            port = owner.getsockname()[1]
            with patch.dict(dev.PORTS, {"other-owner": port}, clear=True):
                with self.assertRaisesRegex(
                    dev.StartError, "No process was stopped.*Get-NetTCPConnection"
                ):
                    dev.check_ports()
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                accepted, _ = owner.accept()
                accepted.close()

    def test_check_is_read_only_even_when_dependencies_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(dev, "ROOT", root),
                patch.object(dev, "node_tools", return_value=("node", "npm-cli.js")),
                patch.object(dev, "check_ports"),
                patch.object(dev, "installed", return_value=False),
                patch.object(dev, "Processes") as processes,
            ):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(dev.main(["--check", "--database", "new.sqlite3"]), 0)
            processes.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])
            self.assertIn("REAL: VITE_USE_MOCK=false", output.getvalue())
            self.assertIn("installation required", output.getvalue())

    def test_skip_install_fails_before_starting_services(self):
        with (
            patch.object(dev, "node_tools", return_value=("node", "npm-cli.js")),
            patch.object(dev, "check_ports"),
            patch.object(dev, "installed", return_value=False),
            patch.object(dev, "Processes") as processes,
        ):
            with self.assertRaisesRegex(dev.StartError, "without -SkipInstall"):
                dev.main(["--skip-install"])
            processes.assert_not_called()

    def test_frontend_environment_excludes_model_secrets(self):
        secrets = {key: "private-test-sentinel" for key in dev.MODEL_KEYS}
        with patch.dict(os.environ, secrets):
            self.assertFalse(any(key in dev.child_environment() for key in dev.MODEL_KEYS))
            self.assertEqual(
                dev.child_environment(model=True)["DEEPSEEK_API_KEY"], "private-test-sentinel"
            )

    def test_tool_failure_is_an_actionable_error(self):
        with patch.object(dev.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(dev.StartError, "reopen PowerShell"):
                dev.version(["missing"], "npm", 8)

    def test_old_node_is_rejected(self):
        result = subprocess.CompletedProcess(["node"], 0, stdout="v16.0.0\n")
        with patch.object(dev.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(dev.StartError, "Node.js 18"):
                dev.version(["node", "--version"], "Node.js", 18)

    def test_npm_missing_has_repair_instruction(self):
        with (
            patch.object(dev.shutil, "which", side_effect=["node", None]),
            patch.object(dev, "version"),
        ):
            with self.assertRaisesRegex(dev.StartError, "npm.*Repair/reinstall"):
                dev.node_tools()


if __name__ == "__main__":
    unittest.main()
