#!/usr/bin/env bash
set -euo pipefail

# Debug logging function
log() {
    if [ "${DEBUG}" -eq 1 ]; then
        echo "[DEBUG] $1" >&2
    fi
}

# Default to debug off unless explicitly set
DEBUG=${DEBUG:-0}

# Get script directory for config path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${SCRIPT_DIR}/autograde_config.json"

# Environment setup for Codio grading
if [ -n "${CODIO_AUTOGRADE_ENV:-}" ]; then
    log "Running in Codio assignment grading mode"
    # Export variables that the Python grader needs
    export CODIO_AUTOGRADE_ENV
    export CODIO_AUTOGRADE_URL
    export GITHUB_TOKEN
    export PYTHONPATH="/usr/share/codio/assessments:${PYTHONPATH:-}"
fi

# Check for GitHub token
if [ -z "${GITHUB_TOKEN:-}" ]; then
    GITHUB_TOKEN="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"
fi

RAW_URL="https://raw.githubusercontent.com/bsitkoff/CodioGrader/main/grader.py"

# Try to download and run the grader, passing all arguments
curl -fsSL \
     -H "Accept: application/vnd.github.raw" \
     -H "Authorization: token ${GITHUB_TOKEN}" \
     "${RAW_URL}" | python3 - --config "${CONFIG_PATH}" "$@" || {
    # If that fails, print diagnostic information (without exposing the token)
    echo "Error: Failed to download grader script" >&2
    echo "URL: ${RAW_URL}" >&2
    echo "Response code:" >&2
    curl -I \
         -H "Accept: application/vnd.github.raw" \
         -H "Authorization: token ${GITHUB_TOKEN}" \
         "${RAW_URL}" >&2
    exit 1
}
