"""Codex CLI 무인 실행: `codex exec --json`.

--json이면 한 줄에 사건 하나(JSONL)가 나오고, turn.completed 사건에 usage가 들어 있다.
Codex는 파일을 읽을 때도 셸 명령을 쓰므로 명령 실행 자체는 막을 수 없다.
대신 샌드박스를 작업 폴더 쓰기까지로 제한하고, 프롬프트에서 코드 · 스크립트로 분류하지 말라고 막는다.
TODO(첫 실행): 실제 출력에서 usage · 모델 이름 칸 이름 확인
"""

from __future__ import annotations

import json
from pathlib import Path

from spira.agents.base import AgentResult


def build_command(instruction: str, model: str | None, workdir: Path) -> list[str]:
    cmd = ["codex", "exec", "--json", "--sandbox", "workspace-write", "--skip-git-repo-check"]
    if model:
        cmd += ["--model", model]
    return cmd + [instruction]


def parse_output(stdout: str, returncode: int) -> AgentResult:
    usage: dict = {}
    models: set[str] = set()
    last_text = ""
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "turn.completed" and isinstance(ev.get("usage"), dict):
            for k, v in ev["usage"].items():
                if isinstance(v, (int, float)):
                    usage[k] = usage.get(k, 0) + v
        if isinstance(ev.get("model"), str):
            models.add(ev["model"])
        item = ev.get("item") or {}
        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            last_text = item["text"]
    return AgentResult(ok=returncode == 0, text=last_text, usage=usage, models=sorted(models),
                       raw=stdout[-4000:])
