#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

REPO_DIR="/Users/macmini-4/.openclaw/workspace/content_pipeline"
LOG_DIR="$REPO_DIR/logs"
mkdir -p "$LOG_DIR"

cd "$REPO_DIR"
/usr/bin/env python3 scripts/email_pipeline_fetch.py >> "$LOG_DIR/email_pipeline.log" 2>&1
