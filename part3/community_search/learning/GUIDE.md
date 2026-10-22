# community_search 읽기 가이드

강의: Part 3 / CH01-08 커뮤니티 검색 구현하기
데이터: Part 2 `retail2kg` 의 H&M 구매 그래프. Neo4j **GDS(Graph Data Science) 플러그인** 필요.

| 파일 | 줄 | 역할 |
|---|---|---|
| [`community_detection_retail.py`](../community_detection_retail.py) | 449 | 같은 날 함께 산 상품을 `CO_PURCHASED` 로 잇고 → GDS 로 메모리에 올려 → **Leiden** 으로 상품 커뮤니티 → `behaviorCommunityId` 저장 |
| [`retail_community_graphrag.py`](../retail_community_graphrag.py) | 639 | 질문 → 키워드 → 상품 → **그 상품의 커뮤니티** → 커뮤니티 상품/특징으로 추천 답변 |

## 한눈에 보기

```
[탐지] (Customer)-[:PURCHASED]->(Article)  ─같은 고객·같은 날─▶  (Article)-[:CO_PURCHASED {weight}]-(Article)
       ─gds.graph.project (무방향, weight)─▶ 메모리 그래프 ─gds.leiden.write─▶ Article.behaviorCommunityId

[검색] 질문 ─LLM─▶ 영문 키워드 ─▶ prod_name CONTAINS ─▶ 상품 + 커뮤니티(크기 필터)
       ─▶ 같은 커뮤니티 상품 20개 + 커뮤니티 특징(스타일, 색) ─▶ 컨텍스트 ─LLM─▶ 추천
```

## 왜 커뮤니티인가

지금까지의 검색은 "질문과 비슷한 것"을 찾았다. 커뮤니티는 **"함께 묶이는 것"** 을 찾는다.
고객들이 실제로 같이 산 상품끼리 그룹이 되므로, 질문에 나오지 않은 상품도 "같이 사면 좋은 상품"으로 추천할 수 있다.
Microsoft GraphRAG 의 "커뮤니티 요약" 방식(전체를 묻는 질문에 커뮤니티 단위로 답하기)과 같은 계열의 아이디어다.

## 읽는 순서

| 순서 | 위치 | 핵심 |
|---|---|---|
| 1 | README "GDS 사용법" | project → stream / mutate / write → drop 의 생명주기 |
| 2 | `check_purchase_data_size` (132) | 데이터가 크면 구매 많은 고객만 쓴다 (메모리 보호) |
| 3 | `project_customer_behavior_graph` (167) | **CO_PURCHASED 만들기**(배치 500명씩) + `gds.graph.project` |
| 4 | `run_leiden_on_customer_behavior` (317) | Leiden 파라미터: `gamma`(해상도), `minCommunitySize`, 가중치 |
| 5 | `analyze_behavior_communities` (363) | 커뮤니티마다 스타일/색 다양성 확인 |
| 6 | `retail_community_graphrag.py` `retail_graphrag_query` (498) | 5단계 파이프라인 전체 |
| 7 | `extract_search_keywords` (60) | 한국어 질문 → 상품명에 실제로 있는 영어 단어 (예시로 실제 상품명을 보여 준다) |
| 8 | `find_similar_products` (112) | 상품명 → 실패하면 설명/외관으로 fallback, **너무 작거나 큰 커뮤니티는 제외** |

## "왜"

- **CO_PURCHASED 를 따로 만드는 이유**: Leiden 은 "상품-상품" 연결이 필요하다. 원래 그래프는 "고객-상품"(이분 그래프)이라 상품끼리 직접 이어지지 않는다. 같은 고객이 같은 날 산 상품을 이어 **투영(projection)** 한다.
- **`elementId(a1) < elementId(a2)`**: 같은 쌍을 (A,B), (B,A) 두 번 만들지 않고, 자기 자신과도 잇지 않는다.
- **weight**: 여러 고객이 함께 산 쌍일수록 연결이 강하다. Leiden 이 가중치를 써서 강한 연결끼리 묶는다.
- **UNDIRECTED**: "함께 샀다"는 방향이 없다. Leiden 은 무방향 그래프를 요구한다.
- **write 모드**: 결과를 노드 속성으로 저장해서 GDS 없이도 일반 Cypher 로 커뮤니티를 쓸 수 있게 한다.
- **커뮤니티 크기 필터 (50~5000 / 파이프라인 기본 5~5000)**: 너무 작으면 추천할 게 없고, 너무 크면 "다 비슷하다"는 의미 없는 그룹이다.
- **키워드 추출 프롬프트에 실제 상품명 예시**: 사용자는 "후드티"라고 하지만 데이터에는 "Theron" 같은 상품명이 있다. LLM 에게 데이터의 실제 어휘를 보여 줘야 검색이 맞는다.

## 생각해 볼 점

1. **"같은 날"이 정말 같은 날인가**: 배치 쿼리는 `p.t_dat` 로 묶는다(252줄). 그런데 `retail2kg.py` 는 PURCHASED 에 날짜를 `date` 라는 이름으로 저장한다. 그러면 `p.t_dat` 는 모두 null → 고객의 **모든 구매**가 한 묶음이 된다. (neo4j-admin import 로 넣었다면 CSV 열 이름 `t_dat` 이 속성이 되어 맞을 수 있다.) 내 DB 에서 `MATCH ()-[p:PURCHASED]->() RETURN keys(p) LIMIT 1` 로 확인해 보자.
2. `project_customer_behavior_graph` 는 `graph_name` 인자를 받지만 project 쿼리에 `'retailBehaviorGraph'` 가 고정돼 있다.
3. `extract_search_keywords` 가 실패하면 `None` 을 돌려주고, 호출한 쪽의 `', '.join(keywords)` 가 터진다.
4. `find_similar_products` 는 상품마다 같은 커뮤니티 전체를 다시 센다(`MATCH (c:Article {behaviorCommunityId: ...})`). `behaviorCommunityId` 인덱스가 없으면 느리다. 커뮤니티 크기를 미리 계산해 두면?
5. `analyze_community` 의 "주요 스타일"은 **빈도순이 아니라** 처음 나온 5개다. 빈도순으로 바꾸려면?
6. `gamma` 를 0.5, 1.0, 2.0 으로 바꾸면 커뮤니티 수와 추천이 어떻게 달라질까?

## 실행 전 체크
- Neo4j Desktop 에 GDS 플러그인 설치(`RETURN gds.version()`), 메모리 설정(README)
- 순서: `retail2kg.py` → `community_detection_retail.py` → `retail_community_graphrag.py`(대화형)
