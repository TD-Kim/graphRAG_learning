# AI Engineering Learning Lab — 프로젝트 기획서

> 이 문서는 사용자가 작성한 기획서를 요약·정리한 것입니다. 세부 실행 계획은 [LEARNING_ROADMAP.md](LEARNING_ROADMAP.md), 구조와 규약은 [ARCHITECTURE.md](ARCHITECTURE.md), 환경은 [ENVIRONMENT.md](ENVIRONMENT.md), 진행 상황은 [PROGRESS.md](PROGRESS.md) 를 봅니다.

## 1. 목적

기존 `graphRAG_learning` 저장소의 학습 자료와 코드를 기반으로 **AI 엔지니어링 전반을 실습형으로** 학습한다.

- 라이브러리를 **사용하는 법**과 그 **내부 원리를 직접 구현**하는 것을 동시에 익힌다.
- 결과물은 Java/Spring Boot 경력과 연결되는 **포트폴리오**로 남긴다.

## 2. 사용자 환경

| 항목 | 값 |
|---|---|
| OS | Windows |
| GPU | NVIDIA RTX 3070 (8GB VRAM, Ampere, sm_86) |
| RAM | 32GB |
| 기존 경로 | `C:\gitRepo\graphRAG_learning\part1` |
| 기존 가상환경 | `part1\.venv` (Python 3.14.7) |
| 패키지 관리 | uv |

**원칙**
- 기존 환경(`part1\.venv` 및 각 실습 폴더의 uv 환경)은 **변경하지 않는다.**
- Python 3.14 와 PyTorch / Transformers / PEFT / bitsandbytes / FAISS 등의 호환성을 확인하고, 필요하면 **별도 3.11/3.12 uv 환경**을 쓴다. (결론: [ENVIRONMENT.md](ENVIRONMENT.md) — AI Lab 전용 3.12 환경 권장)

## 3. 기술 후보 (필요한 단계에서만 도입)

PyTorch, Hugging Face Transformers, Sentence Transformers, PEFT(LoRA/QLoRA), FAISS, ChromaDB, Neo4j, FastAPI, Spring Boot, Docker

- **유료 API 를 전제로 하지 않는다.** 무료 오픈소스·로컬 모델 우선.
- 모델과 데이터셋은 **라이선스를 확인**하고 기록한다.

## 4. 로드맵 (7단계)

| Part | 주제 | 핵심 내용 | 산출물 / 완료 조건 |
|---|---|---|---|
| 0 | 저장소 분석 & 환경 | 기존 코드 분석, 로드맵 매핑, 환경 호환성 | 학습 환경, 이 문서들 |
| 1 | AI/딥러닝 내부 원리 | Tokenizer/BPE, Embedding, Word2Vec(CBOW·Skip-gram·Negative Sampling), PyTorch 기초, Transformer(Self-Attention·MHA·FFN·Residual·LayerNorm·Positional Encoding) | 직접 구현한 작은 Transformer |
| 2 | LLM 학습 원리 | Next token prediction, CE loss, backprop, GD, optimizer, overfitting, pre-training vs fine-tuning, instruction tuning, LoRA/QLoRA | 소형 언어 모델 |
| 3 | RAG 내부 알고리즘 | 로딩, 청킹, 임베딩, Dense(FAISS), BM25/Inverted Index, Hybrid(RRF·Weighted fusion), Reranking(Cross-Encoder), 평가(Precision·Recall·HitRate@K·MRR·NDCG·Latency), CSV 저장·시각화 | **동일 데이터셋에서 BM25 vs Dense vs Hybrid vs Hybrid+Rerank 수치 비교** |
| 4 | GraphRAG 내부 원리 | KG, Entity/Relation 추출(규칙 vs LLM), BFS/DFS/최단경로/멀티홉, Neo4j Cypher 비교, Graph+Vector 검색, Vector RAG vs GraphRAG 멀티홉 평가 | 기존 구현은 중복 구현하지 않고 **"직접 구현 vs 기존 라이브러리 구현" 비교**로 확장 |
| 5 | Fine-tuning | Embedding(MNRL/Triplet/hard negative), Reranker, LLM LoRA | 학습 전후 동일 테스트셋 비교, **개선을 가정하지 않음**, GPU 메모리/시간 측정 |
| 6 | AI 서비스 | FastAPI(`/api/v1/documents`, `embeddings`, `search`, `rag/query`, `graphrag/query`, `health`, 스트리밍), Spring Boot(WebClient, DTO, SSE, 예외·타임아웃·로깅, 장애 처리) | 사용자 → Spring Boot → Python AI Server → RAG/GraphRAG → VectorDB/Neo4j → LLM. **RAG vs GraphRAG 결과를 비교하는 웹 서비스**. 처음엔 REST, gRPC 는 확장 과제 |

## 5. 사용자가 특히 강조한 3가지

### 5.1 Hybrid Search 는 직접 구현하고 실제 프레임워크와 비교한다
- BM25, Dense, RRF, Weighted fusion 을 직접 구현한다.
- LangChain `EnsembleRetriever`, LlamaIndex `QueryFusionRetriever`, Haystack(`DocumentJoiner`) 등의 구현과 **같은 데이터·같은 질문**으로 비교한다. (기존 저장소의 `neo4j-graphrag` `HybridRetriever` 도 비교 대상)
- 목표: 라이브러리 사용 능력과 내부 원리 이해를 동시에 확보.
- 계획: [LEARNING_ROADMAP.md §5](LEARNING_ROADMAP.md#5-hybrid-search-직접-구현-vs-프레임워크-비교-계획)

### 5.2 RTX 3070 으로 가능한 학습과 불가능한 학습을 구분한다
- **LLM 을 처음부터 사전학습하는 것은 목표에서 제외.**
- 작은 Transformer 는 직접 학습, 실제 LLM 은 사전학습 모델 + LoRA/QLoRA.
- 모델 크기별(0.5B/1.5B/3B/7B 등) 추론·LoRA·QLoRA 가능 여부와 예상 VRAM 표: [LEARNING_ROADMAP.md §4](LEARNING_ROADMAP.md#4-rtx-3070-8gb-로-가능한-학습--불가능한-학습), [ENVIRONMENT.md §5](ENVIRONMENT.md#5-모델-추천과-vram-추정)

### 5.3 최종 결과물은 Java/Spring Boot 경력과 연결한다
- Spring Boot 가 Python AI 서버를 호출하는 구조로 마무리.
- 진행 과정 자체를 포트폴리오로 관리: [PROGRESS.md](PROGRESS.md), [`experiments/`](../experiments/README.md)
- 매주 학습 진도/구현 결과를 로드맵 기준으로 점검: [LEARNING_ROADMAP.md §3 주차별 계획](LEARNING_ROADMAP.md#3-주차별-계획), [PROGRESS.md 주간 점검 템플릿](PROGRESS.md#주간-점검-템플릿)

## 6. 학습 코드 규칙 (Part 1 이후 적용)

자세한 규약은 [ARCHITECTURE.md §4](ARCHITECTURE.md#4-실습-코드-규약-starter--solution--test).

- 각 실습의 흐름: **개념 → 수학 원리 → 데이터 흐름 → 코드 구조 → 구현할 부분 → 실행법 → 예상 출력 → 결과 해석 → 과제 → 정답**
- `starter.py`(TODO) / `solution.py`(완성) 분리
- 가능하면 pytest 테스트: solution 기준 통과, starter 는 학습자가 채우면 통과
- 난이도 Level 1 / 2 / 3
- 각 디렉터리 README 12개 항목: 목표, 선수지식, 핵심 개념, 내부 원리, 수식/그림, 실행법, TODO 목록, 예상 결과, 자주 나는 오류, 과제, 체크리스트, 다음 단계 연결
- `experiments/` 에 실험 기록: 목적, 데이터셋, 모델, 하이퍼파라미터, GPU 사용량, 학습시간, 결과, 비교, 개선점
- `PROGRESS.md` 상태값: `NOT_STARTED` / `IN_PROGRESS` / `COMPLETED` / `NEEDS_REVIEW` — **사용자가 직접 확인한 것만 `COMPLETED`**

## 7. 목표 디렉터리 (기존 구조와 충돌 시 기존 우선)

```
docs/
part1_ai_fundamentals/{tokenizer,embedding,word2vec,pytorch,transformer}
part2_llm/...
part3_rag/{document_loader,chunking,dense_retrieval,sparse_retrieval,hybrid_search,reranking,evaluation}
part4_graphrag/{knowledge_graph,entity_extraction,relationship_extraction,graph_traversal,graph_retrieval,evaluation}
part5_finetuning/{embedding,reranker,llm_lora}
part6_ai_service/{python_ai_server,spring_boot_server}
datasets/  experiments/  tests/  requirements/  README.md
```

기존 `part1` ~ `part4` 폴더와의 명칭 충돌·통합 방안은 [ARCHITECTURE.md §2](ARCHITECTURE.md#2-명칭-충돌-해결-기존-partn-vs-신규-partn_xxx) 에서 결정했다.

## 8. Part 0 수행 단계 (기획서 10장)

1. 저장소 분석 → [REPOSITORY_ANALYSIS.md](REPOSITORY_ANALYSIS.md)
2. 로드맵 매핑 → [REPOSITORY_ANALYSIS.md §5](REPOSITORY_ANALYSIS.md#5-로드맵-매핑-기존-vs-추가-필요)
3. 최종 구조 설계 → [ARCHITECTURE.md](ARCHITECTURE.md)
4. 환경 호환성 검증 → [ENVIRONMENT.md](ENVIRONMENT.md)
5. 산출물 작성·커밋 → 이 `docs/` 폴더와 [`requirements/`](../requirements/README.md)
