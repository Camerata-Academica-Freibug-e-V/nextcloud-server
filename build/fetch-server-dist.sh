#!/usr/bin/env bash
#
# SPDX-FileCopyrightText: 2026 Claus-Justus Heine
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Download the server tarball built by the "Server distribution tarball"
# workflow (dist-server.yml) and verify its checksum.
#
# Usage: fetch-server-dist.sh [-r REPO] [-d DIR] [-p] [-h]
#   -r  repository (default: Camerata-Academica-Freibug-e-V/nextcloud-server)
#   -d  destination directory (default: .)
#   -p  fetch the previous successful run instead of the latest one
#   -h  display this header and exit
#
# Requires the GitHub CLI (gh) with a valid login (gh auth login, or GH_TOKEN
# in the environment). ssh-agent forwarding does not authenticate the GitHub
# API, so a token is needed on the machine running this script.
set -euo pipefail

REPO=Camerata-Academica-Freibug-e-V/nextcloud-server
DEST=.
SKIP=0

while getopts 'r:d:ph' opt; do
	case $opt in
		r) REPO=$OPTARG ;;
		d) DEST=$OPTARG ;;
		p) SKIP=1 ;;
		h) sed -n '/^# Download/,/^set /{ /^#/{ s/^# \{0,1\}//; p; }; }' "$0"; exit 0 ;;
		*) exit 2 ;;
	esac
done

RUN_ID=$(gh run list --repo "$REPO" --workflow dist-server.yml --status success \
	--limit $((SKIP + 1)) --json databaseId --jq ".[$SKIP].databaseId // empty")
if [[ -z $RUN_ID ]]; then
	echo "no matching successful run found in $REPO" >&2
	exit 1
fi

mkdir -p -- "$DEST"
echo "downloading artifact server-dist of run $RUN_ID to $DEST"
gh run download "$RUN_ID" --repo "$REPO" -n server-dist -D "$DEST"
(cd "$DEST" && sha256sum -c -- *.sha256)
