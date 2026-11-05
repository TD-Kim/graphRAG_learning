"""[1단계: 읽기] retail_community_graphrag.py (질문 -> 키워드 -> 상품 -> 그 상품의 커뮤니티 -> LLM 추천) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
openai 설명은 설치 소스(openai 1.109.1, requirements.txt 기준)로 확인했다. neo4j-graphrag 는 이 파일에서 쓰지 않는다.

이 파일의 핵심 개념: 커뮤니티 기반 검색(추천)
  - 앞 파일(community_detection_retail.py)이 Leiden 으로 "고객들이 함께 사는 상품 묶음(커뮤니티)" 을 찾아
    각 Article 노드에 behaviorCommunityId 를 적어 두었다.
  - 여기서는 질문과 맞는 상품을 하나 찾고, "그 상품과 같은 커뮤니티의 상품들" 을 추천 후보로 쓴다.
    -> 질문에 나오지 않은 상품도 "같이 사면 좋은 상품" 으로 추천할 수 있다 (비슷한 것이 아니라 함께 묶이는 것).
  - 커뮤니티 요약: 커뮤니티 하나를 "어떤 스타일, 어떤 색이 들어 있나" 같은 짧은 글로 정리한 것.
    Microsoft GraphRAG 는 LLM 으로 커뮤니티마다 요약문을 미리 써 두지만, 이 파일은 Cypher 집계(analyze_community)로
    스타일/색 목록을 그때그때 만들어 LLM 에 넘기는 단순한 버전이다.

흐름 요약 (LLM 을 두 번 부른다)
  질문 "겨울 코트 추천해줘"
    -> [1] extract_search_keywords: gpt-4o-mini 로 영어 키워드 최대 3개 (coat, jacket, pablo)
    -> [1] find_similar_products: prod_name CONTAINS 키워드 (실패하면 설명/외관으로) + 커뮤니티 크기 필터 -> 상품 3개
    -> 첫 번째 상품의 behaviorCommunityId 선택
    -> [2] search_in_community: 그 커뮤니티 상품 20개
    -> [3] analyze_community: 그 커뮤니티의 스타일/색 목록 (간단한 커뮤니티 요약)
    -> [4] build_recommendation_context: 위 결과를 마크다운 글로
    -> [5] generate_recommendation: gpt-4o 가 추천 답변 작성

읽는 순서 권장: main -> retail_graphrag_query -> find_similar_products -> extract_search_keywords
               -> search_in_community -> analyze_community -> build_recommendation_context -> generate_recommendation
실행 위치: part3/community_search  ->  python learning/step1_retail_community_graphrag_annotated.py  (대화형, q 로 종료)
전제: community_detection_retail.py 를 먼저 실행해 behaviorCommunityId 가 있어야 한다. .env 에 NEO4J_*, OPENAI_API_KEY.
"""

# [출처] 표준 라이브러리. os.getenv
import os
# [출처] 표준 라이브러리. 주의: 이 파일에서는 sys 를 쓰지 않는다
import sys
# [출처] 표준 라이브러리 typing. 타입 힌트용 (List[str] = 글자 리스트, Optional = 값이 없을 수도 있음)
from typing import List, Dict, Any, Optional

# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 openai (OpenAI 공식 파이썬 SDK)
# 이 파일은 openai.OpenAI() 클라이언트 객체를 만들지 않고 "모듈 수준" 함수 openai.chat.completions.create 를 바로 쓴다.
# 소스 확인: openai.chat 은 처음 쓰일 때 모듈 전역 클라이언트를 한 번 만든다 (_load_client).
#   그때 openai.api_key 가 있으면 그것을, None 이면 환경변수 OPENAI_API_KEY 를 쓴다
import openai

# .env -> 환경변수
load_dotenv()

# 주의: NEO4J_USERNAME(사용자 이름)을 DB 이름으로 쓴다. 둘 다 "neo4j" 인 기본 설정에서만 우연히 맞는다
# (원래 의도는 NEO4J_DATABASE 였을 가능성이 크다)
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")


# ============================================
# 유틸리티 함수
# ============================================

# [이 파일에서 정의] 드라이버 생성 [반환] Driver
# 주의: verify_connectivity 를 하지 않아서, 실제로 접속하지 않았는데도 "연결 성공" 을 출력한다 (첫 쿼리에서 에러가 난다)
def create_neo4j_connection():
    """Neo4j 데이터베이스 연결 생성"""
    uri = os.getenv('NEO4J_URI')
    username = os.getenv('NEO4J_USERNAME')
    password = os.getenv('NEO4J_PASSWORD')

    driver = GraphDatabase.driver(uri, auth=(username, password))
    print(f"Neo4j 연결 성공: {uri}")
    return driver


# [이 파일에서 정의] openai 모듈 전역 api_key 를 설정
# 사실 load_dotenv 로 OPENAI_API_KEY 가 이미 환경변수에 있으므로, 이 줄이 없어도 openai 가 알아서 읽는다 (소스 확인)
def setup_openai():
    """OpenAI API 설정"""
    api_key = os.getenv('OPENAI_API_KEY')

    # openai.api_key = 값: 모듈 변수에 키를 넣는다. 키가 None 이어도 여기서는 에러가 안 나고 첫 API 호출 때 난다
    openai.api_key = api_key
    print("OpenAI API 설정 완료")


# [이 파일에서 정의] behaviorCommunityId 가 있는 Article 이 하나라도 있는지 확인 [반환] True/False
def check_community_exists(driver) -> bool:
    """behaviorCommunityId 속성 존재 확인"""
    # Cypher 여러 줄 문자열. IS NOT NULL: 속성이 있는 노드만
    query = """
    MATCH (a:Article)
    WHERE a.behaviorCommunityId IS NOT NULL
    RETURN count(a) AS count
    LIMIT 1
    """

    result = driver.execute_query(query, database_=NEO4J_DATABASE)

    if not result.records or result.records[0]['count'] == 0:
        print("먼저 community_detection_retail.py를 실행해주세요.")
        return False

    print("behaviorCommunityId 속성 확인 완료")
    return True


# ============================================
# Step 1: 초기 상품 찾기
# ============================================

# [이 파일에서 정의] 한국어 질문 -> 상품명 검색용 영어 키워드 (최대 3개)
# [반환] ['coat', 'jacket', 'pablo'] 같은 리스트
# [왜] 데이터의 상품명(prod_name)은 영어이고 "Theron", "Pablo coat" 처럼 고유한 이름이 많다.
#      사용자는 "후드티" 라고 묻기 때문에, LLM 에게 실제 상품명 예시를 보여 주고 데이터에 있을 법한 단어로 바꾸게 한다
def extract_search_keywords(question: str) -> List[str]:
    """
    질문에서 검색 키워드 추출

    OpenAI GPT로 질문을 분석하여 H&M 상품 검색에 적합한 키워드 추출
    """
    # try/except: API 오류 등이 나면 except 로
    try:
        # openai.chat.completions.create(model=..., messages=[...], temperature=..., max_tokens=...)
        # [출처] 외부 라이브러리 openai (Chat Completions API)
        # [입력] model: 모델 이름 ("gpt-4o-mini": 싸고 빠른 모델, 키워드 뽑기 정도에 충분)
        #        messages: 대화 목록. 각 원소는 {"role": "system"|"user"|"assistant", "content": 글}
        #          system = 역할/규칙 지시, user = 사용자 입력
        #        temperature: 0~2. 낮을수록 같은 입력에 같은 답 (0.3 = 조금만 다양하게)
        #        max_tokens: 답의 최대 길이(토큰 수). 키워드 몇 개라 50 이면 충분
        # [반환] ChatCompletion 객체. .choices[0].message.content 에 답 글, .usage.total_tokens 에 사용 토큰 수
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    # system 프롬프트: 실제 상품명 예시 + 규칙 + 출력 형식("쉼표로 구분") + 질문->키워드 예시(few-shot)
                    # 출력 형식을 쉼표로 정해 두어야 아래 split(',') 로 나눌 수 있다
                    "content": """H&M 상품 검색을 위한 키워드 추출 전문가입니다.
사용자 질문에서 상품명(prod_name)과 매칭될 **구체적인** 영문 키워드를 추출하세요.

실제 H&M 데이터베이스 상품명 예시:
- 후드티/재킷: "Theron", "Mr Harrington w/hood", "Kevin softshell jacket", "Freja Coat", "Pablo coat"
- 청바지: "6DENIM Jeggings", "6DENIM Skinny", "6DENIM+ Jacket oversized"
- 스포츠: "Karin padded sport bra", "Speedy tee", "CINDY tights", "SUPREME RW tights"
- 외관: Solid (단색), Stripe, Lace, Pattern, Denim

중요 규칙:
1. 상품명에 실제로 나타나는 구체적인 단어 사용 (예: "jacket", "coat", "theron", "denim")
2. 너무 일반적인 단어 피하기 (❌ "top", "shirt", "clothes" 등)
3. 한국어를 영어로 정확히 번역 (후드티 → hoodie, theron / 청바지 → denim, jegging)

출력 형식: 쉼표로 구분된 영문 키워드 (최대 3개)
예시:
"스포츠 의류" → sport, bra, tights
"겨울 후드티" → theron, jacket, hoodie
"겨울 코트" → coat, jacket, pablo
"청바지" → denim, jegging, skinny
"운동 레깅스" → tights, cindy, supreme
"드레스" → dress"""
                },
                {
                    "role": "user",
                    # f-string 으로 질문을 끼워 넣는다. \n\n 은 줄바꿈 두 번
                    "content": f"질문: {question}\n\n검색 키워드:"
                }
            ],
            temperature=0.3,
            max_tokens=50
        )

        # .strip(): 앞뒤 공백/줄바꿈 제거
        keywords_text = response.choices[0].message.content.strip()
        # 글.split(','): 쉼표로 잘라 리스트로. [k.strip() for k in ... if k.strip()]: 각 조각의 공백을 지우고 빈 조각은 버린다
        keywords = [k.strip() for k in keywords_text.split(',') if k.strip()]
        # 리스트[:3]: 앞 3개만 (LLM 이 더 많이 내도 3개로 자른다)
        return keywords[:3]  # 최대 3개

    # 주의: except 에서 return 이 없어서 실패하면 None 을 돌려준다.
    #       호출하는 쪽(143줄)의 ', '.join(keywords) 가 None 에 대해 TypeError 로 터진다. return [] 가 더 안전하다
    except Exception as e:
        print(f"키워드 추출 실패: {e}")


# [이 파일에서 정의] 키워드로 상품을 찾고, 그 상품이 속한 커뮤니티 크기가 적당한 것만 고른다
# [입력] top_k: 돌려줄 상품 수, min/max_community_size: 허용할 커뮤니티 크기 범위
# [반환] [{'article_id', 'name', 'appearance', 'colour', 'communityId', 'communitySize'}, ...] (못 찾으면 [])
# [왜] 커뮤니티가 너무 작으면 추천할 상품이 없고, 너무 크면 "거의 다 한 묶음" 이라 의미가 없다
# """...""" 독스트링의 Args/Returns 는 Google 스타일 설명 형식
# 주의: 독스트링의 "전체 텍스트 검색" 은 Neo4j 의 full-text 인덱스가 아니라 CONTAINS 부분 일치다
def find_similar_products(
    driver,
    question: str,
    top_k: int = 3,
    min_community_size: int = 50,
    max_community_size: int = 5000
) -> List[Dict[str, Any]]:
    """
    질문과 관련된 상품 찾기 (개선된 버전)

    GPT로 키워드를 추출하고, 유연한 전체 텍스트 검색 수행
    적절한 크기의 커뮤니티만 선택하여 더 정확한 추천 제공

    Args:
        driver: Neo4j driver
        question: 사용자 질문
        top_k: 반환할 상품 개수
        min_community_size: 최소 커뮤니티 크기 (기본: 50)
        max_community_size: 최대 커뮤니티 크기 (기본: 5000)

    Returns:
        찾은 상품 리스트
    """
    print("\n" + "=" * 60)
    print("[Step 1] 질문과 관련된 상품 찾기")
    print("=" * 60)

    # GPT로 검색 키워드 추출
    # LLM 호출 1번째 (키워드 추출)
    keywords = extract_search_keywords(question)

    print(f"\n질문: '{question}'")
    # 주의: keywords 가 None 이면 여기서 TypeError (108줄 참고)
    print(f"추출된 키워드: {', '.join(keywords)}")

    # 여러 키워드로 검색 시도
    # 키워드를 하나씩 시도하고, 찾는 순간 return 으로 끝낸다 (첫 키워드가 가장 우선)
    for keyword in keywords:
        # Neo4j 쿼리: prod_name 우선 검색 (가장 정확)
        # 상품명 검색 Cypher
        #   toLower(...) CONTAINS toLower($keyword): 대소문자 무시 부분 일치 (인덱스를 못 써서 Article 전체를 훑는다)
        #   MATCH (c:Article {behaviorCommunityId: a.behaviorCommunityId}) + count(c): 찾은 상품마다 같은 커뮤니티 상품 수를 센다 = 커뮤니티 크기
        #   WHERE 크기 범위 / ORDER BY communitySize ASC: 작은(=더 구체적인) 커뮤니티의 상품부터
        #   // 는 Cypher 의 한 줄 주석
        # 주의: 찾은 상품마다 커뮤니티 전체를 다시 센다. 같은 커뮤니티 상품이 여러 개면 같은 계산을 반복하고,
        #       behaviorCommunityId 인덱스가 없으면 느릴 수 있다
        query = """
        MATCH (a:Article)
        WHERE a.behaviorCommunityId IS NOT NULL
          AND toLower(a.prod_name) CONTAINS toLower($keyword)
        WITH a
        // 커뮤니티 크기 계산
        MATCH (c:Article {behaviorCommunityId: a.behaviorCommunityId})
        WITH a, count(c) AS communitySize
        WHERE communitySize >= $min_size AND communitySize <= $max_size
        RETURN DISTINCT a.article_id AS article_id,
               a.prod_name AS name,
               a.graphical_appearance_name AS appearance,
               a.perceived_colour_master_name AS colour,
               a.behaviorCommunityId AS communityId,
               communitySize
        ORDER BY communitySize ASC
        LIMIT $top_k
        """

        # $keyword, $top_k, $min_size, $max_size 를 키워드 인자로 채운다
        result = driver.execute_query(
            query,
            keyword=keyword,
            top_k=top_k,
            min_size=min_community_size,
            max_size=max_community_size,
            database_=NEO4J_DATABASE
        )

        # prod_name에서 찾으면 바로 반환
        # 결과가 하나라도 있으면 딕셔너리 리스트로 바꿔 바로 돌려준다
        if result.records:
            products = []
            for record in result.records:
                products.append({
                    'article_id': record['article_id'],
                    'name': record['name'],
                    'appearance': record['appearance'],
                    'colour': record['colour'],
                    'communityId': record['communityId'],
                    'communitySize': record['communitySize']
                })

            print(f"'{keyword}' 키워드로 {len(products)}개 상품 발견 (상품명 매칭):")
            # enumerate(리스트, 1): (번호, 값) 쌍을 1번부터 매겨 준다
            for i, prod in enumerate(products, 1):
                # 값 or 'N/A': 값이 None/빈 글자면 'N/A' (or 는 앞이 거짓이면 뒤를 돌려준다)
                appearance = prod['appearance'] or 'N/A'
                colour = prod['colour'] or 'N/A'
                size = prod['communitySize']
                print(f"  {i}. {prod['name']} ({appearance}, {colour}) - Community {prod['communityId']} (크기: {size:,}개)")

            return products

        # prod_name에서 못 찾으면 detail_desc도 검색 (보조)
        # fallback(대안) 검색: 상품명에 없으면 상세 설명(detail_desc)이나 외관(graphical_appearance_name)에서 찾는다
        # 나머지 구조는 위 쿼리와 같다
        # 주의: 위와 거의 같은 코드가 두 번 반복된다. WHERE 조건만 다른 함수 하나로 묶을 수 있다
        fallback_query = """
        MATCH (a:Article)
        WHERE a.behaviorCommunityId IS NOT NULL
          AND (
            toLower(a.detail_desc) CONTAINS toLower($keyword) OR
            toLower(a.graphical_appearance_name) CONTAINS toLower($keyword)
          )
        WITH a
        MATCH (c:Article {behaviorCommunityId: a.behaviorCommunityId})
        WITH a, count(c) AS communitySize
        WHERE communitySize >= $min_size AND communitySize <= $max_size
        RETURN DISTINCT a.article_id AS article_id,
               a.prod_name AS name,
               a.graphical_appearance_name AS appearance,
               a.perceived_colour_master_name AS colour,
               a.behaviorCommunityId AS communityId,
               communitySize
        ORDER BY communitySize ASC
        LIMIT $top_k
        """

        result = driver.execute_query(
            fallback_query,
            keyword=keyword,
            top_k=top_k,
            min_size=min_community_size,
            max_size=max_community_size,
            database_=NEO4J_DATABASE
        )

        if result.records:
            products = []
            for record in result.records:
                products.append({
                    'article_id': record['article_id'],
                    'name': record['name'],
                    'appearance': record['appearance'],
                    'colour': record['colour'],
                    'communityId': record['communityId'],
                    'communitySize': record['communitySize']
                })

            print(f"'{keyword}' 키워드로 {len(products)}개 상품 발견 (설명 매칭):")
            for i, prod in enumerate(products, 1):
                appearance = prod['appearance'] or 'N/A'
                colour = prod['colour'] or 'N/A'
                size = prod['communitySize']
                print(f"  {i}. {prod['name']} ({appearance}, {colour}) - Community {prod['communityId']} (크기: {size:,}개)")

            return products

    # 모든 키워드로 못 찾으면 빈 리스트
    return []


# ============================================
# Step 2: 커뮤니티 내 상품 검색
# ============================================

# [이 파일에서 정의] 커뮤니티 번호로 그 커뮤니티 상품을 최대 max_results 개 가져온다
# [반환] [{'article_id', 'name', 'appearance', 'colour', 'description'}, ...]
# 주의: ORDER BY 가 없어서 "어떤 20개" 가 나올지는 DB 저장 순서에 달려 있다 (질문과의 관련도 순이 아니다)
def search_in_community(driver, community_id: int, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    특정 커뮤니티에 속한 상품 검색

    같은 커뮤니티 = 비슷한 카테고리/스타일의 상품들

    Args:
        driver: Neo4j driver
        community_id: 커뮤니티 ID
        max_results: 최대 결과 개수

    Returns:
        커뮤니티 내 상품 리스트
    """
    print("\n" + "=" * 60)
    print(f"[Step 2] Community {community_id} 내부 검색")
    print("=" * 60)

    # $community_id, $max_results 매개변수. LIMIT 에도 매개변수를 쓸 수 있다
    query = """
    MATCH (a:Article)
    WHERE a.behaviorCommunityId = $community_id
    RETURN a.article_id AS article_id,
           a.prod_name AS name,
           a.graphical_appearance_name AS appearance,
           a.perceived_colour_master_name AS colour,
           a.detail_desc AS description
    LIMIT $max_results
    """

    result = driver.execute_query(
        query,
        community_id=community_id,
        max_results=max_results,
        database_=NEO4J_DATABASE
    )

    products = []
    for record in result.records:
        products.append({
            'article_id': record['article_id'],
            'name': record['name'],
            'appearance': record['appearance'],
            'colour': record['colour'],
            'description': record['description']
        })

    print(f"\nCommunity {community_id}에서 {len(products)}개 상품 발견")

    # 샘플 출력
    print("\n샘플 상품:")
    # products[:5]: 화면에는 앞 5개만
    for i, prod in enumerate(products[:5], 1):
        appearance = prod['appearance'] or 'N/A'
        colour = prod['colour'] or 'N/A'
        print(f"  {i}. {prod['name']} ({appearance}, {colour})")

    return products


# ============================================
# Step 3: 커뮤니티 분석
# ============================================

# [이 파일에서 정의] 커뮤니티 하나를 "스타일 목록 + 색 목록 + 상품 수" 로 요약한 글을 만든다 (간단한 커뮤니티 요약)
# [반환] "Community 12 분석 (총 340개 상품):\n\n주요 스타일: Solid, Stripe, ...\n주요 색상: Black, Blue, ..."
# [왜] LLM 이 "이 묶음은 어떤 성격인가" 를 알아야 추천 이유를 설명할 수 있다
# 주의: "주요" 스타일/색이라고 하지만 빈도순이 아니라 collect 로 처음 모인 5개다.
#       빈도순으로 하려면 Cypher 에서 값별 count 를 구해 ORDER BY 해야 한다
def analyze_community(driver, community_id: int) -> str:
    """
    커뮤니티의 주요 특징 분석

    어떤 부서, 카테고리, 색상이 많은지 분석하여
    커뮤니티의 특성을 파악

    Args:
        driver: Neo4j driver
        community_id: 커뮤니티 ID

    Returns:
        커뮤니티 분석 문자열
    """
    print("\n" + "=" * 60)
    print(f"[Step 3] Community {community_id} 분석")
    print("=" * 60)

    # 커뮤니티 구성 분석
    # WITH 에 집계만 있으면 전체가 한 묶음 -> 결과는 항상 1행 (상품이 0개여도 빈 리스트, 0 으로 1행)
    # 그래서 아래 "if not result.records" 는 사실상 참이 되지 않는다
    query = """
    MATCH (a:Article)
    WHERE a.behaviorCommunityId = $community_id
    WITH
        collect(DISTINCT a.graphical_appearance_name) AS appearances,
        collect(DISTINCT a.perceived_colour_master_name) AS colours,
        count(a) AS total_products
    RETURN appearances, colours, total_products
    """

    result = driver.execute_query(
        query,
        community_id=community_id,
        database_=NEO4J_DATABASE
    )

    if not result.records:
        return f"Community {community_id}: 데이터 없음"

    record = result.records[0]
    # None 빼고 앞 5개
    appearances = [a for a in record['appearances'] if a][:5]
    colours = [c for c in record['colours'] if c][:5]
    total = record['total_products']

    # 분석 텍스트 구성
    # 리스트에 줄을 모았다가 마지막에 "\n".join 으로 잇는다
    analysis_parts = [f"Community {community_id} 분석 (총 {total:,}개 상품):"]

    if appearances:
        analysis_parts.append(f"\n주요 스타일: {', '.join(appearances)}")

    if colours:
        analysis_parts.append(f"주요 색상: {', '.join(colours)}")

    analysis = "\n".join(analysis_parts)
    print(f"\n{analysis}")

    return analysis


# ============================================
# Step 4: 추천 컨텍스트 구성
# ============================================

# [이 파일에서 정의] LLM 에 줄 "상품 정보" 글을 만든다 (마크다운 제목 #, ## 사용)
# [반환] "# 커뮤니티 분석 ... # 검색된 상품 ... ## 질문과 직접 관련된 상품: ... ## 같은 카테고리의 다른 상품 (추천 후보): ..."
# 주의: question 인자는 받기만 하고 쓰지 않는다
def build_recommendation_context(
    question: str,
    initial_products: List[Dict[str, Any]],
    community_products: List[Dict[str, Any]],
    community_analysis: str
) -> str:
    """
    상품 추천을 위한 컨텍스트 구성

    Args:
        question: 사용자 질문
        initial_products: 초기 검색 상품
        community_products: 커뮤니티 내 상품
        community_analysis: 커뮤니티 분석

    Returns:
        포맷된 컨텍스트
    """
    context_parts = [
        "# 커뮤니티 분석",
        community_analysis,
        "",
        "# 검색된 상품",
        ""
    ]

    # 초기 검색 상품
    context_parts.append("## 질문과 직접 관련된 상품:")
    for i, prod in enumerate(initial_products[:3], 1):
        # dict.get(키, 기본값): 키가 없을 때만 기본값.
        # 주의: 키는 있고 값이 None 이면 None 이 그대로 나와 "None" 글자가 들어간다 (위 191줄처럼 "or 'N/A'" 가 더 맞다)
        appearance = prod.get('appearance', 'N/A')
        colour = prod.get('colour', 'N/A')
        context_parts.append(f"{i}. {prod['name']} - {appearance}, {colour}")
    context_parts.append("")

    # 커뮤니티 내 추천 상품
    context_parts.append("## 같은 카테고리의 다른 상품 (추천 후보):")
    # 커뮤니티 상품은 앞 10개만 컨텍스트에 넣는다 (20개를 가져왔지만 프롬프트 길이를 줄이려고)
    # 주의: 질문과 직접 관련된 상품이 커뮤니티 목록에 또 나올 수 있다 (중복 제거 없음)
    for i, prod in enumerate(community_products[:10], 1):
        name = prod.get('name', 'N/A')
        appearance = prod.get('appearance', 'N/A')
        colour = prod.get('colour', '')
        if colour:
            context_parts.append(f"{i}. {name} ({appearance}, {colour})")
        else:
            context_parts.append(f"{i}. {name} ({appearance})")

    return "\n".join(context_parts)


# ============================================
# Step 5: LLM 추천 생성
# ============================================

# [이 파일에서 정의] 컨텍스트 + 질문으로 gpt-4o 가 추천 답변을 쓴다 (LLM 호출 2번째)
# [반환] 답변 글 (실패하면 "추천을 생성할 수 없습니다.")
def generate_recommendation(question: str, context: str) -> str:
    """
    OpenAI GPT로 상품 추천 생성

    Args:
        question: 사용자 질문
        context: 상품 컨텍스트

    Returns:
        추천 답변
    """
    print("\n" + "=" * 60)
    # 주의: 화면 표시는 [Step 4] 지만 파이프라인 순서로는 5단계다 (출력 문구만의 차이)
    print("[Step 4] AI 추천 생성")
    print("=" * 60)

    # system 프롬프트: 역할(패션 어드바이저) + 답변 구조([메인 추천] / [같은 커뮤니티의 다른 추천])
    # "같은 커뮤니티 상품은 직접 관련 없어도 언급" 하게 해서 커뮤니티 기반 추천이 답변에 드러나게 한다
    system_prompt = """당신은 H&M 패션 전문 어드바이저입니다.
커뮤니티 분석 결과와 상품 목록을 바탕으로 고객에게 적합한 상품을 추천해주세요.

추천 답변은 다음 구조로 작성해주세요:

**[메인 추천]**
1. 고객의 질문에 직접 관련된 상품 2-3개를 구체적으로 추천
2. 각 상품의 이름, 특징, 왜 좋은지 간단히 설명
3. 친근하고 도움이 되는 톤으로 작성

**[같은 커뮤니티의 다른 추천]**
4. 메인 추천과 함께 구매하면 좋은 상품이나 같은 카테고리의 다른 스타일 상품 2-3개 소개
5. 직접적으로 관련이 없어도 같은 커뮤니티 내의 상품이라면 언급
6. "함께 보면 좋은 상품", "이런 스타일도 있어요" 등의 표현 사용

커뮤니티 내 다양한 상품을 적극 활용하여 고객에게 더 많은 선택지를 제공하세요.
"""

    # user 프롬프트: 질문 + 컨텍스트 글 (f-string 으로 끼워 넣기)
    user_prompt = f"""고객 질문: {question}

상품 정보:
{context}

위 정보를 바탕으로 고객에게 적합한 상품을 추천해주세요.
"""

    try:
        # Chat Completions 호출. 여기는 gpt-4o (더 좋은 모델), temperature 0.7 (추천 문장은 조금 다양해도 된다), 최대 800 토큰
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=800
        )

        recommendation = response.choices[0].message.content
        # response.usage.total_tokens: 이번 호출에 쓴 입력+출력 토큰 수 (비용 확인용)
        print(f"\n추천 생성 완료 ({response.usage.total_tokens} tokens)")
        return recommendation

    except Exception as e:
        print(f"\n추천 생성 실패: {e}")
        return "추천을 생성할 수 없습니다."


# ============================================
# 전체 파이프라인
# ============================================

# [이 파일에서 정의] 전체 파이프라인 (확인 -> 1 상품 -> 2 커뮤니티 상품 -> 3 커뮤니티 분석 -> 4 컨텍스트 -> 5 답변)
# [입력] min_community_size 기본값 5 (find_similar_products 의 기본값 50 보다 작게 덮어써서 넘긴다)
# [반환] {'question', 'recommendation', 'communityId', 'communitySize', 'products', 'context'}
# 주의: 매 질문마다 check_community_exists 쿼리를 다시 실행한다 (main 에서 한 번만 해도 된다)
def retail_graphrag_query(
    driver,
    question: str,
    min_community_size: int = 5,
    max_community_size: int = 5000
) -> Dict[str, Any]:
    """
    커뮤니티 기반 상품 추천 전체 파이프라인

    Args:
        driver: Neo4j driver
        question: 사용자 질문
        min_community_size: 최소 커뮤니티 크기 (기본: 5)
        max_community_size: 최대 커뮤니티 크기 (기본: 5000)

    Returns:
        추천 결과 딕셔너리
    """
    print("\n" + "=" * 70)
    print("Community-based Product Recommendation")
    print("=" * 70)

    # 0. behaviorCommunityId 확인
    # 커뮤니티가 없으면 결과 딕셔너리 모양을 맞춰서 안내 문구를 돌려준다 (호출하는 쪽이 같은 키로 출력할 수 있게)
    if not check_community_exists(driver):
        return {
            'question': question,
            'recommendation': 'behaviorCommunityId 속성이 없습니다. community_detection_retail.py를 먼저 실행해주세요.',
            'communityId': None,
            'products': []
        }

    # Step 1: 관련 상품 찾기 (커뮤니티 크기 필터링 적용)
    initial_products = find_similar_products(
        driver,
        question,
        top_k=3,
        min_community_size=min_community_size,
        max_community_size=max_community_size
    )
    if not initial_products:
        return {
            'question': question,
            # {min_community_size:,}: 숫자에 천 단위 쉼표
            'recommendation': f'적절한 크기({min_community_size:,}~{max_community_size:,}개)의 커뮤니티에서 관련 상품을 찾을 수 없습니다. 다른 키워드로 시도하거나 크기 범위를 조정해보세요.',
            'communityId': None,
            'products': []
        }

    # 첫 번째 상품의 커뮤니티 사용
    # 첫 번째(가장 작은 커뮤니티의) 상품의 커뮤니티만 쓴다. 상품 2, 3 번의 커뮤니티는 쓰지 않는다
    community_id = initial_products[0]['communityId']
    community_size = initial_products[0]['communitySize']
    print(f"\n선택된 커뮤니티: {community_id} (크기: {community_size:,}개)")

    # Step 2: 커뮤니티 내 상품 검색
    community_products = search_in_community(driver, community_id, max_results=20)

    # Step 3: 커뮤니티 분석
    community_analysis = analyze_community(driver, community_id)

    # Step 4: 컨텍스트 구성
    context = build_recommendation_context(
        question,
        initial_products,
        community_products,
        community_analysis
    )

    # Step 5: 추천 생성
    recommendation = generate_recommendation(question, context)

    return {
        'question': question,
        'recommendation': recommendation,
        'communityId': community_id,
        'communitySize': community_size,
        'products': community_products[:10],
        'context': context
    }


# ============================================
# 결과 출력
# ============================================

# [이 파일에서 정의] 결과 딕셔너리를 보기 좋게 출력
def print_recommendation(result: Dict[str, Any]):
    """추천 결과 출력"""
    print("\n" + "=" * 70)
    print("상품 추천 결과")
    print("=" * 70)

    print(f"\n질문: {result['question']}")

    # 주의: 커뮤니티 번호가 0 이면 0 은 거짓이라 이 블록이 건너뛰어진다. Leiden 커뮤니티 번호는 0 일 수 있다.
    #       "is not None" 으로 비교하는 것이 맞다
    if result.get('communityId'):
        # 조건식 안에서 f-string 을 만든다. communitySize 가 없으면 빈 글자
        size_info = f" (크기: {result.get('communitySize', 'N/A'):,}개)" if result.get('communitySize') else ""
        print(f"\nCommunity ID: {result['communityId']}{size_info}")

    print(f"\n추천:\n{result['recommendation']}")

    if result.get('products'):
        print(f"\n" + "-" * 70)
        print("추천 상품 목록:")
        print("-" * 70)
        for i, prod in enumerate(result['products'][:5], 1):
            name = prod.get('name', 'N/A')
            appearance = prod.get('appearance', 'N/A')
            colour = prod.get('colour', 'N/A')
            print(f"{i}. {name} ({appearance}, {colour})")


# ============================================
# 메인 함수
# ============================================

# [이 파일에서 정의] 연결 -> 질문 입력 반복 -> 파이프라인 -> 출력
def main():
    print("=" * 70)
    print("H&M 커뮤니티 기반 상품 추천 시스템")
    print("=" * 70)

    # 연결 설정
    driver = create_neo4j_connection()
    setup_openai()

    try:
        print("=" * 70)

        # while True + break: q/quit/exit 를 입력할 때까지 반복
        while True:
            # input("질문: "): [출처] 파이썬 기본. 키보드 입력을 한 줄 받는다 (Enter 전까지)
            user_question = input("질문: ").strip()

            # .lower() in [...]: 소문자로 바꿔 목록 안에 있는지
            if user_question.lower() in ['quit', 'exit', 'q']:
                print("\n프로그램을 종료합니다.")
                break

            # 빈 입력이면 continue: 아래를 건너뛰고 다시 질문
            if not user_question:
                continue

            result = retail_graphrag_query(driver, user_question)
            print_recommendation(result)

    # try/finally: 중간에 에러가 나거나 Ctrl+C 로 끊어도 드라이버를 닫는다
    finally:
        driver.close()

# 직접 실행할 때만 main()
if __name__ == "__main__":
    main()
