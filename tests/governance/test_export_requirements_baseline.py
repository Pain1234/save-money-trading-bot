"""Unit tests for export_requirements_baseline.py version enforcement."""

from __future__ import annotations

import sys
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_requirements_baseline as export_baseline

VersionInfo = namedtuple("VersionInfo", ["major", "minor", "micro", "releaselevel", "serial"])


def version_info(major: int, minor: int) -> VersionInfo:
    return VersionInfo(major, minor, 0, "final", 0)


class ExportRequirementsBaselineVersionTests(unittest.TestCase):
    def test_check_python_version_accepts_312(self) -> None:
        with patch.object(export_baseline.sys, "version_info", version_info(3, 12)):
            self.assertIsNone(export_baseline.check_python_version())

    def test_check_python_version_rejects_314(self) -> None:
        with patch.object(export_baseline.sys, "version_info", version_info(3, 14)):
            self.assertEqual(export_baseline.check_python_version(), 1)

    def test_main_exits_without_writing_on_wrong_python(self) -> None:
        mock_output = MagicMock()
        with patch.object(export_baseline.sys, "version_info", version_info(3, 14)), patch.object(
            export_baseline, "OUTPUT", mock_output
        ), patch("export_requirements_baseline.subprocess.run") as run_mock:
            exit_code = export_baseline.main()

        self.assertEqual(exit_code, 1)
        mock_output.write_text.assert_not_called()
        run_mock.assert_not_called()

    def test_main_proceeds_on_312(self) -> None:
        freeze_result = MagicMock(returncode=0, stdout="requests==2.32.0\n")
        run_side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            freeze_result,
        ]
        mock_output = MagicMock()
        mock_output.relative_to.return_value = Path("requirements-baseline.txt")

        with patch.object(export_baseline.sys, "version_info", version_info(3, 12)), patch.object(
            export_baseline.sys, "platform", "linux"
        ), patch.object(export_baseline, "tempfile") as tempfile_mock, patch.object(
            export_baseline, "OUTPUT", mock_output
        ), patch("export_requirements_baseline.subprocess.run", side_effect=run_side_effect):
            tempfile_mock.TemporaryDirectory.return_value.__enter__.return_value = "/tmp/baseline-export"
            exit_code = export_baseline.main()

        self.assertEqual(exit_code, 0)
        mock_output.write_text.assert_called_once()


if __name__ == "__main__":
    unittest.main()
