"""⑦ 임베딩 · 적재 (설계 3 · 8절).

- 임베딩 문자열: basket_text(items) = 상품 이름만 가나다순 정렬 후 ", "로 잇기 (서버와 공동)
- 모델: BGE-M3, 1024차원, L2 정규화
- 저장: PostgreSQL + pgvector의 cases 표 (텍스트 칸 전부 + basket_emb)
  접속 주소는 환경 변수 DATABASE_URL (Actions 비밀값)
- 원본(텍스트만)은 data/<사이클>/batches/에 남긴다
- 사례 id: syn_{배치}_{번호4자리}  예) syn_A2-3_0042 (사이클 A 2회차 조각 3의 42번째)
- kb_version: 평가용으로 끊을 때마다 kb-v1, kb-v2 … (같은 이름의 GitHub 태그) (KB-11, KB-13)
"""


from spira.embedding import basket_text, embed_baskets  # noqa: F401  (서버와 같은 함수)


def run(cycle: str, slice_id: str) -> None:
    raise NotImplementedError
