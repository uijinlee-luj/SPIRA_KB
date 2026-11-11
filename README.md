# SPIRA_KB

Synthetic purchase-intent knowledge base for SPIRA — multi-agent pipeline (Gemini · Codex · Claude) that generates, blind-labels, and quality-gates order cases into PostgreSQL + pgvector.

SPIRA 구매 의도 지식 베이스 — Gemini · Codex · Claude 에이전트가 합성 주문 사례를 생성하고 블라인드 라벨을 단 뒤, 품질 관문을 통과한 사례만 PostgreSQL + pgvector에 저장하는 자동화 파이프라인.

메인 저장소: [iejunkimu/SPIRA_AI](https://github.com/iejunkimu/SPIRA_AI) (README의 Knowledge Retrieval 파트)

## 상태

**진행 상황.** 설정 · 목록 · 설정 검사(`spira check`), 프롬프트 v1, 작업 처리기(`spira start`)까지 있다. 코드 단계(①③⑤⑥⑦)는 구현 예정.

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
pip install "spira-kb[embed] @ git+https://github.com/uijinlee-luj/SPIRA_KB"
```

```python
from spira.embedding import basket_text, embed_basket

basket_text(["세제", "딸기", "줄넘기"])   # "딸기, 세제, 줄넘기"  (이름만, 가나다순)
embed_basket(["세제", "딸기", "줄넘기"])  # BGE-M3, 1024차원, L2 정규화
```

목록 세 개(`config/lists/`)의 원본은 이 저장소다 (KB-15). 바뀌면 JSON으로 만들어 SPIRA_AI `contracts/`에 PR로 보낸다 (자동화 예정).

## 처음 한 번 (팀원)

```bash
git clone https://github.com/uijinlee-luj/SPIRA_KB.git
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
- 오늘 몫을 채우거나 할 일이 없으면 멈춘다. Ctrl+C로 멈추면 하던 작업은 대기열로 돌아간다
- 측정 전(`calibration`이 비어 있음)에는 **측정 모드**로 하루 1개만 한다. 시작 전후 한도 화면을 U에게 알려 준다

## 설계 문서 (노션)

- 구매 의도 지식 베이스 설계 (의진)
- 합성 데이터 자동화 시스템 설계 (의진)
  - 팀원 셋업 가이드 · 해야 할 일
