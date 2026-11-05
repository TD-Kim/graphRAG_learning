"""[1단계: 읽기] graphrag_reasoning.py (막연한 증상 질문 -> 추론용 Cypher -> 그래프를 여러 홉 따라가 모으기 -> 추론 과정을 설명하는 답변) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(neo4j-graphrag 1.14.1, requirements.txt 기준)로 확인했다. openai 는 1.109.1.

전제: Part 2 medical2kg 로 의료 지식그래프가 Neo4j 에 들어 있어야 한다. .env 에 NEO4J_*, OPENAI_API_KEY 필요.
구조는 part3/text2cypher/text2cypher.py 와 같다. 먼저 그 파일의 주석본을 읽었다면 바뀐 부분만 보면 된다.

이 파일의 "추론(reasoning)" 이란
  사용자가 A(예: 기침)만 말해도 그래프 관계를 따라가 B(질병), C(동반 증상), D(치료/약물)까지 모으는 것.
  LLM 혼자 머릿속으로 추론하는 것이 아니라, 그래프의 경로(Symptom -> Disease -> Treatment)가 추론의 뼈대가 된다.
  다중 홉(multi-hop): 관계를 두 번 이상 건너가는 것. "증상 -INDICATES-> 질병 <-TREATS- 치료" 는 2홉.

text2cypher.py 와 다른 점 3가지
  1) custom_prompt: 라이브러리 기본 Cypher 프롬프트 대신 "추론 경로, 질문 분석 단계, 항상 OPTIONAL MATCH" 규칙을 담은 프롬프트
  2) 예제: 질문 -> 쿼리 만이 아니라 "사용자가 말한 것 / 시스템이 추론할 것 / 경로" 를 같이 보여 준다 (생각 과정 시연)
  3) 커스텀 Retriever(Text2CypherWithQueryRetriever): 답변 LLM 에게 결과 행뿐 아니라 "실행된 Cypher" 도 같이 준다

흐름 (LLM 을 두 번 부른다)
  질문 "기침이 심해요"
    -> [Text2CypherWithQueryRetriever.search]
         부모 search: custom_prompt 의 {schema} {examples} {query_text} 를 채워 LLM(1번째) -> Cypher 글
                      -> Neo4j 에서 읽기 전용 실행 -> Record 마다 item(content = str(Record))
         그 다음 (이 파일에서 추가): Cypher + 모든 결과 글을 합쳐 item "하나" 로 바꿈
    -> [GraphRAG] 그 글을 {context} 에, 질문을 {query_text} 에 넣은 답변 프롬프트 -> LLM(2번째) -> 답변 (추론 과정 설명 + 의료 안내 문구)

읽는 순서 권장: main -> get_example_queries -> get_reasoning_text2cypher_prompt -> Text2CypherWithQueryRetriever
               -> create_graphrag_pipeline -> get_medical_schema / schema_to_text -> show_entity_samples
실행 위치: part3/reasoning  ->  python learning/step1_annotated.py  (대화형, q 또는 빈 입력으로 종료)
주의: 파일을 import 하는 순간(599줄) OpenAILLM 이 만들어진다. OPENAI_API_KEY 가 없으면 import 단계에서 에러가 난다.
"""

# [출처] 표준 라이브러리. os.getenv
import os
# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 neo4j-graphrag. Text2CypherRetriever: 질문 -> LLM 이 Cypher 작성 -> 실행 -> 결과 를 하는 검색기.
# 이 파일은 이것을 "상속" 해서 search 만 바꾼 클래스를 만든다 (16줄)
from neo4j_graphrag.retrievers import Text2CypherRetriever
# OpenAILLM: OpenAI 모델 감싸개. 소스 확인: 만들 때 openai.OpenAI() 클라이언트를 만들고, 키는 환경변수 OPENAI_API_KEY 에서 읽는다
from neo4j_graphrag.llm import OpenAILLM
# RagTemplate: 답변 프롬프트 틀 / GraphRAG: 검색기 + LLM + 틀을 묶은 파이프라인
from neo4j_graphrag.generation import RagTemplate, GraphRAG
# RetrieverResultItem: 검색 결과 한 건 (content: LLM 에 넘길 글, metadata: 부가 정보 딕셔너리)
# RetrieverResult: 검색 결과 전체 (items: RetrieverResultItem 리스트, metadata: 딕셔너리)
# 둘 다 pydantic BaseModel 이라 키워드 인자로 만든다 (소스: neo4j_graphrag/types.py)
from neo4j_graphrag.types import RetrieverResultItem, RetrieverResult

# .env -> 환경변수
load_dotenv()


# ============================================
# 커스텀 Retriever: Cypher 쿼리를 컨텍스트에 포함
# ============================================

# class 자식(부모): 상속. 부모 Text2CypherRetriever 의 기능(__init__, get_search_results 등)을 그대로 물려받고,
# 아래 search 메서드만 새로 정의(오버라이드)한다
# [왜] 기본 Text2CypherRetriever 는 결과 Record 만 item 으로 만들고, 실행한 Cypher 는 metadata 에만 둔다.
#      GraphRAG 는 item.content 만 프롬프트에 넣기 때문에 답변 LLM 은 쿼리를 볼 수 없다. 그래서 content 안에 쿼리를 넣는다
class Text2CypherWithQueryRetriever(Text2CypherRetriever):
    """생성된 Cypher 쿼리를 결과에 포함시키는 커스텀 Retriever

    기존 Text2CypherRetriever를 확장하여 LLM에게 전달되는 컨텍스트에
    생성된 Cypher 쿼리문을 함께 포함시킵니다.

    이를 통해 LLM이:
    1. 어떤 쿼리가 실행되었는지 알 수 있음
    2. 쿼리 결과를 더 정확하게 해석할 수 있음
    3. 추론 경로를 명확히 설명할 수 있음
    """

    # def search(self, query_text: str, **kwargs): self 는 이 객체 자신. **kwargs 는 "나머지 키워드 인자를 딕셔너리로 받기"
    # GraphRAG.search 가 내부에서 retriever.search(query_text=질문, **retriever_config) 로 부른다 (소스 확인)
    # -> RetrieverResult 반환 타입 힌트
    def search(self, query_text: str, **kwargs) -> RetrieverResult:
        # 1) 부모 클래스의 search 실행
        # super().search(...): 부모 클래스의 search 를 부른다. **kwargs 는 받은 키워드 인자를 다시 풀어서 넘기기
        # 부모 search 내부 (소스 확인):
        #   get_search_results -> 프롬프트 채우기 -> llm.invoke -> extract_cypher(``` 코드블록 안만 꺼냄)
        #   -> driver.execute_query(..., routing_=READ) 읽기 전용 실행 -> Record 마다 RetrieverResultItem(content=str(record))
        #   -> metadata = {"cypher": 쿼리, "__retriever": 클래스 이름}
        result = super().search(query_text, **kwargs)

        # 2) 생성된 Cypher 쿼리 가져오기
        # 딕셔너리.get(키, 기본값): "cypher" 키가 없으면 빈 글자
        cypher_query = result.metadata.get("cypher", "")

        # 3) Cypher 쿼리는 한 번만 포함하고, 모든 결과를 순차적으로 붙이기
        # 모든 결과 아이템의 content를 하나로 합침
        # [item.content for item in result.items]: 결과마다 content 글을 꺼낸 리스트 -> "\n\n".join 으로 빈 줄 하나씩 끼워 잇기
        # content 는 str(Record) 모양: <Record disease='폐렴' related_symptoms=['기침', '발열'] treatments=[...]>
        all_results = "\n\n".join([item.content for item in result.items])

        # Cypher 쿼리 + 전체 결과를 하나의 컨텍스트로 생성
        # f""" ... """: 여러 줄 f-string. 마크다운 제목(###)과 ```cypher 코드블록으로 쿼리와 결과를 구분해 보여 준다
        combined_content = f"""### 실행된 Cypher 쿼리:
```cypher
{cypher_query}
```

### 쿼리 실행 결과:
{all_results}
"""

        # 하나의 아이템으로 반환
        # RetrieverResultItem 을 "하나만" 담은 리스트
        # [왜] GraphRAG 는 items 의 content 를 "\n" 으로 이어 {context} 를 만든다 (소스 확인). 여러 개면 쿼리가 결과마다 반복될 수 있어 하나로 합쳤다
        # 주의: 결과가 0건이어도 item 이 1개 생긴다 ("쿼리 실행 결과:" 아래가 빈 글). 그래서 GraphRAG 의 response_fallback
        #       (결과 0건이면 LLM 을 부르지 않는 옵션)을 써도 동작하지 않는다. 이 파일은 그 옵션을 쓰지 않는다
        new_items = [
            RetrieverResultItem(
                content=combined_content,
                # 값 if 조건 else 다른값: 결과가 있으면 첫 item 의 metadata, 없으면 빈 딕셔너리
                # (기본 포매터는 record.get("metadata") 를 쓰므로 RETURN 에 metadata 열이 없으면 보통 None)
                metadata=result.items[0].metadata if result.items else {}
            )
        ]

        # 부모가 만든 metadata({"cypher", "__retriever"})는 그대로 유지 -> main 에서 metadata["cypher"] 로 쿼리를 출력할 수 있다
        return RetrieverResult(
            items=new_items,
            metadata=result.metadata
        )


# ============================================
# 의료 지식그래프 스키마 정의
# ============================================

# [이 파일에서 정의] 의료 그래프 스키마를 사람이 정리한 딕셔너리로 돌려준다
# [반환] {"entities": [노드 레이블 8종], "relations": [관계 정보]}
# 노드: Question, Answer, Department, Symptom, Disease, Test, Treatment, Medication, Anatomy (description 은 사람이 읽기용)
# 주의: 스키마와 실제 그래프가 다를 수 있다. medical2kg.py 는 관계에 count, evidence, qa_ids(리스트)를 저장하는데
#       여기는 evidence, qa_id(INTEGER) 로 적혀 있다. 또 LOCATED_IN 은 medical2kg 의 domain_schemas.json 에 없다.
#       LLM 이 없는 관계/속성으로 쿼리를 쓰면 결과가 비게 된다. 실제 DB 에서 CALL db.schema.visualization() 등으로 확인해 보자
def get_medical_schema():
    schema = {
        "entities": [
            {
                "label": "Question",
                "description": "의료 QA 질문",
                "properties": [
                    {
                        "name": "qa_id",
                        "type": "INTEGER",
                        "description": "질문 고유 식별자"
                    },
                    {
                        "name": "content",
                        "type": "STRING",
                        "description": "질문 내용"
                    },
                    {
                        "name": "q_type",
                        "type": "STRING",
                        "description": "질문 유형"
                    },
                    {
                        "name": "domain",
                        "type": "STRING",
                        "description": "도메인"
                    },
                    {
                        "name": "department",
                        "type": "STRING",
                        "description": "진료과 (내과, 산부인과, 소아청소년과, 응급의학과)"
                    }
                ]
            },
            {
                "label": "Answer",
                "description": "의료 QA 답변",
                "properties": [
                    {
                        "name": "qa_id",
                        "type": "INTEGER",
                        "description": "답변 고유 식별자"
                    },
                    {
                        "name": "content",
                        "type": "STRING",
                        "description": "답변 내용"
                    }
                ]
            },
            {
                "label": "Department",
                "description": "진료과",
                "properties": [
                    {
                        "name": "name",
                        "type": "STRING",
                        "description": "진료과 (내과, 산부인과, 소아청소년과, 응급의학과)"
                    }
                ]
            },
            {
                "label": "Symptom",
                "description": "증상 (환자가 경험하는 의료적 증후)",
                "properties": [
                    {
                        "name": "name",
                        "type": "STRING",
                        "description": "증상 이름"
                    }
                ]
            },
            {
                "label": "Disease",
                "description": "질병 (진단된 의료 상태)",
                "properties": [
                    {
                        "name": "name",
                        "type": "STRING",
                        "description": "질병 이름"
                    }
                ]
            },
            {
                "label": "Test",
                "description": "검사 (질병 진단을 위한 의료 검사)",
                "properties": [
                    {
                        "name": "name",
                        "type": "STRING",
                        "description": "검사 이름"
                    }
                ]
            },
            {
                "label": "Treatment",
                "description": "치료법 (질병 치료를 위한 의료 처치)",
                "properties": [
                    {
                        "name": "name",
                        "type": "STRING",
                        "description": "치료법 이름"
                    }
                ]
            },
            {
                "label": "Medication",
                "description": "약물 (질병 치료를 위한 의약품)",
                "properties": [
                    {
                        "name": "name",
                        "type": "STRING",
                        "description": "약물 이름"
                    }
                ]
            },
            {
                "label": "Anatomy",
                "description": "해부학적 구조 (신체 부위 또는 기관)",
                "properties": [
                    {
                        "name": "name",
                        "type": "STRING",
                        "description": "해부학적 구조 이름"
                    }
                ]
            }
        ],
        # 관계 정의. source -> target 방향이 중요하다. INDICATES(증상->질병), DIAGNOSES_FOR(검사->질병),
        # TREATS(치료/약물->질병), LOCATED_IN(부위->질병), MENTIONS(질문->엔티티) 등
        "relations": [
            {
                "label": "HAS_ANSWER",
                "description": "질문에 대한 답변",
                "source": "Question",
                "target": "Answer"
            },
            {
                "label": "BELONGS_TO",
                "description": "질문이 특정 진료과에 속함",
                "source": "Question",
                "target": "Department"
            },
            {
                "label": "MENTIONS",
                "description": "질문이 엔티티를 언급함",
                "source": "Question",
                "target": "Symptom"
            },
            {
                "label": "MENTIONS",
                "description": "질문이 엔티티를 언급함",
                "source": "Question",
                "target": "Disease"
            },
            {
                "label": "MENTIONS",
                "description": "질문이 엔티티를 언급함",
                "source": "Question",
                "target": "Test"
            },
            {
                "label": "MENTIONS",
                "description": "질문이 엔티티를 언급함",
                "source": "Question",
                "target": "Treatment"
            },
            {
                "label": "MENTIONS",
                "description": "질문이 엔티티를 언급함",
                "source": "Question",
                "target": "Medication"
            },
            {
                "label": "MENTIONS",
                "description": "질문이 엔티티를 언급함",
                "source": "Question",
                "target": "Anatomy"
            },
            {
                "label": "INDICATES",
                "description": "증상이 질병을 나타냄 (추론의 출발점)",
                "source": "Symptom",
                "target": "Disease",
                "properties": [
                    {
                        "name": "evidence",
                        "type": "STRING",
                        "description": "증거 텍스트"
                    },
                    {
                        "name": "qa_id",
                        "type": "INTEGER",
                        "description": "출처 QA ID"
                    }
                ]
            },
            {
                "label": "DIAGNOSES_FOR",
                "description": "검사가 질병을 진단함",
                "source": "Test",
                "target": "Disease",
                "properties": [
                    {
                        "name": "evidence",
                        "type": "STRING",
                        "description": "증거 텍스트"
                    },
                    {
                        "name": "qa_id",
                        "type": "INTEGER",
                        "description": "출처 QA ID"
                    }
                ]
            },
            {
                "label": "TREATS",
                "description": "치료법이 질병을 치료함 (추론의 목표점)",
                "source": "Treatment",
                "target": "Disease",
                "properties": [
                    {
                        "name": "evidence",
                        "type": "STRING",
                        "description": "증거 텍스트"
                    },
                    {
                        "name": "qa_id",
                        "type": "INTEGER",
                        "description": "출처 QA ID"
                    }
                ]
            },
            {
                "label": "TREATS",
                "description": "약물이 질병을 치료함 (추론의 목표점)",
                "source": "Medication",
                "target": "Disease",
                "properties": [
                    {
                        "name": "evidence",
                        "type": "STRING",
                        "description": "증거 텍스트"
                    },
                    {
                        "name": "qa_id",
                        "type": "INTEGER",
                        "description": "출처 QA ID"
                    }
                ]
            },
            {
                "label": "LOCATED_IN",
                "description": "해부학적 구조에 위치한 질병",
                "source": "Anatomy",
                "target": "Disease",
                "properties": [
                    {
                        "name": "evidence",
                        "type": "STRING",
                        "description": "증거 텍스트"
                    },
                    {
                        "name": "qa_id",
                        "type": "INTEGER",
                        "description": "출처 QA ID"
                    }
                ]
            }
        ]
    }
    return schema


# [이 파일에서 정의] 스키마 딕셔너리 -> "Node properties: / Relationship properties: / The relationships:" 3구역 글
# (neo4j-graphrag 의 get_schema() 가 DB 에서 자동으로 뽑는 글과 같은 형식)
# 주의: TREATS 처럼 같은 label 이 두 번 있으면 "Relationship properties" 구역에 같은 줄이 두 번 나온다 (동작에는 문제 없음)
def schema_to_text(schema):
    """JSON 스키마를 Text2CypherRetriever가 이해할 수 있는 문자열 형식으로 변환"""
    # 줄을 리스트에 모았다가 마지막에 "\n".join 으로 잇는다
    lines = ["Node properties:"]

    # 엔티티(노드) 정보 추가
    for entity in schema["entities"]:
        # 리스트 컴프리헨션으로 "qa_id: INTEGER" 같은 글을 모아 ", " 로 잇기
        props = ", ".join([f"{p['name']}: {p['type']}" for p in entity["properties"]])
        # f"{{{props}}}": {{ 는 글자 {, {props} 는 변수, }} 는 글자 } -> 예: Symptom {name: STRING}
        lines.append(f"{entity['label']} {{{props}}}")

    # 관계 속성 추가
    lines.append("\nRelationship properties:")
    for relation in schema["relations"]:
        # 키가 있고(and) 비어 있지 않을 때만. and 는 앞이 거짓이면 뒤를 보지 않아 KeyError 를 피한다
        if "properties" in relation and relation["properties"]:
            props = ", ".join([f"{p['name']}: {p['type']}" for p in relation["properties"]])
            lines.append(f"{relation['label']} {{{props}}}")

    # 관계 정의 추가
    lines.append("\nThe relationships:")
    for relation in schema["relations"]:
        source = relation["source"]
        target = relation["target"]
        label = relation["label"]
        if "properties" in relation and relation["properties"]:
            prop_names = ", ".join([p['name'] for p in relation["properties"]])
            # 속성이 있으면 (:Symptom)-[:INDICATES {evidence, qa_id}]->(:Disease) 처럼 이름만 붙인다
            lines.append(f"(:{source})-[:{label} {{{prop_names}}}]->(:{target})")
        else:
            lines.append(f"(:{source})-[:{label}]->(:{target})")

    return "\n".join(lines)


# ============================================
# 예제 쿼리 정의
# ============================================

# [이 파일에서 정의] 추론 패턴 예제 5개 (few-shot)
# 각 예제 = USER INPUT + WHAT USER MENTIONED(말한 것) + WHAT SYSTEM INFERS(추론할 것) + INFERENCE PATH(경로) + QUERY
# [왜] 쿼리만 보여 주면 LLM 은 모양만 흉내 낸다. "왜 이 경로인가" 를 같이 보여 주면 새 질문에도 경로를 설계한다
# 패턴: 1) 증상 하나 -> 질병 + 동반 증상 + 치료  2) 증상 둘 -> 공통 질병(교집합)  3) 질병 -> 증상/검사/치료/부위
#       4) 신체 부위 -> 질병  5) 약물 -> 질병
# 검색기가 이 리스트를 "\n".join 해서 프롬프트의 {examples} 자리에 넣는다 (소스 확인)
def get_example_queries():
    examples = [
        # ========================================
        # 패턴 1 쿼리: 시작점 MATCH 하나 + OPTIONAL MATCH 3개로 확장 + collect(DISTINCT) 로 리스트로 모으기
        # OPTIONAL MATCH: 연결이 없어도 행을 버리지 않고 null 로 채운다 (일반 MATCH 면 치료가 없는 질병은 통째로 사라진다)
        # CONTAINS: 부분 일치. 그래프에는 "마른기침", "기침 및 가래" 처럼 저장돼 있어 = 로는 거의 못 찾는다
        # 주의: OPTIONAL MATCH 를 여러 개 이으면 집계 전 행 수가 (증상 수 x 치료 수 x 약물 수) 로 곱해져 느려질 수 있다
        #       RETURN DISTINCT 는 collect 로 이미 질병별 1행이라 사실상 필요 없다
        # 패턴 1: 증상 단독 언급 → 포괄적 추론
        # ========================================
        """USER INPUT: '기침이 심해요'
WHAT USER MENTIONED: 증상 하나 (기침)
WHAT SYSTEM INFERS: 가능한 질병들 + 동반되는 다른 증상들 + 치료 옵션
INFERENCE PATH: Symptom → Disease → [Symptom, Treatment, Medication]
QUERY: MATCH (s:Symptom)-[:INDICATES]->(d:Disease)
WHERE s.name CONTAINS '기침' OR s.name CONTAINS '가래'
OPTIONAL MATCH (d)<-[:INDICATES]-(other_s:Symptom)
OPTIONAL MATCH (tr:Treatment)-[:TREATS]->(d)
OPTIONAL MATCH (m:Medication)-[:TREATS]->(d)
RETURN DISTINCT d.name AS disease,
       collect(DISTINCT other_s.name) AS related_symptoms,
       collect(DISTINCT tr.name) AS treatments,
       collect(DISTINCT m.name) AS medications
LIMIT 10""",

        # ========================================
        # 패턴 2 쿼리: (s1)-[:INDICATES]->(d)<-[:INDICATES]-(s2) 두 증상이 "같은 질병" 을 가리키는 경로 = 교집합 추론
        # WITH d, count(DISTINCT s1) + count(DISTINCT s2): 질병별로 "기침 쪽 증상 수 + 열 쪽 증상 수" = 일치 점수
        # 주의: 한 패턴 안에서 같은 관계를 두 번 쓸 수 없어서 s1 과 s2 는 서로 다른 관계로 이어진 증상이다.
        #       다만 "기침 발열" 처럼 이름에 둘 다 들어간 증상은 양쪽에 다 세어질 수 있어 점수가 부풀 수 있다
        # 패턴 2: 다중 증상 언급 → 교집합 추론
        # ========================================
        """USER INPUT: '기침도 하고 열도 나요'
WHAT USER MENTIONED: 증상 두 가지 (기침 + 열)
WHAT SYSTEM INFERS: 두 증상의 공통 원인 질병 + 일치도 순위 + 치료 옵션
INFERENCE PATH: [Symptom, Symptom] → Disease (intersection) → [Treatment, Medication]
QUERY: MATCH (s1:Symptom)-[:INDICATES]->(d:Disease)<-[:INDICATES]-(s2:Symptom)
WHERE (s1.name CONTAINS '기침' OR s1.name CONTAINS '가래')
  AND (s2.name CONTAINS '발열' OR s2.name CONTAINS '열')
WITH d, count(DISTINCT s1) + count(DISTINCT s2) AS symptom_match
OPTIONAL MATCH (tr:Treatment)-[:TREATS]->(d)
OPTIONAL MATCH (m:Medication)-[:TREATS]->(d)
RETURN d.name AS disease,
       symptom_match AS matching_symptoms,
       collect(DISTINCT tr.name) AS treatments,
       collect(DISTINCT m.name) AS medications
ORDER BY symptom_match DESC
LIMIT 10""",

        # ========================================
        # 패턴 3 쿼리: 질병에서 시작해 반대 방향(<-)으로 증상/검사/치료/약물/부위를 모은다
        # 주의: LOCATED_IN 이 실제 그래프에 없으면 location 은 항상 빈 리스트다 (67줄 주의 참고)
        # 패턴 3: 질병 단독 언급 → 역방향 확장
        # ========================================
        """USER INPUT: '폐렴이에요'
WHAT USER MENTIONED: 질병명 하나 (폐렴)
WHAT SYSTEM INFERS: 전형적 증상들 + 필요한 검사 + 치료법 + 발병 부위
INFERENCE PATH: Disease → [Symptom, Test, Treatment, Medication, Anatomy]
QUERY: MATCH (d:Disease)
WHERE d.name CONTAINS '폐렴'
OPTIONAL MATCH (s:Symptom)-[:INDICATES]->(d)
OPTIONAL MATCH (t:Test)-[:DIAGNOSES_FOR]->(d)
OPTIONAL MATCH (tr:Treatment)-[:TREATS]->(d)
OPTIONAL MATCH (m:Medication)-[:TREATS]->(d)
OPTIONAL MATCH (a:Anatomy)-[:LOCATED_IN]->(d)
RETURN DISTINCT d.name AS disease,
       collect(DISTINCT s.name) AS symptoms,
       collect(DISTINCT t.name) AS diagnostic_tests,
       collect(DISTINCT tr.name) AS treatments,
       collect(DISTINCT m.name) AS medications,
       collect(DISTINCT a.name) AS location
LIMIT 10""",

        # ========================================
        # 패턴 4: Anatomy -LOCATED_IN-> Disease. 주의: LOCATED_IN 이 없으면 이 패턴은 0건이 된다
        # (조건의 '골반뼈' 는 '골반' 을 이미 포함하므로 OR 뒤는 의미가 없다)
        # 패턴 4: 신체 부위 언급 → 관련 지식 탐색
        # ========================================
        """USER INPUT: '골반이 불편해요'
WHAT USER MENTIONED: 신체 부위 하나 (골반)
WHAT SYSTEM INFERS: 해당 부위 질병들 + 증상들 + 진단 검사들
INFERENCE PATH: Anatomy → Disease → [Symptom, Test]
QUERY: MATCH (a:Anatomy)-[:LOCATED_IN]->(d:Disease)
WHERE a.name CONTAINS '골반' OR a.name CONTAINS '골반뼈'
OPTIONAL MATCH (s:Symptom)-[:INDICATES]->(d)
OPTIONAL MATCH (t:Test)-[:DIAGNOSES_FOR]->(d)
RETURN DISTINCT d.name AS disease,
       collect(DISTINCT s.name) AS symptoms,
       collect(DISTINCT t.name) AS tests
LIMIT 10""",

        # ========================================
        # 패턴 5: Medication -TREATS-> Disease. RETURN 에 m.name 이 있어 (질병, 약물) 쌍마다 1행
        # 패턴 5: 치료/약물 언급 → 대상 질병 추론
        # ========================================
        """USER INPUT: '항생제 먹고 있어요'
WHAT USER MENTIONED: 약물 하나 (항생제)
WHAT SYSTEM INFERS: 치료 대상 질병들 + 그 질병의 증상들 + 필요한 검사들
INFERENCE PATH: Medication → Disease → [Symptom, Test]
QUERY: MATCH (m:Medication)-[:TREATS]->(d:Disease)
WHERE m.name CONTAINS '항생제' OR m.name CONTAINS '항균'
OPTIONAL MATCH (s:Symptom)-[:INDICATES]->(d)
OPTIONAL MATCH (t:Test)-[:DIAGNOSES_FOR]->(d)
RETURN DISTINCT d.name AS disease,
       m.name AS medication,
       collect(DISTINCT s.name) AS symptoms,
       collect(DISTINCT t.name) AS tests
LIMIT 10""",
    ]
    return examples


# ============================================
# Neo4j 연결 관리
# ============================================

# [이 파일에서 정의] 환경변수 확인 -> 드라이버 생성 -> 연결 확인 [반환] Driver
def create_neo4j_driver():
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # all([...]): [출처] 파이썬 기본. 모두 값이 있으면 True. 하나라도 None 이면 ValueError 로 멈춘다
    if not all([uri, username, password]):
        raise ValueError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD 환경 변수를 설정해주세요.")

    # GraphDatabase.driver(uri, auth=(사용자, 비밀번호)) [출처] 외부 라이브러리 neo4j
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        # verify_connectivity: 실제 접속 시험. 실패하면 출력 후 raise 로 같은 예외를 다시 던진다
        driver.verify_connectivity()
        print(f"✓ Neo4j 연결 성공: {uri}")
    except Exception as e:
        print(f"✗ Neo4j 연결 실패: {e}")
        raise

    return driver


# [이 파일에서 정의] driver 가 None 이 아니면 닫는다
def close_neo4j_driver(driver):
    if driver:
        driver.close()


# ============================================
# 추론 특화 Text2Cypher 프롬프트
# ============================================

# [이 파일에서 정의] Text2Cypher 용 "추론 특화" 프롬프트 글을 돌려준다
# {schema} {examples} {query_text} 세 자리를 검색기가 채운다
# 소스 확인: Text2CypherTemplate(template=이 글).format(schema=..., examples=..., query_text=...) -> 내부에서 str.format
#   그래서 이 글 안에 다른 { } 를 쓰면 안 된다 (Cypher 예시를 직접 넣을 때 {name: '...'} 같은 중괄호가 있으면 KeyError).
#   예제 쿼리는 값으로 끼워 넣어지므로 그 안의 중괄호는 괜찮다
# XML 비슷한 태그(<knowledge_graph_structure> 등)는 구역 구분용. LLM 이 어디까지가 스키마고 어디부터가 질문인지 알기 쉽다
# 마지막 "쿼리만 반환" 지시: 검색기는 답에서 ``` 코드블록이 있으면 그 안을, 없으면 답 전체를 Cypher 로 실행한다
def get_reasoning_text2cypher_prompt():
    return """
당신은 의료 지식그래프 추론 전문가입니다.

# 핵심 원칙: 그래프 기반 추론 (Graph Reasoning)
주어진 지식 구조를 기반으로 정보를 조회하기 위한 Cypher 쿼리를 생성합니다.
특히 사용자가 A만 물어봤더라도, 그래프 관계를 따라가며 연결된 B, C, D까지 추론해야 합니다.

<knowledge_graph_structure>
{schema}

**핵심 추론 경로들:**
1. Symptom -[INDICATES]-> Disease
   - 증상이 특정 질병을 암시함
   - 역방향: Disease를 통해 다른 증상들도 찾을 수 있음

2. Test -[DIAGNOSES_FOR]-> Disease
   - 검사가 질병을 진단함
   - 역방향: Disease를 알면 필요한 검사를 찾을 수 있음

3. Treatment -[TREATS]-> Disease / Medication -[TREATS]-> Disease
   - 치료법/약물이 질병을 치료함
   - 역방향: Disease를 알면 치료 옵션을 찾을 수 있음

4. Anatomy -[LOCATED_IN]-> Disease
   - 해부학적 구조(신체 부위)에 위치한 질병들
   - 역방향: Disease를 통해 발병 부위를 찾을 수 있음

**다중 홉(Multi-hop) 추론 경로 예시:**
- Symptom → Disease → Treatment (2-hop: 증상에서 치료까지)
- Symptom → Disease → Symptom (2-hop: 한 증상에서 같은 질병의 다른 증상들)
- Symptom → Disease → Test (2-hop: 증상에서 필요한 검사까지)
- Symptom → Disease ← Anatomy (2-hop: 증상에서 발병 부위까지)
- Treatment → Disease → Symptom (2-hop: 치료법에서 대상 질병의 증상들)
- Anatomy → Disease → Symptom, Test, Treatment (2-hop: 신체 부위에서 모든 관련 정보)

이러한 경로들을 조합하여 사용자의 단편적 질문을 종합적 답변으로 확장하세요.
</knowledge_graph_structure>

<reasoning_mindset>

**질문 분석 단계:**
1. 사용자가 명시한 것: 무엇을 직접 언급했는가? (증상? 질병? 약물? 부위?)
2. 사용자가 원하는 것: 명시하지 않았지만 알고 싶어하는 것은? (원인? 치료? 진단?)
3. 추론 경로 설계: 어떤 그래프 경로를 따라가야 하는가?

**추론 전략 결정:**
- 단일 엔티티 언급 → 연결된 모든 관련 정보 수집 (포괄적 탐색)
- 다중 엔티티 언급 → 공통 연결점 찾기 (교집합 추론)
- 명시적 요청 → 특정 경로만 탐색 (타겟 추론)

**쿼리 구조화:**
1. 시작점: 사용자가 언급한 엔티티로부터 시작
2. 확장: OPTIONAL MATCH로 관련 정보들 수집
3. 집계: COLLECT, COUNT로 정보 종합
4. 정렬: ORDER BY로 중요도/빈도 순 정렬
5. 제한: LIMIT로 핵심 정보만 반환 (단, 너무 적지 않게)
</reasoning_mindset>

<example_queries>
{examples}
</example_queries>

<critical_guidelines>
## 필수 지침

1. **항상 OPTIONAL MATCH 활용**: 연결된 정보가 없을 수도 있으므로 OPTIONAL MATCH로 안전하게 수집
2. **다중 홉 경로 설계**: 단일 관계만 보지 말고 2-3 홉 경로를 적극 활용
3. **포괄적 정보 수집**: 사용자가 A만 물어봤어도 B, C, D까지 수집 (예: 증상 → 질병, 검사, 치료, 위치)
4. **COLLECT로 집계**: 여러 관련 정보를 배열로 수집하여 종합 제시
5. **적절한 LIMIT**: 너무 적으면 정보 부족, 너무 많으면 노이즈 (보통 5-10)
6. **COUNT/ORDER BY 활용**: 빈도나 일치도로 정렬하여 중요한 정보부터 제시
7. **WHERE 조건 유연성**: CONTAINS 사용으로 부분 일치 허용
8. **DISTINCT 사용**: 중복 제거로 깔끔한 결과 제공

## 절대 하지 말 것
- 단일 관계만 보는 쿼리 (예: Symptom만 찾고 끝)
- OPTIONAL MATCH 없이 모든 경로를 MATCH로만 구성 (데이터 누락 위험)
- 지나치게 복잡한 쿼리 (가독성 저하)
</critical_guidelines>

<user_query>
{query_text}
</user_query>

위 지식 구조와 추론 전략을 바탕으로, 사용자 질문에 대한 Cypher 쿼리를 생성하세요.
쿼리만 반환하고 다른 설명은 포함하지 마세요.
"""


# ============================================
# GraphRAG 파이프라인 생성
# ============================================

# OpenAILLM(model_name="gpt-4o", model_params={"temperature": 0})
# [출처] 외부 라이브러리 neo4j-graphrag
# [입력] model_name: 모델 이름 / model_params: 매 호출마다 OpenAI API 에 넘길 옵션
# [반환] LLM 객체. 검색기(Cypher 작성)와 GraphRAG(답변 작성)가 같이 쓴다
# temperature 0: 같은 질문에 최대한 같은 쿼리 (재현성)
# 파일 맨 위(전역)에서 만들어서, import 하는 순간 OpenAI 클라이언트가 생긴다
llm = OpenAILLM(
    model_name="gpt-4o",
    model_params={"temperature": 0}
)

# [이 파일에서 정의] 스키마/예제/추론 프롬프트로 검색기를 만들고, 답변 틀과 묶어 GraphRAG 를 돌려준다
# use_schema, use_examples: 꺼 보며 품질 차이를 비교하는 실험용 스위치
def create_graphrag_pipeline(driver, use_schema=True, use_examples=True):

    # 값 if 조건 else None: 스위치가 꺼지면 None
    schema_json = get_medical_schema() if use_schema else None
    schema_text = schema_to_text(schema_json) if schema_json else None
    examples = get_example_queries() if use_examples else None

    # 추론 특화 Text2Cypher 프롬프트 사용
    reasoning_prompt = get_reasoning_text2cypher_prompt()

    # 커스텀 Retriever 사용: Cypher 쿼리를 컨텍스트에 포함 + 추론 특화 프롬프트
    # Text2CypherWithQueryRetriever(...): 부모의 __init__ 을 그대로 쓴다
    # [입력] driver, llm, neo4j_schema(스키마 글), examples(예제 리스트), custom_prompt(위 추론 프롬프트)
    # 소스 확인 (1.14.1 __init__):
    #   - 만들 때 DB 버전을 조회한다(get_version). 너무 오래된 Neo4j 면 Neo4jVersionError
    #   - custom_prompt 가 있고 neo4j_schema 가 None 이면 스키마는 "" (빈 글자)가 된다. DB 에서 자동으로 읽지 않는다
    #     -> use_schema=False 로 실험하면 {schema} 자리가 비게 된다 (기본 프롬프트일 때만 get_schema() 로 자동 조회)
    #   - neo4j_database 를 안 넘겼으므로 기본 DB 에서 실행된다
    retriever = Text2CypherWithQueryRetriever(
        driver=driver,
        llm=llm,
        neo4j_schema=schema_text,
        examples=examples,
        custom_prompt=reasoning_prompt
    )

    # RagTemplate(template=글, expected_inputs=[...])
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] template: 답변 프롬프트. {context} = 검색 결과(여기서는 Cypher + 결과), {query_text} = 질문
    #        expected_inputs: 틀에 반드시 있어야 하는 자리. 없으면 만들 때 PromptMissingPlaceholderError
    # [왜] 답변 LLM 에게 "Cypher 를 보고 추론 경로를 설명하라", "의료 안내 문구를 꼭 넣어라", "데이터에 없는 건 만들지 마라" 를 지시
    # f-string 이 아니다. {context} 는 나중에 라이브러리가 str.format 으로 채운다
    # 소스 확인: RagTemplate 의 기본 system_instructions "Answer the user question using the provided context." 도 같이 보내진다
    prompt_template = RagTemplate(
        template="""
당신은 의료 지식그래프 추론 전문가입니다.
사용자의 질문에 대해 그래프 추론을 통해 얻은 데이터를 기반으로 정확하고 상세한 답변을 제공하세요.

<retrieval_result>
{context}
</retrieval_result>

<user_query>
{query_text}
</user_query>

<answer_guidelines>
1. Cypher 쿼리 분석: Context에 포함된 Cypher 쿼리를 분석하여 어떤 추론 경로가 사용되었는지 파악하세요.
   - 예: Symptom → Disease (증상에서 질병 추론)
   - 예: Symptom → Disease → Treatment (증상에서 치료법까지 2-hop 추론)
   - 예: Disease ← Symptom (역방향 추론: 질병의 증상들)

2. 추론 과정 설명: 주어진 검색 결과에서 발견한 '추론 과정'을 명확히 설명하세요.

3. 구체적 정보 포함: 검색된 데이터의 구체적인 질병명, 증상, 치료법, 약물명 등을 반드시 포함하세요. 검색결과가 없다면 굳이 언급하지 마세요.

4. 포괄적 답변: 단순한 증상 질문("열이 나요")이라도 관련 질병, 동반 증상, 검사, 치료법까지 종합적으로 설명하세요.

5. 우선순위 제시: 여러 결과가 있을 때 빈도, 중요도, 일치도 등을 고려하여 우선순위를 제시하세요.

6. 의료 안내 필수: 모든 답변 마지막에 "이 정보는 참고용이며, 정확한 진단과 치료를 위해서는 반드시 전문의와 상담이 필요합니다"를 포함하세요.

7. 데이터 기반 답변: 검색된 데이터에 없는 정보는 추측하거나 만들어내지 마세요.

8. 구조화 된 답변: 사용자가 가독성 있게 이해할 수 있도록, 주어진 정보를 명확한 문장과 단락으로 구조화하여 제시하세요.
</answer_guidelines>

답변:
            """,
        expected_inputs=["context", "query_text"]
    )

    # GraphRAG(retriever=..., llm=..., prompt_template=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [반환] 파이프라인. .search(query_text=...) 한 번으로 검색 -> 프롬프트 채우기 -> 답변 생성
    rag = GraphRAG(retriever=retriever, llm=llm, prompt_template=prompt_template)
    return rag


# [이 파일에서 정의] rag.search 를 부르고 결과를 돌려준다. 에러면 출력 후 다시 던진다
def search_with_graphrag(rag, query_text, return_context=False):
    try:
        # GraphRAG 검색 (쿼리 생성 → 실행 → 답변 생성)
        # rag.search(query_text=질문, return_context=True/False)
        # [반환] RagResultModel. .answer = 답변 글, .retriever_result = return_context=True 일 때만 RetrieverResult (아니면 None)
        # 소스 확인: 내부에서 retriever.search(query_text=...) -> items 의 content 를 "\n" 으로 이어 {context} -> llm.invoke
        # LLM 이 문법이 틀린 Cypher 를 쓰면 CypherSyntaxError -> Text2CypherRetrievalError 로 바뀌어 여기 except 로 온다
        response = rag.search(
            query_text=query_text,
            return_context=return_context,
        )

        return response

    except Exception as e:
        print(f"\n✗ 오류 발생: {e}")
        raise


# ============================================
# 엔티티 샘플 조회
# ============================================

# [이 파일에서 정의] 엔티티 종류마다 실제 이름 몇 개를 출력 (사용자가 그래프에 있는 단어로 질문하게 돕는 데모 장치)
def show_entity_samples(driver, limit=5):
    """지식그래프에 실제로 존재하는 엔티티 샘플들을 출력

    Args:
        driver: Neo4j driver
        limit: 각 엔티티 타입별 출력할 샘플 개수
    """
    entity_types = ["Symptom", "Disease", "Test", "Treatment", "Medication", "Anatomy"]

    print("\n" + "=" * 60)
    print(f"지식그래프에 저장된 엔티티 샘플 (각 타입별 {limit}개)")
    print("=" * 60)

    # with driver.session() as session: with 문. 블록이 끝나면(에러가 나도) 세션을 자동으로 닫는다
    # driver.session(): [출처] 외부 라이브러리 neo4j. 쿼리를 여러 번 보낼 작업 단위
    # 주의: database 를 지정하지 않아 기본 DB 를 쓴다. 다른 함수(검색기)도 기본 DB 이므로 여기서는 일관되지만,
    #       기본 DB 가 아닌 곳에 그래프를 넣었다면 둘 다 빈 결과가 된다
    with driver.session() as session:
        for entity_type in entity_types:
            # f-string 으로 레이블과 LIMIT 숫자를 끼워 넣는다 (레이블은 $매개변수로 넘길 수 없다. 값이 고정 목록이라 안전)
            query = f"MATCH (n:{entity_type}) RETURN n.name AS name LIMIT {limit}"
            try:
                # session.run(쿼리): [반환] Result. for 로 돌면 Record 가 하나씩 나온다 (세션이 열려 있는 동안만 읽을 수 있다)
                result = session.run(query)
                # 리스트 컴프리헨션 + if: name 이 비어 있는(None) 행은 뺀다
                names = [record["name"] for record in result if record["name"]]

                if names:
                    # [f"[{name}]" for name in names]: 이름마다 대괄호를 씌워 " " 로 잇기 -> [기침] [발열] [두통]
                    names_str = " ".join([f"[{name}]" for name in names])
                    print(f"\n[{entity_type}] {names_str}")
                else:
                    print(f"\n[{entity_type}] (데이터 없음)")
            except Exception as e:
                print(f"\n[{entity_type}] (조회 실패: {e})")


# ============================================
# 메인 함수
# ============================================

# [이 파일에서 정의] 연결 -> 파이프라인 -> (샘플 출력 -> 질문 -> 쿼리/결과/답변 출력) 반복
def main():
    print("\n" + "=" * 60)
    print("의료 지식그래프 기반 Text2Cypher GraphRAG 추론 시스템")
    print("=" * 60)

    driver = create_neo4j_driver()

    rag = create_graphrag_pipeline(driver=driver, use_schema=True, use_examples=True)

    # 사용자 입력 루프
    # True 면 답변과 함께 "LLM 이 쓴 Cypher" 와 "검색 결과" 를 출력한다 (디버깅용)
    RETURN_CONTEXT = True

    while True:
        # 질문할 때마다 엔티티 샘플을 다시 보여 준다 (매번 6개 쿼리 실행)
        show_entity_samples(driver, limit=5)

        print("\n" + "=" * 60)
        test_query = input("질문: ").strip()

        # 빈 입력도 종료로 처리한다 (retail 쪽 파일은 빈 입력이면 다시 묻는다)
        if not test_query or test_query.lower() in ['quit', 'exit', 'q']:
            print("\n시스템을 종료합니다.")
            break

        # 주의: 예외가 나면 search_with_graphrag 가 다시 던지므로 루프가 끝나고 프로그램이 멈춘다.
        #       잘못된 Cypher 한 번에 대화가 끝난다. 루프 안에서 try/except 로 감싸면 계속 질문할 수 있다
        response = search_with_graphrag(
            rag,
            test_query,
            return_context=RETURN_CONTEXT,
        )

        # hasattr(객체, '속성'): 속성이 있으면 True. RagResultModel 은 항상 retriever_result 를 가지므로 사실상 RETURN_CONTEXT 만 의미 있다
        if RETURN_CONTEXT and hasattr(response, 'retriever_result'):
            print("\n" + "=" * 60)
            print("생성된 Cypher 쿼리문")
            print("=" * 60)
            # metadata["cypher"]: 부모 검색기가 넣고 커스텀 search 가 그대로 넘긴 쿼리 글
            print(response.retriever_result.metadata["cypher"])

            print("\n" + "=" * 60)
            print("검색 결과 ")
            print("=" * 60)
            # items 는 1개뿐 (커스텀 search 가 합쳤다). 그 content 에 쿼리와 결과가 다 들어 있다
            for i in response.retriever_result.items:
                print(i.content)

        print("\n" + "=" * 60)
        print("최종 답변")
        print("=" * 60)
        print(response.answer)

    # 주의: try/finally 가 아니라서 위에서 예외가 나면 이 줄이 실행되지 않는다 (프로그램이 끝나면서 정리되긴 한다)
    close_neo4j_driver(driver)

# 직접 실행할 때만 main()
if __name__ == "__main__":
    main()