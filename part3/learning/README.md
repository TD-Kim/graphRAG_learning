# Part 3 종합 과제 (GraphRAG 핵심 패턴과 평가)

Part 3 의 각 실습 폴더에는 `learning/` (GUIDE.md, step2, step3) 가 있습니다. 먼저 그쪽을 순서대로 하세요.
이 폴더의 파일 3개는 **Part 3 을 다 끝낸 뒤, 원본을 보지 않고 처음부터** 해 보는 종합 과제입니다.

## 실습 폴더 순서

| 순서 | 폴더 | 강의 | 핵심 |
|---|---|---|---|
| 1 | [`vectorsearch/`](../vectorsearch/learning/GUIDE.md) | CH01-05 | 임베딩, 벡터 인덱스, 의미 검색 |
| 2 | [`text2cypher/`](../text2cypher/learning/GUIDE.md) | CH01-01, 02 | 질문 → Cypher → 실행 → 답변 |
| 3 | [`reasoning/`](../reasoning/learning/GUIDE.md) | CH01-03, 04 | 추론 경로를 따라가는 Text2Cypher |
| 4 | [`vectorcypher/`](../vectorcypher/learning/GUIDE.md) | CH01-06 | 벡터로 시작 노드, Cypher 로 주변 |
| 5 | [`vectorcypher_qdrant/`](../vectorcypher_qdrant/learning/GUIDE.md) | CH01-07 | 외부 벡터 DB + 그래프 |
| 6 | [`community_search/`](../community_search/learning/GUIDE.md) | CH01-08 | GDS Leiden 커뮤니티 |
| 7 | [`toolsretriever/`](../toolsretriever/learning/GUIDE.md) | CH01-09 | 검색 방식을 LLM 이 골라 쓰기 |
| 8 | [`evaluation/ragas/`](../evaluation/ragas/learning/GUIDE.md) | CH02-01, 02 | RAGAS 5개 지표 |
| 9 | [`evaluation/neo4j_text2cypher/`](../evaluation/neo4j_text2cypher/learning/GUIDE.md) | CH02-03 | 골든셋, 실행 평가, LLM Judge |

## 종합 과제

| 파일 | 하는 일 |
|---|---|
| `step3_text2cypher.py` | 새 그래프에 Text2Cypher 를 붙이고 안전장치까지 |
| `step3_hybrid_retrieval.py` | 임베딩 단위를 바꿔 가며 벡터 + 그래프 확장 비교 |
| `step3_evaluation.py` | 직접 만든 평가셋으로 여러 방식 비교 |

## 주의
- 라이브러리 API(`neo4j-graphrag`, `ragas` 등)는 버전에 따라 바뀌므로, 코드를 쓰기 전에 설치된 버전의 공식 문서를 먼저 확인한다.
- **API 키는 `.env` 에만 둔다.** README, 노트북 출력, 커밋에 남기지 않는다.
