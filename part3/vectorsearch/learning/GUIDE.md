# vectorsearch 읽기 가이드

강의: Part 3 / CH01-05 Vector Search - 문서 지식그래프에 벡터 인덱스 추가하고 의미 검색 구현하기
전제: Part 2 `pdf2kg.py` 로 만든 TextElement 노드가 Neo4j 에 있다.

| 파일 | 역할 |
|---|---|
| [`vector_index.ipynb`](../vector_index.ipynb) | Neo4j **안에서** 임베딩 생성(GenAI 플러그인) → `TextElement.embedding` 저장 → 벡터 인덱스 생성 → Cypher 로 검색 |
| [`vectorsearch.py`](../vectorsearch.py) (185줄) | 같은 인덱스를 **Python 쪽에서** `neo4j-graphrag` 의 `VectorRetriever` 로 검색 |

## 한눈에 보기

```
[노트북] TextElement.content ─ai.text.embedBatch (DB 안에서 OpenAI 호출)─▶ TextElement.embedding (1536차원)
         ─▶ CREATE VECTOR INDEX textElementEmbedding (cosine)
         ─▶ db.index.vector.queryNodes(index, k, 질문벡터) → (node, score)

[vectorsearch.py] 질문 ─OpenAIEmbeddings(Python)─▶ 질문벡터 ─VectorRetriever─▶ 같은 인덱스 검색 → top_k
```

README 의 한 줄이 핵심이다: **벡터 검색은 "그래프 탐색을 시작할 노드"를 찾는 방법이다.** 이후 vectorcypher 에서 여기서 찾은 노드를 출발점으로 그래프를 따라간다.

## 노트북 읽는 순서

| 셀 | 핵심 |
|---|---|
| 6 | 임베딩 전 상태 확인 (`t.embedding IS NOT NULL` 개수) |
| 10 | `ai.text.embed()` 로 노드 **하나**에 임베딩 저장 (작게 먼저 확인) |
| 12 | `ai.text.embedBatch()` 로 10개 |
| 16 | **전체 배치 루프**: "임베딩 없는 것 100개" 를 반복해서 0개가 될 때까지 |
| 19, 21 | 벡터 인덱스 생성 두 방법 (Cypher / `create_vector_index`) |
| 23 | 인덱스 상태(`state`)가 `ONLINE` 인지 확인 |
| 25 | Cypher 만으로 질문 임베딩 + 검색 |

## "왜"

- **DB 안에서 임베딩 (GenAI 플러그인)**: 데이터를 Python 으로 꺼냈다 다시 넣을 필요가 없다. 대신 `neo4j.conf` 에 `dbms.security.procedures.allowlist=genai.*,ai.*` 설정이 필요하고, 토큰을 쿼리 파라미터로 넘긴다.
- **`WHERE t.embedding IS NULL ... LIMIT` 반복 (셀 16)**: 중간에 실패해도 다시 돌리면 남은 것만 처리한다(재시작 가능). 한 번에 수천 개를 보내면 API 한도와 트랜잭션 크기에 걸린다.
- **`embedBatch` 의 `YIELD index, vector`**: 입력 리스트의 몇 번째 결과인지 `index` 로 알려 주므로 `batch[index]` 노드에 정확히 붙일 수 있다.
- **차원 1536**: `text-embedding-3-small` 의 출력 크기. 인덱스 차원과 모델이 다르면 인덱스를 못 쓴다.
- **cosine**: 벡터 길이가 아니라 방향(의미)을 비교한다. 텍스트 임베딩의 표준 선택.
- **질문과 문서는 같은 모델로 임베딩**: 다른 모델의 벡터끼리는 비교가 의미 없다.
- **`VectorRetriever`**: 질문 임베딩 + `queryNodes` + 결과 포맷팅을 한 번에 해 주는 래퍼. `return_properties` 로 돌려받을 속성만 고른다.

## 생각해 볼 점

1. **`print_search_results` 가 실패할 수 있다**: `content`, `page` 변수는 `item.content` 가 `{` 로 시작할 때만 만들어진다(137~145줄). 아니면 아래 `if page is not None` 에서 `UnboundLocalError`. 어떻게 고칠까?
2. `ast.literal_eval(item.content)`: Retriever 가 결과를 **문자열화된 dict** 로 준다. `result_formatter` 옵션으로 처음부터 원하는 모양을 받을 수 있는지 문서를 찾아보자.
3. TextElement 는 5자 이상 문단 하나 단위다. 너무 짧은 요소가 상위에 뜨는 경우가 있나? Chunk 단위로 임베딩하면 어떻게 달라질까?
4. score 가 0.8 이어도 관련 없는 결과일 수 있다. 관련 없는 질문("오늘 점심 메뉴")을 넣었을 때 score 를 보고 "결과 없음" 기준(threshold)을 정해 보자.

## 실행 전 체크
- Neo4j GenAI 플러그인 설정 (README), `OPENAI_API_KEY`
- **API 키를 README, 노트북 출력, 커밋에 남기지 않는다.** 노트북은 `$openai_token` 파라미터로 넘긴다.
- 실행: `python vectorsearch.py "AI 규제 동향"`
