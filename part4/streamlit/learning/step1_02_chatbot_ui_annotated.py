"""[1단계: 읽기] 02_chatbot_ui.py (LLM 없이 가짜 응답으로 만든 챗봇 화면 연습) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
streamlit 설명은 설치 소스(streamlit 1.57.0, requirements.txt 기준)로 확인했다.
01_basics.py 주석본(step1_01_basics_annotated.py)을 먼저 읽으면 좋다.

핵심: 채팅 입력 한 번 = 파일 전체 재실행 한 번
  Streamlit 은 위젯을 건드릴 때마다 파일 전체를 위에서부터 다시 실행한다.
  그래서 화면에 남아 있어야 할 대화는 매 실행마다 session_state.messages 에서 꺼내 "처음부터 다시 그린다".

흐름 (사용자가 "OpenAI 찾아줘" 를 입력했을 때의 한 번의 실행)
  [재실행 시작]
    -> 1절: 고정 예시 말풍선 4개
    -> messages 가 없으면 인사말 하나로 초기화 (첫 실행만)
    -> for message in messages: 지난 대화를 말풍선 + 도구 호출 Expander 로 다시 그림
    -> chat_input 이 이번 실행에서 "OpenAI 찾아줘" 를 돌려줌
         -> 사용자 말풍선 그림 + messages 에 추가
         -> 글자에 "스키마"/"OpenAI"/"찾아"/"스트리밍" 이 있는지로 가짜 도구 호출 흉내 (진짜 LLM 판단 아님)
         -> 응답 말풍선 그림 + response_message(내용 + tool_calls) 를 messages 에 추가
    -> 대화 초기화 버튼, 사이드바
  [다음 입력 때] 위 for 문이 방금 저장한 response_message 의 tool_calls 까지 다시 그려 준다

참고 (소스로 확인. 이 파일엔 없음)
  st.write_stream(제너레이터): 조각(문자열 등)을 받는 대로 타자기 효과로 그려 주고 [반환] 합친 전체 글.
    OpenAI 스트림 조각, LangChain AIMessageChunk 조각도 알아서 글자로 바꿔 준다.
    이 파일의 "스트리밍" 부분(st.empty 에 한 글자씩 덧붙이기)을 st.write_stream 하나로 바꿀 수 있다.

읽는 순서 권장: 세션 초기화 -> 이전 메시지 다시 그리기(for 문) -> chat_input 블록 -> 4가지 분기 -> 사이드바
실행 위치: part4/streamlit  ->  streamlit run learning/step1_02_chatbot_ui_annotated.py
  (API 키, DB 필요 없음. 응답은 모두 코드에 적힌 가짜 문자열)
"""

# [출처] 외부 라이브러리 streamlit
import streamlit as st
# [출처] 표준 라이브러리 time. time.sleep(초): 그만큼 멈춘다 -> 도구가 일하는 척 기다리게 할 때 쓴다
import time

# st.set_page_config: 탭 제목/아이콘/넓은 레이아웃 (01_basics 참고)
st.set_page_config(page_title="챗봇 UI", page_icon="💬", layout="wide")

st.title("💬 Streamlit 챗봇 UI 가이드")

st.markdown("""
- st.chat_message (메시지 표시)
- st.chat_input (사용자 입력)
- 세션 상태로 대화 기록 관리
- 도구 호출 정보 표시
- 스트리밍 효과
""")

# ============================================
# 1. 기본 채팅 메시지
# ============================================

st.header("1. 기본 채팅 메시지")

# st.chat_message(이름): 채팅 말풍선 컨테이너. with 블록 안에서 그린 것이 그 말풍선 안에 들어간다
# [입력] 이름: "user"/"human" 이나 "assistant"/"ai" 를 주면 미리 정해진 모양과 아바타가 붙는다 (다른 문자열도 가능)
# [반환] 컨테이너 (with 와 함께 쓴다)
with st.chat_message("user"):
    st.write("안녕하세요! 사용자 메시지입니다.")

with st.chat_message("assistant"):
    st.write("안녕하세요! AI 어시스턴트입니다.")

# avatar="👤": 아바타를 이모지(또는 이미지)로 직접 지정. 안 주면(None) 이름에 따라 자동으로 정해진다
with st.chat_message("user", avatar="👤"):
    st.write("커스텀 아바타도 사용할 수 있습니다.")

with st.chat_message("assistant", avatar="🤖"):
    st.write("다양한 이모지를 아바타로 사용 가능!")

# st.divider: 가로 구분선
st.divider()

# ============================================
# 2. 통합 챗봇
# ============================================

st.header("2. 통합 챗봇")

st.markdown("""
- 일반 메시지: 에코 응답 (예: "안녕하세요")
- **스키마 보여줘**: 스키마 조회 도구 호출
- **OpenAI 찾아줘**: Cypher 쿼리 생성 및 실행 도구 호출 (2개 도구 연속)
- **스트리밍**: 타이핑 효과로 응답
""")

# 세션 상태 초기화
# [핵심 패턴] 대화 기록 리스트는 "없을 때만" 만든다 (첫 실행). 이후 재실행에서는 쌓인 기록을 그대로 쓴다
# 각 메시지는 {"role": "user" 또는 "assistant", "content": 글} 딕셔너리. OpenAI/LangChain 메시지 모양과 같게 맞춘 것
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?"}
    ]

# 이전 메시지 표시
# [왜] 재실행되면 이전 실행에서 그린 화면은 다시 그려야 한다. 그래서 매번 기록 전체를 처음부터 다시 그린다
for message in st.session_state.messages:
    # message["role"] 을 그대로 말풍선 이름으로 쓴다 -> user/assistant 모양이 자동으로 정해진다
    with st.chat_message(message["role"]):
        st.write(message["content"])

        # 도구 호출 정보가 있으면 Expander로 표시
        # "tool_calls" in message: 딕셔너리에 그 키가 있는지 [출처] 파이썬 기본
        # 사용자 메시지에는 이 키가 없고, 봇 메시지에는 (비어 있을 수도 있는) 리스트로 있다
        if "tool_calls" in message:
            for tool_call in message["tool_calls"]:
                # f"... {tool_call['name']}" : f-string 안에서 딕셔너리 키를 쓸 때는 바깥 따옴표(")와 다른 따옴표(')를 쓴다
                # expanded=False: 지난 대화의 도구 정보는 접어 둔다 (방금 실행한 것은 아래에서 expanded=True 로 펼쳐 보인다)
                with st.expander(f"🔧 도구 호출: {tool_call['name']}", expanded=False):
                    st.write("**입력:**")
                    # st.json: dict 를 JSON 트리로
                    st.json(tool_call["args"])

                    # 도구 결과는 있을 때만. generate_cypher_query 결과는 Cypher 라서 st.code 로 색칠, 나머지는 st.text (고정폭 글자, 마크다운 해석 안 함)
                    if "result" in tool_call:
                        st.write("**결과:**")
                        # Cypher 쿼리면 코드 블록으로
                        if tool_call["name"] == "generate_cypher_query":
                            st.code(tool_call["result"], language="cypher")
                        else:
                            st.text(tool_call["result"])

# 새 메시지 입력
# st.chat_input(안내글): 채팅 입력칸. 본문에서 부르면 페이지 맨 아래에 고정된다 (소스 설명)
# [반환] 사용자가 "방금" 보낸 글이 있으면 그 문자열, 없으면 None
#        -> 보낸 직후의 그 한 번의 재실행에서만 글이 오고, 다음 재실행에서는 다시 None (st.button 과 같은 방식)
# := (바다코끼리/월러스 연산자) [출처] 파이썬 기본 (3.8+): 값을 변수에 넣으면서 동시에 그 값을 if 조건으로 쓴다
#   if prompt := st.chat_input(...):  는 아래 두 줄과 같다
#       prompt = st.chat_input(...)
#       if prompt:
if prompt := st.chat_input("메시지를 입력하세요 (예: '안녕', '스키마 보여줘', 'OpenAI 찾아줘', '스트리밍')"):
    # 사용자 메시지 저장
    # 먼저 기록에 추가 -> 다음 재실행부터는 위 for 문이 이 메시지도 그려 준다
    st.session_state.messages.append({"role": "user", "content": prompt})
    # 이번 실행에서는 for 문이 이미 지나갔으므로 새 메시지를 여기서 직접 한 번 그린다
    with st.chat_message("user"):
        st.write(prompt)

    # 봇 응답 생성
    with st.chat_message("assistant"):
        # 응답 메시지를 미리 빈 틀로 만들어 두고, 아래 분기에서 content 와 tool_calls 를 채운다
        # [왜] tool_calls 를 같이 저장해야 다음 재실행 때 for 문이 도구 호출 Expander 를 다시 그릴 수 있다
        response_message = {"role": "assistant", "content": "", "tool_calls": []}

        # 1. 스키마 조회 명령
        # "스키마" in prompt: 문자열 안에 그 글자가 들어 있는지 [출처] 파이썬 기본
        # [왜] 진짜 챗봇에서는 LLM 이 "어떤 도구를 부를지" 를 정한다. 여기서는 화면 연습용이라 글자 포함 여부로 흉내만 낸다
        if "스키마" in prompt:
            # expander 안에 spinner 처럼 다른 요소를 넣을 수 있다. 방금 실행한 도구라 expanded=True 로 펼친다
            with st.expander("🔧 도구 호출: schema_introspection", expanded=True):
                st.write("**입력:** (파라미터 없음)")
                # st.spinner(글): with 블록이 실행되는 동안 빙글빙글 + 안내 글을 보여 주고, 블록이 끝나면 사라진다
                with st.spinner("스키마 조회 중..."):
                    time.sleep(0.5)
                # "\n" 은 줄바꿈 문자. 가짜 스키마 결과
                result = "Node: Company, Person, TOC\nRelationship: EMPLOYS, HAS_CHUNK"
                st.write("**결과:**")
                st.code(result)

            # 이번 실행에서 그린 도구 정보를 기록용 딕셔너리로도 남긴다 (위 "이전 메시지 표시" for 문이 다시 그릴 때 읽는 모양과 같다)
            response_message["tool_calls"].append({
                "name": "schema_introspection",
                "args": {},
                "result": result
            })
            response_message["content"] = "그래프 스키마를 조회했습니다. Company, Person, TOC 노드와 관계들이 있습니다."

        # 2. OpenAI 검색 명령 (2개 도구 연속 실행)
        # elif: 위 if 가 거짓일 때만 검사 [출처] 파이썬 기본. 그래서 "스키마" 와 "OpenAI" 가 둘 다 있으면 스키마 쪽만 실행된다
        # or: 둘 중 하나라도 참이면 참. "찾아" 만 있어도 이 분기로 온다 (예: "사람 찾아줘")
        elif "OpenAI" in prompt or "찾아" in prompt:
            # generate_cypher_query 도구
            with st.expander("🔧 도구 호출: generate_cypher_query", expanded=True):
                st.write("**입력:**")
                st.json({"question": prompt})
                with st.spinner("쿼리 생성 중..."):
                    time.sleep(0.5)
                # 가짜 Cypher. 실제로는 LLM 이 만들고(generate_cypher_query) Neo4j 에서 실행(execute_cypher_query)한다
                # 도구 두 개를 "연속으로" 부르는 모습을 보여 주려는 것
                query = "MATCH (c:Company) WHERE c.name CONTAINS 'OpenAI' RETURN c.name, c.description"
                st.write("**생성된 Cypher 쿼리:**")
                st.code(query, language="cypher")

            response_message["tool_calls"].append({
                "name": "generate_cypher_query",
                "args": {"question": prompt},
                "result": query
            })

            # execute_cypher_query 도구
            with st.expander("🔧 도구 호출: execute_cypher_query", expanded=True):
                st.write("**입력:**")
                st.code(query, language="cypher")
                with st.spinner("쿼리 실행 중..."):
                    time.sleep(0.5)
                result = "[1]\n  name: OpenAI\n  description: AI 연구 기업"
                st.write("**실행 결과:**")
                st.text(result)

            response_message["tool_calls"].append({
                "name": "execute_cypher_query",
                "args": {"cypher_query": query},
                "result": result
            })

            response_message["content"] = "OpenAI는 AI 연구 기업입니다. 데이터베이스에서 정보를 찾았습니다."

        # 3. 스트리밍 효과 명령
        # 주의: 분기 순서 때문에 "OpenAI 스트리밍" 처럼 앞 분기 글자가 같이 들어 있으면 이 분기로 오지 않는다.
        #       그런데 아래 "최종 응답 표시" 의 "스트리밍" not in prompt 검사 때문에 답변 글도 화면에 안 그려진다 (기록에는 저장됨)
        elif "스트리밍" in prompt:
            # st.empty(): 요소 "하나" 만 담는 자리표시자. 여기에 다시 그리면 앞의 것을 지우고 바꿔 끼운다
            # [반환] 자리표시자 컨테이너 -> message_placeholder.write(...) 처럼 쓴다
            # [왜] 같은 자리에 글을 조금씩 늘려 가며 다시 그리면 타자 치는 것처럼 보인다
            message_placeholder = st.empty()
            full_response = f"'{prompt}'에 대한 답변입니다. 스트리밍 효과로 한 글자씩 표시됩니다!"

            displayed_text = ""
            # 문자열을 for 로 돌면 한 글자씩 나온다 [출처] 파이썬 기본
            # displayed_text += char: 지금까지의 글에 한 글자를 붙인다. "▌" 는 커서처럼 보이게 붙인 글자
            # 주의: 이것은 "완성된 글" 을 한 글자씩 보여 주는 흉내일 뿐 진짜 스트리밍이 아니다.
            #       진짜 스트리밍은 LLM 이 조각을 내보내는 대로 그리는 것 (st.write_stream 으로 할 수 있다. 맨 위 HEADER 참고)
            for char in full_response:
                displayed_text += char
                message_placeholder.write(displayed_text + "▌")
                time.sleep(0.02)

            # 마지막에 커서 "▌" 없이 완성 글로 바꿔 끼운다
            message_placeholder.write(full_response)
            response_message["content"] = full_response

        # 4. 일반 메시지 (에코)
        else:
            # f-string 안에 \n 과 마크다운(**굵게**, - 목록)을 섞어 쓴 안내 글
            response_message["content"] = f"에코: {prompt}\n\n💡 **명령어를 입력해보세요:**\n- '스키마 보여줘'\n- 'OpenAI 찾아줘'\n- '스트리밍'"

        # 최종 응답 표시 (스트리밍이 아닌 경우)
        # 스트리밍 분기는 이미 자리표시자에 글을 그렸으니 두 번 그리지 않으려고 제외한다
        # 주의: 분기를 "어느 분기로 갔는지" 가 아니라 다시 글자 포함 여부로 판단해서, 위 스트리밍 분기의 주의처럼 어긋날 수 있다
        if "스트리밍" not in prompt:
            st.write(response_message["content"])

        # 응답(내용 + 도구 호출 기록)을 대화 기록에 저장 -> 다음 재실행 때 for 문이 다시 그린다
        st.session_state.messages.append(response_message)

# 대화 초기화 버튼
# len(리스트) > 1: 인사말 말고 대화가 하나라도 있을 때만 초기화 버튼을 보여 준다 [출처] 파이썬 기본 len
if len(st.session_state.messages) > 1:
    if st.button("🗑️ 대화 초기화"):
        # 처음 상태(인사말 하나)로 되돌리고 st.rerun() 으로 즉시 다시 그린다
        # [왜] 이 버튼은 대화를 이미 다 그린 "뒤" 에 있어서, rerun 하지 않으면 지운 대화가 이번 실행 화면에 그대로 남는다
        st.session_state.messages = [
            {"role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?"}
        ]
        st.rerun()

st.divider()


# ============================================
# 사이드바
# ============================================

# with st.sidebar: 이 블록의 요소는 왼쪽 사이드바에 그려진다. 파일 맨 아래에 있어도 화면에서는 왼쪽에 보인다
with st.sidebar:
    st.title("⚙️ 챗봇 설정")

    st.subheader("모델 설정")
    # st.selectbox(라벨, 선택지 리스트): 드롭다운 / [반환] 고른 값 (기본은 첫 번째, index=0)
    # st.slider(라벨, 0.0, 1.0, 0.7): 실수를 넣었으니 실수 값을 돌려준다
    # 주의: model, temperature 는 화면에 보여 주기만 하고 응답 만들기에는 쓰이지 않는다 (가짜 챗봇이라서)
    model = st.selectbox("모델 선택", ["gpt-4o", "gpt-4o-mini", "gpt-5.4"])
    temperature = st.slider("Temperature", 0.0, 1.0, 0.7)

    st.subheader("연결 정보")
    st.text("Neo4j: bolt://localhost:7687")
    st.text(f"Model: {model}")

    st.divider()

    # "messages" in st.session_state 검사는 사실상 항상 참이다 (위 "세션 상태 초기화" 에서 이미 만들었으므로). 지워도 동작은 같다
    if st.button("모든 대화 초기화"):
        if "messages" in st.session_state:
            st.session_state.messages = [
                {"role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?"}
            ]
        st.rerun()