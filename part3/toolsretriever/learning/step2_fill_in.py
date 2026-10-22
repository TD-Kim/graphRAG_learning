"""
[2단계: 빈칸 채우기] 도구 선택(라우팅)을 직접 구현해 본다. ToolsRetriever 가 대신 해 주던 일이다.

  1. 도구 4개의 이름/설명을 내가 쓴다.
  2. LLM 에게 "질문 + 도구 목록"을 주고 도구 이름 하나를 JSON 으로 고르게 한다.
  3. 질문 12개로 라우팅 정확도를 잰다. (Neo4j 없이 LLM 만으로 실습 가능)

실행: part3/toolsretriever 에서 `python learning/step2_fill_in.py`
막히면 GUIDE.md -> vector_retriever.py, vectorcypher_retriever.py, text2cypher_retriever.py 의 description
"""
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ---------- 1. 도구 설명 ----------
TOOLS = {
    "text_vector_search": "TODO 1-1: 언제 쓰는지, 예시 질문 2개",
    "table_vector_search": "TODO 1-2",
    "vectorcypher_context_search": "TODO 1-3",
    "text2cypher_structured_query": "TODO 1-4",
}
# 원본 설명을 보기 전에 먼저 써 보고, 정확도를 잰 뒤 원본과 비교하자.
# 설명끼리 겹치는 표현이 있으면 LLM 이 헷갈린다. 각 도구만의 "구별되는 단서"를 넣자.


# ---------- 2. 라우터 ----------
def route(client: OpenAI, question: str) -> str:
    tool_list = "\n".join(f"- {name}: {desc}" for name, desc in TOOLS.items())
    # TODO 2-1: 시스템 프롬프트: "질문에 가장 알맞은 도구 하나를 고른다. {"tool": "<이름>"} JSON 만 출력"
    # TODO 2-2: chat.completions.create(..., response_format={"type": "json_object"}, temperature=0)
    # TODO 2-3: 결과의 tool 이 TOOLS 에 없는 이름이면 기본값(vectorcypher_context_search)으로.
    #   왜 기본값이 필요할까?
    ...


# ---------- 3. 평가 ----------
# (질문, 기대 도구). 내 문서(aibrief.pdf)에 맞게 질문을 바꿔도 된다.
CASES = [
    ("AI 반도체 동향을 요약해줘", "text_vector_search"),
    ("주요 국가별 AI 투자 규모를 비교한 표가 있어?", "table_vector_search"),
    ("업스테이지에 대해 알려진 내용을 모두 모아줘", "vectorcypher_context_search"),
    ("목차 구조를 보여줘", "text2cypher_structured_query"),
    ("6페이지에 있는 내용은?", "text2cypher_structured_query"),
    ("문서에 등장하는 회사는 몇 개야?", "text2cypher_structured_query"),
    ("EXAONE 모델의 특징은?", "vectorcypher_context_search"),
    ("벤치마크 점수 비교 결과", "table_vector_search"),
    ("생성형 AI 규제에 대한 설명을 찾아줘", "text_vector_search"),
    ("LG AI연구원 소속 인물은?", "text2cypher_structured_query"),
    ("OpenAI 관련 정보를 다 찾아줘", "vectorcypher_context_search"),
    ("AI 기본법 시행 일정 목록", "table_vector_search"),
]


def main():
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    correct = 0
    for q, expected in CASES:
        got = route(client, q)
        ok = got == expected
        correct += ok
        print(f"{'O' if ok else 'X'}  {q}  -> {got} (기대: {expected})")
    print(f"\n정확도 {correct}/{len(CASES)}")
    # TODO 3: 틀린 질문을 보고 설명을 고친 뒤 다시 돌린다. 몇 번 만에 몇 점까지 올라가는지 기록하자.
    #   기대값 자체가 애매한 질문은 없었나? (두 도구 모두 정답일 수 있는 질문)
    print(json.dumps(TOOLS, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
