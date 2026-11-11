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


def read_quota():
    """Codex는 따로 묻는 명령이 없어서, 가장 최근 세션 기록(~/.codex/sessions/**/rollout-*.jsonl)의
    rate_limits를 읽는다 (primary = 5시간, secondary = 주간, used_percent = 쓴 %).
    첫 작업 전이거나 칸이 없으면 None → 작업 수로 센다.
    TODO(첫 실행, Y · J 노트북): 실제 칸 이름 확인
    """
    from datetime import datetime, timedelta, timezone

    from spira.agents.base import Quota

    root = Path.home() / ".codex" / "sessions"
    files = sorted(root.rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    for f in files:
        limits = None
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"rate_limits"' not in line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            found = _find(ev, "rate_limits")
            if isinstance(found, dict):
                limits = (found, datetime.fromtimestamp(f.stat().st_mtime, timezone.utc))
        if limits is None:
            continue
        rl, seen = limits
        def win(w):
            if not isinstance(w, dict) or "used_percent" not in w:
                return None, None
            if w.get("resets_at"):
                reset = datetime.fromtimestamp(float(w["resets_at"]), timezone.utc)
            elif w.get("resets_in_seconds") is not None:
                reset = seen + timedelta(seconds=float(w["resets_in_seconds"]))
            else:
                return None, None
            return 100.0 - float(w["used_percent"]), reset.replace(microsecond=0)
        weekly, wreset = win(rl.get("secondary"))
        five, freset = win(rl.get("primary"))
        if weekly is None:
            return None
        return Quota(weekly_left=weekly, weekly_reset=wreset, five_h_left=five, five_h_reset=freset)
    return None


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, key)
            if r is not None:
                return r
    return None
