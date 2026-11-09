# 아키텍처 & 규약

## 1. 최종 디렉터리 구조

기존 강의 트랙(`part1`~`part4`, `common`)은 **그대로 두고**, 새 AI Lab 트랙을 다른 이름의 최상위 폴더로 추가한다.

```
graphRAG_learning/
├── README.md                     # (기존) + 문서 링크 섹션 추가
├── LEARNING.md                   # (기존) 강의 트랙 학습 목차
├── 커리큘럼.pdf                   # (기존)
│
├── docs/                         # ★ AI Lab 문서
│   ├── PROJECT_PLAN.md  REPOSITORY_ANALYSIS.md  LEARNING_ROADMAP.md
│   ├── ARCHITECTURE.md  ENVIRONMENT.md  PROGRESS.md
│
├── requirements/                 # ★ 단계별 의존성 (AI Lab 환경용)
│   ├── base.txt  part1.txt  part2.txt  part3.txt  part4.txt  part5.txt  part6.txt  dev.txt
│
├── ── 기존 강의 트랙 (변경 없음) ──────────────────────────────
├── common/                       # 강의 트랙 공용 uv 환경
├── part1/                        # Neo4j 기초                (Python 3.14 .venv)
├── part2/{txt2kg,csv2kg,pdf2kg,law2kg,retail2kg,medical2kg}
├── part3/{vectorsearch,text2cypher,reasoning,vectorcypher,vectorcypher_qdrant,
│          community_search,toolsretriever,evaluation,learning}
├── part4/{create_agent,streamlit,graphrag_tool_agent,graphrag_text2cypher_agent,final_chatbot}
│
├── ── 새 AI Lab 트랙 (Part 1 부터 순차 생성) ─────────────────────
├── part1_ai_fundamentals/
│   ├── tokenizer/  embedding/  word2vec/  pytorch/  transformer/
├── part2_llm/
│   ├── next_token/  backprop/  optimizer/  overfitting/  small_lm/
│   ├── generation/  pretrained/  instruction_tuning/  lora/  qlora/
├── part3_rag/
│   ├── document_loader/  chunking/  dense_retrieval/  sparse_retrieval/
│   ├── hybrid_search/  reranking/  evaluation/  generation/
├── part4_graphrag/
│   ├── knowledge_graph/  entity_extraction/  relationship_extraction/
│   ├── graph_traversal/  graph_retrieval/  evaluation/
├── part5_finetuning/
│   ├── embedding/  reranker/  llm_lora/
├── part6_ai_service/
│   ├── python_ai_server/         # FastAPI (app/, tests/, Dockerfile)
│   ├── spring_boot_server/       # Gradle, Java 21 (src/main, src/test, Dockerfile)
│   └── docker-compose.yml
│
├── datasets/                     # 데이터 설명·다운로드 스크립트·작은 샘플만 커밋 (원본 대용량은 gitignore)
├── experiments/                  # ★ 실험 기록 (포트폴리오)
└── tests/                        # pytest — 각 Part 폴더 구조를 그대로 미러링
```

> 각 하위 폴더(예: `tokenizer/`)는 실습 단위 폴더를 가진다: `part1_ai_fundamentals/tokenizer/p1_02_bpe/`. 폴더 이름의 `p1_02` 는 [LEARNING_ROADMAP](LEARNING_ROADMAP.md) 의 실습 ID 와 같다.

## 2. 명칭 충돌 해결: 기존 `partN` vs 신규 `partN_xxx`

**문제**: 기존 `part1` 은 "Neo4j 기초", 새 로드맵의 Part 1 은 "AI/딥러닝 기초"로 내용이 전혀 다르다. 또 사용자는 `C:\gitRepo\graphRAG_learning\part1\.venv` 를 실사용 중이다.

| 대안 | 장점 | 단점 | 판정 |
|---|---|---|---|
| A. 기존 `part1~4` 를 `course_graphrag/` 로 이동 | 이름이 깔끔 | 사용자의 `part1\.venv` 경로, 문서 링크, 각 `uv.lock` 경로가 깨짐. "기존 소스 대규모 변경 금지" 위반 | ❌ |
| B. 기존 `part1` 안에 새 내용 합치기 | 폴더 수 적음 | 주제 혼합, Python 3.14 환경에 torch 등이 섞임 | ❌ |
| **C. 새 트랙을 `part1_ai_fundamentals` 등 접미사 이름으로 추가** | 기존 무변경, 경로·환경 유지, 이름만 봐도 구분됨 | 최상위 폴더 수 증가 | ✅ **채택** |

**규칙**
- `partN/` = **강의 트랙**(GraphRAG 강의, 라이브러리 사용 중심). 수정하지 않고 참조만 한다.
- `partN_<주제>/` = **AI Lab 트랙**(원리 직접 구현 + 비교). 새 코드는 여기에만 쓴다.
- 문서에서 모호할 때는 "강의 part3" / "Lab Part 3" 처럼 접두어를 붙인다.
- Lab Part 4 는 강의 `part2`·`part3` 를 상대 경로로 참조하는 비교 실험으로 구성한다. 강의 코드를 복사해 오지 않는다.

## 3. 서비스 아키텍처 (Part 6 최종 형태)

```mermaid
flowchart LR
    U[사용자<br/>브라우저] -->|HTTP / SSE| SB

    subgraph JVM["Spring Boot (Java 21)"]
        SB[Controller<br/>비교 화면 · REST] --> SVC[Service<br/>DTO 변환 · 검증]
        SVC --> WC[WebClient<br/>timeout · retry · circuit breaker]
    end

    WC -->|REST JSON / SSE<br/>/api/v1/*| API

    subgraph PY["Python AI Server (FastAPI)"]
        API[Router<br/>documents · embeddings · search<br/>rag/query · graphrag/query · health]
        API --> RAG[RAG Pipeline<br/>BM25 · Dense · Hybrid · Rerank]
        API --> GR[GraphRAG Pipeline<br/>Entity link · Traversal · Graph+Vector]
        RAG --> EMB[Embedding / Reranker<br/>sentence-transformers]
        GR --> EMB
    end

    RAG --> VDB[(Vector Index<br/>FAISS / ChromaDB)]
    RAG --> BM[(BM25 Inverted Index)]
    GR --> NEO[(Neo4j)]
    RAG --> LLM[LLM<br/>Ollama 로컬 모델]
    GR --> LLM
```

### 3.1 요청 흐름 (RAG vs GraphRAG 비교 화면)

```mermaid
sequenceDiagram
    participant U as 사용자
    participant S as Spring Boot
    participant P as FastAPI
    participant V as Vector/BM25
    participant N as Neo4j
    participant L as LLM (Ollama)

    U->>S: POST /compare {question}
    par RAG
        S->>P: POST /api/v1/rag/query
        P->>V: hybrid search + rerank
        P->>L: prompt(context)
        L-->>P: answer (stream)
        P-->>S: SSE tokens + sources
    and GraphRAG
        S->>P: POST /api/v1/graphrag/query
        P->>N: entity link → multi-hop traversal
        P->>L: prompt(subgraph context)
        L-->>P: answer (stream)
        P-->>S: SSE tokens + paths
    end
    S-->>U: 두 답변 + 근거 + 지연시간 나란히 표시
```

### 3.2 API 초안 (Part 6 에서 확정)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/v1/health` | 상태, 모델 로드 여부, Neo4j·LLM 연결 |
| POST | `/api/v1/documents` | 문서 업로드 → 로딩·청킹·인덱싱 |
| GET | `/api/v1/documents/{id}` | 문서·청크 메타데이터 |
| POST | `/api/v1/embeddings` | 텍스트 → 벡터 |
| POST | `/api/v1/search` | `{query, method: bm25\|dense\|hybrid, rerank, top_k}` |
| POST | `/api/v1/rag/query` | 검색 + 생성, `stream=true` 이면 SSE |
| POST | `/api/v1/graphrag/query` | 그래프 검색 + 생성, SSE 지원 |

공통 응답에는 `latency_ms`, `sources`(청크 ID·출처) 또는 `paths`(그래프 경로)를 포함한다. 오류는 `{code, message, detail}` 형식으로 통일하고 Spring Boot 에서 도메인 예외로 변환한다.

- 처음엔 **REST + SSE**. gRPC 는 P6-12 확장 과제.
- 유료 API 없이 동작하는 것이 기본값. (선택) 기존 강의 트랙처럼 OpenAI/Claude 를 쓰는 어댑터는 설정으로만 켠다.

## 4. 실습 코드 규약 (starter / solution / test)

### 4.1 실습 폴더 구성

```
part3_rag/sparse_retrieval/p3_07_bm25/
├── README.md          # 12개 항목 (아래 4.3)
├── starter.py         # TODO 가 있는 학습자용 파일
├── solution.py        # 완성본 (정답)
└── data/              # (필요 시) 아주 작은 샘플만
tests/part3_rag/sparse_retrieval/test_p3_07_bm25.py
```

- `starter.py` 와 `solution.py` 는 **같은 공개 함수·클래스 시그니처**를 가진다. starter 의 TODO 는 `raise NotImplementedError("TODO: ...")` 로 표시한다.
- 실행 진입점은 `if __name__ == "__main__":` 블록. 예상 출력은 README 에 적는다.
- 난이도는 README 맨 위와 TODO 주석에 `Level 1/2/3` 으로 표시한다.
- TODO 아래에는 `HINT 1` / `HINT 2` / `WHY` / `REF` 주석을 단다 (§4.4).
- 실습 하나의 흐름: **개념 → 수학 원리 → 데이터 흐름 → 코드 구조 → 구현할 부분 → 실행법 → 예상 출력 → 결과 해석 → 과제 → 정답**.

### 4.2 테스트 규약
- 테스트는 루트 `tests/` 아래에 Part 폴더 구조를 미러링한다.
- 공용 `tests/conftest.py` 가 `--impl` 옵션(`solution` 기본, `starter` 선택)을 받아 해당 파일을 경로로 import 한다.
  - `pytest tests/part3_rag` → solution 기준, **항상 통과해야 함**
  - `pytest tests/part3_rag --impl starter` → 학습자가 TODO 를 채우면 통과
- 수치 비교는 허용 오차를 둔다 (`torch.testing.assert_close`, `pytest.approx`).
- 마커: `@pytest.mark.gpu`(CUDA 필요), `@pytest.mark.slow`(1분 이상), `@pytest.mark.network`(모델 다운로드 필요). 기본 실행은 `-m "not gpu and not slow and not network"`.
- 라이브러리 비교 테스트(예: 직접 BM25 vs `rank-bm25`)는 "같은 설정에서 같은 결과"를 검증한다.

### 4.3 실습 README 12개 항목 (템플릿)

```markdown
# P3-07 BM25 직접 구현  (Level 2)
1. 목표
2. 선수지식
3. 핵심 개념
4. 내부 원리
5. 수식 / 그림
6. 실행법
7. TODO 목록
8. 예상 결과
9. 자주 나는 오류
10. 과제
11. 체크리스트
12. 다음 단계 연결
```

### 4.4 주석 규약 (HINT / WHY / REF)

학습자가 막혔을 때 **정답을 보기 전에 스스로 한 걸음 더 갈 수 있도록** starter 에 단계별 힌트를 두고, solution 에는 "왜"를 남긴다.

**starter.py — 각 TODO 바로 아래**

| 태그 | 내용 | 규칙 |
|---|---|---|
| `# TODO n:` | 구현할 일 (무엇을) | 번호는 파일 안에서 연속 |
| `# HINT 1:` | 방향만 제시 — 떠올려야 할 개념·함수 | 코드 조각 금지 |
| `# HINT 2:` | 더 구체적으로 — 텐서 shape, 사용할 API 이름, 주의할 축(dim) | **정답 코드를 그대로 쓰지 않는다** |
| `# WHY:` | 이 단계가 왜 필요한가 (빠뜨리면 무슨 일이 생기는가) | 필수 |
| `# REF:` | 출처 — 논문(저자, 연도, 제목, 절 번호), 공식 문서 URL(PyTorch/HF/Neo4j/Spring 등), 표준 교재 | **실제로 존재하는 것만.** 불확실하면 REF 를 생략하고 WHY 만 쓴다. 지어낸 URL·절 번호 금지 |

**solution.py — 각 핵심 줄**
- "무엇을"이 아니라 **"왜"** 를 설명하는 주석.
- 텐서가 바뀌는 줄에는 **shape 주석**: `# (batch, heads, seq, d_k)`.
- starter 와 **같은 TODO 번호와 같은 REF** 를 유지해 두 파일을 나란히 비교할 수 있게 한다.

**검수 체크리스트 (실습 PR 마다)**
- [ ] 모든 TODO 에 HINT 1·HINT 2·WHY 가 있다 (REF 는 확실할 때만)
- [ ] HINT 에 정답 한 줄이 그대로 들어 있지 않다
- [ ] REF 의 URL 을 실제로 열어 확인했고, 논문 절 번호가 원문과 일치한다
- [ ] solution 의 shape 주석이 실제 텐서 shape 와 같다 (테스트로 검증되면 더 좋음)

#### 예시 — P1-09 Scaled Dot-Product Attention

`starter.py` (TODO 7~9)

```python
import math
import torch
import torch.nn.functional as F


def scaled_dot_product_attention(q, k, v, mask=None):
    """q, k, v: (batch, heads, seq, d_k)  /  mask: (batch, 1, seq, seq), True = 가릴 위치"""
    d_k = q.size(-1)

    # TODO 7: 질의(q)와 키(k)의 유사도 점수 행렬을 만들고 스케일링하라.
    # HINT 1: 두 벡터의 유사도는 내적이다. 모든 (질의, 키) 쌍의 내적을 한 번에 구하는 행렬 연산을 떠올려라.
    # HINT 2: k 의 마지막 두 축을 바꿔야 (seq, d_k) @ (d_k, seq) 가 된다 → torch.matmul, Tensor.transpose.
    #         결과 shape 는 (batch, heads, seq, seq). 스케일 값은 d_k 에서 나온다.
    # WHY: 스케일링이 없으면 d_k 가 클 때 내적 값의 분산이 d_k 에 비례해 커지고, softmax 가 한 위치로
    #      쏠려(거의 one-hot) gradient 가 0 에 가까워진다.
    # REF: Vaswani et al., 2017, "Attention Is All You Need", §3.2.1 Scaled Dot-Product Attention
    scores = ...

    # TODO 8: mask 가 주어지면, 가릴 위치의 점수를 softmax 후 0 이 되도록 바꿔라.
    # HINT 1: softmax 결과가 0 이 되려면 입력이 어떤 값이어야 하는가?
    # HINT 2: Tensor.masked_fill 을 쓴다. mask 는 브로드캐스팅으로 (batch, heads, seq, seq) 에 맞춰진다.
    # WHY: causal mask 가 없으면 디코더가 미래 토큰을 보고 "정답을 베껴" 학습하게 되고,
    #      padding mask 가 없으면 의미 없는 패딩 토큰에 주의가 분산된다.
    # REF: Vaswani et al., 2017, "Attention Is All You Need", §3.2.3 Applications of Attention in our Model
    # REF: https://pytorch.org/docs/stable/generated/torch.Tensor.masked_fill_.html
    if mask is not None:
        scores = ...

    # TODO 9: 점수를 확률(가중치)로 바꾸고, 그 가중치로 v 를 가중합하라.
    # HINT 1: 각 질의 위치마다 "모든 키에 대한 가중치 합 = 1" 이 되어야 한다.
    # HINT 2: F.softmax 의 dim 은 키 축(마지막 축)이다. 가중합은 (seq, seq) @ (seq, d_k) 행렬곱.
    # WHY: 가중치 합이 1 이어야 출력이 v 들의 볼록 결합(convex combination)이 되어 값의 크기가 안정적이다.
    # REF: https://pytorch.org/docs/stable/generated/torch.nn.functional.softmax.html
    weights = ...
    output = ...
    return output, weights
```

`solution.py` (같은 TODO 번호·REF 유지)

```python
def scaled_dot_product_attention(q, k, v, mask=None):
    d_k = q.size(-1)

    # TODO 7  REF: Vaswani et al., 2017, §3.2.1
    # 내적 = 유사도. sqrt(d_k) 로 나눠 분산을 1 근처로 되돌려 softmax 포화를 막는다.
    scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(d_k)  # (batch, heads, seq, seq)

    # TODO 8  REF: Vaswani et al., 2017, §3.2.3
    if mask is not None:
        # -inf 는 softmax 후 정확히 0 → 가린 위치가 가중합에 전혀 기여하지 않는다.
        # (fp16 에서 한 행 전체가 가려지면 NaN 이 되므로, 그 경우는 큰 음수를 쓰는 대안도 README 에 설명)
        scores = scores.masked_fill(mask, float("-inf"))  # (batch, heads, seq, seq)

    # TODO 9
    # 키 축(dim=-1)으로 정규화해야 "질의마다" 가중치 합이 1 이 된다.
    weights = F.softmax(scores, dim=-1)                   # (batch, heads, seq, seq)
    # 가중치로 v 를 섞는다 → 각 위치가 관련 있는 위치의 정보를 모은 표현이 된다.
    output = torch.matmul(weights, v)                     # (batch, heads, seq, d_k)
    return output, weights
```

> 테스트(P1-09): 같은 입력에서 `F.scaled_dot_product_attention` 결과와 `torch.testing.assert_close` 로 비교한다. 주의: PyTorch 의 bool `attn_mask` 는 **True = 참여(보이는 위치)** 로, 이 예시의 mask(True = 가릴 위치)와 반대이므로 `attn_mask=~mask` 를 넘긴다. (REF: https://pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html)

### 4.5 실험 기록 규약
- 학습·벤치마크를 돌리면 `experiments/` 에 기록한다. 형식: [experiments/README.md](../experiments/README.md)
- 결과 CSV·그림은 `experiments/<날짜>_<실습ID>_<요약>/` 에 둔다. 모델 체크포인트는 커밋하지 않는다.

### 4.6 기타 규약
- 시크릿은 `.env` 에만 (기존 저장소 규칙과 동일).
- 큰 파일(모델, 원본 데이터, 인덱스)은 커밋하지 않는다. Part 1 시작 시 `.gitignore` 에 `datasets/raw/`, `experiments/**/checkpoints/`, `*.faiss`, `*.safetensors` 등을 추가한다.
- 공용 유틸(seed 고정, 시간·GPU 메모리 측정, 실험 기록 저장)은 처음 필요해지는 시점에 `labkit/` 같은 작은 패키지로 묶는다. 미리 만들지 않는다.
- 코드 주석과 문서는 한국어, 식별자는 영어.

## 5. 용어 정리 (혼동 방지)

| 용어 | 이 프로젝트에서의 의미 |
|---|---|
| Hybrid Search | **Sparse(BM25) + Dense(벡터) 결과 융합** (RRF, Weighted). 강의 `part3/learning/step3_hybrid_retrieval.py` 의 "벡터 + 그래프 확장"과 다름 |
| Graph + Vector 검색 | 벡터로 시드 노드를 찾고 그래프로 확장 (강의의 VectorCypher 패턴) |
| GraphRAG | 그래프 구조(개체·관계·경로)를 검색 컨텍스트로 쓰는 RAG |
| 직접 구현 | NumPy/PyTorch/표준 라이브러리로 알고리즘을 작성한 것 |
| 비교군 | 같은 기능의 기존 라이브러리 구현 또는 강의 트랙 코드 |
