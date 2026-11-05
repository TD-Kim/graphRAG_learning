"""[1단계: 읽기] vectorcypher.py (벡터로 비슷한 질의(Question)를 찾고, 거기서 Cypher 로 해석례 주변 그래프를 가져와 LLM 이 답변) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
주석 속 "N줄" 은 원본 파일의 줄 번호다 (이 주석본의 줄 번호와 다르다).
neo4j-graphrag 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1)로 확인했다.

전제: part2/law2kg 로 법령 + 해석례 그래프가 있고, README 4장대로 Question.embedding 과
      벡터 인덱스 question_embedding_index 를 만들어 두었어야 한다. .env 에 NEO4J_*, OPENAI_API_KEY 필요.

흐름 (임베딩 1번 + LLM 1번)
  질문 "피해종교단체의 정의가 뭐야?"
    -> [VectorCypherRetriever] 질문 임베딩 -> Neo4j 에서 한 번에 실행되는 Cypher (소스 확인):
         CALL db.index.vector.queryNodes($vector_index_name, $top_k * $effective_search_ratio, $query_vector)
         YIELD node, score WITH node, score LIMIT $top_k
         + 이 파일의 retrieval_query (node 에서 출발해 해석례/회답/이유/법령/인용 조문을 모은다)
    -> Record 마다 RetrieverResultItem(content=str(Record)) (result_formatter 를 안 줬으므로 기본 포맷)
    -> [GraphRAG] items 의 content 를 줄바꿈으로 이어 {context} 에, 질문을 {query_text} 에 -> LLM(gpt-4o) -> 답변

vectorsearch 와 다른 점: 찾은 노드 "자체" 가 아니라, 그 노드에서 출발한 "주변 그래프" 를 컨텍스트로 쓴다.
text2cypher 와 다른 점: Cypher 를 LLM 이 쓰지 않고 사람이 미리 써 둔다 (안정적, 대신 정해진 모양의 질문만 잘 받는다).

읽는 순서 권장: main -> search_legal_interpretation -> create_legal_vectorcypher_retriever(retrieval_query) -> create_legal_graphrag
실행 위치: part3/vectorcypher  ->  python learning/step1_annotated.py   (질문은 main 의 test_query 를 바꿔 가며)
"""

# [출처] 표준 라이브러리 os. os.getenv 로 환경변수 읽기
import os

# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 neo4j-graphrag. OpenAIEmbeddings: 글 -> 벡터
from neo4j_graphrag.embeddings import OpenAIEmbeddings
# GraphRAG: 검색기 + LLM + 프롬프트를 묶은 파이프라인 / RagTemplate: 답변 프롬프트 틀
from neo4j_graphrag.generation import GraphRAG, RagTemplate
# OpenAILLM: OpenAI 채팅 모델 감싸개. neo4j_graphrag.llm 에서 import 해도 같은 클래스 (여기선 세부 모듈 경로로 import)
from neo4j_graphrag.llm.openai_llm import OpenAILLM
# VectorCypherRetriever: 벡터 검색으로 시작 노드를 찾은 뒤, 사람이 쓴 Cypher(retrieval_query)를 이어 붙여 실행하는 검색기
from neo4j_graphrag.retrievers import VectorCypherRetriever

# .env 를 환경변수로 등록
load_dotenv()


# ============================================
# Neo4j 연결 관리 & Embedder 설정
# ============================================

# [이 파일에서 정의] 환경변수로 드라이버 생성 + 연결 확인 [반환] Driver
# (vectorsearch.py 와 같은 함수. all(), GraphDatabase.driver, try/except/raise 설명은 그쪽 주석 참고)
def create_neo4j_driver():
    """Neo4j 드라이버 생성 및 연결 확인"""
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    if not all([uri, username, password]):
        raise ValueError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD 환경 변수를 설정해주세요.")

    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        driver.verify_connectivity()
        print(f"Neo4j 연결 성공: {uri}")
    except Exception as e:
        print(f"Neo4j 연결 실패: {e}")
        raise

    return driver


# [이 파일에서 정의] driver 가 있으면 닫기
def close_neo4j_driver(driver):
    """Neo4j 드라이버 종료"""
    if driver:
        driver.close()


# [이 파일에서 정의] OpenAIEmbeddings 생성 [반환] Embedder (.embed_query(글) -> list[float])
def create_embedder(model: str = "text-embedding-3-small"):
    """
    OpenAI Embedder 생성

    Args:
        model: OpenAI 임베딩 모델명

    Returns:
        OpenAIEmbeddings 인스턴스
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경 변수를 설정해주세요.")

    # OpenAIEmbeddings(api_key=..., model=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] model: 임베딩 모델 (기본값은 text-embedding-ada-002 라서 꼭 지정). 나머지 키워드는 openai.OpenAI(...) 로 전달
    # [반환] Embedder. 질문 임베딩에 쓴다. 인덱스를 만들 때(README 4장)와 같은 모델이어야 한다
    return OpenAIEmbeddings(api_key=api_key, model=model)


# ============================================
# VectorCypher Retriever 생성
# ============================================

# [이 파일에서 정의] VectorCypherRetriever 를 만들어 돌려준다. 이 실습의 본체는 아래 retrieval_query
def create_legal_vectorcypher_retriever(
    driver,
    index_name: str = "question_embedding_index",
    embedding_model: str = "text-embedding-3-small"
):
    """
    법령 해석례 질의를 벡터 검색하고, 연결된 답변, 이유, 법조항 구조를 함께 가져오는
    VectorCypher Retriever 생성

    그래프 구조:
    (LegalInterpretation)
        ├── HAS_QUESTION → (Question) [벡터 검색 대상]
        │                      └── ANSWERED_BY → (Answer)
        │                                           └── SUPPORTED_BY → (Reason)
        ├── HAS_ANSWER → (Answer)
        ├── INTERPRETS → (Law) [주 법령]
        └── CITES → (Law/Article/Paragraph/Item) [인용 조항]

    Args:
        driver: Neo4j 드라이버
        index_name: 벡터 인덱스 이름 (기본값: "question_embedding_index")
        embedding_model: 쿼리 임베딩 생성에 사용할 모델

    Returns:
        VectorCypherRetriever 인스턴스
    """
    # Embedder 생성
    # 검색기를 만들 때마다 임베더도 새로 만든다
    embedder = create_embedder(model=embedding_model)

    # VectorCypher 검색 쿼리 정의
    # node: 벡터 검색으로 찾은 Question 노드
    # retrieval_query: 벡터 검색 "뒤에" 이어 붙는 Cypher 글 (여러 줄 문자열 """ ... """)
    # 라이브러리가 앞에 붙이는 부분 (소스 확인):
    #   CALL db.index.vector.queryNodes(...) YIELD node, score WITH node, score LIMIT $top_k
    # -> 그래서 여기서 쓸 수 있는 변수는 node(찾은 Question 노드)와 score(유사도) 두 개. 반드시 node 에서 출발한다
    # 줄별 뜻
    #   MATCH (node)<-[:HAS_QUESTION]-(interp)  : 이 질의가 속한 해석례. OPTIONAL 이 아니라서 해석례가 없는 Question 은 결과에서 빠진다
    #   OPTIONAL MATCH ...ANSWERED_BY / SUPPORTED_BY : 회답, 이유 (없어도 행이 사라지지 않고 null)
    #   OPTIONAL MATCH ...INTERPRETS            : 주 법령
    #   OPTIONAL MATCH ...CITES (Law/Article/Paragraph/Item) + 부모로 거슬러 올라가기 : 인용 조문 계층
    #   RETURN: collect 가 아닌 항목(제목, 안건번호, 질의, 회답, 이유, 주 법령)이 "묶음 기준" 이 되고,
    #           collect(DISTINCT ...) 들이 그 묶음 안의 값을 리스트로 모은다. 맵 {law: ..., ...} 을 모아 구조를 남긴다
    # 주의: OPTIONAL MATCH 를 줄줄이 이으면 인용 법령 수 x 조문 수 x 항 수 x 호 수 만큼 행이 불어난 뒤 collect 된다 (행 폭발).
    # 주의: cited_paragraphs, cited_items 의 law 에 article_law.name(인용 "조문" 의 법령)을 쓴다. 항이나 호만 인용했으면 null 이거나 다른 법령일 수 있다.
    # 주의: cited_items 의 article_number 가 para_article.number(인용 "항" 의 조문)다. 호의 부모 항(item_para)의 조문이 아니라서 틀린 조문 번호가 들어갈 수 있다.
    # 주의: collect 는 null 은 버리지만 {law: null, ...} 같은 "값이 모두 null 인 맵" 은 null 이 아니라 그대로 들어간다.
    #       인용 조문이 없으면 cited_articles 에 빈 맵 모양 항목 하나가 남는다
    # 주의: score 를 RETURN 하지 않아서 결과에서 유사도를 볼 수 없다
    retrieval_query = """
    // 질의(Question) 노드를 기준으로 해석례 정보 수집
    MATCH (node)<-[:HAS_QUESTION]-(interp:LegalInterpretation)

    // 회답(Answer) 가져오기
    OPTIONAL MATCH (node)-[:ANSWERED_BY]->(answer:Answer)

    // 이유(Reason) 가져오기
    OPTIONAL MATCH (answer)-[:SUPPORTED_BY]->(reason:Reason)

    // 주 법령(primary law) 가져오기
    OPTIONAL MATCH (interp)-[:INTERPRETS]->(primary_law:Law)

    // 인용된 법조문 계층구조 가져오기 (Law -> Article -> Paragraph -> Item)
    OPTIONAL MATCH (interp)-[:CITES]->(cited_law:Law)
    OPTIONAL MATCH (interp)-[:CITES]->(cited_article:Article)
    OPTIONAL MATCH (cited_article)<-[:HAS_ARTICLE]-(article_law:Law)
    OPTIONAL MATCH (interp)-[:CITES]->(cited_para:Paragraph)
    OPTIONAL MATCH (cited_para)<-[:HAS_PARAGRAPH]-(para_article:Article)
    OPTIONAL MATCH (interp)-[:CITES]->(cited_item:Item)
    OPTIONAL MATCH (cited_item)<-[:HAS_ITEM]-(item_para:Paragraph)

    // 결과 반환
    RETURN
        // 해석례 메타데이터
        interp.title AS interpretation_title,
        interp.case_number AS case_number,

        // 질의/회답/이유
        node.text AS question,
        answer.text AS answer_text,
        reason.text AS reason_text,

        // 주 법령
        primary_law.name AS primary_law_name,

        // 인용된 법령 (중복 제거)
        collect(DISTINCT cited_law.name) AS cited_laws,

        // 인용된 조문 정보 (법령명 + 조문번호)
        collect(DISTINCT {
            law: article_law.name,
            article_number: cited_article.number,
            article_title: cited_article.title,
            article_content: cited_article.content
        }) AS cited_articles,

        // 인용된 항 정보
        collect(DISTINCT {
            law: article_law.name,
            article_number: para_article.number,
            paragraph_number: cited_para.number,
            paragraph_content: cited_para.content
        }) AS cited_paragraphs,

        // 인용된 호 정보
        collect(DISTINCT {
            law: article_law.name,
            article_number: para_article.number,
            paragraph_number: item_para.number,
            item_number: cited_item.number,
            item_content: cited_item.content
        }) AS cited_items
    """

    # VectorCypherRetriever 생성
    # VectorCypherRetriever(driver=..., index_name=..., retrieval_query=..., embedder=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] index_name: Neo4j 벡터 인덱스 이름 / retrieval_query: 위 Cypher 글 / embedder: 질문 임베딩용
    #        result_formatter: 안 넘김 -> 기본 포맷 사용 (아래 참고)
    # [반환] 검색기 객체. .search(query_text=..., top_k=...) -> RetrieverResult
    # 내부 (소스 확인)
    #   - 만들 때: Neo4j 버전 확인 + SHOW VECTOR INDEXES 로 인덱스 정보 읽기 (인덱스가 없으면 여기서 예외)
    #   - 검색 때: embed_query(질문) -> 위 CALL ... + retrieval_query 를 읽기 전용(routing READ)으로 실행
    #   - 기본 포맷: item.content = str(Record) 글 (예: <Record interpretation_title='...' case_number='...' question='...' ...>)
    #                item.metadata = Record 의 "metadata" 열 (이 쿼리엔 없으므로 None)
    retriever = VectorCypherRetriever(
        driver=driver,
        index_name=index_name,
        retrieval_query=retrieval_query,
        embedder=embedder
    )

    return retriever


# ============================================
# GraphRAG 파이프라인 생성
# ============================================

# [이 파일에서 정의] LLM + 답변 프롬프트 + 검색기를 묶어 GraphRAG 를 만든다
def create_legal_graphrag(
    retriever,
    llm_model: str = "gpt-4o"
):
    """
    법령 해석례 기반 GraphRAG 파이프라인 생성

    Args:
        retriever: VectorCypherRetriever 인스턴스
        llm_model: 사용할 LLM 모델 (기본값: "gpt-4o")

    Returns:
        GraphRAG 인스턴스
    """
    # LLM 생성
    # OpenAILLM(model_name="gpt-4o")
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] model_name: OpenAI 모델 이름. model_params(temperature 등)는 안 넘겼으므로 OpenAI 기본값
    #        api_key 를 안 넘기면 openai.OpenAI() 가 OPENAI_API_KEY 환경변수를 스스로 읽는다
    # [반환] LLM 객체. GraphRAG 가 내부에서 .invoke(...) 로 부르고 답은 .content 에 있다
    llm = OpenAILLM(model_name=llm_model)

    # 프롬프트 템플릿 정의
    # RagTemplate(template=글, expected_inputs=[...])
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] template: 답변 프롬프트 틀. {query_text} 에 질문, {context} 에 검색 결과 글이 들어간다
    #        expected_inputs: 틀 안에 꼭 있어야 하는 자리 이름. 없으면 만들 때 PromptMissingPlaceholderError
    # [왜] 법률 답변은 "결론 -> 근거 -> 이유" 순서가 중요해서 출력 형식(<output_format>)을 고정한다
    # 내부: 나중에 template.format(...) 으로 채운다 (f-string 아님). 그래서 글자 그대로의 중괄호를 쓰려면 {{ }} 로 써야 한다
    #       시스템 지시문은 따로 안 줬으므로 기본값 "Answer the user question using the provided context." 가 쓰인다
    prompt_template = RagTemplate(
        template="""
당신은 대한민국의 법령 해석 전문가입니다. 제공된 법령 해석례 정보를 바탕으로 사용자의 질문에 명확하고 정확하게 답변해주세요.

답변 시 다음 정보를 포함하여 체계적으로 설명해주세요:
<output_format>
사용자 질문에 대한 명확한 답변을 1-2문장으로 간단명료하게 제시

1. **관련 해석례**: 해석례 제목과 안건번호
2. **질의 내용**: 해석례의 질의요지
3. **회답 결론**: 해석 결과 (가능/불가능/조건부 등)
4. **법적 근거**: 관련 법령명과 조문
5. **상세 이유**: 해석의 근거가 되는 법리적 설명
</output_format>

<guidelines>
검색된 여러 해석례가 있다면, 가장 관련성이 높은 것을 중심으로 설명하고, 다른 참고할 만한 해석례도 간략히 언급해주세요.
정보는 상세하게 불렛 포인트로 나누어 설명하되, 너무 길지 않도록 핵심 위주로 작성해주세요.
</guidelines>

<user_question>
{query_text}
</user_question>

<검색된 법령 해석례 정보>
{context}
</검색된 법령 해석례 정보>


답변:
        """,
        expected_inputs=["context", "query_text"]
    )

    # GraphRAG 생성
    # GraphRAG(retriever=..., llm=..., prompt_template=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [반환] 파이프라인 객체. .search(...) 한 번에 "검색 -> 프롬프트 채우기 -> LLM 답변" 을 한다
    graph_rag = GraphRAG(
        retriever=retriever,
        llm=llm,
        prompt_template=prompt_template
    )

    return graph_rag


# ============================================
# 검색 및 답변 생성 함수
# ============================================

# [이 파일에서 정의] 검색기, 파이프라인을 만들고 질문 하나를 실행
# [반환] RagResultModel (.answer, .retriever_result)
# 주의: 부를 때마다 검색기와 GraphRAG 를 새로 만든다 (검색기 생성 때마다 DB 에 인덱스 정보를 묻는다). 질문이 많으면 한 번 만들어 재사용하는 게 낫다
def search_legal_interpretation(
    driver,
    query: str,
    top_k: int = 3,
    index_name: str = "question_embedding_index",
    embedding_model: str = "text-embedding-3-small",
    llm_model: str = "gpt-4o",
    return_context: bool = True
):
    """
    법령 해석례 검색 및 답변 생성

    Args:
        driver: Neo4j 드라이버
        query: 사용자 질문
        top_k: 반환할 검색 결과 수 (기본값: 3)
        index_name: 벡터 인덱스 이름
        embedding_model: 임베딩 모델
        llm_model: LLM 모델
        return_context: 검색 컨텍스트 반환 여부

    Returns:
        GraphRAG 검색 결과 (answer, retriever_result 포함)
    """
    print(f"\n{'=' * 60}")
    print(f"질문: {query}")
    print(f"{'=' * 60}")

    # Retriever 생성
    retriever = create_legal_vectorcypher_retriever(
        driver=driver,
        index_name=index_name,
        embedding_model=embedding_model
    )

    # GraphRAG 생성
    graph_rag = create_legal_graphrag(
        retriever=retriever,
        llm_model=llm_model
    )

    # 검색 수행
    # graph_rag.search(query_text=..., retriever_config={...}, return_context=...)
    # [입력] query_text: 질문
    #        retriever_config: 검색기 .search() 에 그대로 풀어 넘길 키워드 딕셔너리 -> retriever.search(query_text=질문, top_k=...)
    #        return_context: True 면 결과에 검색 결과(retriever_result)도 담아 준다
    # [반환] RagResultModel
    # 내부 순서 (소스 확인)
    #   1) retriever.search(...) -> items
    #   2) context = "\n".join(item.content for item in items)   (각 str(Record) 글을 줄바꿈으로 이음)
    #   3) prompt_template.format(query_text=질문, context=context, examples="") -> 프롬프트 글
    #   4) llm.invoke(...) -> answer = 응답.content
    # 검색 결과가 0건이어도 빈 context 로 LLM 을 부른다 (response_fallback 을 안 줬으므로)
    response = graph_rag.search(
        query_text=query,
        retriever_config={"top_k": top_k},
        return_context=return_context
    )

    return response


# ============================================
# 메인 함수
# ============================================

# [이 파일에서 정의] 질문 하나 실행 -> 검색 결과(컨텍스트)와 최종 답변 출력
def main():
    driver = create_neo4j_driver()

    try:
        # 예제 질문들 - 다양한 검색 유형

        # 주석 처리된 질문들: 하나씩 바꿔 가며 실행해 보라는 뜻. 실제로는 306줄 test_query 만 쓰인다
        # test_query = "사찰에 직접적인 '피해자'가 없어도 '피해종교단체'로 인정받을 수 있는 기준이 뭐야?"
        # test_query = "사찰에 직접적인 피해자가 있어야만 피해종교단체로 인정받을 수 있어?"
        test_query = "피해종교단체의 정의가 뭐야?"
        # test_query = "10·27법난 피해자의 명예회복 법률에 대해 알려줘"
        # test_query = " 공무원이 아닌 위원의 임기는?"


        # True 면 LLM 에 들어간 컨텍스트(검색 결과)를 볼 수 있다. 답이 이상할 때 원인 찾기에 필수
        RETURN_CONTEXT = True
        # top_k=1: 가장 비슷한 Question 노드 1개에서만 출발 (함수 기본값 3 을 덮어씀)
        response = search_legal_interpretation(
            driver=driver,
            query=test_query,
            top_k=1,
            return_context=RETURN_CONTEXT
        )

        # hasattr(response, 'retriever_result'): RagResultModel 은 이 속성이 항상 있다 (False 로 부르면 값이 None).
        # 그래서 실제로 의미 있는 조건은 RETURN_CONTEXT
        if RETURN_CONTEXT and hasattr(response, 'retriever_result'):
            print("\n" + "=" * 60)
            print("검색 결과")
            print("=" * 60)
            # for i in ...items: i 는 RetrieverResultItem. i.content 는 str(Record) 글 (LLM 이 본 것과 같은 글)
            for i in response.retriever_result.items:
                print(i.content)

        print("\n" + "=" * 60)
        print("최종 답변")
        print("=" * 60)
        print(response.answer)

    # try/finally: 에러가 나도 드라이버는 닫는다
    finally:
        close_neo4j_driver(driver)


# 이 파일을 직접 실행할 때만 main()
if __name__ == "__main__":
    main()
