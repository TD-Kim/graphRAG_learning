"""
[1단계: 읽기] law_api.py (법제처 Open API 호출) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나

이 파일이 하는 일: 법제처 웹 API 에 HTTP 요청을 보내 법령/해석례 목록과 본문을 JSON 으로 받아 온다.
law2kg.py 가 `from law_api import fetch_law_detail, fetch_law_list` 로 가져다 쓴다. (그래프 코드는 없음)
직접 실행하면 test_api_connection() 이 돌아서 샘플 JSON 4개를 현재 폴더에 저장한다.
  -> 샘플 JSON 을 열어 보면 law2kg.py 가 왜 .get('조문', {}).get('조문단위', []) 처럼 깊게 꺼내는지 이해된다.

읽는 순서 권장: 이 파일 -> step1_law2kg_annotated.py -> step1_load_laws_annotated.py -> step1_link_interpretations_annotated.py
실행 위치: part2/law2kg  ->  python learning/step1_law_api_annotated.py  (.env 에 LAW_API_KEY 필요)
"""

import json     # [출처] 표준 라이브러리. json.dump(파일 저장), json.JSONDecodeError(파싱 실패 예외)
import os       # [출처] 표준 라이브러리. os.getenv
from typing import Any, Dict, Optional    # 타입 힌트. Optional[str] = str 또는 None

# [출처] 외부 라이브러리 requests (pip install requests). 파이썬에서 HTTP 요청을 보내는 사실상 표준 도구
#   requests.get(URL, params=딕셔너리, timeout=초) -> Response 객체
import requests
from dotenv import load_dotenv    # [출처] 외부 라이브러리 python-dotenv

# ============================================
# API 엔드포인트 (요청을 보낼 주소)
# ============================================

BASE_URL_SEARCH = "http://www.law.go.kr/DRF/lawSearch.do" # 목록 조회
BASE_URL_SERVICE = "http://www.law.go.kr/DRF/lawService.do" # 본문 조회
# target=law : 현행법령
# target=expc : 해석례


# ============================================
# API 호출 함수
# ============================================

def fetch_law_list(
    api_key: str,
    target: str = "law",
    display: int = 100,
    page: int = 1,
    query: Optional[str] = None
) -> Dict[str, Any]:
    """법령 목록 조회

    Args:
        api_key: 법제처 API 인증키 (OC 값. 가입한 이메일의 @ 앞부분)
        target: 조회 대상 ('law': 현행법령, 'expc': 법령해석례)
        display: 조회 개수 (기본: 100)
        page: 페이지 번호 (기본: 1). 100개씩 끊어서 주므로 다음 100개는 page=2
        query: 검색 키워드 (선택)

    Returns:
        API 응답 JSON (딕셔너리). 실패하면 빈 딕셔너리 {}
        모양 예) law  -> {"LawSearch": {"totalCnt": "5000", "law": [{...}, ...]}}
                 expc -> {"Expc": {"totalCnt": "...", "expc": [{...}, ...]}}
    """
    # URL 뒤에 붙을 질의 파라미터. requests 가 ?OC=...&target=law&display=100... 로 만들어 준다
    params = {
        'OC': api_key,
        'target': target,
        'display': display,
        'page': page,
        'type': 'JSON'        # 응답 형식. 안 주면 XML 로 온다
    }

    # query 가 None 이나 빈 문자열이 아닐 때만 키를 추가
    if query:
        params['query'] = query

    try:
        # requests.get(URL, params=..., timeout=30)
        # [출처] 외부 라이브러리 requests
        # [입력] params: 질의 파라미터 딕셔너리 / timeout: 응답을 최대 몇 초 기다릴지 (없으면 영원히 기다릴 수 있다)
        # [반환] Response 객체 (.status_code 상태코드, .text 본문 글, .json() 본문을 딕셔너리로)
        response = requests.get(BASE_URL_SEARCH, params=params, timeout=30)
        # response.raise_for_status(): 상태코드가 4xx/5xx(실패)면 HTTPError 예외를 낸다. 200 이면 아무 일 없음
        # [왜] requests 는 404 가 와도 에러를 내지 않는다. 실패를 except 로 보내려면 직접 불러야 한다
        response.raise_for_status()
        # response.json(): 본문 JSON 글 -> 딕셔너리 (json.loads(response.text) 와 같다)
        return response.json()
    # except 를 여러 개 쓰면 위에서부터 맞는 종류 하나만 실행된다
    # requests.exceptions.RequestException: requests 의 모든 예외(연결 실패, 시간 초과, HTTPError 등)의 부모 클래스
    except requests.exceptions.RequestException as e:
        # str(e): 예외 메시지를 문자열로 (f-string 안에서는 {e} 만 써도 같다)
        print(f"ERROR: 법령 목록 조회 실패 - {str(e)}")
        return {}
    # json.JSONDecodeError: 본문이 JSON 이 아닐 때 (예: 인증키가 틀려 HTML 오류 페이지가 온 경우)
    # 참고: 최신 requests 에서는 response.json() 실패가 requests.exceptions.JSONDecodeError 로 나오고,
    #       이것은 RequestException 의 자식이라 바로 위 except 에서 먼저 잡힌다
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON 파싱 실패 - {str(e)}")
        return {}


def fetch_law_detail(
    api_key: str,
    law_id: str,
    target: str = "law"
) -> Dict[str, Any]:
    """법령 상세 조회 (본문)

    Args:
        api_key: 법제처 API 인증키
        law_id: 법령일련번호 (MST) 또는 해석례일련번호 (ID)
        target: 조회 대상 ('law': 현행법령, 'expc': 법령해석례)

    Returns:
        API 응답 JSON (딕셔너리). 실패하면 {}
    """
    # eflaw는 MST 파라미터, expc는 ID 파라미터 사용
    # 값1 if 조건 else 값2 : 해석례면 'ID', 아니면 'MST' 라는 "키 이름" 을 고른다
    id_param = 'ID' if target == 'expc' else 'MST'

    params = {
        'OC': api_key,
        'target': target,
        id_param: law_id,     # 키 자리에 변수를 쓰면 그 변수 값('ID' 또는 'MST')이 키가 된다
        'type': 'JSON'
    }

    # 위 fetch_law_list 와 같은 패턴 (주소만 BASE_URL_SERVICE)
    try:
        response = requests.get(BASE_URL_SERVICE, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: 법령 상세 조회 실패 (ID: {law_id}) - {str(e)}")
        return {}
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON 파싱 실패 - {str(e)}")
        return {}


# ============================================
# API 테스트 및 샘플 데이터 생성
# ============================================

def test_api_connection(save_samples: bool = True) -> bool:
    """[이 파일에서 정의] 목록 -> 첫 항목 상세 를 법령/해석례 각각 한 번씩 호출해 보고, 응답을 샘플 JSON 파일로 저장한다.
    [반환] 성공 True / 실패 False"""
    print("=" * 80)
    print("법제처 Open API 연결 테스트")
    print("=" * 80)

    load_dotenv()      # .env 를 읽어 환경변수로 등록 (함수 안에서 불러도 된다)
    api_key = os.getenv('LAW_API_KEY')

    if not api_key:
        print("\nERROR: LAW_API_KEY가 설정되지 않았습니다.")
        print("\n.env 파일에 다음과 같이 설정하세요:")
        print("  LAW_API_KEY=이메일ID")
        print("\n예: fastcampus@gmail.com → LAW_API_KEY=fastcampus")
        return False

    print(f"\n✓ OC 인증키: {api_key}")

    # 1. 현행법령 테스트
    print("\n" + "-" * 80)
    print("[1] 현행법령(law) 테스트")
    print("-" * 80)

    eflaw_list = fetch_law_list(api_key, target='law', display=3) # 현행법령 3개

    print(eflaw_list)     # 응답 전체를 그대로 출력 (구조 확인용)

    # 빈 딕셔너리 {} 는 거짓 -> 실패하면 else 로
    if eflaw_list:
        # 딕셔너리.get(키, 기본값)을 이어서 써서 안쪽으로 들어간다. 중간 키가 없어도 에러 대신 기본값
        law_data = eflaw_list.get('LawSearch', {})
        laws = law_data.get('law', [])
        total = law_data.get('totalCnt', 0)

        print(f"✓ 성공: 총 {total}건 중 {len(laws)}건 조회")

        if save_samples:
            # with open(...) as f: 블록이 끝나면 파일 자동 닫힘 / 'w' 쓰기 모드
            with open('eflaw_list_sample.json', 'w', encoding='utf-8') as f:
                # json.dump(객체, 파일, ensure_ascii=False 한글 그대로, indent=2 보기 좋게 들여쓰기)
                json.dump(eflaw_list, f, ensure_ascii=False, indent=2)
            print(f"  → 저장: eflaw_list_sample.json")

        # 상세 조회 (첫 번째 법령)
        if laws:
            # 응답의 키가 한글이다 ('법령일련번호', '법령명한글')
            law_id = laws[0].get('법령일련번호')
            law_name = laws[0].get('법령명한글', 'N/A')[:30]     # 앞 30자만

            print(f"\n  첫 번째 법령: {law_name}... (ID: {law_id})")

            eflaw_detail = fetch_law_detail(api_key, law_id, target='law')

            # and: 둘 다 참일 때만
            if eflaw_detail and save_samples:
                with open('eflaw_detail_sample.json', 'w', encoding='utf-8') as f:
                    json.dump(eflaw_detail, f, ensure_ascii=False, indent=2)
                print(f"  → 상세 저장: eflaw_detail_sample.json")
    else:
        print("실패: 현행법령 조회 불가")
        return False

    # 2. 법령해석례 테스트 (위와 같은 순서. 응답 키 이름만 다르다: 'Expc', 'expc', '법령해석례일련번호', '안건명')
    print("\n" + "-" * 80)
    print("[2] 법령해석례(expc) 테스트")
    print("-" * 80)

    expc_list = fetch_law_list(api_key, target='expc', display=3)

    if expc_list:
        expc_data = expc_list.get('Expc', {})
        cases = expc_data.get('expc', [])
        total = expc_data.get('totalCnt', 0)

        print(f"✓ 성공: 총 {total}건 중 {len(cases)}건 조회")

        if save_samples:
            with open('expc_list_sample.json', 'w', encoding='utf-8') as f:
                json.dump(expc_list, f, ensure_ascii=False, indent=2)
            print(f"  → 저장: expc_list_sample.json")

        # 상세 조회 (첫 번째 해석례)
        if cases:
            case_id = cases[0].get('법령해석례일련번호')
            case_name = cases[0].get('안건명', 'N/A')[:30]

            print(f"\n  첫 번째 해석례: {case_name}... (ID: {case_id})")

            expc_detail = fetch_law_detail(api_key, case_id, target='expc')

            if expc_detail and save_samples:
                with open('expc_detail_sample.json', 'w', encoding='utf-8') as f:
                    json.dump(expc_detail, f, ensure_ascii=False, indent=2)
                print(f"  → 상세 저장: expc_detail_sample.json")
    else:
        print("실패: 법령해석례 조회 불가")
        return False

    # 결과 요약
    print("\n" + "=" * 80)
    print("테스트 완료!")
    print("=" * 80)

    if save_samples:
        print("\n생성된 샘플 파일:")
        print("  • eflaw_list_sample.json    - 현행법령 목록")
        print("  • eflaw_detail_sample.json  - 현행법령 상세")
        print("  • expc_list_sample.json     - 법령해석례 목록")
        print("  • expc_detail_sample.json   - 법령해석례 상세")

    print("=" * 80)
    return True

def main():
    test_api_connection(save_samples=True)


# 이 파일을 직접 실행할 때만 main() 실행. law2kg.py 가 import 할 때는 실행되지 않는다
# [왜] law2kg.py 가 fetch 함수만 가져가고 싶은데, import 하자마자 테스트가 돌면 곤란하다
if __name__ == "__main__":
    main()
