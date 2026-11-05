"""[1단계: 읽기] state.py (LangGraph 노드들이 함께 읽고 쓰는 "상태" 의 모양 정의) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
LangGraph 설명은 설치 소스(langgraph 1.1.9, requirements.txt 기준)로 확인했다.

상태(State)란?
  그래프의 노드(함수)들이 돌아가며 들여다보고 고쳐 쓰는 "공용 메모장" 딕셔너리.
    {"query": "기침과 관련된 질병은?", "cypher": "MATCH ...", "db_outputs": [[{...}]], "retry_count": 1, ...}
  노드는 상태 전체를 받아서, 바꾸고 싶은 키만 담은 딕셔너리를 돌려준다 -> LangGraph 가 그 키만 덮어쓴다.

이 파일의 3가지 모양
  InputState  : 밖에서 그래프를 부를 때 넣는 것      graph.invoke({"query": "..."})
  OutputState : 그래프가 끝나고 밖으로 돌려주는 것   -> {"answer": "..."}
  State       : 내부에서 노드들이 쓰는 전체 키 (재시도 횟수 같은 내부 정보 포함)
  main.py 의 StateGraph(State, input_schema=InputState, output_schema=OutputState) 에서 셋이 만난다.

읽는 순서 권장: InputState -> OutputState -> State (각 키가 nodes.py 어느 노드에서 쓰이는지 같이 보기)
실행 위치: 이 파일은 정의만 있어서 실행해도 아무것도 출력하지 않는다. nodes.py, main.py 가 import 해서 쓴다.
"""

# [출처] 표준 라이브러리 typing (타입 힌트 도구 모음)
# Optional[str]: "str 이거나 None" 이라는 뜻의 타입 힌트. 파이썬은 실행할 때 타입 힌트를 검사하지 않는다 (사람과 도구가 읽는 표시)
from typing import Optional
# [출처] 외부 라이브러리 typing_extensions (최신 typing 기능을 옛 파이썬에서도 쓰게 해 주는 패키지. langchain/pydantic 설치 시 같이 깔린다)
# TypedDict: "이 딕셔너리에는 이런 키와 이런 타입의 값이 들어간다" 를 class 문법으로 적는 도구
#   실제로 만들어지는 것은 그냥 dict 다. InputState(query="x") 의 결과는 {"query": "x"} (보통 딕셔너리)
#   [왜] LangGraph 는 이 class 의 키 목록을 읽어 상태의 칸(channel)을 만든다
from typing_extensions import TypedDict


# [이 파일에서 정의] class 이름(TypedDict): 문법. TypedDict 를 물려받은(상속) 새 타입을 만든다
# 그래프 입력 모양: query 하나만. LangGraph 는 입력에서 이 키들만 상태에 넣는다
class InputState(TypedDict):
    # 키 이름: 타입  <- 이 줄 하나가 "query 키에는 str 값" 이라는 선언
    query: str


# 그래프 출력 모양: answer 하나만. graph.invoke(...) 의 반환값이 {"answer": "..."} 로 줄어든다
# (cypher, retry_count 같은 내부 값은 밖에 보이지 않는다. LangGraph Studio 화면의 입력/출력 칸도 이 모양을 따른다)
class OutputState(TypedDict):
    answer: str


# 내부 상태 전체. 노드 함수들의 매개변수 state 가 이 모양이다
# 각 키의 리듀서(합치는 규칙): Annotated[타입, 함수] 로 적으면 그 함수로 "이전 값 + 새 값" 을 합친다
#   (예: langgraph 의 add_messages 는 메시지 리스트를 이어 붙인다. graphrag_tool_agent 의 create_agent 상태가 이 방식)
#   여기처럼 Annotated 가 없으면 LangGraph 는 LastValue 칸을 만든다 = 노드가 돌려준 새 값으로 "덮어쓰기" (소스 확인: graph/state.py _get_channel)
#   -> db_outputs 도 이어 붙지 않고 매번 [이번 결과] 하나짜리 리스트로 바뀐다
# 주의: "= None", "= 0" 같은 기본값은 TypedDict 에서 효과가 없다. 파이썬이 에러 없이 받아 주지만 class 속성으로만 남고,
#       LangGraph 도 TypedDict 기본값을 상태에 채워 주지 않는다 (아직 아무도 안 쓴 키는 노드가 받는 state 딕셔너리에 아예 없다)
#       그래서 nodes.py 는 state["키"] 대신 state.get("retry_count", 0) 처럼 기본값을 직접 준다
class State(TypedDict):
    # 사용자 질문. InputState 의 query 와 이름이 같아서 입력이 이 칸으로 들어온다
    query: Optional[str] = None  # 사용자 질문
    # generate_cypher / correct_cypher 노드가 쓰고, validate / execute / answer 노드가 읽는다
    cypher: Optional[str] = None  # 생성/수정된 Cypher 쿼리
    # execute_cypher 노드가 [결과] 로 쓴다. 결과는 성공이면 list(딕셔너리들), 실패면 str(오류 메시지)
    db_outputs: Optional[list] = None  # DB 조회 결과
    # correct_cypher 노드가 +1. 라우팅 함수가 5 를 넘으면 answer 로 탈출
    retry_count: Optional[int] = 0  # 쿼리 재시도 횟수
    # guardrail 노드가 쓴다. 의료 질문이면 True
    is_db_related: Optional[bool] = None  # DB 관련 질문인지 여부
    # validate_query 노드가 쓴다. 통과면 "" (빈 문자열), 실패면 이유 글
    validation_error: Optional[str] = None  # 쿼리 검증 오류
    # execute_cypher 가 결과 0건이면 True. generate_cypher 가 다시 False 로 되돌린다
    result_empty: Optional[bool] = None  # 조회 결과가 비어있는지
    # 빈 결과 때문에 generate_cypher 를 다시 부른 횟수. 2 번까지
    regenerate_count: Optional[int] = 0  # 빈 결과로 인한 재생성 횟수
    # answer 노드가 쓴다. OutputState 의 answer 와 같은 칸이라 그래프 출력이 된다
    answer: Optional[str] = None  # 최종 답변
