"""
[3단계: 주석만] 법령 그래프(law2kg)용 GraphRAG 도구 에이전트를 처음부터 만든다.

막힌 곳 메모:
  -
"""

# 1. 도구 목록을 설계한다. (이름, 언제 쓰나, 입력, 출력)
#    - search_interpretations(question): 해석례 벡터 검색 + 주변(vectorcypher 의 retrieval_query 재사용)
#    - get_article(law_name, article_number): 특정 조문 본문과 항/호 (고정 Cypher)
#    - cited_by(law_name, article_number): 이 조문을 인용한 해석례 목록 (고정 Cypher)
#    - free_cypher(question): 위로 안 되는 질문만 (읽기 전용)

# 2. 고정 Cypher 도구를 먼저 만든다. LLM 은 인자만 채운다. 왜 이쪽이 더 안전하고 정확한가?

# 3. 공용 자원(드라이버, 임베더)은 한 번만 만든다. (원본 tools.py 의 전역 초기화 패턴)

# 4. 도구를 에이전트 없이 하나씩 테스트하는 __main__ 을 만든다.

# 5. 시스템 프롬프트: 법률 도메인 규칙(조문 번호 인용, 결론과 이유 구분, 안내 문구)

# 6. 질문 10개로 돌려 도구 호출 순서를 기록하고, 이상한 호출(불필요한 free_cypher 등)을 docstring 수정으로 줄인다.

# ---------- 끝난 뒤 스스로 점검 ----------
# [ ] 고정 쿼리 도구와 자유 Cypher 도구의 비율을 어떻게 정할지 기준이 있는가?
# [ ] 도구가 돌려주는 텍스트의 길이 상한을 정했는가?
