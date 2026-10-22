"""
[2단계: 빈칸 채우기] 안전한 Cypher 실행 도구 + 스키마 캐시를 직접 만들고, 원본의 나머지 도구와 함께 에이전트에 넣는다.

전제: graphrag_tool_agent 를 원본대로 실행할 수 있는 환경 (pdf2kg 그래프, 벡터 인덱스)
실행: part4/graphrag_tool_agent 에서 `python learning/step2_fill_in.py`
막히면 GUIDE.md 생각해 볼 점 1~3 -> tools.py
"""
import re
import sys
from functools import lru_cache
from pathlib import Path

from langchain.agents import create_agent
from langchain.tools import tool
from neo4j import RoutingControl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tools as original  # noqa: E402

MAX_ROWS = 20
WRITE_PATTERN = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|CALL\s+dbms)\b", re.IGNORECASE)


# ---------- 1. 스키마 캐시 ----------
@lru_cache(maxsize=1)
def cached_schema() -> str:
    # TODO 1: 원본의 _get_schema_text(driver) 를 한 번만 부르고 결과를 재사용한다.
    #   lru_cache 가 하는 일을 한 줄로 설명해 보자. 스키마가 바뀌면 어떻게 갱신할까? (cached_schema.cache_clear())
    driver, _, _ = original.initialize_tools()
    ...


@tool(parse_docstring=True)
def generate_cypher(question: str) -> str:
    """자연어 질문을 Cypher 쿼리로 바꿉니다. 스키마는 도구가 알아서 사용하므로 넘기지 않습니다.

    Args:
        question: 사용자의 자연어 질문
    """
    # TODO 2: original.generate_cypher_query 를 invoke 하되 schema_text 에 cached_schema() 를 넘긴다.
    #   원본과 달리 에이전트가 스키마를 인자로 복사할 필요가 없어진다.
    ...


# ---------- 2. 안전한 실행 ----------
@tool(parse_docstring=True)
def execute_cypher_readonly(cypher_query: str) -> str:
    """읽기 전용 Cypher 쿼리를 실행하고 최대 20행을 돌려줍니다. 쓰기 쿼리는 거부합니다.

    Args:
        cypher_query: 실행할 Cypher 쿼리
    """
    driver, _, _ = original.initialize_tools()
    # TODO 3-1: WRITE_PATTERN 에 걸리면 실행하지 말고 "쓰기 쿼리는 실행할 수 없습니다: ..." 를 돌려준다.
    # TODO 3-2: execute_query(..., routing_=RoutingControl.READ) 로 실행한다.
    #   (단일 서버에서는 라우팅만으로 쓰기가 막히지 않을 수 있다. 확실히 하려면 session.execute_read 를 쓰자)
    # TODO 3-3: 결과가 MAX_ROWS 보다 많으면 앞 MAX_ROWS 행만 보여 주고 "총 N행 중 20행" 이라고 알린다.
    # TODO 3-4: 오류는 예외 대신 "오류: ... / 쿼리: ..." 문자열로. 에이전트가 고쳐서 다시 부를 수 있게.
    ...


def build_agent():
    tools = [original.schema_introspection, generate_cypher, execute_cypher_readonly, original.vector_search]
    # TODO 4: 시스템 프롬프트를 쓴다.
    #   - 두 워크플로우(구조화 질의 / 의미 검색)와 고르는 기준
    #   - "실행 결과가 오류면 오류 메시지를 근거로 쿼리를 한 번 고쳐서 다시 실행"
    #   - "결과가 비면 vector_search 로 한 번 더 시도"
    return create_agent(model="gpt-4o", tools=tools, system_prompt="TODO")


def main():
    agent = build_agent()
    for q in ["목차 구조를 보여줘", "OpenAI 관련 내용을 요약해줘", "모든 노드를 삭제해줘"]:
        print("=" * 60, "\nQ:", q)
        for chunk in agent.stream({"messages": [{"role": "user", "content": q}]}, stream_mode="updates"):
            for node, data in chunk.items():
                for m in data.get("messages", []):
                    calls = getattr(m, "tool_calls", None)
                    print(f"[{node}]", calls if calls else str(m.content)[:300])
    # 세 번째 질문에서 쓰기 쿼리가 거부되는지 확인하자.


if __name__ == "__main__":
    main()
