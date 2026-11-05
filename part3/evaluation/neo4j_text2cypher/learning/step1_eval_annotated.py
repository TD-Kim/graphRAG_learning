"""[1단계: 읽기] eval.py (Text2Cypher 골든셋 평가: 실행 평가 + 관계 방향 검사 + LLM-as-a-Judge) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
neo4j-graphrag 설명은 설치 소스(requirements.txt 의 neo4j-graphrag 1.14.1)로 확인했다.

전제: recommendations 데이터가 들어 있는 Neo4j (서버의 기본 DB 여야 한다. retriever.py 주석 참고).
      .env 에 NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, OPENAI_API_KEY (선택: DATABASE_NAME=recommendations)
데이터: text2cypher_gpt4o.csv 중 database == "recommendations" 인 792문항
        (유형: Simple Retrieval 247, Complex Retrieval 167, Simple Aggregation 115, Complex Aggregation 103, Pathfinding 90, Verbose 70.
         returns_results 열이 "True" 708개, "False" 84개)

흐름 (질문 하나에 LLM 2번: Cypher 작성 1번 + 채점 1번)
  골든셋 (질문, 정답 Cypher, 유형)
    -> [retriever.py] Text2CypherRetriever 로 Cypher 생성 + 실행
    -> Execution 평가 (규칙, 0~1): 실행됨? 결과 1건 이상? 관계 방향이 VALID_RELATIONSHIPS 와 맞나?  -> 셋의 평균
    -> LLM-as-a-Judge (1~5 세 가지): 질문, 정답 Cypher, 생성 Cypher, 양쪽 결과 유무를 주고 JSON 으로 점수
    -> EvalRecord 하나
  모든 질문 -> print_summary(전체/유형별 평균) -> print_issues(문제 항목 상세) -> save_results(CSV)

읽는 순서 권장: main -> evaluate_single -> extract_relationships_from_cypher / check_relationship_directions
              -> LLM_JUDGE_*_PROMPT, llm_judge_evaluate -> print_summary, print_issues -> save_results
실행 위치: part3/evaluation/neo4j_text2cypher 에서 PYTHONPATH=. python learning/step1_eval_annotated.py --limit 10
  (같은 폴더의 retriever.py 를 import 하므로 PYTHONPATH=. 가 필요하다. 원본은 python eval.py --limit 10.
   CSV 경로는 이 파일이 있는 폴더 기준이라 주석본을 실행하면 learning/ 안에서 CSV 를 찾는다 -> 주석본은 읽기용으로 두고 원본을 실행하자)
"""

# [출처] 표준 라이브러리. argparse: 명령줄 인자(--limit 10 같은 것)를 읽는다
import argparse
# [출처] 표준 라이브러리. csv: CSV 파일 읽기(DictReader)/쓰기(DictWriter)
import csv
# [출처] 표준 라이브러리. json.loads(글 -> 파이썬 값), json.dumps(파이썬 값 -> 글)
import json
# [출처] 표준 라이브러리. os.path 로 파일 경로를 만든다
import os
# [출처] 표준 라이브러리 re (정규표현식). Cypher 글에서 관계 패턴을 찾고, LLM 답에서 JSON 을 꺼낸다
import re
# [출처] 표준 라이브러리. time.time(): 현재 시각(초). 질문 하나에 걸린 시간 재기
import time
# [출처] 표준 라이브러리 dataclasses. @dataclass: 필드만 적으면 __init__ 등을 자동으로 만들어 주는 클래스
# asdict: dataclass 객체 -> 딕셔너리 / field(default_factory=list): 객체마다 새 빈 리스트를 기본값으로
from dataclasses import dataclass, asdict, field

# [출처] 외부 라이브러리 python-dotenv
from dotenv import load_dotenv

# import 보다 먼저 .env 를 읽는다 (아래 main 의 os.getenv("DATABASE_NAME") 가 값을 찾도록)
load_dotenv()

# [출처] 같은 폴더의 retriever.py
from retriever import create_driver, create_llm, build_retriever, generate_and_execute_cypher


# =============================================
# 데이터 구조
# =============================================

# @dataclass: 데코레이터. 바로 아래 클래스를 dataclass 로 바꿔 준다 (@이름 = 함수/클래스를 감싸서 기능을 더하는 문법)
@dataclass
# [이 파일에서 정의] 질문 하나의 평가 결과를 담는 그릇
# "이름: 타입 = 기본값" 모양으로 필드를 적는다. EvalRecord(question=..., ...) 처럼 만들고, 안 준 필드는 기본값
class EvalRecord:
    """단일 질문에 대한 평가 결과"""
    # 입력
    question: str = ""
    question_type: str = ""
    golden_cypher: str = ""
    # 생성 결과
    generated_cypher: str = ""
    # Execution 평가
    is_executable: bool = False
    execution_error: str = ""
    returns_results: bool = False
    result_count: int = 0
    # list 기본값을 = [] 로 쓰면 모든 객체가 같은 리스트를 공유하게 되어 dataclass 가 금지한다 -> field(default_factory=list)
    execution_results: list = field(default_factory=list)
    relationship_direction_correct: bool = False
    direction_detail: str = ""
    # LLM-as-a-Judge 평가
    # LLM 채점 세 가지 (각 1~5). 0 은 "채점 못 함(파싱 실패)" 의 표시
    intent_score: int = 0       # 1-5
    completeness_score: int = 0  # 1-5
    correctness_score: int = 0   # 1-5
    llm_judge_reasoning: str = ""
    # 요약 점수
    # execution_score: 이름과 달리 0/1 이 아니라 0, 1/3, 2/3, 1 중 하나가 된다 (아래 289줄)
    execution_score: float = 0.0  # 0 or 1
    llm_judge_avg: float = 0.0


# =============================================
# 데이터셋 로드
# =============================================

# [이 파일에서 정의] 골든셋 CSV 에서 한 DB 의 행만 골라 온다
# [반환] 딕셔너리 리스트. 각 행 = {"question", "cypher", "type", "database", "explanation", ..., "returns_results", ...}
def load_golden_dataset(csv_path: str, database_filter: str = "recommendations") -> list[dict]:
    """골든 데이터셋에서 특정 database의 레코드만 로드합니다."""
    records = []
    # with open(...) as f: 블록이 끝나면 파일을 자동으로 닫는다
    # encoding="utf-8": 한글이 깨지지 않게
    with open(csv_path, "r", encoding="utf-8") as f:
        # csv.DictReader(f): 첫 줄을 열 이름으로 쓰고, 각 행을 {열이름: 글} 딕셔너리로 준다 (값은 모두 글이다. "True" 도 글)
        reader = csv.DictReader(f)
        for row in reader:
            if row["database"] == database_filter:
                records.append(row)
    return records


# [이 파일에서 정의] 스키마 CSV 에서 해당 DB 의 스키마 글 하나를 찾는다
# [반환] 글. 못 찾으면 ValueError
def load_schema(csv_path: str, database_filter: str = "recommendations") -> str:
    """스키마 CSV에서 특정 database의 스키마 텍스트를 로드합니다."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["database"] == database_filter:
                # 찾자마자 return -> 함수가 바로 끝난다 (반복문도 멈춤)
                return row["schema"]
    # raise ValueError(...): 직접 에러를 일으켜 프로그램을 멈춘다. f"...{변수}" 로 어떤 DB 인지 메시지에 넣는다
    raise ValueError(f"Schema not found for database: {database_filter}")


# =============================================
# Execution 평가: 관계 방향 검사
# =============================================

# recommendations DB의 올바른 관계 방향 정의
# {(a, b, c), ...}: 튜플들의 집합(set). "in" 검사가 빠르다
# (출발 레이블, 관계 타입, 도착 레이블) = 허용되는 방향
# 주의: recommendations DB 에 고정된 목록이다. --dataset-db 를 바꾸면 모든 관계가 "스키마에 없는 관계" 가 된다
VALID_RELATIONSHIPS = {
    ("Movie", "IN_GENRE", "Genre"),
    ("User", "RATED", "Movie"),
    ("Actor", "ACTED_IN", "Movie"),
    ("Actor", "DIRECTED", "Movie"),
    ("Director", "DIRECTED", "Movie"),
    ("Director", "ACTED_IN", "Movie"),
    ("Person", "ACTED_IN", "Movie"),
    ("Person", "DIRECTED", "Movie"),
}


# [이 파일에서 정의] Cypher 글에서 (출발 레이블, 관계, 도착 레이블) 을 정규식으로 뽑는다
# -> list[tuple[str, str, str]]: 반환 타입 힌트
def extract_relationships_from_cypher(cypher: str) -> list[tuple[str, str, str]]:
    """Cypher 쿼리에서 관계 패턴 (source_label, rel_type, target_label) 을 추출합니다."""
    relationships = []

    # (var:Label)-[r:REL_TYPE]->(var:Label) 패턴 매칭
    # 정방향: ()-[]->(  )
    # r'...': raw 문자열. 역슬래시를 그대로 둔다 (정규식에 \( \w 같은 것이 많아서)
    # 정규식 읽기: \( 괄호 글자 / (\w+)? 변수 이름(있어도 없어도) / (?::(\w+))? ":레이블"(있어도 없어도, 레이블만 그룹으로)
    #             \s* 공백 0개 이상 / -\[ ... \]\s*-> 오른쪽 화살표 관계
    # 그룹 번호: 1 출발 변수, 2 출발 레이블, 3 관계 변수, 4 관계 타입, 5 도착 변수, 6 도착 레이블
    # 주의: (m:Movie {title: 'X'}) 처럼 속성이 붙은 노드, [:A|B] 여러 타입, [:R*1..3] 가변 길이는 이 패턴에 안 걸려 검사에서 빠진다
    forward_pattern = r'\((\w+)?(?::(\w+))?\)\s*-\[(\w+)?(?::(\w+))?\]\s*->\s*\((\w+)?(?::(\w+))?\)'
    # re.finditer(패턴, 글, re.IGNORECASE): 겹치지 않게 차례로 찾은 매치들 (대소문자 무시)
    # 주의: (a:A)-[:R]->(b:B)-[:S]->(c:C) 처럼 같은 방향으로 이어지면 (b:B) 를 첫 매치가 써 버려 두 번째 관계를 놓친다
    for m in re.finditer(forward_pattern, cypher, re.IGNORECASE):
        # m.group(2): 2번 그룹(출발 레이블). 없으면 None -> or "" 로 빈 글
        src_label = m.group(2) or ""
        rel_type = m.group(4) or ""
        tgt_label = m.group(6) or ""
        # 관계 타입이 있을 때만 기록 (-[r]-> 처럼 타입 없는 관계는 무시)
        if rel_type:
            relationships.append((src_label, rel_type, tgt_label))

    # 역방향: ()<-[]-()
    # 역방향 패턴 ()<-[]-(): 글자 순서와 실제 방향이 반대
    # 주의: 방향 없는 -[:R]- 패턴은 정방향/역방향 어느 쪽에도 안 걸려 검사하지 않는다
    reverse_pattern = r'\((\w+)?(?::(\w+))?\)\s*<-\[(\w+)?(?::(\w+))?\]\s*-\s*\((\w+)?(?::(\w+))?\)'
    for m in re.finditer(reverse_pattern, cypher, re.IGNORECASE):
        src_label = m.group(2) or ""
        rel_type = m.group(4) or ""
        tgt_label = m.group(6) or ""
        if rel_type:
            # 역방향이므로 실제 관계: target -> source
            # 역방향이므로 (오른쪽, 관계, 왼쪽) 순서로 뒤집어 저장 -> 항상 (출발, 관계, 도착) 모양
            relationships.append((tgt_label, rel_type, src_label))

    return relationships


# [이 파일에서 정의] 뽑은 관계가 VALID_RELATIONSHIPS 와 맞는지 검사
# [반환] (맞으면 True, 설명 글)
def check_relationship_directions(cypher: str) -> tuple[bool, str]:
    """생성된 Cypher의 관계 방향이 스키마와 일치하는지 검사합니다."""
    rels = extract_relationships_from_cypher(cypher)

    # 관계 패턴이 하나도 없으면 "맞음" 으로 본다
    # 주의: 생성 실패로 Cypher 가 "" 여도 여기서 True 가 된다 -> 실행 실패한 문항도 방향 점수 1/3 을 받는다
    if not rels:
        return True, "관계 패턴 없음 (노드 단독 쿼리)"

    issues = []
    for src, rel_type, tgt in rels:
        # 레이블이 없는 쪽이 있으면 판단 불가 -> 건너뜀 (문제로 치지 않는다)
        if not src or not tgt:
            continue  # 라벨이 없으면 검사 불가
        if (src, rel_type, tgt) not in VALID_RELATIONSHIPS:
            # 혹시 역방향으로 존재하는지 확인
            # 허용 목록에 없으면, 뒤집은 방향이 있는지 확인해 "방향 역전" 과 "아예 없는 관계" 를 구분
            if (tgt, rel_type, src) in VALID_RELATIONSHIPS:
                issues.append(f"방향 역전: (:{src})-[:{rel_type}]->(:{tgt}) → 올바른 방향: (:{tgt})-[:{rel_type}]->(:{src})")
            else:
                issues.append(f"스키마에 없는 관계: (:{src})-[:{rel_type}]->(:{tgt})")

    if issues:
        # "; ".join(issues): 문제 설명들을 세미콜론으로 이어 한 줄로
        return False, "; ".join(issues)
    return True, "모든 관계 방향 올바름"


# =============================================
# LLM-as-a-Judge 평가
# =============================================

# LLM_JUDGE_SYSTEM_PROMPT (143~180줄): 채점 LLM 의 system 메시지. llm_judge_evaluate 에서 .format(schema=...) 로 {schema} 를 채운다
# 구역별 역할
#   첫 두 줄            : 역할 (Text2Cypher 평가 전문가) + 할 일 (생성 Cypher 를 정답 Cypher 와 비교)
#   <데이터베이스 스키마> : {schema} 자리. 레이블/속성/관계를 알아야 쿼리가 맞는지 판단할 수 있다
#   "JSON 객체만"       : 출력 형식을 강하게 제한 (파싱하기 쉽게)
#   <평가 기준>         : 루브릭. intent / completeness / correctness 각각 5~1점의 뜻을 적어 채점 기준을 고정한다
#   <출력 형식>         : {{"intent_score": <int>, ...}} -> .format() 뒤에는 { } 하나로 보인다 ({{ }} 는 글자 중괄호)
#                         reasoning 은 한국어로 짧게
LLM_JUDGE_SYSTEM_PROMPT = """당신은 Text2Cypher 쿼리 생성 평가 전문가입니다.
사용자의 자연어 질문에 대해 생성된 Cypher 쿼리를 골든(reference) Cypher 쿼리와 비교하여 평가합니다.

<데이터베이스 스키마>
{schema}
</데이터베이스 스키마>

반드시 다음 세 가지 기준으로 평가를 수행하고, JSON 객체로 결과를 반환해야 합니다.
다른 어떤 설명이나 텍스트도 포함하지 말고, JSON 객체만 반환해야 합니다.

<평가 기준>
1. intent_score (1-5): 생성된 쿼리가 사용자의 의도를 얼마나 정확하게 반영하는지 평가합니다.
   - 5: 의도를 완벽하게 반영
   - 4: 약간의 차이는 있지만 대부분 정확함
   - 3: 부분적으로 의도를 반영
   - 2: 의도를 크게 오해함
   - 1: 완전히 잘못된 의도

2. completeness_score (1-5): 필요한 모든 대상, 조건, 범위, 집계 방법이 반영되었는지 평가합니다.
   - 5: 모든 요구사항이 완전히 반영됨
   - 4: 약간의 누락
   - 3: 일부 주요 요소 누락
   - 2: 주요 요소 대부분 누락
   - 1: 거의 반영되지 않음

3. correctness_score (1-5): 불필요한 조건이나 잘못 해석된 부분이 있는지 평가합니다.
   - 5: 불필요하거나 잘못된 부분 없음
   - 4: 매우 작은 불필요한 부분 있음
   - 3: 일부 불필요하거나 잘못된 조건 있음
   - 2: 상당한 잘못된 조건 있음
   - 1: 대부분 잘못됨
</평가 기준>

Return ONLY a JSON object in this exact format:
<출력 형식>
{{"intent_score": <int>, "completeness_score": <int>, "correctness_score": <int>, "reasoning": "<brief explanation in Korean>"}}
</출력 형식>
"""


# LLM_JUDGE_USER_PROMPT (183~203줄): 채점 LLM 의 user 메시지. 문항마다 .format(...) 으로 채운다
# 구역별 역할
#   <사용자 질문>          : {question}
#   <정답 Cypher>          : {golden_cypher} 기준 답
#   <생성된 Cypher>        : {generated_cypher} 평가 대상 (생성 실패면 빈 칸)
#   <정답/생성 쿼리 실행 결과> : "결과 있음"/"결과 없음". 정답도 빈 결과인 문항이면 생성 쿼리의 빈 결과를 탓하지 않게
#   마지막 줄              : JSON 만 돌려 달라고 한 번 더 강조
# 주의: 실제 결과 "값" 은 주지 않는다. 채점 LLM 은 두 쿼리 글만 비교하고, 결과가 같은지는 모른다
LLM_JUDGE_USER_PROMPT = """<사용자 질문>
{question}
</사용자 질문>

<정답 Cypher (reference)>
{golden_cypher}
</정답 Cypher>

<생성된 Cypher (평가 대상)>
{generated_cypher}
</생성된 Cypher>

<정답 쿼리 실행 결과>
{golden_returns_results}
</정답 쿼리 실행 결과>

<생성된 쿼리 실행 결과>
{generated_returns_results}
</생성된 쿼리 실행 결과>

Evaluate the generated Cypher query. Return ONLY the JSON object."""


# [이 파일에서 정의] LLM 에 채점을 시키고 JSON 을 딕셔너리로 꺼낸다
# [반환] {"intent_score", "completeness_score", "correctness_score", "reasoning"}
def llm_judge_evaluate(
    llm,
    schema: str,
    question: str,
    golden_cypher: str,
    generated_cypher: str,
    golden_returns_results: bool,
    generated_returns_results: bool,
) -> dict:
    """LLM-as-a-Judge로 생성된 Cypher를 평가합니다."""
    # str.format(schema=...): 템플릿의 {schema} 를 값으로 채운 새 글. 넣는 값 안의 중괄호는 다시 해석되지 않는다
    system_msg = LLM_JUDGE_SYSTEM_PROMPT.format(schema=schema)
    user_msg = LLM_JUDGE_USER_PROMPT.format(
        question=question,
        golden_cypher=golden_cypher,
        generated_cypher=generated_cypher,
        # 조건식: True 면 "결과 있음", False 면 "결과 없음"
        golden_returns_results="결과 있음" if golden_returns_results else "결과 없음",
        generated_returns_results="결과 있음" if generated_returns_results else "결과 없음",
    )

    # llm.invoke(user 글, system_instruction=system 글)
    # [출처] 외부 라이브러리 neo4j-graphrag (OpenAILLM)
    # [입력] 첫 인자: user 메시지 / system_instruction: 이번 호출의 system 메시지 (소스 확인: [system, user] 순서로 보낸다)
    # [반환] LLMResponse. .content 에 답 글
    # 주의: Cypher 를 쓴 모델(gpt-4o)과 같은 모델이 채점한다. 자기 답에 후할 수 있다
    # 주의: 이 호출은 try 로 감싸지 않았다. API 오류가 나면 평가 전체가 멈추고 그때까지의 결과도 저장되지 않는다
    response = llm.invoke(user_msg, system_instruction=system_msg)
    # .strip(): 앞뒤 공백 제거
    content = response.content.strip()

    # JSON 파싱
    # 코드블럭 제거
    # LLM 이 ```json ... ``` 으로 감싸 답하는 경우가 많아서 앞뒤 코드블록 표시를 지운다
    # re.sub(패턴, 바꿀글, 원래글): 패턴에 맞는 부분을 바꾼 새 글. ^ 는 글의 시작, $ 는 끝
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    # json.loads(글): JSON 글 -> 파이썬 딕셔너리. 형식이 틀리면 json.JSONDecodeError
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # JSON 부분만 추출 시도
        # re.search(r'\{.*\}', 글, re.DOTALL): 첫 { 부터 마지막 } 까지 (DOTALL: . 이 줄바꿈도 포함)
        # 앞뒤에 설명 글이 붙은 답에서 JSON 부분만 꺼내려는 2차 시도
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            # 주의: 여기서도 JSON 이 깨져 있으면 except 밖이라 JSONDecodeError 가 그대로 터져 평가 전체가 멈춘다
            result = json.loads(match.group())
        else:
            # 둘 다 실패하면 0점과 실패 메시지(앞 200자). content[:200]: 글의 앞 200자
            result = {
                "intent_score": 0,
                "completeness_score": 0,
                "correctness_score": 0,
                "reasoning": f"LLM 응답 파싱 실패: {content[:200]}",
            }

    return result


# =============================================
# 평가 실행
# =============================================

# [이 파일에서 정의] 문항 하나의 평가 전체
# [입력] retriever, llm, schema(스키마 글), golden(골든셋 한 행 딕셔너리)
# [반환] EvalRecord
def evaluate_single(
    retriever,
    llm,
    schema: str,
    golden: dict,
) -> EvalRecord:
    """단일 질문에 대해 전체 평가를 수행합니다."""
    # dataclass 객체 만들기. 안 준 필드는 기본값
    record = EvalRecord(
        question=golden["question"],
        question_type=golden["type"],
        golden_cypher=golden["cypher"],
    )

    # 1. Cypher 생성 및 실행 (retriever.get_search_results 사용)
    # retriever.py 의 함수. (생성 Cypher, 결과 리스트, 에러 글 또는 None)
    generated_cypher, results, error = generate_and_execute_cypher(retriever, golden["question"])
    record.generated_cypher = generated_cypher
    record.execution_results = results

    # if error: 에러 글이 있으면(None 이나 "" 가 아니면) 실행 실패
    if error:
        record.is_executable = False
        record.execution_error = error
        record.returns_results = False
    else:
        record.is_executable = True
        # len(results) > 0: 결과가 1건 이상이면 True
        # 주의: "결과가 있다" 만 보고 "결과가 맞다" 는 보지 않는다. 엉뚱한 쿼리도 결과는 나온다
        #       (정답 Cypher 도 실행해 결과를 비교하면 execution accuracy 라는 더 강한 지표가 된다)
        record.returns_results = len(results) > 0
        record.result_count = len(results)

    # 2. Execution 평가: 관계 방향 검사
    dir_ok, dir_detail = check_relationship_directions(record.generated_cypher)
    record.relationship_direction_correct = dir_ok
    record.direction_detail = dir_detail

    # Execution 점수: 실행 가능 + 결과 있음 + 방향 올바름 → 모두 충족 시 1.0
    # True/False 리스트. 파이썬에서 True 는 1, False 는 0 으로 더해진다
    exec_factors = [record.is_executable, record.returns_results, record.relationship_direction_correct]
    # sum / len: 참인 개수의 비율 -> 0, 0.33, 0.67, 1.0
    record.execution_score = sum(exec_factors) / len(exec_factors)

    # 4. LLM-as-a-Judge 평가
    # 골든셋 CSV 의 값은 글이라 "True" 와 비교해 bool 로 바꾼다. 열이 없으면 "True" 로 본다
    golden_returns = golden.get("returns_results", "True") == "True"
    # 이름=값 으로 넘기는 키워드 인자. 순서를 헷갈리지 않는다
    judge_result = llm_judge_evaluate(
        llm=llm,
        schema=schema,
        question=golden["question"],
        golden_cypher=golden["cypher"],
        generated_cypher=record.generated_cypher,
        golden_returns_results=golden_returns,
        generated_returns_results=record.returns_results,
    )
    # dict.get(키, 0): 키가 없으면 0
    # 주의: LLM 이 "4" 처럼 글로 주면 아래 덧셈에서 TypeError 가 날 수 있다 (int() 변환이 없다)
    record.intent_score = judge_result.get("intent_score", 0)
    record.completeness_score = judge_result.get("completeness_score", 0)
    record.correctness_score = judge_result.get("correctness_score", 0)
    record.llm_judge_reasoning = judge_result.get("reasoning", "")
    # 세 점수의 평균 (0~5)
    record.llm_judge_avg = (
        record.intent_score + record.completeness_score + record.correctness_score
    ) / 3.0

    return record


# [이 파일에서 정의] 전체 요약과 유형별 평균을 출력
def print_summary(records: list[EvalRecord]):
    """평가 요약을 출력합니다."""
    total = len(records)
    if total == 0:
        print("평가 대상 없음")
        return

    # sum(1 for r in records if 조건): 제너레이터 식. 조건을 만족하는 개수 세기 (리스트를 만들지 않고 하나씩 센다)
    executable = sum(1 for r in records if r.is_executable)
    has_results = sum(1 for r in records if r.returns_results)
    dir_correct = sum(1 for r in records if r.relationship_direction_correct)
    avg_exec_score = sum(r.execution_score for r in records) / total

    avg_intent = sum(r.intent_score for r in records) / total
    avg_completeness = sum(r.completeness_score for r in records) / total
    avg_correctness = sum(r.correctness_score for r in records) / total
    avg_llm_judge = sum(r.llm_judge_avg for r in records) / total

    # 유형별 통계
    # dict[str, list[EvalRecord]]: 변수 타입 힌트. {유형: [그 유형의 EvalRecord...]}
    type_stats: dict[str, list[EvalRecord]] = {}
    for r in records:
        # dict.setdefault(키, []): 키가 없으면 [] 를 넣고, 있으면 기존 값을 돌려준다 -> 바로 .append 할 수 있다
        type_stats.setdefault(r.question_type, []).append(r)

    print("\n" + "=" * 70)
    print("  TEXT2CYPHER 평가 결과 요약")
    print("=" * 70)
    print(f"\n총 평가 건수: {total}")

    print(f"\n--- Execution 평가 ---")
    # {executable/total*100:.1f}%: 백분율을 소수 첫째 자리까지
    print(f"  실행 가능:           {executable}/{total} ({executable/total*100:.1f}%)")
    print(f"  결과 반환:           {has_results}/{total} ({has_results/total*100:.1f}%)")
    print(f"  관계 방향 올바름:    {dir_correct}/{total} ({dir_correct/total*100:.1f}%)")
    print(f"  Execution 평균 점수: {avg_exec_score:.3f}")

    print(f"\n--- LLM-as-a-Judge 평가 (1-5) ---")
    print(f"  의도 반영 (Intent):      {avg_intent:.2f}")
    print(f"  완전성 (Completeness):   {avg_completeness:.2f}")
    print(f"  정확성 (Correctness):    {avg_correctness:.2f}")
    print(f"  LLM Judge 평균:          {avg_llm_judge:.2f}")

    print(f"\n--- 유형별 LLM Judge 평균 ---")
    # sorted(type_stats.items()): 유형 이름순으로 (유형, 리스트) 쌍
    # [왜] 전체 평균만 보면 "집계 질문에 약하다" 같은 패턴을 놓친다
    for qtype, recs in sorted(type_stats.items()):
        t_avg = sum(r.llm_judge_avg for r in recs) / len(recs)
        t_exec = sum(1 for r in recs if r.is_executable)
        print(f"  [{qtype}] 건수={len(recs)}, 실행가능={t_exec}/{len(recs)}, LLM Judge 평균={t_avg:.2f}")

    print("\n" + "=" * 70)


# [이 파일에서 정의] 문제가 있는 문항만 골라 정답/생성 Cypher 를 나란히 출력
def print_issues(records: list[EvalRecord]):
    """문제가 있는 평가 결과만 상세히 출력합니다."""
    # 문제가 있는 레코드 필터링
    issues = []
    for r in records:
        # 문제 기준: 실행 실패 or 빈 결과 or 방향 오류 or LLM 평균 3점 미만
        # 주의: 정답도 빈 결과인 문항(returns_results=False, 84개)은 생성 쿼리가 맞아도 "빈 결과" 로 문제 목록에 들어간다
        if not r.is_executable or not r.returns_results or not r.relationship_direction_correct or r.llm_judge_avg < 3.0:
            issues.append(r)

    if not issues:
        print("\n🎉 문제가 있는 항목이 없습니다!")
        return

    print("\n" + "=" * 90)
    print(f"  ⚠️  문제가 있는 항목 ({len(issues)}건)")
    print("=" * 90)

    for idx, r in enumerate(issues, 1):
        # 문제 유형 태그 생성
        tags = []
        if not r.is_executable:
            tags.append("❌ 실행 실패")
        if r.is_executable and not r.returns_results:
            tags.append("⚠️  빈 결과")
        if not r.relationship_direction_correct:
            tags.append("🔀 관계 방향 오류")
        if r.llm_judge_avg < 3.0:
            tags.append(f"📉 낮은 점수 ({r.llm_judge_avg:.1f}/5)")

        # ' | '.join(tags): 태그들을 " | " 로 이어 한 줄로
        print(f"\n[{idx}] {' | '.join(tags)}")
        print(f"📝 질문: {r.question}")
        print(f"🏷️  유형: {r.question_type}")

        if not r.is_executable:
            # r.execution_error[:150]: 앞 150자. 더 길면 ... 을 붙인다 (조건식)
            print(f"❌ 에러: {r.execution_error[:150]}{'...' if len(r.execution_error) > 150 else ''}")

        if not r.relationship_direction_correct:
            print(f"🔀 방향 문제: {r.direction_detail}")

        if r.llm_judge_avg < 3.0:
            print(f"📊 LLM Judge 점수: Intent={r.intent_score}, Complete={r.completeness_score}, Correct={r.correctness_score}")
            print(f"💭 판단 근거: {r.llm_judge_reasoning[:200]}{'...' if len(r.llm_judge_reasoning) > 200 else ''}")

        # Golden vs Generated 비교 (문제가 있는 경우만)
        print(f"\n   Golden Cypher:")
        # .split('\n'): 여러 줄 쿼리를 줄 단위로 나눠 앞에 │ 를 붙여 출력
        for line in r.golden_cypher.split('\n'):
            print(f"   │ {line}")

        print(f"\n   Generated Cypher:")
        if r.generated_cypher:
            for line in r.generated_cypher.split('\n'):
                print(f"   │ {line}")
        else:
            print(f"   │ (생성 실패)")

        # 실행 결과 출력
        print(f"\n   실행 결과 ({r.result_count}건):")
        if r.execution_results:
            # 결과는 최대 3건만 보여 준다
            max_display = 3  # 최대 3건만 표시
            for idx, result in enumerate(r.execution_results[:max_display], 1):
                # 결과를 읽기 쉽게 포맷팅
                # {k}={v} for k, v in result.items(): 딕셔너리의 (키, 값) 쌍을 "키=값" 글로
                result_str = ", ".join([f"{k}={v}" for k, v in result.items()])
                print(f"   │ [{idx}] {result_str}")
        elif r.is_executable:
            print(f"   │ (빈 결과)")
        else:
            print(f"   │ (실행 실패로 결과 없음)")

    # 참고: 이 함수는 records 가 비어 있으면 위 if not issues 에서 먼저 끝나므로 len(records) 로 나눌 때 0 나눗셈은 일어나지 않는다
    print(f"\n총 {len(issues)}건의 문제 발견 (전체 {len(records)}건 중 {len(issues)/len(records)*100:.1f}%)")
    print("=" * 90)


# [이 파일에서 정의] EvalRecord 리스트를 CSV 로 저장
def save_results(records: list[EvalRecord], output_path: str):
    """평가 결과를 CSV로 저장합니다."""
    if not records:
        return
    # asdict(dataclass 객체) -> 딕셔너리. 그 키 목록 = CSV 열 이름
    fieldnames = list(asdict(records[0]).keys())
    # "w": 쓰기 모드(있으면 덮어씀). newline="": csv 모듈이 줄바꿈을 직접 처리하게 (빈 줄이 끼는 것 방지)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        # csv.DictWriter(f, fieldnames=[...]): 딕셔너리를 행으로 쓰는 객체. writeheader() 로 첫 줄(열 이름)
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = asdict(r)
            # 멀티라인 문자열 처리
            for k, v in row.items():
                # isinstance(값, str): 그 타입인지 확인. 글이면 줄바꿈을 \n 두 글자(역슬래시+n)로 바꿔 한 칸에 한 줄로
                if isinstance(v, str):
                    row[k] = v.replace("\n", "\\n")
                elif isinstance(v, list):
                    # execution_results는 JSON으로 직렬화
                    # json.dumps(값, ensure_ascii=False): 리스트 -> JSON 글. ensure_ascii=False 는 한글을 \uXXXX 로 바꾸지 않게
                    # 주의: 결과에 neo4j Node/Relationship, 날짜 같은 값이 있으면 json.dumps 가 TypeError 를 내 저장이 멈출 수 있다
                    row[k] = json.dumps(v, ensure_ascii=False)
            writer.writerow(row)
    print(f"\n결과 저장 완료: {output_path}")


# =============================================
# 메인 함수
# =============================================

# [이 파일에서 정의] 인자 읽기 -> 데이터/스키마 로드 -> 연결 -> 문항마다 평가 -> 요약/문제/CSV
def main():
    # argparse.ArgumentParser(description=...): 명령줄 인자 해석기. python eval.py -h 로 도움말이 나온다
    parser = argparse.ArgumentParser(description="Text2Cypher 평가")
    # add_argument("--이름", type=타입, default=기본값, help=설명): 인자 하나 등록. --limit 10 -> args.limit == 10 (int)
    parser.add_argument("--limit", type=int, default=0, help="평가할 최대 건수 (0=전체)")
    parser.add_argument("--output", type=str, default="eval_results.csv", help="결과 CSV 파일 경로")
    parser.add_argument("--dataset", type=str, default="text2cypher_gpt4o.csv", help="골든 데이터셋 CSV 경로")
    parser.add_argument("--schema-csv", type=str, default="text2cypher_schemas.csv", help="스키마 CSV 경로")
    parser.add_argument(
        # --dataset-db 의 기본값을 .env 의 DATABASE_NAME 에서 가져온다. 하이픈은 args.dataset_db 처럼 밑줄로 바뀐다
        "--dataset-db",
        type=str,
        default=os.getenv("DATABASE_NAME", "recommendations"),
        help="골든 데이터셋 필터링용 database 이름 (기본값: .env의 DATABASE_NAME 또는 'recommendations')"
    )
    # 주의: --neo4j-db 는 받기만 하고 어디에서도 쓰지 않는다. 실행은 항상 서버의 기본 DB 로 간다
    parser.add_argument("--neo4j-db", type=str, default="neo4j", help="Neo4j 실행 대상 데이터베이스명")
    # parse_args(): 실제 명령줄을 읽어 args 객체를 만든다
    args = parser.parse_args()

    # 데이터셋, 스키마 로드
    # os.path.abspath(__file__): 이 파일의 절대 경로 / dirname: 그 폴더
    # -> 어느 폴더에서 실행하든 CSV 를 이 파일 옆에서 찾는다
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(script_dir, args.dataset)
    schema_csv_path = os.path.join(script_dir, args.schema_csv)

    print("[1/5] 골든 데이터셋 로드 중...")
    golden_data = load_golden_dataset(dataset_path, args.dataset_db)
    # --limit 이 0 보다 크면 앞에서부터 그만큼만. [:n] 은 리스트 앞 n개
    # [왜] 792개 전부면 LLM 호출이 약 1,600번. 처음엔 --limit 10 으로 작게 돌린다
    if args.limit > 0:
        golden_data = golden_data[:args.limit]
    print(f"  → {len(golden_data)}건 로드 완료 (database={args.dataset_db})")

    print("[2/5] 스키마 로드 중...")
    schema = load_schema(schema_csv_path, args.dataset_db)
    print(f"  → 스키마 로드 완료 ({len(schema)} chars)")

    # Neo4j 연결 + Retriever 생성
    print("[3/5] Neo4j 연결 및 Retriever 생성 중...")
    driver = create_driver()
    llm = create_llm()
    # examples 를 안 준다 -> zero-shot (스키마만 보고 Cypher 작성). 예제를 넣으면 점수가 오르는지 비교해 볼 수 있다
    retriever = build_retriever(driver, llm, neo4j_schema=schema)
    print("  → Retriever 생성 완료")

    # 평가 실행
    print(f"[4/5] 평가 실행 중... ({len(golden_data)}건)")
    results: list[EvalRecord] = []
    # enumerate(리스트): (0부터 번호, 원소). 출력에는 i+1
    for i, golden in enumerate(golden_data):
        # end="": 줄바꿈 없이 출력 (같은 줄 뒤에 결과를 이어 찍으려고) / flush=True: 바로 화면에 내보내기
        print(f"  [{i+1}/{len(golden_data)}] {golden['question']}", end="", flush=True)
        start_t = time.time()
        # 주의: evaluate_single 을 try 로 감싸지 않았다. 채점 중 예외 하나로 전체가 멈추고 save_results 까지 가지 못한다
        record = evaluate_single(retriever, llm, schema, golden)
        elapsed = time.time() - start_t
        status = "✓" if record.is_executable else "✗"
        print(f" {status} ({elapsed:.1f}s, exec={record.execution_score:.2f}, judge={record.llm_judge_avg:.2f})")
        results.append(record)

    # 결과 출력 + 저장
    print("[5/5] 결과 정리 중...")
    print_summary(results)
    print_issues(results)

    output_path = os.path.join(script_dir, args.output)
    save_results(results, output_path)

    # 드라이버 연결 닫기
    driver.close()


# 직접 실행할 때만 main()
if __name__ == "__main__":
    main()
