"""가구 유형 조합 뽑기와 규칙 검사 (설계 4-3 · 4-4절, config/lists/household.yaml).

뽑는 확률은 시작값이다 (실제 분포 자료 없이 정함). 규칙을 통과할 때까지 다시 뽑는다.
"""

from __future__ import annotations

import random

from spira import config

# 시작값: 인원(하나), 나머지 축은 칸마다 따로 붙을 확률
SIZE_WEIGHTS = {"1인": 0.33, "2인": 0.28, "3~4인": 0.32, "5인 이상": 0.07}
COMPOSITION_P = {"부부·커플": 0.55, "영유아 자녀": 0.15, "초등 자녀": 0.15, "중학생 자녀": 0.10,
                 "고등학생 자녀": 0.10, "부모 + 성인 자녀": 0.15, "3대 함께": 0.05, "룸메이트·셰어하우스": 0.05}
LIFE_STAGE_WEIGHTS = {"대학생": 0.15, "직장인": 0.65, "은퇴·노년": 0.20}
WORK_P = {"맞벌이": 0.40, "재택근무": 0.10}
PET_P = {"반려견": 0.15, "반려묘": 0.08, "그 밖의 반려동물": 0.04}


def _lists():
    return config.load_list("household")


def min_people(types: set[str]) -> int:
    hh = _lists()
    n = (2 if "부부·커플" in types else 1) + sum(1 for c in hh["child_types"] if c in types)
    n += 1 if "부모 + 성인 자녀" in types else 0
    if "3대 함께" in types:
        n = max(n, 3)
    return n


def rule_level(types: list[str]) -> str | None:
    """'blocked' / 'rare' / None. household.yaml의 규칙을 코드로 옮긴 것."""
    hh = _lists()
    t = set(types)
    size = next((s for s in hh["axes"]["size"]["types"] if s in t), None)
    children = {c for c in hh["child_types"] if c in t}
    need = min_people(t)
    cap = hh["size_max"].get(size)
    if cap is not None and need > cap:
        return "blocked"
    if "룸메이트·셰어하우스" in t and (t & {"부부·커플", "부모 + 성인 자녀", "3대 함께"} or children):
        return "blocked"
    if "맞벌이" in t and "부부·커플" not in t:
        return "blocked"
    if "은퇴·노년" in t and t & {"맞벌이", "재택근무"}:
        return "blocked"
    if "대학생" in t and ("맞벌이" in t or children or "재택근무" in t):
        return "rare"
    if "은퇴·노년" in t and children:
        return "rare"
    low = {"1인": 1, "2인": 2, "3~4인": 3, "5인 이상": 5}.get(size, 1)
    if low - need >= 2:
        return "rare"
    return None


def fits_intent(types: list[str], intent_id: str) -> bool:
    req = _lists().get("intent_requirements", {}).get(intent_id)
    if not req:
        return True
    hh = _lists()
    t = set(types)

    def expand(xs):
        out = set()
        for x in xs:
            out |= set(hh[x]) if x in hh and isinstance(hh[x], list) else {x}
        return out
    if "any_of" in req and not (t & expand(req["any_of"])):
        return False
    if "none_of" in req and (t & expand(req["none_of"])):
        return False
    return True


def sample(rng: random.Random, intent_id: str | None = None, tries: int = 5000) -> list[str]:
    """규칙(불가 · 드묾)과 의도 조건을 통과하는 가구 유형 목록 하나."""
    for _ in range(tries):
        size = rng.choices(list(SIZE_WEIGHTS), weights=list(SIZE_WEIGHTS.values()))[0]
        types = [size]
        if size != "1인":   # 1인 가구는 구성 칸이 붙지 않는다 (붙으면 어차피 불가)
            types += [k for k, p in COMPOSITION_P.items() if rng.random() < p]
        types.append(rng.choices(list(LIFE_STAGE_WEIGHTS), weights=list(LIFE_STAGE_WEIGHTS.values()))[0])
        types += [k for k, p in WORK_P.items() if rng.random() < p]
        types += [k for k, p in PET_P.items() if rng.random() < p]
        if rule_level(types) is None and (intent_id is None or fits_intent(types, intent_id)):
            return types
    raise RuntimeError(f"가구 조합을 찾지 못함 (의도 {intent_id})")
