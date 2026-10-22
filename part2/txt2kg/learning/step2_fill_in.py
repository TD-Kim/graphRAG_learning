"""
[2단계: 빈칸 채우기] txt2kg 의 핵심 3가지: LLM 추출 호출, 결과 병합, 동적 레이블로 저장.

방법:
  1. TODO 를 위에서부터 채운다. 막히면 GUIDE.md -> 원본 txt2kg.py.
  2. 시스템 프롬프트는 길어서 원본에서 가져온다(SYSTEM_PROMPT 는 직접 쓰지 않음). 대신 TODO 3 에서 규칙을 하나 직접 추가해 본다.
  3. 실행: part2/txt2kg 에서 `python learning/step2_fill_in.py`
     -> knowledge_graph_step2.json 이 만들어지고 엔티티/관계 수가 출력되면 성공.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # 원본 모듈(txt2kg.py)을 import 하기 위해

from txt2kg import split_text_into_chunks  # noqa: E402  청킹은 원본 것을 그대로 쓴다

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")

# 원본의 시스템 프롬프트를 짧게 줄인 버전. TODO 3 에서 규칙을 하나 더 넣어 본다.
SYSTEM_PROMPT = """
당신은 텍스트에서 지식 그래프를 추출하는 전문가입니다. 반드시 JSON 형식으로 응답하세요.
- 엔티티: name, type, properties(선택)
- 관계: source, target, type(영어 대문자와 언더스코어), properties(선택), evidence(원문 문장)
- 피동형 "A는 B에 의해 ~된다" -> (B)-[동사]->(A)
- 능동형 "A는 B를 ~한다" -> (A)-[동사]->(B)
출력: {"entities": [...], "relations": [...]}
""".strip()
# TODO 3: 위 규칙에 "열거형 'A, B, C' 는 각각 별도 엔티티" 규칙을 추가하고, 추가 전후 결과를 비교해 보자.


# ---------- 1. 청크 하나 추출 ----------
def extract_from_chunk(client: OpenAI, chunk: str, model: str = "gpt-4o") -> dict:
    # TODO 1-1: client.chat.completions.create 로 호출한다.
    #   - messages: system = SYSTEM_PROMPT, user = "<text>{chunk}</text> 위 텍스트에서 지식 그래프를 추출하세요."
    #   - JSON 응답을 강제하는 옵션: response_format={"type": ...}
    #   - 결과가 매번 같도록 temperature 는?
    # TODO 1-2: 응답 문자열을 json.loads 로 dict 로 바꿔 돌려준다.
    # TODO 1-3: 예외가 나면 {"entities": [], "relations": []} 를 돌려준다. 왜 멈추지 않고 빈 결과를 줄까?
    ...


# ---------- 2. 여러 청크 결과 병합 ----------
def merge_results(results: list[dict]) -> dict:
    # TODO 2-1: 엔티티를 name 기준으로 합친다. 같은 이름이 또 나오면 properties 를 {**기존, **새것} 으로 합친다.
    #           name 이 없는 엔티티는 버린다.
    unique_entities: dict[str, dict] = {}

    # TODO 2-2: 관계를 (source, target, type) 기준으로 중복 제거한다. 셋 중 하나라도 비어 있으면 버린다.
    unique_relations: list[dict] = []

    # TODO 2-3: 엔티티 목록에 없는 이름을 source/target 으로 쓰는 관계를 버리고, 버린 개수를 출력한다.

    return {"entities": list(unique_entities.values()), "relations": unique_relations}


# ---------- 3. Neo4j 저장 ----------
def save(kg: dict, driver) -> None:
    def create_nodes(tx, entities):
        for e in entities:
            label = e.get("type", "Entity").replace("`", "").strip()
            # TODO 3-1: 레이블은 파라미터로 못 넘긴다. f-string + 백틱으로 레이블을 넣고,
            #           MERGE 는 name 으로만 하고, 나머지 속성은 SET n += $props 로 넣는다.
            #           (원본과 다른 방식이다. GUIDE.md "생각해 볼 점" 1번 참고)
            #   주의: f-string 안에서 Cypher 의 { } 는 {{ }} 로 써야 한다.
            ...

    def create_relations(tx, relations):
        for r in relations:
            rel_type = r["type"].replace("`", "").strip()
            props = {**r.get("properties", {}), "evidence": r.get("evidence", "")}
            # TODO 3-2: 양 끝 노드를 name 으로 MATCH 하고 관계를 CREATE 한다. 관계 속성은 SET r += $props 로.
            ...

    driver.execute_query("MATCH (n) DETACH DELETE n", database_=NEO4J_DATABASE)
    with driver.session(database=NEO4J_DATABASE) as session:
        # TODO 3-3: execute_write 로 create_nodes, create_relations 를 차례로 실행한다.
        ...


def main():
    text = (HERE.parent / "wiki_protein.txt").read_text(encoding="utf-8")
    chunks = split_text_into_chunks(text, chunk_size=500, chunk_overlap=100)

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # 비용을 아끼려면 처음엔 chunks[:3] 정도로만 돌려 보자.
    results = [extract_from_chunk(client, c) for c in chunks[:3]]
    kg = merge_results(results)
    print(f"엔티티 {len(kg['entities'])}개, 관계 {len(kg['relations'])}개")

    (HERE / "knowledge_graph_step2.json").write_text(json.dumps(kg, ensure_ascii=False, indent=2), encoding="utf-8")

    uri, user, pw = os.getenv("NEO4J_URI"), os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")
    if uri and user and pw:
        driver = GraphDatabase.driver(uri, auth=(user, pw))
        try:
            save(kg, driver)
        finally:
            driver.close()


if __name__ == "__main__":
    main()
