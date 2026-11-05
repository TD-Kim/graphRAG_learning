"""[1단계: 읽기] config.py (Neo4j 드라이버, LLM, 임베더 준비 + 벡터 인덱스 2개 생성) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1)로 확인했다.

이 파일은 직접 실행하지 않는다 (__main__ 없음). main.py 가 import 해서
  initialize_connection()  -> (driver, llm, embedder)
  create_vector_indexes()  -> ("text_content_vector_index", "table_content_vector_index")
를 부른다.

흐름
  .env (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, OPENAI_API_KEY)
    -> neo4j 드라이버 (DB 연결)
    -> OpenAILLM gpt-4o (도구 고르기, Cypher 쓰기, 답변 쓰기에 모두 같은 객체를 쓴다)
    -> OpenAIEmbeddings text-embedding-3-small (질문을 1536차원 벡터로)
  벡터 인덱스: TextElement.embedding, TableElement.embedding 에 각각 하나씩

읽는 순서 권장: initialize_connection -> create_vector_indexes
실행 위치: part3/toolsretriever 에서 PYTHONPATH=. python learning/step1_config_annotated.py
  (함수 정의만 있어서 실행해도 아무것도 출력되지 않는다. 주석본은 import 용으로 쓰지 않는다)
전제: Part 2 pdf2kg (+ pdf2kg_2), part3/vectorsearch 로 TextElement 에 embedding 이 들어 있어야 한다.
"""

# [출처] 표준 라이브러리. os.getenv("이름", 기본값): 환경변수 읽기 (없으면 기본값, 기본값도 없으면 None)
import os
# [출처] 외부 라이브러리 python-dotenv. load_dotenv: .env 파일 내용을 환경변수로 등록
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j (공식 파이썬 드라이버). 아래에서 neo4j.GraphDatabase.driver 처럼 "모듈.이름" 으로 쓴다
import neo4j
# [출처] 외부 라이브러리 neo4j-graphrag. OpenAILLM: OpenAI 채팅 모델을 neo4j-graphrag 형식으로 감싼 객체
# (.invoke(글) 로 답을 받고, .invoke_with_tools(...) 로 "어떤 도구를 부를지" 를 받는다. ToolsRetriever 가 후자를 쓴다)
from neo4j_graphrag.llm import OpenAILLM
# OpenAIEmbeddings: 글 -> 숫자 벡터. .embed_query(글) 이 OpenAI embeddings API 를 불러 list[float] 를 돌려준다
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
# create_vector_index: "CREATE VECTOR INDEX ..." Cypher 를 대신 만들어 실행해 주는 함수
from neo4j_graphrag.indexes import create_vector_index

# 환경 변수 로드
# .env 를 읽는다. OpenAILLM/OpenAIEmbeddings 는 OPENAI_API_KEY 환경변수를 자동으로 읽는다 (api_key 를 안 넘기는 이유)
load_dotenv()


# [이 파일에서 정의] 연결 3종 세트를 만들어 튜플로 돌려준다
# [반환] (driver, llm, embedder)
def initialize_connection():
    """Neo4j 연결 및 OpenAI 클라이언트 초기화"""
    uri = os.getenv("NEO4J_URI")
    # 두 번째 인자 "neo4j": NEO4J_USERNAME 이 .env 에 없을 때 쓸 기본값
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")

    # neo4j.GraphDatabase.driver(uri, auth=(아이디, 비밀번호))
    # [출처] 외부 라이브러리 neo4j
    # [입력] uri: "neo4j+s://..." 같은 접속 주소 / auth: (아이디, 비밀번호) 튜플
    # [반환] Driver 객체. 여기서는 아직 접속하지 않는다 (처음 쿼리할 때 접속). verify_connectivity() 를 안 불러서
    #        주소나 비밀번호가 틀려도 이 줄에서는 에러가 안 나고, 아래 인덱스 생성 때 처음 드러난다
    driver = neo4j.GraphDatabase.driver(uri, auth=(username, password))

    # OpenAILLM(model_name=..., model_params={...})
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] model_name: OpenAI 모델 이름 / model_params: OpenAI API 에 그대로 넘길 옵션
    # [반환] LLM 객체
    # temperature 0: 같은 질문엔 최대한 같은 답. 도구 선택과 Cypher 작성이 매번 흔들리지 않게
    llm = OpenAILLM(
        model_name="gpt-4o",
        model_params={"temperature": 0}
    )

    # OpenAIEmbeddings(model=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [반환] 임베더 객체. text-embedding-3-small 은 1536차원 벡터를 만든다 (아래 dimensions=1536 과 맞아야 한다)
    # 주의: vectorsearch 에서 TextElement.embedding 을 만든 모델과 같아야 한다. 모델이 다르면 차원이 같아도 벡터 공간이 달라 엉뚱한 결과가 나온다
    embedder = OpenAIEmbeddings(model="text-embedding-3-small")

    print(f"Neo4j 연결: {uri}")

    # return a, b, c: 세 값을 튜플 하나로 돌려준다. 받는 쪽은 driver, llm, embedder = ... 로 풀어 받는다 (언패킹)
    return driver, llm, embedder


# [이 파일에서 정의] 벡터 인덱스 2개를 만들고 그 이름을 돌려준다
# [반환] (text_index_name, table_index_name). 만들기에 실패해도 이름은 그대로 돌려준다
def create_vector_indexes(driver):
    """TextElement와 TableElement를 위한 벡터 인덱스 생성"""

    # TextElement 벡터 인덱스
    text_index_name = "text_content_vector_index"
    # try / except: try 안에서 에러가 나면 프로그램을 멈추지 않고 except 로 넘어간다
    try:
        # create_vector_index(driver, 이름, label=..., embedding_property=..., dimensions=..., similarity_fn=...)
        # [출처] 외부 라이브러리 neo4j-graphrag
        # [입력] label: 대상 노드 레이블 / embedding_property: 벡터가 든 속성 / dimensions: 벡터 길이 / similarity_fn: "cosine" 또는 "euclidean"
        # [반환] 없음 (None)
        # 내부 동작 (소스 확인): fail_if_exists 기본값 False 라서
        #   CREATE VECTOR INDEX $name IF NOT EXISTS FOR (n:TextElement) ON n.embedding OPTIONS {...}
        #   를 실행한다. Neo4j 가 ClientError 를 내면 Neo4jIndexError 로 바꿔 던진다
        # [왜] VectorRetriever 는 이 인덱스로 db.index.vector.queryNodes 를 불러 "질문 벡터와 가까운 노드" 를 찾는다
        # 주의: IF NOT EXISTS 라서 이미 같은 이름의 인덱스가 있으면 에러 없이 넘어가고, 아래 "생성" 메시지가 그대로 찍힌다.
        #       vectorsearch 에서 같은 TextElement.embedding 에 다른 이름(textElementEmbedding)의 인덱스를 만들어 두었다면
        #       Neo4j 가 이 인덱스를 새로 만들지 않을 수 있다. 그러면 VectorRetriever 생성 때 "No index with name ... found" 가 날 수 있다.
        #       SHOW VECTOR INDEXES 로 실제 이름을 확인해 보자
        create_vector_index(
            driver,
            text_index_name,
            label="TextElement",
            embedding_property="embedding",
            dimensions=1536,
            similarity_fn="cosine",
        )
        print(f"✓ TextElement 벡터 인덱스 생성: {text_index_name}")
    # except Exception as e: 거의 모든 에러를 잡아서 e 에 담는다. 메시지만 찍고 계속 진행
    except Exception as e:
        print(f"  TextElement 벡터 인덱스 이미 존재 또는 생성 실패: {e}")

    # TableElement 벡터 인덱스
    # 표(TableElement)용 인덱스. 위와 같은 모양, 레이블만 다르다
    # 주의: TableElement 에 embedding 속성을 넣는 단계가 없으면 인덱스는 만들어져도 비어 있어서 표 검색 결과가 항상 0건이다
    table_index_name = "table_content_vector_index"
    try:
        create_vector_index(
            driver,
            table_index_name,
            label="TableElement",
            embedding_property="embedding",
            dimensions=1536,
            similarity_fn="cosine",
        )
        print(f"✓ TableElement 벡터 인덱스 생성: {table_index_name}")
    except Exception as e:
        print(f"  TableElement 벡터 인덱스 이미 존재 또는 생성 실패: {e}")

    return text_index_name, table_index_name
