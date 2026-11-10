#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Install CI dependencies with conservative backoff around Composer's HTTP retries."""

import random
import re
import subprocess
import sys
import time


def retry_delay(output, backoff):
    # Composer 2.11.1 parses Retry-After (seconds or HTTP-date), but only waits
    # up to 60 seconds itself. Longer waits are included in its error message.
    requested = re.findall(
        r"the\s+server\s+asked\s+to\s+retry\s+in\s+(\d+)s\b", output,
    )
    return max(backoff, *(int(value) for value in requested)) if requested else backoff


def main():
    for attempt in range(4):
        output = []
        with subprocess.Popen(
            ["composer", "install", "--no-interaction", "--no-progress", "--no-ansi"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        ) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                output.append(line)
            status = process.wait()
        if status == 0:
            return 0
        if attempt == 3:
            print("Composer installation failed after four attempts.", file=sys.stderr)
            return status
        delay = retry_delay("".join(output), 60 * 2 ** attempt) + random.randint(0, 15)
        print(
            f"Composer installation failed (exit {status}); retrying in {delay}s "
            f"(attempt {attempt + 2}/4).",
            file=sys.stderr, flush=True,
        )
        time.sleep(delay)


if __name__ == "__main__":
    sys.exit(main())
