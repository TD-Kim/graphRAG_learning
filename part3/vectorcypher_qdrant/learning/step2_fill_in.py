"""
[2단계: 빈칸 채우기] QdrantNeo4jRetriever 가 내부에서 하는 일을 손으로 구현한다.

  1. 배치 임베딩 + 결정적 ID 로 Qdrant 적재 (다시 돌려도 중복 없음)
  2. Qdrant 검색 -> payload.element_id 목록
  3. Neo4j 에서 그 element_id 들을 시작점으로 확장 (확장 개수 상한 포함)

전제: pdf2kg(+pdf2kg_2) 그래프, Qdrant 접속 정보
실행: part3/vectorcypher_qdrant 에서 `python learning/step2_fill_in.py "업스테이지 모델의 특징은?"`
막히면 GUIDE.md -> ingest_to_qdrant.py -> graphrag_qdrant.py (177~274줄)
"""
import os
import sys
import uuid

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
COLLECTION = "pdf2kg_step2"           # 원본 컬렉션과 겹치지 않게
NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")
MODEL = "text-embedding-3-small"


# ---------- 1. 적재 ----------
def point_id(element_id: str) -> str:
    # TODO 1-1: uuid.uuid5(NAMESPACE, element_id) 를 문자열로. 같은 element_id 면 항상 같은 ID 가 나온다.
    ...


def ingest(driver, qdrant: QdrantClient, oai: OpenAI, batch: int = 64) -> int:
    if not qdrant.collection_exists(COLLECTION):
        qdrant.create_collection(COLLECTION, vectors_config=VectorParams(size=1536, distance=Distance.COSINE))

    rows = [r.data() for r in driver.execute_query(
        "MATCH (t:TextElement) WHERE t.content IS NOT NULL "
        "RETURN t.element_id AS element_id, t.content AS content, t.page AS page",
        database_=NEO4J_DATABASE,
    ).records]

    for i in range(0, len(rows), batch):
        part = rows[i:i + batch]
        # TODO 1-2: part 의 content 들을 한 번의 embeddings.create 호출로 임베딩한다. (원본은 한 문장씩)
        # TODO 1-3: PointStruct(id=point_id(...), vector=..., payload={element_id, page}) 리스트를 만들어 upsert.
        #   payload 에 content 를 넣을지 말지 정하자. 넣으면 편하지만 Neo4j 와 이중 저장이다.
    return len(rows)


# ---------- 2. 검색 ----------
def search_ids(qdrant: QdrantClient, oai: OpenAI, question: str, k: int = 5) -> list[tuple[str, float]]:
    # TODO 2: 질문을 임베딩해 qdrant.query_points(COLLECTION, query=vec, limit=k) 로 검색하고
    #         [(payload["element_id"], score), ...] 를 돌려준다.
    #   (qdrant-client 버전에 따라 query_points / search 중 하나다. 설치된 버전 문서를 확인)
    ...


# ---------- 3. Neo4j 확장 ----------
EXPAND = """
UNWIND $hits AS hit
MATCH (node:TextElement {element_id: hit.id})
MATCH (chunk:Chunk)-[:HAS_ELEMENT]->(node)
OPTIONAL MATCH (toc:TOC)-[:HAS_CHUNK]->(chunk)

// TODO 3-1: 부모 목차 제목들을 위에서부터 순서대로 모은다. (HAS_CHILD* 가변 경로, level 로 정렬)
//   CALL (toc) { OPTIONAL MATCH (p:TOC)-[:HAS_CHILD*]->(toc) WITH p ORDER BY p.level RETURN collect(p.title) AS path }

// TODO 3-2: 엔티티 기반 확장을 "엔티티 3개, 확장 문장 5개"까지만 가져온다.
//   CALL (chunk) {
//     OPTIONAL MATCH (chunk)-[:HAS_ENTITY]->(e)
//     WITH e LIMIT 3
//     OPTIONAL MATCH (other:Chunk)-[:HAS_ENTITY]->(e) WHERE other <> chunk
//     OPTIONAL MATCH (other)-[:HAS_ELEMENT]->(x:TextElement)
//     WITH e, x LIMIT 5
//     RETURN collect(DISTINCT e.name) AS entities, collect(DISTINCT x.content) AS expanded
//   }

RETURN hit.score AS score, node.content AS content, node.page AS page, toc.title AS section
       // TODO 3-3: path, entities, expanded 를 추가
ORDER BY score DESC
"""


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "업스테이지 모델의 특징은?"
    oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    qdrant = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_KEY"))
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        print("적재:", ingest(driver, qdrant, oai))
        print("적재 (두 번째, 개수가 그대로여야 함):", ingest(driver, qdrant, oai))
        print("Qdrant 포인트 수:", qdrant.count(COLLECTION).count)

        hits = [{"id": eid, "score": s} for eid, s in (search_ids(qdrant, oai, question) or [])]
        for r in driver.execute_query(EXPAND, hits=hits, database_=NEO4J_DATABASE).records:
            print(r.data())
    finally:
        driver.close()


if __name__ == "__main__":
    main()
