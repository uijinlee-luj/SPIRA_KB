"""Claude Code 무인 실행: `claude -p ... --output-format json`.

결과 JSON에 result, usage, total_cost_usd가 들어 있다 (비용은 클라이언트 쪽 추정치).
"""

from __future__ import annotations

import json

from spira.agents.base import AgentResult


def build_command(prompt: str) -> list[str]:
    # 사례는 직접 읽고 판단해야 하므로 파일 읽기 · 쓰기만 허용하고, 명령 실행(Bash)은 막는다.
    # TODO: 모델 고정(--model, config/cycles의 models), 최대 턴 수 설정
    return [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--allowedTools", "Read", "Write",
        "--disallowedTools", "Bash",
    ]


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
