#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${1:-ssh.rc.byu.edu}"
REMOTE_USER="${2:-}"
REMOTE_WORKTREE="${3:-/grphome/grp_tomo/nobackup/archive/segment_sam_remote}"

if [[ -z "$REMOTE_USER" ]]; then
  read -r -p "Remote username: " REMOTE_USER
fi

ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_WORKTREE}'"

rsync -av --delete \
  --include='scripts/***' \
  --include='README.md' \
  --include='*.template.json' \
  --include='*.py' \
  --exclude='*' \
  ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_WORKTREE}/"
