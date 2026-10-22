"""
[1단계: 읽기] pdf2kg_2.py (Stage 2: Chunk -> LLM 스키마 설계 -> 도메인 엔티티/관계) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
txt2kg, pdf2kg(Stage 1) 주석본에서 설명한 것은 짧게만 적었다.

흐름:
  Neo4j 의 Chunk 샘플 -LLM-> 그래프 스키마(글) -> Chunk 마다 "이 스키마대로 뽑아" -LLM-> JSON
  -> 엔티티 MERGE -> (Chunk)-[:HAS_ENTITY]->(엔티티) -> (엔티티)-[:동적 관계]->(엔티티)
전제: pdf2kg.py(Stage 1) 를 먼저 실행해서 Neo4j 에 Chunk 가 있어야 한다. 이 파일은 DB 를 지우지 않는다.
읽는 순서 권장: 맨 아래 __main__ -> generate_schema -> build_domain_graph -> process_chunk -> 나머지

실행 위치: part2/pdf2kg  ->  python learning/step1_pdf2kg_2_annotated.py  (LLM 을 Chunk 수만큼 부른다. 비용 주의)
"""

import os          # [출처] 표준 라이브러리. os.getenv 로 환경변수 읽기
import json        # [출처] 표준 라이브러리. json.loads(문자열) -> 파이썬 딕셔너리/리스트
import sys         # [출처] 표준 라이브러리. sys.exit
# [출처] 표준 라이브러리 textwrap
#   textwrap.dedent(문자열): 모든 줄에 공통으로 있는 앞쪽 들여쓰기를 지운다
#   [왜] 함수 안에서 """ 문자열을 코드 들여쓰기에 맞춰 써도, LLM 에는 들여쓰기 없는 깔끔한 글로 보내려고
import textwrap
from typing import List, Dict, Any, Optional, Tuple   # 타입 힌트 (실행에 영향 없음)
from dataclasses import dataclass                      # [출처] 표준 라이브러리. 데이터 그릇 클래스 만들기

from neo4j import GraphDatabase      # [출처] 외부 라이브러리 neo4j
from openai import OpenAI            # [출처] 외부 라이브러리 openai. OpenAI(api_key=...) 로 클라이언트 생성
from dotenv import load_dotenv       # [출처] 외부 라이브러리 python-dotenv

load_dotenv()

# ============================================
# 환경 변수 설정
# ============================================

NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")


# ============================================
# 데이터 클래스 (LLM 이 돌려준 JSON 을 담는 그릇)
# ============================================

@dataclass
class Entity:
    """추출된 엔티티"""
    entity_id: str
    entity_type: str               # 노드 레이블이 된다 (예: Organization)
    name: str                      # 같은 엔티티인지 판단하는 기준
    properties: Dict[str, Any]     # 나머지 속성들 {"속성명": 값}


@dataclass
class Relationship:
    """추출된 관계: (source)-[relationship_type]->(target)"""
    source_name: str
    source_type: str
    relationship_type: str
    target_name: str
    target_type: str
    properties: Dict[str, Any]


@dataclass
class ExtractionResult:
    """엔티티/관계 추출 결과 (Chunk 하나 분량)"""
    element_id: str
    entities: List[Entity]
    relationships: List[Relationship]


# ============================================
# Chunk 조회 함수
# ============================================

# max_chunks: int = 100 : 기본값이 있는 매개변수. 호출할 때 생략하면 100
def get_chunks(driver, max_chunks: int = 100) -> List[Dict]:
    """[이 파일에서 정의] Stage 1 이 만든 Chunk 중 내용이 20자 넘는 것을 최대 max_chunks 개 가져온다."""
    # size(문자열): Cypher 함수. 글자 수 / AS: 결과 열 이름 정하기 / LIMIT $limit: 최대 개수
    query = """
    MATCH (c:Chunk)
    WHERE c.content IS NOT NULL AND size(c.content) > 20
    RETURN c.chunk_id AS chunk_id,
           c.content AS content,
           c.toc_id AS toc_id
    LIMIT $limit
    """
    # driver.execute_query(쿼리, 파라미터딕셔너리, database_=...)
    # [입력] 두 번째 인자로 {"limit": 값} 딕셔너리를 넘기는 방식. limit=값 처럼 키워드로 넘겨도 같다
    # [반환] EagerResult. 튜플처럼 (records, summary, keys) 세 변수로 풀어 받을 수 있다
    #        records: 결과 행(Record) 리스트 / summary: 실행 요약 / keys: 열 이름 리스트
    records, summary, keys = driver.execute_query(
        query,
        {"limit": max_chunks},
        database_=NEO4J_DATABASE
    )
    # dict(record): Record -> 일반 딕셔너리 {"chunk_id": ..., "content": ..., "toc_id": ...}
    return [dict(record) for record in records]


# ============================================
# 스키마 자동 생성
# ============================================

# 매개변수를 여러 줄로 나눠 써도 된다 (괄호 안에서는 줄바꿈 자유)
def generate_schema(
    driver,
    openai_client: OpenAI,
    sample_size: int = 20
) -> str:
    """
    Neo4j에서 Chunk 샘플을 가져와 LLM이 적합한 그래프 스키마를 생성

    Args:
        driver: Neo4j driver
        openai_client: OpenAI 클라이언트
        sample_size: 샘플링할 Chunk 개수

    Returns:
        생성된 그래프 스키마 문자열 (마크다운 형태의 글. JSON 이 아니다)
        주의: 에러가 나면 아래 except 에서 return 이 없어 None 이 나간다 (GUIDE 생각해 볼 점 2)
    """
    print("\n" + "=" * 60)
    print("그래프 스키마 생성 중...")
    print("=" * 60)

    # Chunk 샘플 조회
    print(f"\nChunk 샘플 조회 중 (최대 {sample_size}개)...")
    samples = get_chunks(driver, max_chunks=sample_size)

    # 빈 리스트는 거짓 -> not samples 가 참
    if not samples:
        # raise 예외클래스("메시지"): [출처] 파이썬 기본. 일부러 에러를 내서 실행을 멈춘다
        # ValueError: 파이썬 기본 예외. "값이 잘못됐다" 는 뜻
        # 괄호 안에 문자열 두 개를 나란히 쓰면 자동으로 이어 붙는다 ("a" "b" == "ab")
        raise ValueError(
            "스키마 생성을 위한 Chunk 샘플을 찾을 수 없습니다. "
            "Neo4j에 Chunk 데이터가 존재하는지 확인하세요."
        )

    print(f"   {len(samples)}개 Chunk 샘플 수집 완료")

    # 샘플 텍스트 결합: "---" 줄로 구분해 하나의 긴 글로
    sample_texts = [s["content"] for s in samples]
    combined_samples = "\n\n---\n\n".join(sample_texts)

    # 스키마 생성 프롬프트 (system 메시지)
    # textwrap.dedent(f"""...""").strip(): 공통 들여쓰기 제거 -> 앞뒤 빈 줄 제거
    # 이 프롬프트에는 {변수} 가 없지만 f-string 으로 썼다 (f 를 빼도 결과는 같다)
    # <requirements> 같은 태그: 프롬프트를 구역별로 나눠 LLM 이 헷갈리지 않게 하는 관례
    schema_generation_prompt = textwrap.dedent(f"""
        당신은 지식그래프 설계 전문가입니다.
        주어진 문서 속 텍스트들을 분석하여, 이 문서에 적합한 지식그래프 스키마를 설계해주세요.

        <requirements>
        1. 위 텍스트들에서 추출할 수 있는 주요 엔티티 타입을 5-8개 정의하세요.
        2. 각 엔티티 타입의 주요 속성을 정의하세요.
        3. 엔티티 간의 관계 타입을 8-10개 정의하세요.
        4. 실제로 텍스트에 나타나는 정보를 기반으로 설계하세요.
        </requirements>

        <rules>
        1. 노드 타입과 관계 타입은 영문 PascalCase/UPPER_CASE로 작성하세요.
        2. 각 노드 타입과 관계 타입 옆에 한글 설명을 괄호로 함께 제공하세요.
        </rules>

        <output_format>
        ```
        ## 노드 타입 (Node Types)

        1. **EntityType1 (한글명)**
        - property1: string (설명)
        - property2: string (설명)

        2. **EntityType2 (한글명)**
        - property1: string (설명)

        ...

        ## 관계 타입 (Relationship Types)

        1. **RELATION_TYPE1** (EntityType1)-[:RELATION_TYPE1]->(EntityType2)
        - 관계 설명

        2. **RELATION_TYPE2** (EntityType2)-[:RELATION_TYPE2]->(EntityType3)
        - 관계 설명

        ...
        ```
        </output_format>
        """).strip()

    print("\nLLM에 스키마 생성 요청 중...")

    try:
        # openai_client.chat.completions.create(...)
        # [출처] 외부 라이브러리 openai
        # [입력] model: 모델 이름 / messages: [{"role": "system"|"user"|"assistant", "content": 글}, ...]
        #        temperature: 0~2, 낮을수록 같은 답. 설계는 약간의 다양성 허용(0.3)
        #        max_tokens: 답의 최대 길이(토큰)
        # [반환] ChatCompletion. 답 글은 response.choices[0].message.content
        # 여기서는 response_format 이 없다 -> 답이 JSON 이 아니라 자유로운 글(마크다운)
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": schema_generation_prompt
                },
                {
                    "role": "user",
                    # user 메시지에 실제 샘플을 넣는다. {combined_samples} 자리에 글이 들어간다
                    # 주의: dedent 는 "들여쓰기가 모든 줄에 공통일 때만" 지운다. 샘플 글의 둘째 줄부터는 들여쓰기가 없어서
                    #       여기서는 사실상 아무것도 지우지 못한다 (LLM 이 읽는 데 큰 문제는 없다)
                    "content": textwrap.dedent(f"""
                        <chunks>
                        {combined_samples}
                        </chunks>
                        위 텍스트 샘플들을 분석하여, 이 문서에 적합한 지식그래프 스키마를 설계해주세요.
                    """)
                }
            ],
            temperature=0.3,
            max_tokens=2000
        )

        schema = response.choices[0].message.content.strip()

        # ``` 제거: 출력 형식 예시에 코드블록이 있어서 LLM 이 ``` 로 감싸서 답하는 경우가 많다
        # "```" in schema : 문자열 안에 그 글자들이 있으면 True
        # 문자열.replace(찾을것, 바꿀것): [출처] 파이썬 기본 str 메서드. 모두 바꾼 새 문자열 반환
        if "```" in schema:
            schema = schema.replace("```", "").strip()

        print("\n생성된 스키마:")
        print("-" * 60)
        print(schema)
        print("-" * 60)
        print("스키마 생성 완료\n")

        return schema

    except Exception as e:
        print(f"\n스키마 생성 중 오류 발생: {e}")
        # 여기서 함수가 끝나면 return 이 없으므로 None 이 반환된다


# ============================================
# LLM 기반 엔티티/관계 추출 함수
# ============================================

def build_extraction_prompt(text: str, graph_schema: str) -> str:
    """[이 파일에서 정의] 추출용 system 프롬프트를 만든다. 스키마 글을 그대로 끼워 넣어 "이 안에서만 뽑아" 라고 제한한다.
    (text 매개변수는 받지만 쓰지 않는다. 실제 텍스트는 user 메시지로 따로 보낸다)"""
    # f-string 안에서 JSON 예시의 중괄호는 {{ }} 로 두 번 써야 글자 { } 가 된다. {graph_schema} 만 변수
    return textwrap.dedent(f"""
        당신은 텍스트에서 지식그래프를 추출하는 전문가입니다.
        아래 텍스트를 분석하여, 주어진 그래프 스키마에 맞는 엔티티(노드)와 관계를 추출해주세요.

        <graph_schema>
        {graph_schema}
        </graph_schema>

        <rules>
        1. 그래프 스키마에 정의된 노드 타입과 관계 타입만 사용하세요.
        2. 텍스트에 명시적으로 언급된 정보만 추출하세요.
        3. 엔티티 이름은 원문 그대로 사용하되, 불필요한 조사는 제거하세요.
        4. 관계는 두 엔티티가 모두 추출된 경우에만 생성하세요.
        5. 추출할 엔티티나 관계가 없으면 빈 배열을 반환하세요.
        </rules>

        반드시 아래 JSON 형식으로만 응답하세요. 다른 설명은 포함하지 마세요.
        <output_format>
        ```json
        {{
        "entities": [
            {{
            "entity_type": "스키마에 정의된 노드 타입",
            "name": "엔티티 이름 (고유 식별자로 사용)",
            "properties": {{
                "속성명": "속성값"
            }}
            }}
        ],
        "relationships": [
            {{
            "source_name": "출발 엔티티 이름",
            "source_type": "출발 엔티티 타입",
            "relationship_type": "스키마에 정의된 관계 타입",
            "target_name": "도착 엔티티 이름",
            "target_type": "도착 엔티티 타입",
            "properties": {{}}
            }}
        ]
        }}
        ```
        </output_format>
    """).strip()


def extract_entities_relationships(
    text: str,
    element_id: str,
    openai_client: OpenAI,
    graph_schema: str
) -> Optional[ExtractionResult]:
    """[이 파일에서 정의] Chunk 글 하나 -> LLM -> ExtractionResult. 실패해도 빈 결과를 돌려준다(예외를 밖으로 안 던짐)."""
    # 10자 미만이면 LLM 을 부르지 않고 빈 결과 (비용 절약)
    if not text or len(text.strip()) < 10:
        return ExtractionResult(element_id=element_id, entities=[], relationships=[])

    prompt = build_extraction_prompt(text, graph_schema)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": textwrap.dedent(f"""<text>
                        {text}
                        </text>
                        위 텍스트에서 그래프 스키마에 맞는 엔티티와 관계를 추출해주세요.
                    """)
                }
            ],
            # response_format={"type": "json_object"}: JSON 으로만 답하게 강제 -> json.loads 가 실패할 일이 줄어든다
            # (이 옵션을 쓰려면 프롬프트 어딘가에 "JSON" 이라는 단어가 있어야 한다)
            response_format={"type": "json_object"},
            temperature=0.1,      # 추출은 일관성 우선
            max_tokens=2000
        )

        # json.loads(문자열): [출처] 표준 라이브러리 json. JSON 글 -> 딕셔너리
        data = json.loads(response.choices[0].message.content)

        # Entity 객체 생성 (리스트 컴프리헨션)
        # data.get("entities", []): 키가 없으면 빈 리스트 -> LLM 이 키를 빼먹어도 에러 없이 넘어간다
        # enumerate(리스트): [출처] 파이썬 기본. (순번, 원소) 쌍. 순번은 0부터
        # e.get("entity_type", "Unknown"): 타입이 없으면 "Unknown"
        entities = [
            Entity(
                entity_id=f"{element_id}_e{idx}",     # 예: chunk_0003_e0
                entity_type=e.get("entity_type", "Unknown"),
                name=e.get("name", ""),
                properties=e.get("properties", {})
            )
            for idx, e in enumerate(data.get("entities", []))
        ]

        # Relationship 객체 생성
        relationships = [
            Relationship(
                source_name=r.get("source_name", ""),
                source_type=r.get("source_type", ""),
                relationship_type=r.get("relationship_type", ""),
                target_name=r.get("target_name", ""),
                target_type=r.get("target_type", ""),
                properties=r.get("properties", {})
            )
            for r in data.get("relationships", [])
        ]

        return ExtractionResult(
            element_id=element_id,
            entities=entities,
            relationships=relationships
        )

    except Exception as e:
        print(f"   추출 실패 ({element_id}): {e}")
        return ExtractionResult(element_id=element_id, entities=[], relationships=[])


# ============================================
# 도메인 지식그래프 구축 함수들
# ============================================

def sanitize_relationship_type(rel_type: str) -> str:
    """관계 타입을 Neo4j에 안전한 형식으로 변환
    [왜] 관계 타입은 파라미터($)로 못 넘기고 f-string 으로 쿼리에 직접 들어간다.
         LLM 이 "works for" 나 "]->(x) DELETE" 같은 글을 내놓으면 쿼리가 깨지거나 위험하다"""
    # import 를 함수 안에서 해도 된다 (이 함수가 처음 불릴 때 한 번 불러온다). 보통은 파일 맨 위에 쓴다
    import re    # [출처] 표준 라이브러리 re (정규표현식)
    # 영문, 숫자, 언더스코어만 허용
    # re.sub(패턴, 바꿀글자, 문자열): 패턴에 맞는 부분을 모두 바꾼 새 문자열
    #   r'...' : raw 문자열. \ 를 그대로 둔다 (정규식에서 자주 씀)
    #   [^A-Za-z0-9_] : 대괄호 안 ^ 는 "이것들이 아닌 글자". 즉 영문/숫자/_ 가 아닌 글자 하나
    #   예) "works for" -> "works_for", "소속" -> "__"
    safe_type = re.sub(r'[^A-Za-z0-9_]', '_', rel_type)
    # 대문자로 변환: 문자열.upper()  (Neo4j 관례: 관계 타입은 UPPER_CASE)
    safe_type = safe_type.upper()
    # 빈 문자열이거나 숫자로 시작하면 접두어 추가
    # safe_type[0]: 첫 글자 / 문자열.isdigit(): 모두 숫자면 True
    # 주의: not safe_type 를 먼저 검사해야 빈 문자열에서 [0] 에러가 안 난다 (or 는 앞이 참이면 뒤를 보지 않는다)
    if not safe_type or safe_type[0].isdigit():
        safe_type = f"REL_{safe_type}"
    return safe_type


def create_entity_node(driver, entity: Entity, entity_name_to_id: Dict[str, str]) -> str:
    """[이 파일에서 정의] 엔티티 노드 생성 또는 기존 노드 반환
    entity_name_to_id: {"타입:이름": 노드id} 딕셔너리. 함수 밖에서 만든 것을 받아 "제자리에서" 채운다
                       (딕셔너리는 참조로 전달되므로 여기서 넣은 값이 호출한 쪽에도 보인다)"""
    # 이미 생성된 엔티티인지 확인 (이름 + 타입으로 식별)
    entity_key = f"{entity.entity_type}:{entity.name}"

    if entity_key in entity_name_to_id:      # 딕셔너리에 키가 있는지 (in)
        return entity_name_to_id[entity_key]

    # 새 엔티티 노드 생성. len(entity_name_to_id): 지금까지 만든 개수 = 순번
    entity_node_id = f"entity_{entity.entity_type}_{len(entity_name_to_id)}"

    # MERGE (e:{타입} {name: $name}) : 그 레이블+이름의 노드가 있으면 찾고, 없으면 만든다
    # ON CREATE SET ... : "새로 만들었을 때만" 실행. 이미 있던 노드면 건너뛴다
    # e += $properties : 딕셔너리의 키/값을 속성으로 한꺼번에 추가 (= 는 전부 덮어쓰기, += 는 덧붙이기)
    # 주의: entity_type(레이블)은 sanitize 없이 f-string 에 들어간다 (GUIDE 생각해 볼 점 1)
    query = f"""
    MERGE (e:{entity.entity_type} {{name: $name}})
    ON CREATE SET e.entity_id = $entity_id, e += $properties
    RETURN e.entity_id AS id
    """

    try:
        driver.execute_query(
            query,
            {"name": entity.name, "entity_id": entity_node_id, "properties": entity.properties},
            database_=NEO4J_DATABASE
        )
        entity_name_to_id[entity_key] = entity_node_id    # 성공했을 때만 등록
        return entity_node_id

    except Exception as e:
        print(f"   엔티티 노드 생성 실패 ({entity.entity_type}): {e}")
        # 실패하면 None 반환, 그리고 딕셔너리에 등록되지 않는다 -> 이 엔티티가 낀 관계도 아래에서 빠진다


def create_relationship(driver, rel: Relationship, entity_name_to_id: Dict[str, str]):
    """[이 파일에서 정의] 관계 생성"""
    source_key = f"{rel.source_type}:{rel.source_name}"
    target_key = f"{rel.target_type}:{rel.target_name}"

    # 양쪽 엔티티가 모두 존재하는지 확인 (없으면 아무것도 하지 않고 끝)
    # return 만 쓰면 None 을 돌려주며 함수 종료
    if source_key not in entity_name_to_id or target_key not in entity_name_to_id:
        return

    # 관계 타입을 안전한 형식으로 변환
    safe_rel_type = sanitize_relationship_type(rel.relationship_type)

    # 동적 관계 타입을 사용한 Cypher 쿼리
    # MATCH (source {name: ...}) : 레이블 없이 이름으로만 찾는다 (GUIDE 생각해 볼 점 3: 같은 이름 다른 타입이면?)
    # MERGE (source)-[r:타입]->(target) : 같은 관계가 이미 있으면 새로 만들지 않는다
    # SET r += $properties : 관계에도 속성 덧붙이기
    query = f"""
    MATCH (source {{name: $source_name}})
    MATCH (target {{name: $target_name}})
    MERGE (source)-[r:{safe_rel_type}]->(target)
    SET r += $properties
    """

    try:
        driver.execute_query(
            query,
            {"source_name": rel.source_name, "target_name": rel.target_name, "properties": rel.properties},
            database_=NEO4J_DATABASE
        )
    except Exception as e:
        print(f"   관계 생성 실패 ({safe_rel_type}): {e}")


def link_entity_to_chunk(driver, entity_name: str, chunk_id: str):
    """[이 파일에서 정의] 엔티티를 Chunk에 HAS_ENTITY 관계로 연결 (이 엔티티가 어느 글에서 나왔는지 = 근거 추적)"""
    query = """
    MATCH (e {name: $entity_name})
    MATCH (c:Chunk {chunk_id: $chunk_id})
    MERGE (c)-[:HAS_ENTITY]->(e)
    """
    # 여기는 try 가 없다 -> 실패하면 예외가 process_chunk 를 거쳐 build_domain_graph 의 except 까지 올라간다
    driver.execute_query(
        query,
        {"entity_name": entity_name, "chunk_id": chunk_id},
        database_=NEO4J_DATABASE
    )


def process_chunk(
    driver,
    chunk: Dict,
    openai_client: OpenAI,
    graph_schema: str,
    entity_name_to_id: Dict[str, str]
) -> Tuple[int, int]:
    """[이 파일에서 정의] 단일 Chunk 처리: 추출 -> 엔티티 저장/연결 -> 관계 저장
    [반환] (뽑은 엔티티 수, 뽑은 관계 수). 실제로 저장에 성공한 수가 아니라 LLM 이 돌려준 수다"""
    chunk_id = chunk["chunk_id"]
    content = chunk["content"]

    # LLM으로 엔티티/관계 추출
    result = extract_entities_relationships(content, chunk_id, openai_client, graph_schema)

    if not result:
        return 0, 0       # 튜플 (0, 0) 반환

    # 엔티티 노드 생성 -> 바로 Chunk 와 연결
    # (순서 중요: 관계보다 엔티티를 먼저 만들어야 create_relationship 의 존재 확인을 통과한다)
    for entity in result.entities:
        create_entity_node(driver, entity, entity_name_to_id)
        link_entity_to_chunk(driver, entity.name, chunk_id)

    # 관계 생성
    for rel in result.relationships:
        create_relationship(driver, rel, entity_name_to_id)

    return len(result.entities), len(result.relationships)


def build_domain_graph(
    driver,
    openai_client: OpenAI,
    graph_schema: str,
    max_chunks: int = 100
):
    """[이 파일에서 정의] 도메인 그래프 구축: Chunk 를 하나씩 process_chunk 에 넣고 개수를 합산"""
    # 모든 Chunk 가 함께 쓰는 "이미 만든 엔티티" 목록. Chunk 가 달라도 같은 타입:이름이면 같은 노드로 본다
    entity_name_to_id = {}

    # Chunk 조회
    print("\nChunk 조회 중...")
    chunks = get_chunks(driver, max_chunks)
    print(f"   조회된 Chunk: {len(chunks)}개")

    if not chunks:
        print("처리할 Chunk가 없습니다.")
        return

    # 배치 처리 (실제로는 하나씩 순서대로)
    total_entities = 0
    total_relationships = 0

    for i, chunk in enumerate(chunks):
        chunk_id = chunk["chunk_id"]
        # [:50] 앞 50자, .replace("\n", " ") 줄바꿈을 공백으로 -> 한 줄 미리보기
        content_preview = chunk["content"][:50].replace("\n", " ") + "..."

        print(f"\n[{i+1}/{len(chunks)}] {chunk_id}")
        print(f"   내용: {content_preview}")

        # Chunk 하나가 실패해도 나머지는 계속 처리
        try:
            # 튜플 반환값을 두 변수로 풀어 받기
            entity_count, rel_count = process_chunk(
                driver, chunk, openai_client, graph_schema, entity_name_to_id
            )
            total_entities += entity_count
            total_relationships += rel_count

            print(f"   → 엔티티 {entity_count}개, 관계 {rel_count}개 추출")

        except Exception as e:
            print(f"   처리 실패: {e}")

    print("\n" + "=" * 60)
    print("도메인 지식그래프 구축 완료")
    print("=" * 60)
    print(f"   처리된 Chunk: {len(chunks)}개")
    print(f"   생성된 엔티티: {total_entities}개")       # 중복 포함 (Chunk 마다 센 합)
    print(f"   생성된 관계: {total_relationships}개")
    print(f"   고유 엔티티: {len(entity_name_to_id)}개")  # 중복 제거된 실제 노드 수


# ============================================
# 그래프 통계 및 검증
# ============================================

def print_graph_stats(driver):
    """[이 파일에서 정의] 그래프 통계 출력"""
    # 노드 통계
    # labels(n): 노드의 레이블 리스트 / [0]: 첫 번째 레이블 (TOC 노드는 Level1 등이 먼저 나올 수 있다)
    # count(n): 같은 label 끼리 묶어서 센다 (Cypher 는 집계 함수 옆의 열로 자동 그룹핑)
    # ORDER BY count DESC: 개수 많은 순
    node_query = """
    MATCH (n)
    RETURN labels(n)[0] AS label, count(n) AS count
    ORDER BY count DESC
    """
    records, summary, keys = driver.execute_query(node_query, database_=NEO4J_DATABASE)
    nodes = [dict(record) for record in records]
    print("\n노드 타입별 개수:")
    for row in nodes:
        print(f"   {row['label']}: {row['count']}개")    # f-string 안에서는 바깥과 다른 따옴표('')를 쓴다

    # 관계 통계. ()-[r]->() : 양 끝 노드는 아무거나. type(r): 관계 타입 이름
    rel_query = """
    MATCH ()-[r]->()
    RETURN type(r) AS rel_type, count(r) AS count
    ORDER BY count DESC
    """
    records, summary, keys = driver.execute_query(rel_query, database_=NEO4J_DATABASE)
    rels = [dict(record) for record in records]
    print("\n관계 타입별 개수:")
    for row in rels:
        print(f"   {row['rel_type']}: {row['count']}개")

    # 엔티티 타입별 통계 (Chunk, Document 등 제외)
    # NOT n:Chunk : Chunk 레이블이 없는 노드만 -> Stage 1 의 문서 구조 노드를 빼고 Stage 2 의 도메인 노드만 남긴다
    entity_type_query = """
    MATCH (n)
    WHERE NOT n:Chunk AND NOT n:Document AND NOT n:TOC AND NOT n:TextElement AND NOT n:TableElement
    RETURN labels(n)[0] AS entity_type, count(n) AS count
    ORDER BY count DESC
    """
    records, summary, keys = driver.execute_query(entity_type_query, database_=NEO4J_DATABASE)
    entity_types = [dict(record) for record in records]
    if entity_types:
        print("\n도메인 엔티티 타입별 개수:")
        for row in entity_types:
            print(f"   {row['entity_type']}: {row['count']}개")


# ============================================
# 메인
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("PDF 지식 그래프 추출 - (2) 도메인 엔티티/관계 추출")
    print("=" * 50)

    MAX_CHUNKS = 100            # 추출할 Chunk 최대 수 = LLM 호출 수. 처음엔 작게 (예: 3)
    SCHEMA_SAMPLE_SIZE =100     # 스키마 설계에 보여 줄 샘플 수 (많으면 프롬프트가 길어진다)

    # os.getenv("키", 기본값): 환경변수가 없으면 기본값
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    print(f"\nNeo4j 연결: {NEO4J_URI}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        # driver.verify_connectivity(): 연결이 되는지 미리 확인. 안 되면 예외 -> finally 로 가서 close
        driver.verify_connectivity()

        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        # 1) 스키마 설계 (LLM 1회)
        graph_schema = generate_schema(
            driver,
            openai_client,
            sample_size=SCHEMA_SAMPLE_SIZE
        )

        # 2) 스키마대로 Chunk 마다 추출 (LLM 최대 MAX_CHUNKS 회)
        build_domain_graph(
            driver,
            openai_client,
            graph_schema,
            max_chunks=MAX_CHUNKS
        )

        # 3) 결과 확인
        print_graph_stats(driver)

    finally:
        driver.close()
