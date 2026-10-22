# reasoning 읽기 가이드

강의: Part 3 / CH01-03, 04 의사결정을 위한 추론 검색 (Text2Cypher - 쿼리 생성, 조회, 답변 파이프라인)
데이터: Part 2 `medical2kg` 의 의료 지식그래프
그림: [`reasoning_flow.md`](../reasoning_flow.md) / `reasoning_flow.png` — text2cypher.py 와 이 파일의 차이를 한 장으로 보여 준다.

| 파일 | 줄 | 역할 |
|---|---|---|
| [`graphrag_reasoning.py`](../graphrag_reasoning.py) | 764 | text2cypher 의 구조 그대로 + **추론용 프롬프트, 추론 패턴 예시, 쿼리를 컨텍스트에 넣는 커스텀 Retriever** |

## text2cypher 와 무엇이 다른가

| | text2cypher.py (타이타닉) | graphrag_reasoning.py (의료) |
|---|---|---|
| 질문 유형 | 정확한 사실/집계 ("1등급 생존율") | 막연한 상황 ("기침이 심해요") |
| Cypher 프롬프트 | 라이브러리 기본 템플릿 | `custom_prompt` 로 **추론 특화** 프롬프트 |
| 예시 | 질문 → 쿼리 | 질문 → **사용자가 말한 것 / 시스템이 추론할 것 / 경로** → 쿼리 |
| 쿼리 모양 | MATCH 한두 개 | 시작 엔티티 MATCH + **OPTIONAL MATCH 여러 개로 확장** + collect |
| 답변 컨텍스트 | 결과 행만 | **실행된 Cypher + 결과** (커스텀 Retriever) |

"사용자가 A 만 말해도 그래프를 따라 B, C, D 까지 모아 오는 것"이 이 실습의 추론(reasoning)이다. LLM 이 혼자 추론하는 게 아니라 **그래프 경로가 추론의 뼈대**가 된다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | `main` (717) | 엔티티 샘플을 보여 주고 질문을 받는 루프 |
| 2 | `get_example_queries` (374) | 5가지 **추론 패턴**: 증상 하나 / 증상 여러 개(교집합) / 질병 / 신체 부위 / 약물 |
| 3 | `get_reasoning_text2cypher_prompt` (505) | 추론 경로 목록, 질문 분석 단계, "항상 OPTIONAL MATCH" 같은 규칙 |
| 4 | `Text2CypherWithQueryRetriever` (16) | 부모 `search` 결과에 Cypher 를 붙여 **아이템 하나로** 합친다 |
| 5 | `create_graphrag_pipeline` (604) | `custom_prompt=` 로 기본 템플릿 교체, 답변 템플릿에 "추론 과정 설명", "의료 안내 문구" |
| 6 | `get_medical_schema` (67) | 손으로 쓴 스키마 (설명 포함) |

## "왜"

- **예시에 `WHAT USER MENTIONED / WHAT SYSTEM INFERS / INFERENCE PATH` 를 넣는 이유**: 쿼리만 보여 주면 LLM 은 모양을 흉내 낼 뿐이다. "왜 이 경로를 골랐는지"를 같이 보여 주면 새로운 질문에도 경로를 설계한다(생각 과정 시연).
- **OPTIONAL MATCH**: 질병에 치료법이 없다고 그 질병까지 결과에서 사라지면 안 된다. MATCH 로만 이으면 하나라도 끊긴 경로는 통째로 빠진다.
- **`CONTAINS` 부분 일치**: 사용자는 "기침", 그래프에는 "마른기침", "기침 및 가래"처럼 저장돼 있다. 정확히 일치(`=`)로는 거의 못 찾는다.
- **교집합 패턴 (증상 2개)**: `(s1)-[:INDICATES]->(d)<-[:INDICATES]-(s2)` 처럼 두 증상이 **같은 질병**을 가리키는 경로. 진단 추론의 기본형.
- **커스텀 Retriever 로 Cypher 를 컨텍스트에**: 결과 행만 보면 답변 LLM 은 "이 목록이 무엇의 목록인지"를 모른다. 실행된 쿼리를 같이 주면 "증상 → 질병 → 치료" 경로를 설명할 수 있다.
- **`show_entity_samples`**: 그래프에 실제로 있는 이름을 보여 줘서 사용자가 찾을 수 있는 질문을 하게 돕는다. 데모용 장치.
- **의료 안내 문구 강제**: 도메인 규칙(면책)을 프롬프트로 보장.

## 생각해 볼 점

1. **스키마와 실제 그래프가 다르다**: 이 스키마는 관계에 `evidence: STRING`, `qa_id: INTEGER` 가 있다고 하지만, medical2kg 는 `count`, `qa_ids`(리스트), `evidence` 로 저장한다. `LOCATED_IN` 은 medical2kg 스키마(`domain_schemas.json`)에 없다. LLM 이 없는 관계/속성으로 쿼리를 만들면 결과가 비게 된다. 실제 그래프에서 스키마를 확인하고 맞춰 보자.
2. medical2kg 가 쌓은 `r.count`(여러 QA 가 말한 관계일수록 큼)를 정렬에 쓰면 더 믿을 만한 질병이 위로 온다. 예시 쿼리에 넣어 보자.
3. "항상 OPTIONAL MATCH" 규칙 때문에 결과가 너무 커질 수 있다(질병 × 증상 × 치료의 곱). collect 를 언제 하느냐에 따라 행 수가 어떻게 달라질까?
4. `show_entity_samples` 는 `driver.session()` 에 database 를 지정하지 않는다. 다른 함수들은 모두 지정한다. 기본 DB 가 아니면 어떻게 될까?
5. 같은 증상 질문을 표현만 바꿔("기침 나요", "콜록거려요") 넣으면 결과가 같을까? 동의어 문제는 그래프와 LLM 중 어디서 풀까?

## 실행 전 체크
- `medical2kg.py` 로 의료 그래프를 적재. `OPENAI_API_KEY`.
- 대화형이다: `python graphrag_reasoning.py` 후 질문 입력, `q` 로 종료.
