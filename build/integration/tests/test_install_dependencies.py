#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

import contextlib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
import zipfile


SPEC = importlib.util.spec_from_file_location(
    "install_dependencies", Path(__file__).resolve().parents[1] / "install-dependencies.py",
)
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


class InstallDependenciesTest(unittest.TestCase):
    def run_installer(self, results, jitter=0):
        def start(*args, **kwargs):
            status, output = next(outcomes)
            process = MagicMock()
            process.__enter__.return_value = process
            process.stdout = io.StringIO(output)
            process.wait.return_value = status
            return process

        outcomes = iter(results)
        with patch.object(INSTALL.subprocess, "Popen", side_effect=start) as popen, \
                patch.object(INSTALL.time, "sleep") as sleep, \
                patch.object(INSTALL.random, "randint", return_value=jitter), \
                patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            status = INSTALL.main()
        return status, popen, sleep, stdout.getvalue(), stderr.getvalue()

    def test_success_does_not_retry(self):
        status, popen, sleep, stdout, stderr = self.run_installer([(0, "Installed\n")])
        self.assertEqual(status, 0)
        self.assertEqual(popen.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(stdout, "Installed\n")
        self.assertEqual(stderr, "")
        self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.STDOUT)

    def test_exponential_backoff_and_final_failure(self):
        status, popen, sleep, stdout, stderr = self.run_installer(
            [(100, "HTTP 429\n")] * 4, jitter=7,
        )
        self.assertEqual(status, 100)
        self.assertEqual(popen.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [67, 127, 247])
        self.assertEqual(stdout.count("HTTP 429"), 4)
        self.assertIn("failed after four attempts", stderr)

    def test_retry_after_longer_than_native_composer_limit(self):
        output = (
            'The "https://example.invalid/package.zip" file could not be downloaded\n'
            "(HTTP/2 429, the server asked to retry in 300s which is longer than\n"
            "the 60s Composer is willing to wait, try again later)\n"
        )
        status, popen, sleep, stdout, stderr = self.run_installer(
            [(100, output), (0, "Installed\n")], jitter=3,
        )
        self.assertEqual(status, 0)
        self.assertEqual(popen.call_count, 2)
        sleep.assert_called_once_with(303)
        self.assertIn(output, stdout)
        self.assertIn("retrying in 303s", stderr)

    def test_wrapped_and_multiple_reported_waits(self):
        output = (
            "the server asked to retry in 90s\n"
            "  the server asked to retry  \n"
            "  in 600s which is longer than the 60s Composer is willing to wait\n"
        )
        self.assertEqual(INSTALL.retry_delay(output, 60), 600)
        self.assertEqual(INSTALL.retry_delay(output, 900), 900)
        self.assertEqual(INSTALL.retry_delay("Retry-After: invalid", 120), 120)

    def test_missing_composer_is_not_retried(self):
        with patch.object(INSTALL.subprocess, "Popen", side_effect=FileNotFoundError), \
                patch.object(INSTALL.time, "sleep") as sleep:
            with self.assertRaises(FileNotFoundError):
                INSTALL.main()
            sleep.assert_not_called()

    @unittest.skipUnless(shutil.which("composer"), "Composer is required for the HTTP fixture")
    def test_real_composer_retry_after_headers(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("fixture/composer.json", '{"name":"test/retry-fixture"}')
        headers = (
            "300",
            format_datetime(datetime.now(timezone.utc) + timedelta(seconds=600), usegmt=True),
        )
        for header in headers:
            with self.subTest(header=header):
                class Handler(BaseHTTPRequestHandler):
                    requests = 0

                    def do_GET(self):
                        Handler.requests += 1
                        if Handler.requests == 1:
                            self.send_response(429)
                            self.send_header("Retry-After", header)
                            self.end_headers()
                        else:
                            self.send_response(200)
                            self.end_headers()
                            self.wfile.write(archive.getvalue())

                    def log_message(self, *args):
                        pass

                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                try:
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        (root / "composer.json").write_text(json.dumps({
                            "name": "test/project",
                            "require": {"test/retry-fixture": "1.0.0"},
                            "config": {"secure-http": False},
                            "repositories": [
                                {"packagist.org": False},
                                {"type": "package", "package": {
                                    "name": "test/retry-fixture", "version": "1.0.0",
                                    "dist": {
                                        "type": "zip",
                                        "url": f"http://127.0.0.1:{server.server_port}/package.zip",
                                    },
                                }},
                            ],
                        }))
                        env = {
                            "COMPOSER_HOME": str(root / "home"),
                            "COMPOSER_CACHE_DIR": str(root / "cache"),
                            "COMPOSER_ALLOW_SUPERUSER": "1",
                            "XDEBUG_MODE": "off",
                        }
                        output = io.StringIO()
                        with contextlib.chdir(root), patch.dict(os.environ, env), \
                                contextlib.redirect_stdout(output), \
                                contextlib.redirect_stderr(output), \
                                patch.object(INSTALL.time, "sleep") as sleep, \
                                patch.object(INSTALL.random, "randint", return_value=0):
                            status = INSTALL.main()
                        self.assertEqual(status, 0, output.getvalue())
                        self.assertEqual(sleep.call_count, 1, output.getvalue())
                        if header == "300":
                            self.assertEqual(sleep.call_args.args[0], 300)
                        else:
                            self.assertGreaterEqual(sleep.call_args.args[0], 540)
                            self.assertLessEqual(sleep.call_args.args[0], 600)
                        self.assertEqual(Handler.requests, 2, output.getvalue())
                        self.assertTrue((root / "vendor/test/retry-fixture/composer.json").is_file())
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()


if __name__ == "__main__":
    unittest.main()
