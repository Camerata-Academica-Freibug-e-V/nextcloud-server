#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Run focused tests for changed repository tools without starting application suites."""

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TESTS = {
    "build/tests/test-pack-apps.py": {
        "build/pack-apps.sh", "build/has-appstore-target.py",
    },
    "build/tests/test-pack-support-app.py": {"build/pack-support-app.py", "Makefile"},
    "tests/test_generate_file_commits.py": {"build/generate-file-commits"},
    "tests/test_update_apps.py": {"update-apps.sh"},
    "build/integration/tests/test_install_dependencies.py": {
        "build/integration/install-dependencies.py",
    },
    "build/tests/test_run_tool_tests.py": {"build/run-tool-tests.py"},
}
POLICY_TEST = ".github/tests/workflow-filters.test.mjs"


def is_tool(path):
    file = PurePosixPath(path)
    return (
        path in {"Makefile", "build/generate-file-commits"}
        or (file.suffix in {".py", ".sh"} and (len(file.parts) == 1 or file.parts[0] == "build"))
        or (file.parent == PurePosixPath("tests") and file.match("test_*.py"))
    )


def select_tests(files, root=ROOT, all_tests=False):
    changed = set(files)
    run_all = all_tests or bool(changed & {
        "build/run-tool-tests.py", ".github/workflows/tooling.yml",
    })
    selected = {
        test for test, sources in TESTS.items()
        if (root / test).is_file() and (run_all or bool(changed & (sources | {test})))
    }
    if run_all or POLICY_TEST in changed or any(
        PurePosixPath(path).parent == PurePosixPath(".github/workflows")
        and PurePosixPath(path).suffix in {".yml", ".yaml"} for path in changed
    ):
        selected.add(POLICY_TEST)
    covered = set().union(*(TESTS.get(test, set()) | {test} for test in selected))
    uncovered = sorted(path for path in changed if is_tool(path) and path not in covered)
    return sorted(selected), uncovered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files-json", default="[]", help="JSON array of changed paths")
    parser.add_argument("--all", action="store_true", help="Run all available tool tests")
    args = parser.parse_args(argv)
    files = json.loads(args.files_json)
    if not isinstance(files, list) or not all(isinstance(path, str) for path in files):
        parser.error("--files-json must be an array of paths")
    for path in files:
        file = PurePosixPath(path)
        if file.is_absolute() or ".." in file.parts:
            parser.error(f"Path must be relative to the repository: {path!r}")

    tests, uncovered = select_tests(files, all_tests=args.all)
    for path in files:
        if not is_tool(path) or not (ROOT / path).is_file():
            continue
        if path.endswith(".sh"):
            subprocess.run(["bash", "-n", "--", path], cwd=ROOT, check=True)
        elif path.endswith(".py") or path == "build/generate-file-commits":
            compile((ROOT / path).read_text(), path, "exec")
    for path in uncovered:
        print(f"::notice file={path}::No dedicated test is registered for this tool.", flush=True)
    if "Makefile" in files:
        print("::notice file=Makefile::Dedicated tests cover distribution-support only.", flush=True)
    for test in tests:
        print(f"Running {test}", flush=True)
        if test == POLICY_TEST:
            command = ["node", "--test", test]
        else:
            command = [sys.executable, "-m", "unittest", test]
        subprocess.run(command, cwd=ROOT, check=True)
    if not tests:
        print("No dedicated tests selected; see notices for tools without coverage.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
