# medical2kg 읽기 가이드

강의: Part 2 / CH02-08 의료 지식 데이터를 지식그래프로 변환하기

| 파일 | 역할 |
|---|---|
| [`medical_dataset.ipynb`](../medical_dataset.ipynb) | AI Hub 필수의료 QA 데이터 구조 탐색 |
| [`medical2kg.py`](../medical2kg.py) (682줄) | 스키마 추출 → QA 그래프 → 엔티티/관계 추출 → 저장 |
| [`output/domain_schemas.json`](../output/domain_schemas.json) | LLM 이 만든 스키마 (커밋되어 있음) |
| [`output/extracted_graph.json`](../output/extracted_graph.json) | QA 200개의 추출 결과 (커밋되어 있음) |

`output/` 의 두 JSON 이 저장소에 있으므로 **원본 데이터나 LLM 없이도 저장 단계(`save_graph_to_neo4j`)를 실습할 수 있다.**

## 한눈에 보기

```
[Step 0] 진료과별 QA 3개씩 샘플 ─LLM─▶ 스키마 JSON (엔티티 타입 + 허용 관계 조합)  ─▶ domain_schemas.json (캐시)
[Step 1] QA 전체 ─▶ (Question)-[:HAS_ANSWER]->(Answer), (Question)-[:BELONGS_TO]->(Department)
[Step 2] QA 마다 ─LLM─▶ 엔티티/관계 ─코드로 검증─▶ 허용 조합만 남김 ─▶ extracted_graph.json (캐시)
[Step 3] (Question)-[:MENTIONS]->(Symptom|Disease|...)  +  (Symptom)-[:INDICATES {count, qa_ids, evidence}]->(Disease)
```

## pdf2kg_2 와 비교하면

| | pdf2kg_2 | medical2kg |
|---|---|---|
| 스키마 형식 | 마크다운 글 | **JSON** (코드가 읽을 수 있다) |
| 스키마 지키기 | 프롬프트로 부탁만 | 프롬프트 + **코드로 관계 필터링** (355~376줄) |
| 같은 관계가 여러 번 | MERGE 로 하나 | MERGE + `count` 증가 + 근거 QA 목록 누적 |
| 재실행 비용 | 매번 LLM 호출 | 스키마와 추출 결과를 JSON 으로 **캐시** |

스키마를 기계가 읽을 수 있는 형태로 만들면 "LLM 이 규칙을 지켰는지"를 코드로 검사할 수 있다. 이게 이 실습의 핵심 진전이다.

## 읽는 순서

| 순서 | 함수 | 줄 | 핵심 |
|---|---|---|---|
| 1 | `__main__` | 611 | 캐시 파일이 있으면 LLM 단계를 건너뛴다 (646, 665줄) |
| 2 | `load_all_qa_data` | 30 | 진료과 폴더의 JSON 을 읽고 `department` 를 붙인다 |
| 3 | `extract_domain_schema`, `extract_unified_schema` | 73, 149 | 진료과를 섞은 샘플로 **통합 스키마** 하나 |
| 4 | `save_qa_graph_to_neo4j` | 188 | 원문 QA 를 먼저 그래프로 (근거 보관용) |
| 5 | `extract_entities_and_relationships_from_qa` | 246 | 스키마로 프롬프트 생성 → 추출 → **허용 조합 필터** |
| 6 | `save_graph_to_neo4j` | 428 | 타입별 레이블로 MERGE, 인덱스, MENTIONS, 관계 누적 |

## 함수별 "왜"

- **진료과별 스키마가 아니라 통합 스키마**: 내과의 "기침"과 소아과의 "기침"이 같은 노드여야 진료과를 넘는 질문("기침이 나타나는 질환을 진료과별로")이 가능하다.
- **`utf-8-sig` (50줄)**: AI Hub JSON 에 BOM 이 붙어 있으면 `utf-8` 로는 `json.load` 가 실패한다.
- **허용 관계를 문자열로 프롬프트에 (260~316줄)**: `symptom -[INDICATES]-> disease` 처럼 방향까지 보여 준다.
- **코드 필터 (355~376줄)**: `(from_type, to_type, type)` 이 스키마에 없으면 버린다. 프롬프트만으로는 100% 지켜지지 않기 때문이다.
- **QA 를 먼저 저장 (Step 1)**: 엔티티가 "어느 질문에서 나왔는지" `MENTIONS` 로 연결해 근거를 추적한다(pdf2kg 의 HAS_ENTITY 와 같은 역할).
- **엔티티는 (이름, 타입)으로 유일 (446줄)**: 같은 이름이라도 타입이 다르면 다른 노드.
- **타입별로 묶어서 배치 (453~473줄)**: 레이블은 파라미터로 못 넘기므로, 같은 레이블끼리 모아 `UNWIND` 한 번에 넣는다.
- **관계 누적 (588~598줄)**: `ON CREATE SET r.count = 1 ... ON MATCH SET r.count = r.count + 1`. 여러 QA 가 같은 관계를 말하면 count 가 올라간다 → **신뢰도/중요도 신호**가 된다. `qa_ids` 로 근거 QA 를 모두 남긴다.
- **인덱스 (477~493줄)**: MENTIONS 와 관계 생성의 MATCH 가 이름/qa_id 로 노드를 찾으므로 먼저 인덱스를 만든다.

## 생각해 볼 점

1. **엔티티 타입은 필터링하지 않는다**: 관계만 스키마로 검사한다. 저장소의 `extracted_graph.json` 에는 스키마에 없는 `allergen` 타입이 1개 있다. 그대로 `Allergen` 레이블이 생긴다.
2. **스키마의 `Anatomy` 는 어떤 관계에도 없다**: 그러면 Anatomy 엔티티는 MENTIONS 외에는 고립된다. 스키마 생성 프롬프트를 어떻게 고치면 될까?
3. **`capitalize()` 레이블**: `symptom` → `Symptom` 은 맞지만, 스키마 키가 `BodyPart` 였다면 `bodypart` → `Bodypart` 가 되어 이름이 달라진다.
4. **예시 문장 복사**: 추출 프롬프트 예시의 evidence "환자가 기침으로 내원"이 실제 결과에도 3번 나온다. 원문에 그 문장이 정말 있었을까? few-shot 예시가 출력에 새어 들어오는 현상을 어떻게 확인하고 막을까?
5. **캐시의 함정**: `domain_schemas.json` 이 있으면 스키마를 다시 만들지 않는다. 프롬프트를 고친 뒤 결과가 안 바뀌면 캐시 파일을 지웠는지부터 확인.
6. `MERGE ... ON MATCH SET r.count = r.count + 1` 은 같은 QA 를 두 번 저장하면 count 가 두 번 오른다. `qa_ids` 를 이용해 막으려면?

## 실행 전 체크
- AI Hub 데이터를 `data/<진료과>/` 에 풀어 둔다(README 참고). 저장 단계만 해 보려면 데이터 없이 `learning/step2_fill_in.py` 를 쓰면 된다.
- Step 1 에서 **DB 전체를 지운다**.
