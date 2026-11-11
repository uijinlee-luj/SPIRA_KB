"""자동 진행 (`spira tick`). GitHub Actions가 data/ · review/ · config/가 바뀔 때마다, 그리고 30분마다 부른다.

할 수 있는 단계를 모두 한 칸씩 진행하고, 바뀐 파일을 main에 올린다. 몇 번을 불러도 같은 결과가 나온다.

⓪ 아이템 풀 작업 60개가 다 끝나면 합친다 → U가 검토 후 `spira confirm-pool`
① 아이템 풀이 확정되면, 활성 사이클마다 회차를 시작한다 (배치 3개 + 생성 작업)
   - 앞 회차가 모두 사람 검수 단계 이상으로 넘어가면 다음 회차를 시작한다 (적재 전 회차는 최대 2개)
   - 앞 회차 배치 중 품질 관문을 통과하지 못한(failed) 것이 있으면 새 회차를 시작하지 않는다 (U가 고친 뒤 다시)
   - 끝나는 날이 있는 사이클(B)은 남은 날이 min_days_for_new_round보다 적으면 시작하지 않는다 (규칙 (가))
③ 생성이 다 끝난 배치 → 주문 조립 + 라벨 작업
⑤ 라벨이 다 끝난 배치 → 확인용 사례를 틀린 작업은 한 번 다시 돌리고, 아니면 비교
⑥ 비교가 끝난 배치 → 자동 지표 + 검수 파일. 검수가 다 모이면 최종 판정
⑦ 통과한 배치는 `spira load`(무거운 임베딩 단계, 따로 도는 Actions 작업)가 적재한다
"""

from __future__ import annotations

from datetime import date

from spira import batches as B
from spira import config
from spira.steps import assemble_orders, compare_labels, merge_item_pool, quality_gate, sample_goals

DONE_ENOUGH = {"reviewing", "passed", "loaded"}


def tick(today: date | None = None) -> dict:
    today = today or date.today()
    changed: list = []
    log: list[str] = []

    # ⓪ 아이템 풀
    pool = B.item_pool()
    if not pool and merge_item_pool.ready():
        changed += merge_item_pool.run()
        log.append("아이템 풀 합침 → U 검토 기다림 (review/item_pool_review.csv)")
        pool = B.item_pool()
    confirmed = pool.get("status") == "confirmed"

    # ③ ⑤ ⑥ 배치 진행
    for b in B.all_batches():
        st = B.state(b)
        if st == "generating" and assemble_orders.ready(b):
            if not confirmed:
                log.append(f"{b}: 생성 끝, 아이템 풀 확정 기다림")
                continue
            changed += assemble_orders.assemble(b)
            log.append(f"{b}: 주문 조립 · 라벨 작업 만듦")
        elif st == "labeling" and compare_labels.ready(b):
            rerun = compare_labels.rerun_failed_checks(b)
            if rerun:
                changed += rerun
                log.append(f"{b}: 확인용 사례를 틀린 라벨 작업 다시 돌림")
                continue
            changed += compare_labels.compare(b)
            changed += quality_gate.step1(b)
            log.append(f"{b}: 두 라벨 비교 · 자동 지표 · 검수 파일 만듦")
        elif st == "compared":
            changed += quality_gate.step1(b)
            log.append(f"{b}: 자동 지표 · 검수 파일 만듦")
        elif st == "reviewing" and quality_gate.review_done(b):
            changed += quality_gate.step2(b)
            log.append(f"{b}: 품질 관문 판정 → {B.state(b)}")

    # ① 새 회차
    if confirmed:
        cfg = B.pipeline()
        for cycle, c in config.load_cycles().items():
            if not config.is_active(c, today):
                continue
            rs = B.rounds(cycle)
            states = {r: [B.state(b) for b in bs] for r, bs in rs.items()}
            if any("failed" in s for s in states.values()):
                log.append(f"사이클 {cycle}: 통과 못 한 배치가 있어 새 회차를 시작하지 않음")
                continue
            if rs and not all(s in DONE_ENOUGH for s in states[max(rs)]):
                continue
            if sum(1 for s in states.values() if any(x != "loaded" for x in s)) >= 2:
                continue
            ends = c.get("ends_on")
            if ends and (ends - today).days < cfg["min_days_for_new_round"]:
                log.append(f"사이클 {cycle}: 끝나는 날({ends})까지 시간이 모자라 새 회차를 시작하지 않음")
                continue
            n = max(rs) + 1 if rs else 1
            changed += sample_goals.start_round(cycle, n)
            log.append(f"사이클 {cycle}: {n}회차 시작 (배치 {cycle}{n}-1 · 2 · 3)")

    ready_to_load = [b for b in B.all_batches() if B.state(b) == "passed"]
    return {"changed": changed, "log": log, "ready_to_load": ready_to_load}


def versions_to_tag() -> list[str]:
    """회차 n이 끝나면 kb-v{n}. A의 n회차가 모두 적재되고, B의 n회차도 모두 적재됐거나 B에 n회차가 없을 때."""
    out = []
    a = B.rounds("A")
    for n, bs in sorted(a.items()):
        if not all(B.state(b) == "loaded" for b in bs):
            continue
        b_round = B.rounds("B").get(n, [])
        if all(B.state(b) == "loaded" for b in b_round):
            out.append(f"kb-v{n}")
    return out
