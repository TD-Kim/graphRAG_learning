"""
[1단계: 읽기] csv2kg.py 의 상세 주석 버전 (동작은 원본과 동일)

주석 읽는 법 (함수나 문법이 처음 나올 때마다 아래 형식으로 적었다. 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나
  [반환] 무엇이 나오나
  [왜]   여기서 왜 쓰나

흐름: 연결 -> (DB 초기화 + 제약조건) -> 노드 4종 -> 관계 4종 -> 통계
읽는 순서 권장: 맨 아래 main() 을 먼저 읽고, 위에서부터 함수를 하나씩.

실행 위치: part2/csv2kg  ->  python learning/step1_annotated.py
(원본과 똑같이 Neo4j 를 초기화하고 다시 적재한다)
"""

# ============================================================
# import
# ============================================================

# [출처] 파이썬 표준 라이브러리 os
# [왜]   os.getenv("이름") 으로 환경변수를 읽으려고
import os

# [출처] 파이썬 표준 라이브러리 pathlib. 파일 경로를 객체로 다룬다 (Path("a") / "b")
from pathlib import Path

# [출처] 외부 라이브러리 pandas (pip install pandas). 표 형태 데이터(DataFrame)를 다루는 라이브러리
# "as pd" : 긴 이름 대신 pd 라는 별명으로 쓰겠다는 뜻 (pandas 는 거의 항상 pd 로 쓴다)
import pandas as pd

# [출처] 외부 라이브러리 python-dotenv (pip install python-dotenv)
#   load_dotenv : .env 파일의 "이름=값" 줄들을 환경변수로 올려 준다
from dotenv import load_dotenv

# [출처] 외부 라이브러리 neo4j (공식 파이썬 드라이버, pip install neo4j)
#   GraphDatabase : 드라이버를 만드는 진입점. GraphDatabase.driver(...) 로 쓴다
from neo4j import GraphDatabase

# load_dotenv()
# [출처] python-dotenv
# [입력] 없음 (기본: 현재 위치에서 위쪽 폴더로 올라가며 .env 파일을 찾는다)
# [반환] .env 를 찾아 읽었으면 True, 못 찾았으면 False
# [왜]   비밀번호를 코드에 쓰지 않고 .gitignore 된 .env 로만 관리하려고
load_dotenv()

# os.getenv("이름")
# [출처] 파이썬 표준 라이브러리 os
# [입력] 환경변수 이름 (두 번째 인자로 기본값을 줄 수도 있다: os.getenv("X", "기본"))
# [반환] 값(문자열). 없으면 None (또는 기본값)
# [왜]   AuraDB 무료 인스턴스는 데이터베이스 이름이 사용자 이름과 같아서, 사용자 이름을 DB 이름으로 쓴다
#        대문자 변수 이름은 "바꾸지 않을 상수" 라는 파이썬 관례
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")

# 노트북(titanic.ipynb)이 만든 CSV 위치
# Path(__file__) : 이 파일의 경로 (__file__ 은 파이썬이 자동으로 넣어 주는 변수)
# .resolve()     : 절대 경로로 / .parent : 한 단계 위 폴더 / / "output" : 경로 이어 붙이기
# [왜] 원본은 "./output" 이라 csv2kg 폴더에서만 동작한다. 이렇게 하면 어디서 실행해도 찾는다
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


# ============================================================
# 1단계: Neo4j 연결
# def 함수이름(매개변수들): -> 함수 정의. 호출할 때 넘긴 값이 매개변수에 들어간다
# ============================================================
def create_neo4j_driver(uri, username, password):
    """[이 파일에서 정의] 드라이버를 만들고 실제로 접속되는지 확인한 뒤 돌려준다."""

    # GraphDatabase.driver(uri, auth=(사용자, 비밀번호))
    # [출처] neo4j 드라이버
    # [입력] uri: "neo4j+s://xxxx.databases.neo4j.io" 같은 접속 주소
    #        auth: (사용자, 비밀번호) 튜플. 괄호로 묶은 값 묶음을 튜플이라고 한다
    # [반환] Driver 객체. 내부에 연결 풀(재사용 가능한 연결 묶음)을 가진다
    # [왜]   모든 쿼리는 이 드라이버를 통해 보낸다. 무거운 객체라 프로그램 전체에서 하나만 만든다
    #        주의: 이 줄에서는 아직 접속하지 않는다(필요할 때 접속하는 "게으른" 방식)
    driver = GraphDatabase.driver(uri, auth=(username, password))

    # try: ... except 예외종류 as e: ...
    # [출처] 파이썬 기본 문법 (예외 처리)
    # [왜]   try 블록에서 에러가 나면 프로그램이 바로 죽지 않고 except 블록으로 넘어온다
    #        e 에는 에러 객체가 들어 있다. Exception 은 거의 모든 에러의 부모 클래스
    try:
        # driver.verify_connectivity()
        # [출처] neo4j 드라이버
        # [입력] 없음
        # [반환] 없음. 접속이 안 되면 예외를 던진다
        # [왜]   주소/비밀번호가 틀렸을 때 첫 쿼리가 아니라 지금 바로 실패시키려고
        driver.verify_connectivity()
        print(f"Neo4j 연결 성공: {uri}")      # f-string: {} 안에 변수 값이 들어간다
    except Exception as e:
        print(f"Neo4j 연결 실패: {e}")
        # raise (뒤에 아무것도 없이): 방금 잡은 예외를 다시 던진다
        # [왜] 에러 메시지만 찍고 삼켜 버리면, 연결 안 된 드라이버로 다음 단계가 진행돼 버린다
        raise

    return driver   # return: 함수를 끝내고 값을 돌려준다


# ============================================================
# 2단계: 데이터베이스 초기화
# ============================================================
def clear_database(driver):
    """[이 파일에서 정의] 모든 노드와 관계를 지운다. 여러 번 실행해도 같은 결과가 나오게 하려고."""

    # driver.execute_query(쿼리, 파라미터들..., database_=DB이름)
    # [출처] neo4j 드라이버 (5.x 부터 있는 가장 간단한 실행 방법)
    # [입력] 1) Cypher 쿼리 문자열
    #        2) 쿼리 안의 $이름 에 들어갈 값 -> 이름=값 형태의 키워드 인자 (여기서는 없음)
    #        3) 끝에 _ 가 붙은 인자는 드라이버 설정: database_=어느 DB 에서 실행할지
    # [반환] EagerResult. (records, summary, keys) 세 개를 묶은 것
    #        records: 결과 행 리스트 / summary: 실행 통계(만든 노드 수 등) / keys: RETURN 컬럼 이름들
    # Cypher: MATCH (n) = 모든 노드 / DETACH DELETE = 연결된 관계까지 함께 삭제
    #         (관계가 달린 노드를 그냥 DELETE 하면 에러가 난다)
    driver.execute_query("MATCH (n) DETACH DELETE n", database_=NEO4J_DATABASE)
    print("기존 데이터 삭제 완료")


def create_constraints(driver):
    """[이 파일에서 정의] 노드 키가 중복되지 않게 UNIQUE 제약조건을 만든다. 인덱스도 함께 생겨 MATCH 가 빨라진다."""

    # [ ... , ... ] : 리스트. 여러 값을 순서대로 담는다
    constraints = [
        # Cypher: CREATE CONSTRAINT 이름 IF NOT EXISTS FOR (변수:레이블) REQUIRE 변수.속성 IS UNIQUE
        #   IF NOT EXISTS: 이미 있으면 에러 없이 넘어간다 (다시 실행해도 안전)
        "CREATE CONSTRAINT passenger_id IF NOT EXISTS FOR (p:Passenger) REQUIRE p.PassengerId IS UNIQUE",
        "CREATE CONSTRAINT pclass_id IF NOT EXISTS FOR (c:PClass) REQUIRE c.Pclass IS UNIQUE",
        "CREATE CONSTRAINT cabin_id IF NOT EXISTS FOR (c:Cabin) REQUIRE c.Cabin IS UNIQUE",
        "CREATE CONSTRAINT port_id IF NOT EXISTS FOR (p:Port) REQUIRE p.Port IS UNIQUE",
    ]

    # for 변수 in 리스트: -> 리스트의 값을 하나씩 꺼내 변수에 넣고 블록을 반복 실행
    for constraint in constraints:
        driver.execute_query(constraint, database_=NEO4J_DATABASE)

    print("제약조건 생성 완료")


# ============================================================
# 3단계: 노드 생성
#   모든 load_* 함수는 같은 4단계 패턴: CSV 읽기 -> dict 리스트로 변환 -> UNWIND 로 한 번에 삽입 -> 생성 개수 출력
# ============================================================
def load_passenger_nodes(driver, csv_path):
    """[이 파일에서 정의] nodes_passenger.csv 를 읽어 Passenger 노드를 만든다."""

    # pd.read_csv(경로)
    # [출처] pandas
    # [입력] CSV 파일 경로 (문자열 또는 Path)
    # [반환] DataFrame (엑셀 시트 같은 표. 열 이름 = CSV 첫 줄)
    df = pd.read_csv(csv_path)

    # df.where(조건, 대체값).to_dict("records")
    # pd.notnull(df)
    #   [출처] pandas
    #   [반환] df 와 같은 모양의 True/False 표. 값이 비어 있지 않으면(NaN 이 아니면) True
    # df.where(조건표, None)
    #   [출처] pandas DataFrame 의 메서드
    #   [반환] 조건이 True 인 칸은 그대로, False 인 칸은 None 으로 바꾼 새 DataFrame
    #   [왜]   pandas 는 빈 칸을 NaN(숫자 '없음')으로 읽는데, NaN 을 Neo4j 에 보내면 null 이 아니라
    #          NaN 이라는 실수 값으로 저장된다. None 으로 바꿔야 Neo4j 에서 null(값 없음)이 된다
    # .to_dict("records")
    #   [출처] pandas DataFrame 의 메서드
    #   [반환] 행마다 {열이름: 값} 딕셔너리, 그 딕셔너리들의 리스트
    #          예) [{"PassengerId": "P1", "Name": "...", ...}, {...}, ...]
    #   [왜]   Neo4j 드라이버에 넘길 수 있는 파이썬 기본 자료형으로 바꾸려고
    # .where(...).to_dict(...) 처럼 점(.)으로 이어 쓰는 것: 앞 결과에 바로 다음 메서드를 부른다(메서드 체이닝)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # """ ... """ : 여러 줄 문자열
    # Cypher:
    #   UNWIND $records AS row : 리스트 파라미터 $records 를 한 행씩 풀어 row 라는 이름으로 아래를 반복
    #   CREATE (p:Passenger { 속성: row.열이름, ... }) : 노드 생성
    # [왜] 891명을 891번 쿼리로 보내는 대신, 쿼리 1번 + 리스트 1개로 보낸다(배치 삽입). 훨씬 빠르다
    #      $records 는 문자열 포맷팅이 아니라 "파라미터"다 -> 값이 쿼리 구조를 바꿀 수 없어 안전하다(인젝션 방지)
    query = """
    UNWIND $records AS row
    CREATE (
        p:Passenger {
            PassengerId: row.PassengerId,
            Name: row.Name,
            Sex: row.Sex,
            Age: row.Age,
            Survived: row.Survived,
            SibSp: row.SibSp,
            Parch: row.Parch,
            Fare: row.Fare,
            Ticket: row.Ticket
        }
    )
    """

    # driver.execute_query(query, records=records, database_=...)
    #   records=records : 쿼리 안의 $records 에 파이썬 변수 records 를 넣는다 (왼쪽 = $이름, 오른쪽 = 파이썬 값)
    #   .summary        : 반환값 EagerResult 에서 실행 통계만 꺼낸다 (CREATE 는 결과 행이 없으니 records 는 필요 없다)
    summary = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary

    # summary.counters.nodes_created
    # [출처] neo4j 드라이버 ResultSummary -> SummaryCounters
    # [반환] 이 쿼리로 실제 만들어진 노드 수 (relationships_created, properties_set 등도 있다)
    # [왜]   CSV 행 수와 비교하면 적재가 잘 됐는지 바로 확인할 수 있다
    print(f"  Passenger 노드 생성: {summary.counters.nodes_created}개")


def load_pclass_nodes(driver, csv_path):
    """[이 파일에서 정의] 객실 등급(PClass) 노드. 패턴은 load_passenger_nodes 와 같다."""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # 모델링 포인트: 등급처럼 "값의 종류가 몇 개 안 되는 속성"을 노드로 뺐다.
    # 속성이면 '1등급 승객'을 찾을 때 모든 승객을 훑지만, 노드면 1등급 노드에서 연결만 따라가면 된다
    query = """
    UNWIND $records AS row
    CREATE (c:PClass {
        Pclass: row.Pclass,
        ClassName: row.ClassName,
        SES: row.SES
    })
    """
    summary = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary
    print(f"  PClass 노드 생성: {summary.counters.nodes_created}개")


def load_cabin_nodes(driver, csv_path):
    """[이 파일에서 정의] 객실(Cabin) 노드. 패턴 동일."""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    query = """
    UNWIND $records AS row
    CREATE (c:Cabin {
        Cabin: row.Cabin
    })
    """
    summary = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary
    print(f"  Cabin 노드 생성: {summary.counters.nodes_created}개")


def load_port_nodes(driver, csv_path):
    """[이 파일에서 정의] 승선 항구(Port) 노드. 패턴 동일."""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    query = """
    UNWIND $records AS row
    CREATE (p:Port {
        Port: row.Port,
        PortName: row.PortName
    })
    """
    summary = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary
    print(f"  Port 노드 생성: {summary.counters.nodes_created}개")


# ============================================================
# 4단계: 관계 생성
#   노드를 다 만든 "뒤에" 한다. MATCH 로 양 끝 노드를 찾아야 하기 때문이다.
#   관계 CSV 는 (시작 노드 키, 끝 노드 키) 열만 있으면 된다.
# ============================================================
def create_traveled_in_relationships(driver, csv_path):
    """[이 파일에서 정의] Passenger -> PClass (TRAVELED_IN)"""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # Cypher:
    #   MATCH (p:Passenger {PassengerId: row.PassengerId}) : 속성 값이 같은 노드를 찾는다
    #     왼쪽 PassengerId = 노드의 속성 이름 / 오른쪽 row.PassengerId = CSV 의 열 값
    #   CREATE (p)-[:TRAVELED_IN]->(c) : p 에서 c 로 가는 TRAVELED_IN 관계 생성 (화살표 = 방향)
    # 둘 중 하나라도 못 찾으면 그 행은 조용히 건너뛴다 -> 생성 개수가 CSV 행 수보다 적으면 키 불일치를 의심
    # 제약조건(인덱스) 덕분에 MATCH 가 빠르다
    query = """
    UNWIND $records AS row
    MATCH (p:Passenger {PassengerId: row.PassengerId})
    MATCH (c:PClass {Pclass: row.Pclass})
    CREATE (p)-[:TRAVELED_IN]->(c)
    """
    summary = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary
    # relationships_created: 만들어진 관계 수
    print(f"  TRAVELED_IN 관계 생성: {summary.counters.relationships_created}개")


def create_stayed_in_relationships(driver, csv_path):
    """[이 파일에서 정의] Passenger -> Cabin (STAYED_IN). 패턴 동일."""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    query = """
    UNWIND $records AS row
    MATCH (p:Passenger {PassengerId: row.PassengerId})
    MATCH (c:Cabin {Cabin: row.Cabin})
    CREATE (p)-[:STAYED_IN]->(c)
    """
    summary = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary
    print(f"  STAYED_IN 관계 생성: {summary.counters.relationships_created}개")


def create_embarked_at_relationships(driver, csv_path):
    """[이 파일에서 정의] Passenger -> Port (EMBARKED_AT). 패턴 동일."""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    # 변수 이름을 port 로 한 이유: 위의 p(Passenger)와 겹치지 않게
    query = """
    UNWIND $records AS row
    MATCH (p:Passenger {PassengerId: row.PassengerId})
    MATCH (port:Port {Port: row.Port})
    CREATE (p)-[:EMBARKED_AT]->(port)
    """
    summary = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary
    print(f"  EMBARKED_AT 관계 생성: {summary.counters.relationships_created}개")


def create_traveled_with_relationships(driver, csv_path):
    """[이 파일에서 정의] Passenger <-> Passenger (TRAVELED_WITH), 같은 티켓으로 함께 탄 승객"""

    # Path(경로).exists()
    # [출처] pathlib Path 의 메서드
    # [반환] 파일(또는 폴더)이 있으면 True
    # [왜]   같은 티켓을 공유한 승객이 없으면 이 CSV 가 안 만들어질 수 있어서
    # not : 참/거짓 뒤집기
    if not Path(csv_path).exists():
        print("  TRAVELED_WITH 파일 없음 (모두 단독 여행)")
        return   # 값 없이 return: 함수를 여기서 끝낸다

    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # 양 끝이 둘 다 Passenger 라서 CSV 열 이름이 PassengerId1, PassengerId2 이다
    # p1, p2 처럼 변수 이름을 달리해야 한다. 둘 다 p 로 쓰면 "같은 노드" 하나를 두 조건으로 찾는 뜻이 된다
    # -[:TRAVELED_WITH {Ticket: row.Ticket}]-> : 관계에도 속성을 달 수 있다
    # 동행은 방향이 없지만 Neo4j 관계는 방향이 있다. 조회할 때 -[:TRAVELED_WITH]- (화살표 없이) 로 방향을 무시하면 된다
    query = """
    UNWIND $records AS row
    MATCH (p1:Passenger {PassengerId: row.PassengerId1})
    MATCH (p2:Passenger {PassengerId: row.PassengerId2})
    CREATE (p1)-[:TRAVELED_WITH {Ticket: row.Ticket}]->(p2)
    """
    summary = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary
    print(f"  TRAVELED_WITH 관계 생성: {summary.counters.relationships_created}개")


# ============================================================
# 5단계: 통계 확인
# ============================================================
def print_graph_statistics(driver):
    """[이 파일에서 정의] 적재 결과를 DB 에 직접 물어봐서 개수를 출력한다."""
    labels = ["Passenger", "PClass", "Cabin", "Port"]
    rel_types = ["TRAVELED_IN", "STAYED_IN", "EMBARKED_AT", "TRAVELED_WITH"]

    # { 키식: 값식 for 변수 in 리스트 } : 딕셔너리 컴프리헨션 (반복문으로 딕셔너리를 한 줄에 만들기)
    #   아래는 이것과 같다:
    #     node_counts = {}
    #     for label in labels:
    #         node_counts[label] = driver.execute_query(...).records[0]["count"]
    # .records[0]["count"]
    #   .records : 결과 행 리스트 / [0] : 첫 행 (COUNT 는 집계라서 결과가 항상 1행) / ["count"] : AS count 로 붙인 이름의 값
    # 레이블 이름은 $파라미터로 넘길 수 없어서 f-string 으로 쿼리에 넣는다.
    #   여기서는 위에 코드로 적은 리스트 값만 쓰니 안전하다. 사용자 입력을 이렇게 넣으면 인젝션 위험이 있다
    #   (원본은 같은 쿼리를 8번 풀어서 썼다. 동작은 같다)
    node_counts = {
        label: driver.execute_query(
            f"MATCH (n:{label}) RETURN count(n) AS count", database_=NEO4J_DATABASE
        ).records[0]["count"]
        for label in labels
    }
    rel_counts = {
        rel: driver.execute_query(
            f"MATCH ()-[r:{rel}]->() RETURN count(r) AS count", database_=NEO4J_DATABASE
        ).records[0]["count"]
        for rel in rel_types
    }

    print("\n" + "=" * 60)       # 문자열 + 문자열 = 이어 붙이기 / "=" * 60 = "=" 60번 반복
    print("타이타닉 지식그래프 통계")
    print("=" * 60)

    print("\n1) 노드:")
    # 딕셔너리.items()
    #   [출처] 파이썬 기본 dict 의 메서드
    #   [반환] (키, 값) 튜플들 -> for 키, 값 in ... 으로 풀어서 받는다
    for label, count in node_counts.items():
        # {count:,} : f-string 서식. 천 단위 쉼표 (1234 -> 1,234)
        print(f"  • {label}: {count:,}개")
    # sum(값들)
    #   [출처] 파이썬 기본 함수. 숫자들의 합계
    #   딕셔너리.values() : 값들만 꺼낸다
    print(f"  -> 총 {sum(node_counts.values()):,}개 노드")

    print("\n2) 관계:")
    for rel_type, count in rel_counts.items():
        print(f"  • {rel_type}: {count:,}개")
    print(f"  -> 총 {sum(rel_counts.values()):,}개 관계")

    print("\n" + "=" * 60)


# ============================================================
# 실행 흐름
# ============================================================
def main():
    """[이 파일에서 정의] 전체 실행 순서. 여기부터 읽으면 흐름이 보인다."""
    print("=" * 50)
    print("타이타닉 지식 그래프 추출")
    print("=" * 50)

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # raise ValueError("메시지")
    # [출처] 파이썬 기본. ValueError 는 "값이 잘못됨" 을 뜻하는 기본 예외 클래스
    # [왜]   비밀번호가 없으면 연결 시도 전에 이유가 분명한 에러로 멈춘다
    if not password:
        raise ValueError("NEO4J_PASSWORD 환경변수가 설정되지 않았습니다.")

    # 파일 경로를 딕셔너리로 모아 두면 아래에서 csv_files["passenger"] 처럼 이름으로 꺼낼 수 있다
    csv_files = {
        "passenger": OUTPUT_DIR / "nodes_passenger.csv",
        "pclass": OUTPUT_DIR / "nodes_pclass.csv",
        "cabin": OUTPUT_DIR / "nodes_cabin.csv",
        "port": OUTPUT_DIR / "nodes_port.csv",
        "rel_pclass": OUTPUT_DIR / "rels_passenger_pclass.csv",
        "rel_cabin": OUTPUT_DIR / "rels_passenger_cabin.csv",
        "rel_port": OUTPUT_DIR / "rels_passenger_port.csv",
        "rel_traveled": OUTPUT_DIR / "rels_traveled_with.csv",
    }

    driver = create_neo4j_driver(uri, user, password)

    # try: ... finally: ...
    # [출처] 파이썬 기본 문법
    # [왜]   try 블록에서 에러가 나든 안 나든 finally 블록은 반드시 실행된다 -> 연결을 꼭 닫기 위해
    try:
        print("\n- 1단계: 데이터베이스 초기화")
        clear_database(driver)
        create_constraints(driver)

        print("\n- 2단계: 노드 생성")
        load_passenger_nodes(driver, csv_files["passenger"])
        load_pclass_nodes(driver, csv_files["pclass"])
        load_cabin_nodes(driver, csv_files["cabin"])
        load_port_nodes(driver, csv_files["port"])

        print("\n- 3단계: 관계 생성")
        create_traveled_in_relationships(driver, csv_files["rel_pclass"])
        create_stayed_in_relationships(driver, csv_files["rel_cabin"])
        create_embarked_at_relationships(driver, csv_files["rel_port"])
        create_traveled_with_relationships(driver, csv_files["rel_traveled"])

        print_graph_statistics(driver)
        print("\n타이타닉 지식그래프 구축 완료!")
    finally:
        # driver.close()
        # [출처] neo4j 드라이버
        # [왜]   연결 풀을 정리해서 서버 쪽 연결을 반납한다
        driver.close()


# 이 파일을 직접 실행했을 때만 main() 을 부른다 (다른 파일에서 import 할 때는 실행되지 않음)
if __name__ == "__main__":
    main()
