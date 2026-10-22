"""[1단계: 읽기] law2kg.py (법령 + 해석례 지식그래프의 함수 모음) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
csv2kg, txt2kg, pdf2kg 주석본에서 설명한 것은 짧게만 적었다.

이 파일은 직접 실행하지 않는다 (__main__ 없음). 함수만 정의해 두고
  step1_load_laws.py            -> setup_neo4j, build_law_graph            (1단계: 법령 -> 조/항/호)
  step2_link_interpretations.py -> build_interpretation_graph               (2단계: 해석례 -> 법령/조문 연결)
가 import 해서 쓴다.

그래프 모양
  1단계 (API 데이터 그대로, LLM 없음)
    (Law)-[:HAS_ARTICLE]->(Article)-[:HAS_PARAGRAPH]->(Paragraph)-[:HAS_ITEM]->(Item)
    (Article)-[:NEXT_ARTICLE]->(Article)        조문 순서
  2단계 (해석례 + LLM 으로 인용 조문 추출)
    (LegalInterpretation)-[:HAS_QUESTION]->(Question)-[:ANSWERED_BY]->(Answer)-[:SUPPORTED_BY]->(Reason)
    (LegalInterpretation)-[:HAS_ANSWER]->(Answer)
    (LegalInterpretation)-[:INTERPRETS]->(Law)                      「법령명」 정규식 + 이름 정규화
    (LegalInterpretation)-[:CITES]->(Article | Paragraph | Item | Law) LLM 이 뽑은 조/항/호, 다른 법령
    (Organization)-[:REQUESTED]->(LegalInterpretation)-[:ANSWERED_BY]->(Organization)

읽는 순서 권장
  1단계: build_law_graph(382줄 근처) -> create_law_node -> extract_articles_from_law_detail -> create_article_structure
  2단계: build_interpretation_graph(맨 아래) -> create_interpretation_node -> link_to_law -> link_cited_articles
  law_api 주석본(step1_law_api_annotated.py)을 먼저 읽으면 API 응답 모양을 알 수 있다.

주의: 이 주석본은 import 용으로 쓸 수 없다 (step 스크립트는 원본 law2kg.py 를 import 한다).
"""

# [출처] 표준 라이브러리. json.loads(글->딕셔너리), json.dumps(딕셔너리->글)
import json
# [출처] 표준 라이브러리. os.getenv
import os
# [출처] 표준 라이브러리 re (정규표현식). 「법령명」 같은 패턴을 글에서 찾는다
import re
# [출처] 표준 라이브러리. textwrap.dedent: 공통 들여쓰기 제거
import textwrap
# 타입 힌트. Any=아무 타입, Dict[str, Any]=문자열 키 딕셔너리, List[...] 리스트
from typing import Any, Dict, List

# [출처] 이 폴더의 law_api.py (같은 폴더의 .py 파일은 파일 이름으로 import 할 수 있다)
# fetch_law_list: 목록 조회 / fetch_law_detail: 본문 조회. 실패하면 둘 다 {} 를 돌려준다
from law_api import fetch_law_detail, fetch_law_list
# [출처] 외부 라이브러리 openai
from openai import OpenAI

# ============================================
# 환경 변수 설정
# ============================================

# 주의: 이 파일은 load_dotenv() 를 부르지 않는다. import 하는 쪽(step1, step2)이 먼저 load_dotenv() 를 불러야
# os.getenv 가 값을 찾는다. (import 시점에 이 줄이 실행되므로, import 보다 load_dotenv 가 먼저여야 한다.
# step 스크립트를 보면 import 가 load_dotenv() 보다 위에 있어서 NEO4J_DATABASE 가 None 이 될 수 있다.
# 그래도 동작하는 이유: database_=None 이면 드라이버가 서버의 기본 DB 를 쓴다)
NEO4J_DATABASE = os.getenv('NEO4J_USERNAME')  # Neo4j 데이터베이스명


# ============================================
# Neo4j 제약조건 설정
# ============================================

# [이 파일에서 정의] 고유 제약조건(UNIQUE) 7개 생성. 같은 id 의 노드가 두 번 생기는 것을 DB 가 막고, 자동으로 인덱스도 생긴다
def setup_neo4j(driver):
    """Neo4j 제약조건 설정"""
    print("Neo4j 제약조건 설정 중...")

    # CREATE CONSTRAINT 이름 IF NOT EXISTS FOR (l:Law) REQUIRE l.law_id IS UNIQUE
    #   -> Law 노드의 law_id 는 겹치면 안 된다. IF NOT EXISTS: 이미 있으면 그냥 넘어감 (여러 번 실행해도 안전)
    # [왜] MERGE (l:Law {law_id: ...}) 가 빨라지고(인덱스), 실수로 중복이 생기지 않는다
    constraints = [
        "CREATE CONSTRAINT law_id_unique IF NOT EXISTS FOR (l:Law) REQUIRE l.law_id IS UNIQUE",
        "CREATE CONSTRAINT article_id_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.article_id IS UNIQUE",
        "CREATE CONSTRAINT org_name_unique IF NOT EXISTS FOR (o:Organization) REQUIRE o.name IS UNIQUE",
        "CREATE CONSTRAINT interpretation_id_unique IF NOT EXISTS FOR (i:LegalInterpretation) REQUIRE i.interpretation_id IS UNIQUE",
        "CREATE CONSTRAINT question_id_unique IF NOT EXISTS FOR (q:Question) REQUIRE q.question_id IS UNIQUE",
        "CREATE CONSTRAINT answer_id_unique IF NOT EXISTS FOR (a:Answer) REQUIRE a.answer_id IS UNIQUE",
        "CREATE CONSTRAINT reason_id_unique IF NOT EXISTS FOR (r:Reason) REQUIRE r.reason_id IS UNIQUE",
    ]

    # 제약조건 하나가 실패해도 나머지는 계속 만들도록 하나씩 try
    for constraint in constraints:
        try:
            driver.execute_query(constraint, database_=NEO4J_DATABASE)
            # constraint[:50]: 문자열 앞 50자
            print(f"✓ {constraint[:50]}...")
        except Exception as e:
            print(f"ERROR: {str(e)}")

    print("제약조건 설정 완료!\n")


# ============================================
# 유틸리티 함수
# ============================================

# [이 파일에서 정의] 이름을 비교하기 좋게 통일한다. "주차장법 시행령" 과 "주차장법시행령" 을 같은 이름으로 보려고
# [입력] 법령명 문자열   [반환] 정규화된 문자열
def normalize_law_name(name: str) -> str:
    """법령명 정규화 (중복 체크용)

    - 띄어쓰기 제거
    - 특수문자 정규화 (·, ㆍ, ・ → 통일)
    - 소문자 변환
    """
    # None 이나 빈 문자열이면 빈 문자열 반환 (아래 .replace 에서 에러 나지 않게)
    if not name:
        return ''

    # 문자열.replace(a, b): a 를 모두 b 로 바꾼 "새" 문자열 (문자열은 바꿀 수 없는 값이라 항상 새로 만든다)
    # .replace(...).replace(...) 처럼 이어서 쓸 수 있다 (메서드 체이닝). 가운뎃점 모양 3가지를 하나로
    normalized = name.replace('ㆍ', '·').replace('・', '·') # 특수문자 정규화
    normalized = normalized.replace(' ', '') # 띄어쓰기 제거
    # 문자열.lower(): 영문 소문자로. 한글에는 영향 없음
    normalized = normalized.lower() # 소문자 변환 (영문 포함 시)

    return normalized


# [이 파일에서 정의] 해석례 글 -> LLM -> 어느 법령의 몇 조 몇 항 몇 호를 인용했는지
# [반환] {"primary_law": 법령명, "cited_articles": [{"article": "4", "paragraph": "1"}, ...], "other_laws": [...]}
# 실패하면 빈 값들로 채운 같은 모양의 딕셔너리 -> 호출한 쪽이 키 존재를 따로 확인할 필요가 없다
def extract_law_citations_with_llm(text: str, interpretation_title: str) -> Dict[str, Any]:
    """LLM으로 해석례 텍스트에서 법령 및 조문 추출 (Structured Output)

    Args:
        text: 질의요지 + 회답 + 이유 합친 텍스트
        interpretation_title: 해석례 제목 (컨텍스트용)

    Returns:
        {
            "primary_law": "도로교통법",
            "cited_articles": ["3", "5", "12"],
            "other_laws": ["주차장법", "장애인복지법"]
        }
    """
    try:
        # 함수가 불릴 때마다 클라이언트를 새로 만든다 (해석례 수만큼). 바깥에서 한 번 만들어 넘기는 편이 효율적이다
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

        # system 프롬프트. f-string 이라 JSON 예시의 중괄호는 {{ }} 로 썼다
        prompt = textwrap.dedent(f"""
        당신은 법령 해석례를 분석하는 전문가입니다.
        주어진 텍스트를 분석하여 다음 키를 가진 JSON 객체를 생성해주세요:

        <output_format>
        1. **primary_law**: 이 해석례가 주로 다루는 법령명 (제목에서 「」 안의 법령)
        2. **cited_articles**: primary_law의 조문·항·호 정보를 상세히 추출 (배열)
        - 각 항목은 객체로 구성: {{"article": "조문번호", "paragraph": "항번호", "item": "호번호"}}
        - 예시:
            * "제4조제1항" → {{"article": "4", "paragraph": "1"}}
            * "제2조제2호" → {{"article": "2", "item": "2"}}
            * "제3조" → {{"article": "3"}}
            * "제5조제3항제2호" → {{"article": "5", "paragraph": "3", "item": "2"}}
        - primary_law와 관련된 조문만 포함
        3. **other_laws**: 본문에 언급된 다른 법령명 리스트 (primary_law 제외)
        </output_format>

        <rules>
        - cited_articles는 반드시 primary_law의 조문만 포함
        - 다른 법령의 조문은 cited_articles에 포함하지 말 것
        - 항·호가 없으면 해당 필드는 생략
        - 법령명은 「」를 제외한 순수 법령명만
        </rules>
        """).strip()

        # openai_client.chat.completions.create (txt2kg 주석본 참고)
        # gpt-4o-mini: 작고 싼 모델. 인용 조문 뽑기는 단순 작업이라 충분하다
        # user 메시지의 {text[:3000]}: 앞 3000자만 보낸다 (토큰 비용, 길이 제한)
        # response_format json_object: JSON 으로만 답하게 강제 / max_tokens=500: 답이 짧으니 작게
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"""
                    다음은 법령 해석례의 내용입니다.

                    <interpretation_title>
                    {interpretation_title}
                    </interpretation_title>

                    <interpretation_text>
                    {text[:3000]}
                    </interpretation_text>

                    위 텍스트에서 primary_law, cited_articles, other_laws를 추출하여 JSON으로 답변해주세요."""
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500
        )

        # json.loads: 답 글(JSON) -> 딕셔너리
        result = json.loads(response.choices[0].message.content)

        # .get(키, 기본값)으로 다시 담아서 키가 빠져도 항상 같은 모양을 돌려준다
        return {
            "primary_law": result.get("primary_law", ""),
            "cited_articles": result.get("cited_articles", []),
            "other_laws": result.get("other_laws", [])
        }

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {
            "primary_law": "",
            "cited_articles": [],
            "other_laws": []
        }


# ============================================
# 조문 추출 함수
# ============================================

# [이 파일에서 정의] fetch_law_detail(law) 응답 -> [{number, title, content, paragraphs}, ...]
# 응답 모양: {"법령": {"조문": {"조문단위": [조문, 조문, ...]}}}
def extract_articles_from_law_detail(law_detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    """법령 상세에서 조문 정보 추출"""
    articles = []

    # JSON 구조: 법령 → 조문 → 조문단위
    # .get(키, {}) 를 이어서: 중간 키가 없으면 빈 딕셔너리 -> 다음 .get 도 에러 없이 기본값
    law_data = law_detail.get('법령', {})
    article_section = law_data.get('조문', {})
    article_list = article_section.get('조문단위', [])

    # API 특징: 결과가 1개면 리스트가 아니라 딕셔너리 하나로 온다 (XML -> JSON 변환의 흔한 문제)
    # isinstance(x, dict) 이면 [x] 로 감싸서 항상 리스트로 다룬다. 이 파일 곳곳에 같은 패턴이 나온다
    if isinstance(article_list, dict):
        article_list = [article_list]

    for article in article_list:
        # a or b : a 가 None/빈 값이면 b. 응답마다 키 이름이 다를 수 있어서 후보를 순서대로 시도한다
        articles.append({
            'number': article.get('조문번호') or article.get('조번호'),
            'title': article.get('조문제목') or article.get('조문가지번호'),
            'content': article.get('조문내용') or article.get('조문'),
            'paragraphs': extract_paragraphs_from_article(article),
        })

    return articles


# [이 파일에서 정의] 조문 딕셔너리 -> [{content, items}, ...] (항 목록)
def extract_paragraphs_from_article(article: Dict[str, Any]) -> List[Dict[str, Any]]:
    """조문에서 항 정보 추출"""
    paragraphs = []

    # '항' in article: 딕셔너리에 '항' 키가 있는지
    if '항' in article:
        para_list = article['항']

        # 항이 딕셔너리면 리스트로 변환
        if isinstance(para_list, dict):
            para_list = [para_list]

        for para in para_list:
            # 항이 호 정보만 가진 경우 (제2조처럼)
            # 항 내용 없이 호만 있는 경우: 항을 내용 '' 인 빈 항으로 만들고 그 아래에 호를 둔다
            # (그래서 Item 은 항상 Paragraph 아래에 있다 -> link_cited_articles 에서 "항 없이 호만" 인 경우도 Paragraph 를 거쳐 찾는다)
            if isinstance(para, dict) and '호' in para and '항내용' not in para:
                # 항 없이 바로 호가 있는 경우
                paragraphs.append({
                    'content': '',
                    'items': extract_items_from_value(para.get('호', [])),
                })
            else:
                # 일반적인 항 구조
                paragraphs.append({
                    'content': para.get('항내용') or para.get('내용', ''),
                    'items': extract_items_from_value(para.get('호', [])),
                })

    return paragraphs


# [이 파일에서 정의] 호 값(리스트 또는 딕셔너리 하나) -> [{content}, ...]
# [입력] Any: 무엇이 올지 모른다는 뜻. None, {}, [] 모두 가능
def extract_items_from_value(item_value: Any) -> List[Dict[str, Any]]:
    """호 정보 추출 (배열 또는 딕셔너리)"""
    items = []

    if not item_value:
        return items

    item_list = item_value
    if isinstance(item_list, dict):
        item_list = [item_list]

    for item in item_list:
        items.append({
            'content': item.get('호내용') or item.get('내용', ''),
        })

    return items


# ============================================
# 1단계: 현행법령(law) 그래프 구축
# ============================================

# [이 파일에서 정의] 목록 API 의 법령 하나 -> Law 노드 (MERGE: 있으면 갱신, 없으면 생성)
def create_law_node(driver, law_data: Dict[str, Any]):
    """법령 노드 생성"""
    # MERGE (l:Law {law_id: $law_id}) SET ... : law_id 로 찾거나 만들고, 나머지 속성은 매번 덮어쓴다
    # datetime(): Cypher 함수. 지금 시각
    cypher = """
    MERGE (l:Law {law_id: $law_id})
    SET l.name = $name,
        l.short_name = $short_name,
        l.category = $category,
        l.promulgation_date = $promulgation_date,
        l.promulgation_number = $promulgation_number,
        l.enforcement_date = $enforcement_date,
        l.authority = $authority,
        l.status = $status,
        l.updated_at = datetime()
    RETURN l
    """

    # 한글 키를 영문 속성 이름으로 바꾸는 매핑. or '시행': 값이 없으면 기본값
    params = {
        'law_id': law_data.get('법령일련번호') or law_data.get('MST'),
        'name': law_data.get('법령명한글') or law_data.get('법령명'),
        'short_name': law_data.get('법령약칭명'),
        'category': law_data.get('법령구분명') or law_data.get('법령구분'),
        'promulgation_date': law_data.get('공포일자'),
        'promulgation_number': law_data.get('공포번호'),
        'enforcement_date': law_data.get('시행일자'),
        'authority': law_data.get('소관부처명') or law_data.get('소관부처'),
        'status': law_data.get('법령상태') or '시행',
    }

    # execute_query(쿼리, 파라미터딕셔너리, database_=...) : 두 번째 인자 딕셔너리의 키가 쿼리의 $키 에 들어간다
    driver.execute_query(cypher, params, database_=NEO4J_DATABASE)


# [이 파일에서 정의] 조문 리스트 -> Article, Paragraph, Item 노드와 관계를 하나씩 만든다
# id 를 부모 id + 순번으로 만든다: 법령id_조번호 -> _p1 -> _i1. 다시 실행해도 같은 id 라 MERGE 로 중복이 안 생긴다
def create_article_structure(driver, law_id: str, articles: List[Dict[str, Any]]):
    """조문 구조 생성 (조문, 항, 호)"""
    if not articles:
        print("    [SKIP] 조문 데이터가 없습니다.")
        return

    print(f"    - 조문 {len(articles)}개에 대한 조-항-호 구조 생성")

    # enumerate(리스트, 1): (순번, 원소). 두 번째 인자 1 = 순번을 1부터 시작
    for order, article_data in enumerate(articles, 1):
        # article_data.get('number', order): 조번호가 없으면 순번을 대신 쓴다
        # 주의: 키가 있고 값이 None 이면 기본값이 아니라 None 이 나온다 -> "법령id_None" 이 될 수 있다
        article_id = f"{law_id}_{article_data.get('number', order)}"

        # Article 노드 생성
        # MERGE (a:Article ...) SET ... WITH a MATCH (l:Law ...) MERGE (l)-[:HAS_ARTICLE {order}]->(a)
        # WITH a: 앞 결과(a)를 다음 단계로 넘긴다. 쿼리 한 번에 노드 만들기 + 부모와 연결까지
        # 관계에도 속성(order)을 줄 수 있다
        cypher_article = """
        MERGE (a:Article {article_id: $article_id})
        SET a.number = $number,
            a.title = $title,
            a.content = $content,
            a.law_id = $law_id,
            a.order = $order
        WITH a
        MATCH (l:Law {law_id: $law_id})
        MERGE (l)-[:HAS_ARTICLE {order: $order}]->(a)
        RETURN a
        """

        # Neo4j 속성에는 숫자, 문자열, 불리언과 그 리스트만 넣을 수 있다. 딕셔너리는 못 넣는다
        # -> 딕셔너리/리스트면 json.dumps 로 JSON 글로 바꿔서 저장 (ensure_ascii=False: 한글 그대로)
        # content가 dict/list인 경우 JSON 문자열로 변환
        content = article_data.get('content')
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False)
        # elif ... is not None: None 은 그대로 두고(속성 없음), 숫자 등은 str() 로 문자열로
        elif content is not None:
            content = str(content)

        params_article = {
            'article_id': article_id,
            'number': article_data.get('number'),
            'title': article_data.get('title'),
            'content': content,
            'law_id': law_id,
            'order': order,
        }

        driver.execute_query(cypher_article, params_article, database_=NEO4J_DATABASE)

        # 항(Paragraph) 처리: 조문과 같은 패턴을 한 단계 아래로. 항 번호는 순번(p_order)
        # 항(Paragraph) 처리
        paragraphs = article_data.get('paragraphs', [])
        for p_order, para_data in enumerate(paragraphs, 1):
            paragraph_id = f"{article_id}_p{p_order}"

            cypher_para = """
            MERGE (p:Paragraph {paragraph_id: $paragraph_id})
            SET p.number = $number,
                p.content = $content,
                p.article_id = $article_id,
                p.order = $order
            WITH p
            MATCH (a:Article {article_id: $article_id})
            MERGE (a)-[:HAS_PARAGRAPH {order: $order}]->(p)
            RETURN p
            """

            # content가 dict/list인 경우 JSON 문자열로 변환
            para_content = para_data.get('content')
            if isinstance(para_content, (dict, list)):
                para_content = json.dumps(para_content, ensure_ascii=False)
            elif para_content is not None:
                para_content = str(para_content)

            params_para = {
                'paragraph_id': paragraph_id,
                'number': p_order,
                'content': para_content,
                'article_id': article_id,
                'order': p_order,
            }

            driver.execute_query(cypher_para, params_para, database_=NEO4J_DATABASE)

            # 호(Item) 처리: 또 한 단계 아래로 (반복문 3중첩)
            # 호(Item) 처리
            items = para_data.get('items', [])
            for i_order, item_data in enumerate(items, 1):
                item_id = f"{paragraph_id}_i{i_order}"

                cypher_item = """
                MERGE (i:Item {item_id: $item_id})
                SET i.number = $number,
                    i.content = $content,
                    i.paragraph_id = $paragraph_id,
                    i.order = $order
                WITH i
                MATCH (p:Paragraph {paragraph_id: $paragraph_id})
                MERGE (p)-[:HAS_ITEM {order: $order}]->(i)
                RETURN i
                """

                # content가 dict/list인 경우 JSON 문자열로 변환
                item_content = item_data.get('content')
                if isinstance(item_content, (dict, list)):
                    item_content = json.dumps(item_content, ensure_ascii=False)
                elif item_content is not None:
                    item_content = str(item_content)

                params_item = {
                    'item_id': item_id,
                    'number': i_order,
                    'content': item_content,
                    'paragraph_id': paragraph_id,
                    'order': i_order,
                }

                driver.execute_query(cypher_item, params_item, database_=NEO4J_DATABASE)

    # 조문 순서대로 NEXT_ARTICLE 로 줄줄이 잇기 (1조 -> 2조 -> 3조 ...)
    # WITH a ORDER BY a.order : 순서대로 정렬
    # collect(a) as articles : 정렬된 조문들을 리스트 하나로 모은다
    # UNWIND range(0, size(articles)-2) as idx : 0 부터 끝에서 두 번째까지의 번호를 한 행씩 (range 는 끝 포함)
    # articles[idx], articles[idx+1] : 이웃한 두 조문 -> MERGE 로 연결
    # [왜] "다음 조문" 을 따라가며 읽는 질의(앞뒤 문맥)가 쉬워진다
    # NEXT_ARTICLE 관계 생성 (순차적 연결)
    cypher_next = """
    MATCH (l:Law {law_id: $law_id})-[:HAS_ARTICLE]->(a:Article)
    WITH a ORDER BY a.order
    WITH collect(a) as articles
    UNWIND range(0, size(articles)-2) as idx
    WITH articles[idx] as current, articles[idx+1] as next
    MERGE (current)-[:NEXT_ARTICLE]->(next)
    """

    driver.execute_query(cypher_next, {'law_id': law_id}, database_=NEO4J_DATABASE)


# [이 파일에서 정의] 1단계 진입점. 목록 API 를 페이지 단위로 받아 법령을 max_laws 개까지 처리
# [입력] driver, api_key, max_laws   [반환] 없음 (DB 에 저장)
def build_law_graph(driver, api_key: str, max_laws: int = 10):
    """1단계: 현행법령 그래프 구축"""
    print("=" * 80)
    print("[1단계] 현행법령(law) 그래프 구축 시작")
    print("=" * 80)

    # 주의: 1부터 시작하고 "< max_laws" 로 비교하므로 실제로는 max_laws - 1 개를 처리한다 (10 이면 9개)
    # 마지막 출력의 "총 N개" 도 실제보다 1 크다. 0 에서 시작하면 정확해진다
    processed_count = 1
    page = 1

    # while 조건: 조건이 참인 동안 반복. 페이지를 늘려 가며 계속 받는다
    while processed_count < max_laws:
        # display=max_laws: 한 페이지에 max_laws 개씩 요청
        law_list_response = fetch_law_list(api_key, target='law', display=max_laws, page=page)

        # 빈 딕셔너리 {} (API 실패) -> 반복 중단. break: 가장 가까운 반복문을 빠져나간다
        if not law_list_response:
            print("ERROR: 법령 목록을 가져올 수 없습니다.")
            break

        law_list_data = law_list_response.get('LawSearch', {})
        laws = law_list_data.get('law', [])
        if isinstance(laws, dict):
            laws = [laws]

        if not laws:
            print("더 이상 법령이 없습니다.")
            break

        # 이 for 안의 break 는 for 만 빠져나간다. 바깥 while 은 조건(processed_count < max_laws)이 거짓이 되어 끝난다
        for idx, law_summary in enumerate(laws, 1):
            if processed_count >= max_laws:
                break

            # 법령 하나가 실패해도 다음 법령으로 계속
            try:
                law_id = law_summary.get('법령일련번호') or law_summary.get('MST')
                law_name = law_summary.get('법령명한글') or law_summary.get('법령명')
                status_code = law_summary.get('현행연혁코드', '')

                # continue: 이번 반복의 나머지를 건너뛰고 다음 원소로
                if not law_id or not law_name:
                    continue

                # '연혁' = 지금은 효력이 없는 옛 법령 -> 건너뛴다 (현행만 적재)
                if status_code == '연혁':
                    continue

                print(f"[{processed_count}/{max_laws}] 처리 중: {law_name} (ID: {law_id})")

                create_law_node(driver, law_summary)

                # 목록에는 조문이 없어서, 법령마다 본문 API 를 한 번 더 부른다
                law_detail = fetch_law_detail(api_key, law_id, target='law')
                if law_detail:
                    articles = extract_articles_from_law_detail(law_detail)
                    create_article_structure(driver, law_id, articles)

                processed_count += 1

            except Exception as e:
                print(f"ERROR: {str(e)}\n")

        # 페이지 끝까지 처리했는데 아직 부족하면 다음 페이지
        page += 1

    print("=" * 80)
    print(f"[1단계] 현행법령 그래프 구축 완료! (총 {processed_count}개 법령 처리)")
    print("=" * 80)


# ============================================
# 2단계: 법령해석례(expc) 추가
# ============================================

# [이 파일에서 정의] 해석례 하나 -> 노드 4종 생성 후, LLM 으로 인용 조문을 뽑아 돌려준다
# interp_detail: Dict[str, Any] = None : 기본값 None (상세 없이 불러도 된다)
# [반환] extract_law_citations_with_llm 의 결과 딕셔너리 (연결은 호출한 쪽이 나중에 한다)
def create_interpretation_node(driver, interp_summary: Dict[str, Any], interp_detail: Dict[str, Any] = None):
    """
    법령해석례 노드 생성

    생성 노드:
    - LegalInterpretation (메타데이터)
    - Question (질의요지)
    - Answer (회답)
    - Reason (이유)
    """
    # 목록 API 데이터
    interp_id = interp_summary.get('법령해석례일련번호') or interp_summary.get('MST')
    title = interp_summary.get('안건명') or interp_summary.get('제목', '')
    case_number = interp_summary.get('안건번호')
    answer_date_str = interp_summary.get('회신일자', '')

    # 상세 응답 모양: {"ExpcService": {"질의요지": ..., "회답": ..., "이유": ...}}
    # 상세 API 데이터 (ExpcService)
    question_text = None
    answer_text = None
    reason_text = None

    if interp_detail:
        expc_data = interp_detail.get('ExpcService', {})
        question_text = expc_data.get('질의요지', '')
        answer_text = expc_data.get('회답', '')
        reason_text = expc_data.get('이유', '')

    # "20240115" 같은 8자리 글 -> Cypher 의 datetime('2024-01-15') 표현식 "글" 을 만든다
    # [왜] 이 값은 파라미터($)가 아니라 f-string 으로 쿼리에 직접 들어간다. 그래서 숫자인지, 범위가 맞는지 엄격히 검사한다
    # (검사 없이 넣으면 이상한 글이 쿼리 구조를 깨뜨릴 수 있다)
    # 참고: 파라미터로 '2024-01-15' 를 넘기고 쿼리에서 datetime($date) 로 바꾸는 방법이 더 안전하고 간단하다
    # 날짜 변환 (YYYYMMDD → datetime) - 안전한 변환
    answer_date_cypher = "null"
    if answer_date_str and len(answer_date_str) >= 8:
        try:
            # 문자열 슬라이싱: [:4] 앞 4글자, [4:6] 5~6번째, [6:8] 7~8번째
            year = answer_date_str[:4]
            month = answer_date_str[4:6]
            day = answer_date_str[6:8]

            # 숫자인지 검증
            # 문자열.isdigit(): 전부 숫자면 True
            if year.isdigit() and month.isdigit() and day.isdigit():
                # 한 줄에 여러 변수 대입 (튜플 풀기). int(글): 정수로
                y, m, d = int(year), int(month), int(day)
                # 유효 범위 검증
                # 1900 <= y <= 2100 : 파이썬은 비교를 이어 쓸 수 있다 (1900 <= y and y <= 2100 과 같다)
                if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
                    answer_date_cypher = f"datetime('{year}-{month}-{day}')"
        # except: (예외 종류 없이) 모든 예외를 잡는다. 실패하면 "null" 그대로
        except:
            pass

    # f-string 쿼리: {answer_date_cypher} 만 변수, {{ }} 는 글자 중괄호
    # 1. LegalInterpretation 메타 노드 생성
    cypher_interp = f"""
    MERGE (i:LegalInterpretation {{interpretation_id: $interpretation_id}})
    SET i.title = $title,
        i.case_number = $case_number,
        i.answer_date = {answer_date_cypher},
        i.status = 'active',
        i.updated_at = datetime()
    RETURN i
    """

    # 파라미터 딕셔너리를 호출 안에 바로 써도 된다
    driver.execute_query(cypher_interp, {
        'interpretation_id': interp_id,
        'title': title,
        'case_number': case_number,
    }, database_=NEO4J_DATABASE)

    # 질의요지 -> Question 노드. id = 해석례id + "-Q"
    # 2. Question 노드 생성
    if question_text:
        cypher_question = """
        MATCH (i:LegalInterpretation {interpretation_id: $interpretation_id})
        MERGE (q:Question {question_id: $question_id})
        SET q.text = $text,
            q.updated_at = datetime()
        MERGE (i)-[:HAS_QUESTION]->(q)
        RETURN q
        """

        driver.execute_query(cypher_question, {
            'interpretation_id': interp_id,
            'question_id': f"{interp_id}-Q",
            'text': question_text,
        }, database_=NEO4J_DATABASE)

    # 회답 -> Answer 노드, 그리고 질문이 있으면 질문과 연결
    # // 는 Cypher 주석
    # OPTIONAL MATCH: 못 찾아도 행을 없애지 않고 q 를 null 로 둔다 (그냥 MATCH 면 결과가 0행이 되어 RETURN 도 없다)
    # FOREACH (x IN CASE WHEN q IS NOT NULL THEN [1] ELSE [] END | MERGE ...)
    #   : Cypher 에는 if 가 없어서 쓰는 관용구. 조건이 참이면 원소 1개짜리 리스트 -> MERGE 1번, 거짓이면 빈 리스트 -> 0번
    # 3. Answer 노드 생성 및 Question과 연결
    if answer_text:
        cypher_answer = """
        MATCH (i:LegalInterpretation {interpretation_id: $interpretation_id})
        MERGE (a:Answer {answer_id: $answer_id})
        SET a.text = $text,
            a.updated_at = datetime()
        MERGE (i)-[:HAS_ANSWER]->(a)

        // Question과 Answer 직접 연결
        WITH i, a
        OPTIONAL MATCH (i)-[:HAS_QUESTION]->(q:Question)
        FOREACH (x IN CASE WHEN q IS NOT NULL THEN [1] ELSE [] END |
            MERGE (q)-[:ANSWERED_BY]->(a)
        )
        RETURN a
        """

        driver.execute_query(cypher_answer, {
            'interpretation_id': interp_id,
            'answer_id': f"{interp_id}-A",
            'text': answer_text,
        }, database_=NEO4J_DATABASE)

    # 이유 -> Reason 노드. 회답이 있으면 Answer-[:SUPPORTED_BY]->Reason, 없으면 해석례-[:HAS_REASON]->Reason
    # WITH ... WHERE a IS NOT NULL : 조건에 안 맞으면 그 뒤는 실행되지 않는다(행이 사라짐)
    # 주의: 회답이 없으면 첫 WHERE 에서 행이 사라져서 HAS_REASON 부분도 실행되지 않는다.
    #       그래서 HAS_REASON 은 사실상 만들어지지 않는다 (step2 통계에도 HAS_REASON 이 없다). 고쳐 보는 연습 거리
    # 4. Reason 노드 생성
    if reason_text:
        cypher_reason = """
        MATCH (i:LegalInterpretation {interpretation_id: $interpretation_id})
        OPTIONAL MATCH (i)-[:HAS_ANSWER]->(a:Answer)
        MERGE (r:Reason {reason_id: $reason_id})
        SET r.text = $text,
            r.updated_at = datetime()
        WITH i, a, r
        WHERE a IS NOT NULL
        MERGE (a)-[:SUPPORTED_BY]->(r)
        WITH i, r
        WHERE NOT EXISTS((i)-[:HAS_ANSWER]->())
        MERGE (i)-[:HAS_REASON]->(r)
        RETURN r
        """

        driver.execute_query(cypher_reason, {
            'interpretation_id': interp_id,
            'reason_id': f"{interp_id}-R",
            'text': reason_text,
        }, database_=NEO4J_DATABASE)

    # {x or ''}: None 이면 빈 문자열. 세 글을 공백으로 이어 LLM 에 넘긴다
    # LLM으로 인용된 법령 및 조문 추출
    all_text = f"{question_text or ''} {answer_text or ''} {reason_text or ''}"
    citations = extract_law_citations_with_llm(all_text, title)

    return citations



# [이 파일에서 정의] LLM 이 뽑은 조/항/호를 실제 노드에서 찾아 CITES 로 연결
# 경로: 해석례 -INTERPRETS-> 법령 -HAS_ARTICLE-> 조 -HAS_PARAGRAPH-> 항 -HAS_ITEM-> 호
# 그래서 link_to_law(INTERPRETS 생성)가 이 함수보다 먼저 실행되어야 한다
def link_cited_articles(driver, interp_id: str, citations: List[Dict[str, str]]):
    """
    텍스트에서 인용된 조문·항·호와 노드 연결

    예시:
    - "제3조" → Article(3)과 CITES 연결
    - "제4조제1항" → Article(4) + Paragraph(1) 모두 CITES 연결
    - "제2조제2호" → Article(2) + Item(2) 모두 CITES 연결
    - "제5조제3항제2호" → Article(5) + Paragraph(3) + Item(2) 모두 CITES 연결

    Args:
        driver: Neo4j driver
        interp_id: 해석례 ID
        citations: 인용 정보 리스트
                  예: [{'article': '4', 'paragraph': '1'}, {'article': '2', 'item': '2'}]
    """
    if not citations:
        return

    # 연결 결과 설명 글을 모으지만, 이 파일에서는 출력하지 않는다
    linked_items = []

    for citation in citations:
        article_num = citation.get('article')
        paragraph_num = citation.get('paragraph')
        item_num = citation.get('item')

        if not article_num:
            continue

        # 해석례가 INTERPRETS 하는 법령 안에서 그 번호의 조문을 찾는다
        # 주의: a.number 는 API 의 '조문번호' 글("4"), LLM 도 글("4")을 준다 -> 글끼리 비교라 맞는다
        # ON CREATE SET: 관계를 새로 만들었을 때만 생성 시각 기록
        # 1. Article 연결
        cypher_article = """
        MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
        MATCH (i)-[:INTERPRETS]->(l:Law)
        MATCH (l)-[:HAS_ARTICLE]->(a:Article)
        WHERE a.number = $article_number
        MERGE (i)-[r:CITES]->(a)
        ON CREATE SET r.created_at = datetime()
        RETURN a.number as target
        """

        try:
            result = driver.execute_query(cypher_article, {
                'interp_id': interp_id,
                'article_number': article_num,
            }, database_=NEO4J_DATABASE)

            # result.records 가 비어 있지 않음 = 조문을 찾아 연결했다
            if result.records:
                link_desc = f"제{article_num}조"

                # 항 번호는 create_article_structure 에서 순번(정수)으로 저장했다 -> int(paragraph_num) 로 정수로 바꿔 비교
                # (글 "1" 과 정수 1 은 Cypher 에서 다르다)
                # 2. Paragraph 연결 (있으면)
                if paragraph_num:
                    cypher_para = """
                    MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
                    MATCH (i)-[:INTERPRETS]->(l:Law)
                    MATCH (l)-[:HAS_ARTICLE]->(a:Article {number: $article_number})
                    MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)
                    WHERE p.number = $paragraph_number
                    MERGE (i)-[r:CITES]->(p)
                    ON CREATE SET r.created_at = datetime()
                    RETURN p.number as target
                    """

                    para_result = driver.execute_query(cypher_para, {
                        'interp_id': interp_id,
                        'article_number': article_num,
                        'paragraph_number': int(paragraph_num),
                    }, database_=NEO4J_DATABASE)

                    if para_result.records:
                        link_desc += f"제{paragraph_num}항"

                # 호: 항 번호가 있으면 그 항 아래에서, 없으면 그 조의 "모든 항" 아래에서 찾는다
                # 3. Item 연결 (있으면)
                if item_num:
                    # Item은 Paragraph 아래에 있거나, Article 바로 아래에 있을 수 있음
                    if paragraph_num:
                        cypher_item = """
                        MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
                        MATCH (i)-[:INTERPRETS]->(l:Law)
                        MATCH (l)-[:HAS_ARTICLE]->(a:Article {number: $article_number})
                        MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph {number: $paragraph_number})
                        MATCH (p)-[:HAS_ITEM]->(item:Item)
                        WHERE item.number = $item_number
                        MERGE (i)-[r:CITES]->(item)
                        ON CREATE SET r.created_at = datetime()
                        RETURN item.number as target
                        """

                        item_result = driver.execute_query(cypher_item, {
                            'interp_id': interp_id,
                            'article_number': article_num,
                            'paragraph_number': int(paragraph_num),
                            'item_number': int(item_num),
                        }, database_=NEO4J_DATABASE)
                    else:
                        # Paragraph 없이 Item만 있는 경우 (Article 바로 아래)
                        cypher_item = """
                        MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
                        MATCH (i)-[:INTERPRETS]->(l:Law)
                        MATCH (l)-[:HAS_ARTICLE]->(a:Article {number: $article_number})
                        MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)
                        MATCH (p)-[:HAS_ITEM]->(item:Item)
                        WHERE item.number = $item_number
                        MERGE (i)-[r:CITES]->(item)
                        ON CREATE SET r.created_at = datetime()
                        RETURN item.number as target
                        """

                        item_result = driver.execute_query(cypher_item, {
                            'interp_id': interp_id,
                            'article_number': article_num,
                            'item_number': int(item_num),
                        }, database_=NEO4J_DATABASE)

                    # item_result 는 위 if/else 둘 중 하나에서 반드시 만들어진다
                    if item_result and item_result.records:
                        link_desc += f"제{item_num}호"

                linked_items.append(link_desc)

        # str(e)[:40]: 에러 메시지 앞 40자만
        except Exception as e:
            print(f"       ERROR: (제{article_num}조): {str(e)[:40]}...")
            continue


# [이 파일에서 정의] 질의기관 -REQUESTED-> 해석례, 해석례 -ANSWERED_BY-> 회신기관
# Organization 은 name 으로 MERGE -> 같은 기관은 노드 하나로 모인다 (제약조건 org_name_unique)
def link_organizations(driver, interp_data: Dict[str, Any]):
    """기관 노드 생성 및 해석례 연결"""
    question_org = interp_data.get('질의기관명') or interp_data.get('질의기관')
    answer_org = interp_data.get('회신기관명') or interp_data.get('회신기관')
    interp_id = interp_data.get('법령해석례일련번호') or interp_data.get('MST')

    # 질의기관
    # 날짜가 있으면 관계 속성에 date 를 넣고, 없으면 속성 없이. 쿼리 글만 다르고 실행 부분은 같다
    # (date 파라미터를 넘기지만 두 번째 쿼리에서는 안 쓴다. 쓰지 않는 파라미터는 무시된다)
    if question_org:
        question_date = interp_data.get('질의일자') or ''
        if question_date:
            cypher = """
            MERGE (o:Organization {name: $org_name})
            SET o.code = $org_code
            WITH o
            MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
            MERGE (o)-[:REQUESTED {date: $date}]->(i)
            """
        else:
            cypher = """
            MERGE (o:Organization {name: $org_name})
            SET o.code = $org_code
            WITH o
            MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
            MERGE (o)-[:REQUESTED]->(i)
            """
        driver.execute_query(cypher, {
            'org_name': question_org,
            'org_code': interp_data.get('질의기관코드'),
            'interp_id': interp_id,
            'date': question_date,
        }, database_=NEO4J_DATABASE)

    # 회신기관
    if answer_org:
        answer_date = interp_data.get('회신일자') or ''
        if answer_date:
            cypher = """
            MERGE (o:Organization {name: $org_name})
            SET o.code = $org_code
            WITH o
            MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
            MERGE (i)-[:ANSWERED_BY {date: $date}]->(o)
            """
        else:
            cypher = """
            MERGE (o:Organization {name: $org_name})
            SET o.code = $org_code
            WITH o
            MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
            MERGE (i)-[:ANSWERED_BY]->(o)
            """
        driver.execute_query(cypher, {
            'org_name': answer_org,
            'org_code': interp_data.get('회신기관코드'),
            'interp_id': interp_id,
            'date': answer_date,
        }, database_=NEO4J_DATABASE)


# [이 파일에서 정의] 해석례 글 속 「법령명」 을 뽑아, DB 의 법령 이름과 정규화해서 완전히 같으면 INTERPRETS 로 연결
def link_to_law(driver, interp_data: Dict[str, Any], interp_detail: Dict[str, Any] = None):
    """해석례를 법령에 연결"""
    interp_id = interp_data.get('법령해석례일련번호') or interp_data.get('MST')

    # set(): [출처] 파이썬 기본. 중복 없는 모음. .add(x) 로 추가 (같은 값은 한 번만 들어간다)
    # 법령명 추출: 해석례 텍스트에서 「법령명」 패턴으로 추출
    law_names = set()

    # 1) 상세 API의 안건명과 본문에서 「법령명」 패턴 추출
    if interp_detail:
        expc_data = interp_detail.get('ExpcService', {})
        text_fields = [
            expc_data.get('안건명', ''),
            expc_data.get('이유', ''),
            expc_data.get('질의요지', ''),
            expc_data.get('회답', '')
        ]

        # r'「([^」]+)」' : 「 로 시작해 」 로 끝나는 부분. ( ) 안이 꺼낼 부분 = 」 가 아닌 글자 1개 이상
        # re.findall(패턴, 글): [출처] 표준 라이브러리 re. 맞는 부분을 모두 찾아 리스트로 (괄호 그룹이 있으면 그룹 안 글만)
        # 예) "「도로교통법」 제4조" -> ["도로교통법"]
        # 정규식: 「...」 패턴에서 법령명 추출
        law_pattern = r'「([^」]+)」'
        for text in text_fields:
            matches = re.findall(law_pattern, text)
            for match in matches:
                # 5글자 이하는 버린다, '동'으로 시작하면 버린다 ("동법" 같은 지시어)
                # 주의: 이 규칙이면 "민법", "형법" 같은 짧은 법도 버려지고, "동물보호법" 도 버려진다
                # "동법", "이 법" 등 일반명사 제외
                if len(match) > 5 and not match.startswith('동'):
                    law_names.add(match.strip())

    # 2) 목록 API의 안건명에서도 추출
    title = interp_data.get('안건명', '')
    if title:
        matches = re.findall(r'「([^」]+)」', title)
        for match in matches:
            if len(match) > 5 and not match.startswith('동'):
                law_names.add(match.strip())

    if not law_names:
        print("    - 관련 법령을 찾을 수 없습니다.")
        return

    # 주의: 이 반복문 안에서 매번 "모든 Law" 를 DB 에서 다시 가져온다. 반복문 밖에서 한 번만 가져오면 된다
    # (아래 link_cited_laws 는 밖에서 한 번 가져온다)
    # 각 법령명으로 매칭 시도
    matched_count = 0
    for law_name in law_names:
        # 법령명 정규화 (특수문자, 띄어쓰기 통일)
        normalized_search = normalize_law_name(law_name)

        # 정규화된 이름으로 매칭 (Cypher에서 직접 정규화는 불가하므로 Python에서 처리)
        # 모든 Law를 가져와서 Python에서 비교
        cypher_get_laws = """
        MATCH (l:Law)
        RETURN l.law_id as law_id, l.name as name, l.short_name as short_name
        """

        result_laws = driver.execute_query(cypher_get_laws, database_=NEO4J_DATABASE)

        # law_record['name'] or '' : None 이면 빈 문자열 (normalize_law_name 에 넘기려고)
        for law_record in result_laws.records:
            law_id = law_record['law_id']
            db_name = law_record['name'] or ''
            db_short_name = law_record['short_name'] or ''

            # 정규화 비교
            normalized_db_name = normalize_law_name(db_name)
            normalized_db_short = normalize_law_name(db_short_name)

            matched = False

            # 완전 일치만 허용 (부분 일치를 허용하면 "도로법" 이 "도로교통법" 에 잘못 붙을 수 있다)
            # 완전 일치만 허용
            if normalized_search == normalized_db_name:
                matched = True
            elif db_short_name and normalized_search == normalized_db_short:
                matched = True

            if matched:
                # 매칭된 법령과 연결
                cypher_link = """
                MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
                MATCH (l:Law {law_id: $law_id})
                MERGE (i)-[r:INTERPRETS]->(l)
                RETURN l.name
                """

                link_result = driver.execute_query(cypher_link, {
                    'interp_id': interp_id,
                    'law_id': law_id,
                }, database_=NEO4J_DATABASE)

                if link_result.records:
                    print(f"    - 법령 매칭: {law_name[:30]}")
                    matched_count += 1


# [이 파일에서 정의] LLM 이 뽑은 "다른 법령" 들을 DB 의 법령과 이름으로 맞춰 CITES 로 연결
def link_cited_laws(driver, interp_id: str, other_laws: List[str]):
    """참조 법령 연결 (other_laws → CITES 관계)

    Args:
        driver: Neo4j driver
        interp_id: 해석례 ID
        other_laws: LLM이 추출한 참조 법령명 리스트
    """
    if not other_laws:
        return

    # 그래프의 모든 법령 목록 조회
    cypher_get_laws = """
    MATCH (l:Law)
    RETURN l.law_id as law_id, l.name as name, l.short_name as short_name
    """

    result_laws = driver.execute_query(cypher_get_laws, database_=NEO4J_DATABASE)

    cited_count = 0

    for other_law_name in other_laws:
        # 법령명 정규화
        normalized_search = normalize_law_name(other_law_name)

        # 각 법령과 비교
        for law_record in result_laws.records:
            law_id = law_record['law_id']
            db_name = law_record['name'] or ''
            db_short_name = law_record['short_name'] or ''

            # 정규화 비교
            normalized_db_name = normalize_law_name(db_name)
            normalized_db_short = normalize_law_name(db_short_name)

            # 완전 일치만 허용
            matched = False
            if normalized_search == normalized_db_name:
                matched = True
            elif db_short_name and normalized_search == normalized_db_short:
                matched = True

            if matched:
                # CITES 관계 생성
                cypher_cite = """
                MATCH (i:LegalInterpretation {interpretation_id: $interp_id})
                MATCH (l:Law {law_id: $law_id})
                MERGE (i)-[r:CITES]->(l)
                ON CREATE SET r.created_at = datetime()
                RETURN l.name
                """

                cite_result = driver.execute_query(cypher_cite, {
                    'interp_id': interp_id,
                    'law_id': law_id,
                }, database_=NEO4J_DATABASE)

                if cite_result.records:
                    cited_count += 1
                    # 이 break 는 안쪽 for(DB 법령 목록)만 빠져나가고 다음 other_law_name 으로 넘어간다
                    break  # 매칭되면 다음 법령으로

    if cited_count > 0:
        print(f"       → 참조 법령 연결: {cited_count}개")


# [이 파일에서 정의] 2단계 진입점
# STEP 1: DB 에 있는 법령 이름 목록 -> STEP 2: 법령 이름으로 해석례 검색, 제목의 「법령명」 이 DB 에 있는 것만 수집
# -> STEP 3: 해석례마다 노드 생성, 기관 연결, 법령 연결, 인용 조문 연결
def build_interpretation_graph(driver, api_key: str, max_interpretations: int = 50):
    """2단계: 법령해석례 그래프 추가 (적재된 법령 기반)"""
    print("\n" + "=" * 80)
    print("[2단계] 법령해석례(expc) 그래프 구축 시작")
    print("=" * 80)

    # 1단계: 그래프에 적재된 법령 목록 조회
    print("\n[STEP 1] 그래프에서 적재된 법령 목록 조회 중...")
    cypher_laws = """
    MATCH (l:Law)
    RETURN l.name as name, l.short_name as short_name
    ORDER BY l.name
    """

    result = driver.execute_query(cypher_laws, database_=NEO4J_DATABASE)
    if not result.records:
        print("ERROR: 그래프에 법령이 없습니다. 먼저 step1_load_laws.py를 실행하세요.")
        return

    # law_name_pairs: {정식명칭: 약칭}
    law_names = []
    law_name_pairs = {}

    for record in result.records:
        full_name = record['name']
        short_name = record['short_name']

        if full_name:
            law_names.append(full_name)
            if short_name:
                law_name_pairs[full_name] = short_name
        elif short_name:  # 정식명칭이 없으면 약칭 사용
            law_names.append(short_name)

    # list(set(리스트)): 중복 제거 (순서는 보장되지 않는다)
    law_names = list(set(law_names))

    # {정규화된 이름: 원래 이름}. 약칭도 키로 넣어서 약칭으로 써도 찾을 수 있게
    # [왜] 딕셔너리 키로 두면 "in" 검사가 리스트보다 훨씬 빠르다
    normalized_law_names = {}
    for name in law_names:
        normalized_law_names[normalize_law_name(name)] = name
        # 약칭도 추가
        if name in law_name_pairs:
            normalized_law_names[normalize_law_name(law_name_pairs[name])] = name

    print(f"✓ 적재된 법령: {len(law_names)}개")
    # ', '.join(리스트): 쉼표로 이어 붙이기. [:5] 앞 5개만
    print(f"  {', '.join(law_names[:5])}...\n")

    # 2단계: 각 법령에 대해 해석례 검색
    print(f"[STEP 2] 적재된 법령 기반으로 해석례 검색 중...\n")

    # seen_...: 이미 본 것을 기억하는 set. 같은 해석례/같은 검색어를 두 번 처리하지 않으려고
    all_interpretations = []
    seen_interp_ids = set()
    seen_search_keywords = set()  # 이미 검색한 키워드 추적 (중복 검색 방지)

    for law_name in law_names:
        if len(all_interpretations) >= max_interpretations:
            break

        # " 시행령", " 시행규칙" 을 지운다 -> 모법, 시행령, 시행규칙이 같은 검색어가 되어 아래에서 중복 검색을 건너뛴다
        # .strip(): 앞뒤 공백 제거
        # 법령명에서 핵심 키워드 추출 (시행령, 시행규칙 등 제거)
        search_keyword = law_name.replace(' 시행령', '').replace(' 시행규칙', '').replace('시행령', '').replace('시행규칙', '').strip()

        # 너무 짧은 키워드는 스킵
        if len(search_keyword) < 4:
            continue

        # 이미 검색한 키워드는 스킵 (정규화해서 비교)
        normalized_keyword = normalize_law_name(search_keyword)
        if normalized_keyword in seen_search_keywords:
            continue
        seen_search_keywords.add(normalized_keyword)

        print(f"  검색 중: '{search_keyword[:30]}...'")

        # query 파라미터로 해당 법령 관련 해석례만 검색
        display_count = 100  # API 최대값

        # query=검색어: 해당 법령과 관련된 해석례만 검색 (최대 100개)
        expc_list_response = fetch_law_list(
            api_key,
            target='expc',
            display=display_count,
            query=search_keyword
        )

        if not expc_list_response:
            continue

        # JSON 응답에서 해석례 리스트 추출
        expc_list_data = expc_list_response.get('Expc', {})
        interpretations = expc_list_data.get('expc', [])
        if isinstance(interpretations, dict):
            interpretations = [interpretations]

        print(f"    → API 응답: {len(interpretations)}개")

        matched_count = 0
        filtered_count = 0

        # 각 해석례를 검증하면서 수집
        for interp in interpretations:
            if len(all_interpretations) >= max_interpretations:
                break

            interp_id = interp.get('법령해석례일련번호') or interp.get('MST')
            if not interp_id or interp_id in seen_interp_ids:
                filtered_count += 1
                continue

            # API 검색 결과에는 관련 없는 해석례도 섞여 있다 -> 제목의 「법령명」 이 DB 에 있는 경우만 남긴다
            # 해석례 제목에서 법령명 패턴 추출하여 사전 검증
            title = interp.get('안건명', '')
            extracted_laws = re.findall(r'「([^」]+)」', title)

            # 추출된 법령명이 그래프에 있는지 확인 (완전 일치만)
            has_match = False
            for extracted_law in extracted_laws:
                normalized_extracted = normalize_law_name(extracted_law)
                # 정규화된 이름으로 완전 일치 확인
                # 딕셔너리에 대한 in: 키에 있는지 검사
                if normalized_extracted in normalized_law_names:
                    has_match = True
                    break

            # 매칭되는 경우에만 추가
            if has_match:
                all_interpretations.append(interp)
                seen_interp_ids.add(interp_id)
                matched_count += 1
            else:
                filtered_count += 1

        if matched_count > 0:
            print(f"    → 매칭: {matched_count}개 | 필터링: {filtered_count}개 | 누적: {len(all_interpretations)}개")
        elif filtered_count > 0:
            print(f"    → 매칭: 0개 | 필터링: {filtered_count}개 (관련 없는 해석례)")

    if not all_interpretations:
        print("\nERROR: 적재된 법령과 관련된 해석례를 찾을 수 없습니다.")
        return

    print(f"\n✓ 총 {len(all_interpretations)}개의 관련 해석례를 찾았습니다.\n")
    print("[STEP 3] 해석례 노드 생성 및 법령 연결 중...\n")

    # 3단계: 해석례 하나씩. 순서가 중요하다: 노드 생성 -> 기관 -> INTERPRETS(link_to_law) -> CITES(조문)
    # 3단계: 각 해석례 처리
    for idx, interp_summary in enumerate(all_interpretations, 1):
        try:
            interp_id = interp_summary.get('법령해석례일련번호') or interp_summary.get('MST')
            title = interp_summary.get('안건명') or interp_summary.get('제목')

            # 주의: 아래 print 의 len(interpretations) 는 마지막 검색 결과의 개수다. len(all_interpretations) 가 맞다
            # (앞에서 interp_id 없는 것은 걸러졌으므로 이 줄이 실행될 일은 거의 없다)
            if not interp_id:
                print(f"[{idx}/{len(interpretations)}] SKIP: 해석례일련번호가 없습니다.")
                continue

            # {title[:50] if title else 'N/A'} : f-string 안에서도 조건식을 쓸 수 있다
            print(f"[{idx}/{len(all_interpretations)}] 처리 중: {title[:50] if title else 'N/A'}... (ID: {interp_id})")

            # 해석례 상세 조회
            interp_detail = fetch_law_detail(api_key, interp_id, target='expc')

            # 해석례 노드 생성 (상세 정보 포함) - LLM 추출 결과 반환받음
            citations = create_interpretation_node(driver, interp_summary, interp_detail)

            # 기관 노드 생성 및 연결
            link_organizations(driver, interp_summary)

            # 관련 법령 연결 (상세 정보 사용) - INTERPRETS 생성
            link_to_law(driver, interp_summary, interp_detail)

            # LLM으로 추출한 인용 조문 연결 (INTERPRETS 이후 수행)
            # citations 가 있고, 그 안의 'cited_articles' 리스트가 비어 있지 않을 때
            if citations and citations.get('cited_articles'):
                cited_articles = citations['cited_articles']
                primary_law = citations.get('primary_law', '')

                # 출력용 라벨 만들기: {"article": "4", "paragraph": "1"} -> "제4조제1항"
                # cite['article']: 키가 없으면 KeyError -> 바깥 except 로 가서 이 해석례의 나머지가 건너뛰어진다
                # Build display labels for each citation
                cite_labels = []
                for cite in cited_articles:
                    label = f"제{cite['article']}조"
                    if cite.get('paragraph'):
                        label += f"제{cite['paragraph']}항"
                    if cite.get('item'):
                        label += f"제{cite['item']}호"
                    cite_labels.append(label)

                print(f"    → 조항호 상세 추출(LLM): {primary_law} {', '.join(cite_labels)}")

                link_cited_articles(driver, interp_id, cited_articles)

            if citations and citations.get('other_laws'):
                other_laws = citations['other_laws']
                # {'...' if len(other_laws) > 3 else ''} : 3개 넘으면 말줄임표
                print(f"       참조 법령 추출(LLM): {', '.join(other_laws[:3])}{'...' if len(other_laws) > 3 else ''}")
                link_cited_laws(driver, interp_id, other_laws)

        except Exception as e:
            print(f"ERROR: {str(e)}\n")

    print("=" * 80)
    print("[2단계] 법령해석례 그래프 구축 완료!")
    print("=" * 80)
