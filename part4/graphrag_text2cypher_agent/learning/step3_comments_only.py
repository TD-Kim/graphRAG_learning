"""
[3단계: 주석만] "질문 유형에 따라 검색 방식을 고르는" LangGraph 워크플로우를 처음부터 설계한다.
graphrag_tool_agent(LLM 이 도구를 고름)를 그래프(코드가 흐름을 고정)로 다시 만드는 과제다.

막힌 곳 메모:
  -
"""

# 1. 그래프를 종이에 먼저 그린다.
#    START -> classify(질문 유형: 구조화 질의 / 의미 검색 / 무관)
#      구조화 -> text2cypher 서브흐름(생성 -> 검증 -> 실행 -> 수정 루프)
#      의미   -> vector_search
#      무관   -> general_answer
#    두 검색 결과 모두 -> answer -> END
#    (선택) text2cypher 가 2번 실패하면 vector_search 로 넘기는 "대체 경로"

# 2. 상태(State)를 정의한다. 입력/출력/내부를 나눈다.
#    question_type, cypher, rows, vector_context, retry_count, error, answer ...

# 3. classify 노드: 구조화 출력(Pydantic, Literal 3개)으로.

# 4. 라우팅 함수들을 쓴다. 모든 순환에 상한을 둔다.

# 5. 테스트 질문 12개(유형별 4개)로 경로를 기록한다. 기대 경로와 다른 질문을 찾아 classify 프롬프트를 고친다.

# 6. LangGraph Studio(langgraph dev)로 열어 단계별 상태를 눈으로 확인한다.
#    .langgraph_api/ 는 .gitignore 에 넣는다.

# ---------- 끝난 뒤 스스로 점검 ----------
# [ ] "LLM 이 흐름을 정하는 에이전트"와 "코드가 흐름을 정하는 워크플로우"의 장단점을 말할 수 있는가?
# [ ] 그래프의 모든 순환에 탈출 조건이 있는가?
