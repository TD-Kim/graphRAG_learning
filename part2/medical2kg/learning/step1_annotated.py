"""[1단계: 읽기] medical2kg.py (의료 QA -> 스키마 -> 엔티티/관계 그래프) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
pdf2kg_2 주석본(스키마 먼저 -> 스키마대로 추출)과 같은 생각이다. 다른 점은
  1) 스키마를 JSON 으로 받아서 "허용된 (from, to, type) 조합" 으로 LLM 결과를 코드에서 한 번 더 거른다
  2) 중간 결과(스키마, 추출 결과)를 output/ 에 JSON 으로 저장하고, 있으면 LLM 을 다시 부르지 않는다(캐시)
  3) 같은 관계가 여러 QA 에서 나오면 관계 하나에 count 와 qa_ids 를 누적한다

흐름
  data/<진료과>/**/*.json (QA 하나당 파일 하나)
  Step 0  샘플 12개 -LLM-> 스키마(엔티티 타입 + 허용 관계)        -> output/domain_schemas.json
  Step 1  QA -> (Question)-[:HAS_ANSWER]->(Answer), (Question)-[:BELONGS_TO]->(Department)
  Step 2  QA 마다 -LLM-> 엔티티/관계 -> 스키마로 검증           -> output/extracted_graph.json
          -> 엔티티 MERGE -> (Question)-[:MENTIONS]->(엔티티) -> (엔티티)-[:INDICATES|TREATS|...]->(엔티티)

읽는 순서 권장: __main__ -> load_all_qa_data -> extract_unified_schema -> extract_entities_and_relationships_from_qa -> save_graph_to_neo4j
실행 위치: part2/medical2kg (DB 를 전부 지우고 시작한다. output/ 의 JSON 을 지우면 LLM 을 다시 부른다)
"""

# [출처] 표준 라이브러리. os.getenv
import os
# [출처] 표준 라이브러리. sys.exit
import sys
# [출처] 표준 라이브러리. json.load(파일) / json.loads(글) / json.dump(객체, 파일)
import json
# [출처] 표준 라이브러리. textwrap.dedent: 공통 들여쓰기 제거
import textwrap
# [출처] 표준 라이브러리. 경로 객체
from pathlib import Path
# 타입 힌트. Optional[int] = int 또는 None
from typing import List, Dict, Optional
# [출처] 표준 라이브러리 time. time.sleep(초): 그 시간만큼 멈춤
import time

# [출처] 외부 라이브러리 neo4j / python-dotenv / openai
from neo4j import GraphDatabase
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ============================================
# 환경 변수 설정
# ============================================

# 이 강의 환경은 DB 이름 = 사용자 이름
NEO4J_DATABASE = os.getenv("NEO4J_USERNAME")

# 처리할 진료과. data/ 아래 폴더 이름과 같아야 한다
DEPARTMENTS = ["내과", "산부인과", "소아청소년과", "응급의학과"]
# Path("data"): 실행 위치 기준 상대 경로
DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")
# 모듈이 import(실행)되자마자 output 폴더를 만든다. exist_ok=True: 이미 있어도 에러 없음
OUTPUT_DIR.mkdir(exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# OpenAI 클라이언트를 파일 맨 위(전역)에서 한 번 만들어 모든 함수가 같이 쓴다
# (키가 없으면 여기서 바로 에러가 나서, 아래 __main__ 의 "키 없음" 안내까지 가지 못한다)
client = OpenAI(api_key=OPENAI_API_KEY)


# [이 파일에서 정의] 진료과별 QA JSON 파일들을 읽는다
# [입력] max_qa_per_dept: 진료과마다 최대 몇 개 (None 이면 전부)
# [반환] {"내과": [qa딕셔너리, ...], "산부인과": [...], ...}
def load_all_qa_data(max_qa_per_dept: Optional[int] = None) -> Dict[str, List[Dict]]:
    """모든 진료과의 QA 데이터 로드

    Args:
        max_qa_per_dept: 각 진료과별 최대 QA 개수 (None이면 전체 로드)
    """
    print(f"\n[Step 1/3] QA 데이터 로딩 중...")
    if max_qa_per_dept:
        print(f"   (각 진료과별 최대 {max_qa_per_dept}개 샘플링)")

    all_qa_data = {}
    total_count = 0

    for dept in DEPARTMENTS:
        # Path / 문자열: 경로 잇기 -> data/내과
        dept_path = DATA_DIR / dept
        # 경로.rglob("*.json"): [출처] pathlib. 하위 폴더까지 모두 뒤져서 .json 파일 경로를 찾는다 (r = recursive)
        # 반환은 반복자라서 list(...) 로 리스트로 만든다
        json_files = list(dept_path.rglob("*.json"))

        qa_list = []
        for json_file in json_files:
            try:
                # encoding='utf-8-sig': 파일 맨 앞의 BOM(윈도우 메모장 등이 붙이는 보이지 않는 표시)을 자동으로 떼고 읽는다
                # json.load(파일): [출처] 표준 라이브러리 json. 파일 내용(JSON) -> 딕셔너리
                with open(json_file, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    # 읽은 딕셔너리에 키를 추가. 나중에 Question 노드의 department 로 쓴다
                    data['department'] = dept  # 진료과 정보 추가
                    qa_list.append(data)
            # 읽기 실패한 파일은 조용히 건너뛴다 (continue)
            except Exception as e:
                continue

            # max_qa_per_dept 가 None 이면 이 조건은 항상 거짓 -> 전부 읽는다
            # 샘플링: 최대 개수 도달시 중단
            if max_qa_per_dept and len(qa_list) >= max_qa_per_dept:
                break

        all_qa_data[dept] = qa_list
        total_count += len(qa_list)
        print(f"   {dept}: {len(qa_list)}개 QA")

    print(f"\n   총 {total_count}개 QA 로드 완료")

    return all_qa_data

# ============================================
# Step 0: 스키마 추출 (Schema Extraction)
# ============================================

# [이 파일에서 정의] QA 샘플 -> LLM -> 스키마 딕셔너리
# [반환] {"entity_types": {"Symptom": [예시...], ...}, "relationships": [{"from", "to", "type"}, ...]}
def extract_domain_schema(samples: List[Dict]) -> Dict:
    """LLM으로 도메인 통합 스키마 추출"""

    # "\n\n".join([...]): 리스트 컴프리헨션으로 만든 QA 글들을 빈 줄로 이어 붙인다
    # enumerate(samples[:5]): 앞 5개만, (순번, qa) 로. i+1 로 1번부터 번호를 붙인다
    # 주의: 아래에서 샘플 12개를 모아 넘기지만 실제로는 앞 5개(내과 3, 산부인과 2)만 쓴다
    # 샘플 데이터를 텍스트로 변환
    samples_text = "\n\n".join([
        f"[QA {i+1}]\nQ: {s.get('question', '')}...\nA: {s.get('answer', '')}..."
        for i, s in enumerate(samples[:5])  # 처음 5개만 사용
    ])

    # system 프롬프트. f-string 이라 JSON 예시의 중괄호는 {{ }}
    prompt = textwrap.dedent(f"""
        당신은 의료 지식 그래프 전문가입니다.

        <requirements>
        1. 엔티티 타입 추출 (예: Symptom, Disease, Test, Treatment, Anatomy, Medication)
        2. 각 타입별 주요 엔티티 (3-5개 예시)
        3. 엔티티 타입 간 관계 정의
        </requirements>

        <output_format>
        JSON만 반환 (설명 없이):
        {{
          "entity_types": {{
            "Symptom": ["예시1", "예시2", "예시3"],
            "Disease": ["예시1", "예시2", "예시3"],
            "Test": ["예시1", "예시2"],
            "Treatment": ["예시1", "예시2"],
            "Medication": ["예시1", "예시2"],
            "Anatomy": ["예시1", "예시2"]
          }},
          "relationships": [
            {{"from": "Symptom", "to": "Disease", "type": "INDICATES"}},
            {{"from": "Test", "to": "Disease", "type": "DIAGNOSES_FOR"}},
            {{"from": "Treatment", "to": "Disease", "type": "TREATS"}},
            {{"from": "Medication", "to": "Disease", "type": "TREATS"}}
          ]
        }}
        </output_format>
    """).strip()

    try:
        # chat.completions.create (txt2kg 주석본 참고). json_object 로 JSON 만 받는다
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": textwrap.dedent(f"""
                    다음은 내과, 산부인과, 소아청소년과, 응급의학과의 QA 샘플 텍스트입니다.
                    이를 분석하여 그래프 스키마를 추출하세요.

                    <qa_samples>
                    {samples_text}
                    </qa_samples>
                """).strip()}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1500
        )

        # 아래 ``` 제거 코드는 json_object 모드에서는 거의 필요 없다 (안전장치)
        # "```json" in 글: 포함 여부 / 글.split("```json")[1]: 그 표시 뒤쪽 / .split("```")[0]: 닫는 표시 앞쪽
        result_text = response.choices[0].message.content.strip()

        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        # json.loads(글): JSON 글 -> 딕셔너리
        schema = json.loads(result_text)
        return schema

    # 실패하면 빈 스키마. 그러면 Step 2 에서 허용 관계가 없어 관계가 전부 걸러진다
    except Exception as e:
        print(f"   오류: 스키마 추출 실패 - {e}")
        return {
            "entity_types": {},
            "relationships": [],
        }


# [이 파일에서 정의] 진료과마다 3개씩 샘플을 모아 스키마를 만들고 output/domain_schemas.json 에 저장
def extract_unified_schema() -> Dict:
    """모든 진료과의 샘플을 통합하여 통일된 스키마 추출"""
    print(f"\n[Step 0/3] 통일된 도메인 스키마 추출 중...")

    # 모든 진료과의 샘플 수집 (각 3개씩)
    qa_data = load_all_qa_data(max_qa_per_dept=3)

    all_samples = []
    # 딕셔너리.items(): (키, 값) 쌍 / 리스트.extend(다른리스트): 원소들을 이어 붙인다 (append 는 리스트 통째로 하나 추가)
    for dept, qa_list in qa_data.items():
        all_samples.extend(qa_list)
        print(f"   {dept}: {len(qa_list)}개 샘플 수집")

    if not all_samples:
        return {
            "entity_types": {},
            "relationships": [],
        }

    print(f"   총 {len(all_samples)}개 샘플로 통일된 스키마 추출 중...")

    unified_schema = extract_domain_schema(all_samples)

    # 괄호 안에서 f-string 두 개를 나란히 쓰면 이어 붙는다
    print(f"   스키마: {len(unified_schema['entity_types'])}개 엔티티 타입, "
          f"{len(unified_schema['relationships'])}개 관계 타입")

    # 스키마 저장
    schema_path = OUTPUT_DIR / "domain_schemas.json"
    # json.dump(객체, 파일, ensure_ascii=False 한글 그대로, indent=2)
    with open(schema_path, 'w', encoding='utf-8') as f:
        json.dump(unified_schema, f, ensure_ascii=False, indent=2)

    print(f"   스키마 저장: {schema_path}")

    return unified_schema


# ============================================
# Step 1: QA 그래프 구축 (QA Graph Construction)
# ============================================

# [이 파일에서 정의] QA 를 그래프로: Department, Question, Answer 노드와 관계
def save_qa_graph_to_neo4j(all_qa_data: Dict[str, List[Dict]], driver):
    """QA 그래프를 Neo4j에 저장"""
    print(f"\n   Neo4j에 QA 그래프 저장 중...")

    # DB 전체 삭제
    # 1. 기존 데이터 삭제
    driver.execute_query(
        "MATCH (n) DETACH DELETE n",
        database_=NEO4J_DATABASE
    )
    print(f"      step 1 - 기존 데이터 삭제")

    # 2. Department 노드 생성
    # execute_query(쿼리, name=dept, ...): 키워드 인자 name 이 쿼리의 $name 으로
    for dept in DEPARTMENTS:
        driver.execute_query(
            "CREATE (d:Department {name: $name})",
            name=dept,
            database_=NEO4J_DATABASE
        )
    print(f"      step 2 - Department 노드 {len(DEPARTMENTS)}개 생성")

    # 3. Question-Answer 노드 및 관계 생성
    created = 0

    for dept, qa_list in all_qa_data.items():
        # 배치 처리 (50개씩)
        # range(0, 개수, 50): 0, 50, 100 ... / qa_list[i:i+50]: 50개씩 잘라 배치
        for i in range(0, len(qa_list), 50):
            batch = qa_list[i:i+50]

            # UNWIND $batch AS qa: 배치를 한 행씩
            # CREATE 두 번 + 관계 CREATE: 질문과 답 노드를 만들고 잇는다
            # WITH q, qa: 다음 단계로 넘길 변수만 고른다 (a 는 더 필요 없음)
            # MATCH (d:Department {name: qa.department}) -> 진료과 노드를 찾아 BELONGS_TO
            # qa.qa_id, qa.question ... : JSON 파일의 키 이름 그대로
            driver.execute_query("""
                UNWIND $batch AS qa
                CREATE (q:Question {
                    qa_id: qa.qa_id,
                    content: qa.question,
                    q_type: qa.q_type,
                    domain: qa.domain,
                    department: qa.department
                })
                CREATE (a:Answer {
                    qa_id: qa.qa_id,
                    content: qa.answer
                })
                CREATE (q)-[:HAS_ANSWER]->(a)
                WITH q, qa
                MATCH (d:Department {name: qa.department})
                CREATE (q)-[:BELONGS_TO]->(d)
            """, batch=batch, database_=NEO4J_DATABASE)

            created += len(batch)

    print(f"      step 3 - Question/Answer 노드 {created}개 생성 및 관계 연결")

    print(f"\n   QA 그래프 저장 완료!")


# ============================================
# Step 2: 엔티티 및 관계 추출 (Entity & Relationship Extraction)
# ============================================

# [이 파일에서 정의] QA 하나 -> LLM -> {"entities": [...], "relationships": [...]}
# 스키마를 프롬프트에 넣어 제한하고, 돌아온 관계를 코드에서 한 번 더 검사한다 (프롬프트만으로는 100% 지켜지지 않으므로)
def extract_entities_and_relationships_from_qa(qa: Dict, schema: Dict) -> Dict:
    """LLM으로 QA에서 의료 엔티티와 관계를 한번에 추출"""

    question = qa.get('question', '')
    answer = qa.get('answer', '')

    # 딕셔너리.keys(): 키들만 -> list(...) 로 리스트. 예) ["Symptom", "Disease", ...]
    # [t.lower() for t in ...]: 모두 소문자로. 프롬프트 예시와 검사에서 소문자를 쓴다
    # "|".join(...): 이어 붙이기 (entity_types_enum 은 만들기만 하고 이 파일에서 쓰지 않는다)
    # 스키마 정보 요약
    entity_types_list = list(schema.get('entity_types', {}).keys())
    entity_types_lower = [t.lower() for t in entity_types_list]
    entity_types_str = ", ".join(entity_types_list)
    entity_types_enum = "|".join(entity_types_lower)

    relationship_types = schema.get('relationships', [])

    # 허용 관계를 "symptom -[INDICATES]-> disease" 같은 줄로 만들어 프롬프트에 넣는다
    allowed_rels = []
    for r in relationship_types:
        from_type = r['from'].lower()
        to_type = r['to'].lower()
        rel_type = r['type']
        allowed_rels.append(f"{from_type} -[{rel_type}]-> {to_type}")
    allowed_rels_str = "\n".join(allowed_rels)

    # {entity_types_str}, {allowed_rels_str} 자리에 스키마가 들어간다
    # 주의: 규칙 2의 "허용된_관계_조합" 이라는 이름은 프롬프트의 태그 이름(allowed_relationships)과 다르다
    prompt = textwrap.dedent(f"""
        당신은 의료 지식 그래프 전문가입니다.
        아래 스키마에 정의된 관계만 추출해야 합니다.

        <entity_types>
        {entity_types_str}
        </entity_types>

        <allowed_relationships>
        아래에 명시된 조합만 추출 가능합니다 (방향 준수 필수):
        {allowed_rels_str}
        </allowed_relationships>

        <rules>
        1. 엔티티는 원문에 명시된 것만 추출
        2. 관계는 위 "허용된_관계_조합"에 있는 것만 추출
        3. from_type과 to_type의 방향을 정확히 지킬 것
        4. 엔티티 이름은 2-6 단어로 간결하게
        </rules>

        <output_format>
        다음은 출력 예시입니다.
        JSON만 반환 (설명 없이):
        {{
          "entities": [
            {{"name": "기침", "type": "symptom"}},
            {{"name": "폐렴", "type": "disease"}},
            {{"name": "아목시실린", "type": "medication"}}
          ],
          "relationships": [
            {{
              "from": "기침",
              "from_type": "symptom",
              "to": "폐렴",
              "to_type": "disease",
              "type": "INDICATES",
              "evidence": "환자가 기침으로 내원"
            }},
            {{
              "from": "아목시실린",
              "from_type": "medication",
              "to": "폐렴",
              "to_type": "disease",
              "type": "TREATS",
              "evidence": "아목시실린으로 치료"
            }}
          ]
        }}
        </output_format>
    """).strip()

    try:
        # temperature=0.2: 추출은 일관성 우선
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": textwrap.dedent(f"""
                    <qa_pair>
                    질문: {question}
                    답변: {answer}
                    </qa_pair>

                    위 QA에서 엔티티와 관계를 추출하세요.
                """).strip()}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1500
        )

        result_text = response.choices[0].message.content.strip()

        # JSON 추출
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        result = json.loads(result_text)

        # LLM 이 키를 빠뜨려도 아래 코드가 에러 나지 않게 빈 리스트를 넣어 둔다
        # 기본 구조 보장
        if "entities" not in result:
            result["entities"] = []
        if "relationships" not in result:
            result["relationships"] = []

        # 스키마 기반 관계 검증
        # (from, to, type) 튜플을 키로 하는 딕셔너리 -> "in" 검사가 빠르다 (set 을 써도 같다)
        # ===== 스키마 기반 관계 검증 =====
        allowed_rel_map = {}
        for r in relationship_types:
            key = (r['from'].lower(), r['to'].lower(), r['type'])
            allowed_rel_map[key] = True

        # 관계 필터링
        valid_relationships = []
        filtered_count = 0

        for rel in result.get("relationships", []):
            # rel.get('from_type', '').lower(): 없으면 '' -> 소문자로 맞춰 비교
            from_type = rel.get('from_type', '').lower()
            to_type = rel.get('to_type', '').lower()
            rel_type = rel.get('type', '')

            # 스키마에서 허용된 조합인지 확인
            # 튜플을 만들어 딕셔너리 키에 있는지 검사. 없으면 버린다 (filtered_count 는 세기만 하고 출력하지 않는다)
            if (from_type, to_type, rel_type) in allowed_rel_map:
                valid_relationships.append(rel)
            else:
                filtered_count += 1

        # 필터링 결과 적용
        result["relationships"] = valid_relationships

        return result

    # 실패하면 빈 결과. qa.get('qa_id'): 어느 QA 가 실패했는지
    except Exception as e:
        print(f"      오류: QA {qa.get('qa_id')} 추출 실패 - {e}")
        return {
            "entities": [],
            "relationships": []
        }


# [이 파일에서 정의] 모든 QA 를 돌며 추출하고 output/extracted_graph.json 에 저장
# [반환] {qa_id: 추출결과, ...}
def extract_all_entities_and_relationships(all_qa_data: Dict[str, List[Dict]],
                                           unified_schema: Dict) -> Dict[int, Dict]:
    """모든 QA에서 엔티티와 관계를 한번에 추출"""
    print(f"\n[Step 2/3] 엔티티 및 관계 추출 중...")

    all_results = {}
    # sum(len(qas) for qas in ...): 진료과별 개수의 합 (total_count 는 만들기만 하고 쓰지 않는다)
    total_count = sum(len(qas) for qas in all_qa_data.values())
    processed = 0

    for dept, qa_list in all_qa_data.items():
        print(f"\n   {dept} 처리 중... ({len(qa_list)}개)")

        for i, qa in enumerate(qa_list):
            # 10개마다 진행률 출력. {(i+1)/len(qa_list)*100:.1f}: 계산 결과를 소수 1자리로
            if (i + 1) % 10 == 0:
                print(f"      진행: {i+1}/{len(qa_list)} ({(i+1)/len(qa_list)*100:.1f}%)")

            result = extract_entities_and_relationships_from_qa(qa, unified_schema)
            all_results[qa['qa_id']] = result

            processed += 1

            # 10번 부를 때마다 0.5초 쉰다 -> API 분당 요청 제한(rate limit)에 덜 걸리게
            # API 요청 제한 (필요시)
            if processed % 10 == 0:
                time.sleep(0.5)

    # 결과 저장
    results_path = OUTPUT_DIR / "extracted_graph.json"
    # 주의: JSON 은 키가 항상 문자열이다. qa_id(정수) 키가 "123" 같은 글로 저장된다 -> __main__ 에서 다시 int 로 바꾼다
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # 통계 출력
    total_entities = sum(len(r.get('entities', [])) for r in all_results.values())
    total_relationships = sum(len(r.get('relationships', [])) for r in all_results.values())

    print(f"\n   결과 저장: {results_path}")
    print(f"   처리 완료: {processed}개 QA | {total_entities}개 엔티티 | {total_relationships}개 관계")

    return all_results


# [이 파일에서 정의] 추출 결과 -> 엔티티 노드, MENTIONS, 엔티티 간 관계
def save_graph_to_neo4j(all_results: Dict[int, Dict], driver):
    """추출된 엔티티와 관계를 Neo4j에 저장"""
    print(f"\n   Neo4j에 그래프 저장 중...")

    # 1. 엔티티 노드 생성 (type을 레이블로 사용)
    entity_data = []

    for qa_id, result in all_results.items():
        for entity in result.get('entities', []):
            entity_name = entity.get('name', '')
            entity_type = entity.get('type', '')
            if entity_name and entity_type:
                entity_data.append({
                    'name': entity_name,
                    'type': entity_type
                })

    # (이름, 타입) 이 같으면 같은 엔티티. 딕셔너리 키로 중복 제거
    # 유니크한 엔티티만 추출
    unique_entities = {}
    for e in entity_data:
        key = (e['name'], e['type'])
        if key not in unique_entities:
            unique_entities[key] = e

    # 타입별로 그룹화
    # from collections import defaultdict: [출처] 표준 라이브러리 collections
    # defaultdict(list): 없는 키를 꺼내면 자동으로 빈 리스트를 만들어 주는 딕셔너리
    # [왜] "if 키 not in d: d[키] = []" 를 매번 쓰지 않고 바로 d[키].append(...) 할 수 있다
    from collections import defaultdict
    entities_by_type = defaultdict(list)
    for e in unique_entities.values():
        entities_by_type[e['type']].append(e)

    # 타입별로 배치 생성 (동적 레이블 사용)
    total_entities = 0
    # 레이블은 파라미터로 못 넘기므로 타입별로 묶어서, 타입마다 쿼리 글을 따로 만든다
    for entity_type, entities in entities_by_type.items():
        # type을 레이블로 변환 (첫 글자 대문자)
        # 문자열.capitalize(): 첫 글자 대문자, 나머지는 소문자 ("symptom" -> "Symptom")
        # 주의: LLM 이 "lab test" 처럼 공백 있는 타입을 주면 레이블이 깨져 쿼리 에러가 난다 (검증 없음)
        label = entity_type.capitalize()

        for i in range(0, len(entities), 100):
            batch = entities[i:i+100]
            # MERGE (e:Symptom {name: entity.name}): 이름이 같으면 하나만
            # 동적 레이블 사용
            driver.execute_query(f"""
                UNWIND $batch AS entity
                MERGE (e:{label} {{name: entity.name}})
            """, batch=batch, database_=NEO4J_DATABASE)

        total_entities += len(entities)
        print(f"         {label}: {len(entities)}개")

    print(f"      step 1 - 엔티티 노드 {total_entities}개 생성")

    # 엔티티 타입별로 name 인덱스. 아래 MATCH (e:Label {name: ...}) 를 빠르게
    # f-string 으로 인덱스 이름과 레이블을 만든다
    # 2. 인덱스 생성 (각 엔티티 타입별)
    entity_types = list(entities_by_type.keys())
    for entity_type in entity_types:
        label = entity_type.capitalize()
        driver.execute_query(
            f"CREATE INDEX {entity_type}_name_idx IF NOT EXISTS FOR (e:{label}) ON (e.name)",
            database_=NEO4J_DATABASE
        )

    driver.execute_query(
        "CREATE INDEX question_qa_id_idx IF NOT EXISTS FOR (q:Question) ON (q.qa_id)",
        database_=NEO4J_DATABASE
    )
    driver.execute_query(
        "CREATE INDEX answer_qa_id_idx IF NOT EXISTS FOR (a:Answer) ON (a.qa_id)",
        database_=NEO4J_DATABASE
    )
    print(f"      step 2 - 인덱스 생성 ({len(entity_types)}개 엔티티 타입)")

    # QA 와 엔티티 연결 데이터 모으기. 이름은 MENTIONS 지만 Question 에 연결한다(답에서 나온 엔티티도 질문에 붙는다)
    # 3. QA-Entity 관계 데이터 수집
    mentions_data = []

    for qa_id, result in all_results.items():
        for entity in result.get('entities', []):
            entity_name = entity.get('name', '')
            entity_type = entity.get('type', '')
            if not entity_name or not entity_type:
                continue

            # Question-Entity 관계 데이터
            mentions_data.append({
                'qa_id': qa_id,
                'name': entity_name,
                'type': entity_type
            })

    # 4. MENTIONS 관계 생성
    if mentions_data:
        print(f"      step 3 - MENTIONS 관계 생성 중... ({len(mentions_data)}개)")

        # 레이블별로 묶어서 배치 (위와 같은 이유)
        # 타입별로 그룹화
        mentions_by_type = defaultdict(list)
        for data in mentions_data:
            mentions_by_type[data['type']].append(data)

        # 타입별로 배치 생성 (동적 레이블 사용)
        for entity_type, mentions in mentions_by_type.items():
            label = entity_type.capitalize()

            for i in range(0, len(mentions), 100):
                batch = mentions[i:i+100]
                # {{qa_id: data.qa_id}}: f-string 이라 중괄호 두 번
                # 주의: Question 의 qa_id 는 JSON 파일 값 그대로, data.qa_id 는 all_results 의 키다.
                #       캐시에서 불러오면 int 로 바꾸므로, 원래 파일의 qa_id 가 정수여야 둘이 맞는다
                driver.execute_query(f"""
                    UNWIND $batch AS data
                    MATCH (q:Question {{qa_id: data.qa_id}})
                    MATCH (e:{label} {{name: data.name}})
                    MERGE (q)-[:MENTIONS]->(e)
                """, batch=batch, database_=NEO4J_DATABASE)

        print(f"      step 3 - MENTIONS 관계 {len(mentions_data)}개 생성 완료")

    # 엔티티 간 관계 데이터 모으기. rel.get('type', 'RELATED_TO'): 타입이 없으면 기본 이름
    # 5. 엔티티 간 관계 생성
    relationship_data = []

    for qa_id, result in all_results.items():
        for rel in result.get('relationships', []):
            from_name = rel.get('from', '')
            from_type = rel.get('from_type', '')
            to_name = rel.get('to', '')
            to_type = rel.get('to_type', '')
            rel_type = rel.get('type', 'RELATED_TO')

            if not from_name or not to_name:
                continue

            relationship_data.append({
                'from_name': from_name,
                'from_type': from_type,
                'to_name': to_name,
                'to_type': to_type,
                'rel_type': rel_type,
                'evidence': rel.get('evidence', ''),
                'qa_id': qa_id
            })

    if relationship_data:
        print(f"      step 4 - 엔티티 간 관계 생성 중... ({len(relationship_data)}개)")

        # 관계 타입과 (from 레이블, to 레이블) 이 모두 쿼리 글에 들어가므로 두 번 묶는다
        # 관계 타입별로 그룹화하여 처리
        rels_by_type = defaultdict(list)
        for rel in relationship_data:
            rels_by_type[rel['rel_type']].append(rel)

        total_created = 0
        for rel_type, rels in rels_by_type.items():
            # 엔티티 타입 조합별로 한번 더 그룹화
            rels_by_entity_types = defaultdict(list)
            for rel in rels:
                key = (rel['from_type'], rel['to_type'])
                rels_by_entity_types[key].append(rel)

            # 엔티티 타입 조합별로 처리
            # for (from_type, to_type), type_rels in ...items(): 키가 튜플이라 괄호로 한 번 더 풀어 받는다
            for (from_type, to_type), type_rels in rels_by_entity_types.items():
                from_label = from_type.capitalize()
                to_label = to_type.capitalize()

                # MERGE (e1)-[r:타입]->(e2): 같은 관계는 하나만
                # ON CREATE SET: 처음 만들 때 count=1, 근거 문장, 출처 QA id 리스트
                # ON MATCH SET: 이미 있으면 count +1, qa_ids 에 없을 때만 추가 (CASE WHEN ... THEN ... ELSE ... END = Cypher 의 조건식)
                # r.qa_ids + rel.qa_id: 리스트 + 값 = 끝에 추가한 새 리스트
                # [왜] 여러 QA 에서 같은 관계가 나올수록 count 가 커진다 -> 관계의 "신뢰도" 처럼 쓸 수 있다
                # 주의: rel_type 은 스키마 검증을 통과한 값이라 비교적 안전하지만, 스키마 자체가 LLM 이 만든 것이다
                for i in range(0, len(type_rels), 50):
                    batch = type_rels[i:i+50]
                    driver.execute_query(f"""
                        UNWIND $batch AS rel
                        MATCH (e1:{from_label} {{name: rel.from_name}})
                        MATCH (e2:{to_label} {{name: rel.to_name}})
                        MERGE (e1)-[r:{rel_type}]->(e2)
                        ON CREATE SET
                            r.count = 1,
                            r.evidence = rel.evidence,
                            r.qa_ids = [rel.qa_id]
                        ON MATCH SET
                            r.count = r.count + 1,
                            r.qa_ids = CASE
                                WHEN rel.qa_id IN r.qa_ids THEN r.qa_ids
                                ELSE r.qa_ids + rel.qa_id
                            END
                    """, batch=batch, database_=NEO4J_DATABASE)
                    total_created += len(batch)

        print(f"      step 4 - 엔티티 간 관계 {total_created}개 생성 완료")

    print(f"\n   그래프 저장 완료!")


# ============================================
# 메인
# ============================================

# 직접 실행할 때만
if __name__ == "__main__":
    print("=" * 70)
    print("의료 지식 그래프 구축 (Medical Knowledge Graph)")
    print("=" * 70)

    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USER = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # all([a, b, c]): [출처] 파이썬 기본. 모두 참이면 True. 하나라도 None/빈 값이면 False
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("\n오류: Neo4j 연결 정보가 .env 파일에 없습니다")
        print("필요한 환경변수: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD")
        sys.exit(1)

    if not OPENAI_API_KEY:
        print("\n오류: OpenAI API 키가 .env 파일에 없습니다")
        print("필요한 환경변수: OPENAI_API_KEY")
        sys.exit(1)

    # Path.exists(): 파일/폴더가 있으면 True
    if not DATA_DIR.exists():
        print(f"\n오류: 데이터 디렉토리가 없습니다: {DATA_DIR}")
        print("data/ 폴더에 진료과별(내과, 산부인과, 소아청소년과, 응급의학과) JSON 파일을 넣어주세요")
        sys.exit(1)

    # 진료과마다 50개 -> 최대 200 QA -> LLM 최대 200번 (캐시가 없을 때)
    MAX_QA_PER_DEPT = 50  # 각 진료과별 처리 데이터 개수

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        # ============================================
        # Step 0: 통일된 도메인 스키마
        # ============================================
        # 캐시: 파일이 있으면 LLM 을 부르지 않고 불러온다. 스키마를 바꾸고 싶으면 이 파일을 지운다
        schema_path = OUTPUT_DIR / "domain_schemas.json"

        if schema_path.exists():  # 기존 스키마가 있으면 로드, 없으면 새로 추출
            print(f"\n[Step 0/3] 기존 스키마 로드 중...")
            with open(schema_path, 'r', encoding='utf-8') as f:
                unified_schema = json.load(f)
            print(f"   ✓ 기존 스키마 로드: {schema_path}")
        else:
            unified_schema = extract_unified_schema()

        # ============================================
        # Step 1: QA 그래프 구축
        # ============================================
        # Step 1 은 캐시와 상관없이 매번 실행 (DB 를 지우고 QA 를 다시 넣는다)
        all_qa_data = load_all_qa_data(max_qa_per_dept=MAX_QA_PER_DEPT)
        save_qa_graph_to_neo4j(all_qa_data, driver)

        # ============================================
        # Step 2: 엔티티 및 관계 추출
        # ============================================
        # 추출 결과도 캐시. 주의: MAX_QA_PER_DEPT 를 바꿔도 이 파일이 있으면 예전 결과를 그대로 쓴다
        results_path = OUTPUT_DIR / "extracted_graph.json"

        if results_path.exists():
            print(f"\n[Step 2/3] 기존 추출 결과 로드 중...")
            with open(results_path, 'r', encoding='utf-8') as f:
                all_results_raw = json.load(f)
                # {int(k): v for k, v in ...}: 딕셔너리 컴프리헨션. 문자열 키 "123" -> 정수 123
                # JSON에서 로드할 때 qa_id가 문자열이므로 정수로 변환
                all_results = {int(k): v for k, v in all_results_raw.items()}

            total_entities = sum(len(r.get('entities', [])) for r in all_results.values())
            total_relationships = sum(len(r.get('relationships', [])) for r in all_results.values())
            print(f"   ✓ 기존 추출 결과 로드: {results_path}")
            print(f"   데이터: {len(all_results)}개 QA | {total_entities}개 엔티티 | {total_relationships}개 관계")
        else:
            all_results = extract_all_entities_and_relationships(all_qa_data, unified_schema)

        save_graph_to_neo4j(all_results, driver)

    finally:
        driver.close()
