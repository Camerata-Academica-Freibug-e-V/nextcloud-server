#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Conservatively find appstore targets without executing Makefile code."""

import os
from pathlib import Path
import re
import sys


VARIABLE = re.compile(r"\$\(([^()]+)\)|\$\{([^{}]+)\}")


def has_appstore_target(directory):
    directory = Path(directory).resolve()
    variables = dict(os.environ, CURDIR=str(directory))
    visited = set()

    def expand(value, seen=frozenset()):
        def substitute(match):
            name = match[1] or match[2]
            if name in seen or name not in variables:
                return match[0]
            return expand(variables[name], seen | {name})

        return VARIABLE.sub(substitute, value)

    def inspect(path):
        path = path.resolve()
        if path in visited or not path.is_file():
            return False
        visited.add(path)
        text = path.read_text().replace("\\\n", " ")
        for line in text.splitlines():
            if line.startswith("\t"):
                continue
            line = line.split("#", 1)[0].strip()
            assignment = re.fullmatch(r"([\w.-]+)\s*(\?=|:=|\+=|=)\s*(.*)", line)
            if assignment:
                name, operator, value = assignment.groups()
                if operator == "?=" and name in variables:
                    continue
                if operator == ":=":
                    value = expand(value)
                if operator == "+=":
                    value = variables.get(name, "") + " " + value
                variables[name] = value
                continue
            include = re.fullmatch(r"(?:-?include|sinclude)\s+(.+)", line)
            if include:
                for filename in expand(include[1]).split():
                    # Make functions and unresolved variables need real Make.
                    if "$" not in filename and inspect(directory / filename):
                        return True
            elif re.match(r"^(?:[\w./-]+\s+)*appstore(?:\s+[\w./-]+)*\s*:(?!=)", line):
                return True
        return False

    for name in ("GNUmakefile", "makefile", "Makefile"):
        if (directory / name).is_file():
            return inspect(directory / name)
    return False


if __name__ == "__main__":
    sys.exit(0 if has_appstore_target(sys.argv[1]) else 1)
