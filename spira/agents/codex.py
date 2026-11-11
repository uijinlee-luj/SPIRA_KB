"""Codex CLI 무인 실행: `codex exec`.

TODO: 토큰 사용량이 출력에 어떻게 나오는지 실제로 돌려 보고 parse_output을 채운다.
"""

from __future__ import annotations

from spira.agents.base import AgentResult


def build_command(prompt: str) -> list[str]:
    # TODO: 샌드박스·승인 설정을 작업 폴더 쓰기까지로 제한하고, 명령 실행을 막는 설정 확인
    #       (사례는 직접 읽고 판단해야 한다. 코드로 규칙화 금지)
    return ["codex", "exec", prompt]


def parse_output(stdout: str, returncode: int) -> AgentResult:
    return AgentResult(ok=returncode == 0, text=stdout.strip(), usage={}, raw=stdout)
