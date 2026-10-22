"""
[2단계: 빈칸 채우기] pdf2kg_2.py 의 핵심: 스키마 기반 추출 결과를 안전하게 Neo4j 에 넣기.

전제: pdf2kg.py(Stage 1)를 먼저 실행해서 Neo4j 에 Chunk 노드가 있어야 한다.

방법:
  1. TODO 를 채운다. 막히면 GUIDE.md -> 원본 pdf2kg_2.py.
  2. 스키마 생성과 LLM 추출은 원본 함수를 그대로 쓴다. 여기서는 "저장"과 "방어"에 집중한다.
  3. 실행: part2/pdf2kg 에서 `python learning/step2_domain_fill_in.py`
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pdf2kg_2 import (  # noqa: E402
    Entity,
    Relationship,
    extract_entities_relationships,
    generate_schema,
    get_chunks,
    print_graph_stats,
)

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")


# ---------- 1. LLM 출력 이름 방어 ----------
def sanitize_label(name: str) -> str:
    # TODO 1-1: 노드 레이블용. 영문, 숫자, 언더스코어만 남기고 나머지는 "_" 로 바꾼다.
    #           비었거나 숫자로 시작하면 "Entity_" 를 앞에 붙인다.
    #           (원본은 관계 타입만 sanitize 하고 레이블은 그대로 넣는다. GUIDE.md 생각해 볼 점 1)
    ...


def sanitize_rel_type(name: str) -> str:
    # TODO 1-2: 관계 타입용. 1-1 과 같은 규칙 + 대문자로. 숫자로 시작하면 "REL_".
    ...


def allowed_types_from_schema(schema: str) -> set[str]:
    # TODO 1-3 (심화): 스키마 문자열에서 "**TypeName (한글명)**" 패턴의 TypeName 들을 뽑아 집합으로 돌려준다.
    #   힌트: re.findall(r"\*\*([A-Za-z][A-Za-z0-9_]*)\s*\(", schema)
    #   이걸로 LLM 이 스키마에 없는 타입을 만들어 낼 때 걸러낼 수 있다.
    ...


# ---------- 2. 저장 ----------
def save_entity(driver, entity: Entity, seen: dict[str, str]) -> str | None:
    """엔티티를 MERGE 하고 '타입:이름' -> 레이블 을 seen 에 기록한다."""
    key = f"{entity.entity_type}:{entity.name}"
    if key in seen:
        return seen[key]

    label = sanitize_label(entity.entity_type)
    # TODO 2-1: MERGE (e:`{label}` {name: $name}) 후, 처음 만들 때만 속성을 넣는다. (ON CREATE SET e += $props)
    #   - f-string 안에서 Cypher 중괄호는 {{ }}
    #   - 실패하면 None 을 돌려주고, 성공하면 seen[key] = label 후 label 을 돌려준다.
    ...


def save_relationship(driver, rel: Relationship, seen: dict[str, str]) -> bool:
    src_key = f"{rel.source_type}:{rel.source_name}"
    tgt_key = f"{rel.target_type}:{rel.target_name}"
    # TODO 2-2: 양 끝이 모두 seen 에 있어야 한다. 없으면 False.

    # TODO 2-3: 원본과 달리 MATCH 에 레이블을 넣는다: (s:`{seen[src_key]}` {name: $s}), (t:`{seen[tgt_key]}` {name: $t})
    #           관계는 MERGE (s)-[r:`{rel_type}`]->(t) SET r += $props
    #           왜 레이블을 넣는 게 더 정확하고 빠를까?
    ...


def link_to_chunk(driver, label: str, name: str, chunk_id: str) -> None:
    # TODO 2-4: (c:Chunk {chunk_id})-[:HAS_ENTITY]->(e:`label` {name}) 를 MERGE 한다.
    ...


def main():
    max_chunks = 5  # 비용 절약: 처음엔 작게
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        driver.verify_connectivity()

        schema = generate_schema(driver, client, sample_size=20)
        # TODO 3-1: schema 가 None(생성 실패)이면 여기서 멈춘다. (원본은 그대로 진행한다)

        allowed = allowed_types_from_schema(schema) or set()
        seen: dict[str, str] = {}

        for chunk in get_chunks(driver, max_chunks):
            result = extract_entities_relationships(chunk["content"], chunk["chunk_id"], client, schema)
            for entity in result.entities:
                # TODO 3-2: allowed 가 비어 있지 않고 entity.entity_type 이 allowed 에 없으면 건너뛰고 개수를 센다.
                label = save_entity(driver, entity, seen)
                if label:
                    link_to_chunk(driver, label, entity.name, chunk["chunk_id"])
            for rel in result.relationships:
                save_relationship(driver, rel, seen)

        print_graph_stats(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
