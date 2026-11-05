"""[1단계: 읽기] nodes.py (LangGraph 노드 함수 6개 + 라우팅 함수 3개) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
LangGraph/LangChain/neo4j 설명은 설치 소스(langgraph 1.1.9, langchain-core 1.3.0, langchain-openai 1.2.0, neo4j 6.1.0)로 확인했다.

노드 함수와 라우팅 함수의 약속 (LangGraph)
  노드 함수   : def 이름(state) -> {"바꿀키": 새값, ...}
                state 는 지금까지의 상태 딕셔너리. 돌려준 딕셔너리의 키만 상태에 덮어쓴다 (state.py 주석 참고)
  라우팅 함수 : def route_이름(state) -> "다음 노드 이름"
                main.py 의 add_conditional_edges 에 넘긴다. 상태를 바꾸지 않고 "어디로 갈지" 만 정한다

흐름 (main.py 에서 이렇게 연결된다)
  START -> guardrail_node --route_guardrail--> generate_cypher_node (의료 질문) / answer_node (아님)
  generate_cypher_node -> validate_query_node --route_validation--> execute_cypher_node (통과)
                                                                   correct_cypher_node (실패) -> validate_query_node
                                                                   answer_node (retry_count > 5)
  execute_cypher_node --route_execution--> answer_node (결과 있음 / 재시도 초과 / 빈 결과 재생성 2회 소진)
                                            generate_cypher_node (빈 결과, 2회까지)
                                            correct_cypher_node (실행 오류)
  answer_node -> END

중요: 이 파일은 import 되는 순간 Neo4j 에 접속해 스키마를 읽는다 (schema_str = get_cached_schema() 줄). DB 와 .env 가 준비되어야 import 가 된다.

읽는 순서 권장: guardrail_node -> generate_cypher_node -> validate_query_node -> execute_cypher_node
               -> correct_cypher_node -> route_* 3개 -> answer_node
실행 위치: part4/graphrag_text2cypher_agent 에서  PYTHONPATH=. python learning/step1_nodes_annotated.py
  (state, schema, prompts 를 import 하므로 PYTHONPATH=. 가 필요하다. 주석본은 import 용으로 쓰지 않는다)
  실행하면 DB 접속 + 스키마 조회만 하고 끝난다 (노드를 부르는 코드는 main.py 에 있다)
"""

# [출처] 표준 라이브러리 typing. Literal["a", "b"]: "값은 'a' 나 'b' 중 하나" 라는 타입 힌트
# 라우팅 함수의 반환 타입에 쓰면 LangGraph 가 갈 수 있는 노드 목록으로 읽는다 (main.py 처럼 path_map 을 주면 그쪽이 우선)
from typing import Literal

# [출처] 외부 라이브러리 langchain-core
# ChatPromptTemplate: (역할, 틀글) 목록으로 채팅 프롬프트 틀을 만든다. {자리} 를 채우면 메시지 리스트가 된다
from langchain_core.prompts import ChatPromptTemplate
# [출처] 외부 라이브러리 langchain-openai. ChatOpenAI: LangChain 방식으로 OpenAI 채팅 모델을 부르는 객체
from langchain_openai import ChatOpenAI
# [출처] 외부 라이브러리 pydantic (langchain 이 같이 설치). BaseModel: 필드와 타입을 적으면 검증해 주는 데이터 클래스
# Field(description=...): 필드에 설명을 붙인다. 이 설명이 LLM 에 보내는 JSON 스키마에 들어간다
from pydantic import BaseModel, Field

# [출처] 같은 폴더의 모듈. 같은 폴더의 state.py, schema.py, prompts.py 를 가져온다 (같은 폴더가 sys.path 에 있어야 찾는다)
from state import State
from schema import NEO4J_DATABASE, get_neo4j_driver, get_cached_schema
from prompts import (
    FEWSHOT_EXAMPLES_STR,
    GENERATE_CYPHER_PROMPTS,
    CORRECT_CYPHER_PROMPTS,
    FINAL_ANSWER_PROMPTS,
)


# LLM 초기화
# ChatOpenAI(model="gpt-4o")
# [출처] 외부 라이브러리 langchain-openai
# [입력] model: OpenAI 모델 이름. api_key 를 안 주면 OPENAI_API_KEY 환경변수를 읽는다
#        temperature 를 안 주면 None -> API 에 보내지 않아 OpenAI 서버 기본값을 쓴다 (소스 확인: temperature: float | None = None)
# [반환] 채팅 모델 객체. .invoke(메시지 리스트) -> AIMessage (글은 .content)
# 모듈 전역에 하나 만들어 모든 노드가 같이 쓴다
llm = ChatOpenAI(model="gpt-4o")

# Neo4j 드라이버 및 스키마 초기화
# schema.py 의 함수: 환경변수 확인 후 드라이버 생성 (Cypher 실행용, 프로그램이 끝날 때까지 열어 둔다)
driver = get_neo4j_driver()
# 스키마 글을 DB 에서 한 번 읽어 둔다. 이 줄 때문에 nodes.py 를 import 만 해도 DB 에 접속한다
# 주의: 그래프 실행 중 데이터가 바뀌어도 이 schema_str 은 갱신되지 않는다 (get_cached_schema(refresh=True) 를 다시 불러야 한다)
schema_str = get_cached_schema()

# 데이터베이스 이름
# execute_query(database_=...) 에 넣을 DB 이름
database = NEO4J_DATABASE


# ============================================
# Pydantic 모델 정의
# ============================================

# [이 파일에서 정의] guardrail 판정 결과의 모양. class 이름(BaseModel): BaseModel 을 상속한 pydantic 모델
# binary_score: str 필드 하나. LLM 이 {"binary_score": "yes"} 같은 JSON 을 내게 만든다
# class 의 docstring 과 Field 설명이 LLM 에 보내는 스키마 설명으로 쓰인다
class GuardrailGrade(BaseModel):
    """Binary score for database relevance check."""
    binary_score: str = Field(description="Relevance score 'yes' or 'no'")


# ============================================
# 노드 함수들
# ============================================

# [이 파일에서 정의] 노드 1. 질문이 의료 그래프와 관련 있는지 LLM 에 yes/no 로 묻는다
# [입력] state: 상태 딕셔너리 (state["query"] 사용)  [반환] {"is_db_related": True/False}
# 매개변수 state: State 의 ": State" 는 타입 힌트 (실제로는 그냥 dict 가 들어온다)
def guardrail_node(state: State):
    """질문이 의료 지식 그래프 DB와 관련이 있는지 확인"""
    print("\n###### GUARDRAIL CHECK ######")

    # state["query"]: 입력으로 반드시 들어오는 키라 [] 로 바로 꺼낸다 (없으면 KeyError)
    user_question = state["query"]
    print(f"사용자 질문: {user_question}")

    # llm.with_structured_output(GuardrailGrade)
    # [출처] 외부 라이브러리 langchain-openai (ChatOpenAI 의 메서드)
    # [입력] 원하는 출력 모양 (pydantic 클래스)
    # [반환] 새 Runnable. invoke 하면 글이 아니라 GuardrailGrade 객체가 나온다
    # 내부 동작 (소스 확인): ChatOpenAI 에서는 기본 method="json_schema" -> OpenAI 의 구조화 출력 기능으로 JSON 을 강제하고 pydantic 으로 파싱
    # [왜] "yes", "Yes.", "네" 처럼 제멋대로인 글 대신 정해진 필드로 받으려고
    grader = llm.with_structured_output(GuardrailGrade)

    # ChatPromptTemplate.from_messages([(역할, 틀글), ...])
    # [출처] 외부 라이브러리 langchain-core
    # [입력] ("system", 글), ("user", "{question}") 같은 튜플 리스트. {question} 이 나중에 채울 자리
    # [반환] ChatPromptTemplate 객체 (Runnable 이라 | 로 다른 것과 이을 수 있다)
    # 시스템 메시지에 카테고리 6개와 yes/no 예시를 적어 판단 기준을 준다
    guardrail_prompt = ChatPromptTemplate.from_messages([
        ("system", """
당신은 질문이 의료 지식 그래프 데이터베이스와 관련이 있는지 판단하는 AI입니다.

의료 지식 그래프는 다음 정보를 포함합니다:
- 증상(Symptom): 발열, 기침, 두통 등
- 질병(Disease): 폐렴, 당뇨병, 고혈압 등
- 검사(Test): 혈액 검사, X-ray, MRI 등
- 치료법(Treatment): 물리치료, 수술, 방사선 치료 등
- 약물(Medication): 아스피린, 인슐린, 항생제 등
- 신체 부위(Anatomy): 폐, 심장, 뇌 등

질문이 위 카테고리 중 하나와 관련이 있으면 'yes'를, 그렇지 않으면 'no'를 반환하세요.
예시:
- '기침 증상과 관련된 질병은?' → yes
- '오늘 날씨는?' → no
- '파이썬 코드를 작성해줘' → no
- '두통에 좋은 약은?' → yes
        """),
        ("user", "{question}")
    ])

    # 체인 구성 및 실행
    # A | B : LangChain 의 파이프 문법 (LCEL). A 의 출력이 B 의 입력으로 가는 RunnableSequence 를 만든다
    # 여기서는 "프롬프트 틀 채우기 -> 구조화 출력 LLM" 두 단계
    chain = guardrail_prompt | grader
    # chain.invoke({"question": ...}): 딕셔너리의 값으로 {question} 을 채우고 LLM 까지 부른다 [반환] GuardrailGrade 객체
    scored_result = chain.invoke({"question": user_question})
    # pydantic 객체는 속성(.binary_score)으로 값을 꺼낸다
    score = scored_result.binary_score

    # .lower() 로 소문자로 바꿔 비교 -> "Yes" 도 yes 로 인정
    is_related = score.lower() == "yes"
    print(f"DB 관련 질문 여부: {is_related} (score: {score})")

    # 노드의 반환: 바꿀 키만. LangGraph 가 이 값을 상태의 is_db_related 칸에 덮어쓴다
    return {
        "is_db_related": is_related
    }


# [이 파일에서 정의] 노드 2. 스키마 + few-shot 예시 + 질문으로 Cypher 를 만든다
# [반환] {"cypher": 새 쿼리, "regenerate_count": 횟수, "result_empty": False}
def generate_cypher_node(state: State):
    """Cypher 쿼리 생성"""
    print("\n###### GENERATE CYPHER ######")

    # 빈 결과로 인한 재생성인지 확인
    # state.get(키, 기본값): 딕셔너리 메서드. 키가 없으면 기본값 (첫 실행엔 result_empty 가 아직 상태에 없다)
    result_empty = state.get("result_empty", False)
    regenerate_count = state.get("regenerate_count", 0)

    # 빈 결과 때문에 다시 온 것이면 재생성 횟수 +1
    # 주의: 이전 쿼리가 빈 결과였다는 사실을 프롬프트에 알려 주지 않는다. 같은 프롬프트를 다시 보내므로
    #       같은 쿼리가 또 나올 수 있다 (GUIDE 생각해 볼 점 4)
    if result_empty:
        regenerate_count += 1
        print(f"빈 결과로 인한 쿼리 재생성 ({regenerate_count}회차)")

    # prompts.py 의 [("system", ...), ("user", ...)] 로 프롬프트 틀을 만든다
    text2cypher_prompt = ChatPromptTemplate.from_messages(GENERATE_CYPHER_PROMPTS)

    # llm.invoke(메시지 리스트) [반환] AIMessage. 체인(|) 대신 "틀 채우기" 와 "LLM 부르기" 를 따로 쓴 방식
    # text2cypher_prompt.format_messages(이름=값, ...): [출처] langchain-core. {자리} 를 채워 [SystemMessage, HumanMessage] 리스트를 돌려준다
    response = llm.invoke(
        text2cypher_prompt.format_messages(
            question=state["query"],
            schema=schema_str,
            fewshot_examples=FEWSHOT_EXAMPLES_STR,
        )
    )

    # response.content: LLM 이 쓴 글 (Cypher 쿼리여야 한다)
    print(f"생성된 쿼리: {response.content}")

    return {
        "cypher": response.content,
        "regenerate_count": regenerate_count,
        # 다음 실행에서 또 빈 결과인지 새로 판단하도록 False 로 되돌린다
        "result_empty": False,  # 리셋
    }


# [이 파일에서 정의] 노드 3. 실행 전에 규칙으로 쿼리를 검사한다 (LLM 을 쓰지 않는 순수 코드)
# [반환] {"validation_error": ""} (통과) 또는 {"validation_error": "이유"} (실패)
def validate_query_node(state: State):
    """Cypher 쿼리 검증"""
    print("\n###### VALIDATE QUERY ######")

    cypher_query = state.get("cypher")
    # 쿼리가 없거나 빈 글이면 실패
    # 주의: 그다음 correct_cypher_node 가 "No Cypher found" 예외를 낸다 (cypher 가 비어 있으므로)
    if not cypher_query:
        return {"validation_error": "쿼리를 찾을 수 없습니다"}

    print(f"검증할 쿼리: {cypher_query}")

    # 1. 위험한 쿼리 키워드 체크
    # 쓰기/삭제 Cypher 키워드 목록. LLM 이 만든 쿼리가 DB 를 바꾸지 못하게 막는 유일한 장치다
    # (execute_cypher_node 의 execute_query 는 기본이 쓰기 모드(routing_=WRITE)라 DB 쪽에서는 막지 않는다. 소스 확인)
    dangerous_keywords = ["DELETE", "DROP", "CREATE", "MERGE", "REMOVE", "SET", "DETACH"]
    # .upper(): 대문자로 바꿔 "delete" 도 잡는다
    cypher_upper = cypher_query.upper()

    for keyword in dangerous_keywords:
        # 키워드 in 글: 부분 문자열 검사
        # 주의: "SET" in "OFFSET", "CREATE" in "CREATED_AT" 처럼 정상 쿼리도 걸린다.
        #       반대로 CALL 로 프로시저를 부르는 쓰기는 못 막는다. 정규식 단어 경계 \b 를 쓰거나 읽기 전용 실행이 더 안전하다
        if keyword in cypher_upper:
            error_msg = f"위험한 쿼리 감지: {keyword} 키워드는 사용할 수 없습니다"
            print(f"✗ 검증 실패: {error_msg}")
            # 첫 실패에서 바로 return (나머지 검사는 하지 않는다)
            return {
                "validation_error": error_msg
            }

    # 2. 기본 문법 검증
    # .strip().startswith("MATCH"): 앞뒤 공백을 지우고 MATCH 로 시작하는지
    # 주의: OPTIONAL MATCH, WITH, CALL {...}, UNWIND 로 시작하는 정상 쿼리와 ```cypher 로 감싼 쿼리도 실패로 본다
    if not cypher_upper.strip().startswith("MATCH"):
        error_msg = "쿼리는 MATCH로 시작해야 합니다"
        print(f"✗ 검증 실패: {error_msg}")
        return {
            "validation_error": error_msg
        }

    # RETURN 이 글 어딘가에 있는지 (이것도 부분 문자열 검사)
    if "RETURN" not in cypher_upper:
        error_msg = "쿼리에 RETURN 절이 필요합니다"
        print(f"✗ 검증 실패: {error_msg}")
        return {
            "validation_error": error_msg
        }

    print("✓ 검증 통과")
    return {
        # 빈 문자열 "" 은 거짓(falsy) -> route_validation 의 not validation_error 가 True 가 되어 실행으로 간다
        "validation_error": ""
    }


# [이 파일에서 정의] 노드 4. 쿼리를 Neo4j 에서 실행한다
# [반환] {"db_outputs": [결과], "result_empty": bool}. 결과는 성공이면 list[dict], 실패면 오류 str
def execute_cypher_node(state: State):
    """Cypher 쿼리 실행"""
    print("\n###### EXECUTE CYPHER ######")

    cypher_query = state.get("cypher")
    if not cypher_query:
        # raise ValueError: 이 경우는 그래프 흐름상 생기면 안 되는 상황이라 예외로 멈춘다
        raise ValueError("No cypher query found in state")

    print(f"실행 쿼리: {cypher_query}")

    # try/except: try 블록에서 에러가 나면 except 블록으로 넘어간다. 프로그램을 멈추지 않고 오류를 "값" 으로 바꾼다
    # [왜] 오류 메시지를 상태에 남겨야 correct_cypher_node 가 LLM 에게 "이 오류를 고쳐라" 고 넘길 수 있다
    try:
        # driver.execute_query(쿼리, database_=...)
        # [출처] 외부 라이브러리 neo4j
        # [입력] Cypher 글, database_: DB 이름 (끝의 _ 는 쿼리 매개변수 이름과 겹치지 않게 붙인 드라이버 규칙)
        #        routing_ 기본값은 RoutingControl.WRITE (소스 확인)
        # [반환] EagerResult (records, summary, keys 세 칸짜리 튜플). 결과를 메모리에 다 받아 온다
        result = driver.execute_query(cypher_query, database_=database)

        # result.records를 리스트로 변환
        # record.data(): Record -> 보통 딕셔너리 {"d.name": "폐렴"} (노드 값도 속성 딕셔너리로 바뀐다)
        # [왜] 상태에 담고 LLM 에 넘기기 쉬운 파이썬 기본 타입으로
        database_output = [record.data() for record in result.records]

        print(f"조회 결과: {database_output}")

        # 빈 결과 플래그 설정
        # len(리스트) == 0 이면 True. 비교식의 결과(True/False)를 바로 변수에 담는다
        result_empty = len(database_output) == 0

    # except Exception as e: 거의 모든 에러를 잡아 e 에 담는다. Cypher 문법 오류, 없는 속성, 연결 오류 등
    # str(e): 에러 메시지 글. 이후 라우팅은 "결과가 str 이면 오류" 로 구분한다
    except Exception as e:
        database_output = str(e)
        result_empty = False
        print(f"조회 실패: {database_output}")

    return {
        # [database_output]: 리스트로 한 번 감싼다. 리듀서가 없어 덮어쓰기라 항상 원소 하나짜리 (state.py 주석)
        "db_outputs": [database_output],
        "result_empty": result_empty,
    }


# [이 파일에서 정의] 노드 5. 오류가 난 쿼리를 LLM 에게 고치게 한다
# [반환] {"cypher": 고친 쿼리, "retry_count": +1}
def correct_cypher_node(state: State):
    """Cypher 쿼리 수정"""
    print("\n###### CORRECT CYPHER ######")

    # if 변수 := 식: "바다코끼리 연산자" (파이썬 3.8+). 식의 값을 변수에 담으면서 동시에 참/거짓을 검사한다
    # 빈 리스트 [] 는 거짓 -> else 로 간다
    # 주의: 첫 쿼리가 validate 에서 떨어져 바로 여기로 오면 아직 실행한 적이 없어서 db_outputs 가 상태에 없다
    #       (LangGraph 는 아직 쓰지 않은 키를 state 에서 뺀다. 소스 확인: read_channels 가 빈 칸을 건너뜀)
    #       -> [] -> "No DB result found" 예외로 그래프가 멈춘다. 이 경우엔 validation_error 를 오류로 넘겨야 한다 (GUIDE 생각해 볼 점 1)
    #       또 이전에 실행한 적이 있으면 "지난번 실행 결과" 가 오류로 넘어가 이번 검증 실패 이유와 다를 수 있다
    if messages := state.get("db_outputs", []):
        # 리스트[-1]: 마지막 원소. db_outputs 는 원소 하나짜리라 사실상 그 하나
        db_result = messages[-1]
    else:
        raise ValueError("No DB result found")

    cypher = state.get("cypher")
    if not cypher:
        raise ValueError("No Cypher found")

    print(f"수정 전 쿼리: {cypher}")
    print(f"에러 내용: {db_result}")

    correct_cypher_prompt = ChatPromptTemplate.from_messages(CORRECT_CYPHER_PROMPTS)

    # 수정 프롬프트: 스키마, 질문, 틀린 쿼리, 오류를 모두 넣는다
    response = llm.invoke(
        correct_cypher_prompt.format_messages(
            question=state["query"],
            schema=schema_str,
            cypher=cypher,
            errors=db_result,
        )
    )

    print(f"수정 후 쿼리: {response.content}")

    return {
        "cypher": response.content,
        # state.get("retry_count", 0) + 1: 처음이면 0 에서 시작
        "retry_count": state.get("retry_count", 0) + 1
    }


# [이 파일에서 정의] 노드 6. 최종 답변 [반환] {"answer": 답변 글}
# 세 경우: 의료 질문 아님 -> 일반 답변 / 정상 결과 -> 결과 기반 답변 / 오류 str -> 오류 설명 답변
def answer_node(state: State):
    """최종 답변 생성"""
    print("\n###### ANSWER GENERATION ######")

    # guardrail 을 거쳤으면 항상 값이 있다. 기본 True 는 혹시 없을 때 DB 쪽 답변으로 가게
    is_db_related = state.get("is_db_related", True)

    # DB 관련 질문이 아닌 경우 직접 답변
    if not is_db_related:
        print("DB 관련 질문이 아니므로 일반 답변 생성")

        # 일반 답변용 프롬프트를 함수 안에서 바로 만든다
        general_answer_prompt = ChatPromptTemplate.from_messages([
            ("system", """당신은 친절한 AI 어시스턴트입니다.
사용자의 질문이 의료 지식 그래프 데이터베이스와 관련이 없으므로,
데이터베이스를 사용하지 않고 일반적인 답변을 제공해주세요.
반드시 한국어로 답변하세요."""),
            ("user", "{question}")
        ])

        response = llm.invoke(
            general_answer_prompt.format_messages(
                question=state["query"]
            )
        )

        print(f"일반 답변: {response.content}\n")

        return {
            "answer": response.content
        }

    # DB 관련 질문인 경우 - DB 결과 기반 답변 (정상 결과 또는 에러 모두 처리)
    print("DB 결과 기반 답변 생성")

    # 주의: route_validation 이 retry_count > 5 로 여기로 보냈는데 한 번도 실행이 안 됐다면 db_outputs 가 없어 예외가 난다
    if messages := state.get("db_outputs", []):
        db_result = messages[-1]
    else:
        raise ValueError("No DB result found")

    cypher = state.get("cypher")
    if not cypher:
        raise ValueError("No Cypher found")

    # isinstance(db_result, str): 오류는 str, 정상은 list 로 저장했던 약속을 이용해 구분
    is_error = isinstance(db_result, str)

    if is_error:
        # db_result[:100]: 슬라이싱. 글의 앞 100글자만
        print(f"에러 기반 답변 생성: {db_result[:100]}...")
    else:
        print(f"정상 결과 기반 답변 생성: {len(db_result)}개 레코드")

    final_answer_prompt = ChatPromptTemplate.from_messages(FINAL_ANSWER_PROMPTS)

    # 최종 답변 프롬프트. 정상이든 오류든 같은 틀로 보내고, 시스템 메시지가 경우에 따라 답하는 법을 알려 준다
    response = llm.invoke(
        final_answer_prompt.format_messages(
            cypher_query=cypher,
            context=db_result,
            question=state["query"],
        )
    )

    print(f"최종 답변: {response.content}\n")

    return {
        "answer": response.content
    }


# ============================================
# 라우팅 함수들(조건 함수)
# ============================================

# [이 파일에서 정의] 라우팅 1 (guardrail 다음). [반환] "generate_cypher" 또는 "answer"
# -> Literal[...]: 반환값이 이 둘 중 하나라는 타입 힌트. 반환한 글을 main.py 의 path_map 이 실제 노드 이름으로 바꾼다
def route_guardrail(state: State) -> Literal["generate_cypher", "answer"]:
    """
    질문이 DB 관련 질문인지 확인하고 라우팅
    """
    is_db_related = state.get("is_db_related", True)

    print("\n###### ROUTE GUARDRAIL ######")
    print(f"DB 관련 질문: {is_db_related}")

    if is_db_related:
        print("→ Cypher 쿼리 생성으로 이동")
        return "generate_cypher"
    else:
        print("→ DB 관련 질문 아님 - 직접 답변")
        return "answer"


# [이 파일에서 정의] 라우팅 2 (validate_query 다음). [반환] "execute_cypher" / "correct_cypher" / "answer"
def route_validation(state: State) -> Literal["execute_cypher", "correct_cypher", "answer"]:
    """
    쿼리 검증 결과에 따라 라우팅
    """
    validation_error = state.get("validation_error", "")
    retry_count = state.get("retry_count", 0)

    print("\n###### ROUTE VALIDATION ######")
    print(f"재시도 횟수: {retry_count}/5")

    # 재시도 횟수가 5를 초과하면 답변 생성으로 이동
    # 재시도 상한을 먼저 본다 (검증 결과보다 우선)
    # 주의: > 5 라서 retry_count 가 6 이 되어야 탈출한다. 즉 수정을 6 번 하고 나서 멈춘다 (GUIDE 생각해 볼 점 5)
    # LangGraph 자체의 반복 상한(recursion_limit)은 1.1.9 기본값이 10007 이라 (소스 확인) 이 코드의 상한이 실제로 무한 반복을 막는다
    if retry_count > 5:
        # f-string 인데 {} 가 없다. 그냥 글과 같다 (f 가 없어도 된다)
        print(f"✗ 최대 재시도 횟수(5회) 초과 - 답변 생성으로 이동")
        return "answer"

    if not validation_error:
        print("✓ 검증 통과 - 쿼리 실행으로 이동")
        return "execute_cypher"
    else:
        print(f"✗ 검증 실패: {validation_error} - 쿼리 수정으로 이동")
        return "correct_cypher"


# [이 파일에서 정의] 라우팅 3 (execute_cypher 다음). [반환] "generate_cypher" / "correct_cypher" / "answer"
# max_regenerate: int = 2 : 기본값 있는 매개변수. LangGraph 는 state 만 넘겨 부르므로 항상 2 가 쓰인다
# (config, writer, store 같은 정해진 이름만 LangGraph 가 채워 준다. 소스 확인: _internal/_runnable.py KWARGS_CONFIG_KEYS)
def route_execution(state: State, max_regenerate: int = 2) -> Literal["generate_cypher", "correct_cypher", "answer"]:
    """
    쿼리 실행 결과에 따라 라우팅
    - 빈 결과: 재생성 (최대 2회)
    - 에러: 수정 (기존 로직)
    - 정상: 답변 생성
    """
    # 바다코끼리 연산자 := (correct_cypher_node 에서 설명). 실행 노드 바로 다음이라 db_outputs 는 항상 있다
    if db_outputs := state.get("db_outputs", []):
        db_result = db_outputs[-1]
    else:
        raise ValueError("No DB result found")

    regenerate_count = state.get("regenerate_count", 0)
    retry_count = state.get("retry_count", 0)

    print("\n###### ROUTE EXECUTION ######")
    print(f"재생성 횟수: {regenerate_count}/{max_regenerate}")
    print(f"재시도 횟수: {retry_count}/5")

    # 재시도 횟수가 5를 초과하면 답변 생성으로 이동
    if retry_count > 5:
        print(f"✗ 최대 재시도 횟수(5회) 초과 - 답변 생성으로 이동")
        return "answer"

    # 정상 조회 (결과가 있음)
    # type(x) == list: 타입이 정확히 list 인지. 정상 결과는 list, 오류는 str 이라는 약속으로 3가지를 나눈다
    # (관례상 isinstance(x, list) 를 더 많이 쓴다)
    if type(db_result) == list and len(db_result) > 0:
        print("✓ 정상 조회 완료!")
        return "answer"

    # 빈 결과 처리
    if type(db_result) == list and len(db_result) == 0:
        # regenerate_count 는 generate_cypher_node 가 올린다. 0, 1 일 때 재생성 -> 최대 2 번
        if regenerate_count < max_regenerate:
            print(f"✗ 빈 결과 - 쿼리 재생성 ({regenerate_count + 1}/{max_regenerate})")
            return "generate_cypher"
        else:
            print(f"✗ 최대 재생성 횟수({max_regenerate}회) 초과 - 답변 생성으로 이동")
            return "answer"

    # 에러 발생
    # 여기까지 왔으면 db_result 가 str (오류) -> 쿼리 수정
    print("✗ 쿼리 실행 오류 - 쿼리 수정으로 이동")
    return "correct_cypher"
