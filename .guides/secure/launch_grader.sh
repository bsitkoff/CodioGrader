#!/usr/bin/env bash
set -euo pipefail

RAW_URL="https://raw.githubusercontent.com/bsitkoff/CodioGrader/main/grader.py"

# Try to download and run the grader
curl -fsSL \
     -H "Accept: application/vnd.github.raw" \
     -H "Authorization: token ${GITHUB_TOKEN}" \
     "${RAW_URL}" | python3 - || {
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
