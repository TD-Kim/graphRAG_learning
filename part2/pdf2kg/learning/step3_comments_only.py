"""
[3단계: 주석만] 원본에서 "미완성"으로 남은 [3단계] — 제목 level 로 parent 관계를 만드는 일.
직접 설계해 본 뒤 정답과 비교한다. 정답: pdf2kg.py 의 extract_hierarchical_toc (99~151줄, 부모 스택 방식).

입력: (title, level, page) 가 문서 순서대로 나열된 제목 리스트
      예) [("1. 개요",1), ("1.1 배경",2), ("1.2 목적",2), ("2. 방법",1), ("2.1 데이터",2), ("2.1.1 수집",3)]
출력: TOCNode 리스트 (toc_id, title, level, parent_id, is_leaf)

막힌 곳 메모:
  -
"""

# 0. toc_extract 의 TOCNode dataclass 를 가져오거나 같은 필드로 다시 정의한다.

# 1. toc_id 규칙을 정한다. (예: "toc_0001" 처럼 순번, 또는 "1.2.1" 같은 번호)
#    왜 title 을 id 로 쓰면 안 되나? (같은 제목이 여러 곳에 있을 수 있다)

# 2. parent 찾기: 스택 하나로 풀 수 있다.
#    - 제목을 문서 순서대로 훑는다.
#    - 스택의 맨 위가 현재 level 이상이면 pop 한다. (같거나 깊은 level 은 형제/자손이 아니다)
#    - 스택이 비었으면 parent 는 None(최상위), 아니면 스택 맨 위가 parent.
#    - 현재 제목을 스택에 push.
#    -> 손으로 위의 예시 리스트를 따라가며 스택이 어떻게 변하는지 종이에 써 보자.

# 3. is_leaf 계산: 다른 노드의 parent_id 로 한 번도 등장하지 않은 노드가 leaf.
#    leaf 아래에만 본문 Chunk 를 붙이는 이유를 한 줄로 적어 보자.

# 4. 예외 처리:
#    - 첫 제목이 level 2 로 시작하면? (부모가 없는 level 2)
#    - level 이 1 -> 3 으로 건너뛰면? (중간 level 이 없음)
#    어떻게 다룰지 정하고 이유를 주석으로 남긴다.

# 5. 검증: 위 예시 리스트를 넣어 parent_id / is_leaf 를 출력하고 기대값과 비교하는 assert 를 쓴다.

# 6. (다음 단계 예고) Neo4j 에 저장
#    - MERGE (d:Document {...}) / MERGE (t:TOC {toc_id: ...})
#    - (d)-[:HAS_TOC]->(level1), (parent)-[:HAS_CHILD]->(child)
#    - 노드 키에 UNIQUE 제약조건을 먼저 만든다. (csv2kg 의 create_constraints 와 같은 이유)
#    CREATE 가 아니라 MERGE 를 쓰는 이유는? 두 번 실행하면 어떻게 달라지나?

# ---------- 끝난 뒤 스스로 점검 ----------
# [ ] 스택 방식을 아무것도 안 보고 설명할 수 있는가?
# [ ] 제목 level 이 틀리게 나온 PDF 에서는 어디가 가장 먼저 깨지는가?
