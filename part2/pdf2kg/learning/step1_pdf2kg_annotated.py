"""
[1단계: 읽기] pdf2kg.py (Stage 1: PDF -> 문서 구조 그래프) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
docling 설명은 설치 소스(docling 2.141, docling-core 2.103, docling-hierarchical-pdf 0.2)로 확인했다.
toc_extract 주석본(step1_annotated.py), csv2kg 주석본에서 설명한 것은 짧게만 적었다.

흐름 (LLM 없음):
  PDF -docling-> 제목 level 복원 -> TOC 트리(부모 스택) -> 본문/표를 "지금 어느 제목 아래인가"로 매핑 -> JSON + Neo4j
  (Document)-[:HAS_TOC]->(TOC)-[:HAS_CHILD]->(TOC)-[:HAS_CHUNK]->(Chunk)-[:HAS_ELEMENT]->(TextElement|TableElement)
읽는 순서 권장: 맨 아래 __main__ -> process_pdf -> 나머지 함수

실행 위치: part2/pdf2kg  ->  python learning/step1_pdf2kg_annotated.py  (원본과 똑같이 동작. DB 를 지운다)
"""

# ============================================================
# import
# ============================================================
import os            # [출처] 표준 라이브러리. os.getenv 로 환경변수 읽기
import sys           # [출처] 표준 라이브러리. sys.exit(코드) 로 프로그램 종료
import json          # [출처] 표준 라이브러리. json.dump 로 JSON 파일 저장
from pathlib import Path   # [출처] 표준 라이브러리. 경로 객체
# [출처] 표준 라이브러리 dataclasses
#   dataclass: 속성만 적으면 생성자를 만들어 주는 데코레이터
#   asdict: dataclass 객체 -> 일반 딕셔너리로 변환하는 함수 (JSON 저장용)
from dataclasses import dataclass, asdict
# [출처] 표준 라이브러리 typing (타입 힌트. 실행에는 영향 없음)
#   List[X]: X 의 리스트 / Dict / Any: 아무 타입 / Optional[X]: X 또는 None / Tuple[...]: 튜플
from typing import List, Dict, Any, Optional, Tuple

from neo4j import GraphDatabase       # [출처] 외부 라이브러리 neo4j 드라이버
from dotenv import load_dotenv        # [출처] 외부 라이브러리 python-dotenv
# [출처] 외부 라이브러리 docling (toc_extract 주석본 참고)
from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
# [출처] 외부 라이브러리 docling-hierarchical-pdf. 제목 계층(level) 복원 후처리기
from hierarchical.postprocessor import ResultPostprocessor
# [출처] 외부 라이브러리 docling-core. 문서 안의 항목 종류(클래스)
#   SectionHeaderItem: 제목 / TextItem: 글 문단 / TableItem: 표
#   주의: SectionHeaderItem 은 TextItem 의 "자식 클래스" 다 (제목도 글의 한 종류).
#         그래서 isinstance(제목, TextItem) 도 True 가 된다 -> 아래에서 검사 순서가 중요하다
from docling_core.types.doc import SectionHeaderItem, TextItem, TableItem

load_dotenv()

# ============================================
# 환경 변수 설정
# ============================================

NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")

# ============================================
# 데이터 클래스: 단계 사이에 데이터를 넘기는 "그릇"
#   @dataclass 를 붙이면 TOCNode(toc_id=..., title=..., ...) 로 만들고 node.title 로 꺼낸다
#   "= 0", "= None" 처럼 기본값이 있는 속성은 만들 때 생략 가능 (기본값 있는 속성은 뒤쪽에 와야 한다)
# ============================================

@dataclass
class TOCNode:
    """목차 노드"""
    toc_id: str
    title: str
    level: int
    parent_id: Optional[str]      # 부모 목차 id. 최상위면 None
    is_leaf: bool                 # 자식 목차가 없으면 True
    page_start: int = 0
    page_end: int = 0             # 정의만 있고 이 파일에서는 채우지 않는다
    bbox: Optional[Tuple[float, float, float, float]] = None   # (왼쪽, 위, 오른쪽, 아래)


@dataclass
class TextElement:
    """텍스트 요소 (문단 하나)"""
    element_id: str
    toc_id: str          # 이 문단이 속한 목차
    text: str
    page: int
    bbox: Tuple[float, float, float, float]


@dataclass
class TableElement:
    """테이블 요소 (표 하나)"""
    element_id: str
    toc_id: str
    page: int
    bbox: Tuple[float, float, float, float]
    content: str         # 표를 마크다운 글로 바꾼 것


@dataclass
class DocumentStructure:
    """문서 구조 전체: 이 파일의 최종 결과물"""
    title: str
    pdf_path: str
    total_pages: int
    toc: List[TOCNode]
    texts: List[TextElement]
    tables: List[TableElement]


# ============================================
# 1단계: TOC 추출
# ============================================

# -> Tuple[List[TOCNode], Any] : "TOCNode 리스트와 무언가(변환 결과)를 튜플로 돌려준다" 는 타입 힌트
def extract_hierarchical_toc(pdf_path: str) -> Tuple[List[TOCNode], Any]:
    """[이 파일에서 정의] docling 으로 PDF 를 변환하고 제목들로 목차 트리를 만든다.
    [반환] (목차 노드 리스트, docling 변환 결과) -> 변환 결과는 2단계에서 다시 쓴다"""
    print(f"\n[1/3] TOC 추출 중: {pdf_path}")

    # ---- docling 변환 (toc_extract 주석본과 같다) ----
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False          # 글자가 살아 있는 PDF 라 OCR 끔

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend
            )
        }
    )

    print("   PDF 변환 중...")
    # converter.convert(경로) -> ConversionResult (.document = DoclingDocument, .pages = 페이지 리스트)
    result = converter.convert(pdf_path)

    print("   계층 구조 처리 중...")
    # ResultPostprocessor(result).process() -> 반환 없음. result.document 의 제목 level 과 트리를 제자리에서 고친다
    postprocessor = ResultPostprocessor(result)
    postprocessor.process()

    toc_nodes = []
    # 부모 스택: "지금까지 열려 있는 상위 제목들" 을 쌓아 두는 리스트. 맨 끝([-1])이 가장 최근 제목
    parent_stack = []
    toc_idx = 0

    # result.document.iterate_items()
    # [출처] docling-core DoclingDocument.iterate_items
    # [반환] (항목, 트리깊이) 튜플을 문서 순서대로. 원본 변수 이름은 prov 지만 실제로는 트리 깊이(정수)이고 여기서는 쓰지 않는다
    for item, prov in result.document.iterate_items():
        # isinstance(객체, 클래스): [출처] 파이썬 기본. 그 클래스(또는 자식 클래스)의 객체면 True
        if isinstance(item, SectionHeaderItem):
            # getattr(객체, "속성", 기본값): [출처] 파이썬 기본. 속성이 없으면 기본값 1
            level = getattr(item, 'level', 1)
            title = item.text.strip()            # 제목 글자, 앞뒤 공백 제거
            # or : 둘 중 하나라도 참이면 참. len(title) < 2 -> 한 글자 이하 제목은 버린다
            # [왜] docling 이 쪽번호나 기호를 제목으로 잘못 잡는 경우를 거른다
            if not title or len(title) < 2:
                continue                         # 이번 항목은 건너뛰기

            # f"toc_{toc_idx:03d}" : 서식 지정. 03d = 정수를 3자리로, 빈자리는 0 (5 -> "005")
            toc_id = f"toc_{toc_idx:03d}"

            # ---- 부모 찾기 (부모 스택 방식) ----
            # while 조건: -> 조건이 참인 동안 반복
            # 스택 맨 위 제목의 level 이 지금 제목 level 이상이면 꺼낸다(pop)
            #   예) 스택 [1장(1), 1.1절(2)] 에서 "2장(1)" 이 오면 1.1절, 1장을 모두 꺼낸다 -> 2장은 최상위
            # parent_stack[-1] : 리스트의 마지막 원소 (음수 인덱스는 뒤에서부터)
            # 리스트.pop() : [출처] 파이썬 기본 list 메서드. 마지막 원소를 꺼내서 지운다
            while parent_stack and parent_stack[-1]['level'] >= level:
                parent_stack.pop()

            # 값1 if 조건 else 값2 : 스택에 남은 게 있으면 맨 위가 부모, 없으면 None(최상위)
            parent_id = parent_stack[-1]['toc_id'] if parent_stack else None

            # ---- 페이지 번호, 위치(bbox) 꺼내기 ----
            page_num = 1
            bbox = None

            # item.prov
            # [출처] docling-core DocItem 의 속성
            # [값]   ProvenanceItem 의 리스트. 각 원소: page_no(페이지 번호), bbox(BoundingBox: l, t, r, b)
            # hasattr(객체, "속성"): [출처] 파이썬 기본. 속성이 있으면 True
            # [왜] 아래처럼 hasattr 를 겹겹이 쓰는 건 "혹시 모양이 다르면 에러 없이 기본값을 쓰자" 는 방어 코드
            if hasattr(item, 'prov') and item.prov:
                item_prov = item.prov
                # hasattr(x, '__len__') : 길이를 잴 수 있는(리스트 같은) 값인지
                if hasattr(item_prov, '__len__') and len(item_prov) > 0:
                    first_prov = item_prov[0]
                    if hasattr(first_prov, 'page_no'):
                        # 주의: docling 의 page_no 는 이미 1부터 센다 (docling-hierarchical-pdf 소스가
                        #       result.pages[prov.page_no - 1] 로 접근). 그래서 + 1 을 하면 실제보다 1 큰 페이지가 된다.
                        #       aibrief.pdf 의 1페이지 제목이 몇 페이지로 나오는지 확인해 보자 (GUIDE.md 참고)
                        page_num = first_prov.page_no + 1
                    if hasattr(first_prov, 'bbox'):
                        prov_bbox = first_prov.bbox
                        # BoundingBox 객체면 .l .t .r .b 속성으로, 리스트/튜플이면 그대로
                        if hasattr(prov_bbox, 'l'):
                            bbox = (prov_bbox.l, prov_bbox.t, prov_bbox.r, prov_bbox.b)
                        # isinstance(값, (A, B)) : A 또는 B 중 하나면 True
                        elif isinstance(prov_bbox, (list, tuple)) and len(prov_bbox) == 4:
                            bbox = tuple(prov_bbox)       # tuple(리스트): 튜플로 변환

            # dataclass 객체 만들기 (키워드 인자로)
            toc_node = TOCNode(
                toc_id=toc_id,
                title=title,
                level=level,
                parent_id=parent_id,
                is_leaf=True,              # 일단 leaf 로 두고, 자식이 생기면 아래에서 False 로 바꾼다
                page_start=page_num,
                bbox=bbox
            )
            toc_nodes.append(toc_node)

            # 부모가 있으면, 부모는 이제 자식이 생겼으므로 leaf 가 아니다
            # 참고: 리스트 전체를 처음부터 훑어 부모를 찾는다. 목차가 아주 많으면 딕셔너리로 찾는 게 빠르다
            if parent_id:
                for node in toc_nodes:
                    if node.toc_id == parent_id:
                        node.is_leaf = False       # dataclass 객체의 속성 바꾸기
                        break                      # break: 반복문을 즉시 빠져나간다

            # 지금 제목을 스택에 올린다 -> 다음 제목들의 부모 후보
            parent_stack.append({'toc_id': toc_id, 'level': level})
            toc_idx += 1

    # level 별 개수 (toc_extract 주석본의 distribution 과 같은 패턴)
    level_counts = {}
    for node in toc_nodes:
        level_counts[node.level] = level_counts.get(node.level, 0) + 1

    print(f"   TOC 노드 {len(toc_nodes)}개 추출")
    # sorted(딕셔너리.items()) : (키, 값) 쌍을 키 순서로 정렬한 리스트 / dict(...) : 다시 딕셔너리로
    print(f"   레벨 분포: {dict(sorted(level_counts.items()))}")

    return toc_nodes, result    # 쉼표로 두 값을 돌려주면 튜플 하나로 묶여 나간다


# ============================================
# 2단계: 요소 추출 및 매핑
# ============================================

def extract_and_map_elements(docling_result, toc_nodes: List[TOCNode]) -> Tuple[List[TextElement], List[TableElement]]:
    """[이 파일에서 정의] 문서를 위에서부터 다시 훑으며, 문단/표를 "직전에 나온 제목(목차)" 에 붙인다."""
    print(f"\n[2/3] 요소 추출 중...")

    all_texts = []
    all_tables = []

    text_idx = 0
    table_idx = 0

    # iter(리스트): [출처] 파이썬 기본. 반복자를 만든다. (이 변수는 만들기만 하고 아래에서 쓰지 않는다)
    toc_iterator = iter(toc_nodes)
    # {(제목, 페이지): [목차노드, ...]} : 같은 제목이 같은 페이지에 여러 번 나올 수 있어서 값이 리스트
    toc_map_by_title_page = {}

    for node in toc_nodes:
        key = (node.title, node.page_start)       # 튜플을 딕셔너리 키로 (리스트는 키가 될 수 없다)
        if key not in toc_map_by_title_page:
            toc_map_by_title_page[key] = []
        toc_map_by_title_page[key].append(node)

    # {level: 목차노드} : 지금 열려 있는 level 별 목차 (이 파일에서는 만들기만 하고 결과에는 쓰지 않는다)
    active_toc_stack = {}
    current_toc = None     # "지금 어느 제목 아래인가"

    print(f"   순차 처리 중...")

    item_count = 0
    for item, prov in docling_result.document.iterate_items():
        item_count += 1

        # 검사 순서가 중요: SectionHeaderItem 은 TextItem 의 자식이라, TextItem 을 먼저 검사하면 제목도 문단으로 처리된다
        if isinstance(item, SectionHeaderItem):
            title = item.text.strip()

            # 페이지 번호 (1단계와 같은 방어 코드, 같은 +1 주의)
            page_num = 1
            if hasattr(item, 'prov') and item.prov:
                item_prov = item.prov
                if hasattr(item_prov, '__len__') and len(item_prov) > 0:
                    first_prov = item_prov[0]
                    if hasattr(first_prov, 'page_no'):
                        page_num = first_prov.page_no + 1

            # 1단계에서 만든 목차 노드를 (제목, 페이지) 로 찾는다
            key = (title, page_num)
            if key in toc_map_by_title_page and toc_map_by_title_page[key]:
                # 리스트.pop(0): 맨 앞 원소를 꺼내서 지운다. 같은 키가 여러 개면 문서 순서대로 하나씩 쓰게 된다
                toc_node = toc_map_by_title_page[key].pop(0)
                level = toc_node.level

                # 딕셔너리 컴프리헨션 + 조건: 지금 level 보다 작은(상위) 것만 남기고, 지금 것을 넣는다
                active_toc_stack = {lv: node for lv, node in active_toc_stack.items() if lv < level}
                active_toc_stack[level] = toc_node

                current_toc = toc_node    # 이후 나오는 문단/표는 이 목차에 붙는다
            # 1단계에서 버린 제목(2자 미만)은 여기서도 못 찾으니 current_toc 가 바뀌지 않는다

        # elif: 위 if 가 거짓일 때만 검사하는 "그 밖의 경우"
        elif isinstance(item, TextItem):
            # 첫 제목이 나오기 전의 글(표지 등)은 붙일 목차가 없어서 버린다
            if current_toc is None:
                continue

            text = item.text.strip()
            # 5자 미만 텍스트(쪽번호, 머리말 조각 등)는 버린다
            if not text or len(text) < 5:
                continue

            page_num = 1
            bbox_tuple = (0, 0, 0, 0)

            if hasattr(item, 'prov') and item.prov:
                item_prov = item.prov
                if hasattr(item_prov, '__len__') and len(item_prov) > 0:
                    first_prov = item_prov[0]
                    if hasattr(first_prov, 'page_no'):
                        page_num = first_prov.page_no + 1
                    if hasattr(first_prov, 'bbox'):
                        prov_bbox = first_prov.bbox
                        if hasattr(prov_bbox, 'l'):
                            bbox_tuple = (prov_bbox.l, prov_bbox.t, prov_bbox.r, prov_bbox.b)

            all_texts.append(TextElement(
                element_id=f"text_{text_idx:04d}",     # text_0000, text_0001 ... (순번 기반 id)
                toc_id=current_toc.toc_id,             # "지금 어느 제목 아래인가" 를 기록
                text=text,
                page=page_num,
                bbox=bbox_tuple
            ))

            text_idx += 1

        elif isinstance(item, TableItem):
            if current_toc is None:
                continue

            page_num = 1
            bbox_tuple = (0, 0, 0, 0)

            if hasattr(item, 'prov') and item.prov:
                item_prov = item.prov
                if hasattr(item_prov, '__len__') and len(item_prov) > 0:
                    first_prov = item_prov[0]
                    if hasattr(first_prov, 'page_no'):
                        page_num = first_prov.page_no + 1
                    if hasattr(first_prov, 'bbox'):
                        prov_bbox = first_prov.bbox
                        if hasattr(prov_bbox, 'l'):
                            bbox_tuple = (prov_bbox.l, prov_bbox.t, prov_bbox.r, prov_bbox.b)

            table_text = ""
            try:
                # item.export_to_markdown(doc=문서)
                # [출처] docling-core TableItem 의 메서드
                # [입력] doc: 그 표가 속한 DoclingDocument (넘기지 않는 방식은 더 이상 권장되지 않는다는 경고가 뜬다)
                # [반환] 표를 마크다운 표 문자열로 ( | 열1 | 열2 | ... )
                # [왜]   LLM 이 읽기 좋은 글 형태로 바꿔 두면 Stage 2 에서 표 내용도 추출할 수 있다
                if hasattr(item, 'export_to_markdown'):
                    table_text = item.export_to_markdown(doc=docling_result.document)

            except Exception as e:
                pass      # pass: 아무것도 하지 않음. 실패하면 아래 기본 문구를 쓴다

            if not table_text:
                table_text = f"[Table {table_idx}]"

            all_tables.append(TableElement(
                element_id=f"table_{table_idx:04d}",
                toc_id=current_toc.toc_id,
                page=page_num,
                bbox=bbox_tuple,
                content=table_text
            ))

            table_idx += 1

    print(f"   텍스트 {len(all_texts)}개, 표 {len(all_tables)}개 추출")
    print(f"   {item_count}개 항목(헤더, 텍스트/테이블 요소) 처리")

    return all_texts, all_tables


# ============================================
# 3단계: 통계 계산 (사람이 확인할 요약 txt 파일)
# ============================================

def calculate_toc_stats(toc_nodes: List[TOCNode], texts: List[TextElement],
                       tables: List[TableElement], pdf_path: str):
    """[이 파일에서 정의] 목차 트리와 목차별 문단/표 개수를 output/<pdf이름>_toc_structure.txt 로 저장"""
    print(f"\n[3/3] 통계 계산 중...")

    # Path("output").mkdir(exist_ok=True)
    # [출처] pathlib. 폴더 만들기. exist_ok=True: 이미 있어도 에러 내지 않기
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # Path(pdf_path).stem : 확장자를 뺀 파일 이름 ("aibrief.pdf" -> "aibrief")
    output_path = output_dir / f"{Path(pdf_path).stem}_toc_structure.txt"

    # open(경로, 'w') : 쓰기 모드(기존 내용은 덮어씀). f.write(문자열): 파일에 쓰기 (print 와 달리 줄바꿈 자동 아님)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write(f"목차 구조 및 콘텐츠 분포: {Path(pdf_path).name}\n")     # .name: 확장자 포함 파일 이름
        f.write("="*80 + "\n\n")

        f.write("목차 계층 구조:\n")
        f.write("-"*80 + "\n")

        for node in toc_nodes:
            indent = "  " * (node.level - 1)       # level 만큼 들여쓰기
            # sum(1 for t in texts if 조건) : 조건에 맞는 개수 세기 (제너레이터 식: 리스트를 만들지 않고 하나씩 셈)
            t_count = sum(1 for t in texts if t.toc_id == node.toc_id)
            tb_count = sum(1 for tb in tables if tb.toc_id == node.toc_id)
            total = t_count + tb_count

            leaf_mark = "[L]" if node.is_leaf else "[P]"     # Leaf / Parent
            content_info = f"[T:{t_count} Tb:{tb_count}]" if total > 0 else ""

            f.write(f"{indent}{leaf_mark} [{node.toc_id}] {node.title} (p.{node.page_start}) {content_info}\n")

        f.write("\n\n")

        # 내용(문단 또는 표)이 하나라도 붙은 목차 개수
        content_tocs = sum(1 for node in toc_nodes
                          if sum(1 for t in texts if t.toc_id == node.toc_id) +
                             sum(1 for tb in tables if tb.toc_id == node.toc_id) > 0)

        f.write(f"\nTotal: {len(toc_nodes)} TOC nodes, {content_tocs} with content\n")
        f.write(f"Elements: {len(texts)} texts, {len(tables)} tables\n")

    print(f"   TOC별 콘텐츠 구조 저장: {output_path}")


# ============================================
# 메인 처리 함수
# ============================================

def process_pdf(pdf_path: str) -> DocumentStructure:
    """[이 파일에서 정의] 1~3단계를 차례로 실행해 DocumentStructure 하나로 묶는다."""
    # 튜플 반환값을 두 변수로 풀어서 받기
    toc_nodes, docling_result = extract_hierarchical_toc(pdf_path)  # toc: table of contents

    if not toc_nodes:
        print("\n경고: TOC를 추출할 수 없습니다!")
        return None     # 주의: 타입 힌트는 DocumentStructure 지만 실패하면 None 을 돌려준다 (호출한 쪽에서 if 로 확인)

    texts, tables = extract_and_map_elements(docling_result, toc_nodes)

    calculate_toc_stats(toc_nodes, texts, tables, pdf_path)

    doc_structure = DocumentStructure(
        title=Path(pdf_path).stem,
        pdf_path=pdf_path,
        # docling_result.document.pages: 문서의 페이지 정보(딕셔너리, 키 = 1부터 시작하는 페이지 번호). len 은 페이지 수
        total_pages=len(docling_result.document.pages),
        toc=toc_nodes,
        texts=texts,
        tables=tables
    )

    print("\n" + "="*70)
    print("처리 완료")
    print("="*70)
    print(f"   TOC: {len(toc_nodes)}개")
    print(f"   텍스트: {len(texts)}개")
    print(f"   표: {len(tables)}개")

    return doc_structure


# ============================================
# JSON 저장
# ============================================

def save_to_json(doc_structure: DocumentStructure, output_path: str):
    """[이 파일에서 정의] 문서 구조를 JSON 파일로 저장 (중간 결과 확인용)"""
    data = {
        "title": doc_structure.title,
        "pdf_path": doc_structure.pdf_path,
        "total_pages": doc_structure.total_pages,
        # asdict(객체): [출처] 표준 라이브러리 dataclasses. dataclass 객체 -> 딕셔너리 (json 은 dataclass 를 직접 저장 못 한다)
        "toc": [asdict(node) for node in doc_structure.toc],
        # [:100] : 텍스트는 앞 100개만 저장한다 (파일 크기 때문으로 보인다. Neo4j 에는 전부 들어간다)
        "texts": [asdict(elem) for elem in doc_structure.texts[:100]],
        "tables": [asdict(elem) for elem in doc_structure.tables]
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)    # 한글 그대로, 2칸 들여쓰기

    print(f"\nJSON 저장: {output_path}")


# ============================================
# Neo4j 저장
# ============================================

def save_to_neo4j(doc_structure: DocumentStructure, uri, user, password):
    """[이 파일에서 정의] 노드를 종류별로 먼저 모두 만들고, 관계는 노드에 저장한 id 값을 맞춰 한 번에 연결한다."""
    print(f"\nNeo4j 저장 중: {uri}")

    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        # 1. 기존 데이터 삭제
        driver.execute_query(
            "MATCH (n) DETACH DELETE n",
            database_=NEO4J_DATABASE
        )
        print("   step 1 - 기존 데이터 삭제")

        # 2. Document 노드 생성
        # execute_query(쿼리, title=..., pdf_path=..., ...): 쿼리의 $title, $pdf_path 에 값이 들어간다
        driver.execute_query(
            """
            CREATE (d:Document {
                title: $title,
                pdf_path: $pdf_path,
                total_pages: $total_pages
            })
            """,
            title=doc_structure.title,
            pdf_path=doc_structure.pdf_path,
            total_pages=doc_structure.total_pages,
            database_=NEO4J_DATABASE
        )
        print(f"   step 2 - Document 노드 생성")

        # 3. TOC 노드 생성
        level_labels = {1: "Level1", 2: "Level2", 3: "Level3", 4: "Level4", 5: "Level5"}

        # 트랜잭션 함수: 첫 인자 tx 는 드라이버가 넣어 준다 (txt2kg 주석본 참고)
        def create_toc_nodes(tx, toc_list):
            """트랜잭션 함수: TOC 노드 생성"""
            for node in toc_list:
                # 딕셔너리.get(키, 기본값): level 6 이상이면 "Level6" 같은 이름을 만든다
                label = level_labels.get(node.level, f"Level{node.level}")
                # (t:Level2:TOC {...}) : 레이블을 두 개 붙인다. "모든 목차"(TOC)와 "특정 깊이"(Level2)로 둘 다 찾을 수 있게
                # 레이블은 파라미터로 못 넘겨서 f-string, 속성 중괄호는 {{ }}
                query = f"""
                    CREATE (t:{label}:TOC {{
                        toc_id: $toc_id,
                        title: $title,
                        level: $level,
                        parent_id: $parent_id,
                        is_leaf: $is_leaf,
                        page_start: $page_start
                    }})
                """
                tx.run(query,
                       toc_id=node.toc_id,
                       title=node.title,
                       level=node.level,
                       parent_id=node.parent_id,
                       is_leaf=node.is_leaf,
                       page_start=node.page_start)
            return len(toc_list)

        # with driver.session(...) as session: 블록이 끝나면 세션 자동 종료
        # session.execute_write(함수, 인자): 함수 안의 쿼리들을 하나의 쓰기 트랜잭션으로 (txt2kg 주석본 참고)
        with driver.session(database=NEO4J_DATABASE) as session:
            toc_count = session.execute_write(create_toc_nodes, doc_structure.toc)
            print(f"   step 3 - TOC 노드 {toc_count}개 생성")

        # 4. TOC 관계 생성: 노드에 저장해 둔 parent_id 와 toc_id 를 맞춰 한 번에 연결
        # MATCH (parent:TOC), (child:TOC) WHERE ... : 모든 TOC 쌍 중 조건에 맞는 쌍
        #   (목차가 아주 많으면 느려질 수 있다. GUIDE.md 생각해 볼 점 1)
        driver.execute_query(
            """
            MATCH (parent:TOC), (child:TOC)
            WHERE child.parent_id = parent.toc_id
            CREATE (parent)-[:HAS_CHILD]->(child)
            """,
            database_=NEO4J_DATABASE
        )
        print(f"   step 4 - TOC 관계 생성")

        # 5. Chunk 노드 생성: 목차 하나 아래의 문단 + 표를 이어 붙인 덩어리 하나
        chunks_to_create = []
        for node in doc_structure.toc:
            # 리스트 컴프리헨션 + 조건: 이 목차에 속한 문단/표만
            toc_texts = [t for t in doc_structure.texts if t.toc_id == node.toc_id]
            toc_tables = [t for t in doc_structure.tables if t.toc_id == node.toc_id]

            if len(toc_texts) + len(toc_tables) > 0:
                content_parts = [t.text for t in toc_texts]
                content_parts.extend([f"[Table {t.element_id}]\n{t.content}" for t in toc_tables])
                # "\n\n".join(리스트): 빈 줄 하나를 사이에 두고 이어 붙이기
                combined_text = "\n\n".join(content_parts)

                chunks_to_create.append({
                    # len(chunks_to_create): 지금까지 만든 개수 = 다음 순번
                    "chunk_id": f"chunk_{len(chunks_to_create):04d}",
                    "toc_id": node.toc_id,
                    "content": combined_text,
                    "text_count": len(toc_texts),
                    "table_count": len(toc_tables)
                })

        def create_chunk_nodes(tx, chunks):
            """트랜잭션 함수: Chunk 노드 생성"""
            for chunk in chunks:
                # **chunk: 딕셔너리를 키워드 인자로 펼친다 -> chunk_id=..., toc_id=..., content=... 와 같다
                tx.run("""
                    CREATE (c:Chunk {
                        chunk_id: $chunk_id,
                        toc_id: $toc_id,
                        content: $content,
                        text_count: $text_count,
                        table_count: $table_count
                    })
                """, **chunk)
            return len(chunks)

        with driver.session(database=NEO4J_DATABASE) as session:
            chunk_count = session.execute_write(create_chunk_nodes, chunks_to_create)
            print(f"   step 5 - Chunk 노드 {chunk_count}개 생성")

        # 6. TOC-Chunk 관계 생성 (4번과 같은 "id 맞추기" 방식)
        driver.execute_query(
            """
            MATCH (toc:TOC), (c:Chunk)
            WHERE c.toc_id = toc.toc_id
            CREATE (toc)-[:HAS_CHUNK]->(c)
            """,
            database_=NEO4J_DATABASE
        )
        print(f"   step 6 - TOC-Chunk 관계 생성")

        # 7. TextElement 노드 생성 (100개씩 배치로 UNWIND)
        def create_text_elements(tx, texts_batch):
            """트랜잭션 함수: TextElement 배치 생성"""
            # UNWIND $texts AS text: 리스트를 한 행씩 풀어 반복 (csv2kg 주석본 참고)
            tx.run("""
                UNWIND $texts AS text
                CREATE (t:TextElement {
                    element_id: text.element_id,
                    toc_id: text.toc_id,
                    content: text.text,
                    page: text.page
                })
            """, texts=texts_batch)

        with driver.session(database=NEO4J_DATABASE) as session:
            # range(시작, 끝, 간격): [출처] 파이썬 기본. 0, 100, 200, ... (끝은 포함 안 함)
            for i in range(0, len(doc_structure.texts), 100):
                batch = doc_structure.texts[i:i+100]     # 슬라이싱: i 번째부터 100개
                batch_data = [{
                    "element_id": t.element_id,
                    "toc_id": t.toc_id,
                    "text": t.text,
                    "page": t.page
                } for t in batch]
                # 배치마다 별도 트랜잭션 -> 너무 큰 트랜잭션 하나를 피한다
                session.execute_write(create_text_elements, batch_data)
        print(f"   step 7 - TextElement 노드 {len(doc_structure.texts)}개 생성")

        # 8. TableElement 노드 생성
        if doc_structure.tables:
            def create_table_elements(tx, tables_list):
                """트랜잭션 함수: TableElement 생성"""
                for table in tables_list:
                    tx.run("""
                        CREATE (t:TableElement {
                            element_id: $element_id,
                            toc_id: $toc_id,
                            page: $page,
                            content: $content
                        })
                    """, element_id=table.element_id,
                         toc_id=table.toc_id,
                         page=table.page,
                         content=table.content)

            with driver.session(database=NEO4J_DATABASE) as session:
                session.execute_write(create_table_elements, doc_structure.tables)
            print(f"   step 8 - TableElement 노드 {len(doc_structure.tables)}개 생성")

        # 9. Chunk-Element 관계 생성
        # RETURN count(*) as cnt: 만든 관계 수를 결과로 받는다 -> .records[0]["cnt"]
        text_rels_result = driver.execute_query(
            """
            MATCH (c:Chunk), (t:TextElement)
            WHERE t.toc_id = c.toc_id
            CREATE (c)-[:HAS_ELEMENT]->(t)
            RETURN count(*) as cnt
            """,
            database_=NEO4J_DATABASE
        )
        text_rels = text_rels_result.records[0]["cnt"]

        table_rels_result = driver.execute_query(
            """
            MATCH (c:Chunk), (t:TableElement)
            WHERE t.toc_id = c.toc_id
            CREATE (c)-[:HAS_ELEMENT]->(t)
            RETURN count(*) as cnt
            """,
            database_=NEO4J_DATABASE
        )
        table_rels = table_rels_result.records[0]["cnt"]

        print(f"   step 9 - Chunk-Element 관계 생성: 텍스트 {text_rels}개, 표 {table_rels}개")

        # 10. Document-TOC 관계 생성: 부모가 없는(최상위) 목차만 문서에 연결
        # IS NULL: 값이 없는지 검사 (Cypher 에서는 = null 이 아니라 IS NULL 을 쓴다)
        driver.execute_query(
            """
            MATCH (d:Document), (toc:TOC)
            WHERE toc.parent_id IS NULL
            CREATE (d)-[:HAS_TOC]->(toc)
            """,
            database_=NEO4J_DATABASE
        )

    finally:
        driver.close()     # 에러가 나도 연결은 닫는다

    print(f"\nNeo4j 저장 완료!")


# ============================================
# 메인 (함수로 감싸지 않고 if __name__ 블록에 바로 썼다)
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("PDF 지식 그래프 추출 - (1) 목차 및 텍스트")
    print("=" * 50)

    pdf_path = "aibrief.pdf"       # 상대 경로: 실행 위치(part2/pdf2kg) 기준

    if not Path(pdf_path).exists():
        print(f"오류: {pdf_path} 파일을 찾을 수 없습니다")
        # sys.exit(1): [출처] 표준 라이브러리 sys. 프로그램 종료. 0 = 정상, 0 이 아니면 "실패로 끝났다" 는 뜻
        sys.exit(1)

    doc_structure = process_pdf(pdf_path)

    # None 이 아니면(처리 성공) 저장
    if doc_structure:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        output_path = output_dir / f"{Path(pdf_path).stem}_structure.json"
        save_to_json(doc_structure, str(output_path))      # str(Path): 경로를 문자열로

        NEO4J_URI = os.getenv("NEO4J_URI")
        NEO4J_USER = os.getenv("NEO4J_USERNAME")
        NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

        # 세 값이 모두 있을 때만 Neo4j 에 저장 (없으면 JSON 까지만)
        if NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD:
            save_to_neo4j(doc_structure, uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
