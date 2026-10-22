"""
[2단계: 빈칸 채우기] neo4j-graphrag 없이 Text2Cypher 를 직접 구현한다. 라이브러리가 대신 해 주던 일을 손으로 해 보는 것이 목적.

  질문 -> (스키마 + 예시 + 질문) 프롬프트 -> LLM -> Cypher 추출 -> 안전 검사 -> 읽기 트랜잭션 실행 -> 답변 생성

전제: part2/csv2kg 로 타이타닉 그래프가 적재되어 있다.
실행: part3/text2cypher 에서 `python learning/step2_fill_in.py "1등급 승객의 생존율은?"`
막히면 GUIDE.md -> text2cypher.ipynb(셀 5, 8) -> text2cypher.py
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase, RoutingControl
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from text2cypher import get_example_queries, get_titanic_schema, schema_to_text  # noqa: E402

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
MODEL = "gpt-4o"


# ---------- 1. 프롬프트 ----------
def build_prompt(question: str) -> str:
    schema = schema_to_text(get_titanic_schema())
    examples = "\n".join(get_example_queries())
    # TODO 1: 아래 4가지를 포함한 프롬프트 문자열을 만든다.
    #   - 역할: "Neo4j Cypher 전문가"
    #   - <schema> 블록: 위 schema. "스키마에 있는 레이블/속성/관계만 사용" 규칙
    #   - <examples> 블록: 위 examples
    #   - 출력 규칙: "설명 없이 Cypher 쿼리 하나만", "읽기 전용(MATCH/RETURN)만"
    #   - 마지막에 질문
    ...


# ---------- 2. 추출 ----------
def extract_cypher(text: str) -> str:
    # TODO 2: ```cypher ... ``` 또는 ``` ... ``` 코드블록이 있으면 안쪽만, 없으면 전체를 strip 해서 돌려준다.
    #   힌트: re.findall(r"```(?:cypher)?(.*?)```", text, re.DOTALL)
    ...


# ---------- 3. 안전 검사 ----------
WRITE_KEYWORDS = ("CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP", "LOAD CSV", "CALL DBMS")


def is_read_only(cypher: str) -> bool:
    # TODO 3: 대문자로 바꾼 쿼리에 WRITE_KEYWORDS 가 "단어로" 들어 있으면 False.
    #   단순 `in` 검사는 "OFFSET" 안의 "SET" 도 잡는다. 정규식 \b 경계를 쓰자.
    #   이 검사만으로 충분한가? (아래 run 에서 읽기 트랜잭션으로 한 번 더 막는다)
    ...


# ---------- 4. 실행 ----------
def run(driver, cypher: str) -> list[dict]:
    # TODO 4: execute_query 에 routing_=RoutingControl.READ 를 주고 실행해 [record.data() ...] 를 돌려준다.
    #   결과가 너무 많으면 프롬프트가 길어진다. 앞 50행만 쓰자.
    #   참고: 읽기 라우팅만으로는 단일 서버에서 쓰기가 막히지 않을 수 있다.
    #         확실히 막으려면 session.execute_read(...) 또는 읽기 전용 계정을 쓴다.
    ...


# ---------- 5. 답변 ----------
def answer(client: OpenAI, question: str, cypher: str, rows: list[dict]) -> str:
    # TODO 5: 질문, 실행한 Cypher, 결과 행을 주고 한국어로 답하게 한다.
    #   규칙: "결과에 없는 정보는 지어내지 말 것", "결과가 비면 찾지 못했다고 말할 것"
    ...


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "1등급 승객의 생존율은?"
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL, temperature=0, messages=[{"role": "user", "content": build_prompt(question)}]
        )
        cypher = extract_cypher(resp.choices[0].message.content)
        print("[Cypher]\n", cypher)

        if not is_read_only(cypher):
            print("쓰기 쿼리라서 실행하지 않습니다.")
            return

        # TODO 6 (심화): 실행이 실패하면 에러 메시지를 프롬프트에 붙여 한 번 더 생성하게 해 보자. (Part 4 의 "쿼리 수정 자동화" 예고)
        rows = run(driver, cypher)
        print("[결과]", rows[:5] if rows else rows)
        print("[답변]", answer(client, question, cypher, rows or []))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
