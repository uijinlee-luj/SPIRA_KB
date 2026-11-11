"""⓪ 아이템 풀 작업 만들기 (코드, 처음 한 번, U가 실행).

config/lists/item_categories.yaml의 상품군마다 세 회사 작업을 하나씩 만든다.
작업 id = pool_{회사}_{상품군번호2자리}. 이미 있는 작업(대기 · 실행 중 · 완료)은 다시 만들지 않는다.
"""

from __future__ import annotations

import json

from spira import config, queue
from spira.schemas import ItemPoolJob

PROMPT_VERSION = "item_pool@v1"


def run(push: bool = True) -> int:
    cats = config.load_list("item_categories")["categories"]
    qdir = queue.DATA / "pool" / "queue"
    qdir.mkdir(parents=True, exist_ok=True)
    made = []
    for c in cats:
        for company in sorted(config.COMPANIES):
            job_id = f"pool_{company}_{c['num']}"
            if any((queue.DATA / "pool" / kind / f"{job_id}.json").exists()
                   for kind in ("queue", "running", "results", "failed")):
                continue
            job = ItemPoolJob(job_id=job_id, company=company, prompt_version=PROMPT_VERSION,
                              category=c["name"], target_count=c["target_count"])
            path = qdir / f"{job_id}.json"
            path.write_text(json.dumps(job.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
            made.append(path)
    if push and made:
        queue._commit_and_push(f"아이템 풀 작업 {len(made)}개", made)
    return len(made)
