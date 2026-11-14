"""`spira` 명령. 노트북에서는 `/spira-start`가 결국 `spira start`를 부른다."""

from __future__ import annotations

from pathlib import Path

import typer

from spira import config

app = typer.Typer(help="SPIRA 지식 베이스 합성 데이터 파이프라인", no_args_is_help=True)
ME_FILE = config.ROOT / ".spira-me"   # 이 노트북의 주인 (U/Y/S/J). git에 올리지 않는다.


@app.command()
def check() -> None:
    """설정 파일이 설계 규칙을 지키는지 검사한다."""
    problems = config.check()
    if problems:
        for p in problems:
            typer.echo(f"✗ {p}")
        raise typer.Exit(1)
    typer.echo("✓ 설정 검사 통과")


@app.command()
def whoami(person: str = typer.Argument(None, help="처음 한 번: U / Y / S / J")) -> None:
    """이 노트북의 주인을 정하거나 확인한다."""
    if person:
        person = person.upper()
        if person not in config.load_nodes():
            typer.echo(f"config/nodes/{person}.yaml이 없습니다.")
            raise typer.Exit(1)
        ME_FILE.write_text(person, encoding="utf-8")
    me = ME_FILE.read_text(encoding="utf-8").strip() if ME_FILE.exists() else None
    if not me:
        typer.echo("아직 정하지 않았습니다. `spira whoami Y`처럼 한 번 실행하세요.")
        raise typer.Exit(1)
    node = config.load_nodes()[me]
    cycles = config.load_cycles()
    typer.echo(f"나는 {me}")
    for a in node["accounts"]:
        active = [c for c in a.get("cycles", []) if config.is_active(cycles[c])]
        label = ", ".join(active) if active else "쉬는 중"
        typer.echo(f"  - {a['company']} ({a['tool']}): 사이클 {label}")


def _me() -> str:
    me = ME_FILE.read_text(encoding="utf-8").strip() if ME_FILE.exists() else ""
    if not me:
        typer.echo("아직 정하지 않았습니다. `spira whoami Y`처럼 한 번 실행하세요.")
        raise typer.Exit(1)
    return me


@app.command()
def start(args: list[str] = typer.Argument(None, help="작업 수 · AI 이름 · 사이클 (모두 비워도 됨). 예: 20 / gemini / A 20 / A gemini 5"),
          max_jobs: int = typer.Option(None, "--max-jobs", hidden=True)) -> None:
    """작업을 가져와 처리한다. `spira start` = 기본 몫만큼, `spira start 20` = 계정마다 20개까지,
    `spira start 5 gemini` = Gemini 계정만 5개 (gemini · codex · claude), `spira start A 20` = 사이클 A 몫만 20개.
    순서는 상관없다.

    1. git pull로 대기열 최신화, 오래 멈춘 작업은 대기열로 되돌림
    2. 내 계정마다 활성 사이클의 대기열에서 작업을 하나씩 예약 (아이템 풀 작업이 먼저)
    3. 작업마다 새 세션으로 에이전트 실행 → 결과 검사 (실패하면 한 번 더)
    4. 결과 · 모델 · 토큰 기록을 data/<사이클>/에 올리고 push
    5. 오늘 할당량(config/nodes/<나>.yaml)을 채우거나 할 일이 없으면 멈춤
    """
    from spira import worker

    problems = config.check()
    if problems:
        for p in problems:
            typer.echo(f"✗ {p}")
        typer.echo("설정 검사를 통과하지 못해 시작하지 않습니다. U에게 알려 주세요.")
        raise typer.Exit(1)
    count, only, cycle = None, None, None
    cycle_names = sorted(config.load_cycles())
    for a in args or []:
        if a.isdigit() and int(a) >= 1:
            count = int(a)
        elif a.lower() in worker.COMPANY_NAME:
            only = a.lower()
        elif a.upper() in cycle_names:
            cycle = a.upper()
        else:
            typer.echo(f"✗ '{a}'를 알아듣지 못했습니다. 숫자(작업 수), gemini · codex · claude, "
                       f"사이클 이름({' · '.join(cycle_names)})만 쓸 수 있습니다.")
            raise typer.Exit(1)
    raise typer.Exit(worker.start(_me(), max_jobs=count or max_jobs, only=only, cycle=cycle, echo=typer.echo))


@app.command("make-pool-jobs")
def make_pool_jobs(push: bool = typer.Option(True, help="만든 뒤 바로 올릴지")) -> None:
    """(U) 아이템 풀 작업을 상품군 × 세 회사만큼 대기열에 넣는다. 프롬프트 버전을 올린 뒤 다시 실행해도 된다."""
    from spira.steps import make_pool_jobs as step

    made, updated, redo = step.run(push=push)
    typer.echo(f"✓ 아이템 풀 작업 ({step.PROMPT_VERSION}): 새로 {made}개 · 버전 변경 {updated}개 · 옛 결과 다시 돌림 {redo}개")


@app.command()
def tick(commit: bool = typer.Option(False, help="바뀐 파일을 main에 올릴지 (Actions에서 켬)")) -> None:
    """(Actions) 할 수 있는 단계를 모두 한 칸씩 진행한다."""
    import os

    from spira import pipeline, queue

    res = pipeline.tick()
    for line in res["log"]:
        typer.echo(f"· {line}")
    if commit and res["changed"]:
        queue.sync()
        ok = queue._commit_and_push("자동 진행: " + " / ".join(res["log"])[:300], res["changed"])
        typer.echo("✓ 올림" if ok else "✗ 올리지 못함 (다음 실행 때 다시)")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"ready_to_load={' '.join(res['ready_to_load'])}\n")
    typer.echo(f"적재 기다림: {', '.join(res['ready_to_load']) or '없음'}")


@app.command()
def load(batch: list[str] = typer.Argument(None, help="비우면 통과한 배치 전부"),
         dry_run: bool = typer.Option(False, "--dry-run", help="DB에 쓰지 않고 미리 보기만"),
         commit: bool = typer.Option(False, help="결과를 main에 올리고 KB 버전 태그를 붙일지 (Actions에서 켬)")) -> None:
    """(Actions) 품질 관문을 통과한 배치를 임베딩해서 DB에 올린다."""
    from spira import batches as B
    from spira import pipeline, queue
    from spira.steps import embed_load

    targets = batch or [b for b in B.all_batches() if B.state(b) == "passed"]
    changed = []
    for b in targets:
        changed += embed_load.load(b, dry_run=dry_run or None)
        typer.echo(f"✓ {b}")
    if commit and changed:
        queue.sync()
        queue._commit_and_push(f"적재: {', '.join(targets)}", changed)
        existing = set(queue.git("tag", "--list").stdout.split())
        for tag in pipeline.versions_to_tag():
            if tag not in existing:
                queue.git("tag", tag)
                queue.git("push", "origin", tag)
                typer.echo(f"✓ 태그 {tag}")


@app.command("confirm-pool")
def confirm_pool() -> None:
    """(U) 아이템 풀을 검토한 뒤 확정한다. 확정해야 사이클이 시작된다."""
    from spira import queue
    from spira.steps import merge_item_pool

    merge_item_pool.confirm()
    queue.sync()
    queue._commit_and_push("아이템 풀 확정", [merge_item_pool.OUT])
    typer.echo("✓ 아이템 풀 확정. 다음 자동 진행 때 사이클이 시작됩니다")


@app.command()
def review() -> None:
    """내 검수 파일을 보여 준다 (review/todo/<배치>_<내이름>.csv)."""
    from spira import queue
    queue.sync()
    me = _me()
    files = sorted((config.ROOT / "review" / "todo").glob(f"*_{me}.csv"))
    if not files:
        typer.echo("지금 검수할 파일이 없습니다.")
        return
    typer.echo("검수할 파일 (엑셀로 열어 '판정' 칸에 O 또는 X, X면 '맞는 의도 id'도 적고 저장):")
    for f in files:
        typer.echo(f"  - {f.relative_to(config.ROOT)}")
    typer.echo("다 했으면 `uv run spira review-done`")


@app.command("review-done")
def review_done() -> None:
    """판정을 다 적은 내 검수 파일을 review/done/으로 옮기고 올린다."""
    import csv as _csv

    from spira import queue
    from spira.checks import _read_csv
    me = _me()
    todo = config.ROOT / "review" / "todo"
    done = config.ROOT / "review" / "done"
    moved, skipped = [], []
    for f in sorted(todo.glob(f"*_{me}.csv")):
        rows = _read_csv(f)
        marks = [next((r[k] for k in r if k and k.startswith("판정")), "").strip().upper() for r in rows]
        if not rows or any(m not in ("O", "X") for m in marks):
            skipped.append(f.name)
            continue
        done.mkdir(parents=True, exist_ok=True)
        dst = done / f.name
        f.replace(dst)
        moved += [f, dst]
    if moved:
        queue.sync()
        queue._commit_and_push(f"검수 완료 ({me})", moved)
        typer.echo(f"✓ {len(moved) // 2}개 파일을 올렸습니다")
    for name in skipped:
        typer.echo(f"✗ {name}: 판정 칸이 비었거나 O/X가 아닌 줄이 있어 옮기지 않았습니다")


@app.command()
def accept(batch: str, reason: str = typer.Option(..., help="통과시키는 이유 (보고서에 남는다)")) -> None:
    """(U) 품질 관문을 통과하지 못한 배치를 그래도 통과시킨다. 기준이 첫 배치 시작값이라 다시 잡을 때 등."""
    from spira import batches as B
    from spira import queue
    if B.state(batch) != "failed":
        typer.echo(f"{batch}는 failed 상태가 아닙니다 ({B.state(batch)})")
        raise typer.Exit(1)
    rep = B.read(batch, "report.json")
    rep["accepted"] = {"by": _me(), "reason": reason, "at": B.now_iso()}
    B.write(batch, "report.json", rep)
    B.set_state(batch, "passed", note=f"U 통과 처리: {reason}")
    queue.sync()
    queue._commit_and_push(f"{batch} 통과 처리", [B.bdir(batch) / "report.json", B.bdir(batch) / "state.json"])
    typer.echo(f"✓ {batch} 통과 처리. 다음 자동 진행 때 적재됩니다")


@app.command("redo-batch")
def redo_batch(batch: str) -> None:
    """(U) 배치를 처음부터 다시 만든다. 프롬프트 · 설정을 고친 뒤에 쓴다. 옛 배치는 discarded_batches/로 옮긴다."""
    import shutil

    from spira import batches as B
    from spira import queue
    from spira.steps import sample_goals
    cycle, _, _ = B.parse(batch)
    src = B.bdir(batch)
    if not src.exists():
        typer.echo(f"{batch}가 없습니다")
        raise typer.Exit(1)
    queue.sync()
    k = 1
    while (dst := queue.DATA / cycle / "discarded_batches" / f"{batch}.{k}").exists():
        k += 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    changed = [src, dst]
    shutil.move(src, dst)
    for kind in ("queue", "running", "results", "failed"):   # 그 배치의 옛 작업 파일
        for f in (queue.DATA / cycle / kind).glob(f"{batch}_*"):
            target = dst / "jobs" / kind / f.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(f, target)
            changed += [f, target]
    for f in (config.ROOT / "review").glob(f"*/{batch}_*.csv"):
        f.unlink()
        changed.append(f)
    changed += sample_goals.start_batch(batch)
    queue._commit_and_push(f"{batch} 다시 만들기", changed)
    typer.echo(f"✓ {batch}를 새로 시작했습니다 (옛 것은 {dst.relative_to(config.ROOT)})")


if __name__ == "__main__":
    app()
