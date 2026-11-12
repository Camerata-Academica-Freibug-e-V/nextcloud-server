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

    def test_current_checkout_reference(self):
        with patch(
            "subprocess.check_output",
            side_effect=[
                b"review/my-branch\n",
                b"https://github.com/owner/repository.git\n",
            ],
        ):
            self.assertEqual(
                SCRIPT["current_checkout_reference"](),
                ("owner/repository", "review/my-branch"),
            )

    def test_default_base_follows_stable_branch_suffix(self):
        for branch, expected in [
            ("cjh-stable35", ("nextcloud/server", "stable35")),
            ("feature/stable36", ("nextcloud/server", "stable36")),
            ("review/branch", ("nextcloud/server", "stable35")),
        ]:
            with self.subTest(branch=branch):
                self.assertEqual(SCRIPT["default_base_reference"](branch), expected)

    def test_local_reference_uses_matching_remote_tracking_branch(self):
        commit = self.git("rev-parse", "base")
        self.git("remote", "add", "upstream", "https://github.com/nextcloud/server.git")
        self.git("update-ref", "refs/remotes/upstream/stable35", commit)

        self.assertEqual(
            SCRIPT["local_reference"](self.directory, ("nextcloud/server", "stable35")),
            "refs/remotes/upstream/stable35",
        )

    def test_local_reference_fails_when_branch_is_not_cached(self):
        self.git("remote", "add", "upstream", "https://github.com/nextcloud/server.git")

        with self.assertRaisesRegex(RuntimeError, "fetch it before using --local-only"):
            SCRIPT["local_reference"](self.directory, ("nextcloud/server", "stable35"))

    def test_no_arguments_uses_default_references(self):
        git_calls = []

        def fake_git(directory, *args):
            git_calls.append(args)
            return b""

        git = patch.dict(SCRIPT["main"].__globals__, {
            "git": fake_git,
            "write_csv": lambda directory, repository, output: None,
            "current_checkout_reference": lambda: ("owner/repository", "review/branch"),
        })
        with git:
            self.assertEqual(SCRIPT["main"]([]), 0)

        self.assertIn((
            "fetch", "--quiet", "--no-tags", "--filter=blob:none",
            "https://github.com/nextcloud/server.git",
            "+refs/heads/stable35:refs/heads/base",
        ), git_calls)
        self.assertIn((
            "fetch", "--quiet", "--no-tags", "--filter=blob:none",
            "https://github.com/owner/repository.git",
            "+refs/heads/review/branch:refs/heads/target",
        ), git_calls)

    def test_local_only_uses_local_refs_without_fetching(self):
        references = []
        written = []
        globals_ = SCRIPT["main"].__globals__

        def fake_local_reference(directory, reference):
            references.append(reference)
            return f"refs/remotes/cached/{reference[1]}"

        with patch.dict(globals_, {
            "current_checkout_reference": lambda: ("owner/repository", "cjh-stable35"),
            "local_reference": fake_local_reference,
            "write_csv": lambda *args: written.append(args),
            "git": lambda *args: self.fail("unexpected git invocation"),
        }):
            self.assertEqual(SCRIPT["main"](["--local-only"]), 0)

        self.assertEqual(references, [
            ("nextcloud/server", "stable35"),
            ("owner/repository", "cjh-stable35"),
        ])
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0][1], "owner/repository")
        self.assertEqual(written[0][3:], (
            "refs/remotes/cached/stable35",
            "refs/remotes/cached/cjh-stable35",
        ))

    def test_explicit_references_override_defaults(self):
        git_calls = []

        def fake_git(directory, *args):
            git_calls.append(args)
            return b""

        with patch.dict(SCRIPT["main"].__globals__, {
            "git": fake_git,
            "write_csv": lambda directory, repository, output: None,
            "current_checkout_reference": lambda: self.fail("unexpected default lookup"),
        }):
            self.assertEqual(SCRIPT["main"]([
                "example/base#release",
                "example/fork#review/branch",
            ]), 0)

        self.assertIn((
            "fetch", "--quiet", "--no-tags", "--filter=blob:none",
            "https://github.com/example/base.git",
            "+refs/heads/release:refs/heads/base",
        ), git_calls)
        self.assertIn((
            "fetch", "--quiet", "--no-tags", "--filter=blob:none",
            "https://github.com/example/fork.git",
            "+refs/heads/review/branch:refs/heads/target",
        ), git_calls)

    def test_help_shows_default_references(self):
        output = io.StringIO()
        with patch("sys.stdout", output):
            with self.assertRaises(SystemExit) as error:
                SCRIPT["main"](["--help"])
        self.assertEqual(error.exception.code, 0)
        help_text = output.getvalue()
        self.assertIn("OWNER/REPO#BASE_BRANCH", help_text)
        self.assertIn("OWNER/REPO#TARGET_BRANCH", help_text)
        self.assertIn("--local-only", help_text)
        self.assertIn("nextcloud/server#stable35", help_text)
        self.assertIn("current checkout's origin repository and branch", help_text)
        self.assertIn("semicolon separator", help_text)
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
