#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "pack_support", Path(__file__).resolve().parents[1] / "pack-support-app.py"
)
PACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK)


class SupportTest(unittest.TestCase):
    def test_download(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "download"
            with patch.object(PACK.urllib.request, "urlopen", return_value=io.BytesIO(b"archive")):
                PACK.download("https://example.invalid/archive", target)
            self.assertEqual(target.read_bytes(), b"archive")

    def test_release_selection(self):
        index = "\n".join(f'nextcloud-{version}.tar.bz2' for version in (
            "34.0.9", "35.0.1", "35.0.2", "35.0.3rc1", "35.0.4", "35.1.0", "36.0.0",
        ))
        self.assertEqual(PACK.select_release(index, (35, 0, 2)), "35.0.2")
        self.assertEqual(PACK.select_release(index, (35, 0, 3)), "35.0.2")
        with self.assertRaisesRegex(ValueError, "No stable release"):
            PACK.select_release(index, (33, 0, 1))

    def test_repack_and_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "server.tar.bz2"
            with tarfile.open(source, "w:bz2") as archive:
                for name in (
                    "nextcloud/apps/support/appinfo/info.xml",
                    "nextcloud/apps/support/COPYING",
                    "nextcloud/apps/files/other",
                    "nextcloud/config/config.php",
                ):
                    data = name.encode()
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
            checksum = root / "checksum"
            checksum.write_text(hashlib.sha256(source.read_bytes()).hexdigest() + "  server.tar.bz2")
            output = root / "dist/support.tar.xz"
            PACK.repack(source, checksum, output)
            with tarfile.open(output, "r:xz") as archive:
                names = archive.getnames()
                self.assertIn("nextcloud/apps/support/appinfo/info.xml", names)
                self.assertEqual(archive.extractfile("nextcloud/apps/support/COPYING").read(),
                                 b"nextcloud/apps/support/COPYING")
                self.assertTrue(all(name == "nextcloud/apps/support"
                                    or name.startswith("nextcloud/apps/support/")
                                    for name in names))
            self.assertEqual(output.with_name(output.name + ".sha256").read_text(),
                             f"{hashlib.sha256(output.read_bytes()).hexdigest()}  {output.name}\n")
            checksum.write_text("0" * 64)
            with self.assertRaisesRegex(ValueError, "mismatch"):
                PACK.repack(source, checksum, output)
            checksum.write_text("invalid")
            with self.assertRaisesRegex(ValueError, "Invalid"):
                PACK.repack(source, checksum, output)
            checksum.write_text("")
            with self.assertRaisesRegex(ValueError, "Invalid"):
                PACK.repack(source, checksum, output)

    def test_main_downloads_selected_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "version.php").write_text("<?php $OC_Version = [35, 0, 3, 0];")
            source = root / "fixture.tar.bz2"
            with tarfile.open(source, "w:bz2") as archive:
                archive.addfile(tarfile.TarInfo("nextcloud/apps/support/appinfo/info.xml"))
            urls = []

            def download(url, destination):
                urls.append(url)
                if url == PACK.RELEASES_URL:
                    destination.write_text("nextcloud-35.0.2.tar.bz2 nextcloud-36.0.0.tar.bz2")
                elif url.endswith(".sha256"):
                    destination.write_text(hashlib.sha256(source.read_bytes()).hexdigest())
                else:
                    destination.write_bytes(source.read_bytes())

            with patch.object(PACK, "download", download), patch(
                "sys.argv", ["pack-support-app.py", str(root), str(root / "dist")]
            ):
                PACK.main()
            self.assertEqual(urls, [
                PACK.RELEASES_URL,
                PACK.RELEASES_URL + "nextcloud-35.0.2.tar.bz2.sha256",
                PACK.RELEASES_URL + "nextcloud-35.0.2.tar.bz2",
            ])
            self.assertTrue((root / "dist/support-nextcloud-35.0.2.tar.xz").is_file())

    def test_missing_support_and_unsafe_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for unsafe in (False, True):
                source = root / "server.tar"
                with tarfile.open(source, "w") as archive:
                    if unsafe:
                        archive.addfile(tarfile.TarInfo("nextcloud/apps/support/appinfo/info.xml"))
                        link = tarfile.TarInfo("nextcloud/apps/support/outside")
                        link.type = tarfile.SYMTYPE
                        link.linkname = "/etc"
                        archive.addfile(link)
                checksum = root / "checksum"
                checksum.write_text(hashlib.sha256(source.read_bytes()).hexdigest())
                with self.assertRaises((ValueError, tarfile.FilterError)):
                    PACK.repack(source, checksum, root / "support.tar.xz")
                self.assertFalse((root / "support.tar.xz").exists())


if __name__ == "__main__":
    unittest.main()
