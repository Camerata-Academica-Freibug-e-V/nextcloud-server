# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "update-apps.sh"


class UpdateAppsShellTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="update-apps-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log_dir = self.root / "logs"
        self.log_dir.mkdir()
        self.env = dict(
            os.environ, RESULT_FILE=str(self.root / "result"), TMPDIR=str(self.log_dir),
        )

    def run_script(self, *args):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def make_build_apps(self):
        apps = ["groupfolders", "logreader", "notifications"]
        self.make_apps([*apps, "activity"])
        for app in [*apps, "activity"]:
            (self.root / "apps" / app / ".git").mkdir()
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        self.env["TEST_ROOT"] = str(self.root)
        git = bin_dir / "git"
        git.write_text(
            '#!/bin/bash\n'
            'case "$1" in\n'
            '  status) echo "On branch feature" ;;\n'
            '  fetch)\n'
            '    echo "update ${PWD##*/}" >> "$RESULT_FILE"\n'
            '    if [ "${PWD##*/}" = "$FAIL_UPDATE" ]; then\n'
            '      echo "fetch failed" >&2; exit 9\n'
            '    fi ;;\n'
            'esac\n'
        )
        git.chmod(0o755)
        make = bin_dir / "make"
        make.write_text(
            f"#!{sys.executable}\n"
            "import os, pathlib, sys, time\n"
            "app = pathlib.Path.cwd().name\n"
            "root = pathlib.Path(os.environ['TEST_ROOT'])\n"
            "def record(event):\n"
            "    with open(os.environ['RESULT_FILE'], 'a') as result:\n"
            "        result.write(f'{event} {app}\\n')\n"
            "record('start')\n"
            "(root / (app + '.started')).touch()\n"
            "for peer in os.environ.get('BARRIER_APPS', '').split():\n"
            "    deadline = time.monotonic() + 5\n"
            "    while not (root / (peer + '.started')).exists():\n"
            "        if time.monotonic() > deadline:\n"
            "            sys.exit('parallel build did not start')\n"
            "        time.sleep(0.01)\n"
            "time.sleep(0.05)\n"
            "print(f'{app} stdout: {sys.argv[1:]}')\n"
            "print(f'{app} stderr', file=sys.stderr)\n"
            "record('end')\n"
            "sys.exit(7 if app == os.environ.get('FAIL_APP') else 0)\n"
        )
        make.chmod(0o755)
        return apps

    def test_build_defaults_to_sequential_updates_and_builds(self):
        apps = self.make_build_apps()
        result = self.run_script("--only", " ".join(apps), "--build")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.result_lines(),
            [f"{event} {app}" for app in apps for event in ("update", "start", "end")],
        )

    def test_parallel_builds_are_bounded_and_follow_sequential_updates(self):
        apps = self.make_build_apps()
        self.env["BARRIER_APPS"] = " ".join(apps[:2])
        result = self.run_script("--build", "--jobs", "2", "--only", " ".join(apps))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.result_lines()
        self.assertEqual(lines[:3], [f"update {app}" for app in apps])
        active = maximum = 0
        for line in lines[3:]:
            active += 1 if line.startswith("start ") else -1
            maximum = max(maximum, active)
            self.assertLessEqual(active, 2)
        self.assertEqual((active, maximum), (0, 2))
        self.assertEqual(list(self.log_dir.iterdir()), [])
        self.assertLess(lines.index(f"end {apps[1]}"), lines.index(f"start {apps[2]}"))
        for app in apps:
            self.assertIn(f"{app} stdout", result.stdout)
            self.assertIn(f"{app} stderr", result.stderr)
        self.assertLess(
            result.stdout.index(f"{apps[0]} stdout"),
            result.stdout.index(f"*** Rebuilding {apps[1]} ***"),
        )

    def test_failed_build_drains_batch_and_stops_before_next_batch(self):
        apps = self.make_build_apps()
        self.env["FAIL_APP"] = apps[0]
        self.env["BARRIER_APPS"] = " ".join(apps[:2])
        result = self.run_script("--build", "-j2", "--only", " ".join(apps))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"Build failed for app {apps[0]} (exit 7)", result.stderr)
        self.assertIn(f"end {apps[1]}", self.result_lines())
        self.assertNotIn(f"start {apps[2]}", self.result_lines())
        self.assertIn(f"{apps[1]} stdout", result.stdout)
        self.assertEqual(list(self.log_dir.iterdir()), [])

    def test_update_failure_does_not_start_queued_builds(self):
        apps = self.make_build_apps()
        self.env["FAIL_UPDATE"] = apps[1]
        result = self.run_script("--build", "-j", "2", "--only", " ".join(apps))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fetch failed", result.stderr)
        self.assertEqual(self.result_lines(), [f"update {app}" for app in apps[:2]])

    def test_serial_build_failure_stops_updates(self):
        apps = self.make_build_apps()
        self.env["FAIL_APP"] = apps[0]
        result = self.run_script("--build", "-j", "1", "--only", " ".join(apps))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.result_lines(), [f"{event} {apps[0]}" for event in ("update", "start", "end")]
        )

    def test_jobs_without_build_only_updates_apps(self):
        apps = self.make_build_apps()
        result = self.run_script("--jobs=2", "--only", " ".join(apps))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.result_lines(), [f"update {app}" for app in apps])

    def test_build_selection_dev_mode_and_large_job_count(self):
        self.make_build_apps()
        result = self.run_script(
            "--build", "--dev", "--jobs=999999999999999999999999",
            "--only", "groupfolders activity logreader notifications",
            "--exclude", "logreader notifications",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.result_lines(),
            ["update groupfolders", "update activity",
             "start groupfolders", "end groupfolders"],
        )
        self.make_apps(["files_archive"])
        (self.root / "apps" / "files_archive" / ".git").mkdir()
        result = self.run_script(
            "--build", "--dev", "-j", "2", "--only", "files_archive",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("files_archive stdout: ['dev']", result.stdout)

    def test_jobs_does_not_parallelize_shell_commands(self):
        self.make_apps(["calendar", "contacts"])
        result = self.run_script(
            "--build", "--jobs", "2", "--only", "calendar contacts",
            "--shell", 'echo "${PWD##*/}" >> "$RESULT_FILE"; exit 7',
        )
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.result_lines(), ["calendar"])

    def test_invalid_or_missing_jobs_are_rejected(self):
        for value in ("0", "-1", "1.5", "abc", "", "01"):
            with self.subTest(value=value):
                result = self.run_script("--jobs", value, "--list")
                self.assertEqual(result.returncode, 2)
                self.assertIn("expected a positive integer", result.stderr)
        result = self.run_script("--jobs")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires an argument", result.stderr)

    def make_apps(self, apps):
        for app in apps:
            (self.root / "apps" / app).mkdir(parents=True)

    def result_lines(self):
        return (self.root / "result").read_text().splitlines()

    def git(self, app, *args):
        return subprocess.run(
            ["git", "-C", str(self.root / "apps" / app), *args],
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def make_reset_app(self):
        app = "activity"
        self.make_apps([app])
        self.git(app, "init", "--initial-branch=feature")
        self.git(app, "config", "user.name", "Test")
        self.git(app, "config", "user.email", "test@example.com")
        tracked = self.root / "apps" / app / "tracked"
        tracked.write_text("original\n")
        self.git(app, "add", "tracked")
        self.git(app, "commit", "-m", "Initial")
        remote = self.root / "remote.git"
        self.git(app, "init", "--bare", str(remote))
        self.git(app, "remote", "add", "origin", str(remote))
        self.git(app, "push", "--set-upstream", "origin", "HEAD:stable35")
        tracked.write_text("local commit\n")
        self.git(app, "commit", "-am", "Local change")
        tracked.write_text("uncommitted change\n")
        return app, tracked

    def test_status_omits_apps_without_attention_items(self):
        app, tracked = self.make_reset_app()
        result = self.run_script("--only", app, "--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("[activity]=", result.stdout)
        self.assertEqual(tracked.read_text(), "uncommitted change\n")

    def test_status_reports_tracking_issues(self):
        app, tracked = self.make_reset_app()
        cases = [
            ("different-upstream", "does not match origin/stable35"),
            ("no-upstream", "no valid upstream"),
            ("missing-upstream", "no valid upstream"),
            ("detached", "detached HEAD"),
        ]
        self.git(app, "push", "origin", "HEAD:other")
        for case, expected in cases:
            with self.subTest(case=case):
                if case == "different-upstream":
                    self.git(app, "branch", "--set-upstream-to=origin/other")
                elif case == "no-upstream":
                    self.git(app, "branch", "--unset-upstream")
                elif case == "missing-upstream":
                    self.git(app, "branch", "--set-upstream-to=origin/stable35")
                    self.git(app, "update-ref", "-d", "refs/remotes/origin/stable35")
                else:
                    self.git(app, "checkout", "--detach")
                result = self.run_script("--only", app, "--status")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("[activity]=", result.stdout)
                self.assertIn(expected, result.stdout)
                self.assertEqual(tracked.read_text(), "uncommitted change\n")

    def make_diverged_app(self):
        app, tracked = self.make_reset_app()
        tracked.write_text("local commit\n")
        self.git(app, "checkout", "-b", "other", "origin/stable35")
        tracked.write_text("remote change\n")
        self.git(app, "commit", "-am", "Remote change")
        self.git(app, "push", "origin", "HEAD:stable35")
        self.git(app, "checkout", "feature")
        return app, tracked

    def test_status_reports_divergence(self):
        app, _ = self.make_diverged_app()
        result = self.run_script("--only", app, "--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[activity]=diverged", result.stdout)

    def test_status_reports_missing_reset_configuration(self):
        app, _ = self.make_reset_app()
        self.git(app, "branch", "--unset-upstream")
        (self.root / "apps" / app).rename(self.root / "apps" / "unknown")
        result = self.run_script("--only", "unknown", "--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[unknown]=reset branch is empty; no valid upstream", result.stdout)

    def test_status_reports_merge_even_after_conflicts_are_resolved(self):
        app, tracked = self.make_diverged_app()
        merge = subprocess.run(
            ["git", "-C", str(tracked.parent), "merge", "other"],
            env=self.env, capture_output=True, text=True,
        )
        self.assertNotEqual(merge.returncode, 0)
        result = self.run_script("--only", app, "--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("diverged; conflicts; merge in progress", result.stdout)
        tracked.write_text("resolved\n")
        self.git(app, "add", "tracked")
        result = self.run_script("--only", app, "--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("merge in progress", result.stdout)
        self.assertNotIn("conflicts", result.stdout)
        self.assertEqual(tracked.read_text(), "resolved\n")

    def test_status_detects_pending_merge_in_linked_worktree(self):
        app, tracked = self.make_diverged_app()
        worktree = self.root / "apps" / "viewer"
        self.git(app, "worktree", "add", "-b", "linked", str(worktree), "feature")
        self.git("viewer", "branch", "--set-upstream-to=origin/stable35")
        merge = subprocess.run(
            ["git", "-C", str(worktree), "merge", "other"],
            env=self.env, capture_output=True, text=True,
        )
        self.assertNotEqual(merge.returncode, 0)
        result = self.run_script("--only", "viewer", "--status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[viewer]=diverged; conflicts; merge in progress", result.stdout)

    def test_status_reports_pending_rebase_with_both_backends(self):
        for backend in ("--merge", "--apply"):
            with self.subTest(backend=backend):
                with tempfile.TemporaryDirectory(dir=self.root) as directory:
                    original_root = self.root
                    self.root = Path(directory)
                    try:
                        app, tracked = self.make_diverged_app()
                        rebase = subprocess.run(
                            ["git", "-C", str(tracked.parent),
                             "rebase", backend, "other"],
                            env=self.env, capture_output=True, text=True,
                        )
                        self.assertNotEqual(rebase.returncode, 0)
                        tracked.write_text("resolved\n")
                        self.git(app, "add", "tracked")
                        result = self.run_script("--only", app, "--status")
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn("rebase in progress", result.stdout)
                        self.assertNotIn("conflicts", result.stdout)
                        self.assertEqual(tracked.read_text(), "resolved\n")
                    finally:
                        self.root = original_root

    def test_reset_accepts_matching_upstream_without_switching_branches(self):
        app, tracked = self.make_reset_app()
        self.git(app, "branch", "-m", "stable34")
        self.git(app, "branch", "stable35")
        result = self.run_script("--only", app, "--reset")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(app, "branch", "--show-current"), "stable34")
        self.assertEqual(
            self.git(app, "rev-parse", "HEAD"),
            self.git(app, "rev-parse", "origin/stable35"),
        )
        self.assertEqual(tracked.read_text(), "original\n")

    def test_reset_stops_when_fetch_fails(self):
        app, tracked = self.make_reset_app()
        before = self.git(app, "rev-parse", "HEAD")
        self.git(app, "remote", "set-url", "origin", str(self.root / "missing.git"))
        result = self.run_script("--only", app, "--reset")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("*** Hard resetting", result.stdout)
        self.assertEqual(self.git(app, "rev-parse", "HEAD"), before)
        self.assertEqual(tracked.read_text(), "uncommitted change\n")

    def test_reset_failure_is_reported(self):
        app, tracked = self.make_reset_app()
        (self.root / "apps" / app / ".git" / "index.lock").touch()
        result = self.run_script("--only", app, "--reset")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("index.lock", result.stderr)
        self.assertEqual(tracked.read_text(), "uncommitted change\n")

    def test_reset_rejections_preserve_head_and_worktree(self):
        cases = (
            "different-upstream", "no-upstream", "detached",
            "local-upstream", "missing-upstream",
        )
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(dir=self.root) as directory:
                    original_root = self.root
                    self.root = Path(directory)
                    try:
                        app, tracked = self.make_reset_app()
                        if case == "different-upstream":
                            self.git(app, "push", "origin", "HEAD:other")
                            self.git(app, "branch", "--set-upstream-to=origin/other")
                        elif case == "no-upstream":
                            self.git(app, "branch", "--unset-upstream")
                        elif case == "detached":
                            self.git(app, "checkout", "--detach")
                        elif case == "local-upstream":
                            self.git(app, "branch", "origin/stable35")
                            self.git(app, "config", "branch.feature.remote", ".")
                            self.git(app, "config", "branch.feature.merge",
                                     "refs/heads/origin/stable35")
                        else:
                            self.git(app, "update-ref", "-d",
                                     "refs/remotes/origin/stable35")
                        before = self.git(app, "rev-parse", "HEAD")
                        status = self.git(app, "status", "--porcelain")
                        result = self.run_script("--only", app, "--reset")
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("Refusing to reset app activity:", result.stderr)
                        self.assertEqual(self.git(app, "rev-parse", "HEAD"), before)
                        self.assertEqual(self.git(app, "status", "--porcelain"), status)
                        self.assertEqual(tracked.read_text(), "uncommitted change\n")
                    finally:
                        self.root = original_root

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

    def test_help_options_print_usage_and_exit(self):
        for option in ("-h", "--help"):
            with self.subTest(option=option):
                result = self.run_script(option)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Usage: update-apps.sh [OPTIONS]", result.stdout)
                self.assertIn("-h, --help", result.stdout)
                self.assertIn("--shell COMMAND", result.stdout)


if __name__ == "__main__":
    unittest.main()
