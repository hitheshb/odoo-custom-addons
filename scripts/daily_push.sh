#!/usr/bin/env bash
# Daily auto-commit + push for custom-addons, run via cron at 18:30.
# Only stages known project paths -- never home-directory dotfiles or editor config.
set -euo pipefail

REPO="/home/hithesh/odoo20/custom-addons"
LOG="$REPO/scripts/daily_push.log"
CLAUDE_BIN="/home/hithesh/.nvm/versions/node/v22.23.2/bin/claude"

# cron runs with no desktop session, so the gnome-keyring SSH agent isn't
# available -- use the key file directly instead of relying on SSH_AUTH_SOCK.
export GIT_SSH_COMMAND="ssh -i /home/hithesh/.ssh/id_ed25519 -o IdentitiesOnly=yes"

# Paths eligible for auto-commit. Add new addon dirs here as they're created.
TRACK_PATHS=(
  README.md
  ODOO20_CHANGES.md
  grocery_management
  meditrack
  sale_dispatch_report
  stock_dispatch_report
  scripts
)

cd "$REPO"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

{
  echo "[$(ts)] daily_push starting"

  git add -- "${TRACK_PATHS[@]}"

  if git diff --cached --quiet; then
    echo "[$(ts)] no changes to commit, skipping"
    exit 0
  fi

  DIFF_STAT="$(git diff --cached --stat)"
  DIFF_FILE="$(mktemp)"
  git diff --cached -- . ':!*.pot' ':!*.po' > "$DIFF_FILE" 2>&1 || true
  DIFF_CONTENT="$(head -c 12000 "$DIFF_FILE")"
  rm -f "$DIFF_FILE"

  PROMPT="Write a concise git commit message (a short summary line, optionally followed by a blank line and 2-4 bullet points) describing this staged diff for an Odoo custom-addons repo. Only output the commit message text, nothing else, no markdown fences.

Diff stat:
${DIFF_STAT}

Diff:
${DIFF_CONTENT}"

  if MSG="$("$CLAUDE_BIN" -p "$PROMPT" 2>>"$LOG")" && [ -n "$MSG" ]; then
    echo "[$(ts)] generated commit message via claude"
  else
    echo "[$(ts)] claude generation failed, falling back to file-list message"
    MSG="Update $(git diff --cached --name-only | tr '\n' ' ')"
  fi

  git commit -m "$MSG

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"

  git push origin 20.0

  echo "[$(ts)] pushed successfully"
} >> "$LOG" 2>&1
