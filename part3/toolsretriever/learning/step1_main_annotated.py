"""[1단계: 읽기] main.py (검색기 4개를 도구로 묶은 ToolsRetriever + GraphRAG 대화형 실행) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1)로 확인했다.

전제: Part 2 pdf2kg (+ pdf2kg_2) 문서 그래프, part3/vectorsearch 의 TextElement.embedding.
      .env 에 NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, OPENAI_API_KEY.

흐름 (질문 하나에 LLM 을 최소 2번, text2cypher 가 골라지면 3번 부른다)
                         ┌─ text_vector_search          (TextElement 벡터)
  질문 ─▶ ToolsRetriever ─┼─ table_vector_search         (TableElement 벡터)
          (LLM 1번:       ├─ vectorcypher_context_search (벡터 + 문서 구조 + 엔티티 확장)
           도구 고르기)   └─ text2cypher_structured_query (LLM 이 Cypher 작성 = LLM 1번 더)
                                    │ 고른 도구(들)의 결과, 결과마다 metadata["tool"] = 도구 이름
                                    ▼
                    GraphRAG: 결과 글을 {context} 에 넣은 prompts.py 의 프롬프트 -> LLM(마지막 1번) -> 답변
ToolsRetriever 내부 (소스 확인)
  1) llm.invoke_with_tools(질문, tools, system_instruction=기본 안내문) -> OpenAI chat.completions(tools=..., tool_choice="auto")
     기본 안내문: "질문을 분석해 가장 알맞은 도구를 고르라. 여러 개를 골라도 되고, 하나도 안 골라도 된다"
  2) LLM 이 돌려준 tool_calls 마다 (이름, 인자 JSON) -> 그 Tool.execute(**인자) = 검색기.search(**인자)
  3) 결과 item 마다 Record({"content": item.content, "tool_name": 이름, "metadata": {...item.metadata, "tool": 이름}}) 로 감싼다
  4) 기본 포매터가 content = str(Record 전체), metadata = Record["metadata"] 로 바꾼다
  5) 어디서든 예외가 나면 에러를 던지지 않고 빈 결과 + metadata["error"] 를 돌려준다

읽는 순서 권장: main -> create_tools_retriever -> run_graphrag
  (그다음 vector_retriever -> vectorcypher_retriever -> text2cypher_retriever -> schema -> prompts 주석본)
실행 위치: part3/toolsretriever 에서 PYTHONPATH=. python learning/step1_main_annotated.py  (대화형, 'q' 나 'exit' 로 종료)
  (같은 폴더의 config, vector_retriever 등을 import 하므로 PYTHONPATH=. 가 필요하다. 원본은 python main.py)
"""

# [출처] 외부 라이브러리 neo4j-graphrag. ToolsRetriever: 여러 도구 중 LLM 이 골라 실행하는 검색기 (검색기들의 "라우터")
from neo4j_graphrag.retrievers import ToolsRetriever
# GraphRAG: 검색기 + LLM + 프롬프트 틀을 묶은 파이프라인. .search 한 번으로 검색과 답변까지
from neo4j_graphrag.generation import GraphRAG

# [출처] 같은 폴더의 config.py, vector_retriever.py, vectorcypher_retriever.py, text2cypher_retriever.py, prompts.py
# 기능별로 파일을 나누고 main 에서 조립한다
from config import initialize_connection, create_vector_indexes
# from 모듈 import ( ... ): 이름이 많을 때 괄호로 감싸 여러 줄로 쓸 수 있다
from vector_retriever import (
    create_text_vector_retriever,
    create_table_vector_retriever,
    create_text_vector_tool,
    create_table_vector_tool
)
from vectorcypher_retriever import create_vectorcypher_retriever, create_vectorcypher_tool
from text2cypher_retriever import create_text2cypher_retriever, create_text2cypher_tool
from prompts import create_rag_prompt_template


# ============================================
# ToolsRetriever 생성
# ============================================

# [이 파일에서 정의] 검색기 4개 생성 -> 도구 4개로 변환 -> ToolsRetriever 하나로 묶기
# [입력] driver, llm, embedder, 인덱스 이름 2개   [반환] ToolsRetriever
def create_tools_retriever(driver, llm, embedder, text_index_name, table_index_name):
    """4가지 Retriever를 생성하고 ToolsRetriever로 통합"""

    # 1. TextElement 벡터 검색
    text_vector_retriever = create_text_vector_retriever(driver, embedder, text_index_name)

    # 2. TableElement 벡터 검색
    table_vector_retriever = create_table_vector_retriever(driver, embedder, table_index_name)

    # 3. VectorCypher 검색
    # VectorCypher 도 텍스트 인덱스(text_index_name)를 쓴다. 출발점은 텍스트 검색과 같고, 그 뒤 그래프로 확장하는 것이 다르다
    vectorcypher_retriever = create_vectorcypher_retriever(driver, embedder, text_index_name)

    # 4. Text2Cypher 검색
    # 이 함수 안에서 DB 스키마를 조회하고 화면에 출력한다 (schema.py)
    text2cypher_retriever = create_text2cypher_retriever(driver, llm)

    # Tool로 변환
    # 각 검색기.convert_to_tool(name, description) -> Tool. 이름과 설명이 LLM 의 선택 기준
    text_vector_tool = create_text_vector_tool(text_vector_retriever)
    table_vector_tool = create_table_vector_tool(table_vector_retriever)
    vectorcypher_tool = create_vectorcypher_tool(vectorcypher_retriever)
    text2cypher_tool = create_text2cypher_tool(text2cypher_retriever)

    # ToolsRetriever 생성
    # ToolsRetriever(driver=..., llm=..., tools=[...])
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] llm: 도구를 고를 LLM (invoke_with_tools 를 지원해야 한다. OpenAILLM 은 지원)
    #        tools: Tool 리스트. 이름이 겹치면 만들 때 ValueError
    #        system_instruction: 안 주면 영어 기본 안내문 (위 HEADER 참고)
    # [반환] 검색기. 다른 검색기처럼 .search(query_text=...) 로 부를 수 있어서 GraphRAG 의 retriever 자리에 그대로 들어간다
    # 이 검색기는 Neo4j 를 직접 조회하지 않는다 (만들 때 버전 확인도 하지 않는다). driver 는 형식상 받는다
    tools_retriever = ToolsRetriever(
        driver=driver,
        llm=llm,
        tools=[text_vector_tool, table_vector_tool, vectorcypher_tool, text2cypher_tool]
    )

    print("✓ ToolsRetriever 생성 완료 (4개 도구 등록)")
    return tools_retriever


# ============================================
# GraphRAG 실행 함수
# ============================================

# [이 파일에서 정의] 질문 하나를 GraphRAG 로 처리하고 선택된 도구, 답변, 검색 결과를 출력
# [반환] RagResultModel (.answer, .retriever_result)
def run_graphrag(tools_retriever, llm, query_text):
    """GraphRAG 실행 및 결과 반환"""

    # 프롬프트 템플릿 생성
    # prompts.py 의 RagTemplate. 질문마다 새로 만든다
    prompt_template = create_rag_prompt_template()

    # GraphRAG 생성
    # GraphRAG(llm=..., retriever=..., prompt_template=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [반환] 파이프라인 객체
    # 주의: 질문마다 GraphRAG 와 프롬프트 틀을 새로 만든다. 동작은 같지만 main 에서 한 번만 만들어 넘겨도 된다
    graphrag = GraphRAG(
        llm=llm,
        retriever=tools_retriever,
        prompt_template=prompt_template
    )

    # f"{'='*70}": f-string 안에서 식 사용. "=" 를 70번 반복한 구분선
    print(f"\n{'='*70}")
    print(f"질문: {query_text}")
    print(f"{'='*70}\n")
    print("🔍 검색 중...")

    # graphrag.search(query_text=..., return_context=True)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # 내부 동작 (소스 확인):
    #   1) tools_retriever.search(query_text=질문) -> RetrieverResult(items, metadata)
    #   2) context = "\n".join(item.content for item in items)
    #   3) 프롬프트 = template.format(query_text=질문, context=context, examples="")
    #   4) llm.invoke(프롬프트, system_instruction="Answer the user question using the provided context.")
    # [반환] RagResultModel. .answer: 답변 글 / .retriever_result: return_context=True 일 때만 채워짐
    # 주의: 도구 선택이나 실행에서 에러가 나도 ToolsRetriever 가 삼켜서 items 가 빈 리스트가 된다.
    #       그래도 답변 LLM 은 빈 context 로 불린다. 에러 내용은 result.retriever_result.metadata["error"] 에만 있고
    #       이 함수는 그것을 출력하지 않으므로, "검색 결과 0건" 인 이유를 알 수 없다
    result = graphrag.search(query_text=query_text, return_context=True)

    # 선택된 Tool 정보 출력
    # hasattr(객체, '이름'): [출처] 파이썬 기본. 그 속성이 있으면 True
    # and 뒤의 result.retriever_result: None 이 아닐 때만 진행 (return_context=True 라서 사실상 항상 있다)
    if hasattr(result, 'retriever_result') and result.retriever_result:
        # A if 조건 else B: 조건식(삼항 연산자). 한 줄짜리 if/else
        items = result.retriever_result.items if hasattr(result.retriever_result, 'items') else []
        if items:
            # set(): 중복을 허용하지 않는 집합. 같은 도구 결과가 여러 개여도 이름은 한 번만 모인다
            tools_used = set()
            for item in items:
                # 'tool' in item.metadata: 딕셔너리에 그 키가 있는지. ToolsRetriever 가 모든 결과에 "tool" 을 넣어 주므로 항상 참
                if hasattr(item, 'metadata') and item.metadata and 'tool' in item.metadata:
                    tools_used.add(item.metadata['tool'])

            if tools_used:
                # sorted(집합): 이름순 리스트 / ', '.join: 쉼표로 이어 출력. 예) 선택된 Tool(검색 방식): text2cypher_structured_query, vectorcypher_context_search
                print(f"\n🔧 선택된 Tool(검색 방식): {', '.join(sorted(tools_used))}")

    print("\n" + "="*70)
    print("📝 답변 결과")
    print("="*70)
    # result.answer: 최종 답변 글
    print(result.answer)
    print("="*70)

    # 검색 결과 상세 출력
    if hasattr(result, 'retriever_result') and result.retriever_result:
        items = result.retriever_result.items if hasattr(result.retriever_result, 'items') else []
        if items:
            print(f"\n검색된 항목: {len(items)}개")
            print("-"*70)

            # enumerate(items, 1): 1번부터 번호를 붙이며 반복
            for idx, item in enumerate(items, 1):
                print(f"\n[{idx}] 검색 결과:")

                # content 출력
                # item.content: str(Record) 글. 예) <Record content='...' tool_name='text_vector_search' metadata={...}>
                content = item.content if hasattr(item, 'content') else str(item)
                print(f"  내용: {content}")

                # metadata 출력
                # item.metadata.get('tool'): 이 결과를 만든 도구 이름
                if hasattr(item, 'metadata') and item.metadata:
                    # vectorcypher 결과는 metadata 에 entities, base_context, expanded_context 가 다 들어 있어 너무 길다 -> 메타데이터 출력만 건너뛴다
                    # continue: 반복문의 나머지를 건너뛰고 다음 원소로 (내용은 위에서 이미 출력했다)
                    if item.metadata.get('tool') == "vectorcypher_context_search":
                        continue
                    print(f"  메타데이터: {item.metadata}")

            print("-"*70)

    return result


# ============================================
# 메인 함수
# ============================================

# [이 파일에서 정의] 초기화 -> 인덱스 -> ToolsRetriever -> 질문 입력 반복
def main():
    print("\n" + "="*70)
    print("PDF 지식그래프 기반 ToolsRetriever GraphRAG")
    print("="*70 + "\n")

    print("[1단계] 초기화")
    print("-"*70)
    # 튜플 언패킹: config.initialize_connection 이 돌려준 (driver, llm, embedder) 를 세 변수에 나눠 받는다
    driver, llm, embedder = initialize_connection()
    print()

    print("[2단계] 벡터 인덱스 생성")
    print("-"*70)
    # 인덱스가 이미 있으면 에러 없이 넘어간다 (IF NOT EXISTS). 이름 2개를 받는다
    text_index_name, table_index_name = create_vector_indexes(driver)
    print()

    print("[3단계] ToolsRetriever 생성")
    print("-"*70)
    tools_retriever = create_tools_retriever(driver, llm, embedder, text_index_name, table_index_name)
    print()

    print("[4단계] GraphRAG 대화형 실행")
    print("-"*70)
    print("\n여러 질문을 계속 입력할 수 있습니다. 종료하려면 'q' 또는 'exit'를 입력하세요.\n")

    # try / except KeyboardInterrupt / finally: Ctrl+C 로 끝내도 finally 에서 연결을 닫는다
    try:
        # while True: 무한 반복. 아래 break 로만 빠져나간다
        while True:
            print("-" * 70)
            # input(안내글): [출처] 파이썬 기본. 키보드 입력 한 줄을 글로 받는다
            # .strip(): 앞뒤 공백/줄바꿈 제거
            query = input("질문을 입력하세요 (종료: 'q' 또는 'exit'): ").strip()

            # .lower(): 소문자로 바꿔 'Q', 'EXIT' 도 종료로 처리
            if query.lower() in ['q', 'exit']:
                print("\n프로그램을 종료합니다.")
                break

            # GraphRAG 실행
            # 질문 하나가 실패해도 프로그램이 끝나지 않도록 안쪽 try. continue 로 다음 질문을 받는다
            # 주의: 빈 입력(엔터만)도 그대로 검색에 들어간다
            try:
                # result 변수는 이후 쓰이지 않는다 (run_graphrag 안에서 이미 출력함)
                result = run_graphrag(tools_retriever, llm, query)
            except Exception as e:
                print(f"\n오류 발생: {e}")
                continue

    # KeyboardInterrupt: Ctrl+C 를 눌렀을 때 나는 예외
    except KeyboardInterrupt:
        print("\n\n프로그램을 종료합니다.")
    # finally: 정상 종료든 예외든 항상 실행
    finally:
        driver.close()
        print("Neo4j 연결을 종료했습니다.")

    # 주의: finally 에서 이미 닫은 driver 를 돌려준다. 이 반환값으로 다시 쿼리하면 에러가 난다 (스크립트 실행에서는 쓰이지 않는다)
    return driver, tools_retriever, llm

# if __name__ == "__main__": 이 파일을 직접 실행할 때만 main() (import 할 때는 실행 안 됨)
if __name__ == "__main__":
    main()
