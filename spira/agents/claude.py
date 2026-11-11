"""Claude Code 무인 실행: `claude -p ... --output-format json`.

결과 JSON에 result, usage, modelUsage(실제 쓰인 모델별 사용량), total_cost_usd가 들어 있다.
"""

from __future__ import annotations

import json
from pathlib import Path

from spira.agents.base import AgentResult


def build_command(instruction: str, model: str | None, workdir: Path) -> list[str]:
    # 사례는 직접 읽고 판단해야 하므로 파일 읽기 · 쓰기만 허용하고, 명령 실행(Bash)은 막는다.
    cmd = [
        "claude", "-p", instruction,
        "--output-format", "json",
        "--allowedTools", "Read", "Write", "Edit",
        "--disallowedTools", "Bash", "WebFetch", "WebSearch", "Task",
        "--max-turns", "30",
    ]
    if model:
        cmd += ["--model", model]
    return cmd


def parse_output(stdout: str, returncode: int) -> AgentResult:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return AgentResult(ok=False, raw=stdout, error="Claude 출력이 JSON이 아님")
    ok = returncode == 0 and not data.get("is_error", False)
    usage = dict(data.get("usage") or {})
    if "total_cost_usd" in data:
        usage["total_cost_usd"] = data["total_cost_usd"]
    models = sorted((data.get("modelUsage") or {}).keys())
    return AgentResult(ok=ok, text=data.get("result", ""), usage=usage, models=models, raw=stdout[-4000:],
                       error="" if ok else str(data.get("result", ""))[:2000])
