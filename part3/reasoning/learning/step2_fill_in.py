"""
[2단계: 빈칸 채우기] 추론 패턴 쿼리를 직접 쓰고, 커스텀 Retriever 를 직접 만든다.

  A. 추론 패턴 Cypher 3개 (LLM 없이, Neo4j Browser 로도 확인 가능)
  B. Text2CypherRetriever 를 상속해 "실행된 Cypher + 결과"를 하나의 컨텍스트로 만드는 Retriever

전제: part2/medical2kg 로 의료 그래프가 적재되어 있다.
실행: part3/reasoning 에서 `python learning/step2_fill_in.py`
막히면 GUIDE.md -> graphrag_reasoning.py (374~468줄 예시, 16~60줄 Retriever)
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j_graphrag.retrievers import Text2CypherRetriever
from neo4j_graphrag.types import RetrieverResult, RetrieverResultItem

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")


# ---------- A. 추론 패턴 ----------
# 각 쿼리는 $keyword 파라미터를 받는다. 실제 그래프의 관계/속성 이름을 먼저 확인하자:
#   MATCH ()-[r]->() RETURN DISTINCT type(r), keys(r) LIMIT 20

SYMPTOM_TO_EVERYTHING = """
// TODO A-1: 증상 하나 -> 질병 -> (같은 질병의 다른 증상, 치료법, 약물)
//   - 시작: (s:Symptom)-[i:INDICATES]->(d:Disease) WHERE s.name CONTAINS $keyword
//   - 확장: OPTIONAL MATCH 3개
//   - 집계: collect(DISTINCT ...) 3개
//   - 정렬: medical2kg 가 쌓은 i.count 가 큰 질병부터 (없으면 0 으로: coalesce)
//   - LIMIT 10
"""

TWO_SYMPTOMS_INTERSECTION = """
// TODO A-2: 증상 두 개($k1, $k2)가 공통으로 가리키는 질병
//   (s1:Symptom)-[:INDICATES]->(d:Disease)<-[:INDICATES]-(s2:Symptom)
//   s1 과 s2 가 같은 노드가 되지 않도록 조건을 넣자.
"""

DISEASE_PROFILE = """
// TODO A-3: 질병 이름($keyword) -> 증상, 검사, 치료, 약물을 한 행에
//   이 질병을 언급한 Question 수(MENTIONS)도 함께 돌려주면 "얼마나 자주 다뤄진 질병인지" 알 수 있다.
"""


def run(driver, cypher: str, **params) -> list[dict]:
    if "TODO" in cypher:
        return []
    return [r.data() for r in driver.execute_query(cypher, params, database_=NEO4J_DATABASE).records]


# ---------- B. 커스텀 Retriever ----------
class Text2CypherWithQuery(Text2CypherRetriever):
    def search(self, query_text: str, **kwargs) -> RetrieverResult:
        result = super().search(query_text, **kwargs)
        # TODO B-1: result.metadata 에서 생성된 cypher 를 꺼낸다.
        # TODO B-2: result.items 의 content 를 모두 이어 붙인다. (빈 결과도 처리)
        # TODO B-3: "### 실행된 Cypher 쿼리" + 코드블록 + "### 쿼리 실행 결과" 형식의 문자열을 만들어
        #           RetrieverResultItem 하나로 감싼 RetrieverResult 를 돌려준다. metadata 는 그대로.
        #   생각해 보기: 결과가 0행이면 컨텍스트에 무엇을 써 줘야 답변 LLM 이 지어내지 않을까?
        return result


def main():
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
    try:
        print("[A-1]", run(driver, SYMPTOM_TO_EVERYTHING, keyword="기침")[:3])
        print("[A-2]", run(driver, TWO_SYMPTOMS_INTERSECTION, k1="기침", k2="열")[:3])
        print("[A-3]", run(driver, DISEASE_PROFILE, keyword="폐렴")[:3])

        # B 는 LLM 이 필요하다. A 를 끝낸 뒤 아래 주석을 풀고, 원본의 스키마/예시/프롬프트를 그대로 써서 확인해 보자.
        # from neo4j_graphrag.llm import OpenAILLM
        # from graphrag_reasoning import get_medical_schema, schema_to_text, get_example_queries, get_reasoning_text2cypher_prompt
        # retriever = Text2CypherWithQuery(driver=driver, llm=OpenAILLM(model_name="gpt-4o", model_params={"temperature": 0}),
        #     neo4j_schema=schema_to_text(get_medical_schema()), examples=get_example_queries(),
        #     custom_prompt=get_reasoning_text2cypher_prompt())
        # print(retriever.search(query_text="기침도 하고 열도 나요").items[0].content)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
