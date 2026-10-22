"""
[2단계: 빈칸 채우기] retrieval_query 를 직접 쓴다. VectorCypher 의 핵심은 "벡터로 찾은 node 에서 어디까지 따라갈까" 이다.

  A. 라이브러리 없이 같은 일을 하는 순수 Cypher (벡터 검색 + 확장을 한 쿼리로)
  B. 행 폭발 없이 조/항/호를 모으는 retrieval_query (CALL {} 서브쿼리)

전제: law2kg 그래프 + question_embedding_index (README 4장)
실행: part3/vectorcypher 에서 `python learning/step2_fill_in.py "피해종교단체의 정의가 뭐야?"`
막히면 GUIDE.md -> vectorcypher.py (97~160줄)
"""
import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
INDEX = "question_embedding_index"


# ---------- A. 벡터 검색 + 확장을 한 쿼리로 ----------
PLAIN_VECTOR_CYPHER = """
// TODO A-1: 벡터 인덱스로 시작 노드를 찾는다.
//   CALL db.index.vector.queryNodes($index, $k, $vec) YIELD node, score
// TODO A-2: node 에서 해석례로 거슬러 올라간다. (node)<-[:HAS_QUESTION]-(interp:LegalInterpretation)
// TODO A-3: 회답, 주 법령을 OPTIONAL MATCH 로.
// TODO A-4: RETURN score, interp.title, node.text, answer.text, primary_law.name
//   VectorCypherRetriever 가 내부에서 해 주는 일이 바로 이것(A-1 + 내 retrieval_query)이다.
"""


# ---------- B. 행 폭발 없는 retrieval_query ----------
RETRIEVAL_QUERY = """
// node(벡터로 찾은 Question)에서 출발한다.
MATCH (node)<-[:HAS_QUESTION]-(interp:LegalInterpretation)
OPTIONAL MATCH (node)-[:ANSWERED_BY]->(answer:Answer)
OPTIONAL MATCH (answer)-[:SUPPORTED_BY]->(reason:Reason)
OPTIONAL MATCH (interp)-[:INTERPRETS]->(primary_law:Law)

// TODO B-1: 인용 조문을 서브쿼리 안에서 따로 모은다. 서브쿼리 밖으로는 리스트 하나만 나간다 -> 행 폭발이 없다.
//   CALL (interp) {
//     OPTIONAL MATCH (interp)-[:CITES]->(a:Article)<-[:HAS_ARTICLE]-(l:Law)
//     RETURN collect(DISTINCT {law: l.name, article: a.number, title: a.title}) AS cited_articles
//   }
//   (Neo4j 버전이 낮아 CALL (interp) 문법이 안 되면: CALL { WITH interp ... })

// TODO B-2: 인용 "항" 도 같은 방식. 단, 법령명은 항 -> 조문 -> 법령으로 직접 올라가서 가져온다.
//   (원본은 조문 쪽 법령명을 재사용한다. GUIDE.md 생각해 볼 점 1)

// TODO B-3: 인용 "호" 도 같은 방식. 호 -> 항 -> 조문 -> 법령.

RETURN interp.title AS interpretation_title,
       interp.case_number AS case_number,
       node.text AS question,
       answer.text AS answer_text,
       reason.text AS reason_text,
       primary_law.name AS primary_law_name
       // TODO B-4: cited_articles, cited_paragraphs, cited_items 를 RETURN 에 추가
"""


def embed(text: str) -> list[float]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return client.embeddings.create(model="text-embedding-3-small", input=[text]).data[0].embedding


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "피해종교단체의 정의가 뭐야?"
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        vec = embed(question)
        if "TODO A-1" not in PLAIN_VECTOR_CYPHER.split("CALL")[0] or "queryNodes" in PLAIN_VECTOR_CYPHER.replace("//", "", 1):
            pass
        # A 를 채웠으면 실행해 본다.
        try:
            for r in driver.execute_query(PLAIN_VECTOR_CYPHER, index=INDEX, k=3, vec=vec, database_=NEO4J_DATABASE).records:
                print("[A]", r.data())
        except Exception as e:
            print("[A] 아직 미완성이거나 오류:", e)

        # B 는 VectorCypherRetriever 에 넣어 확인한다.
        from neo4j_graphrag.embeddings import OpenAIEmbeddings
        from neo4j_graphrag.retrievers import VectorCypherRetriever

        retriever = VectorCypherRetriever(
            driver=driver,
            index_name=INDEX,
            retrieval_query=RETRIEVAL_QUERY,
            embedder=OpenAIEmbeddings(model="text-embedding-3-small"),
        )
        for item in retriever.search(query_text=question, top_k=2).items:
            print("[B]", item.content[:500])
        # TODO B-5: 원본 retrieval_query 와 내 쿼리의 결과 행 수를 PROFILE 로 비교해 보자.
    finally:
        driver.close()


if __name__ == "__main__":
    main()
