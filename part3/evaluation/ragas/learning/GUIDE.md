# evaluation/ragas 읽기 가이드

강의: Part 3 / CH02-01 RAG 평가 기준 이해하기, CH02-02 RAGAS 로 GraphRAG 평가하기
데이터: Neo4j Sandbox **Recommendations**(영화) 데이터셋

| 파일 | 역할 |
|---|---|
| [`graphrag_ragas_evaluation.ipynb`](../graphrag_ragas_evaluation.ipynb) | 지표 5개 맛보기 → Text2Cypher GraphRAG 구성 → 정답 만들기 → 실행 → RAGAS 평가 → 분석 |
| `graph_rag_results(sample).csv` | 질문 10개의 답변, 컨텍스트, 정답, Cypher (평가 입력) |
| `graph_rag_evaluation_results_...(sample).csv` | 위 입력의 RAGAS 점수 (평가 출력) |

두 샘플 CSV 가 있어서 **Neo4j 없이도** 평가 단계만 다시 돌려 볼 수 있다.

## 한눈에 보기

```
질문 10개 + 정답 Cypher 10개 ─실행─▶ 정답 텍스트(ground_truth)
질문 10개 ─GraphRAG(Text2Cypher)─▶ 답변 + 컨텍스트(실행된 Cypher + 결과를 텍스트로)
                                              │
            RAGAS(LLM 이 채점) ◀───────────────┘
   Faithfulness / Answer Relevancy / Context Recall / Context Precision / Answer Accuracy
```

## 지표 5개를 "무엇을 보느냐"로 나누면

| 지표 | 보는 것 | 필요한 입력 | 낮으면 의심할 곳 |
|---|---|---|---|
| Faithfulness | 답변이 **컨텍스트에 근거**하는가 (환각) | 질문, 답변, 컨텍스트 | 답변 생성 프롬프트 |
| Answer Relevancy | 답변이 **질문에 맞는** 내용인가 | 질문, 답변 | 답변 생성 |
| Context Recall | 정답을 뒷받침할 내용이 **컨텍스트에 다 있나** | 질문, 컨텍스트, 정답 | **검색**(Cypher 가 덜 가져옴) |
| Context Precision | 가져온 컨텍스트가 **쓸모 있는 것 위주인가** | 질문, 컨텍스트, 정답 | **검색**(쓸데없이 많이 가져옴) |
| Answer Accuracy | 답변이 **정답과 일치**하나 | 질문, 답변, 정답 | 전체 |

검색 문제인지 생성 문제인지를 나눠 볼 수 있다는 게 지표를 여러 개 쓰는 이유다.

## 읽는 순서

| 셀 | 핵심 |
|---|---|
| 5~13 | 지표 5개를 아주 작은 예시로 하나씩. 점수가 왜 그렇게 나오는지 감 잡기 |
| 16, 18 | DB 에서 스키마 자동 추출 |
| 20~21 | Text2Cypher GraphRAG + **커스텀 프롬프트**("Matrix, The" 같은 제목 표기 문제를 CONTAINS 로) |
| 24~26 | 정답 만들기: **정답 Cypher 를 실행한 결과**를 문장으로 (`format_gt_result`) |
| 28 | `convert_graph_context_to_text`: 그래프 결과(구조화 데이터)를 RAGAS 가 읽을 텍스트로 |
| 29 | 질문마다 실행해 답변, 컨텍스트, 정답, Cypher 수집 |
| 34~36 | `SingleTurnSample` 로 감싸고 지표별로 필요한 입력만 넘겨 비동기 평가 |
| 40~41 | 평균과 가장 낮은 질문 3개 |

## "왜"

- **GraphRAG 는 컨텍스트 변환이 필요하다**: 벡터 RAG 의 컨텍스트는 이미 문장이지만, GraphRAG 는 Cypher 결과(행)다. RAGAS 는 텍스트를 읽으므로 "실행한 쿼리 + 결과 행"을 글로 바꿔 준다.
- **정답을 DB 쿼리로 만든다**: 사람이 정답 문장을 일일이 쓰는 대신, 정답 Cypher 결과로 만든다. 데이터가 바뀌어도 정답이 자동으로 갱신된다.
- **지표별로 필요한 입력만 넘긴다 (셀 36)**: 지표마다 요구하는 필드가 다르다. 위 표와 같이 보면 이해가 쉽다.
- **평가 LLM 은 답변 LLM 과 같은 gpt-4o**: (생각해 볼 점 3)

## 생각해 볼 점

1. **컨텍스트가 하나뿐이다**: `"contexts": [context_text]` 처럼 전체를 문자열 하나로 넣는다. Context Precision 은 "여러 컨텍스트 중 관련 있는 것이 위에 있나"를 보는 지표인데, 항목이 하나면 의미가 약해진다. 결과 행마다 하나의 컨텍스트로 나누면 어떻게 달라질까?
2. **샘플 결과의 톰 행크스 질문**: 답변은 43편, 정답은 38편이다. 정답 쿼리는 `CONTAINS 'Tom Hanks'`, 생성 쿼리는 무엇이었을지 `graph_rag_results(sample).csv` 의 cypher 열에서 확인해 보자. 같은 샘플의 faithfulness 0.0 은 왜일까? contexts 열을 직접 읽고 판단해 보자.
3. **같은 계열 모델이 만들고 채점한다**. 채점 모델을 바꾸거나, 같은 평가를 3번 돌려 점수가 얼마나 흔들리는지 재 보자.
4. **질문 10개**로 평균을 내면 질문 하나가 평균을 10% 움직인다. 결론을 내리기 전에 질문 수를 늘리자.
5. 정답 문장이 "Matrix Reloaded, The - Andy Arness; …" 처럼 긴 목록이면 답변이 일부만 말해도 Accuracy 가 낮게 나온다. 정답의 "형식"이 점수에 주는 영향은?

## 실행 전 체크
- Neo4j Sandbox Recommendations (또는 같은 데이터) 접속 정보, `OPENAI_API_KEY`
- 노트북은 `await` 를 셀에서 바로 쓴다(Jupyter 전용). 스크립트로 옮길 때는 `asyncio.run(...)`
- 평가만 다시 해 보려면 `learning/step2_fill_in.py` (샘플 CSV 사용)
