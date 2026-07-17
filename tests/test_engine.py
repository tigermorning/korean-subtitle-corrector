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
    check_confusable_words,
    check_spacing,
    check_spelling,
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

    def test_irregular_verb_stem_still_detected(self):
        """kiwi가 불규칙 활용 어간(잇다의 '잇')을 'VV'가 아니라 'VV-I'로
        태깅해, 정확히 일치("==")로만 비교하던 코드가 이런 보조용언 구성을
        아예 놓치던 버그. 사전에 없는 '이어가다'는 원칙대로 띄어 써야 한다."""
        text = "안트베르펜 공격을 이어가도록"
        assert correct_aux_verb_spacing(text) == (
            "안트베르펜 공격을 이어 가도록",
            [f"{text} -> 안트베르펜 공격을 이어 가도록"],
        )


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

    def test_jalhada_contracted_form_not_split(self):
        """'잘해야'(잘하다+아야)를 '잘 해야'로 잘못 갈라놓던 버그 —
        '해'가 '하'+'어'의 축약형이라 표면형 재구성 비교가 실패하던 것을
        위치 기반 간격 확인으로 수정."""
        assert check_spacing(0, "힘 조절을 잘해야 합니다") is None


class TestCheckSpacingTermCompoundProtection:
    """전문 용어·고유명사·편제 번호 성격의 복합 표현(한글 맞춤법 제49항/
    제50항이 붙여쓰기를 허용하는 대상)을 kiwi가 사전에 없다는 이유만으로
    갈라놓지 않도록 보호하는 회귀 테스트. 실제 다큐멘터리 자막(Hitler's
    Last Stand)을 감수하다가 무더기로 발견됨."""

    def test_military_unit_designation_not_split(self):
        assert check_spacing(0, "제505공수보병연대원들이 엄폐 중입니다") is None
        assert check_spacing(0, "제82공수사단장") is None
        assert check_spacing(0, "제505공수보병연대 2대대") is None

    def test_plain_occupation_compound_not_split(self):
        assert check_spacing(0, "폭파병 제리 위드 하사가 신속하게 움직입니다") is None

    def test_letter_designation_not_split(self):
        assert check_spacing(0, "E중대") is None

    def test_number_within_man_unit_not_split(self):
        """한글 맞춤법 제44항: '만' 단위 이내의 숫자는 붙여 쓴다."""
        assert check_spacing(0, "아르덴 숲에 독일군 20만 명") is None


class TestAndoedaContextDisambiguation:
    """'안되다'(형용사, 상황이 좋지 않다)와 '안 되다'(부정 부사+동사,
    허용·가능하지 않다)는 사전 등재 여부만으로 구분이 안 된다. '-면'/
    '-어서는' 같은 조건·전제 어미 뒤에 오는 경우만 확실한 금지 구성으로
    보고 항상 띄어 쓰게 하고, 그 외(예: '공부가 안된다')는 기존처럼
    사전 등재 판단(항상 붙임)을 따른다."""

    def test_conditional_marker_forces_split(self):
        assert check_spacing(0, "그러면 안됩니다").suggested_fix == "그러면 안 됩니다"
        assert (
            check_spacing(0, "여기서 담배를 피우면 안됩니다").suggested_fix
            == "여기서 담배를 피우면 안 됩니다"
        )
        assert check_spacing(0, "그렇게 해서는 안된다").suggested_fix == "그렇게 해서는 안 된다"

    def test_no_marker_keeps_idiom_default(self):
        assert check_spacing(0, "공부가 안된다") is None
        assert check_spacing(0, "사업이 안돼") is None

    def test_already_correct_forms_unflagged(self):
        assert check_spacing(0, "그러면 안 됩니다") is None
        assert check_spacing(0, "공부가 안 된다") is None


class TestCheckSpacingCompoundVerbStemLookback:
    """_protect_unfounded_respacing()의 사전 등재 확인이 연결어미(EC) 하나만
    보고 후보를 재구성하다가, 그 앞의 어간까지 봐야 하는 3형태소 복합동사
    ('기다'+'어'+'다니다'='기어다니다', '데리'+'어다'+'주다'='데려다주다')를
    놓치던 버그. 어간이 EC와 받침/음절을 공유해 위치가 겹치는 경우까지
    포함해서 잡아야 한다."""

    def test_gieodanida_not_split(self):
        assert check_spacing(0, "벌레가 기어다닌다") is None

    def test_ddeonabonaeda_not_split(self):
        assert check_spacing(0, "엄마를 떠나보냈다") is None

    def test_deryeodajuda_not_split_even_with_overlap(self):
        assert check_spacing(0, "집에 데려다줬다") is None


class TestParticleSpacingPrefixParticleHomograph:
    """"과"(조사 "~와/과" vs 한자어 접두사 "과-[過]": 과증식/과체중 등)처럼
    조사와 형태가 같은 접두사가 있을 때, 뒤 단어와 합쳐 사전에 등재된
    단어가 되면 조사로 보고 앞말에 붙이지 않는다."""

    def test_gwa_prefix_not_attached_to_preceding_noun(self):
        assert correct_particle_spacing("좌심실 과증식 상태") == ("좌심실 과증식 상태", [])

    def test_normal_gwa_particle_still_works(self):
        assert correct_particle_spacing("나와 과일") == ("나와 과일", [])


class TestCheckSpacingSentenceEndingProtection:
    """종결어미(EF)는 항상 앞말에 붙는다 — kiwi가 축약형("잖아요"="지"+"않"+
    "아요")을 tokenize()/space()에서 서로 다르게 분석해 "말했잖아 요",
    "같잖 아요"처럼 잘못 갈라놓던 버그."""

    def test_malhaessjanayo_not_split(self):
        assert check_spacing(0, "말했잖아요") is None

    def test_geunyangyo_not_split(self):
        assert check_spacing(0, "그냥요") is None

    def test_saramdeuleunyo_not_split(self):
        assert check_spacing(0, "사람들은요") is None

    def test_gatjanayo_not_split(self):
        assert check_spacing(0, "모범생 같잖아요") is None


class TestCheckSpacingNumberSymbol:
    def test_percent_not_split(self):
        assert check_spacing(0, "80% 완료됐다") is None


class TestActionNounPlusBatdaSuffix:
    """번역가 교육자료(동사/접사 구분법): 동작성 명사(호출, 사랑, 상처 등)
    뒤의 "받다"는 접사로 항상 붙여 쓰지만, 구체적 사물 명사(상, 만점 등)
    뒤의 "받다"는 독립된 동사로 띄어 쓴다. "동작성 명사+받다" 조합은
    개별 표제어로 사전에 등재되어 있지 않은 경우가 많아(예: 호출받다,
    사랑받다), "명사+하다"가 사전에 등재되어 있는지로 동작성을 판단한다."""

    def test_action_noun_plus_batda_stays_joined(self):
        assert check_spacing(0, "그는 호출받았다") is None
        assert check_spacing(0, "그는 사랑받는다") is None
        assert check_spacing(0, "상처받았다") is None

    def test_concrete_object_noun_plus_batda_unaffected(self):
        assert check_spacing(0, "상을 받았다") is None
        assert check_spacing(0, "만점을 받았다") is None


class TestCompoundSpacingDurationMarkerException:
    """숫자+시간단위(년/월/일 등) 뒤에 오는 "전"은 "~하기 전"이 아니라
    "며칠 전"의 뜻이라, 뒤에 오는 명사와 절대 하나의 단어가 될 수 없다.
    "전일"(全日/前日)이 별개로 사전에 등재되어 있어 우연히 충돌하는
    사고("7년 전 일" -> "7년 전일")를 막는다."""

    def test_duration_marker_before_jeon_not_joined(self):
        assert correct_compound_spacing("7년 전 일이에요") == ("7년 전 일이에요", [])
        assert correct_compound_spacing("3일 전 사건") == ("3일 전 사건", [])


class TestCompoundSpacingMMAllowlist:
    """관형사(그/이/저/두/세 등)+명사 조합은 사전이 '합성어'로 확인해 줘도
    원문 의도와 무관한 우연의 동형이의어일 위험이 크다("두 강"이 "두강"
    [杜康=술의 별칭]과 충돌하는 식) — 검증된 소수의 고정 표현만 자동으로
    붙이고 나머지는 사전 등재 여부와 무관하게 그대로 둔다."""

    def test_numeral_determiner_plus_noun_not_joined(self):
        assert correct_compound_spacing("두 강을 건넜다") == ("두 강을 건넜다", [])

    def test_demonstrative_plus_unrelated_homograph_not_joined(self):
        assert correct_compound_spacing("그 다리를 건넜다") == ("그 다리를 건넜다", [])

    def test_allowlisted_demonstrative_compound_still_joined(self):
        assert correct_compound_spacing("그 때 이야기를 했다") == (
            "그때 이야기를 했다",
            ["그 때 -> 그때"],
        )


class TestCheckSpellingProductiveDemonymCompound:
    """국가/지역명 + 군(軍)/인(人)/어(語) 같은 생산적 파생어는 그 정확한
    조합이 사전에 개별 등재되어 있지 않아도(미군/독일군은 있지만 영국군은
    없는 것처럼 사전 등재 자체가 들쭉날쭉함) 신조어·오탈자로 플래그하지
    않는다."""

    def test_country_plus_gun_not_flagged(self):
        assert check_spelling(0, "미군과 영국군") is None


class TestMachidaMajidaObjectDisambiguation:
    """'마치다'(끝내다)/'맞히다'(맞게 하다)는 제57항 공식 혼동 쌍이지만,
    목적어(를/을 앞의 명사)만 봐도 의미가 명확히 갈리는 경우가 대부분이라
    그런 경우엔 예외적으로 플래그를 생략한다."""

    def test_activity_object_with_machida_not_flagged(self):
        assert check_confusable_words(0, "아르덴 전투 지역에 전개를 마칩니다") is None
        assert check_confusable_words(0, "수업을 마쳤다") is None

    def test_answer_object_with_majida_not_flagged(self):
        assert check_confusable_words(0, "정답을 맞혔다") is None

    def test_mismatched_object_still_flagged(self):
        """목적어가 반대쪽 부류인데 다른 동사가 쓰이면(실제 오류 가능성이
        높은 경우) 여전히 플래그한다 — 자동 교정은 하지 않는다."""
        assert check_confusable_words(0, "정답을 마쳤다") is not None
        assert check_confusable_words(0, "수업을 맞혔다") is not None

    def test_unrelated_pair_unaffected(self):
        assert check_confusable_words(0, "고개를 반듯이 들어라") is not None
