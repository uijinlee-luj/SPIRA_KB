"""Antigravity CLI 무인 실행: `agy -p ... --output-format json` (Google AI Pro 계정).

반드시 Gemini 모델로 고정한다. Antigravity는 Claude · GPT-OSS 모델도 고를 수 있어서,
고정하지 않으면 "회사가 다른 세 모델" 조건이 깨진다. 모델 이름에 수준이 들어 있다
(예: gemini-3.8-flash-high). `agy models`로 목록을 볼 수 있다.

- --mode accept-edits: 파일 쓰기는 자동 승인 (무인 실행에서 멈추지 않게)
- --sandbox: 터미널 명령 제한. 사례는 직접 읽고 판단해야 하므로 스크립트 실행을 막는다
- --dangerously-skip-permissions는 쓰지 않는다 (명령 실행까지 자동 승인되어 위 규칙이 깨짐)

JSON 출력 칸: status, response, error, duration_seconds, num_turns,
usage{input_tokens, output_tokens, thinking_tokens, cache_read_tokens, total_tokens}, finished_reason
"""

from __future__ import annotations

import json
from pathlib import Path

from spira.agents.base import AgentResult

DEFAULT_MODEL = "gemini-3.8-flash-high"


def build_command(instruction: str, model: str | None, workdir: Path) -> list[str]:
    model = model or DEFAULT_MODEL
    if not model.startswith("gemini"):
        raise ValueError(f"Gemini 노드에 Gemini가 아닌 모델이 설정됨: {model}")
    return ["agy", "-p", instruction, "--output-format", "json", "--model", model,
            "--mode", "accept-edits", "--sandbox"]


def parse_output(stdout: str, returncode: int) -> AgentResult:
    data = None
    for line in reversed(stdout.strip().splitlines()):   # 앞에 다른 줄이 섞여도 마지막 JSON을 읽는다
        try:
            data = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(data, dict):
        return AgentResult(ok=False, raw=stdout[-4000:], error="Antigravity 출력이 JSON이 아님")
    usage = {k: v for k, v in (data.get("usage") or {}).items() if isinstance(v, (int, float))}
    ok = returncode == 0 and data.get("status") != "ERROR" and not data.get("error")
    model = data.get("model")
    return AgentResult(ok=ok, text=str(data.get("response", ""))[-2000:], usage=usage,
                       models=[model] if isinstance(model, str) else [],
                       raw=stdout[-4000:], error=str(data.get("error") or "")[:2000])
