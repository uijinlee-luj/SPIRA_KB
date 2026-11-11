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
def start(max_jobs: int = typer.Option(None, "--max-jobs", help="이번 실행에서 계정마다 최대 몇 개 (시험용)")) -> None:
    """오늘 할당량만큼 작업을 가져와 처리한다. (`/spira-start`가 부르는 명령)

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
    raise typer.Exit(worker.start(_me(), max_jobs=max_jobs, echo=typer.echo))


@app.command("make-pool-jobs")
def make_pool_jobs(push: bool = typer.Option(True, help="만든 뒤 바로 올릴지")) -> None:
    """(U) 아이템 풀 작업을 상품군 × 세 회사만큼 대기열에 넣는다. 프롬프트 버전을 올린 뒤 다시 실행해도 된다."""
    from spira.steps import make_pool_jobs as step

    made, updated, redo = step.run(push=push)
    typer.echo(f"✓ 아이템 풀 작업 ({step.PROMPT_VERSION}): 새로 {made}개 · 버전 변경 {updated}개 · 옛 결과 다시 돌림 {redo}개")


if __name__ == "__main__":
    app()
