"""
[2단계: 빈칸 채우기] 저장소의 샘플 CSV 로 RAGAS 평가를 다시 돌린다. (Neo4j 없이 OpenAI 키만 필요)
그리고 컨텍스트를 "하나의 문자열"이 아니라 "행별 목록"으로 나눴을 때 점수가 어떻게 바뀌는지 비교한다.

실행: part3/evaluation/ragas 에서 `python learning/step2_fill_in.py`
RAGAS 버전에 따라 import 경로가 다를 수 있다. 노트북 셀 35 와 같은 경로를 쓴다.
막히면 GUIDE.md -> 노트북 셀 34~36
"""
import ast
import asyncio
import csv
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness

load_dotenv()
SAMPLE = Path(__file__).resolve().parent.parent / "graph_rag_results(sample).csv"


def load_samples() -> list[dict]:
    rows = list(csv.DictReader(SAMPLE.open(encoding="utf-8")))
    for r in rows:
        # contexts 열은 파이썬 리스트를 문자열로 저장한 것이다: '["Executed Cypher query: ...\\n..."]'
        r["contexts"] = ast.literal_eval(r["contexts"])
    return rows


# ---------- 1. 컨텍스트 나누기 ----------
def split_context(contexts: list[str]) -> list[str]:
    # TODO 1: contexts[0] 은 "Executed Cypher query: ..." 한 줄 + 결과 행들이 줄바꿈으로 이어진 문자열이다.
    #   - 첫 줄(Cypher)은 따로 하나의 컨텍스트로 두고
    #   - 나머지 줄을 각각 하나의 컨텍스트로 나눈다. (빈 줄 제외)
    #   이렇게 나누면 Context Precision 이 "관련 있는 행이 앞에 있는가"를 볼 수 있게 된다.
    ...


# ---------- 2. 평가 ----------
async def score_one(metrics: dict, row: dict, contexts: list[str]) -> dict:
    out = {"question": row["question"]}
    # TODO 2: 지표별로 필요한 입력만 넘겨 ascore 를 호출하고 .value 를 out 에 넣는다.
    #   faithfulness:      user_input, response, retrieved_contexts
    #   context_recall:    user_input, retrieved_contexts, reference
    #   context_precision: user_input, retrieved_contexts, reference
    #   예외가 나면 그 지표는 None 으로.
    return out


async def run(rows: list[dict], mode: str) -> list[dict]:
    client = AsyncOpenAI()
    llm = llm_factory("gpt-4o-mini", client=client)  # 비용 절약. 원본은 gpt-4o
    metrics = {
        "faithfulness": Faithfulness(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "context_precision": ContextPrecision(llm=llm),
    }
    results = []
    for r in rows:
        ctx = r["contexts"] if mode == "single" else (split_context(r["contexts"]) or r["contexts"])
        results.append(await score_one(metrics, r, ctx))
    return results


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 3) if xs else None


def main():
    rows = load_samples()
    single = asyncio.run(run(rows, "single"))
    split = asyncio.run(run(rows, "split"))
    for name in ("faithfulness", "context_recall", "context_precision"):
        print(f"{name:18}  하나로: {mean([s.get(name) for s in single])}   나눔: {mean([s.get(name) for s in split])}")
    # TODO 3: 같은 설정으로 한 번 더 돌려 점수가 얼마나 흔들리는지 본다. 흔들림보다 작은 차이는 "차이 없음"으로 본다.
    # TODO 4: 질문별 점수를 나란히 출력해서 가장 크게 바뀐 질문을 찾고, contexts 를 직접 읽어 이유를 적는다.


if __name__ == "__main__":
    main()
