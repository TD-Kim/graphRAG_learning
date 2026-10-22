# vectorcypher 읽기 가이드

강의: Part 3 / CH01-06 Vector + Graph - 의미 검색과 서브 그래프를 함께 가져오는 하이브리드 GraphRAG
데이터: Part 2 `law2kg` 의 법령 + 해석례 그래프

| 파일 | 역할 |
|---|---|
| [`README.md`](../README.md) 4장 | Question 노드에 임베딩 저장 + `question_embedding_index` 생성 (Cypher, GenAI 플러그인) |
| [`vectorcypher.py`](../vectorcypher.py) (336줄) | `VectorCypherRetriever`: 벡터로 Question 을 찾고, 거기서 Cypher 로 주변 그래프를 가져와 답변 |

## 한눈에 보기

```
질문 ─임베딩─▶ question_embedding_index ─▶ 비슷한 Question 노드 (= node)
                                            │
                       retrieval_query (Cypher, node 에서 출발)
                                            ▼
   해석례(제목, 안건번호) + 회답 + 이유 + 주 법령 + 인용 법령/조/항/호  ─▶ 컨텍스트 ─LLM─▶ 구조화된 답변
```

지금까지의 세 방식을 한 줄로:
- **vectorsearch**: 비슷한 텍스트 조각만 가져온다.
- **text2cypher**: LLM 이 쿼리를 만든다. 정확하지만 질문이 모호하면 약하다.
- **vectorcypher**: 시작점은 의미로 찾고(유연), 그 다음은 **사람이 미리 쓴 Cypher** 로 정해진 주변을 가져온다(안정적).

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | README 4-1, 4-2 | Question.text 를 임베딩하고 인덱스 생성 |
| 2 | `create_legal_vectorcypher_retriever` (66) | **`retrieval_query`** 가 이 실습의 본체 |
| 3 | `create_legal_graphrag` (177) | 답변 형식(관련 해석례 / 질의 / 회답 / 법적 근거 / 이유)을 템플릿으로 고정 |
| 4 | `search_legal_interpretation` (243) | `retriever_config={"top_k": ...}` 로 시작 노드 수 조절 |

## "왜"

- **`retrieval_query` 의 `node` 변수**: VectorCypherRetriever 가 벡터 검색으로 찾은 노드를 `node` 라는 이름으로 넘겨준다(점수는 `score`). 쿼리는 반드시 `node` 에서 출발해야 한다.
- **벡터 검색 대상을 Question 으로 고른 이유**: 사용자의 질문과 가장 모양이 비슷한 텍스트가 해석례의 "질의요지"다. 질문-질문 매칭이 질문-이유 매칭보다 잘 맞는다.
- **OPTIONAL MATCH 로 주변 수집**: 회답이 없거나 인용 조문이 없는 해석례도 있다. 하나라도 없으면 결과에서 사라지지 않게.
- **조/항/호를 각각 부모까지 거슬러 올라가기 (113~117줄)**: "제4조제1항"이라는 표현을 만들려면 항 노드에서 조문 번호를, 조문에서 법령명을 가져와야 한다.
- **`collect(DISTINCT {...})`**: 맵(map)을 모아 구조화된 컨텍스트를 만든다. LLM 이 "어느 법의 몇 조"를 정확히 인용할 수 있다.
- **답변 템플릿의 출력 형식 고정**: 법률 도메인은 결론 → 근거 → 이유 순서가 중요하다. 형식을 정해 두면 답변 품질이 안정된다.

## 생각해 볼 점

1. **항/호의 법령명이 틀릴 수 있다**: `cited_paragraphs`, `cited_items` 의 `law` 에 `article_law.name` 을 쓰는데, `article_law` 는 `cited_article` 에서 거슬러 올라간 법령이다(113줄). 항이나 호만 인용하고 조문은 인용하지 않았으면? 항 → 조문 → 법령으로 따로 올라가야 맞다.
2. **행 폭발**: OPTIONAL MATCH 를 8개 이어 쓰면 각 결과의 곱만큼 행이 생긴 뒤 collect 된다. 인용 조문 5개 × 항 5개 × 호 5개면? `CALL {}` 서브쿼리나 단계별 `WITH ... collect` 로 나눠 보자.
3. **README 의 배치 임베딩 쿼리**: `WITH collect(q) AS questions, ... LIMIT $batch_size` 는 collect 로 이미 한 행이 된 뒤에 LIMIT 을 건다. 100개씩 나눠질까? (vectorsearch 노트북의 셀 16 과 비교)
4. `top_k=1` 로 실행한다. 비슷한 해석례가 여러 개면 2~3으로 늘리는 게 나을까? 컨텍스트 길이와의 균형은?
5. `answer.text` 와 `reason.text` 는 `node`(Question)-[:ANSWERED_BY]->(Answer) 경로로 가져온다. law2kg 의 `HAS_REASON` 분기(law2kg GUIDE 생각해 볼 점 2)와 연결해 보면, 회답이 없는 해석례의 이유는 컨텍스트에 들어올까?

## 실행 전 체크
- `part2/law2kg` 의 step1, step2 를 먼저 실행
- README 4장의 임베딩과 인덱스 생성 (토큰은 `:param` 으로만, 파일에 남기지 않기)
- `python vectorcypher.py` (질문은 `main` 의 `test_query` 를 바꿔 가며)
