"""[1단계: 읽기] ingest_to_qdrant.py (Neo4j 의 TextElement 를 읽어 OpenAI 로 임베딩하고 Qdrant 에 저장) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
주석 속 "N줄" 은 원본 파일의 줄 번호다 (이 주석본의 줄 번호와 다르다).
qdrant-client 설명은 설치 소스(requirements.txt 의 qdrant-client 1.17.1)로 확인했다.

전제: Part 2 pdf2kg.py (+ pdf2kg_2.py) 로 TextElement, Chunk, TOC 가 Neo4j 에 있어야 한다.
      .env 에 NEO4J_*, OPENAI_API_KEY, QDRANT_URL, QDRANT_KEY, (선택) QDRANT_COLLECTION (기본 "pdf2kg") 필요.
주의: 실제로 Qdrant 에 쓰는 프로그램이다. 이미 데이터가 있을 때 y 를 누르면 컬렉션 전체를 지우고 다시 만든다.

흐름
  [Step 1] Qdrant 컬렉션 확인/생성 (벡터 1536차원, cosine)
           이미 점(point)이 있으면 "지우고 다시?" 를 묻는다 -> N 이면 종료
  [Step 2] Neo4j: TextElement + (속한 Chunk 의) TOC 제목/레벨 조회 -> TextElementData 리스트
  [Step 3] 원소마다: OpenAI 임베딩 1번 -> PointStruct(id=무작위 UUID, vector, payload{element_id, toc_id, page, toc_title, toc_level, content})
           10개 모일 때마다 upsert, 남은 것 마지막에 upsert

  Qdrant 용어: collection(컬렉션) = 벡터를 담는 표 하나, point(점) = 벡터 1개 + id + payload(붙여 둔 딕셔너리)
  두 저장소를 잇는 열쇠: payload["element_id"] == Neo4j TextElement.element_id (graphrag_qdrant.py 가 이걸로 다시 찾는다)

읽는 순서 권장: __main__ (240줄) -> create_qdrant_collection -> fetch_text_elements_from_neo4j -> ingest_text_elements_to_qdrant
실행 위치: part3/vectorcypher_qdrant  ->  python learning/step1_ingest_to_qdrant_annotated.py
"""

# [출처] 표준 라이브러리 os. 환경변수 읽기
import os
# [출처] 표준 라이브러리 uuid. uuid.uuid4() = 무작위 고유 ID (Qdrant point id 로 쓴다)
import uuid
# [출처] 표준 라이브러리 dataclasses. @dataclass 데코레이터 (19줄 설명)
from dataclasses import dataclass
# [출처] 표준 라이브러리 typing. List[X] = "X 들의 리스트" 라는 타입 힌트 (요즘은 list[X] 로도 쓴다)
from typing import List

# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 openai (OpenAI 공식 SDK). 여기서는 neo4j-graphrag 를 거치지 않고 직접 임베딩을 만든다
from openai import OpenAI
# [출처] 외부 라이브러리 qdrant-client. QdrantClient: Qdrant 서버와 이야기하는 객체
from qdrant_client import QdrantClient
# qdrant_client.models: 요청에 쓰는 데이터 모양(pydantic 모델)
#   Distance: 거리 방식 열거형 (COSINE, EUCLID, DOT, MANHATTAN)
#   PointStruct: 저장할 점 하나 (id, vector, payload)
#   VectorParams: 컬렉션의 벡터 설정 (size=차원, distance=거리 방식)
from qdrant_client.models import Distance, PointStruct, VectorParams

# .env 를 환경변수로 등록. 아래 함수 기본값의 os.getenv(...) 보다 먼저 실행되어야 해서 맨 위에 있다
load_dotenv()


# ============================================
# 데이터 구조
# ============================================

# @dataclass: [출처] 표준 라이브러리. 데코레이터(@이름)는 바로 아래 클래스/함수를 감싸 기능을 덧붙인다
# -> 아래처럼 "이름: 타입" 만 적으면 __init__(생성자), 보기 좋은 출력(__repr__), == 비교를 자동으로 만들어 준다
#    TextElementData(element_id="...", toc_id="...", content="...", page=3) 처럼 만든다
# 기본값(= None)이 있는 필드는 기본값 없는 필드 뒤에 와야 한다
@dataclass
class TextElementData:
    """TextElement 데이터 구조"""
    element_id: str
    toc_id: str
    content: str
    page: int
    # toc_title: str = None: 타입 힌트는 str 이지만 None 이 들어갈 수 있다 (정확히는 Optional[str]). 힌트는 검사되지 않는다
    toc_title: str = None
    toc_level: int = None


# ============================================
# 클라이언트 생성
# ============================================

# [이 파일에서 정의] Neo4j 드라이버 생성 + 연결 확인 [반환] Driver
# (vectorsearch.py 의 같은 함수와 달리 try/except 없이, 실패하면 verify_connectivity 의 예외가 그대로 올라간다)
def create_neo4j_driver():
    """Neo4j 드라이버 생성"""
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # all([...]): 셋 다 값이 있어야 True
    if not all([uri, username, password]):
        raise ValueError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD 환경 변수를 설정해주세요.")

    driver = GraphDatabase.driver(uri, auth=(username, password))
    driver.verify_connectivity()
    print(f"Neo4j 연결 성공: {uri}")
    return driver


# [이 파일에서 정의] Qdrant 클라이언트 생성 [반환] QdrantClient
def create_qdrant_client():
    """Qdrant 클라이언트 생성"""
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_KEY")

    if not url:
        raise ValueError("QDRANT_URL 환경 변수를 설정해주세요.")

    # QdrantClient(url=..., api_key=...)
    # [출처] 외부 라이브러리 qdrant-client
    # [입력] url: Qdrant 서버 주소 (Qdrant Cloud 주소) / api_key: 클라우드 키 (주면 https 를 기본으로 쓴다)
    # [반환] 클라이언트 객체. get_collections, create_collection, upsert, query_points 등을 부른다
    # 내부 (소스 확인): 만들 때 접속을 확인하지 않는다. 서버 버전 호환성 검사만 백그라운드 스레드에서 하고, 문제가 있으면 경고만 띄운다
    # 주의: 그래서 58줄 "연결 성공" 은 실제 접속 확인이 아니다. 주소나 키가 틀리면 93줄 get_collections 에서 처음 에러가 난다
    client = QdrantClient(url=url, api_key=api_key)
    print(f"Qdrant 연결 성공: {url}")
    return client


# [이 파일에서 정의] OpenAI 클라이언트 생성 [반환] openai.OpenAI
def create_openai_client():
    """OpenAI 클라이언트 생성"""
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경 변수를 설정해주세요.")

    # OpenAI(api_key=...): [출처] 외부 라이브러리 openai. .embeddings.create(...) 로 임베딩 API 를 부른다
    client = OpenAI(api_key=api_key)
    # {} 자리가 없는 f-string. f 를 빼도 결과는 같다
    print(f"OpenAI 클라이언트 생성 완료")
    return client


# ============================================
# Qdrant Collection 관리
# ============================================

# [이 파일에서 정의] 컬렉션이 없으면 만들고, 있으면 그대로 둔다
def create_qdrant_collection(
    qdrant_client: QdrantClient,
    # 기본값 os.getenv(...): 기본값은 "함수를 정의할 때(파일을 import 할 때) 한 번" 계산된다.
    # 나중에 환경변수를 바꿔도 이 기본값은 안 바뀐다 (여기서는 12줄 load_dotenv 뒤라 .env 값이 들어간다)
    collection_name: str = os.getenv("QDRANT_COLLECTION", "pdf2kg"),
    vector_size: int = 1536,
    # Distance.COSINE: 벡터의 방향(의미)을 비교. 텍스트 임베딩의 표준
    distance: Distance = Distance.COSINE
):
    """
    Qdrant 컬렉션 생성

    Args:
        qdrant_client: Qdrant 클라이언트
        collection_name: 컬렉션 이름
        vector_size: 벡터 차원 (text-embedding-3-small: 1536)
        distance: 거리 측정 방식 (COSINE, EUCLID, DOT)
    """
    # qdrant_client.get_collections()
    # [출처] 외부 라이브러리 qdrant-client
    # [반환] CollectionsResponse. .collections 는 CollectionDescription 리스트 (각각 .name 만 있다)
    collections = qdrant_client.get_collections().collections
    # [c.name for c in collections]: 리스트 컴프리헨션. [출처] 파이썬 기본
    # "collections 의 각 c 에 대해 c.name 을 모은 새 리스트" 를 한 줄로 만든다
    existing = [c.name for c in collections]

    # x in 리스트: 리스트 안에 x 가 있으면 True
    if collection_name in existing:
        print(f"Qdrant 컬렉션 '{collection_name}' 이미 존재")
    else:
        # qdrant_client.create_collection(collection_name=..., vectors_config=VectorParams(size=..., distance=...))
        # [출처] 외부 라이브러리 qdrant-client
        # [입력] collection_name: 이름 / vectors_config: 벡터 차원과 거리 방식
        # [반환] bool (성공 여부)
        # [왜] size=1536 은 text-embedding-3-small 의 출력 길이. 다르면 upsert 때 차원 오류
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=distance
            )
        )
        print(f"Qdrant 컬렉션 '{collection_name}' 생성 완료")


# [이 파일에서 정의] 컬렉션 삭제 (안의 점도 모두 사라진다)
def delete_qdrant_collection(
    qdrant_client: QdrantClient,
    collection_name: str = os.getenv("QDRANT_COLLECTION", "pdf2kg")
):
    """Qdrant 컬렉션 삭제"""
    # delete_collection(collection_name=...): [출처] qdrant-client [반환] bool
    qdrant_client.delete_collection(collection_name=collection_name)
    print(f"Qdrant 컬렉션 '{collection_name}' 삭제 완료")


# ============================================
# Neo4j 데이터 조회
# ============================================

# [이 파일에서 정의] Neo4j 에서 TextElement 와 소속 TOC 정보를 읽어 TextElementData 리스트로
def fetch_text_elements_from_neo4j(neo4j_driver):
    """
    Neo4j에서 모든 TextElement 노드와 TOC 정보를 가져오기

    Returns:
        TextElementData 리스트
    """
    # Cypher (여러 줄 문자열)
    #   MATCH (element:TextElement)                      : 모든 TextElement
    #   OPTIONAL MATCH (chunk:Chunk)-[:HAS_ELEMENT]->(element)  : 그 원소를 가진 Chunk (없어도 행 유지)
    #   OPTIONAL MATCH (toc:TOC)-[:HAS_CHUNK]->(chunk)   : 그 Chunk 가 속한 목차
    #   RETURN ... ORDER BY element.element_id          : 원소 ID 순으로
    # 주의: 한 TextElement 가 Chunk 여러 개(또는 TOC 여러 개)에 걸려 있으면 같은 원소가 여러 행으로 나와 Qdrant 에 중복 저장될 수 있다
    query = """
    MATCH (element:TextElement)
    OPTIONAL MATCH (chunk:Chunk)-[:HAS_ELEMENT]->(element)
    OPTIONAL MATCH (toc:TOC)-[:HAS_CHUNK]->(chunk)
    RETURN
        element.element_id AS element_id,
        element.toc_id AS toc_id,
        element.content AS content,
        element.page AS page,
        toc.title AS toc_title,
        toc.level AS toc_level
    ORDER BY element.element_id
    """

    # with A as B: [출처] 파이썬 기본 (컨텍스트 매니저). 블록이 끝나면(에러가 나도) 세션을 자동으로 닫는다
    # neo4j_driver.session(): [출처] neo4j. 쿼리를 보내는 세션 하나를 연다
    with neo4j_driver.session() as session:
        # session.run(query): [출처] neo4j. Cypher 실행 [반환] Result (Record 를 하나씩 꺼낼 수 있는 객체)
        # 결과는 세션이 열려 있을 때 다 읽어야 한다 -> 그래서 아래 리스트 만들기를 with 안에서 한다
        result = session.run(query)
        # [TextElementData(...) for record in result if record["content"]]
        # 리스트 컴프리헨션 + if 거르기: content 가 비어 있지 않은 Record 만 객체로 바꿔 모은다
        elements = [
            TextElementData(
                element_id=record["element_id"],
                toc_id=record["toc_id"],
                # record["content"] or "": None 이면 빈 글로 (155줄에서 이미 걸렀으므로 사실상 그대로)
                # record["키"]: 그 열의 값 / record.get("키"): [출처] neo4j. 키(열 이름)가 없을 때만 None. 열이 있고 값이 null 이어도 None
                content=record["content"] or "",
                # page 가 null 이면 0
                page=record["page"] or 0,
                toc_title=record.get("toc_title"),
                toc_level=record.get("toc_level")
            )
            for record in result
            if record["content"]  # content가 있는 것만
        ]

    # len(리스트): 개수
    print(f"✓ Neo4j에서 {len(elements)}개 TextElement 조회 완료")
    return elements


# ============================================
# Qdrant 수집
# ============================================

# [이 파일에서 정의] TextElementData 마다 임베딩 -> PointStruct -> batch_size 개씩 Qdrant 에 upsert
# elements: List[TextElementData]: 타입 힌트 (TextElementData 리스트)
def ingest_text_elements_to_qdrant(
    elements: List[TextElementData],
    qdrant_client: QdrantClient,
    openai_client: OpenAI,
    # 여기도 기본값은 import 때 한 번 계산 (80줄 설명)
    collection_name: str = os.getenv("QDRANT_COLLECTION", "pdf2kg"),
    batch_size: int = 10,
    embedding_model: str = "text-embedding-3-small"
):
    """
    TextElement 데이터를 Qdrant에 수집

    Args:
        elements: TextElementData 리스트
        qdrant_client: Qdrant 클라이언트
        openai_client: OpenAI 클라이언트
        collection_name: Qdrant 컬렉션 이름
        batch_size: 배치 크기 (임베딩 생성 속도 제한 고려)
        embedding_model: 임베딩 모델
    """
    print(f"\n{'='*80}")
    print(f"Qdrant 수집 시작: {len(elements)}개 TextElements")
    print(f"{'='*80}\n")

    # 업로드를 기다리는 점들을 모아 두는 리스트
    points = []

    # enumerate(elements, 1): (1부터 번호, 원소)
    for idx, element in enumerate(elements, 1):
        # 임베딩 생성
        # openai_client.embeddings.create(input=글, model=모델)
        # [출처] 외부 라이브러리 openai
        # [입력] input: 글 하나 (글 리스트도 받는다) / model: 임베딩 모델
        # [반환] 응답 객체. .data 는 입력 순서대로의 결과 리스트, .data[0].embedding 이 숫자 리스트(1536개)
        # 주의: 원소 하나마다 API 를 한 번 부른다. input 에 글 리스트를 넣으면 한 번에 여러 개를 받을 수 있어 훨씬 빠르다
        response = openai_client.embeddings.create(
            input=element.content,
            model=embedding_model
        )
        embedding = response.data[0].embedding

        # Qdrant Point 생성
        # PointStruct(id=..., vector=..., payload={...})
        # [출처] 외부 라이브러리 qdrant-client
        # [입력] id: 점 ID. 클라이언트 타입은 정수 / 글 / UUID. 글이면 서버가 UUID 모양만 받는 것으로 알려져 있다 (서버 쪽은 확인 못 함) -> str(uuid.uuid4())
        #        vector: 숫자 리스트 / payload: 점에 붙여 둘 딕셔너리 (검색 결과와 함께 돌려받을 수 있다)
        # [왜] payload 의 element_id 가 Neo4j 노드로 돌아가는 열쇠. content, toc 는 Qdrant 만 봐도 내용을 알 수 있게 (디버깅용, 이중 저장)
        # 주의: uuid4 는 매번 무작위라 다시 적재하면 같은 원소가 다른 ID 로 또 들어간다 (그래서 __main__ 에서 컬렉션을 지우고 다시 만든다).
        #       uuid.uuid5(namespace, element_id) 처럼 정해진 ID 를 쓰면 upsert 만으로 덮어쓸 수 있다
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "element_id": element.element_id,
                "toc_id": element.toc_id,
                "page": element.page,
                "toc_title": element.toc_title,
                "toc_level": element.toc_level,
                "content": element.content
            }
        )
        # 리스트.append(x): 끝에 하나 추가
        points.append(point)

        # 배치 단위로 Qdrant에 업로드
        # len(points) >= batch_size: 10개가 모이면 한 번에 올린다 (요청 수를 줄이려고)
        if len(points) >= batch_size:
            # qdrant_client.upsert(collection_name=..., points=[...])
            # [출처] 외부 라이브러리 qdrant-client
            # [입력] collection_name / points: PointStruct 리스트
            # [반환] UpdateResult. wait 기본값 True 라서 서버에 실제로 반영된 뒤에 돌아온다
            # upsert = update + insert: 같은 id 가 있으면 덮어쓰고, 없으면 새로 넣는다
            qdrant_client.upsert(
                collection_name=collection_name,
                points=points
            )
            print(f"  [{idx}/{len(elements)}] {len(points)}개 벡터 업로드 완료")
            # 비우고 다음 묶음을 다시 모은다
            points = []

    # 남은 벡터 업로드
    # for 문이 끝난 뒤 10개가 안 되는 나머지가 있으면 마지막으로 올린다 (if points: 빈 리스트면 거짓)
    if points:
        qdrant_client.upsert(
            collection_name=collection_name,
            points=points
        )
        print(f"  [{len(elements)}/{len(elements)}] {len(points)}개 벡터 업로드 완료")

    print(f"\n{'='*80}")
    print(f"✓ Qdrant 수집 완료: 총 {len(elements)}개 벡터")
    print(f"{'='*80}\n")


# ============================================
# 메인 함수
# ============================================

# 이 파일을 직접 실행할 때만 아래가 실행된다 (main 함수 없이 바로 씀)
if __name__ == "__main__":
    # [출처] 표준 라이브러리 sys. sys.exit(코드) 로 프로그램 종료
    import sys

    print("="*80)
    print("Neo4j TextElements → Qdrant 임베딩 수집") # TextElements 노드 찾기
    print("="*80)

    # try / except / finally: 에러가 나면 except, 그리고 무슨 일이 있어도 마지막에 finally
    try:
        # 클라이언트 초기화
        neo4j_driver = create_neo4j_driver()
        qdrant_client = create_qdrant_client()
        openai_client = create_openai_client()

        collection_name = os.getenv("QDRANT_COLLECTION", "pdf2kg")

        # Step 1: Qdrant 컬렉션 생성/확인
        print(f"\n[Step 1] Qdrant 컬렉션 '{collection_name}' 확인/생성")
        # 컬렉션이 없을 때만 만든다
        create_qdrant_collection(qdrant_client, collection_name)    # 컬렉션 이름이 없으면 새로 생성해주는 함수

        # 이미 저장된 벡터가 있는지 확인
        # qdrant_client.get_collection(이름)
        # [출처] 외부 라이브러리 qdrant-client
        # [반환] CollectionInfo (상태, 설정, points_count 등)
        collection_info = qdrant_client.get_collection(collection_name)
        # points_count: 저장된 점 개수. 소스상 타입은 Optional[int]
        # 주의: 서버가 None 을 돌려주면 다음 줄 None > 0 에서 TypeError 가 날 수 있다
        points_count = collection_info.points_count

        if points_count > 0:
            print(f"\n이미 {points_count}개의 벡터가 저장되어 있습니다.")
            # input("안내글"): [출처] 파이썬 기본. 키보드 입력을 글로 받는다
            # .strip(): 앞뒤 공백 제거 / .lower(): 소문자로 -> "Y", " y " 도 'y' 가 된다. 그냥 Enter 면 '' 라서 N 취급
            response = input("기존 데이터를 삭제하고 다시 수집하시겠습니까? (y/N): ").strip().lower()

            if response == 'y':
                # 지우고 다시 만들기 (위 uuid4 중복 문제를 피하는 방법)
                delete_qdrant_collection(qdrant_client, collection_name)
                create_qdrant_collection(qdrant_client, collection_name)
            else:
                print("\n수집을 건너뜁니다.")
                # 닫고 종료. sys.exit 는 SystemExit 예외를 던지는데, 이건 Exception 의 자식이 아니라 except Exception 에 안 잡힌다.
                # 대신 finally 는 실행되어 드라이버 close 가 한 번 더 불린다
                neo4j_driver.close()
                sys.exit(0)

        # Step 2: Neo4j에서 TextElement 가져오기
        print(f"\n[Step 2] Neo4j에서 TextElement 조회")
        elements = fetch_text_elements_from_neo4j(neo4j_driver)

        if not elements:
            print("\nNeo4j에 TextElement 데이터가 없습니다.")
            print("먼저 pdf2kg.py를 실행하여 PDF를 Neo4j에 로드하세요.")
            neo4j_driver.close()
            # 데이터가 없으면 안내만 하고 종료 코드 1 (실패) 로 끝낸다
            sys.exit(1)

        # Step 3: Qdrant에 임베딩 저장
        print(f"\n[Step 3] Qdrant에 임베딩 저장")
        # 여기서 실제 임베딩 + 업로드
        ingest_text_elements_to_qdrant(
            elements=elements,
            qdrant_client=qdrant_client,
            openai_client=openai_client,
            collection_name=collection_name,
            batch_size=10,
            embedding_model="text-embedding-3-small"
        )
    # 주의: 에러 메시지만 출력하고 삼킨다. 어디서 났는지(traceback)가 안 보이고, 종료 코드도 0(성공)이 된다
    except Exception as e:
        print(f"\n오류 발생: {e}")
    finally:
        # 'neo4j_driver' in locals(): 그 이름의 변수가 만들어졌는지 확인 (249줄 전에 실패하면 없다).
        # 파일 맨 바깥에서 locals() 는 전역 변수 딕셔너리라서 이 확인이 동작한다
        if 'neo4j_driver' in locals():
            neo4j_driver.close()
