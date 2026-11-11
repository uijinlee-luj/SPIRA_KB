"""③ 주문 조립 · 평소 장보기 추가 · 맥락 붙이기 + 라벨 작업 만들기 (설계 5-2 · 5-3 · 5-4절).

생성 작업이 모두 끝난 배치에서 돈다. 숫자는 config/pipeline.yaml.

주문 유형:
- A 평범한 장보기: 아이템 풀의 평소 물건만
- B 묶음 + 평소 물건 1~3개
- W 약한 단서: 묶음 물건 1~2개 + 평소 물건
- E 경계 의도: 묶음 + 헷갈리는 다른 의도 묶음의 물건 1~2개 (+ 평소 물건 0~2개)
- C 의도 둘: 묶음 두 개 (+ 평소 물건 0~1개)
- D 무작위: 특정 용도 물건을 무작위로 2~5개 (+ 평소 물건 0~2개). 말이 안 되는 조합 포함
주문 하나는 2~10개. 물건 순서는 섞는다.

맥락:
- 가구: 의도 있는 주문은 목적을 뽑을 때의 가구, A · D는 아무 가구. 20%는 라벨러에게 숨김 (만든 기록에는 남김)
- 캘린더: 태그 0~3개. 관련 있는 일정은 전체의 15%로, 관련 태그가 있는 의도의 주문에만 최대 1개.
  관련 없는 일정은 절반 행사 태그 · 절반 일상 태그, 그 주문 의도의 관련 태그는 빼고 뽑는다
- 일정 날짜: 도착 하루 전 ~ 14일 뒤, 요일은 도착 요일에서 계산

라벨 작업:
- 사례 50개 + 확인용 사례 3개씩, 라벨① · 라벨② 각각 같은 묶음으로 (순서는 따로 섞음)
- 라벨러가 보는 것은 서버 ③이 받는 수준: 물건, 가구(숨김이면 null), 도착 요일, 캘린더(태그 · 며칠 뒤 · 요일)
- case_ref는 무작위 8자리. 확인용 사례도 새 case_ref를 받아 구별되지 않는다
"""

from __future__ import annotations

import json

from spira import batches as B
from spira import checks, config, household
from spira.queue import DATA
from spira.schemas import LabelJob

PROMPT_VERSION = "label@v1"


def ready(batch: str) -> bool:
    plan = B.read(batch, "plan.json")
    cycle, _, _ = B.parse(batch)
    return bool(plan) and all(B.job_done(cycle, j["job_id"]) for j in plan["generate_jobs"])


def _bundles(batch: str) -> dict[str, list[str]]:
    plan = B.read(batch, "plan.json")
    cycle, _, _ = B.parse(batch)
    out = {}
    for j in plan["generate_jobs"]:
        for b in B.job_result(cycle, j["job_id"])["bundles"]:
            items = list(dict.fromkeys(" ".join(x.split()) for x in b["items"] if x.strip()))
            out[b["goal_id"]] = items
    return out


def _tag_count_dists(cfg, r: float) -> tuple[dict, dict]:
    """(관련 일정이 있는 주문의 태그 수 분포, 없는 주문의 분포). 둘을 섞으면 전체가 설정 분포가 되게 한다
    (관련 일정을 붙인 주문은 태그가 최소 1개라서, 나머지 주문의 0개 비율을 그만큼 올린다)."""
    P = {int(k): v for k, v in cfg["calendar_tag_count"].items()}
    q = {k: P[k] / (1 - P[0]) for k in P if k > 0}
    if r >= 1:
        return q, P
    p = {0: P[0] / (1 - r)} | {k: max(0.0, (P[k] - r * q[k]) / (1 - r)) for k in q}
    return q, p


def _calendar(rng, cfg, arrival: str, intents_here: list[str], related: bool, by_id: dict, dists) -> list[dict]:
    tags_cfg = config.load_list("calendar_tags")
    groups = tags_cfg["groups"]
    everyday = groups[tags_cfg["everyday_group"]]
    events = [t for g, ts in groups.items() if g != tags_cfg["everyday_group"] for t in ts]
    rel_tags = sorted({t for i in intents_here for t in by_id[i].get("related_tags", [])})
    dist = dists[0] if (related and rel_tags) else dists[1]
    n = rng.choices(list(dist), weights=list(dist.values()))[0]
    chosen: list[tuple[str, bool]] = []
    if related and rel_tags:
        chosen.append((rng.choice(rel_tags), True))
    while len(chosen) < n:
        pool = events if rng.random() < cfg["unrelated_event_vs_everyday"] else everyday
        t = rng.choice(pool)
        if t in rel_tags or t in {c[0] for c in chosen}:
            continue
        chosen.append((t, False))
    lo, hi = cfg["calendar_days"]
    start = B.WEEKDAYS.index(arrival)
    out = []
    for tag, rel in chosen:
        d = rng.randint(lo, hi)
        out.append({"tag": tag, "days_from_arrival": d, "weekday": B.WEEKDAYS[(start + d) % 7], "related": rel})
    rng.shuffle(out)
    return out


def assemble(batch: str) -> list:
    cycle, _, _ = B.parse(batch)
    cfg = B.pipeline()
    rng = B.rng_for(batch, "assemble")
    plan = B.read(batch, "plan.json")
    bundles = _bundles(batch)
    pool = B.item_pool()
    if pool.get("status") != "confirmed":
        raise RuntimeError("아이템 풀이 확정되지 않았습니다 (config/lists/item_pool.yaml status: confirmed)")
    everyday = [i["name"] for i in pool["items"] if i["everyday"]]
    special = [i["name"] for i in pool["items"] if not i["everyday"]]
    by_id = {i["id"]: i for i in B.intents()}
    sizes = cfg["order_size"]["weights"]

    def target_size():
        return rng.choices([int(k) for k in sizes], weights=list(sizes.values()))[0]

    def everyday_items(k, avoid):
        cand = [x for x in everyday if x not in avoid]
        return rng.sample(cand, min(k, len(cand)))

    # 관련 있는 일정: 전체의 15%를 자격 있는 주문 안에서
    eligible = [c["case_no"] for c in plan["cases"]
                if c["made_intents"] and any(by_id[i].get("related_tags") for i in c["made_intents"])]
    n_rel = min(len(eligible), round(cfg["related_event_share"] * len(plan["cases"])))
    related_set = set(rng.sample(eligible, n_rel))
    dists = _tag_count_dists(cfg, n_rel / len(plan["cases"]))

    cases, used_refs = [], set()
    for c in plan["cases"]:
        t = c["type"]
        g = [bundles[x] for x in c["goals"]]
        if t == "A":
            items = everyday_items(target_size(), set())
        elif t == "B":
            items = g[0] + everyday_items(rng.randint(*cfg["everyday_added"]["B"]), set(g[0]))
        elif t == "W":
            k = min(len(g[0]), rng.randint(*cfg["weak_bundle_items"]))
            core = rng.sample(g[0], k)
            items = core + everyday_items(max(target_size() - k, 1), set(core))
        elif t == "E":
            borrow = [x for x in g[1] if x not in g[0]]
            k = min(len(borrow), rng.randint(*cfg["boundary_items"]))
            items = g[0] + rng.sample(borrow, k)
            items += everyday_items(rng.randint(*cfg["everyday_added"]["E"]), set(items))
        elif t == "C":
            items = g[0] + [x for x in g[1] if x not in g[0]]
            while len(items) > cfg["order_size"]["max"]:   # 묶음마다 최소 2개는 남기고 줄인다
                side = g[0] if sum(x in g[0] for x in items) > sum(x in g[1] for x in items) else g[1]
                drop = [x for x in items if x in side]
                if len(drop) <= 2:
                    break
                items.remove(rng.choice(drop))
            items += everyday_items(rng.randint(*cfg["everyday_added"]["C"]), set(items))
        else:  # D
            items = rng.sample(special, rng.randint(*cfg["random_items"]))
            items += everyday_items(rng.randint(*cfg["everyday_added"]["D"]), set(items))
        items = list(dict.fromkeys(items))[: cfg["order_size"]["max"]]
        if len(items) < cfg["order_size"]["min"]:
            items += everyday_items(cfg["order_size"]["min"] - len(items), set(items))
        rng.shuffle(items)

        hh = c["household_types"] or household.sample(rng)
        arrival = rng.choice(B.WEEKDAYS)
        while True:
            ref = f"{rng.getrandbits(32):08x}"
            if ref not in used_refs:
                used_refs.add(ref)
                break
        cases.append({
            "case_no": c["case_no"], "case_ref": ref, "type": t, "items": items,
            "made_intents": c["made_intents"], "goals": c["goals"], "boundary_with": c.get("boundary_with"),
            "household_types": hh, "household_hidden": rng.random() < cfg["household_hidden"],
            "arrival_weekday": arrival,
            "calendar": _calendar(rng, cfg, arrival, c["made_intents"], c["case_no"] in related_set, by_id, dists),
        })
    written = [B.write(batch, "cases.json", cases)]
    written += make_label_jobs(batch, cases)
    B.set_state(batch, "labeling")
    written.append(B.bdir(batch) / "state.json")
    return written


def label_case(c: dict) -> dict:
    return {"case_ref": c["case_ref"], "items": c["items"],
            "household_types": None if c["household_hidden"] else c["household_types"],
            "arrival_weekday": c["arrival_weekday"],
            "calendar": [{k: e[k] for k in ("tag", "days_from_arrival", "weekday")} for e in c["calendar"]]}


def make_label_jobs(batch: str, cases: list[dict], only: list[str] | None = None) -> list:
    """라벨 작업을 대기열에 넣는다. only가 있으면 그 작업만 다시 만든다 (확인용 사례를 틀린 작업)."""
    cycle, _, _ = B.parse(batch)
    cfg = B.pipeline()
    rng = B.rng_for(batch, "label_jobs" if only is None else f"rerun:{','.join(only)}")
    plan = B.read(batch, "plan.json")
    intents = [B.intent_ref(i) for i in B.intents()]
    check_pool = checks.load()
    per = cfg["cases_per_job"]
    order = cases[:]
    rng.shuffle(order)
    chunks = [order[k:k + per] for k in range(0, len(order), per)]
    label_map = B.read(batch, "label_map.json") or {"jobs": {}, "checks_available": len(check_pool)}
    used = {r for j in label_map["jobs"].values() for r in j["cases"]} | {c["case_ref"] for c in cases}
    qdir = DATA / cycle / "queue"
    qdir.mkdir(parents=True, exist_ok=True)
    written = []
    for role in ("label_1", "label_2"):
        for n, chunk in enumerate(chunks, 1):
            job_id = f"{batch}_{role}_{n:03d}"
            if only is not None and job_id not in only:
                continue
            items = [label_case(c) for c in chunk]
            check_refs = {}
            for chk in rng.sample(check_pool, min(cfg["checks_per_label_job"], len(check_pool))):
                while True:
                    ref = f"{rng.getrandbits(32):08x}"
                    if ref not in used:
                        used.add(ref)
                        break
                lc = dict(chk["case"], case_ref=ref)
                items.append(lc)
                check_refs[ref] = {"check_ref": chk["case"]["case_ref"], "answer": chk["answer"]}
            rng.shuffle(items)
            job = LabelJob(job_id=job_id, batch=batch, role=role, company=plan["roles"][role],
                           prompt_version=PROMPT_VERSION, intents=intents, cases=items)
            p = qdir / f"{job_id}.json"
            p.write_text(json.dumps(job.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
            written.append(p)
            prev = label_map["jobs"].get(job_id, {})
            label_map["jobs"][job_id] = {"role": role, "cases": [c["case_ref"] for c in chunk],
                                         "checks": check_refs, "reruns": prev.get("reruns", -1) + 1}
    written.append(B.write(batch, "label_map.json", label_map))
    return written
