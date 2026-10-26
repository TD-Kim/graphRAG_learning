"""
[2단계: 빈칸 채우기] toc_extract.py 의 핵심(변환 -> 제목 수집 -> 후처리 -> 전/후 비교)을 채운다.

방법:
  1. TODO 를 위에서부터 채운다.
  2. 막히면 step1_annotated.py (정답은 원본 toc_extract.py).
  3. 실행해서 후처리 후 level 분포가 1 하나가 아니라 여러 단계로 나오면 성공.

실행 위치: part2/pdf2kg  ->  python learning/step2_fill_in.py
"""
from pathlib import Path

from cv2 import sort
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import (DocumentConverter, InputFormat,
                                        PdfFormatOption)
from docling_core.types.doc import SectionHeaderItem
from hierarchical.postprocessor import ResultPostprocessor


def collect_headers(result) -> list[dict]:
    headers = []
    # TODO 1: result.document.iterate_items() 는 (item, prov) 를 돌려준다.
    #         item 이 SectionHeaderItem 일 때만 {"text": 앞 50자, "level": item 의 level} 을 추가한다.
    #         (level 속성이 없을 수도 있다. getattr 의 기본값을 쓰자)
    for item, _depth in result.document.iterate_items():
        if isinstance(item, SectionHeaderItem):
            headers.append(
                {
                    "text": item.text.strip()[:50],
                    "level": getattr(item, "level", None)
                }
            )
            
    return headers


def toc_extract_tester(pdf_path: str):
    # TODO 2: 텍스트 PDF 는 OCR 이 필요 없다. PdfPipelineOptions 를 만들고 OCR 을 끈다.
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False

    # TODO 3: DocumentConverter 를 만든다.
    #   format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=..., backend=PyPdfiumDocumentBackend)}
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend
            )
        }
    )

    # TODO 4: PDF 를 변환한다. (converter.convert)
    result = converter.convert(pdf_path)

    # TODO 5: 후처리 "전" 제목 목록을 먼저 저장한다.
    #   왜 후처리 전에 저장해야 할까? (힌트: process() 는 result 를 제자리에서 바꾼다)
    before = collect_headers(result)

    # TODO 6: ResultPostprocessor(result).process() 로 계층(level)을 복원한다.
    for i, h in enumerate(before[:5], 1):
        print(f'  {i}. "{h["text"]}"  (level={h["text"]})')
    
    ResultPostprocessor(result).process()

    # TODO 7: 후처리 "후" 제목 목록을 저장하고, level 별 개수를 세어 출력한다.
    after = collect_headers(result)
    distribution: dict[int, int] = {}
    for h in after:
        if h["level"] is not None:
            distribution[h["level"]] = distribution.get(h["level"], 0) + 1
    
    # 출력 예) Level 1: 8개 / Level 2: 31개 / Level 3: 12개
    for level in sorted(distribution):
        print(f"  - Level {level}: {distribution["level"]}개")

    # TODO 8: 앞의 10개 제목에 대해 level 이 바뀐 것만 "제목: 1 -> 2" 로 출력한다.
    for i in range(min(20, len(before))):
            b, a = before[i], after[i]
            print(f'\n{i + 1}. "{b["text"]}"')
            if b["level"] != a["level"]:
                print(f"   level 변화: {b["level"]} -> {a["level"]} ⭐")
            else:
                print(f"   level: {a['level']} (변화 없음)")
    

if __name__ == "__main__":
    pdf_path = Path(__file__).resolve().parent.parent / "aibrief.pdf"
    toc_extract_tester(str(pdf_path))
