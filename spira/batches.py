"""배치 폴더와 상태 (data/<사이클>/batches/<배치>/).

배치 하나 = 조각 하나 = 사례 1천 개. 상태는 state.json에 적는다.

    generating → labeling → reviewing → passed → loaded
                                      ↘ failed (U가 설정 · 프롬프트를 고쳐 다시)

파일
  plan.json      ① 주문 계획 (유형, 만들 때의 의도, 가구) + 생성 작업 목록
  goals.json     ① 생성 에이전트에게 준 목적
  cases.json     ③ 조립한 주문 (정답 아닌 "만든 쪽" 기록 포함, 서버에 안 감)
  label_map.json ③ 라벨 작업 ↔ 사례, 확인용 사례 대응
  compared.json  ⑤ 두 라벨 비교 결과 + 서버에 갈 줄(rows)
  report.json/md ⑥ 품질 관문
  loaded.json    ⑦ 적재 결과
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from spira import config

DATA = config.ROOT / "data"
BATCH_RE = re.compile(r"^([A-Z])(\d+)-(\d)$")


def parse(batch: str) -> tuple[str, int, str]:
    m = BATCH_RE.match(batch)
    if not m:
        raise ValueError(f"배치 이름이 아님: {batch}")
    return m.group(1), int(m.group(2)), m.group(3)


def name(cycle: str, round_no: int, slice_id: str) -> str:
    return f"{cycle}{round_no}-{slice_id}"


def bdir(batch: str) -> Path:
    cycle, _, _ = parse(batch)
    return DATA / cycle / "batches" / batch


def rng_for(batch: str, step: str) -> random.Random:
    """배치 · 단계마다 고정된 시드 (같은 배치를 다시 만들 수 있게)."""
    seed = int(hashlib.sha256(f"{batch}:{step}".encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def read(batch: str, fname: str, default=None):
    p = bdir(batch) / fname
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write(batch: str, fname: str, data) -> Path:
    p = bdir(batch) / fname
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state(batch: str) -> str | None:
    s = read(batch, "state.json")
    return s["state"] if s else None


def set_state(batch: str, new: str, note: str = "") -> None:
    s = read(batch, "state.json", {"history": []})
    s["state"] = new
    s["history"].append({"state": new, "at": now_iso(), **({"note": note} if note else {})})
    write(batch, "state.json", s)


def all_batches() -> list[str]:
    out = []
    for p in sorted(DATA.glob("*/batches/*")):
        if p.is_dir() and BATCH_RE.match(p.name):
            out.append(p.name)
    return sorted(out, key=lambda b: (parse(b)[0], parse(b)[1], parse(b)[2]))


def rounds(cycle: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for b in all_batches():
        c, r, _ = parse(b)
        if c == cycle:
            out.setdefault(r, []).append(b)
    return out


def job_done(scope: str, job_id: str) -> bool:
    return (DATA / scope / "results" / f"{job_id}.json").exists()


def job_result(scope: str, job_id: str):
    p = DATA / scope / "results" / f"{job_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def job_failed(scope: str, job_id: str) -> bool:
    return (DATA / scope / "failed" / f"{job_id}.json").exists()


def pipeline() -> dict:
    return config._load(config.CONFIG / "pipeline.yaml")


def intents() -> list[dict]:
    return config.load_list("intents")["intents"]


def intent_ref(i: dict) -> dict:
    return {"id": i["id"], "name": i["name"], "definition": i["definition"]}


def item_pool() -> dict:
    p = config.CONFIG / "lists" / "item_pool.yaml"
    return config._load(p) if p.exists() else {}


WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
