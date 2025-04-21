#!/usr/bin/env bash
set -euo pipefail

# Debug logging function
log() {
    if [ "${DEBUG:-0}" -eq 1 ]; then
        echo "[DEBUG] $1" >&2
    fi
}

# Default to debug off unless explicitly set
DEBUG=${DEBUG:-0}

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="https://raw.githubusercontent.com/bsitkoff/CodioGrader/main"
CONFIG_PATH="${SCRIPT_DIR}/autograde_config.json"
GRADER_PATH="${SCRIPT_DIR}/grader.py"

# Function to update the grader
update_grader() {
    log "Updating grader from ${REPO_URL}"
    
    # Backup existing grader if it exists
    if [ -f "${GRADER_PATH}" ]; then
        log "Backing up existing grader"
        cp "${GRADER_PATH}" "${GRADER_PATH}.backup"
    fi

    # Download latest grader
    curl -fsSL "${REPO_URL}/grader.py" > "${GRADER_PATH}" || {
        echo "Error: Failed to download grader script" >&2
        if [ -f "${GRADER_PATH}.backup" ]; then
            mv "${GRADER_PATH}.backup" "${GRADER_PATH}"
            echo "Restored backup grader script" >&2
        fi
        return 1
    }

    chmod +x "${GRADER_PATH}"
    rm -f "${GRADER_PATH}.backup"
    echo "Successfully updated grader script"
}

# Load environment variables
ENV_FILE="${SCRIPT_DIR}/.env"
if [ -f "${ENV_FILE}" ]; then
    log "Loading environment variables from ${ENV_FILE}"
    source "${ENV_FILE}"
    
    # Log environment variable status (without exposing values)
    if [ "${DEBUG}" -eq 1 ]; then
        [ -n "${NOTION_API_KEY:-}" ] && log "NOTION_API_KEY is set (${#NOTION_API_KEY} chars)"
        [ -n "${NOTION_GRADES_DATABASE_ID:-}" ] && log "NOTION_GRADES_DATABASE_ID is set"
        [ -n "${NOTION_STUDENTS_DATABASE_ID:-}" ] && log "NOTION_STUDENTS_DATABASE_ID is set"
        [ -n "${OPENAI_API_KEY:-}" ] && log "OPENAI_API_KEY is set (${#OPENAI_API_KEY} chars)"
    fi
else
    echo "Warning: Environment file not found at ${ENV_FILE}" >&2
fi

# Process command line arguments
UPDATE=0
for arg in "$@"; do
    case $arg in
        --update)
            UPDATE=1
            shift
            ;;
    esac
done

# Update grader if requested
if [ "${UPDATE}" -eq 1 ]; then
    update_grader || exit 1
fi

# Check if grader exists
if [ ! -f "${GRADER_PATH}" ]; then
    echo "Error: Grader script not found. Run with --update to download it." >&2
    exit 1
fi

# Environment setup for Codio grading
if [ -n "${CODIO_AUTOGRADE_ENV:-}" ]; then
    log "Running in Codio assignment grading mode"
    export CODIO_AUTOGRADE_ENV
    export CODIO_AUTOGRADE_URL
    export NOTION_API_KEY
    export NOTION_GRADES_DATABASE_ID
    export NOTION_STUDENTS_DATABASE_ID
    export OPENAI_API_KEY
    export PYTHONPATH="/usr/share/codio/assessments:${PYTHONPATH:-}"
    log "Exported all environment variables for the grader"
fi

# Ensure all required environment variables are exported
export NOTION_API_KEY
export NOTION_GRADES_DATABASE_ID
export NOTION_STUDENTS_DATABASE_ID
export OPENAI_API_KEY
export DEBUG

# Run the grader
log "Running grader: ${GRADER_PATH}"
python3 "${GRADER_PATH}" --config "${CONFIG_PATH}" "$@"
