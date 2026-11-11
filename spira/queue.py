"""GitHub 저장소를 작업 대기열로 쓴다.

폴더 (scope = 사이클 이름 A · B, 또는 처음 한 번 하는 아이템 풀 pool):
  data/<scope>/queue/<job_id>.json          기다리는 작업
  data/<scope>/running/<job_id>.json        누가 가져간 작업 (+ <job_id>.claim.json: 누가 · 언제)
  data/<scope>/results/<job_id>.json        검사를 통과한 결과
  data/<scope>/logs/<job_id>.meta.json      모델 · 토큰 · 걸린 시간 기록
  data/<scope>/failed/<job_id>.json         두 번 실패한 작업 (+ .error.txt)

예약은 "queue → running 이동을 커밋해서 push"다. 두 노트북이 같은 작업을 동시에 가져가려 하면
한쪽 push가 거절되고, 거절된 쪽은 자기 예약을 취소하고 다음 작업을 찾는다.
git 명령은 한 번에 하나만 돌도록 잠근다 (한 사람이 계정 두 개를 동시에 돌리기 때문).
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from spira.config import ROOT

DATA = ROOT / "data"
STALE_AFTER = timedelta(hours=3)   # 이보다 오래 running에 있으면 멈춘 것으로 보고 대기열로 돌린다
_lock = threading.RLock()


class GitError(RuntimeError):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} 실패: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def sync() -> None:
    """원격의 최신 대기열을 받는다. 노트북에서 고친 다른 파일은 그대로 둔다."""
    with _lock:
        git("pull", "--rebase", "--autostash", "-q")


def _commit_and_push(message: str, paths: list[Path], attempts: int = 5) -> bool:
    """paths만 커밋해서 push한다. 다른 사람이 먼저 push했으면 받아서 다시 시도한다.
    rebase가 충돌하면(= 같은 작업을 남이 먼저 가져감) 이 커밋을 취소하고 False."""
    rel = []
    for p in paths:
        r = str(p.relative_to(ROOT)).replace("\\", "/")
        if p.exists():
            git("add", "--", r)
            rel.append(r)
        elif git("cat-file", "-e", f"HEAD:{r}", check=False).returncode == 0:
            git("rm", "-q", "--cached", "--ignore-unmatch", "--", r)   # 지운 파일
            rel.append(r)
    if not rel:
        return True
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return True   # 바뀐 것 없음
    git("commit", "-q", "-m", message, "--", *rel)
    for _ in range(attempts):
        if git("push", "-q", check=False).returncode == 0:
            return True
        if git("pull", "--rebase", "--autostash", "-q", check=False).returncode != 0:
            git("rebase", "--abort", check=False)
            git("reset", "--keep", "HEAD~1", check=False)   # 내 커밋만 취소, 다른 로컬 변경은 유지
            git("pull", "--rebase", "--autostash", "-q", check=False)
            return False
    return False


@dataclass
class Job:
    scope: str
    job_id: str
    data: dict

    @property
    def company(self) -> str:
        return self.data["company"]

    @property
    def role(self) -> str:
        return self.data["role"]


def _dir(scope: str, kind: str) -> Path:
    return DATA / scope / kind


def waiting(scope: str, company: str) -> list[Path]:
    """그 회사가 할 수 있는, 기다리는 작업 (이름순 = 만든 순서)."""
    out = []
    for p in sorted(_dir(scope, "queue").glob("*.json")):
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("company") == company:
                out.append(p)
        except (json.JSONDecodeError, OSError):
            continue
    return out


def claim_next(scopes: list[str], company: str, person: str) -> Job | None:
    """scopes 순서대로 그 회사의 다음 작업을 하나 예약한다. 없으면 None."""
    with _lock:
        sync()
        for scope in scopes:
            for path in waiting(scope, company):
                if not path.exists():   # 앞선 시도에서 받은 최신 상태에 이미 없음
                    continue
                job_id = path.stem
                running = _dir(scope, "running")
                running.mkdir(parents=True, exist_ok=True)
                dst = running / path.name
                claim = running / f"{job_id}.claim.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                git("mv", str(path.relative_to(ROOT)), str(dst.relative_to(ROOT)))
                claim.write_text(json.dumps({"person": person, "company": company,
                                             "claimed_at": now().isoformat()}, ensure_ascii=False),
                                 encoding="utf-8")
                if _commit_and_push(f"예약 {job_id} ({person}·{company})", [path, dst, claim]):
                    return Job(scope, job_id, data)
                # 남이 먼저 가져감 → 다음 작업
        return None


def finish(job: Job, result: dict, meta: dict) -> None:
    """결과와 기록을 올리고 running에서 지운다."""
    with _lock:
        res = _dir(job.scope, "results") / f"{job.job_id}.json"
        log = _dir(job.scope, "logs") / f"{job.job_id}.meta.json"
        for p, d in ((res, result), (log, meta)):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        run = _dir(job.scope, "running")
        _remove_running(run, job.job_id)
        if not _commit_and_push(f"완료 {job.job_id}", [res, log, run / f"{job.job_id}.json",
                                                         run / f"{job.job_id}.claim.json"]):
            raise GitError(f"{job.job_id} 결과를 올리지 못했습니다. 잠시 뒤 `spira start`를 다시 실행하면 이어서 올립니다.")


def fail(job: Job, error: str, meta: dict) -> None:
    """두 번 실패한 작업은 failed로 옮겨 U가 보게 한다."""
    with _lock:
        failed = _dir(job.scope, "failed")
        failed.mkdir(parents=True, exist_ok=True)
        dst = failed / f"{job.job_id}.json"
        err = failed / f"{job.job_id}.error.txt"
        log = _dir(job.scope, "logs") / f"{job.job_id}.meta.json"
        log.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(job.data, ensure_ascii=False, indent=1), encoding="utf-8")
        err.write_text(error, encoding="utf-8")
        log.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        run = _dir(job.scope, "running")
        _remove_running(run, job.job_id)
        _commit_and_push(f"실패 {job.job_id}", [dst, err, log, run / f"{job.job_id}.json",
                                                run / f"{job.job_id}.claim.json"])


def release(job: Job) -> None:
    """중간에 멈췄을 때 작업을 대기열로 돌려놓는다."""
    with _lock:
        run = _dir(job.scope, "running")
        q = _dir(job.scope, "queue") / f"{job.job_id}.json"
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(json.dumps(job.data, ensure_ascii=False, indent=1), encoding="utf-8")
        _remove_running(run, job.job_id)
        _commit_and_push(f"되돌림 {job.job_id}", [q, run / f"{job.job_id}.json", run / f"{job.job_id}.claim.json"])


def requeue_stale(scopes: list[str]) -> list[str]:
    """오래 멈춰 있는 작업(노트북이 꺼진 경우 등)을 대기열로 돌린다."""
    back = []
    with _lock:
        sync()
        for scope in scopes:
            run = _dir(scope, "running")
            for claim in sorted(run.glob("*.claim.json")):
                info = json.loads(claim.read_text(encoding="utf-8"))
                if now() - datetime.fromisoformat(info["claimed_at"]) < STALE_AFTER:
                    continue
                job_id = claim.name.removesuffix(".claim.json")
                job_file = run / f"{job_id}.json"
                if job_file.exists():
                    data = json.loads(job_file.read_text(encoding="utf-8"))
                    release(Job(scope, job_id, data))
                    back.append(job_id)
    return back


def _remove_running(run: Path, job_id: str) -> None:
    for p in (run / f"{job_id}.json", run / f"{job_id}.claim.json"):
        if p.exists():
            p.unlink()


def logs_for(person: str, company: str, day: str) -> list[dict]:
    """그 사람 · 회사가 그날(UTC 날짜 아님, 기록된 local_date) 처리한 작업 기록."""
    out = []
    for p in DATA.glob("*/logs/*.meta.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if m.get("person") == person and m.get("company") == company and m.get("local_date") == day:
            out.append(m)
    return out
