"""[1단계: 읽기] main.py (노드 6개와 엣지를 이어 LangGraph 그래프를 조립하고 그림으로 저장) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
LangGraph 설명은 설치 소스(langgraph 1.1.9, langchain-core 1.3.0, requirements.txt 기준)로 확인했다.

LangGraph 그래프 만드는 4단계
  1) builder = StateGraph(상태모양)                 빈 설계도
  2) builder.add_node("이름", 함수)                 상자(노드) 추가
  3) builder.add_edge(A, B)                         A 다음엔 무조건 B
     builder.add_conditional_edges(A, 라우팅함수, {반환값: 노드})   A 다음엔 함수가 고른 곳
  4) graph = builder.compile()                      실행할 수 있는 그래프 (CompiledStateGraph)
  그 뒤 graph.invoke({"query": "..."}) 로 실행 -> {"answer": "..."}

이 파일의 그래프 (GUIDE.md 그림과 같다)
  START -> guardrail -> (generate_cypher | answer)
  generate_cypher -> validate_query -> (execute_cypher | correct_cypher | answer)
  correct_cypher  -> validate_query
  execute_cypher  -> (generate_cypher | correct_cypher | answer)
  answer -> END

실행 방법 2가지
  - 질의: langgraph dev (LangGraph Studio). langgraph.json 의 "agent": "./main.py:graph" 가 아래 전역 graph 변수를 가리킨다
          또는 파이썬에서 from main import graph; graph.invoke({"query": "기침과 관련된 질병은?"})
  - 그림만: part4/graphrag_text2cypher_agent 에서  PYTHONPATH=. python learning/step1_main_annotated.py
          (nodes.py 를 import 하므로 DB 접속과 .env 가 필요하다. 질의는 하지 않는다)
          주의: 현재 폴더에 graph_visualization.png 를 새로 써서 원래 그림을 덮어쓴다.
                그림 변환은 기본으로 인터넷의 mermaid.ink 서버를 쓴다 (소스 확인: draw_mermaid_png 기본 draw_method=API)

읽는 순서 권장: create_agent_graph (add_node -> add_edge -> add_conditional_edges -> compile) -> 맨 아래 __main__
"""

# [출처] 외부 라이브러리 langgraph
# StateGraph: 상태 딕셔너리를 노드들이 돌려 가며 고치는 그래프의 설계도 클래스
# START, END: 시작과 끝을 뜻하는 특별한 노드 이름 (값은 "__start__", "__end__" 글)
from langgraph.graph import StateGraph, START, END

# [출처] 같은 폴더의 state.py. 상태 모양 3개
from state import State, InputState, OutputState
# [출처] 같은 폴더의 nodes.py. 이 import 순간 nodes.py 가 DB 에 접속하고 스키마를 읽는다
# from 모듈 import ( ... ): 괄호로 감싸면 여러 줄에 나눠 적을 수 있다
from nodes import (
    guardrail_node,
    validate_query_node,
    generate_cypher_node,
    execute_cypher_node,
    correct_cypher_node,
    answer_node,
    route_guardrail,
    route_validation,
    route_execution,
)


# ============================================
# 그래프 생성 함수
# ============================================

# [이 파일에서 정의] 그래프를 조립해 컴파일된 그래프를 돌려준다 [반환] CompiledStateGraph
def create_agent_graph():
    """Text2Cypher Agent 그래프 생성"""

    # StateGraph 초기화
    # StateGraph(State, input_schema=InputState, output_schema=OutputState)
    # [출처] 외부 라이브러리 langgraph
    # [입력] 첫 인자: 내부 상태 모양 (TypedDict). 키마다 칸(channel)을 만든다. Annotated 리듀서가 없으면 덮어쓰기 칸
    #        input_schema: invoke 에 넣을 수 있는 키 (query 만)
    #        output_schema: invoke 가 돌려줄 키 (answer 만)
    #        (1.x 이름이다. 옛 이름 input=, output= 은 경고를 내며 아직 받는다. 소스 확인)
    # [반환] 빌더 객체. 노드와 엣지를 추가한 뒤 compile() 한다
    graph_builder = StateGraph(State, input_schema=InputState, output_schema=OutputState)

    # 노드 추가
    # builder.add_node("이름", 함수)
    # [출처] 외부 라이브러리 langgraph
    # [입력] 노드 이름(글), 노드 함수 (state 를 받아 바꿀 키 딕셔너리를 돌려주는 함수)
    # [왜] 이름은 엣지와 라우팅 함수의 반환값에서 이 노드를 가리킬 때 쓴다. 함수 이름과 달라도 된다
    graph_builder.add_node("guardrail", guardrail_node)
    graph_builder.add_node("validate_query", validate_query_node)
    graph_builder.add_node("generate_cypher", generate_cypher_node)
    graph_builder.add_node("execute_cypher", execute_cypher_node)
    graph_builder.add_node("correct_cypher", correct_cypher_node)
    graph_builder.add_node("answer", answer_node)

    # 엣지 연결
    # builder.add_edge(출발, 도착)
    # [출처] 외부 라이브러리 langgraph
    # [입력] 출발 노드 이름, 도착 노드 이름. 출발이 끝나면 조건 없이 항상 도착으로 간다
    # START -> guardrail: 그래프가 시작하면 처음 실행할 노드
    graph_builder.add_edge(START, "guardrail")
    # 생성과 수정 다음은 항상 검증. 그래서 "수정 -> 검증 -> 수정 ..." 순환이 생긴다 (상한은 nodes.py 의 retry_count)
    graph_builder.add_edge("generate_cypher", "validate_query")
    graph_builder.add_edge("correct_cypher", "validate_query")
    # answer 다음은 끝. 끝나면 output_schema 의 키(answer)만 돌려준다
    graph_builder.add_edge("answer", END)

    # 조건부 엣지 연결
    # 1. Guardrail: DB 관련 질문인지 확인
    # builder.add_conditional_edges(출발, 라우팅함수, path_map)
    # [출처] 외부 라이브러리 langgraph
    # [입력] 출발: 이 노드가 끝난 뒤에 판단한다
    #        라우팅함수: 상태를 받아 "어디로 갈지" 글을 돌려주는 함수 (nodes.py 의 route_guardrail)
    #        path_map: {라우팅함수가 돌려준 값: 실제 노드 이름}. 여기서는 이름이 같아서 {"a": "a"} 꼴
    # [왜] path_map(또는 반환 타입 Literal)이 있어야 그래프 그림에 갈 수 있는 화살표만 그려진다.
    #      없으면 모든 노드로 갈 수 있다고 그린다 (소스의 docstring 경고)
    # 분기 판단이 프롬프트(LLM)가 아니라 이 코드(라우팅 함수)에 있다 -> 흐름이 예측 가능하다
    graph_builder.add_conditional_edges(
        "guardrail",
        route_guardrail,
        {"generate_cypher": "generate_cypher", "answer": "answer"},
    )

    # 2. Validation: 쿼리 검증
    # 검증 다음: 통과 -> 실행, 실패 -> 수정, 재시도 초과 -> 답변
    graph_builder.add_conditional_edges(
        "validate_query",
        route_validation,
        {
            "execute_cypher": "execute_cypher",
            "correct_cypher": "correct_cypher",
            "answer": "answer",  # 재시도 제한 초과
        },
    )

    # 3. Execution: 실행 결과에 따라 라우팅
    # 실행 다음: 빈 결과 -> 재생성, 오류 -> 수정, 정상 또는 상한 초과 -> 답변
    graph_builder.add_conditional_edges(
        "execute_cypher",
        route_execution,
        {
            "generate_cypher": "generate_cypher",  # 빈 결과 → 재생성
            "correct_cypher": "correct_cypher",     # 에러 → 수정
            "answer": "answer",                     # 정상 or 제한 초과
        },
    )

    # 그래프 컴파일
    # builder.compile()
    # [출처] 외부 라이브러리 langgraph
    # [반환] CompiledStateGraph. .invoke(입력), .stream(입력), .get_graph() 를 쓸 수 있다
    # compile 할 때 노드/엣지가 맞는지 검사한다 (없는 노드 이름을 가리키면 여기서 에러)
    # checkpointer 를 안 넘겼으므로 invoke 할 때마다 상태가 새로 시작한다 (대화 기억 없음. langgraph dev 로 띄우면 서버가 따로 상태를 저장한다. GUIDE 의 .langgraph_api 파일)
    graph = graph_builder.compile()

    return graph


# [이 파일에서 정의] 감싸기 함수. 같은 일을 하는 다른 이름 (langgraph.json 이나 다른 코드에서 부르기 쉬우라고)
def create_graph():
    return create_agent_graph()

# 모듈 전역 graph: import 될 때 한 번 만들어진다. langgraph.json 의 "./main.py:graph" 가 이 변수 이름을 가리킨다
graph = create_graph()


# if __name__ == "__main__": 이 파일을 직접 실행할 때만 아래 블록 실행 (import 될 때는 실행 안 됨)
# 주의: 바로 위 80줄에서 이미 graph 를 만들었는데 한 번 더 만든다 (무해하지만 중복)
if __name__ == "__main__":
    graph = create_graph()

    # try/except: 그림 저장이 실패해도(인터넷 없음 등) 프로그램이 에러로 끝나지 않게
    try:
        # graph.get_graph(): [출처] langgraph. 노드/엣지 구조를 그림용 Graph 객체로 [반환] langchain_core 의 Graph
        # .draw_mermaid_png(): [출처] langchain-core. Mermaid 그림 문법으로 바꾼 뒤 PNG 바이트를 돌려준다 (기본: mermaid.ink 웹 서비스 사용)
        png_data = graph.get_graph().draw_mermaid_png()
        output_file = "graph_visualization.png"

        # open(파일, "wb"): w = 쓰기(있으면 덮어씀), b = 바이너리(바이트). PNG 는 글이 아니라 바이트라 "wb"
        # with 블록이 끝나면 파일이 자동으로 닫힌다
        with open(output_file, "wb") as f:
            f.write(png_data)

        print(f"✓ 그래프 시각화 저장: {output_file}\n")
    # except Exception as e: 에러를 e 로 받아 메시지만 출력
    except Exception as e:
        print(f"그래프 시각화 중 오류 발생: {e}")
        # import traceback: [출처] 표준 라이브러리. 함수 안(블록 안)에서도 import 할 수 있다
        # traceback.print_exc(): 에러가 난 위치(호출 경로)를 자세히 출력
        import traceback
        traceback.print_exc()
