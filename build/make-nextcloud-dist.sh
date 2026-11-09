#!/usr/bin/env bash
# Build a Nextcloud distribution tarball from a checkout (no signing).
# Usage: make-dist.sh [path-to-checkout] [output-dir]
set -euo pipefail

SRC="$(realpath "${1:-.}")"
OUT="$(realpath -m "${2:-$PWD}")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$SRC"
git submodule update --init --recursive

VERSION="$(php -r 'require "version.php"; echo implode(".", array_slice($OC_Version, 0, 3));')"
REV="$(git rev-parse --short HEAD)"
NAME="nextcloud-${VERSION}-${REV}"
DEST="$WORK/nextcloud"
mkdir -p "$DEST" "$OUT"

# 1. Clean export of tracked files, including submodules (working tree state)
git ls-files -z --recurse-submodules | tar --null -T - -cf - | tar -xf - -C "$DEST"

cd "$DEST"

# 2. PHP dependencies (root and bundled apps)
composer install --no-dev --optimize-autoloader --no-interaction
for f in apps/*/composer.json; do
	[ -f "$f" ] || continue
	(cd "$(dirname "$f")" && composer install --no-dev --optimize-autoloader --no-interaction)
done

# 3. Frontend build
npm ci
npm run build
[ -x build/npm-post-build.sh ] && build/npm-post-build.sh

# 4. Bundled apps with their own frontend
for f in apps/*/package.json; do
	[ -f "$f" ] || continue
	if grep -q '"build"' "$f"; then
		(cd "$(dirname "$f")" && npm ci && npm run build)
	fi
done

# 5. Prune dev-only content
find . -type d -name node_modules -prune -exec rm -rf {} +
find . -type d \( -name tests -o -name cypress -o -name .github \) -prune -exec rm -rf {} +
rm -rf build
find . \( -name '.git*' -o -name '*.map' -o -name 'package.json' -o -name 'package-lock.json' \
	-o -name 'composer.lock' \) -prune -exec rm -rf {} +

# 8. Package and checksum
cd "$WORK"
tar -cjf "$OUT/$NAME.tar.bz2" nextcloud
(cd "$OUT" && sha256sum "$NAME.tar.bz2" > "$NAME.tar.bz2.sha256")
echo "Created $OUT/$NAME.tar.bz2"
