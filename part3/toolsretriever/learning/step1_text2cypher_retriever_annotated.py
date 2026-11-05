"""[1단계: 읽기] text2cypher_retriever.py (DB 에서 읽은 스키마 + 예제로 Text2Cypher 검색기와 도구 만들기) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1)로 확인했다.

이 파일은 직접 실행하지 않는다 (__main__ 없음). main.py 의 create_tools_retriever 가
  create_text2cypher_retriever -> create_text2cypher_tool 을 부른다.

흐름
  schema.fetch_schema_from_neo4j(driver) -> schema_to_text -> 스키마 글 (화면에 출력)
  get_text2cypher_examples() -> "USER INPUT: '질문' QUERY: Cypher" 예제 9개
  Text2CypherRetriever(스키마 글, 예제) --convert_to_tool--> Tool "text2cypher_structured_query"
  도구가 골라지면: LLM 이 정한 query_text -> (LLM 1번) Cypher 작성 -> Neo4j 에서 읽기 전용 실행 -> Record 들
  -> ToolsRetriever 가 결과마다 metadata["tool"] = "text2cypher_structured_query" 를 붙인다

part3/text2cypher 와 다른 점: 스키마를 손으로 쓰지 않고 DB 에서 읽는다. 대신 예제는 여전히 손으로 쓴다.

읽는 순서 권장: create_text2cypher_retriever -> get_text2cypher_examples -> create_text2cypher_tool
실행 위치: part3/toolsretriever 에서 PYTHONPATH=. python learning/step1_text2cypher_retriever_annotated.py
  (같은 폴더의 schema.py 를 import 하므로 PYTHONPATH=. 가 필요하다. 함수 정의만 있어서 실행해도 아무것도 출력되지 않는다.
   주석본은 import 용으로 쓰지 않는다)
"""

# [출처] 외부 라이브러리 neo4j-graphrag. Text2CypherRetriever: 질문 -> LLM 이 Cypher 작성 -> 실행 -> 결과
from neo4j_graphrag.retrievers import Text2CypherRetriever
# [출처] 같은 폴더의 schema.py (같은 폴더의 .py 는 파일 이름으로 import 할 수 있다)
from schema import fetch_schema_from_neo4j, schema_to_text


# [이 파일에서 정의] few-shot 예제 리스트
# [반환] 글 9개의 리스트. 검색기가 "\n".join 으로 이어 프롬프트의 {examples} 자리에 넣는다
# [왜] 예제를 보면 LLM 이 이 그래프의 레이블/속성 이름과 쿼리 스타일(CONTAINS 로 부분 일치, AS 한글 별칭)을 따라 한다
# 주의: 예제가 쓰는 toc.document, c.description, p.role/p.title/p.position, HAS_EXECUTIVE 등은
#       실제 DB 스키마에 없을 수 있다 (pdf2kg_2 의 속성/관계는 LLM 이 정한다).
#       Text2Cypher 기본 프롬프트에 "스키마에 없는 속성은 쓰지 말라" 가 있어 스키마와 예제가 서로 반대로 말하게 된다.
#       출력된 스키마와 예제를 나란히 놓고 맞춰 보자
def get_text2cypher_examples():
    """Text2Cypher를 위한 예시 질의-쿼리 쌍"""
    # 리스트 안에 주석(#)을 써서 예제를 종류별로 나눠 두었다 (주석은 리스트 원소가 아니다)
    examples = [
        # 문서 구조 관련 쿼리
        # 문서 구조 예제: TOC, TextElement 처럼 pdf2kg 가 만든 고정된 구조를 조회
        "USER INPUT: 'AI 기본법에 대한 내용을 찾아줘' QUERY: MATCH (toc:TOC) WHERE toc.title CONTAINS 'AI 기본법' RETURN toc.title AS 제목, toc.page_start AS 페이지, toc.level AS 레벨",
        "USER INPUT: '목차 구조를 보여줘' QUERY: MATCH (toc:TOC) RETURN toc.title AS 목차_제목, toc.page_start AS 시작_페이지, toc.level AS 레벨, toc.document AS 문서_제목 ORDER BY toc.page_start, toc.level",
        "USER INPUT: '6페이지에 있는 내용을 보여줘' QUERY: MATCH (t:TextElement) WHERE t.page = 6 RETURN t.content AS 내용, t.page AS 페이지",

        # 도메인 엔티티 검색 쿼리
        "USER INPUT: 'OpenAI에 대해 알려줘' QUERY: MATCH (c:Company) WHERE c.name CONTAINS 'OpenAI' RETURN c.name AS 회사명, c.description AS 설명",
        "USER INPUT: 'AI 관련 정책이나 법률을 찾아줘' QUERY: MATCH (n) WHERE n:Policy OR n:Law OR n:Regulation RETURN labels(n)[0] AS 유형, n.name AS 이름",

        # 엔티티 간 관계 쿼리 (핵심: 임원, 소속, 역할 등)
        # 관계 예제: [:A|B|C] = 셋 중 아무 관계 / 화살표 없는 -[]- = 방향 무관
        # coalesce(a, b, c): 처음으로 null 이 아닌 값 (어떤 속성 이름을 썼을지 몰라 여러 개를 시도)
        "USER INPUT: '알리바바의 CEO는 누구인가요?' QUERY: MATCH (c:Company)-[:HAS_EXECUTIVE|EMPLOYS|AFFILIATED_WITH]-(p:Person) WHERE c.name CONTAINS '알리바바' AND (p.role CONTAINS 'CEO' OR p.title CONTAINS 'CEO' OR p.position CONTAINS 'CEO') RETURN c.name AS 회사, p.name AS 이름, coalesce(p.role, p.title, p.position) AS 직책",
        "USER INPUT: '업스테이지의 기술책임자는 누군가요?' QUERY: MATCH (c:Company)-[:HAS_EXECUTIVE|EMPLOYS|AFFILIATED_WITH]-(p:Person) WHERE c.name CONTAINS '업스테이지' AND (p.role CONTAINS '기술책임자' OR p.role CONTAINS 'CTO' OR p.title CONTAINS 'CTO') RETURN c.name AS 회사, p.name AS 이름, coalesce(p.role, p.title, p.position) AS 직책",
        "USER INPUT: 'LG AI연구원 소속 인물은 누구인가요?' QUERY: MATCH (org:Company|Organization)-[:EMPLOYS|HAS_MEMBER|AFFILIATED_WITH]-(p:Person) WHERE org.name CONTAINS 'LG AI연구원' RETURN org.name AS 조직, p.name AS 인물, coalesce(p.role, p.title, p.position, '소속') AS 역할",

        # 포괄적 관계 탐색
        # 포괄 탐색 예제: 이름에 OpenAI 가 들어간 노드의 이웃을 모두. LIMIT 50 으로 결과 수를 제한
        "USER INPUT: 'OpenAI와 관련된 모든 정보를 찾아줘' QUERY: MATCH (n)-[r]-(related) WHERE n.name CONTAINS 'OpenAI' RETURN n.name AS 중심_엔티티, type(r) AS 관계, labels(related)[0] AS 연관_타입, coalesce(related.name, related.title) AS 연관_엔티티 LIMIT 50"
    ]
    return examples


# [이 파일에서 정의] 스키마를 DB 에서 읽고 Text2CypherRetriever 를 만든다
# [입력] driver, llm   [반환] Text2CypherRetriever
def create_text2cypher_retriever(driver, llm):
    """Text2Cypher 검색 Retriever 생성 (구조화 질의)

    Neo4j에서 동적으로 스키마를 조회하여 Retriever 생성
    """
    # schema.py 의 두 함수: DB 조회 -> 딕셔너리 -> 글
    schema_dict = fetch_schema_from_neo4j(driver)
    schema_text = schema_to_text(schema_dict)

    # 스키마 글을 화면에 출력: LLM 이 무엇을 보고 Cypher 를 쓰는지 사람이 확인하려고
    print("=== Neo4j에서 조회한 스키마 정보 ===")
    print(schema_text)
    print("===================================")
    # Text2CypherRetriever(driver=..., llm=..., neo4j_schema=..., examples=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] neo4j_schema: 스키마 글 (None 이면 만들 때 get_schema() 로 자동 조회. 여기서는 직접 만든 글을 준다)
    #        examples: 예제 글 리스트
    # [반환] 검색기
    # 내부 동작 (소스 확인):
    #   - 만들 때 Neo4j 버전 확인 쿼리를 한 번 실행한다
    #   - search(query_text=...) 때
    #       1) 기본 프롬프트: "Task: Generate a Cypher statement ... Schema: {schema} Examples (optional): {examples} Input: {query_text}
    #          Do not use any properties or relationships not included in the schema. ..."
    #       2) llm.invoke(프롬프트) -> extract_cypher: ``` 코드블록이 있으면 안쪽만 꺼내고, 띄어쓰기 있는 레이블에 백틱을 붙인다
    #       3) driver.execute_query(Cypher, routing_=READ) -> 읽기 전용으로 실행. 문법 오류는 Text2CypherRetrievalError
    #       4) 기본 포매터: 결과 한 건 content = str(record), item.metadata = None.
    #          실행한 Cypher 는 결과 "전체" 의 metadata["cypher"] 에만 들어간다
    # 주의: ToolsRetriever 는 도구 결과의 items 만 옮겨 담고 결과 전체의 metadata 는 버린다 (소스 확인).
    #       그래서 main.py 화면에서는 LLM 이 어떤 Cypher 를 썼는지 볼 수 없다 (디버깅이 어려움)
    #   - main.py 의 llm 과 같은 객체 -> 도구 선택, Cypher 작성, 답변 작성을 모두 gpt-4o 가 한다
    retriever = Text2CypherRetriever(
        driver=driver,
        llm=llm,
        neo4j_schema=schema_text,
        examples=get_text2cypher_examples()
    )
    print("[4/4] Text2Cypher 검색 Retriever 생성 완료")
    return retriever


# [이 파일에서 정의] Text2CypherRetriever -> Tool "text2cypher_structured_query"
def create_text2cypher_tool(retriever):
    """Text2CypherRetriever를 Tool로 변환"""

    # convert_to_tool (자세한 설명은 vector_retriever 주석본)
    # 입력 스키마 (소스 확인): get_search_results(self, query_text: str, prompt_params=None)
    #   -> query_text 는 기본값이 없어 "필수", prompt_params 는 선택(객체)
    # 주의: query_text 는 사용자의 원래 질문이 아니라 도구를 고른 LLM 이 다시 써서 넘긴 글이다 (질문이 바뀌어 들어갈 수 있다)
    tool = retriever.convert_to_tool(
        name="text2cypher_structured_query",
        # 도구 설명: 엔티티 검색 / 관계 조회 / 문서 구조 / 목록과 통계 4가지 시나리오
        # **...** 는 마크다운 굵게 표시. LLM 이 읽을 때 강조 신호가 된다
        # 주의: "표 데이터", "표로 정리된 내용" 은 table_vector_search 의 역할과, "OpenAI에 대해 알려줘" 는 vectorcypher 의 예시와 겹친다
        description="""
        그래프 데이터베이스의 구조화된 엔티티와 관계를 활용한 정확한 질의를 수행합니다.

        **주요 사용 시나리오**:

        1. 도메인 엔티티 검색:
           - 특정 회사, 조직, 인물, AI 모델, 정책, 법률 등을 찾을 때
           - 예: "OpenAI에 대해 알려줘", "EXAONE 모델 정보"

        2. 엔티티 간 관계 조회:
           - "X의 Y는?" 형식의 질문 (소속, 직책, 관계 등)
           - 회사의 임원, 조직의 소속 인물, 제품의 개발사 등

        3. 문서 구조 탐색:
           - 목차 구조, 특정 페이지 내용, 표 데이터
           - 예: "목차 구조는?", "10페이지 내용", "표로 정리된 내용"

        4. 목록과 통계:
           - 엔티티 개수, 목록, 정확한 데이터
           - 예: "AI 정책 목록", "회사 목록", "모델 개수"
        """
    )

    return tool
