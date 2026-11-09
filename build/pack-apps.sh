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
#                     [-x EXCLUDES] [-i ONLY] [-k] [-n] [--dry-run] [APP ...]
#   -a  apps directory (default: ./apps)
#   -o  output archive (default: ./apps-YYYYmmdd-HHMMSS.tar.gz)
#   -s  staging directory, kept after the run (default: temporary, removed)
#   -c  continue: skip apps already present in the staging directory
#   -x, --exclude LIST  comma/space separated app names or classes to exclude
#       (adds to the default :server exclusion; :no-server cancels it)
#   -i, --only LIST     select only these app names or classes (union)
#       :server     apps with directly tracked files in Git's current index
#                   below APPS_DIR (submodules and untracked apps excluded)
#       :no-server  cancel bundled-app exclusion; in --only, non-bundled apps
#       :disabled   apps reported disabled by php ./occ app:list --output=json
#       :legacy     apps without an apparent make appstore/krankerl rule
#       Class matches within a list are combined with app names by union.
#       :disabled requires php and jq and queries occ in the current folder.
#       :legacy checks rule availability even when -n disables rule execution.
#       Exclusions always win, including for positional APP arguments.
#       Example: --only ':server,calendar' --exclude ':no-server,testing'
#   -k  keep going: skip failing apps instead of aborting
#   -n  never run packaging rules, always use the heuristic
#   --dry-run  preview selection and actions without builds or file changes;
#       make rules are detected from literal appstore targets without invoking
#       make (included/generated rules may not be detected). Still queries occ
#       if :disabled is used. Does not validate built assets or build success.
#   APP further restrict to the given app ids

set -euo pipefail

APPS_DIR=./apps
OUTPUT=./apps-$(date +%Y%m%d-%H%M%S).tar.gz
KEEP_GOING=0
NO_RULES=0
DRY_RUN=0
STAGING=
TMP_STAGING=
CONTINUE=0
EXCLUDES=
ONLY=
ONLY_SET=0
POSITIONAL_APPS=()

while [[ $# -gt 0 ]]; do
	case $1 in
		-a|-o|-s|-x|--exclude|-i|--only)
			[[ $# -ge 2 ]] || { echo "missing argument for $1" >&2; exit 2; }
			case $1 in
				-a) APPS_DIR=$2 ;;
				-o) OUTPUT=$2 ;;
				-s) STAGING=$2 ;;
				-x|--exclude) EXCLUDES+=" $2" ;;
				-i|--only) ONLY+=" $2"; ONLY_SET=1 ;;
			esac
			shift 2
			;;
		--exclude=*) EXCLUDES+=" ${1#*=}"; shift ;;
		--only=*) ONLY+=" ${1#*=}"; ONLY_SET=1; shift ;;
		-c) CONTINUE=1; shift ;;
		-k) KEEP_GOING=1; shift ;;
		-n) NO_RULES=1; shift ;;
		--dry-run) DRY_RUN=1; shift ;;
		--) shift; POSITIONAL_APPS+=("$@"); break ;;
		-*) echo "unknown option: $1" >&2; exit 2 ;;
		*) POSITIONAL_APPS+=("$1"); shift ;;
	esac
done

APPS_DIR=$(realpath "$APPS_DIR")
OUTPUT=$(realpath -m "$OUTPUT")

if [[ -z $STAGING ]]; then
	[[ $CONTINUE -eq 0 ]] || { echo "-c requires -s STAGING_DIR" >&2; exit 2; }
	if [[ $DRY_RUN -eq 0 ]]; then
		STAGING=$(mktemp -d)
		TMP_STAGING=1
	fi
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
if [[ $DRY_RUN -eq 0 ]]; then
	rm -rf "$PARTIAL"
	mkdir -p "$STAGING/apps" "$PARTIAL"
fi

log() { printf '[%s] %s\n' "$1" "$2" >&2; }
die() { log "$1" "ERROR: $2"; return 1; }

# Sets the terminal title, if stderr is a terminal. Inside screen/tmux the
# window name is set as well; otherwise terminfo tsl/fsl are preferred over
# the xterm OSC 2 sequence when the terminal declares a status line.
CMD=$(basename "$0")
SHORT_PWD=$(basename "$(pwd)")
TITLE_MODE=none
if [[ -t 2 && ${TERM:-dumb} != dumb ]]; then
	if [[ -n ${TMUX:-} || $TERM == screen* || $TERM == tmux* ]]; then
		TITLE_MODE=multiplexer
	elif tput hs 2>/dev/null && TSL=$(tput tsl 2>/dev/null) && FSL=$(tput fsl 2>/dev/null) \
		&& [[ -n $TSL && -n $FSL ]]; then
		TITLE_MODE=terminfo
	else
		TITLE_MODE=xterm
	fi
fi
setTitle() {
	local title=
	[[ -n ${1:-} ]] && title=".../$SHORT_PWD - $CMD: $1"
	case $TITLE_MODE in
		multiplexer) printf '\033k%s\033\\\033]2;%s\007' "$title" "$title" >&2 ;;
		terminfo) printf '%s%s%s' "$TSL" "$title" "$FSL" >&2 ;;
		xterm) printf '\033]2;%s\007' "$title" >&2 ;;
	esac
}
# Save the title on the xterm title stack and restore it on exit; terminals
# without a title stack ignore these sequences and fall back to the reset.
if [[ $TITLE_MODE == xterm ]]; then
	printf '\033[22;0t' >&2
	restoreTitle() { setTitle; printf '\033[23;0t' >&2; }
else
	restoreTitle() { setTitle; }
fi
if [[ -n $TMP_STAGING ]]; then
	trap 'restoreTitle; rm -rf "$STAGING"' EXIT
else
	trap restoreTitle EXIT
fi
trap 'exit 130' INT TERM

# Prints the name of a packaging rule for the app, or nothing.
detect_rule() {
	local dir=$1
	if [[ -f $dir/Makefile ]]; then
		if [[ $DRY_RUN -eq 1 ]]; then
			# Even make -n can execute recursive recipes and $(shell ...).
			if grep -qE '^[[:space:]]*appstore[[:space:]]*:' "$dir/Makefile"; then
				echo make-appstore
				return 0
			fi
		elif make -C "$dir" -n appstore >/dev/null 2>&1; then
			echo make-appstore
			return 0
		fi
	fi
	if [[ -f $dir/krankerl.toml ]] && command -v krankerl >/dev/null; then
		echo krankerl
	fi
}

# Runs the packaging rule and unpacks the produced tarball into the staging dir.
package_with_rule() {
	local app=$1 dir=$2 rule=$3 dest=$4 marker tarball
	marker=$(mktemp)
	setTitle "$app ($rule)"
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
		if [[ $DRY_RUN -eq 1 ]]; then
			log "$app" "would copy verbatim (no .git)"
			return 0
		fi
		log "$app" "no .git, copying verbatim"
		cp -a "$dir" "$dest"
		return 0
	fi

	if [[ -n ${RULES[$app]+present} ]]; then
		rule=${RULES[$app]}
	else
		rule=$(detect_rule "$dir")
	fi
	if [[ -n $rule && $NO_RULES -eq 0 ]]; then
		if [[ $DRY_RUN -eq 1 ]]; then
			log "$app" "would package with rule '$rule'"
			return 0
		fi
		log "$app" "packaging with rule '$rule'"
		package_with_rule "$app" "$dir" "$rule" "$dest"
	else
		if [[ $DRY_RUN -eq 1 ]]; then
			log "$app" "would use heuristic cleanup"
			return 0
		fi
		log "$app" "no packaging rule, using heuristic cleanup"
		package_heuristic "$app" "$dir" "$dest"
	fi
}

declare -A SERVER=() DISABLED=() RULES=()
if ! SERVER_APPS=$(
	git -C "$APPS_DIR" ls-files --stage -z -- . |
		while IFS= read -r -d '' entry; do
			mode=${entry%% *}
			path=${entry#*$'\t'}
			if [[ $mode != 160000 && $path == */* ]]; then
				printf '%s\n' "${path%%/*}"
			fi
		done
); then
	die selection "cannot determine server apps from Git's index in $APPS_DIR"
	exit 1
fi
for app in $SERVER_APPS; do SERVER[$app]=1; done

EXCLUDES=${EXCLUDES//,/ }
EXCLUDES=${EXCLUDES//$'\n'/ }
ONLY=${ONLY//,/ }
ONLY=${ONLY//$'\n'/ }
read -r -a EXCLUDE_TOKENS <<< "$EXCLUDES"
read -r -a ONLY_TOKENS <<< "$ONLY"
EXCLUDE_SERVER=1
NEED_DISABLED=0
NEED_LEGACY=0
for token in "${EXCLUDE_TOKENS[@]}" "${ONLY_TOKENS[@]}"; do
	case $token in
		:server|:no-server) ;;
		:disabled) NEED_DISABLED=1 ;;
		:legacy) NEED_LEGACY=1 ;;
		:*) die selection "unknown class: $token"; exit 2 ;;
		*) [[ $token =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]] \
			|| { die selection "invalid app name: $token"; exit 2; } ;;
	esac
done
for token in "${EXCLUDE_TOKENS[@]}"; do
	[[ $token != :no-server ]] || EXCLUDE_SERVER=0
done

if [[ $NEED_DISABLED -eq 1 ]]; then
	if ! APP_STATUS=$(php ./occ app:list --output=json); then
		die selection "cannot query disabled apps using php ./occ app:list --output=json"
		exit 1
	fi
	if ! DISABLED_IDS=$(jq -er '
		.disabled | if type == "object" then keys | join("\n")
		elif . == [] then "" else error("invalid disabled app list") end
	' <<< "$APP_STATUS"); then
		die selection "invalid app:list JSON (jq is required)"
		exit 1
	fi
	while IFS= read -r app; do
		[[ -z $app ]] || DISABLED[$app]=1
	done <<< "$DISABLED_IDS"
fi

matches() {
	local app=$1 token
	shift
	for token in "$@"; do
		case $token in
			:server) [[ -n ${SERVER[$app]:-} ]] && return 0 ;;
			:no-server) [[ -z ${SERVER[$app]:-} ]] && return 0 ;;
			:disabled) [[ -n ${DISABLED[$app]:-} ]] && return 0 ;;
			:legacy) [[ -z ${RULES[$app]:-} ]] && return 0 ;;
			*) [[ $token == "$app" ]] && return 0 ;;
		esac
	done
	return 1
}

# :no-server is a directive in exclusions, not a class to remove.
FILTER_EXCLUDES=()
for token in "${EXCLUDE_TOKENS[@]}"; do
	[[ $token == :no-server ]] || FILTER_EXCLUDES+=("$token")
done
[[ $EXCLUDE_SERVER -eq 0 ]] || FILTER_EXCLUDES+=(:server)

if [[ ${#POSITIONAL_APPS[@]} -gt 0 ]]; then
	CANDIDATES=("${POSITIONAL_APPS[@]}")
else
	mapfile -t CANDIDATES < <(find "$APPS_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
fi
APPS=()
declare -A SEEN=()
for app in "${CANDIDATES[@]}"; do
	[[ $app =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]] \
		|| { die selection "invalid app name: $app"; exit 2; }
	[[ -z ${SEEN[$app]:-} ]] || continue
	SEEN[$app]=1
	if [[ $NEED_LEGACY -eq 1 ]]; then
		RULES[$app]=$(detect_rule "$APPS_DIR/$app")
	fi
	if [[ $ONLY_SET -eq 1 ]] && ! matches "$app" "${ONLY_TOKENS[@]}"; then
		continue
	fi
	if matches "$app" "${FILTER_EXCLUDES[@]}"; then
		log "$app" "excluded"
		continue
	fi
	APPS+=("$app")
done

FAILED=()
ARCHIVE_APPS=()
for app in "${APPS[@]}"; do
	setTitle "$app"
	if [[ ! -f $APPS_DIR/$app/appinfo/info.xml ]]; then
		log "$app" "not an app, skipping"
		continue
	fi
	if [[ -n $STAGING && -d $STAGING/apps/$app ]]; then
		if [[ $CONTINUE -eq 1 ]]; then
			log "$app" "already staged, skipping"
			ARCHIVE_APPS+=("apps/$app")
			continue
		fi
		rm -rf "${STAGING:?}/apps/$app"
	fi
	if process_app "$app" "$PARTIAL/$app"; then
		if [[ $DRY_RUN -eq 0 ]]; then
			mv "$PARTIAL/$app" "$STAGING/apps/$app"
		fi
		ARCHIVE_APPS+=("apps/$app")
	else
		rm -rf "${PARTIAL:?}/$app"
		[[ $KEEP_GOING -eq 1 ]] || exit 1
		FAILED+=("$app")
	fi
done
if [[ $DRY_RUN -eq 1 ]]; then
	log pack "would archive ${#ARCHIVE_APPS[@]} apps to $OUTPUT (dry run; nothing packaged)"
	exit 0
fi
rmdir "$PARTIAL"

setTitle "writing $(basename "$OUTPUT")"
tar -czf "$OUTPUT" -C "$STAGING" --files-from /dev/null -- "${ARCHIVE_APPS[@]}"
log pack "wrote $OUTPUT"
if [[ ${#FAILED[@]} -gt 0 ]]; then
	log pack "skipped failing apps: ${FAILED[*]}"
	exit 1
fi
