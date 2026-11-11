"""⓪ 아이템 풀 합치기 (코드, 처음 한 번).

규칙 (기준 문서 5-1절):
- 상품군마다 세 회사가 각자 쓴 목록(pool_{회사}_{번호})을 모은다. 60개가 다 끝나야 합친다.
- 띄어쓰기만 다른 이름(생일 초 / 생일초)은 같은 물건으로 합친다.
- 비슷한 이름(한 글자 차이)은 코드가 판단하지 않고 U의 검토 목록에 올린다.
- everyday 표시가 회사마다 다르면 다수결. 1 대 1이면 false (평소 장보기에 섞지 않는 쪽이 안전) + 검토 목록.
- 물건마다 어느 회사가 썼는지 남긴다 (한 회사 말투로 쏠렸는지 확인용).
- 결과는 config/lists/item_pool.yaml (status: draft). U가 review/item_pool_review.csv를 보고
  고칠 것을 고친 뒤 `spira confirm-pool`로 확정(status: confirmed)해야 사이클이 시작된다.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict

import yaml

from spira import config
from spira.batches import DATA

OUT = config.CONFIG / "lists" / "item_pool.yaml"
REVIEW = config.ROOT / "review" / "item_pool_review.csv"


def _key(name: str) -> str:
    return "".join(name.split())


def _one_apart(a: str, b: str) -> bool:
    """세 글자 이상이고 같은 길이에서 한 글자만 다른 이름 (예: 키친타올 / 키친타월). 길이가 다른 쌍은
    다른 물건인 경우가 많아(고구마 / 고구마순) 올리지 않는다."""
    if a == b or len(a) != len(b) or len(a) < 3:
        return False
    return sum(x != y for x, y in zip(a, b)) == 1


def ready() -> bool:
    cats = config.load_list("item_categories")["categories"]
    return all((DATA / "pool" / "results" / f"pool_{co}_{c['num']}.json").exists()
               for c in cats for co in config.COMPANIES)


def run() -> list:
    cats = config.load_list("item_categories")["categories"]
    items: dict[str, dict] = {}
    for c in cats:
        for co in sorted(config.COMPANIES):
            p = DATA / "pool" / "results" / f"pool_{co}_{c['num']}.json"
            for it in json.loads(p.read_text(encoding="utf-8"))["items"]:
                name = " ".join(it["name"].split())
                k = _key(name)
                e = items.setdefault(k, {"name": name, "votes": Counter(), "sources": set(), "categories": set()})
                e["votes"][bool(it["everyday"])] += 1
                e["sources"].add(co)
                e["categories"].add(c["name"])

    rows, review = [], []
    for k, e in sorted(items.items(), key=lambda kv: kv[1]["name"]):
        t, f = e["votes"][True], e["votes"][False]
        everyday = t > f
        if t and f:
            review.append({"종류": "everyday 엇갈림", "물건": e["name"], "참고": f"true {t} · false {f} → {everyday}"})
        rows.append({"name": e["name"], "everyday": everyday, "sources": sorted(e["sources"]),
                     "categories": sorted(e["categories"])})
    names = [r["name"] for r in rows]
    by_len = defaultdict(list)
    for n in names:
        by_len[len(_key(n))].append(n)
    for n in names:
        for L in (len(_key(n)),):
            for m in by_len.get(L, []):
                if n < m and _one_apart(_key(n), _key(m)):
                    review.append({"종류": "비슷한 이름", "물건": n, "참고": m})

    by_src = Counter(len(r["sources"]) for r in rows)
    doc = {
        "status": "draft",
        "note": "U가 review/item_pool_review.csv를 보고 고친 뒤 `uv run spira confirm-pool`로 확정한다",
        "counts": {"items": len(rows), "everyday": sum(r["everyday"] for r in rows),
                   "written_by_1_company": by_src[1], "by_2": by_src[2], "by_3": by_src[3]},
        "items": rows,
    }
    OUT.write_text("# 아이템 풀 (KB 전용, 서버와 공유하지 않음). merge_item_pool이 만든다.\n"
                   + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["종류", "물건", "참고"])
        w.writeheader()
        w.writerows(review)
    return [OUT, REVIEW]


def confirm() -> None:
    doc = yaml.safe_load(OUT.read_text(encoding="utf-8"))
    doc["status"] = "confirmed"
    OUT.write_text("# 아이템 풀 (KB 전용, 서버와 공유하지 않음). merge_item_pool이 만든다.\n"
                   + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
