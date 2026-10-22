"""
[2단계: 빈칸 채우기] 벡터 검색의 3단계(임베딩 저장 -> 인덱스 -> 검색)를 Python 드라이버 + OpenAI SDK 로 직접 구현한다.
노트북은 DB 안(GenAI 플러그인)에서 임베딩을 만들었다. 여기서는 플러그인 없이 Python 에서 만들어 넣는다.

전제: pdf2kg.py 로 TextElement 노드가 있다.
실행: part3/vectorsearch 에서 `python learning/step2_fill_in.py "AI 규제 동향"`
막히면 GUIDE.md -> vector_index.ipynb(셀 16, 19, 25) -> vectorsearch.py
"""
import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
MODEL = "text-embedding-3-small"
DIM = 1536
INDEX = "textElementEmbeddingPy"   # 노트북 인덱스와 겹치지 않게 다른 이름
PROP = "embedding_py"              # 노트북 속성과 겹치지 않게 다른 속성


def embed(client: OpenAI, texts: list[str]) -> list[list[float]]:
    # TODO 1: client.embeddings.create(model=MODEL, input=texts) 로 여러 문장을 한 번에 임베딩하고
    #         결과의 .data 에서 각 .embedding 을 순서대로 리스트로 돌려준다.
    ...


def fill_embeddings(driver, client: OpenAI, batch_size: int = 100) -> int:
    total = 0
    while True:
        # TODO 2-1: 아직 PROP 이 없는 TextElement 를 batch_size 개 가져온다. (element_id, content)
        #           f-string 으로 PROP 을 넣을 때 중괄호 주의.
        rows = []
        if not rows:
            break
        # TODO 2-2: content 들을 embed() 로 한 번에 임베딩한다.
        # TODO 2-3: UNWIND $rows AS row MATCH (t:TextElement {element_id: row.id}) SET t.<PROP> = row.vec
        #   왜 노드마다 쿼리를 보내지 않고 UNWIND 로 한 번에 보낼까?
        total += len(rows)
        print(f"누적 {total}")
    return total


def create_index(driver) -> None:
    # TODO 3: CREATE VECTOR INDEX {INDEX} IF NOT EXISTS FOR (t:TextElement) ON t.{PROP}
    #         OPTIONS {indexConfig: {`vector.dimensions`: $dim, `vector.similarity_function`: 'cosine'}}
    #   f-string 이면 OPTIONS 의 중괄호는 {{ }} 로.
    ...


def search(driver, client: OpenAI, question: str, k: int = 5) -> list[dict]:
    # TODO 4-1: 질문을 embed() 로 벡터화한다. 문서와 "같은 모델"이어야 하는 이유는?
    # TODO 4-2: CALL db.index.vector.queryNodes($index, $k, $vec) YIELD node, score
    #           RETURN node.element_id, node.page, node.content, score
    ...


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "AI 규제 동향"
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        fill_embeddings(driver, client)
        create_index(driver)
        # TODO 5: 인덱스가 ONLINE 이 될 때까지 기다린다. (SHOW INDEXES YIELD name, state WHERE name = $index)
        for r in search(driver, client, question) or []:
            print(f"{r['score']:.4f}  p.{r['page']}  {r['content'][:80]}")
        # TODO 6: score 가 몇 이하면 "관련 결과 없음"으로 볼지 정하고, 관련 없는 질문으로 확인해 보자.
    finally:
        driver.close()


if __name__ == "__main__":
    main()
