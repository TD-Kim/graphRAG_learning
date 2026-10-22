"""
[2단계: 빈칸 채우기] 커뮤니티 탐지의 핵심 3단계: 투영 관계 만들기 -> GDS 투영 -> Leiden -> 커뮤니티 요약.
LLM 은 쓰지 않는다. GDS 플러그인이 필요하다.

전제: retail2kg 로 Customer, Article, PURCHASED 가 적재되어 있다.
실행: part3/community_search 에서 `python learning/step2_fill_in.py`
막히면 GUIDE.md -> community_detection_retail.py
"""
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
GRAPH = "coPurchaseStep2"
PROP = "communityStep2"   # 원본 behaviorCommunityId 와 겹치지 않게


def q(driver, cypher: str, **params):
    return driver.execute_query(cypher, params, database_=NEO4J_DATABASE).records


# ---------- 0. 날짜 속성 이름 확인 ----------
def purchase_date_key(driver) -> str:
    # TODO 0: PURCHASED 관계 하나의 keys() 를 보고, 'date' 와 't_dat' 중 있는 것을 돌려준다.
    #   (GUIDE.md 생각해 볼 점 1. 원본은 t_dat 을 가정한다)
    ...


# ---------- 1. CO_PURCHASED ----------
def build_co_purchased(driver, date_key: str, min_purchases: int = 5, max_customers: int = 5000) -> int:
    q(driver, "MATCH ()-[r:CO_PURCHASED_S2]-() DELETE r")
    ids = [r["id"] for r in q(driver, """
        MATCH (c:Customer)-[:PURCHASED]->()
        WITH c, count(*) AS n WHERE n >= $min
        RETURN elementId(c) AS id ORDER BY n DESC LIMIT $max
    """, min=min_purchases, max=max_customers)]

    for i in range(0, len(ids), 500):
        # TODO 1: 고객 배치마다
        #   (c)-[p:PURCHASED]->(a) 를 (c, p.<date_key>) 로 묶어 collect(a)
        #   2개 이상인 묶음에서 a1, a2 쌍을 만들고 (elementId(a1) < elementId(a2))
        #   MERGE (a1)-[r:CO_PURCHASED_S2]-(a2) ON CREATE SET r.weight = 1 ON MATCH SET r.weight = r.weight + 1
        #   date_key 는 속성 이름이라 f-string 으로 넣는다. 사용자 입력이 아니라 코드가 확인한 값이라 안전하다.
        pass
    return q(driver, "MATCH ()-[r:CO_PURCHASED_S2]->() RETURN count(r) AS n")[0]["n"]


# ---------- 2. GDS 투영 ----------
def project(driver) -> dict:
    # TODO 2-1: 이미 있으면 지운다. CALL gds.graph.exists($g) YIELD exists ... / gds.graph.drop($g)
    # TODO 2-2: CALL gds.graph.project($g, 'Article', {CO_PURCHASED_S2: {orientation: 'UNDIRECTED', properties: 'weight'}})
    #           YIELD nodeCount, relationshipCount
    #   왜 UNDIRECTED 인가?
    ...


# ---------- 3. Leiden ----------
def leiden(driver, gamma: float = 1.0) -> dict:
    # TODO 3-1: 먼저 stream 모드로 커뮤니티 수만 세어 본다. (DB 에 아무것도 쓰지 않음)
    #   CALL gds.leiden.stream($g, {relationshipWeightProperty: 'weight', gamma: $gamma})
    #   YIELD nodeId, communityId RETURN count(DISTINCT communityId) AS communities
    # TODO 3-2: 만족하면 write 모드로 PROP 에 저장한다. YIELD communityCount, modularity
    #   stream / mutate / write 의 차이를 한 줄씩 적어 보자.
    ...


# ---------- 4. 커뮤니티 요약 ----------
SUMMARY = """
// TODO 4: 크기 상위 5개 커뮤니티마다
//   - 상품 수
//   - 가장 많은 product_type_name 3개 (빈도순! 원본은 처음 나온 순서)
//   - 가장 많은 colour_group_name 3개
//   힌트: WITH community, a.product_type_name AS t, count(*) AS n ORDER BY n DESC
//         WITH community, collect(t)[..3] AS top_types ...
"""


def main():
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        key = purchase_date_key(driver)
        print("날짜 속성:", key)
        print("CO_PURCHASED:", build_co_purchased(driver, key or "date"))
        print("투영:", project(driver))
        for gamma in (0.5, 1.0, 2.0):
            print(f"gamma={gamma}:", leiden(driver, gamma))   # 마지막 실행 결과가 PROP 에 남는다
        if "TODO" not in SUMMARY:
            for r in q(driver, SUMMARY):
                print(r.data())
    finally:
        try:
            q(driver, "CALL gds.graph.drop($g, false)", g=GRAPH)  # 메모리 정리
        finally:
            driver.close()


if __name__ == "__main__":
    main()
