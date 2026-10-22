# evaluation/neo4j_text2cypher 읽기 가이드

강의: Part 3 / CH02-01 RAG 평가 기준 이해하기, CH02-03 GraphRAG 평가 데이터셋 활용하여 평가하기
데이터: Neo4j Labs 의 Text2Cypher 골든 데이터셋(`text2cypher_gpt4o.csv`) 중 `recommendations` DB 질문 792개

| 파일 | 줄 | 역할 |
|---|---|---|
| [`retriever.py`](../retriever.py) | 77 | Text2CypherRetriever 생성, `get_search_results` 로 생성+실행 |
| [`eval.py`](../eval.py) | 518 | 골든셋 로드 → 생성/실행 → **실행 평가** + **관계 방향 검사** + **LLM-as-a-Judge** → 요약/문제 목록/CSV |
| `text2cypher_gpt4o.csv` | | 질문, 정답 Cypher, 유형, DB, 정답이 결과를 내는지 등 |
| `text2cypher_schemas.csv` | | DB 별 스키마 텍스트 |
| `eval_results(sample).csv` | | 결과 예시 |

## 한눈에 보기

```
골든셋(질문, 정답 Cypher) ─▶ 내 Text2Cypher 로 생성 ─▶ 실행
     │                                                   │
     │      ┌─ Execution: 실행됨? 결과 있음? 관계 방향 맞음? (규칙, 0~1)
     └──────┤
            └─ LLM Judge: 정답 Cypher 와 비교해 의도/완전성/정확성 1~5 (LLM 이 채점)
                         ─▶ 요약표, 문제 항목 상세, CSV
```

"좋아졌다"를 숫자로 말하기 위한 실습이다. 앞의 text2cypher, reasoning 에서 프롬프트나 예시를 바꿨을 때 **이 점수가 오르는지**로 판단한다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | `main` (457) | 인자: `--limit`(처음엔 10), `--dataset-db` |
| 2 | `evaluate_single` (255) | 한 질문의 평가 전체 흐름 |
| 3 | `generate_and_execute_cypher` (retriever.py 43) | 예외를 잡아 "실행 실패"로 기록 |
| 4 | `extract_relationships_from_cypher`, `check_relationship_directions` (89, 116) | 정규식으로 `(:A)-[:R]->(:B)` 를 뽑아 허용 목록과 비교 |
| 5 | `LLM_JUDGE_*_PROMPT`, `llm_judge_evaluate` (143~248) | 채점 기준표(루브릭) + JSON 파싱 방어 |
| 6 | `print_summary`, `print_issues` (313, 361) | **유형별** 평균, 문제 항목만 정답/생성 쿼리를 나란히 |

## "왜"

- **규칙 평가 + LLM 평가를 함께**: 규칙(실행 여부, 방향)은 싸고 확실하지만 "의도에 맞나"는 못 본다. LLM 채점은 의도를 보지만 흔들린다. 둘을 같이 봐야 한다.
- **루브릭에 점수별 기준을 적는 이유**: "1~5 로 채점"만 주면 LLM 마다, 실행마다 기준이 달라진다. 5/4/3/2/1 의 뜻을 적어 두면 일관성이 오른다.
- **정답 쿼리 결과 유무도 Judge 에 준다**: 정답도 빈 결과인 질문이면 생성 쿼리가 빈 결과여도 잘못이 아니다.
- **유형별 통계**: 전체 평균만 보면 "집계 질문에 약하다" 같은 패턴을 놓친다.
- **문제 항목만 상세 출력**: 사람이 실제로 읽고 원인을 찾는 단계가 평가의 진짜 가치다.

## 생각해 볼 점

1. **결과가 "맞는지"는 보지 않는다**: 실행 평가는 "결과가 있나"만 본다. 엉뚱한 쿼리도 결과는 나온다. 정답 Cypher 도 실행해서 **결과 집합을 비교**(실행 정확도, execution accuracy)하면 훨씬 강한 지표가 된다. → `step2_fill_in.py`
2. **같은 모델이 만들고 같은 모델이 채점한다** (둘 다 gpt-4o). 자기 답에 후한 편향이 생길 수 있다. 채점 모델을 바꾸면 점수가 달라질까?
3. **정규식 방향 검사의 한계**: `(a:Actor)-[:ACTED_IN]->(m:Movie)<-[:DIRECTED]-(d:Director)` 처럼 노드를 공유하는 연쇄 패턴은 `finditer` 가 겹치지 않게 찾기 때문에 두 번째 관계를 놓친다. 방향 없는 패턴 `-[:R]-` 도 검사하지 않는다.
4. **`--neo4j-db` 인자를 받지만 쓰지 않는다**: Retriever 는 드라이버 기본 DB 로 실행한다.
5. `VALID_RELATIONSHIPS` 가 recommendations DB 에 고정돼 있다. 다른 DB(`--dataset-db northwind`)로 바꾸면 방향 검사가 모두 "스키마에 없는 관계"가 된다. 스키마 CSV 의 `structured_schema` 에서 자동으로 만들 수 있을까?
6. 792개 전부 돌리면 LLM 호출이 1,600번(생성+채점)이다. 대표 샘플을 어떻게 뽑을까? (유형별 층화 추출)

## 실행 전 체크
- recommendations 데이터가 있는 Neo4j (Neo4j 데모 DB 또는 직접 적재). `.env` 의 `DATABASE_NAME=recommendations`
- `python eval.py --limit 10` 으로 작게 시작
