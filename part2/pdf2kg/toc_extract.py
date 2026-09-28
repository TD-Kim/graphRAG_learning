from dataclasses import dataclass
from pprint import pprint
from typing import Optional, Tuple

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import (DocumentConverter, InputFormat,
                                        PdfFormatOption)
from docling_core.types.doc import SectionHeaderItem
from hierarchical.postprocessor import ResultPostprocessor


@dataclass
class TOCNode:
    """ 목차 노드 """
    toc_id: str
    title: str
    level: int
    parent_id: Optional[str]
    is_leaf: bool
    page_start: int = 0
    bbox: Optional[Tuple[float, float, float, float]] = None
    

def toc_extract_tester(pdf_path: str):
    print("="*80)
    print("Docling > ResultPostprocessor > ToC 추출 동작 테스트")
    print("="*80)
    
    print(f"\nPDF 파일: {pdf_path}")
    
    print("\n[1단계] docling - PDF 변환 중...")
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend
            )
        }
    )
    
    result = converter.convert(pdf_path)
    print("변환 완료")
    
    print("\ndocling-hierarchical-pdf 실행 전 상태")
    print("-"*80)
    
    section_headers_before = []
    # pprint(type(result))
    # pprint(vars(result))
    for item, prov in result.document.iterate_items():
        if isinstance(item, SectionHeaderItem):
            section_headers_before.append({
                'text': item.text.strip()[:50],
                'level': getattr(item, 'level', None),
                'has_level_attr': hasattr(item, 'level'),
                'type': type(item).__name__
            })
    
    print(f"섹션 헤더 개수: {len(section_headers_before)}개")
    print("\n처음 5개 섹션 헤더:")
    for i, header in enumerate(section_headers_before[:5], 1):
        print(f"  {i}. \"{header['text']}\"")
        print(f"     - level 값: {header['level']}")
        
    print("\n[2단계] docling-hierarchical-pdf - ResultPostprocessor 실행 중...")
    postprocessor = ResultPostprocessor(result)
    postprocessor.process()
    
    print("\nResultPostprocessor 실행 후 상태")
    print("-"*80)
    
    section_headers_after = []
    for item, prov in result.document.iterate_items():
        if isinstance(item, SectionHeaderItem):
            section_headers_after.append({
                'text': item.text.strip()[:50],
                'level': getattr(item, 'level', None),
                'has_level_attr': hasattr(item, 'level'),
                'type': type(item).__name__
            })
            
    print(f"섹션 헤더 개수: {len(section_headers_after)}개")
    print("\n처음 5개 섹션 헤더:")
    for i, header in enumerate(section_headers_after[:5], 1):
        print(f"  {i}. \"{header['text']}\"")
        print(f"     - level 값: {header['level']}")

    print("\n[변화 분석]")
    print("="*80)
    
    level_distribution = {}
    for header in section_headers_after:
        if header['level'] is not None:
            level = header['level']
            level_distribution[level] = level_distribution.get(level, 0) + 1
            
    print(f"\nlevel 분포:")
    for level in sorted(level_distribution.keys()):
        count = level_distribution[level]
        print(f"   - Level {level}: {count}개")
        
    for i in range(min(20, len(section_headers_before))):
        before = section_headers_before[i]
        after = section_headers_after[i]
        
        print(f"\n{i+1}. \"{before['text']}\"")
        
        if before['level'] != after['level']:
            print(f"   level 변화: {before['level']} -> {after['level']} ⭐")
        else:
            print(f"   level: {after['level']} (변화 없음)")
            
    print("\n\n[3단계] level을 기반으로 parent 관계 설정")
    print("="*80)
     
    


if __name__ == "__main__":
    pdf_path = "aibrief.pdf"
    
    toc_extract_tester(pdf_path)