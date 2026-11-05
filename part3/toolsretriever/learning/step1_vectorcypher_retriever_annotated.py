"""[1단계: 읽기] vectorcypher_retriever.py (벡터 검색 + 문서 구조/엔티티 확장 Cypher 검색기와 그 도구) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1)로 확인했다.

이 파일은 직접 실행하지 않는다 (__main__ 없음). main.py 의 create_tools_retriever 가
  create_vectorcypher_retriever -> create_vectorcypher_tool 을 부른다.

흐름 (VectorCypherRetriever = 벡터 검색 한 번 + 그 결과 노드에서 출발하는 Cypher 한 번)
  질문 -> 임베딩 -> TextElement 벡터 인덱스에서 top_k 개 (node, score)
    -> retrieval_query 가 node 마다 이어서 실행된다
         node 가 속한 Chunk -> 그 Chunk 의 TOC -> 상위 TOC 들 (문서 계층)
         같은 Chunk 의 다른 TextElement (base_context)
         Chunk 의 엔티티 (HAS_ENTITY) -> 같은 엔티티를 가진 다른 Chunk 의 TextElement (expanded_context)
    -> Record 하나 -> format_vectorcypher_result -> RetrieverResultItem(content=읽기 좋은 글, metadata=원본 값)
  part3/vectorcypher_qdrant 와 같은 확장 로직을 Qdrant 대신 Neo4j 벡터 인덱스로 한다.

읽는 순서 권장: create_vectorcypher_retriever -> get_vectorcypher_retrieval_query -> format_vectorcypher_result -> create_vectorcypher_tool
실행 위치: part3/toolsretriever 에서 PYTHONPATH=. python learning/step1_vectorcypher_retriever_annotated.py
  (함수 정의만 있어서 실행해도 아무것도 출력되지 않는다. 주석본은 import 용으로 쓰지 않는다)
"""

# [출처] 외부 라이브러리 neo4j. 여기서는 타입 힌트 neo4j.Record 에만 쓴다
import neo4j
# [출처] 외부 라이브러리 neo4j-graphrag. VectorCypherRetriever: 벡터 검색 뒤에 내가 쓴 Cypher(retrieval_query)를 이어 붙이는 검색기
from neo4j_graphrag.retrievers import VectorCypherRetriever
# RetrieverResultItem: 검색 결과 한 건 (content: LLM 에 보낼 글, metadata: 딕셔너리)
from neo4j_graphrag.types import RetrieverResultItem


# [이 파일에서 정의] 결과 포매터(result_formatter). Record 하나 -> RetrieverResultItem 하나
# (record: neo4j.Record) -> RetrieverResultItem : 타입 힌트. 실행에는 영향 없고 읽는 사람/편집기를 위한 표시
# [왜] 기본 포매터는 str(record) 를 그대로 content 로 쓴다. 중첩 리스트/맵이 섞인 긴 글이 되므로 사람이 읽기 좋은 글로 정리한다
def format_vectorcypher_result(record: neo4j.Record) -> RetrieverResultItem:
    """
    VectorCypher 검색 결과를 RetrieverResultItem으로 변환하여 정제

    Args:
        record: Neo4j Record 객체

    Returns:
        RetrieverResultItem: 정제된 검색 결과
    """
    # 기본 정보
    # 글 조각을 리스트에 모았다가 마지막에 "\n".join
    content_parts = []

    # 1. 핵심 내용
    # record.get("키", 기본값): Record 도 딕셔너리처럼 .get 을 쓸 수 있다. 키(RETURN 별칭)가 없으면 기본값
    # 주의: 키는 있는데 값이 null 이면 기본값이 아니라 None 이 나온다
    content = record.get("content", "")
    page = record.get("page", "")
    content_parts.append(f"내용: {content}")
    content_parts.append(f"페이지: {page}")

    # 2. TOC 정보 (있는 경우)
    # if toc_title: None 이나 빈 글이면 거짓 -> TOC 가 없는 Chunk 면 이 구역을 건너뛴다
    toc_title = record.get("toc_title")
    if toc_title:
        toc_level = record.get("toc_level", "")
        toc_page = record.get("toc_page_start", "")
        # "  " * (toc_level - 1): 문자열 * 정수 = 반복. 레벨 2 면 공백 2칸 들여쓰기
        # f"...{'  ' * (...)}..." : f-string 의 {} 안에는 식을 쓸 수 있다 (바깥이 큰따옴표라 안쪽은 작은따옴표)
        # 주의: toc_title 은 있는데 toc.level 이 null 이면 None - 1 에서 TypeError 가 날 수 있다
        content_parts.append(f"섹션: {'  ' * (toc_level - 1)}{toc_title} (p.{toc_page})")

    # 3. 부모 계층 구조 (있는 경우)
    # parent_hierarchy: 쿼리가 [pt IN parent_tocs | {...}] 로 만든 맵 리스트. 상위 목차들
    parent_hierarchy = record.get("parent_hierarchy", [])
    if parent_hierarchy:
        content_parts.append("\n문서 계층:")
        # sorted(리스트, key=lambda x: x.get('level', 0)): level 값 기준으로 정렬한 새 리스트
        # lambda x: 식 -> 이름 없는 한 줄 함수. 각 원소에서 정렬 기준을 꺼내는 데 쓴다
        for parent in sorted(parent_hierarchy, key=lambda x: x.get('level', 0)):
            level = parent.get('level', 0)
            title = parent.get('title', '')
            page_start = parent.get('page_start', '')
            # 레벨에 따라 들여쓰고 └─ 를 붙여 트리처럼 보이게
            content_parts.append(f"  {'  ' * (level - 1)}└─ {title} (p.{page_start})")

    # 4. 연결된 엔티티 (있는 경우)
    # entities: [{type: 레이블, name: 이름}, ...]. 같은 Chunk 와 HAS_ENTITY 로 연결된 도메인 엔티티 (pdf2kg_2 가 만든 것)
    entities = record.get("entities", [])
    if entities:
        content_parts.append("\n연결된 엔티티:")
        # {타입: [이름, ...]} 로 묶기. 예) {"Company": ["OpenAI", "LG AI연구원"], "AIModel": ["EXAONE"]}
        entity_groups = {}
        for entity in entities:
            entity_type = entity.get('type', 'Unknown')
            entity_name = entity.get('name', 'N/A')
            # 처음 보는 타입이면 빈 리스트부터 (dict.setdefault(k, []) 와 같은 효과)
            if entity_type not in entity_groups:
                entity_groups[entity_type] = []
            entity_groups[entity_type].append(entity_name)

        # dict.items(): (키, 값) 쌍을 차례로
        for entity_type, names in entity_groups.items():
            content_parts.append(f"  • {entity_type}: {', '.join(names)}")

    # 5. 기본 컨텍스트 (같은 섹션의 모든 관련 문장)
    # base_context: 같은 Chunk 안의 TextElement 들 (검색된 문장 자신도 포함된다)
    base_context = record.get("base_context", [])
    if base_context:
        content_parts.append(f"\n같은 섹션의 관련 문장 ({len(base_context)}개):")
        # enumerate(리스트, 1): (번호, 원소) 쌍. 두 번째 인자 1 = 번호를 1부터
        for idx, item in enumerate(base_context, 1):
            item_content = item.get('content', '')
            content_parts.append(f"  [{idx}] {item_content}")

    # 6. 확장 컨텍스트 (엔티티 기반으로 확장된 모든 문장)
    # expanded_context: 같은 엔티티를 공유하는 "다른" Chunk 의 TextElement 들 (GraphRAG 확장의 핵심)
    # 주의: 흔한 엔티티(예: "AI") 하나만 겹쳐도 많은 Chunk 가 딸려 와 글이 아주 길어질 수 있다. 개수 제한(LIMIT)이 없다
    expanded_context = record.get("expanded_context", [])
    if expanded_context:
        content_parts.append(f"\n엔티티 기반 확장 문장 ({len(expanded_context)}개):")
        for idx, item in enumerate(expanded_context, 1):
            item_content = item.get('content', '')
            content_parts.append(f"  [{idx}] {item_content}")

    # 7. 유사도 점수
    score = record.get("score", 0.0)
    # {score:.4f}: f-string 서식. 소수점 아래 4자리까지
    content_parts.append(f"\n유사도: {score:.4f}")

    # 최종 문자열 생성
    # 조각들을 줄바꿈으로 이어 content 글 완성
    formatted_content = "\n".join(content_parts)

    # Metadata 구성 (원본 데이터도 함께 보관)
    # metadata: 정리 전 원본 값을 그대로 보관 (LLM 에 보내는 글과 별도)
    # 참고 (소스 확인): ToolsRetriever 는 이 metadata 에 "tool": 도구이름 을 더해 다시 Record 로 감싸고,
    #      그 Record 를 str() 한 글을 최종 context 로 쓴다 -> 이 metadata 도 결국 답변 LLM 프롬프트에 함께 들어간다
    #      (content 와 metadata 에 같은 내용이 두 번 들어가 글이 길어진다)
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

    # RetrieverResultItem(content=..., metadata=...): [출처] neo4j-graphrag. 결과 한 건 객체를 만들어 반환
    return RetrieverResultItem(
        content=formatted_content,
        metadata=metadata
    )


# [이 파일에서 정의] retrieval_query 글을 돌려준다
# [반환] Cypher 문자열
def get_vectorcypher_retrieval_query():
    """VectorCypher을 위한 검색 쿼리 (벡터 검색 + 주변 관계)

    vectorcypher_qdrant와 동일한 로직 사용:
    HAS_ENTITY 기반으로 컨텍스트를 확장하여 관련 정보 수집
    """
    # retrieval_query: 벡터 검색 쿼리 뒤에 그대로 이어 붙는다 (소스 확인)
    #   앞부분(라이브러리가 만듦): CALL db.index.vector.queryNodes($vector_index_name, $top_k * $effective_search_ratio, $query_vector) YIELD node, score WITH node, score LIMIT $top_k
    #   그래서 이 글 안에서 node(찾은 TextElement), score(유사도) 변수를 바로 쓸 수 있다
    # 구역별 역할
    #   1~5: MATCH/OPTIONAL MATCH 로 Chunk, TOC, 상위 TOC(HAS_CHILD* = 1단계 이상 몇 단계든), 같은 Chunk 의 TextElement, 엔티티를 찾는다
    #        OPTIONAL MATCH: 없어도 행을 버리지 않고 null 로 채운다 (SQL 의 LEFT JOIN 과 비슷)
    #   WITH ... collect(DISTINCT ...): node 별로 한 행이 되도록 리스트로 모은다 (행이 곱해져 불어나는 것을 막는다)
    #   6~7: 같은 엔티티를 가진 다른 Chunk(other_chunk <> chunk) 와 그 TextElement, TOC 를 찾는다
    #   8 RETURN: [x IN 리스트 | {...}] 리스트 컴프리헨션(Cypher 문법)으로 맵 리스트를 만들고, AS 별칭이 위 포매터의 record.get 키가 된다
    # 주의: 1번이 MATCH(OPTIONAL 아님)라서 Chunk 와 HAS_ELEMENT 로 연결되지 않은 TextElement 는 결과에서 빠진다
    # 주의: base_element, expanded_element 모두 TextElement 만 본다. 같은 Chunk 의 TableElement 는 확장에 들어가지 않는다
    return """
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


# [이 파일에서 정의] VectorCypherRetriever 를 만든다
# [입력] index_name: TextElement 벡터 인덱스 이름 (텍스트 검색기와 같은 인덱스를 공유)
def create_vectorcypher_retriever(driver, embedder, index_name):
    """VectorCypher 검색 Retriever 생성 (텍스트 벡터 + 주변 관계)"""
    # VectorCypherRetriever(driver=..., index_name=..., retrieval_query=..., embedder=..., result_formatter=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] retrieval_query: 벡터 검색 뒤에 이어 붙일 Cypher / result_formatter: Record -> RetrieverResultItem 함수
    #        (함수를 "부르지 않고" 이름만 넘긴다. 괄호가 없다 -> 라이브러리가 결과마다 대신 부른다)
    # [반환] 검색기. search(query_text=..., top_k=5 기본) 때 질문 임베딩 -> 벡터 검색 + retrieval_query 를 읽기 전용(READ)으로 실행
    retriever = VectorCypherRetriever(
        driver=driver,
        index_name=index_name,
        retrieval_query=get_vectorcypher_retrieval_query(),
        embedder=embedder,
        result_formatter=format_vectorcypher_result
    )
    print("[3/4] VectorCypher 검색 Retriever 생성")
    return retriever


# [이 파일에서 정의] VectorCypherRetriever -> Tool "vectorcypher_context_search"
def create_vectorcypher_tool(retriever):
    """VectorCypherRetriever를 Tool로 변환"""

    # convert_to_tool: vector_retriever.py 설명 참고. 이 검색기는 query_params(객체) 매개변수가 하나 더 있어 입력 스키마에 들어간다
    tool = retriever.convert_to_tool(
        name="vectorcypher_context_search",
        # 도구 설명: "종합 정보", "흩어진 정보 모으기", "~에 대해 설명해줘" 같은 개방형 질문을 받도록 적었다
        # 주의: 예시 "OpenAI에 대해 관련 정보를 모두 찾아줘" 는 text2cypher 도구 예시("OpenAI와 관련된 모든 정보를 찾아줘" 예제, "OpenAI에 대해 알려줘")와 거의 같다.
        #       같은 질문에 두 도구가 동시에 또는 번갈아 골라질 수 있다
        description="""
        텍스트 검색과 함께 문맥 정보를 종합적으로 제공합니다.

        검색 결과에 포함되는 정보:
        - 검색된 텍스트 내용
        - 해당 텍스트가 속한 목차 정보 (장/절 제목)
        - 상위 목차 및 문서 구조
        - 관련 도메인 엔티티 (인물, 조직, 기술 등)
        - 엔티티 간 관계 및 확장 컨텍스트

        사용 시나리오:
        - 특정 엔티티에 대한 종합 정보가 필요할 때 (회사, 제품, 기술, 인물, 모델 등)
        - 문서 내 여러 곳에 흩어진 관련 정보를 한번에 모아야 할 때
        - 내용과 함께 문서 상의 위치를 알고 싶을 때
        - "~에 대해 설명해줘" 같은 개방형 질문

        예시:
        - "업스테이지의 Solar 모델 성능이 어떤가요?"
        - "ChatGPT Health에 대해 알려주세요"
        - "OpenAI에 대해 관련 정보를 모두 찾아줘"
        - "EXAONE 모델의 특징은 무엇인가요?"
        """
    )

    return tool
