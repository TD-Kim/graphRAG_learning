"""
[2단계: 빈칸 채우기] final_chatbot 의 구조적 문제 4가지를 고친 버전을 만든다.
  1. 설정 검사를 맨 위에서
  2. 에이전트/드라이버는 cache_resource 로 한 번만
  3. 도구 결과를 tool_call_id 로 정확히 짝짓기
  4. 진짜 토큰 스트리밍 (stream_mode="messages")

그래프 시각화는 원본의 visualize_graph_results 를 그대로 쓴다.
실행: part4/final_chatbot 에서 `streamlit run learning/step2_fill_in.py`
막히면 GUIDE.md 생각해 볼 점 1~6 -> app.py
"""
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "graphrag_tool_agent"))
load_dotenv()

st.set_page_config(page_title="GraphRAG 챗봇 (개선판)", page_icon="🔗", layout="wide")

# ---------- 1. 설정 검사 (맨 위에서) ----------
# TODO 1: OPENAI_API_KEY, NEO4J_URI 중 없는 것이 있으면 st.error 로 알리고 st.stop().
#   원본은 이 검사가 파일 맨 끝에 있어서, 초기화가 먼저 실패한다.


# ---------- 2. 한 번만 만들기 ----------
@st.cache_resource
def get_agent():
    # TODO 2: graphrag_tool_agent 의 create_graphrag_agent() 를 불러 돌려준다.
    #   cache_resource 는 모든 사용자/재실행이 같은 객체를 공유한다. session_state 와 차이를 주석으로 적자.
    ...


if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("💬 GraphRAG 챗봇 (개선판)")

# 이전 대화 다시 그리기
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        for call in m.get("tool_calls", []):
            with st.expander(f"🔧 {call['name']}"):
                st.json(call["args"])
                if "result" in call:
                    st.text(call["result"][:2000])

if prompt := st.chat_input("질문을 입력하세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        agent = get_agent()
        calls: dict[str, dict] = {}     # tool_call_id -> {name, args, result}
        answer_box = st.empty()
        answer = ""
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]

        # ---------- 3, 4. 진짜 스트리밍 + 정확한 짝짓기 ----------
        # stream_mode="messages" 는 (메시지 조각, 메타데이터) 튜플을 토큰 단위로 내보낸다.
        for msg, meta in agent.stream({"messages": history}, stream_mode="messages"):
            kind = type(msg).__name__
            # TODO 3-1: AIMessageChunk 이고 tool_call_chunks 가 있으면, 도구 호출이 만들어지는 중이다.
            #           완성된 호출 정보는 AIMessage 의 tool_calls 로 오지 않을 수 있으니,
            #           ToolMessage 가 올 때 tool_call_id 와 name 으로 calls 에 기록하는 쪽이 간단하다.
            # TODO 3-2: ToolMessage 면 calls[msg.tool_call_id] = {"name": msg.name, "args": {}, "result": str(msg.content)}
            #           (원본은 "마지막 호출"에 붙여서, 동시 호출이면 결과가 엇갈린다)
            # TODO 4: AIMessageChunk 이고 content 가 있으면 answer 에 이어 붙이고 answer_box.markdown(answer + "▌")
            #   메타데이터의 langgraph_node 가 "model"(또는 agent) 인 것만 답변으로 보자.
            pass

        answer_box.markdown(answer or "(답변 없음)")
        for call in calls.values():
            with st.expander(f"🔧 {call['name']}"):
                st.text(call["result"][:2000])

        st.session_state.messages.append({"role": "assistant", "content": answer, "tool_calls": list(calls.values())})

# 확인: 질문 하나에 도구가 2개 이상 불리는 질문으로, 결과가 올바른 도구 아래에 붙는지 본다.
