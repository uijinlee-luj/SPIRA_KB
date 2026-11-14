# SPIRA_KB

Synthetic purchase-intent knowledge base for SPIRA — multi-agent pipeline (Gemini · Codex · Claude) that generates, blind-labels, and quality-gates order cases into PostgreSQL + pgvector.

SPIRA 구매 의도 지식 베이스 — Gemini · Codex · Claude 에이전트가 합성 주문 사례를 생성하고 블라인드 라벨을 단 뒤, 품질 관문을 통과한 사례만 PostgreSQL + pgvector에 저장하는 자동화 파이프라인.

팀 저장소: [CSE-SPIRA/SPIRA](https://github.com/CSE-SPIRA/SPIRA) (README의 Knowledge Retrieval 파트)

## 상태

**진행 상황.** 설정 · 목록 · 프롬프트, 작업 처리기(`spira start`), 코드 단계 ⓪①③⑤⑥⑦과 자동 진행(`spira tick`, GitHub Actions), 현황판까지 있다.

## 구조

```text
SPIRA_KB/
├─ spira/                 # 코드 (두 사이클 공통)
│  ├─ runner.py           #   spira 명령: check · whoami · start · make-pool-jobs
│  ├─ worker.py           #   spira start 본체: 예약 → 새 세션 실행 → 결과 검사 → 기록
│  ├─ queue.py            #   GitHub 저장소를 대기열로 (queue → running → results)
│  ├─ schemas.py          #   작업 파일 · 결과 파일 양식
│  ├─ validate.py         #   결과 검사 (형식 + 작업과 맞는지)
│  ├─ config.py           #   설정 읽기 + 설계 규칙 검사
│  ├─ embedding.py        #   basket_text · embed_basket (서버와 공동)
│  ├─ steps/              #   코드 단계 ①③⑤⑥⑦ (GitHub Actions에서 실행)
│  └─ agents/             #   AI별 실행 방법: claude · codex · gemini
├─ prompts/               # 생성 · 라벨 프롬프트 (공통, 커밋 기록 = 수정 이력)
├─ config/
│  ├─ cycles/A.yaml       # 사이클 A (계속): Y=Gemini, J=Codex, S=Claude + 모델
│  ├─ cycles/B.yaml       # 사이클 B (~11/18): U=Gemini, Y=Codex, J=Claude
│  ├─ nodes/              # 사람별 계정과 낼 몫: U · Y · S · J
│  └─ lists/              # 의도 · 캘린더 태그 · 가구 유형 · 아이템 풀 상품군
├─ checks/                # 확인용 사례 (U가 정답을 단 20개)
├─ data/pool/             # 아이템 풀 작업 (처음 한 번)
├─ data/A/ · data/B/      # 사이클별 queue · running · results · logs · failed
├─ review/todo · done/    # 사람 검수 파일 (사람 기준이라 공통)
├─ .claude/commands/      # Claude Code의 /spira-start
└─ AGENTS.md              # Codex · Antigravity용 /spira-start 안내
```

- 코드와 프롬프트는 사이클별로 나누지 않는다. 나누면 A와 B가 다른 규칙으로 데이터를 만들게 된다
- 누가 어떤 AI로 무슨 역할을 하는지는 `config/cycles/`에서 본다
- 코드 폴더 이름은 `code/`가 아니라 `spira/`다. `code`는 파이썬 기본 모듈 이름과 겹친다

## 이름 규칙

| 무엇 | 규칙 | 예시 |
| --- | --- | --- |
| 배치 (조각) | `{사이클}{회차}-{조각}` | `A1-1` · `A1-2` · `A1-3` · `A2-1` … |
| 사례 id | `syn_{배치}_{번호4자리}` | `syn_A2-3_0042` |
| KB 버전 | 회차 한 바퀴 = 한 판. 같은 회차의 A·B가 모두 관문을 통과하면 끊는다 (11/18 이후는 A 회차만). `kb_version` 칸 + 같은 이름의 GitHub 태그 | `kb-v1` = A1 + B1, `kb-v2` = + A2 + B2 |
| 서버용 조회 전용 DB 계정 | `kb_reader` | |

## 서버에서 쓰는 법 (KB-16)

```bash
pip install "spira-kb[embed] @ git+https://github.com/CSE-SPIRA/SPIRA_KB"
```

```python
from spira.embedding import basket_text, embed_basket

basket_text(["세제", "딸기", "줄넘기"])   # "딸기, 세제, 줄넘기"  (이름만, 가나다순)
embed_basket(["세제", "딸기", "줄넘기"])  # BGE-M3, 1024차원, L2 정규화
```

목록 세 개(`config/lists/`)의 원본은 이 저장소다 (KB-15). 바뀌면 JSON으로 만들어 팀 저장소 SPIRA `contracts/`에 PR로 보낸다 (자동화 예정).

## 처음 한 번 (팀원)

```bash
git clone https://github.com/CSE-SPIRA/SPIRA_KB.git
cd SPIRA_KB
uv sync                 # uv가 없으면: https://docs.astral.sh/uv/
uv run spira whoami Y   # 내 이름 (U / Y / S / J)
uv run spira check      # 설정 검사
```

그다음 `config/nodes/내이름.yaml`에 이번 주에 낼 몫을 적는다. 자세한 셋업은 노션 「팀원 셋업 가이드 · 해야 할 일」.

## 매일

에이전트 창(Claude Code · Codex · Antigravity 중 아무거나)에서 `/spira-start`. 터미널에서 `uv run spira start`를 직접 쳐도 같다.

- 내 계정마다 대기열에서 작업을 하나씩 가져와, 작업마다 새 세션으로 AI를 실행한다 (작업 폴더: `~/.spira-work/`, 저장소 밖)
- 결과가 양식에 맞지 않으면 새 세션으로 한 번 더 하고, 또 실패하면 `data/*/failed/`로 보낸다
- 결과 · 실제 모델 · 토큰 · 걸린 시간은 `data/*/results/` · `data/*/logs/`에 올라간다
- 몫은 `config/nodes/내이름.yaml`의 `weekly_share_percent`(주간 한도 중 낼 %). AI 도구가 알려 주는 남은 한도 %를 작업 전후로 자동으로 읽어서, 이번 주 몫을 남은 날에 나눠 채운다. 팀원이 재거나 적을 것은 없다
- 5시간 한도가 거의 차면 다시 찰 때까지 기다렸다가 이어서 한다. 주간 한도가 5% 남으면 멈춘다
- 한도 %를 읽을 수 없는 도구는 하루 `jobs_per_day`개(기본 10)로 센다
- 할 일이 없으면 멈춘다. Ctrl+C로 멈추면 하던 작업은 대기열로 돌아간다

## 자동 진행 (GitHub Actions)

결과가 올라올 때마다, 그리고 30분마다 `pipeline` 워크플로가 `spira tick`으로 한 칸씩 진행한다.

| 단계 | 언제 | 무엇을 |
| --- | --- | --- |
| ⓪ 아이템 풀 합치기 | 아이템 풀 작업 60개가 다 끝나면 | `config/lists/item_pool.yaml`(draft) + `review/item_pool_review.csv` |
| ① 회차 시작 | 아이템 풀이 확정되고, 앞 회차가 검수 단계까지 가면 | 배치 3개 + 생성 작업 (조각당 약 11개) |
| ③ 주문 조립 | 배치의 생성 작업이 다 끝나면 | 사례 1천 개 + 라벨 작업 40개 (확인용 사례 3개씩) |
| ⑤ 비교 | 라벨 작업이 다 끝나면 | 확인용 사례를 틀린 작업은 한 번 다시, 아니면 두 라벨 비교 |
| ⑥ 품질 관문 | 비교가 끝나면 → 검수가 다 모이면 | 자동 지표 + 검수 30개(4명에게 나눔) → passed / failed |
| ⑦ 적재 | 통과하면 | 중복 제거(0.97) + BGE-M3 임베딩 + Neon `cases` 표, 회차가 끝나면 `kb-vN` 태그 |

숫자(비율 · 기준)는 `config/pipeline.yaml`. 배치 기록은 `data/<사이클>/batches/<배치>/`(보고서는 `report.md`).

## U가 하는 일

```bash
uv run spira confirm-pool          # 아이템 풀 검토 뒤 확정 (확정해야 사이클이 시작된다)
uv run spira accept B1-1 --reason "…"   # 관문을 못 넘었지만 통과시킬 때 (첫 배치 기준 재조정 등)
uv run spira redo-batch B1-1       # 프롬프트 · 설정을 고친 뒤 배치를 처음부터 다시
```

## 검수 (4명)

```bash
uv run spira review        # 내 검수 파일 보기 → 엑셀로 열어 '판정'에 O/X
uv run spira review-done   # 다 적은 파일을 올리기
```

## 설계 문서 (노션)

- 구매 의도 지식 베이스 설계 (의진)
- 합성 데이터 자동화 시스템 설계 (의진)
  - 팀원 셋업 가이드 · 해야 할 일
