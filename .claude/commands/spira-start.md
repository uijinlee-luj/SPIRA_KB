---
description: Spira 데이터 작업을 시작한다 (숫자 · AI 이름을 붙일 수 있음, 예: /spira-start 20, /spira-start 5 gemini)
---

Spira 지식 베이스 작업을 시작한다.

1. 저장소 루트에서 `uv run spira whoami`를 실행해 이 노트북의 주인을 확인한다. 아직 정해지지 않았으면 멈추고, 사용자에게 `uv run spira whoami <이름>`을 한 번 실행하라고 안내한다.
2. `uv run spira start`를 **백그라운드로** 실행한다. 사용자가 붙인 말을 그대로 넘긴다: `/spira-start 20` → `uv run spira start 20` (계정마다 20개), `/spira-start 5 gemini` → `uv run spira start 5 gemini` (Gemini 계정만 5개). AI 이름은 gemini · codex · claude. 작업이 몇 시간 걸릴 수 있어서 이 대화의 명령 시간 제한에 걸리지 않게 해야 한다.
3. 시작 직후 출력되는 요약(오늘 할 일, 어제 결과, 검수 파일, 토큰 사용)을 사용자에게 그대로 보여 준다.
4. 그 뒤로는 이 대화에서 다른 작업을 하지 않는다. 작업 처리는 `spira start`가 작업마다 새 세션을 열어서 한다.
