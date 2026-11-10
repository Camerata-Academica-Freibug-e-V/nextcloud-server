# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

import csv
import io
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "build/generate-file-commits"))


class GenerateFileCommitsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("commit", "--quiet", "--allow-empty", "-m", "base")
        self.git("branch", "base")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.directory), *args], stderr=subprocess.PIPE
        ).decode().strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")

    def rows(self):
        self.git("branch", "target")
        output = io.StringIO()
        SCRIPT["write_csv"](self.directory, "owner/repository", output)
        return list(csv.reader(io.StringIO(output.getvalue()), delimiter=";"))

    def test_multiple_commits_deleted_file_and_csv_escaping(self):
        path = self.directory / 'a; "file".txt'
        path.write_text("first")
        first = self.commit("add")
        path.write_text("second")
        second = self.commit("update")
        path.unlink()
        deleted = self.commit("delete")
        rows = self.rows()
        self.assertEqual(rows, [[
            f'=HYPERLINK("https://github.com/owner/repository/blob/{second}/a%3B%20%22file%22.txt";"a; ""file"".txt")',
            *[
                f'=HYPERLINK("https://github.com/owner/repository/commit/{commit}";"{subject}")'
                for commit, subject in [
                    (first, "add"), (deleted, "delete"), (second, "update"),
                ]
            ],
        ]])

    def test_rename_lists_both_paths(self):
        (self.directory / "old.txt").write_text("content")
        first = self.commit("add")
        (self.directory / "old.txt").rename(self.directory / "new.txt")
        renamed = self.commit("rename")
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertIn('/new.txt";"new.txt")', rows[0][0])
        self.assertIn(f'/{first}/old.txt";"old.txt")', rows[1][0])
        self.assertEqual(rows[0][1], f'=HYPERLINK("https://github.com/owner/repository/commit/{renamed}";"rename")')
        self.assertEqual(len(rows[1]), 3)

    def test_merge_is_included_once(self):
        self.git("checkout", "--quiet", "-b", "side")
        (self.directory / "side.txt").write_text("side")
        side = self.commit("side")
        self.git("checkout", "--quiet", "-b", "main-test", "base")
        (self.directory / "main.txt").write_text("main")
        main = self.commit("main")
        self.git("merge", "--quiet", "--no-ff", "side", "-m", "merge")
        merge = self.git("rev-parse", "HEAD")
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        for row, changes in [
            (rows[0], [(main, "main"), (merge, "merge")]),
            (rows[1], [(merge, "merge"), (side, "side")]),
        ]:
            self.assertEqual(row[1:], [
                f'=HYPERLINK("https://github.com/owner/repository/commit/{commit}";"{subject}")'
                for commit, subject in changes
            ])

    def test_identical_subjects_are_sorted_by_hash(self):
        path = self.directory / "file.txt"
        path.write_text("first")
        first = self.commit("same subject")
        path.write_text("second")
        second = self.commit("same subject")
        rows = self.rows()
        self.assertEqual(rows[0][1:], [
            f'=HYPERLINK("https://github.com/owner/repository/commit/{commit}";"same subject")'
            for commit in sorted([first, second])
        ])

    def test_subject_formula_characters_are_quoted(self):
        (self.directory / "file.txt").write_text("content")
        subject = '=SUM(1;2), "quoted"'
        commit = self.commit(subject)
        rows = self.rows()
        self.assertEqual(rows[0][1], (
            f'=HYPERLINK("https://github.com/owner/repository/commit/{commit}";'
            '"=SUM(1;2), ""quoted""")'
        ))

    def test_hyperlink_quotes_both_arguments(self):
        self.assertEqual(
            SCRIPT["hyperlink"]('https://example.invalid/"', '"label"'),
            '=HYPERLINK("https://example.invalid/""";"""label""")',
        )

    def test_empty_range(self):
        self.assertEqual(self.rows(), [])

    def test_reference_with_slashes(self):
        for branch in ["stable35", "review/branch", "copilot/fix/issue", "bugfix/issue"]:
            with self.subTest(branch=branch):
                self.assertEqual(
                    SCRIPT["parse_reference"](f"owner/repository#{branch}"),
                    ("owner/repository", branch),
                )

    def test_no_arguments_shows_full_help(self):
        output = io.StringIO()
        with patch("sys.stderr", output):
            self.assertEqual(SCRIPT["main"]([]), 2)
        help_text = output.getvalue()
        self.assertIn("OWNER/REPO#BASE_BRANCH", help_text)
        self.assertIn("OWNER/REPO#TARGET_BRANCH", help_text)
        self.assertIn("semicolon separator", help_text)
        self.assertIn("nextcloud/server#stable35", help_text)
        self.assertIn("sorted by subject line", help_text)
        self.assertIn("commit hash", help_text)
        self.assertIn("Evaluate formulas", help_text)

    def test_invalid_reference(self):
        import argparse

        for reference in [
            "owner/repository", "/repository#branch", "owner/repository#",
            "owner/repository/review/branch", "owner/repository/extra#branch",
        ]:
            with self.subTest(reference=reference):
                with self.assertRaises(argparse.ArgumentTypeError):
                    SCRIPT["parse_reference"](reference)
