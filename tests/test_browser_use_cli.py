from __future__ import annotations

import subprocess
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from spark_cli import cli


class BrowserUseCliTests(unittest.TestCase):
    def test_status_reports_missing_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value=None), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=False):
                payload = cli.browser_use_status_payload()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["next_action"], "Run `spark browser-use install`, then `spark browser-use probe`.")

    def test_status_marks_old_ready_receipt_unproven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            screenshot = Path(tmp_dir) / "probe-screenshot.png"
            status_path.parent.mkdir(parents=True)
            screenshot.write_bytes(b"png")
            status_path.write_text(
                cli.json.dumps(
                    {
                        "status": "ready",
                        "last_success_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                        "proofs": ["doctor", "public_page_open", "screenshot_capture", "state_read"],
                        "screenshot_path": str(screenshot),
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True):
                payload = cli.browser_use_status_payload()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "installed_unproven")
        self.assertFalse(payload["proof_fresh"])
        self.assertIn("stale", payload["last_failure_reason"])

    def test_status_accepts_builder_screenshot_proof_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            screenshot = Path(tmp_dir) / "smoke-screenshot.png"
            status_path.parent.mkdir(parents=True)
            screenshot.write_bytes(b"png")
            status_path.write_text(
                cli.json.dumps(
                    {
                        "status": "ready",
                        "last_success_at": datetime.now(timezone.utc).isoformat(),
                        "proofs": {
                            "doctor": {"status": "success"},
                            "public_page_open": {"status": "success"},
                            "state_read": {"status": "success"},
                            "screenshot_capture": {"status": "success", "path": str(screenshot)},
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True):
                payload = cli.browser_use_status_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")

    def test_probe_writes_ready_receipt_for_public_page_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            completed = subprocess.CompletedProcess(["browser-use"], 0, stdout="ok", stderr="")
            screenshot_path = status_path.parent / "probe-screenshot.png"

            def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if "screenshot" in argv:
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    screenshot_path.write_bytes(b"png")
                return completed

            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch("spark_cli.cli.subprocess.run", side_effect=fake_run) as run:
                probe = cli.browser_use_probe_payload()
                status = cli.browser_use_status_payload()

        self.assertEqual(probe["status"], "ready")
        self.assertTrue(status["ok"])
        self.assertEqual(
            status["proven_scope"],
            ["browser-use doctor", "public page open", "page state read", "screenshot capture"],
        )
        self.assertEqual(
            [call.args[0][:4] for call in run.call_args_list[:4]],
            [
                ["browser-use", "doctor"],
                ["browser-use", "--session", "spark-probe", "open"],
                ["browser-use", "--session", "spark-probe", "state"],
                ["browser-use", "--session", "spark-probe", "screenshot"],
            ],
        )

    def test_install_dry_run_is_non_mutating(self) -> None:
        with patch("spark_cli.cli.subprocess.run") as run:
            exit_code = cli.cmd_browser_use(Namespace(browser_use_command="install", dry_run=True))

        self.assertEqual(exit_code, 0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
