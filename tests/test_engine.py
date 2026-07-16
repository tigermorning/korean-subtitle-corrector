"""엔진 검증표 — PRD.md에 기록된 실사용 버그 수정 사례를 실행 가능한
회귀 테스트로 옮긴 것.

이 프로젝트의 핵심 원칙(PRD.md §5 "실시간 사전 데이터가 항상 우선",
"검증표 먼저, 코드는 나중")에 따라, 여기 있는 기대값은 전부 실제
표준국어대사전/우리말샘 API를 직접 조회해 확인한 결과다. 그래서 이
테스트는 네트워크 접근(.env의 STDICT_API_KEY/OPENDICT_API_KEY 필요)이
필요하고, 정적으로 미리 캡처해 둔 응답을 mock하지 않는다 — 국립국어원이
사전을 개정하면 이 테스트도 그 변화를 그대로 반영해야 하기 때문이다.

테스트가 실패하면: 코드 회귀인지, 아니면 사전 자체가 개정되어 기대값이
바뀐 것인지 먼저 확인한 뒤(§5 "규정 개정에 따른 유지보수" 참고), 실제
사전 상태에 맞게 코드와 테스트를 함께 고친다 — 테스트 숫자만 바꿔서
통과시키지 않는다.
"""

from subtitle_corrector.engine import (
    check_spacing,
    correct_always_wrong,
    correct_aux_verb_spacing,
    correct_compound_spacing,
    correct_discriminatory_terms,
    correct_loanwords,
    correct_particle_spacing,
)


class TestAuxVerbSpacingPattern1:
    """본용언-아/어+보조용언(제47항). 사전에 이미 붙여 쓴 한 단어로 등재된
    경우(여쭤보다 등)는 원칙(띄어쓰기)보다 사전 등재가 우선이라 건드리지
    않는다."""

    def test_yeojjuboda_already_registered_untouched(self):
        assert correct_aux_verb_spacing("여쭤보다") == ("여쭤보다", [])


class TestAuxVerbSpacingPattern2:
    """관형사형+의존명사(만/척/법/듯/뻔/성/직/체/양)+하다/싶다.

    (a) 전체가 통째로 별개의 표제어로 등재된 경우(그럴듯하다, 볼만하다)는
        그대로 두고, (b)/(c) 일반적인 경우는 관형사형-의존명사 사이만
        띄우고 의존명사-하다 사이는 사전에 등재된 보조 용언이라 붙여 쓴다.
    """

    def test_halmanhada_splits_only_leading_gap(self):
        assert correct_aux_verb_spacing("할만하다") == ("할 만하다", ["할만하다 -> 할 만하다"])

    def test_aneuncheokhada_splits_only_leading_gap(self):
        assert correct_aux_verb_spacing("아는척하다") == (
            "아는 척하다",
            ["아는척하다 -> 아는 척하다"],
        )

    def test_geureolbeophada_splits_only_leading_gap(self):
        assert correct_aux_verb_spacing("그럴법하다") == (
            "그럴 법하다",
            ["그럴법하다 -> 그럴 법하다"],
        )

    def test_nalppeonhaetda_splits_only_leading_gap(self):
        assert correct_aux_verb_spacing("날뻔했다") == ("날 뻔했다", ["날뻔했다 -> 날 뻔했다"])

    def test_geureoldeutada_whole_word_registered_untouched(self):
        """'그럴-듯하다'가 그 자체로 형용사 표제어라, 억지로 쪼개면 안 된다."""
        assert correct_aux_verb_spacing("그럴듯하다") == ("그럴듯하다", [])

    def test_bolmanhada_whole_word_registered_untouched(self):
        """'볼만-하다'도 별도로 등재된 표제어(동사)라 그대로 둔다."""
        assert correct_aux_verb_spacing("볼만하다") == ("볼만하다", [])


class TestApplyReplacementsTokenBoundary:
    """_apply_replacements()가 kiwi 토큰 경계와 정확히 일치하는 위치만
    치환하는지 확인 — '재판장님'(재판장+님) 안에 우연히 들어있는 '장님'을
    '시각장애인'으로 잘못 바꾸는 사고를 막기 위한 회귀 테스트."""

    def test_ganjil_discriminatory_term_replaced(self):
        assert correct_discriminatory_terms("그는 간질이 있다") == (
            "그는 뇌전증이 있다",
            ["간질 -> 뇌전증"],
        )

    def test_ganjilida_unrelated_verb_untouched(self):
        """'간질이다'(간지럽히다)는 '간질'(뇌전증)과 전혀 다른 단어라 건드리면 안 된다."""
        assert correct_discriminatory_terms("그는 몸을 간질이다가 웃었다") == (
            "그는 몸을 간질이다가 웃었다",
            [],
        )

    def test_ganjilganjil_onomatopoeia_untouched(self):
        assert correct_discriminatory_terms("간질간질한 느낌이었다") == (
            "간질간질한 느낌이었다",
            [],
        )

    def test_jaepanjangnim_false_positive_fixed(self):
        """'재판장님'(재판장+님) 안의 '장님'을 잘못 치환하던 실사용 버그."""
        assert correct_discriminatory_terms("재판장님 안녕하세요") == (
            "재판장님 안녕하세요",
            [],
        )

    def test_jangnim_real_case_still_fires(self):
        assert correct_discriminatory_terms("장님이 걸어간다") == (
            "시각장애인이 걸어간다",
            ["장님 -> 시각장애인"],
        )


class TestAlwaysWrong:
    def test_geurigo_naseo(self):
        assert correct_always_wrong("그리고 나서 밥을 먹었다") == (
            "그러고 나서 밥을 먹었다",
            ["그리고 나서 -> 그러고 나서"],
        )

    def test_geurigoneun(self):
        assert correct_always_wrong("그리고는 집에 갔다") == (
            "그러고는 집에 갔다",
            ["그리고는 -> 그러고는"],
        )


class TestParticleSpacing:
    """제41항(조사)/제1항(어미): 문맥과 무관하게 정답이 하나뿐인 지점만
    자동으로 정리한다."""

    def test_josa_spacing_normalized(self):
        assert correct_particle_spacing("오늘은날씨가좋네요") == (
            "오늘은 날씨가 좋네요",
            ["오늘은날씨가좋네요 -> 오늘은 날씨가 좋네요"],
        )

    def test_subtitle_linebreak_preserved(self):
        """두 줄 자막의 줄바꿈을 공백으로 뭉개버리던 실사용 버그 회귀 테스트."""
        assert correct_particle_spacing("안녕\n하세요") == ("안녕\n하세요", [])

    def test_trailing_yo_particle_untouched(self):
        """존대 보조사 '요'를 kiwi가 관형사(MM)로 잘못 태깅해도 그대로 둔다."""
        assert correct_particle_spacing("때만요") == ("때만요", [])


class TestCompoundSpacing:
    """사전에 하나의 합성어(하이픈 표기)로 등재된 경우만 자동으로 붙인다."""

    def test_notcheon_cafe(self):
        assert correct_compound_spacing("노천 카페에 갔다") == (
            "노천카페에 갔다",
            ["노천 카페 -> 노천카페"],
        )

    def test_geu_ttae(self):
        assert correct_compound_spacing("그 때 이야기를 했다") == (
            "그때 이야기를 했다",
            ["그 때 -> 그때"],
        )

    def test_sseun_mat(self):
        assert correct_compound_spacing("쓴 맛이 난다") == ("쓴맛이 난다", ["쓴 맛 -> 쓴맛"])


class TestLoanwordFix:
    def test_chocolate_misspelling_fixed(self):
        corrected, applied, needs_review, proper_noun = correct_loanwords("나는 초코렛을 좋아한다")
        assert corrected == "나는 초콜릿을 좋아한다"
        assert applied == ["초코렛 -> 초콜릿"]
        assert needs_review == []
        assert proper_noun == []

    def test_registered_native_word_not_treated_as_loanword(self):
        """'집'(house)처럼 이미 정식 등재된 고유어는 kornorms의 무관한
        외래어 항목과 우연히 겹쳐도 절대 건드리면 안 된다 (실사용 버그)."""
        assert correct_loanwords("나는 집에 간다") == ("나는 집에 간다", [], [], [])


class TestCheckSpacingJoiningProtection:
    """kiwi.space()가 원문에 있던 공백을 근거 없이 지워버리는(단어를 붙여
    버리는) 것을 막는 _protect_unfounded_joining() 회귀 테스트.

    '-려고 하다'(의도를 나타내는 본동사 구성)는 제47항 보조 용언 붙임
    허용 대상이 전혀 아니라 항상 띄어 써야 하는데, kiwi가 통계적으로
    붙여 쓴 형태("그만하려고합니다")를 제안해 실사용 중 발견됨."""

    def test_haryeogo_hada_not_joined(self):
        assert check_spacing(0, "그만하려고 합니다") is None

    def test_haryeogo_hada_not_joined_with_other_verbs(self):
        assert check_spacing(0, "나는 가려고 합니다") is None
        assert check_spacing(0, "먹으려고 해요") is None
