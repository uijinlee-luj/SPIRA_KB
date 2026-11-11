"""⑦ 중복 제거 · 임베딩 · 적재 (설계 3 · 5-6 · 8절). 품질 관문을 통과한(passed) 배치에서 돈다.

- 임베딩: basket_text(items) → BGE-M3 1024차원, L2 정규화 (spira.embedding, 서버와 같은 함수)
- 중복 제거 (KB-07): 같은 의도 + 물건 임베딩 코사인 유사도 0.97 이상이면 하나만 남긴다.
  배치 안끼리 + 이미 DB에 있는 합성 사례와. 물건이 같아도 의도가 다르면 둘 다 남긴다
- kb_version: 회차 n의 배치는 kb-v{n} (kb-v1 = A1 + B1, 설계 7절)
- 저장: DATABASE_URL의 cases 표. 표는 서버의 Alembic이 만든다(KB-04). 칸 종류(jsonb · 배열 · 텍스트)는
  DB에서 읽어서 맞춘다. 표가 없으면 멈추고 알린다
- DATABASE_URL이 없으면 연습 실행: DB에 쓰지 않고 load_preview.json만 남긴다

시험용: SPIRA_FAKE_EMBED=1이면 BGE-M3 대신 이름에서 만든 가짜 벡터를 쓴다.
"""

from __future__ import annotations

import hashlib
import json
import math
import os

from spira import batches as B
from spira.embedding import DIM, MODEL_NAME, basket_text

COLUMNS = ["case_id", "source", "items", "intent_id", "intent_text", "situation", "when", "household",
           "basket_emb", "kb_version"]


def _embed(baskets: list[list[str]]) -> list[list[float]]:
    if os.environ.get("SPIRA_FAKE_EMBED") == "1":
        out = []
        for items in baskets:
            h = hashlib.sha256(basket_text(items).encode()).digest()
            v = [((h[i % 32] + i * 31) % 255) / 255 - 0.5 for i in range(DIM)]
            n = math.sqrt(sum(x * x for x in v))
            out.append([x / n for x in v])
        return out
    from spira.embedding import embed_baskets
    return embed_baskets(baskets)


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def load(batch: str, dry_run: bool | None = None) -> list:
    cfg = B.pipeline()
    _, round_no, _ = B.parse(batch)
    kb_version = f"kb-v{round_no}"
    rows = B.read(batch, "compared.json")["rows"]
    vecs = _embed([r["items"] for r in rows])
    thr = cfg["dedup_similarity"]

    keep, dropped = [], []
    by_intent: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        twin = next((j for j in by_intent.get(r["intent_id"], []) if _cos(vecs[i], vecs[j]) >= thr), None)
        if twin is not None:
            dropped.append({"case_id": r["case_id"], "same_as": rows[twin]["case_id"], "where": "batch"})
            continue
        by_intent.setdefault(r["intent_id"], []).append(i)
        keep.append(i)

    url = os.environ.get("DATABASE_URL")
    dry = (not url) if dry_run is None else dry_run
    if dry:
        preview = {"kb_version": kb_version, "would_load": len(keep), "dropped": dropped, "model": MODEL_NAME,
                   "sample": [rows[i] for i in keep[:3]], "at": B.now_iso()}
        return [B.write(batch, "load_preview.json", preview)]

    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("select column_name, data_type, udt_name from information_schema.columns "
                    "where table_name = 'cases'")
        cols = {c: (dt, udt) for c, dt, udt in cur.fetchall()}
        if not cols:
            raise RuntimeError("DB에 cases 표가 없습니다. 서버 쪽 Alembic 마이그레이션으로 먼저 만들어야 합니다 (KB-04).")
        missing = [c for c in COLUMNS if c not in cols]
        if missing:
            raise RuntimeError(f"cases 표에 칸이 없습니다: {missing}. 서버 팀원과 칸 이름을 맞춰야 합니다 (KB-05).")

        def adapt(col, v):
            dt, udt = cols[col]
            if col == "basket_emb":
                return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
            if v is None:
                return None
            if dt in ("json", "jsonb"):
                return Jsonb(v)
            if dt == "ARRAY":
                return list(v)
            if isinstance(v, (dict, list)):
                return json.dumps(v, ensure_ascii=False)
            return v

        ph = ", ".join("%s::vector" if c == "basket_emb" else "%s" for c in COLUMNS)
        sql = f'insert into cases ({", ".join(chr(34) + c + chr(34) for c in COLUMNS)}) values ({ph})'
        loaded = 0
        for i in keep:
            r = rows[i]
            cur.execute("select 1 from cases where case_id = %s", (r["case_id"],))
            if cur.fetchone():   # 지난번에 중간까지 올린 경우
                continue
            emb = "[" + ",".join(f"{x:.6f}" for x in vecs[i]) + "]"
            cur.execute("select case_id from cases where source = 'synthetic' and intent_id = %s "
                        "and 1 - (basket_emb <=> %s::vector) >= %s limit 1", (r["intent_id"], emb, thr))
            hit = cur.fetchone()
            if hit:
                dropped.append({"case_id": r["case_id"], "same_as": hit[0], "where": "db"})
                continue
            vals = {**r, "basket_emb": vecs[i], "kb_version": kb_version}
            cur.execute(sql, [adapt(c, vals[c]) for c in COLUMNS])
            loaded += cur.rowcount
        conn.commit()
    written = [B.write(batch, "loaded.json", {"kb_version": kb_version, "loaded": loaded, "dropped": dropped,
                                              "model": MODEL_NAME, "at": B.now_iso()})]
    B.set_state(batch, "loaded")
    written.append(B.bdir(batch) / "state.json")
    return written
