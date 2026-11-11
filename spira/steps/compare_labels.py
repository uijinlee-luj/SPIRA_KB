"""⑤ 두 라벨 비교 · 확인용 사례 채점 · 서버에 갈 줄 만들기 (설계 5-5절, 6절).

라벨 작업이 모두 끝난 배치에서 돈다.

1. 확인용 사례 채점: 작업마다 섞은 확인용 사례를 U의 정답과 비교한다(의도 집합이 같아야 맞음).
   하나라도 틀린 작업은 새 세션으로 한 번 다시 돌린다. 다시 해도 틀리면 그대로 두고 품질 관문에서 "확인용 사례 틀림"으로 잡는다.
2. 사례마다 두 라벨 비교:
   - 의도가 같으면 그 의도 (1개 또는 2개), 다르면 겹치는 의도만, 겹치는 게 없으면 none
   - 의도 문장: 그 의도의 묶음이 두 라벨 묶음의 교집합에 더 가까운 라벨(물건을 덜 덧붙인 쪽). 같으면 라벨①
   - 상황: 두 라벨이 모두 채운 칸만, 값은 의도 문장을 고른 라벨의 것
   - 저장한 정답이 만들 때의 의도와 다르면 "주문에 안 보이는 의도"로 기록
3. 서버에 갈 줄(rows): 의도 하나에 한 줄. 의도 둘이면 두 줄(물건은 둘 다 주문 전체). 의도 없음은 intent_id none 한 줄.
   case_id = syn_{배치}_{번호4자리}, 번호는 줄마다 하나씩
   중복 제거(같은 의도 + 물건 유사도 0.97)는 임베딩이 필요해서 ⑦ 적재 직전에 한다
"""

from __future__ import annotations

import shutil

from spira import batches as B
from spira.queue import DATA
from spira.steps import assemble_orders


def ready(batch: str) -> bool:
    lm = B.read(batch, "label_map.json")
    cycle, _, _ = B.parse(batch)
    return bool(lm) and all(B.job_done(cycle, j) for j in lm["jobs"])


def _labels(batch: str) -> tuple[dict, dict, dict]:
    """(role → case_ref → label, job_id → result, case_ref → job_id)"""
    cycle, _, _ = B.parse(batch)
    lm = B.read(batch, "label_map.json")
    by_role: dict = {"label_1": {}, "label_2": {}}
    results = {}
    for job_id, j in lm["jobs"].items():
        r = B.job_result(cycle, job_id)
        results[job_id] = r
        for lab in r["labels"]:
            by_role[j["role"]][lab["case_ref"]] = lab
    return by_role, results, lm


def grade_checks(batch: str) -> dict:
    """job_id → {wrong: [...], total}"""
    by_role, _, lm = _labels(batch)
    out = {}
    for job_id, j in lm["jobs"].items():
        wrong = []
        for ref, chk in j["checks"].items():
            lab = by_role[j["role"]].get(ref)
            got = sorted({a["intent_id"] for a in (lab or {}).get("intents", [])})
            if got != sorted(chk["answer"]):
                wrong.append({"check_ref": chk["check_ref"], "answer": chk["answer"], "got": got})
        out[job_id] = {"wrong": wrong, "total": len(j["checks"]), "reruns": j.get("reruns", 0)}
    return out


def rerun_failed_checks(batch: str) -> list:
    """확인용 사례를 틀린 작업 중 아직 다시 안 돌린 것을 대기열에 다시 넣는다. 넣은 파일 목록."""
    cycle, _, _ = B.parse(batch)
    graded = grade_checks(batch)
    redo = [j for j, g in graded.items() if g["wrong"] and g["reruns"] < 1]
    if not redo:
        return []
    written = []
    ddir = DATA / cycle / "discarded"
    ddir.mkdir(parents=True, exist_ok=True)
    for job_id in redo:
        src = DATA / cycle / "results" / f"{job_id}.json"
        dst = ddir / f"{job_id}.checkfail{graded[job_id]['reruns'] + 1}.json"
        shutil.move(src, dst)
        written += [src, dst]
    cases = B.read(batch, "cases.json")
    written += assemble_orders.make_label_jobs(batch, cases, only=redo)
    return written


def _closer(items_a: list[str], items_b: list[str]) -> int:
    """두 라벨 묶음 중 교집합에 더 가까운 쪽 (0 = 라벨①, 1 = 라벨②)."""
    inter = set(items_a) & set(items_b)
    extra_a, extra_b = len(set(items_a) - inter), len(set(items_b) - inter)
    return 0 if extra_a <= extra_b else 1


def compare(batch: str) -> list:
    by_role, _, lm = _labels(batch)
    cases = B.read(batch, "cases.json")
    graded = grade_checks(batch)
    out_cases, rows = [], []
    for c in cases:
        l1 = by_role["label_1"].get(c["case_ref"], {"intents": [], "situation": {}, "alternatives": []})
        l2 = by_role["label_2"].get(c["case_ref"], {"intents": [], "situation": {}, "alternatives": []})
        a1 = {a["intent_id"]: a for a in l1["intents"]}
        a2 = {a["intent_id"]: a for a in l2["intents"]}
        final = sorted(set(a1) & set(a2))
        chosen = {}
        for iid in final:
            pick = _closer(a1[iid]["bundle_items"], a2[iid]["bundle_items"])
            src = (a1, a2)[pick][iid]
            chosen[iid] = {"from": ("label_1", "label_2")[pick], "intent_text": src["intent_text"],
                           "bundle_items": src["bundle_items"]}
        situation = {}
        if final:
            src_lab = l1 if chosen[final[0]]["from"] == "label_1" else l2
            s1, s2 = l1.get("situation") or {}, l2.get("situation") or {}
            situation = {k: (src_lab.get("situation") or {}).get(k) for k in ("event", "guests", "activity", "theme")
                         if s1.get(k) and s2.get(k)}
        made = sorted(c["made_intents"])
        rec = {
            "case_no": c["case_no"], "case_ref": c["case_ref"], "type": c["type"], "made_intents": made,
            "label_1": sorted(a1), "label_2": sorted(a2), "agree": sorted(a1) == sorted(a2),
            "alternatives": sorted(set(l1.get("alternatives", [])) | set(l2.get("alternatives", []))),
            "final": final, "chosen": chosen, "situation": situation,
            "unseen_intent": bool(made) and final != made,
            "has_related": any(e["related"] for e in c["calendar"]),
            "has_calendar": bool(c["calendar"]),
        }
        out_cases.append(rec)
        when = {"weekday": c["arrival_weekday"], "calendar_tags": [e["tag"] for e in c["calendar"]]}
        hh = {"types": None if c["household_hidden"] else c["household_types"]}
        for iid in (final or ["none"]):
            rows.append({
                "case_id": f"{batch}_{len(rows) + 1:04d}",
                "order_ref": c["case_ref"], "source": "synthetic", "items": c["items"],
                "intent_id": iid,
                "intent_text": chosen[iid]["intent_text"] if iid in chosen else None,
                "situation": situation if iid != "none" else {},
                "when": when, "household": hh,
            })
    for r in rows:
        r["case_id"] = "syn_" + r["case_id"]
    data = {"cases": out_cases, "rows": rows, "checks": graded, "compared_at": B.now_iso()}
    written = [B.write(batch, "compared.json", data)]
    B.set_state(batch, "compared")
    written.append(B.bdir(batch) / "state.json")
    return written
