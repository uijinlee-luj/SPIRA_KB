"""코드 단계 (GitHub Actions에서 실행). 한 사이클의 흐름:

  ① sample_goals     목적 · 가구 뽑기
  ② (에이전트)        물건 묶음 생성
  ③ assemble_orders  주문 조립 · 평소 장보기 추가 · 맥락 붙이기
  ④ (에이전트)        블라인드 라벨 2개
  ⑤ compare_labels   두 라벨 비교 · 형식 검사 · 확인용 사례 채점 · 중복 제거
  ⑥ quality_gate     품질 관문 (1천 개마다) + 사람 검수 파일
  ⑦ embed_load       주문 목록만 임베딩 → PostgreSQL + pgvector

각 단계의 규칙은 노션 「구매 의도 지식 베이스 설계」 5~7절을 따른다.
"""
