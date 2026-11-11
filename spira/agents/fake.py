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
import hashlib
def h(s):
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)
if r == "item_pool":
    cat = job["job_id"].split("_")[-1]
    out = {"job_id": job["job_id"], "items": [{"name": f"물건{cat}-{i}", "everyday": i % 3 != 0} for i in range(job["target_count"])]}
elif r == "generate":
    # 목적 id가 들어간 물건 이름 (라벨 가짜가 읽어 낼 수 있게)
    out = {"job_id": job["job_id"], "bundles": [
        {"goal_id": g["goal_id"], "items": [f"{g['intent']['id']}용품{(h(g['goal_id']) + k) % 9}" for k in range(2 + h(g["goal_id"]) % 4)]}
        for g in job["goals"]]}
else:
    ids = {i["id"] for i in job["intents"]}
    labels = []
    for c in job["cases"]:
        found = {}
        for it in c["items"]:
            iid = it.split("용품")[0]
            if iid in ids:
                found.setdefault(iid, []).append(it)
        if r == "label_2" and h(c["case_ref"]) % 12 == 0 and found:   # 가끔 하나를 놓친다 (불일치 흉내)
            found.pop(sorted(found)[0])
        if len(found) > 2:
            found = dict(sorted(found.items(), key=lambda kv: -len(kv[1]))[:2])
        labels.append({"case_ref": c["case_ref"], "intents": [
            {"intent_id": k, "intent_text": f"{k} 준비", "bundle_items": v} for k, v in sorted(found.items())],
            "situation": {"event": "가짜 행사"} if found else {}, "alternatives": []})
    out = {"job_id": job["job_id"], "labels": labels}
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
