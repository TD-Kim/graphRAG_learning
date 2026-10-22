"""
[3단계: 주석만] Part 3 의 GraphRAG 하나(text2cypher 타이타닉 추천)를 Streamlit 화면에 올린다.
final_chatbot 을 보기 전에 혼자 만들어 보는 연습이다.

막힌 곳 메모:
  -
"""

# 1. 화면 설계를 먼저 그린다.
#    - 사이드바: 연결 상태(Neo4j 연결 성공/실패), 예시 질문 버튼 3개
#    - 본문: 대화
#    - 답변 아래 Expander 2개: "생성된 Cypher", "조회 결과(데이터프레임)"

# 2. 무거운 객체는 한 번만 만든다.
#    - Neo4j 드라이버, GraphRAG 객체를 매 재실행마다 만들면 느리다.
#    - @st.cache_resource 로 감싼 함수에서 만든다. (cache_data 와 차이는?)

# 3. 세션 상태에 저장할 것: 메시지(역할, 내용, cypher, rows)
#    - 재실행 후 Expander 를 다시 그리려면 cypher 와 rows 도 저장해야 한다.

# 4. 질문 처리: rag.search(..., return_context=True) -> answer, cypher, items

# 5. 예시 질문 버튼을 누르면 그 질문으로 바로 처리되게 한다.
#    (힌트: 버튼 클릭 시 session_state 에 pending_question 을 넣고, 본문에서 그것이 있으면 처리)

# 6. 실패 처리: Cypher 실행 오류가 나면 st.error 와 함께 생성된 Cypher 를 보여 준다.

# ---------- 끝난 뒤 스스로 점검 ----------
# [ ] 재실행 모델을 설명하고, 그 때문에 생기는 버그(답변이 사라짐, 드라이버를 매번 만듦)를 2개 말할 수 있는가?
# [ ] cache_resource 와 session_state 의 차이(모든 사용자 공유 vs 사용자별)를 말할 수 있는가?
