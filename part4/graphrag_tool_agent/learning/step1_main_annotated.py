"""[1단계: 읽기] main.py (create_agent 로 도구 에이전트를 만들고, 대화형으로 질문받아 노드별 진행을 스트리밍 출력) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
LangChain/LangGraph 설명은 설치 소스(langchain 1.2.15, langchain-core 1.3.0, langgraph 1.1.9, requirements.txt 기준)로 확인했다.

create_agent 가 만드는 그래프 (소스 확인: langchain/agents/factory.py)
  START -> "model" 노드 : 시스템 프롬프트 + 대화 메시지를 LLM 에 보낸다. LLM 이 답(AIMessage)을 낸다
            AIMessage 에 tool_calls (도구 호출 요청)가 있으면 -> "tools" 노드 : 도구를 실행해 ToolMessage 를 만든다 -> 다시 "model"
            tool_calls 가 없으면 -> END (그 AIMessage 가 최종 답)
  상태는 {"messages": [...]} 하나. messages 키는 Annotated[list, add_messages] 리듀서라
  노드가 돌려준 메시지가 "덮어쓰기" 가 아니라 "뒤에 이어 붙기" 가 된다.
  graphrag_text2cypher_agent 는 이 순서를 코드(엣지)로 고정했고, 여기서는 LLM 이 매번 다음 도구를 스스로 고른다.

한 번의 질문에서 오가는 메시지 예시
  HumanMessage("OpenAI 의 CEO 는?")
  AIMessage(tool_calls=[schema_introspection])       <- model 노드
  ToolMessage("=== Neo4j 그래프 스키마 ===...")      <- tools 노드
  AIMessage(tool_calls=[generate_cypher_query(...)])
  ToolMessage("MATCH (c:Company) ...")
  AIMessage(tool_calls=[execute_cypher_query(...)])
  ToolMessage("=== 쿼리 실행 결과 === ...")
  AIMessage("OpenAI 의 CEO 는 ... 입니다")            <- tool_calls 없음 -> 끝

읽는 순서 권장: create_graphrag_agent (시스템 프롬프트, create_agent) -> run_agent_interactive (stream 루프) -> main
실행 위치: part4/graphrag_tool_agent 에서  PYTHONPATH=. python learning/step1_main_annotated.py
  (같은 폴더의 tools.py 를 import 하므로 PYTHONPATH=. 가 필요하다. 주석본은 import 용으로 쓰지 않는다)
  실행하면 현재 폴더의 tool_agent.png 를 새로 써서 덮어쓰고(그림 변환에 mermaid.ink 웹 서비스 사용), 질문 입력을 기다린다. exit / quit / q 로 끝
전제: tools.py 와 같다 (pdf2kg 그래프 + text_content_vector_index, .env 에 NEO4J_*, OPENAI_API_KEY)
"""

# [출처] 표준 라이브러리. os.environ.get
import os
# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 langchain (1.x)
# create_agent: "LLM + 도구 반복 호출" 그래프를 만들어 주는 함수. 결과는 LangGraph 의 CompiledStateGraph
from langchain.agents import create_agent
# [출처] 같은 폴더의 tools.py. 도구 목록과 공용 자원 초기화 함수
from tools import get_all_tools, initialize_tools

load_dotenv()


# [이 파일에서 정의] 도구 준비 -> 시스템 프롬프트 -> create_agent [반환] 에이전트 (CompiledStateGraph)
def create_graphrag_agent():
    # 드라이버/LLM/임베더/검색기를 먼저 만든다 (DB 에 접속해 벡터 인덱스 정보도 확인한다)
    initialize_tools()

    tools = get_all_tools()
    print(f"✓ 총 {len(tools)}개의 도구 등록:")
    # tool.name: 함수 이름 / tool.description: @tool(parse_docstring=True) 가 docstring 앞 덩어리에서 뽑은 설명
    # .split('.')[0]: 첫 마침표 앞까지만 = 첫 문장
    for tool in tools:
        print(f"  - {tool.name}: {tool.description.split('.')[0]}...")

    # 시스템 프롬프트: 두 워크플로우(Text2Cypher 3단계, Vector Search)를 "언제 쓰는지" 와 함께 설명한다
    # 도구 각각의 설명은 LLM 이 tools 정의로 따로 받는다. 여기서는 도구들 사이의 "순서와 선택 기준" 을 알려 준다
    # <Text2Cypher 워크플로우> 같은 태그는 구역 구분용 관례 (특별한 문법이 아니다)
    system_prompt = """당신은 Neo4j 기반 그래프 데이터베이스를 활용하는 GraphRAG 전문 AI 어시스턴트입니다.

<Text2Cypher 워크플로우>
**Text2Cypher 워크플로우** (구조화된 정확한 질의):

- 특정 엔티티의 속성값을 찾을 때
- "X의 Y는?" 형식의 관계 질의 (소속, 직책, 개발사 등)
- 목차 구조, 페이지 내용 같은 문서 메타데이터
- 정확한 개수, 목록, 통계 데이터
- 도메인 그래프를 활용한 구조화된 정보 검색

*실행 흐름:*
1. schema_introspection - 스키마 확인
2. generate_cypher_query - 질문 → Cypher 쿼리 변환
3. execute_cypher_query - 쿼리 실행 및 결과 반환
</Text2Cypher 워크플로우>

<Vector Search 워크플로우>
**Vector Search** (의미 기반 종합 검색):

- "~에 관해 설명해줘" 같은 관련 내용 기반 질문
- 의미 기반 검색으로 관련 텍스트 찾기
- 그래프 관계를 통해 관련 정보 자동 확장
- 문서 계층, 엔티티 관계, 확장 컨텍스트 포함
</Vector Search 워크플로우>

**질문과 상황에 따라 다중 도구를 선택하여 사용자에게 최선의 답변을 하세요.**
"""

    # create_agent(model=..., tools=..., system_prompt=...)
    # [출처] 외부 라이브러리 langchain
    # [입력] model: "gpt-4o" 같은 글이면 init_chat_model 로 모델 객체를 만든다.
    #               "gpt-" 로 시작하면 provider 를 openai 로 추정해 langchain_openai.ChatOpenAI 를 쓴다 (소스 확인: chat_models/base.py)
    #               ChatOpenAI(...) 나 ChatAnthropic(...) 같은 모델 객체를 직접 넘겨도 된다 (temperature 등을 정하고 싶을 때)
    #        tools: 도구 리스트 (@tool 로 만든 것)
    #        system_prompt: 글이면 SystemMessage 로 바꿔, model 노드가 LLM 을 부를 때마다 메시지 맨 앞에 붙인다 (상태에는 저장되지 않는다)
    # [반환] CompiledStateGraph. .invoke / .stream 에 {"messages": [...]} 를 넣는다
    #        노드 이름: "model", "tools" (소스 확인)
    agent = create_agent(
        model="gpt-4o",
        tools=tools,
        system_prompt=system_prompt
    )

    print("\n✓ GraphRAG Tool Agent 생성 완료\n")
    return agent


# [이 파일에서 정의] 질문을 계속 입력받아 에이전트를 실행하고, 진행 과정을 출력한다
def run_agent_interactive(agent):
    print("=" * 70)
    print("GraphRAG Tool Agent")
    print("=" * 70)

    # 대화 기록. 이번 질문 + 이전 질문/답/도구 결과를 모두 담아 매번 에이전트에 넘긴다 (에이전트 자체는 기억이 없다: checkpointer 없음)
    conversation_history = []

    # while True: 무한 반복. break 를 만나야 끝난다
    while True:
        try:
            # input("안내글"): [출처] 파이썬 기본. 키보드로 한 줄 입력을 받아 글로 돌려준다. .strip() 으로 앞뒤 공백 제거
            user_input = input("\n질문: ").strip()

            # x in [목록]: 목록 안에 있으면 True. .lower() 로 "EXIT" 도 인정
            if user_input.lower() in ["exit", "quit", "q"]:
                break

            # continue: 이번 반복의 나머지를 건너뛰고 다음 반복으로 (빈 입력이면 다시 묻기)
            if not user_input:
                continue

            # 메시지를 {"role": "user", "content": 글} 딕셔너리로 넣어도 된다
            # add_messages 리듀서가 HumanMessage 객체로 바꿔 준다 (소스 확인: graph/message.py 의 convert_to_messages)
            conversation_history.append({"role": "user", "content": user_input})

            print("=" * 70)

            # 이번 질문에서 새로 생긴 메시지만 모은다 (나중에 대화 기록에 붙이려고)
            final_messages = []
            # 마지막으로 호출한 도구 이름 (ToolMessage 를 출력할 때 이름을 붙이려고)
            current_tool_name = None

            # agent.stream(입력)
            # [출처] 외부 라이브러리 langgraph (CompiledStateGraph 메서드)
            # [입력] {"messages": 대화 기록}
            # [반환] 제너레이터: for 로 꺼낼 때마다 노드 하나가 끝난 결과를 하나씩 준다 (전부 끝날 때까지 기다리지 않는다)
            #   제너레이터: 값을 한꺼번에 리스트로 만들지 않고, 요청할 때마다 하나씩 만들어 주는 반복 객체 (함수 안에서 yield 로 만든다)
            # stream_mode 를 안 주면 compile 때 정한 "updates" 가 기본 (소스 확인: StateGraph.compile 의 stream_mode="updates")
            #   -> chunk 모양: {노드이름: 그 노드가 돌려준 값}  예: {"model": {"messages": [AIMessage(...)]}}
            #   -> 전체 상태가 아니라 "이번에 바뀐 부분" 만 온다. 그래서 messages 에는 새 메시지만 들어 있다
            for chunk in agent.stream({"messages": conversation_history}):
                # chunk: {node_name: {messages: [...]}}
                # chunk.items(): (노드이름, 노드값) 쌍. updates 모드에서는 보통 노드 하나씩
                for node_name, node_data in chunk.items():
                    print(f"> 노드 진입: {node_name}")
                    print("-" * 70)

                    # "messages" in 딕셔너리: 그 키가 있는지
                    if "messages" in node_data:
                        messages = node_data["messages"]
                        for msg in messages:
                            # type(msg).__name__: 객체의 클래스 이름 글 ("AIMessage", "ToolMessage", ...). isinstance 대신 이름으로 구분
                            msg_type = type(msg).__name__

                            if msg_type == "AIMessage":
                                # hasattr(객체, "속성"): 속성이 있으면 True
                                # msg.tool_calls: LLM 이 요청한 도구 호출 리스트. 각 항목은 {"name": 도구이름, "args": {인자}, "id": ...} 딕셔너리
                                # 비어 있지 않으면 "도구를 불러 줘" 라는 뜻 -> 다음은 tools 노드
                                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                    for tool_call in msg.tool_calls:
                                        print(f"🔧 Tool 호출: {tool_call['name']}")
                                        print(f"   입력: {tool_call['args']}")
                                        # 주의: 한 번에 도구를 여러 개 요청하면(병렬 호출) 마지막 이름만 남아서, 아래 ToolMessage 들이 모두 같은 이름으로 찍힐 수 있다
                                        # (ToolMessage 에는 msg.name 이 있어 그쪽을 쓰면 정확하다)
                                        current_tool_name = tool_call['name']
                                # tool_calls 가 없고 글이 있으면 최종 답변
                                elif msg.content:
                                    # 최종 응답
                                    print(f"💬 Agent 응답:")
                                    print(f"   {msg.content}")

                            # ToolMessage: 도구 실행 결과 메시지. content 에 도구가 return 한 글이 들어 있다
                            elif msg_type == "ToolMessage":
                                # Tool 실행 결과
                                print(f"Tool 실행 결과 ({current_tool_name}):")
                                # 결과가 너무 길면 요약
                                result = str(msg.content)
                                # 화면 출력만 1000글자로 자른다. 대화 기록에는 원문 그대로 들어간다
                                if len(result) > 1000:
                                    print(f"   {result[:1000]}...")
                                    print(f"   (총 {len(result)} 글자)")
                                else:
                                    print(f"   {result}")

                            # 종류와 상관없이 모든 새 메시지를 모은다 (AIMessage 의 tool_calls 와 ToolMessage 짝이 맞아야 다음 질문에서 LLM API 가 받아 준다)
                            final_messages.append(msg)

                    print()

            # list.extend(다른리스트): 원소들을 뒤에 이어 붙인다 (append 는 리스트 통째로 하나를 붙인다)
            # 주의: 기록이 계속 쌓인다. 도구 결과가 길면 몇 번만에 모델의 컨텍스트 한도에 닿을 수 있다 (GUIDE 생각해 볼 점 4)
            conversation_history.extend(final_messages)

            print("=" * 70)

        # KeyboardInterrupt: Ctrl+C 를 누르면 나는 예외 -> 반복을 끝낸다
        except KeyboardInterrupt:
            break
        # 그 밖의 에러는 출력하고 다음 질문으로 계속
        # 주의: Ctrl+D 등으로 입력이 끝나면 input() 이 EOFError 를 내는데, EOFError 는 Exception 의 자식이라 여기서 잡히고
        #       다시 input() 이 바로 EOFError -> 오류 출력이 끝없이 반복될 수 있다 (except EOFError: break 를 앞에 두면 막힌다)
        # 주의: stream 도중 에러가 나면 이번 user 메시지는 기록에 남고 답은 안 남는다 (다음 질문 때 답 없는 질문이 같이 간다)
        except Exception as e:
            print(f"\n오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()


# [이 파일에서 정의] 에이전트 그래프 그림을 tool_agent.png 로 저장 (text2cypher_agent 의 main.py 와 같은 방법)
def save_graph_as_png(agent):
    """Agent 그래프를 PNG 파일로 저장"""
    try:
        # agent.get_graph().draw_mermaid_png(): 그래프 구조 -> Mermaid -> PNG 바이트 (기본: mermaid.ink 웹 서비스)
        png_data = agent.get_graph().draw_mermaid_png()
        # f-string 인데 {} 가 없다. 그냥 글과 같다
        filename = f"tool_agent.png"

        # "wb": 바이트 쓰기 모드. with 가 끝나면 파일이 닫힌다
        with open(filename, 'wb') as f:
            f.write(png_data)

        print(f"✓ 그래프 이미지 저장 완료: {filename}\n")
    except Exception as e:
        print(f"그래프 저장 실패: {e}\n")


# [이 파일에서 정의] 환경변수 확인 -> 에이전트 생성 -> 그림 저장 -> 대화 시작
def main():
    """메인 실행 함수"""
    # os.environ.get(이름): 환경변수 읽기 (없으면 None)
    # 주의: 키가 없으면 아무 메시지 없이 그냥 끝난다. 처음 실행하는 사람은 왜 끝났는지 알 수 없다 (GUIDE 생각해 볼 점 6)
    if not os.environ.get("OPENAI_API_KEY"):
        return
    if not os.environ.get("NEO4J_URI"):
        return

    agent = create_graphrag_agent()
    save_graph_as_png(agent)
    run_agent_interactive(agent)


# 직접 실행할 때만 main()
if __name__ == "__main__":
    main()
