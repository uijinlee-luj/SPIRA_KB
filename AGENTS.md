# 에이전트 안내 (Codex · Antigravity 공통)

이 저장소는 SPIRA 지식 베이스 합성 데이터 파이프라인이다.

## 사용자가 `/spira-start`라고 하면

1. 저장소 루트에서 `uv run spira whoami`를 실행해 이 노트북의 주인을 확인한다. 정해지지 않았으면 멈추고 `uv run spira whoami <이름>`을 한 번 실행하라고 안내한다.
2. `uv run spira start`를 실행한다. 사용자가 붙인 말을 그대로 넘긴다: `/spira-start 20` → `uv run spira start 20` (계정마다 20개), `/spira-start 5 gemini` → `uv run spira start 5 gemini` (Gemini 계정만 5개). 몇 시간 걸릴 수 있으니 명령 시간 제한에 걸리지 않도록 백그라운드로 돌린다.
3. 시작 직후 요약을 사용자에게 그대로 보여 주고, 이 대화에서는 다른 작업을 하지 않는다.

## 하지 말 것

- `spira/`, `prompts/`, `config/cycles/`, `config/lists/`를 고치지 않는다. 바꿀 게 있으면 사용자에게 U에게 말하라고 한다
- 비밀값(DB 접속 주소 등)을 출력하거나 저장소에 쓰지 않는다
- 작업 파일을 직접 만들거나 고치지 않는다. 작업은 `spira start`가 처리한다
