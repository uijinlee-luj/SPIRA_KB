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


@app.command()
def start() -> None:
    """오늘 할당량만큼 작업을 가져와 처리한다. (구현 예정)

    순서:
      1. git pull로 대기열 최신화
      2. 내 계정별로 활성 사이클의 대기열(data/<사이클>/queue/)에서 작업을 하나씩 예약
      3. 작업마다 새 세션으로 에이전트 실행 (spira.agents)
      4. 결과와 토큰 사용량을 data/<사이클>/batches/에 쓰고 push
      5. 할당량(config/nodes/<나>.yaml)을 채우면 요약을 남기고 멈춤
    """
    typer.echo("아직 구현 전입니다. (뼈대 단계)")
    raise typer.Exit(2)


if __name__ == "__main__":
    app()
