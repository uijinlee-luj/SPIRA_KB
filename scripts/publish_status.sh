#!/usr/bin/env bash
# 현황 요약(status.json)을 만들어 status 브랜치에 강제로 올린다. Actions에서만 쓴다.
set -euo pipefail
python -m spira.status > "$RUNNER_TEMP/status.json"
rm -rf "$RUNNER_TEMP/pub" && mkdir "$RUNNER_TEMP/pub" && cd "$RUNNER_TEMP/pub"
cp ../status.json .
git init -q -b status
git add status.json
git -c user.name="spira-status" -c user.email="actions@users.noreply.github.com" commit -qm "현황 ${GITHUB_SHA::7}"
# 다른 워크플로와 같은 순간에 올릴 때를 대비해 몇 번까지 시도한다 (강제로 올리므로 마지막 것이 남는다)
for i in 1 2 3; do
  git push -qf "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" status && exit 0
  sleep $((i * 5))
done
exit 1
