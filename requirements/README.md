# requirements/ — AI Lab 단계별 의존성 (초안)

AI Lab 전용 환경(`.venv-ailab`, Python 3.12)에서 쓰는 파일이다. 기존 강의 트랙(`part1`~`part4`)의 폴더별 uv 환경과는 무관하다.
설치 순서·주의점은 [docs/ENVIRONMENT.md](../docs/ENVIRONMENT.md#3-ai-lab-환경-구성-windows-powershell) 참고.

| 파일 | 대상 | 비고 |
|---|---|---|
| `base.txt` | 공통 | 다른 파일이 `-r base.txt` 로 포함 |
| `part1.txt` | AI 기초 (토크나이저, Word2Vec, Transformer) | **torch 는 CUDA 인덱스로 먼저 설치** |
| `part2.txt` | LLM 학습 원리, LoRA/QLoRA | bitsandbytes 포함 |
| `part3.txt` | RAG 알고리즘 + 프레임워크 하이브리드 비교 | |
| `part4.txt` | GraphRAG 원리 | Neo4j 드라이버는 강의 트랙과 같은 5.28 |
| `part5.txt` | Fine-tuning | part2 + part3 포함 |
| `part6.txt` | FastAPI AI 서버 | Spring Boot 는 Gradle 로 별도 관리 |
| `dev.txt` | 테스트·린트·노트북 | |

- 하한(`>=`)만 두었다. 실제 설치 버전은 실험마다 `uv pip freeze` 로 `experiments/` 에 남긴다.
- torch 는 일부러 버전을 고정하지 않았다. PyPI 의 Windows torch 는 CPU 빌드이므로, 반드시 CUDA 인덱스로 먼저 설치한 뒤 이 파일들을 설치한다.
