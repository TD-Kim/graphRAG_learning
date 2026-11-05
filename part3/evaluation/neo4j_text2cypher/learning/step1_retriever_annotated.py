"""[1단계: 읽기] retriever.py (평가용 Text2CypherRetriever 생성 + Cypher 생성/실행 도우미) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1)로 확인했다.

이 파일은 직접 실행하지 않는다 (__main__ 없음). eval.py 가
  create_driver, create_llm, build_retriever, generate_and_execute_cypher
를 import 해서 쓴다. (execute_cypher 는 eval.py 에서 쓰이지 않는다. step2 실습에서 정답 Cypher 실행용으로 쓸 수 있다)

흐름
  create_driver() -> Driver (연결 확인까지)
  create_llm()    -> OpenAILLM gpt-4o (Cypher 작성 + eval.py 의 채점에 같은 모델)
  build_retriever(driver, llm, 스키마 글, 예제) -> Text2CypherRetriever
  generate_and_execute_cypher(retriever, 질문) -> (생성된 Cypher, 결과 딕셔너리 리스트, 에러 글 또는 None)

읽는 순서 권장: generate_and_execute_cypher -> build_retriever -> create_driver/create_llm -> execute_cypher
실행 위치: part3/evaluation/neo4j_text2cypher 에서 PYTHONPATH=. python learning/step1_retriever_annotated.py
  (함수 정의만 있어서 실행해도 아무것도 출력되지 않는다. 주석본은 import 용으로 쓰지 않는다)
"""

# [출처] 표준 라이브러리. os.getenv: 환경변수 읽기
import os
# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버. GraphDatabase.driver 로 연결 객체를 만든다
from neo4j import GraphDatabase
# [출처] 외부 라이브러리 neo4j-graphrag. Text2CypherRetriever: 질문 -> LLM 이 Cypher 작성 -> 실행
from neo4j_graphrag.retrievers import Text2CypherRetriever
# OpenAILLM: OpenAI 채팅 모델 감싸개. OPENAI_API_KEY 환경변수를 자동으로 읽는다
from neo4j_graphrag.llm import OpenAILLM

# import 될 때 .env 를 읽는다 (eval.py 도 따로 load_dotenv 를 부른다. 두 번 불러도 문제 없다)
load_dotenv()


# [이 파일에서 정의] Neo4j 드라이버를 만들고 연결을 확인한다 [반환] Driver
def create_driver():
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    # GraphDatabase.driver(uri, auth=(아이디, 비밀번호)): [출처] neo4j. 연결 객체 (아직 접속 전)
    driver = GraphDatabase.driver(uri, auth=(username, password))
    # driver.verify_connectivity(): 실제로 접속해 본다. 주소/비밀번호가 틀리면 여기서 바로 에러 -> 평가 도중이 아니라 시작할 때 알 수 있다
    driver.verify_connectivity()
    return driver


# [이 파일에서 정의] 평가에 쓸 LLM [반환] OpenAILLM
def create_llm():
    # OpenAILLM(model_name, model_params): temperature 0 = 같은 질문엔 최대한 같은 답 (평가를 다시 돌려도 점수가 덜 흔들리게)
    return OpenAILLM(
        model_name="gpt-4o",
        model_params={"temperature": 0},
    )


# [이 파일에서 정의] Text2CypherRetriever 를 만든다
# neo4j_schema: str, examples: list[str] | None = None : 타입 힌트. "X | None" 은 X 또는 None (파이썬 3.10+ 문법)
#   = None 은 기본값. examples 를 안 주면 예제 없이(zero-shot) Cypher 를 쓴다 (eval.py 는 안 준다)
def build_retriever(driver, llm, neo4j_schema: str, examples: list[str] | None = None):
    """Text2CypherRetriever 인스턴스를 생성합니다.

    Args:
        driver: Neo4j 드라이버
        llm: LLM 인스턴스
        neo4j_schema: 스키마 텍스트
        examples: few-shot 예시 목록 (선택)
    """
    # Text2CypherRetriever(driver=..., llm=..., neo4j_schema=..., examples=...)
    # [출처] 외부 라이브러리 neo4j-graphrag
    # [입력] neo4j_schema: 스키마 글 (eval.py 는 text2cypher_schemas.csv 의 recommendations 스키마 글을 준다)
    #        examples: 예제 글 리스트 또는 None
    # [반환] 검색기
    # 내부 동작 (소스 확인): 만들 때 Neo4j 버전 확인 쿼리를 실행한다. neo4j_database 를 안 주므로 이후 모든 쿼리가 서버의 기본 DB 로 간다
    # 주의: eval.py 의 --neo4j-db 인자는 여기까지 전달되지 않는다
    return Text2CypherRetriever(
        driver=driver,
        llm=llm,
        neo4j_schema=neo4j_schema,
        examples=examples,
    )


# [이 파일에서 정의] 질문 하나로 Cypher 생성 + 실행
# -> tuple[str, list[dict], str | None]: 반환 타입 힌트. (글, 딕셔너리 리스트, 글 또는 None) 세 개짜리 튜플
def generate_and_execute_cypher(
    retriever: Text2CypherRetriever, question: str
) -> tuple[str, list[dict], str | None]:
    """질문으로부터 Cypher를 생성하고 실행합니다.

    retriever.get_search_results()를 사용하여 Cypher 생성 + 실행을 한번에 처리하고,
    metadata에서 생성된 Cypher를 추출합니다.

    Returns:
        (generated_cypher, results, error): 생성된 Cypher, 결과 리스트, 에러 문자열
    """
    # try / except Exception: 생성이나 실행 중 어떤 에러가 나도 프로그램을 멈추지 않고 "실패" 로 기록하려고
    try:
        # retriever.get_search_results(query_text=질문)
        # [출처] 외부 라이브러리 neo4j-graphrag (search 가 내부에서 부르는 메서드를 직접 부름)
        # [반환] RawSearchResult. .records: neo4j Record 리스트 / .metadata: {"cypher": 실행한 Cypher}
        # [왜] search() 는 Record 를 RetrieverResultItem(content=str(record)) 로 바꾼다. 평가에는 원래 Record 값이 필요해서 한 단계 아래를 부른다
        # 내부 동작 (소스 확인):
        #   프롬프트 "Task: Generate a Cypher statement ... Schema: {schema} Examples (optional): {examples} Input: {query_text} ..."
        #   -> llm.invoke -> extract_cypher(``` 코드블록 안쪽만, 띄어쓰기 있는 이름에 백틱) -> execute_query(routing_=READ, 읽기 전용)
        #   Cypher 문법 오류는 Text2CypherRetrievalError, 그 밖의 DB 오류는 neo4j 예외 그대로
        search_result = retriever.get_search_results(query_text=question)
        # metadata.get("cypher", ""): 키가 없으면 빈 글
        generated_cypher = search_result.metadata.get("cypher", "")
        # [dict(record) for record in ...]: 리스트 컴프리헨션. Record 를 {열이름: 값} 딕셔너리로 바꾼다
        # 주의: 값이 노드/관계(Node, Relationship)나 날짜 타입이면 eval.py 의 json.dumps 저장에서 에러가 날 수 있다
        results = [dict(record) for record in search_result.records]
        return generated_cypher, results, None
    # except Exception as e: 에러 객체를 e 로 받아 str(e) 로 메시지만 돌려준다
    # 주의: 실패하면 생성된 Cypher 도 "" 로 버려진다. LLM 이 쓴 쿼리가 실행에서 실패한 경우에도 무엇을 썼는지 볼 수 없다
    #       (문법 오류 메시지 안에 쿼리 일부가 들어 있을 수는 있다)
    except Exception as e:
        return "", [], str(e)


# [이 파일에서 정의] 임의의 Cypher 를 실행하고 (결과, 에러) 를 돌려준다
# database: str = "neo4j": 기본값이 있는 매개변수
# 주의: eval.py 에서 쓰이지 않는다. routing_ 을 안 줘서 쓰기 쿼리도 그대로 실행된다
def execute_cypher(driver, cypher: str, database: str = "neo4j") -> tuple[list[dict], str | None]:
    """Cypher 쿼리를 실행하고 결과와 에러를 반환합니다.

    Returns:
        (results, error): 결과 리스트와 에러 문자열 (없으면 None)
    """
    try:
        # records, _, _ = ...: EagerResult 는 (records, summary, keys) 로 풀 수 있다. _ 는 "안 쓰는 값" 이라는 관례 이름
        records, _, _ = driver.execute_query(
            cypher,
            database_=database,
        )
        results = [dict(record) for record in records]
        return results, None
    except Exception as e:
        return [], str(e)
