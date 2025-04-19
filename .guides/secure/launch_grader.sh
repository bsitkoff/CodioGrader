#!/usr/bin/env bash
set -euo pipefail

# Check for GitHub token
if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "ERROR: GITHUB_TOKEN environment variable is not set." >&2
    echo "Please configure GITHUB_TOKEN in Codio:" >&2
    echo "1. Go to Project Settings → Environment" >&2
    echo "2. Click 'Add variable'" >&2
    echo "3. Set Name='GITHUB_TOKEN', Value=your_github_token" >&2
    echo "4. Set Scope='All assignments in this project'" >&2
    echo "5. Set Visibility='Instructors only'" >&2
    exit 1
fi

RAW_URL="https://raw.githubusercontent.com/bsitkoff/CodioGrader/main/grader.py"

# Try to download and run the grader
curl -fsSL \
     -H "Accept: application/vnd.github.raw" \
     -H "Authorization: token ${GITHUB_TOKEN}" \
     "${RAW_URL}" | python3 - "$@" || {
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
