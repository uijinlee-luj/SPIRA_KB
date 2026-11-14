"""임베딩 함수 — 지식 베이스와 서버가 같이 쓴다 (KB-02, KB-16).

서버는 이 파일을 그대로 가져다 쓴다:

    pip install "spira-kb[embed] @ git+https://github.com/CSE-SPIRA/SPIRA_KB"

    from spira.embedding import basket_text, embed_basket

같은 주문은 KB와 서버에서 반드시 같은 벡터가 나와야 한다. 그래서 문자열 규칙과
모델(이름 · 버전)을 이 파일 한 곳에서만 정한다. 바꿀 때는 KB 버전을 새로 끊고 서버에 알린다.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

MODEL_NAME = "BAAI/bge-m3"
# TODO(첫 적재 전): Hugging Face 모델 커밋 해시로 고정해서 양쪽이 같은 가중치를 쓰게 한다.
MODEL_REVISION: str | None = None
DIM = 1024


def basket_text(items: Sequence[str]) -> str:
    """물건 이름만 가나다순으로 정렬해 ", "로 잇는다.

    수량 · 속성은 넣지 않는다 (서버와 합의: 이름만 사용). 앞뒤 공백과 빈 이름은 버린다.

    >>> basket_text(["세제", "딸기", "줄넘기"])
    '딸기, 세제, 줄넘기'
    """
    names = sorted(name.strip() for name in items if name and name.strip())
    return ", ".join(names)


@lru_cache(maxsize=1)
def _model():
    from FlagEmbedding import BGEM3FlagModel  # [embed] 묶음에 들어 있다

    return BGEM3FlagModel(MODEL_NAME, revision=MODEL_REVISION, use_fp16=False)


def embed_basket(items: Sequence[str]) -> list[float]:
    """basket_text를 BGE-M3로 임베딩한다. 1024차원, L2 정규화된 dense 벡터."""
    return embed_baskets([items])[0]


def embed_baskets(baskets: Sequence[Sequence[str]]) -> list[list[float]]:
    """여러 주문을 한 번에 임베딩한다 (적재할 때 사용)."""
    texts = [basket_text(b) for b in baskets]
    out = _model().encode(texts, return_dense=True, return_sparse=False, return_colbert_vecs=False)
    vectors = out["dense_vecs"]
    result: list[list[float]] = []
    for v in vectors:
        norm = sum(float(x) * float(x) for x in v) ** 0.5 or 1.0
        result.append([float(x) / norm for x in v])
    return result
