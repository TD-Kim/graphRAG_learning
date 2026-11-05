"""[1단계: 읽기] app.py (graphrag_tool_agent 에이전트를 Streamlit 챗봇으로 감싸고, Cypher 결과를 pyvis 그래프로 그리기) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
설치 소스로 확인한 버전 (requirements.txt 기준): streamlit 1.57.0, langgraph 1.1.10, langchain 1.2.17,
  neo4j 6.1.0, pyvis 0.3.2, python-dotenv 1.2.2
먼저 part4/streamlit 의 주석본 두 개(실행 모델, session_state, chat_message/chat_input)를 읽으면 좋다.

Streamlit 실행 모델 복습: 채팅을 보낼 때마다 이 파일 전체가 위에서부터 다시 실행된다.
  -> 에이전트와 대화 기록은 st.session_state 에 두고, 지난 대화는 매 실행마다 다시 그린다.

흐름 (질문 하나를 보냈을 때의 한 번의 실행)
  import -> sys.path 에 ../graphrag_tool_agent 추가 -> main.create_graphrag_agent 가져오기
  -> session_state 초기화 (agent 는 세션당 처음 한 번만 만든다)
  -> 사이드바, 제목 -> 지난 대화 다시 그리기 (도구 호출 Expander, 그래프 iframe 까지)
  -> chat_input 으로 질문 도착
       -> agent.stream({"messages": 대화 기록})   (기본 stream_mode="updates": 노드 하나가 끝날 때마다 {노드이름: 바뀐 상태})
            ├─ "model" 노드의 AIMessage + tool_calls  -> "🔧 도구 호출" Expander
            ├─ "tools" 노드의 ToolMessage             -> Cypher 코드 / 실행 결과 / 기타 결과 Expander
            └─ "model" 노드의 AIMessage + content     -> 최종 답변 (한 글자씩 보여 주는 흉내)
       -> Cypher 와 결과가 둘 다 있으면 visualize_graph_results: RETURN 절을 노드/관계 변수로 바꿔 "다시" 실행 -> pyvis HTML
       -> 답변 + 도구 호출 + 그래프 HTML 을 messages 에 저장 (다음 재실행 때 다시 그리려고)
  -> 맨 끝: main() (환경변수 검사. Streamlit 에서도 __name__ 이 "__main__" 이라 매 실행마다 마지막에 불린다)

다른 폴더 의존 (중요)
  원본 11줄은 "이 파일이 있는 폴더/../graphrag_tool_agent" 를 import 경로에 넣는다.
  원본 app.py (part4/final_chatbot/app.py) 기준이면 part4/graphrag_tool_agent 가 맞게 잡히지만,
  이 주석본은 learning/ 안에 있어서 part4/final_chatbot/graphrag_tool_agent (없는 폴더) 를 가리킨다.
  -> 그래서 이 주석본을 실행할 때는 PYTHONPATH 로 에이전트 폴더를 직접 알려 준다.
  graphrag_tool_agent 의 main.py / tools.py 가 필요로 하는 것: pdf2kg 로 만든 그래프와 벡터 인덱스가 든 Neo4j,
  OPENAI_API_KEY, NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD (graphrag_tool_agent 의 GUIDE.md 참고)

.env 를 어디서 읽나 (python-dotenv 1.2.2 소스 확인)
  load_dotenv() 는 "load_dotenv 를 부른 파일이 있는 폴더" 부터 위로 올라가며 .env 를 찾고, 이미 있는 환경변수는 덮어쓰지 않는다.
  import 순서상 graphrag_tool_agent 의 main.py/tools.py 의 load_dotenv 가 먼저 실행된다
  -> part4/graphrag_tool_agent/.env 가 있으면 그 값이 먼저 들어가고, 이 파일의 load_dotenv 로 읽는 final_chatbot/.env 보다 우선할 수 있다.

읽는 순서 권장: 세션 상태 초기화 -> 지난 대화 다시 그리기 -> chat_input 블록(스트리밍 루프) -> visualize_graph_results -> main
실행 위치: part4/final_chatbot  ->  PYTHONPATH=../graphrag_tool_agent streamlit run learning/step1_annotated.py
  (원본은 part4/final_chatbot 에서 streamlit run app.py. Windows PowerShell 이면 $env:PYTHONPATH="../graphrag_tool_agent" 후 실행)
  주의: 실제 OpenAI API 호출(유료)과 Neo4j 접속이 일어난다.
"""

# [출처] 표준 라이브러리 base64: 글/바이트를 영문자+숫자로만 된 글로 바꾼다 -> 그래프 HTML 을 iframe 의 data: 주소에 넣을 때
import base64
# [출처] 표준 라이브러리 os: 환경변수(os.getenv), 경로(os.path), 파일 삭제(os.unlink)
import os
# [출처] 표준 라이브러리 re: 정규식. LLM 이 만든 Cypher 를 글자 패턴으로 찾고 바꾼다
import re
# [출처] 표준 라이브러리 sys: sys.path (import 할 때 모듈을 찾는 폴더 목록)
import sys
# [출처] 표준 라이브러리 time: 한 글자씩 보여 줄 때 time.sleep
import time

# [출처] 외부 라이브러리 streamlit
import streamlit as st
# [출처] 외부 라이브러리 python-dotenv. load_dotenv: .env 파일 내용을 환경변수로 등록
from dotenv import load_dotenv
# [출처] 외부 라이브러리 neo4j 드라이버. 그래프 시각화용으로 따로 연결할 때 쓴다
from neo4j import GraphDatabase

# sys.path.insert(0, 폴더): import 할 때 이 폴더를 "가장 먼저" 찾게 한다
# os.path.dirname(__file__): 이 파일이 있는 폴더 / os.path.join(a, "..", "b"): a 의 부모 폴더 아래 b
# [왜] 옆 폴더 part4/graphrag_tool_agent 의 main.py, tools.py 를 패키지 설치 없이 그대로 가져다 쓰려고
# 주의: 이 주석본(learning/ 안)에서는 이 경로가 없는 폴더를 가리킨다. 실행법은 맨 위 HEADER 참고
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "graphrag_tool_agent"))

# [출처] 다른 폴더(part4/graphrag_tool_agent/main.py)에서 정의
# create_graphrag_agent(): 도구 4개(schema_introspection, generate_cypher_query, execute_cypher_query, vector_search)를
#   가진 LangChain create_agent(model="gpt-4o") 에이전트를 만들어 돌려준다
# import 하는 순간 main.py 맨 위가 실행된다: load_dotenv(), 그리고 main.py 가 tools.py 를 import (tools.py 도 load_dotenv)
# 주의: 모듈 이름이 "main" 이라 흔한 이름이다. 경로 앞쪽에 다른 main.py 가 있으면 그것이 잡힐 수 있다
from main import create_graphrag_agent

# .env 를 읽어 환경변수로 (이미 등록된 값은 덮어쓰지 않는다. 위 import 에서 이미 읽은 값이 있으면 그것이 남는다)
load_dotenv()


# [이 파일에서 정의] LLM 이 만든 Cypher 를 "그림 그리기용" 으로 고쳐 다시 실행하고, pyvis 그래프 HTML 을 돌려준다
# [입력] cypher_query: generate_cypher_query 도구의 결과 Cypher 글
#        results: execute_cypher_query 도구의 결과 글 (이 함수 안에서는 쓰지 않는다. 호출 조건에만 쓰임)
# [반환] HTML 문자열, 또는 노드가 없거나 실패하면 None
# [왜] 원래 쿼리는 RETURN c.name AS 회사명 처럼 "값" 만 돌려줘서 그림을 그릴 수 없다.
#      노드/관계 "객체" 를 받아야 점(노드)과 선(관계)을 그릴 수 있다
# : str 는 타입 힌트 [출처] 파이썬 기본. 실행에는 영향이 없고 읽는 사람에게 알려 주는 표시
def visualize_graph_results(cypher_query: str, results: str):
    """Cypher 쿼리 결과를 그래프로 시각화 - 실제 Neo4j 그래프 구조 기반"""
    # try/except [출처] 파이썬 기본: try 블록에서 에러가 나면 멈추지 않고 except 블록으로 간다 (맨 아래 except 에서 경고만 띄움)
    try:
        # 함수 안에서 import: 이 함수가 처음 불릴 때 불러온다. [출처] 표준 라이브러리 tempfile (임시 파일)
        import tempfile

        # [출처] 외부 라이브러리 pyvis. Network: vis.js 기반 인터랙티브 네트워크 그림을 HTML 로 만들어 주는 클래스
        from pyvis.network import Network

        # Neo4j 연결
        # GraphDatabase.driver(주소, auth=(아이디, 비밀번호)): Neo4j 드라이버 객체 [반환] Driver
        # 주의: 그림을 그릴 때마다 드라이버를 새로 만들고 닫는다. tools.py 에 이미 만들어 둔 드라이버가 있는데 따로 만든다
        # 주의: driver.close() 가 try 블록 중간(원본 160줄)에 있어서, 쿼리 실행에서 에러가 나면 close 되지 않고 except 로 빠진다
        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
        )

        # Network(height=캔버스 높이, width=폭, bgcolor=배경색, font_color=글자색) [반환] 빈 그래프 그림 객체
        net = Network(height="550px", width="100%", bgcolor="#222222", font_color="white")
        # barnes_hut(...): 노드끼리 밀어내고(gravity 음수) 관계로 당기는 물리 배치 방식 설정. 0.3.2 의 기본 gravity 는 -80000 인데 여기선 -8000
        net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=250)

        # 원본 쿼리를 수정해서 그래프 패스를 반환하도록
        # MATCH (m:AImodel)-[r:DEVELOPED_BY]->(c:Company) ... RETURN m, r, c
        # 변수 = 같은 글을 가리키는 새 이름. 문자열은 바꿀 수 없는(immutable) 값이라, 아래 re.sub 는 "새 글" 을 만들어 modified_query 에 다시 넣는다
        modified_query = cypher_query

        # RETURN 절을 찾아서 수정
        # .upper(): 대문자로 바꾼 글 -> return / Return 처럼 소문자로 써도 찾는다
        if "RETURN" in modified_query.upper():
            # MATCH 패턴에서 변수 추출
            # re.search(패턴, 글, 플래그): 글에서 패턴과 처음 맞는 곳 하나 [반환] Match 객체 또는 None
            # 패턴 MATCH\s+(.+?)(?:WHERE|RETURN|$): "MATCH 공백" 뒤부터 WHERE/RETURN/글끝 직전까지를 1번 그룹으로
            #   \s+ = 공백 1개 이상, (.+?) = 최대한 짧게, (?:...) = 묶기만 하고 그룹으로 저장하지 않음
            # r'...' 는 raw 문자열 [출처] 파이썬 기본: 역슬래시를 그대로 둔다 (정규식에 꼭 필요)
            # re.IGNORECASE = 대소문자 무시, re.DOTALL = . 이 줄바꿈도 포함, | 로 플래그 둘을 같이 준다
            # 주의: 첫 MATCH 만 본다. MATCH 가 여러 개이거나 OPTIONAL MATCH, WITH 가 있으면 일부 변수만 잡힌다
            match_pattern = re.search(r'MATCH\s+(.+?)(?:WHERE|RETURN|$)', modified_query, re.IGNORECASE | re.DOTALL)
            if match_pattern:
                # .group(1): 1번 괄호에 걸린 글 / .strip(): 앞뒤 공백 제거
                match_clause = match_pattern.group(1).strip()

                # 노드 변수 추출: (변수:라벨) 패턴
                # re.findall: 맞는 것을 "모두" 찾아 리스트로. 괄호 그룹이 하나면 그 그룹 글만 모은다
                # \((\w+):\w+\) : (변수:레이블) 모양에서 변수 이름만. \( 는 글자 ( 자체, \w+ 는 영문/숫자/_ 1개 이상
                # 주의: (c:Company {name: 'OpenAI'}) 처럼 속성이 붙은 노드나 (c) 처럼 레이블 없는 노드는 못 잡는다
                nodes = re.findall(r'\((\w+):\w+\)', match_clause)

                # 관계 변수 추가: [:타입] → [r:타입] 형식으로 변경
                # 기존 관계 변수가 있는지 확인
                # \[(\w+):\w+\] : [r:관계타입] 모양에서 관계 변수 이름만
                # 주의: [r:TYPE*1..2] 같은 가변 길이는 끝이 ] 가 아니라 안 잡힌다
                existing_rels = re.findall(r'\[(\w+):\w+\]', match_clause)

                # 관계 변수가 없으면 자동으로 추가
                # 관계에 변수가 하나도 없으면 [:TYPE 를 [r0:TYPE, [r1:TYPE ... 로 바꿔 변수를 붙인다
                if not existing_rels:
                    # [:TYPE] → [r0:TYPE] 형식으로 변경
                    rel_count = 0
                    # 함수 안의 함수 (중첩 함수) [출처] 파이썬 기본. re.sub 가 맞는 곳마다 이 함수를 불러 "바꿀 글" 을 받는다
                    # [입력] match: 맞은 곳의 Match 객체 [반환] 바꿔 넣을 글
                    def add_rel_var(match):
                        # nonlocal [출처] 파이썬 기본: 바깥 함수의 변수 rel_count 를 "새 지역 변수로 만들지 말고" 그것을 바꾸겠다는 선언
                        # (없으면 rel_count += 1 에서 UnboundLocalError)
                        nonlocal rel_count
                        var_name = f"r{rel_count}"
                        rel_count += 1
                        return f"[{var_name}:{match.group(1)}"

                    # re.sub(패턴, 바꿀함수, 글): 맞는 곳을 모두 바꾼 새 글. 두 번째 인자로 함수를 주면 맞은 곳마다 그 함수의 반환값으로 바꾼다
                    # 주의: 쿼리 "전체" 에서 바꾼다 (MATCH 밖, 문자열 안의 [: 도 바뀔 수 있다)
                    modified_query = re.sub(r'\[:(\w+)', add_rel_var, modified_query)

                    # 다시 추출
                    # 바꾼 쿼리에서 MATCH 절과 관계 변수를 다시 뽑는다
                    match_pattern = re.search(r'MATCH\s+(.+?)(?:WHERE|RETURN|$)', modified_query, re.IGNORECASE | re.DOTALL)
                    if match_pattern:
                        match_clause = match_pattern.group(1).strip()
                        existing_rels = re.findall(r'\[(\w+):\w+\]', match_clause)

                # 그래프 요소를 반환하도록 쿼리 수정
                # 리스트 + 리스트 = 이어 붙인 새 리스트 [출처] 파이썬 기본. 예: ["m", "c"] + ["r0"] -> ["m", "c", "r0"]
                graph_elements = nodes + existing_rels

                if graph_elements:
                    # RETURN 절 교체
                    # RETURN\s+.+$ (DOTALL): 첫 RETURN 부터 글 끝까지 전부를 "RETURN m, c, r0 LIMIT 20" 으로 바꾼다
                    # ', '.join(리스트): 쉼표+공백으로 이어 붙인 글
                    # 주의: 원래의 ORDER BY, LIMIT 도 같이 지워진다. WITH 로 변수를 넘기며 집계한 쿼리는 앞쪽 변수가 사라져 에러가 날 수 있다
                    # 주의: 고친 쿼리를 읽기 전용 제한 없이 그대로 실행한다 (LLM 이 쓰기 쿼리를 만들었다면 그것도 다시 실행된다)
                    modified_query = re.sub(
                        r'RETURN\s+.+$',
                        f"RETURN {', '.join(graph_elements)} LIMIT 20",
                        modified_query,
                        flags=re.IGNORECASE | re.DOTALL
                    )

        # 쿼리 실행
        # with driver.session() as session: 세션을 열고 블록이 끝나면 자동으로 닫는다
        # session.run(쿼리) [반환] Result. for 로 돌면 Record 가 하나씩 나온다
        with driver.session() as session:
            result = session.run(modified_query)

            # set() [출처] 파이썬 기본: 중복 없는 모음. 이미 그린 노드/관계를 또 그리지 않으려고 기록한다
            added_nodes = set()
            added_edges = set()

            for record in result:
                # 레코드의 각 값 처리
                # record.keys(): RETURN 한 이름들 / record[key]: 그 값 (노드, 관계, 또는 일반 값)
                for key in record.keys():
                    value = record[key]

                    # 노드인 경우
                    # hasattr(객체, "이름"): 그 속성이 있는지 [출처] 파이썬 기본
                    # neo4j 6.1.0 소스: Node 는 labels(레이블 frozenset)와 element_id(노드 고유 ID 글)를 가진다 -> "노드인가?" 를 이렇게 판별
                    # 주의: Path(경로) 객체는 labels 도 type 도 없어서 그냥 건너뛴다
                    if hasattr(value, 'labels') and hasattr(value, 'element_id'):
                        node_id = value.element_id
                        if node_id not in added_nodes:
                            # frozenset 은 순서가 없어서 list 로 바꾼 뒤 [0] 을 대표 레이블로 쓴다 (레이블이 여러 개면 어느 것이 먼저일지 정해져 있지 않다)
                            # A if 조건 else B : 조건식 [출처] 파이썬 기본
                            labels = list(value.labels)
                            label = labels[0] if labels else "Node"

                            # 노드 속성에서 name 또는 첫 번째 속성 가져오기
                            # dict(value.items()): 노드 속성을 일반 딕셔너리로
                            props = dict(value.items())
                            # a or b or c: 앞에서부터 처음으로 "참" 인 값 [출처] 파이썬 기본 -> name 없으면 title, 그것도 없으면 "레이블_ID"
                            display_name = props.get('name') or props.get('title') or f"{label}_{node_id}"

                            # 속성 정보를 툴팁으로
                            # [f"{k}: {v}" for k, v in ...] : 리스트 컴프리헨션 [출처] 파이썬 기본 (for 문으로 리스트 만들기를 한 줄로)
                            # list(props.items())[:5]: 속성 앞 5개만 (슬라이싱) -> 마우스를 올렸을 때 보일 툴팁 글
                            hover_text = f"{label}\n" + "\n".join([f"{k}: {v}" for k, v in list(props.items())[:5]])

                            # 라벨별 색상
                            color = "#97C2FC"  # 기본 파란색
                            if label in ["Company", "Organization"]:
                                color = "#FB7E81"  # 빨간색
                            elif label in ["AImodel", "Model"]:
                                color = "#FFA807"  # 주황색
                            elif label in ["Person"]:
                                color = "#90EE90"  # 연두색

                            # net.add_node(노드ID, label=점 아래 글, title=툴팁, color=색, size=크기): 그림에 점 하나 추가 [출처] pyvis
                            net.add_node(
                                node_id,
                                label=str(display_name),
                                title=hover_text,
                                color=color,
                                size=25
                            )
                            added_nodes.add(node_id)

                    # 관계인 경우
                    # elif: 노드가 아니면 관계인지 검사. neo4j Relationship 은 type(관계 타입 글), start_node, end_node 를 가진다
                    elif hasattr(value, 'type') and hasattr(value, 'start_node') and hasattr(value, 'end_node'):
                        # (시작ID, 끝ID, 타입) 튜플을 관계의 이름표로 쓴다. 튜플은 set 에 넣을 수 있다 (바뀌지 않는 값이라서)
                        # 주의: 같은 두 노드 사이에 같은 타입 관계가 여러 개면 하나만 그려진다
                        edge_id = (value.start_node.element_id, value.end_node.element_id, value.type)
                        if edge_id not in added_edges:
                            # 시작/끝 노드도 추가
                            # 관계만 RETURN 된 경우에도 양 끝 노드를 그리려고 추가 (위 노드 처리와 같은 코드가 반복된다)
                            for node in [value.start_node, value.end_node]:
                                node_id = node.element_id
                                if node_id not in added_nodes:
                                    labels = list(node.labels)
                                    label = labels[0] if labels else "Node"
                                    props = dict(node.items())
                                    display_name = props.get('name') or props.get('title') or f"{label}_{node_id}"
                                    hover_text = f"{label}\n" + "\n".join([f"{k}: {v}" for k, v in list(props.items())[:5]])

                                    color = "#97C2FC"
                                    if label in ["Company", "Organization"]:
                                        color = "#FB7E81"
                                    elif label in ["AImodel", "Model"]:
                                        color = "#FFA807"
                                    elif label in ["Person"]:
                                        color = "#90EE90"

                                    net.add_node(node_id, label=str(display_name), title=hover_text, color=color, size=25)
                                    added_nodes.add(node_id)

                            # 관계 추가
                            # net.add_edge(시작ID, 끝ID, label=선 위 글, title=툴팁): 선 하나 추가 [출처] pyvis
                            net.add_edge(
                                value.start_node.element_id,
                                value.end_node.element_id,
                                label=value.type,
                                title=value.type
                            )
                            added_edges.add(edge_id)

        driver.close()

        # 노드가 없으면 시각화하지 않음
        # len(set) == 0: 하나도 없으면. st.info 로 알리고 None 반환
        if len(added_nodes) == 0:
            st.info("그래프 결과가 없습니다. 쿼리가 노드/관계를 반환하지 않았습니다.")
            return None

        # HTML 생성
        # tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html', encoding='utf-8'): 이름 있는 임시 파일
        # delete=False: with 가 끝나도 지우지 않는다 (아래에서 다시 읽은 뒤 직접 지운다)
        # net.generate_html() [반환] 완성된 HTML 문자열 (pyvis 0.3.2 소스: 템플릿에 노드/관계/옵션을 채워 넣는다)
        # 참고: html 변수를 이미 갖고 있으므로 파일에 썼다가 다시 읽는 과정은 없어도 결과가 같다
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html', encoding='utf-8') as f:
            html = net.generate_html()
            f.write(html)
            temp_path = f.name

        # open(경로, 'r', encoding='utf-8') [출처] 파이썬 기본: 파일 읽기 / f.read(): 전부 읽은 글
        with open(temp_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # os.unlink(경로): 파일 삭제
        os.unlink(temp_path)

        # HTML에 명시적인 높이 추가
        # .replace(찾을 글, 바꿀 글): 모두 바꾼 새 글
        # pyvis 템플릿이 "height: {{height}};" 로 되어 있어 "height: 550px" 가 들어 있다 -> 600px 로 바꾸고 body 여백을 없앤다
        # 참고: Network 의 cdn_resources 기본값 "local" 이면 HTML 이 lib/bindings/utils.js 를 상대 경로로 부른다.
        #       data: 주소 iframe 에서는 그 파일을 찾을 수 없어 일부 기능이 안 될 수 있다 (vis-network 본체는 CDN 에서 받는다)
        html_content = html_content.replace(
            '<body>',
            '<body style="margin:0; padding:0; height:600px; overflow:hidden;">'
        )
        html_content = html_content.replace(
            'height: 550px',
            'height: 600px'
        )

        return html_content

    # Exception: 거의 모든 에러의 부모 클래스. as e 로 에러 객체를 받는다
    # st.warning: 노란 경고 상자. 앱은 멈추지 않는다
    except Exception as e:
        st.warning(f"그래프 시각화 실패: {str(e)}")
        return None


# 페이지 설정
# st.set_page_config: 탭 제목/아이콘/넓은 레이아웃 (part4/streamlit 01_basics 참고)
st.set_page_config(
    page_title="GraphRAG 챗봇",
    page_icon="🔗",
    layout="wide"
)

# 세션 상태 초기화
# [핵심 패턴] 대화 기록은 "없을 때만" 빈 리스트로 (첫 실행). 재실행 때는 쌓인 기록 유지
if "messages" not in st.session_state:
    st.session_state.messages = []

# 에이전트도 세션당 한 번만 만든다. 매 재실행마다 만들면 질문할 때마다 초기화 비용이 든다
# st.spinner: 만드는 동안 "초기화 중..." 표시
# 참고: session_state 는 브라우저 탭(세션)마다 따로라서, 탭마다 에이전트가 하나씩 만들어진다.
#       @st.cache_resource 를 붙인 함수로 만들면 서버 전체에서 하나만 만들어 공유한다 (소스: 기본 scope="global", 모든 사용자/세션/재실행 공유)
# 참고: tools.py 의 드라이버/LLM 은 모듈 전역 변수라, 사실 이미 모든 세션이 하나를 같이 쓴다 (import 된 모듈은 한 번만 로드되므로)
# 주의: 키나 DB 설정이 없으면 여기서 먼저 실패한다. 맨 아래 main() 의 환경변수 검사는 이보다 늦게 실행된다
if "agent" not in st.session_state:
    with st.spinner("GraphRAG Agent 초기화 중..."):
        st.session_state.agent = create_graphrag_agent()

# 사이드바
# with st.sidebar: 이 블록의 요소는 왼쪽 사이드바에
with st.sidebar:
    st.title("🔗 GraphRAG 챗봇")
    st.markdown("""
    ### 지원 기능

    **Text2Cypher** (구조화된 질의)
    - 특정 엔티티 속성값 검색
    - 관계 기반 질의 (소속, 직책 등)
    - 정확한 개수, 목록, 통계

    **Vector Search** (의미 기반 검색)
    - 관련 내용 기반 질문
    - 의미 기반 텍스트 검색
    - 그래프 관계를 통한 컨텍스트 확장
    """)

    # st.button: 누른 직후 그 실행에서만 True -> 기록 비우고 st.rerun() 으로 즉시 다시 그림
    if st.button("대화 기록 초기화"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("**연결 정보**")
    # os.getenv(이름, 기본값): 환경변수가 없으면 'Not configured' 를 보여 준다
    st.text(f"Neo4j: {os.getenv('NEO4J_URI', 'Not configured')}")
    # 주의: 모델 이름을 글로 고정해 둔 것이다 (main.py 의 model="gpt-4o" 와 따로 관리됨). 중괄호 없는 f-string 이라 f 는 없어도 같다
    st.text(f"Model: gpt-4o")

# 제목
# st.caption: 작은 회색 설명 글
st.title("💬 GraphRAG 챗봇")
st.caption("Neo4j 기반 지식 그래프 검색 및 질의응답 시스템")

# 이전 대화 기록 표시
# [왜] 재실행되면 화면을 다시 그려야 하므로, 기록 전체를 매번 처음부터 다시 그린다
# st.chat_message(role): "user"/"assistant" 이름이면 정해진 모양과 아바타의 말풍선
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # st.markdown: 답변에 들어 있는 마크다운(굵게, 목록 등)을 그대로 살려 그린다
        st.markdown(message["content"])

        # 도구 호출 정보가 있으면 표시
        if "tool_calls" in message:
            for tool_call in message["tool_calls"]:
                # 지난 도구 호출은 접어서(expanded=False) 보여 준다
                with st.expander(f"🔧 도구 호출: {tool_call['name']}", expanded=False):
                    st.json(tool_call["args"])

                    # Cypher 쿼리인 경우 코드 블록으로 표시
                    # 결과가 있고 그 도구가 generate_cypher_query 면 Cypher 색칠 코드 블록, 다른 도구 결과는 st.text
                    if "result" in tool_call and tool_call["name"] == "generate_cypher_query":
                        st.code(tool_call["result"], language="cypher")
                    elif "result" in tool_call:
                        st.text(tool_call["result"])

        # 그래프 시각화가 있으면 표시
        if "graph_html" in message:
            # base64.b64encode(바이트) [반환] base64 바이트 -> .decode() 로 글. 문자열.encode() 는 글 -> 바이트 (utf-8)
            # [왜] HTML 전체를 iframe 의 src="data:text/html;base64,..." 주소 안에 통째로 넣으려고
            b64_html = base64.b64encode(message["graph_html"].encode()).decode()
            iframe_html = f'<iframe src="data:text/html;base64,{b64_html}" width="100%" height="600" frameborder="0"></iframe>'
            # unsafe_allow_html=True: st.markdown 이 HTML 태그(여기선 iframe)를 글자로 바꾸지 않고 HTML 로 그리게 허용
            # 참고: Streamlit 화면 쪽(JavaScript)에서 iframe 을 어떻게 처리하는지는 파이썬 소스로 확인 못 함
            st.markdown(iframe_html, unsafe_allow_html=True)

# 사용자 입력
# st.chat_input: 본문 맨 아래에 고정되는 채팅 입력칸 [반환] 방금 보낸 글이 있으면 문자열, 없으면 None
# := (월러스 연산자): 값을 prompt 에 넣으면서 바로 if 조건으로 검사 [출처] 파이썬 기본 (3.8+)
if prompt := st.chat_input("질문을 입력하세요..."):
    # 사용자 메시지 표시
    # 먼저 기록에 추가하고, 이번 실행에서는 직접 한 번 그린다 (위 for 문은 이미 지나갔으므로)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Agent 응답 생성
    with st.chat_message("assistant"):
        # st.container(): 여러 요소를 담는 빈 상자 / st.empty(): 요소 하나만 담는 자리표시자 (다시 그리면 바꿔 끼움)
        # [왜] 상자를 먼저 "위→아래" 순서로 만들어 두면, 나중에 무엇을 넣든 도구 호출들은 위 상자에, 답변은 아래 자리에 그려진다
        tool_calls_container = st.container()
        response_placeholder = st.empty()

        # 리스트 컴프리헨션으로 기록에서 role 과 content 만 뽑은 새 리스트 (방금 넣은 질문까지 포함)
        # [왜] LangChain 에이전트는 {"role": ..., "content": ...} 딕셔너리 리스트를 메시지로 받아들인다
        # 주의: tool_calls, 도구 결과, graph_html 은 빠진다 -> 다음 질문에서 에이전트는 이전 Cypher 결과를 모른다 (GUIDE 생각해 볼 점 2)
        # 주의: 에러 메시지("오류 발생: ...")도 assistant 내용으로 기록되어 다음 질문 때 에이전트에게 넘어간다
        conversation_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in st.session_state.messages
        ]

        # 스트리밍 도중에 모을 값들을 빈 값으로 준비
        agent_response = ""
        tool_calls_info = []
        cypher_query = None
        cypher_results = None

        try:
            # Agent 스트리밍
            # agent.stream(입력): 에이전트(LangGraph 그래프)를 실행하면서 중간 결과를 하나씩 내보내는 제너레이터
            # [입력] {"messages": 대화 기록}
            # [반환] 조각(chunk)을 하나씩 준다. langgraph 1.1.10 소스: create_agent 가 만든 그래프는 기본 stream_mode="updates"
            #        -> chunk 는 {노드이름: 그 노드가 바꾼 상태} 딕셔너리. 노드 이름은 "model"(LLM 호출) 과 "tools"(도구 실행) (langchain 1.2.17 소스)
            # 흐름 예: {"model": {"messages": [AIMessage(tool_calls=[...])]}} -> {"tools": {"messages": [ToolMessage(...)]}} -> ... -> {"model": {"messages": [AIMessage(content="답변")]}}
            for chunk in st.session_state.agent.stream({"messages": conversation_history}):
                # .items(): (키, 값) 짝들 [출처] 파이썬 기본. node_name 은 여기서 쓰지 않는다
                for node_name, node_data in chunk.items():
                    if "messages" in node_data:
                        messages = node_data["messages"]

                        for msg in messages:
                            # type(msg).__name__: 객체의 클래스 이름 글 ("AIMessage", "ToolMessage" 등) [출처] 파이썬 기본
                            # (isinstance(msg, AIMessage) 로 비교하는 것이 더 일반적이다. 그러려면 langchain_core 에서 클래스를 import 해야 한다)
                            msg_type = type(msg).__name__

                            if msg_type == "AIMessage":
                                # Tool 호출
                                # AIMessage.tool_calls: LLM 이 부르겠다고 한 도구 목록. 각 항목은 {"name": 도구이름, "args": 인자 dict, "id": 호출ID} 모양
                                # 비어 있으면(빈 리스트) 도구를 부르지 않은 "최종 답변" 메시지다
                                # 주의: 도구 호출과 글(content)을 같이 가진 AIMessage 면 elif 때문에 그 글은 무시된다
                                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                    for tool_call in msg.tool_calls:
                                        tool_info = {
                                            "name": tool_call['name'],
                                            "args": tool_call['args']
                                        }
                                        tool_calls_info.append(tool_info)

                                        # 도구 호출 표시
                                        # with tool_calls_container: 위에 만들어 둔 상자 안에 그린다 (with 를 겹쳐 쓰면 안쪽 expander 가 그 상자 안에 들어간다)
                                        with tool_calls_container:
                                            with st.expander(f"🔧 도구 호출: {tool_call['name']}", expanded=True):
                                                st.json(tool_call['args'])

                                # 최종 응답 (스트리밍 효과)
                                # elif msg.content: 도구 호출이 없고 글이 있으면 최종 답변
                                elif msg.content:
                                    agent_response = msg.content

                                    # 한 글자씩 스트리밍 효과
                                    displayed_text = ""
                                    # 한 글자씩 덧붙여 st.empty 자리에 다시 그리는 "타자기 흉내" (part4/streamlit 02_chatbot_ui 와 같은 방법)
                                    # 주의: 답변이 이미 다 만들어진 뒤에 보여 주기만 하는 것이라, 기다리는 시간은 줄지 않고 오히려 글자 수 x 0.01초가 더해진다
                                    #       (1000자면 약 10초 + 화면 갱신 1000번)
                                    # 참고: 진짜 토큰 스트리밍은 agent.stream(..., stream_mode="messages") 로 LLM 조각을 받아 그리는 것.
                                    #       st.write_stream 은 LangChain AIMessageChunk 조각을 글로 바꿔 타자기 효과로 그려 준다 (streamlit 1.57.0 소스).
                                    #       다만 "messages" 모드는 (조각, 메타데이터) 짝을 주므로, 조각만 골라 내보내는 작은 제너레이터 함수가 필요하다
                                    for char in agent_response:
                                        displayed_text += char
                                        response_placeholder.markdown(displayed_text + "▌")
                                        time.sleep(0.01)

                                    # 커서 제거하고 최종 표시
                                    response_placeholder.markdown(agent_response)

                            # ToolMessage: 도구 실행 결과 메시지. content 에 도구 함수가 돌려준 글이 들어 있다
                            elif msg_type == "ToolMessage":
                                # Tool 실행 결과
                                # str(...): 글로 바꾼다 [출처] 파이썬 기본
                                result = str(msg.content)

                                # 해당 도구 정보에 결과 추가
                                if tool_calls_info:
                                    # 리스트[-1]: 마지막 항목 [출처] 파이썬 기본 -> "가장 최근 도구 호출" 에 결과를 붙인다
                                    # 주의: LLM 이 도구 여러 개를 한 번에(병렬로) 부르면 결과가 엉뚱한 호출에 붙는다.
                                    #       ToolMessage.tool_call_id 와 tool_call["id"] 로 짝을 맞추면 정확하다 (GUIDE 생각해 볼 점 3)
                                    tool_calls_info[-1]["result"] = result

                                    # generate_cypher_query 결과인 경우
                                    if tool_calls_info[-1]["name"] == "generate_cypher_query":
                                        # generate_cypher_query 의 결과 = Cypher 글. 그래프 시각화에 쓰려고 따로 보관
                                        cypher_query = result
                                        with tool_calls_container:
                                            # 주의: 중괄호 없는 f-string (f 를 빼도 같다). 아래 "📊 쿼리 실행 결과" Expander 도 같다
                                            with st.expander(f"📝 생성된 Cypher 쿼리", expanded=True):
                                                st.code(result, language="cypher")

                                    # execute_cypher_query 결과인 경우
                                    elif tool_calls_info[-1]["name"] == "execute_cypher_query":
                                        # execute_cypher_query 의 결과 글 보관
                                        # 주의: tools.py 의 execute_cypher_query 는 실패해도 "쿼리 실행 중 오류 발생..." 같은 글을 돌려주고, 결과 0건이어도 글을 돌려준다.
                                        #       그래서 cypher_results 는 대개 "참" 이 되어, 실패한 쿼리로도 아래 시각화를 시도할 수 있다
                                        cypher_results = result
                                        with tool_calls_container:
                                            with st.expander(f"📊 쿼리 실행 결과", expanded=True):
                                                st.text(result)

                                    # 기타 도구 결과
                                    else:
                                        with tool_calls_container:
                                            with st.expander(f"✅ {tool_calls_info[-1]['name']} 결과", expanded=False):
                                                st.text(result)

            # 그래프 시각화 (Cypher 결과가 있는 경우)
            # 그래프 시각화는 Cypher 와 실행 결과가 둘 다 있을 때만 (Text2Cypher 경로를 탔을 때)
            # Vector Search 경로만 탔다면 cypher_query 가 None 이라 건너뛴다
            graph_html = None
            if cypher_query and cypher_results:
                try:
                    # visualize_graph_results 안에서도 try/except 로 에러를 잡지만, 바깥에서 한 번 더 감싼다
                    graph_html = visualize_graph_results(cypher_query, cypher_results)
                    if graph_html:
                        # 그림은 Expander 안에 iframe 으로 넣는다 (지난 대화 다시 그리기와 같은 base64 방법)
                        with st.expander("🌐 그래프 시각화", expanded=True):
                            b64_html = base64.b64encode(graph_html.encode()).decode()
                            iframe_html = f'<iframe src="data:text/html;base64,{b64_html}" width="100%" height="600" frameborder="0"></iframe>'
                            st.markdown(iframe_html, unsafe_allow_html=True)
                except Exception as e:
                    st.warning(f"그래프 시각화 중 오류 발생: {str(e)}")

            # 응답을 세션에 저장
            # 기록에 남길 응답 딕셔너리. agent_response 가 빈 글이면 or 뒤의 "처리 완료" 가 들어간다
            message_data = {
                "role": "assistant",
                "content": agent_response or "처리 완료"
            }

            # 도구 호출 정보와 그래프 HTML 은 있을 때만 키를 추가 -> 위 "지난 대화 다시 그리기" 의 "키" in message 검사와 짝이 맞는다
            # [왜] 저장하지 않으면 다음 재실행(다음 질문) 때 화면에서 사라진다
            # 참고: 그래프 HTML 은 크기가 커서, 대화가 길어지면 session_state 와 매 재실행의 그리기 양이 함께 커진다
            if tool_calls_info:
                message_data["tool_calls"] = tool_calls_info

            if graph_html:
                message_data["graph_html"] = graph_html

            st.session_state.messages.append(message_data)

        # 스트리밍 도중 에러(API 키, DB 연결, 네트워크 등)가 나면 빨간 상자로 보여 주고 에러 글을 기록에 남긴다
        # 주의: 에러 전까지 화면에 그린 도구 호출 정보는 기록에 저장되지 않아 다음 재실행 때 사라진다
        except Exception as e:
            error_msg = f"오류 발생: {str(e)}"
            st.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg
            })


# [이 파일에서 정의] 필수 환경변수가 있는지 검사하고 없으면 에러 상자 + st.stop()
# st.stop(): 그 자리에서 이번 실행을 멈춘다 (아래 문장은 실행 안 함)
# 주의: Streamlit 은 파일을 위에서부터 실행하므로 이 함수는 맨 마지막에 불린다.
#       키가 없으면 그 전에 에이전트 초기화(세션 상태 초기화 부분)에서 이미 실패한다. 검사는 파일 앞쪽(set_page_config 바로 뒤)에 있어야 의미가 있다
def main():
    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        st.stop()

    if not os.getenv("NEO4J_URI"):
        st.error("NEO4J_URI가 설정되지 않았습니다. .env 파일을 확인하세요.")
        st.stop()


# if __name__ == "__main__": 이 파일을 "직접 실행" 했을 때만 [출처] 파이썬 기본
# streamlit 1.57.0 소스: 매 실행마다 types.ModuleType("__main__") 으로 새 모듈을 만들어 그 안에서 파일을 실행한다
# -> __name__ 이 "__main__" 이므로 streamlit run 에서도 매 재실행 끝에 main() 이 불린다
if __name__ == "__main__":
    main()
