"""[1단계: 읽기] prompts.py (Cypher 생성 / 수정 / 최종 답변 프롬프트와 의료 few-shot 예시) 의 상세 주석 버전. 코드는 원본과 동일.

주석 읽는 법 (함수나 문법이 처음 나올 때 자세히, 두 번째부터는 짧게)
  [출처] 파이썬 기본 / 파이썬 표준 라이브러리(설치 없이 import) / 외부 라이브러리(설치 필요) / 이 파일에서 정의
  [입력] 무엇을 넣나   [반환] 무엇이 나오나   [왜] 여기서 왜 쓰나
LangChain 설명은 설치 소스(langchain-core 1.3.0, requirements.txt 기준)로 확인했다.

이 파일은 "글(문자열)" 만 정의한다. 함수도 import 도 없다.
  *_SYSTEM_TEMPLATE : 시스템 메시지 (LLM 의 역할, 규칙)
  *_USER_TEMPLATE   : 사용자 메시지 (스키마, 예시, 질문을 끼워 넣을 {자리} 가 있는 틀)
  *_PROMPTS         : [("system", 시스템글), ("user", 사용자글)] 튜플 리스트
                      -> nodes.py 에서 ChatPromptTemplate.from_messages(*_PROMPTS) 로 프롬프트 틀 객체가 된다
                      -> .format_messages(schema=..., question=...) 로 {자리} 를 채워 메시지 리스트를 만든다

어디서 쓰이나 (nodes.py)
  GENERATE_CYPHER_PROMPTS -> generate_cypher_node   {schema} {fewshot_examples} {question}
  CORRECT_CYPHER_PROMPTS  -> correct_cypher_node    {schema} {question} {cypher} {errors}
  FINAL_ANSWER_PROMPTS    -> answer_node            {cypher_query} {context} {question}

읽는 순서 권장: FEWSHOT_EXAMPLES -> GENERATE -> CORRECT -> FINAL_ANSWER
실행 위치: 정의만 있는 모듈 (실행해도 출력 없음). nodes.py 가 import 해서 쓴다.
"""

# ============================================
# Few-shot 예시
# ============================================

# Cypher 쿼리 생성을 위한 Few-shot 예시 (의료 지식 그래프 도메인)
# few-shot 예시: "질문 -> 정답 Cypher" 쌍 10개. 문자열 하나가 예시 하나
# [왜] LLM 이 이 DB 의 레이블(Symptom, Disease, ...), 관계 이름(INDICATES, TREATS, ...), 방향을 따라 쓰게 한다
# 예시 안의 {name: '기침'} 같은 중괄호는 Cypher 문법이다.
#   이 글은 프롬프트 틀에 직접 쓰지 않고 {fewshot_examples} 자리에 "값" 으로 넣기 때문에 괜찮다.
#   틀(template) 자체에 적었다면 LangChain 이 {name: '기침'} 을 채울 자리로 읽어 에러가 난다 (그럴 땐 {{ }} 로 써야 한다)
FEWSHOT_EXAMPLES = [
    "USER INPUT: '기침 증상과 관련된 질병은?' QUERY: MATCH (s:Symptom {name: '기침'})-[:INDICATES]->(d:Disease) RETURN d.name",
    "USER INPUT: '폐렴을 진단하는 검사는?' QUERY: MATCH (t:Test)-[:DIAGNOSES_FOR]->(d:Disease {name: '폐렴'}) RETURN t.name",
    "USER INPUT: '당뇨병 치료 방법을 알려줘' QUERY: MATCH (tr:Treatment)-[:TREATS]->(d:Disease {name: '당뇨병'}) RETURN tr.name LIMIT 5",
    "USER INPUT: '고혈압에 사용하는 약물은?' QUERY: MATCH (m:Medication)-[:TREATS]->(d:Disease {name: '고혈압'}) RETURN m.name",
    "USER INPUT: '두통과 관련된 신체 부위는?' QUERY: MATCH (s:Symptom {name: '두통'})-[:AFFECTS]->(a:Anatomy) RETURN a.name",
    "USER INPUT: '천식 증상에는 무엇이 있나요?' QUERY: MATCH (s:Symptom)-[:INDICATES]->(d:Disease {name: '천식'}) RETURN DISTINCT s.name",
# 리스트 안의 빈 줄은 보기 좋게 묶은 것뿐 (파이썬은 무시한다)

    # Question, Department 노드를 쓰는 예시: medical2kg 의 질문 데이터 쪽 구조
    "USER INPUT: '내과 질문 중 당뇨병 관련 질문들을 보여줘' QUERY: MATCH (q:Question)-[:BELONGS_TO]->(d:Department {name: '내과'}) WHERE q.content CONTAINS '당뇨병' RETURN q.content LIMIT 5",
    "USER INPUT: '응급의학과에서 다루는 질병은?' QUERY: MATCH (q:Question)-[:BELONGS_TO]->(d:Department {name: '응급의학과'}), (q)-[:MENTIONS]->(dis:Disease) RETURN DISTINCT dis.name LIMIT 10",

    # <-[:INDICATES]- : 화살표 방향이 반대인 패턴. 스키마의 방향 (Symptom)-[:INDICATES]->(Disease) 를 지키려고
    "USER INPUT: '폐렴과 관련된 증상과 검사를 함께 보여줘' QUERY: MATCH (d:Disease {name: '폐렴'})<-[:INDICATES]-(s:Symptom), (d)<-[:DIAGNOSES_FOR]-(t:Test) RETURN s.name AS symptom, t.name AS test LIMIT 5",

    # 집계 예시: count(q) + ORDER BY ... DESC LIMIT 5
    "USER INPUT: '가장 많이 언급된 질병 5개는?' QUERY: MATCH (q:Question)-[:MENTIONS]->(d:Disease) RETURN d.name, count(q) AS mention_count ORDER BY mention_count DESC LIMIT 5",
]

# "\n".join(리스트): 예시들을 줄바꿈으로 이어 하나의 글로. 이 글이 {fewshot_examples} 자리에 들어간다
FEWSHOT_EXAMPLES_STR = "\n".join(FEWSHOT_EXAMPLES)

# ============================================
# Cypher 쿼리 생성 프롬프트
# ============================================

# Cypher 생성용 시스템 메시지. 3중 따옴표 """ 는 여러 줄 문자열 문법
# "백틱이나 다른 것으로 감싸지 마세요": LLM 이 ```cypher ... ``` 로 감싸면 그대로 실행되어 문법 오류가 나기 때문
# 주의: 이 부탁을 LLM 이 어기면 nodes.py 는 따로 벗겨 내지 않는다 (graphrag_tool_agent 의 tools.py 는 ``` 를 벗겨 낸다)
GENERATE_CYPHER_SYSTEM_TEMPLATE = """당신은 Neo4j 전문가입니다. 입력된 질문에 대해 문법적으로 올바른 Cypher 쿼리를 생성하세요.
백틱이나 다른 것으로 감싸지 마세요. Cypher 쿼리문만 응답하세요!"""

# Cypher 생성용 사용자 메시지 틀. {schema} {fewshot_examples} {question} 이 채울 자리
# f-string 이 아니다 (앞에 f 가 없다). 나중에 ChatPromptTemplate 이 format_messages(...) 로 채운다
# <schema> ... </schema> 같은 XML 비슷한 태그: LLM 에게 "여기부터 여기까지가 스키마" 라고 구역을 나눠 보여 주는 관례
GENERATE_CYPHER_USER_TEMPLATE = """
<schema>
{schema}
</schema>

다음은 질문과 대응하는 Cypher 쿼리의 예시들입니다:
<examples>
{fewshot_examples}
</examples>

<user_question>
{question}
</user_question>
Cypher 쿼리:"""

# (역할, 글) 튜플의 리스트. 역할 "system" 은 SystemMessage, "user" 는 HumanMessage 가 된다
# (소스 확인: langchain_core/prompts/chat.py 에서 "human", "user" 둘 다 HumanMessage 로 바뀐다)
GENERATE_CYPHER_PROMPTS = [
    ("system", GENERATE_CYPHER_SYSTEM_TEMPLATE),
    ("user", GENERATE_CYPHER_USER_TEMPLATE),
]


# ============================================
# Cypher 쿼리 수정 프롬프트
# ============================================

# Cypher 수정용 시스템 메시지. "주니어가 쓴 쿼리를 검토하는 전문가" 역할을 준다
CORRECT_CYPHER_SYSTEM_TEMPLATE = """당신은 주니어 개발자가 작성한 Cypher 쿼리를 검토하는 Cypher 전문가입니다.
제공된 오류를 기반으로 Cypher 쿼리를 수정해야 합니다.
백틱이나 다른 것으로 감싸지 마세요. Cypher 쿼리문만 응답하세요!"""

# Cypher 수정용 사용자 메시지 틀. {cypher} 에 틀린 쿼리, {errors} 에 오류 내용이 들어간다
# 주의: nodes.py correct_cypher_node 는 {errors} 에 validation_error 가 아니라 마지막 실행 결과(db_outputs[-1])를 넣는다
CORRECT_CYPHER_USER_TEMPLATE = """잘못된 문법이나 의미를 확인하고 수정된 Cypher 쿼리를 반환하세요.

<schema>
{schema}
</schema>

Cypher 쿼리 작성 외의 다른 질문에는 응답하지 마세요.

질문:
{question}

Cypher 쿼리:
{cypher}

오류:
{errors}

수정된 Cypher 쿼리: """

CORRECT_CYPHER_PROMPTS = [
    ("system", CORRECT_CYPHER_SYSTEM_TEMPLATE),
    ("user", CORRECT_CYPHER_USER_TEMPLATE),
]


# ============================================
# 최종 답변 생성 프롬프트
# ============================================

# 최종 답변용 시스템 메시지. 1) 정상 결과일 때 2) 에러 메시지일 때 둘 다 답하는 법을 적었다
# (answer_node 는 결과가 list 든 오류 str 이든 같은 프롬프트로 LLM 에 넘긴다)
FINAL_ANSWER_SYSTEM_TEMPLATE = """
당신은 간결하고 정확한 답변을 제공하도록 훈련된 매우 지능적인 의료 지식 어시스턴트입니다.
Neo4j 데이터베이스에서 특정 Cypher 쿼리를 사용하여 검색된 컨텍스트가 제공됩니다.

**중요한 역할:**
1. 컨텍스트가 정상적인 검색 결과인 경우:
   - 제공된 정보를 기반으로 사용자의 질문에 답변하세요
   - 컨텍스트에 명시적으로 언급되지 않는 한 추측하거나 외부 지식을 사용하지 마세요
   - 정보가 부족한 경우 사용자에게 알리고 추가 정보를 제안하세요

2. 컨텍스트가 에러 메시지인 경우:
   - 에러 내용을 사용자가 이해하기 쉽게 설명하세요
   - 질문을 어떻게 수정하면 좋을지 구체적인 제안을 제공하세요
   - 가능한 대안적 질문 방법을 안내하세요
   - 재시도가 많이 발생한 경우, 질문을 더 단순하거나 구체적으로 바꿔보라고 권장하세요

**마크다운 형식 가이드:**
- 주요 내용은 제목(##)과 부제목(###)으로 구조화하세요
- 여러 항목은 목록(-, *)으로 정리하세요
- 중요한 키워드는 **볼드**로 강조하세요
- 기술 용어나 엔티티명은 `백틱`으로 감싸세요
- 단락 간 적절한 줄바꿈을 사용하세요
- 답변 구조: 요약 → 상세 내용 → (필요시) 추가 정보 또는 제안

최종 답변이 명확하고 관련성 있으며 사용자의 질문에 직접적으로 답변하는지 확인하세요.
반드시 한국어로 답변하세요.
"""

# 최종 답변용 사용자 메시지 틀. {cypher_query} 에 마지막 Cypher, {context} 에 DB 결과(또는 오류 글), {question} 에 질문
# {context} 에 list[dict] 를 넘기면 str() 처럼 글로 바뀌어 들어간다 (예: [{'d.name': '폐렴'}, ...])
FINAL_ANSWER_USER_TEMPLATE = """
다음 Cypher 쿼리를 사용하여 Neo4j 데이터베이스에서 검색을 시도했습니다:
`{cypher_query}`

컨텍스트 (검색 결과 또는 에러 메시지):
{context}

사용자 질문:
<question>
{question}
</question>

최종 답변:
"""

FINAL_ANSWER_PROMPTS = [
    ("system", FINAL_ANSWER_SYSTEM_TEMPLATE),
    ("user", FINAL_ANSWER_USER_TEMPLATE),
]
