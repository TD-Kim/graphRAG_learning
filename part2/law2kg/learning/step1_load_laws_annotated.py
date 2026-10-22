"""[1단계: 읽기] step1_load_laws.py (1단계 실행 스크립트: 현행법령 적재) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법: [출처] 파이썬 기본 / 표준 라이브러리 / 외부 라이브러리 / 이 파일에서 정의  [입력] [반환] [왜]

이 파일은 "얇은 실행 스크립트" 다. 실제 일은 law2kg.py 의 setup_neo4j, build_law_graph 가 한다.
여기서는 환경변수 확인 -> 연결 -> 제약조건 -> 법령 적재 -> 통계 출력 순서만 담당한다.
[왜] 함수 모음(law2kg.py)과 실행 순서(step1, step2)를 나누면 1단계와 2단계를 따로 실행/재실행할 수 있다.

실행 (law2kg.py 를 import 하므로 위치가 중요하다)
  part2/law2kg 에서:  PYTHONPATH=. python learning/step1_load_laws_annotated.py
  (python 은 "실행한 파일이 있는 폴더" 에서 import 할 파일을 찾는다. 이 파일은 learning/ 안에 있어서
   PYTHONPATH=. 로 현재 폴더(part2/law2kg)도 찾도록 알려 줘야 한다. 원본은 python step1_load_laws.py 로 충분)
DB 를 지우지는 않는다(MERGE 라 다시 실행해도 중복이 생기지 않는다).
"""

# [출처] 표준 라이브러리. os.getenv
import os
# [출처] 표준 라이브러리. sys.exit(1): 실패로 종료
import sys
# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j
from neo4j import GraphDatabase

# [출처] 같은 폴더의 law2kg.py. 괄호로 감싸면 여러 이름을 여러 줄에 나눠 import 할 수 있다
# 주의: import 하는 순간 law2kg.py 의 맨 위 코드(NEO4J_DATABASE = os.getenv(...))가 실행된다.
#       아직 load_dotenv() 전이라 .env 값이 없을 수 있다 -> law2kg 안의 NEO4J_DATABASE 는 None 일 수 있다
#       (None 이면 드라이버가 기본 DB 를 써서 보통은 문제없다. 고치려면 load_dotenv() 를 import 보다 위로)
from law2kg import (
    setup_neo4j,
    build_law_graph
)

# ============================================
# 환경 변수 설정
# ============================================

# .env 파일을 읽어 환경변수로 등록
load_dotenv()

NEO4J_URI = os.getenv('NEO4J_URI')
NEO4J_USER = os.getenv('NEO4J_USERNAME')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD')
# 이 강의 환경(Neo4j Aura)은 DB 이름 = 사용자 이름이라 같은 값을 쓴다
NEO4J_DATABASE = NEO4J_USER
LAW_API_KEY = os.getenv('LAW_API_KEY')


# [이 파일에서 정의] 1단계 결과를 개수로 확인
def print_law_statistics(driver):
    """법령 그래프 통계 출력 (step1용)"""
    print("\n" + "=" * 50)
    print("법령 그래프 통계")
    print("=" * 50)

    # 노드 수
    # (표시이름, 쿼리) 튜플의 리스트 -> 아래 for 에서 두 변수로 풀어 받는다
    # [왜] 같은 모양의 쿼리를 반복문 하나로 돌리려고
    stats = [
        ("법령(Law)", "MATCH (n:Law) RETURN count(n) as cnt"),
        ("조문(Article)", "MATCH (n:Article) RETURN count(n) as cnt"),
        ("항(Paragraph)", "MATCH (n:Paragraph) RETURN count(n) as cnt"),
        ("호(Item)", "MATCH (n:Item) RETURN count(n) as cnt"),
    ]

    print("\n노드:")
    # for label, query in stats: 튜플 (a, b) 를 label=a, query=b 로 풀기
    for label, query in stats:
        result = driver.execute_query(query, database_=NEO4J_DATABASE)
        # result.records[0]['cnt']: count 쿼리는 결과가 항상 1행 -> [0] 으로 그 행, ['cnt'] 로 AS cnt 열 값
        count = result.records[0]['cnt']
        print(f"  {label}: {count}개")

    # 관계 수
    print("\n관계:")
    rel_stats = [
        ("HAS_ARTICLE", "MATCH ()-[r:HAS_ARTICLE]->() RETURN count(r) as cnt"),
        ("HAS_PARAGRAPH", "MATCH ()-[r:HAS_PARAGRAPH]->() RETURN count(r) as cnt"),
        ("HAS_ITEM", "MATCH ()-[r:HAS_ITEM]->() RETURN count(r) as cnt"),
        ("NEXT_ARTICLE", "MATCH ()-[r:NEXT_ARTICLE]->() RETURN count(r) as cnt"),
    ]

    for label, query in rel_stats:
        result = driver.execute_query(query, database_=NEO4J_DATABASE)
        count = result.records[0]['cnt']
        print(f"  {label}: {count}개")

    # 법령별 조문 수
    print("\n법령별 조문 수 (상위 5개):")
    # Law 별로 묶어서 조문 수 세기 -> 많은 순 5개
    law_article_query = """
    MATCH (l:Law)-[:HAS_ARTICLE]->(a:Article)
    RETURN l.name as law_name, count(a) as article_count
    ORDER BY article_count DESC
    LIMIT 5
    """
    result = driver.execute_query(law_article_query, database_=NEO4J_DATABASE)
    for record in result.records:
        print(f"  {record['law_name']}: {record['article_count']}개")

    print("=" * 50)


# 이 파일을 직접 실행할 때만 아래가 실행된다
if __name__ == "__main__":
    print("=" * 50)
    print("법령 지식 그래프 구축 - (1) 현행법령 적재")
    print("=" * 50)

    # 적재할 법령 수 (law2kg 의 build_law_graph 는 1부터 세서 실제로는 9개를 처리한다. law2kg 주석본 참고)
    max_laws = 10

    # or: 하나라도 없으면 / not 값: 값이 None 이나 빈 문자열이면 True
    if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
        print("\n오류: Neo4j 연결 정보가 설정되지 않았습니다")
        sys.exit(1)

    if not LAW_API_KEY:
        print("\n오류: LAW_API_KEY가 설정되지 않았습니다")
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        # 연결 확인. 실패하면 예외 -> finally 에서 close
        driver.verify_connectivity()
        print(f"\nNeo4j 연결 성공: {NEO4J_URI}\n")

        # 제약조건 먼저 (MERGE 가 빨라지고 중복 방지)
        setup_neo4j(driver)

        print(f"법령 {max_laws}개 적재 시작...\n")
        # max_laws=max_laws: 키워드 인자. 왼쪽은 매개변수 이름, 오른쪽은 이 파일의 변수
        build_law_graph(driver, LAW_API_KEY, max_laws=max_laws)

        print_law_statistics(driver)

    # try 안에서 에러가 나도 반드시 실행
    finally:
        driver.close()
