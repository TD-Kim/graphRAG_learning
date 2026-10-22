"""
[2단계: 빈칸 채우기] law2kg 의 핵심 2가지
  A. 중첩 API JSON -> 조/항/호 구조로 파싱 (Neo4j, API 없이 샘플 JSON 만으로 연습 가능)
  B. 조/항/호를 그래프에 넣는 Cypher (MERGE + 경로형 id + order)

준비: part2/law2kg 에서 `python law_api.py` 를 한 번 실행해 eflaw_detail_sample.json 을 만든다.
실행: part2/law2kg 에서 `python learning/step2_fill_in.py`
     -> A 만 채워도 조문/항/호 개수가 출력된다. B 는 Neo4j 가 있을 때 저장까지 한다.
막히면 GUIDE.md -> 원본 law2kg.py (152~380줄).
"""
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")
SAMPLE = Path(__file__).resolve().parent.parent / "eflaw_detail_sample.json"


# ---------- A. 파싱 ----------
def as_list(value: Any) -> list:
    # TODO A-1: 이 API 는 항목이 1개면 dict, 여러 개면 list 로 준다.
    #           None/빈값 -> [], dict -> [dict], list -> 그대로 돌려준다.
    ...


def to_text(value: Any) -> str | None:
    # TODO A-2: Neo4j 속성에는 중첩 객체를 넣을 수 없다.
    #           dict/list 면 json.dumps(ensure_ascii=False), None 이면 None, 나머지는 str().
    ...


def parse_items(item_value: Any) -> list[dict]:
    # TODO A-3: as_list 로 감싼 뒤, 각 호에서 '호내용'(없으면 '내용')을 content 로 꺼낸다.
    ...


def parse_paragraphs(article: dict) -> list[dict]:
    # TODO A-4: article 에 '항' 이 없으면 [].
    #   각 항에서 content = '항내용'(없으면 '내용', 없으면 ''), items = parse_items(항['호'])
    #   주의: '항내용' 없이 '호' 만 있는 항도 있다(원본 188줄). 그때도 items 는 살려야 한다.
    ...


def parse_articles(law_detail: dict) -> list[dict]:
    # TODO A-5: law_detail['법령']['조문']['조문단위'] 를 as_list 로 감싸 돌면서
    #   number = '조문번호' or '조번호'
    #   title  = '조문제목' or '조문가지번호'
    #   content= '조문내용' or '조문'
    #   paragraphs = parse_paragraphs(조문)
    #   중간 키가 없을 수도 있으니 .get(..., {}) 로 안전하게.
    ...


# ---------- B. 저장 ----------
def save_law_structure(driver, law_id: str, articles: list[dict]) -> None:
    for order, art in enumerate(articles, 1):
        article_id = f"{law_id}_{art.get('number') or order}"
        # TODO B-1: Article 을 article_id 로 MERGE, 나머지 속성은 SET.
        #           같은 쿼리에서 (l:Law {law_id}) 를 MATCH 해 HAS_ARTICLE {order} 를 MERGE 한다.
        #   힌트: MERGE ... SET ... WITH a MATCH (l:Law ...) MERGE (l)-[:HAS_ARTICLE {order: $order}]->(a)

        for p_order, para in enumerate(art["paragraphs"], 1):
            paragraph_id = f"{article_id}_p{p_order}"
            # TODO B-2: Paragraph MERGE + (Article)-[:HAS_PARAGRAPH {order}]->(Paragraph)

            for i_order, item in enumerate(para["items"], 1):
                item_id = f"{paragraph_id}_i{i_order}"
                # TODO B-3: Item MERGE + (Paragraph)-[:HAS_ITEM {order}]->(Item)

    # TODO B-4: 한 법령의 조문을 order 순으로 collect 해서 이웃끼리 NEXT_ARTICLE 로 잇는다.
    #   힌트: WITH a ORDER BY a.order  WITH collect(a) AS arts  UNWIND range(0, size(arts)-2) AS i ...
    #   왜 이 관계가 있으면 좋을까? ("제3조 다음 조문은?")


def main():
    if not SAMPLE.exists():
        print(f"{SAMPLE.name} 이 없습니다. 먼저 `python law_api.py` 를 실행하세요.")
        return

    detail = json.loads(SAMPLE.read_text(encoding="utf-8"))
    articles = parse_articles(detail) or []
    n_para = sum(len(a["paragraphs"]) for a in articles)
    n_item = sum(len(p["items"]) for a in articles for p in a["paragraphs"])
    print(f"조문 {len(articles)}개 / 항 {n_para}개 / 호 {n_item}개")

    # 원본 law2kg.extract_articles_from_law_detail 결과와 개수가 같은지 비교해 보자.

    uri, user, pw = os.getenv("NEO4J_URI"), os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")
    if uri and user and pw:
        law_id = str(detail.get("법령", {}).get("기본정보", {}).get("법령ID", "SAMPLE"))
        driver = GraphDatabase.driver(uri, auth=(user, pw))
        try:
            driver.execute_query("MERGE (:Law {law_id: $id})", id=law_id, database_=NEO4J_DATABASE)
            save_law_structure(driver, law_id, articles)
            print("저장 완료. Neo4j Browser: MATCH p=(:Law)-[:HAS_ARTICLE]->()-[:HAS_PARAGRAPH]->() RETURN p LIMIT 25")
        finally:
            driver.close()


if __name__ == "__main__":
    main()
