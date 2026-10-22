# vectorcypher_qdrant 읽기 가이드

강의: Part 3 / CH01-07 Vector + Graph - 벡터 데이터베이스(Qdrant)와 함께 사용하기
데이터: Part 2 `pdf2kg.py` + `pdf2kg_2.py` 의 문서 그래프 (TextElement, Chunk, TOC, 도메인 엔티티)

| 파일 | 줄 | 역할 |
|---|---|---|
| [`ingest_to_qdrant.py`](../ingest_to_qdrant.py) | 299 | Neo4j 의 TextElement 를 읽어 임베딩 → Qdrant 에 저장 (payload 에 `element_id`) |
| [`graphrag_qdrant.py`](../graphrag_qdrant.py) | 637 | `QdrantNeo4jRetriever`: Qdrant 로 찾고 Neo4j 로 확장, 결과 포맷터, 긴 답변 템플릿 |

## 한눈에 보기

```
[적재] Neo4j TextElement ─▶ OpenAI 임베딩 ─▶ Qdrant point {vector, payload: element_id, toc, page, content}

[검색] 질문 ─임베딩─▶ Qdrant top_k ─▶ payload.element_id ─▶ Neo4j (:TextElement {element_id})  = node
         ─▶ retrieval_query: node → Chunk → TOC(+부모 TOC 계층) / 같은 Chunk 의 문장들 / Chunk 의 엔티티
                             → 같은 엔티티를 가진 다른 Chunk 의 문장들(확장)
         ─▶ result_formatter 로 읽기 좋은 텍스트 ─▶ 답변 (본문 + "함께 보면 좋은 정보")
```

vectorcypher(법령)와 구조는 같다. 차이는 **벡터가 Neo4j 가 아닌 별도 벡터 DB 에 있다**는 것.
두 저장소를 잇는 열쇠는 `element_id` 하나다(`id_property_external` ↔ `id_property_neo4j`).

## 왜 벡터 DB 를 따로 쓰나

| | Neo4j 벡터 인덱스 | Qdrant 같은 벡터 DB |
|---|---|---|
| 장점 | 한 곳에서 관리, 쿼리 한 번에 검색+확장 | 대용량 벡터 성능, 필터/양자화 등 벡터 전용 기능, 이미 회사에 있을 수 있음 |
| 단점 | 벡터가 매우 많으면 부담 | 두 저장소의 **동기화**(삭제/수정 반영)를 직접 챙겨야 함 |

실무에서는 "이미 쓰고 있는 벡터 DB 에 그래프를 붙이는" 경우가 많아서 이 패턴을 배운다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | `ingest_to_qdrant.py` `__main__` (240) | 컬렉션 확인 → 이미 있으면 지우고 다시 할지 묻기 → 조회 → 적재 |
| 2 | `fetch_text_elements_from_neo4j` (122) | TextElement + 속한 TOC 제목을 함께 (payload 에 넣으려고) |
| 3 | `ingest_text_elements_to_qdrant` (166) | point = 벡터 + payload. 10개씩 upsert |
| 4 | `graphrag_qdrant.py` `create_retriever` (152) | **retrieval_query** (부모 TOC 계층 `HAS_CHILD*`, 엔티티 기반 확장) |
| 5 | `format_retrieval_result` (53) | Neo4j Record → 사람이 읽을 텍스트 + metadata 보관 |
| 6 | `create_graphrag_pipeline` (297) | 2부 구성 답변 템플릿 (본문 + 연결 구조 설명) |

## "왜"

- **payload 에 content, toc 까지 넣는 이유**: Qdrant 만으로도 결과를 보여 줄 수 있고, 디버깅이 쉽다. 단, Neo4j 와 내용이 이중 저장된다.
- **`HAS_CHILD*` (가변 길이 경로)**: 부모, 조부모 … 목차를 모두 올라간다. "이 문장은 2장 > 2.3절 > 2.3.1 에 있다"는 위치 정보를 만든다.
- **엔티티 기반 확장 (202~219줄)**: 이 Chunk 의 엔티티(예: K-EXAONE)를 가진 **다른 Chunk** 의 문장까지 가져온다. 키워드나 벡터로는 연결되지 않던 섹션이 그래프로 이어지는 것이 GraphRAG 의 "확장 인사이트".
- **`result_formatter`**: 기본 포맷(문자열화된 dict) 대신, LLM 이 읽기 좋은 구조로 바꾼다. vectorsearch 의 `ast.literal_eval` 문제를 여기서 해결하는 방법이다.
- **metadata 에 원본 보관 (129~140줄)**: 답변용 텍스트와 별개로, 화면에 출처를 그리거나 평가할 때 쓸 원본 데이터를 남긴다.

## 생각해 볼 점

1. **확장 크기에 상한이 없다**: 흔한 엔티티(예: "AI")를 공유하는 Chunk 가 수십 개면 expanded_context 가 매우 길어진다. 엔티티당/전체 확장 개수를 어떻게 제한할까? (`LIMIT` 를 서브쿼리 안에서)
2. **`uuid4()` 포인트 ID**: 다시 적재하면 같은 문장이 다른 ID 로 또 들어간다(그래서 컬렉션을 지우고 다시 만든다). `uuid5(namespace, element_id)` 처럼 결정적 ID 를 쓰면 upsert 만으로 갱신된다.
3. **임베딩을 한 문장씩 요청한다** (193줄). OpenAI 임베딩 API 는 리스트를 받는다. 배치로 바꾸면 몇 배 빨라질까?
4. **동기화**: pdf2kg 를 다시 실행하면 `element_id` 가 바뀔 수 있다(순번 기반). 그러면 Qdrant 의 payload 와 Neo4j 가 어긋난다. 어떻게 감지할까?
5. **긴 답변 프롬프트** (313~486줄): 규칙이 많고 "볼드체는 entities 만" 같은 세부 규칙이 반복된다. 규칙이 많을수록 잘 지켜질까? 절반으로 줄여 비교해 보자.
6. `__main__` 의 `finally: neo4j_driver.close()` 는 드라이버 생성 전에 실패하면 `NameError` 가 난다. ingest 쪽처럼 `locals()` 확인이 필요하다.

## 실행 전 체크
- Qdrant Cloud 무료 클러스터: `.env` 에 `QDRANT_URL`, `QDRANT_KEY`, (선택) `QDRANT_COLLECTION`
- 순서: `pdf2kg.py` → `pdf2kg_2.py` → `ingest_to_qdrant.py` → `graphrag_qdrant.py`(대화형)
