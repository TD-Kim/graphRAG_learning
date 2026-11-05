"""[1단계: 읽기] vectorsearch.py (질문을 임베딩해서 Neo4j 벡터 인덱스로 비슷한 TextElement 찾기) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
주석 속 "N줄" 은 원본 파일의 줄 번호다 (이 주석본의 줄 번호와 다르다).
neo4j-graphrag 설명은 설치 소스로 확인했다 (requirements.txt 의 1.14.0. 1.14.1 과 관련 파일이 동일함을 비교로 확인).

전제: Part 2 pdf2kg.py 로 TextElement 노드가 있고, vector_index.ipynb 로 TextElement.embedding 과
      벡터 인덱스 textElementEmbedding 을 만들어 두었어야 한다. .env 에 NEO4J_*, OPENAI_API_KEY 필요.

흐름 (LLM 은 부르지 않는다. 임베딩 API 만 한 번)
  질문 "AI 규제 동향" (명령줄 인자)
    -> [OpenAIEmbeddings.embed_query] 질문 글 -> 1536개 숫자 리스트(질문 벡터)
    -> [VectorRetriever] Neo4j 에서 실행하는 Cypher (소스 확인):
         CALL db.index.vector.queryNodes($vector_index_name, $top_k * $effective_search_ratio, $query_vector)
         YIELD node, score WITH node, score LIMIT $top_k
         RETURN node {.element_id, .content, .page} AS node, labels(node) AS nodeLabels, elementId(node) AS elementId, elementId(node) AS id, score
    -> Record 마다 RetrieverResultItem(content=str(node 딕셔너리), metadata={"score", "nodeLabels", "id"})
    -> print_search_results: content 글을 다시 딕셔너리로 되돌려(ast.literal_eval) 내용, 페이지, 유사도 출력

읽는 순서 권장: main -> vector_search -> create_embedder -> print_search_results
실행 위치: part3/vectorsearch  ->  python learning/step1_annotated.py "AI 규제 동향"
"""

# [출처] 표준 라이브러리 ast. 여기서는 ast.literal_eval(글) 만 쓴다: "{'a': 1}" 같은 글을 진짜 딕셔너리로 바꾼다
import ast
# [출처] 표준 라이브러리 os. os.getenv("이름") 으로 환경변수를 읽는다 (없으면 None)
import os

# [출처] 외부 라이브러리 python-dotenv. load_dotenv() 가 .env 파일 내용을 환경변수로 올린다
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j (공식 파이썬 드라이버). GraphDatabase.driver(...) 로 DB 연결 객체를 만든다
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 neo4j-graphrag. OpenAIEmbeddings: 글 -> 숫자 벡터(임베딩)로 바꿔 주는 객체 (내부에서 openai 패키지 사용)
from neo4j_graphrag.embeddings import OpenAIEmbeddings
# VectorRetriever: "질문 임베딩 + 벡터 인덱스 검색 + 결과 정리" 를 한 번에 해 주는 검색기
from neo4j_graphrag.retrievers import VectorRetriever

# .env 를 읽어 환경변수로 등록 (파일이 import 될 때 바로 한 번 실행)
load_dotenv()


# ============================================
# Neo4j 연결 관리 & Embedder 설정
# ============================================

# [이 파일에서 정의] 환경변수로 Neo4j 드라이버를 만들고 연결을 확인한다
# [반환] neo4j Driver 객체 (세션/쿼리 실행의 출발점)
def create_neo4j_driver():
    """Neo4j 드라이버 생성 및 연결 확인"""
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # all([a, b, c]): [출처] 파이썬 기본. 리스트 안이 모두 "값이 있음"(None, 빈 글 아님)이면 True
    # not all(...): 하나라도 비어 있으면 -> raise ValueError 로 즉시 멈춘다
    if not all([uri, username, password]):
        raise ValueError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD 환경 변수를 설정해주세요.")

    # GraphDatabase.driver(uri, auth=(아이디, 비밀번호))
    # [출처] 외부 라이브러리 neo4j
    # [입력] uri: neo4j+s://... 같은 주소 / auth: (사용자, 비밀번호) 튜플
    # [반환] Driver. 만드는 순간에는 접속하지 않는다 (그래서 아래 verify_connectivity 로 확인)
    driver = GraphDatabase.driver(uri, auth=(username, password))

    # try/except: [출처] 파이썬 기본. try 안에서 에러(예외)가 나면 except 로 넘어간다
    # except Exception as e: 거의 모든 예외를 잡고, 그 예외 객체를 e 라는 이름으로 쓴다
    try:
        # driver.verify_connectivity(): 실제로 서버에 붙어 보고, 안 되면 예외를 던진다
        driver.verify_connectivity()
        # f"...{uri}": f-string. [출처] 파이썬 기본. 중괄호 안 변수 값이 글자 안에 들어간다
        print(f"Neo4j 연결 성공: {uri}")
    except Exception as e:
        print(f"Neo4j 연결 실패: {e}")
        # raise (뒤에 아무것도 없이): 방금 잡은 예외를 그대로 다시 던진다 -> 출력만 하고 프로그램은 멈춘다
        raise

    return driver


# [이 파일에서 정의] driver 가 있을 때만 닫는다 (if driver: None 이면 건너뜀)
def close_neo4j_driver(driver):
    """Neo4j 드라이버 종료"""
    if driver:
        driver.close()

# [이 파일에서 정의] OpenAI 임베딩 객체를 만든다
# model: str = "...": 타입 힌트(str 이라는 표시일 뿐 검사는 안 함) + 기본값
def create_embedder(model: str = "text-embedding-3-small"):
    """
    OpenAI Embedder 생성

    Args:
        model: OpenAI 임베딩 모델명

    Returns:
        OpenAIEmbeddings 인스턴스
    """
    # 키 값은 출력하지 않는다. 없는지만 확인
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경 변수를 설정해주세요.")

    # OpenAIEmbeddings(api_key=..., model=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] model: 임베딩 모델 이름 (넘기지 않으면 기본값은 "text-embedding-ada-002" 이니 꼭 지정)
    #        그 밖의 키워드(api_key 등)는 그대로 openai.OpenAI(...) 를 만들 때 넘어간다 (소스 확인)
    # [반환] Embedder 객체. .embed_query(글) -> list[float]
    #   내부: client.embeddings.create(input=글, model=모델) 의 response.data[0].embedding 을 돌려준다.
    #         속도 제한(rate limit) 에러는 기본으로 최대 3번까지 다시 시도한다
    # [왜] 질문도 문서와 "같은 모델" 로 임베딩해야 비교가 의미 있다 (노트북에서 text-embedding-3-small, 1536차원)
    return OpenAIEmbeddings(api_key=api_key, model=model)


# ============================================
# 벡터 검색 함수들
# ============================================

# [이 파일에서 정의] 질문 하나로 벡터 검색을 하고 RetrieverResult 를 돌려준다
# 여러 줄로 나눈 매개변수 목록: 괄호 안이라 줄바꿈해도 된다. 각 매개변수에 타입 힌트와 기본값
def vector_search(
    driver,
    query_text: str,
    top_k: int = 5,
    index_name: str = "textElementEmbedding",
    embedding_model: str = "text-embedding-3-small",
    # return_properties: list = None: 기본값을 리스트([])로 직접 쓰지 않고 None 으로 둔 다음 함수 안에서 채운다 (88~89줄)
    # (파이썬은 기본값 객체를 한 번만 만들어 모든 호출이 공유하므로, 리스트 기본값은 실수하기 쉽다)
    return_properties: list = None
):
    """
    기본 벡터 검색 수행 (VectorRetriever 사용)

    전제조건: TextElement 노드에 임베딩이 저장되어 있고, 벡터 인덱스가 생성되어 있어야 함

    Args:
        driver: Neo4j 드라이버
        query_text: 검색 쿼리
        top_k: 반환할 결과 수
        index_name: 벡터 인덱스 이름 (기본값: "textElementEmbedding")
        embedding_model: 쿼리 임베딩 생성에 사용할 모델
        return_properties: 반환할 노드 속성 리스트

    Returns:
        검색 결과 리스트 (각 결과는 RetrieverResultItem 객체)
    """
    # None 이면 돌려받을 노드 속성 3개로 채운다. 이 이름들이 Cypher 의 node {.element_id, .content, .page} 가 된다
    if return_properties is None:
        return_properties = ["element_id", "content", "page"]

    # f"{'=' * 60}": 중괄호 안에 계산식도 쓸 수 있다. '=' * 60 은 = 를 60번 반복한 글
    # "\n": 줄바꿈 문자 -> 위에 빈 줄 하나
    print(f"\n{'=' * 60}")
    print(f"🔍 벡터 검색: {query_text}")
    print(f"{'=' * 60}")

    # Embedder 생성
    # 이 함수를 부를 때마다 임베더와 검색기를 새로 만든다 (한 번만 검색하는 실습이라 괜찮다)
    embedder = create_embedder(model=embedding_model)

    # VectorRetriever 생성
    # VectorRetriever(driver=..., index_name=..., embedder=..., return_properties=[...])
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] driver: 검색을 실행할 연결 / index_name: Neo4j 벡터 인덱스 이름
    #        embedder: query_text 를 벡터로 바꿀 객체 (없으면 query_vector 를 직접 넘겨야 한다)
    #        return_properties: 노드에서 돌려받을 속성 이름 리스트. None 이면 embedding 만 null 로 지운 모든 속성
    # [반환] 검색기 객체
    # 내부 (소스 확인): 만드는 순간 DB 에 두 번 묻는다
    #   1) Neo4j 버전 확인 (벡터 인덱스를 지원하는 버전인지)
    #   2) SHOW VECTOR INDEXES ... WHERE name = $index_name -> 인덱스의 레이블, 속성, 차원을 읽어 둔다
    #      인덱스가 없으면 여기서 "No index with name textElementEmbedding found" 예외
    retriever = VectorRetriever(
        driver=driver,
        index_name=index_name,
        embedder=embedder,
        return_properties=return_properties
    )

    try:
        # retriever.search(query_text=질문, top_k=5)
        # [입력] query_text: 질문 글 / top_k: 가장 비슷한 노드 몇 개 (1 이상의 정수여야 함)
        # [반환] RetrieverResult
        #   .items: RetrieverResultItem 리스트. 각 item.content 는 str(node 딕셔너리) 글,
        #           예: "{'element_id': '...', 'content': '...', 'page': 3}"
        #           item.metadata = {"score": 유사도, "nodeLabels": ["TextElement"], "id": elementId}
        #   .metadata: {"query_vector": 질문 벡터, "__retriever": "VectorRetriever"}
        # 내부 순서: embed_query(질문) -> queryNodes Cypher 실행(읽기 전용, routing READ) -> Record 마다 위 모양으로 변환
        # score: cosine 인덱스면 1 에 가까울수록 비슷하다
        results = retriever.search(query_text=query_text, top_k=top_k)
        return results

    # 검색 실패(인덱스 차원 불일치, 연결 오류, 임베딩 실패 등)를 출력하고 다시 던진다
    except Exception as e:
        print(f"검색 실패: {e}")
        raise

# ============================================
# 결과 출력 함수
# ============================================

# [이 파일에서 정의] 검색 결과를 번호, 유사도, 페이지, 내용으로 출력
# 주의: docstring 의 max_content_length, debug 는 실제 매개변수에 없다 (예전 버전의 흔적일 수 있다)
def print_search_results(results):
    """
    검색 결과를 보기 좋게 출력

    Args:
        results: VectorRetriever의 RetrieverResult 객체 또는 dict 리스트
        max_content_length: 출력할 최대 내용 길이
        debug: 디버깅 정보 출력 여부
    """
    print("\n" + "=" * 80)
    print("검색 결과")
    print("=" * 80)

    # A if 조건 else B: [출처] 파이썬 기본 (조건 표현식). 조건이 참이면 A, 아니면 B
    # hasattr(객체, 'items'): 그 이름의 속성이 있으면 True. RetrieverResult 면 .items, 그냥 리스트면 그대로 쓰려는 것
    items = results.items if hasattr(results, 'items') else results

    # enumerate(리스트, 1): [출처] 파이썬 기본. (번호, 값) 짝을 돌려준다. 1 은 번호를 1부터 시작
    for i, item in enumerate(items, 1):
        # item.metadata or {}: metadata 가 None 이면 빈 딕셔너리로 (or 는 앞이 "비어 있음" 이면 뒤 값)
        metadata = item.metadata or {}
        # 딕셔너리.get(키, 기본값): 키가 없으면 기본값. VectorRetriever 는 항상 score 를 넣어 준다
        score = metadata.get("score", 0.0)

        # isinstance(값, str): 그 값이 글(str) 타입인지 / .startswith('{'): '{' 로 시작하는지
        # -> "딕셔너리를 글로 바꾼 것" 처럼 보일 때만 되돌린다
        # 주의: 이 조건이 거짓이면 content, page 가 만들어지지 않는다.
        #       첫 항목이면 아래 149줄에서 UnboundLocalError, 두 번째 이후면 "앞 항목의" 값이 잘못 출력된다.
        #       (return_properties 를 쓰는 지금 설정에서는 content 가 항상 '{' 로 시작하므로 실제로는 잘 돈다)
        if isinstance(item.content, str) and item.content.startswith('{'):
            # 문자열을 dict로 파싱
            # ast.literal_eval(글)
            # [출처] 표준 라이브러리 ast
            # [입력] 파이썬 값 모양의 글 (딕셔너리, 리스트, 숫자, 글, None 등만)
            # [반환] 진짜 파이썬 값. "{'page': 3}" -> {'page': 3}
            # [왜] VectorRetriever 기본 포맷이 str(딕셔너리) 라서 다시 딕셔너리로 되돌린다.
            #      eval() 과 달리 함수 호출 같은 코드는 실행하지 않아 안전하다
            # 주의: 노드 속성에 날짜(DateTime) 같은 값이 섞이면 str() 결과가 리터럴이 아니라 ValueError 가 날 수 있다.
            #       처음부터 result_formatter 로 원하는 모양을 받는 편이 낫다 (vectorcypher_qdrant 에서 그렇게 한다)
            parsed_content = ast.literal_eval(item.content)
            # literal_eval 결과가 딕셔너리일 때만 .get 으로 꺼낸다
            if isinstance(parsed_content, dict):
                content = parsed_content.get("content", "")
                page = parsed_content.get("page")
            else:
                content = str(item.content)
                page = None

        # {score:.4f}: f-string 서식. 소수점 아래 4자리까지 (예: 0.8123)
        print(f"\n[{i}] 유사도: {score:.4f}")

        if page is not None:
            print(f"    페이지: {page}")

        # content 가 빈 글이면 출력하지 않는다
        if content:
            display_content = str(content)
            print(f"    내용: {display_content}")

    print("\n" + "=" * 80)


# ============================================
# 메인 함수
# ============================================

# [이 파일에서 정의] 명령줄 질문 하나로 검색 -> 출력
def main():
    # 함수 안의 import: 이 함수에서만 쓰는 모듈을 여기서 불러온다 (파일 맨 위에 두는 게 보통이다)
    # [출처] 표준 라이브러리 sys. sys.argv 는 명령줄 단어 리스트
    import sys

    print("\n" + "=" * 60)
    print("PDF 지식그래프 Vector Search 시스템")
    print("=" * 60)

    # sys.argv[0] 은 파일 이름, [1] 이 첫 번째 인자 (질문)
    # 주의: 질문 없이 실행하면 IndexError 로 멈춘다. 띄어쓰기가 있는 질문은 "따옴표" 로 감싸야 한 인자가 된다
    query = sys.argv[1]
    TOP_K = 5

    # Neo4j 드라이버 생성
    driver = create_neo4j_driver()

    # try/finally: 검색 중 에러가 나도 finally 의 드라이버 닫기는 반드시 실행된다
    try:
        results = vector_search(driver, query, top_k=TOP_K)
        print_search_results(results)

    finally:
        close_neo4j_driver(driver)


# 이 파일을 직접 실행할 때만 main() (다른 파일이 import 하면 실행 안 됨)
if __name__ == "__main__":
    main()
