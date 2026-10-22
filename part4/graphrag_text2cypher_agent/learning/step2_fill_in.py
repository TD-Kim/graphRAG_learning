"""
[2단계: 빈칸 채우기] 같은 LangGraph 워크플로우를 "고친 버전"으로 다시 조립한다.
원본 노드(생성, 실행, 답변)는 그대로 쓰고, 검증/수정/라우팅을 내가 쓴다.

고칠 것 (GUIDE.md 생각해 볼 점 1~4):
  - 검증 실패 시 수정 노드가 validation_error 를 보게
  - 키워드 검사를 단어 경계로
  - OPTIONAL MATCH / WITH / CALL 로 시작하는 쿼리 허용
  - 빈 결과 재생성 때 이전 쿼리를 알려 주기

실행: part4/graphrag_text2cypher_agent 에서 `python learning/step2_fill_in.py "기침 증상과 관련된 질병은?"`
"""
import re
import sys
from pathlib import Path
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nodes  # noqa: E402  원본 노드와 llm, schema_str 재사용
from prompts import CORRECT_CYPHER_PROMPTS, FEWSHOT_EXAMPLES_STR, GENERATE_CYPHER_PROMPTS  # noqa: E402
from state import InputState, OutputState, State  # noqa: E402

MAX_RETRY = 3
MAX_REGENERATE = 2
WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b", re.IGNORECASE)
READ_START = re.compile(r"^\s*(OPTIONAL\s+MATCH|MATCH|WITH|CALL|UNWIND)\b", re.IGNORECASE)


# ---------- 1. 검증 ----------
def validate_query_node(state: State):
    cypher = (state.get("cypher") or "").strip().strip("`")
    # TODO 1: 아래 순서로 검사하고, 실패하면 {"validation_error": "...", "cypher": cypher} 를 돌려준다.
    #   - 비어 있음
    #   - WRITE 패턴 (단어 경계라서 OFFSET, created_at 은 통과)
    #   - READ_START 로 시작하지 않음
    #   - RETURN 이 단어로 없음
    #   통과하면 {"validation_error": "", "cypher": cypher}
    ...


# ---------- 2. 수정 ----------
def correct_cypher_node(state: State):
    # TODO 2-1: 오류 원인을 고른다. validation_error 가 있으면 그것, 없으면 db_outputs[-1](실행 오류 문자열).
    #   (원본은 항상 db_outputs[-1] 을 써서 첫 검증 실패 때 오류가 난다)
    # TODO 2-2: CORRECT_CYPHER_PROMPTS 로 llm 을 호출해 고친 쿼리를 받는다. (nodes.llm, nodes.schema_str 사용)
    # TODO 2-3: {"cypher": 고친 쿼리, "retry_count": +1, "validation_error": ""} 를 돌려준다.
    ...


# ---------- 3. 재생성 ----------
def generate_cypher_node(state: State):
    note = ""
    if state.get("result_empty"):
        # TODO 3: 이전 쿼리가 빈 결과였다는 사실과 그 쿼리를 질문 뒤에 덧붙인다.
        #   예) "\n(참고: 이전 쿼리 `...` 는 결과가 비었습니다. 조건을 넓히거나 CONTAINS 를 쓰세요)"
        note = ""
    prompt = ChatPromptTemplate.from_messages(GENERATE_CYPHER_PROMPTS)
    resp = nodes.llm.invoke(prompt.format_messages(
        question=state["query"] + note, schema=nodes.schema_str, fewshot_examples=FEWSHOT_EXAMPLES_STR))
    return {
        "cypher": resp.content,
        "result_empty": False,
        "regenerate_count": state.get("regenerate_count", 0) + (1 if state.get("result_empty") else 0),
    }


# ---------- 4. 라우팅 ----------
def route_validation(state: State) -> Literal["execute_cypher", "correct_cypher", "answer"]:
    # TODO 4-1: retry_count >= MAX_RETRY 면 "answer", 검증 통과면 "execute_cypher", 아니면 "correct_cypher"
    #   주의: 검증만 계속 실패해서 answer 로 가면 db_outputs 가 없어서 원본 answer_node 가 오류를 낸다.
    #         그럴 때를 위해 아래 answer_guard 노드를 거치게 했다.
    ...


def route_execution(state: State) -> Literal["generate_cypher", "correct_cypher", "answer"]:
    # TODO 4-2: 결과가 list 이고 비어 있지 않으면 "answer"
    #           빈 list 이고 regenerate_count < MAX_REGENERATE 면 "generate_cypher", 아니면 "answer"
    #           문자열(오류)이면 retry_count < MAX_RETRY 일 때 "correct_cypher", 아니면 "answer"
    ...


def answer_guard(state: State):
    """검증만 실패하다 끝난 경우에도 답변 노드가 동작하도록 db_outputs 를 채워 준다."""
    if not state.get("db_outputs"):
        return {"db_outputs": [f"쿼리 검증 실패: {state.get('validation_error', '알 수 없음')}"]}
    return {}


def build_graph():
    g = StateGraph(State, input_schema=InputState, output_schema=OutputState)
    g.add_node("guardrail", nodes.guardrail_node)
    g.add_node("generate_cypher", generate_cypher_node)
    g.add_node("validate_query", validate_query_node)
    g.add_node("execute_cypher", nodes.execute_cypher_node)
    g.add_node("correct_cypher", correct_cypher_node)
    g.add_node("answer_guard", answer_guard)
    g.add_node("answer", nodes.answer_node)

    # TODO 5: 엣지를 연결한다. main.py 를 참고하되, answer 로 가는 모든 경로가 answer_guard 를 거치게.
    #   START -> guardrail
    #   guardrail -(nodes.route_guardrail)-> generate_cypher | answer_guard
    #   generate_cypher -> validate_query, correct_cypher -> validate_query
    #   validate_query -(route_validation)-> execute_cypher | correct_cypher | answer_guard
    #   execute_cypher -(route_execution)-> generate_cypher | correct_cypher | answer_guard
    #   answer_guard -> answer -> END
    #   힌트: add_conditional_edges(노드, 라우팅함수, {"반환값": "노드이름", ...})
    return g.compile()


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "기침 증상과 관련된 질병은?"
    graph = build_graph()
    print(graph.invoke({"query": question})["answer"])
    # 일부러 실패를 유도해 보자:
    #   "모든 질병 노드를 지워줘"            -> 검증 실패 -> 수정 -> ... -> 안전하게 종료되는가?
    #   "존재하지 않는증상XYZ 관련 질병은?"   -> 빈 결과 -> 재생성 2회 -> 답변
