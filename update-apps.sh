#!/bin/bash

export LC_ALL=C

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
CHECKOUT=false
BUILD_MODE=build
PUSH=false
RESET=false
REBASE=false
STATUS=false
LIST=false
APPS="${ALL_APPS}"

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
    [mail]=stable5.12
)

declare -A REBASE_BRANCHES
REBASE_BRANCHES=(
    [calendar]=origin/stable6.6
    [contacts]=origin/stable8.9
    [groupfolders]=origin/$CORE_BRANCH
    [ldap_write_support]=origin/$CORE_BRANCH
    [logreader]=origin/$CORE_BRANCH
    [mail]=origin/stable5.12
    [maps]=origin/master
    [related_resources]=origin/$CORE_BRANCH
    [richdocuments]=origin/$CORE_BRANCH
    [terms_of_service]=origin/stable4.8
    [twofactor_gateway]=origin/main
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
    [mail]=cjh/feature/stable5.12/provision-additional-email-addresses
    [mail_roundcube]=origin/master
    [maps]=cjh/production/cafevdb/master
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
    [twofactor_gateway]=origin/main
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

VALID_ARGS=$(getopt -o bldre:o:s --long build,list,dev,only:,exclude:,rebase,status,push,reset,checkout -- "$@")
# shellcheck disable=SC2181
if [[ $? -ne 0 ]]; then
    exit 1;
fi

eval set -- "$VALID_ARGS"
while true; do
  case "$1" in
    -l|--list)
      LIST=true
      shift
      ;;
    -b|--build)
      BUILD=true
      shift
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
          APPS=$(echo "$APPS"|grep -Fv "$APP")
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
    --) shift;
      break
      ;;
  esac
done

declare -A ATTENTION

SHORT_PWD=$(basename "$(pwd)")
CMD=$(basename "$0")

function setTitle
{
    if [ -n "$1" ]; then
        echo -ne "\033]2;.../$SHORT_PWD - $CMD: $1\007"
    else
        echo -ne "\033]2;\007"
    fi
}

if $LIST; then
  echo "$APPS"
  exit 0
fi

for APP in $APPS; do
    setTitle "$APP"
    cd "$NCDIR/apps/$APP" || exit 1
    if ! [ -e .git ]; then
        cd "$NCDIR" || exit 1
        continue
    fi
    if $STATUS; then
        APP_STATUS=$(git status)
        case "$APP_STATUS" in
            *diverged*)
                ATTENTION[$APP]=diverged
                ;;
            *)
                ;;
        esac
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
    setTitle "$APP (git fetch)"
    git fetch --all -p
    case $BRANCH in
        "$STABLE_BRANCH")
            ;;
        stable*)
            setTitle "$APP (git checkout $STABLE_BRANCH)"
            echo "Updating to $STABLE_BRANCH"
            git checkout "$STABLE_BRANCH"
            ;;
    esac
    if $RESET; then
        RESET_BRANCH="${RESET_BRANCHES[$APP]}"
        setTitle "$APP (get reset --hard $RESET_BRANCH)"
        if [ -z "$RESET_BRANCH" ]; then
            echo "Reset branch for app $APP is empty" 1>&2
            exit 1
        fi
        echo "*** Hard resetting $APP to $RESET_BRANCH ***"
        git reset --hard "$RESET_BRANCH"
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
        setTitle "$APP (build)"
        echo "*** Rebuilding $APP ***"
        echo "Running ${BUILD_COMMANDS[$APP]}"
        { eval "${BUILD_COMMANDS[$APP]}"; } || exit 1
    fi
    echo
    setTitle
    cd "$NCDIR" || exit 1
done

for x in "${!ATTENTION[@]}"; do
    printf "[%s]=%s\n" "$x" "${ATTENTION[$x]}"
done
