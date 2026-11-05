"""[1단계: 읽기] schema.py (환경변수 확인, Neo4j 드라이버, DB 에서 스키마를 뽑아 LLM 용 글로 만들고 캐시) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j 드라이버 설명은 설치 소스(neo4j 6.1.0, requirements.txt 기준)로 확인했다.

흐름
  get_cached_schema()
    -> (캐시가 비었으면) get_neo4j_driver() -> validate() 로 환경변수 확인 -> 드라이버
    -> get_schema_dict(driver): Cypher 3개로 노드 속성 / 관계 속성 / 관계 방향을 읽어 딕셔너리로
         {"nodes": {"Disease": {"name": "STRING"}, ...}, "relationships": {...}, "relations": ["(:Symptom)-[:INDICATES]->(:Disease)", ...]}
    -> get_schema_str(dict): LLM 프롬프트에 넣을 글로
         Node properties:
         Disease {name: STRING}
         ...
         The relationships:
         (:Symptom)-[:INDICATES]->(:Disease)
    -> _schema_cache 에 저장. 두 번째부터는 DB 에 안 가고 저장된 글을 돌려준다

part3/text2cypher 는 스키마를 사람이 손으로 적었다. 여기서는 DB 를 직접 조회해서 자동으로 만든다.

읽는 순서 권장: get_cached_schema -> get_schema_dict -> get_node_datatype -> get_schema_str -> validate / get_neo4j_driver
실행 위치: 정의만 있는 모듈 (실행해도 출력 없음). nodes.py 가 import 할 때 load_dotenv 와 환경변수 읽기가 실행된다.
전제: 이 폴더 또는 상위 폴더의 .env 에 OPENAI_API_KEY, NEO4J_URI, NEO4J_PASSWORD (Part 2 medical2kg 가 적재된 DB)
"""

# [출처] 표준 라이브러리. os.getenv(이름, 기본값): 환경변수 읽기 (없으면 기본값, 기본값도 없으면 None)
import os
# [출처] 표준 라이브러리 typing. Dict[str, Any] = "키는 str, 값은 아무 타입" 인 딕셔너리라는 타입 힌트
from typing import Dict, Any
# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버
# GraphDatabase.driver(...): 연결 객체 생성 / basic_auth(사용자, 비밀번호): 인증 정보 객체 (튜플 (user, pw) 로 줘도 같다)
from neo4j import GraphDatabase, basic_auth
# neo4j.time.Date: Neo4j 의 날짜 값이 파이썬으로 올 때의 타입 (파이썬 datetime.date 가 아니라 드라이버 고유 타입)
from neo4j.time import Date

# load_dotenv(): [출처] 외부 라이브러리 python-dotenv
# load_dotenv() 를 부른 파일이 있는 폴더부터 위로 올라가며 .env 를 찾아 os.environ 에 넣는다 (소스 확인: find_dotenv). 이미 있는 환경변수는 덮어쓰지 않는다
load_dotenv()

# 모듈 전역 상수: 이 파일이 import 되는 순간 한 번 읽힌다
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
# 데이터베이스 이름. 따로 없으면 사용자 이름과 같게 (Neo4j Aura 는 DB 이름이 사용자 이름과 같다. 로컬 기본은 "neo4j")
# 이 파일에서는 안 쓰고, nodes.py 가 가져가서 execute_query(database_=...) 에 넣는다
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", NEO4J_USERNAME)


# [이 파일에서 정의] 필수 환경변수 3개가 비어 있으면 ValueError 를 일으킨다 [반환] True
def validate():
    """필수 환경 변수가 설정되어 있는지 확인합니다."""
    required = {
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "NEO4J_URI": NEO4J_URI,
        "NEO4J_PASSWORD": NEO4J_PASSWORD,
    }

    # 리스트 컴프리헨션: [만들값 for 변수들 in 반복대상 if 조건]
    # required.items() 는 (키, 값) 쌍을 하나씩 준다 -> name, value 두 변수로 풀어 받는다
    # not value: None 이나 "" 이면 True -> 빠진 이름만 모은다
    missing = [name for name, value in required.items() if not value]

    if missing:
        # raise 예외(메시지): 일부러 에러를 일으켜 실행을 멈춘다. 위로 전달되어 nodes.py import 자체가 실패한다
        # f-string 두 개를 줄바꿈만으로 이어 쓰면 파이썬이 한 문자열로 붙인다 (괄호 안이라 줄을 나눠도 된다)
        raise ValueError(
            f"필수 환경 변수가 누락되었습니다: {', '.join(missing)}\n"
            f".env 파일에 설정해주세요"
        )

    return True


# ============================================
# Neo4j 스키마 관련 함수들
# ============================================


# [이 파일에서 정의] 샘플 값 하나를 보고 Cypher 타입 이름 글을 돌려준다
# [입력] value: DB 에서 꺼낸 속성 값 하나  [반환] "STRING", "INTEGER", "LIST[STRING]" ...
# -> str 은 반환 타입 힌트 (이 함수는 str 을 돌려준다는 표시)
def get_node_datatype(value: Any) -> str:
    """
    입력된 노드 Value의 데이터 타입을 반환하는 함수

    Args:
        value: 노드의 속성 값

    Returns:
        str: 데이터 타입 문자열 (STRING, INTEGER, FLOAT, BOOLEAN, LIST, DATE 등)
    """
    # isinstance(값, 타입): [출처] 파이썬 기본. 값이 그 타입(또는 그 자식 타입)이면 True
    if isinstance(value, str):
        return "STRING"
    # 주의: 파이썬에서 bool 은 int 의 자식 타입이라 isinstance(True, int) 가 True 다 (직접 실행해 확인).
    #       그래서 아래 BOOLEAN 줄에 도달하지 못하고 True/False 값도 "INTEGER" 로 나온다. bool 검사를 int 보다 먼저 해야 한다
    elif isinstance(value, int):
        return "INTEGER"
    elif isinstance(value, float):
        return "FLOAT"
    elif isinstance(value, bool):
        return "BOOLEAN"
    elif isinstance(value, list):
        # 조건식 + 재귀: 리스트면 첫 원소의 타입을 다시 이 함수로 알아내 LIST[STRING] 처럼. 빈 리스트면 그냥 "LIST"
        return f"LIST[{get_node_datatype(value[0])}]" if value else "LIST"
    elif isinstance(value, Date):
        return "DATE"
    # DateTime, Point 같은 다른 타입은 모두 UNKNOWN
    else:
        return "UNKNOWN"


# [이 파일에서 정의] DB 를 조회해 스키마 딕셔너리를 만든다
# [입력] driver: Neo4j 드라이버  [반환] {"nodes": {...}, "relationships": {...}, "relations": [...]}
# 타입 힌트 GraphDatabase.driver 는 사실 "드라이버를 만드는 함수" 이름이다 (정확한 타입은 neo4j.Driver). 실행에는 영향 없다
def get_schema_dict(driver: GraphDatabase.driver) -> Dict[str, Any]:
    """
    Graph DB의 정보를 받아 노드 및 관계의 프로퍼티를 추출하고 스키마 딕셔너리를 반환하는 함수

    Args:
        driver: Neo4j 드라이버 인스턴스

    Returns:
        Dict: 노드, 관계, 관계 방향 정보를 담은 딕셔너리
              {"nodes": {...}, "relationships": {...}, "relations": [...]}
    """
    # with A as B: 문법. 블록에 들어갈 때 B 를 열고, 블록이 끝나면(에러가 나도) 자동으로 닫는다
    # driver.session(): [출처] 외부 라이브러리 neo4j. 쿼리를 보내는 작업 단위(세션)를 연다. database 를 안 주면 서버의 기본(home) DB
    with driver.session() as session:
        # 노드 프로퍼티 및 타입 추출
        # 노드 속성 조회 Cypher: 모든 노드 n 의 (레이블, 속성 키, 그 노드의 값) 을 한 줄씩
        # UNWIND 리스트 AS x: 리스트를 풀어 원소마다 한 줄로 만든다
        # 주의: WITH DISTINCT 에 n 자체가 들어 있어서 노드마다 다 달라 DISTINCT 가 걸러 주는 게 거의 없다.
        #       즉 "모든 노드 x 모든 속성" 을 다 가져온다. 노드가 많은 DB 에서는 느릴 수 있다
        node_query = """
        MATCH (n)
        WITH DISTINCT labels(n) AS node_labels, keys(n) AS property_keys, n
        UNWIND node_labels AS label
        UNWIND property_keys AS key
        RETURN label, key, n[key] AS sample_value
        """
        # session.run(쿼리): [출처] 외부 라이브러리 neo4j
        # [반환] Result (결과를 하나씩 꺼내는 반복 객체). for record in nodes 로 Record 를 받는다
        # 같은 세션에서 다음 run 을 부르면 드라이버가 이전 결과를 메모리에 다 받아 둔다 (소스 확인: session.run 안 _buffer_all)
        # -> 그래서 쿼리 3개를 먼저 다 보내고 아래에서 차례로 읽어도 결과가 사라지지 않는다
        nodes = session.run(node_query)

        # 관계 프로퍼티 및 타입 추출
        # 관계 속성 조회: 모든 관계 r 의 (타입, 속성 키, 값). 속성이 없는 관계는 UNWIND 할 게 없어 줄이 안 나온다
        rel_query = """
        MATCH ()-[r]->()
        WITH DISTINCT type(r) AS rel_type, keys(r) AS property_keys, r
        UNWIND property_keys AS key
        RETURN rel_type, key, r[key] AS sample_value
        """
        relationships = session.run(rel_query)

        # 관계 유형 및 방향 추출
        # 관계 방향 조회: (시작 레이블 리스트, 관계 타입, 끝 레이블 리스트) 의 중복 없는 조합
        rel_direction_query = """
        MATCH (a)-[r]->(b)
        RETURN DISTINCT labels(a) AS start_label, type(r) AS rel_type, labels(b) AS end_label
        ORDER BY start_label, rel_type, end_label
        """
        rel_directions = session.run(rel_direction_query)

        # 스키마 딕셔너리 생성
        # 빈 딕셔너리/리스트로 틀을 먼저 만든다
        schema = {"nodes": {}, "relationships": {}, "relations": []}

        # record["label"]: Record 는 딕셔너리처럼 RETURN 의 별칭 이름으로 값을 꺼낸다
        for record in nodes:
            label = record["label"]
            key = record["key"]
            sample_value = record["sample_value"]  # 데이터 타입을 추론하기 위한 샘플 데이터
            inferred_type = get_node_datatype(sample_value)
            # 레이블이 처음 나오면 빈 딕셔너리를 만든다. 같은 (레이블, 키) 가 여러 번 나오면 마지막 샘플의 타입으로 덮어쓴다
            if label not in schema["nodes"]:
                schema["nodes"][label] = {}
            schema["nodes"][label][key] = inferred_type

        for record in relationships:
            rel_type = record["rel_type"]
            key = record["key"]
            sample_value = record["sample_value"]  # 데이터 타입을 추론하기 위한 샘플 데이터
            inferred_type = get_node_datatype(sample_value)
            if rel_type not in schema["relationships"]:
                schema["relationships"][rel_type] = {}
            schema["relationships"][rel_type][key] = inferred_type

        for record in rel_directions:
            # ["start_label"][0]: 레이블 리스트의 첫 번째만 쓴다
            # 주의: 레이블이 여러 개인 노드는 첫 레이블만 보이고, 레이블이 없는 노드가 있으면 [0] 에서 IndexError 가 날 수 있다
            start_label = record["start_label"][0]
            rel_type = record["rel_type"]
            end_label = record["end_label"][0]
            # f"(:{start_label})-[:{rel_type}]->(:{end_label})" -> "(:Symptom)-[:INDICATES]->(:Disease)" 같은 화살표 글
            schema["relations"].append(f"(:{start_label})-[:{rel_type}]->(:{end_label})")

        return schema


# [이 파일에서 정의] 스키마 딕셔너리 -> LLM 에 넣을 글. 형식은 part3/text2cypher 의 schema_to_text 와 같다
def get_schema_str(schema: Dict[str, Any]) -> str:
    """
    스키마 딕셔너리를 LLM에 제공하기 위해 원하는 형태로 formatting 하는 함수

    Args:
        schema: get_schema_dict()에서 반환된 스키마 딕셔너리

    Returns:
        str: 포맷팅된 스키마 문자열
    """
    # 줄을 리스트에 모았다가 맨 끝에 "\n".join 으로 한 번에 잇는다
    result = []

    # 노드 프로퍼티 출력
    result.append("Node properties:")
    for label, properties in schema["nodes"].items():
        # ", ".join(f"..." for k, v in ...): 괄호 안의 for 는 제너레이터 식 (리스트를 만들지 않고 하나씩 넘긴다). 결과: "name: STRING, code: STRING"
        props = ", ".join(f"{k}: {v}" for k, v in properties.items())
        # {{ 는 글자 {, }} 는 글자 }. {{{props}}} = 글자 { + props 값 + 글자 }
        result.append(f"{label} {{{props}}}")

    # 관계 프로퍼티 출력
    # 앞의 \n: 구역 사이에 빈 줄을 하나 넣으려고
    result.append("\nRelationship properties:")
    for rel_type, properties in schema["relationships"].items():
        props = ", ".join(f"{k}: {v}" for k, v in properties.items())
        result.append(f"{rel_type} {{{props}}}")

    # 관계 방향 출력
    result.append("\nThe relationships:")
    for relation in schema["relations"]:
        result.append(relation)

    return "\n".join(result)


# [이 파일에서 정의] 환경변수 확인 후 드라이버 생성 [반환] Driver
# GraphDatabase.driver(uri, auth=...): 만들기만 하고 실제 접속은 첫 쿼리 때 한다 (연결 확인 verify_connectivity 는 부르지 않는다)
def get_neo4j_driver() -> GraphDatabase.driver:
    """
    Neo4j 드라이버 인스턴스 생성

    Returns:
        GraphDatabase.driver: Neo4j 드라이버 인스턴스
    """
    validate()

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=basic_auth(NEO4J_USERNAME, NEO4J_PASSWORD)
    )
    return driver


# 전역 스키마 캐시
# 전역 캐시: 모듈 전역 딕셔너리. 함수 안에서 _schema_cache["키"] = 값 처럼 "안의 값" 을 바꾸는 것은 global 선언 없이 된다
# (이름 자체에 새 값을 대입할 때만 global 이 필요하다)
# 이름 앞의 _ : "이 모듈 안에서만 쓰는 것" 이라는 관례 표시 (강제는 아니다)
_schema_cache = {
    "schema_dict": None,
    "schema_str": None,
}


# [이 파일에서 정의] 스키마 글을 돌려준다. 처음 한 번만 DB 에 가고 이후는 저장된 글
# [입력] refresh: True 면 DB 를 다시 읽는다 (데이터를 새로 적재한 뒤)  [반환] 스키마 글
def get_cached_schema(refresh: bool = False) -> str:
    """
    스키마 문자열 반환 (캐싱 지원)

    Args:
        refresh: True면 스키마를 다시 추출

    Returns:
        str: 포맷팅된 스키마 문자열
    """
    if _schema_cache["schema_str"] is None or refresh:
        driver = get_neo4j_driver()
        # try/finally: 중간에 에러가 나도 finally 블록(driver.close)은 반드시 실행된다 -> 연결이 남지 않는다
        # 스키마 전용으로 드라이버를 잠깐 만들고 바로 닫는다 (nodes.py 는 쿼리 실행용 드라이버를 따로 만든다)
        try:
            _schema_cache["schema_dict"] = get_schema_dict(driver)
            _schema_cache["schema_str"] = get_schema_str(_schema_cache["schema_dict"])
        finally:
            driver.close()

    return _schema_cache["schema_str"]
