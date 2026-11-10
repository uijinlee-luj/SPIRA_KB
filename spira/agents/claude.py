"""Claude Code 무인 실행: `claude -p ... --output-format json`.

결과 JSON에 result, usage, total_cost_usd가 들어 있다 (비용은 클라이언트 쪽 추정치).
"""

from __future__ import annotations

import json

from spira.agents.base import AgentResult


def build_command(prompt: str) -> list[str]:
    # TODO: 허용 도구를 작업 폴더 읽기/쓰기로 제한 (--allowedTools), 최대 턴 수 설정
    return ["claude", "-p", prompt, "--output-format", "json"]


def parse_output(stdout: str, returncode: int) -> AgentResult:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return AgentResult(ok=False, text="", raw=stdout)
    ok = returncode == 0 and not data.get("is_error", False)
    usage = dict(data.get("usage") or {})
    if "total_cost_usd" in data:
        usage["total_cost_usd"] = data["total_cost_usd"]
    return AgentResult(ok=ok, text=data.get("result", ""), usage=usage, raw=stdout)
