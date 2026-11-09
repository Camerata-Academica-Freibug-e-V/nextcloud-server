#!/usr/bin/env bash
#
# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Pack the apps below an apps directory into a single tar archive.
#
#  - apps without .git (dir or file) are copied verbatim
#  - apps with a known packaging rule (make appstore, krankerl) are packaged
#    with that rule and the resulting tarball is unpacked into the staging dir
#  - all other git apps are cleaned heuristically: built JS assets must exist,
#    then node_modules/, vendor-bin/*, VCS files, top-level test suites
#    (test/, tests/, phpunit/, unit/) and (for JS apps) src/ are dropped
#
# Usage: pack-apps.sh [-a APPS_DIR] [-o OUTPUT.tar.gz] [-s STAGING_DIR] [-c]
#                     [-x EXCLUDES] [-k] [-n] [APP ...]
#   -a  apps directory (default: ./apps)
#   -o  output archive (default: ./apps-YYYYmmdd-HHMMSS.tar.gz)
#   -s  staging directory, kept after the run (default: temporary, removed)
#   -c  continue: skip apps already present in the staging directory
#   -x  comma or space separated apps to skip (default: the apps shipped in
#       apps/ of the server repository, see DEFAULT_EXCLUDES);
#       pass -x '' to skip nothing
#   -k  keep going: skip failing apps instead of aborting
#   -n  never run packaging rules, always use the heuristic
#   APP restrict to the given app ids; the exclude list is not applied

set -euo pipefail

APPS_DIR=./apps
OUTPUT=./apps-$(date +%Y%m%d-%H%M%S).tar.gz
KEEP_GOING=0
NO_RULES=0
STAGING=
CONTINUE=0
DEFAULT_EXCLUDES="
	admin_audit appstore cloud_federation_api comments contactsinteraction
	dashboard dav encryption federatedfilesharing federation files
	files_external files_reminders files_sharing files_trashbin files_versions
	lookup_server_connector oauth2 profile provisioning_api settings
	sharebymail sharing systemtags testing theming twofactor_backupcodes
	updatenotification user_ldap user_status weather_status
	webhook_listeners workflowengine
"
EXCLUDES=$DEFAULT_EXCLUDES

while getopts "a:o:s:cx:kn" opt; do
	case $opt in
		a) APPS_DIR=$OPTARG ;;
		o) OUTPUT=$OPTARG ;;
		s) STAGING=$OPTARG ;;
		c) CONTINUE=1 ;;
		x) EXCLUDES=$OPTARG ;;
		k) KEEP_GOING=1 ;;
		n) NO_RULES=1 ;;
		*) sed -n '/^# Usage/,/^$/p' "$0"; exit 2 ;;
	esac
done
shift $((OPTIND - 1))

APPS_DIR=$(realpath "$APPS_DIR")
OUTPUT=$(realpath -m "$OUTPUT")

if [[ -z $STAGING ]]; then
	[[ $CONTINUE -eq 0 ]] || { echo "-c requires -s STAGING_DIR" >&2; exit 2; }
	STAGING=$(mktemp -d)
	trap 'rm -rf "$STAGING"' EXIT
else
	STAGING=$(realpath -m "$STAGING")
	if [[ $CONTINUE -eq 0 && -d $STAGING/apps ]] && [[ -n $(ls -A "$STAGING/apps") ]]; then
		echo "staging directory $STAGING/apps is not empty; use -c to continue or remove it" >&2
		exit 2
	fi
fi
# Apps are built below .partial/ and moved to apps/ only when complete, so an
# interrupted run never leaves a half-staged app that -c would skip.
PARTIAL=$STAGING/.partial
rm -rf "$PARTIAL"
mkdir -p "$STAGING/apps" "$PARTIAL"

declare -A EXCLUDED=()
for app in ${EXCLUDES//,/ }; do EXCLUDED[$app]=1; done

log() { printf '[%s] %s\n' "$1" "$2" >&2; }
die() { log "$1" "ERROR: $2"; return 1; }

# Prints the name of a packaging rule for the app, or nothing.
detect_rule() {
	local dir=$1
	[[ $NO_RULES -eq 1 ]] && return 0
	if [[ -f $dir/Makefile ]] && make -C "$dir" -n appstore >/dev/null 2>&1; then
		echo make-appstore
	elif [[ -f $dir/krankerl.toml ]] && command -v krankerl >/dev/null; then
		echo krankerl
	fi
}

# Runs the packaging rule and unpacks the produced tarball into the staging dir.
package_with_rule() {
	local app=$1 dir=$2 rule=$3 dest=$4 marker tarball
	marker=$(mktemp)
	case $rule in
		make-appstore) (cd "$dir" && make appstore) >&2 ;;
		krankerl) (cd "$dir" && krankerl package) >&2 ;;
	esac
	# Pick the newest tarball produced by the rule (location differs between apps).
	tarball=$(find "$dir/build" -type f \( -name '*.tar.gz' -o -name '*.tgz' \) \
		-newer "$marker" -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1 | cut -d' ' -f2-)
	rm -f "$marker"
	[[ -n $tarball ]] || { die "$app" "no tarball found below $dir/build after '$rule'"; return 1; }
	log "$app" "using $tarball"

	local tmp
	tmp=$(mktemp -d)
	tar -xzf "$tarball" -C "$tmp"
	if [[ -d $tmp/$app ]]; then
		mv "$tmp/$app" "$dest"
	else
		rm -rf "$tmp"
		die "$app" "tarball does not contain top-level folder '$app'"
		return 1
	fi
	rm -rf "$tmp"
}

# Checks that a git checkout looks built, i.e. it is usable without a build step.
check_built() {
	local app=$1 dir=$2
	if [[ -f $dir/package.json ]]; then
		if ! find "$dir/js" -type f \( -name '*.js' -o -name '*.mjs' \) -print -quit 2>/dev/null | grep -q .; then
			die "$app" "package.json present but no built assets below js/"
			return 1
		fi
	fi
	if [[ -f $dir/composer.json ]] \
		&& jq -e '(.require // {}) | with_entries(select(.key != "php" and (.key | startswith("ext-") | not))) | length > 0' \
			"$dir/composer.json" >/dev/null 2>&1 \
		&& [[ ! -f $dir/vendor/autoload.php ]]; then
		die "$app" "composer runtime dependencies declared but vendor/autoload.php missing"
		return 1
	fi
}

package_heuristic() {
	local app=$1 dir=$2 dest=$3
	local excludes=(--exclude='/.git' --exclude='node_modules/' --exclude='/vendor-bin/*/'
		--exclude='/test/' --exclude='/tests/' --exclude='/phpunit/' --exclude='/unit/')
	check_built "$app" "$dir" || return 1
	# src/ holds frontend sources compiled into js/; only drop it for JS apps.
	[[ -f $dir/package.json ]] && excludes+=(--exclude='/src/')
	rsync -a "${excludes[@]}" "$dir/" "$dest/"
}

process_app() {
	local app=$1 dir=$APPS_DIR/$1 dest=$2 rule

	if [[ ! -e $dir/.git ]]; then
		log "$app" "no .git, copying verbatim"
		cp -a "$dir" "$dest"
		return 0
	fi

	rule=$(detect_rule "$dir")
	if [[ -n $rule ]]; then
		log "$app" "packaging with rule '$rule'"
		package_with_rule "$app" "$dir" "$rule" "$dest"
	else
		log "$app" "no packaging rule, using heuristic cleanup"
		package_heuristic "$app" "$dir" "$dest"
	fi
}

if [[ $# -gt 0 ]]; then
	APPS=("$@")
else
	APPS=()
	while IFS= read -r app; do
		if [[ -n ${EXCLUDED[$app]:-} ]]; then
			log "$app" "excluded"
		else
			APPS+=("$app")
		fi
	done < <(find "$APPS_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
fi

FAILED=()
for app in "${APPS[@]}"; do
	if [[ ! -f $APPS_DIR/$app/appinfo/info.xml ]]; then
		log "$app" "not an app, skipping"
		continue
	fi
	if [[ -d $STAGING/apps/$app ]]; then
		if [[ $CONTINUE -eq 1 ]]; then
			log "$app" "already staged, skipping"
			continue
		fi
		rm -rf "${STAGING:?}/apps/$app"
	fi
	if process_app "$app" "$PARTIAL/$app"; then
		mv "$PARTIAL/$app" "$STAGING/apps/$app"
	else
		rm -rf "${PARTIAL:?}/$app"
		[[ $KEEP_GOING -eq 1 ]] || exit 1
		FAILED+=("$app")
	fi
done
rmdir "$PARTIAL"

tar -czf "$OUTPUT" -C "$STAGING" apps
log pack "wrote $OUTPUT"
if [[ ${#FAILED[@]} -gt 0 ]]; then
	log pack "skipped failing apps: ${FAILED[*]}"
	exit 1
fi
