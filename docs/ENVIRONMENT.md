# 환경 설정 (Part 0 · Step 4)

> 조사 시점: **2026-11-09**. PyPI 메타데이터(최신 버전, 업로드된 휠 태그)를 직접 조회한 결과와 웹 검색 결과를 기반으로 한다. `download.pytorch.org` 는 조사 환경에서 접근이 막혀 **PyTorch CUDA 휠 목록은 직접 확인하지 못했다** — 설치 후 §3.3 검증 스크립트로 꼭 확인한다.

## 1. 결론 요약

| 항목 | 결정 |
|---|---|
| 기존 강의 트랙 환경 | **그대로 유지** (`part1\.venv` 등 폴더별 Python 3.14 uv 환경, `uv.lock` 대부분 `>=3.14`) |
| 새 AI Lab 환경 | 저장소 루트에 **별도 uv 가상환경 `.venv-ailab` (Python 3.12)** 하나 |
| PyTorch | CUDA 빌드 `cu128` 권장 (RTX 3070 = sm_86, cu126/cu128/cu130 모두 대상). 드라이버가 최신이면 `cu130` 도 가능 |
| FAISS | Windows 는 **`faiss-cpu`** (GPU 휠 없음). GPU 가 꼭 필요하면 WSL2 |
| bitsandbytes | Windows 공식 휠 사용 (`pip install bitsandbytes`). 문제 시 WSL2 |
| 생성 LLM (서비스·GraphRAG) | **Ollama** 로 로컬 4bit 모델. 유료 API 없음 |
| Java | JDK 21 (Temurin) + Spring Boot 3.x, Gradle |

### 왜 3.14 가 아니라 3.12 인가
Python 3.14 로도 핵심 패키지 상당수는 설치된다(아래 표). 그래도 별도 3.12 를 권장하는 이유:
1. **기존 3.14 환경을 건드리지 않기 위해** 어차피 새 환경이 필요하다. 그렇다면 생태계가 가장 두터운 버전을 고르는 게 낫다.
2. 3.14 휠이 **없는** 패키지가 있다: `gensim`(cp313 까지), `faiss-gpu-cu12`(`<3.14`), 그 외 CUDA 확장 계열(triton-windows, xformers, flash-attn 커뮤니티 빌드 등)은 최신 Python 지원이 늦다.
3. `numpy`/`scipy` 최신은 `>=3.12` 요구 → **3.11 은 구버전 numpy 로 묶인다.** 3.12 가 "충분히 새롭고 충분히 검증된" 지점.
4. 오류가 났을 때 검색되는 사례·이슈가 3.12 에서 가장 많다.

## 2. 호환성 조사표 (PyPI 기준, 2026-11-09)

| 패키지 | 최신 버전 | 휠 태그 / 요구 Python | 3.14 | 3.12 | Windows 비고 |
|---|---|---|---|---|---|
| torch | 2.15.0 | cp311~cp315 | ✅ | ✅ | PyPI 의 Windows 휠은 **CPU 전용**. CUDA 는 `download.pytorch.org/whl/cu1xx` 인덱스 사용 |
| torchvision | 0.29.2 | py3, `!=3.14.1` | ✅ | ✅ | torch 와 같은 인덱스에서 설치 |
| transformers | 5.22.2 | py3, `>=3.11` | ✅ | ✅ | v5 계열. 예제 코드가 v4 기준이면 API 차이 확인 |
| tokenizers | 0.23.3 | cp310(abi3), cp314 | ✅ | ✅ | |
| safetensors | 0.8.0 | cp310 abi3 | ✅ | ✅ | |
| sentence-transformers | 6.2.0 | py3 | ✅ | ✅ | |
| peft | 0.21.2 | py3 | ✅ | ✅ | |
| trl | 1.17.1 | py3, `>=3.11` | ✅ | ✅ | |
| accelerate | 1.15.0 | py3 | ✅ | ✅ | |
| bitsandbytes | 0.50.2 | py3-none-win_amd64 휠 있음 | ✅ | ✅ | Windows 공식 지원(0.43+). CUDA 빌드 torch 필요 |
| faiss-cpu | 1.15.1 | cp310~cp314 | ✅ | ✅ | |
| faiss-gpu-cu12 | 1.14.1.post1 | **Linux 전용**, `<3.14` | ❌ | ❌(Win) | Windows 휠 없음 → WSL2 또는 torch 행렬곱으로 대체 |
| chromadb | 1.5.9 | cp39 abi3 | ✅ | ✅ | |
| rank-bm25 / bm25s | 0.2.2 / 0.3.16 | py3 | ✅ | ✅ | rank-bm25 는 2022 이후 갱신 없음(비교용으로 충분) |
| scikit-learn | 1.9.1 | cp311~cp315 | ✅ | ✅ | |
| numpy / scipy | 2.5.4 / 1.18.1 | cp312~cp315, `>=3.12` | ✅ | ✅ | 3.11 불가 |
| gensim | 4.4.0 | cp39~**cp313** | ❌ | ✅ | P1-06 비교군(선택) |
| kiwipiepy | 0.24.1 | cp39 abi3, cp314 | ✅ | ✅ | 한국어 형태소 분석(BM25 토큰화) |
| datasets | 5.1.0 | py3 | ✅ | ✅ | |
| neo4j (driver) | 6.4.1 | py3 | ✅ | ✅ | 강의 트랙은 `neo4j~=5.28` 고정. Lab 도 5.28 로 맞춤 |
| neo4j-graphrag | 1.23.0 | py3, `<3.15` | ✅ | ✅ | |
| langchain / langchain-classic | 1.4.9 / 1.0.8 | py3 | ✅ | ✅ | LangChain 1.x 에서 `EnsembleRetriever` 등 레거시 retriever 의 패키지 위치 확인 |
| llama-index-core | 0.14.25 | py3, `<4.0` | ✅ | ✅ | |
| haystack-ai | 3.4.1 | py3, `>=3.11` | ✅ | ✅ | |
| fastapi / uvicorn | 0.162.2 / 0.54.0 | py3 | ✅ | ✅ | |
| onnxruntime | 1.31.1 | cp311~cp314 | ✅ | ✅ | (선택) 추론 최적화 |

**해석(resolve) 검증**: `uv pip compile requirements/part5.txt`, `part6.txt` 를 `--python-platform x86_64-pc-windows-msvc` 로 **Python 3.12 / 3.14 둘 다 충돌 없이 해석**됨을 확인했다(약 200개 패키지, torch 2.15.0, transformers 5.22.2, sentence-transformers 6.2.0, peft 0.21.2, bitsandbytes 0.50.2, faiss-cpu 1.15.1). 해석만 확인한 것이며 실제 설치·GPU 동작은 사용자 PC 에서 §3.3 으로 확인해야 한다. 즉 3.14 는 "막혀 있지 않다"가 결론이고, 3.12 권장은 안정성·선택 패키지(gensim 등)·사례 수 때문이다.

> 버전은 학습 도중 계속 오른다. requirements 파일은 하한만 두고, 실제 설치된 버전은 `uv pip freeze > experiments/<실험>/freeze.txt` 로 실험마다 기록한다.

## 3. AI Lab 환경 구성 (Windows PowerShell)

### 3.1 사전 준비
1. **NVIDIA 드라이버** 최신으로 업데이트 → `nvidia-smi` 우상단 `CUDA Version` 이 고를 PyTorch CUDA 버전 이상인지 확인 (cu128 → 12.8 이상, cu130 → 13.0 이상). PyTorch·bitsandbytes 휠은 CUDA 런타임을 포함하므로 **CUDA Toolkit 별도 설치는 필요 없다.**
2. Windows **긴 경로 허용**(LongPathsEnabled) — HF 캐시 경로가 길어진다.
3. (선택) **개발자 모드** 켜기 — HF Hub 캐시의 symlink 경고 방지.
4. 환경 변수 권장: `PYTHONUTF8=1`(한글 경로·파일 인코딩), `HF_HOME=D:\hf_cache`(모델 캐시를 여유 있는 드라이브로).

### 3.2 설치 명령

```powershell
cd C:\gitRepo\graphRAG_learning

# 1) Python 3.12 설치 (uv 가 관리, 시스템 Python·기존 3.14 환경과 무관)
uv python install 3.12

# 2) 루트에 AI Lab 전용 가상환경 생성 (part1\.venv 와 별개)
uv venv .venv-ailab --python 3.12
.\.venv-ailab\Scripts\Activate.ps1

# 3) PyTorch CUDA 빌드를 먼저 설치 (PyPI 의 CPU 빌드가 들어오지 않도록)
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
#    대안: uv pip install torch torchvision --torch-backend=cu128   (uv 의 torch-backend 기능)

# 4) 필요한 Part 의 의존성만 추가 설치
uv pip install -r requirements\part1.txt
# uv pip install -r requirements\part3.txt   ... Part 진행에 맞춰
uv pip install -r requirements\dev.txt
```

- 이후 의존성을 설치할 때 torch 가 CPU 빌드로 바뀌지 않았는지 §3.3 으로 다시 확인한다.
- VS Code 인터프리터는 `.venv-ailab\Scripts\python.exe` 로 선택. 강의 트랙 폴더 작업 시에는 기존 폴더별 `.venv` 로 되돌린다.
- `.venv-ailab/` 는 `.gitignore` 에 추가되어 있다.

### 3.3 GPU 검증

```powershell
python -c "import torch;print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())"
python -c "import torch;f,t=torch.cuda.mem_get_info();print(f'free {f/2**30:.2f} / total {t/2**30:.2f} GiB')"
python -c "import bitsandbytes as bnb, torch; print(bnb.__version__); print(bnb.nn.Linear4bit(64,64).cuda())"   # Part 2 이후
```

기대값: `+cu128` 표시, `True`, `NVIDIA GeForce RTX 3070`, `True`, total ≈ 8 GiB(free 는 화면 출력 때문에 7.x GiB). 결과는 P0-02 로 `experiments/` 에 기록.

## 4. Windows 에서 예상되는 문제와 대안

| 문제 | 증상 | 해결책 |
|---|---|---|
| torch 가 CPU 빌드로 설치됨 | `torch.cuda.is_available() == False`, 버전에 `+cpu` | §3.2 의 CUDA 인덱스로 재설치. `uv pip install` 시 torch 를 다른 인덱스에서 덮어쓰지 않았는지 확인 |
| faiss-gpu 없음 | `pip install faiss-gpu` 실패 | `faiss-cpu` 사용(학습 규모 수만~수십만 벡터면 충분). GPU 비교가 필요하면 `torch.matmul` brute-force 를 GPU 에서 직접 구현(오히려 학습 가치 있음) 또는 WSL2 Ubuntu |
| bitsandbytes 로드 실패 | CUDA 라이브러리를 못 찾음, CPU fallback 경고 | CUDA torch 설치 확인, `python -m bitsandbytes` 진단, 비공식 Windows 포크 사용 금지. 그래도 안 되면 QLoRA 실습만 WSL2 에서 |
| `torch.compile` / triton | Windows 에서 triton 공식 미지원 | 이 로드맵에서는 `torch.compile` 을 쓰지 않는다(필수 아님) |
| flash-attention | 공식 Windows 휠 없음 | PyTorch 내장 `scaled_dot_product_attention`(SDPA) 사용. transformers 에서 `attn_implementation="sdpa"` |
| DataLoader 멀티프로세스 | `num_workers>0` 에서 재귀 실행 오류 | 스크립트에 `if __name__ == "__main__":` 필수, 처음엔 `num_workers=0` |
| VRAM 실사용량 8GB 미만 | 7.x GB 에서 OOM | 브라우저 하드웨어 가속 끄기, 실험 중 Ollama 종료, `torch.cuda.empty_cache()`, batch·seq 축소 |
| HF 다운로드 경로·용량 | C 드라이브 부족, symlink 경고 | `HF_HOME` 변경, 개발자 모드 |
| 한글 인코딩 | `UnicodeDecodeError` (cp949) | `PYTHONUTF8=1`, 파일 열 때 `encoding="utf-8"` 명시 |
| Docker 에서 GPU | Docker Desktop + GPU 는 WSL2 백엔드 + NVIDIA 드라이버 필요 | Part 6 은 AI 서버를 호스트에서 실행하고 Neo4j·Spring Boot 만 컨테이너로 시작해도 됨 |

## 5. 모델 추천과 VRAM 추정

### 5.1 계산식 (근사)
- **가중치**: 파라미터 수 × (fp16/bf16 2B, int8 1B, NF4 ≈ 0.55B)
- **KV 캐시**: `2 × 레이어 × KV헤드 × head_dim × 토큰수 × 2B`. 예) Qwen2.5-7B(28층, KV 4헤드, 128) ≈ 57KB/토큰 → 4K 토큰 ≈ 0.23GB
- **Full fine-tuning**: 파라미터당 ≈ 16B (bf16 가중치 2 + 그래디언트 2 + fp32 master 4 + Adam m·v 8)
- **LoRA**: 동결 base 가중치 + LoRA 파라미터(전체의 0.1~1%) × 16B + 활성값(배치·시퀀스에 비례, gradient checkpointing 으로 크게 감소)
- **CUDA 컨텍스트**: 0.3~0.5GB

예) 1.5B LoRA(bf16): 3.1GB + 0.5GB + 활성값 1.5~3GB ≈ 5~7GB / 7B QLoRA: 4.2GB + LoRA·옵티마이저 0.3GB + 활성값 1~2GB + 0.5GB ≈ 6~7.5GB(한계).

### 5.2 RTX 3070 판정표
[LEARNING_ROADMAP.md §4](LEARNING_ROADMAP.md#4-rtx-3070-8gb-로-가능한-학습--불가능한-학습) 의 표를 기준으로 한다. Part 5 실측 후 이 문서와 함께 갱신한다.

### 5.3 추천 모델 (라이선스는 **다운로드 시 모델 카드에서 다시 확인**)

**LLM (생성·LoRA)**
| 용도 | 모델 | 크기 | 라이선스 | 비고 |
|---|---|---|---|---|
| 빠른 LoRA 실험 | Qwen2.5-0.5B-Instruct / Qwen3-0.6B | 0.5~0.6B | Apache-2.0 | 한국어 일부 가능 |
| 주력 LoRA | Qwen2.5-1.5B-Instruct / Qwen3-1.7B | 1.5~1.7B | Apache-2.0 | |
| QLoRA | Qwen3-4B | 4B | Apache-2.0 | ⚠️ Qwen2.5-**3B** 는 Qwen Research License(비상업) |
| QLoRA 도전 | Qwen2.5-7B-Instruct / Qwen3-8B | 7~8B | Apache-2.0 | batch 1, seq ≤512 |
| 대안 | Llama-3.2-1B/3B-Instruct | 1~3B | Llama 3.2 Community License (게이트, 이용 정책) | |
| 대안 | Gemma 3 1B/4B | 1~4B | Gemma Terms of Use | |
| 한국어 특화 | EXAONE-3.5-2.4B/7.8B-Instruct | 2.4~7.8B | EXAONE AI Model License (**비상업**) | 포트폴리오 데모는 OK, 상업 사용 불가 |
| 초소형 비교 | SmolLM2-135M/360M | 0.1~0.4B | Apache-2.0 | 영어 중심, 학습 흐름 확인용 |
| 서비스 추론 | Ollama 4bit (예: `qwen2.5:7b`, `qwen3:8b`, `qwen3:4b`) | — | 원본 모델 라이선스 따름 | Ollama 자체는 MIT |

> 2026-11 시점에는 더 새로운 세대가 나와 있을 수 있다. 같은 크기·같은 라이선스 조건이면 교체해도 되며, 교체 시 VRAM 을 다시 실측한다.

**임베딩 (Part 3·5)**
| 모델 | 크기·차원 | 라이선스 | 비고 |
|---|---|---|---|
| intfloat/multilingual-e5-small | 118M · 384 | MIT | 가장 가벼움, 파인튜닝 실습 1순위. `query:`/`passage:` 접두어 필요 |
| intfloat/multilingual-e5-base | 278M · 768 | MIT | |
| BAAI/bge-m3 | 568M · 1024 | MIT | 한국어 성능 우수, 8K 토큰. 파인튜닝 시 배치 작게 |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | 118M · 384 | Apache-2.0 | 비교용 |

**Reranker (Part 3·5)**
| 모델 | 크기 | 라이선스 | 비고 |
|---|---|---|---|
| BAAI/bge-reranker-v2-m3 | 568M | Apache-2.0 | 다국어·한국어 |
| cross-encoder/ms-marco-MiniLM-L6-v2 | 22M | Apache-2.0 | 영어, 매우 빠름(원리 확인용) |

**토크나이저 비교 (Part 1)**: GPT-2 BPE(MIT), `tiktoken`(MIT), Qwen 토크나이저.

### 5.4 데이터셋 후보와 라이선스 (사용 전 원문 확인)
| 데이터 | 용도 | 라이선스 |
|---|---|---|
| 저장소 `part2/txt2kg/wiki_*.txt` | P1 말뭉치, P4 추출 | 위키백과 본문 → CC BY-SA |
| 저장소 `part2/pdf2kg/aibrief.pdf` | P3 공통 문서 | 발행기관 저작물 — 개인 학습용으로만, 재배포 금지 |
| 저장소 `part2/csv2kg/train.csv` | P4 그래프 탐색 | Kaggle Titanic (대회 이용 약관) |
| Tiny Shakespeare | P1-13, P2-05 | 퍼블릭 도메인 텍스트 |
| 한국어 위키백과 덤프(일부) | P2-05 소형 LM | CC BY-SA |
| KorQuAD 1.0 | P3·P5 질의-문서 쌍 | CC BY-ND 2.0 KR (변형물 재배포 제한) |
| HotpotQA | P4-10 멀티홉 | CC BY-SA 4.0 |
| 2WikiMultihopQA | P4-10 멀티홉 | Apache-2.0 (확인 필요) |
| MS MARCO | P5 영어 비교 | 비상업 연구용 |

## 6. 외부 서비스

| 서비스 | 권장 | 라이선스·비고 |
|---|---|---|
| Neo4j | Neo4j Desktop 또는 Docker `neo4j:5` Community (+APOC) | Community: GPLv3. 강의 `community_search` 는 GDS 플러그인 필요 |
| Ollama | Windows 네이티브 설치, GPU 자동 사용 | MIT. 기본 포트 11434 |
| Java | Eclipse Temurin JDK 21, Spring Boot 3.x, Gradle | |
| Docker | Docker Desktop (WSL2 백엔드) | Part 6 |

## 7. 의존성 파일
단계별 파일은 [`requirements/`](../requirements/README.md). 설치는 강제하지 않으며, Part 를 시작할 때 해당 파일만 설치한다.
