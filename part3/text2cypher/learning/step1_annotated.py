"""[1단계: 읽기] text2cypher.py (자연어 질문 -> LLM 이 Cypher 작성 -> 실행 -> LLM 이 답변) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(neo4j-graphrag 1.13.1)로 확인했다.

전제: Part 2 csv2kg 로 타이타닉 그래프가 Neo4j 에 들어 있어야 한다. .env 에 NEO4J_*, OPENAI_API_KEY 필요.

흐름 (LLM 을 두 번 부른다)
  질문 "어린이의 생존율은?"
    -> [Text2CypherRetriever] 프롬프트 = 스키마 글 + 예제 10개 + 질문 -> LLM(1번째) -> Cypher 글
    -> 그 Cypher 를 Neo4j 에서 실행(읽기 전용) -> Record 들 -> 각 Record 를 str() 로 글로 바꿔 items 에 담음
    -> [GraphRAG] items 글을 줄바꿈으로 이어 {context} 에, 질문을 {query_text} 에 넣은 프롬프트 -> LLM(2번째) -> 답변

벡터 검색(part3/vectorsearch)과 다른 점: 비슷한 글을 찾는 게 아니라 "정확한 계산/집계"를 DB 가 한다.
  -> 개수, 비율, 순위 같은 질문에 강하다. 대신 LLM 이 잘못된 Cypher 를 쓰면 틀리거나 에러가 난다.

읽는 순서 권장: main -> create_graphrag_pipeline -> schema_to_text -> get_example_queries -> search_with_graphrag
실행 위치: part3/text2cypher  ->  python learning/step1_annotated.py
"""

# [출처] 표준 라이브러리. os.getenv
import os
# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 neo4j-graphrag (Neo4j 공식 GraphRAG 패키지)
# Text2CypherRetriever: 질문 -> LLM 으로 Cypher 생성 -> 실행 -> 결과를 돌려주는 "검색기"
from neo4j_graphrag.retrievers import Text2CypherRetriever
# OpenAILLM: neo4j-graphrag 가 OpenAI 모델을 부르는 감싸개(wrapper). 검색기와 GraphRAG 가 이 객체의 invoke 를 부른다
from neo4j_graphrag.llm import OpenAILLM
# RagTemplate: 답변용 프롬프트 틀 / GraphRAG: 검색기 + LLM + 프롬프트를 묶은 파이프라인 (search 한 번으로 검색과 답변까지)
from neo4j_graphrag.generation import RagTemplate, GraphRAG

# .env 를 읽어 환경변수로 등록. OpenAILLM 은 OPENAI_API_KEY 환경변수를 자동으로 읽는다 (api_key 를 따로 안 넘기는 이유)
load_dotenv()


# ============================================
# 타이타닉 지식그래프 스키마 정의
# ============================================

# [이 파일에서 정의] 그래프 스키마를 "사람이 정리한" 딕셔너리로 돌려준다
# [반환] {"entities": [노드 레이블 정보...], "relations": [관계 정보...]}
# [왜] LLM 은 DB 안에 무엇이 있는지 모른다. 레이블, 속성 이름, 타입, 관계 방향을 알려줘야 맞는 Cypher 를 쓴다.
#      description(한글 설명)은 사람이 읽기 위한 것이다. 아래 schema_to_text 는 이름과 타입만 LLM 에 보낸다
def get_titanic_schema():
    schema = {
        # 노드 레이블 4종: Passenger, PClass, Cabin, Port. 각 속성은 {"name", "type", "description"}
        "entities": [
            {
                "label": "Passenger",
                "description": "타이타닉호에 탑승한 승객",
                "properties": [
                    {
                        "name": "PassengerId",
                        "type": "STRING",
                        "description": "승객 고유 식별자"
                    },
                    {
                        "name": "Name",
                        "type": "STRING",
                        "description": "승객의 이름"
                    },
                    {
                        "name": "Sex",
                        "type": "STRING",
                        "description": "승객의 성별 (male/female)"
                    },
                    {
                        "name": "Age",
                        "type": "FLOAT",
                        "description": "승객의 나이"
                    },
                    {
                        "name": "Survived",
                        "type": "INTEGER",
                        "description": "생존 여부 (1: 생존, 0: 사망)"
                    },
                    {
                        "name": "SibSp",
                        "type": "INTEGER",
                        "description": "동승한 형제자매/배우자 수"
                    },
                    {
                        "name": "Parch",
                        "type": "INTEGER",
                        "description": "동승한 부모/자녀 수"
                    },
                    {
                        "name": "Fare",
                        "type": "FLOAT",
                        "description": "지불한 운임 요금"
                    },
                    {
                        "name": "Ticket",
                        "type": "STRING",
                        "description": "티켓 번호"
                    }
                ]
            },
            {
                "label": "PClass",
                "description": "승객 등급 (사회경제적 지위를 나타냄)",
                "properties": [
                    {
                        "name": "Pclass",
                        "type": "INTEGER",
                        "description": "등급 번호 (1/2/3)"
                    },
                    {
                        "name": "ClassName",
                        "type": "STRING",
                        "description": "등급 이름 (1st Class/2nd Class/3rd Class)"
                    },
                    {
                        "name": "SES",
                        "type": "STRING",
                        "description": "사회경제적 지위 (Upper/Middle/Lower)"
                    }
                ]
            },
            {
                "label": "Cabin",
                "description": "승객이 머문 선실",
                "properties": [
                    {
                        "name": "Cabin",
                        "type": "STRING",
                        "description": "선실 번호"
                    }
                ]
            },
            {
                "label": "Port",
                "description": "승객이 탑승한 항구",
                "properties": [
                    {
                        "name": "Port",
                        "type": "STRING",
                        "description": "항구 코드 (S/C/Q)"
                    },
                    {
                        "name": "PortName",
                        "type": "STRING",
                        "description": "항구 이름 (Southampton/Cherbourg/Queenstown)"
                    }
                ]
            }
        ],
        # 관계 4종. source -> target 방향이 중요하다 (LLM 이 화살표 방향을 틀리면 결과가 0건)
        "relations": [
            {
                "label": "TRAVELED_IN",
                "description": "승객이 특정 등급으로 여행함",
                "source": "Passenger",
                "target": "PClass"
            },
            {
                "label": "STAYED_IN",
                "description": "승객이 특정 선실에 머뭄",
                "source": "Passenger",
                "target": "Cabin"
            },
            {
                "label": "EMBARKED_AT",
                "description": "승객이 특정 항구에서 승선함",
                "source": "Passenger",
                "target": "Port"
            },
            {
                # 관계에도 속성이 있을 수 있다 (TRAVELED_WITH 에만 properties 키가 있다)
                "label": "TRAVELED_WITH",
                "description": "같은 티켓으로 함께 여행한 승객들",
                "source": "Passenger",
                "target": "Passenger",
                "properties": [
                    {
                        "name": "Ticket",
                        "type": "STRING",
                        "description": "공유한 티켓 번호"
                    }
                ]
            }
        ]
    }
    return schema


# [이 파일에서 정의] 위 딕셔너리 -> LLM 에 넣을 스키마 "글"
# [반환] 실제 출력 (직접 실행해서 확인한 결과):
#   Node properties:
#   Passenger {PassengerId: STRING, Name: STRING, Sex: STRING, Age: FLOAT, Survived: INTEGER, SibSp: INTEGER, Parch: INTEGER, Fare: FLOAT, Ticket: STRING}
#   PClass {Pclass: INTEGER, ClassName: STRING, SES: STRING}
#   Cabin {Cabin: STRING}
#   Port {Port: STRING, PortName: STRING}
#
#   Relationship properties:
#   TRAVELED_WITH {Ticket: STRING}
#
#   The relationships:
#   (:Passenger)-[:TRAVELED_IN]->(:PClass)
#   (:Passenger)-[:STAYED_IN]->(:Cabin)
#   (:Passenger)-[:EMBARKED_AT]->(:Port)
#   (:Passenger)-[:TRAVELED_WITH {Ticket}]->(:Passenger)
# [왜] 이 모양은 neo4j-graphrag 의 get_schema() 가 DB 에서 자동으로 뽑는 글과 같은 형식이다. 같은 형식으로 맞춰 준 것
def schema_to_text(schema):
    """JSON 스키마를 Text2CypherRetriever가 이해할 수 있는 문자열 형식으로 변환"""
    # 리스트에 줄을 하나씩 모았다가 맨 끝에 "\n".join 으로 한 번에 잇는다 (문자열을 += 로 계속 붙이는 것보다 깔끔)
    lines = ["Node properties:"]

    # 엔티티(노드) 정보 추가
    for entity in schema["entities"]:
        # [f"..." for p in ...]: 속성마다 "Name: STRING" 글을 만든 리스트 -> ", ".join: 쉼표로 이어 붙이기
        props = ", ".join([f"{p['name']}: {p['type']}" for p in entity["properties"]])
        # f"{entity['label']} {{{props}}}" : {{ 는 글자 {, {props} 는 변수, }} 는 글자 }
        #   -> 중괄호 세 개 {{{ 는 "글자 { + 변수 시작" 이다. 결과: Passenger {PassengerId: STRING, ...}
        lines.append(f"{entity['label']} {{{props}}}")

    # 관계 속성 추가
    # "\nRelationship..." 앞의 \n: 구역 사이에 빈 줄을 하나 넣으려고
    lines.append("\nRelationship properties:")
    for relation in schema["relations"]:
        # "properties" in relation: 딕셔너리에 그 키가 있는지 / and relation["properties"]: 그리고 비어 있지 않은지
        # (and 는 앞이 거짓이면 뒤를 보지 않는다 -> 키가 없을 때 relation["properties"] 의 KeyError 를 피한다)
        if "properties" in relation and relation["properties"]:
            props = ", ".join([f"{p['name']}: {p['type']}" for p in relation["properties"]])
            lines.append(f"{relation['label']} {{{props}}}")

    # 관계 정의 추가
    lines.append("\nThe relationships:")
    for relation in schema["relations"]:
        source = relation["source"]
        target = relation["target"]
        label = relation["label"]
        # 관계 줄은 속성이 있으면 이름만 {Ticket} 처럼, 없으면 화살표만
        if "properties" in relation and relation["properties"]:
            prop_names = ", ".join([p['name'] for p in relation["properties"]])
            lines.append(f"(:{source})-[:{label} {{{prop_names}}}]->(:{target})")
        else:
            lines.append(f"(:{source})-[:{label}]->(:{target})")

    return "\n".join(lines)


# ============================================
# 예제 쿼리 정의
# ============================================

# [이 파일에서 정의] 질문 -> 정답 Cypher 예제 10개 (few-shot)
# [왜] 예제를 보여 주면 LLM 이 이 DB 의 속성 이름(Survived = 1, Sex = 'female')과 쿼리 스타일을 따라 한다
#      특히 "생존율" 같은 계산을 어떻게 쓰는지(round(100.0 * sum / count, 2)) 그대로 흉내 낸다
# 형식: "USER INPUT: '질문' QUERY: Cypher" 글 하나가 예제 하나. 검색기가 이것들을 줄바꿈으로 이어 프롬프트에 넣는다
# 주의: 7번째, 10번째 예제의 p.Pclass 는 위 스키마의 Passenger 속성에 없다 (PClass 노드의 속성이다).
#       실제 DB 의 Passenger 노드에 Pclass 가 있는지 Neo4j Browser 에서 확인해 보자. 없으면 null 이 나온다
def get_example_queries():
    examples = [
        "USER INPUT: '생존한 승객은 몇 명인가요?' QUERY: MATCH (p:Passenger) WHERE p.Survived = 1 RETURN count(p) AS survivors",
        "USER INPUT: '등급별 생존율은 어떻게 되나요?' QUERY: MATCH (p:Passenger)-[:TRAVELED_IN]->(c:PClass) RETURN c.ClassName, count(p) AS total, sum(p.Survived) AS survived, round(100.0 * sum(p.Survived) / count(p), 2) AS survival_rate ORDER BY c.Pclass",
        "USER INPUT: '여성 승객 중 생존자는 몇 명인가요?' QUERY: MATCH (p:Passenger) WHERE p.Sex = 'female' AND p.Survived = 1 RETURN count(p) AS female_survivors",
        "USER INPUT: '이름에 John이 포함된 승객을 알려주세요' QUERY: MATCH (p:Passenger) WHERE p.Name CONTAINS 'John' RETURN p.Name, p.Age, p.Sex, p.Survived LIMIT 10",
        "USER INPUT: '각 항구에서 탑승한 승객은 몇 명인가요?' QUERY: MATCH (p:Passenger)-[:EMBARKED_AT]->(port:Port) RETURN port.PortName, count(p) AS passengers ORDER BY passengers DESC",
        "USER INPUT: '같은 티켓으로 여행한 승객들을 보여주세요' QUERY: MATCH (p1:Passenger)-[r:TRAVELED_WITH]->(p2:Passenger) RETURN p1.Name, p2.Name, r.Ticket LIMIT 10",
        "USER INPUT: 'C85 선실에 머문 승객은 누구인가요?' QUERY: MATCH (p:Passenger)-[:STAYED_IN]->(c:Cabin) WHERE c.Cabin = 'C85' RETURN p.Name, p.Pclass, p.Survived",
        "USER INPUT: '18세 미만 어린이의 생존율은 어떻게 되나요?' QUERY: MATCH (p:Passenger) WHERE p.Age < 18 AND p.Age IS NOT NULL RETURN count(p) AS total, sum(p.Survived) AS survived, round(100.0 * sum(p.Survived) / count(p), 2) AS survival_rate",
        "USER INPUT: '가족 규모가 생존에 어떤 영향을 미쳤나요?' QUERY: MATCH (p:Passenger) WITH p, p.SibSp + p.Parch AS family_size RETURN CASE WHEN family_size = 0 THEN 'Alone' WHEN family_size <= 3 THEN 'Small' ELSE 'Large' END AS family_category, count(p) AS total, sum(p.Survived) AS survived, round(100.0 * sum(p.Survived) / count(p), 2) AS survival_rate ORDER BY family_category",
        "USER INPUT: '가장 높은 요금을 지불한 승객은 누구인가요?' QUERY: MATCH (p:Passenger) WHERE p.Fare IS NOT NULL RETURN p.Name, p.Fare, p.Pclass ORDER BY p.Fare DESC LIMIT 5"
    ]
    return examples


# ============================================
# Neo4j 연결 관리
# ============================================

# [이 파일에서 정의] 환경변수로 드라이버를 만들고 연결 확인 [반환] Driver
def create_neo4j_driver():
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    # all([a, b, c]): [출처] 파이썬 기본. 모두 값이 있으면 True
    if not all([uri, username, password]):
        raise ValueError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD 환경 변수를 설정해주세요.")

    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        driver.verify_connectivity()
        print(f"✓ Neo4j 연결 성공: {uri}")
    except Exception as e:
        print(f"✗ Neo4j 연결 실패: {e}")
        # raise: 잡은 예외를 그대로 다시 던져서 프로그램을 멈춘다
        raise

    return driver


# [이 파일에서 정의] driver 가 None 이 아닐 때만 닫는다
def close_neo4j_driver(driver):
    if driver:
        driver.close()


# ============================================
# GraphRAG 파이프라인 생성
# ============================================

# OpenAILLM(model_name=..., model_params={...})
# [출처] 외부 라이브러리 neo4j-graphrag
# [입력] model_name: OpenAI 모델 이름 / model_params: OpenAI API 에 그대로 넘길 옵션 딕셔너리
# [반환] LLM 객체. .invoke(프롬프트글) 로 부르면 답을 .content 에 담아 돌려준다
# temperature 0: 같은 질문엔 최대한 같은 Cypher. 쿼리는 창의성보다 정확성이 중요하다
# 파일 맨 위(전역)에서 한 번 만들어 검색기와 GraphRAG 가 같이 쓴다 (Cypher 작성과 답변 작성에 같은 모델)
llm = OpenAILLM(
    model_name="gpt-4o",
    model_params={"temperature": 0}
)

# [이 파일에서 정의] 검색기 + 프롬프트 + LLM 을 조립해서 GraphRAG 객체를 돌려준다
# use_schema, use_examples: False 로 바꿔서 실행해 보며 스키마/예제가 쿼리 품질에 주는 영향을 비교하는 실험용 스위치
def create_graphrag_pipeline(driver, use_schema=True, use_examples=True):

    # 값 if 조건 else None : 스위치가 꺼져 있으면 None
    # schema_json 이 None 이면 schema_text 도 None
    schema_json = get_titanic_schema() if use_schema else None
    schema_text = schema_to_text(schema_json) if schema_json else None
    examples = get_example_queries() if use_examples else None

    # Text2CypherRetriever(driver=..., llm=..., neo4j_schema=..., examples=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] driver: Cypher 를 실행할 연결 / llm: Cypher 를 쓸 LLM
    #        neo4j_schema: 스키마 글. None 이면 만들 때 DB 에서 get_schema() 로 자동으로 읽어 온다
    #        examples: 예제 글 리스트 (None 이면 예제 없이)
    # [반환] 검색기 객체. 이 파일에서는 직접 부르지 않고 GraphRAG 가 내부에서 .search(query_text=...) 를 부른다
    # 내부 동작 (소스 확인):
    #   1) 기본 프롬프트에 끼워 넣기
    #        Task: Generate a Cypher statement ...
    #        Schema: {schema}   Examples (optional): {examples}   Input: {query_text}
    #        Do not use any properties or relationships not included in the schema. ...
    #   2) llm.invoke(프롬프트) -> 답에서 Cypher 만 추출
    #   3) driver.execute_query(Cypher, routing_=READ) -> 읽기 전용 트랜잭션으로 실행 (LLM 이 DELETE 같은 쓰기 쿼리를 쓰면 실행되지 않고 에러가 난다)
    #   4) Record 마다 str(record) 를 content 로 하는 item 을 만들고, metadata["cypher"] 에 쓴 Cypher 를 남긴다
    retriever = Text2CypherRetriever(
        driver=driver,
        llm=llm,
        neo4j_schema=schema_text,
        examples=examples
    )

    # RagTemplate(template=글, expected_inputs=[...])
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] template: 답변 프롬프트 틀. {context} 자리에 검색 결과 글, {query_text} 자리에 질문이 들어간다
    #        expected_inputs: 틀 안에 반드시 있어야 하는 자리 이름. 없으면 만들 때 에러로 알려 준다
    # [왜] 기본 틀(영어, 짧음) 대신 한국어 답변, 숫자 포함, 추측 금지 같은 규칙을 넣으려고
    # 이 틀은 f-string 이 아니다. {context} 는 나중에 라이브러리가 format 으로 채운다
    prompt_template = RagTemplate(
        template="""
당신은 타이타닉 데이터베이스 전문 분석가입니다.
사용자의 질문에 대해 검색된 데이터를 기반으로 정확하고 상세한 답변을 제공하세요.

<retrieval_result>
{context}
</retrieval_result>

<user_query>
{query_text}
</user_query>

<answer_guidelines>
1. 검색된 데이터에 포함된 구체적인 숫자, 이름, 비율 등을 반드시 포함하여 답변하세요.
2. 데이터가 여러 건인 경우 주요 내용을 모두 언급하세요.
3. 검색된 데이터에 없는 정보는 추측하거나 만들어내지 마세요.
4. 검색 결과의 원본 텍스트를 활용하되 한국어로 자연스럽게 작성하세요.
5. 필요한 경우 비교, 순위, 통계 등을 명확히 설명하세요.
</answer_guidelines>

답변:
            """,
        expected_inputs=["context", "query_text"]
    )

    # GraphRAG(retriever=..., llm=..., prompt_template=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [반환] 파이프라인 객체. .search(query_text=...) 하나로 "검색 -> 프롬프트 채우기 -> 답변 생성" 을 다 한다
    rag = GraphRAG(retriever=retriever, llm=llm, prompt_template=prompt_template)
    return rag


# [이 파일에서 정의] 질문을 출력하고 rag.search 를 부른다
# return_context=False 기본값: 이 함수의 매개변수 기본값
def search_with_graphrag(rag, query_text, return_context=False):
    print(f"\n{'=' * 60}")
    print(f"질문: {query_text}")
    print(f"{'=' * 60}")

    try:
        # rag.search(query_text=질문, return_context=True/False)
        # [반환] RagResultModel
        #   .answer: 최종 답변 글
        #   .retriever_result: return_context=True 일 때만 채워진다 (False 면 None)
        #      .items: 검색 결과 리스트. 각 item.content 는 str(Record) 글 (예: <Record total=113 survived=61 survival_rate=53.98>)
        #      .metadata: {"cypher": LLM 이 쓴 Cypher, "__retriever": "Text2CypherRetriever"}
        # 내부: 검색 결과가 0건이어도 그대로 LLM 에 넘긴다 -> 프롬프트 규칙 3("추측 금지")이 중요한 이유
        # GraphRAG 검색 (쿼리 생성 → 실행 → 답변 생성)
        response = rag.search(
            query_text=query_text,
            return_context=return_context,
        )

        return response

    # Cypher 문법 오류(Text2CypherRetrievalError), 연결 오류 등. 출력하고 다시 던진다
    except Exception as e:
        print(f"\n✗ 오류 발생: {e}")
        raise

# ============================================
# 메인 함수
# ============================================

# [이 파일에서 정의] 연결 -> 파이프라인 -> 질문 하나 -> Cypher, 검색 결과, 답변 출력
def main():
    print("\n" + "=" * 60)
    print("타이타닉 지식그래프 기반 Text2Cypher GraphRAG")
    print("=" * 60)

    driver = create_neo4j_driver()

    rag = create_graphrag_pipeline(driver=driver, use_schema=True, use_examples=True)

    # 주석 처리된 질문들: 하나씩 주석을 풀어 바꿔 가며 실행해 보라는 뜻 (마지막 test_query 하나만 실제로 쓰인다)
    # test_query = "타이타닉 참사에서 생존한 승객은 몇 명인가요?"
    # test_query = "1등급 승객의 생존율은 어떻게 되나요?"
    # test_query = "여성 승객은 총 몇 명이었나요?"
    # test_query = "어느 항구에서 가장 많은 승객이 탑승했나요?"
    # test_query = "남성과 여성의 생존율을 비교해주세요"
    # test_query = "3등급 승객 중 생존자는 몇 명인가요?"
    # test_query = "가장 높은 요금을 지불한 승객은 누구인가요?"
    test_query = "어린이(18세 미만)의 생존율은 얼마인가요?"

    # True 면 답변뿐 아니라 "LLM 이 쓴 Cypher" 와 "DB 결과" 도 볼 수 있다 -> 디버깅에 필수
    RETURN_CONTEXT = True
    response = search_with_graphrag( # search 메서드
        rag,
        test_query,
        return_context=RETURN_CONTEXT,
    )

    # hasattr(객체, '속성'): 그 속성이 있으면 True. (RagResultModel 은 항상 retriever_result 속성을 가지므로 사실상 RETURN_CONTEXT 만 의미 있다)
    if RETURN_CONTEXT and hasattr(response, 'retriever_result'):
        print("\n" + "=" * 60)
        print("생성된 Cypher 쿼리문")
        print("=" * 60)
        # metadata 는 딕셔너리 -> ["cypher"] 로 생성된 쿼리 글을 꺼낸다
        print(response.retriever_result.metadata["cypher"]) # Text2CypherRetriever가 생성한 Cypher 쿼리문 출력(검색 결과의 메타데이터)

        print("\n" + "=" * 60)
        print("검색 결과 ")
        print("=" * 60)
        # items 를 하나씩 꺼내 content(글)를 출력. 이 글들이 그대로 답변 프롬프트의 {context} 가 된다
        for i in response.retriever_result.items: # 검색된 데이터들(items)
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