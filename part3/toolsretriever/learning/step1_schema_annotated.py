"""[1단계: 읽기] schema.py (Neo4j 에서 스키마를 직접 조회해 Text2Cypher 용 글로 바꾸기) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나

이 파일은 직접 실행하지 않는다 (__main__ 없음). text2cypher_retriever.py 가
  schema_text = schema_to_text(fetch_schema_from_neo4j(driver))
로 불러 Text2CypherRetriever(neo4j_schema=schema_text) 에 넘긴다.

part3/text2cypher 와 다른 점: 거기서는 스키마 딕셔너리를 손으로 썼다. 여기서는 DB 에 물어서 만든다.
  [왜] pdf2kg_2 처럼 LLM 이 레이블/속성을 정한 그래프는 실행할 때마다 스키마가 달라질 수 있다. DB 에서 읽으면 항상 현재 상태와 같다.

흐름
  fetch_schema_from_neo4j(driver)
    1) db.schema.nodeTypeProperties()  -> 레이블별 속성 이름/타입
    2) db.schema.relTypeProperties()   -> 관계 타입별 속성
    3) MATCH (a)-[r]->(b)               -> 실제로 존재하는 (출발 레이블, 관계, 도착 레이블) 조합
    -> {"entities": [{"label", "properties"}...], "relations": [{"label", "source", "target", ("properties")}...]}
  schema_to_text(schema)
    -> "Node properties:\n레이블 {속성: 타입, ...}\n...\nRelationship properties:\n...\nThe relationships:\n(:A)-[:R]->(:B)"

읽는 순서 권장: fetch_schema_from_neo4j (쿼리 3개) -> schema_to_text
실행 위치: part3/toolsretriever 에서 PYTHONPATH=. python learning/step1_schema_annotated.py
  (함수 정의만 있어서 실행해도 아무것도 출력되지 않는다. 주석본은 import 용으로 쓰지 않는다)
"""

# [이 파일에서 정의] DB 에서 스키마를 읽어 딕셔너리로 돌려준다
# [입력] driver: neo4j Driver
# [반환] {"entities": [...], "relations": [...]} (part3/text2cypher 의 손으로 쓴 스키마와 같은 모양, description 만 없다)
# 주의: 아래 execute_query 3개 모두 database_= 를 주지 않는다. 다른 파일과 달리 NEO4J_DATABASE 를 쓰지 않으므로
#       기본 DB 가 아닌 곳에 데이터가 있으면 엉뚱한 DB 의 스키마를 읽는다
def fetch_schema_from_neo4j(driver):
    """Neo4j에서 동적으로 스키마 정보를 조회하여 딕셔너리 형태로 반환"""

    # 1. 노드 라벨과 속성 정보 조회
    # """ ... """ 여러 줄 문자열에 Cypher 를 담는다
    # db.schema.nodeTypeProperties(): [출처] Neo4j 내장 프로시저. (레이블 조합, 속성 이름, 속성 타입 목록, 필수 여부) 를 속성 하나당 한 줄로 돌려준다
    # YIELD: 프로시저 결과 중 쓸 열을 고른다 / nodeLabels[0]: 레이블 목록의 첫 번째
    # collect({...}): 같은 label 끼리 묶어 {name, type} 맵의 리스트로 모은다
    # 주의: propertyTypes 는 Neo4j 가 정한 이름("String", "Long" 같은 모양일 수 있다)이라
    #       neo4j-graphrag get_schema() 의 "STRING", "INTEGER" 와 표기가 다를 수 있다. 출력해서 확인해 보자
    # 주의: 레이블이 둘 이상인 노드는 첫 번째 레이블로만 묶인다
    node_query = """
    CALL db.schema.nodeTypeProperties()
    YIELD nodeType, nodeLabels, propertyName, propertyTypes, mandatory
    RETURN nodeLabels[0] as label,
           collect({name: propertyName, type: propertyTypes[0]}) as properties
    ORDER BY label
    """

    # driver.execute_query(쿼리)
    # [출처] 외부 라이브러리 neo4j
    # [입력] Cypher 글 (파라미터, database_=, routing_= 도 줄 수 있다)
    # [반환] EagerResult (records, summary, keys). 여기서는 .records (Record 리스트) 만 쓴다
    node_result = driver.execute_query(node_query)
    # {레이블: [속성 맵, ...]} 를 모을 빈 딕셔너리
    nodes_data = {}
    for record in node_result.records:
        # record["label"]: Record 에서 RETURN 의 별칭(as label)으로 값 꺼내기
        label = record["label"]
        # 처음 보는 레이블이면 빈 리스트를 만들어 둔다
        # 주의: label 이 None 이면(레이블 없는 노드) 리스트를 안 만드는데, 바로 아래 nodes_data[label] 에서 KeyError 가 날 수 있다
        if label and label not in nodes_data:
            nodes_data[label] = []
        if record["properties"]:
            for prop in record["properties"]:
                # prop["name"]: 속성이 없는 노드는 propertyName 이 null 이라 {name: None} 이 섞여 들어온다 -> 건너뛴다
                # prop not in 리스트: 같은 맵이 이미 있으면 중복 추가 안 함
                if prop["name"] and prop not in nodes_data[label]:
                    nodes_data[label].append(prop)

    # 2. 관계 타입과 속성 정보 조회
    # db.schema.relTypeProperties(): 관계 타입별 속성 (이름, 타입). 관계 하나당 속성이 없으면 propertyName 이 null
    rel_props_query = """
    CALL db.schema.relTypeProperties()
    YIELD relType, propertyName, propertyTypes, mandatory
    RETURN relType,
           collect({name: propertyName, type: propertyTypes[0]}) as properties
    """

    # 결과를 {관계타입: [속성 맵...]} 로 모은다
    rel_props_result = driver.execute_query(rel_props_query)
    rel_properties = {}
    for record in rel_props_result.records:
        rel_type = record["relType"]
        # 주의: 이 프로시저의 relType 은 ":`HAS_CHUNK`" 처럼 콜론과 백틱이 붙은 모양일 수 있다 (Neo4j Browser 에서 직접 실행해 확인).
        #       그러면 아래 3번 쿼리의 type(r)("HAS_CHUNK") 와 키가 맞지 않아 관계 속성이 붙지 않는다
        if rel_type and record["properties"]:
            rel_properties[rel_type] = record["properties"]

    # 3. 관계 패턴 조회 (source -> relation -> target)
    # 실제로 존재하는 (출발 레이블)-[관계]->(도착 레이블) 조합을 찾는다
    # labels(a): 노드의 레이블 리스트 / type(r): 관계 타입 이름 / RETURN DISTINCT: 중복 조합 제거
    # [왜] LLM 이 화살표 방향을 틀리지 않게 실제 방향을 알려 준다
    # 주의: 모든 관계를 한 번씩 훑는다. 관계가 수백만 개인 그래프에서는 매우 느릴 수 있다
    rel_pattern_query = """
    MATCH (a)-[r]->(b)
    WITH labels(a) as sourceLabels, type(r) as relType, labels(b) as targetLabels
    WHERE size(sourceLabels) > 0 AND size(targetLabels) > 0
    RETURN DISTINCT sourceLabels[0] as source, relType, targetLabels[0] as target
    ORDER BY relType
    """

    rel_pattern_result = driver.execute_query(rel_pattern_query)
    relations_data = []
    # Record 하나 = 조합 하나. 딕셔너리로 바꿔 리스트에 담는다
    for record in rel_pattern_result.records:
        rel_info = {
            "label": record["relType"],
            "source": record["source"],
            "target": record["target"]
        }
        # 관계 속성 추가
        # 2번에서 찾은 관계 속성이 있으면 "properties" 키를 추가 (없으면 키 자체가 없다)
        if record["relType"] in rel_properties:
            rel_info["properties"] = rel_properties[record["relType"]]

        relations_data.append(rel_info)

    # 4. 딕셔너리 형태로 스키마 구성
    # 최종 딕셔너리. "entities" 는 리스트 컴프리헨션으로 만든다
    schema = {
        "entities": [
            # [식 for 변수 in 반복가능] : 리스트 컴프리헨션. 반복하며 식의 결과를 모은 리스트를 한 줄로 만든다
            # 여기서는 (label, properties) 쌍마다 {"label": ..., "properties": ...} 딕셔너리를 만든다
            {
                "label": label,
                "properties": properties
            }
            # nodes_data.items(): (키, 값) 쌍들 / sorted(...): 레이블 이름순 정렬 (쌍은 첫 값부터 비교)
            # for label, properties in ...: 쌍을 두 변수로 풀어 받는다
            for label, properties in sorted(nodes_data.items())
        ],
        "relations": relations_data
    }

    return schema


# [이 파일에서 정의] 위 딕셔너리 -> LLM 에 넣을 스키마 "글"
# [반환] 예) Node properties:
#           Chunk {chunk_id: String, toc_id: String, content: String}
#           ...
#           Relationship properties:
#           ...
#           The relationships:
#           (:Chunk)-[:HAS_ELEMENT]->(:TextElement)
# [왜] neo4j-graphrag 의 get_schema() 가 만드는 글과 비슷한 형식으로 맞춘 것 (Text2CypherRetriever 프롬프트의 {schema} 자리에 들어간다)
def schema_to_text(schema):
    """딕셔너리 스키마를 Text2CypherRetriever가 이해할 수 있는 문자열 형식으로 변환"""
    # 줄을 리스트에 모았다가 마지막에 "\n".join 으로 한 번에 잇는다
    lines = ["Node properties:"]

    # 엔티티(노드) 정보 추가
    for entity in schema["entities"]:
        if entity["properties"]:
            # [f"..." for p in ... if p.get('name')]: 조건(if)이 붙은 컴프리헨션. 이름이 있는 속성만 "이름: 타입" 글로
            # dict.get('name'): 키가 없으면 에러 대신 None
            # ", ".join(리스트): 쉼표+공백으로 이어 붙인 글 하나
            props = ", ".join([f"{p['name']}: {p['type']}" for p in entity["properties"] if p.get('name')])
            if props:
                # f"{entity['label']} {{{props}}}": {{ 와 }} 는 글자 { }, 가운데 {props} 는 변수
                # -> 결과: TextElement {element_id: String, content: String, ...}
                lines.append(f"{entity['label']} {{{props}}}")
        # 속성이 없는 레이블은 이름만 (예: Document)
        else:
            lines.append(f"{entity['label']}")

    # 관계 속성 추가
    # "\n..." 앞의 \n: 구역 사이에 빈 줄 하나
    lines.append("\nRelationship properties:")
    for relation in schema["relations"]:
        # "properties" in relation: 딕셔너리에 그 키가 있는지. and 뒤는 앞이 참일 때만 본다 (KeyError 방지)
        if "properties" in relation and relation["properties"]:
            props = ", ".join([f"{p['name']}: {p['type']}" for p in relation["properties"] if p.get('name')])
            if props:
                lines.append(f"{relation['label']} {{{props}}}")

    # 관계 정의 추가
    # 관계 정의 줄: 속성이 있으면 이름만 {이름, ...} 으로, 없으면 화살표만
    lines.append("\nThe relationships:")
    for relation in schema["relations"]:
        source = relation["source"]
        target = relation["target"]
        label = relation["label"]
        if "properties" in relation and relation["properties"]:
            prop_names = ", ".join([p['name'] for p in relation["properties"] if p.get('name')])
            if prop_names:
                lines.append(f"(:{source})-[:{label} {{{prop_names}}}]->(:{target})")
            else:
                lines.append(f"(:{source})-[:{label}]->(:{target})")
        else:
            lines.append(f"(:{source})-[:{label}]->(:{target})")

    # 리스트의 줄들을 줄바꿈으로 이어 하나의 글로 반환
    return "\n".join(lines)
