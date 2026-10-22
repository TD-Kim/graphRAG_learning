"""
[2단계: 빈칸 채우기] 진짜 LLM 에 연결된 최소 챗봇. 가짜 응답(02_chatbot_ui.py) 대신 OpenAI 스트리밍을 쓴다.

실행: part4/streamlit 에서 `streamlit run learning/step2_fill_in.py`
필요: OPENAI_API_KEY
막히면 GUIDE.md -> 02_chatbot_ui.py
"""
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
st.set_page_config(page_title="최소 챗봇", page_icon="💬")
st.title("💬 최소 챗봇 (진짜 LLM)")

# ---------- 사이드바: 설정이 실제로 쓰이게 ----------
with st.sidebar:
    model = st.selectbox("모델", ["gpt-4o-mini", "gpt-4o"])
    temperature = st.slider("Temperature", 0.0, 1.0, 0.3)
    system_prompt = st.text_area("시스템 프롬프트", "당신은 친절한 한국어 어시스턴트입니다.")
    # TODO 1: "대화 초기화" 버튼을 누르면 messages 를 빈 리스트로 만들고 st.rerun()


# ---------- 세션 상태 ----------
# TODO 2: st.session_state 에 "messages" 가 없으면 빈 리스트로 초기화한다.
#   왜 이 코드가 필요한가? (Streamlit 은 매번 파일을 처음부터 다시 실행한다)


# ---------- 이전 대화 다시 그리기 ----------
# TODO 3: messages 를 돌며 st.chat_message(role) 안에 content 를 st.markdown 으로 그린다.


# ---------- 새 입력 ----------
if prompt := st.chat_input("메시지를 입력하세요"):
    # TODO 4-1: 사용자 메시지를 messages 에 추가하고 화면에 그린다.

    with st.chat_message("assistant"):
        client = OpenAI()
        # TODO 4-2: 시스템 프롬프트 + 지금까지의 messages 를 합쳐 API 에 보낸다. stream=True
        #   stream = client.chat.completions.create(model=model, temperature=temperature, stream=True, messages=[...])
        # TODO 4-3: st.write_stream 에 "토큰 문자열을 하나씩 내보내는 제너레이터"를 넘기면 진짜 스트리밍이 된다.
        #   def tokens():
        #       for chunk in stream:
        #           delta = chunk.choices[0].delta.content if chunk.choices else None
        #           if delta: yield delta
        #   answer = st.write_stream(tokens())
        answer = ""

    # TODO 4-4: 완성된 answer 를 assistant 메시지로 messages 에 추가한다.
    #   이걸 빠뜨리면 다음 재실행 때 답변이 화면에서 사라진다. 직접 빼고 확인해 보자.
