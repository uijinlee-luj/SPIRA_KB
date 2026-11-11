"""현황 요약 만들기. GitHub Actions가 data/가 바뀔 때마다 실행해서 status 브랜치에 status.json을 올리고,
현황판(dashboard/index.html, GitHub Pages)이 그 파일을 몇 분마다 다시 읽는다.

    python -m spira.status > status.json

pyyaml만 있으면 돈다 (Actions에서 가볍게 돌리려고).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from spira import config

DATA = config.ROOT / "data"
KST = timezone(timedelta(hours=9))
STATES = ("queue", "running", "results", "failed")
DEFAULT_SHARE = 30.0


def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _dt(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def build(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(KST).date()
    week_ago = now - timedelta(days=7)

    # 작업 로그 (지금 기록 + 다시 돌리기 전 기록)
    metas = []
    current_meta = {}
    for p in DATA.glob("*/logs/*.meta.json"):
        m = _load(p)
        if not m:
            continue
        metas.append(m)
        if ".prev" not in p.name:
            current_meta[m.get("job_id")] = m

    # 작업 상태
    jobs = {}
    running = []
    failed = []
    for scope_dir in sorted(p for p in DATA.iterdir() if p.is_dir()):
        scope = scope_dir.name
        for state in STATES:
            for p in sorted((scope_dir / state).glob("*.json")):
                if p.name.endswith(".claim.json"):
                    continue
                job_id = p.stem
                info = {"scope": scope, "state": state}
                if state in ("queue", "running", "failed"):
                    d = _load(p) or {}
                    info.update(batch=d.get("batch"), role=d.get("role"), company=d.get("company"))
                else:
                    m = current_meta.get(job_id) or {}
                    info.update(batch=m.get("batch"), role=m.get("role"), company=m.get("company"))
                jobs[job_id] = info
                if state == "running":
                    c = _load(scope_dir / state / f"{job_id}.claim.json") or {}
                    running.append({"job_id": job_id, "scope": scope, "role": info["role"],
                                    "company": info["company"], "person": c.get("person"),
                                    "claimed_at": c.get("claimed_at")})
                if state == "failed":
                    err = scope_dir / state / f"{job_id}.error.txt"
                    msg = err.read_text(encoding="utf-8").strip().splitlines()[-1] if err.exists() else ""
                    failed.append({"job_id": job_id, "scope": scope, "company": info["company"],
                                   "error": msg[:300]})

    # 진행률: 범위(pool · A · B) → 배치 → 역할 → 상태별 개수
    progress: dict = {}
    for job_id, j in jobs.items():
        scope = progress.setdefault(j["scope"], {})
        batch_key = "아이템 풀" if j["scope"] == "pool" else (j["batch"] or "?")
        batch = scope.setdefault(batch_key, {})
        group = j["company"] if j["scope"] == "pool" else (j["role"] or "?")
        cell = batch.setdefault(group, {s: 0 for s in STATES})
        cell[j["state"]] += 1

    # 배치 상태 · 품질 관문
    batch_info = {}
    for st_file in sorted(DATA.glob("*/batches/*/state.json")):
        b = st_file.parent.name
        st = (_load(st_file) or {}).get("state")
        rep = _load(st_file.parent / "report.json") or {}
        items = ((rep.get("metrics") or {}).get("items") or {})
        batch_info[b] = {
            "state": st, "verdict": rep.get("verdict"),
            "failed_items": [k for k, v in items.items() if v.get("ok") is False],
            "review": (rep.get("review") or {}).get("wrong_ratio"),
        }
    pool_status = None
    pool_file = config.CONFIG / "lists" / "item_pool.yaml"
    if pool_file.exists():
        import yaml
        pool_status = (yaml.safe_load(pool_file.read_text(encoding="utf-8")) or {}).get("status")
    review_dir = config.ROOT / "review" / "todo"
    review_todo = sorted(p.name for p in review_dir.glob("*.csv")) if review_dir.exists() else []

    # 사람 · 계정별
    cycles = config.load_cycles()
    people = []
    for person, node in config.load_nodes().items():
        share = float(node.get("weekly_share_percent") or DEFAULT_SHARE)
        for a in node.get("accounts", []):
            company = a["company"]
            active = [c for c in a.get("cycles", []) if c in cycles and config.is_active(cycles[c], today)]
            mine = [m for m in metas if m.get("person") == person and m.get("company") == company
                    and not m.get("fake")]
            mine.sort(key=lambda m: m.get("finished_at") or "")

            def pct(ms):
                return round(sum(((m.get("quota") or {}).get("weekly_used_pct") or 0) for m in ms), 2)

            today_ms = [m for m in mine if (_dt(m.get("finished_at")) or now).astimezone(KST).date() == today]
            week_ms = [m for m in mine if (_dt(m.get("finished_at")) or now) >= week_ago]
            with_quota = [m for m in mine if (m.get("quota") or {}).get("weekly_left_after") is not None]
            people.append({
                "person": person, "company": company, "cycles": active, "share": share,
                "measures_quota": bool(with_quota),
                "today_pct": pct(today_ms), "week_pct": pct(week_ms),
                "today_jobs": len(today_ms), "week_jobs": len(week_ms), "total_jobs": len(mine),
                "failed_jobs": sum(1 for m in mine if not m.get("ok")),
                "weekly_left": (with_quota[-1]["quota"]["weekly_left_after"] if with_quota else None),
                "last_finished_at": mine[-1].get("finished_at") if mine else None,
                "running": [r["job_id"] for r in running if r["person"] == person and r["company"] == company],
            })

    recent = sorted((m for m in metas if not m.get("fake")), key=lambda m: m.get("finished_at") or "", reverse=True)[:20]
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "running": sorted(running, key=lambda r: r.get("claimed_at") or ""),
        "progress": progress,
        "people": people,
        "recent": [{k: m.get(k) for k in ("job_id", "person", "company", "role", "ok", "seconds",
                                           "finished_at", "attempts", "prompt_version")}
                   | {"weekly_used_pct": (m.get("quota") or {}).get("weekly_used_pct")} for m in recent],
        "failed": failed,
        "batches": batch_info,
        "item_pool": pool_status,
        "review_todo": review_todo,
        "cycles": {name: {"active": config.is_active(c, today), "ends_on": str(c.get("ends_on") or ""),
                          "models": c.get("models") or {}} for name, c in cycles.items()},
    }


if __name__ == "__main__":
    json.dump(build(), sys.stdout, ensure_ascii=False, indent=1)
