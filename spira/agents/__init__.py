"""AI별 실행 방법. 작업 하나 = 새 세션 하나.

A · B 두 사이클이 같은 파일을 쓴다. 예를 들어 Gemini 모델 고정은 gemini.py 한 곳만 고치면 된다.
"""

from spira.agents.base import AgentResult, run_agent

__all__ = ["AgentResult", "run_agent"]
