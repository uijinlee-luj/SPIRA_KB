"""에이전트 공통 실행부. 회사별 파일은 명령어와 결과 해석만 정한다.

긴 프롬프트는 명령줄에 넣지 않는다. 작업 폴더에 prompt.md · job.json을 두고, 명령줄에는
"prompt.md를 읽고 따르라"는 짧은 지시만 준다. (Windows 명령줄 길이 · 따옴표 · 줄바꿈 문제를 피한다)
작업 폴더는 저장소 밖에 새로 만든다. 에이전트가 저장소의 다른 파일(확인용 사례 정답 등)을 보지 못하게 하기 위해서다.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

INSTRUCTION = (
    "이 폴더의 prompt.md 파일을 읽고 그 지시를 그대로 따르세요. "
    "작업 파일은 job.json이고, 결과는 result.json 파일에 씁니다. "
    "이 폴더 밖의 파일은 읽거나 쓰지 마세요."
)


@dataclass
class AgentResult:
    ok: bool
    text: str = ""                             # 에이전트의 마지막 답 (참고용, 결과는 result.json)
    usage: dict = field(default_factory=dict)  # 토큰 사용량 (회사마다 칸 이름이 다름)
    models: list[str] = field(default_factory=list)  # CLI 출력에서 읽은 실제 모델 (없으면 빈 목록)
    raw: str = ""
    error: str = ""


def total_tokens(usage: dict) -> int | None:
    """회사마다 다른 사용량 칸을 하나의 숫자로. 할당량은 이 숫자로 잰다 (측정으로 % 환산).
    CLI가 합계(total_tokens)를 주면 그대로 쓴다 (입력에 캐시가 이미 포함됐는지 회사마다 달라서)."""
    if isinstance(usage.get("total_tokens"), (int, float)):
        return int(usage["total_tokens"])
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
            "cached_input_tokens", "reasoning_output_tokens",
            "thinking_tokens", "cache_read_tokens")
    vals = [usage[k] for k in keys if isinstance(usage.get(k), (int, float))]
    return int(sum(vals)) if vals else None


def _module(company: str):
    from spira.agents import claude, codex, fake, gemini
    return {"claude": claude, "codex": codex, "gemini": gemini, "fake": fake}[company]


def run_agent(company: str, model: str | None, workdir: Path, timeout_s: int = 1800) -> AgentResult:
    """company에 맞는 CLI를 새 세션으로 한 번 실행한다."""
    module = _module(company)
    cmd = module.build_command(INSTRUCTION, model, workdir)
    exe = shutil.which(cmd[0])   # Windows의 .cmd / .exe도 찾는다
    if exe is None:
        return AgentResult(ok=False, error=f"'{cmd[0]}' 명령을 찾을 수 없습니다 (설치 · PATH 확인)")
    try:
        proc = subprocess.run([exe, *cmd[1:]], cwd=workdir, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout_s,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return AgentResult(ok=False, error=f"{timeout_s}초 안에 끝나지 않음")
    res = module.parse_output(proc.stdout, proc.returncode)
    if not res.ok and not res.error:
        res.error = (proc.stderr or proc.stdout)[-2000:]
    return res
