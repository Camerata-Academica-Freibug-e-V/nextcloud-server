# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "run_tool_tests", Path(__file__).resolve().parents[1] / "run-tool-tests.py",
)
TOOLS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOLS)


class ToolTestsTest(unittest.TestCase):
    def test_selects_only_direct_tests_and_shared_helper_consumers(self):
        cases = {
            "build/pack-apps.sh": "build/tests/test-pack-apps.py",
            "build/has-appstore-target.py": "build/tests/test-pack-apps.py",
            "build/pack-support-app.py": "build/tests/test-pack-support-app.py",
            "Makefile": "build/tests/test-pack-support-app.py",
            "build/generate-file-commits": "tests/test_generate_file_commits.py",
            "build/integration/install-dependencies.py":
                "build/integration/tests/test_install_dependencies.py",
        }
        for source, test in cases.items():
            with self.subTest(source=source):
                self.assertEqual(TOOLS.select_tests([source]), ([test], []))
                self.assertEqual(TOOLS.select_tests([test]), ([test], []))

    def test_unknown_tools_and_unavailable_tests_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                TOOLS.select_tests(["build/pack-apps.sh"], root=Path(directory)),
                ([], ["build/pack-apps.sh"]),
            )
        self.assertEqual(
            TOOLS.select_tests(["build/uncovered.sh", "unknown.py", "lib/private/File.php"]),
            ([], ["build/uncovered.sh", "unknown.py"]),
        )

    def test_workflow_changes_only_select_policy_tests(self):
        self.assertEqual(
            TOOLS.select_tests([".github/workflows/phpunit.yml"]),
            ([TOOLS.POLICY_TEST], []),
        )
        tests, uncovered = TOOLS.select_tests([".github/workflows/tooling.yml"])
        self.assertIn("build/tests/test-pack-apps.py", tests)
        self.assertIn("build/tests/test_run_tool_tests.py", tests)
        self.assertIn(TOOLS.POLICY_TEST, tests)
        self.assertEqual(uncovered, [])

    def test_runner_checks_syntax_and_notifies_about_missing_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "unknown.sh").write_text("#!/bin/sh\ntrue\n")
            output = io.StringIO()
            with patch.object(TOOLS, "ROOT", root), \
                    patch.object(TOOLS, "select_tests", return_value=([], ["unknown.sh"])), \
                    patch.object(TOOLS.subprocess, "run") as run, \
                    contextlib.redirect_stdout(output):
                self.assertEqual(TOOLS.main(["--files-json", '["unknown.sh"]']), 0)
            run.assert_called_once_with(["bash", "-n", "--", "unknown.sh"], cwd=root, check=True)
            self.assertIn("::notice file=unknown.sh::No dedicated test", output.getvalue())

    def test_invalid_python_and_failed_tests_are_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "unknown.py").write_text("def broken(\n")
            with patch.object(TOOLS, "ROOT", root), \
                    patch.object(TOOLS, "select_tests", return_value=([], ["unknown.py"])):
                with self.assertRaises(SyntaxError):
                    TOOLS.main(["--files-json", '["unknown.py"]'])
        with patch.object(TOOLS, "select_tests", return_value=(
            ["build/tests/test-pack-apps.py"], [],
        )), patch.object(TOOLS.subprocess, "run", side_effect=RuntimeError("test failed")):
            with self.assertRaisesRegex(RuntimeError, "test failed"):
                TOOLS.main([])

    def test_runs_hyphenated_test_paths_without_discovery(self):
        test = "build/tests/test-pack-apps.py"
        with patch.object(TOOLS, "select_tests", return_value=([test], [])), \
                patch.object(TOOLS.subprocess, "run") as run, \
                contextlib.redirect_stdout(io.StringIO()):
            TOOLS.main([])
        run.assert_called_once_with(
            [TOOLS.sys.executable, "-m", "unittest", test], cwd=TOOLS.ROOT, check=True,
        )

    def test_deleted_scripts_are_not_syntax_checked(self):
        with patch.object(TOOLS, "select_tests", return_value=([], ["build/deleted.sh"])), \
                patch.object(TOOLS.subprocess, "run") as run, \
                contextlib.redirect_stdout(io.StringIO()):
            TOOLS.main(["--files-json", '["build/deleted.sh"]'])
        run.assert_not_called()

    def test_rejects_non_array_and_outside_paths(self):
        for value in ('{}', '[null]', '["/tmp/tool.sh"]', '["build/../../tool.sh"]'):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    TOOLS.main(["--files-json", value])
                self.assertEqual(error.exception.code, 2)
