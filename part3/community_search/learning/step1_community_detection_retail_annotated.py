"""[1단계: 읽기] community_detection_retail.py (함께 산 상품끼리 잇고 -> GDS Leiden 으로 상품 커뮤니티 찾기 -> 노드에 저장) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나

이 파일의 핵심 개념 두 가지
  - 커뮤니티(community): 그래프 안에서 "자기들끼리는 촘촘히 연결되고, 바깥과는 듬성듬성 연결된" 노드 묶음.
    여기서는 "고객들이 같이 사는 상품 묶음" 이다 (예: 운동복 상의 + 레깅스 + 스포츠 브라).
  - Leiden 알고리즘: 커뮤니티를 자동으로 찾는 알고리즘. 처음엔 노드 하나하나가 각자 커뮤니티였다가,
    "옆 커뮤니티로 옮기면 묶음이 더 좋아지는가(모듈성 modularity 가 오르는가)" 를 반복해서 합친다.
    묶음을 다시 노드 하나로 보고 같은 일을 위 단계(level)에서 반복한다. Louvain 의 개선판으로,
    "커뮤니티 안이 실제로 서로 이어져 있음" 을 보장하도록 다듬는 단계(refinement)가 추가된 것이 차이다.
    모듈성: "커뮤니티 안의 연결이 무작위로 이었을 때보다 얼마나 많은가" 를 나타내는 점수 (대략 -0.5~1, 클수록 잘 나뉨).

GDS(Graph Data Science) 에 대해
  - GDS 는 파이썬 패키지가 아니라 Neo4j 서버에 설치하는 "플러그인" 이다. 이 파일은 파이썬 GDS 클라이언트(graphdatascience)를
    쓰지 않고, CALL gds.xxx(...) Cypher 문장을 neo4j 드라이버로 보낸다.
  - GDS 사용 순서: (1) gds.graph.project 로 DB 의 일부를 "메모리 그래프" 로 복사 -> (2) 알고리즘 실행
    (stream: 결과를 행으로 돌려줌 / mutate: 메모리 그래프에만 저장 / write: DB 노드 속성에 저장) -> (3) gds.graph.drop 으로 메모리 해제.
  - GDS 프로시저의 매개변수/반환 열 이름은 neo4j.com 문서에 접속하지 못해, 같은 프로시저를 감싸는 파이썬 클라이언트
    graphdatascience 2.3 의 소스(LeidenWriteResult, GraphProjectResult 등)로 확인했다. GDS 서버 플러그인 자체의 소스는 확인 못 함.

흐름 요약
  [원래 그래프]  (Customer)-[:PURCHASED]->(Article)      <- 고객-상품 (이분 그래프: 상품끼리는 직접 안 이어짐)
       | 같은 고객이 "같은 날" 산 상품 쌍마다 (배치 500명씩 Cypher)
       v
  (Article)-[:CO_PURCHASED {weight: 같이 산 횟수}]-(Article)  <- 상품-상품 (DB 에 실제로 저장되는 관계)
       | gds.graph.project('retailBehaviorGraph', 'Article', CO_PURCHASED 무방향 + weight)
       v
  메모리 그래프 --gds.leiden.write--> 각 Article 노드에 behaviorCommunityId = 커뮤니티 번호
       v
  analyze_behavior_communities: 커뮤니티마다 스타일/색 다양성을 출력
  다음 파일 retail_community_graphrag.py 가 이 behaviorCommunityId 로 추천을 한다.

읽는 순서 권장: main -> check_purchase_data_size -> project_customer_behavior_graph -> run_leiden_on_customer_behavior
               -> analyze_behavior_communities -> (나머지 유틸 함수)
실행 위치: part3/community_search  ->  python learning/step1_community_detection_retail_annotated.py
전제: part2/retail2kg 로 H&M 그래프 적재, Neo4j 에 GDS 플러그인 설치(RETURN gds.version() 로 확인), .env 에 NEO4J_URI/USERNAME/PASSWORD.
주의: 이 스크립트는 DB 에 CO_PURCHASED 관계를 지우고 다시 만들고, Article 노드에 속성을 쓴다 (읽기 전용이 아니다).
"""

# [출처] 표준 라이브러리. os.getenv 로 환경변수 읽기
import os
# [출처] 표준 라이브러리. sys.exit(1) 로 프로그램을 "실패(1)" 상태로 끝내는 데 쓴다
import sys
# [출처] 표준 라이브러리 typing. Dict[str, Any] 처럼 "이 값은 어떤 모양이다" 를 적는 타입 힌트용 (실행에는 영향 없음)
from typing import Dict, List, Any

# [출처] 외부 라이브러리 python-dotenv. .env 파일을 읽어 환경변수로 등록
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 공식 파이썬 드라이버. GraphDatabase.driver(...) 로 DB 연결 객체를 만든다
from neo4j import GraphDatabase

# .env -> 환경변수. 이후 os.getenv("NEO4J_URI") 등이 값을 돌려준다
load_dotenv()

# 모든 쿼리에 database_=NEO4J_DATABASE 로 넘길 "데이터베이스 이름"
# 주의: 환경변수 NEO4J_USERNAME(사용자 이름)을 DB 이름으로 쓰고 있다. 사용자 이름과 DB 이름이 둘 다 "neo4j" 인
#       기본 설정(Aura 무료 등)에서는 우연히 맞지만, 다르면 "그런 데이터베이스 없음" 에러가 날 수 있다.
#       원래 의도는 os.getenv("NEO4J_DATABASE") 였을 가능성이 크다
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")


# ============================================
# 유틸리티 함수
# ============================================

# [이 파일에서 정의] 환경변수로 드라이버를 만들고 연결을 확인한다 [반환] neo4j Driver
def create_neo4j_connection():
    """Neo4j 데이터베이스 연결 생성"""
    uri = os.getenv('NEO4J_URI')
    username = os.getenv('NEO4J_USERNAME')
    password = os.getenv('NEO4J_PASSWORD')

    # GraphDatabase.driver(uri, auth=(사용자, 비밀번호))
    # [출처] 외부 라이브러리 neo4j  [반환] Driver (연결 풀). 만드는 것만으로는 아직 접속하지 않는다
    driver = GraphDatabase.driver(uri, auth=(username, password))
    # driver.verify_connectivity(): 실제로 서버에 접속해 본다. 주소/비밀번호가 틀리면 여기서 예외가 난다
    driver.verify_connectivity()
    # f"...{uri}": f-string. 따옴표 앞 f 를 붙이면 {변수} 자리에 값이 들어간 글이 된다
    print(f"✓ Neo4j 연결 성공: {uri}")
    return driver


# [이 파일에서 정의] GDS 플러그인이 설치돼 있는지 확인 [반환] True/False
# "-> bool" 은 반환 타입 힌트
def verify_gds_available(driver) -> bool:
    """GDS 플러그인 설치 확인"""
    # try/except: try 안에서 예외(에러)가 나면 프로그램이 죽지 않고 except 로 넘어간다
    try:
        # driver.execute_query(쿼리, database_=DB이름)
        # [출처] 외부 라이브러리 neo4j
        # [입력] Cypher 글, (선택) 쿼리 매개변수는 키워드 인자로, database_ 처럼 밑줄로 끝나는 인자는 드라이버 설정
        # [반환] EagerResult (records, summary, keys 세 가지). .records 는 Record 리스트, record['열이름'] 으로 값을 꺼낸다
        # [왜] gds.version() 은 GDS 가 없으면 "알 수 없는 함수" 에러가 나므로, 에러 여부로 설치를 판단한다
        result = driver.execute_query("RETURN gds.version() AS version", database_=NEO4J_DATABASE)
        version = result.records[0]['version']
        print(f"✓ Neo4j GDS 버전: {version}")
        return True
    # Exception: 거의 모든 에러를 잡는다. 여기서는 "GDS 없음" 외의 에러(연결 끊김 등)도 False 로 뭉뚱그려진다
    except Exception:
        return False


# [이 파일에서 정의] Article 노드가 하나라도 있는지 확인 (retail2kg 를 먼저 돌렸는지)
def check_retail_data_exists(driver) -> bool:
    """Retail 데이터 존재 확인"""
    # """ ... """: 여러 줄 문자열. Cypher 를 보기 좋게 여러 줄로 쓴다
    # count(a) 는 집계라 결과는 항상 1행이다 (LIMIT 1 은 사실상 의미 없음)
    query = """
    MATCH (a:Article)
    RETURN count(a) AS article_count
    LIMIT 1
    """

    result = driver.execute_query(query, database_=NEO4J_DATABASE)

    # not result.records: 리스트가 비어 있으면 True. or 뒤는 앞이 False 일 때만 계산된다
    if not result.records or result.records[0]['article_count'] == 0:
        print("먼저 part2/retail2kg 데이터를 로드해주세요.")
        return False

    count = result.records[0]['article_count']
    # {count:,}: 형식 지정. 천 단위 쉼표 (105542 -> 105,542)
    print(f"✓ Article 노드 {count:,}개 확인")
    return True


# ============================================
# 데이터 통계 함수
# ============================================

# [이 파일에서 정의] 노드/관계 개수 통계 출력 (확인용, 결과를 돌려주지 않음)
def print_data_statistics(driver):
    """Retail 그래프 통계 출력"""
    # "=" * 60: 문자열 곱하기. "=" 를 60번 이어 붙인 구분선
    print("\n" + "=" * 60)
    print("H&M Retail Graph 통계")
    print("=" * 60)

    # 노드 통계
    # labels(n)[0]: 노드의 첫 번째 레이블. WITH ... count(*): 레이블별로 묶어 세기 (Cypher 의 그룹화는 WITH/RETURN 의 집계로 한다)
    # 주의: 모든 노드를 훑으므로 큰 DB 에서는 느릴 수 있다
    node_query = """
    MATCH (n)
    WITH labels(n)[0] AS label, count(*) AS count
    WHERE label IS NOT NULL
    RETURN label, count
    ORDER BY count DESC
    """

    result = driver.execute_query(node_query, database_=NEO4J_DATABASE)

    print("\n노드 통계:")
    print("-" * 60)
    total_nodes = 0
    # for 변수 in 리스트: 하나씩 꺼내 반복
    for record in result.records:
        count = record['count']
        total_nodes += count
        # {값:20}: 20칸 폭으로 왼쪽 정렬, {값:>10,}: 10칸 폭 오른쪽 정렬 + 쉼표
        print(f"  {record['label']:20} {count:>10,}개")
    print(f"  {'총합':20} {total_nodes:>10,}개")

    # 관계 통계 (최적화: 관계 타입별로 개별 카운트)
    print("\n관계 통계:")
    print("-" * 60)

    # 알려진 관계 타입들을 개별적으로 빠르게 카운트
    # 관계 타입 이름 목록을 직접 적어 두고 타입별로 따로 센다
    # [왜] MATCH ()-[r:타입]->() RETURN count(r) 은 Neo4j 가 통계 저장소에서 바로 답할 수 있어 빠르다 (전체 관계를 훑지 않음)
    rel_types = [
        'PURCHASED', 'OF_TYPE', 'HAS_COLOUR', 'IN_DEPARTMENT',
        'IN_SECTION', 'IN_GARMENT_GROUP', 'IN_GROUP'
    ]

    total_rels = 0
    for rel_type in rel_types:
        # f-string 으로 관계 타입 이름을 쿼리에 끼워 넣는다. 레이블/관계 타입은 $매개변수로 넘길 수 없어서 이렇게 한다
        # (사용자 입력이 아니라 위 고정 목록이라 안전하다)
        query = f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS count"
        try:
            result = driver.execute_query(query, database_=NEO4J_DATABASE)
            count = result.records[0]['count']
            if count > 0:
                total_rels += count
                print(f"  {rel_type:20} {count:>10,}개")
        # except: (아무것도 안 쓰면) 모든 예외를 잡는다. pass: 아무것도 안 함 -> 그 타입은 조용히 건너뛴다
        except:
            pass

    print(f"  {'총합':20} {total_rels:>10,}개")

    print("=" * 60)


# ============================================
# Graph Projection
# ============================================

# [이 파일에서 정의] 같은 이름의 메모리 그래프가 이미 있으면 지운다
# [왜] gds.graph.project 는 같은 이름의 그래프가 이미 있으면 에러가 나므로 다시 실행하기 전에 지운다
def drop_graph_if_exists(driver, graph_name: str):
    """기존 그래프 제거"""
    try:
        # CALL gds.graph.drop('이름') YIELD graphName
        # [출처] Neo4j GDS 플러그인 프로시저 (Cypher 로 부른다)
        # [입력] 메모리 그래프 이름. 두 번째 인자 failIfMissing 기본값이 true 라서, 그래프가 없으면 에러가 난다
        #        (graphdatascience 2.3 소스에서 drop 의 fail_if_missing 을 그대로 넘기는 것으로 확인)
        # [반환] 지운 그래프 정보. YIELD graphName 으로 이름만 받는다
        # [왜] 메모리 그래프는 서버 RAM 을 차지한다. 다 쓰면 지워야 한다
        # 그래서 아래 except 는 "그래프가 없었다" 는 뜻으로 쓰인다 (다른 에러도 같은 메시지가 된다)
        driver.execute_query(
            f"CALL gds.graph.drop('{graph_name}') YIELD graphName",
            database_=NEO4J_DATABASE
        )
        print(f"기존 '{graph_name}' 그래프 제거 완료")
    except:
        print(f"기존 그래프 없음")


# [이 파일에서 정의] 구매 관계 수를 보고 "고객을 샘플링할지" 와 "최소 구매 횟수" 를 정한다
# [반환] 딕셔너리 {'total_purchases', 'total_customers', 'use_sampling', 'recommended_min_purchases'}
# [왜] CO_PURCHASED 는 고객마다 (산 상품 수)^2 에 가까운 쌍을 만든다. 데이터가 크면 메모리/시간이 폭발하므로 활동 많은 고객만 쓴다
def check_purchase_data_size(driver) -> Dict[str, Any]:
    """구매 데이터 규모 확인 (메모리 안전성 체크)"""
    print("\n" + "=" * 60)
    print("구매 데이터 규모 확인")
    print("=" * 60)

    # 전체 PURCHASED 관계 수
    query = "MATCH ()-[r:PURCHASED]->() RETURN count(r) AS total"
    result = driver.execute_query(query, database_=NEO4J_DATABASE)
    total_purchases = result.records[0]['total']

    # 고객 수
    query = "MATCH (c:Customer) RETURN count(c) AS total"
    result = driver.execute_query(query, database_=NEO4J_DATABASE)
    total_customers = result.records[0]['total']

    print(f"\n전체 구매 관계: {total_purchases:,}개")
    print(f"전체 고객 수: {total_customers:,}개")

    # 100_000: 숫자 안의 밑줄은 읽기 쉽게 하는 구분자 (= 100000)
    if total_purchases > 100_000:
        use_sampling = True
        print("(5회 이상 구매한 고객만 샘플링합니다.)")
        recommended_min_purchases = 5   # 5회 이상 구매 고객
    else:
        use_sampling = False
        recommended_min_purchases = 2

    # 딕셔너리로 여러 값을 한 번에 돌려준다. 주의: use_sampling 은 main 에서 쓰이지 않는다
    return {
        'total_purchases': total_purchases,
        'total_customers': total_customers,
        'use_sampling': use_sampling,
        'recommended_min_purchases': recommended_min_purchases
    }


# [이 파일에서 정의] CO_PURCHASED 관계를 만들고, 그걸로 GDS 메모리 그래프를 만든다 (이 파일의 핵심 1)
# [입력] graph_name: 메모리 그래프 이름 (기본값 "retailBehaviorGraph"), min_purchases: 이 횟수 이상 산 고객만 사용
#        "인자: 타입 = 기본값" 형태. 호출할 때 안 넘기면 기본값이 쓰인다
# [반환] {'graphName', 'nodeCount', 'relationshipCount'}
# 주의: graph_name 을 받지만 아래 project 쿼리(285줄)에는 'retailBehaviorGraph' 가 글자로 고정돼 있다.
#       다른 이름을 넘기면 drop 은 그 이름으로, project 는 고정 이름으로 해서 어긋난다
def project_customer_behavior_graph(
    driver,
    graph_name: str = "retailBehaviorGraph",
    min_purchases: int = 10
):
    """
    고객 구매 행동 기반 그래프 프로젝션

    같은 날 구매한 상품들만 연결
    → "함께 구매되는 상품" 정확히 발견
    → 예: 2019-09-25 재킷 + 셔츠 + 바지 구매 → 3개 상품 연결
    """
    print("\n" + "=" * 60)
    print("[1] 고객 구매 행동 Graph Projection")
    print("=" * 60)

    # 다시 실행해도 되도록 먼저 기존 메모리 그래프 제거
    drop_graph_if_exists(driver, graph_name)

    # 활성 고객 수 확인
    # f""" ... """: 여러 줄 f-string. {min_purchases} 자리에 숫자가 들어간다 (Cypher 의 {} 가 없어서 중괄호 이스케이프 불필요)
    # 고객별 구매 수를 세고(WITH c, count(r)), 기준 이상인 고객 수와 그들의 구매 합계를 구한다 (출력용 통계)
    active_customer_query = f"""
    MATCH (c:Customer)-[r:PURCHASED]->()
    WITH c, count(r) AS purchaseCount
    WHERE purchaseCount >= {min_purchases}
    RETURN count(c) AS activeCustomers, sum(purchaseCount) AS totalPurchases
    """

    result = driver.execute_query(active_customer_query, database_=NEO4J_DATABASE)
    active_customers = result.records[0]['activeCustomers']
    total_relevant = result.records[0]['totalPurchases']

    print(f"\n샘플링 전략:")
    print(f"  - 최소 구매 횟수: {min_purchases}회 이상 (고활성 고객)")
    print(f"  - 활성 고객 수: {active_customers:,}명")
    print(f"  - 해당 구매 건수: {total_relevant:,}개")

    print(f"\nCO_PURCHASED 관계 생성 중...")

    print(f"  - 기존 CO_PURCHASED 관계 삭제 중...")
    deleted_total = 0
    # while True: 무한 반복. 안에서 break 를 만나야 끝난다
    # [왜] 기존 CO_PURCHASED 를 한 번에 다 지우면 트랜잭션이 너무 커져 메모리가 부족할 수 있다 -> 5만 개씩 나눠 지운다
    while True:
        delete_result = driver.execute_query(
            # WITH r LIMIT 50000 DELETE r: 5만 개만 골라 지운다. 지운 개수가 0 이 되면 다 지운 것
            "MATCH ()-[r:CO_PURCHASED]->() WITH r LIMIT 50000 DELETE r RETURN count(r) AS deleted",
            database_=NEO4J_DATABASE
        )
        deleted = delete_result.records[0]['deleted']
        if deleted == 0:
            break
        deleted_total += deleted
        print(f"    - {deleted_total:,}개 삭제 중...")

    if deleted_total > 0:
        print(f"  ✓ 기존 관계 {deleted_total:,}개 삭제 완료")

    print(f"  - 같은 날 구매한 상품 관계 생성 중 (장바구니 분석)...")

    # 1단계: 고활성 고객 ID 수집 (가벼운 쿼리)
    # 1단계: 대상 고객의 ID 목록만 먼저 가져온다 (가벼운 쿼리)
    # elementId(c): Neo4j 가 노드마다 붙인 내부 ID 글자 (예: "4:abc...:123"). 다음 쿼리에서 그 노드를 다시 찾는 데 쓴다
    # ORDER BY purchaseCount DESC LIMIT 10000: 많이 산 순서로 최대 1만 명
    customer_query = f"""
    MATCH (c:Customer)-[:PURCHASED]->(:Article)
    WITH c, count(*) AS purchaseCount
    WHERE purchaseCount >= {min_purchases}
    RETURN elementId(c) AS customerId
    ORDER BY purchaseCount DESC
    LIMIT 10000
    """

    result = driver.execute_query(customer_query, database_=NEO4J_DATABASE)
    # [r['customerId'] for r in result.records]: 리스트 컴프리헨션.
    # "결과 행마다 customerId 값을 꺼내 새 리스트로" 를 한 줄로 쓴 것 (for 문 + append 와 같다)
    customer_ids = [r['customerId'] for r in result.records]
    total_customers = len(customer_ids)
    print(f"  대상 고객: {total_customers:,}명")

    # 2단계: 배치 처리로 관계 생성
    # 2단계: 500명씩 나눠(배치) 처리한다. 한 번에 1만 명을 하면 트랜잭션이 너무 커진다
    batch_size = 500
    total_created = 0

    # range(시작, 끝, 간격): 0, 500, 1000, ... 처럼 batch_size 씩 건너뛰는 숫자
    for i in range(0, total_customers, batch_size):
        # 리스트[i:i + 500]: 슬라이싱. i 번째부터 500개 (끝을 넘어도 에러 없이 있는 만큼만)
        batch_ids = customer_ids[i:i + batch_size]
        # //: 정수 나눗셈 (몫만). 배치 번호 표시용
        batch_num = i // batch_size + 1
        # (전체 + 크기 - 1) // 크기: 올림 나눗셈. 1001명이면 3배치
        total_batches = (total_customers + batch_size - 1) // batch_size

        # 각 고객의 같은 날 구매한 상품들만 연결
        # 이 파일의 핵심 Cypher: 같은 고객이 같은 날 산 상품끼리 CO_PURCHASED 로 잇는다 (장바구니 분석)
        #   UNWIND $customerIds: 넘겨받은 ID 리스트를 행으로 펼친다 ($customerIds 는 아래 customerIds=batch_ids 로 채워짐)
        #   WITH c, p.t_dat AS purchaseDate, collect(a): (고객, 날짜) 별로 상품을 리스트로 모은다 = "그날의 장바구니"
        #   WHERE size(articles) >= 2: 상품이 2개 이상인 장바구니만 (쌍을 만들 수 있어야 하니까)
        #   UNWIND articles AS a1 / UNWIND articles AS a2: 장바구니 안에서 모든 (a1, a2) 조합을 만든다
        #   elementId(a1) < elementId(a2): (A,B) 와 (B,A) 중 하나만 남기고, 자기 자신(A,A)은 뺀다 (글자 비교라도 "한쪽만" 고르는 데는 충분)
        #   MERGE (a1)-[r:CO_PURCHASED]-(a2): 방향 없이 찾고, 없으면 만든다 (만들 때는 a1->a2 방향으로 저장된다)
        #   ON CREATE SET weight = 1 / ON MATCH SET weight + 1: 처음이면 1, 이미 있으면 1 증가 -> "함께 산 장바구니 수" = 가중치
        #   RETURN count(*): 처리한 (a1, a2) 행 수. 새로 만든 관계 수가 아니다 (기존 관계 +1 도 포함)
        # 주의: retail2kg.py 는 PURCHASED 날짜를 p.date 로 저장한다 (part2/retail2kg 의 "date: date(row.t_dat)" 확인).
        #       그렇다면 p.t_dat 는 모두 null 이 되어 고객의 "모든 구매" 가 한 장바구니로 묶인다 (같은 날 조건이 사라짐).
        #       내 DB 에서 MATCH ()-[p:PURCHASED]->() RETURN keys(p) LIMIT 1 로 확인해 보자
        # 주의: 같은 날 같은 상품을 두 번 산 경우 articles 에 중복이 들어가 그 쌍의 weight 가 더 크게 셀 수 있다 (collect(DISTINCT a) 가 아님)
        batch_query = """
        UNWIND $customerIds AS customerId
        MATCH (c:Customer)
        WHERE elementId(c) = customerId
        MATCH (c)-[p:PURCHASED]->(a:Article)
        WITH c, p.t_dat AS purchaseDate, collect(a) AS articles
        WHERE size(articles) >= 2
        WITH purchaseDate, articles
        UNWIND articles AS a1
        UNWIND articles AS a2
        WITH a1, a2
        WHERE elementId(a1) < elementId(a2)
        MERGE (a1)-[r:CO_PURCHASED]-(a2)
        ON CREATE SET r.weight = 1
        ON MATCH SET r.weight = r.weight + 1
        RETURN count(*) AS created
        """

        # 쿼리 매개변수는 키워드 인자로 넘긴다: customerIds=batch_ids -> 쿼리 안의 $customerIds
        # (문자열에 직접 끼워 넣지 않으므로 따옴표/주입 문제가 없다)
        batch_result = driver.execute_query(
            batch_query,
            customerIds=batch_ids,
            database_=NEO4J_DATABASE
        )
        # 값 if 조건 else 다른값: 조건식(삼항 연산자). 결과 행이 없으면 0
        created = batch_result.records[0]['created'] if batch_result.records else 0
        total_created += created

        print(f"  - 배치 {batch_num}/{total_batches} 완료 ({created:,}개 관계 처리)")

    print(f"  ✓ 임시 관계 생성 완료 (총 {total_created:,}개 처리)")

    # 최종 CO_PURCHASED 개수 (방향 있는 패턴 ()-[]->() 이라 각 관계를 한 번씩 센다)
    count_query = "MATCH ()-[r:CO_PURCHASED]->() RETURN count(r) AS total"
    result = driver.execute_query(count_query, database_=NEO4J_DATABASE)
    final_count = result.records[0]['total']
    print(f"\n  ✓ CO_PURCHASED 관계: {final_count:,}개")

    # Native Projection (UNDIRECTED + 가중치 포함)
    # CALL gds.graph.project(그래프이름, 노드 투영, 관계 투영)
    # [출처] Neo4j GDS 플러그인 프로시저 ("Native projection": 레이블/관계 타입 이름으로 고르는 방식)
    # [입력] 'retailBehaviorGraph': 메모리 그래프 이름
    #        'Article': Article 레이블 노드를 모두 넣는다 (CO_PURCHASED 가 없는 상품도 고립 노드로 들어간다)
    #        {CO_PURCHASED: {orientation: 'UNDIRECTED', properties: 'weight'}}:
    #          CO_PURCHASED 관계를 "방향 없음" 으로 읽고, weight 속성을 같이 싣는다
    # [반환] YIELD graphName, nodeCount, relationshipCount (그 밖에 projectMillis 등도 있다. graphdatascience 2.3 의 GraphProjectResult 로 확인)
    # [왜] UNDIRECTED: "함께 샀다" 에는 방향이 없다. GDS 의 Leiden 은 무방향 그래프를 요구한다.
    #      무방향으로 투영하면 관계 하나가 양쪽 방향으로 저장되어 relationshipCount 가 DB 개수의 약 2배로 나올 수 있다
    # 주의: 이름이 고정 글자라 graph_name 인자와 무관하다 (위 167줄 주의 참고)
    query = """
    CALL gds.graph.project(
      'retailBehaviorGraph',
      'Article',
      {
        CO_PURCHASED: {
          orientation: 'UNDIRECTED',
          properties: 'weight'
        }
      }
    )
    YIELD graphName, nodeCount, relationshipCount
    RETURN graphName, nodeCount, relationshipCount
    """

    result = driver.execute_query(query, database_=NEO4J_DATABASE)
    # Record 에서 열을 꺼내 보통 딕셔너리로 옮겨 담는다
    stats = {
        'graphName': result.records[0]['graphName'],
        'nodeCount': result.records[0]['nodeCount'],
        'relationshipCount': result.records[0]['relationshipCount']
    }

    print(f"\n✓ 그래프 '{graph_name}' 프로젝션 완료")
    print(f"  - 노드 수: {stats['nodeCount']:,}")
    print(f"  - 관계 수: {stats['relationshipCount']:,}")
    print(f"  - 관계 타입: UNDIRECTED (무방향)")

    return stats


# ============================================
# Leiden Community Detection
# ============================================

# [이 파일에서 정의] 메모리 그래프에 Leiden 을 돌리고 결과를 Article 노드 속성으로 쓴다 (이 파일의 핵심 2)
# [입력] write_property: 저장할 속성 이름, gamma: 해상도, min_community_size: 이보다 작은 커뮤니티는 결과에서 제외
# [반환] Leiden 결과 통계 Record
def run_leiden_on_customer_behavior(
    driver,
    graph_name: str = "retailBehaviorGraph",
    write_property: str = "behaviorCommunityId",
    gamma: float = 1.0,
    min_community_size: int = 5
):
    """
    고객 행동 기반 커뮤니티 탐지
    실제 구매 패턴으로 상품을 그룹핑
    """
    print("\n" + "=" * 60)
    print("[2] 고객 행동 기반 커뮤니티 탐지 (Leiden Algorithm)")
    print("=" * 60)
    print(f"\n알고리즘 설정:")
    print(f"  - Resolution (gamma): {gamma}")
    print(f"  - 최소 커뮤니티 크기: {min_community_size}개 상품 이상")
    print(f"  - 가중치 사용: weight")

    # CALL gds.leiden.write(그래프이름, {설정})
    # [출처] Neo4j GDS 플러그인 프로시저. write 모드 = 계산 결과를 DB 노드 속성에 저장
    # [입력] 설정 (기본값은 graphdatascience 2.3 의 leiden write 시그니처로 확인)
    #   writeProperty: 커뮤니티 번호를 저장할 노드 속성 이름 (여기서는 behaviorCommunityId)
    #   includeIntermediateCommunities: true 면 단계별 커뮤니티 번호를 리스트로 저장. false 면 마지막 단계 번호 하나 (기본 false)
    #   maxLevels: 합치기를 위로 몇 단계까지 할지 (기본 10)
    #   tolerance: 점수 변화가 이보다 작으면 수렴으로 보고 멈춤 (기본 0.0001)
    #   gamma: 해상도(resolution). 클수록 작은 커뮤니티 여러 개, 작을수록 큰 커뮤니티 몇 개 (기본 1.0)
    #   minCommunitySize: 이 크기 이상인 커뮤니티의 노드만 결과에 포함 (기본은 제한 없음)
    #   relationshipWeightProperty: 'weight' -> 함께 산 횟수가 많은 쌍을 더 강한 연결로 본다 (없으면 모든 연결이 같은 무게)
    # [반환] 1행. 열: communityCount, modularity, modularities, ranLevels, didConverge, nodeCount, nodePropertiesWritten,
    #        communityDistribution, 각종 Millis, configuration (graphdatascience 2.3 의 LeidenWriteResult 로 확인)
    # [왜] write 로 저장해 두면 GDS 없이 일반 Cypher (WHERE a.behaviorCommunityId = ...) 로 커뮤니티를 쓸 수 있다
    # f-string 안의 {{ }} 는 Cypher 의 글자 { } (설정 맵), {graph_name} {gamma} 등은 파이썬 값이 들어가는 자리
    # YIELD 를 안 쓰고 CALL 만 단독으로 쓰면 모든 반환 열이 그대로 결과가 된다
    # 주의: minCommunitySize 로 걸러진 작은 커뮤니티의 노드에는 속성이 써지지 않을 수 있다. 그 노드에 지난 실행의
    #       behaviorCommunityId 가 남아 있으면 오래된 값이 섞일 수 있다 (재실행 전에 속성을 지우는 단계가 없다)
    # 주의: randomSeed 를 주지 않아 실행할 때마다 커뮤니티 번호와 구성이 조금씩 달라질 수 있다
    query = f"""
    CALL gds.leiden.write('{graph_name}', {{
        writeProperty: '{write_property}',
        includeIntermediateCommunities: false,
        maxLevels: 10,
        tolerance: 0.0001,
        gamma: {gamma},
        minCommunitySize: {min_community_size},
        relationshipWeightProperty: 'weight'
    }})
    """

    result = driver.execute_query(query, database_=NEO4J_DATABASE)
    # 결과는 1행. Record 를 그대로 돌려준다 (stats['communityCount'] 처럼 꺼낸다)
    stats = result.records[0]

    print(f"\n✓ Leiden 알고리즘 실행 완료")
    print(f"  - 탐지된 커뮤니티 수: {stats['communityCount']}")
    # {값:.4f}: 소수점 넷째 자리까지
    print(f"  - 모듈성 점수: {stats['modularity']:.4f}")
    # ranLevels: 실제로 몇 단계까지 합쳤는지
    print(f"  - 계층 수준: {stats['ranLevels']}")
    print(f"  - 속성 '{write_property}' 저장 완료")

    return stats

# ============================================
# 커뮤니티 분석
# ============================================

# [이 파일에서 정의] 커뮤니티마다 어떤 스타일/색이 섞여 있는지 확인 출력 (결과 검증용)
def analyze_behavior_communities(driver):
    """고객 행동 기반 커뮤니티 분석 (PURCHASED 관계)"""
    print("\n" + "=" * 60)
    print("[3] 구매 패턴 커뮤니티 분석")
    print("=" * 60)

    # 커뮤니티 번호별로 묶어 (스타일 목록, 색 목록, 샘플 상품 5개, 상품 수) 를 만든다
    #   collect(DISTINCT x): 중복 없이 리스트로 모으기 / collect(a)[..5]: 리스트 앞 5개 (슬라이스)
    #   [a IN appearances WHERE a IS NOT NULL]: Cypher 의 리스트 컴프리헨션 (null 빼기)
    #   스타일이 2종 이상인 커뮤니티 중 스타일 종류가 많은 순서로 5개 = "교차 판매(cross-sell)" 후보
    # 주의: 커뮤니티를 만들 때 쓴 변수 a 를 컴프리헨션 안에서 다시 a 로 쓴다. Cypher 에서는 컴프리헨션 안쪽 이름이 따로라 동작은 한다
    cross_sell_query = """
    MATCH (a:Article)
    WHERE a.behaviorCommunityId IS NOT NULL
    WITH a.behaviorCommunityId AS communityId,
         collect(DISTINCT a.graphical_appearance_name) AS appearances,
         collect(DISTINCT a.perceived_colour_master_name) AS colours,
         collect(a)[..5] AS samples,
         count(a) AS articleCount
    WHERE size([a IN appearances WHERE a IS NOT NULL]) >= 2
    RETURN communityId, appearances, colours, samples, articleCount
    ORDER BY size(appearances) DESC
    LIMIT 5
    """

    result = driver.execute_query(cross_sell_query, database_=NEO4J_DATABASE)

    for record in result.records:
        comm_id = record['communityId']
        # [a for a in 리스트 if a]: 파이썬 리스트 컴프리헨션 + 조건. None 이나 빈 글자를 뺀다
        appearances = [a for a in record['appearances'] if a]
        colours = [c for c in record['colours'] if c]
        samples = record['samples']
        article_count = record['articleCount']

        # ', '.join(리스트[:3]): 앞 3개를 쉼표로 이어 한 줄로
        print(f"\nCommunity {comm_id}: {article_count:,}개 상품, {len(appearances)}개 스타일 ({', '.join(appearances[:3])})")
        print(f"  주요 색상: {', '.join(colours[:5])}")
        # samples 의 각 원소는 neo4j Node 객체
        for article in samples[:3]:
            # Node.get('속성', 기본값): 속성이 없으면 기본값. [출처] 외부 라이브러리 neo4j (Node 는 딕셔너리처럼 쓸 수 있다)
            name = article.get('prod_name', 'N/A')
            appearance = article.get('graphical_appearance_name', 'N/A')
            colour = article.get('perceived_colour_master_name', 'N/A')
            print(f"  • {name} ({appearance}, {colour})")


# ============================================
# 메인 함수
# ============================================

# [이 파일에서 정의] 확인 -> 통계 -> 규모 확인 -> CO_PURCHASED + 투영 -> Leiden -> 분석
def main():
    print("=" * 60)
    print("H&M Retail 고객 구매 행동 기반 커뮤니티 탐지")
    print("=" * 60)

    driver = create_neo4j_connection()

    # try/finally: 중간에 에러가 나거나 sys.exit 를 해도 finally 의 driver.close() 는 꼭 실행된다
    try:
        # GDS 확인
        if not verify_gds_available(driver):
            # sys.exit(1): SystemExit 예외를 던져 프로그램을 끝낸다 (1 = 실패). 예외라서 finally 는 실행된다
            sys.exit(1)

        # 데이터 확인
        if not check_retail_data_exists(driver):
            sys.exit(1)

        # 데이터 통계
        print_data_statistics(driver)

        # 구매 데이터 규모 확인
        data_info = check_purchase_data_size(driver)

        # 규모에 따라 2회 또는 5회 이상 산 고객만 사용 (함수 기본값 10 은 여기서는 쓰이지 않는다)
        project_customer_behavior_graph(
            driver,
            min_purchases=data_info['recommended_min_purchases']
        )

        # gamma=1.0, 최소 크기 5 로 Leiden 실행
        run_leiden_on_customer_behavior(
            driver,
            gamma=1.0,
            min_community_size=5
        )

        # 커뮤니티 내용 분석
        analyze_behavior_communities(driver)

        print("\n" + "=" * 60)
        print("커뮤니티 탐지 완료!")
        print("=" * 60)
    finally:
        driver.close()


# 이 파일을 직접 실행할 때만 main(). 다른 파일이 import 하면 실행되지 않는다
if __name__ == "__main__":
    main()
