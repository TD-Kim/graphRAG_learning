"""
[1단계: 읽기] part1/ch2_python_neo4j.py 의 "왜" 주석 버전 (동작은 원본과 동일)

Part 1 / CH02-05. 파이썬에서 Neo4j 를 쓰는 두 가지 방법을 비교하는 파일이다.
  방법 A. driver.execute_query()          -> 간단. 짧은 쿼리 한 번에 적합. (신규 코드는 이쪽이 기본)
  방법 B. session + execute_read/write()  -> 트랜잭션 함수. 여러 쿼리를 한 트랜잭션으로 묶거나
                                             실패 시 자동 재시도가 필요할 때.

사전 조건: .env 에 NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD,
           Neo4j 샌드박스(Stack Overflow 예제: Tag, Question, User) 데이터.
"""
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase, RoutingControl

# .env -> 환경변수. 비밀번호를 코드/깃에 남기지 않기 위해서다.
load_dotenv()

URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")
# AuraDB/샌드박스는 데이터베이스 이름이 사용자 이름과 같다. (로컬 Desktop 은 보통 "neo4j")
NEO4J_DATABASE = USERNAME

# driver 는 연결 풀을 가진 객체라 프로그램 전체에서 하나만 만든다.
driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
# driver() 는 접속하지 않는다. 계정/주소가 틀렸는지 지금 바로 확인한다.
driver.verify_connectivity()


# =========================================================
# 방법 A-1. 조회: execute_query
# =========================================================
# 반환값은 (records, summary, keys) 세 개:
#   records: 결과 행들 / summary: 실행 통계 / keys: RETURN 의 컬럼 이름들
records, summary, keys = driver.execute_query(
    # 화살표 방향에 주의: (Tag)<-[:TAGGED]-(Question)<-[:ASKED]-(User)
    # "neo4j 태그가 달린 질문과 그 질문자"를 거꾸로 따라간다.
    """
    MATCH (t:Tag {name: $tagName})<-[:TAGGED]-(q:Question)<-[:ASKED]-(u:User)
    RETURN q.title AS title, u.display_name AS author
    LIMIT 5
    """,
    database_=NEO4J_DATABASE,  # 끝에 _ 가 붙은 인자는 드라이버 설정, 없는 인자는 쿼리 파라미터다.
    tagName="neo4j",           # $tagName 파라미터. 문자열 포맷팅 대신 쓰는 이유: 인젝션 방지 + 쿼리 플랜 캐시
    routing_=RoutingControl.READ,  # 읽기 전용이라고 알려 주면 클러스터에서 읽기 서버로 보낼 수 있다.
)

for record in records:
    print(record.data())  # record.data() -> {"title": ..., "author": ...} 딕셔너리
    # record["title"] 처럼 컬럼 이름으로 직접 꺼낼 수도 있다.

# summary 로 쿼리가 실제로 어떻게 실행됐는지 확인한다. (성능 점검의 첫걸음)
print(
    f"쿼리`{summary.query}`가 반환한 결과 {len(records)} 개는 "
    f"{summary.result_available_after} ms 만에 반환되었습니다.\n"
)


# =========================================================
# 방법 A-2. 생성: 같은 execute_query, 쿼리만 CREATE
# =========================================================
create_query = """
CREATE (q:Question {
    id: $questionId,
    title: $title,
    body: $body,
    created_at: datetime()
})
RETURN q.id AS new_id, q.title AS new_title
"""
# datetime() 은 DB 서버 시간. 파이썬 시간을 넘기지 않아서 시계가 어긋날 일이 없다.

records, summary, keys = driver.execute_query(
    create_query,
    questionId=999999,  # 샌드박스 원본 id 와 겹치지 않을 큰 값
    title="질문의 제목입니다.",
    body="질문의 본문입니다.",
    database_=NEO4J_DATABASE,
)

# CREATE 뒤에 RETURN 을 붙였으니 records 가 비어 있지 않다.
if records:
    print(f"ID '{records[0]['new_id']}'인 질문이 생성되었습니다.")
    # 쓰기 쿼리의 검증은 summary.counters 로 한다. "몇 개가 실제로 만들어졌나".
    print(f"생성된 노드 개수: {summary.counters.nodes_created}")

# 다 쓴 driver 는 닫아서 연결 풀을 반납한다.
driver.close()


# =========================================================
# 방법 B. 세션 + 트랜잭션 함수 (execute_read)
# =========================================================
# 위에서 driver 를 닫았으니 새로 만든다. (원본 파일이 두 방식을 한 파일에 나란히 보여주려는 구조)
driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
driver.verify_connectivity()


# 트랜잭션 함수: 첫 번째 인자 tx 는 드라이버가 만들어서 넣어 준다.
# 일시적 오류(네트워크, 리더 변경)가 나면 드라이버가 이 함수를 "통째로 다시" 실행한다.
# 그래서 함수 안에서는 외부 상태를 바꾸지 않아야 한다. (멱등하게)
def get_questions(tx, tag_name):
    result = tx.run(
        """
        MATCH (t:Tag {name: $tagName})<-[:TAGGED]-(q:Question)<-[:ASKED]-(u:User)
        RETURN q.title AS title, u.display_name AS author
        LIMIT 5
        """,
        tagName=tag_name,
    )
    # result 는 트랜잭션이 끝나면 못 읽는 "게으른" 스트림이다.
    # 그래서 함수 안에서 리스트로 모두 꺼내서 돌려줘야 한다.
    return [record.data() for record in result]


# with: 블록이 끝나면 세션이 자동으로 닫힌다.
with driver.session(database=NEO4J_DATABASE) as session:
    # execute_read: 읽기 트랜잭션. 쓰기는 execute_write 를 쓴다.
    # 뒤쪽 인자("neo4j")는 get_questions 의 tag_name 으로 전달된다.
    records = session.execute_read(get_questions, "neo4j")
    for record in records:
        print(record)

driver.close()

# 정리: 언제 무엇을 쓰나?
#   - 쿼리 1개, 간단한 스크립트        -> driver.execute_query()
#   - 여러 쿼리를 하나의 트랜잭션으로, 또는 재시도 로직이 중요 -> session.execute_read/write()
