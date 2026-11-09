#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Run with: python3 build/tests/test-pack-apps.py
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "pack-apps.sh"


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for app in ("files", "calendar", "disabled", "legacy", "modern"):
            directory = self.root / "apps" / app / "appinfo"
            directory.mkdir(parents=True)
            (directory / "info.xml").touch()
        (self.root / "apps/modern/Makefile").write_text("appstore:\n\t@true\n")
        self.git("init", "--quiet")
        self.git("add", "apps/files")
        # Test selection separately from real instance initialization.
        bindir = self.root / "bin"
        bindir.mkdir()
        php = bindir / "php"
        php.write_text(
            '#!/bin/sh\n'
            '[ "$*" = "./occ app:list --output=json" ] || exit 99\n'
            'printf "%s" "$APP_STATUS"\n'
            'exit "${PHP_STATUS:-0}"\n'
        )
        php.chmod(0o755)
        self.env = dict(
            os.environ,
            PATH=f"{bindir}:{os.environ['PATH']}",
            APP_STATUS=json.dumps({"disabled": {"disabled": "1.0"}}),
        )

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True, input=""
        ).stdout.strip()

    def test_server_uses_current_index_and_excludes_submodules(self):
        self.git("add", "apps/calendar")
        self.assertEqual(self.run_pack("-i", ":server", "-x", ":no-server"), {"files", "calendar"})
        self.git("rm", "--cached", "-r", "apps/files")
        self.assertEqual(self.run_pack("-i", ":server", "-x", ":no-server"), {"calendar"})
        # A gitlink is not a direct app, even though its working folder exists.
        empty_tree = self.git("hash-object", "-t", "tree", "--stdin")
        commit = self.git(
            "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit-tree", empty_tree, "-m", "Submodule fixture",
        )
        self.git("update-index", "--add", "--cacheinfo", f"160000,{commit},apps/modern")
        self.assertEqual(self.run_pack("-i", ":server", "-x", ":no-server"), {"calendar"})
        self.assertEqual(
            self.run_pack("-i", ":no-server"), {"files", "disabled", "legacy", "modern"}
        )

    def test_server_query_failure_is_explicit(self):
        git = self.root / "bin/git"
        git.write_text("#!/bin/sh\nexit 1\n")
        git.chmod(0o755)
        self.assertIn("cannot determine server apps", self.run_pack(success=False).stderr)

    def test_server_uses_selected_apps_directory(self):
        appinfo = self.root / "custom-apps/custom/appinfo"
        appinfo.mkdir(parents=True)
        (appinfo / "info.xml").touch()
        self.git("add", "custom-apps")
        self.assertEqual(self.run_pack("-a", "custom-apps"), set())
        self.assertEqual(
            self.run_pack("-a", "custom-apps", "-i", ":server", "-x", ":no-server"),
            {"custom"},
        )

    def run_pack(self, *args, success=True):
        result = subprocess.run(
            ["bash", str(SCRIPT), "-n", "-o", "out.tgz", *args],
            cwd=self.root, env=self.env, text=True, capture_output=True,
        )
        if not success:
            self.assertNotEqual(result.returncode, 0, result.stderr)
            return result
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("[pack] wrote ", result.stdout)
        with tarfile.open(self.root / "out.tgz") as archive:
            return {
                name.split("/")[1]
                for name in archive.getnames()
                if name.startswith("apps/")
            }

    def test_help_prints_header_without_comment_prefixes(self):
        header = SCRIPT.read_text().split("\n\n", 1)[0].splitlines()[1:]
        expected = "\n".join(
            line[2:] if line.startswith("# ") else line[1:] for line in header
        ) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            for option in ("-h", "--help"):
                with self.subTest(option=option):
                    result = subprocess.run(
                        ["bash", str(SCRIPT), option],
                        cwd=directory, text=True, capture_output=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, expected)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(list(Path(directory).iterdir()), [])

    def test_default_and_server_override(self):
        self.assertEqual(
            self.run_pack(), {"calendar", "disabled", "legacy", "modern"}
        )
        self.assertEqual(
            self.run_pack("-x", ":no-server,files"),
            {"calendar", "disabled", "legacy", "modern"},
        )
        self.assertEqual(
            self.run_pack("--exclude=:no-server"),
            {"files", "calendar", "disabled", "legacy", "modern"},
        )
        self.assertEqual(
            self.run_pack("-x", ":server"), {"calendar", "disabled", "legacy", "modern"}
        )
        self.assertEqual(
            self.run_pack("-x", "calendar", "-x", ":no-server"),
            {"files", "disabled", "legacy", "modern"},
        )

    def test_only_union_and_exclusion_precedence(self):
        self.assertEqual(
            self.run_pack("--only", ":server,calendar", "-x", ":no-server"),
            {"files", "calendar"},
        )
        self.assertEqual(
            self.run_pack("-i", ":server,calendar", "-x", "calendar"), set()
        )
        self.assertEqual(
            self.run_pack("-i", "calendar", "--only=modern", "-x", "modern"),
            {"calendar"},
        )
        self.assertEqual(
            self.run_pack("-i", ":no-server", "-x", "legacy"),
            {"calendar", "disabled", "modern"},
        )

    def test_disabled(self):
        self.assertEqual(
            self.run_pack("-x", ":disabled"), {"calendar", "legacy", "modern"}
        )
        self.assertEqual(self.run_pack("-i", ":disabled"), {"disabled"})
        self.env["APP_STATUS"] = '{"disabled":[]}'
        self.assertEqual(self.run_pack("-i", ":disabled"), set())

    def test_disabled_query_failure_and_invalid_json(self):
        self.env["PHP_STATUS"] = "1"
        self.assertIn("cannot query", self.run_pack("-i", ":disabled", success=False).stderr)
        self.env["PHP_STATUS"] = "0"
        for status in ("not json", "{}", '{"disabled":true}'):
            self.env["APP_STATUS"] = status
            with self.subTest(status=status):
                self.assertIn(
                    "invalid app:list", self.run_pack("-x", ":disabled", success=False).stderr
                )

    def test_legacy_is_independent_of_no_rules_option(self):
        self.assertEqual(self.run_pack("-x", ":legacy"), {"modern"})
        self.assertEqual(
            self.run_pack("-i", ":legacy"), {"calendar", "disabled", "legacy"}
        )
        krankerl = self.root / "bin/krankerl"
        krankerl.write_text("#!/bin/sh\nexit 0\n")
        krankerl.chmod(0o755)
        (self.root / "apps/calendar/krankerl.toml").touch()
        self.assertEqual(self.run_pack("-x", ":legacy"), {"calendar", "modern"})

    def test_positional_apps_are_filtered_and_deduplicated(self):
        self.assertEqual(
            self.run_pack("-x", "calendar", "calendar", "modern", "files", "modern"),
            {"modern"},
        )
        self.assertEqual(self.run_pack("-i", "calendar", "modern"), set())
        self.assertEqual(self.run_pack("-x", ":no-server", "files"), {"files"})

    def test_invalid_selection(self):
        for args in (
            ("-x", ":unknown"), ("-i", ":unknown"), ("--only",),
            ("-x", "../files"), ("../files",),
        ):
            with self.subTest(args=args):
                self.run_pack(*args, success=False)
        self.assertEqual(self.run_pack("--only="), set())

    def test_continue_archive_obeys_current_selection(self):
        self.assertEqual(
            self.run_pack("-s", "stage", "-x", ":no-server"),
            {"files", "calendar", "disabled", "legacy", "modern"},
        )
        # Retained staged apps must not bypass the new filter.
        self.assertEqual(
            self.run_pack("-s", "stage", "-c", "-i", "calendar,modern", "-x", "modern"),
            {"calendar"},
        )
        self.assertTrue((self.root / "stage/apps/modern").is_dir())
        self.assertEqual(self.run_pack("-s", "stage", "-c", "-i", "missing"), set())

    def run_dry(self, *args, success=True):
        before = {
            str(path.relative_to(self.root)): path.read_bytes() if path.is_file() else None
            for path in self.root.rglob("*")
        }
        result = subprocess.run(
            ["bash", str(SCRIPT), "--dry-run", "-o", "out.tgz", *args],
            cwd=self.root, env=self.env, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)
        after = {
            str(path.relative_to(self.root)): path.read_bytes() if path.is_file() else None
            for path in self.root.rglob("*")
        }
        self.assertEqual(before, after, "dry run changed files or directories")
        if success:
            self.assertEqual(result.stderr, "")
            return result.stdout
        return result.stderr

    def test_progress_and_errors_use_separate_streams(self):
        (self.root / "apps/legacy/.git").mkdir()
        (self.root / "apps/legacy/package.json").write_text("{}")
        result = self.run_pack("-k", success=False)
        self.assertIn("[calendar] no .git, copying verbatim", result.stdout)
        self.assertIn("[pack] wrote ", result.stdout)
        self.assertNotIn("ERROR:", result.stdout)
        self.assertIn("[legacy] ERROR:", result.stderr)
        self.assertIn("[pack] skipped failing apps: legacy", result.stderr)
        self.assertNotIn("copying verbatim", result.stderr)

    def test_make_target_override_dry_run_and_legacy(self):
        output = self.run_dry(
            "--make-target", "calendar=build", "--make-target=legacy=dist",
            "-x", ":legacy",
        )
        self.assertIn("[calendar] would package with rule 'make-build'", output)
        self.assertIn("[legacy] would package with rule 'make-dist'", output)
        self.assertNotIn("[disabled] would", output)
        self.assertIn(
            "[calendar] would use heuristic cleanup",
            self.run_dry("-n", "--make-target", "calendar=build", "--only", "calendar"),
        )
        for value in ("calendar", "=build", "calendar=", "../app=build",
                      "calendar=--eval", "calendar=build extra", "calendar=A=B"):
            with self.subTest(value=value):
                self.assertIn(
                    "invalid make-target", self.run_dry("--make-target", value, success=False)
                )
        self.run_dry("--make-target", success=False)

    def test_make_target_override_creates_distribution_archive(self):
        (self.root / "apps/calendar/Makefile").write_text(
            ".PHONY: appstore build\n"
            "appstore:\n\t@false\n"
            "build:\n"
            "\tmkdir -p build/release/calendar/appinfo\n"
            "\tcp appinfo/info.xml build/release/calendar/appinfo/\n"
            "\tprintf 'distribution' > build/release/calendar/packaged\n"
            "\ttar -czf build/release/calendar.tgz -C build/release calendar\n"
        )
        result = subprocess.run(
            ["bash", str(SCRIPT), "--only", "calendar",
             "--make-target", "calendar=build", "-o", "out.tgz"],
            cwd=self.root, env=self.env, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("packaging with rule 'make-build'", result.stdout)
        with tarfile.open(self.root / "out.tgz") as archive:
            self.assertEqual(
                archive.extractfile("apps/calendar/packaged").read(), b"distribution"
            )
            self.assertNotIn("apps/calendar/Makefile", archive.getnames())
        # A failed target must not use a tarball it produced before failing.
        with (self.root / "apps/calendar/Makefile").open("a") as makefile:
            makefile.write("\tfalse\n")
        failed = subprocess.run(
            ["bash", str(SCRIPT), "--only", "calendar",
             "--make-target=calendar=build", "-o", "failed.tgz"],
            cwd=self.root, env=self.env, text=True, capture_output=True,
        )
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("packaging rule 'make-build' failed", failed.stderr)
        self.assertFalse((self.root / "failed.tgz").exists())

    def test_dry_run_previews_all_methods_without_running_build_tools(self):
        (self.root / "apps/modern/.git").touch()
        (self.root / "apps/legacy/.git").mkdir()
        (self.root / "apps/legacy/package.json").write_text("{}")
        (self.root / "apps/modern/Makefile").write_text(
            "SIDE_EFFECT := $(shell touch ../../make-was-run)\n"
            "appstore:\n\t+touch ../../recipe-was-run\n"
        )
        make = self.root / "bin/make"
        make.write_text("#!/bin/sh\ntouch make-was-run\nexit 1\n")
        make.chmod(0o755)
        krankerl = self.root / "bin/krankerl"
        krankerl.write_text("#!/bin/sh\ntouch krankerl-was-run\nexit 1\n")
        krankerl.chmod(0o755)
        (self.root / "apps/disabled/.git").touch()
        (self.root / "apps/disabled/krankerl.toml").touch()
        tempdir = self.root / "temporary"
        tempdir.mkdir()
        self.env["TMPDIR"] = str(tempdir)
        output = self.run_dry()
        self.assertIn("[calendar] would copy verbatim", output)
        self.assertIn("[modern] would package with rule 'make-appstore'", output)
        self.assertIn("[disabled] would package with rule 'krankerl'", output)
        self.assertIn("[legacy] would use heuristic cleanup", output)
        self.assertIn("would archive 4 apps", output)
        self.assertIn("[files] excluded", output)
        self.assertIn(
            "[modern] would use heuristic cleanup",
            self.run_dry("-n", "--only", "modern", "-s", "new-stage"),
        )

    def test_dry_run_filters_and_continue_preserve_staging_and_archive(self):
        (self.root / "stage/apps/calendar").mkdir(parents=True)
        partial = self.root / "stage/.partial/modern/incomplete"
        partial.parent.mkdir(parents=True)
        partial.write_text("keep")
        (self.root / "out.tgz").write_bytes(b"existing archive")
        output = self.run_dry(
            "-s", "stage", "-c", "--only", "calendar,modern,disabled",
            "-x", ":disabled",
        )
        self.assertIn("[calendar] already staged, skipping", output)
        self.assertIn("[modern] would copy verbatim", output)
        self.assertIn("[disabled] excluded", output)
        self.assertIn("would archive 2 apps", output)
        self.assertIn(
            "would archive 0 apps",
            self.run_dry("-s", "stage", "-c", "--only="),
        )
        self.run_dry("-s", "stage", success=False)

    def test_dry_run_legacy_selection_and_query_errors(self):
        output = self.run_dry("--only", ":legacy")
        self.assertIn("[calendar] would copy verbatim", output)
        self.assertNotIn("[modern] would", output)
        self.run_dry("-c", success=False)
        self.run_dry("-x", ":unknown", success=False)
        self.env["PHP_STATUS"] = "1"
        self.assertIn(
            "cannot query", self.run_dry("--only", ":disabled", success=False)
        )


if __name__ == "__main__":
    unittest.main()
