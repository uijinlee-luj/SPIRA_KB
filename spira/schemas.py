"""작업 파일 · 결과 파일 형식 (v1 초안).

에이전트는 작업 파일(JSON)을 읽고 결과 파일(JSON)을 쓴다. 코드 단계는 결과를 이 형식으로 검사한다.
작업 하나 = 사례 50개 (+ 라벨 작업은 확인용 사례 3개를 섞어 53개).

이름 규칙: 작업 id = {배치}_{역할}_{번호3자리}  예) A1-2_label1_007
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Company = Literal["gemini", "codex", "claude"]
Role = Literal["item_pool", "generate", "label_1", "label_2"]


# ---------------------------------------------------------------- 공통

class IntentRef(BaseModel):
    """에이전트에게 보여 주는 의도 하나 (목록에서 그대로 복사)."""

    id: str
    name: str
    definition: str


class JobHeader(BaseModel):
    job_id: str
    batch: str                 # 예) A1-2
    role: Role
    company: Company
    prompt_version: str        # 예) generate_bundle@v1


# ---------------------------------------------------------------- 아이템 풀 (처음 한 번)

class ItemPoolJob(JobHeader):
    role: Literal["item_pool"] = "item_pool"
    category: str              # 예) 과일·채소, 세제·청소용품
    target_count: int = Field(ge=20, le=300)


class PoolItem(BaseModel):
    name: str                  # 단순한 일반 이름 (예: 딸기, 세제, 줄넘기)
    everyday: bool             # 평소 장보기 물건이면 true


class ItemPoolResult(BaseModel):
    job_id: str
    items: list[PoolItem]


# ---------------------------------------------------------------- ② 물건 묶음 생성

class Goal(BaseModel):
    goal_id: str               # 코드가 매김. 예) A1-2_g0042
    intent: IntentRef
    household_types: list[str] # 4-4 조건을 통과한 가구 (생성할 때만 보여 줌)


class GenerateJob(JobHeader):
    role: Literal["generate"] = "generate"
    goals: list[Goal]


class Bundle(BaseModel):
    goal_id: str
    items: list[str] = Field(min_length=2, max_length=6)


class GenerateResult(BaseModel):
    job_id: str
    bundles: list[Bundle]


# ---------------------------------------------------------------- ④ 블라인드 라벨

class CalendarEvent(BaseModel):
    tag: str                   # 캘린더 태그 30개 중 하나
    days_from_arrival: int     # 도착일 기준 며칠 뒤 (-1 ~ 14)
    weekday: str               # 예) 토


class LabelCase(BaseModel):
    """라벨러가 보는 사례. 서버 ③ 단계가 받는 수준만 담는다 (만들 때의 의도는 절대 넣지 않음)."""

    case_ref: str              # 무작위 id. 확인용 사례인지 알 수 없게 한다
    items: list[str]
    household_types: list[str] | None   # 숨긴 경우 null
    arrival_weekday: str
    calendar: list[CalendarEvent]


class LabelJob(JobHeader):
    role: Literal["label_1", "label_2"]
    intents: list[IntentRef]   # 의도 30개 전체 (none · unclassified 설명은 프롬프트에)
    cases: list[LabelCase]


class Situation(BaseModel):
    event: str | None = None     # 무슨 일인지 (캘린더 태그 단어가 맞으면 그 단어)
    guests: str | None = None    # 누가 오는지
    activity: str | None = None  # 무엇을 하는지
    theme: str | None = None     # 분위기 · 주제


class IntentAnswer(BaseModel):
    intent_id: str               # 목록의 id 또는 unclassified
    intent_text: str             # 한 문장
    bundle_items: list[str]      # 이 의도에 속하는 주문 물건 (주문에 있는 이름 그대로)


class CaseLabel(BaseModel):
    case_ref: str
    intents: list[IntentAnswer] = Field(max_length=2)   # 빈 목록 = 의도 없음(none)
    situation: Situation = Situation()
    alternatives: list[str] = []  # 대안 의도 id (정답을 바꾸지 않는 기록)

    @field_validator("alternatives")
    @classmethod
    def _no_dup(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


class LabelResult(BaseModel):
    job_id: str
    labels: list[CaseLabel]
