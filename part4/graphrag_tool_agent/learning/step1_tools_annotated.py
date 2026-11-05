"""[1단계: 읽기] tools.py (에이전트가 고를 도구 4개: 스키마 조회 / Cypher 생성 / Cypher 실행 / VectorCypher 검색) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
LangChain/neo4j-graphrag/neo4j 설명은 설치 소스(langchain 1.2.15, langchain-core 1.3.0, neo4j-graphrag 1.15.0, neo4j 6.1.0, requirements.txt 기준)로 확인했다.

도구(tool)란?
  LLM 이 "이 함수를 이 인자로 불러 줘" 라고 요청할 수 있게 이름 + 설명 + 인자 모양을 붙인 함수.
  @tool 을 붙이면 함수가 StructuredTool 객체가 된다. LLM 은 docstring 에서 뽑은 "설명" 을 읽고 언제 쓸지 고른다.
  -> 그래서 이 파일에서 docstring 은 사람용 메모가 아니라 LLM 에게 보내는 "사용 설명서" 다.

흐름
  initialize_tools()  : 드라이버 / LLM / 임베더 / VectorCypherRetriever 를 모듈 전역에 한 번만 만든다
  [Text2Cypher 3단계]  schema_introspection() -> 스키마 글
                       generate_cypher_query(question, schema_text) -> Cypher 글 (실행은 안 함)
                       execute_cypher_query(cypher_query) -> 결과 글 (오류도 글로)
  [Vector]            vector_search(question, top_k) -> 벡터 검색 + Chunk/TOC/엔티티로 확장한 글
  get_all_tools()     : 위 4개 리스트 -> main.py 의 create_agent(tools=...) 로 간다

모든 도구가 "예외를 던지지 않고 오류도 문자열로 돌려준다": 에이전트(LLM)가 오류 글을 읽고 다음 행동을 고를 수 있게.

전제: Part 2 pdf2kg 문서 그래프 + 임베딩 + text_content_vector_index (Part 3 toolsretriever 가 만든다), .env 에 NEO4J_*, OPENAI_API_KEY
읽는 순서 권장: initialize_tools -> schema_introspection -> generate_cypher_query -> execute_cypher_query
               -> _create_vectorcypher_retriever (retrieval_query, format_result) -> vector_search -> __main__
실행 위치: part4/graphrag_tool_agent 에서  python learning/step1_tools_annotated.py
  (같은 폴더 모듈을 import 하지 않아 PYTHONPATH 는 필요 없다. 도구 4개를 에이전트 없이 하나씩 실제로 부른다: DB 와 OpenAI API 사용)
"""

# [출처] 표준 라이브러리. os.getenv
import os
# [출처] 표준 라이브러리 typing. List[str]: "str 들의 리스트" 타입 힌트
from typing import Dict, Any, List
# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버. neo4j.GraphDatabase, neo4j.Record 처럼 모듈 이름을 붙여 쓴다
import neo4j
# [출처] 외부 라이브러리 langchain (안에서 langchain_core.tools 의 tool 을 그대로 다시 내보낸다. 소스 확인: langchain/tools/__init__.py)
# tool: 함수를 LLM 이 부를 수 있는 "도구" 로 바꾸는 데코레이터
from langchain.tools import tool
# [출처] 외부 라이브러리 neo4j-graphrag. OpenAILLM: .invoke(글) -> LLMResponse(.content 에 답 글)
from neo4j_graphrag.llm import OpenAILLM
# OpenAIEmbeddings: 글 -> 벡터(숫자 리스트). 벡터 검색에서 질문을 벡터로 바꿀 때 쓴다
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
# VectorCypherRetriever: 벡터 인덱스로 비슷한 노드를 찾고, 그 노드에서 출발하는 Cypher(retrieval_query)를 이어 실행하는 검색기
from neo4j_graphrag.retrievers import VectorCypherRetriever
# RetrieverResultItem: 검색 결과 한 건 (content 글 + metadata 딕셔너리). format_result 가 이걸 만든다
from neo4j_graphrag.types import RetrieverResultItem

# .env 를 읽어 환경변수로 등록 (OpenAILLM, OpenAIEmbeddings 가 OPENAI_API_KEY 를 여기서 읽는다)
load_dotenv()

# 모듈 전역 변수 4개를 None 으로 시작. initialize_tools 가 처음 불릴 때 채운다 (지연 초기화)
# [왜] 도구는 호출될 때마다 실행된다. 매번 드라이버를 만들면 느리고 연결이 쌓인다
_driver = None
_llm = None
_embedder = None
_vectorcypher_retriever = None


# [이 파일에서 정의] 공용 자원을 한 번만 만든다 [반환] (driver, llm, embedder) 튜플
# 여러 번 불러도 이미 만든 것은 다시 만들지 않는다 (if ... is None)
def initialize_tools():
    # global 이름들: 문법. 함수 안에서 "모듈 전역 변수" 에 새 값을 대입하겠다는 선언
    # 이 줄이 없으면 _driver = ... 는 함수 안에서만 사는 새 지역 변수가 되어 전역 _driver 는 계속 None 이다
    global _driver, _llm, _embedder, _vectorcypher_retriever

    if _driver is None:
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        # neo4j.GraphDatabase.driver(uri, auth=(user, pw)): 연결 객체 생성. 실제 접속은 첫 쿼리 때
        _driver = neo4j.GraphDatabase.driver(uri, auth=(username, password))
        print(f"✓ Neo4j 연결: {uri}")

    if _llm is None:
        # OpenAILLM(model_name=..., model_params={...})
        # [출처] 외부 라이브러리 neo4j-graphrag
        # [입력] model_name: OpenAI 모델 이름 / model_params: OpenAI API 에 그대로 넘길 옵션 (temperature 0 = 최대한 같은 답)
        # [반환] LLM 객체. generate_cypher_query 가 .invoke(프롬프트글) 로 쓴다
        # (에이전트를 움직이는 LLM 은 main.py 의 create_agent(model="gpt-4o") 쪽이고, 이건 도구 안에서 Cypher 를 쓰는 별도 LLM 이다)
        _llm = OpenAILLM(
            model_name="gpt-4o",
            model_params={"temperature": 0}
        )
        print("✓ OpenAI LLM 초기화")

    if _embedder is None:
        # OpenAIEmbeddings(model=...): [출처] neo4j-graphrag. 인덱스를 만들 때와 같은 임베딩 모델이어야 벡터가 비교된다
        _embedder = OpenAIEmbeddings(model="text-embedding-3-small")
        print("✓ OpenAI Embeddings 초기화")

    if _vectorcypher_retriever is None:
        # _create_vectorcypher_retriever 는 아래에서 정의. 함수 본문은 "불릴 때" 실행되므로 아래에 정의돼 있어도 된다
        _vectorcypher_retriever = _create_vectorcypher_retriever()
        print("✓ VectorCypher Retriever 생성")

    # 주의: _vectorcypher_retriever 는 돌려주지 않는다. vector_search 는 전역 변수를 직접 쓴다
    return _driver, _llm, _embedder


# [이 파일에서 정의] VectorCypherRetriever 를 만든다. 이름 앞 _ : 이 모듈 안에서만 쓰는 함수라는 관례
def _create_vectorcypher_retriever():
    """VectorCypher Retriever 생성 (벡터 검색 + 그래프 컨텍스트 확장)"""

    # retrieval_query: 벡터 검색 "다음에" 이어 붙는 Cypher
    # neo4j-graphrag 가 앞에 이 쿼리를 붙인다 (소스 확인: neo4j_queries.py)
    #   CALL db.index.vector.queryNodes($vector_index_name, $top_k * $effective_search_ratio, $query_vector)
    #   YIELD node, score WITH node, score LIMIT $top_k
    #   -> 그래서 이 글에서 node (찾은 TextElement), score (유사도) 를 바로 쓸 수 있다
    # 단계: TextElement -> 속한 Chunk -> Chunk 의 TOC(목차)와 부모 TOC들 -> 같은 Chunk 의 문장들 -> Chunk 의 엔티티
    #       -> 같은 엔티티를 가진 다른 Chunk 의 문장들(확장) -> 한 줄로 정리해 RETURN
    # 주의: 1단계가 OPTIONAL 이 아닌 MATCH 라 Chunk 에 연결 안 된 TextElement 는 결과에서 빠진다.
    #       OPTIONAL MATCH 를 여러 개 이어 쓴 뒤 collect 하므로 중간에 (부모TOC x 문장 x 엔티티) 줄이 곱으로 늘어난다. 큰 문서에서는 느릴 수 있다
    retrieval_query = """
    // node = 벡터 검색으로 찾은 TextElement
    // score = 유사도 점수

    // 1. 검색된 TextElement가 속한 Chunk 찾기
    MATCH (chunk:Chunk)-[:HAS_ELEMENT]->(node)

    // 2. Chunk가 속한 TOC(목차) 찾기
    OPTIONAL MATCH (toc:TOC)-[:HAS_CHUNK]->(chunk)

    // 3. 부모 TOC 노드들 (계층 구조) 수집
    OPTIONAL MATCH (parent_toc:TOC)-[:HAS_CHILD*]->(toc)

    // 4. 기본 컨텍스트: 현재 Chunk의 모든 TextElement
    OPTIONAL MATCH (chunk)-[:HAS_ELEMENT]->(base_element:TextElement)

    // 5. HAS_ENTITY 기반 확장: Chunk의 엔티티들
    OPTIONAL MATCH (chunk)-[:HAS_ENTITY]->(entity)

    WITH
        node, chunk, toc, score,
        collect(DISTINCT parent_toc) AS parent_tocs,
        collect(DISTINCT base_element) AS base_elements,
        collect(DISTINCT entity) AS entities

    // 6. 같은 엔티티를 공유하는 다른 Chunk들 찾기
    OPTIONAL MATCH (other_chunk:Chunk)-[:HAS_ENTITY]->(shared_entity)
    WHERE shared_entity IN entities AND other_chunk <> chunk

    // 7. 확장된 Chunk들의 TextElement 및 TOC 정보 수집
    OPTIONAL MATCH (other_chunk)-[:HAS_ELEMENT]->(expanded_element:TextElement)
    OPTIONAL MATCH (expanded_toc:TOC)-[:HAS_CHUNK]->(other_chunk)

    WITH
        node, chunk, toc, score,
        parent_tocs,
        base_elements,
        entities,
        collect(DISTINCT other_chunk) AS expanded_chunks,
        collect(DISTINCT {
            element: expanded_element,
            toc: expanded_toc
        }) AS expanded_elements_with_toc

    // 8. 결과 반환
    RETURN
        elementId(node) AS element_id,
        elementId(chunk) AS chunk_id,
        elementId(toc) AS toc_id,
        node.content AS content,
        node.page AS page,
        score,

        // TOC 정보
        toc.title AS toc_title,
        toc.level AS toc_level,
        toc.page_start AS toc_page_start,

        // 부모 계층 구조
        [p IN parent_tocs | {
            title: p.title,
            level: p.level,
            page_start: p.page_start
        }] AS parent_hierarchy,

        // 엔티티 정보
        [e IN entities | {
            type: labels(e)[0],
            name: e.name
        }] AS entities,

        // 기본 컨텍스트 (같은 Chunk)
        [b IN base_elements | {
            content: b.content,
            page: b.page
        }] AS base_context,

        // 확장된 컨텍스트 (엔티티 기반)
        [item IN expanded_elements_with_toc WHERE item.element IS NOT NULL | {
            content: item.element.content,
            page: item.element.page,
            source_toc_title: item.toc.title,
            source_toc_page: item.toc.page_start,
            source_toc_level: item.toc.level
        }] AS expanded_context

    ORDER BY score DESC
    """

    # [이 파일에서 정의] 함수 안의 함수(중첩 함수). Record 한 줄 -> RetrieverResultItem
    # 검색기의 result_formatter 로 넘겨, 검색 결과 Record 마다 한 번씩 불린다 (소스 확인: Retriever.search 가 [formatter(record) for record in records])
    def format_result(record: neo4j.Record) -> RetrieverResultItem:
        """검색 결과를 포맷팅"""
        content_parts = []

        # 핵심 내용
        # record.get(키, 기본값): [출처] neo4j Record 메서드. 키가 "없을 때만" 기본값
        # 주의: 키는 있는데 값이 null 이면 기본값이 아니라 None 이 나온다 (소스 확인). page 가 null 이면 "[페이지] None" 으로 찍힌다
        content = record.get("content", "")
        page = record.get("page", "")
        content_parts.append(f"[내용] {content}")
        content_parts.append(f"[페이지] {page}")

        # TOC 정보
        toc_title = record.get("toc_title")
        if toc_title:
            content_parts.append(f"[섹션] {toc_title}")

        # 엔티티
        entities = record.get("entities", [])
        if entities:
            # e['type'], e['name']: retrieval_query 에서 {type: labels(e)[0], name: e.name} 로 만든 맵이 파이썬 딕셔너리로 온다
            entity_strs = [f"{e['type']}: {e['name']}" for e in entities]
            content_parts.append(f"[연결된 엔티티] {', '.join(entity_strs)}")

        # 기본 컨텍스트
        base_context = record.get("base_context", [])
        # 같은 Chunk 의 문장이 2개 이상일 때만 (1개면 검색된 그 문장 자신뿐이라)
        if base_context and len(base_context) > 1:
            content_parts.append(f"\n[같은 섹션의 관련 문장 {len(base_context)}개]")
            # enumerate(리스트, 1): [출처] 파이썬 기본. (번호, 원소) 쌍을 준다. 1 은 시작 번호
            for idx, item in enumerate(base_context, 1):
                content_parts.append(f"  {idx}. {item['content']}")

        # 확장 컨텍스트
        expanded_context = record.get("expanded_context", [])
        if expanded_context:
            content_parts.append(f"\n[엔티티 기반 확장 문장 {len(expanded_context)}개]")
            for idx, item in enumerate(expanded_context, 1):
                content_parts.append(f"  {idx}. {item['content']}")

        formatted_content = "\n".join(content_parts)

        # metadata: 에이전트에게 보내는 글에는 안 들어가고 RetrieverResultItem 안에만 남는다 (vector_search 는 item.content 만 쓴다)
        metadata = {
            "page": page,
            "toc_title": toc_title,
            "score": record.get("score", 0.0),
            "entities": entities,
        }

        return RetrieverResultItem(content=formatted_content, metadata=metadata)

    # VectorCypherRetriever(driver=..., index_name=..., embedder=..., retrieval_query=..., result_formatter=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] index_name: Neo4j 벡터 인덱스 이름 / embedder: 질문을 벡터로 바꿀 객체 / retrieval_query: 위 Cypher / result_formatter: 위 함수
    # [반환] 검색기. .search(query_text=..., top_k=...) -> RetrieverResult(.items 리스트)
    # 만들 때 바로 DB 에 인덱스 정보를 물어본다 (소스 확인: __init__ 끝의 _fetch_index_infos). 인덱스가 없으면 여기서 에러가 난다
    # 실행은 읽기 전용 (routing_=READ, 소스 확인)
    retriever = VectorCypherRetriever(
        driver=_driver,
        index_name="text_content_vector_index",
        embedder=_embedder,
        retrieval_query=retrieval_query,
        result_formatter=format_result
    )

    return retriever


# ============================================
# 도구 1: Schema Introspection
# ============================================

# @tool(parse_docstring=True)
# 데코레이터 문법: def 바로 위의 @식 은  schema_introspection = tool(parse_docstring=True)(schema_introspection)  과 같다
#   -> 함수를 받아 다른 것(여기서는 StructuredTool 객체)으로 바꿔 같은 이름에 다시 담는다
# [출처] 외부 라이브러리 langchain-core (langchain.tools 로 가져옴)
# [입력] parse_docstring=True: Google 스타일 docstring 을 읽어
#          맨 앞 덩어리(빈 줄 전까지) -> 도구 설명(description)
#          Args: 아래 "이름: 설명" -> 각 인자의 설명 (Returns: 덩어리는 설명에서 빠진다)
#        error_on_invalid_docstring 기본값 True: 인자가 있는데 Args: 덩어리가 없으면 import 할 때 ValueError (소스 확인)
# [반환] StructuredTool. .name = 함수 이름 "schema_introspection", .description, .invoke({인자 딕셔너리})
# 주의(사용법): 이제 schema_introspection() 처럼 그냥 부를 수 없다 (StructuredTool 에는 __call__ 이 없다). .invoke({}) 로 부른다
@tool(parse_docstring=True)
# 인자가 없는 도구. -> str: 결과는 글
def schema_introspection() -> str:
    """그래프 스키마(노드, 관계, 속성)를 조회합니다.
    사용자가 "어떤 데이터가 있어?", "스키마를 보여줘" 같은 질문을 할 때 사용하거나
    Text2Cypher 워크플로우에서 generate_cypher_query가 스키마 정보를 필요로 할 때 사용합니다.

    Returns:
        그래프 스키마를 설명하는 텍스트 (노드, 관계, 속성 정보 포함)
    """
    # 튜플 풀기: (driver, llm, embedder) 중 driver 만 쓰고 나머지는 _ 로 버린다 (_ 는 "안 쓰는 값" 관례)
    driver, _, _ = initialize_tools()

    # try/except Exception: 어떤 에러가 나도 오류 글을 return (도구는 예외를 던지지 않는다)
    try:
        # 1. 노드 레이블과 속성 조회
        # CALL db.schema.nodeTypeProperties(): Neo4j 내장 프로시저. 레이블 조합마다 속성 이름과 타입 목록을 준다
        # YIELD: 프로시저 결과에서 쓸 열을 고른다. nodeLabels[0] 로 첫 레이블만 쓰고 collect 로 레이블별로 묶는다
        node_query = """
        CALL db.schema.nodeTypeProperties()
        YIELD nodeLabels, propertyName, propertyTypes
        RETURN nodeLabels[0] AS label,
               collect({
                 name: propertyName,
                 types: propertyTypes
               }) AS properties
        ORDER BY label
        """
        # driver.execute_query(쿼리): [출처] neo4j. [반환] EagerResult (.records 리스트)
        # database_ 를 안 주면 서버 기본(home) DB. routing_ 기본값은 WRITE (소스 확인)
        node_result = driver.execute_query(node_query)

        nodes_info = []
        for record in node_result.records:
            label = record["label"]
            if not label:
                continue
            properties = record["properties"]
            # properties[0]["name"]: 속성이 없는 레이블은 propertyName 이 null 인 줄 하나만 온다 -> 이름 없이 레이블만 출력
            # 주의: 같은 레이블에 속성 없는 노드 조합이 섞여 있으면 null 항목이 맨 앞에 와서 속성이 통째로 빠질 수 있다
            if properties and properties[0]["name"]:
                # types는 리스트로 반환되므로 첫 번째 요소를 Python에서 추출
                # 리스트 컴프리헨션 안의 조건식: p['types'][0] if p['types'] else 'Unknown' -> 타입 목록의 첫 번째 (예: "String")
                # for p in properties if p.get('name'): 이름이 있는 항목만
                props_str = ", ".join([f"{p['name']}: {p['types'][0] if p['types'] else 'Unknown'}" for p in properties if p.get('name')])
                # {{{props_str}}}: 글자 { + 값 + 글자 }
                nodes_info.append(f"  - {label} {{{props_str}}}")
            else:
                nodes_info.append(f"  - {label}")

        # 2. 관계 타입과 속성 조회
        # CALL db.schema.relTypeProperties(): 관계 타입별 속성 목록
        # 주의: 이 프로시저의 relType 은 ":`HAS_CHUNK`" 처럼 콜론과 백틱이 붙은 모양으로 오는 것으로 알고 있다 (이 환경에서 실행 확인은 못 함).
        #       그렇다면 아래 관계 패턴 반복문의 rel_type in rel_properties 비교에서 type(r) 의 "HAS_CHUNK" 와 모양이 달라 관계 속성이 늘 빠질 수 있다.
        #       Neo4j Browser 에서 CALL db.schema.relTypeProperties() 를 직접 실행해 확인해 보자
        rel_props_query = """
        CALL db.schema.relTypeProperties()
        YIELD relType, propertyName, propertyTypes
        RETURN relType,
               collect({
                 name: propertyName,
                 types: propertyTypes
               }) AS properties
        """
        rel_props_result = driver.execute_query(rel_props_query)

        rel_properties = {}
        for record in rel_props_result.records:
            rel_type = record["relType"]
            if rel_type and record["properties"] and record["properties"][0]["name"]:
                rel_properties[rel_type] = record["properties"]

        # 3. 관계 패턴 조회
        # 관계 방향 패턴: 모든 관계를 훑는다 (GUIDE 생각해 볼 점 5. 큰 그래프에서는 느리다)
        rel_pattern_query = """
        MATCH (a)-[r]->(b)
        WITH labels(a) as sourceLabels, type(r) as relType, labels(b) as targetLabels
        WHERE size(sourceLabels) > 0 AND size(targetLabels) > 0
        RETURN DISTINCT sourceLabels[0] as source, relType, targetLabels[0] as target
        ORDER BY relType
        """
        rel_pattern_result = driver.execute_query(rel_pattern_query)

        relations_info = []
        for record in rel_pattern_result.records:
            source = record["source"]
            rel_type = record["relType"]
            target = record["target"]

            if rel_type in rel_properties:
                props = rel_properties[rel_type]
                # types는 리스트로 반환되므로 첫 번째 요소를 Python에서 추출
                props_str = ", ".join([f"{p['name']}: {p['types'][0] if p['types'] else 'Unknown'}" for p in props if p.get('name')])
                relations_info.append(f"  - ({source})-[:{rel_type} {{{props_str}}}]->({target})")
            else:
                relations_info.append(f"  - ({source})-[:{rel_type}]->({target})")

        # 문자열 += : 기존 글 뒤에 이어 붙인다
        result = "=== Neo4j 그래프 스키마 ===\n\n"
        result += "📦 노드 레이블 및 속성:\n"
        # A if 조건 else B: 목록이 비어 있으면 "(노드 없음)"
        result += "\n".join(nodes_info) if nodes_info else "  (노드 없음)"
        result += "\n\n🔗 관계 패턴:\n"
        result += "\n".join(relations_info) if relations_info else "  (관계 없음)"

        return result

    except Exception as e:
        return f"스키마 조회 중 오류 발생: {str(e)}"


# ============================================
# 도구 2: Generate Cypher Query (Text2Cypher)
# ============================================

# [이 파일에서 정의] 도구 2. 질문 -> Cypher 글 (실행은 하지 않는다)
# [입력] question: 질문 / schema_text: 스키마 글 (에이전트가 schema_introspection 결과를 인자로 복사해 넘긴다. 없으면 직접 조회)
# [반환] Cypher 글 또는 오류 글
# schema_text: str = None : 타입 힌트는 str 인데 기본값은 None (엄밀히는 Optional[str])
# 주의: 스키마 전체를 LLM(에이전트)이 인자로 다시 써야 해서 토큰이 두 번 든다 (GUIDE 생각해 볼 점 3)
@tool(parse_docstring=True)
def generate_cypher_query(question: str, schema_text: str = None) -> str:
    """자연어 질문을 Neo4j Cypher 쿼리로 변환합니다.
    Text2Cypher 검색방식을 선택할 때 schema_introspection 결과를 전달받아 사용할 수 있습니다.
    execute_cypher_query와 함께 사용합니다.

    Args:
        question: 자연어 질문 (예: "OpenAI에 대해 알려줘", "목차 구조를 보여줘")
        schema_text: 스키마 텍스트

    Returns:
        생성된 Cypher 쿼리 문자열
    """
    driver, llm, _ = initialize_tools()

    try:
        # 스키마 조회 (전달받지 못한 경우에만)
        # schema_text is None: "값이 없음" 은 == None 보다 is None 으로 검사하는 것이 관례
        if schema_text is None:
            schema_text = _get_schema_text(driver)

        # 예시 질의-쿼리 쌍
        examples = _get_text2cypher_examples()

        # LLM을 사용하여 Cypher 쿼리 생성
        # f-string 프롬프트: {schema_text}, {question} 자리에 지금 값이 바로 들어간다 (prompts 틀과 달리 즉시 채움)
        # {chr(10).join(examples)}: chr(10) 은 줄바꿈 문자 \n. 파이썬 3.12 전에는 f-string 의 {} 안에 역슬래시를 쓸 수 없어서 이렇게 쓴다
        # 예시나 스키마 글 안의 중괄호는 "값" 이라 그대로 들어간다. 이 틀 자체에 {이름} 을 쓰면 변수로 해석된다
        prompt = f"""당신은 Neo4j Cypher 쿼리 생성 전문가입니다.

주어진 스키마와 예시를 참고하여, 사용자의 질문을 Cypher 쿼리로 변환하세요.

<Neo4j 스키마>
{schema_text}
</Neo4j 스키마>

<예시 질의-쿼리 쌍>
{chr(10).join(examples)}
</예시 질의-쿼리 쌍>

<사용자 질문>
{question}
</사용자 질문>

<RULES>
1. 스키마에 정의된 노드 레이블과 관계 타입만 사용하세요
2. 검색 시 CONTAINS를 사용하여 부분 매칭을 허용하세요
3. 결과는 사용자가 이해하기 쉬운 별칭(AS)을 사용하세요
4. 쿼리만 출력하고, 설명이나 추가 텍스트는 포함하지 마세요
</RULES>

생성된 Cypher 쿼리:"""

        # llm.invoke(글): [출처] neo4j-graphrag OpenAILLM. 글 하나를 user 메시지로 보낸다 [반환] LLMResponse (.content)
        # .strip(): 앞뒤 공백/줄바꿈 제거
        response = llm.invoke(prompt)
        cypher_query = response.content.strip()

        # 마크다운 코드 블록 제거
        # LLM 이 ```cypher ... ``` 로 감싸 답한 경우 첫 줄과 마지막 줄을 버린다
        # 주의: 닫는 ``` 뒤에 설명 글이 더 붙어 있으면 마지막 줄만 버려서 ``` 가 남을 수 있다
        if cypher_query.startswith("```"):
            lines = cypher_query.split("\n")
            cypher_query = "\n".join(lines[1:-1])

        return cypher_query

    except Exception as e:
        return f"Cypher 쿼리 생성 중 오류 발생: {str(e)}"


# [이 파일에서 정의] generate_cypher_query 가 스키마를 직접 조회할 때 쓰는 간단한 버전 (관계 속성은 없다)
def _get_schema_text(driver) -> str:
    """스키마를 텍스트로 변환"""
    node_query = """
    CALL db.schema.nodeTypeProperties()
    YIELD nodeLabels, propertyName, propertyTypes
    RETURN nodeLabels[0] AS label,
           collect({
             name: propertyName,
             types: propertyTypes
           }) AS properties
    ORDER BY label
    """
    node_result = driver.execute_query(node_query)

    lines = ["Node properties:"]
    for record in node_result.records:
        label = record["label"]
        if not label:
            continue
        properties = record["properties"]
        if properties and properties[0].get("name"):
            props = ", ".join([f"{p['name']}: {p['types'][0] if p['types'] else 'Unknown'}" for p in properties if p.get('name')])
            lines.append(f"{label} {{{props}}}")

    rel_pattern_query = """
    MATCH (a)-[r]->(b)
    RETURN DISTINCT labels(a)[0] as source, type(r) as relType, labels(b)[0] as target
    ORDER BY relType
    """
    rel_result = driver.execute_query(rel_pattern_query)

    lines.append("\nThe relationships:")
    for record in rel_result.records:
        lines.append(f"(:{record['source']})-[:{record['relType']}]->(:{record['target']})")

    return "\n".join(lines)


# [이 파일에서 정의] few-shot 예시 4개. -> List[str] 반환 타입 힌트
def _get_text2cypher_examples() -> List[str]:
    """예시 질의-쿼리 쌍"""
    return [
        "USER INPUT: 'AI 기본법에 대한 내용을 찾아줘' QUERY: MATCH (toc:TOC) WHERE toc.title CONTAINS 'AI 기본법' RETURN toc.title AS 제목, toc.page_start AS 페이지",
        "USER INPUT: '목차 구조를 보여줘' QUERY: MATCH (toc:TOC) RETURN toc.title AS 제목, toc.page_start AS 페이지, toc.level AS 레벨 ORDER BY toc.page_start",
        "USER INPUT: 'OpenAI에 대해 알려줘' QUERY: MATCH (c:Company) WHERE c.name CONTAINS 'OpenAI' RETURN c.name AS 회사명, c.description AS 설명",
        "USER INPUT: '업스테이지의 CEO는 누구인가요?' QUERY: MATCH (c:Company)-[:HAS_EXECUTIVE|EMPLOYS|AFFILIATED_WITH]-(p:Person) WHERE c.name CONTAINS '업스테이지' AND (p.role CONTAINS 'CEO' OR p.title CONTAINS 'CEO') RETURN c.name AS 회사, p.name AS 이름, coalesce(p.role, p.title) AS 직책",
    ]


# ============================================
# 도구 3: Execute Cypher Query
# ============================================

# [이 파일에서 정의] 도구 3. Cypher 실행 -> 결과 글
# 주의: LLM 이 만든 쿼리를 검사 없이 쓰기 가능 모드(routing_ 기본 WRITE)로 실행한다. "모든 노드를 지워줘" 도 실행될 수 있다
#       routing_=neo4j.RoutingControl.READ 나 읽기 전용 계정으로 막을 수 있다 (GUIDE 생각해 볼 점 1)
# 주의: docstring 의 "최대 20개 레코드" 와 달리 코드는 결과를 전부 글로 만든다 (GUIDE 생각해 볼 점 2)
@tool(parse_docstring=True)
def execute_cypher_query(cypher_query: str) -> str:
    """Neo4j에서 Cypher 쿼리를 실행하고 결과를 반환합니다.
    Text2Cypher 검색방식 사용시 generate_cypher_query가 생성한 쿼리를 실행합니다.

    Args:
        cypher_query: 실행할 Cypher 쿼리 문자열

    Returns:
        쿼리 실행 결과를 포맷팅한 텍스트 (최대 20개 레코드)
    """
    driver, _, _ = initialize_tools()

    try:
        result = driver.execute_query(cypher_query)

        # 빈 리스트는 거짓 -> 결과 0건이면 성공 메시지 (오류와 구분되게)
        if not result.records:
            return "쿼리 실행 성공. 결과가 없습니다."

        # 결과 포맷팅
        output = ["=== 쿼리 실행 결과 ===\n"]
        output.append(f"총 {len(result.records)}개의 레코드\n")

        for idx, record in enumerate(result.records, 1):
            output.append(f"[{idx}]")
            # record.keys(): RETURN 의 열 이름들. record[key] 로 값. 노드 값은 str 로 찍히면 <Node element_id=... labels=... properties=...> 모양이 된다
            for key in record.keys():
                value = record[key]
                output.append(f"  {key}: {value}")
            output.append("")

        return "\n".join(output)

    except Exception as e:
        # 오류 글에 실행하려던 쿼리를 같이 넣는다 -> 에이전트가 무엇을 고쳐야 할지 보고 다시 시도할 수 있다
        return f"쿼리 실행 중 오류 발생: {str(e)}\n\n실행하려던 쿼리:\n{cypher_query}"


# ============================================
# 도구 4: Vector Search
# ============================================

# [이 파일에서 정의] 도구 4. 벡터 검색 + 그래프 확장
# [입력] question, top_k (기본 5. Args 설명과 기본값이 LLM 에 보내는 인자 스키마에 들어간다)
@tool(parse_docstring=True)
def vector_search(question: str, top_k: int = 5) -> str:
    """의미 기반 벡터 검색을 수행하고 그래프 컨텍스트를 자동으로 확장합니다.
    "~와 관련 내용 찾아줘"와 같은 개방형 질문에 적합합니다.

    Args:
        question: 검색할 자연어 질문
        top_k: 반환할 최대 결과 개수 (기본값: 5)

    Returns:
        검색된 텍스트와 관련 컨텍스트를 포함한 결과
    """
    # 반환값을 안 받고 부르기만 한다 -> 전역 _vectorcypher_retriever 가 준비된다
    initialize_tools()

    try:
        # VectorCypher 검색 수행
        # retriever.search(query_text=..., top_k=...)
        # [출처] 외부 라이브러리 neo4j-graphrag
        # 내부 (소스 확인): embedder 로 질문 -> 벡터 -> 벡터 인덱스 검색 + retrieval_query 를 읽기 전용으로 실행 -> Record 마다 format_result
        # [반환] RetrieverResult. .items: RetrieverResultItem 리스트 (.content 가 format_result 가 만든 글)
        results = _vectorcypher_retriever.search(
            query_text=question,
            top_k=top_k
        )

        if not results.items:
            return "검색 결과가 없습니다."

        # 결과 포맷팅
        output = [f"=== 벡터 검색 결과 (총 {len(results.items)}개) ===\n"]

        for idx, item in enumerate(results.items, 1):
            output.append(f"[검색 결과 {idx}]")
            output.append(item.content)
            # "-" * 50: 글 곱하기 = 50번 반복한 구분선
            output.append("-" * 50)

        return "\n".join(output)

    except Exception as e:
        return f"벡터 검색 중 오류 발생: {str(e)}"


# [이 파일에서 정의] 도구 4개 리스트. main.py 가 create_agent(tools=...) 에 넘긴다
def get_all_tools():
    return [
        schema_introspection,
        generate_cypher_query,
        execute_cypher_query,
        vector_search
    ]


# 직접 실행할 때만: 도구를 에이전트 없이 하나씩 테스트 (도구가 틀렸는지, LLM 판단이 틀렸는지 나눠 보려고)
if __name__ == "__main__":
    print("=" * 70)
    print("GraphRAG 도구 테스트")
    print("=" * 70)
    print()

    try:
        initialize_tools()
        print()
    # 주의: 초기화 실패 이유(e)를 출력하지 않고 바로 끝낸다. 무엇이 잘못됐는지 알 수 없다 (print(e) 를 넣으면 좋다)
    # exit(1): 프로그램 종료 (1 = 실패 코드). exit 는 대화형용 내장 이름이라 스크립트에서는 sys.exit 가 관례
    except Exception as e:
        exit(1)

    # 테스트할 도구와 입력 파라미터
    # 딕셔너리 리스트: 도구 객체와 넘길 인자 딕셔너리
    tests = [
        {
            "tool": schema_introspection,
            "args": {},
        },
        {
            "tool": generate_cypher_query,
            "args": {"question": "OpenAI에 대해 알려줘"},
        },
        {
            "tool": execute_cypher_query,
            "args": {"cypher_query": "MATCH (n) RETURN n LIMIT 5"},
        },
        {
            "tool": vector_search,
            "args": {"question": "OpenAI 관련 내용 요약해줘", "top_k": 3},
        },
    ]

    for idx, test in enumerate(tests, 1):
        print("\n" + "=" * 70)
        print("=" * 70)
        print(f"도구: {test['tool'].name}")
        print(f"파라미터: {test['args']}")
        print("-" * 70)

        try:
            # tool.invoke(인자 딕셔너리): [출처] langchain-core BaseTool. 인자를 스키마로 검증한 뒤 원래 함수를 부른다 [반환] 함수의 반환값 (여기서는 글)
            # 에이전트도 내부에서 이 방식으로 도구를 부른다
            result = test['tool'].invoke(test['args'])
            print("\n실행 결과:")
            print(result)
        except Exception as e:
            print(f"\n오류 발생: {str(e)}")

        print()