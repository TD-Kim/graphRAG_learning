# 기존 저장소 분석 (Part 0 · Step 1~2)

> 분석 기준: `main` 브랜치 커밋 `8f3e1ef` (2026-11-04, "text2cypher openai -> claude 로 LLM 변경")
> 추적 파일 259개, 학습용 복사본(`learning/`)을 제외한 Python 코드 약 12,700줄.

## 1. 한눈에 보기

이 저장소는 패스트캠퍼스 강의 **"GraphRAG의 모든 것 : Neo4j·지식그래프로 완성하는 Graph 기반 Agent 챗봇"**(`커리큘럼.pdf`)의 실습 코드와, 그 위에 사용자가 만든 복습용 학습 파일(`learning/`)로 구성되어 있다.

- 주제가 **Neo4j / 지식그래프 / GraphRAG / Agent** 에 집중되어 있다.
- 임베딩·LLM 은 전부 **유료 API(OpenAI, 일부 Anthropic)** 를 호출한다. 로컬 모델, PyTorch, Transformer 내부 구현, BM25, Reranker, IR 지표는 **없다.**
- 즉 새 로드맵의 **Part 4(GraphRAG)·Part 6(서비스) 일부**는 이미 "라이브러리 사용" 수준으로 갖춰져 있고, **Part 1·2·3·5 와 "직접 구현" 측면은 거의 비어 있다.**

## 2. 폴더 구조

```
graphRAG_learning/
├── README.md              # 프로젝트 소개 (짧음)
├── LEARNING.md            # 기존 학습 목차 (GUIDE/step1/step2/step3 체계, 데이터 의존 관계)
├── 커리큘럼.pdf            # 강의 커리큘럼 (외부 저작물)
├── common/                # Part1~3 일부 의존성을 모은 공용 uv 프로젝트 (pyproject + uv.lock)
├── part1/                 # 강의 Part1: Neo4j 기초 (Python 드라이버 CRUD)
│   ├── ch2_python_neo4j.py
│   └── learning/ step1_annotated · step2_fill_in · step3_comments_only
├── part2/                 # 강의 Part2: 지식그래프 구축
│   ├── txt2kg/            # 텍스트 → LLM(OpenAI) 추출 → Neo4j  (wiki_bus.txt, wiki_protein.txt)
│   ├── csv2kg/            # 타이타닉 CSV → 노드/관계 CSV → Neo4j 배치 적재
│   ├── pdf2kg/            # PDF(aibrief.pdf) 목차/본문 → Document-TOC-Chunk 그래프 + LLM 스키마 도메인 그래프
│   ├── law2kg/            # 법령 Open API → 법령/조문 그래프 + 해석례 연결
│   ├── retail2kg/         # H&M 구매 이력 대용량 적재 (노트북)
│   └── medical2kg/        # 스키마 JSON + LLM 추출 + 코드 검증 + 관계 누적
├── part3/                 # 강의 Part3: GraphRAG 패턴과 평가 (neo4j-graphrag 라이브러리 중심)
│   ├── vectorsearch/      # OpenAIEmbeddings + Neo4j 벡터 인덱스 + VectorRetriever
│   ├── text2cypher/       # Text2CypherRetriever (최근 LLM 을 Claude 로 변경)
│   ├── reasoning/         # 추론 경로를 따라가는 Text2Cypher
│   ├── vectorcypher/      # VectorCypherRetriever (벡터로 시작 노드 → Cypher 확장, 법령 데이터)
│   ├── vectorcypher_qdrant/ # Qdrant 외부 벡터DB + Neo4j (QdrantNeo4jRetriever)
│   ├── community_search/  # GDS Leiden 커뮤니티 탐지 + 커뮤니티 요약 검색
│   ├── toolsretriever/    # ToolsRetriever: LLM 이 검색 도구 선택
│   ├── evaluation/ragas/  # RAGAS 5개 지표 평가 (LLM 기반 지표)
│   ├── evaluation/neo4j_text2cypher/ # 골든셋, 실행 결과 비교, LLM Judge
│   └── learning/          # Part3 종합 과제 (text2cypher, hybrid_retrieval, evaluation — 주석 골격만)
└── part4/                 # 강의 Part4: Agent / 챗봇
    ├── create_agent/      # LangChain create_agent 노트북
    ├── streamlit/         # Streamlit 기초 + 챗봇 UI
    ├── graphrag_tool_agent/        # LangGraph + neo4j-graphrag 도구 에이전트
    ├── graphrag_text2cypher_agent/ # LangGraph StateGraph Text2Cypher 에이전트 (langgraph dev)
    └── final_chatbot/     # Streamlit + LangGraph + pyvis 최종 GraphRAG 챗봇
```

각 실습 폴더는 거의 모두 **독립 uv 프로젝트**(`pyproject.toml` + `uv.lock`, 다수는 `requirements.txt` 도 병행)이고, `.env.example` 로 `NEO4J_URI`, `OPENAI_API_KEY` 등을 받는다.

## 3. 의존성 현황

| 항목 | 내용 |
|---|---|
| 프로젝트 수 | uv 프로젝트 20개 (`common` 포함), 각자 `uv.lock` 보유 |
| Python 버전 | `uv.lock` 기준 `>=3.14` 13개, `>=3.13` 5개, `>=3.11` 2개 → 사용자의 3.14 환경에 맞춰 잠겨 있음 |
| 핵심 라이브러리 | `neo4j~=5.28`, `neo4j-graphrag` 1.13~1.21 (폴더마다 다름), `openai>=2`, `anthropic`, `langchain>=1`, `langgraph>=1`, `ragas>=0.4`, `streamlit`, `docling`, `PyMuPDF`, `pandas~=3.0`, `qdrant`(extra) |
| 없는 것 | `torch`, `transformers`, `sentence-transformers`, `peft`, `bitsandbytes`, `faiss`, `chromadb`, `rank-bm25`/`bm25s`, `fastapi`, `pytest` |
| 사용 모델 | `gpt-4o`(31회), `gpt-4o-mini`(12), `gpt-4.1`, `text-embedding-3-small`(15), Claude(최근 text2cypher) — **모두 유료 API** |
| 외부 서비스 | Neo4j(AuraDB/Desktop, GDS 플러그인 필요: community_search), Qdrant, 법령 Open API |

## 4. 기존 학습 내용 정리

### 4.1 이미 잘 갖춰진 것
- **Neo4j/Cypher 사용법**: 드라이버 CRUD, `execute_query`, 배치 적재(`UNWIND`), 제약조건/인덱스.
- **KG 구축 파이프라인 6종**: 비정형(txt, pdf) → LLM 추출, 정형(csv, retail) → 규칙 매핑, API(law), 스키마 검증(medical).
- **GraphRAG 검색 패턴 7종**: Vector, Text2Cypher, Reasoning, VectorCypher, Qdrant+Neo4j, Community(Leiden), Tools(라우팅).
- **평가**: RAGAS(LLM 기반: faithfulness, answer relevancy, context precision/recall 등), Text2Cypher 골든셋 실행 평가 + LLM Judge.
- **Agent/UI**: LangChain/LangGraph 에이전트, Streamlit 챗봇.
- **학습 장치**: 폴더별 `GUIDE.md` / step1(주석본) / step2(빈칸) / step3(과제) 3단계 체계. "생각해 볼 점"에 코드 약점까지 기록 → 새 로드맵의 starter/solution 규약과 철학이 같다.

### 4.2 비어 있는 것 (새 로드맵에서 채울 것)
- 토크나이저, 임베딩, Word2Vec, Transformer 를 **직접 구현**하는 내용 전무.
- LLM 학습(loss, optimizer, fine-tuning, LoRA) 전무.
- **Sparse 검색(BM25/Inverted Index), Hybrid fusion, Reranker 전무.** `part3/learning/step3_hybrid_retrieval.py` 의 "하이브리드"는 *벡터 + 그래프 확장*을 뜻하며 BM25 결합이 아니다.
- **IR 지표(Precision@K, Recall@K, HitRate, MRR, NDCG, Latency) 전무.** 평가는 LLM 판정 기반뿐.
- 그래프 탐색 알고리즘(BFS/DFS/최단경로) 직접 구현 없음 — 모두 Cypher/GDS 에 위임.
- 로컬/오픈소스 모델 사용 없음, GPU 사용 없음.
- FastAPI 서버, Spring Boot 연동, Docker, 테스트(pytest) 없음.

## 5. 로드맵 매핑 (기존 vs 추가 필요)

| 새 Part | 기존 저장소에서 가져다 쓸 것 | 추가로 필요한 것 |
|---|---|---|
| **0. 분석·환경** | 기존 uv 환경(변경 금지), `LEARNING.md` | `docs/`, `requirements/`, AI Lab 전용 3.12 환경 |
| **1. AI 기초** | (없음) — `part2/txt2kg/wiki_*.txt` 를 토크나이저·Word2Vec 말뭉치로 재사용 가능 | BPE, Embedding, Word2Vec, PyTorch, Transformer 전부 신규 |
| **2. LLM 학습** | (없음) | Next-token 학습 루프, 소형 LM, instruction tuning, LoRA 원리 신규 |
| **3. RAG 알고리즘** | `part2/pdf2kg`(PDF 로딩·목차/청킹 아이디어, `aibrief.pdf`), `part3/vectorsearch`(Dense 검색의 라이브러리 버전), `part3/evaluation/*`(LLM 기반 평가 비교군), `langchain-text-splitters` | 로더/청킹 직접 구현, numpy·FAISS Dense, BM25·Inverted Index, RRF/Weighted fusion, Cross-Encoder rerank, IR 지표, CSV·시각화, **프레임워크 하이브리드 비교** |
| **4. GraphRAG** | **대부분 존재**: `part2/*2kg`(KG 구축·LLM 추출), `part3/text2cypher`·`reasoning`·`vectorcypher`·`vectorcypher_qdrant`·`community_search`·`toolsretriever`, `part3/evaluation/neo4j_text2cypher` | 중복 구현 금지. **규칙 기반 추출(vs 기존 LLM 추출)**, **Python BFS/DFS/최단경로/멀티홉(vs Cypher·GDS)**, **로컬 LLM 추출(vs OpenAI)**, **Vector RAG vs GraphRAG 멀티홉 정량 평가** |
| **5. Fine-tuning** | (없음) — Part 3 평가셋 재사용 | Embedding(MNRL/Triplet/hard negative), Reranker, LLM LoRA/QLoRA, 학습 전후 비교 |
| **6. AI 서비스** | `part4/streamlit`, `part4/final_chatbot`(UI·LangGraph 흐름 참고), `part4/graphrag_*_agent` | FastAPI `/api/v1/*`, 스트리밍(SSE), Spring Boot(WebClient·DTO·SSE·타임아웃·장애 처리), Docker Compose, RAG vs GraphRAG 비교 화면 |

### 5.1 기존 파일별 배치

| 기존 위치 | 새 로드맵 배치 | 활용 방식 |
|---|---|---|
| `part1/` | Part 4 선수 (Neo4j 기초) | 그대로 유지. Part 4 시작 전 복습 |
| `part2/txt2kg` | Part 4 entity/relation 추출 | "LLM 추출(기존)" 비교군. `wiki_*.txt` 는 Part 1 말뭉치로도 사용 |
| `part2/csv2kg` | Part 4 knowledge_graph | 규칙 기반 매핑 예시. 그래프 탐색 실습용 소형 그래프 |
| `part2/pdf2kg` | Part 3 document_loader·chunking / Part 4 | `aibrief.pdf` 를 Part 3 공통 데이터셋 후보로 사용 |
| `part2/law2kg`, `medical2kg`, `retail2kg` | Part 4 심화 | 멀티홉 질문셋 원천 그래프 |
| `part3/vectorsearch` | Part 3 dense_retrieval | "라이브러리(neo4j-graphrag) 버전" 비교군 |
| `part3/text2cypher`, `reasoning` | Part 4 graph_retrieval | Cypher 기반 검색 비교군 |
| `part3/vectorcypher*` | Part 4 graph_retrieval (Graph+Vector) | 직접 구현한 Graph+Vector 와 비교 |
| `part3/community_search` | Part 4 심화 (GraphRAG global search) | GDS Leiden — 선택 과제 |
| `part3/toolsretriever` | Part 4 / Part 6 라우팅 | 서비스의 "검색 전략 선택" 참고 |
| `part3/evaluation/*` | Part 3·4 evaluation | LLM 기반 평가(RAGAS) vs IR 지표 비교 |
| `part4/*` | Part 6 | Streamlit 은 프로토타입, 최종 UI 는 Spring Boot 앞단 |
| `common/` | 유지 | 기존 Part1~3 공용 환경. 새 AI Lab 환경과 분리 |

## 6. 중복·불필요 코드 및 정리 후보 (삭제하지 않음, 기록만)

| 항목 | 관찰 | 권장 |
|---|---|---|
| 의존성 선언 중복 | 대부분 폴더에 `pyproject.toml` 과 `requirements.txt` 가 함께 있고, `neo4j-graphrag` 버전이 1.13~1.21 로 제각각 | 기존은 유지. 새 Part 는 `requirements/*.txt` + 단일 AI Lab 환경으로 통일 |
| 환경 20개 | 폴더마다 `.venv` 생성 → 디스크·설치 시간 중복 | 기존은 유지. 새 Part 는 공유 환경 1개 |
| `common/` | part1·part2·part3/text2cypher 만 모은 부분 공용 환경 | 유지. 문서에 "기존 트랙 공용 환경"으로 명시 |
| `pdf2kg.py` vs `pdf2kg_2.py` | 같은 문제의 두 접근(목차 기반 vs 스키마 기반) | 유지 (비교 학습 가치 있음) |
| 폴더별 연결 코드 반복 | `create_neo4j_driver`, `create_embedder` 등이 여러 파일에 복붙 | 기존은 유지. 새 Part 는 공통 유틸 모듈로 |
| 유료 API 의존 | OpenAI/Anthropic 키 없으면 Part 3·4 대부분 실행 불가 | 새 Part 4 에서 로컬 LLM(Ollama) / 로컬 임베딩 대체 경로를 비교 과제로 |
| `part3/learning/step3_hybrid_retrieval.py` | "hybrid" 용어가 vector+graph 확장 의미 | 새 Part 3 의 BM25+Dense hybrid 와 혼동 주의 — ARCHITECTURE 용어집에 명시 |
| `커리큘럼.pdf`, 강의 원본 코드 | 외부 강의 저작물 | 포트폴리오로 **공개**할 때는 저장소 공개 범위와 강의 저작권을 확인. 새 Part 코드는 직접 작성분만 포함 |
| 샘플 CSV(`*(sample).csv`, `text2cypher_gpt4o.csv`) | 평가 결과 샘플 | 유지. 새 실험 결과는 `experiments/` 로 |

## 7. 결론

1. 기존 `part1`~`part4` 는 **"GraphRAG 강의 트랙"** 으로 그대로 보존한다.
2. 새 로드맵은 `part1_ai_fundamentals` ~ `part6_ai_service` 라는 **다른 이름의 최상위 폴더**로 추가해 충돌을 피한다. (이유와 대안: [ARCHITECTURE.md §2](ARCHITECTURE.md#2-명칭-충돌-해결-기존-partn-vs-신규-partn_xxx))
3. 새 Part 4 는 기존 `part2`·`part3` 를 **참조하는 비교 실험**으로 구성하고, 같은 기능을 다시 만들지 않는다.
4. 새 Part 는 기존 3.14 환경과 분리된 **Python 3.12 AI Lab 환경**에서 진행한다. ([ENVIRONMENT.md](ENVIRONMENT.md))
