"""확인용 사례 (설계 6절): 라벨 작업 50개마다 3개를 섞고, 틀린 작업은 다시 돌린다.

첫 사이클은 U가 직접 정답을 단 20개(checks/check_cases_v1.json + checks/check_answers_U.csv)를 쓴다.
정답 칸이 빈 사례는 쓰지 않는다. 정답이 하나도 없으면 확인용 사례 없이 진행하고 보고서에 적는다.
TODO(둘째 사이클부터): 사람 검수와 두 라벨이 모두 일치한 사례를 더한다.
"""

from __future__ import annotations

import csv
import json

from spira import config

CASES = config.ROOT / "checks" / "check_cases_v1.json"
ANSWERS = config.ROOT / "checks" / "check_answers_U.csv"


def _read_csv(path):
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            with path.open(encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    return []


def _col(row: dict, prefix: str) -> str:
    for k, v in row.items():
        if k and k.strip().startswith(prefix):
            return (v or "").strip()
    return ""


def load() -> list[dict]:
    """[{case(LabelCase dict), answer: set[str]}] 정답이 있는 것만. answer가 빈 집합이면 의도 없음."""
    if not CASES.exists() or not ANSWERS.exists():
        return []
    cases = {c["case_ref"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]}
    ids = {i["id"] for i in config.load_list("intents")["intents"]} | {"unclassified", "none"}
    out = []
    for row in _read_csv(ANSWERS):
        ref = _col(row, "case_ref")
        a1, a2 = _col(row, "정답1"), _col(row, "정답2")
        if ref not in cases or not a1:
            continue
        answer = {a for a in (a1, a2) if a and a != "none"}
        if not answer <= ids:
            continue
        out.append({"case": cases[ref], "answer": sorted(answer)})
    return out
