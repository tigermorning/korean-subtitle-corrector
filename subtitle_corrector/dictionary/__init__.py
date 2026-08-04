"""국립국어원 표준국어대사전 / 우리말샘 / 온용어 / 한국어기초사전 / 지역어 오픈API 연동.

조회 함수들에 @lru_cache를 달아 같은 단어를 반복 조회하지 않게 한다(자막에는
"그리고", "저는" 같은 흔한 단어가 반복되므로 실제 API 호출 수가 크게 줄어든다).
이건 §5의 "국립국어원 API에 최대한 의존" 원칙과 충돌하지 않는다 — 매번 최신
데이터를 받아오는 대신 잠깐(서버 프로세스가 살아있는 동안) 같은 답을 재사용
하는 것뿐이고, 로컬에 사전을 통째로 복제해 규정 개정 추적 부담을 떠안는
것과는 다르다. 서버를 재시작하면 캐시도 비워진다.

이 파일은 파사드다. 실제 내용은 네 모듈에 있고, 경계는 "통신 / 판정 / 대안 / 사투리"다:

- `clients.py` — 요청을 보내고 응답을 그대로 돌려준다. 판정하지 않는다.
- `headwords.py` — "이 표기가 사전에 있는가" (있다/없다로 끝나는 조회).
- `terms.py` — "이 표기를 무엇으로 바꿔야 하는가" (사전이 대안까지 확정해 준 경우만).
- `dialect.py` — 사투리 표지 사전과 지역 판정.

통신과 판정을 갈라 둔 이유: `docs/DESIGN_PRINCIPLES.md` 원리 4(조회 로직 버그)는
"가진 데이터를 잘못된 판정으로 버리는" 부류라 거의 전부 판정 쪽에서 난다.
"""

from .clients import (
    failed_lookups,
    lookup_stats,
    note_lookup_attempt,
    reset_failed_lookups,
    search_dialect,
    search_kornorms,
    search_kornorms_partial,
    search_krdict,
    search_onyongeo,
    search_opendict,
    search_stdict,
)
from .headwords import (
    appears_in_standard_headword,
    compound_status,
    definition_markers,
    is_contemporary_general_word,
    registered_ending,
    usage_examples,
    word_exists,
)
from .terms import (
    former_term_field,
    former_term_lookup,
    get_purified_terms,
    loanword_fix,
    lookup_by_source,
    standard_term_replacement,
)
from .dialect import (
    DIALECT_MARKERS,
    DIALECT_TO_STANDARD,
    STANDARD_TO_DIALECT,
    convert_dialect,
    detect_dialect_ratio,
    detect_speaker_dialect,
)

__all__ = [
    "search_stdict",
    "search_opendict",
    "search_kornorms",
    "search_kornorms_partial",
    "search_onyongeo",
    "search_krdict",
    "failed_lookups",
    "lookup_stats",
    "note_lookup_attempt",
    "reset_failed_lookups",
    "search_dialect",
    "word_exists",
    "compound_status",
    "appears_in_standard_headword",
    "definition_markers",
    "is_contemporary_general_word",
    "registered_ending",
    "usage_examples",
    "standard_term_replacement",
    "former_term_field",
    "former_term_lookup",
    "loanword_fix",
    "lookup_by_source",
    "get_purified_terms",
    "DIALECT_MARKERS",
    "DIALECT_TO_STANDARD",
    "STANDARD_TO_DIALECT",
    "detect_dialect_ratio",
    "detect_speaker_dialect",
    "convert_dialect",
]
