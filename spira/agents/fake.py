"""시험용 가짜 에이전트. 실제 AI를 부르지 않고 형식에 맞는 result.json을 쓴다.

`SPIRA_FAKE_AGENT=1`일 때만 쓰인다 (실행기 · 대기열 시험용, 한도를 쓰지 않음).
"""

from __future__ import annotations

import sys
from pathlib import Path

from spira.agents.base import AgentResult

SCRIPT = r'''
import json, os, time
time.sleep(float(os.environ.get('SPIRA_FAKE_SLEEP', '0')))
job = json.load(open("job.json", encoding="utf-8"))
r = job["role"]
if r == "item_pool":
    out = {"job_id": job["job_id"], "items": [{"name": f"물건{i}", "everyday": i % 2 == 0} for i in range(job["target_count"])]}
elif r == "generate":
    out = {"job_id": job["job_id"], "bundles": [{"goal_id": g["goal_id"], "items": ["케이크", "생일 초"]} for g in job["goals"]]}
else:
    out = {"job_id": job["job_id"], "labels": [{"case_ref": c["case_ref"], "intents": []} for c in job["cases"]]}
json.dump(out, open("result.json", "w", encoding="utf-8"), ensure_ascii=False)
print(json.dumps({"usage": {"input_tokens": 1000, "output_tokens": 200}}))
qf = os.environ.get("SPIRA_FAKE_QUOTA")
if qf:
    q = json.load(open(qf)); q["weekly"] -= 0.6; q["five"] -= 1.4
    json.dump(q, open(qf, "w"))
'''


def build_command(instruction: str, model: str | None, workdir: Path) -> list[str]:
    return [sys.executable, "-c", SCRIPT]


def parse_output(stdout: str, returncode: int) -> AgentResult:
    import json
    try:
        usage = json.loads(stdout.strip().splitlines()[-1])["usage"]
    except Exception:
        usage = {}
    return AgentResult(ok=returncode == 0, usage=usage, models=["fake"], raw=stdout)


def read_quota():
    """SPIRA_FAKE_QUOTA 파일이 있으면 가짜 한도를 돌려준다 (시험용)."""
    import json
    import os
    from datetime import datetime, timedelta, timezone

    from spira.agents.base import Quota
    qf = os.environ.get("SPIRA_FAKE_QUOTA")
    if not qf:
        return None
    q = json.load(open(qf))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return Quota(weekly_left=q["weekly"], weekly_reset=datetime.fromisoformat(q["weekly_reset"]),
                 five_h_left=q["five"], five_h_reset=now + timedelta(hours=4))
