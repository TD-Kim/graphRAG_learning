"""
[1단계: 읽기] part2/pdf2kg/toc_extract.py 의 "왜" 주석 버전

목적: PDF 의 "목차(TOC) 계층"을 뽑아서 그래프의 뼈대(Document -> TOC -> Chunk)로 쓰기 위한 사전 실험.
  - docling 이 PDF 를 읽으면 제목(SectionHeader)은 찾아 주지만, level 이 제대로 구분되지 않는 경우가 많다(이 실습에서 전/후 비교로 직접 확인한다).
  - docling-hierarchical-pdf 의 ResultPostprocessor 가 글자 크기/위치 등으로 level 을 다시 매긴다.
  - 이 파일은 "전/후 level 이 어떻게 바뀌는지" 눈으로 확인하는 테스트 스크립트다.

원본과 다른 점 (동작은 같고 읽기 쉽게 정리):
  1) 제목을 모으는 반복 코드를 collect_headers() 로 합쳤다.
  2) 원본은 __main__ 에서 pdf_path 만 정해 두고 함수를 호출하지 않아서 실행해도 아무 일도 없다.
     여기서는 마지막에 호출한다.
  3) 원본의 "[3단계] parent 관계 설정"은 출력만 하고 미완성이다. step3 에서 직접 구현해 보자.

실행 위치: part2/pdf2kg  ->  python learning/step1_annotated.py
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption
from docling_core.types.doc import SectionHeaderItem
from hierarchical.postprocessor import ResultPostprocessor


@dataclass
class TOCNode:
    """목차 한 줄. 나중에 Neo4j 의 TOC 노드가 된다."""

    toc_id: str                 # 그래프에서 노드를 식별하는 키
    title: str
    level: int                  # 1 = 가장 큰 제목
    parent_id: Optional[str]    # 상위 제목. 이 값이 HAS_CHILD 관계가 된다. 최상위는 None
    is_leaf: bool               # 하위 제목이 없으면 True -> 이 노드 아래에 본문 Chunk 를 붙인다
    page_start: int = 0
    bbox: Optional[Tuple[float, float, float, float]] = None  # 페이지 위 위치(좌,상,우,하)


def collect_headers(result) -> list[dict]:
    """변환 결과에서 SectionHeaderItem 만 골라 (텍스트, level) 로 모은다."""
    headers = []
    # iterate_items() 는 문서의 모든 요소를 (item, 위치정보) 로 읽는 순서대로 돌려준다.
    for item, _prov in result.document.iterate_items():
        if isinstance(item, SectionHeaderItem):  # 문단/표/그림은 건너뛰고 제목만
            headers.append(
                {
                    "text": item.text.strip()[:50],       # 출력용으로 50자만
                    "level": getattr(item, "level", None),  # 속성이 없을 수도 있어 getattr 로 안전하게
                }
            )
    return headers


def toc_extract_tester(pdf_path: str):
    print("=" * 80)
    print("Docling > ResultPostprocessor > ToC 추출 동작 테스트")
    print("=" * 80)
    print(f"\nPDF 파일: {pdf_path}")

    # ---------- [1단계] docling 으로 변환 ----------
    print("\n[1단계] docling - PDF 변환 중...")
    pipeline_options = PdfPipelineOptions()
    # OCR(이미지 글자 인식)을 끈다. 텍스트가 살아 있는 PDF 는 OCR 이 필요 없고 훨씬 빨라진다.
    # 스캔본 PDF 라면 True 로 켜야 한다.
    pipeline_options.do_ocr = False

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                # pypdfium2 백엔드: 가볍고 빠른 PDF 렌더러
                backend=PyPdfiumDocumentBackend,
            )
        }
    )
    result = converter.convert(pdf_path)
    print("변환 완료")

    # ---------- 후처리 "전" ----------
    print("\ndocling-hierarchical-pdf 실행 전 상태")
    print("-" * 80)
    before = collect_headers(result)
    print(f"섹션 헤더 개수: {len(before)}개")
    print("\n처음 5개 섹션 헤더:")
    for i, h in enumerate(before[:5], 1):
        print(f'  {i}. "{h["text"]}"  (level={h["level"]})')

    # ---------- [2단계] 계층 복원 ----------
    print("\n[2단계] docling-hierarchical-pdf - ResultPostprocessor 실행 중...")
    # process() 는 result 를 "제자리에서" 수정한다. (반환값을 받는 게 아니라 result 가 바뀐다)
    # 그래서 위에서 before 를 먼저 리스트로 복사해 둔 것이다. 안 그러면 비교할 "전"이 사라진다.
    ResultPostprocessor(result).process()

    print("\nResultPostprocessor 실행 후 상태")
    print("-" * 80)
    after = collect_headers(result)
    print(f"섹션 헤더 개수: {len(after)}개")

    # ---------- 변화 분석 ----------
    print("\n[변화 분석]")
    print("=" * 80)

    # level 별로 제목이 몇 개인지: 1 하나만 있다면 계층 복원이 안 된 것이다.
    distribution: dict[int, int] = {}
    for h in after:
        if h["level"] is not None:
            distribution[h["level"]] = distribution.get(h["level"], 0) + 1
    print("\nlevel 분포:")
    for level in sorted(distribution):
        print(f"   - Level {level}: {distribution[level]}개")

    # 앞쪽 20개만 전/후 level 을 나란히 비교. 같은 위치끼리 비교하려면 두 리스트 길이/순서가 같아야 한다.
    for i in range(min(20, len(before))):
        b, a = before[i], after[i]
        print(f'\n{i + 1}. "{b["text"]}"')
        if b["level"] != a["level"]:
            print(f"   level 변화: {b['level']} -> {a['level']} ⭐")
        else:
            print(f"   level: {a['level']} (변화 없음)")

    # ---------- [3단계] 미완성: parent 관계 ----------
    # 여기서부터가 다음 단계(pdf2kg.py)의 일이다:
    #   level 로 TOCNode.parent_id 를 정하고, is_leaf 를 계산한 뒤 Neo4j 에 HAS_CHILD 로 저장.
    print("\n\n[3단계] level을 기반으로 parent 관계 설정")
    print("=" * 80)
    print("(미완성: step3_comments_only.py 에서 직접 구현해 보세요)")


if __name__ == "__main__":
    # 이 파일 기준으로 PDF 위치를 잡아서 어디서 실행해도 동작하게 한다.
    pdf_path = Path(__file__).resolve().parent.parent / "aibrief.pdf"
    toc_extract_tester(str(pdf_path))
