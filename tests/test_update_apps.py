# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "update-apps.sh"


class UpdateAppsShellTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="update-apps-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, RESULT_FILE=str(self.root / "result"))

    def run_script(self, *args):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def make_apps(self, apps):
        for app in apps:
            (self.root / "apps" / app).mkdir(parents=True)

    def result_lines(self):
        return (self.root / "result").read_text().splitlines()

    def test_only_runs_bash_in_selected_app_directories(self):
        self.make_apps(["calendar", "contacts", "mail"])
        result = self.run_script(
            "--only", "calendar contacts",
            "--shell",
            'values=("quoted value" "${PWD##*/}"); '
            'printf "%s\\n" "${values[*]}" | cat >> "$RESULT_FILE"; cd /',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.result_lines(), ["quoted value calendar", "quoted value contacts"]
        )

    def test_shell_defaults_to_all_apps_and_honors_exclude(self):
        listed = self.run_script("--list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        apps = listed.stdout.split()
        self.make_apps(apps)
        result = self.run_script(
            "--exclude", "calendar",
            "--shell", 'printf "%s\\n" "${PWD##*/}" >> "$RESULT_FILE"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.result_lines(), [app for app in apps if app != "calendar"])

    def test_only_subrepo_is_honored(self):
        listed = self.run_script("--only", "subrepo", "--list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        apps = listed.stdout.split()
        self.make_apps(apps)
        result = self.run_script(
            "--shell", 'printf "%s\\n" "${PWD##*/}" >> "$RESULT_FILE"',
            "--only", "subrepo",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.result_lines(), apps)

    def test_exclusions_match_exact_names_regardless_of_option_order(self):
        cases = [
            (["--only", "calendar contacts mail",
              "--exclude", "calendar contacts"], ["mail"]),
            (["--exclude", "calendar contacts",
              "--only", "calendar contacts mail"], ["mail"]),
            (["--only", "mail mail_roundcube emlviewer",
              "--exclude", "mail"], ["mail_roundcube", "emlviewer"]),
            (["--exclude", "calendar", "--only", "calendar contacts mail",
              "--exclude", "contacts"], ["mail"]),
            (["--only", "calendar contacts",
              "--exclude", "calendar contacts"], []),
            (["--only", "calendar contacts", "--exclude", "unknown"],
             ["calendar", "contacts"]),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                result = self.run_script(*args, "--list")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.split(), expected)

    def test_exclude_subrepo_is_honored_before_only(self):
        result = self.run_script(
            "--exclude", "subrepo",
            "--only", "bav cafevdb calendar mail_roundcube",
            "--list",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["calendar"])

    def test_shell_uses_final_filtered_selection(self):
        self.make_apps(["mail_roundcube"])
        result = self.run_script(
            "--exclude", "calendar mail",
            "--only", "calendar mail mail_roundcube",
            "--shell", 'printf "%s\\n" "${PWD##*/}" >> "$RESULT_FILE"',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.result_lines(), ["mail_roundcube"])

    def test_failure_stops_before_next_app(self):
        self.make_apps(["calendar", "contacts"])
        result = self.run_script(
            "--only", "calendar contacts",
            "--shell", 'printf "%s\\n" "${PWD##*/}" >> "$RESULT_FILE"; exit 7',
        )
        self.assertEqual(result.returncode, 7)
        self.assertIn("Shell command failed for app calendar (exit 7)", result.stderr)
        self.assertEqual(self.result_lines(), ["calendar"])

    def test_missing_command_is_rejected(self):
        result = self.run_script("--shell")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires an argument", result.stderr)

    def test_empty_command_does_not_update_apps(self):
        self.make_apps(["calendar"])
        result = self.run_script("--only", "calendar", "--shell", "")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Updating", result.stdout)


if __name__ == "__main__":
    unittest.main()
