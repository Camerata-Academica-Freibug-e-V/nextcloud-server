#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Repack the support app from an official Nextcloud server distribution."""

import argparse
import hashlib
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path


RELEASES_URL = "https://download.nextcloud.com/server/releases/"


def select_release(index, version):
    """Prefer the exact stable version, otherwise an older patch in its series."""
    versions = {
        tuple(map(int, match))
        for match in re.findall(r'nextcloud-(\d+)\.(\d+)\.(\d+)\.tar\.bz2', index)
    }
    candidates = [
        candidate for candidate in versions
        if candidate[:2] == version[:2] and candidate <= version
    ]
    if not candidates:
        raise ValueError(f"No stable release at or below {version} in the same major/minor series")
    return ".".join(map(str, max(candidates)))


def download(url, destination):
    with urllib.request.urlopen(url, timeout=120) as response:
        with destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)


def repack(source, checksum, output):
    """Verify the download and extract only the support app using safe tar filters."""
    fields = checksum.read_text().split()
    expected = fields[0] if fields else ""
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
        raise ValueError("Invalid upstream SHA256 checksum")
    with source.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected.lower():
        raise ValueError("Upstream distribution SHA256 checksum mismatch")

    with tempfile.TemporaryDirectory(prefix="nextcloud-support-") as directory:
        root = Path(directory)
        with tarfile.open(source, "r:*") as archive:
            members = [
                member for member in archive.getmembers()
                if member.name == "nextcloud/apps/support"
                or member.name.startswith("nextcloud/apps/support/")
            ]
            if not any(member.name == "nextcloud/apps/support/appinfo/info.xml"
                       and member.isfile() for member in members):
                raise ValueError("Official distribution contains no support appinfo/info.xml")
            archive.extractall(root, members=members, filter="data")
        support = root / "nextcloud/apps/support"
        # Keep upstream sources, license files and metadata verbatim.
        with tarfile.open(root / "support.tar.xz", "w:xz") as archive:
            archive.add(support, arcname="support")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root / "support.tar.xz"), output)
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    output.with_name(output.name + ".sha256").write_text(f"{digest}  {output.name}\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            __doc__ + " Uses the exact stable version from version.php or the newest "
            "older patch in the same major/minor series; prereleases are not selected. "
            "Writes support-nextcloud-VERSION.tar.xz (top-level support/) and its "
            "SHA256 checksum, preserving the upstream app's licenses and metadata."
        ),
        epilog="Requires PHP and Python 3.12+. No app build or Nextcloud installation is needed.",
    )
    parser.add_argument("checkout", nargs="?", type=Path, default=Path("."))
    parser.add_argument("output_dir", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = subprocess.run(
            ["php", "-r",
             'require $argv[1]; echo implode(".", array_slice($OC_Version, 0, 3));',
             str(args.checkout.resolve() / "version.php")],
            check=True, text=True, capture_output=True,
        )
        if not re.fullmatch(r"\d+\.\d+\.\d+", result.stdout):
            raise ValueError("Invalid OC_Version in version.php")
        version = tuple(map(int, result.stdout.split(".")))
        with tempfile.TemporaryDirectory(prefix="nextcloud-release-") as directory:
            work = Path(directory)
            download(RELEASES_URL, work / "index")
            release = select_release((work / "index").read_text(), version)
            name = f"nextcloud-{release}.tar.bz2"
            print(f"Using official Nextcloud {release} for checkout {result.stdout}", flush=True)
            download(RELEASES_URL + name + ".sha256", work / "checksum")
            download(RELEASES_URL + name, work / name)
            output = args.output_dir.resolve() / f"support-nextcloud-{release}.tar.xz"
            repack(work / name, work / "checksum", output)
            print(f"Created {output}")
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
