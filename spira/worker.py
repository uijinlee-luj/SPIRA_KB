"""`spira start`의 본체: 내 계정마다 대기열에서 작업을 가져와 새 세션으로 처리한다.

- 한 사람이 계정을 둘 가졌으면 (예: Y = Gemini(A) + Codex(B)) 두 계정이 동시에 돈다.
- 아이템 풀(pool) 작업이 있으면 사이클 작업보다 먼저 한다.
- 오늘 할당량을 채우거나 할 일이 없으면 멈춘다. 오늘 쓴 양은 저장소의 기록(logs)에서 세므로,
  두 번 실행해도 할당량을 더 쓰지 않는다.
- 측정 전(config/nodes의 calibration이 비어 있음)에는 "측정 모드"로 하루 작업 1개만 한다.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from spira import config, queue
from spira.agents.base import run_agent, total_tokens
from spira.validate import ResultError, check_result

PROMPTS = config.ROOT / "prompts"
PROMPT_FILE = {"item_pool": "item_pool.md", "generate": "generate_bundle.md",
               "label_1": "label.md", "label_2": "label.md"}
WORK_ROOT = Path.home() / ".spira-work"   # 저장소 밖. 에이전트가 저장소 파일을 보지 못하게 한다
COMPANY_NAME = {"gemini": "Gemini", "codex": "Codex", "claude": "Claude"}


@dataclass
class Account:
    person: str
    company: str
    cycles: list[str]          # 지금 활성인 사이클
    model: str | None
    token_budget: int | None   # 오늘 쓸 토큰 (측정 후)
    job_budget: int | None     # 오늘 할 작업 수 (토큰을 못 재는 경우 · 측정 모드)
    measuring: bool

    @property
    def scopes(self) -> list[str]:
        return ["pool", *self.cycles]

    @property
    def label(self) -> str:
        return f"{'·'.join(self.cycles)}({COMPANY_NAME[self.company]})"


def plan_accounts(person: str, today: date | None = None) -> list[Account]:
    node = config.load_nodes()[person]
    cycles = config.load_cycles()
    share = node.get("weekly_share_percent")
    cal = node.get("calibration") or {}
    out = []
    for a in node.get("accounts", []):
        company = a["company"]
        active = [c for c in a.get("cycles", []) if c in cycles and config.is_active(cycles[c], today)]
        if not active:
            continue
        model = (cycles[active[0]].get("models") or {}).get(company)
        tpp = (cal.get("tokens_per_percent") or {}).get(company)
        jpp = (cal.get("jobs_per_percent") or {}).get(company)
        token_budget = int(share * tpp / 7) if share and tpp else None
        job_budget = max(1, int(share * jpp / 7)) if share and jpp and not tpp else None
        measuring = token_budget is None and job_budget is None
        out.append(Account(person, company, active, model, token_budget,
                           1 if measuring else job_budget, measuring))
    return out


def used_today(acc: Account, day: str) -> tuple[int, int]:
    logs = queue.logs_for(acc.person, acc.company, day)
    return len(logs), sum(m.get("total_tokens") or 0 for m in logs)


def render_prompt(role: str) -> str:
    text = (PROMPTS / PROMPT_FILE[role]).read_text(encoding="utf-8")
    if "\n---\n" in text:   # 위쪽 머리말(관리용 설명)은 에이전트에게 주지 않는다
        text = text.split("\n---\n", 1)[1]
    return text.replace("{input_path}", "job.json").replace("{output_path}", "result.json").strip() + "\n"


def run_one(acc: Account, job: queue.Job, stop: threading.Event, log) -> str:
    """작업 하나를 처리한다. 'done' / 'failed' / 'released'."""
    workdir = WORK_ROOT / job.job_id
    started = datetime.now().astimezone()
    usage_all: dict = {}
    models_seen: set[str] = set()
    errors: list[str] = []
    runner = "fake" if os.environ.get("SPIRA_FAKE_AGENT") == "1" else acc.company
    attempts = 0
    result = None
    for attempts in (1, 2):   # 실패하면 새 세션으로 한 번 더
        shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True)
        (workdir / "job.json").write_text(json.dumps(job.data, ensure_ascii=False, indent=1), encoding="utf-8")
        (workdir / "prompt.md").write_text(render_prompt(job.role), encoding="utf-8")
        res = run_agent(runner, acc.model, workdir)
        for k, v in res.usage.items():
            if isinstance(v, (int, float)):
                usage_all[k] = usage_all.get(k, 0) + v
        models_seen.update(res.models)
        if stop.is_set():
            queue.release(job)
            return "released"
        try:
            if not res.ok:
                raise ResultError(f"에이전트 실행 실패: {res.error}")
            out = workdir / "result.json"
            if not out.exists():
                raise ResultError("result.json을 쓰지 않음")
            result = check_result(job.data, json.loads(out.read_text(encoding="utf-8")))
            break
        except (ResultError, json.JSONDecodeError) as e:
            errors.append(f"[{attempts}회] {e}")
            log(f"  ✗ {job.job_id} {attempts}회째 실패: {str(e)[:200]}")
    finished = datetime.now().astimezone()
    meta = {
        "job_id": job.job_id, "scope": job.scope, "batch": job.data.get("batch"),
        "role": job.role, "company": acc.company, "person": acc.person,
        "prompt_version": job.data.get("prompt_version"),
        "model_config": acc.model, "models_seen": sorted(models_seen),
        "usage": usage_all, "total_tokens": total_tokens(usage_all),
        "attempts": attempts, "ok": result is not None, "errors": errors,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "seconds": round((finished - started).total_seconds()),
        "local_date": started.date().isoformat(),
        "fake": runner == "fake",
    }
    if result is None:
        queue.fail(job, "\n".join(errors), meta)
        return "failed"
    queue.finish(job, result, meta)
    shutil.rmtree(workdir, ignore_errors=True)
    return "done"


def work_account(acc: Account, max_jobs: int | None, stop: threading.Event, log, stats: dict) -> None:
    day = date.today().isoformat()
    n = 0
    while not stop.is_set():
        jobs_today, tokens_today = used_today(acc, day)
        if acc.job_budget is not None and jobs_today >= acc.job_budget:
            log(f"■ {acc.label}: 오늘 할당량({acc.job_budget}개)을 채웠습니다")
            break
        if acc.token_budget is not None and tokens_today >= acc.token_budget:
            log(f"■ {acc.label}: 오늘 할당량({acc.token_budget:,} 토큰)을 채웠습니다")
            break
        if max_jobs is not None and n >= max_jobs:
            break
        try:
            job = queue.claim_next(acc.scopes, acc.company, acc.person)
        except queue.GitError as e:
            log(f"✗ {acc.label}: 대기열을 받지 못했습니다 — {e}")
            break
        if job is None:
            log(f"■ {acc.label}: 지금 할 작업이 없습니다")
            break
        log(f"▶ {acc.label}: {job.job_id}")
        try:
            status = run_one(acc, job, stop, log)
        except queue.GitError as e:
            log(f"✗ {job.job_id}: {e}")
            break
        stats[status] = stats.get(status, 0) + 1
        n += 1
        log(f"  {'✓' if status == 'done' else '·'} {job.job_id} {status}")


def keep_awake() -> None:
    """실행 중 노트북이 잠들지 않게 한다 (Windows). 프로그램이 끝나면 자동으로 풀린다."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)


def start(person: str, max_jobs: int | None = None, echo=print) -> int:
    lock = threading.Lock()

    def log(msg: str) -> None:
        with lock:
            echo(msg)

    accounts = plan_accounts(person)
    if not accounts:
        log(f"📦 {person} — 지금 활성인 사이클이 없어서 할 일이 없습니다.")
        return 0
    all_scopes = sorted({s for a in accounts for s in a.scopes})
    try:
        back = queue.requeue_stale(all_scopes)
    except queue.GitError as e:
        log(f"✗ 저장소를 최신으로 받지 못했습니다: {e}")
        log("  main 브랜치에 있는지(`git checkout main`), 인터넷이 되는지 확인하고 다시 실행하세요.")
        return 1

    day = date.today().isoformat()
    now = datetime.now()
    log(f"📦 {person} · {now.month}월 {now.day}일 — 시작합니다")
    for a in accounts:
        jobs_today, tokens_today = used_today(a, day)
        waiting = sum(len(queue.waiting(s, a.company)) for s in a.scopes)
        if a.measuring:
            budget = "측정 모드: 오늘 1개"
        elif a.token_budget is not None:
            budget = f"오늘 {a.token_budget:,} 토큰까지"
        else:
            budget = f"오늘 {a.job_budget}개까지"
        model = a.model or "앱에서 고른 모델"
        log(f"  - {a.label} [{model}] {budget} · 기다리는 작업 {waiting}개 · "
            f"오늘 이미 {jobs_today}개 / {tokens_today:,} 토큰")
    if back:
        log(f"  - 멈춰 있던 작업 {len(back)}개를 대기열로 돌렸습니다")
    if any(a.measuring for a in accounts):
        log("  ⓘ 측정 모드: 시작 전과 끝난 뒤에 각 AI의 사용량(한도) 화면을 확인해 U에게 알려 주세요.")

    keep_awake()
    stop = threading.Event()
    stats: dict = {}
    threads = [threading.Thread(target=work_account, args=(a, max_jobs, stop, log, stats), daemon=True)
               for a in accounts]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        log("멈추는 중입니다. 하던 작업은 대기열로 돌려놓습니다…")
        stop.set()
        for t in threads:
            t.join(timeout=120)

    lines = [f"완료 {stats.get('done', 0)}개"]
    if stats.get("failed"):
        lines.append(f"실패 {stats['failed']}개 (data/*/failed/)")
    if stats.get("released"):
        lines.append(f"되돌림 {stats['released']}개")
    used = sum(used_today(a, day)[1] for a in accounts)
    log(f"📦 끝 — {' · '.join(lines)} · 오늘 토큰 {used:,}")
    return 1 if stats.get("failed") else 0
