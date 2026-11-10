"""에이전트 공통 실행부. 회사별 파일은 명령어와 결과 해석만 정한다."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentResult:
    ok: bool
    text: str                                  # 에이전트의 최종 답 (작업 결과 JSON 문자열)
    usage: dict = field(default_factory=dict)  # 토큰 사용량 (input/output 등, 회사마다 다름)
    raw: str = ""


def run_agent(company: str, prompt: str, workdir: Path, timeout_s: int = 1800) -> AgentResult:
    """company에 맞는 CLI를 새 세션으로 한 번 실행한다."""
    from spira.agents import claude, codex, gemini

    module = {"claude": claude, "codex": codex, "gemini": gemini}[company]
    cmd = module.build_command(prompt)
    proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout_s)
    return module.parse_output(proc.stdout, proc.returncode)
