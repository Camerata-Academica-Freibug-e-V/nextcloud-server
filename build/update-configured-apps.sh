#!/bin/bash

# SPDX-FileCopyrightText: 2026 Claus-Justus Heine
# SPDX-License-Identifier: AGPL-3.0-or-later

# Run a Bash command instead of updating apps:
# ./build/update-configured-apps.sh --only "calendar contacts" --shell 'pwd; git status --short'
# --shell honors --only and --exclude, and stops on command failure.
# --exclude matches exact app names and applies after --only, regardless of order.

export LC_ALL=C.UTF-8

ALL_APPS="
 activity
 app_api
 bav
 cafevdb
 cafevdbmembers
 calendar
 circles
 collectives
 contacts
 context_chat
 dokuwiki
 emlviewer
 files_archive
 files_lock
 files_pdfviewer
 files_texteditor
 groupfolders
 ldap_write_support
 logreader
 mail
 mail_roundcube
 maps
 notifications
 password_policy
 pdf_downloader
 photos
 privacy
 recommendations
 redaxo
 related_resources
 richdocuments
 serverinfo
 suspicious_login
 terms_of_service
 text
 twofactor_gateway
 twofactor_nextcloud_notification
 twofactor_totp
 user_sql
 viewer
 workflow_pdf_converter
"

CORE_BRANCH=stable35

BUILD=false
JOBS=1
BUILD_APPS=()
CHECKOUT=false
BUILD_MODE=build
PUSH=false
RESET=false
REBASE=false
STATUS=false
LIST=false
SHELL_MODE=false
SHELL_COMMAND=
APPS="${ALL_APPS}"
declare -A EXCLUDED_APPS

declare -A BUILD_COMMANDS
BUILD_COMMANDS=(
    [bav]="make \$BUILD_MODE"
    [cafevdb]="make \$BUILD_MODE"
    [cafevdbmembers]="make \$BUILD_MODE"
    [calendar]="rm -rf node_modules && run-krankerl.sh"
    [collectives]="npm install && make setup-dev node-modules build-js-production composer-install-no-dev"
    [contacts]="run-krankerl.sh"
    [context_chat]="make \$BUILD_MODE"
    [dokuwiki]="make \$BUILD_MODE"
    [emlviewer]="npm install && make"
    [files_archive]="make \$BUILD_MODE"
    [files_lock]="rm -rf node_modules package-lock.json && npm install --legacy-peer-deps && npm ci --legacy-peer-deps && npm run build"
    [groupfolders]="make"
    [ldap_write_support]="run-krankerl.sh"
    [logreader]="make"
    [mail]="make install-deps optimize-js"
    [mail_roundcube]="make \$BUILD_MODE"
    [maps]="rm -rf node_modules package-lock.json && npm install && run-krankerl.sh"
    [notifications]="make"
    [pdf_downloader]="make \$BUILD_MODE"
    # TODO: remove photos, either use photos or memories, not both
    # [photos]="make dev-setup build-js-production && rm -rf vendor/* && composer install --no-dev"
    [photos]="rm -rf vendor/* && composer install --no-dev"
    [redaxo]="make \$BUILD_MODE"
    [richdocuments]="run-krankerl.sh"
    [terms_of_service]=make
    [twofactor_gateway]="run-krankerl.sh"
    [workflow_pdf_converter]="run-krankerl.sh"
)

declare -A STABLE_BRANCHES
STABLE_BRANCHES=(
    [calendar]=stable6.6
    [contacts]=stable8.9
    [context_chat]=main
    [emlviewer]=master
    [mail]=stable5.13
)

declare -A REBASE_BRANCHES
REBASE_BRANCHES=(
    [calendar]=origin/stable6.6
    [contacts]=origin/stable8.9
    [groupfolders]=origin/$CORE_BRANCH
    [ldap_write_support]=origin/$CORE_BRANCH
    [logreader]=origin/$CORE_BRANCH
    [mail]=origin/stable5.13
    [maps]=origin/master
    [related_resources]=origin/$CORE_BRANCH
    [richdocuments]=origin/$CORE_BRANCH
    [terms_of_service]=origin/stable4.8
    [twofactor_gateway]=origin/$CORE_BRANCH
    [workflow_pdf_converter]=origin/$CORE_BRANCH
)

# hard reset branches, meant to update the server
declare -A RESET_BRANCHES
RESET_BRANCHES=(
    [activity]=origin/$CORE_BRANCH
    [app_api]=origin/$CORE_BRANCH
    [bav]=origin/master
    [cafevdb]=origin/nextcloud35
    [cafevdbmembers]=origin/$CORE_BRANCH
    [calendar]=cjh/production/cafevdb/stable6.6
    [circles]=origin/$CORE_BRANCH
    [collectives]=origin/main
    [contacts]=cjh/production/cafevdb/stable8.9
    [context_chat]=origin/main
    [dokuwiki]=origin/master
    [emlviewer]=cjh/production/$CORE_BRANCH
    [files_archive]=origin/main
    [files_lock]=origin/$CORE_BRANCH
    [files_pdfviewer]=origin/$CORE_BRANCH
    [files_texteditor]=origin/master
    [groupfolders]=cjh/production/cafevdb/$CORE_BRANCH
    [ldap_write_support]=cjh/production/cafevdb/$CORE_BRANCH
    [logreader]=cjh/production/cafevdb/$CORE_BRANCH
    [mail]=cjh/feature/stable5.13/provision-additional-email-addresses
    [mail_roundcube]=origin/master
    [maps]=cjh/feature/request-parameter-search
    [notifications]=origin/$CORE_BRANCH
    [password_policy]=origin/$CORE_BRANCH
    [pdf_downloader]=origin/main
    [photos]=origin/$CORE_BRANCH
    [privacy]=origin/$CORE_BRANCH
    [recommendations]=origin/$CORE_BRANCH
    [redaxo]=origin/main
    [related_resources]=origin/$CORE_BRANCH
    [richdocuments]=cjh/feature/authenticated-requests-35
    [serverinfo]=origin/$CORE_BRANCH
    [suspicious_login]=origin/$CORE_BRANCH
    [terms_of_service]=origin/stable4.8
    [text]=origin/$CORE_BRANCH
    [twofactor_gateway]=origin/$CORE_BRANCH
    [twofactor_nextcloud_notification]=origin/$CORE_BRANCH
    [twofactor_totp]=origin/$CORE_BRANCH
    [user_sql]=cjh/production/cafevdb/$CORE_BRANCH
    [viewer]=origin/$CORE_BRANCH
    [workflow_pdf_converter]=cjh/production/rotdrop/$CORE_BRANCH
)

declare -A SUBREPO_APPS
SUBREPO_APPS=(
    [bav]=true
    [cafevdb]=true
    [cafevdbmembers]=true
    [dokuwiki]=true
    [files_archive]=true
    [mail_roundcube]=true
    [pdf_downloader]=true
    [redaxo]=true
)

NCDIR=$(realpath .)
CMD=$(basename "$0")

VALID_ARGS=$(getopt -o bldhrj:e:o:s --long help,build,jobs:,list,dev,only:,exclude:,rebase,status,push,reset,checkout,shell: -- "$@")
# shellcheck disable=SC2181
if [[ $? -ne 0 ]]; then
    exit 1;
fi

eval set -- "$VALID_ARGS"
while true; do
  case "$1" in
    -h|--help)
      cat <<EOF
Usage: $CMD [OPTIONS]

Options:
  -h, --help              Show this help and exit
  -b, --build             Build apps with their configured build command
  -j, --jobs N            Run up to N app builds concurrently (default: 1; only with --build)
  -l, --list              List selected apps and exit
  -d, --dev               Use development build mode
  -o, --only APPS         Select space-separated app names (or "subrepo")
  -e, --exclude APPS      Exclude space-separated app names (or "subrepo")
  -r, --rebase            Rebase apps with configured rebase branches
  -s, --status            Report divergence, tracking issues, conflicts and pending operations
      --push              Push app branches
      --reset             Hard-reset apps only when tracking the configured branch
      --checkout          Check out configured app branches
      --shell COMMAND     Run a Bash command in each selected app directory

With --jobs greater than 1, all sequential app updates finish before builds
start. Build output is grouped per app. A failed batch is drained before
exiting nonzero; no later batches are started.
EOF
      exit 0
      ;;
    -l|--list)
      LIST=true
      shift
      ;;
    -b|--build)
      BUILD=true
      shift
      ;;
    -j|--jobs)
      [[ $2 =~ ^[1-9][0-9]*$ ]] || {
          echo "invalid job count: $2 (expected a positive integer)" >&2
          exit 2
      }
      JOBS=$2
      shift 2
      ;;
    -d|--dev)
      BUILD_MODE=dev
      shift
      ;;
    -r|--rebase)
      REBASE=true
      shift
      ;;
    -o|--only)
      ARG=$2
      if [ "$ARG" = subrepo ]; then
        ARG="$(echo "${!SUBREPO_APPS[*]}"|xargs -n1|sort|xargs)"
      fi
      APPS="$ARG"
      shift 2
      ;;
    -e|--exclude)
      ARG=$2
      if [ "$ARG" = subrepo ]; then
        ARG="$(echo "${!SUBREPO_APPS[*]}"|xargs -n1|sort|xargs)"
      fi
      for APP in $ARG; do
          EXCLUDED_APPS[$APP]=true
      done
      shift 2
      ;;
    --push)
      PUSH=true
      shift
      ;;
    --reset)
      RESET=true
      shift
      ;;
    --checkout)
      CHECKOUT=true
      shift
      ;;
    -s|--status)
      STATUS=true
      shift
      ;;
    --shell)
      SHELL_MODE=true
      SHELL_COMMAND=$2
      shift 2
      ;;
    --) shift;
      break
      ;;
  esac
done

if [ "${#EXCLUDED_APPS[@]}" -gt 0 ]; then
    SELECTED_APPS=()
    for APP in $APPS; do
        if [ "${EXCLUDED_APPS[$APP]}" != true ]; then
            SELECTED_APPS+=("$APP")
        fi
    done
    APPS="${SELECTED_APPS[*]}"
fi

declare -A ATTENTION

SHORT_PWD=$(basename "$(pwd)")

function setTitle
{
    if [ -n "$1" ]; then
        echo -ne "\033]2;.../$SHORT_PWD - $CMD: $1\007"
    else
        echo -ne "\033]2;\007"
    fi
}

function buildApp
{
    local APP=$1
    echo "*** Rebuilding $APP ***"
    echo "Running ${BUILD_COMMANDS[$APP]}"
    { eval "${BUILD_COMMANDS[$APP]}"; } || {
        local RESULT=$?
        echo "Build failed for app $APP (exit $RESULT)" >&2
        return "$RESULT"
    }
}

if $LIST; then
  echo "$APPS"
  exit 0
fi

for APP in $APPS; do
    setTitle "$APP"
    cd "$NCDIR/apps/$APP" || exit 1
    if $SHELL_MODE; then
        setTitle "$APP (running '$SHELL_COMMAND')"
        echo
        echo "*** $APP: running '$SHELL_COMMAND'"
        echo
        bash -c -- "$SHELL_COMMAND" || {
            RESULT=$?
            echo "Shell command failed for app $APP (exit $RESULT)" >&2
            exit "$RESULT"
        }
        setTitle
        cd "$NCDIR" || exit 1
        continue
    fi
    if ! [ -e .git ]; then
        cd "$NCDIR" || exit 1
        continue
    fi
    if $STATUS; then
        APP_ISSUES=()
        APP_STATUS=$(git status --porcelain --branch) || exit 1
        if [[ "${APP_STATUS%%$'\n'*}" =~ \[ahead\ [0-9]+,\ behind\ [0-9]+\] ]]; then
            APP_ISSUES+=(diverged)
        fi
        UNMERGED=$(git ls-files --unmerged) || exit 1
        if [ -n "$UNMERGED" ]; then
            APP_ISSUES+=(conflicts)
        fi
        RESET_BRANCH="${RESET_BRANCHES[$APP]}"
        if [ -z "$RESET_BRANCH" ]; then
            APP_ISSUES+=("reset branch is empty")
        fi
        if ! git symbolic-ref --quiet HEAD >/dev/null; then
            APP_ISSUES+=("detached HEAD")
        elif ! UPSTREAM=$(git rev-parse --symbolic-full-name '@{upstream}' 2>/dev/null); then
            APP_ISSUES+=("no valid upstream")
        elif [ -n "$RESET_BRANCH" ] && [ "$UPSTREAM" != "refs/remotes/$RESET_BRANCH" ]; then
            APP_ISSUES+=("upstream $UPSTREAM does not match $RESET_BRANCH")
        fi
        MERGE_HEAD=$(git rev-parse --git-path MERGE_HEAD) || exit 1
        REBASE_MERGE=$(git rev-parse --git-path rebase-merge) || exit 1
        REBASE_APPLY=$(git rev-parse --git-path rebase-apply) || exit 1
        if [ -f "$MERGE_HEAD" ]; then
            APP_ISSUES+=("merge in progress")
        fi
        if [ -d "$REBASE_MERGE" ] || [ -d "$REBASE_APPLY" ]; then
            APP_ISSUES+=("rebase in progress")
        fi
        if [ "${#APP_ISSUES[@]}" -gt 0 ]; then
            ATTENTION[$APP]=$(printf '%s; ' "${APP_ISSUES[@]}")
            ATTENTION[$APP]=${ATTENTION[$APP]%; }
        fi
        cd "$NCDIR" || exit 1
        continue
    fi
    echo
    BRANCH=$(git status |grep -i "On branch"|awk '{ print $3; }')
    # REMOTE=$(git rev-parse --abbrev-ref --symbolic-full-name @{u})
    if [ -n "${STABLE_BRANCHES[$APP]}" ]; then
        STABLE_BRANCH=${STABLE_BRANCHES[$APP]}
    else
        STABLE_BRANCH=$CORE_BRANCH
    fi
    echo "** Updating $APP@$BRANCH **"
    if $RESET; then
        RESET_BRANCH="${RESET_BRANCHES[$APP]}"
        if [ -z "$RESET_BRANCH" ]; then
            echo "Reset branch for app $APP is empty" >&2
            exit 1
        fi
        if ! git symbolic-ref --quiet HEAD >/dev/null; then
            echo "Refusing to reset app $APP: HEAD is detached" >&2
            exit 1
        fi
        if ! UPSTREAM=$(git rev-parse --symbolic-full-name '@{upstream}'); then
            echo "Refusing to reset app $APP: current branch has no valid upstream" >&2
            exit 1
        fi
        if [ "$UPSTREAM" != "refs/remotes/$RESET_BRANCH" ]; then
            echo "Refusing to reset app $APP: upstream $UPSTREAM does not match $RESET_BRANCH" >&2
            exit 1
        fi
    fi
    setTitle "$APP (git fetch)"
    git fetch --all -p || exit 1
    if ! $RESET; then
        case $BRANCH in
            "$STABLE_BRANCH")
                ;;
            stable*)
                setTitle "$APP (git checkout $STABLE_BRANCH)"
                echo "Updating to $STABLE_BRANCH"
                git checkout "$STABLE_BRANCH"
                ;;
        esac
    fi
    if $RESET; then
        setTitle "$APP (git reset --hard $RESET_BRANCH)"
        echo "*** Hard resetting $APP to $RESET_BRANCH ***"
        git reset --hard "$RESET_BRANCH" || exit 1
    fi
    if $CHECKOUT; then
        RESET_BRANCH="${RESET_BRANCHES[$APP]}"
        setTitle "$APP (get checkout $RESET_BRANCH)"
        if [ -z "$RESET_BRANCH" ]; then
            echo "Checkout branch for app $APP is empty" 1>&2
            exit 1
        fi
        echo "*** Checking out $RESET_BRANCH for $APP ***"
	REMOTE=$(echo "$RESET_BRANCH"|cut -d/ -f1)
	CHECKOUT_BRANCH=$(echo "$RESET_BRANCH"|cut -d/ -f2-)
        git checkout "$CHECKOUT_BRANCH"
    fi
    case $BRANCH in
        stable*|master|main)
            setTitle "$APP (git pull from $BRANCH)"
            echo "Performing simple pull from upstream"
            git pull
            ;;
    esac
    if [ "${SUBREPO_APPS[$APP]}" = true ]; then
      setTitle "$APP (git subrepo pull --all)"
      git subrepo pull --all
    fi
    if $PUSH; then
      setTitle "$APP (git push)"
      git push --force
    fi
    if $REBASE && [ -n "${REBASE_BRANCHES[$APP]}" ]; then
        setTitle "$APP (git rebase ${REBASE_BRANCHES[$APP]})"
        echo "*** Rebasing $APP to ${REBASE_BRANCHES[$APP]} ***"
        git checkout . || exit 1
        git rebase "${REBASE_BRANCHES[$APP]}" || exit 1
    fi
    if $BUILD && [ -n "${BUILD_COMMANDS[$APP]}" ]; then
        if [ "$JOBS" = 1 ]; then
            setTitle "$APP (build)"
            buildApp "$APP" || exit 1
        else
            BUILD_APPS+=("$APP")
        fi
    fi
    echo
    setTitle
    cd "$NCDIR" || exit 1
done

if [ "${#BUILD_APPS[@]}" -gt 0 ]; then
    BUILD_LOG_DIR=$(mktemp -d) || exit 1
    trap 'wait; rm -rf -- "$BUILD_LOG_DIR"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    # Cap before arithmetic so even very large positive job counts are safe.
    MAX_JOBS=${#BUILD_APPS[@]}
    if [[ ${#JOBS} -gt ${#MAX_JOBS} || ( ${#JOBS} -eq ${#MAX_JOBS} && $JOBS > $MAX_JOBS ) ]]; then
        JOBS=$MAX_JOBS
    fi
    for ((OFFSET = 0; OFFSET < ${#BUILD_APPS[@]}; OFFSET += JOBS)); do
        BATCH=("${BUILD_APPS[@]:OFFSET:JOBS}")
        PIDS=()
        for INDEX in "${!BATCH[@]}"; do
            APP=${BATCH[$INDEX]}
            (
                cd "$NCDIR/apps/$APP" || exit 1
                buildApp "$APP"
            ) >"$BUILD_LOG_DIR/$INDEX.stdout" 2>"$BUILD_LOG_DIR/$INDEX.stderr" &
            PIDS+=("$!")
        done
        BATCH_FAILED=false
        for INDEX in "${!BATCH[@]}"; do
            if ! wait "${PIDS[$INDEX]}"; then
                BATCH_FAILED=true
            fi
            cat "$BUILD_LOG_DIR/$INDEX.stdout" || exit 1
            cat "$BUILD_LOG_DIR/$INDEX.stderr" >&2 || exit 1
        done
        if $BATCH_FAILED; then
            exit 1
        fi
    done
fi

for x in "${!ATTENTION[@]}"; do
    printf "[%s]=%s\n" "$x" "${ATTENTION[$x]}"
done
