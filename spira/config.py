"""config/ 아래 설정 파일을 읽고, 설계 규칙을 지키는지 검사한다."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
COMPANIES = {"gemini", "codex", "claude"}


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_cycles() -> dict[str, dict]:
    return {p.stem: _load(p) for p in sorted((CONFIG / "cycles").glob("*.yaml"))}


def load_nodes() -> dict[str, dict]:
    return {p.stem: _load(p) for p in sorted((CONFIG / "nodes").glob("*.yaml"))}


def load_list(name: str) -> dict:
    return _load(CONFIG / "lists" / f"{name}.yaml")


def is_active(cycle: dict, today: date | None = None) -> bool:
    """active가 켜져 있고, 끝나는 날이 지나지 않았으면 활성."""
    today = today or date.today()
    ends_on = cycle.get("ends_on")
    return bool(cycle.get("active")) and (ends_on is None or today < ends_on)


def check(today: date | None = None) -> list[str]:
    """설계 규칙 위반을 찾아 문제 목록을 돌려준다. 빈 목록이면 통과."""
    problems: list[str] = []
    cycles = load_cycles()
    nodes = load_nodes()

    # 1) 사이클마다: 회사가 다른 세 모델 + 역할 돌리기
    seen_accounts: dict[tuple[str, str], str] = {}
    for name, c in cycles.items():
        members = c.get("members", {})
        if set(members) != COMPANIES:
            problems.append(f"사이클 {name}: 회사가 gemini·codex·claude 셋이어야 함 (지금 {sorted(members)})")
        for slice_id, roles in c.get("slices", {}).items():
            trio = [roles.get("generate"), roles.get("label_1"), roles.get("label_2")]
            if len(set(trio)) != 3 or not set(trio) <= COMPANIES:
                problems.append(f"사이클 {name} 조각 {slice_id}: 생성·라벨①·라벨②가 서로 다른 회사여야 함 ({trio})")
        gens = sorted(r.get("generate") for r in c.get("slices", {}).values())
        if gens != sorted(COMPANIES):
            problems.append(f"사이클 {name}: 각 회사가 생성을 한 번씩 맡아야 함 ({gens})")

        # 2) 계정 하나는 한 사이클에만 (활성 사이클끼리)
        if is_active(c, today):
            for company, m in members.items():
                key = (m["person"], company)
                if key in seen_accounts:
                    problems.append(f"{m['person']}의 {company} 계정이 사이클 {seen_accounts[key]}·{name}에 겹침")
                seen_accounts[key] = name

    # 3) 사이클 설정과 사람별 설정이 서로 맞는지
    for name, c in cycles.items():
        for company, m in c.get("members", {}).items():
            node = nodes.get(m["person"])
            if node is None:
                problems.append(f"사이클 {name}: config/nodes/{m['person']}.yaml이 없음")
                continue
            ok = any(a["company"] == company and name in a.get("cycles", []) for a in node.get("accounts", []))
            if not ok:
                problems.append(f"{m['person']}.yaml에 {company} 계정의 사이클 {name}이 적혀 있지 않음")

    # 4) 목록 개수 (지식 베이스 설계 4절)
    intents = load_list("intents").get("intents", [])
    if len(intents) != 30:
        problems.append(f"의도가 30개여야 함 (지금 {len(intents)})")
    if len({i["id"] for i in intents}) != len(intents):
        problems.append("의도 id가 중복됨")
    tag_groups = load_list("calendar_tags").get("groups", {})
    tags = [t for ts in tag_groups.values() for t in ts]
    if len(tags) != 30 or len(set(tags)) != 30:
        problems.append(f"캘린더 태그가 서로 다른 30개여야 함 (지금 {len(set(tags))})")
    for i in intents:
        for t in i.get("related_tags", []):
            if t not in tags:
                problems.append(f"의도 {i['id']}의 관련 태그 '{t}'가 태그 목록에 없음")
    syn = load_list("calendar_tags").get("synonyms", {})
    owners: dict[str, str] = {}
    for tag, words in syn.items():
        for w in words:
            if w in owners:
                problems.append(f"동의어 '{w}'가 태그 {owners[w]}·{tag} 두 곳에 있음")
            owners[w] = tag
    axes = load_list("household").get("axes", {})
    n_types = sum(len(a["types"]) for a in axes.values())
    if n_types != 20:
        problems.append(f"가구 유형이 20개여야 함 (지금 {n_types})")

    return problems
