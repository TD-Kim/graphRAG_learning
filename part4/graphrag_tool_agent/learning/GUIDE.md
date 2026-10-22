# graphrag_tool_agent 읽기 가이드

강의: Part 4 / CH01-03 GraphRAG 를 위한 도구 정의하기, CH01-04 GraphRAG Agent 구현하기 (1) 검색 방식 자동화
데이터: Part 2 pdf2kg 문서 그래프 + `text_content_vector_index` (Part 3 toolsretriever 의 인덱스)

| 파일 | 줄 | 역할 |
|---|---|---|
| [`tools.py`](../tools.py) | 543 | `@tool` 4개: 스키마 조회 / Cypher 생성 / Cypher 실행 / VectorCypher 검색. 공용 자원은 모듈 전역에 한 번만 |
| [`main.py`](../main.py) | 156 | `create_agent` + 워크플로우를 설명하는 시스템 프롬프트 + 대화형 스트리밍 루프 |
| `tool_agent.png` | | 에이전트 그래프 그림 |

## 한눈에 보기

```
질문 ─▶ Agent(LLM) ─┬─ [Text2Cypher 워크플로우] schema_introspection → generate_cypher_query → execute_cypher_query
                     └─ [Vector 워크플로우]     vector_search (벡터 + 문서 구조 + 엔티티 확장)
                     ─▶ 도구 결과를 보고 필요하면 또 호출 ─▶ 최종 답변
```

Part 3 toolsretriever 와 비교:
- toolsretriever: 검색 도구 4개 중 **하나를 골라 한 번** 검색.
- tool agent: Text2Cypher 를 **세 단계 도구로 쪼개** 에이전트가 순서대로 부르고, 실패하면 다시 시도할 수도 있다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | `main.py` `create_graphrag_agent` | 시스템 프롬프트가 **두 워크플로우와 언제 쓰는지**를 설명 |
| 2 | `tools.py` `initialize_tools` (19) | 드라이버/LLM/임베더/Retriever 를 전역에 **한 번만** 만든다 |
| 3 | `schema_introspection` (200) | DB 에서 스키마 조회 → 텍스트 |
| 4 | `generate_cypher_query` (296) | 스키마 + 예시 + 규칙으로 Cypher **생성만** (실행 안 함) |
| 5 | `execute_cypher_query` (411) | 실행 + 결과 포맷. 오류도 문자열로 돌려준다 |
| 6 | `vector_search` (451) | VectorCypherRetriever 결과를 텍스트로 |
| 7 | `main.py` `run_agent_interactive` (56) | 노드별 스트리밍 출력, **대화 기록 누적** |
| 8 | `tools.py` `__main__` (498) | 도구를 에이전트 없이 하나씩 테스트 |

## "왜"

- **Text2Cypher 를 3개 도구로 쪼갠 이유**: 한 도구 안에서 생성+실행을 하면 에이전트는 중간 Cypher 를 볼 수 없다. 쪼개면 에이전트가 생성된 쿼리를 보고, 실행 오류를 받고, **고쳐서 다시** 부를 수 있다(다음 실습의 자동 수정으로 이어짐).
- **오류를 예외가 아니라 문자열로 반환**: 예외면 에이전트 루프가 끊긴다. 문자열이면 LLM 이 읽고 다음 행동을 정한다.
- **전역 초기화**: 도구는 호출될 때마다 실행된다. 매번 드라이버를 만들면 느리고 연결이 쌓인다.
- **도구를 에이전트 없이 먼저 테스트 (`tools.py` 직접 실행)**: 에이전트가 틀렸을 때 "도구가 틀렸나, LLM 판단이 틀렸나"를 나누려면 도구 단독 동작부터 확인해야 한다.
- **대화 기록에 도구 메시지까지 누적**: 다음 질문에서 "아까 그 회사"처럼 앞 맥락을 이어 갈 수 있다.

## 생각해 볼 점

1. **LLM 이 만든 Cypher 를 그대로 실행한다**: `execute_cypher_query` 에는 읽기 전용 제한이 없다. "모든 노드를 지워줘"라고 하면? 읽기 트랜잭션(`routing_=READ` 또는 `session.execute_read`), 키워드 검사, 읽기 전용 계정 중 무엇을 넣을까?
2. docstring 은 "최대 20개 레코드"라고 하지만 코드는 **전부** 출력한다. 결과가 1만 행이면 에이전트 컨텍스트가 넘친다.
3. `generate_cypher_query(question, schema_text)`: 에이전트가 스키마 전체를 **인자로 복사해서** 넘기게 된다. 토큰이 두 번 든다. 스키마를 도구 안에서 캐시하면?
4. 대화 기록이 계속 쌓인다(117줄). 도구 결과가 길면 몇 턴 만에 컨텍스트 한도에 닿는다. 오래된 도구 결과를 줄이는 방법은?
5. 스키마 조회 쿼리들에 `database_` 가 없고, 관계 패턴은 `MATCH (a)-[r]->(b)` 로 전체를 훑는다 (toolsretriever 와 같은 문제).
6. `main()` 은 환경변수가 없으면 아무 메시지 없이 끝난다(145~148줄). 처음 실행하는 사람에게 친절할까?

## 실행 전 체크
- pdf2kg + 임베딩 + `text_content_vector_index` (toolsretriever 를 먼저 실행하면 생긴다)
- `python tools.py` 로 도구 단독 테스트 → `python main.py`
