"""[1단계: 읽기] vector_retriever.py (텍스트/표 벡터 검색기 2개를 만들고 "도구(Tool)" 로 바꾸기) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1)로 확인했다.

이 파일은 직접 실행하지 않는다 (__main__ 없음). main.py 의 create_tools_retriever 가 4개 함수를 차례로 부른다.

흐름
  VectorRetriever(인덱스 "text_content_vector_index")  --convert_to_tool-->  Tool "text_vector_search"
  VectorRetriever(인덱스 "table_content_vector_index") --convert_to_tool-->  Tool "table_vector_search"
  Tool = 이름 + 설명(description) + 입력 스키마(JSON Schema) + 실행 함수
  ToolsRetriever 가 이 이름/설명/입력 스키마를 OpenAI 의 tools 형식으로 LLM 에 보여 주고, LLM 이 고른 도구의 실행 함수를 부른다

핵심: description 이 "라우팅 규칙" 이다. if 문이 아니라 LLM 이 이 글을 읽고 질문에 맞는 도구를 고른다.

읽는 순서 권장: create_text_vector_retriever -> create_text_vector_tool (convert_to_tool 설명) -> 표 쪽 두 함수
실행 위치: part3/toolsretriever 에서 PYTHONPATH=. python learning/step1_vector_retriever_annotated.py
  (함수 정의만 있어서 실행해도 아무것도 출력되지 않는다. 주석본은 import 용으로 쓰지 않는다)
"""

# [출처] 외부 라이브러리 neo4j-graphrag. VectorRetriever: 질문을 임베딩해서 벡터 인덱스에서 가까운 노드를 찾는 검색기
from neo4j_graphrag.retrievers import VectorRetriever


# [이 파일에서 정의] TextElement 용 벡터 검색기를 만든다
# [입력] driver, embedder, index_name (config.create_vector_indexes 가 돌려준 이름)
# [반환] VectorRetriever
def create_text_vector_retriever(driver, embedder, index_name):
    """TextElement 벡터 검색 Retriever 생성"""
    # VectorRetriever(driver=..., index_name=..., embedder=..., return_properties=[...])
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] index_name: 벡터 인덱스 이름 / embedder: 질문 글을 벡터로 바꿀 객체
    #        return_properties: 찾은 노드에서 돌려받을 속성 이름 (embedding 같은 긴 벡터는 빼고 이것만)
    # [반환] 검색기 객체
    # 내부 동작 (소스 확인):
    #   - 만들 때: Neo4j 버전 확인 쿼리 + SHOW VECTOR INDEXES 로 인덱스의 레이블/속성/차원을 읽는다
    #             -> 인덱스가 없으면 여기서 "No index with name ... found" 에러
    #   - search(query_text=...) 때: embedder.embed_query(질문) -> db.index.vector.queryNodes(인덱스, top_k=5 기본, 벡터)
    #         -> RETURN node {.content, .page, .toc_id} AS node, labels(node), elementId(node) AS id, score
    #   - 결과 한 건 = RetrieverResultItem(content=str(node 딕셔너리), metadata={"score", "nodeLabels", "id"})
    retriever = VectorRetriever(
        driver=driver,
        index_name=index_name,
        embedder=embedder,
        return_properties=["content", "page", "toc_id"]
    )
    # print 의 [1/4]: main 에서 만드는 검색기 4개 중 몇 번째인지
    print("[1/4] TextElement 벡터 검색 Retriever 생성")
    return retriever


# [이 파일에서 정의] TableElement 용. 위 함수와 인덱스 이름만 다르고 똑같다
# (두 함수가 사실상 같아서 하나로 합칠 수도 있다)
def create_table_vector_retriever(driver, embedder, index_name):
    """TableElement 벡터 검색 Retriever 생성"""
    retriever = VectorRetriever(
        driver=driver,
        index_name=index_name,
        embedder=embedder,
        return_properties=["content", "page", "toc_id"]
    )
    print("[2/4] TableElement 벡터 검색 Retriever 생성")
    return retriever


# [이 파일에서 정의] 텍스트 검색기 -> LLM 이 고를 수 있는 Tool
# [입력] text_retriever: 위에서 만든 VectorRetriever  [반환] Tool
def create_text_vector_tool(text_retriever):
    """TextVectorRetriever를 Tool로 변환"""

    # 검색기.convert_to_tool(name=..., description=..., parameter_descriptions=None)
    # [출처] 외부 라이브러리 neo4j-graphrag (모든 Retriever 가 물려받는 메서드)
    # [입력] name: 도구 이름 (LLM 이 이 이름으로 고른다. ToolsRetriever 안에서 겹치면 ValueError)
    #        description: 도구 설명 (LLM 이 읽는 글)
    #        parameter_descriptions: 매개변수별 설명 (안 주면 "Parameter query_text" 같은 기본 설명)
    # [반환] Tool 객체
    # 내부 동작 (소스 확인):
    #   1) get_search_results 의 함수 시그니처를 inspect 로 읽어 입력 스키마를 자동으로 만든다
    #      VectorRetriever 는 query_vector(숫자 배열), query_text(글), top_k(정수, 최소 1), effective_search_ratio(정수),
    #      filters(객체) -> 기본값이 모두 있어서 "필수 매개변수" 는 하나도 없다
    #   2) 실행 함수 execute_func(**kwargs) = self.search(**kwargs) 를 담는다
    #      **kwargs: 이름=값 인자를 딕셔너리로 모아 받고, 그대로 펼쳐 넘긴다 (LLM 이 정한 인자를 그대로 search 에 전달)
    # 주의: LLM 이 query_text 를 빼먹으면 검색이 에러가 나는데, ToolsRetriever 가 에러를 삼켜 빈 결과가 될 수 있다
    tool = text_retriever.convert_to_tool(
        name="text_vector_search",
        # description="""...""": 여러 줄 문자열. 앞쪽 들여쓰기 공백도 글에 그대로 포함되어 LLM 에 간다 (동작에는 문제 없음)
        # 사용 시나리오가 한 줄뿐이라 다른 도구(vectorcypher 의 "개방형 질문")와 겹치기 쉽다 -> 실제로 덜 선택될 수 있다
        description="""
        PDF 문서 내 텍스트 단락을 의미 기반으로 검색합니다.

        사용 시나리오:
        - 특정 주제나 개념에 대한 요약 등을 찾을 때
        """
    )
    return tool


# [이 파일에서 정의] 표 검색기 -> Tool "table_vector_search"
def create_table_vector_tool(table_retriever):
    """TableVectorRetriever를 Tool로 변환"""

    tool = table_retriever.convert_to_tool(
        name="table_vector_search",
        # 표 도구 설명: "비교 표", "통계", "목록" 질문을 받도록 예시를 적었다
        # 주의: text2cypher 도구 설명에도 "목록과 통계", "표로 정리된 내용" 이 있어 둘이 겹친다. 어느 쪽이 골라지는지 실험해 보자
        description="""
        PDF 문서 내 표(테이블) 데이터를 의미 기반으로 검색합니다.

        사용 시나리오:
        - 표로 정리된 정보를 찾을 때
        - 비교 데이터, 통계, 목록 등을 찾을 때
        - "~를 비교한 표", "~통계", "~목록" 같은 질문

        예: "모델 성능 비교 표", "주요 일정 목록"
        """
    )
    return tool
