"""
[2단계: 빈칸 채우기] 원본 eval.py 에 없는 "실행 정확도(execution accuracy)"를 추가한다.
생성 쿼리와 정답 쿼리를 둘 다 실행해서 결과 집합이 같은지 본다.

실행: part3/evaluation/neo4j_text2cypher 에서 `python learning/step2_fill_in.py --limit 10`
막히면 GUIDE.md 생각해 볼 점 1 -> eval.py
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from eval import load_golden_dataset, load_schema  # noqa: E402
from retriever import build_retriever, create_driver, create_llm, execute_cypher, generate_and_execute_cypher  # noqa: E402


# ---------- 1. 결과 정규화 ----------
def normalize_value(v):
    # TODO 1-1: 비교 전에 값을 정규화한다.
    #   - float 는 소수 4자리로 반올림 (1.0 과 1.00001 을 같게)
    #   - list 는 각 원소를 정규화한 tuple 로 (dict 키로 쓸 수 있게)
    #   - 나머지(문자열, 정수, None)는 그대로
    ...


def normalize_rows(rows: list[dict]) -> Counter:
    # TODO 1-2: 컬럼 "이름"은 버리고 "값"만 비교한다. (정답은 AS title, 생성은 AS movieTitle 일 수 있으므로)
    #   각 행을 정렬된 값들의 tuple 로 바꾸고, Counter 로 센다. (행 순서는 무시, 중복 행 수는 유지)
    #   생각해 보기: ORDER BY 가 질문의 핵심("상위 5개")이면 순서를 무시해도 될까?
    ...


# ---------- 2. 비교 ----------
def execution_match(golden_rows: list[dict], generated_rows: list[dict]) -> str:
    # TODO 2: 세 가지 중 하나를 돌려준다.
    #   "exact"   : 두 Counter 가 같다
    #   "subset"  : 정답 결과가 생성 결과에 모두 포함된다 (생성 쪽이 컬럼/행을 더 많이 반환)
    #   "mismatch": 나머지
    #   subset 을 정답으로 쳐줄지는 내가 정하는 정책이다. 이유를 주석으로 남기자.
    ...


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--db", default=os.getenv("DATABASE_NAME", "recommendations"))
    args = p.parse_args()

    golden = load_golden_dataset(str(HERE.parent / "text2cypher_gpt4o.csv"), args.db)[: args.limit]
    schema = load_schema(str(HERE.parent / "text2cypher_schemas.csv"), args.db)
    driver, llm = create_driver(), create_llm()
    retriever = build_retriever(driver, llm, neo4j_schema=schema)

    tally = Counter()
    by_type: dict[str, Counter] = {}
    try:
        for g in golden:
            gen_cypher, gen_rows, err = generate_and_execute_cypher(retriever, g["question"])
            gold_rows, gold_err = execute_cypher(driver, g["cypher"])
            # TODO 3-1: 정답 쿼리 자체가 실패하면(gold_err) 이 질문은 평가에서 뺀다. 왜?
            # TODO 3-2: 생성 쿼리가 실패하면 "error", 아니면 execution_match 결과를 쓴다.
            verdict = "TODO"
            tally[verdict] += 1
            by_type.setdefault(g["type"], Counter())[verdict] += 1
            print(f"[{verdict:8}] {g['question']}")
    finally:
        driver.close()

    print("\n전체:", dict(tally))
    for t, c in by_type.items():
        print(f"  {t}: {dict(c)}")
    # TODO 4: 원본 eval.py 의 LLM Judge 점수와 내 실행 정확도가 어긋나는 질문(Judge 는 5점인데 mismatch 등)을 찾아보자.
    #   어느 지표가 맞았나? 직접 판정해 보고 이유를 적는다.


if __name__ == "__main__":
    main()
