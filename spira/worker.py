"""`spira start`의 본체: 내 계정마다 대기열에서 작업을 가져와 새 세션으로 처리한다.

- 한 사람이 계정을 둘 가졌으면 (예: Y = Gemini(A) + Codex(B)) 두 계정이 동시에 돈다.
- 아이템 풀(pool) 작업이 있으면 사이클 작업보다 먼저 한다.
- 할 일이 없거나 몫을 채우면 멈춘다. 팀원은 아무것도 재거나 적지 않는다.

몫 계산 (사람마다 config/nodes의 weekly_share_percent = 주간 한도 중 낼 %):
- AI 도구가 한도 %를 알려 주면 (Antigravity `/usage`) 작업 전후의 남은 % 차이를 그 작업이 쓴 양으로 기록한다.
  이번 주(한도가 다시 차는 시각 기준) 우리가 쓴 % 합이 주간 몫에 닿으면 멈춘다.
  하루 목표 = (주간 몫 - 이번 주 이미 쓴 양) ÷ 한도가 다시 찰 때까지 남은 날 수. 며칠 쉬어도 나머지 날에 나눠 채운다.
  5시간 한도가 거의 차면 다시 찰 때까지 기다렸다가 이어서 한다.
- 한도 %를 읽을 수 없는 도구는 하루 작업 수(jobs_per_day, 기본 10개)로 멈춘다.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from spira import config, queue
from spira.agents.base import Quota, read_quota, run_agent, total_tokens
from spira.validate import ResultError, check_result

PROMPTS = config.ROOT / "prompts"
PROMPT_FILE = {"item_pool": "item_pool.md", "generate": "generate_bundle.md",
               "label_1": "label.md", "label_2": "label.md"}
WORK_ROOT = Path.home() / ".spira-work"   # 저장소 밖. 에이전트가 저장소 파일을 보지 못하게 한다
COMPANY_NAME = {"gemini": "Gemini", "codex": "Codex", "claude": "Claude"}
DEFAULT_SHARE = 30.0         # weekly_share_percent를 비워 두면
DEFAULT_JOBS_PER_DAY = 10    # 한도 %를 읽을 수 없는 도구
WEEKLY_FLOOR = 5.0           # 주간 한도가 이만큼 남으면 몫과 상관없이 멈춘다 (본인 사용분 보호)
FIVE_H_FLOOR = 5.0           # 5시간 한도가 이만큼 남으면 다시 찰 때까지 기다린다


@dataclass
class Account:
    person: str
    company: str
    cycles: list[str]          # 지금 활성인 사이클
    model: str | None
    share: float               # 주간 몫 (주간 한도의 %)
    jobs_per_day: int

    @property
    def runner(self) -> str:
        return "fake" if os.environ.get("SPIRA_FAKE_AGENT") == "1" else self.company

    @property
    def scopes(self) -> list[str]:
        return ["pool", *self.cycles]

    @property
    def label(self) -> str:
        return f"{'·'.join(self.cycles)}({COMPANY_NAME[self.company]})"


def plan_accounts(person: str, today: date | None = None) -> list[Account]:
    node = config.load_nodes()[person]
    cycles = config.load_cycles()
    share = float(node.get("weekly_share_percent") or DEFAULT_SHARE)
    jobs_per_day = int(node.get("jobs_per_day") or DEFAULT_JOBS_PER_DAY)
    out = []
    for a in node.get("accounts", []):
        company = a["company"]
        active = [c for c in a.get("cycles", []) if c in cycles and config.is_active(cycles[c], today)]
        if not active:
            continue
        model = (cycles[active[0]].get("models") or {}).get(company)
        out.append(Account(person, company, active, model, share, jobs_per_day))
    return out


# ---------------------------------------------------------------- 몫 계산

def _logs(acc: Account, since: datetime) -> list[dict]:
    days = {(since.astimezone().date() + timedelta(days=i)).isoformat() for i in range(-1, 9)}
    out = []
    for m in queue.logs_for(acc.person, acc.company, days):
        try:
            if datetime.fromisoformat(m["finished_at"]) >= since:
                out.append(m)
        except (KeyError, ValueError):
            continue
    return out


def week_start(q: Quota) -> datetime:
    return q.weekly_reset - timedelta(days=7)


def used_this_week(acc: Account, q: Quota) -> float:
    """이번 주(한도 기준) 우리 작업이 쓴 주간 한도 %."""
    return sum((m.get("quota") or {}).get("weekly_used_pct") or 0 for m in _logs(acc, week_start(q)))


def today_target(acc: Account, q: Quota, now: datetime) -> tuple[float, float]:
    """(오늘 목표 %, 오늘 이미 쓴 %)."""
    midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    week = used_this_week(acc, q)
    today = sum((m.get("quota") or {}).get("weekly_used_pct") or 0 for m in _logs(acc, midnight))
    days_left = max(1, (q.weekly_reset.astimezone().date() - now.astimezone().date()).days + 1)
    return max(0.0, (acc.share - (week - today)) / days_left), today


def jobs_today(acc: Account) -> int:
    midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return len(_logs(acc, midnight))


def fmt(x: float) -> str:
    return f"{x:.1f}%"


# ---------------------------------------------------------------- 작업 하나

def render_prompt(role: str) -> str:
    text = (PROMPTS / PROMPT_FILE[role]).read_text(encoding="utf-8")
    if "\n---\n" in text:   # 위쪽 머리말(관리용 설명)은 에이전트에게 주지 않는다
        text = text.split("\n---\n", 1)[1]
    return text.replace("{input_path}", "job.json").replace("{output_path}", "result.json").strip() + "\n"


def run_one(acc: Account, job: queue.Job, stop: threading.Event, log, q_before: Quota | None) -> tuple[str, Quota | None]:
    """작업 하나를 처리한다. ('done' / 'failed' / 'released', 끝난 뒤 한도)."""
    workdir = WORK_ROOT / job.job_id
    started = datetime.now().astimezone()
    usage_all: dict = {}
    models_seen: set[str] = set()
    errors: list[str] = []
    attempts = 0
    result = None
    for attempts in (1, 2):   # 실패하면 새 세션으로 한 번 더
        shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True)
        (workdir / "job.json").write_text(json.dumps(job.data, ensure_ascii=False, indent=1), encoding="utf-8")
        (workdir / "prompt.md").write_text(render_prompt(job.role), encoding="utf-8")
        res = run_agent(acc.runner, acc.model, workdir)
        for k, v in res.usage.items():
            if isinstance(v, (int, float)):
                usage_all[k] = usage_all.get(k, 0) + v
        models_seen.update(res.models)
        if stop.is_set():
            queue.release(job)
            return "released", None
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
    q_after = read_quota(acc.runner)
    meta = {
        "job_id": job.job_id, "scope": job.scope, "batch": job.data.get("batch"),
        "role": job.role, "company": acc.company, "person": acc.person,
        "prompt_version": job.data.get("prompt_version"),
        "model_config": acc.model, "models_seen": sorted(models_seen),
        "usage": usage_all, "total_tokens": total_tokens(usage_all),
        "quota": _quota_delta(q_before, q_after),
        "attempts": attempts, "ok": result is not None, "errors": errors,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "seconds": round((finished - started).total_seconds()),
        "local_date": started.date().isoformat(),
        "fake": acc.runner == "fake",
    }
    if result is None:
        queue.fail(job, "\n".join(errors), meta)
        return "failed", q_after
    queue.finish(job, result, meta)
    shutil.rmtree(workdir, ignore_errors=True)
    return "done", q_after


def _quota_delta(before: Quota | None, after: Quota | None) -> dict | None:
    """작업 전후 남은 한도 차이 = 이 작업이 쓴 양. 그사이 한도가 다시 찼으면 기록하지 않는다."""
    if before is None or after is None:
        return None
    d: dict = {"weekly_left_after": round(after.weekly_left, 3)}
    if _same(after.weekly_reset, before.weekly_reset):
        d["weekly_used_pct"] = round(max(0.0, before.weekly_left - after.weekly_left), 3)
    if after.five_h_left is not None and before.five_h_left is not None and _same(after.five_h_reset, before.five_h_reset):
        d["five_h_used_pct"] = round(max(0.0, before.five_h_left - after.five_h_left), 3)
    return d


def _same(a: datetime | None, b: datetime | None) -> bool:
    """같은 한도 창인지 (다시 차는 시각이 10분 안쪽으로 같으면 같은 창)."""
    return a is not None and b is not None and abs((a - b).total_seconds()) < 600


# ---------------------------------------------------------------- 계정 하나

def _wait_five_hour(acc: Account, q: Quota, stop: threading.Event, log) -> Quota | None:
    """5시간 한도가 다시 찰 때까지 기다린다 (최대 5시간 10분)."""
    until = min(q.five_h_reset, datetime.now(timezone.utc) + timedelta(hours=5, minutes=10)) + timedelta(minutes=1)
    log(f"⏸ {acc.label}: 5시간 한도가 거의 찼습니다. {until.astimezone():%H:%M}까지 기다렸다가 이어서 합니다")
    while datetime.now(timezone.utc) < until:
        if stop.wait(30):
            return None
    return read_quota(acc.runner)


def work_account(acc: Account, max_jobs: int | None, stop: threading.Event, log, stats: dict) -> None:
    n = 0
    q = read_quota(acc.runner)
    while not stop.is_set():
        if max_jobs is not None and n >= max_jobs:
            log(f"■ {acc.label}: 요청한 {max_jobs}개를 끝냈습니다")
            break
        if q is not None:
            target, today = today_target(acc, q, datetime.now(timezone.utc))
            if max_jobs is None and today >= target:
                log(f"■ {acc.label}: 오늘 목표({fmt(target)})를 채웠습니다. 더 하려면 `uv run spira start 숫자`")
                break
            if q.weekly_left <= WEEKLY_FLOOR:
                log(f"■ {acc.label}: 주간 한도가 {fmt(q.weekly_left)}만 남아 멈춥니다")
                break
            if q.five_h_left is not None and q.five_h_reset is not None and q.five_h_left <= FIVE_H_FLOOR:
                q = _wait_five_hour(acc, q, stop, log)
                if q is None:
                    break
                continue
        elif max_jobs is None and jobs_today(acc) >= acc.jobs_per_day:
            log(f"■ {acc.label}: 오늘 {acc.jobs_per_day}개를 채웠습니다. 더 하려면 `uv run spira start 숫자`")
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
            status, q_after = run_one(acc, job, stop, log, q)
        except queue.GitError as e:   # 결과는 커밋돼 있고, 다음 동기화 때 같이 올라간다
            log(f"△ {job.job_id}: 올리기가 밀렸습니다. 다음 작업 때 같이 올립니다")
            status, q_after = "done", None
        q = q_after if q_after is not None else (read_quota(acc.runner) if q is not None else None)
        stats[status] = stats.get(status, 0) + 1
        n += 1
        log(f"  {'✓' if status == 'done' else '·'} {job.job_id} {status}")


def describe(acc: Account) -> str:
    q = read_quota(acc.runner)
    model = acc.model or "기본 모델"
    if q is None:
        return f"{acc.label} [{model}] 오늘 {jobs_today(acc)}/{acc.jobs_per_day}개 (이 도구는 한도 %를 알려 주지 않아 개수로 셉니다)"
    target, today = today_target(acc, q, datetime.now(timezone.utc))
    line = (f"{acc.label} [{model}] 오늘 {fmt(today)} / 목표 {fmt(target)} · "
            f"이번 주 {fmt(used_this_week(acc, q))} / 몫 {fmt(acc.share)} · 남은 한도 주간 {fmt(q.weekly_left)}")
    if q.five_h_left is not None:
        line += f" · 5시간 {fmt(q.five_h_left)}"
    return line


# ---------------------------------------------------------------- 시작

_instance_lock = None


def single_instance() -> bool:
    """이 저장소 폴더에서 spira start가 이미 돌고 있으면 False. (localhost 포트를 잡아 두는 방식이라
    프로그램이 꺼지면 저절로 풀린다. 포트는 저장소 경로에서 정한다)"""
    global _instance_lock
    import hashlib
    import socket
    port = 47000 + int(hashlib.sha256(str(config.ROOT).encode()).hexdigest()[:6], 16) % 1000
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    except OSError:
        s.close()
        return False
    _instance_lock = s
    return True


def keep_awake() -> None:
    """실행 중 노트북이 잠들지 않게 한다 (Windows). 프로그램이 끝나면 자동으로 풀린다."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)


def start(person: str, max_jobs: int | None = None, only: str | None = None,
          cycle: str | None = None, echo=print) -> int:
    lock = threading.Lock()

    def log(msg: str) -> None:
        with lock:
            echo(msg)

    if not single_instance():
        log("📦 이미 이 노트북에서 spira start가 돌고 있습니다. 그 창이 끝날 때까지 기다리세요.")
        return 0
    accounts = plan_accounts(person)
    if not accounts:
        log(f"📦 {person} — 지금 활성인 사이클이 없어서 할 일이 없습니다.")
        return 0
    if only or cycle:
        mine = [a for a in accounts if (not only or a.company == only) and (not cycle or cycle in a.cycles)]
        if cycle:   # 그 사이클 대기열만 (아이템 풀 작업은 회사 몫이라 그대로 포함)
            mine = [replace(a, cycles=[cycle]) for a in mine]
        if not mine:
            have = " · ".join(a.label for a in accounts)
            want = " ".join(x for x in [cycle and f"사이클 {cycle}", only and COMPANY_NAME[only]] if x)
            log(f"📦 {person} — 지금 돌릴 수 있는 {want} 계정이 없습니다 (내 계정: {have}).")
            return 0
        accounts = mine
    all_scopes = sorted({s for a in accounts for s in a.scopes})
    try:
        back = queue.requeue_stale(all_scopes, me=person)
    except queue.GitError as e:
        log(f"✗ 저장소를 최신으로 받지 못했습니다: {e}")
        log("  main 브랜치에 있는지(`git checkout main`), 인터넷이 되는지 확인하고 다시 실행하세요.")
        return 1

    now = datetime.now()
    picked = " ".join(x for x in [cycle, only and COMPANY_NAME[only]] if x)
    who = f"{picked}만 " if picked else ("계정마다 " if max_jobs else "")
    how = f"{who}{max_jobs}개" if max_jobs else f"{who}기본 몫만큼"
    log(f"📦 {person} · {now.month}월 {now.day}일 — 시작합니다 ({how})")
    for a in accounts:
        waiting = sum(len(queue.waiting(s, a.company)) for s in a.scopes)
        log(f"  - {describe(a)} · 기다리는 작업 {waiting}개")
    if back:
        log(f"  - 지난번에 멈춘 작업 {len(back)}개를 대기열로 돌렸습니다 (이어서 합니다)")

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
    log(f"📦 끝 — {' · '.join(lines)}")
    for a in accounts:
        log(f"  - {describe(a)}")
    return 1 if stats.get("failed") else 0
