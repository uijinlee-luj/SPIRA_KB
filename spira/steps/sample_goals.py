"""① 목적 · 가구 뽑기 (설계 5-1절).

- 의도 목록에서 빈도 가중치(흔함 ×3 · 보통 ×2 · 드묾 ×1)로 목적을 뽑는다
- 4-3 조합 규칙과 4-4 의도 조건을 통과하는 가구 조합을 함께 뽑는다
- 결과를 data/<사이클>/queue/의 생성 작업으로 넣는다 (조각별 생성 회사 기준)
- 시드를 고정해서 같은 배치를 다시 만들 수 있게 한다
"""


def run(cycle: str, slice_id: str, seed: int) -> None:
    raise NotImplementedError
