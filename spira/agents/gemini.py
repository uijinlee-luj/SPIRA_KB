"""Antigravity CLI 무인 실행: `agy -p` (Google AI Pro 계정).

반드시 Gemini 모델로 고정한다. Antigravity는 Claude 모델도 고를 수 있어서,
고정하지 않으면 "회사가 다른 세 모델" 조건이 깨진다.

주의: 짧은 간격으로 반복 실행하면 분당 한도에 걸릴 수 있다. 측정 결과에 따라
작업 하나의 크기를 키운다. 한도가 부족하면 Gemini API 무료 키를 예비로 쓴다.
"""

from __future__ import annotations

from spira.agents.base import AgentResult

# TODO(측정 후): 실제 모델 이름 확정. agy에서 고를 수 있는 Gemini 모델 중 하나로 고정.
MODEL = "GEMINI_MODEL_TBD"


def build_command(prompt: str) -> list[str]:
    # TODO: 무인 실행에서 승인 대기로 멈추지 않도록 설정 (non-TTY에서 멈추는 문제 확인)
    return ["agy", "--model", MODEL, "-p", prompt]


def parse_output(stdout: str, returncode: int) -> AgentResult:
    # TODO: JSON 출력과 사용량 필드 확인 후 채움
    return AgentResult(ok=returncode == 0, text=stdout.strip(), usage={}, raw=stdout)
