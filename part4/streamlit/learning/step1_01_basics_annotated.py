"""[1단계: 읽기] 01_basics.py (Streamlit 화면 요소, 레이아웃, 세션 상태 기본기) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
streamlit 설명은 설치 소스(streamlit 1.57.0, requirements.txt 기준)로 확인했다.

가장 중요한 한 가지: Streamlit 의 실행 모델
  `streamlit run` 은 이 파일을 "웹 페이지를 그리는 대본" 으로 쓴다.
  사용자가 버튼을 누르거나, 입력칸에 쓰고 Enter 를 치거나, 슬라이더를 움직일 때마다
  파일 전체가 맨 위 1줄부터 맨 아래까지 "다시" 실행된다 (rerun).
  (소스 확인: streamlit/runtime/scriptrunner/script_runner.py 가 매 실행마다 새 모듈을 만들고
   exec(code, module.__dict__) 로 파일 전체를 실행한다. 그래서 일반 변수는 매번 처음 값으로 돌아간다)
  -> 실행과 실행 사이에 남겨야 하는 값은 st.session_state 에 넣는다 (브라우저 탭 하나 = 세션 하나).

흐름 (한 번의 실행)
  위에서부터: 제목 -> 1.텍스트 -> 2.컬럼 -> 3.사이드바(입력/버튼) -> 4.Expander
            -> 5.세션 상태(메시지 리스트, key 위젯) -> 6.데이터프레임 -> 7.세션 상태 보기
  버튼 클릭 -> [파일 전체 재실행] -> 그 버튼만 이번 실행에서 True -> if 블록 실행 -> session_state 변경
            -> (st.rerun() 이 있으면) 즉시 한 번 더 재실행해서 바뀐 상태로 다시 그림

참고 (이 파일엔 없지만 같이 알아 둘 것, 소스로 확인)
  @st.cache_resource: 함수 결과(DB 연결, 모델 같은 "자원")를 모든 사용자/세션/재실행에 걸쳐 하나만 만들어 공유 (기본 scope="global")
  @st.cache_data: 함수 결과(데이터)를 pickle 로 저장해 두고, 부를 때마다 복사본을 돌려준다
  session_state 는 "이 사용자(탭) 것", cache_resource 는 "서버 전체 공용" 이라는 점이 다르다.

읽는 순서 권장: 위 "실행 모델" -> 3절(사이드바 버튼과 session_state) -> 5절 -> 7절 -> 나머지 화면 요소
실행 위치: part4/streamlit  ->  streamlit run learning/step1_01_basics_annotated.py
  (API 키, DB 필요 없음. pip install -r requirements.txt 또는 uv sync)
"""

# [출처] 외부 라이브러리 pandas. 표(DataFrame)를 만들 때 쓴다 (6절, 4절)
import pandas as pd
# [출처] 외부 라이브러리 streamlit. 관례상 st 라는 짧은 이름으로 가져온다
# [왜] st.xxx(...) 를 부를 때마다 그 요소가 웹 페이지에 "위에서부터 순서대로" 추가된다.
#      print 대신 화면에 그리는 함수들이라고 생각하면 쉽다
import streamlit as st

# st.set_page_config: 브라우저 탭 제목, 탭 아이콘, 레이아웃 설정
# [입력] page_title=탭 제목, page_icon=탭 아이콘(이모지), layout="wide"(화면 폭 전체 사용) 또는 "centered"(가운데 좁게, 기본)
# [반환] 없음 (화면 설정만 바꾼다)
# 참고: 1.57.0 소스의 설명에 "한 번의 실행에서 여러 번 불러도 된다" 고 되어 있다 (옛 버전은 맨 처음 한 번만 허용)
st.set_page_config(
    page_title="Streamlit 기본",
    page_icon="📝", # 웹 브라우저 탭 아이콘
    layout="wide"
)

# st.title: 가장 큰 제목 / [입력] 문자열 (마크다운 일부 허용)
st.title("📝 Streamlit 기본 - ChatBot 구현 핵심")   # 페이지의 타이틀

# st.markdown: 마크다운 글을 그린다. **굵게**, *기울임*, - 목록 등
# """...""" 는 여러 줄 문자열 [출처] 파이썬 기본
st.markdown("""
이 예제는 **GraphRAG 챗봇 구현에 필요한 핵심 기능**만 다룹니다.
- 텍스트 표시
- 레이아웃 (컬럼, 사이드바, Expander)
- 세션 상태 관리
- 기본 위젯 (버튼, 입력)
""")

# ============================================
# 1. 텍스트 표시
# ============================================

# st.header: title 보다 한 단계 작은 제목 (st.subheader 는 그보다 작다)
st.header("1. 텍스트 표시")

# st.write: "만능" 출력. 문자열이면 마크다운으로, DataFrame 이면 표로, dict 면 JSON 으로... 넣은 것의 종류를 보고 알맞게 그린다
st.write("st.write()는 가장 자주 쓰는 만능 함수입니다.")
st.markdown("**마크다운**도 사용 가능: *기울임*, ~~취소선~~")
# st.code: 코드 블록 (문법 색칠 + 복사 버튼) / [입력] 코드 문자열, language="python" 등
st.code("print('코드 블록')", language="python")

# st.info / success / warning / error: 색깔 상자로 된 알림 메시지 (파랑/초록/노랑/빨강)
# st.error 는 "보여 주기" 만 할 뿐 프로그램을 멈추지 않는다 (멈추려면 st.stop())
st.info("ℹ️ 정보 메시지")
st.success("✅ 성공 메시지")
st.warning("⚠️ 경고 메시지")
st.error("❌ 에러 메시지")

# ============================================
# 2. 레이아웃 - 컬럼
# ============================================

st.header("2. 컬럼 레이아웃")

# st.columns(3): 가로로 나란한 칸 3개를 만든다
# [반환] 칸(컨테이너) 3개가 든 리스트 -> col1, col2, col3 = ... 로 한 번에 나눠 받는다 (튜플 언패킹 [출처] 파이썬 기본)
# [왜] col1.write(...) 처럼 "칸.함수" 로 부르면 그 칸 안에 그려진다 (st.write 는 본문에 그려진다)
col1, col2, col3 = st.columns(3)

col1.write("컬럼 1")
# metric: 큰 숫자 + 변화량 카드 / [입력] (제목, 값, 변화량)
# 변화량이 + 면 초록 화살표 위, - 면 빨강 화살표 아래 (delta_color="normal" 기본)
col1.metric("사용자", "1,234", "+12")

col2.write("컬럼 2")
col2.metric("매출", "$5.6M", "+$1.2M")

col3.write("컬럼 3")
# delta_color="inverse": 색을 거꾸로. 에러율은 "줄어드는 게 좋은 것" 이라 -0.5% 를 초록으로 보이게 한다
col3.metric("에러율", "2.3%", "-0.5%", delta_color="inverse")

# ============================================
# 3. 사이드바
# ============================================

st.header("3. 사이드바")

st.write("왼쪽 사이드바를 확인하세요")

# with 문 [출처] 파이썬 기본: "with 대상:" 아래 들여쓴 블록 동안 대상을 켜 두었다가 블록이 끝나면 정리한다.
# 여기서 with st.sidebar: 는 "이 블록 안에서 부른 st.xxx 는 왼쪽 사이드바에 그려라" 라는 뜻
# (st.sidebar.title(...) 처럼 써도 같다)
with st.sidebar:
    st.title("⚙️ 설정")
    st.write("사이드바에는 설정과 옵션을 배치합니다.")

    # st.text_input: 한 줄 입력칸 / [입력] 라벨, placeholder=비어 있을 때 흐리게 보이는 안내 글
    # [반환] 지금 입력칸에 들어 있는 문자열 (처음엔 빈 문자열 "")
    # [왜] 재실행될 때마다 이 줄이 다시 실행되지만, 위젯이 매번 같은 자리에 그려지는 한 Streamlit 이
    #      사용자가 쓴 값을 기억했다가 돌려준다. 그래서 key 가 없어도 입력값이 사라지지 않는다
    user_name = st.text_input("이름", placeholder="홍길동")
    # st.slider(라벨, 최솟값, 최댓값, 기본값): 슬라이더 / [반환] 현재 값 (정수를 넣었으니 정수)
    age = st.slider("나이", 0, 100, 25)

    # st.button: 버튼 / [반환] bool
    # 소스 설명: "마지막 실행에서 버튼이 눌렸으면 True, 아니면 False"
    # -> 누른 직후의 그 한 번의 재실행에서만 True. 다음에 다른 위젯을 건드려 재실행되면 다시 False 가 된다.
    # [왜] 그래서 버튼으로 얻은 결과를 계속 보이게 하려면 session_state 에 저장해 둬야 한다 (바로 아래 두 줄)
    if st.button("정보 저장"):
        # 세션 상태에 저장
        # st.session_state: 세션(브라우저 탭)마다 따로 있는 저장소. 재실행되어도 값이 남는다
        # [사용법] 딕셔너리처럼 st.session_state["saved_name"] 으로도, 속성처럼 st.session_state.saved_name 으로도 쓸 수 있다
        #          (소스: SessionStateProxy 의 __getattr__/__setattr__ 가 결국 self[key] 를 읽고 쓴다)
        # 없는 이름을 속성으로 읽으면 AttributeError, [ ] 로 읽으면 KeyError 가 난다
        st.session_state.saved_name = user_name
        st.session_state.saved_age = age
        # 주의: 이 "저장 완료!" 는 버튼을 누른 그 실행에서만 보인다. 다음 재실행 때는 버튼이 False 라 사라진다
        st.success("저장 완료!")

# 저장된 정보 표시
# "키" in st.session_state: 그 값이 저장된 적 있는지 확인 (in 연산자 [출처] 파이썬 기본)
# [왜] 한 번도 저장 안 했을 때 st.session_state.saved_name 을 읽으면 에러가 나니까 먼저 확인한다
# 참고: 이 줄은 사이드바 코드 "뒤" 에 있으므로, 버튼을 누른 바로 그 실행에서도 저장된 값이 보인다
if "saved_name" in st.session_state:
    # f"...{변수}..." : f-string [출처] 파이썬 기본. 중괄호 안의 변수(또는 식)를 값으로 바꿔 끼운 문자열
    st.info(f"💾 저장된 정보: {st.session_state.saved_name} ({st.session_state.saved_age}세)")

# ============================================
# 4. Expander (접기/펼치기)
# ============================================

st.header("4. Expander (접기/펼치기)")

st.write("**ChatBot에서 도구 호출 정보를 표시할 때 사용합니다.**")

# st.expander(라벨): 접었다 폈다 하는 상자. 기본은 접힌 상태 (expanded=False)
# [왜] 챗봇에서 "도구 호출 정보" 처럼 보조 정보를 접어 두는 데 쓴다 (02_chatbot_ui.py, final_chatbot)
with st.expander("🔧 도구 호출 정보 보기"):
    st.write("도구 이름: generate_cypher_query")
    # st.json: dict 나 리스트를 접을 수 있는 JSON 트리로 보여 준다
    st.json({"question": "OpenAI에 대해 알려줘"})
    # language="cypher": Cypher 문법으로 색칠. 여기선 보여 주기만 한다 (실행하지 않음)
    st.code("MATCH (c:Company) WHERE c.name CONTAINS 'OpenAI' RETURN c", language="cypher")

# expanded=True: 처음부터 펼친 상태로 그린다
with st.expander("📊 실행 결과", expanded=True):
    st.write("기본적으로 펼쳐진 상태로 표시할 수도 있습니다.")
    # st.dataframe: pandas DataFrame 을 정렬/스크롤 가능한 표로 그린다
    # pd.DataFrame({열이름: [값들]}) : 딕셔너리로 표 만들기 [출처] pandas
    st.dataframe(pd.DataFrame({"이름": ["OpenAI"], "설명": ["AI 연구 기업"]}))

# ============================================
# 5. 세션 상태 (Session State)
# ============================================

st.header("5. 세션 상태 관리")

st.markdown("""
**세션 상태는 챗봇 구현의 핵심입니다!**
- 페이지가 재실행되어도 데이터를 유지
- 대화 기록, 사용자 설정 등을 저장
""")

st.subheader("5-1. 리스트 관리 (대화 기록과 유사)")

# [가장 중요한 패턴] "없을 때만 만든다"
# 매 재실행마다 이 줄이 실행되므로, 그냥 st.session_state.messages = [] 라고 쓰면 실행될 때마다 목록이 비워진다.
# "아직 없을 때(첫 실행)만" 빈 리스트를 만들고, 그 뒤로는 있는 것을 그대로 쓴다
if "messages" not in st.session_state:
    st.session_state.messages = []

# 새 메시지 추가
# key="new_message": 위젯에 이름표를 붙인다. 값이 st.session_state["new_message"] 에도 들어간다 (5-2절 참고)
# 주의: 추가 버튼을 눌러도 입력칸 글자는 지워지지 않는다. 한 번 더 누르면 같은 메시지가 또 추가된다
new_msg = st.text_input("메시지 추가:", key="new_message")
# if 안의 if: 버튼이 눌렸고(바깥) 입력이 비어 있지 않을 때(안쪽)만 추가. 빈 문자열 "" 은 거짓으로 취급된다 [출처] 파이썬 기본
if st.button("➕ 추가"):
    if new_msg:
        # .append(값): 리스트 끝에 추가 [출처] 파이썬 기본
        # session_state 안의 리스트를 직접 바꾸는 것이라, 다음 재실행에도 남는다
        st.session_state.messages.append(new_msg)
        # st.rerun(): 지금 실행을 그 자리에서 멈추고 파일을 처음부터 다시 실행한다 (소스: "executes no further statements")
        # [왜] 상태를 바꾼 뒤 바뀐 상태로 화면을 다시 그리고 싶을 때.
        # 참고: 목록 표시(아래 if)가 이 버튼보다 "뒤" 에 있어서, 여기서는 rerun 이 없어도 새 메시지가 보이긴 한다.
        #       반대로 아래 "전체 삭제" 버튼은 목록을 이미 그린 "뒤" 에 있으므로 rerun 이 있어야 화면에서 바로 사라진다
        st.rerun()

# 메시지 목록 표시
# 빈 리스트는 거짓, 하나라도 있으면 참 [출처] 파이썬 기본
if st.session_state.messages:
    st.write("**메시지 목록:**")
    # enumerate(리스트): (번호, 값) 짝을 차례로 준다. 번호는 0부터 [출처] 파이썬 기본 -> 그래서 idx + 1 로 1부터 보여 준다
    for idx, msg in enumerate(st.session_state.messages):
        st.write(f"{idx + 1}. {msg}")

    # 이 버튼은 메시지가 있을 때만 화면에 나온다 (if 블록 안에 있으니까)
    if st.button("🗑️ 전체 삭제"):
        st.session_state.messages = []
        st.rerun()
else:
    st.info("메시지가 없습니다.")


st.subheader("5-2. 위젯에 key 지정")

st.write("key 파라미터를 사용하면 자동으로 세션 상태에 저장됩니다.")

# key를 지정하면 st.session_state.user_input으로 접근 가능
# key 를 지정한 위젯: 반환값(user_input 변수)과 st.session_state.user_input 이 같은 값이다
# [왜] 다른 곳(콜백 함수, 다른 위젯 처리 코드)에서도 이 위젯 값을 이름으로 읽을 수 있다
user_input = st.text_input("입력:", key="user_input")

if user_input:
    st.write(f"입력한 값: {st.session_state.user_input}")


# ============================================
# 6. DataFrame 표시
# ============================================

st.header("6. 데이터 표시")

# pd.DataFrame: 딕셔너리 {열 이름: 값 리스트} -> 표. 리스트 길이가 모두 같아야 한다
df = pd.DataFrame({
    "이름": ["홍길동", "김철수", "이영희"],
    "나이": [25, 30, 28],
    "직업": ["개발자", "디자이너", "기획자"]
})

# width='stretch': 표를 화면 폭에 맞춰 늘린다. 1.57.0 소스에서 st.dataframe 의 width 기본값이 이미 "stretch" 이다
st.dataframe(df, width='stretch')

# JSON 표시
st.json({"name": "홍길동", "age": 25, "skills": ["Python", "JavaScript"]})

# ============================================
# 7. 세션 상태 디버깅
# ============================================

st.header("7. 세션 상태 디버깅")

with st.expander("현재 세션 상태 보기"):
    st.write("**모든 세션 상태 변수:**")
    # dict(st.session_state): 세션 상태 전체를 일반 딕셔너리로 복사
    # 소스 확인: 직접 넣은 값(saved_name, messages)뿐 아니라 key 를 준 위젯 값(new_message, user_input)도 함께 들어 있다.
    # key 없는 위젯(이름, 나이 입력칸)은 빠진다
    # [왜] 디버깅: 지금 무엇이 저장돼 있는지 한눈에 본다
    st.json(dict(st.session_state))

# st.divider: 가로 구분선
st.divider()