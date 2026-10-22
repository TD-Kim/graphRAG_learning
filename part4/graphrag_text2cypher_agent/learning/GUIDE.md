# graphrag_text2cypher_agent 읽기 가이드

강의: Part 4 / CH01-05 Agentic 워크플로우 이해하기 (LangGraph), CH01-06 GraphRAG Agent 구현하기 (2) 쿼리 생성 수정 자동화
데이터: Part 2 `medical2kg` 의료 그래프

| 파일 | 줄 | 역할 |
|---|---|---|
| [`main.py`](../main.py) | 97 | **그래프 조립**: 노드 6개, 일반 엣지, 조건부 엣지 3개 |
| [`state.py`](../state.py) | 22 | 노드들이 공유하는 상태(질문, Cypher, 결과, 재시도 횟수 ...) |
| [`nodes.py`](../nodes.py) | 376 | 노드 함수 6개 + 라우팅 함수 3개 |
| [`prompts.py`](../prompts.py) | 135 | 생성 / 수정 / 답변 프롬프트, 의료 예시 |
| [`schema.py`](../schema.py) | 208 | DB 스키마 추출 + 전역 캐시 |
| [`langgraph.json`](../langgraph.json) | | `langgraph dev`(LangGraph Studio)용 설정 |
| `graph_visualization.png` | | 그래프 그림 |

## 한눈에 보기

```
START → guardrail ─(의료 질문 아님)──────────────────────────────▶ answer → END
            │(의료 질문)
            ▼
     generate_cypher ──▶ validate_query ─(통과)─▶ execute_cypher ─(결과 있음)─▶ answer
            ▲                 │(실패)                │
            │                 ▼                      ├─(오류)──▶ correct_cypher ─▶ validate_query
            │           correct_cypher               │
            └──────────(빈 결과, 2회까지)────────────┘
                   (재시도 5회 초과 → answer 로 탈출)
```

graphrag_tool_agent 에서는 "언제 고쳐서 다시 할지"를 **LLM 이 스스로** 정했다.
여기서는 그 흐름을 **코드(그래프)로 고정**한다. 예측 가능하고, 무한 반복을 막기 쉽고, 단계마다 로그를 남길 수 있다. 이것이 "Agentic 워크플로우"다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | `graph_visualization.png` + `main.py` | 노드와 엣지를 먼저 그림으로 |
| 2 | `state.py` | **InputState(query) / OutputState(answer) / State(내부 전부)** 를 나눈 이유 |
| 3 | `nodes.py` `guardrail_node` (41) | 구조화 출력(`with_structured_output`)으로 yes/no 판정 |
| 4 | `generate_cypher_node` (85) | 스키마 + 예시로 생성 |
| 5 | `validate_query_node` (116) | 실행 전에 규칙 검사 (쓰기 키워드, MATCH 시작, RETURN 존재) |
| 6 | `execute_cypher_node` (159) | 결과는 list, 오류는 **문자열**로 상태에 저장 |
| 7 | `correct_cypher_node` (191) | 오류 메시지를 주고 고친 쿼리 받기 |
| 8 | `route_*` 3개 (296~376) | 상태를 보고 다음 노드 이름을 돌려주는 함수 |
| 9 | `answer_node` (226) | 일반 답변 / 결과 기반 답변 / 오류 설명 |

## "왜"

- **노드는 "상태의 바뀐 부분만" 돌려준다**: `return {"cypher": ...}` 처럼. LangGraph 가 기존 상태에 합친다.
- **조건부 엣지 = 라우팅 함수**: 상태를 보고 문자열을 돌려주면, 그 이름의 노드로 간다. 분기 로직이 프롬프트가 아니라 **코드**에 있다.
- **InputState / OutputState**: 외부(Studio, API)에는 `query` 만 받고 `answer` 만 내보낸다. 내부 상태(재시도 횟수 등)는 숨긴다.
- **guardrail**: 의료와 무관한 질문에 DB 를 뒤지지 않게 맨 앞에서 거른다. 비용과 엉뚱한 답을 줄인다.
- **오류와 빈 결과를 다르게 처리**: 오류는 "쿼리가 틀렸다"(수정), 빈 결과는 "조건이 너무 좁거나 값이 다르다"(다시 생성). 원인이 다르니 대응도 다르다.
- **재시도 상한**: 그래프에 순환이 있으므로 상한이 없으면 무한 루프. 5회, 2회로 막는다.
- **스키마 전역 캐시 (`schema.py`)**: 노드가 불릴 때마다 스키마를 다시 뽑지 않는다.

## 생각해 볼 점

1. **검증 실패 후 수정 노드가 무엇을 보는가**: `validate_query` 가 실패하면 `correct_cypher` 로 가는데, `correct_cypher_node` 는 `validation_error` 가 아니라 `db_outputs[-1]`(마지막 **실행** 결과)을 오류로 넘긴다(195~214줄). 첫 생성 쿼리가 검증에서 떨어지면 아직 실행 결과가 없으니 어떻게 될까? 직접 `DELETE` 를 유도하는 질문으로 확인해 보자.
2. **키워드 검사가 부분 문자열이다** (130줄): `"SET" in "OFFSET"`, `"CREATE" in "created_at"` 도 걸린다. 정상 쿼리가 위험 쿼리로 몰리는 경우는? 정규식 단어 경계(`\b`)로 바꿔 보자.
3. **`MATCH` 로 시작해야 통과** (139줄): `OPTIONAL MATCH`, `WITH`, `CALL {}` 로 시작하는 정상 쿼리는 떨어진다.
4. **빈 결과 재생성은 같은 프롬프트를 다시 보낸다**: 이전 쿼리가 빈 결과였다는 사실을 알려 주지 않는다. 다른 쿼리가 나오는 건 temperature 덕(우연)이다. 이전 쿼리를 알려 주도록 바꾸면?
5. `retry_count > 5` 는 6번째에 탈출한다. 의도한 횟수인가?
6. **`.langgraph_api/*.pckl` 이 커밋되어 있다**: `langgraph dev` 가 만드는 로컬 상태 파일(대화 기록, 체크포인트)이다. 저장소에 올릴 필요가 없고 대화 내용이 들어갈 수 있으니 `.gitignore` 에 넣는 게 좋다.

## 실행 전 체크
- medical2kg 적재, `.env` (OpenAI, Neo4j)
- `python main.py` 는 그래프 그림만 저장한다. 질의는 `langgraph dev`(Studio) 또는 `graph.invoke({"query": "..."})`
