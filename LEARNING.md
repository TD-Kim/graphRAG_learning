# 학습 목차

강의 실습 코드(각 폴더)는 그대로 두고, 폴더마다 `learning/` 에 복습용 파일을 두었습니다.

## 학습 파일 종류

| 파일 | 하는 일 |
|---|---|
| `GUIDE.md` | 원본 코드를 옆에 열고 읽는 안내서: 한눈에 보기, 읽는 순서, 함수별 "왜", **생각해 볼 점**(실제 코드의 약점 포함) |
| `step1_*annotated.py` | 원본과 코드는 같고 주석만 단 복사본. Part 2 는 파이썬 문법과 함수의 **[출처] [입력] [반환] [왜]** 까지 적었다 (part1, Part 2 전체) |
| `step2_*.py` | 핵심 함수만 TODO 로 비워 둔 빈칸 채우기. 원본이 정답 |
| `step3_comments_only.py` | 할 일 목록만 있는 과제. 대부분 **다른 데이터나 도메인에 같은 패턴을 적용**하는 과제 |

**권장 순서**: GUIDE 읽기 → step1 주석본 읽기 → 원본 실행 → step2 → step3. GUIDE 의 "생각해 볼 점"은 면접 질문 연습으로도 좋습니다.

## Part 1. GraphDB 와 Neo4j 기초

| 폴더 | 학습 파일 |
|---|---|
| `part1/` | [step1](part1/learning/step1_annotated.py) · [step2](part1/learning/step2_fill_in.py) · [step3](part1/learning/step3_comments_only.py) |

## Part 2. 지식그래프 구축

| 순서 | 폴더 | 주제 | 가이드 |
|---|---|---|---|
| 1 | `part2/txt2kg` | 텍스트 → LLM 추출 → 그래프 | [GUIDE](part2/txt2kg/learning/GUIDE.md) · [step1](part2/txt2kg/learning/step1_annotated.py) |
| 2 | `part2/csv2kg` | CSV → 그래프 (배치 적재) | [step1](part2/csv2kg/learning/step1_annotated.py) |
| 3 | `part2/pdf2kg` | PDF 목차/본문 구조 + LLM 스키마 기반 도메인 그래프 | [GUIDE](part2/pdf2kg/learning/GUIDE.md) · step1: [toc_extract](part2/pdf2kg/learning/step1_annotated.py), [pdf2kg](part2/pdf2kg/learning/step1_pdf2kg_annotated.py), [pdf2kg_2](part2/pdf2kg/learning/step1_pdf2kg_2_annotated.py) |
| 4 | `part2/law2kg` | 법령 Open API + 해석례 연결 | [GUIDE](part2/law2kg/learning/GUIDE.md) · step1: [law_api](part2/law2kg/learning/step1_law_api_annotated.py), [law2kg](part2/law2kg/learning/step1_law2kg_annotated.py), [load_laws](part2/law2kg/learning/step1_load_laws_annotated.py), [link_interpretations](part2/law2kg/learning/step1_link_interpretations_annotated.py) |
| 5 | `part2/retail2kg` | 대용량 구매 이력 적재 | [GUIDE](part2/retail2kg/learning/GUIDE.md) · [step1](part2/retail2kg/learning/step1_annotated.py) |
| 6 | `part2/medical2kg` | 스키마 JSON + 코드 검증 + 관계 누적 | [GUIDE](part2/medical2kg/learning/GUIDE.md) · [step1](part2/medical2kg/learning/step1_annotated.py) |

## Part 3. GraphRAG 핵심 패턴과 평가

[Part 3 안내](part3/learning/README.md) (순서표 + 종합 과제)

| 순서 | 폴더 | 가이드 |
|---|---|---|
| 1 | `part3/vectorsearch` | [GUIDE](part3/vectorsearch/learning/GUIDE.md) |
| 2 | `part3/text2cypher` | [GUIDE](part3/text2cypher/learning/GUIDE.md) |
| 3 | `part3/reasoning` | [GUIDE](part3/reasoning/learning/GUIDE.md) |
| 4 | `part3/vectorcypher` | [GUIDE](part3/vectorcypher/learning/GUIDE.md) |
| 5 | `part3/vectorcypher_qdrant` | [GUIDE](part3/vectorcypher_qdrant/learning/GUIDE.md) |
| 6 | `part3/community_search` | [GUIDE](part3/community_search/learning/GUIDE.md) |
| 7 | `part3/toolsretriever` | [GUIDE](part3/toolsretriever/learning/GUIDE.md) |
| 8 | `part3/evaluation/ragas` | [GUIDE](part3/evaluation/ragas/learning/GUIDE.md) |
| 9 | `part3/evaluation/neo4j_text2cypher` | [GUIDE](part3/evaluation/neo4j_text2cypher/learning/GUIDE.md) |

## Part 4. GraphRAG 에이전트와 챗봇

| 순서 | 폴더 | 가이드 |
|---|---|---|
| 1 | `part4/create_agent` | [GUIDE](part4/create_agent/learning/GUIDE.md) |
| 2 | `part4/streamlit` | [GUIDE](part4/streamlit/learning/GUIDE.md) |
| 3 | `part4/graphrag_tool_agent` | [GUIDE](part4/graphrag_tool_agent/learning/GUIDE.md) |
| 4 | `part4/graphrag_text2cypher_agent` | [GUIDE](part4/graphrag_text2cypher_agent/learning/GUIDE.md) |
| 5 | `part4/final_chatbot` | [GUIDE](part4/final_chatbot/learning/GUIDE.md) |

## 데이터 의존 관계

```
part2/csv2kg (타이타닉) ──▶ part3/text2cypher
part2/pdf2kg (+pdf2kg_2) ─▶ part3/vectorsearch ─▶ part3/vectorcypher_qdrant, toolsretriever ─▶ part4/graphrag_tool_agent ─▶ final_chatbot
part2/law2kg ────────────▶ part3/vectorcypher
part2/medical2kg ────────▶ part3/reasoning, part4/graphrag_text2cypher_agent
part2/retail2kg ─────────▶ part3/community_search
(외부) Recommendations ───▶ part3/evaluation/*
```

각 스크립트는 대부분 **DB 를 지우고 시작**합니다. 여러 실습을 오갈 때는 GUIDE 의 "실행 전 체크"를 먼저 보세요.

## 주의
- API 키, DB 비밀번호는 `.env` 에만 두고 README, 노트북 출력, 커밋에 남기지 않습니다.
- step2/step3 은 문법 검사만 했고, 실제 실행은 각자의 환경(Neo4j, API 키)에서 확인해야 합니다.
