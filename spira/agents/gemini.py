"""Antigravity CLI 무인 실행: `agy -p` (Google AI Pro 계정).

반드시 Gemini 모델로 고정한다. Antigravity는 Claude · GPT-OSS 모델도 고를 수 있어서,
고정하지 않으면 "회사가 다른 세 모델" 조건이 깨진다.
- config/cycles의 models.gemini에 이름을 적으면 --model로 넘긴다.
- 비어 있으면 Antigravity에서 고른 모델을 그대로 쓴다. 이때는 반드시 Gemini 모델이 골라져 있어야 한다.

TODO(첫 실행, U 노트북): `agy --help`로 아래를 확인하고 고친다
  - 모델을 고르는 옵션 이름 (--model인지)
  - 승인 대기 없이 파일을 쓰게 하는 옵션
  - 사용량 · 모델 이름이 출력에 나오는지 (안 나오면 할당량은 작업 개수로 잰다)
"""

from __future__ import annotations

from pathlib import Path

from spira.agents.base import AgentResult


def build_command(instruction: str, model: str | None, workdir: Path) -> list[str]:
    cmd = ["agy"]
    if model:
        cmd += ["--model", model]
    return cmd + ["-p", instruction]


def parse_output(stdout: str, returncode: int) -> AgentResult:
    return AgentResult(ok=returncode == 0, text=stdout.strip()[-2000:], raw=stdout[-4000:])
