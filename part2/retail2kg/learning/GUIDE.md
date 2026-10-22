# retail2kg 읽기 가이드

강의: Part 2 / CH02-07 캐글 상품 구매이력 데이터를 지식그래프로 변환하기

| 파일 | 역할 |
|---|---|
| [`hnm_recommendations.ipynb`](../hnm_recommendations.ipynb) | H&M 원본 CSV → 샘플링 → 노드/관계 CSV (`output/`, `output_admin/`) |
| [`retail2kg.py`](../retail2kg.py) (661줄) | `output/` CSV 를 Python 드라이버로 Neo4j 에 적재 |
| [`README.md`](../README.md) | 적재 방법 4가지: neo4j-admin import / Import 도구 / Python 드라이버 / LOAD CSV |

## 한눈에 보기

```
articles.csv (10만) ┐
customers.csv (137만)├─ 노트북: 최근 거래 50만 건만 샘플 ─▶ 노드 CSV 8종 + 관계 CSV 7종 ─▶ Neo4j
transactions (3천만)┘

(Customer)-[:PURCHASED {date, price, sales_channel_id}]->(Article)
(Article)-[:OF_TYPE]->(ProductType)      (Article)-[:IN_GROUP]->(ProductGroup)
(Article)-[:HAS_COLOUR]->(ColourGroup)   (Article)-[:IN_DEPARTMENT]->(Department)
(Article)-[:IN_SECTION]->(Section)       (Article)-[:IN_GARMENT_GROUP]->(GarmentGroup)
```

csv2kg(타이타닉 891행)와 구조는 같다. 이 실습의 진짜 주제는 **규모**다: 거래가 수천만 건이면 어떻게 넣을까?

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | 노트북 셀 2~4 | **샘플링**: 최근 거래 50만 건 → 그 거래에 등장한 고객/상품만 남긴다 |
| 2 | 노트북 셀 11 | 상품별 구매자 수 분포. 추천에 쓸 만한 데이터인지 먼저 본다 |
| 3 | 노트북 셀 14~19 | 노드 CSV(분류 노드는 `drop_duplicates`), 관계 CSV |
| 4 | 노트북 셀 22~23 | `neo4j-admin import` 용 헤더(`:ID(Article)`, `:START_ID`, `:END_ID`) |
| 5 | `retail2kg.py` `main` (589) | csv2kg 와 같은 흐름: 초기화 → 제약조건 → 노드 → 관계 → 통계 |
| 6 | `create_purchased_relationships` (304) | **청크 단위 적재** (5만 행씩) |
| 7 | README "적재하는 방식" | 4가지 방법의 차이 |

## 함수별 "왜"

- **샘플링을 "최근 거래" 기준으로**: 무작위로 거래를 뽑으면 고객당 거래가 1건뿐인 경우가 많아져 "이 고객이 산 다른 상품"을 찾기 어렵다. 최근 기간을 통째로 가져오면 고객 행동이 유지된다.
- **분류는 노드로, 동시에 Article 속성에도**: `product_type_name` 등이 Article 속성에도 있고 ProductType 노드로도 있다. 속성은 필터/표시용, 노드는 "같은 분류 상품 찾기" 같은 탐색용이다. 중복이지만 의도된 비정규화다.
- **`toInteger()`, `toFloat()`**: CSV 는 전부 문자열이라 숫자로 바꿔 넣는다. 안 바꾸면 `article_id: "108775015"` 와 `108775015` 가 달라 MATCH 가 실패한다.
- **`date(row.t_dat)`**: 날짜를 문자열이 아닌 날짜 타입으로 넣어야 "최근 30일 구매" 같은 비교가 된다.
- **`pd.read_csv(chunksize=50000)` (326줄)**: 한 번에 수백만 행을 파라미터로 보내면 메모리와 트랜잭션이 터진다. 5만 행씩 나눠 보내고 진행 상황을 찍는다.
- **관계 MATCH 가 빠른 이유**: `create_constraints` 의 UNIQUE 제약조건이 인덱스를 만들어 준다. 제약조건 없이 50만 건 관계를 만들면 매우 느리다.

## 4가지 적재 방법 비교 (README)

| 방법 | 속도 | 언제 |
|---|---|---|
| `neo4j-admin import` | 가장 빠름 | 처음 한 번 대량 적재. **DB 를 멈추고**, 빈 DB 에만 |
| Neo4j Import 도구(GUI) | 빠름 | 소/중규모, 코드 없이 |
| Python 드라이버 (`retail2kg.py`) | 보통 | 변환 로직이 필요할 때, 증분 적재 |
| `LOAD CSV` | 보통 | Browser 에서 바로. 대량 관계는 `CALL {} IN TRANSACTIONS` 로 나눠야 함 |

## 생각해 볼 점

1. **`retail2kg.py` 를 그대로 실행하면 PURCHASED 에서 멈춘다**: `create_purchased_relationships` 는 `time.time()` 을 쓰는데 파일 맨 위에 `import time` 이 없다(312줄). 실행 전에 직접 고쳐 보자.
2. 노드 로더 8개가 거의 같은 코드다. csv2kg step3 의 일반화 과제와 같은 방식으로 하나로 줄일 수 있다.
3. 같은 고객이 같은 상품을 같은 날 두 번 사면 PURCHASED 가 2개 생긴다(CREATE). 추천에서는 좋은 신호일까, 중복일까?
4. 고객 노드가 수십만 개다. "이 상품을 산 사람들이 산 다른 상품" 쿼리가 느려지는 지점은 어디일까? (인기 상품은 구매자가 매우 많다 → 슈퍼노드)

## 실행 전 체크
- Kaggle 데이터를 `datasets/` 에 넣고 노트북을 먼저 실행해 `output/` 을 만든다.
- `retail2kg.py` 는 **DB 전체를 지운다**.
- `import time` 을 먼저 추가할 것.
