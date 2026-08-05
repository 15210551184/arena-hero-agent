#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
INSTALLER=$PROJECT_ROOT/scripts/install-systemd.sh
GIT_BIN=${ARENA_UPDATE_GIT_BIN:-git}
SUDO_BIN=${ARENA_UPDATE_SUDO_BIN:-sudo}
ID_BIN=${ARENA_UPDATE_ID_BIN:-id}

usage() {
    cat <<'EOF'
Usage: sh scripts/update-systemd.sh

Fast-forward the current checkout to its configured upstream, then switch the
running systemd Agent from the old strategy process to the new strategy. Run
this command as the checkout owner, without sudo; privilege escalation happens
only for the transactional install and service restart.
EOF
}

if [ "$#" -gt 1 ]; then
    echo "This updater does not accept installer or credential arguments." >&2
    usage >&2
    exit 2
fi
case "${1:-}" in
    "") ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 2
        ;;
esac

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Required command is unavailable: $1" >&2
        exit 2
    fi
}

require_command "$GIT_BIN"
require_command "$ID_BIN"
current_uid=$("$ID_BIN" -u)
case "$current_uid" in
    ""|*[!0-9]*)
        echo "Unable to determine the current numeric user ID." >&2
        exit 2
        ;;
esac
if [ "$current_uid" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    echo "Run this updater without sudo so Git remains owned by the checkout user." >&2
    exit 2
fi
if [ ! -r "$INSTALLER" ]; then
    echo "Systemd installer is missing: $INSTALLER" >&2
    exit 2
fi

repository_root=$("$GIT_BIN" -C "$PROJECT_ROOT" rev-parse --show-toplevel 2>/dev/null) || {
    echo "The project directory is not a Git checkout." >&2
    exit 2
}
if [ "$repository_root" != "$PROJECT_ROOT" ]; then
    echo "Run the updater from the standalone Arena Hero repository root." >&2
    exit 2
fi

working_changes=$("$GIT_BIN" -C "$PROJECT_ROOT" status --porcelain --untracked-files=all)
if [ -n "$working_changes" ]; then
    echo "The Git worktree is not clean. Commit, stash, or remove local changes before updating." >&2
    exit 2
fi

branch=$("$GIT_BIN" -C "$PROJECT_ROOT" symbolic-ref --quiet --short HEAD) || {
    echo "The checkout is detached. Switch to a branch with a configured upstream." >&2
    exit 2
}
upstream=$("$GIT_BIN" -C "$PROJECT_ROOT" rev-parse \
    --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null) || {
    echo "The current branch has no configured upstream." >&2
    exit 2
}
remote=$("$GIT_BIN" -C "$PROJECT_ROOT" config --get "branch.$branch.remote") || {
    echo "The current branch has no configured remote." >&2
    exit 2
}
case "$remote" in
    ""|-*|*[!A-Za-z0-9._-]*)
        echo "The configured Git remote name is not supported." >&2
        exit 2
        ;;
esac

current_commit=$("$GIT_BIN" -C "$PROJECT_ROOT" rev-parse --verify 'HEAD^{commit}')
echo "Fetching $upstream for branch $branch."
"$GIT_BIN" -C "$PROJECT_ROOT" fetch --prune --tags "$remote"
target_commit=$("$GIT_BIN" -C "$PROJECT_ROOT" rev-parse --verify '@{upstream}^{commit}')

if ! "$GIT_BIN" -C "$PROJECT_ROOT" merge-base --is-ancestor \
    "$current_commit" "$target_commit"; then
    echo "The upstream update is not a fast-forward. Review the branch history manually." >&2
    exit 2
fi

if [ "$current_commit" != "$target_commit" ]; then
    "$GIT_BIN" -C "$PROJECT_ROOT" merge --ff-only "$target_commit"
fi
deployed_commit=$("$GIT_BIN" -C "$PROJECT_ROOT" rev-parse --short=12 "$target_commit")
echo "Deploying source commit $deployed_commit."

run_installer() {
    if [ "$current_uid" -eq 0 ]; then
        ARENA_HERO_API_KEY= sh "$INSTALLER"
    else
        require_command "$SUDO_BIN"
        "$SUDO_BIN" env ARENA_HERO_API_KEY= sh "$INSTALLER"
    fi
}

if run_installer; then
    echo "Arena Hero Agent updated to $deployed_commit and the new strategy is running."
    echo "The systemd restart stopped any previous strategy process before starting this version."
    echo "Follow logs with: sudo journalctl -fu arena-hero-agent.service -o short-iso-precise"
else
    status=$?
    echo "Update deployment failed with exit code $status; the installer kept or restored the previous active release." >&2
    exit "$status"
fi
