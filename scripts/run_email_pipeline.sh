#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export CONTENT_PIPELINE_REPO="${CONTENT_PIPELINE_REPO:-/Users/macmini-4/.openclaw/repos/content_pipeline}"
export CONTENT_PIPELINE_BASE="${CONTENT_PIPELINE_BASE:-/Users/macmini-4/.openclaw/runtime/content_pipeline/landing}"
export CONTENT_PIPELINE_CONFIG="${CONTENT_PIPELINE_CONFIG:-$CONTENT_PIPELINE_REPO/config/pipelines.json}"

LOG_DIR="/Users/macmini-4/.openclaw/runtime/content_pipeline/logs"
mkdir -p "$LOG_DIR" "$CONTENT_PIPELINE_BASE"

cd "$CONTENT_PIPELINE_REPO"
/usr/bin/env python3 scripts/email_pipeline_fetch.py >> "$LOG_DIR/email_pipeline.log" 2>&1
