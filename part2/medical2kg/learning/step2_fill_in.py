"""
[2단계: 빈칸 채우기] medical2kg 의 핵심: 스키마로 검증하고, 관계를 누적하며 저장하기.

원본 데이터와 LLM 없이 저장소에 커밋된 output/*.json 만으로 실습한다.
실행: part2/medical2kg 에서 `python learning/step2_fill_in.py`
  - TODO 1 만 채워도 검증 결과(버려진 엔티티/관계 수)가 출력된다.
  - Neo4j 정보가 있으면 TODO 2 까지 저장한다. (주의: 엔티티/관계만 넣고 Question 노드는 만들지 않는다)
막히면 GUIDE.md -> 원본 medical2kg.py (246~378, 428~604줄).
"""
import json
import os
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
OUT = Path(__file__).resolve().parent.parent / "output"


# ---------- 1. 스키마로 검증 ----------
def build_allowed(schema: dict) -> tuple[set[str], set[tuple[str, str, str]]]:
    # TODO 1-1: 허용 엔티티 타입 집합(소문자)과 허용 관계 조합 집합 {(from 소문자, to 소문자, TYPE)} 을 만든다.
    ...


def validate(results: dict, schema: dict) -> dict:
    allowed_types, allowed_rels = build_allowed(schema)
    dropped_entities = dropped_rels = 0
    clean = {}
    for qa_id, r in results.items():
        # TODO 1-2: 원본과 달리 엔티티 타입도 검사한다. allowed_types 에 없는 타입의 엔티티는 버린다.
        # TODO 1-3: 관계는 (from_type, to_type, type) 이 allowed_rels 에 있고,
        #           양 끝 이름이 이 QA 에서 살아남은 엔티티에 있어야 한다.
        # TODO 1-4: 버린 개수를 dropped_entities, dropped_rels 에 더한다.
        clean[qa_id] = {"entities": [], "relationships": []}
    print(f"버린 엔티티 {dropped_entities}개, 버린 관계 {dropped_rels}개")
    return clean


def label_of(entity_type: str, schema: dict) -> str:
    # TODO 1-5: capitalize() 대신, 스키마 키 중 소문자가 같은 것을 찾아 원래 표기 그대로 돌려준다.
    #           ("bodypart" -> 스키마의 "BodyPart"). 못 찾으면 capitalize().
    ...


# ---------- 2. 저장 ----------
def save(driver, results: dict, schema: dict) -> None:
    # 엔티티: 타입별로 묶어 MERGE
    by_label: dict[str, set[str]] = defaultdict(set)
    for r in results.values():
        for e in r["entities"]:
            by_label[label_of(e["type"], schema)].add(e["name"])

    for label, names in by_label.items():
        # TODO 2-1: 이 레이블의 name 인덱스를 먼저 만든다. (CREATE INDEX ... IF NOT EXISTS FOR (e:`label`) ON (e.name))
        # TODO 2-2: UNWIND $names AS name MERGE (e:`label` {name: name})
        ...

    # 관계: (관계 타입, 출발 레이블, 도착 레이블) 별로 묶어 배치
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for qa_id, r in results.items():
        for rel in r["relationships"]:
            key = (rel["type"], label_of(rel["from_type"], schema), label_of(rel["to_type"], schema))
            groups[key].append({"from": rel["from"], "to": rel["to"], "qa_id": int(qa_id), "evidence": rel.get("evidence", "")})

    for (rel_type, from_label, to_label), rows in groups.items():
        # TODO 2-3: 양 끝을 MATCH 하고 관계를 MERGE 한다.
        #   ON CREATE SET r.count = 1, r.qa_ids = [row.qa_id], r.evidence = [row.evidence]
        #   ON MATCH  SET: 이미 qa_ids 에 있는 qa_id 면 아무것도 바꾸지 않고,
        #                  아니면 count + 1, qa_ids 에 추가, evidence 에도 추가
        #   (원본은 같은 QA 를 두 번 넣으면 count 가 두 번 오른다. GUIDE.md 생각해 볼 점 6)
        #   힌트: SET r.count = CASE WHEN row.qa_id IN r.qa_ids THEN r.count ELSE r.count + 1 END
        ...


def main():
    schema = json.loads((OUT / "domain_schemas.json").read_text(encoding="utf-8"))
    raw = json.loads((OUT / "extracted_graph.json").read_text(encoding="utf-8"))
    results = validate(raw, schema)

    uri, user, pw = os.getenv("NEO4J_URI"), os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")
    if uri and user and pw:
        driver = GraphDatabase.driver(uri, auth=(user, pw))
        try:
            save(driver, results, schema)
            save(driver, results, schema)  # 일부러 두 번: count 가 그대로여야 정답
            for rec in driver.execute_query(
                "MATCH (s:Symptom)-[r:INDICATES]->(d:Disease) RETURN s.name AS s, d.name AS d, r.count AS n "
                "ORDER BY n DESC LIMIT 5",
                database_=NEO4J_DATABASE,
            ).records:
                print(rec.data())
        finally:
            driver.close()


if __name__ == "__main__":
    main()
