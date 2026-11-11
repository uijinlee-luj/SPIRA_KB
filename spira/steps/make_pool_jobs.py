"""⓪ 아이템 풀 작업 만들기 (코드, U가 실행).

config/lists/item_categories.yaml의 상품군마다 세 회사 작업을 하나씩 만든다.
작업 id = pool_{회사}_{상품군번호2자리}.

프롬프트 버전을 올렸을 때도 같은 명령을 다시 실행하면 된다.
- 대기 중인 작업은 새 버전으로 바꾼다
- 옛 버전으로 끝난 결과는 data/pool/discarded/로 옮기고 작업을 새 버전으로 다시 만든다
- 실행 중(running)인 작업은 건드리지 않는다
기록(logs)은 지우지 않는다 (한도를 쓴 기록이라 측정 · 할당량 계산에 필요하다).
"""

from __future__ import annotations

import json

from spira import config, queue
from spira.schemas import ItemPoolJob

PROMPT_VERSION = "item_pool@v2"


def run(push: bool = True) -> tuple[int, int, int]:
    """(새로 만든 수, 버전을 바꾼 대기 작업 수, 다시 돌릴 옛 결과 수)"""
    cats = config.load_list("item_categories")["categories"]
    pool = queue.DATA / "pool"
    qdir, rdir, ddir = pool / "queue", pool / "results", pool / "discarded"
    qdir.mkdir(parents=True, exist_ok=True)
    changed = []
    made = updated = redo = 0
    for c in cats:
        for company in sorted(config.COMPANIES):
            job_id = f"pool_{company}_{c['num']}"
            if (pool / "running" / f"{job_id}.json").exists() or (pool / "failed" / f"{job_id}.json").exists():
                continue
            qpath, rpath = qdir / f"{job_id}.json", rdir / f"{job_id}.json"
            if qpath.exists():
                data = json.loads(qpath.read_text(encoding="utf-8"))
                if data.get("prompt_version") == PROMPT_VERSION:
                    continue
                updated += 1
            elif rpath.exists():
                log = pool / "logs" / f"{job_id}.meta.json"
                ver = json.loads(log.read_text(encoding="utf-8")).get("prompt_version") if log.exists() else None
                if ver == PROMPT_VERSION:
                    continue
                ddir.mkdir(parents=True, exist_ok=True)
                old = ddir / f"{job_id}.{(ver or 'unknown').split('@')[-1]}.json"
                rpath.replace(old)
                changed += [rpath, old]
                redo += 1
            else:
                made += 1
            job = ItemPoolJob(job_id=job_id, company=company, prompt_version=PROMPT_VERSION,
                              category=c["name"], target_count=c["target_count"])
            qpath.write_text(json.dumps(job.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
            changed.append(qpath)
    if push and changed:
        queue._commit_and_push(f"아이템 풀 작업 {PROMPT_VERSION}: 새로 {made} · 버전 변경 {updated} · 다시 {redo}", changed)
    return made, updated, redo
