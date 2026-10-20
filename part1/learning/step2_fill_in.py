"""
[2단계: 빈칸 채우기] part1/ch2_python_neo4j.py 를 TODO 를 채워서 완성한다.

방법:
  1. 위에서부터 TODO 를 채운다.
  2. 막히면 step1_annotated.py 의 같은 부분을 본다. (정답은 원본 ch2_python_neo4j.py)
  3. 실행해서 질문 5개가 출력되고, 생성된 노드 개수가 1이면 성공.

실행 위치: part1  ->  python learning/step2_fill_in.py
"""
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase, RoutingControl

load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = USERNAME

# TODO 1: driver 를 만들고, 연결이 되는지 바로 확인한다.
driver = ...  # GraphDatabase.driver(URI, auth=(?, ?))
# ...  # 힌트: verify_ 로 시작하는 메서드


# ---------- A-1. 조회 ----------
# TODO 2: execute_query 로 "neo4j 태그가 달린 질문의 제목과 질문자 이름" 5개를 조회한다.
#   - 그래프 경로: (Tag)<-[:TAGGED]-(Question)<-[:ASKED]-(User)
#   - 태그 이름은 문자열을 직접 이어 붙이지 말고 $tagName 파라미터로 넘긴다.
#   - RETURN 의 컬럼 이름: title, author  (q.title / u.display_name)
#   - 읽기 전용임을 알리는 routing_ 옵션을 준다.
records, summary, keys = ...

# TODO 3: records 를 순회하며 딕셔너리로 출력한다. (힌트: record.data())

# TODO 4: summary 에서 "실행한 쿼리"와 "결과가 준비되기까지 걸린 ms" 를 출력한다.
#   (summary.query, summary.result_available_after)


# ---------- A-2. 생성 ----------
# TODO 5: Question 노드를 하나 만든다. 속성: id, title, body, created_at(서버 시간)
#   - 서버 시간은 Cypher 함수 datetime() 을 쓴다.
#   - RETURN 으로 id, title 을 돌려받는다.
create_query = """
...
"""

# TODO 6: 실행하고 summary.counters 에서 "생성된 노드 개수"를 출력한다.
records, summary, keys = ...

driver.close()


# ---------- B. 세션 + 트랜잭션 함수 ----------
driver = ...  # TODO 7: driver 를 다시 만든다 (위에서 닫았으므로)


# TODO 8: 트랜잭션 함수 get_questions(tx, tag_name) 을 만든다.
#   - tx.run(쿼리, 파라미터) 로 TODO 2 와 같은 조회를 한다.
#   - 반환은 [record.data() for record in result] 처럼 "함수 안에서" 리스트로 만들어 돌려준다.
#     (왜 함수 밖이 아니라 안에서 읽어야 할까? 직접 밖으로 빼서 실행해 보면 에러로 알 수 있다.)
def get_questions(tx, tag_name):
    ...


# TODO 9: with driver.session(database=...) as session: 안에서
#         session.execute_read(get_questions, "neo4j") 를 호출하고 결과를 출력한다.

driver.close()
