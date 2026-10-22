# toolsretriever 읽기 가이드

강의: Part 3 / CH01-09 다양한 검색 기반 GraphRAG 파이프라인 완성하기 - ToolsRetriever
데이터: Part 2 `pdf2kg` + `pdf2kg_2` 문서 그래프 (+ vectorsearch 에서 만든 `TextElement.embedding`)

| 파일 | 줄 | 역할 |
|---|---|---|
| [`main.py`](../main.py) | 172 | 초기화 → 인덱스 → 4개 Retriever 를 도구로 → `ToolsRetriever` → 대화형 GraphRAG |
| [`config.py`](../config.py) | 65 | 드라이버, LLM, 임베더, 벡터 인덱스 2개(Text, Table) |
| [`vector_retriever.py`](../vector_retriever.py) | 59 | 텍스트/표 벡터 검색 + `convert_to_tool` |
| [`vectorcypher_retriever.py`](../vectorcypher_retriever.py) | 248 | vectorcypher_qdrant 와 같은 확장 쿼리를 Neo4j 벡터 인덱스로 |
| [`text2cypher_retriever.py`](../text2cypher_retriever.py) | 77 | **DB 에서 자동으로 뽑은 스키마** + 예시 |
| [`schema.py`](../schema.py) | 113 | `db.schema.nodeTypeProperties()` 등으로 스키마 조회 → 텍스트 |
| [`prompts.py`](../prompts.py) | 241 | 답변 템플릿 (vectorcypher 결과일 때만 2부 작성) |

## 한눈에 보기

```
                       ┌─ text_vector_search          (TextElement 벡터)
질문 ─▶ ToolsRetriever ─┼─ table_vector_search         (TableElement 벡터)
        (LLM 이 도구     ├─ vectorcypher_context_search (벡터 + 문서 구조 + 엔티티 확장)
         설명을 읽고     └─ text2cypher_structured_query (LLM 이 Cypher 생성)
         골라 호출)
                                   │ 선택된 도구(들)의 결과
                                   ▼
                          GraphRAG(답변 템플릿) ─▶ 답변
```

Part 3 에서 배운 검색 방식을 **하나로 묶는** 실습이다. 핵심은 "어떤 질문에 어떤 검색을 쓸지"를 코드의 if 문이 아니라 **LLM 이 도구 설명(description)을 읽고 고른다**는 것.
Part 4 의 에이전트(도구를 쓰는 LLM)로 넘어가는 다리다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | `main.py` `main`, `create_tools_retriever` | 조립 순서 |
| 2 | `vector_retriever.py` 의 `convert_to_tool` 두 개 | **도구 이름 + 설명**이 선택 기준 |
| 3 | `vectorcypher_retriever.py` `create_vectorcypher_tool` | 개방형 질문, 엔티티 종합용이라고 설명 |
| 4 | `text2cypher_retriever.py` `create_text2cypher_tool` | 정확한 조회, 관계, 목록/통계용이라고 설명 |
| 5 | `schema.py` | 손으로 쓰던 스키마를 DB 에서 자동으로 |
| 6 | `main.py` `run_graphrag` | 결과 metadata 의 `tool` 로 어떤 도구가 선택됐는지 출력 |
| 7 | `prompts.py` | 결과 종류에 따라 답변 형식이 달라지게 |

## "왜"

- **도구 설명이 곧 라우팅 규칙**: 설명에 "사용 시나리오"와 "예시 질문"을 적어 두면 LLM 이 질문과 비교해 고른다. 설명이 겹치면 잘못 고른다. 4개 도구의 설명을 나란히 놓고 겹치는 부분을 찾아보자.
- **표를 따로 검색**: 표는 문장과 모양이 달라 같은 인덱스에 섞으면 잘 안 걸린다. "비교 표", "통계" 같은 질문을 따로 받는다.
- **스키마 자동 조회 (`schema.py`)**: pdf2kg_2 처럼 LLM 이 스키마를 만든 그래프는 실행할 때마다 레이블이 달라질 수 있어서, 손으로 쓴 스키마가 금방 낡는다. DB 에서 직접 읽으면 항상 현재 상태와 같다.
- **`convert_to_tool`**: Retriever 를 LLM 이 호출할 수 있는 도구 형식(이름, 설명, 입력 스키마)으로 감싼다. 같은 Retriever 를 에이전트 프레임워크에서도 쓸 수 있게 하는 어댑터.
- **답변 템플릿이 도구 종류를 의식한다**: vectorcypher 결과에만 entities/expanded_context 가 있으므로, 있을 때만 2부("함께 보면 좋은 정보")를 쓰게 한다.

## 생각해 볼 점

1. **예시와 스키마가 따로 논다**: text2cypher 예시는 `Company.description`, `Person.role`, `toc.document` 같은 속성을 쓴다. pdf2kg 의 TOC 에는 `document` 속성이 없고, Company/Person 의 속성은 pdf2kg_2 를 돌릴 때마다 LLM 이 정한다. 자동 스키마를 출력해서 예시와 맞는지 확인해 보자.
2. **TableElement 임베딩은 누가 만드나**: vectorsearch 노트북은 TextElement 에만 `embedding` 을 넣었다. TableElement 에 임베딩이 없으면 `table_vector_search` 는 항상 빈 결과다.
3. **같은 속성에 인덱스가 둘?**: vectorsearch 에서 `TextElement.embedding` 에 `textElementEmbedding` 인덱스를 이미 만들었다면, 여기서 다른 이름(`text_content_vector_index`)으로 또 만들 수 있을까? 실패는 `except` 로 삼켜지고 이름만 반환된다. `SHOW INDEXES` 로 확인해 보자.
4. **`schema.py` 의 관계 패턴 조회**는 `MATCH (a)-[r]->(b)` 로 모든 관계를 훑는다. 관계가 수백만 개인 그래프(retail)에서는? `db.schema.visualization()` 이나 샘플링으로 바꿀 수 있다.
5. **스키마 조회에 `database_` 가 없다**: 다른 파일들은 모두 `NEO4J_DATABASE` 를 지정한다. 기본 DB 가 아니면 다른 DB 의 스키마를 읽는다.
6. 같은 질문이 매번 같은 도구를 고르는가? 도구 선택이 흔들리는 질문을 찾아 설명을 고쳐 보자.

## 실행 전 체크
- pdf2kg, pdf2kg_2, vectorsearch(임베딩) 선행
- `python main.py` (대화형). 선택된 도구 이름이 출력된다.
