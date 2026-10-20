"""
[3단계: 주석만] 구조와 할 일 목록만 있고 코드는 전부 직접 쓴다.

규칙:
  - 함수 이름과 주석(할 일)만 보고 구현한다.
  - 처음 막힌 곳이 곧 복습해야 할 곳이다. 그 지점을 아래에 메모해 두자.
  - 막히면 step2 -> step1 -> 원본 csv2kg.py 순서로 힌트를 본다.

막힌 곳 메모:
  -
"""

# 필요한 import 도 직접 정한다.
# (환경변수 읽기, 경로 다루기, CSV 읽기, .env 로딩, Neo4j 드라이버)

# 환경변수에서 NEO4J_URI / USERNAME / PASSWORD 를 읽는다. 데이터베이스 이름 = USERNAME.
# CSV 폴더는 이 파일 기준 상위의 output/ 으로 잡는다.


def create_neo4j_driver(uri, username, password):
    """driver 를 만들고 연결을 검증해서 돌려준다. 실패하면 메시지를 찍고 예외를 다시 던진다."""


def clear_database(driver):
    """전부 삭제. 재실행해도 같은 결과가 나오게 하는 이유를 한 줄로 적어 보자."""


def create_constraints(driver):
    """Passenger.PassengerId, PClass.Pclass, Cabin.Cabin, Port.Port 에 UNIQUE 제약조건."""


def load_nodes(driver, csv_path, label, properties):
    """
    과제: step1 에서는 노드 로더가 4개로 복붙되어 있다.
    label 과 properties 목록을 받아 하나의 함수로 일반화해 보자.
    (주의: 레이블은 Cypher 파라미터로 못 넘긴다. 왜인가? 그리고 f-string 으로 넣을 때 무엇을 조심해야 하나?)
    """


def create_relationships(driver, csv_path, rel_type, start, end, props=None):
    """
    과제: 관계 생성 4개도 하나로 일반화한다.
    start / end 는 (레이블, 노드키, CSV 열 이름) 정보를 담는다.
    TRAVELED_WITH 는 관계 속성(Ticket)이 있고 CSV 가 없을 수도 있다.
    """


def print_graph_statistics(driver):
    """노드·관계 개수를 DB 에서 직접 세어 출력한다. CSV 행 수와 같은지 눈으로 비교."""


def main():
    """연결 -> 초기화 -> 노드 4종 -> 관계 4종 -> 통계 -> 연결 종료(에러가 나도 반드시)."""


if __name__ == "__main__":
    main()


# ---------- 끝난 뒤 스스로 점검 ----------
# [ ] 두 번 연속 실행해도 개수가 같은가? (멱등)
# [ ] 노드 생성 전에 관계를 만들면 어떻게 되는가?
# [ ] 제약조건을 지우고 실행하면 무엇이 달라지는가? (중복, 속도)
# [ ] Neo4j Browser 에서 "같은 티켓으로 함께 탄 3등급 승객"을 Cypher 로 조회해 보자.
