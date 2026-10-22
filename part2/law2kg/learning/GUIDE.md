# law2kg 읽기 가이드

강의: Part 2 / CH02-05, 06 법률·법령 정보를 지식그래프로 변환하기 (1) Open API (2) 현행법령과 해석례 통합

| 파일 | 줄 | 역할 |
|---|---|---|
| [`law_api.py`](../law_api.py) | 216 | 국가법령정보센터 API 호출 2개(목록, 상세) + 연결 테스트 |
| [`law2kg.py`](../law2kg.py) | 1107 | 그래프 구축 함수 전부 (실행 파일 아님) |
| [`step1_load_laws.py`](../step1_load_laws.py) | 102 | **실행 1**: 현행법령 → 법령/조/항/호 그래프 |
| [`step2_link_interpretations.py`](../step2_link_interpretations.py) | 105 | **실행 2**: 해석례 → 질의/회답/이유 + 법령에 연결 |

## 한눈에 보기

```
[1단계] 정형 데이터 → 그래프 (LLM 없음)
  목록 API ─▶ 상세 API(JSON 중첩) ─▶ 조문/항/호 파싱 ─▶ (Law)-[:HAS_ARTICLE]->(Article)-[:HAS_PARAGRAPH]->(Paragraph)-[:HAS_ITEM]->(Item)
                                                     + (Article)-[:NEXT_ARTICLE]->(Article)

[2단계] 반정형 텍스트 → 기존 그래프에 연결 (정규식 + LLM)
  적재된 법령명으로 해석례 검색 ─▶ 제목의 「법령명」이 그래프에 있는 것만 ─▶ 해석례/질의/회답/이유 노드
     ─▶ 「법령명」 정규식으로 INTERPRETS ─▶ LLM 으로 "제4조제1항" 같은 인용 추출 ─▶ CITES (조/항/호/다른 법령)
```

txt2kg, pdf2kg 와 다른 점: **스키마를 사람이 정했고**, 정형 데이터(API JSON)를 최대한 쓰고 LLM 은 "인용 조문 추출"이라는 좁은 일에만 쓴다.
실무 데이터는 대부분 이 모양(정형 + 일부 텍스트)이다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | `law_api.py` 전체 | 목록(`lawSearch.do`)과 상세(`lawService.do`) 두 엔드포인트. `target=law` 현행법령, `target=expc` 해석례 |
| 2 | `step1_load_laws.py` | `setup_neo4j` → `build_law_graph` → 통계 |
| 3 | `law2kg.py` `setup_neo4j` (21) | 키마다 UNIQUE 제약조건 |
| 4 | `build_law_graph` (382) | 목록 페이지를 돌며 법령마다 노드 + 상세 조회 |
| 5 | `extract_articles_from_law_detail` 외 2개 (152~220) | **중첩 JSON 파싱**. dict 하나 / list 여러 개 처리 |
| 6 | `create_article_structure` (258) | 조-항-호 노드와 관계, `NEXT_ARTICLE` |
| 7 | `step2_link_interpretations.py` | `build_interpretation_graph` 호출 |
| 8 | `build_interpretation_graph` (916) | 해석례 검색 → 필터 → 노드 → 연결 순서 |
| 9 | `create_interpretation_node` (447) | 해석례/질의/회답/이유 노드 + LLM 인용 추출 호출 |
| 10 | `link_to_law` (762), `link_cited_articles` (580), `link_cited_laws` (851) | INTERPRETS, CITES |
| 11 | `extract_law_citations_with_llm` (66) | LLM 에게 맡기는 유일한 일 |

## 함수별 "왜"

### 1단계
- **`if isinstance(x, dict): x = [x]` 가 계속 나온다 (161, 183, 212, 400줄)**: 이 API 는 항목이 1개면 객체, 여러 개면 배열로 준다. 이걸 맞추지 않으면 반복문이 dict 의 키를 돌게 된다. 외부 API 를 다룰 때 흔한 함정.
- **`a.get('조문번호') or a.get('조번호')`**: 응답 필드 이름이 법령마다 조금씩 달라서 후보를 순서대로 시도한다.
- **id 를 경로로 만든다** (`{law_id}_{조번호}_p{항순서}_i{호순서}`): 부모 id 를 포함하니 전역에서 유일하고, 다시 돌려도 같은 id → `MERGE` 로 중복 없이 재실행할 수 있다.
- **`MERGE ... SET` 패턴**: 키로 찾거나 만들고, 나머지 속성은 매번 덮어쓴다. 법령이 개정돼 다시 적재해도 최신 값이 된다.
- **관계에 `order` 속성**: 조문 순서를 보존한다. 그래프는 순서가 없으니 명시해야 한다.
- **`NEXT_ARTICLE` (370줄)**: `collect` 로 순서대로 모은 뒤 `range` 로 이웃 쌍을 만든다. "제3조 다음 조문은?" 같은 탐색이 쉬워진다.
- **`content` 가 dict/list 면 JSON 문자열로 (285줄)**: Neo4j 속성에는 중첩 객체를 넣을 수 없다.
- **`현행연혁코드 == '연혁'` 건너뛰기 (419줄)**: 지금 시행 중이 아닌 옛 법령은 제외.

### 2단계
- **적재된 법령으로만 검색 (968줄)**: 해석례 전체가 아니라 우리 그래프에 연결될 수 있는 것만 가져온다. 연결 안 되는 노드는 그래프에서 고립된다.
- **`normalize_law_name`**: `ㆍ`/`・`/`·`, 띄어쓰기 차이 때문에 같은 법령을 못 찾는 일을 막는다. 일종의 엔티티 정규화.
- **정규식 `「([^」]+)」`**: 법률 문서는 법령명을 낫표로 감싼다는 **도메인 규칙**을 이용한다. LLM 보다 싸고 정확하다. `동법`, 5자 이하 같은 일반명사는 거른다.
- **LLM 은 조문 인용 추출에만 (66줄)**: "제5조제3항제2호" → `{article: 5, paragraph: 3, item: 2}` 처럼 표현이 다양한 부분만 맡긴다. `gpt-4o-mini` + JSON 강제 + 입력 3000자 제한으로 비용을 줄인다.
- **CITES 는 INTERPRETS 이후 (1076→1095줄)**: 인용 조문을 "주 법령의 조문" 중에서 찾기 때문에, 먼저 어떤 법령을 해석하는지 연결돼 있어야 한다.
- **`FOREACH (x IN CASE WHEN q IS NOT NULL THEN [1] ELSE [] END | MERGE ...)` (537줄)**: Cypher 에는 if 문이 없어서, 조건부로 쓰기를 할 때 쓰는 관용구다. 리스트가 비면 아무것도 안 한다.

## 생각해 볼 점

1. **처리 개수가 하나 적다**: `build_law_graph` 는 `processed_count = 1` 에서 시작하고 `< max_laws` 동안 돈다(388~391줄). `max_laws=10` 이면 몇 개를 처리할까? 마지막 출력 "총 N개"는 맞을까?
2. **`HAS_REASON` 이 만들어질 수 있나** (551~563줄): `WITH i, a, r WHERE a IS NOT NULL` 에서 회답이 없으면 행이 사라진다. 그 뒤의 "회답이 없으면 HAS_REASON" 분기에 도달할 수 있을까? 회답 없는 해석례로 직접 확인해 보자.
3. **조문 번호 타입**: 조문 `number` 는 API 문자열 그대로, 항/호 `number` 는 순서(정수)다. LLM 이 준 `"4"` 와 API 의 조문번호 표기가 다르면 CITES 가 안 생긴다. 어떻게 맞출까?
4. **항 없이 호만 인용할 때 (675줄)**: 그 조문의 **모든 항** 아래에서 호 번호가 같은 것을 찾는다. 여러 항에 같은 번호의 호가 있으면?
5. **`link_to_law` 는 법령명마다 전체 Law 를 다시 조회한다** (808줄). 2단계 시작 때 한 번 만든 `normalized_law_names` 사전을 재사용하면?
6. **날짜를 f-string 으로 쿼리에 넣는다** (487, 496줄). 숫자 검증을 하고 있어 안전하지만, `date($d)` 처럼 파라미터로 넘기면 검증 코드가 필요 없다.

## 실행 전 체크
- `.env`: `LAW_API_KEY`(이메일 ID 앞부분), `OPENAI_API_KEY`, Neo4j 정보
- 먼저 `python law_api.py` 로 API 연결을 확인하면 샘플 JSON 4개가 생긴다. **이 JSON 을 열어 구조를 보는 게 파싱 코드를 이해하는 지름길**이다.
- 순서: `step1_load_laws.py` → `step2_link_interpretations.py`. 1단계는 DB 를 지우지 않는다(MERGE).
