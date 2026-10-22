"""
[1단계: 읽기] txt2kg.py 의 상세 주석 버전 (코드는 원본과 동일)

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
csv2kg 의 step1 에서 설명한 것(load_dotenv, os.getenv, execute_query, try/except 등)은 짧게만 적었다.

흐름: 텍스트 읽기 -> 청크로 자르기 -> 청크마다 LLM 으로 엔티티/관계 추출 -> 합치고 중복 제거 -> 검증 -> JSON 저장 -> Neo4j 저장
읽는 순서 권장: 맨 아래 main() -> 위에서부터 함수 순서대로

실행 위치: part2/txt2kg  ->  python learning/step1_annotated.py  (원본과 똑같이 동작. DB 를 지우고 저장한다)
"""

# ============================================================
# import
# ============================================================

# [출처] 표준 라이브러리 json. 파이썬 dict/list <-> JSON 문자열 변환 (json.loads, json.dump)
import json
# [출처] 표준 라이브러리 os. 환경변수 읽기 (csv2kg step1 참고)
import os
# [출처] 표준 라이브러리 textwrap
# [왜]   textwrap.dedent: 여러 줄 문자열의 "공통 들여쓰기"를 지워 준다. 코드 안에서 들여 쓴 프롬프트를 깔끔하게 보내려고
import textwrap

# [출처] 외부 라이브러리 python-dotenv. .env -> 환경변수
from dotenv import load_dotenv
# [출처] 외부 라이브러리 langchain-text-splitters (pip install langchain-text-splitters)
#   RecursiveCharacterTextSplitter: 긴 글을 정해진 길이 이하의 조각(청크)으로 나눠 주는 도구
from langchain_text_splitters import RecursiveCharacterTextSplitter
# [출처] 외부 라이브러리 neo4j 드라이버
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 openai (pip install openai). OpenAI API 를 부르는 공식 SDK
#   OpenAI: API 클라이언트 클래스. OpenAI(api_key=...) 로 만들고 client.chat.completions.create(...) 로 호출
from openai import OpenAI

load_dotenv()

# ============================================
# 환경 변수 설정
# ============================================

NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")  # AuraDB 는 DB 이름 = 사용자 이름


# ============================================
# 1단계: 텍스트 청킹
# 하는 이유: LLM 에 너무 많은 글을 한 번에 주면 엔티티를 빠뜨리거나 뭉뚱그린다. 짧게 나눠 주면 꼼꼼해진다
# ============================================

# 매개변수=기본값 : 호출할 때 생략하면 기본값이 쓰인다. split_text_into_chunks(text) 만 써도 된다
def split_text_into_chunks(text, chunk_size=500, chunk_overlap=100):
    """[이 파일에서 정의] 텍스트를 청크(문자열) 리스트로 나눈다."""

    # RecursiveCharacterTextSplitter(...)
    # [출처] langchain-text-splitters
    # [입력] chunk_size: 청크 하나의 최대 길이 (length_function 기준. 여기서는 글자 수)
    #        chunk_overlap: 이웃 청크끼리 겹치게 할 길이. 문장이 경계에서 잘려 주어/목적어가 갈라지는 일을 줄인다
    #        length_function: 길이를 재는 함수. len 은 파이썬 기본 함수(글자 수). 괄호 없이 함수 자체를 넘긴다
    #        separators: 자를 위치 후보. 앞에서부터 시도한다 -> 문단(\n\n) > 줄(\n) > 문장(". ") > 단어(" ") > 글자("")
    #                    "가능한 큰 단위에서 먼저 자른다" 그래서 Recursive(재귀) 라는 이름
    # [반환] 분할기 객체
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # text_splitter.split_text(문자열)
    # [출처] langchain-text-splitters
    # [입력] 긴 문자열 하나
    # [반환] 문자열 리스트 (청크들)
    chunks = text_splitter.split_text(text)

    print(f"텍스트 분할: {len(text)}자 -> {len(chunks)}개 청크")   # len(문자열) = 글자 수, len(리스트) = 개수

    return chunks


# ============================================
# 2단계: 지식 추출 (LLM)
# ============================================

def extract_knowledge_from_chunk(chunk, chunk_idx, api_key, model="gpt-4o"):
    """[이 파일에서 정의] 청크 하나를 LLM 에 보내 {"entities": [...], "relations": [...]} 딕셔너리로 받는다."""

    # OpenAI(api_key=...)
    # [출처] openai SDK
    # [입력] api_key: API 키 문자열 (생략하면 환경변수 OPENAI_API_KEY 를 자동으로 읽는다)
    # [반환] 클라이언트 객체
    # 참고: 청크마다 새로 만들고 있다. 한 번 만들어 재사용해도 된다
    client = OpenAI(api_key=api_key)

    # textwrap.dedent("""...""").strip()
    # [출처] dedent: 표준 라이브러리 textwrap / strip: 파이썬 기본 str 메서드
    # [반환] 공통 들여쓰기와 앞뒤 공백을 지운 문자열
    # 프롬프트 구조 (XML 처럼 <태그> 로 구역을 나눴다. LLM 이 구역을 구분하기 쉽다):
    #   <extraction_strategy> 동사를 먼저 찾고 주어/목적어를 정하는 "관계 우선" 전략
    #   <rules>               엔티티/속성/관계 규칙. 특히 피동형 "A는 B에 의해 ~된다" -> (B)->(A) 처럼 방향 규칙
    #   <examples>            규칙만으로 모호한 경우를 예시로 고정 (few-shot)
    #   <output_format>       받고 싶은 JSON 모양. evidence(원문 문장)는 나중에 근거를 추적하려고 받는다
    # 주의: 이 문자열은 f-string 이 아니라서 { } 를 그대로 쓸 수 있다
    system_prompt = textwrap.dedent("""
        당신은 텍스트에서 지식 그래프를 추출하는 전문가입니다. 반드시 JSON 형식으로 응답하세요.

        <extraction_strategy>
        **관계 우선 추출 (Relation-First Extraction)**:
        1. 문장에서 동사/서술어를 먼저 찾는다
        2. 그 동사의 실제 주어(agent)와 목적어(patient)를 정확히 식별한다
        3. 상위 개념이 아닌, 문장에서 직접 언급된 구체적인 개념을 엔티티로 사용한다
        4. 정보 손실 없이 원문의 의미를 최대한 보존한다
        </extraction_strategy>

        <rules>
        **엔티티 추출 규칙**:
        - 문장에서 직접 언급된 구체적인 개념을 추출 (추상화하지 말 것)
        - 각 엔티티에는 반드시 "name"과 "type"을 포함해야 함
        - type은 엔티티의 범주를 나타냄 (예: 인물, 장소, 조직, 개념, 물질, 기술 등)
        - "A는 B에 의해 C된다" → A와 B 둘 다 엔티티로 추출
        - "A의 B" → A와 B 각각 별도 엔티티
        - 상위 개념보다 하위/구체적 개념을 우선 추출
        - 열거형 "A, B, C" → 각각 별도 엔티티
        - 중간 매개체(~에 의해, ~를 통해, ~로 인해)는 반드시 엔티티로 추출

        **속성(properties) 추출 규칙** - 엔티티가 아닌 부가정보 예시:
        - 숫자/수량 → {"count": "값", "unit": "단위"}
        - 연도/날짜 → {"year": "연도", "date": "날짜"}
        - 위치/장소 → {"location": "장소"}
        - 역할/기능 → {"role": "역할"}
        - 영어명/별칭 → {"english_name": "영어명", "alias": "별칭"}
        - 국적/출신 → {"nationality": "국적"}
        - 직업/직함 → {"profession": "직업"}
        - 화학식/공식 → {"formula": "공식"}
        - 수식어/형용사적 정보는 엔티티가 아닌 properties로

        **관계 추출 규칙**:
        - 관계 라벨(type)은 반드시 영어 대문자와 언더스코어로 작성
        - 피동형 "A는 B에 의해 ~된다" → (B)-[동사]->(A)
        - 능동형 "A는 B를 ~한다" → (A)-[동사]->(B)
        - 구성 "A는 B로 구성된다" → (A)-[COMPOSED_OF]->(B)
        - 하나의 문장에서 여러 관계가 있으면 모두 추출
        - 관계의 부가정보(연도, 장소 등)는 관계의 properties에 저장

        **관계 라벨 작성 가이드**:
        - 문장의 동사/서술어를 기반으로 의미가 명확한 영어 관계 라벨을 선택하세요
        - 아래는 일반적인 카테고리별 예시일 뿐이며, 문맥에 맞는 다른 라벨을 자유롭게 생성하세요
        - 예시 카테고리:
          * 구성/포함: COMPOSED_OF, CONTAINS, INCLUDES 등
          * 생성/형성: FORMS, CREATES, PRODUCES 등
          * 연결/상호작용: BINDS_TO, INTERACTS_WITH 등
          * 위치/소속: LOCATED_IN, PART_OF 등
          * 유래/기원: DERIVED_FROM, ORIGINATES_FROM 등
          * 작용/영향: CAUSES, AFFECTS, REGULATES 등
          * 변환/전환: CONVERTS_TO, TRANSFORMS_INTO 등
        </rules>

        <examples>
        예시 1 - 피동형 문장:
        원문: "X는 Y에 의해 형성된다"
        → 엔티티: [{"name": "X", "type": "구조"}, {"name": "Y", "type": "구성요소"}]
        → 관계: (Y)-[FORMS]->(X)

        예시 2 - 구성 관계:
        원문: "A는 B와 C로 구성된다"
        → 엔티티: [{"name": "A", "type": "구조"}, {"name": "B", "type": "구성요소"}, {"name": "C", "type": "구성요소"}]
        → 관계: (A)-[COMPOSED_OF]->(B), (A)-[COMPOSED_OF]->(C)

        예시 3 - 수량 정보:
        원문: "100개의 X가 Y를 이룬다"
        → 엔티티: [{"name": "X", "type": "구성요소", "properties": {"count": "100"}}]
        → 관계: (X)-[FORMS]->(Y)

        예시 4 - 인물과 행위:
        원문: "1900년 독일의 과학자 A가 B를 발견했다"
        → 엔티티: [{"name": "A", "type": "인물", "properties": {"nationality": "독일", "profession": "과학자"}}, {"name": "B", "type": "개념"}]
        → 관계: (A)-[DISCOVERED]->(B) with properties: {"year": "1900"}

        예시 5 - 별칭/영어명:
        원문: "A(영어명: X)는 B에서 유래했다"
        → 엔티티: [{"name": "A", "type": "개념", "properties": {"english_name": "X"}}, {"name": "B", "type": "개념"}]
        → 관계: (A)-[DERIVED_FROM]->(B)

        예시 6 - 복합 문장:
        원문: "A는 B를 통해 C에 작용한다"
        → 엔티티: [{"name": "A", "type": "개념"}, {"name": "B", "type": "개념"}, {"name": "C", "type": "개념"}]
        → 관계: (A)-[USES]->(B), (A)-[AFFECTS]->(C)
        </examples>

        <output_format>
        {
        "entities": [
            {"name": "엔티티명", "type": "타입", "properties": {"key": "value"}}
        ],
        "relations": [
            {
            "source": "엔티티명(실제 행위자/원인)",
            "target": "엔티티명(행위 대상/결과)",
            "type": "ENGLISH_RELATION_TYPE",
            "properties": {"key": "value"},
            "evidence": "엔티티와 관계를 추출한 원본 문장(원문에서 발췌)"
            }
        ]
        }
        </output_format>
    """).strip()

    # try/except: LLM 호출이나 JSON 파싱이 실패해도 프로그램 전체가 멈추지 않게
    try:
        # client.chat.completions.create(...)
        # [출처] openai SDK. 채팅 모델을 호출하는 가장 기본 API
        # [입력] model: 모델 이름
        #        messages: 대화 목록. 각 항목은 {"role": "system"|"user"|"assistant", "content": 글}
        #                  system = 역할과 규칙 / user = 이번 요청
        #        response_format={"type": "json_object"}: 응답을 반드시 JSON 문법으로 하게 강제 (필드가 빠지는 건 막지 못한다)
        #        temperature=0: 무작위성을 최소로. 같은 입력에 최대한 같은 출력 (추출 작업은 일관성이 중요)
        # [반환] ChatCompletion 객체. 답변 글은 response.choices[0].message.content (문자열)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    # f"""...""" : 여러 줄 f-string. {chunk} 자리에 청크 글이 들어간다
                    "content": textwrap.dedent(f"""
                        <text>
                        {chunk}
                        </text>
                        위 텍스트에서 지식 그래프를 추출하세요.
                    """),
                },
            ],
            response_format={"type": "json_object"},  # json 응답 강제
            temperature=0,
        )

        # json.loads(문자열)
        # [출처] 표준 라이브러리 json
        # [입력] JSON 형식 문자열
        # [반환] 파이썬 dict / list (JSON 객체 -> dict, 배열 -> list)
        # [왜]   LLM 응답은 글(문자열)이라, 파이썬에서 result["entities"] 처럼 쓰려면 변환해야 한다
        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        # str(e): 에러 객체를 메시지 문자열로 / chunk_idx+1: 사람이 보기 좋게 1부터
        print(f"  청크 {chunk_idx+1} 오류: {str(e)}")
        # 실패한 청크는 빈 결과로 처리 -> 다른 청크는 계속 진행된다
        return {"entities": [], "relations": []}


def extract_knowledge_batch(chunks, api_key, model="gpt-4.1"):
    """[이 파일에서 정의] 모든 청크에서 추출하고, 엔티티는 이름으로 합치고 관계는 중복을 지운다.
    참고: 기본값은 gpt-4.1 이지만 main() 이 model="gpt-4o" 를 넘기므로 실제로는 gpt-4o 로 돈다."""

    print(f"\n지식 추출 중 ({len(chunks)}개 청크)...")

    all_entities = []
    all_relations = []

    # enumerate(리스트) : (번호, 값) 을 차례로. 시작번호를 안 주면 0부터
    for i, chunk in enumerate(chunks):
        # print(..., end=" ") : 끝에 줄바꿈 대신 공백을 찍는다 -> 다음 print 가 같은 줄에 이어서 나온다
        print(f"  청크 {i+1}/{len(chunks)}...", end=" ")

        result = extract_knowledge_from_chunk(chunk, i, api_key, model)

        # 딕셔너리.get(키, 기본값)
        # [출처] 파이썬 기본 dict 메서드
        # [반환] 키가 있으면 값, 없으면 기본값 (result["entities"] 는 키가 없으면 KeyError 로 멈춘다)
        # [왜]   LLM 이 entities 키를 빠뜨려도 멈추지 않게
        entities = result.get("entities", [])
        relations = result.get("relations", [])

        # 리스트.extend(다른리스트)
        # [출처] 파이썬 기본 list 메서드
        # [왜]   append 는 리스트 "통째로" 1개를 넣고, extend 는 "원소들을 하나씩" 이어 붙인다
        all_entities.extend(entities)
        all_relations.extend(relations)

        print(f"엔티티 {len(entities)}개, 관계 {len(relations)}개")

        # if 리스트: -> 비어 있지 않으면 True (빈 리스트, 빈 문자열, 0, None 은 모두 False 로 취급)
        if entities:
            # [식 for 변수 in 리스트] : 리스트 컴프리헨션. 각 원소에서 name 만 뽑은 새 리스트
            entity_names = [e.get("name") for e in entities]
            # "구분자".join(문자열리스트)
            # [출처] 파이썬 기본 str 메서드
            # [반환] 리스트 원소들을 구분자로 이어 붙인 문자열 ["a","b"] -> "a, b"
            print(f"    → 엔티티: {', '.join(entity_names)}", end="")
            print()   # 인자 없는 print(): 줄바꿈만

        if relations:
            for j, rel in enumerate(relations):
                source = rel.get("source", "?")
                target = rel.get("target", "?")
                rel_type = rel.get("type", "?")
                evidence = rel.get("evidence", "")
                # \" : 문자열 안에서 큰따옴표 쓰기 (이스케이프)
                print(f"    → 관계 {j+1}: ({source})-[{rel_type}]->({target}) with evidence: \"{evidence}\"")
        print()

    # ---- 엔티티 합치기: 이름이 같으면 하나로 ----
    unique_entities = {}   # {이름: 엔티티딕셔너리}
    for entity in all_entities:
        name = entity.get("name")
        if not name:
            continue   # continue: 이번 반복은 건너뛰고 다음 원소로

        # 키 in 딕셔너리 : 그 키가 있으면 True
        if name not in unique_entities:
            unique_entities[name] = entity
        else:
            # 이미 있는 이름이면 속성(properties)만 합친다
            existing = unique_entities[name]
            existing_props = existing.get("properties", {})
            new_props = entity.get("properties", {})
            # {**a, **b} : 딕셔너리 두 개를 펼쳐 합친 새 딕셔너리. 같은 키는 뒤(b)의 값이 이긴다
            existing["properties"] = {**existing_props, **new_props}

    # ---- 관계 중복 제거: (출발, 도착, 타입)이 같으면 하나만 ----
    unique_relations = []
    # set() : 집합. 중복 없이 값을 담고, "in" 검사가 리스트보다 훨씬 빠르다
    seen = set()
    for rel in all_relations:
        # (a, b, c) : 튜플. 바뀌지 않는 값 묶음이라 집합이나 딕셔너리의 키로 쓸 수 있다 (리스트는 못 쓴다)
        key = (rel.get("source"), rel.get("target"), rel.get("type"))
        # all(값들)
        # [출처] 파이썬 기본 함수
        # [반환] 모든 값이 참이면 True. 셋 중 하나라도 None 이나 빈 문자열이면 False
        # [왜]   출발/도착/타입이 빠진 불완전한 관계는 버리려고
        if key not in seen and all(key):
            seen.add(key)            # 집합.add(값): 집합에 넣기
            unique_relations.append(rel)

    # 딕셔너리.values() : 값들만 / list(...) : 리스트로 변환
    entities_list = list(unique_entities.values())

    print(f"\n추출 완료:")
    print(f"  엔티티: {len(entities_list)}개")
    print(f"  관계: {len(unique_relations)}개")

    return {"entities": entities_list, "relations": unique_relations}


# ============================================
# 3단계: 검증
# ============================================

def validate_knowledge_graph(kg):
    """[이 파일에서 정의] 엔티티 목록에 없는 이름을 가리키는 관계를 버린다.
    [왜] LLM 은 엔티티 목록에 없는 이름을 관계에 쓰기도 한다. 그대로 저장하면 MATCH 가 실패해 관계가 조용히 사라진다."""

    print("\n검증 중...")

    # {식 for 변수 in 리스트} : 집합 컴프리헨션 (중괄호 + 키:값이 없으면 집합). 이름들의 집합
    entity_names = {e["name"] for e in kg["entities"]}

    valid_relations = []
    invalid_count = 0

    for rel in kg["relations"]:
        # and : 둘 다 참일 때만 참
        if rel["source"] in entity_names and rel["target"] in entity_names:  # source/target 존재 확인
            valid_relations.append(rel)
        else:
            invalid_count += 1   # += 1 : 1 더해서 다시 저장 (invalid_count = invalid_count + 1)

    kg["relations"] = valid_relations   # 딕셔너리의 값 바꾸기

    print(f"  유효 관계: {len(valid_relations)}개")
    if invalid_count:
        print(f"  제거된 관계: {invalid_count}개")

    return kg


# ============================================
# 4단계: Neo4j 저장
# ============================================

def save_to_neo4j(kg, driver):
    """[이 파일에서 정의] 엔티티를 노드로, 관계를 관계로 저장한다. 레이블/관계 타입은 LLM 이 정한 값을 쓴다."""
    print("\nNeo4j 저장 중...")

    entities = kg.get("entities", [])
    relations = kg.get("relations", [])

    try:
        # 1. 기존 데이터 삭제 (csv2kg step1 의 clear_database 와 같다)
        driver.execute_query(
            "MATCH (n) DETACH DELETE n",
            database_=NEO4J_DATABASE,
        )
        print("  기존 데이터 삭제 완료")

        # 2. 노드 생성
        # 함수 안에 함수 정의 (중첩 함수): 이 함수 안에서만 쓰는 도우미
        def create_nodes(tx, entities_list):
            """트랜잭션 함수: 모든 노드 생성
            tx: 드라이버가 만들어서 넣어 주는 트랜잭션 객체. tx.run(쿼리, 파라미터) 로 쿼리를 보낸다"""
            created_count = 0
            for entity in entities_list:
                name = entity["name"]
                # 문자열.replace(찾을것, 바꿀것) : [출처] 파이썬 기본 str. 백틱(`)을 지운다
                # [왜] 레이블은 아래에서 `레이블` 처럼 백틱으로 감싸 쿼리에 넣는데, 값 안에 백틱이 있으면 쿼리가 깨진다
                node_type = entity.get("type", "Entity").replace("`", "").strip()
                props = entity.get("properties", {})

                # 속성을 Cypher 파라미터로 변환: {"year": "1900"} -> ", year: $year"
                # 딕셔너리.keys() : 키들만
                props_str = ", ".join([f"{k}: ${k}" for k in props.keys()])
                if props_str:
                    props_str = ", " + props_str

                # 레이블은 $파라미터로 넘길 수 없어서 f-string 으로 넣고 백틱으로 감싼다 (한글 레이블도 가능해진다)
                # {{ }} : f-string 안에서 진짜 중괄호 문자를 쓰려면 두 번 쓴다 (Cypher 의 속성 { } 용)
                # MERGE: 같은 레이블+속성의 노드가 있으면 재사용, 없으면 생성
                #   주의: 여기서는 name 뿐 아니라 모든 속성이 MERGE 조건에 들어간다 (GUIDE.md 생각해 볼 점 1)
                query = f"MERGE (n:`{node_type}` {{name: $name{props_str}}})"

                # tx.run(쿼리, 키워드인자들)
                # [출처] neo4j 드라이버 Transaction.run
                # [입력] 쿼리, 그리고 $이름 에 들어갈 값들 (이름=값)
                # **props : 딕셔너리를 "이름=값" 키워드 인자들로 펼친다. {"year": "1900"} -> year="1900"
                tx.run(query, name=name, **props)
                created_count += 1

            return created_count

        # with 객체 as 변수: -> 블록이 끝나면 객체를 자동으로 정리(여기서는 세션 닫기)하는 문법
        # driver.session(database=...)
        # [출처] neo4j 드라이버
        # [반환] Session 객체. 여러 쿼리/트랜잭션을 묶어 실행하는 단위
        with driver.session(database=NEO4J_DATABASE) as session:
            # session.execute_write(함수, 그함수에줄인자...)
            # [출처] neo4j 드라이버
            # [입력] 첫 인자가 tx 인 함수, 그 함수에 넘길 나머지 인자들
            # [반환] 그 함수가 return 한 값
            # [왜]   함수 안의 모든 tx.run 이 "하나의 쓰기 트랜잭션"으로 묶인다. 중간에 실패하면 전부 롤백(없던 일로).
            #        일시적 오류(네트워크 등)가 나면 드라이버가 함수를 통째로 다시 실행해 준다
            node_count = session.execute_write(create_nodes, entities)
            print(f"  {node_count}개 노드 생성 완료")

        # 3. 관계 생성
        def create_relations(tx, relations_list):
            """트랜잭션 함수: 모든 관계 생성"""
            created_count = 0
            for rel in relations_list:
                rel_type = rel["type"].replace("`", "").strip()
                evidence = rel.get("evidence", "")
                props = rel.get("properties", {})

                # evidence 를 관계 속성에도 넣는다 (근거 문장 추적용)
                props["evidence"] = evidence

                props_str = ", ".join([f"{k}: ${k}" for k in props.keys()])

                # MATCH (source {name: $source}) : 레이블 없이 name 으로만 찾는다 (GUIDE.md 생각해 볼 점 2)
                # {{{props_str}}} : 바깥 {{ }} 는 진짜 중괄호, 안쪽 {props_str} 는 f-string 자리
                query = f"""
                MATCH (source {{name: $source}})
                MATCH (target {{name: $target}})
                CREATE (source)-[r:`{rel_type}` {{{props_str}}}]->(target)
                """
                tx.run(query, source=rel["source"], target=rel["target"], **props)
                created_count += 1

            return created_count

        with driver.session(database=NEO4J_DATABASE) as session:
            rel_count = session.execute_write(create_relations, relations)
            print(f"  {rel_count}개 관계 생성 완료")

        print("  완료!")

    except Exception as e:
        print(f"  오류: {e}")


# ============================================
# 메인
# ============================================

def main():
    """[이 파일에서 정의] 전체 실행 순서"""
    print("=" * 50)
    print("지식 그래프 추출")
    print("=" * 50)

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

    MODEL = "gpt-4o"
    INPUT_FILE = "wiki_protein.txt"      # 상대 경로: 실행한 위치(part2/txt2kg) 기준
    # INPUT_FILE = "wiki_bus.txt"        # 앞의 # 를 옮기면 다른 텍스트로 실험
    OUTPUT_FILE = "knowledge_graph.json"

    print(f"\n텍스트 로드: {INPUT_FILE}")
    # open(경로, 모드, encoding=...)
    # [출처] 파이썬 기본 함수
    # [입력] 경로, 모드("r" 읽기 / "w" 쓰기(덮어씀) / "a" 이어쓰기), encoding: 글자 인코딩 (한글이 있으면 "utf-8" 지정)
    # [반환] 파일 객체. with 와 함께 쓰면 블록이 끝날 때 자동으로 닫힌다
    # f.read() : 파일 전체를 문자열 하나로 읽는다
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    print(f"  {len(text)}자")

    # 1. 청킹
    chunks = split_text_into_chunks(text, chunk_size=500, chunk_overlap=100)

    # 2. 지식그래프(엔티티, 관계) 추출
    kg = extract_knowledge_batch(chunks, OPENAI_API_KEY, model=MODEL)

    # 3. 검증
    kg = validate_knowledge_graph(kg)

    # 4. JSON 저장
    print(f"\n추출 결과 JSON 저장: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # json.dump(데이터, 파일, ensure_ascii=False, indent=2)
        # [출처] 표준 라이브러리 json
        # [입력] ensure_ascii=False: 한글을 \uXXXX 로 바꾸지 않고 그대로 저장
        #        indent=2: 사람이 읽기 좋게 2칸 들여쓰기
        # [반환] 없음. 파일에 쓴다 (문자열로 받고 싶으면 json.dumps)
        json.dump(kg, f, ensure_ascii=False, indent=2)

    # 5. Neo4j 저장 (접속 정보가 모두 있을 때만)
    if NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD:
        print(f"\nNeo4j 연결: {NEO4J_URI}")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        try:
            driver.verify_connectivity()
            save_to_neo4j(kg, driver)
        except Exception as e:
            print(f"  연결 실패: {e}")
        finally:
            driver.close()   # 에러가 나도 연결은 닫는다

    print("\n" + "=" * 50)
    print("샘플 결과:")
    print("=" * 50)

    print("\n[엔티티 샘플]")
    # 리스트[:5] : 앞 5개만
    for e in kg["entities"][:5]:
        props = e.get("properties", {})
        # 값1 if 조건 else 값2 : 조건부 표현식 (한 줄 if). 속성이 있으면 앞에 공백을 붙여 출력, 없으면 빈 문자열
        props_str = f" {props}" if props else ""
        print(f"  ({e['name']}) [{e.get('type', '?')}]{props_str}")

    print("\n[관계 샘플]")
    for r in kg["relations"][:5]:
        props = r.get("properties", {})
        props_str = f" {props}" if props else ""
        print(f"  ({r['source']})-[{r['type']}]->({r['target']}){props_str}")

    print(f"\n최종: 엔티티 {len(kg['entities'])}개, 관계 {len(kg['relations'])}개")


if __name__ == "__main__":
    main()
