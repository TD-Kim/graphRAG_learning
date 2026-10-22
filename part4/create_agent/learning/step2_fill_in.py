"""
[2단계: 빈칸 채우기] 도구 3개짜리 에이전트를 스크립트로 만든다. (노트북 내용을 .py 로 옮기며 빈칸 채우기)
DB 없이 OPENAI_API_KEY 만 있으면 된다.

실행: part4/create_agent 에서 `python learning/step2_fill_in.py`
막히면 GUIDE.md -> langchain_create_agent.ipynb (셀 4, 9, 12, 14)
"""
from datetime import date

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool

load_dotenv()


# ---------- 1. 도구 ----------
@tool(parse_docstring=True)
def international_age(birth_date: str) -> str:
    """TODO 1-1: 이 docstring 을 채운다. LLM 이 읽는 설명서다.

    무엇을 계산하는지(만 나이), 언제 쓰는지, 입력 형식(YYYY-MM-DD)을 분명히 쓴다.

    Args:
        birth_date: TODO 1-2 입력 형식과 예시
    """
    # TODO 1-3: birth_date 를 date.fromisoformat 으로 바꿔 오늘 기준 만 나이를 계산한다.
    #           형식이 틀리면 예외 대신 "형식 오류: YYYY-MM-DD 로 입력" 문자열을 돌려준다. 왜 예외가 아니라 문자열일까?
    ...


@tool(parse_docstring=True)
def days_until(target_date: str) -> str:
    """TODO 2-1: 오늘부터 target_date 까지 남은 날 수를 계산한다는 설명.

    Args:
        target_date: TODO 2-2
    """
    # TODO 2-3: 남은 날 수(음수면 "지났다")를 문장으로 돌려준다.
    ...


@tool(parse_docstring=True)
def safe_divide(a: float, b: float) -> str:
    """두 수를 나눈다.

    Args:
        a: 나뉘는 수
        b: 나누는 수
    """
    # TODO 3: b 가 0 이면 에이전트가 이해할 수 있는 안내 문장을 돌려준다.
    ...


# ---------- 2. 에이전트 ----------
def build_agent():
    # TODO 4: create_agent(model=..., tools=[...], system_prompt=...) 로 만든다.
    #   시스템 프롬프트에 "날짜 계산은 반드시 도구를 쓸 것", "도구 결과를 그대로 인용할 것" 같은 규칙을 넣어 보자.
    ...


def show(agent, question: str) -> None:
    print("=" * 60)
    print("Q:", question)
    # TODO 5: agent.stream({"messages": [{"role": "user", "content": question}]}, stream_mode="updates") 로
    #         노드 이름과 메시지를 차례로 출력한다. 어떤 도구가 어떤 인자로 불렸는지 보이게.
    ...


if __name__ == "__main__":
    agent = build_agent()
    for q in [
        "1995-03-14 에 태어난 사람의 만 나이는?",
        "2026-12-25 까지 며칠 남았어? 그리고 그 날수를 7로 나누면 몇 주야?",
        "10을 0으로 나눠줘",
        "오늘 기분 어때?",   # 도구가 필요 없는 질문. 도구를 부르지 않는지 확인
    ]:
        show(agent, q)
