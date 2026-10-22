"""
[1단계: 읽기] part2/pdf2kg/toc_extract.py 의 상세 주석 버전

목적: PDF 의 "목차(TOC) 계층"을 뽑아서 그래프의 뼈대(Document -> TOC -> Chunk)로 쓰기 위한 사전 실험.
  - docling 이 PDF 를 읽으면 제목(SectionHeader)은 찾아 주지만 level 이 제대로 구분되지 않는 경우가 많다.
  - docling-hierarchical-pdf 의 ResultPostprocessor 가 level 을 다시 매긴다.
  - 이 파일은 "전/후 level 이 어떻게 바뀌는지" 눈으로 확인하는 테스트 스크립트다.

주석 읽는 법 (함수나 문법이 처음 나올 때마다 아래 형식으로 적었다)
  [출처] 어디서 온 것인가: 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나
  [반환] 무엇이 나오나
  [왜]   여기서 왜 쓰나
  라이브러리 함수 설명은 설치된 소스(docling 2.141, docling-core 2.103, docling-hierarchical-pdf 0.2)를 직접 확인해서 썼다.

원본과 다른 점 (동작은 같고 읽기 쉽게 정리):
  1) 제목을 모으는 반복 코드를 collect_headers() 로 합쳤다.
  2) 원본은 __main__ 에서 pdf_path 만 정해 두고 함수를 호출하지 않아서 실행해도 아무 일도 없다. 여기서는 호출한다.
  3) 원본의 "[3단계] parent 관계 설정"은 출력만 하고 미완성이다. step3 에서 직접 구현해 보자.

실행 위치: part2/pdf2kg  ->  python learning/step1_annotated.py
"""

# ============================================================
# import: 다른 곳에 정의된 것을 가져다 쓰겠다는 선언
#   import 모듈         -> 모듈.이름 으로 사용
#   from 모듈 import 이름 -> 이름 만으로 바로 사용
# ============================================================

# [출처] 파이썬 표준 라이브러리 dataclasses
# [왜]   클래스 위에 @dataclass 를 붙이면, 속성만 적어도 __init__(생성자) 등을 자동으로 만들어 준다. 아래 TOCNode 참고
from dataclasses import dataclass

# [출처] 파이썬 표준 라이브러리 pathlib
# [왜]   파일 경로를 문자열 대신 객체로 다룬다. Path("a") / "b" 처럼 / 연산자로 경로를 이어 붙일 수 있다
from pathlib import Path

# [출처] 파이썬 표준 라이브러리 typing  (타입 힌트용. 실행 결과에는 영향 없고, 사람과 편집기가 읽는 설명)
#   Optional[X] = "X 이거나 None"
#   Tuple[float, float] = "float 2개짜리 튜플"
from typing import Optional, Tuple

# [출처] 외부 라이브러리 docling (pip install docling)  — PDF 같은 문서를 구조화된 데이터로 바꿔 주는 IBM 의 오픈소스
#   PyPdfiumDocumentBackend : PDF 를 읽는 엔진 중 하나(pypdfium2 기반). 가볍고 빠르다
#   PdfPipelineOptions      : PDF 변환 설정 묶음 (OCR 사용 여부 등)
#   DocumentConverter       : 변환기 본체. .convert() 를 부른다
#   InputFormat             : 입력 형식 목록 (InputFormat.PDF, InputFormat.DOCX ...)
#   PdfFormatOption         : "PDF 는 이 설정과 이 엔진으로" 를 묶어 주는 객체
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption

# [출처] 외부 라이브러리 docling-core (docling 을 설치하면 같이 설치됨)
#   SectionHeaderItem : 문서 안의 "제목" 항목을 나타내는 클래스. text(글자), level(제목 단계, 기본값 1), prov(위치 정보) 를 가진다
from docling_core.types.doc import SectionHeaderItem

# [출처] 외부 라이브러리 docling-hierarchical-pdf (pip install docling-hierarchical-pdf, 패키지 이름은 hierarchical)
#   ResultPostprocessor : docling 변환 결과의 제목 계층(level)을 다시 계산해 주는 후처리기
from hierarchical.postprocessor import ResultPostprocessor


# ============================================================
# @dataclass: 데이터를 담는 그릇(클래스)을 간단히 만드는 문법
#   TOCNode(toc_id="toc_001", title="개요", level=1, parent_id=None, is_leaf=True) 처럼 만들 수 있고
#   node.title 처럼 꺼낼 수 있다.  "= 0" 처럼 기본값이 있는 속성은 생략 가능
# ============================================================
@dataclass
class TOCNode:
    """목차 한 줄. 나중에 Neo4j 의 TOC 노드가 된다. (이 파일에서는 정의만 하고 아직 쓰지 않는다)"""

    toc_id: str                 # 그래프에서 노드를 식별하는 키
    title: str
    level: int                  # 1 = 가장 큰 제목
    parent_id: Optional[str]    # 상위 제목 id. 최상위면 None. 이 값이 그래프의 HAS_CHILD 관계가 된다
    is_leaf: bool               # 하위 제목이 없으면 True -> 이 노드 아래에 본문 Chunk 를 붙인다
    page_start: int = 0
    bbox: Optional[Tuple[float, float, float, float]] = None  # 페이지 위 위치(왼쪽, 위, 오른쪽, 아래)


# ============================================================
# def 함수이름(매개변수: 타입) -> 반환타입:   함수 정의
#   "-> list[dict]" 는 "딕셔너리들의 리스트를 돌려준다" 는 타입 힌트(설명)
# ============================================================
def collect_headers(result) -> list[dict]:
    """[이 파일에서 정의] 변환 결과에서 제목(SectionHeaderItem)만 골라 {"text", "level"} 딕셔너리 리스트로 돌려준다."""
    headers = []  # 빈 리스트. 아래에서 append 로 하나씩 채운다

    # result.document.iterate_items()
    # [출처] docling-core 의 DoclingDocument.iterate_items 메서드
    #        result      = converter.convert() 가 돌려준 ConversionResult (docling)
    #        .document   = 그 안의 DoclingDocument (문서 전체: 제목, 문단, 표, 그림 ...)
    # [입력] 없음 (선택 인자로 page_no=3 처럼 특정 페이지만 볼 수도 있다)
    # [반환] (항목, 깊이) 튜플을 문서 순서대로 하나씩 내보내는 반복자(iterator)
    #        항목 = SectionHeaderItem(제목), TextItem(문단), TableItem(표) ... 중 하나
    #        깊이 = 문서 트리에서의 깊이(정수). 제목 level 과는 다른 값이다
    # [왜]   문서의 모든 요소를 위에서 아래로 한 번씩 훑기 위해
    #
    # for a, b in 반복자:  -> 튜플 (a, b) 를 두 변수로 "풀어서" 받는 문법 (언패킹)
    # 변수 이름 앞의 _ (_depth): "받긴 하지만 쓰지 않는다" 는 파이썬 관례. 원본은 이름을 _prov 로 했지만
    #        docling 소스상 두 번째 값은 위치 정보(prov)가 아니라 트리 깊이라서 여기서는 _depth 로 바꿨다
    for item, _depth in result.document.iterate_items():

        # isinstance(객체, 클래스)
        # [출처] 파이썬 기본 함수 (import 없이 사용)
        # [입력] 검사할 객체, 클래스
        # [반환] 객체가 그 클래스(또는 그 자식 클래스)의 것이면 True, 아니면 False
        # [왜]   문단/표/그림은 건너뛰고 제목만 고르려고
        if isinstance(item, SectionHeaderItem):

            # 리스트.append(값)
            # [출처] 파이썬 기본 list 의 메서드
            # [입력] 끝에 붙일 값 하나
            # [반환] 없음(None). 리스트 자체가 바뀐다
            headers.append(
                # { "키": 값, ... } : 딕셔너리(dict) 만들기. 키로 값을 찾는 자료형
                {
                    # item.text
                    #   [출처] docling-core TextItem 의 속성. 제목의 글자 (정리된 버전. 원본 글자는 item.orig)
                    # 문자열.strip()
                    #   [출처] 파이썬 기본 str 의 메서드
                    #   [반환] 앞뒤 공백/줄바꿈을 지운 새 문자열 (원본은 그대로)
                    # [:50]  슬라이싱: 앞에서부터 50글자까지만 (50글자보다 짧으면 전부)
                    #   [왜] 출력용이라 너무 긴 제목을 자른다
                    "text": item.text.strip()[:50],

                    # getattr(객체, "속성이름", 기본값)
                    #   [출처] 파이썬 기본 함수
                    #   [입력] 객체, 속성 이름(문자열), 그 속성이 없을 때 쓸 값
                    #   [반환] 객체.속성이름 의 값. 속성이 없으면 에러 대신 기본값
                    #   [왜]   item.level 이라고 바로 쓰면 속성이 없을 때 AttributeError 로 프로그램이 멈춘다.
                    #          (SectionHeaderItem 은 level 이 기본 1 로 항상 있지만, 방어적으로 쓴 것)
                    "level": getattr(item, "level", None),
                }
            )

    return headers  # 함수를 끝내고 값을 돌려준다


def toc_extract_tester(pdf_path: str):
    """[이 파일에서 정의] PDF 를 변환하고, 후처리 전/후 제목 level 을 비교해 출력한다."""

    # print(값)
    #   [출처] 파이썬 기본 함수. 화면에 출력
    # "=" * 80 : 문자열 * 정수 = 그 문자열을 80번 반복한 문자열 (구분선 만들기)
    print("=" * 80)
    print("Docling > ResultPostprocessor > ToC 추출 동작 테스트")
    print("=" * 80)

    # f"...{변수}..."  : f-string. 문자열 안의 {} 자리에 변수 값을 넣는다
    print(f"\nPDF 파일: {pdf_path}")   # \n 은 줄바꿈 문자

    # ---------- [1단계] docling 으로 변환 ----------
    print("\n[1단계] docling - PDF 변환 중...")

    # PdfPipelineOptions()
    # [출처] docling. 클래스 이름() 은 "그 클래스의 객체를 새로 만든다" 는 뜻 (생성자 호출)
    # [반환] 기본값이 채워진 설정 객체
    pipeline_options = PdfPipelineOptions()
    # 객체.속성 = 값 : 설정 바꾸기
    # [왜] OCR(이미지 속 글자 인식)을 끈다. 글자가 살아 있는 PDF 는 OCR 이 필요 없고 훨씬 빨라진다. 스캔본이면 True 로
    pipeline_options.do_ocr = False

    # DocumentConverter(format_options={형식: 옵션})
    # [출처] docling
    # [입력] format_options: "어떤 형식을 어떻게 읽을지" 딕셔너리
    #        여기서는 PDF 를 위 설정(pipeline_options) + pypdfium2 엔진(backend)으로 읽으라고 지정
    # [반환] 변환기 객체
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,   # 이름=값 형태로 넘기는 인자를 "키워드 인자" 라고 한다
                backend=PyPdfiumDocumentBackend,     # 클래스 자체를 넘긴다(괄호 없음). docling 이 필요할 때 만든다
            )
        }
    )

    # converter.convert(경로)
    # [출처] docling DocumentConverter.convert
    # [입력] 파일 경로(문자열 또는 Path) 또는 URL
    # [반환] ConversionResult. 주로 쓰는 속성:
    #        .document = DoclingDocument (변환된 문서 본체)
    #        .status   = 성공/실패 상태
    #        .pages    = 페이지 목록(리스트, 0번부터)
    # [왜]   PDF 를 제목/문단/표 단위의 구조로 바꾼다. 이 파일에서 가장 오래 걸리는 줄
    result = converter.convert(pdf_path)
    print("변환 완료")

    # ---------- 후처리 "전" ----------
    print("\ndocling-hierarchical-pdf 실행 전 상태")
    print("-" * 80)
    before = collect_headers(result)   # 위에서 정의한 함수 호출

    # len(값)
    #   [출처] 파이썬 기본 함수
    #   [반환] 리스트/문자열/딕셔너리의 길이(개수)
    print(f"섹션 헤더 개수: {len(before)}개")
    print("\n처음 5개 섹션 헤더:")

    # enumerate(반복가능한것, 시작번호)
    # [출처] 파이썬 기본 함수 (import 없이 사용)
    # [입력] 리스트 같은 반복 가능한 값, 번호를 몇부터 셀지(생략하면 0)
    # [반환] (번호, 값) 튜플을 차례로 내보내는 반복자 -> (1, 첫째), (2, 둘째), ...
    # [왜]   "1. 제목" 처럼 번호를 붙여 출력하려고. 번호 변수를 따로 만들어 +1 하지 않아도 된다
    # before[:5] : 앞에서 5개만 (슬라이싱)
    for i, h in enumerate(before[:5], 1):
        # h["text"] : 딕셔너리에서 키 "text" 의 값 꺼내기 (키가 없으면 KeyError)
        # f-string 안에서 큰따옴표를 쓰려고 바깥을 작은따옴표 f'...' 로 감쌌다
        print(f'  {i}. "{h["text"]}"  (level={h["level"]})')

    # ---------- [2단계] 계층 복원 ----------
    print("\n[2단계] docling-hierarchical-pdf - ResultPostprocessor 실행 중...")

    # ResultPostprocessor(result).process()
    # [출처] docling-hierarchical-pdf
    # [입력] ResultPostprocessor(변환결과) 로 만들고 .process() 를 부른다 (인자 없음)
    # [반환] 없음(None). 대신 result.document 를 "제자리에서" 고친다
    # [하는 일] PDF 안에 책갈피(북마크 목차)가 있으면 그걸 기준으로, 없으면 제목 번호("1.", "1.1", "가.")와 모양으로
    #          제목 계층을 추론해 각 제목의 level 과 문서 트리 구조를 다시 맞춘다
    # [왜]   위에서 before 를 먼저 리스트로 복사해 둔 이유: process() 가 result 를 바꿔 버려서 "전" 상태가 사라진다
    ResultPostprocessor(result).process()

    print("\nResultPostprocessor 실행 후 상태")
    print("-" * 80)
    after = collect_headers(result)
    print(f"섹션 헤더 개수: {len(after)}개")

    # ---------- 변화 분석 ----------
    print("\n[변화 분석]")
    print("=" * 80)

    # level 별 개수 세기
    # dict[int, int] : "키도 정수, 값도 정수인 딕셔너리" 라는 타입 힌트
    distribution: dict[int, int] = {}
    for h in after:
        # is not None : None 이 아닌지 검사 (None 비교는 == 대신 is 를 쓰는 것이 파이썬 관례)
        if h["level"] is not None:
            # 딕셔너리.get(키, 기본값)
            #   [출처] 파이썬 기본 dict 의 메서드
            #   [반환] 키가 있으면 그 값, 없으면 기본값 (에러가 나지 않는다)
            #   [왜]   처음 보는 level 이면 0 에서 시작해 +1 하려고. "개수 세기" 의 기본 패턴
            #   (참고: 표준 라이브러리 collections.Counter 를 쓰면 한 줄로도 셀 수 있다)
            distribution[h["level"]] = distribution.get(h["level"], 0) + 1

    print("\nlevel 분포:")
    # sorted(값)
    #   [출처] 파이썬 기본 함수
    #   [입력] 리스트나 딕셔너리 (딕셔너리를 넣으면 "키들" 을 정렬)
    #   [반환] 정렬된 "새 리스트" (원본은 그대로)
    for level in sorted(distribution):
        print(f"   - Level {level}: {distribution[level]}개")

    # 앞쪽 20개만 전/후 level 을 나란히 비교
    # min(a, b)
    #   [출처] 파이썬 기본 함수. 더 작은 값을 돌려준다
    #   [왜]   제목이 20개보다 적을 수도 있으니 실제 개수와 20 중 작은 쪽까지만
    # range(n)
    #   [출처] 파이썬 기본 함수. 0, 1, ..., n-1 을 차례로 내보낸다
    # 주의: 같은 위치(i)끼리 비교하므로 before 와 after 의 개수와 순서가 같다고 가정한다
    for i in range(min(20, len(before))):
        b, a = before[i], after[i]   # 두 값을 한 줄에 각각 넣기 (튜플 언패킹)
        print(f'\n{i + 1}. "{b["text"]}"')
        # != : 같지 않으면 True
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


# ============================================================
# if __name__ == "__main__":
#   "이 파일을 직접 실행했을 때만 아래를 실행" 하라는 파이썬 관례.
#   다른 파일에서 import 하면 __name__ 이 파일 이름이 되므로 아래가 실행되지 않는다 (함수만 가져다 쓸 수 있게)
# ============================================================
if __name__ == "__main__":
    # Path(__file__)
    #   __file__ : [출처] 파이썬이 자동으로 넣어 주는 변수. 지금 실행 중인 이 파일의 경로
    #   .resolve() : 절대 경로로 바꾼다 (상대 경로, .. 등을 정리)
    #   .parent    : 한 단계 위 폴더. .parent.parent 는 두 단계 위 (learning/ -> pdf2kg/)
    #   / "aibrief.pdf" : Path 에서 / 는 "경로 이어 붙이기"
    # [왜] 터미널을 어느 폴더에서 열고 실행하든 PDF 를 찾게 하려고 (원본은 "aibrief.pdf" 상대 경로라 pdf2kg 폴더에서만 동작)
    pdf_path = Path(__file__).resolve().parent.parent / "aibrief.pdf"

    # str(값) : [출처] 파이썬 기본 함수. 값을 문자열로 바꾼다 (Path 객체 -> "C:/.../aibrief.pdf")
    toc_extract_tester(str(pdf_path))
