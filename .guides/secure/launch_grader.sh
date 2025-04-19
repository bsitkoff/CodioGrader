#!/usr/bin/env bash
set -euo pipefail

RAW_URL="https://raw.githubusercontent.com/bsitkoff/codio-grader/main/grader.py"

curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
     "$RAW_URL" | python3 -

