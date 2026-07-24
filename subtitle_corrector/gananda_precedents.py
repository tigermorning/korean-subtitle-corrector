"""온라인가나다(국립국어원 온라인 상담) 질의응답으로 확인한 판례 모음.

표준국어대사전·우리말샘 API에는 명확한 답이 없는 경우(신조어, 개별 활용형,
문형 자체가 표제어로 등재되지 않는 경우)가 있다. 온라인가나다는 국립국어원
연구사가 실제 질문에 직접 답한 상담 게시판이라 이런 빈틈을 메울 수 있는
권위 있는 근거이지만, 공식 검색/크롤링 API가 없어 실시간 조회가 불가능하다
(PRD.md §8 "온라인가나다 연동(2단계)" 참고).

그래서 실시간 조회 대신, 실제로 애매한 사례를 만날 때마다(수동으로, 또는
예약 실행되는 배치 조사로) 하나씩 검증해서 이 파일에 축적해 둔다. 즉 이
파일은 "온라인가나다 전체를 미리 다 외워두는 것"이 아니라, 실제로 쓰일
가능성이 높은 사례부터 골라 계속 채워나가는 성장형 참고 자료다.

각 항목:
- expression: 판단 대상이 되는 정확한 표기(붙여 쓴 후보 형태 등 — dictionary.py의
  word_exists()에 실제로 들어오는 query 문자열과 정확히 일치해야 매칭된다)
- correct: 이 표기(expression)가 맞으면 True, 틀리면(다르게 써야 하면) False
- source: 근거가 된 온라인가나다 질문 요지 + 국립국어원 답변 요지(직접 인용 아님, 요약)
- verified: 확인한 날짜(YYYY-MM-DD)
"""

PRECEDENTS: list[dict] = [
    # 사례를 만날 때마다 아래 형식으로 추가한다. 예:
    # {
    #     "expression": "예시표현",
    #     "correct": True,
    #     "source": "온라인가나다 질문 요지 -> 답변 요지",
    #     "verified": "2026-07-17",
    # },
]


def check_precedent(expression: str) -> bool | None:
    """expression에 대한 온라인가나다 판례가 있으면 True/False, 없으면 None."""
    for entry in PRECEDENTS:
        if entry["expression"] == expression:
            return entry["correct"]
    return None
