"""[1단계: 읽기] graphrag_qdrant.py (Qdrant 로 비슷한 문장을 찾고, Neo4j 그래프로 목차/같은 Chunk/엔티티 기반 확장 문장을 모아 LLM 이 답변) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
주석 속 "N줄" 은 원본 파일의 줄 번호다 (이 주석본의 줄 번호와 다르다).
neo4j-graphrag 와 qdrant-client 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1, qdrant-client 1.17.1, neo4j 5.28.3)로 확인했다.

전제: ingest_to_qdrant.py 로 Qdrant 컬렉션에 점(벡터 + payload.element_id)이 들어 있어야 한다.
      Neo4j 에는 pdf2kg.py + pdf2kg_2.py 의 TextElement, Chunk, TOC, 엔티티(HAS_ENTITY) 가 있어야 한다.
      .env 에 NEO4J_*, OPENAI_API_KEY, QDRANT_URL, QDRANT_KEY, (선택) QDRANT_COLLECTION 필요.

흐름 (임베딩 1번 + LLM 1번, 질문마다 반복)
  질문 (키보드 입력)
    -> [QdrantNeo4jRetriever] 질문 임베딩 -> Qdrant query_points(limit=top_k, payload 는 element_id 만)
         -> [(element_id, score), ...] 짝 리스트
    -> Neo4j 에서 실행되는 Cypher (소스 확인)
         UNWIND $match_params AS match_param
         WITH match_param[0] AS match_id_value, match_param[1] AS score
         MATCH (node:TextElement) WHERE node[$id_property] = match_id_value
         + 이 파일의 retrieval_query (node -> Chunk -> TOC/부모 TOC, 같은 Chunk 문장, 엔티티, 엔티티를 공유하는 다른 Chunk 문장)
    -> Record 마다 format_retrieval_result -> RetrieverResultItem(읽기 좋은 글, metadata 에 원본)
    -> [GraphRAG] content 들을 줄바꿈으로 이어 {context} 에 -> 긴 답변 프롬프트 -> LLM(gpt-4o) -> 2부 구성 답변

vectorcypher(법령)와 구조가 같다. 다른 점은 벡터가 Neo4j 가 아니라 Qdrant 에 있다는 것. 둘을 잇는 열쇠는 element_id 하나.

읽는 순서 권장: __main__ (570줄) -> create_retriever (retrieval_query) -> format_retrieval_result -> create_graphrag_pipeline -> execute_graphrag_query
실행 위치: part3/vectorcypher_qdrant  ->  python learning/step1_graphrag_qdrant_annotated.py   (대화형. q 또는 exit 로 종료)
"""

# [출처] 표준 라이브러리 os. 환경변수 읽기
import os
# [출처] 표준 라이브러리 typing. 타입 힌트용 이름
#   Optional[str]: str 또는 None / Dict[str, Any]: 키는 str, 값은 아무거나인 딕셔너리 / Any: 아무 타입
from typing import Optional, Dict, Any

# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 qdrant-client
from qdrant_client import QdrantClient

# [출처] 외부 라이브러리 neo4j-graphrag (qdrant 추가 설치 필요: neo4j-graphrag[qdrant])
# QdrantNeo4jRetriever: 벡터 검색은 Qdrant 에서, 그 뒤 그래프 확장은 Neo4j 에서 하는 검색기
from neo4j_graphrag.retrievers import QdrantNeo4jRetriever
# GraphRAG: 검색 + 프롬프트 + LLM 파이프라인 / RagTemplate: 답변 프롬프트 틀
from neo4j_graphrag.generation import GraphRAG, RagTemplate
# OpenAILLM: OpenAI 채팅 모델 감싸개
from neo4j_graphrag.llm import OpenAILLM
# OpenAIEmbeddings: 글 -> 벡터
from neo4j_graphrag.embeddings import OpenAIEmbeddings
# RetrieverResultItem: 검색 결과 한 건 (content 글 + metadata 딕셔너리). 아래 포맷터가 직접 만든다
from neo4j_graphrag.types import RetrieverResultItem
# neo4j 모듈 전체를 import. 53줄 타입 힌트 neo4j.Record 에 쓰려고
import neo4j

# .env 를 환경변수로 등록
load_dotenv()


# ============================================
# 클라이언트 생성
# ============================================

# [이 파일에서 정의] Neo4j 드라이버 생성 + 연결 확인 [반환] Driver (ingest_to_qdrant.py 와 같은 함수)
def create_neo4j_driver():
    """Neo4j 드라이버 생성"""
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    if not all([uri, username, password]):
        raise ValueError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD 환경 변수를 설정해주세요.")

    driver = GraphDatabase.driver(uri, auth=(username, password))
    driver.verify_connectivity()
    print(f"Neo4j 연결 성공: {uri}")
    return driver


# [이 파일에서 정의] QdrantClient 생성
# 주의: QdrantClient(...) 는 만들 때 접속을 확인하지 않는다 (소스 확인). 46줄 "연결 성공" 은 실제 확인이 아니고, 첫 검색 때 에러가 날 수 있다
def create_qdrant_client():
    """Qdrant 클라이언트 생성"""
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_KEY")

    if not url:
        raise ValueError("QDRANT_URL 환경 변수를 설정해주세요.")

    client = QdrantClient(url=url, api_key=api_key)
    print(f"Qdrant 연결 성공: {url}")
    return client

# ============================================
# Result Formatter - 검색 결과 정제
# ============================================

# [이 파일에서 정의] Neo4j Record 하나 -> RetrieverResultItem (검색기의 result_formatter 로 넘긴다)
# record: neo4j.Record -> RetrieverResultItem: 매개변수 타입 힌트와 "-> 반환 타입" 힌트
# [입력] record: retrieval_query 의 RETURN 열(element_id, content, page, toc_*, parent_hierarchy, entities, base_context, expanded_context, expanded_chunks, score)을 가진 한 행
# [반환] content = 사람/LLM 이 읽기 좋은 여러 줄 글, metadata = 원본 값들
# [왜] 기본 포맷은 str(Record) 라서 읽기 어렵다. vectorsearch 의 ast.literal_eval 되돌리기 문제를 처음부터 피하는 방법
def format_retrieval_result(record: neo4j.Record) -> RetrieverResultItem:
    """
    Neo4j Record를 RetrieverResultItem으로 변환하여 결과 정제

    Args:
        record: Neo4j Record 객체

    Returns:
        RetrieverResultItem: 정제된 검색 결과
    """
    # 기본 정보
    # 줄을 리스트에 모았다가 126줄에서 "\n".join 으로 한 번에 잇는다
    content_parts = []

    # 1. 핵심 내용
    # record.get("content", ""): [출처] neo4j. 기본값 "" 은 그 "열이 없을 때만" 쓰인다 (소스 확인).
    # RETURN 에 열이 항상 있으므로, 값이 null 이면 "" 가 아니라 None 이 나온다 -> "내용: None" 처럼 출력될 수 있다
    content = record.get("content", "")
    page = record.get("page", "")
    content_parts.append(f"내용: {content}")
    content_parts.append(f"페이지: {page}")

    # 2. TOC 정보 (있는 경우)
    toc_title = record.get("toc_title")
    # if toc_title: None 이나 빈 글이면 거짓 -> 섹션 줄을 건너뛴다
    if toc_title:
        toc_level = record.get("toc_level", "")
        toc_page = record.get("toc_page_start", "")
        # f"{'  ' * (toc_level - 1)}...": 레벨만큼 공백 2칸씩 들여쓰기 (레벨 1 은 0칸)
        # 주의: toc_title 은 있는데 toc.level 이 null 이면 None - 1 에서 TypeError 가 난다 (75줄 기본값 "" 도 열이 없을 때만 쓰인다)
        content_parts.append(f"섹션: {'  ' * (toc_level - 1)}{toc_title} (p.{toc_page})")

    # 3. 부모 계층 구조 (있는 경우)
    # parent_hierarchy: Cypher 의 맵 리스트 -> 파이썬에서는 딕셔너리 리스트
    parent_hierarchy = record.get("parent_hierarchy", [])
    if parent_hierarchy:
        content_parts.append("\n문서 계층:")
        # sorted(리스트, key=함수): [출처] 파이썬 기본. key 함수가 돌려준 값 기준으로 정렬한 "새" 리스트
        # lambda x: x.get('level', 0): 이름 없는 한 줄 함수. "x 를 받아 x 의 level 을 돌려준다" -> 상위 목차(레벨 작은 것)부터
        for parent in sorted(parent_hierarchy, key=lambda x: x.get('level', 0)):
            level = parent.get('level', 0)
            title = parent.get('title', '')
            page_start = parent.get('page_start', '')
            # 주의: 부모 TOC 의 level 이 null 이면 dict.get 의 기본값 0 이 아니라 None 이 나와(키는 있으므로) TypeError 가 날 수 있다
            content_parts.append(f"  {'  ' * (level - 1)}└─ {title} (p.{page_start})")

    # 4. 연결된 엔티티 (있는 경우)
    entities = record.get("entities", [])
    if entities:
        content_parts.append("\n연결된 엔티티:")
        # 유형별로 묶기: {"Company": ["LG AI연구원", ...], "AIModel": [...]} 모양의 딕셔너리를 만든다
        entity_groups = {}
        for entity in entities:
            entity_type = entity.get('type', 'Unknown')
            entity_name = entity.get('name', 'N/A')
            # 처음 보는 유형이면 빈 리스트를 먼저 만든다 (entity_groups.setdefault(유형, []).append(이름) 한 줄로도 된다)
            if entity_type not in entity_groups:
                entity_groups[entity_type] = []
            entity_groups[entity_type].append(entity_name)

        # 딕셔너리.items(): (키, 값) 짝을 하나씩 / ', '.join(names): 이름들을 쉼표로 이어 붙인 글
        for entity_type, names in entity_groups.items():
            content_parts.append(f"  • {entity_type}: {', '.join(names)}")

    # 5. 기본 컨텍스트 (같은 섹션의 모든 관련 문장)
    # 같은 Chunk 의 모든 문장 (검색된 문장 자신도 포함된다)
    base_context = record.get("base_context", [])
    if base_context:
        content_parts.append(f"\n같은 섹션의 관련 문장 ({len(base_context)}개):")
        for idx, item in enumerate(base_context, 1):
            item_content = item.get('content', '')
            content_parts.append(f"  [{idx}] {item_content}")

    # 6. 확장 컨텍스트 (엔티티 기반으로 확장된 모든 문장)
    # 엔티티를 공유하는 다른 Chunk 의 문장들
    # 주의: 여기서는 content 만 출력한다. 프롬프트가 쓰라고 하는 source_toc_title, page 는 컨텍스트 글에 들어가지 않는다 (metadata 에만 있다)
    expanded_context = record.get("expanded_context", [])
    if expanded_context:
        content_parts.append(f"\n엔티티 기반 확장 문장 ({len(expanded_context)}개):")
        for idx, item in enumerate(expanded_context, 1):
            item_content = item.get('content', '')

            content_parts.append(f"  [{idx}] {item_content}")

    # 7. 유사도 점수
    # score: Qdrant 가 준 유사도 (cosine 이면 클수록 비슷)
    score = record.get("score", 0.0)
    content_parts.append(f"\n유사도: {score:.4f}")

    # 최종 문자열 생성
    formatted_content = "\n".join(content_parts)

    # Metadata 구성 (원본 데이터도 함께 보관)
    # metadata: LLM 에는 안 가고 결과 객체에만 남는 원본 데이터 (화면 출처 표시, 평가용)
    metadata = {
        "element_id": record.get("element_id"),
        "chunk_id": record.get("chunk_id"),
        "toc_id": record.get("toc_id"),
        "page": page,
        "score": score,
        # 상세 정보는 metadata에 보관
        "entities": entities,
        "base_context": base_context,
        "expanded_context": expanded_context,
        "parent_hierarchy": parent_hierarchy
    }

    # RetrieverResultItem(content=..., metadata=...)
    # [출처] 외부 라이브러리 neo4j-graphrag (pydantic 모델) [반환] 결과 한 건. GraphRAG 는 이 content 만 컨텍스트로 쓴다
    return RetrieverResultItem(
        content=formatted_content,
        metadata=metadata
    )


# ============================================
# QdrantNeo4jRetriever 생성
# ============================================

# [이 파일에서 정의] retrieval_query 를 정의하고 QdrantNeo4jRetriever 를 만든다
# collection_name: Optional[str] = None: 안 주면 아래에서 환경변수로 채운다
def create_retriever(
    neo4j_driver,
    qdrant_client: QdrantClient,
    embedder,
    collection_name: Optional[str] = None
) -> QdrantNeo4jRetriever:
    """
    QdrantNeo4jRetriever 생성

    Qdrant에서 벡터 검색 → Neo4j에서 그래프 컨텍스트 확장

    Args:
        neo4j_driver: Neo4j 드라이버
        qdrant_client: Qdrant 클라이언트
        embedder: OpenAI Embeddings
        collection_name: Qdrant 컬렉션 이름 (기본값: 환경변수 QDRANT_COLLECTION)

    Returns:
        QdrantNeo4jRetriever 인스턴스
    """
    # 환경변수에서 컬렉션 이름 읽기
    # None 이면 환경변수 QDRANT_COLLECTION, 그것도 없으면 "pdf2kg"
    if collection_name is None:
        collection_name = os.getenv("QDRANT_COLLECTION", "pdf2kg")

    # HAS_ENTITY 기반 컨텍스트 확장 Cypher 쿼리
    # retrieval_query: Qdrant 결과로 찾은 node(TextElement)와 score 에서 출발하는 Cypher (여러 줄 문자열)
    # 번호별 뜻
    #   1. MATCH (chunk:Chunk)-[:HAS_ELEMENT]->(node) : 문장이 속한 Chunk. OPTIONAL 이 아니라서 Chunk 가 없는 문장은 결과에서 빠진다
    #   2. OPTIONAL MATCH (toc)-[:HAS_CHUNK]->(chunk) : 그 Chunk 의 목차
    #   3. (parent_toc)-[:HAS_CHILD*]->(toc) : * 는 가변 길이 경로. 부모, 조부모 ... 목차를 모두
    #   4. 같은 Chunk 의 모든 TextElement
    #   5. Chunk 의 엔티티 (레이블은 정하지 않음: 어떤 노드든)
    #   WITH ... collect(DISTINCT ...) : 여기서 한 번 모아 node 당 한 행으로 줄인다 (행 폭발을 중간에 끊는다)
    #   6. 같은 엔티티를 가진 "다른" Chunk : WHERE shared_entity IN entities (리스트 안에 있나) AND other_chunk <> chunk
    #   7. 그 Chunk 들의 문장과 목차 -> 다시 collect
    #   8. RETURN: [x IN 리스트 | {...}] 은 Cypher 의 리스트 컴프리헨션 (파이썬의 [... for x in ...] 과 같은 일)
    #      labels(e)[0]: 첫 번째 레이블을 유형으로 / coalesce(a, b, 'N/A'): null 이 아닌 첫 값
    # 주의: 확장 크기에 상한이 없다. 흔한 엔티티를 공유하는 Chunk 가 많으면 expanded_context 가 매우 길어져 프롬프트가 커진다
    # 주의: 맨 끝에 ORDER BY score DESC 가 없다. 중간의 집계(WITH ... collect) 뒤라서 Qdrant 의 유사도 순서가 유지된다는 보장은 없을 수 있다
    # 주의: 라이브러리가 붙이는 WHERE node[$id_property] = ... 는 속성 이름을 매개변수로 받는 방식이라 element_id 인덱스를 못 탈 수 있다 (문장이 많으면 느릴 수 있다)
    retrieval_query = """
    // node = Qdrant에서 찾은 TextElement
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

    // 6. 같은 엔티티를 공유하는 다른 Chunk들 찾기 (HAS_ENTITY가 있는 경우만)
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
        // 검색된 TextElement 정보
        node.element_id AS element_id,
        node.content AS content,
        node.page AS page,

        // Chunk 정보
        chunk.chunk_id AS chunk_id,

        // TOC 정보
        toc.toc_id AS toc_id,
        toc.title AS toc_title,
        toc.level AS toc_level,
        toc.page_start AS toc_page_start,

        // 부모 TOC 계층 구조
        [pt IN parent_tocs | {
            toc_id: pt.toc_id,
            title: pt.title,
            level: pt.level,
            page_start: pt.page_start
        }] AS parent_hierarchy,

        // 연결된 엔티티 정보
        [e IN entities | {
            type: labels(e)[0],
            name: coalesce(e.name, e.title, 'N/A')
        }] AS entities,

        // 기본 컨텍스트 (현재 Chunk의 TextElement)
        [be IN base_elements | {
            element_id: be.element_id,
            content: be.content,
            page: be.page
        }] AS base_context,

        // 확장된 컨텍스트 (엔티티 기반 확장된 TextElement + 출처 TOC 정보)
        [item IN expanded_elements_with_toc WHERE item.element IS NOT NULL | {
            element_id: item.element.element_id,
            content: item.element.content,
            page: item.element.page,
            source_toc_title: item.toc.title,
            source_toc_page: item.toc.page_start,
            source_toc_level: item.toc.level
        }] AS expanded_context,

        // 확장된 Chunk 정보
        [ec IN expanded_chunks | {
            chunk_id: ec.chunk_id
        }] AS expanded_chunks,

        score
    """

    # QdrantNeo4jRetriever(driver=..., client=..., collection_name=..., id_property_external=..., id_property_neo4j=...,
    #                      embedder=..., node_label_neo4j=..., retrieval_query=..., result_formatter=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] client, collection_name: 검색할 Qdrant 컬렉션
    #        id_property_external: Qdrant payload 의 열쇠 이름 / id_property_neo4j: Neo4j 노드의 열쇠 속성 이름
    #        node_label_neo4j: MATCH (node:TextElement) 의 레이블 (이스케이프하지 않고 그대로 붙인다)
    #        retrieval_query: 위 Cypher / result_formatter: 53줄 함수 (Record -> RetrieverResultItem)
    # [반환] 검색기 객체. .search(query_text=..., top_k=...) -> RetrieverResult
    # 내부 (소스 확인)
    #   - Neo4j 쪽 버전 확인이나 인덱스 확인을 하지 않는다 (Neo4j 에 벡터 인덱스가 없어도 된다)
    #   - 검색 때: embed_query(질문) -> client.query_points(collection_name, query=질문벡터, limit=top_k, with_payload=["element_id"])
    #             -> 점마다 (payload["element_id"] (없으면 point.id), point.score) 짝 -> Neo4j 쿼리(읽기 전용) -> 포맷터
    #   - payload 의 content, toc_title 등은 요청하지 않는다. 내용은 Neo4j 에서 다시 읽는다
    #   - 결과 metadata 에는 "__retriever" 만 들어간다
    retriever = QdrantNeo4jRetriever(
        driver=neo4j_driver,
        client=qdrant_client,
        collection_name=collection_name,
        # Qdrant payload의 element_id → Neo4j TextElement.element_id 매핑
        id_property_external="element_id",
        id_property_neo4j="element_id",
        embedder=embedder,
        node_label_neo4j="TextElement",
        retrieval_query=retrieval_query,
        result_formatter=format_retrieval_result,
    )

    # f-string 으로 컬렉션 이름 출력
    print(f"QdrantNeo4jRetriever 생성 완료 (컬렉션: {collection_name})")
    return retriever


# ============================================
# GraphRAG 파이프라인 생성
# ============================================

# [이 파일에서 정의] 답변 프롬프트 + 검색기 + LLM 으로 GraphRAG 를 만든다
# retriever: QdrantNeo4jRetriever, llm: 매개변수 타입 힌트 (llm 은 힌트 없음) / -> GraphRAG: 반환 타입 힌트
def create_graphrag_pipeline(
    retriever: QdrantNeo4jRetriever,
    llm
) -> GraphRAG:
    """
    GraphRAG 파이프라인 생성

    Args:
        retriever: QdrantNeo4jRetriever
        llm: OpenAI LLM

    Returns:
        GraphRAG 인스턴스
    """
    # 커스텀 프롬프트 템플릿
    # RagTemplate(template=긴 글, expected_inputs=["context", "query_text"])
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] template: {query_text}, {context} 자리가 있는 프롬프트. 라이브러리가 template.format(...) 으로 채운다
    #        그래서 글자 그대로의 중괄호는 {{ }} 로 두 번 쓴다 (324, 328줄 예시의 {{"type": ...}} -> LLM 에는 {"type": ...} 로 보인다)
    # [왜] 답변을 [파트 1] 본문 + [파트 2] "함께 보면 이해가 쉬워지는 정보" 로 고정하고, 지어내기를 막는 규칙을 많이 둔다
    # 주의: 프롬프트는 컨텍스트에 content, toc_title, entities, base_context, expanded_context, source_toc_title 같은 "필드 이름" 이 있다고 설명하지만,
    #       실제 컨텍스트는 format_retrieval_result 가 만든 "내용:", "섹션:", "연결된 엔티티:", "엔티티 기반 확장 문장" 같은 한글 글이다.
    #       특히 확장 문장의 source_toc_title, 페이지는 글에 없어서 LLM 이 출처를 정확히 적기 어려울 수 있다
    # 주의: 규칙이 많고 반복된다 (예: 볼드체 규칙). 길수록 일부 규칙이 지켜지지 않을 수 있다
    prompt_template = RagTemplate(
        template="""
당신은 PDF 문서 분석 전문 AI 어시스턴트입니다.
제공된 컨텍스트는 단순한 텍스트가 아닌, **문서의 계층적 구조(TOC, 섹션, 페이지)**와 **같은 주제/모델/회사로 연결된 관련 섹션들의 정보**를 포함한 GraphRAG 검색 결과입니다.

<context_structure>
컨텍스트에는 다음과 같은 구조화된 정보가 포함되어 있습니다:

**각 검색 결과 항목마다 제공되는 필드:**
1. **content**: 검색된 핵심 텍스트
2. **toc_title, page**: 핵심 텍스트가 속한 섹션명과 페이지 (참고용이며, 답변에서는 섹션명 대신 내용을 설명)
3. **entities**: 이 Chunk와 그래프 관계(HAS_ENTITY)로 연결된 **공통 엔티티들** [type, name]
   - 예: [{{"type": "Company", "name": "LG AI연구원"}}, {{"type": "AIModel", "name": "K-EXAONE"}}]
   - **GraphRAG의 핵심**: 이 공통 엔티티들을 기준으로 다른 관련 섹션들이 자동 확장됨
4. **base_context**: 같은 Chunk 내 관련 TextElement들 [content, page]
5. **expanded_context**: **entities의 공통 엔티티를 기준으로 확장된 다른 섹션들의 텍스트**
   - 각 항목: {{content, page, source_toc_title, source_toc_page, source_toc_level}}
   - 같은 엔티티(회사/모델/기술)를 공유하는 다른 섹션의 정보가 자동으로 포함됨
   - **중요**: source_toc_title은 참고용이며, 답변에서는 content를 읽고 핵심 내용을 설명문으로 작성
</context_structure>

<output_format>
**답변은 크게 2개 파트로 구성됩니다:**

<[파트 1] 본문 답변>
- 질문에 대한 직접 답변과 관련 주제로 연결된 확장 지식을 자연스럽게 통합하여 서술
- 작성 순서:
  a) 먼저 질문과 직접 관련된 content, base_context 정보를 서술 (구체적 내용: 기술명, 수치, 벤치마크 등 포함)
  b) **모든 검색 결과의 entities 필드를 종합**하여 공통 엔티티를 파악하고, expanded_context의 content로 이들에 대한 확장 지식 추가
  c) **entities 필드의 엔티티들**(회사, AI모델, 기술 등) 중심으로 정보를 자연스럽게 그룹화하여 통합
     - **질문에 없던 엔티티도 적극 활용** (예: "업스테이지" 질문 → entities에 K-EXAONE, Solar Open100B도 있으면 이들을 비교)
  d) 각 문단이나 주요 정보 블록 아래 출처 표기
     - 줄바꿈 후 블록쿼트 형식으로 표기: `>[출처] 'TOC 섹션명'/페이지 X`
     - expanded_context 사용 시 source_toc_title 명시
- **마크다운 강조**: entities 필드의 엔티티는 **볼드체**로 강조
- **중요**: 메타 헤더(예: "핵심 답변", "확장 지식")를 출력하지 말고, 내용만 자연스럽게 흐르도록 작성
</[파트 1] 본문 답변>

<[파트 2] 정보 연결 구조 (Knowledge Graph Trace)>
<반드시 작성> 본문 답변 작성 후 → 구분선 `---` 및 헤더 "**[함께 보면 이해가 쉬워지는 정보]**" </반드시 작성>

작성 흐름:

a) **도입 문단**:
   - "이번 답변에서 함께 언급된 내용을 바탕으로, **[공통 엔티티]** 관점에서 이어서 살펴보면 좋은 내용을 정리해드릴게요."
   - **공통 엔티티 선택 방법 - GraphRAG의 확장 인사이트 제공**:
     * **모든 검색 결과의 entities 필드를 종합**하여 반복 등장하는 엔티티를 파악
     * **질문에 직접 언급되지 않았어도**, 여러 검색 결과의 entities에 공통으로 등장하면 **확장 주제로 활용** (이것이 GraphRAG의 가치)
     * **목표**: 질문의 직접 답변만이 아닌, 그래프로 연결된 관련 엔티티들을 통해 더 넓은 맥락 제공
     * expanded_context의 content는 이 엔티티들에 대한 구체적 설명으로 활용
   - **선택한 공통 엔티티는 볼드체로 강조**

b) **직접 관련 내용 서술**:
   - "먼저, [핵심 내용 설명](p.X)..."으로 시작
   - 초기 검색된 항목들의 content를 읽고 핵심을 자연스럽게 서술
   - **검색 결과에 실제로 등장하는 내용만 언급** (지어내지 말 것)
   - 주요 엔티티(모델명, 회사명 등)는 볼드체 없이 자연스럽게 언급
   - 여러 항목이 있다면 자연스럽게 연결하여 문단으로 작성

c) **연결 이유 설명**:
   - "왜 이 정보들이 같이 나왔나요?" 질문으로 자연스럽게 전환
   - **모든 검색 결과의 entities 필드에서 공통으로 등장하는 엔티티들을 명시**
   - **예시**: "K-EXAONE, Solar Open100B, Mi:dm K 등 여러 국내 AI 모델들이 공통 엔티티로 연결되어 관련 정보들이 함께 검색되었습니다."
   - **질문에 없던 엔티티도 적극 활용** - 이것이 확장 인사이트
   - **entities 필드의 엔티티만 볼드체로 강조**

d) **확장 내용 서술**:
   - "이와 함께 [내용]도 주목할 만합니다..." 형식으로 자연스럽게 연결
   - **expanded_context의 content를 정확히 읽고**, 그 안에 실제로 언급된 내용만 설명문으로 작성
   - **절대 지어내지 말 것**: content에 없는 기술명, 수치, 개념을 창작하지 말 것
   - 페이지 번호 포함: (p.Y)
   - **content에 실제로 등장하는 강점이나 특징만 볼드체로 강조**

e) **추가 확장 내용** (있는 경우):
   - "추가로 함께 보면 좋은 내용은?" 질문으로 전환
   - 나머지 expanded_context의 content들을 **정확히 읽고** 자연스럽게 서술
   - **없는 내용을 추론하거나 창작하지 말 것**

f) **종합 정리**:
   - "결과적으로..." 또는 "이를 종합하면..." 으로 시작
   - **앞서 언급했던 실제 내용들만** 종합하여 핵심 메시지 정리
   - **content에 실제로 등장했던 개념만 볼드체로 강조** (새로운 개념 창작 금지)

**작성 원칙**:
- **구조화된 번호 금지**: "1.", "2.", "3." 대신 자연스러운 문단 흐름으로 작성
- **기술 용어 사용 금지**: "벡터 검색", "엔티티", "그래프 확장" 같은 시스템 용어 대신 자연어로 설명
- **섹션 제목 금지**: toc_title, source_toc_title을 그대로 쓰지 말고, content를 읽고 핵심을 파악하여 설명문으로 작성
- **절대 지어내지 말 것 - 검색 결과에 실제로 있는 내용만 사용**:
  * **entities 필드에 나열된 엔티티만이 공통 주제가 될 수 있음**
  * **expanded_context는 단지 보조 텍스트**: 여기서 새로운 엔티티나 주제를 찾으려 하지 말 것
  * expanded_context의 content에 실제로 명시된 내용만 서술
  * content에 없는 기술명, 수치, 개념, 모델명을 창작하지 말 것
  * **절대 금지**: content에서 반복 등장하는 개념을 찾아 주제로 만들기
- **볼드체 강조 원칙**:
  * **entities 필드의 엔티티만** 볼드체 강조 가능
  * expanded_context에 등장하는 다른 개체들은 볼드체 없이 자연스럽게 언급
  * 추상적 개념을 볼드체로 강조 절대 금지
- 확장 섹션이 없으면 d), e) 부분을 생략하고 c)에서 바로 f) 종합 정리로 이동
- **핵심**: 리스트나 구조가 아닌, 읽기 쉬운 자연스러운 설명문으로 작성
</[파트 2] 정보 연결 구조 (Knowledge Graph Trace)>
</output_format>

<guidelines>
**CRITICAL - 정보 출처 추적 규칙**:

**절대 금지**:
- 컨텍스트에 없는 섹션명, 주제, 모델명을 추측하거나 만들어내지 말 것
- expanded_context에 없는 섹션을 "추가 관련 내용"에 포함하지 말 것
- entities 리스트에 없는 항목을 언급하지 말 것

**반드시 준수**:
- **추가 관련 내용은 오직 expanded_context의 source_toc_title만 사용**
- **연결 이유는 모든 검색 결과의 entities 필드를 종합하여 공통 엔티티 활용**
  * 질문에 직접 언급 안된 엔티티도 적극 활용 (이것이 GraphRAG의 확장 인사이트)
- 각 확장 섹션이 어떤 entities 때문에 연결되었는지 명확히 추적
- 컨텍스트에 정보가 부족하면 "추가 관련 내용"을 억지로 만들지 말고 생략

**GraphRAG 핵심 원칙 - 반드시 준수**:
이 시스템은 단순 키워드 검색이 아닌 **GraphRAG**입니다. 검색된 모든 결과를 활용하여 확장된 지식을 제공해야 합니다.

**구체적 가이드라인**:

1. **모든 검색 결과(top_k개)를 반드시 답변에 포함 - GraphRAG의 확장 인사이트**
   - **절대 규칙**: 검색된 모든 항목의 정보를 언급할 것
   - **모든 검색 결과의 entities 필드를 종합**하여 공통 엔티티를 파악하고 활용
   - **질문에 직접 언급 안된 엔티티도 적극 활용** (예: "업스테이지" 질문 → entities에 K-EXAONE도 있으면 비교/대조 제공)
   - content만 요약하지 말고, base_context와 expanded_context를 적극 활용
   - 직접 관련성이 낮아 보이는 결과도 "entities 필드의 공통 엔티티"를 통해 연결된 이유를 설명하여 포함

2. **expanded_context를 적극 활용 - GraphRAG의 핵심 가치**
   - expanded_context는 **entities 필드의 공통 엔티티를 기준으로 확장된 관련 지식**
   - 단순 키워드 검색으로는 찾을 수 없는 연결된 정보 제공
   - 비교, 대조, 맥락 제공, 심화 설명 등에 활용
   - 각 확장 정보가 **어떤 entities(회사/모델/기술)**를 통해 연결되었는지 명시

3. **구체적인 정보를 빠짐없이 포함 - 절대 지어내지 말 것**
   - **content에 실제로 언급된** 기술명, 수치, 벤치마크 결과, 회사명, 모델명만 명시
   - **절대 금지**: content에 없는 숫자, 기술명, 성능 지표를 만들어내거나 추측하지 말 것
   - **모든 검색 결과의 entities 필드를 종합**하여 본문에 언급 (질문에 없던 엔티티도 적극 활용)

4. **각 문단마다 출처를 명시**
   - **entities 필드의 공통 엔티티**(회사/모델/기술) 중심으로 서로 다른 섹션의 정보를 자연스럽게 통합하여 서술
   - 각 정보 블록이나 문단 아래 줄바꿈 후 블록쿼트 형식으로 표기
   - 형식: `>[출처] 'TOC 섹션명'/페이지 X` 또는 `>[출처] 페이지 X`
   - toc_title과 page 정보를 활용하여 출처 명시
   - expanded_context의 경우 source_toc_title, source_toc_page를 활용

5. **답변 마지막에 정보 연결 이유를 사용자가 이해하기 쉽게 설명 - GraphRAG의 확장 인사이트**
   - **도입**: "이번 답변에서 함께 언급된 내용을 바탕으로, **[공통 엔티티]** 관점에서..."
     * 모든 검색 결과의 entities 필드를 종합하여 공통 엔티티 선택
     * 질문에 직접 언급 안된 엔티티도 적극 활용 - 이것이 확장 인사이트의 핵심
     * 절대 금지: "한국 AI 경쟁력" 같은 추상적 개념 창작
   - **직접 관련 내용**: 초기 검색 결과의 content에 실제로 있는 내용만 자연스럽게 서술
   - **연결 이유**: "왜 이 정보들이 같이 나왔나요?" 질문 후 entities 필드의 공통 엔티티들을 구체적으로 명시
   - **확장 내용**: expanded_context의 content는 추가 정보로만 활용 (새로운 엔티티를 찾지 말 것)
   - **추가 확장**: 나머지 expanded_context의 실제 내용 (선택적)
   - **종합 정리**: 앞서 언급된 실제 내용들만 종합하여 정리
   - **핵심**: 구조화된 리스트가 아닌, 읽기 쉬운 자연스러운 문단 형식으로 작성
</guidelines>

**CRITICAL - 핵심 원칙**
**반드시 수행**: 모든 검색 결과의 entities 필드를 종합하여 질문에 없던 엔티티도 적극 활용 (GraphRAG의 확장 인사이트 가치)
**절대 금지**: content에 없는 수치/기술명 창작, entities에 없는 추상적 개념 생성

<user_question>
{query_text}
</user_question>

<context>
{context}
</context>


답변:
""",
        expected_inputs=["context", "query_text"]
    )

    # GraphRAG(retriever=..., llm=..., prompt_template=...) [출처] neo4j-graphrag [반환] 파이프라인. .search(...) 로 실행
    rag = GraphRAG(
        retriever=retriever,
        llm=llm,
        prompt_template=prompt_template
    )

    return rag


# ============================================
# Main GraphRAG 쿼리 실행
# ============================================

# [이 파일에서 정의] 질문 하나 실행 -> 검색 결과와 답변 출력
# 주의: 반환 힌트는 Dict[str, Any] 지만 실제로 돌려주는 것은 RagResultModel 객체다 (힌트는 검사되지 않아 실행엔 문제 없음)
def execute_graphrag_query(
    rag: GraphRAG,
    query: str,
    top_k: int = 5,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    GraphRAG 쿼리 실행

    Args:
        rag: GraphRAG 인스턴스
        query: 사용자 질문
        top_k: 검색할 결과 개수
        verbose: 상세 출력 여부

    Returns:
        검색 결과 및 답변
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"질문: {query}")
        print(f"{'='*60}")

    # GraphRAG 검색 실행
    # rag.search(query_text=..., retriever_config={"top_k": ...}, return_context=True)
    # [반환] RagResultModel (.answer: 답변 글, .retriever_result: RetrieverResult)
    # 내부 (소스 확인): retriever.search(query_text=질문, top_k=...) -> context = "\n".join(item.content ...)
    #                   -> prompt_template.format(...) -> llm.invoke(...) -> answer
    # 검색 결과가 0건이어도 빈 컨텍스트로 LLM 을 부른다
    result = rag.search(
        query_text=query,
        retriever_config={"top_k": top_k},
        return_context=True  # 컨텍스트도 함께 반환
    )

    if verbose:
        # 검색 결과 출력
        print(f"\n{'='*60}")
        print(f"검색 결과")
        print(f"{'='*60}")

        # hasattr(...) and 값: return_context=True 로 불렀으므로 retriever_result 는 항상 있다. 방어용 확인
        if hasattr(result, 'retriever_result') and result.retriever_result:
            items = result.retriever_result.items if hasattr(result.retriever_result, 'items') else []

            if items:
                for idx, item in enumerate(items, 1):
                    print(f"\n{'─'*60}")
                    print(f"[검색 결과 {idx}]")
                    print(f"{'─'*60}")
                    # RetrieverResultItem 은 항상 content 가 있어 else 쪽은 실제로 거의 안 탄다
                    if hasattr(item, 'content'):
                        print(item.content)
                    else:
                        print(item)
                    print()
            else:
                print("검색된 항목이 없습니다.")
        else:
            print("검색 결과를 가져올 수 없습니다.")

        # 최종 답변 출력
        print(f"\n{'='*60}")
        print(f"최종 답변")
        print(f"{'='*60}")
        print(result.answer)

    return result


# ============================================
# 메인 함수
# ============================================

# 이 파일을 직접 실행할 때만 아래가 실행된다
if __name__ == "__main__":
    print("="*80)
    print("Qdrant + Neo4j GraphRAG")
    print("="*80)
    print()

    # try / except / finally
    try:
        # 1. 클라이언트 초기화
        print("[1/3] 클라이언트 초기화 중...")
        neo4j_driver = create_neo4j_driver()
        qdrant_client = create_qdrant_client()
        # 키가 있는지 확인만 하고 넘기지는 않는다. 아래 두 객체가 내부의 openai.OpenAI() 로 OPENAI_API_KEY 환경변수를 스스로 읽는다
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경 변수를 설정해주세요.")

        # OpenAIEmbeddings(model=...): 임베딩 모델은 ingest_to_qdrant.py 에서 쓴 것과 같아야 한다 (text-embedding-3-small, 1536차원)
        embedder = OpenAIEmbeddings(
            model="text-embedding-3-small"
        )

        # OpenAILLM(model_name=...): model_params 를 안 줬으므로 temperature 등은 OpenAI 기본값
        llm = OpenAILLM(
            model_name="gpt-4o"
        )

        print()

        # 2. Retriever 생성
        print("[2/3] QdrantNeo4jRetriever 생성 중...")
        # 컬렉션 이름은 ingest_to_qdrant.py 와 같은 규칙 (환경변수, 없으면 "pdf2kg")
        collection_name = os.getenv("QDRANT_COLLECTION", "pdf2kg")
        retriever = create_retriever(
            neo4j_driver=neo4j_driver,
            qdrant_client=qdrant_client,
            embedder=embedder,
            collection_name=collection_name
        )
        print()

        # 3. GraphRAG 파이프라인 생성
        print("[3/3] GraphRAG 파이프라인 생성 중...")
        rag = create_graphrag_pipeline(retriever=retriever, llm=llm)
        print()

        # 4. 대화형 GraphRAG 쿼리
        print(f"{'='*80}")
        print("GraphRAG 쿼리 실행")
        print(f"{'='*80}\n")

        # while True: [출처] 파이썬 기본. break 를 만날 때까지 계속 반복 (대화형 질문 루프)
        while True:
            print("-" * 80)
            # input(...).strip(): 키보드 입력 앞뒤 공백 제거
            query = input("질문을 입력하세요 (종료: 'q' 또는 'exit'): ").strip()

            # x in ['q', 'exit']: 둘 중 하나면 break 로 반복 종료
            if query.lower() in ['q', 'exit']:
                break

            # 빈 입력이면 continue: 아래를 건너뛰고 다음 반복으로
            if not query:
                print("질문을 입력해주세요!")
                continue

            # GraphRAG 실행
            # 결과는 함수 안에서 이미 출력한다. 반환값 result 는 여기서 쓰지 않는다
            result = execute_graphrag_query(
                rag=rag,
                query=query,
                top_k=5,
                verbose=True
            )
    # 주의: 에러 메시지만 출력한다 (traceback 이 안 보여 원인 찾기가 어렵다)
    except Exception as e:
        print(f"\n오류 발생: {e}")
    finally:
        # 주의: 579줄 create_neo4j_driver 에서 실패하면 neo4j_driver 변수가 없어 여기서 NameError 가 난다.
        #       ingest_to_qdrant.py 처럼 'neo4j_driver' in locals() 로 확인하면 안전하다
        neo4j_driver.close()
