# 진행 상황 (PROGRESS)

> 실습 목록과 주차는 [LEARNING_ROADMAP.md](LEARNING_ROADMAP.md) 와 같다. 로드맵을 바꾸면 이 표도 함께 고친다.

## 상태값 규칙

| 상태 | 의미 | 누가 바꾸나 |
|---|---|---|
| `NOT_STARTED` | 시작 전 | — |
| `IN_PROGRESS` | 진행 중 | 학습자 / Claude |
| `NEEDS_REVIEW` | 구현·실행은 끝났고 사용자 확인 대기 (테스트 통과, 실험 기록 작성) | 학습자 / Claude |
| `COMPLETED` | **사용자가 직접 확인한 것만.** 확인일을 적는다 | **사용자만** |

- Claude 는 작업을 끝내도 `NEEDS_REVIEW` 까지만 바꾼다.
- `COMPLETED` 기준: ① solution 테스트 통과 ② 학습자가 starter 를 직접 채워 테스트 통과(또는 README 체크리스트 완료) ③ 실험이 있는 실습은 `experiments/` 기록 링크 존재.

## 요약

| Part | 실습 수 | COMPLETED | NEEDS_REVIEW | IN_PROGRESS | 마일스톤 |
|---|---|---|---|---|---|
| 0. 분석·환경 | 3 | 0 | 0 | 0 | — |
| 1. AI 기초 | 13 | 0 | 0 | 0 | P1-13 미니 GPT |
| 2. LLM 학습 | 10 | 0 | 0 | 0 | P2-05 소형 LM |
| 3. RAG | 14 | 0 | 0 | 0 | P3-12 4방식 비교 |
| 4. GraphRAG | 10 | 0 | 0 | 0 | P4-10 Vector vs Graph |
| 5. Fine-tuning | 7 | 0 | 0 | 0 | P5-07 전후 비교 |
| 6. AI 서비스 | 12 | 0 | 0 | 0 | P6-10 비교 웹 |

> Part 0 의 문서 산출물(`docs/*`, `requirements/*`)은 작성되었지만, 사용자 확인 전이므로 P0-01 도 `NOT_STARTED` 로 둔다. 검토를 시작하면 `IN_PROGRESS` 로 바꾼다.

## 실습별 상태

### Part 0. 저장소 분석 & 환경 (1주)

| ID | 주차 | 폴더 | 실습 | 난이도 | 상태 | 확인일 | 메모·실험 링크 |
|---|---|---|---|---|---|---|---|
| P0-01 | W1 | — | 기존 저장소 분석 문서 검토 | L1 | NOT_STARTED | | |
| P0-02 | W1 | — | AI Lab 전용 uv 환경(Python 3.12) 구축, `torch.cuda.is_available()` 확인 | L1 | NOT_STARTED | | |
| P0-03 | W1 | — | Neo4j(Desktop/Docker), Ollama 로컬 설치 확인 | L1 | NOT_STARTED | | |

### Part 1. AI/딥러닝 내부 원리 (`part1_ai_fundamentals/`, 5주)

| ID | 주차 | 폴더 | 실습 | 난이도 | 상태 | 확인일 | 메모·실험 링크 |
|---|---|---|---|---|---|---|---|
| P1-01 | W2 | tokenizer | 문자·단어 토크나이저, vocab, encode/decode | L1 | NOT_STARTED | | |
| P1-02 | W2 | tokenizer | BPE 학습·인코딩·디코딩 직접 구현 | L2 | NOT_STARTED | | |
| P1-03 | W3 | embedding | one-hot vs embedding lookup, 코사인 유사도, 차원의 의미 | L1 | NOT_STARTED | | |
| P1-04 | W3 | word2vec | Skip-gram (full softmax, NumPy) | L2 | NOT_STARTED | | |
| P1-05 | W3 | word2vec | CBOW | L2 | NOT_STARTED | | |
| P1-06 | W4 | word2vec | Negative Sampling + subsampling, 유사 단어·유추 평가 | L3 | NOT_STARTED | | |
| P1-07 | W4 | pytorch | Tensor, autograd, `nn.Module`, 학습 루프, GPU 이동 | L1 | NOT_STARTED | | |
| P1-08 | W4 | pytorch | Word2Vec 을 PyTorch 로 재구현, CPU vs GPU 시간 측정 | L2 | NOT_STARTED | | |
| P1-09 | W5 | transformer | Scaled dot-product attention + causal/padding mask | L2 | NOT_STARTED | | |
| P1-10 | W5 | transformer | Multi-Head Attention | L2 | NOT_STARTED | | |
| P1-11 | W5 | transformer | Positional Encoding (sinusoidal, 선택: learned/RoPE) | L2 | NOT_STARTED | | |
| P1-12 | W6 | transformer | FFN + Residual + LayerNorm (Pre-LN) 블록 | L2 | NOT_STARTED | | |
| P1-13 ★ | W6 | transformer | 미니 GPT 조립 + 문자 단위 언어모델 학습 (≈1~10M 파라미터) | L3 | NOT_STARTED | | |

### Part 2. LLM 학습 원리 (`part2_llm/`, 4주)

| ID | 주차 | 폴더 | 실습 | 난이도 | 상태 | 확인일 | 메모·실험 링크 |
|---|---|---|---|---|---|---|---|
| P2-01 | W7 | next_token | Next token prediction, Cross-Entropy, perplexity 수식 구현 | L1 | NOT_STARTED | | |
| P2-02 | W7 | backprop | 스칼라 autograd 엔진 직접 구현, 수동 미분 | L2 | NOT_STARTED | | |
| P2-03 | W7 | optimizer | SGD / Momentum / Adam / AdamW 직접 구현, LR 스케줄(warmup+cosine) | L2 | NOT_STARTED | | |
| P2-04 | W8 | overfitting | train/val 곡선, dropout, weight decay, early stopping | L2 | NOT_STARTED | | |
| P2-05 ★ | W8 | small_lm | 소형 LM 사전학습 (P1-13 확장, BPE 토크나이저, 10~30M 파라미터) | L3 | NOT_STARTED | | |
| P2-06 | W9 | generation | greedy / temperature / top-k / top-p, KV cache 개념 | L2 | NOT_STARTED | | |
| P2-07 | W9 | pretrained | 사전학습 모델 로드(Qwen 0.5B 등), perplexity 비교, pre-training vs fine-tuning | L2 | NOT_STARTED | | |
| P2-08 | W10 | instruction_tuning | chat template, 프롬프트 부분 loss masking, 소규모 SFT | L2 | NOT_STARTED | | |
| P2-09 | W10 | lora | LoRA 를 `nn.Linear` 래퍼로 직접 구현 | L3 | NOT_STARTED | | |
| P2-10 | W10 | qlora | 4bit NF4 로드, 메모리 측정, QLoRA 구조 이해 | L2 | NOT_STARTED | | |

### Part 3. RAG 내부 알고리즘 (`part3_rag/`, 5주)

| ID | 주차 | 폴더 | 실습 | 난이도 | 상태 | 확인일 | 메모·실험 링크 |
|---|---|---|---|---|---|---|---|
| P3-01 | W11 | document_loader | txt/md/pdf 로더, 메타데이터(출처·페이지) 보존 | L1 | NOT_STARTED | | |
| P3-02 | W11 | chunking | 고정 길이 / overlap / 재귀 / 문장 단위 청킹 | L2 | NOT_STARTED | | |
| P3-03 | W11 | evaluation | 평가셋(질문 → 정답 청크 qrels) 구축 | L1 | NOT_STARTED | | |
| P3-04 | W12 | dense_retrieval | 임베딩 + NumPy brute-force 코사인 top-k | L1 | NOT_STARTED | | |
| P3-05 | W12 | dense_retrieval | FAISS Flat / IVF / HNSW, recall vs latency | L2 | NOT_STARTED | | |
| P3-06 | W13 | sparse_retrieval | Inverted Index + TF-IDF 직접 구현 | L2 | NOT_STARTED | | |
| P3-07 | W13 | sparse_retrieval | BM25 직접 구현 (k1, b), 한국어 토큰화 영향 | L2 | NOT_STARTED | | |
| P3-08 | W14 | hybrid_search | RRF, Weighted fusion(min-max / z-score) 직접 구현 | L2 | NOT_STARTED | | |
| P3-09 | W14 | hybrid_search | 프레임워크 하이브리드 비교 (§5) | L3 | NOT_STARTED | | |
| P3-10 | W15 | reranking | Cross-Encoder 재순위, top-N 후보 수에 따른 품질·지연 | L2 | NOT_STARTED | | |
| P3-11 | W15 | evaluation | Precision/Recall/HitRate@K, MRR, NDCG 직접 구현, Latency(p50/p95) | L2 | NOT_STARTED | | |
| P3-12 ★ | W15 | evaluation | BM25 vs Dense vs Hybrid vs Hybrid+Rerank 동일 데이터셋 비교, CSV + 그래프 | L3 | NOT_STARTED | | |
| P3-13 | 선택 | dense_retrieval | (선택) ChromaDB 로 같은 실험, FAISS 와 차이 | L1 | NOT_STARTED | | |
| P3-14 | W15 | generation | 로컬 LLM 으로 답변 생성, (선택) RAGAS 와 IR 지표 비교 | L2 | NOT_STARTED | | |

### Part 4. GraphRAG 내부 원리 (`part4_graphrag/`, 4주)

| ID | 주차 | 폴더 | 실습 | 난이도 | 상태 | 확인일 | 메모·실험 링크 |
|---|---|---|---|---|---|---|---|
| P4-01 | W16 | knowledge_graph | 인접 리스트·트리플 저장소 직접 구현, 직렬화 | L1 | NOT_STARTED | | |
| P4-02 | W16 | entity_extraction | 사전·규칙 기반 개체 추출 | L2 | NOT_STARTED | | |
| P4-03 | W16 | relationship_extraction | 패턴 기반 관계 추출, 스키마 제약 검증 | L2 | NOT_STARTED | | |
| P4-04 | W17 | entity_extraction | 개체 정규화·병합(entity resolution) | L2 | NOT_STARTED | | |
| P4-05 | W17 | graph_traversal | BFS/DFS 직접 구현 | L1 | NOT_STARTED | | |
| P4-06 | W17 | graph_traversal | 최단경로(BFS/Dijkstra) 직접 구현 | L2 | NOT_STARTED | | |
| P4-07 | W17 | graph_traversal | 멀티홉 질의 (k-hop, 경로 제약) | L2 | NOT_STARTED | | |
| P4-08 | W18 | graph_retrieval | Graph + Vector 검색 직접 구현 (벡터로 시드 개체 → 그래프 확장 → 컨텍스트) | L3 | NOT_STARTED | | |
| P4-09 | W18 | graph_retrieval | (선택) 로컬 LLM Text2Cypher | L2 | NOT_STARTED | | |
| P4-10 ★ | W19 | evaluation | 멀티홉 질문셋으로 Vector RAG vs GraphRAG 정량 평가 | L3 | NOT_STARTED | | |

### Part 5. Fine-tuning (`part5_finetuning/`, 4주)

| ID | 주차 | 폴더 | 실습 | 난이도 | 상태 | 확인일 | 메모·실험 링크 |
|---|---|---|---|---|---|---|---|
| P5-01 | W20 | embedding | Part 3 평가셋으로 baseline 측정, train/test 분리(누수 방지) | L1 | NOT_STARTED | | |
| P5-02 | W20 | embedding | MultipleNegativesRankingLoss 학습 | L2 | NOT_STARTED | | |
| P5-03 | W21 | embedding | Triplet loss + hard negative mining (BM25/Dense) | L3 | NOT_STARTED | | |
| P5-04 | W21 | reranker | Cross-Encoder Reranker 미세조정 | L3 | NOT_STARTED | | |
| P5-05 | W22 | llm_lora | 0.5B~1.5B LoRA (도메인 QA / 포맷 학습) | L2 | NOT_STARTED | | |
| P5-06 | W23 | llm_lora | 3B~7B QLoRA (메모리 한계 실측) | L3 | NOT_STARTED | | |
| P5-07 ★ | W23 | (공통) | 학습 전후 종합 리포트 (품질·메모리·시간) | L3 | NOT_STARTED | | |

### Part 6. AI 서비스 (`part6_ai_service/`, 5주)

| ID | 주차 | 폴더 | 실습 | 난이도 | 상태 | 확인일 | 메모·실험 링크 |
|---|---|---|---|---|---|---|---|
| P6-01 | W24 | python_ai_server | FastAPI 구조, 설정, `/api/v1/health` | L1 | NOT_STARTED | | |
| P6-02 | W24 | python_ai_server | `/api/v1/documents`, `/api/v1/embeddings` | L2 | NOT_STARTED | | |
| P6-03 | W24 | python_ai_server | `/api/v1/search` (bm25/dense/hybrid/rerank 선택 파라미터) | L2 | NOT_STARTED | | |
| P6-04 | W25 | python_ai_server | `/api/v1/rag/query`, `/api/v1/graphrag/query` | L2 | NOT_STARTED | | |
| P6-05 | W25 | python_ai_server | 스트리밍 응답 (SSE) | L2 | NOT_STARTED | | |
| P6-06 | W25 | python_ai_server | pytest (TestClient), 예외 처리, 구조화 로깅 | L2 | NOT_STARTED | | |
| P6-07 | W26 | spring_boot_server | WebClient + DTO, Python 서버 호출 | L2 | NOT_STARTED | | |
| P6-08 | W26 | spring_boot_server | SSE 프록시 (`Flux<ServerSentEvent>`) | L3 | NOT_STARTED | | |
| P6-09 | W27 | spring_boot_server | 타임아웃·재시도·서킷브레이커(Resilience4j), 전역 예외 처리, 로깅 | L3 | NOT_STARTED | | |
| P6-10 ★ | W28 | spring_boot_server | RAG vs GraphRAG 결과 비교 웹 화면 | L2 | NOT_STARTED | | |
| P6-11 | W28 | (공통) | Docker Compose (Neo4j + AI 서버 + Spring Boot + Ollama) | L2 | NOT_STARTED | | |
| P6-12 | 확장 | (확장) | gRPC 전환 | L3 | NOT_STARTED | | |

## 주간 점검 템플릿

매주 한 번 아래 블록을 복사해 [주간 기록](#주간-기록) 맨 위에 추가한다. 기준은 [LEARNING_ROADMAP.md §3](LEARNING_ROADMAP.md#3-주차별-계획) 의 "주간 목표".

```markdown
### W? (YYYY-MM-DD ~ YYYY-MM-DD)

**계획 대비**
- 이번 주 계획 실습: P?-??, P?-??
- 상태 변화: P?-?? NOT_STARTED → IN_PROGRESS / NEEDS_REVIEW / COMPLETED
- 주간 목표 달성 여부: 예 / 부분 / 아니오 — (근거: 테스트, 수치, 실험 링크)

**구현 결과**
- 직접 구현한 것:
- 비교군과 비교한 결과 (수치):
- 실험 기록: experiments/...

**이해 점검** (말로 설명할 수 있는가?)
- [ ] 이번 주 핵심 개념을 수식 없이 3문장으로 설명
- [ ] 핵심 수식을 손으로 유도
- [ ] 라이브러리가 내부적으로 하는 일을 설명

**자원·시간**
- 학습 시간: ?h  /  GPU 사용 실험: 최대 VRAM ?GB, 학습 시간 ?분

**막힌 점 / 질문**
-

**다음 주 계획 조정**
- 일정 지연: 없음 / ?주 — 조정 내용:
- 다음 주 실습:
```

## 주간 기록

(아직 없음)
