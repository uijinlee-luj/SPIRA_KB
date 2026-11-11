"""① 목적 · 가구 뽑기 + 생성 작업 만들기 (설계 5-1 · 5-2절).

회차 하나를 시작하면 조각 1 · 2 · 3 배치를 한꺼번에 만든다 (배치 이름 {사이클}{회차}-{조각}).

배치마다:
- 사례 1천 개의 주문 유형을 비율대로 정한다 (config/pipeline.yaml order_types)
- 의도가 있는 주문(B · W · E · C)마다 목적(의도 + 그 의도에 맞는 가구)을 뽑는다
  - 의도는 빈도 가중치(흔함 ×3 · 보통 ×2 · 드묾 ×1)로 뽑는다
  - E(경계 의도)는 헷갈리는 쌍(config/lists/confusable_pairs.yaml)에서 고르고, 쌍의 다른 쪽 묶음도 하나 만든다
  - C(의도 둘)는 서로 다른 두 의도, 두 의도의 가구 조건을 모두 만족하는 가구
- 목적을 50개씩 묶어 생성 작업으로 대기열에 넣는다. 생성 회사는 조각의 역할 돌리기를 따른다
- 시드는 배치 이름에서 나온다. 같은 배치를 다시 만들면 같은 계획이 나온다
"""

from __future__ import annotations

import json

from spira import batches as B
from spira import config, household
from spira.queue import DATA
from spira.schemas import GenerateJob

PROMPT_VERSION = "generate_bundle@v1"


def _counts(n: int, ratios: dict[str, float]) -> dict[str, int]:
    raw = {k: n * v for k, v in ratios.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: n - sum(out.values())]:
        out[k] += 1
    return out


def plan_batch(batch: str) -> tuple[dict, list[dict]]:
    """(plan, goals). 파일은 쓰지 않는다."""
    cycle, round_no, slice_id = B.parse(batch)
    cfg = B.pipeline()
    rng = B.rng_for(batch, "plan")
    intents = B.intents()
    by_id = {i["id"]: i for i in intents}
    weights = config.load_list("intents")["frequency_weight"]
    ids = [i["id"] for i in intents]
    w = [weights[i["frequency"]] for i in intents]
    pairs = config.load_list("confusable_pairs")["pairs"]

    def pick_intent(exclude=()):
        while True:
            x = rng.choices(ids, weights=w)[0]
            if x not in exclude:
                return x

    goals: list[dict] = []

    def new_goal(intent_id: str, hh: list[str]) -> str:
        gid = f"{batch}_g{len(goals) + 1:04d}"
        goals.append({"goal_id": gid, "intent": B.intent_ref(by_id[intent_id]), "household_types": hh})
        return gid

    counts = _counts(cfg["cases_per_batch"], cfg["order_types"])
    types = [t for t, n in counts.items() for _ in range(n)]
    rng.shuffle(types)
    cases = []
    for n, t in enumerate(types, 1):
        c = {"case_no": n, "type": t, "made_intents": [], "goals": [], "household_types": None}
        if t in ("B", "W"):
            x = pick_intent()
            hh = household.sample(rng, x)
            c.update(made_intents=[x], goals=[new_goal(x, hh)], household_types=hh)
        elif t == "E":
            a, b = rng.choice(pairs)
            x, y = (a, b) if rng.random() < 0.5 else (b, a)
            hh = household.sample(rng, x)
            # y 묶음은 물건 1~2개를 빌려 오는 용도. y에 맞는 가구로 따로 만든다
            c.update(made_intents=[x], goals=[new_goal(x, hh), new_goal(y, household.sample(rng, y))],
                     household_types=hh, boundary_with=y)
        elif t == "C":
            x = pick_intent()
            y = pick_intent(exclude=(x,))
            for _ in range(200):
                hh = household.sample(rng, x)
                if household.fits_intent(hh, y):
                    break
            else:
                y = pick_intent(exclude=(x,) + tuple(i for i in ids if not household.fits_intent(hh, i)))
            c.update(made_intents=[x, y], goals=[new_goal(x, hh), new_goal(y, hh)], household_types=hh)
        cases.append(c)

    # 생성 작업: 목적을 섞어서 50개씩
    order = goals[:]
    rng.shuffle(order)
    per = cfg["cases_per_job"]
    slices = config.load_cycles()[cycle]["slices"][slice_id]
    jobs = []
    for k in range(0, len(order), per):
        jobs.append({"job_id": f"{batch}_generate_{k // per + 1:03d}", "company": slices["generate"],
                     "goal_ids": [g["goal_id"] for g in order[k:k + per]]})
    plan = {"batch": batch, "cycle": cycle, "round": round_no, "slice": slice_id, "roles": slices,
            "counts": counts, "cases": cases, "generate_jobs": jobs, "created_at": B.now_iso()}
    return plan, goals


def start_batch(batch: str) -> list:
    cycle, _, _ = B.parse(batch)
    plan, goals = plan_batch(batch)
    written = [B.write(batch, "plan.json", plan), B.write(batch, "goals.json", goals)]
    by_id = {g["goal_id"]: g for g in goals}
    qdir = DATA / cycle / "queue"
    qdir.mkdir(parents=True, exist_ok=True)
    for j in plan["generate_jobs"]:
        job = GenerateJob(job_id=j["job_id"], batch=batch, company=j["company"], prompt_version=PROMPT_VERSION,
                          goals=[by_id[g] for g in j["goal_ids"]])
        p = qdir / f"{j['job_id']}.json"
        p.write_text(json.dumps(job.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(p)
    B.set_state(batch, "generating")
    written.append(B.bdir(batch) / "state.json")
    return written


def start_round(cycle: str, round_no: int) -> list:
    written = []
    for s in ("1", "2", "3"):
        written += start_batch(B.name(cycle, round_no, s))
    return written
