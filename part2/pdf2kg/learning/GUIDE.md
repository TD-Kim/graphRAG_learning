# pdf2kg 읽기 가이드

강의: Part 2 / CH02-03, 04 PDF 문서를 지식그래프로 변환하기 (1) 목차 (2) 본문

| 파일 | 줄 | 하는 일 | 학습 파일 |
|---|---|---|---|
| [`toc_extract.py`](../toc_extract.py) | 125 | docling 계층 복원 전/후 비교 실험 | `step1_annotated.py`, `step2_fill_in.py` |
| [`pdf2kg.py`](../pdf2kg.py) | 638 | **Stage 1**: PDF → 문서 구조 그래프 (Document, TOC, Chunk, Element) | 이 가이드, `step3_comments_only.py` |
| [`pdf2kg_2.py`](../pdf2kg_2.py) | 581 | **Stage 2**: Chunk → LLM 이 설계한 스키마로 도메인 엔티티/관계 | 이 가이드, `step2_domain_fill_in.py` |

## 한눈에 보기

```
Stage 1 (pdf2kg.py) - LLM 없음, 문서 "모양"을 그래프로
  PDF ─docling─▶ 제목 level 복원 ─▶ TOC 트리(부모 스택) ─▶ 본문/표를 현재 제목에 매핑 ─▶ Neo4j
  (Document)-[:HAS_TOC]->(TOC)-[:HAS_CHILD]->(TOC)-[:HAS_CHUNK]->(Chunk)-[:HAS_ELEMENT]->(TextElement|TableElement)

Stage 2 (pdf2kg_2.py) - LLM 사용, 문서 "내용"을 그래프로
  Chunk 샘플 ─LLM─▶ 스키마 설계(노드 5-8종, 관계 8-10종) ─▶ Chunk 마다 스키마대로 추출 ─▶ 엔티티 MERGE, 관계 MERGE
  (Chunk)-[:HAS_ENTITY]->(도메인 엔티티)-[:동적 관계]->(도메인 엔티티)
```

이 두 층을 합친 것이 README 그림의 **lexical graph(문서 구조) + domain graph(내용)** 모델이다.
나중에 GraphRAG 에서 "답의 근거가 문서 어디에 있나"를 Chunk → TOC → Document 로 거슬러 올라가 보여줄 수 있는 이유가 Stage 1 이다.

## Stage 1: `pdf2kg.py` 읽는 순서

| 순서 | 함수 | 줄 | 핵심 |
|---|---|---|---|
| 1 | `__main__` | 612 | `process_pdf` → JSON 저장 → Neo4j 저장 |
| 2 | `extract_hierarchical_toc` | 76 | **부모 스택**으로 parent_id 계산 (toc_extract 의 미완성 3단계의 답) |
| 3 | `extract_and_map_elements` | 167 | 문서를 순서대로 훑으며 "지금 어느 제목 아래인가"를 따라 본문/표를 붙인다 |
| 4 | `calculate_toc_stats` | 300 | 사람이 확인할 수 있는 트리 요약 txt 저장 |
| 5 | `save_to_neo4j` | 402 | 노드를 먼저 다 만들고, 관계는 `toc_id` 값을 맞춰 한 번에 연결 |

### 함수별 "왜"
- **부모 스택 (112~115줄)**: 스택 맨 위 level 이 현재 level 이상이면 pop → 남은 맨 위가 부모. 문서를 한 번만 훑어 트리를 만든다.
  `is_leaf` 는 처음엔 True, 자식이 생기면 부모를 False 로 바꾼다(144줄).
- **제목 2자 미만 버리기 (107줄)**: docling 이 페이지 번호나 기호를 제목으로 잘못 잡는 경우를 거른다.
- **`page_no + 1` (125줄)**: docling 은 0부터 세고 사람은 1부터 센다.
- **`(title, page)` 로 TOC 찾기 (179, 209줄)**: 같은 제목이 여러 번 나올 수 있어서 제목만으로는 못 찾는다. 같은 키가 또 있으면 `pop(0)` 으로 순서대로 하나씩 쓴다.
- **5자 미만 텍스트 버리기 (224줄)**: 쪽번호, 머리말 같은 잡음 제거.
- **표는 마크다운으로 (272줄)**: LLM 이 읽기 좋은 형태로 바꿔 둔다. Stage 2 에서 표 내용도 추출 대상이 된다.
- **Chunk = 한 TOC 아래의 본문 + 표 전체 (474~490줄)**: 글자 수가 아니라 **문서 구조 단위**로 자른다. txt2kg 의 고정 길이 청킹과 비교해 보자.
- **관계는 나중에 한 번에 (465, 513줄)**: 노드에 `parent_id`, `toc_id` 를 저장해 두고 `WHERE child.parent_id = parent.toc_id` 로 연결한다. 노드를 만들 때마다 관계를 만드는 것보다 코드가 단순하다.
- **`Level1:TOC` 처럼 레이블 2개 (440줄)**: "모든 목차"(TOC)와 "특정 깊이 목차"(Level2)를 둘 다 쉽게 찾으려고.
- **TextElement 는 100개씩 UNWIND (535줄)**: csv2kg 에서 본 배치 삽입.

### 생각해 볼 점
1. `MATCH (parent:TOC), (child:TOC) WHERE ...` 는 모든 쌍을 비교한다. 노드가 1만 개면? `toc_id` 에 제약조건(인덱스)을 걸면 어떻게 달라질까?
2. Chunk 크기에 상한이 없다. 한 절이 매우 길면 Stage 2 에서 LLM 입력이 커진다. 어떻게 나눌까?
3. `save_to_json` 은 텍스트를 앞 100개만 저장한다(388줄). Neo4j 에는 전부 들어간다. 왜 다르게 했을까?
4. 본문이 첫 제목보다 앞에 있으면(`current_toc is None`) 버려진다(220줄). 표지/요약문이 사라져도 괜찮을까?

## Stage 2: `pdf2kg_2.py` 읽는 순서

| 순서 | 함수 | 줄 | 핵심 |
|---|---|---|---|
| 1 | `__main__` | 541 | 스키마 생성 → 도메인 그래프 구축 → 통계 |
| 2 | `get_chunks` | 57 | Stage 1 이 만든 Chunk 를 읽는다 (Stage 1 이 먼저 돌아야 하는 이유) |
| 3 | `generate_schema` | 79 | **LLM 이 스키마를 설계**한다 |
| 4 | `build_extraction_prompt` | 204 | 그 스키마를 프롬프트에 넣어 추출 범위를 제한한다 |
| 5 | `extract_entities_relationships` | 251 | Chunk 하나 → Entity/Relationship dataclass |
| 6 | `process_chunk`, `build_domain_graph` | 413, 442 | Chunk 마다 추출 → 노드 → Chunk 연결 → 관계 |
| 7 | `create_entity_node`, `create_relationship`, `link_entity_to_chunk` | 339~411 | 저장 쿼리 |
| 8 | `sanitize_relationship_type` | 326 | LLM 이 만든 관계 이름을 Cypher 에 넣어도 안전하게 |

### 함수별 "왜"
- **스키마를 먼저 만드는 이유**: txt2kg 처럼 청크마다 LLM 이 마음대로 레이블을 만들면 "Organization / 조직 / Company"처럼 같은 개념이 여러 레이블로 흩어진다. 먼저 문서 전체 샘플로 스키마를 정하고 그 안에서만 추출하게 하면 그래프가 일관된다.
- **스키마 생성은 temperature 0.3, 추출은 0.1**: 설계는 약간의 다양성을 허용하고, 추출은 일관성을 우선한다.
- **엔티티 키 = `타입:이름` (342줄)**: 같은 이름이라도 타입이 다르면 다른 엔티티("Apple" 회사 vs 과일).
- **`MERGE ... ON CREATE SET` (351줄)**: 처음 만들 때만 id 와 속성을 넣는다. 이미 있으면 그대로 둔다.
- **관계는 양 끝이 모두 만들어졌을 때만 (375줄)**: 끊어진 관계를 미리 거른다(txt2kg 의 검증 단계와 같은 역할).
- **`HAS_ENTITY` (404줄)**: 엔티티가 어느 Chunk 에서 나왔는지 연결한다. 근거 추적의 핵심.
- **`sanitize_relationship_type`**: 영문/숫자/언더스코어만 남기고 대문자로. 숫자로 시작하면 접두어. LLM 출력이 쿼리 구조에 들어갈 때의 방어.

### 생각해 볼 점
1. 관계 타입은 sanitize 하는데 **엔티티 타입(레이블)은 그대로** f-string 에 들어간다(351줄). 타입에 공백이 있으면? 실패하면 `entity_name_to_id` 에 등록되지 않아 그 엔티티의 관계도 전부 빠진다.
2. `generate_schema` 가 예외로 끝나면 `None` 을 돌려주고, 추출 프롬프트에 `None` 이 스키마로 들어간다. 어떻게 막을까?
3. `MATCH (source {name: ...})` 에 레이블이 없다(383줄). 같은 이름의 다른 타입 노드가 있으면?
4. LLM 이 스키마에 없는 타입을 내놓으면 지금은 그대로 저장된다. 스키마에서 허용 타입 목록을 뽑아 걸러 내려면?
5. 스키마를 사람이 검토/수정하는 단계를 넣는다면 어디에? (FDE 강의의 "사람이 루프 안에" 와 같은 생각)

## 실행 전 체크
- Stage 1 은 **DB 전체를 지우고** 시작한다. Stage 2 는 지우지 않고 Stage 1 결과 위에 덧붙인다.
- 순서: `python pdf2kg.py` → `python pdf2kg_2.py`
- Stage 2 는 Chunk 수만큼 LLM 을 부른다(최대 100). 처음엔 `MAX_CHUNKS` 를 작게.
