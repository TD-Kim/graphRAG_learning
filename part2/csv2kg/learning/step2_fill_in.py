"""
[2단계: 빈칸 채우기] 뼈대와 힌트만 있고 핵심이 TODO 로 비어 있다.

방법:
  1. TODO 를 위에서부터 하나씩 채운다. 힌트 주석을 따라가면 된다.
  2. 막히면 step1_annotated.py 에서 같은 함수를 본다. (정답은 원본 csv2kg.py)
  3. 다 채웠으면 `python learning/step2_fill_in.py` 로 실행해서
     통계의 개수가 CSV 행 수와 같은지 확인한다.

실행 위치: part2/csv2kg
"""
import csv
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


# ---------- 1. 연결 ----------
def create_neo4j_driver(uri, username, password):
    # TODO 1-1: GraphDatabase.driver(...) 로 driver 를 만든다. (auth 는 (username, password) 튜플)
    driver = GraphDatabase.driver(uri, auth={username, password})

    # TODO 1-2: 연결이 실제로 되는지 확인하는 메서드를 호출한다.
    #           힌트: verify_ 로 시작한다. 실패하면 에러 메시지를 출력하고 다시 raise 하자.
    try:
        driver.verify_connectivity()
        print(f"NEO4J DATABASE 연결 성공 : {uri}")
    except Exception as e:
        print(f"NEO4J DATABASE 연결 실패 : {e}")
        raise

    return driver


# ---------- 2. 초기화 ----------
def clear_database(driver):
    # TODO 2-1: 모든 노드와 관계를 지우는 Cypher 를 실행한다.
    #           힌트: 관계가 달린 노드도 지워지려면 DELETE 앞에 무엇이 필요할까?
    query = "MATCH (n) DETACH DELETE n"
    driver.execute_query(query, database_=NEO4J_DATABASE)


def create_constraints(driver):
    # TODO 2-2: 아래 4개 노드의 "키 속성"이 UNIQUE 하도록 제약조건을 만든다.
    #   Passenger.PassengerId / PClass.Pclass / Cabin.Cabin / Port.Port
    #   힌트: CREATE CONSTRAINT <이름> IF NOT EXISTS FOR (x:Label) REQUIRE x.prop IS UNIQUE
    constraints = [
        "CREATE CONSTRAINT passenger_id IF NOT EXISTS FOR (p:Passenger) REQUIRE p.PassengerId IS UNIQUE",
        "CREATE CONSTRAINT pclass_id IF NOT EXISTS FOR (c:PClass) REQUIRE c.Pclass IS UNIQUE",
        "CREATE CONSTRAINT cabin_id IF NOT EXISTS FOR (c:Cabin) REQUIRE c.Cabin IS UNIQUE",
        "CREATE CONSTRAINT port_id IF NOT EXISTS FOR (p:Port) REQUIRE p.Port IS UNIQUE",
    ]
    for constraint in constraints:
        driver.execute_query(constraint, database_=NEO4J_DATABASE)


# ---------- 3. 노드 ----------
def load_passenger_nodes(driver, csv_path):
    df = pd.read_csv(csv_path)

    # TODO 3-1: DataFrame 을 dict 리스트로 바꾼다. 단, NaN 은 None 으로.
    #           힌트: df.where(pd.notnull(df), None).to_dict(...)  (to_dict 의 인자는 'records')
    records = df.where(pd.notnull(df), None).to_dict("records")

    # TODO 3-2: UNWIND 로 records 를 풀어 Passenger 노드를 만드는 Cypher 를 쓴다.
    #   속성: PassengerId, Name, Sex, Age, Survived, SibSp, Parch, Fare, Ticket
    query = """
    UNWIND $records AS row
    CREATE (
        p: Passenger{
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

    # TODO 3-3: 쿼리를 실행하고 summary 에서 "만들어진 노드 수"를 출력한다.
    #           힌트: driver.execute_query(query, records=records, database_=...).summary.counters
    count = driver.execute_query(query, records=records, database_=NEO4J_DATABASE).summary.counters.nodes_created
    print(f"  Passenger 노드 생성 : ${count}개")


# TODO 3-4: load_pclass_nodes / load_cabin_nodes / load_port_nodes 를
#           load_passenger_nodes 를 보고 같은 패턴으로 직접 만든다.
#   - PClass: Pclass, ClassName, SES
#   - Cabin : Cabin
#   - Port  : Port, PortName
#   (CSV 컬럼명은 output/ 폴더의 nodes_*.csv 헤더를 열어서 확인하자)

def load_pclass_nodes(driver, csv_path):
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    
    query = """
    UNWIND $records AS row
    CREATE (
        p: PClass{
            Pclass: row.Pclass,
            ClassName: row.ClassName,
            SES: row.SES
        }
    )
    """
    
    count = driver.execute_query(query, records, database_=NEO4J_DATABASE).summary.counter.nodes_created
    print(f"  PClass 노드 생성 : ${count}개")

def load_cabin_nodes(driver, csv_path):
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    
    query ="""
    UNWIND $records AS row
    CREATE (
        p: Cabin {
            Cabin: row.Cabin
        }
    )
    """
    
    count = driver.execute_query(query, records, database_=NEO4J_DATABASE).summary.counter.nodes_created
    print(f"  Cabin 노드 생성 : ${count}개")

def load_port_nodes(driver, csv_path):
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    
    query = """
    UNWIND $records AS row
    CREATE (
        p: Port{
            Port: row.Port,
            PortName: row.PortName
        }
    )
    """
    
    count = driver.execute_query(query, records, database_=NEO4J_DATABASE).summary.counter.nodes_created
    print(f"  Port 노드 생성 : ${count}개")

# ---------- 4. 관계 ----------
def create_traveled_in_relationships(driver, csv_path):
    """Passenger -> PClass (TRAVELED_IN)"""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")

    # TODO 4-1: 한 행마다 양 끝 노드를 MATCH 로 찾고 관계를 CREATE 하는 Cypher.
    #   힌트: rels_passenger_pclass.csv 의 열은 PassengerId, Pclass
    #   (p:Passenger {...}) 와 (c:PClass {...}) 를 각각 MATCH 한 뒤 (p)-[:TRAVELED_IN]->(c)
    query = """
    UNWIND $records AS row
    MATCH (p:Passenger {PassengerId: row.PassengerId})
    MATCH (c:PClass {Pclass: row.Pclass})
    CREATE (p)-[:TRAVELED_IN]->(c)
    """

    # TODO 4-2: 실행하고 "만들어진 관계 수"를 출력한다. (counters 의 relationships_created)
    count = driver.execute_query(query, records, database_=NEO4J_DATABASE).summary.counter.nodes_created
    print(f"  TRAVELED_IN 관계 생성 : ${count}개")

# TODO 4-3: create_stayed_in_relationships (Passenger -> Cabin),
#           create_embarked_at_relationships (Passenger -> Port) 를 같은 패턴으로 만든다.
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
    
    count = driver.execute_query(query, records, database_=NEO4J_DATABASE).summary.counter.nodes_created
    print(f"  STAYED_IN 관계 생성 : ${count}개")

def create_embarked_at_relationships(driver, csv_path):
    """Passenger -> Port (EMBARKED_AT)"""
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    
    query = """
    UNWIND $records AS row
    MATCH (p:Passenger {PassengerId: row.PassengerId})
    MATCH (port:Port {Port: row.Port})
    CREATE (p)-[:EMBARKED_AT]->(port)
    """
    
    count = driver.execute_query(query, records, database_=NEO4J_DATABASE).summary.counter.nodes_created
    print(f"  EMBARKED_AT 관계 생성 : ${count}개")

# TODO 4-4: create_traveled_with_relationships (Passenger <-> Passenger)
#   - 두 노드 키 열이 PassengerId1, PassengerId2 이다. 변수 이름이 겹치지 않게 주의.
#   - 관계에 Ticket 속성을 달아 보자: -[:TRAVELED_WITH {Ticket: row.Ticket}]->
#   - CSV 파일이 없을 수도 있다. 없으면 안내만 출력하고 return. (Path(...).exists())
def create_traveled_with_relationships(driver, csv_path):
    """Passenger <-> Passenger (TRAVELED_WITH), 같은 티켓으로 함께 탄 승객"""
    if not Path(csv_path).exists():
        print("  TRAVELED_WITH 파일 없음 (모두 단독 여행)")
        return
    
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict("records")
    
    query = """
    UNWIND $records AS row
    MATCH (p1:Passenger {PassengerId: row.PassengerId1})
    MATCH (p2:Passenger {PassengerId: row.PassengerId2})
    CREATE (p1)-[:TRAVELED_WITH {Ticket: row.Ticket}]->(p2)
    """
    
    count = driver.execute_query(query, records, database_=NEO4J_DATABASE).summary.counter.nodes_created
    print(f"  TRAVELED_WITH 관계 생성 : ${count}개")

# ---------- 5. 통계 ----------
def print_graph_statistics(driver):
    labels = ["Passenger", "PClass", "Cabin", "Port"]
    rel_types = ["TRAVELED_IN", "STAYED_IN", "EMBARKED_AT", "TRAVELED_WITH"]

    # TODO 5-1: 레이블마다 count 쿼리를 날려 {레이블: 개수} dict 를 만든다.
    #   힌트: MATCH (n:Passenger) RETURN count(n) AS count -> .records[0]["count"]
    #         레이블 이름은 파라미터로 못 넘기니 f-string 을 쓰되, 왜 여기선 안전한지 생각해 보자.
    node_counts = {
        label: driver.execute_query(
            f"MATCH (n:{label}) RETURN COUNT(n) AS count", database_=NEO4J_DATABASE
        ).records[0]["count"] for label in labels
    }

    # TODO 5-2: 관계 타입도 같은 방식으로. 힌트: MATCH ()-[r:TYPE]->() RETURN count(r) AS count
    rel_counts = {
        rel: driver.execute_query(
            f"MATCH ()-[r:{rel}]->() RETURN COUNT(r) AS count", database_=NEO4J_DATABASE    
        ).records[0]["count"] for rel in rel_types
    }
    
    print("\n" + "=" * 60)
    print("타이타닉 지식그래프 통계")
    print("=" * 60)

    print("\n1) 노드:")
    for label, count in node_counts.items():
        print(f"  • {label}: {count:,}개 ")    
    print(f"  -> 총 {sum(node_counts.values()):,}개 노드")
    
    print("\n2) 관계:")
    for rel, count in rel_counts.items():
        print(f"  • {rel}: {count:,}개")
    print(f"  -> 총 {sum(rel_counts.values()):,}개 관계")
    
    print("\n" + "=" * 60)


# ---------- 실행 ----------
def main():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # TODO 6-1: 비밀번호가 없으면 ValueError 를 낸다.
    if not password:
        raise ValueError("NEO4J_PASSWORD 환경변수가 없습니다. .env 파일을 확인하세요.")

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

    # TODO 6-2: try/finally 로 감싸고, 순서대로 호출한다. finally 에서 driver.close().
    #   순서: clear_database -> create_constraints -> 노드 4종 -> 관계 4종 -> print_graph_statistics
    #   (왜 노드가 먼저, 관계가 나중일까? 직접 순서를 바꿔 실행해 보면 바로 알 수 있다.)
    try:
        clear_database(driver)
        create_constraints(driver)
        
        load_passenger_nodes(driver, csv_files["passenger"])
        load_pclass_nodes(driver, csv_files["pclass"])
        load_cabin_nodes(driver, csv_files["cabin"])
        load_port_nodes(driver, csv_files["port"])
        
        create_traveled_in_relationships(driver, csv_files["rel_pclass"])
        create_stayed_in_relationships(driver, csv_files["rel_cabin"])
        create_embarked_at_relationships(driver, csv_files["rel_port"])
        create_traveled_with_relationships(driver, csv_files["rel_traveled"])
        
        print_graph_statistics(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
