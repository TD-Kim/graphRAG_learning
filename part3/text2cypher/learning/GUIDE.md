# text2cypher 읽기 가이드

강의: Part 3 / CH01-01 GraphRAG 란, CH01-02 Text2Cypher - 사용자 질의를 Cypher 쿼리로 변환하기
데이터: Part 2 `csv2kg` 의 타이타닉 그래프

| 파일 | 역할 |
|---|---|
| [`text2cypher.ipynb`](../text2cypher.ipynb) | **DB 없이** 프롬프트 → Cypher 생성 과정만 들여다보기 (영화 스키마 예시, `extract_cypher`) |
| [`text2cypher.py`](../text2cypher.py) (354줄) | 타이타닉 그래프에 **실제로** 질문 → Cypher → 실행 → 답변 (`neo4j-graphrag` 의 GraphRAG) |

## 한눈에 보기

```
질문 ─▶ [Text2CypherRetriever] 스키마 + 예시 + 질문 ─LLM─▶ Cypher ─실행─▶ 결과 행들
     ─▶ [GraphRAG] RagTemplate(결과 + 질문) ─LLM─▶ 자연어 답변
```

LLM 을 **두 번** 부른다: ① Cypher 를 만들 때 ② 결과를 문장으로 만들 때.
벡터 검색과 달리 "몇 명?", "비율은?", "가장 높은 것은?" 같은 **집계와 정확한 조건** 질문에 강하다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | 노트북 셀 5 | `Text2CypherTemplate` 의 기본 프롬프트 원문. LLM 이 실제로 무엇을 받는지 |
| 2 | 노트북 셀 8 | `extract_cypher`: 응답에서 코드블록만 꺼내고, 공백 있는 이름에 백틱 |
| 3 | 노트북 셀 11~15 | 스키마만 줬을 때 vs 예시까지 줬을 때 생성 결과 비교 |
| 4 | `get_titanic_schema` (15) | 사람이 쓴 JSON 스키마 (설명 포함) |
| 5 | `schema_to_text` (155) | JSON → `Node properties / Relationship properties / The relationships` 텍스트 |
| 6 | `get_example_queries` (190) | 질문-쿼리 예시 10개 (few-shot) |
| 7 | `create_graphrag_pipeline` (244) | Retriever + 답변 템플릿 + GraphRAG 조립 |
| 8 | `main` (309) | `return_context=True` 로 생성된 Cypher 와 결과 행까지 출력 |

## "왜"

- **스키마를 텍스트로 넣는 이유**: LLM 은 그래프에 어떤 레이블/속성/관계가 있는지 모른다. 없으면 `(:Person)` 처럼 존재하지 않는 이름을 지어낸다.
- **스키마 텍스트 형식**: `neo4j-graphrag` 가 DB 에서 자동으로 뽑는 스키마와 같은 모양이라 템플릿과 잘 맞는다. 직접 쓰면 **설명(description)** 을 넣을 수 있다는 장점이 있지만, `schema_to_text` 는 설명을 텍스트에 넣지 않는다. 넣으면 무엇이 좋아질까?
- **예시(few-shot)**: "생존율" 같은 표현을 `sum(p.Survived)/count(p)` 로 바꾸는 법, `Survived` 가 0/1 이라는 사실을 예시로 알려 준다. 스키마만으로는 알 수 없는 **도메인 관례**를 가르치는 수단이다.
- **`temperature: 0`**: 같은 질문엔 같은 Cypher.
- **답변 템플릿의 규칙 3번** "검색된 데이터에 없는 정보는 추측하지 마세요": 결과가 비었을 때 LLM 이 그럴듯한 숫자를 지어내는 것을 막는다.
- **`return_context=True`**: 최종 답만 보면 틀린 이유를 알 수 없다. 생성된 Cypher 와 결과 행을 같이 봐야 "쿼리가 틀렸는지, 답변이 틀렸는지"를 나눌 수 있다.

## 생각해 볼 점

1. **예시 7번의 `p.Pclass`** (198줄): Passenger 노드에는 `Pclass` 속성이 없다(PClass 노드에 있다). 예시가 틀리면 LLM 이 그 실수를 따라 한다. 고쳐 보자.
2. **쓰기 쿼리 방어가 없다**: "모든 승객을 삭제해줘" 같은 질문에 `DETACH DELETE` 가 생성되면 그대로 실행될 수 있다. 읽기 전용 계정, 읽기 트랜잭션, 키워드 검사 중 무엇을 쓸까?
3. 스키마를 빼고(`use_schema=False`), 예시를 빼고(`use_examples=False`) 각각 같은 질문 5개를 돌려 정확도를 비교해 보자. (Part 3 평가 실습의 씨앗)
4. 존재하지 않는 값("D99 선실")을 물으면 결과가 비고, 답변은 무엇이라고 할까?

## 실행 전 체크
- 타이타닉 그래프가 적재된 Neo4j (`part2/csv2kg`)
- `OPENAI_API_KEY`. 노트북은 Neo4j 없이도 돌아간다.
