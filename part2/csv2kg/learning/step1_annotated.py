"""
[1단계: 읽기] csv2kg.py 의 "왜" 주석 버전 (동작은 원본과 동일)

실행: part2/csv2kg 폴더에서 `python learning/step1_annotated.py`
      (원본과 똑같이 Neo4j를 초기화하고 다시 적재하니, 필요하면 DB 이름을 확인하고 실행하세요)

읽는 순서 권장:
  main() 먼저 -> 전체 흐름(연결 -> 초기화 -> 노드 -> 관계 -> 통계) 파악
  -> 위에서부터 함수를 하나씩.
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

# .env 의 NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD 를 환경변수로 올린다.
# 비밀번호를 코드에 쓰지 않고, .gitignore 된 .env 로만 관리하기 위해서다.
load_dotenv()

# AuraDB 무료 인스턴스는 데이터베이스 이름이 사용자 이름과 같다.
# 그래서 모든 execute_query 에 database_=NEO4J_DATABASE 를 명시한다.
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")

# 노트북(titanic.ipynb)이 만든 CSV 위치. 실행 위치와 상관없게 이 파일 기준으로 잡는다.
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


# ============================================
# 1단계: Neo4j 연결
# ============================================
def create_neo4j_driver(uri, username, password):
    # driver 는 연결 풀을 가진 무거운 객체. 앱 전체에서 하나만 만들어 재사용한다.
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        # driver() 자체는 접속하지 않는다(게으른 연결).
        # verify_connectivity() 로 URI/계정이 틀렸을 때 첫 쿼리 전에 바로 실패시킨다.
        driver.verify_connectivity()
        print(f"Neo4j 연결 성공: {uri}")
    except Exception as e:
        print(f"Neo4j 연결 실패: {e}")
        raise  # 삼키지 않고 다시 던진다: 연결 실패 상태로 다음 단계로 가면 안 되므로

    return driver


# ============================================
# 2단계: 데이터베이스 초기화
# ============================================
def clear_database(driver):
    """스크립트를 여러 번 돌려도 같은 결과가 나오게(멱등) 먼저 비운다."""
    # DETACH: 관계가 달린 노드는 그냥 DELETE 하면 에러라서, 관계까지 함께 지운다.
    driver.execute_query("MATCH (n) DETACH DELETE n", database_=NEO4J_DATABASE)
    print("기존 데이터 삭제 완료")


def create_constraints(driver):
    """고유성 제약조건. 중복 노드를 막고, 아래 MATCH 가 인덱스를 타서 빨라진다."""
    constraints = [
        # IF NOT EXISTS: 재실행해도 에러 없이 넘어가게 한다.
        "CREATE CONSTRAINT passenger_id IF NOT EXISTS FOR (p:Passenger) REQUIRE p.PassengerId IS UNIQUE",
        "CREATE CONSTRAINT pclass_id IF NOT EXISTS FOR (c:PClass) REQUIRE c.Pclass IS UNIQUE",
        "CREATE CONSTRAINT cabin_id IF NOT EXISTS FOR (c:Cabin) REQUIRE c.Cabin IS UNIQUE",
        "CREATE CONSTRAINT port_id IF NOT EXISTS FOR (p:Port) REQUIRE p.Port IS UNIQUE",
    ]

    for constraint in constraints:
        driver.execute_query(constraint, database_=NEO4J_DATABASE)

    print("제약조건 생성 완료")


# ============================================
# 3단계: 노드 생성
#   모든 load_* 함수는 같은 4단계 패턴이다:
#   CSV 읽기 -> dict 리스트로 변환 -> UNWIND 로 한 번에 삽입 -> 생성 개수 출력
# ============================================
def load_passenger_nodes(driver, csv_path):
    df = pd.read_csv(csv_path)

    # NaN 은 Neo4j 로 보낼 수 없어서(드라이버가 float nan 으로 저장해 버림) None(=null)으로 바꾼다.
    # where(조건, 대체값): 조건이 False(= NaN)인 칸을 None 으로 바꾼다.
    # to_dict('records') -> [{"PassengerId": 1, "Name": "...", ...}, ...]
    records = df.where(pd.notnull(df), None).to_dict("records")

    # UNWIND: 리스트를 한 행씩 풀어서 아래 CREATE 를 행마다 실행한다.
    # 891번 쿼리를 보내는 대신 쿼리 1번 + 파라미터 1번으로 끝낸다(배치 삽입).
    # $records 는 문자열 포맷팅이 아니라 "파라미터"다 -> Cypher 인젝션 방지 + 쿼리 플랜 재사용.
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

    # execute_query 는 (records, summary, keys) 를 돌려준다. 쓰기에서는 summary 만 필요하다.
    summary = driver.execute_query(
        query, records=records, database_=NEO4J_DATABASE
    ).summary

    # summary.counters: 실제로 DB 가 몇 개 만들었는지. CSV 행 수와 비교하는 가장 쉬운 검증이다.
    print(f"  Passenger 노드 생성: {summary.counters.nodes_created}개")


def load_pclass_nodes(driver, csv_path):
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # 객실 등급처럼 "값이 몇 개 안 되는 속성"을 노드로 뺀 것이 그래프 모델링의 핵심.
    # 속성이면 '1등급 승객'을 찾을 때 전체를 훑지만, 노드면 1등급 노드에서 이웃만 따라가면 된다.
    query = """
    UNWIND $records AS row
    CREATE (c:PClass {
        Pclass: row.Pclass,
        ClassName: row.ClassName,
        SES: row.SES
    })
    """

    summary = driver.execute_query(
        query, records=records, database_=NEO4J_DATABASE
    ).summary
    print(f"  PClass 노드 생성: {summary.counters.nodes_created}개")


def load_cabin_nodes(driver, csv_path):
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    query = """
    UNWIND $records AS row
    CREATE (c:Cabin {
        Cabin: row.Cabin
    })
    """

    summary = driver.execute_query(
        query, records=records, database_=NEO4J_DATABASE
    ).summary
    print(f"  Cabin 노드 생성: {summary.counters.nodes_created}개")


def load_port_nodes(driver, csv_path):
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    query = """
    UNWIND $records AS row
    CREATE (p:Port {
        Port: row.Port,
        PortName: row.PortName
    })
    """

    summary = driver.execute_query(
        query, records=records, database_=NEO4J_DATABASE
    ).summary
    print(f"  Port 노드 생성: {summary.counters.nodes_created}개")


# ============================================
# 4단계: 관계 생성
#   반드시 노드를 다 만든 "뒤에" 한다. MATCH 로 양 끝 노드를 찾아야 하기 때문이다.
#   관계 CSV 는 (시작 노드 키, 끝 노드 키) 두 열만 있으면 된다.
# ============================================
def create_traveled_in_relationships(driver, csv_path):
    """Passenger -> PClass (TRAVELED_IN)"""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # 두 MATCH 는 제약조건(인덱스) 덕에 빠르게 노드를 찾는다.
    # 못 찾으면 그 행은 조용히 건너뛴다 -> 생성 개수가 CSV 행 수보다 적으면 키 불일치를 의심.
    query = """
    UNWIND $records AS row
    MATCH (p:Passenger {PassengerId: row.PassengerId})
    MATCH (c:PClass {Pclass: row.Pclass})
    CREATE (p)-[:TRAVELED_IN]->(c)
    """

    summary = driver.execute_query(
        query, records=records, database_=NEO4J_DATABASE
    ).summary
    print(f"  TRAVELED_IN 관계 생성: {summary.counters.relationships_created}개")


def create_stayed_in_relationships(driver, csv_path):
    """Passenger -> Cabin (STAYED_IN)"""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    query = """
    UNWIND $records AS row
    MATCH (p:Passenger {PassengerId: row.PassengerId})
    MATCH (c:Cabin {Cabin: row.Cabin})
    CREATE (p)-[:STAYED_IN]->(c)
    """

    summary = driver.execute_query(
        query, records=records, database_=NEO4J_DATABASE
    ).summary
    print(f"  STAYED_IN 관계 생성: {summary.counters.relationships_created}개")


def create_embarked_at_relationships(driver, csv_path):
    """Passenger -> Port (EMBARKED_AT)"""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # 변수명을 port 로 쓴 이유: 위쪽 p(Passenger)와 이름이 겹치지 않게 하려고.
    query = """
    UNWIND $records AS row
    MATCH (p:Passenger {PassengerId: row.PassengerId})
    MATCH (port:Port {Port: row.Port})
    CREATE (p)-[:EMBARKED_AT]->(port)
    """

    summary = driver.execute_query(
        query, records=records, database_=NEO4J_DATABASE
    ).summary
    print(f"  EMBARKED_AT 관계 생성: {summary.counters.relationships_created}개")


def create_traveled_with_relationships(driver, csv_path):
    """Passenger <-> Passenger (TRAVELED_WITH), 같은 티켓으로 함께 탄 승객"""
    # 같은 티켓을 공유한 승객이 없으면 이 CSV 가 안 만들어질 수 있어서 방어한다.
    if not Path(csv_path).exists():
        print("  TRAVELED_WITH 파일 없음 (모두 단독 여행)")
        return

    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # 관계에도 속성(Ticket)을 달 수 있다: "무슨 티켓으로 함께 탔는가"
    # 방향은 있지만 의미상 양방향이라, CSV 에 (A,B) 한 쌍만 있으면 한 방향으로만 저장된다.
    # 조회할 때는 -[:TRAVELED_WITH]- (화살표 없이) 로 방향을 무시하면 된다.
    query = """
    UNWIND $records AS row
    MATCH (p1:Passenger {PassengerId: row.PassengerId1})
    MATCH (p2:Passenger {PassengerId: row.PassengerId2})
    CREATE (p1)-[:TRAVELED_WITH {Ticket: row.Ticket}]->(p2)
    """

    summary = driver.execute_query(
        query, records=records, database_=NEO4J_DATABASE
    ).summary
    print(f"  TRAVELED_WITH 관계 생성: {summary.counters.relationships_created}개")


# ============================================
# 5단계: 통계 확인
# ============================================
def print_graph_statistics(driver):
    """적재 결과를 DB 에 직접 물어봐서 확인한다. (CSV 행 수와 맞는지 눈으로 비교)"""
    labels = ["Passenger", "PClass", "Cabin", "Port"]
    rel_types = ["TRAVELED_IN", "STAYED_IN", "EMBARKED_AT", "TRAVELED_WITH"]

    # 원본은 쿼리를 8번 풀어서 썼다. 레이블/관계 이름은 파라미터로 못 넘기므로
    # f-string 으로 넣는데, 여기서는 위 리스트(하드코딩)만 쓰니 안전하다.
    # 사용자 입력을 이렇게 넣으면 인젝션 위험이 있다는 점을 기억해 두자.
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

    print("\n" + "=" * 60)
    print("타이타닉 지식그래프 통계")
    print("=" * 60)

    print("\n1) 노드:")
    for label, count in node_counts.items():
        print(f"  • {label}: {count:,}개")
    print(f"  -> 총 {sum(node_counts.values()):,}개 노드")

    print("\n2) 관계:")
    for rel_type, count in rel_counts.items():
        print(f"  • {rel_type}: {count:,}개")
    print(f"  -> 총 {sum(rel_counts.values()):,}개 관계")

    print("\n" + "=" * 60)


# ============================================
# 실행 흐름: 연결 -> (초기화 + 제약) -> 노드 -> 관계 -> 통계
# ============================================
def main():
    print("=" * 50)
    print("타이타닉 지식 그래프 추출")
    print("=" * 50)

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # 비밀번호가 없으면 연결 시도 전에 이유가 분명한 에러로 멈춘다.
    if not password:
        raise ValueError("NEO4J_PASSWORD 환경변수가 설정되지 않았습니다.")

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

    # try/finally: 중간에 에러가 나도 연결은 반드시 닫는다.
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
        driver.close()


if __name__ == "__main__":
    main()
