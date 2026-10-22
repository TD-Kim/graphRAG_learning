"""[1단계: 읽기] retail2kg.py (H&M 구매 데이터 -> 추천용 지식그래프) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
csv2kg 주석본과 거의 같은 패턴이다 (CSV -> pandas -> UNWIND 배치). 처음 나오는 load_article_nodes 에만 자세히 적었다.

흐름
  output/nodes_*.csv, rels_*.csv  (hnm_recommendations.ipynb 가 원본 데이터를 정리해서 만든 파일)
  -> 노드 8종 CREATE -> 관계 7종 CREATE (구매 관계는 수가 많아서 5만 행씩 나눠 읽기) -> 개수 통계
그래프 모양
  (Customer)-[:PURCHASED {date, price, sales_channel_id}]->(Article)
  (Article)-[:OF_TYPE]->(ProductType)  -[:IN_GROUP]->(ProductGroup)  -[:HAS_COLOUR]->(ColourGroup)
           -[:IN_DEPARTMENT]->(Department)  -[:IN_SECTION]->(Section)  -[:IN_GARMENT_GROUP]->(GarmentGroup)

주의: 원본에 import time 이 빠져 있다 -> create_purchased_relationships 에서 NameError: name 'time' is not defined
      (노트북에서는 앞 셀에서 import 해 둬서 문제가 없었을 것이다. .py 로 실행하려면 맨 위에 import time 을 추가하자)

읽는 순서 권장: main -> load_article_nodes -> create_purchased_relationships -> print_graph_statistics
실행 위치: part2/retail2kg (DB 를 전부 지우고 시작한다)
"""

# [출처] 표준 라이브러리. os.getenv
import os
# [출처] 외부 라이브러리 pandas. 관례상 pd 라는 짧은 이름으로 쓴다 (as: 별명)
import pandas as pd
# [출처] 표준 라이브러리. 경로 객체. Path("a") / "b.csv" 처럼 / 로 경로를 잇는다
from pathlib import Path
# [출처] 외부 라이브러리 neo4j
# 주의: 원본에 import time 이 없다 (헤더 설명 참고)
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv

# .env 를 읽어 환경변수로 등록
load_dotenv()

# ============================================
# 환경 변수 설정
# ============================================

NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")  # 데이터베이스명


# ============================================
# 1단계: Neo4j 연결
# ============================================

# [이 파일에서 정의] 드라이버를 만들고 연결을 확인한 뒤 돌려준다
# [입력] uri, username, password   [반환] Driver 객체
def create_neo4j_driver(uri, username, password):
    # GraphDatabase.driver(uri, auth=(사용자, 비밀번호)): 연결 정보를 가진 드라이버 생성 (실제 연결은 처음 쓸 때)
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        # verify_connectivity(): 지금 바로 연결해 보고, 안 되면 예외
        driver.verify_connectivity()
        print(f"Neo4j 연결 성공: {uri}")
    except Exception as e:
        print(f"Neo4j 연결 실패: {e}")
        # raise (뒤에 아무것도 없이): 방금 잡은 예외를 그대로 다시 던진다
        # [왜] 실패 메시지는 출력하되, 프로그램은 멈추게 하려고 (연결 없이 계속 가면 의미가 없다)
        raise

    return driver


# ============================================
# 2단계: 데이터베이스 초기화
# ============================================

# [이 파일에서 정의] 모든 노드와 관계 삭제. DETACH DELETE: 관계까지 같이 지운다
def clear_database(driver):
    """
    데이터베이스의 모든 노드와 관계를 삭제
    """
    driver.execute_query(
        "MATCH (n) DETACH DELETE n",
        database_=NEO4J_DATABASE
    )
    print("기존 데이터 삭제 완료")


# [이 파일에서 정의] UNIQUE 제약조건 8개. 같은 id 의 노드를 막고, MATCH (a:Article {article_id: ...}) 를 빠르게 하는 인덱스도 생긴다
# [왜] 아래 관계 만들기에서 MATCH 를 수십만 번 하므로 인덱스가 없으면 매우 느리다
def create_constraints(driver):
    """
    노드 ID의 고유성을 보장하는 제약조건 생성
    """
    constraints = [
        "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.article_id IS UNIQUE",
        "CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE",
        "CREATE CONSTRAINT product_type_no IF NOT EXISTS FOR (p:ProductType) REQUIRE p.product_type_no IS UNIQUE",
        "CREATE CONSTRAINT product_group_name IF NOT EXISTS FOR (p:ProductGroup) REQUIRE p.name IS UNIQUE",
        "CREATE CONSTRAINT colour_code IF NOT EXISTS FOR (c:ColourGroup) REQUIRE c.colour_group_code IS UNIQUE",
        "CREATE CONSTRAINT dept_no IF NOT EXISTS FOR (d:Department) REQUIRE d.department_no IS UNIQUE",
        "CREATE CONSTRAINT section_no IF NOT EXISTS FOR (s:Section) REQUIRE s.section_no IS UNIQUE",
        "CREATE CONSTRAINT garment_no IF NOT EXISTS FOR (g:GarmentGroup) REQUIRE g.garment_group_no IS UNIQUE"
    ]

    # IF NOT EXISTS 라 여러 번 실행해도 에러가 나지 않는다
    for constraint in constraints:
        driver.execute_query(constraint, database_=NEO4J_DATABASE)

    print("제약조건 생성 완료")


# ============================================
# 3단계: 노드 생성
# ============================================

# [이 파일에서 정의] Article(상품) CSV -> Article 노드. 아래 load_*_nodes 7개도 모두 같은 모양이다
def load_article_nodes(driver, csv_path):
    """
    Article 노드를 pandas로 CSV 파일에서 로드하여 배치 삽입
    """
    # pd.read_csv(경로)
    # [출처] 외부 라이브러리 pandas
    # [입력] CSV 파일 경로 (문자열 또는 Path)
    # [반환] DataFrame (표). 첫 줄을 열 이름으로 쓴다
    df = pd.read_csv(csv_path)
    # df.where(조건, 대체값): 조건이 True 인 칸은 그대로, False 인 칸은 대체값(None)으로
    # pd.notnull(df): 칸마다 "값이 있나" 를 True/False 로 담은 같은 크기의 표
    # -> 빈 칸(NaN)을 None 으로 바꾼다. [왜] NaN 은 Neo4j 에 숫자 NaN 으로 들어가고, None 은 "속성 없음" 이 된다
    # .to_dict('records'): 표 -> [{열이름: 값, ...}, ...] 행 딕셔너리 리스트 (UNWIND 에 넘길 모양)
    records = df.where(pd.notnull(df), None).to_dict('records')

    # UNWIND $records AS row: 리스트를 한 행씩 풀어 반복. row.열이름 으로 값 꺼내기
    # toInteger(...), toFloat(...): Cypher 형 변환 함수. CSV 에서 온 값을 정수/실수로 확실히 맞춘다
    # [왜] 나중에 MATCH (a:Article {article_id: toInteger(...)}) 로 찾을 때 형이 같아야 찾아진다 (정수 1 과 글 "1" 은 다르다)
    query = """
    UNWIND $records AS row
    CREATE (a:Article {
        article_id: toInteger(row.article_id),
        product_code: toInteger(row.product_code),
        prod_name: row.prod_name,
        product_type_no: toInteger(row.product_type_no),
        product_type_name: row.product_type_name,
        product_group_name: row.product_group_name,
        graphical_appearance_no: toInteger(row.graphical_appearance_no),
        graphical_appearance_name: row.graphical_appearance_name,
        colour_group_code: toInteger(row.colour_group_code),
        colour_group_name: row.colour_group_name,
        perceived_colour_value_id: toInteger(row.perceived_colour_value_id),
        perceived_colour_value_name: row.perceived_colour_value_name,
        perceived_colour_master_id: toInteger(row.perceived_colour_master_id),
        perceived_colour_master_name: row.perceived_colour_master_name,
        department_no: toInteger(row.department_no),
        department_name: row.department_name,
        index_code: row.index_code,
        index_name: row.index_name,
        index_group_no: toInteger(row.index_group_no),
        index_group_name: row.index_group_name,
        section_no: toInteger(row.section_no),
        section_name: row.section_name,
        garment_group_no: toInteger(row.garment_group_no),
        garment_group_name: row.garment_group_name,
        detail_desc: row.detail_desc
    })
    """

    # execute_query(쿼리, records=리스트, database_=...)  -> 쿼리의 $records 에 리스트가 들어간다
    # 반환 EagerResult 의 .summary 만 꺼낸다 (결과 행은 필요 없음)
    # 괄호 안에서는 줄을 나눠도 되므로 ).summary 처럼 이어 쓸 수 있다
    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    # summary.counters.nodes_created: 이 쿼리로 만든 노드 수
    count = summary.counters.nodes_created
    # {count:,}: 천 단위 쉼표 서식 (12345 -> 12,345)
    print(f"  Article 노드 생성: {count:,}개")


# [이 파일에서 정의] Customer(고객) 노드. customer_id 는 긴 해시 문자열이라 형 변환 없이 그대로
def load_customer_nodes(driver, csv_path):
    """
    Customer 노드를 pandas로 CSV 파일에서 로드하여 배치 삽입
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    CREATE (c:Customer {
        customer_id: row.customer_id,
        FN: toFloat(row.FN),
        Active: toFloat(row.Active),
        club_member_status: row.club_member_status,
        fashion_news_frequency: row.fashion_news_frequency,
        age: toInteger(row.age),
        postal_code: row.postal_code
    })
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.nodes_created
    print(f"  Customer 노드 생성: {count:,}개")


# [이 파일에서 정의] 이하 분류 노드 6개: ProductType, ProductGroup, ColourGroup, Department, Section, GarmentGroup
# 모두 "번호 + 이름" 두 속성만 가진 작은 노드. 상품을 분류 기준으로 묶어 탐색하려고 따로 노드로 뺐다
def load_product_type_nodes(driver, csv_path):
    """
    ProductType 노드를 pandas로 CSV 파일에서 로드하여 배치 삽입
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    CREATE (p:ProductType {
        product_type_no: toInteger(row.product_type_no),
        product_type_name: row.product_type_name
    })
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.nodes_created
    print(f"  ProductType 노드 생성: {count:,}개")


def load_product_group_nodes(driver, csv_path):
    """
    ProductGroup 노드를 pandas로 CSV 파일에서 로드하여 배치 삽입
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    CREATE (p:ProductGroup {
        name: row.name
    })
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.nodes_created
    print(f"  ProductGroup 노드 생성: {count:,}개")


def load_colour_group_nodes(driver, csv_path):
    """
    ColourGroup 노드를 pandas로 CSV 파일에서 로드하여 배치 삽입
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    CREATE (c:ColourGroup {
        colour_group_code: toInteger(row.colour_group_code),
        colour_group_name: row.colour_group_name
    })
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.nodes_created
    print(f"  ColourGroup 노드 생성: {count:,}개")


def load_department_nodes(driver, csv_path):
    """
    Department 노드를 pandas로 CSV 파일에서 로드하여 배치 삽입
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    CREATE (d:Department {
        department_no: toInteger(row.department_no),
        department_name: row.department_name
    })
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.nodes_created
    print(f"  Department 노드 생성: {count:,}개")


def load_section_nodes(driver, csv_path):
    """
    Section 노드를 pandas로 CSV 파일에서 로드하여 배치 삽입
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    CREATE (s:Section {
        section_no: toInteger(row.section_no),
        section_name: row.section_name
    })
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.nodes_created
    print(f"  Section 노드 생성: {count:,}개")


def load_garment_group_nodes(driver, csv_path):
    """
    GarmentGroup 노드를 pandas로 CSV 파일에서 로드하여 배치 삽입
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    CREATE (g:GarmentGroup {
        garment_group_no: toInteger(row.garment_group_no),
        garment_group_name: row.garment_group_name
    })
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.nodes_created
    print(f"  GarmentGroup 노드 생성: {count:,}개")


# ============================================
# 4단계: 관계 생성
# ============================================

# [이 파일에서 정의] 구매 기록 -> PURCHASED 관계. 수백만 행이라 한 번에 읽지 않고 5만 행씩 나눠서 처리
def create_purchased_relationships(driver, csv_path):
    """
    Customer → Article (PURCHASED) 관계를 pandas로 배치 생성 (청크 단위 처리)
    """
    print("  PURCHASED 관계 생성 중 (대용량 데이터, 청크 단위 처리)...")

    total_count = 0
    chunk_num = 0
    # time.time(): [출처] 표준 라이브러리 time. 지금 시각을 초(실수)로. 두 번 재서 빼면 걸린 시간
    # 주의: 이 파일에는 import time 이 없어서 여기서 NameError 가 난다
    start_time = time.time()

    # 두 MATCH 로 고객과 상품을 찾고(제약조건 인덱스 덕분에 빠르다) 그 사이에 관계를 CREATE
    # date(row.t_dat): "2020-09-01" 같은 글 -> Cypher 날짜 값
    # 관계 속성: 날짜, 가격, 판매 채널. 같은 고객이 같은 상품을 여러 번 사면 관계도 여러 개 (CREATE 라서)
    query = """
    UNWIND $records AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (a:Article {article_id: toInteger(row.article_id)})
    CREATE (c)-[:PURCHASED {
        date: date(row.t_dat),
        price: toFloat(row.price),
        sales_channel_id: toInteger(row.sales_channel_id)
    }]->(a)
    """

    # pd.read_csv(경로, chunksize=50000)
    # [반환] DataFrame 이 아니라 "반복자". for 로 돌리면 5만 행짜리 DataFrame 을 하나씩 준다
    # [왜] 전체를 메모리에 올리지 않고, Neo4j 트랜잭션 하나도 너무 커지지 않게
    # 청크 단위로 읽기 (50,000개씩)
    for chunk in pd.read_csv(csv_path, chunksize=50000):
        chunk_num += 1
        records = chunk.where(pd.notnull(chunk), None).to_dict('records')

        summary = driver.execute_query(
            query,
            records=records,
            database_=NEO4J_DATABASE
        ).summary

        # relationships_created: 만든 관계 수
        count = summary.counters.relationships_created
        total_count += count

        # %: 나머지. chunk_num 이 10의 배수일 때만 (50만 행마다) 진행 상황 출력
        # 10개 청크마다 진행상황 출력
        if chunk_num % 10 == 0:
            elapsed = time.time() - start_time
            # {elapsed:.1f}: 소수점 아래 1자리
            print(f"    처리 중... {total_count:,}개 ({elapsed:.1f}초)")

    elapsed = time.time() - start_time
    print(f"  PURCHASED 관계 생성: {total_count:,}개 ({elapsed:.1f}초)")


# [이 파일에서 정의] 이하 관계 6개는 모두 같은 모양: 상품 찾기 + 분류 노드 찾기 + CREATE
# (데이터가 작아서 chunksize 없이 한 번에)
def create_of_type_relationships(driver, csv_path):
    """
    Article → ProductType (OF_TYPE) 관계를 pandas로 배치 생성
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    MATCH (a:Article {article_id: toInteger(row.article_id)})
    MATCH (p:ProductType {product_type_no: toInteger(row.product_type_no)})
    CREATE (a)-[:OF_TYPE]->(p)
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.relationships_created
    print(f"  OF_TYPE 관계 생성: {count:,}개")


def create_in_group_relationships(driver, csv_path):
    """
    Article → ProductGroup (IN_GROUP) 관계를 pandas로 배치 생성
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    MATCH (a:Article {article_id: toInteger(row.article_id)})
    MATCH (p:ProductGroup {name: row.product_group_name})
    CREATE (a)-[:IN_GROUP]->(p)
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.relationships_created
    print(f"  IN_GROUP 관계 생성: {count:,}개")


def create_has_colour_relationships(driver, csv_path):
    """
    Article → ColourGroup (HAS_COLOUR) 관계를 pandas로 배치 생성
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    MATCH (a:Article {article_id: toInteger(row.article_id)})
    MATCH (c:ColourGroup {colour_group_code: toInteger(row.colour_group_code)})
    CREATE (a)-[:HAS_COLOUR]->(c)
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.relationships_created
    print(f"  HAS_COLOUR 관계 생성: {count:,}개")


def create_in_department_relationships(driver, csv_path):
    """
    Article → Department (IN_DEPARTMENT) 관계를 pandas로 배치 생성
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    MATCH (a:Article {article_id: toInteger(row.article_id)})
    MATCH (d:Department {department_no: toInteger(row.department_no)})
    CREATE (a)-[:IN_DEPARTMENT]->(d)
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.relationships_created
    print(f"  IN_DEPARTMENT 관계 생성: {count:,}개")


def create_in_section_relationships(driver, csv_path):
    """
    Article → Section (IN_SECTION) 관계를 pandas로 배치 생성
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    MATCH (a:Article {article_id: toInteger(row.article_id)})
    MATCH (s:Section {section_no: toInteger(row.section_no)})
    CREATE (a)-[:IN_SECTION]->(s)
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.relationships_created
    print(f"  IN_SECTION 관계 생성: {count:,}개")


def create_in_garment_group_relationships(driver, csv_path):
    """
    Article → GarmentGroup (IN_GARMENT_GROUP) 관계를 pandas로 배치 생성
    """
    df = pd.read_csv(csv_path)
    records = df.where(pd.notnull(df), None).to_dict('records')

    query = """
    UNWIND $records AS row
    MATCH (a:Article {article_id: toInteger(row.article_id)})
    MATCH (g:GarmentGroup {garment_group_no: toInteger(row.garment_group_no)})
    CREATE (a)-[:IN_GARMENT_GROUP]->(g)
    """

    summary = driver.execute_query(
        query,
        records=records,
        database_=NEO4J_DATABASE
    ).summary

    count = summary.counters.relationships_created
    print(f"  IN_GARMENT_GROUP 관계 생성: {count:,}개")


# ============================================
# 5단계: 통계 확인
# ============================================

# [이 파일에서 정의] 노드/관계 개수 통계
# 딕셔너리를 만들면서 값 자리에서 바로 쿼리를 실행한다: {"Article": 쿼리결과.records[0]["count"], ...}
# .records[0]["count"]: count 쿼리 결과는 1행 -> 첫 행 -> AS count 열
def print_graph_statistics(driver):
    # 노드 개수 조회
    node_counts = {
        "Article": driver.execute_query(
            "MATCH (n:Article) RETURN count(n) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "Customer": driver.execute_query(
            "MATCH (n:Customer) RETURN count(n) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "ProductType": driver.execute_query(
            "MATCH (n:ProductType) RETURN count(n) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "ProductGroup": driver.execute_query(
            "MATCH (n:ProductGroup) RETURN count(n) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "ColourGroup": driver.execute_query(
            "MATCH (n:ColourGroup) RETURN count(n) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "Department": driver.execute_query(
            "MATCH (n:Department) RETURN count(n) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "Section": driver.execute_query(
            "MATCH (n:Section) RETURN count(n) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "GarmentGroup": driver.execute_query(
            "MATCH (n:GarmentGroup) RETURN count(n) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"]
    }

    # 관계 개수 조회
    rel_counts = {
        "PURCHASED": driver.execute_query(
            "MATCH ()-[r:PURCHASED]->() RETURN count(r) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "OF_TYPE": driver.execute_query(
            "MATCH ()-[r:OF_TYPE]->() RETURN count(r) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "IN_GROUP": driver.execute_query(
            "MATCH ()-[r:IN_GROUP]->() RETURN count(r) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "HAS_COLOUR": driver.execute_query(
            "MATCH ()-[r:HAS_COLOUR]->() RETURN count(r) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "IN_DEPARTMENT": driver.execute_query(
            "MATCH ()-[r:IN_DEPARTMENT]->() RETURN count(r) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "IN_SECTION": driver.execute_query(
            "MATCH ()-[r:IN_SECTION]->() RETURN count(r) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"],
        "IN_GARMENT_GROUP": driver.execute_query(
            "MATCH ()-[r:IN_GARMENT_GROUP]->() RETURN count(r) AS count",
            database_=NEO4J_DATABASE
        ).records[0]["count"]
    }

    print("\n" + "=" * 60)
    print("H&M 지식그래프 통계")
    print("=" * 60)

    print("\n1) 노드:")
    # 딕셔너리.items(): (키, 값) 쌍을 하나씩
    for label, count in node_counts.items():
        print(f"  • {label}: {count:,}개")
    # 딕셔너리.values(): 값들만. sum(...): 합계
    total_nodes = sum(node_counts.values())
    print(f"  → 총 {total_nodes:,}개 노드")

    print("\n2) 관계:")
    for rel_type, count in rel_counts.items():
        print(f"  • {rel_type}: {count:,}개")
    total_rels = sum(rel_counts.values())
    print(f"  → 총 {total_rels:,}개 관계")

    print("\n" + "=" * 60)



# ============================================
# 메인
# ============================================

# [이 파일에서 정의] 전체 순서: 환경변수 -> CSV 경로 -> 연결 -> 초기화 -> 노드 -> 관계 -> 통계
def main():
    print("=" * 50)
    print("H&M 지식그래프 구축")
    print("=" * 50)

    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

    # 비밀번호가 없으면 에러를 내서 멈춘다 (raise ValueError)
    if not NEO4J_PASSWORD:
        raise ValueError("NEO4J_PASSWORD 환경변수가 설정되지 않았습니다.")

    # 1. CSV 파일 경로 설정
    # Path("./output"): 실행 위치 기준 상대 경로 -> part2/retail2kg 에서 실행해야 한다
    output_dir = Path("./output")
    # 이름 -> 경로 딕셔너리. 아래에서 csv_files["article"] 처럼 꺼내 쓴다
    # [왜] 파일 경로를 한곳에 모아 두면 바꾸기 쉽다
    csv_files = {
        "article": output_dir / "nodes_article.csv",
        "customer": output_dir / "nodes_customer.csv",
        "product_type": output_dir / "nodes_product_type.csv",
        "product_group": output_dir / "nodes_product_group.csv",
        "colour_group": output_dir / "nodes_colour_group.csv",
        "department": output_dir / "nodes_department.csv",
        "section": output_dir / "nodes_section.csv",
        "garment_group": output_dir / "nodes_garment_group.csv",
        "rel_purchased": output_dir / "rels_purchased.csv",
        "rel_of_type": output_dir / "rels_of_type.csv",
        "rel_in_group": output_dir / "rels_in_group.csv",
        "rel_has_colour": output_dir / "rels_has_colour.csv",
        "rel_in_department": output_dir / "rels_in_department.csv",
        "rel_in_section": output_dir / "rels_in_section.csv",
        "rel_in_garment_group": output_dir / "rels_in_garment_group.csv"
    }

    # 2. Neo4j 연결
    driver = create_neo4j_driver(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # 3. 데이터베이스 초기화
        print("\n- 1단계: 데이터베이스 초기화")
        clear_database(driver)
        create_constraints(driver)

        # 노드를 먼저 모두 만들어야 아래 관계 MATCH 가 노드를 찾을 수 있다 (순서 중요)
        # 4. 노드 생성
        print("\n- 2단계: 노드 생성")
        load_article_nodes(driver, csv_files["article"])
        load_customer_nodes(driver, csv_files["customer"])
        load_product_type_nodes(driver, csv_files["product_type"])
        load_product_group_nodes(driver, csv_files["product_group"])
        load_colour_group_nodes(driver, csv_files["colour_group"])
        load_department_nodes(driver, csv_files["department"])
        load_section_nodes(driver, csv_files["section"])
        load_garment_group_nodes(driver, csv_files["garment_group"])

        # 5. 관계 생성
        print("\n- 3단계: 관계 생성")
        create_purchased_relationships(driver, csv_files["rel_purchased"])
        create_of_type_relationships(driver, csv_files["rel_of_type"])
        create_in_group_relationships(driver, csv_files["rel_in_group"])
        create_has_colour_relationships(driver, csv_files["rel_has_colour"])
        create_in_department_relationships(driver, csv_files["rel_in_department"])
        create_in_section_relationships(driver, csv_files["rel_in_section"])
        create_in_garment_group_relationships(driver, csv_files["rel_in_garment_group"])

        # 6. 통계 출력
        print_graph_statistics(driver)

        print("\nH&M 지식그래프 구축 완료!")

    # 에러가 나도 연결은 닫는다
    finally:
        driver.close()


# 직접 실행할 때만 main()
if __name__ == "__main__":
    main()
