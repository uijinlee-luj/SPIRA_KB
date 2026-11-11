#!/usr/bin/env bash
# 현황 요약(status.json)을 만들어 status 브랜치에 강제로 올린다. Actions에서만 쓴다.
set -euo pipefail
python -m spira.status > "$RUNNER_TEMP/status.json"
rm -rf "$RUNNER_TEMP/pub" && mkdir "$RUNNER_TEMP/pub" && cd "$RUNNER_TEMP/pub"
cp ../status.json .
git init -q -b status
git add status.json
git -c user.name="spira-status" -c user.email="actions@users.noreply.github.com" commit -qm "현황 ${GITHUB_SHA::7}"
git push -qf "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" status
