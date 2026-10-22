"""[1단계: 읽기] step2_link_interpretations.py (2단계 실행 스크립트: 해석례 연결) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법: [출처] 파이썬 기본 / 표준 라이브러리 / 외부 라이브러리 / 이 파일에서 정의  [입력] [반환] [왜]
step1_load_laws 주석본과 같은 구조라서 다른 부분만 적었다.

전제: step1_load_laws.py 를 먼저 실행해서 Law, Article ... 이 DB 에 있어야 한다
      (build_interpretation_graph 는 DB 의 법령 이름으로 해석례를 검색한다)
실제 일은 law2kg.py 의 build_interpretation_graph 가 한다. 해석례마다 LLM 을 1번 부른다(gpt-4o-mini).

실행: part2/law2kg 에서  PYTHONPATH=. python learning/step1_link_interpretations_annotated.py
"""

import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase

# [출처] 같은 폴더의 law2kg.py (import 하는 순간 law2kg.py 맨 위 코드가 실행된다. step1 주석본 참고)
from law2kg import (
    build_interpretation_graph
)

# ============================================
# 환경 변수 설정
# ============================================

# .env 읽기
load_dotenv()

NEO4J_URI = os.getenv('NEO4J_URI')
NEO4J_USER = os.getenv('NEO4J_USERNAME')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD')
NEO4J_DATABASE = NEO4J_USER
LAW_API_KEY = os.getenv('LAW_API_KEY')


# [이 파일에서 정의] 2단계 결과를 개수로 확인
def print_interpretation_statistics(driver):
    """해석례 그래프 통계 출력 (step2용)"""
    print("\n" + "=" * 50)
    print("해석례 그래프 통계")
    print("=" * 50)

    # 노드 수
    # (표시이름, 쿼리) 리스트 -> 반복문 하나로 개수 세기
    stats = [
        ("해석례(LegalInterpretation)", "MATCH (n:LegalInterpretation) RETURN count(n) as cnt"),
        ("질의(Question)", "MATCH (n:Question) RETURN count(n) as cnt"),
        ("회답(Answer)", "MATCH (n:Answer) RETURN count(n) as cnt"),
        ("이유(Reason)", "MATCH (n:Reason) RETURN count(n) as cnt"),
        ("기관(Organization)", "MATCH (n:Organization) RETURN count(n) as cnt"),
    ]

    print("\n노드:")
    for label, query in stats:
        result = driver.execute_query(query, database_=NEO4J_DATABASE)
        # count 쿼리 결과는 항상 1행 -> records[0], 그 안의 cnt 열
        count = result.records[0]['cnt']
        print(f"  {label}: {count}개")

    # 관계 수
    print("\n관계:")
    # 주의: HAS_REASON 은 목록에 없다. law2kg 주석본(create_interpretation_node)을 보면 실제로도 거의 안 만들어진다
    rel_stats = [
        ("INTERPRETS", "MATCH ()-[r:INTERPRETS]->() RETURN count(r) as cnt"),
        ("CITES", "MATCH ()-[r:CITES]->() RETURN count(r) as cnt"),
        ("HAS_QUESTION", "MATCH ()-[r:HAS_QUESTION]->() RETURN count(r) as cnt"),
        ("HAS_ANSWER", "MATCH ()-[r:HAS_ANSWER]->() RETURN count(r) as cnt"),
        ("ANSWERED_BY", "MATCH ()-[r:ANSWERED_BY]->() RETURN count(r) as cnt"),
        ("SUPPORTED_BY", "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) as cnt"),
        ("REQUESTED", "MATCH ()-[r:REQUESTED]->() RETURN count(r) as cnt"),
    ]

    for label, query in rel_stats:
        result = driver.execute_query(query, database_=NEO4J_DATABASE)
        count = result.records[0]['cnt']
        print(f"  {label}: {count}개")

    # CITES 가 어떤 종류 노드(Article, Paragraph, Item, Law)를 가리키는지 종류별 개수
    # labels(target)[0]: 노드의 첫 번째 레이블
    # WITH ... count(r) : 레이블별로 묶어서 센 다음 다음 단계로 넘긴다
    # CITES 상세 분석
    print("\nCITES 관계 상세:")
    cites_detail_query = """
    MATCH (i:LegalInterpretation)-[r:CITES]->(target)
    WITH labels(target)[0] as target_type, count(r) as cnt
    RETURN target_type, cnt
    ORDER BY cnt DESC
    """
    result = driver.execute_query(cites_detail_query, database_=NEO4J_DATABASE)
    for record in result.records:
        print(f"  → {record['target_type']}: {record['cnt']}개")

    print("=" * 50)


if __name__ == "__main__":
    print("=" * 50)
    print("법령 지식 그래프 구축 - (2) 해석례 연결")
    print("=" * 50)

    # 수집할 해석례 최대 수 (= LLM 호출 최대 수)
    max_interpretations = 20

    if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
        print("\n오류: Neo4j 연결 정보가 설정되지 않았습니다")
        sys.exit(1)

    if not LAW_API_KEY:
        print("\n오류: LAW_API_KEY가 설정되지 않았습니다")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print(f"\nNeo4j 연결 성공: {NEO4J_URI}\n")

        # 해석례 그래프 구축
        print(f"해석례 ~{max_interpretations}개 수집 시작...\n")
        # 2단계 진입점: 법령 이름으로 검색 -> 걸러서 수집 -> 노드 생성 -> 연결 (law2kg 주석본 참고)
        build_interpretation_graph(driver, LAW_API_KEY, max_interpretations=max_interpretations)

        # 통계 출력
        print_interpretation_statistics(driver)

    finally:
        driver.close()
