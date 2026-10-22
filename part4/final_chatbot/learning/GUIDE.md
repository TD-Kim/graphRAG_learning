# final_chatbot 읽기 가이드

강의: Part 4 / CH02-02 GraphRAG Agent 를 챗봇으로 완성하기
의존: `../graphrag_tool_agent` 의 `create_graphrag_agent()` 를 그대로 가져다 쓴다.

| 파일 | 줄 | 역할 |
|---|---|---|
| [`app.py`](../app.py) | 399 | Streamlit 챗봇: 에이전트 스트리밍 → 도구 호출/Cypher/결과 표시 → **pyvis 그래프 시각화** |

실행: `streamlit run app.py`

## 한눈에 보기

```
chat_input ─▶ session_state.messages 에 추가
          ─▶ agent.stream(대화 기록)
                ├─ AIMessage(tool_calls) ─▶ "🔧 도구 호출" Expander
                ├─ ToolMessage ─▶ generate_cypher_query 면 Cypher 코드, execute 면 결과 텍스트
                └─ AIMessage(content) ─▶ 최종 답변 (한 글자씩 표시)
          ─▶ Cypher 가 있었으면: 쿼리를 "노드/관계를 돌려주도록" 고쳐 다시 실행 ─▶ pyvis HTML ─▶ iframe
          ─▶ 답변 + 도구 호출 + 그래프 HTML 을 messages 에 저장 (재실행 때 다시 그리려고)
```

Part 4 의 모든 것이 합쳐진 최종 결과물이다: 도구 에이전트(graphrag_tool_agent) + Streamlit 패턴(streamlit 폴더) + 그래프 시각화.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | 11~13줄 | 옆 폴더의 에이전트를 `sys.path` 로 가져온다 |
| 2 | 203~208줄 | 에이전트를 `session_state` 에 한 번만 만든다 |
| 3 | 241~261줄 | 이전 대화 다시 그리기 (도구 호출, 그래프 HTML 까지) |
| 4 | 264~385줄 | 스트리밍 루프: 메시지 종류별 처리 |
| 5 | `visualize_graph_results` (18) | LLM 이 만든 Cypher 의 RETURN 을 **노드/관계 변수로 바꿔** 다시 실행 → pyvis |

## "왜"

- **도구 호출을 화면에 보여 주는 이유**: 사용자(그리고 데모를 보는 면접관)는 "왜 이런 답이 나왔나"를 궁금해한다. 실행된 Cypher 와 결과를 같이 보여 주면 답변을 검증할 수 있다. GraphRAG 의 장점(설명 가능성)을 화면으로 드러내는 장치.
- **그래프 시각화를 위해 쿼리를 고친다**: 원래 쿼리는 `RETURN c.name AS 회사` 처럼 값만 돌려준다. 그림을 그리려면 노드/관계 객체가 필요해서 `RETURN c, r0, p LIMIT 20` 으로 바꿔 다시 실행한다.
- **pyvis → HTML → base64 iframe**: Streamlit 안에 인터랙티브 그래프를 넣는 우회 방법.
- **답변/도구 호출/그래프를 모두 messages 에 저장**: Streamlit 재실행 모델 때문에, 저장하지 않으면 다음 입력 때 사라진다.

## 생각해 볼 점

1. **`main()` 의 환경변수 검사가 너무 늦다**: Streamlit 은 파일을 위에서부터 실행한다. 에이전트 초기화(206줄)와 대화 처리가 모두 끝난 뒤 마지막에 `main()` 이 불린다. 키가 없으면 검사 전에 이미 초기화에서 실패한다. 검사를 어디로 옮겨야 할까?
2. **대화 기록에서 도구 결과가 빠진다** (275~278줄): 역할과 내용만 넘기므로, 다음 질문에서 에이전트는 이전 Cypher 결과를 모른다. graphrag_tool_agent 의 `main.py` 는 도구 메시지까지 누적했다. 무엇이 더 나을까? (맥락 vs 토큰)
3. **도구 결과를 마지막 도구 호출에 붙인다** (329~330줄): 에이전트가 도구 두 개를 **동시에** 부르면 결과가 엉뚱한 호출에 붙는다. `ToolMessage.tool_call_id` 로 짝을 맞추면?
4. **시각화가 LLM 쿼리를 정규식으로 고쳐 다시 실행한다**: 쿼리가 복잡하면(여러 MATCH, WITH, 집계) 고친 쿼리가 틀리거나 다른 결과를 낸다. 읽기 전용 제한도 없다. 대안: 처음부터 에이전트 도구가 "그림용 경로"도 함께 돌려주게 하기.
5. 에이전트를 `session_state` 에 둔다: 사용자(브라우저 탭)마다 하나씩 만들어진다. `@st.cache_resource` 와 비교하면?
6. "스트리밍 효과"는 완성된 답을 한 글자씩 보여 줄 뿐이다. 진짜 토큰 스트리밍(`stream_mode="messages"`)으로 바꾸면 첫 글자가 나오는 시간이 얼마나 줄어들까?

## 실행 전 체크
- graphrag_tool_agent 가 동작하는 환경(pdf2kg 그래프, 벡터 인덱스) + `pyvis`
- `streamlit run app.py`
