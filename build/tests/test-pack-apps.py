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

    def run_pack(self, *args, success=True):
        result = subprocess.run(
            ["bash", str(SCRIPT), "-n", "-o", "out.tgz", *args],
            cwd=self.root, env=self.env, text=True, capture_output=True,
        )
        if not success:
            self.assertNotEqual(result.returncode, 0, result.stderr)
            return result
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.root / "out.tgz") as archive:
            return {
                name.split("/")[1]
                for name in archive.getnames()
                if name.startswith("apps/")
            }

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


if __name__ == "__main__":
    unittest.main()
