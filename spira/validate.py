"""에이전트 결과 검사 (형식 + 작업과 맞는지). 통과하지 못하면 그 작업을 새 세션으로 한 번 더 돌린다."""

from __future__ import annotations

from spira import config
from spira.schemas import GenerateResult, ItemPoolResult, LabelResult


class ResultError(ValueError):
    pass


def check_result(job: dict, result: dict) -> dict:
    """문제가 있으면 ResultError. 통과하면 정리된 결과(dict)를 돌려준다."""
    role = job["role"]
    try:
        if role == "item_pool":
            r = ItemPoolResult.model_validate(result)
        elif role == "generate":
            r = GenerateResult.model_validate(result)
        else:
            r = LabelResult.model_validate(result)
    except Exception as e:  # pydantic ValidationError
        raise ResultError(f"형식이 맞지 않음: {e}") from e
    if r.job_id != job["job_id"]:
        raise ResultError(f"job_id가 다름 ({r.job_id})")

    if role == "item_pool":
        if not r.items:
            raise ResultError("물건이 하나도 없음")
        if len(r.items) < job["target_count"] * 0.5:
            raise ResultError(f"물건이 너무 적음 ({len(r.items)}개, 목표 {job['target_count']}개)")
    elif role == "generate":
        want = [g["goal_id"] for g in job["goals"]]
        got = [b.goal_id for b in r.bundles]
        if sorted(got) != sorted(want):
            raise ResultError(f"goal_id가 작업과 맞지 않음 (빠짐 {set(want) - set(got)}, 남음 {set(got) - set(want)})")
    else:
        want = [c["case_ref"] for c in job["cases"]]
        got = [lab.case_ref for lab in r.labels]
        if sorted(got) != sorted(want):
            raise ResultError(f"case_ref가 작업과 맞지 않음 (빠짐 {set(want) - set(got)}, 남음 {set(got) - set(want)})")
        ids = {i["id"] for i in config.load_list("intents")["intents"]}
        items_by_case = {c["case_ref"]: set(c["items"]) for c in job["cases"]}
        for lab in r.labels:
            for a in lab.intents:
                if a.intent_id not in ids | {"unclassified"}:
                    raise ResultError(f"{lab.case_ref}: 목록에 없는 의도 id '{a.intent_id}'")
                extra = set(a.bundle_items) - items_by_case[lab.case_ref]
                if extra:
                    raise ResultError(f"{lab.case_ref}: 주문에 없는 물건 {sorted(extra)}")
            bad = [x for x in lab.alternatives if x not in ids]
            if bad:
                raise ResultError(f"{lab.case_ref}: 목록에 없는 대안 의도 {bad}")
    return r.model_dump()
