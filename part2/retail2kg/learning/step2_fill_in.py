"""
[2단계: 빈칸 채우기] retail2kg 의 핵심: 반복되는 로더를 일반화 + 대용량 관계를 청크로 적재 + 추천 쿼리.

전제: 노트북으로 output/ CSV 를 만들어 두었다.
실행: part2/retail2kg 에서 `python learning/step2_fill_in.py`
막히면 GUIDE.md -> 원본 retail2kg.py.
"""
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
OUT = Path(__file__).resolve().parent.parent / "output"

# 분류 노드: (레이블, CSV 파일, 키 속성, {노드 속성: 변환식})
CATEGORY_NODES = [
    ("ProductType", "nodes_product_type.csv", "product_type_no",
     {"product_type_no": "toInteger(row.product_type_no)", "product_type_name": "row.product_type_name"}),
    ("ColourGroup", "nodes_colour_group.csv", "colour_group_code",
     {"colour_group_code": "toInteger(row.colour_group_code)", "colour_group_name": "row.colour_group_name"}),
    ("Department", "nodes_department.csv", "department_no",
     {"department_no": "toInteger(row.department_no)", "department_name": "row.department_name"}),
]

# 분류 관계: (관계 타입, CSV 파일, 대상 레이블, 대상 키, CSV 열)
CATEGORY_RELS = [
    ("OF_TYPE", "rels_of_type.csv", "ProductType", "product_type_no", "product_type_no"),
    ("HAS_COLOUR", "rels_has_colour.csv", "ColourGroup", "colour_group_code", "colour_group_code"),
    ("IN_DEPARTMENT", "rels_in_department.csv", "Department", "department_no", "department_no"),
]


def read_records(path: Path) -> list[dict]:
    df = pd.read_csv(path)
    return df.where(pd.notnull(df), None).to_dict("records")


# ---------- 1. 노드 로더 일반화 ----------
def load_nodes(driver, label: str, csv_name: str, props: dict[str, str]) -> int:
    # TODO 1-1: props 로 Cypher 속성 문자열을 만든다.
    #   예) {"a": "toInteger(row.a)", "b": "row.b"} -> "a: toInteger(row.a), b: row.b"
    # TODO 1-2: f"UNWIND $records AS row CREATE (n:{label} {{ ... }})" 를 실행하고 생성 개수를 돌려준다.
    #   레이블을 f-string 으로 넣어도 되는 이유는? (CATEGORY_NODES 는 코드에 고정된 값)
    ...


# ---------- 2. 관계 로더 일반화 ----------
def load_category_rels(driver, rel_type: str, csv_name: str, target_label: str, target_key: str, col: str) -> int:
    # TODO 2-1: (a:Article {article_id: toInteger(row.article_id)}) 와
    #           (t:{target_label} {{{target_key}: toInteger(row.{col})}}) 를 MATCH 하고
    #           (a)-[:{rel_type}]->(t) 를 CREATE 한다.
    #   주의: f-string 의 중괄호 이스케이프
    ...


# ---------- 3. 대용량 관계: 청크 적재 ----------
PURCHASED_QUERY = """
UNWIND $records AS row
MATCH (c:Customer {customer_id: row.customer_id})
MATCH (a:Article {article_id: toInteger(row.article_id)})
CREATE (c)-[:PURCHASED {date: date(row.t_dat), price: toFloat(row.price),
                        sales_channel_id: toInteger(row.sales_channel_id)}]->(a)
"""


def load_purchased(driver, chunk_size: int = 50_000) -> int:
    total, start = 0, time.time()
    # TODO 3-1: pd.read_csv(OUT / "rels_purchased.csv", chunksize=chunk_size) 로 청크를 돌며
    #           NaN -> None 처리 후 PURCHASED_QUERY 를 실행하고 relationships_created 를 누적한다.
    # TODO 3-2: 청크마다 "누적 개수 / 경과 초" 를 출력한다.
    # 실험: chunk_size 를 5_000 / 50_000 / 200_000 으로 바꿔 걸린 시간을 비교해 보자.
    return total


# ---------- 4. 추천 쿼리 ----------
ALSO_BOUGHT = """
// TODO 4-1: "이 상품($article_id)을 산 고객들이 함께 많이 산 다른 상품 Top 5"
//   (a:Article {article_id: $article_id})<-[:PURCHASED]-(c:Customer)-[:PURCHASED]->(other:Article)
//   자기 자신은 제외하고, other 별로 "몇 명의 고객이 샀는지" 세어 내림차순.
//   힌트: WHERE other <> a / count(DISTINCT c) AS score / ORDER BY score DESC LIMIT 5
"""

SAME_TYPE_POPULAR = """
// TODO 4-2: "같은 ProductType 에서 구매자가 가장 많은 상품 Top 5" (콘텐츠 기반)
"""


def main():
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        driver.verify_connectivity()
        # 이 파일은 원본 retail2kg.py 로 Article/Customer 가 이미 적재되어 있다고 가정하고,
        # 분류 노드/관계와 PURCHASED 만 다시 넣는다. 먼저 기존 것을 지운다.
        for label, *_ in CATEGORY_NODES:
            driver.execute_query(f"MATCH (n:{label}) DETACH DELETE n", database_=NEO4J_DATABASE)
        driver.execute_query("MATCH ()-[r:PURCHASED]->() DELETE r", database_=NEO4J_DATABASE)

        for label, csv_name, _key, props in CATEGORY_NODES:
            print(label, load_nodes(driver, label, csv_name, props))
        for args in CATEGORY_RELS:
            print(args[0], load_category_rels(driver, *args))
        print("PURCHASED", load_purchased(driver))

        sample = driver.execute_query(
            "MATCH (a:Article)<-[:PURCHASED]-() RETURN a.article_id AS id, count(*) AS n ORDER BY n DESC LIMIT 1",
            database_=NEO4J_DATABASE,
        ).records[0]["id"]
        if "TODO" not in ALSO_BOUGHT:
            for r in driver.execute_query(ALSO_BOUGHT, article_id=sample, database_=NEO4J_DATABASE).records:
                print(r.data())
    finally:
        driver.close()


if __name__ == "__main__":
    main()
