"""자막 교정 엔진

세 가지를 확인한다:
1. 외래어 표기 — 국립국어원 어문 규범(kornorms)이 명시적으로 "이 표기는
   틀렸다"고 확정하고 정답까지 준 경우 자동으로 교정한다.
   - 일반 용어(예: 초코렛 -> 초콜릿): 문맥과 무관하게 하나의 공식 정답만
     있으므로 조용히 자동 반영하고 플래그하지 않는다.
   - 고유명사(NNP: 인명·지명·작품 제목 등): kornorms 정답이 하나뿐이든
     여러 관례가 공존하든 상관없이 텍스트에는 절대 자동 반영하지 않고
     항상 확인 플래그로만 제안한다. 예를 들어 "스노우"가 인명(스노우 기자)
     이면 표기 규칙대로 "스노"가 맞지만, 같은 표기가 영화 제목("스노우맨")
     처럼 배급사가 정한 고유 표기일 수도 있다 — 텍스트만으로는 이 둘을
     구분할 방법이 없으므로, 고유명사 표기는 자동화보다 안전을 우선한다.
2. 맞춤법 — 일반명사/동사/형용사 같은 내용어를 형태소 단위로 뽑아 사전 기본형
   (표제어)으로 복원한 뒤 표준국어대사전에 있는지 확인한다. 없으면 플래그만
   하고 자동 수정하지 않는다 (어떤 게 맞는 표기인지 알 수 없기 때문).
   고유명사(NNP, 사람 이름 등)는 이 검사에서 제외한다 — 정상적인 이름도
   사전 표제어가 아닌 경우가 대부분이라, 포함시키면 멀쩡한 이름을 전부
   오탐지하게 된다.
3. 띄어쓰기 — 두 성격을 구분한다.
   - 조사·어미·접미사를 앞말에 붙이는 것(제1항/제41항)은 문맥과 무관하게
     항상 정답이 하나뿐이라 자동으로 정리한다(예: "오늘은날씨가좋네요" ->
     "오늘은 날씨가 좋네요"). 이건 "단어 경계가 어디인지 애매한" 문제가
     아니라 형태소 결합 규칙 자체가 예외 없이 고정되어 있어서다.
   - 내용어와 내용어가 바로 이어질 때(합성어처럼 하나로 합쳐질지 별개로
     남을지)는 '한번/한 번'처럼 의미에 따라 정답이 갈릴 수 있어, 사전으로
     확정되지 않는 한 절대 자동 적용하지 않고 플래그만 한다.
   - 예외적으로 보조 용언(제47항)은 "붙여 씀"이 허용되는 예외일 뿐 "띄어
     씀"이 원칙이므로, 붙여 쓴 형태를 항상 원칙(띄어쓰기) 형태로 자동
     통일한다 — 사용자가 붙여쓰기를 선호한다는 별도 지시가 없는 한.

주의: 이건 여전히 PRD 3단계 판단 엔진 중 1단계(사전/규범 근거)에 해당한다.
온라인가나다 아카이브 검색(2단계)은 아직 없다.

---

이 파일은 파사드다 — 공개 API를 재수출할 뿐 로직은 없다. 실제 내용은 아래 모듈에
있고, **의존 방향은 단방향**이다(위가 아래를 모른다):

    text_utils      순수 문자열·한글 음절 도구 (사전도 kiwi도 안 씀)
    kiwi_adapter    _kiwi 싱글턴, 형태소 태그 집합, 토큰 조회 도구
    options         문서 단위 설정값과 정규화 (구두점·제47항 기준·자막 표지·사투리 모드)
    markers         자막 편집 표지를 실제 텍스트에서 찾는 도구
    lexicon         사전 근거 단어 판정 술어 (원리 1 억제 로직이 모이는 자리)
    ── 규칙 모듈 ──
    spacing         띄어쓰기 자동 교정 (제41항·제42항·제47항)
    affix           접사 붙임 (하다/시키다/당하다/받다)
    punctuation     감탄사·호격 뒤 쉼표
    subtitle_rules  자막 모드 전용 부호 규칙
    loanwords       외래어 표기
    replacements    어휘 치환 (확정 오류·비표준어·차별적 표현·전 용어)
    spelling        맞춤법·순화어 검사 (플래그만)
    dialect         사투리 처리
    consistency     문서 전체 일관성 (제49항·제50항 혼용)
    ── 그 위 ──
    spacing_guards  띄어쓰기 제안에서 근거 없는 부분을 되돌리는 가드 + check_spacing
    pipeline        correct_entries 오케스트레이션 (규칙을 두지 않고 순서만 정한다)

새 규칙은 규칙 모듈에 넣고 `pipeline.py`에는 호출 순서만 추가한다. 새 공개 함수는
아래 `__all__`에도 넣어야 `from subtitle_corrector.engine import ...`로 보인다.
`_kiwi`는 `kiwi_adapter.py`에만 있어야 한다 — 자세한 이유는 그 파일 docstring 참고.
"""

from ..parsers import SubtitleEntry
from ..report import FlagItem
from .kiwi_adapter import detect_recurring_unknown_words, register_custom_words
from .options import (
    ELLIPSIS_STYLES,
    PunctuationStyle,
    QUOTE_STYLES,
    SPACING_MODES,
    SubtitleMarkers,
    normalize_dialect_mode,
    normalize_punctuation_style,
    normalize_spacing_mode,
    normalize_subtitle_markers,
    resolve_dialect_mode,
)
from .spacing import (
    _aux_verb_spacing,
    check_ambiguous_compound,
    check_compound_merge_candidate,
    correct_aux_verb_spacing,
    correct_compound_spacing,
    correct_particle_spacing,
)
from .affix import (
    check_action_noun_affix,
    check_adnominal_noun_verb_split,
    check_honorific_dependent_noun,
    check_intensive_prefix_cheo,
    correct_action_noun_affix,
    correct_adnominal_noun_verb_split,
    correct_honorific_dependent_noun_spacing,
    correct_intensive_prefix_cheo,
)
from .punctuation import (
    check_ambiguous_interjection_comma,
    check_joined_interjection_spacing,
    correct_interjection_vocative_comma,
)
from .subtitle_rules import (
    correct_subtitle_bracket_spacing,
    correct_subtitle_ellipsis,
    correct_subtitle_final_period,
    correct_subtitle_internal_period,
    correct_subtitle_quotes,
)
from .loanwords import check_colloquial_loanword, correct_loanwords
from .replacements import (
    check_ambiguous_particle,
    check_contracted_form,
    correct_always_wrong,
    correct_discriminatory_terms,
    correct_former_terms,
    correct_mot_hada_compound,
    correct_nonstandard_terms,
)
from .spelling import check_purified_terms, check_spelling
from .dialect import check_dialect
from .consistency import (
    check_aux_verb_consistency,
    check_street_name_spacing,
    check_term_spacing_consistency,
)
from .dependent_nouns import (
    check_hanpan_spacing,
    check_purpose_cha_spacing,
    correct_bun_spacing,
    correct_duration_cha_spacing,
)
from .spacing_guards import check_spacing
from .pipeline import apply_report_fixes, correct_entries

__all__ = [
    "SubtitleEntry",
    "FlagItem",
    "PunctuationStyle",
    "SubtitleMarkers",
    "ELLIPSIS_STYLES",
    "QUOTE_STYLES",
    "SPACING_MODES",
    "normalize_punctuation_style",
    "normalize_subtitle_markers",
    "normalize_spacing_mode",
    "normalize_dialect_mode",
    "resolve_dialect_mode",
    "register_custom_words",
    "detect_recurring_unknown_words",
    "correct_entries",
    "apply_report_fixes",
    "correct_loanwords",
    "correct_particle_spacing",
    "correct_compound_spacing",
    "correct_aux_verb_spacing",
    "_aux_verb_spacing",
    "check_action_noun_affix",
    "check_adnominal_noun_verb_split",
    "check_honorific_dependent_noun",
    "check_intensive_prefix_cheo",
    "correct_action_noun_affix",
    "correct_honorific_dependent_noun_spacing",
    "correct_intensive_prefix_cheo",
    "correct_adnominal_noun_verb_split",
    "check_ambiguous_interjection_comma",
    "check_joined_interjection_spacing",
    "correct_interjection_vocative_comma",
    "correct_always_wrong",
    "correct_nonstandard_terms",
    "correct_discriminatory_terms",
    "correct_former_terms",
    "correct_mot_hada_compound",
    "correct_subtitle_final_period",
    "correct_subtitle_internal_period",
    "correct_subtitle_bracket_spacing",
    "correct_subtitle_quotes",
    "correct_subtitle_ellipsis",
    "check_spelling",
    "check_purified_terms",
    "check_spacing",
    "check_ambiguous_compound",
    "check_compound_merge_candidate",
    "check_ambiguous_particle",
    "check_contracted_form",
    "check_colloquial_loanword",
    "check_dialect",
    "check_aux_verb_consistency",
    "check_street_name_spacing",
    "check_term_spacing_consistency",
    "correct_bun_spacing",
    "correct_duration_cha_spacing",
    "check_purpose_cha_spacing",
    "check_hanpan_spacing",
]
