"""접사 붙임 규칙(하다/시키다/당하다/받다) 및 관형어+명사 분리.
"""

from ..dictionary import only_sino_korean_headword, sino_korean_origin, word_exists
from ..report import FlagItem
from .text_utils import _josa, _localized_change
from .kiwi_adapter import _kiwi
from .lexicon import _is_action_noun

# 동작성 신호로 쓰는 word_exists(N+"하다")가 동형이의어로 오탐지하는 명사들.
# '상'(賞)은 '상하다'(음식이 상하다)·'상당하다'·'상되다'가 사전에 있어 동작성으로
# 오판되지만 실제로는 동작성이 없다('상 받다'는 띄움). '돈'·'벌'도 마찬가지.
# '사진'은 다른 이유다 — '사진하다' 표제어 3개(仕進하다/査陳하다/寫眞하다)가 전부
# 현대에 안 쓰이는 옛 뜻(관직 출근·옛 토지조사·"그림 그리다")뿐이라 동작성 신호
# 자체가 무효다(2026-08-28, docs/BACKLOG.md 최우선 항목). is_contemporary_general_word()가
# 이걸 못 잡는 이유는 우리말샘이 세 뜻 다 cat/type을 안 채워서다.
_AFFIX_ACTION_EXCLUDE = {"상", "돈", "벌", "사진"}


def is_honorific_drida_affix(noun_form: str) -> bool:
    """'명사+드리다'의 '드리다'가 접미사 자리인지 — 붙여 쓴 표기가 맞는지.

    근거: 표준국어대사전·우리말샘 **둘 다** 접미사 '-드리다'를 표제어로 싣는다
    ("((몇몇 명사 뒤에 붙어)) '공손한 행위'의 뜻을 더하고 동사를 만드는 접미사").
    피동 접미사 '-받다'와 같은 구조이므로, '어떤 명사 뒤인가'도 같은 신호로
    가른다 — 동작성 명사 뒤면 접미사라 붙여 쓰고('부탁드리다'), 구체적 사물
    명사 뒤면 '주다'의 높임말인 본동사라 띄어 쓴다('선물을 드리다').

    **파생어의 사전 등재 여부로는 가를 수 없다.** 접미사 결합은 규칙적으로
    만들 수 있어 사전이 그 파생어를 전부 싣지 않는다 — `말씀드리다`·
    `사과드리다`·`도와드리다`는 등재돼 있지만 `부탁드리다`·`감사드리다`·
    `인사드리다`·`축하드리다`·`연락드리다`는 미등재다(2026-08-05 조회).
    '-받다'에서 `호출받다`·`사랑받다`가 미등재인 것과 같은 사정이다.

    동작성 신호가 동형이의어로 오탐지하는 명사(`_AFFIX_ACTION_EXCLUDE`)는 뺀다 —
    '상'·'돈'은 이 자리에서 바로 사물 명사 쪽('상 드리다'·'돈 드리다')이다.
    """
    return noun_form not in _AFFIX_ACTION_EXCLUDE and _is_action_noun(noun_form)


# 수량 표현을 이루는 태그. 숫자(SN)·단위 약물(SL, 'cc')·한자 수(SH)·수사(NR)·
# 의존명사(NNB, '개'·'년'·'번')가 앞에 오면 그 뒤 명사는 명사구의 머리다.
_QUANTITY_LEAD_TAGS = {"SN", "SL", "SH", "NR", "NNB"}


# 동작성 명사 뒤에 붙는 접사 중 **자동으로 붙이지 않고 확인 플래그로 남기는** 것들.
#
# 왜 내렸나(2026-08-05 사용자 보고 `일단 술 시켜요` -> `일단 술시켜요`): 이 셋의 붙임
# 근거는 **다른 낱말**이 사전에 있다는 것이다 — `N시키다`가 아니라 `N하다`가 표제어인지
# 를 본다. 그 간접성이 동형이의어 하나에 뚫린다: `술하다`는 한자어 述하다(서술하다)라
# 표제어이고, 그 때문에 사물 명사 `술`이 동작성으로 판정됐다. `밥하다`(밥을 짓다)도
# 같은 방식으로 `밥시키다`를 만든다.
#
# 제외 목록(`_AFFIX_ACTION_EXCLUDE`)으로 막던 부류인데 목록에는 끝이 없다 — 상·돈·벌
# 다음이 술·밥이었을 뿐이다. 근거를 강화하는 쪽은 막혔다: 붙임형 등재를 요구하면
# 정당한 `사랑받다`·`청소시키다`·`교육시키다`가 전부 미등재라 규칙 자체가 죽는다
# (실측 18건 중 등재된 것은 `무시당하다` 하나뿐).
#
# 그래서 **자동 교정에서 내리고 제안으로 남긴다.** 붙여야 할 것을 못 붙이는 대가는
# §26·§27과 같은 부류이고, 붙이지 말아야 할 것을 붙이는 것보다 낫다. '하다'는 그대로
# 자동이다 — 그쪽은 붙임형(`청소하다`) 자체가 표제어라 직접 근거다.
_SUGGEST_ONLY_AFFIX_LEMMAS = {"시키다", "당하다", "받다"}


def correct_action_noun_affix(text: str) -> tuple[str, list[str]]:
    """동작성 명사 뒤의 접사(하다/시키다/당하다/받다/되다)가 띄어 써 있으면 붙인다
    (예: '선물 받았어'→'선물받았어', '배달 시켜서'→'배달시켜서', '무시 당하다'→
    '무시당하다', '음악 하는'→'음악하는'). 동작성 없는 명사 뒤에서는 이들이 동사라
    띄어 쓴다('상 받다', '짜장면 시키다', '팀장 되다'는 그대로).

    동작성 판정 = _is_action_noun(word_exists(N+'하다')). 다만 이 신호는 '상하다'
    (부패) 같은 동형이의어로 오탐지하므로 _AFFIX_ACTION_EXCLUDE(상/돈/벌)를 먼저
    배제한다. '되다'는 동작성 heuristic을 쓰지 않고 붙임형(N되다)이 사전 표제어일
    때만 붙인다('해체되다' O / '도움 되다'·'팀장 되다' X). 접사가 명사 바로 뒤에
    공백 하나로 떨어져 있을 때만 붙인다.

    반환값: (교정된 텍스트, 적용 로그)."""
    tokens = _kiwi.tokenize(text)
    cuts = []  # (공백 시작, 공백 끝) — 제거해서 붙인다
    for i in range(1, len(tokens)):
        noun, affix = tokens[i - 1], tokens[i]
        if noun.tag not in ("NNG", "NNP"):
            continue
        if text[noun.start + noun.len : affix.start] != " ":
            continue  # 명사와 접사가 공백 하나로 떨어져 있을 때만
        # 관형사(MM)·관형형(ETM)이 이 명사를 꾸미면 '하다'는 명사와 띄어야 한다
        # (correct_adnominal_noun_verb_split과 같은 원칙: '이런 생각 하다'). 접사로
        # 붙이면 그 분리를 되돌리게 되므로 건너뛴다.
        if i >= 2:
            prev = tokens[i - 2]
            # 관형격 조사(JKG)도 관형어를 만든다 — '내'는 kiwi가 '나'(NP)+'의'(JKG)로
            # 읽으므로 MM/ETM 조건에 걸리지 않았다. 2026-08-04 사용자 제공 자막 7강
            # 147번에서 '내 탓 하지 마'가 '내 탓하지 마'로 붙었다.
            if prev.tag in ("MM", "ETM", "JKG") and text[prev.start + prev.len : noun.start] in (" ", ""):
                continue
            # 앞말이 **명사**여도 붙이지 않는다. 명사가 명사를 꾸며 명사구를 이루면
            # ('나물 타령', '수학 공부', '순간 이동') 그 뒤의 '하다'는 접사가 아니라
            # 동사이므로 띄어 쓴 표기가 맞다 — 온라인가나다 `qna_seq=320467`(2025-09-11):
            # "'순간 이동을 하다'처럼 구 구성이면 띄어 씁니다". 사용자가 이미 맞게 띄어
            # 놓은 '나물 타령 하셨어'를 '나물 타령하셨어'로 붙여 버리던 과교정이었다
            # (2026-08-03 사용자 보고).
            #
            # 대가: 앞 명사가 관형어가 아닌 경우(예: '어제 청소 했다'의 '어제'는 시간
            # 부사어)의 정당한 붙임을 놓친다. 표면만으로는 관형어인지 부사어인지 가릴
            # 수 없으므로, **맞는 표기를 깨뜨리지 않는 쪽**을 택했다.
            if prev.tag in ("NNG", "NNP") and text[prev.start + prev.len : noun.start] == " ":
                continue
            # 수량·단위·의존명사 뒤도 같은 부류다. `250cc 정도 됩니다`가 `정도됩니다`로
            # 붙었는데, 붙임 근거는 `정도되다`가 표제어라는 것뿐이었다 — 그 표제어는
            # 定都되다(도읍이 정해지다)로 원문의 程度와 무관한 동형이의어다
            # (`docs/BACKLOG.md` 27번, 2026-08-04 규칙 전수 점검에서 원인 규명).
            #
            # 동형이의어 수로는 가를 수 없다는 것을 먼저 확인했다: 자동 붙임을 막아야
            # 하는 '정도'(원어 10종)와 막으면 안 되는 '청소'(6종)·'공부'(9종)·'전화'(10종)가
            # 같은 신호로 묶인다. 대신 **앞말이 수량 표현이면 그 명사는 수량을 받는
            # 자립 명사**('250cc 정도', '3년 정도', '세 개 정도')이고 뒤의 되다/하다는
            # 별개 서술어다 — 위 명사구 가드와 같은 근거를 태그만 넓혀 적용한다.
            #
            # 대가도 같다: '두 번 참고 하세요'처럼 수량이 부사어인 정당한 붙임을 놓친다.
            if prev.tag in _QUANTITY_LEAD_TAGS and text[prev.start + prev.len : noun.start] == " ":
                continue
        n = noun.form
        if n in _AFFIX_ACTION_EXCLUDE:
            continue
        affix_is_hada = affix.lemma == "하다" or (affix.tag == "XSV" and affix.form == "하")
        if affix.lemma == "되다":
            attach = word_exists(n + "되다")
        elif affix.lemma in _SUGGEST_ONLY_AFFIX_LEMMAS:
            attach = False  # 간접 근거 — check_action_noun_affix()가 제안만 남긴다
        elif affix_is_hada:
            attach = _is_action_noun(n)
        else:
            attach = False
        if attach:
            cuts.append((noun.start + noun.len, affix.start))
    if not cuts:
        return text, []
    corrected = text
    for gap_start, gap_end in sorted(cuts, reverse=True):
        corrected = corrected[:gap_start] + corrected[gap_end:]
    return corrected, [_localized_change(text, corrected)]


# 명사를 꾸미는 앞말. 관형사(MM)·관형형 어미(ETM)에 **관형격 조사(JKG)**를 더했다 —
# '마음의 준비해'·'내 탓하지 마'처럼 '의'로 이어진 관형어도 뒤 명사를 꾸미므로 그
# 명사는 명사구의 머리다(2026-08-05 사용자 보고). `correct_action_noun_affix`는
# 처음부터 JKG를 가드에 넣고 있었고, 가르는 쪽만 빠져 있었다.
_ADNOMINAL_TAGS = ("MM", "ETM", "JKG")


def correct_adnominal_noun_verb_split(text: str) -> tuple[str, list[str]]:
    """관형사(MM)나 관형형(…ETM) 바로 뒤에 '명사+하다' 동사가 붙어 있으면
    (예: '뭔 생각하냐', '만날 생각해') 명사와 '하'를 띄어 준다. 관형사·관형형은
    반드시 '명사'를 꾸미므로, 뒤의 'X하다'는 관형어의 수식을 받는 명사 X와
    동사 '하다'로 나뉘어야 한다(뭔 생각 하냐 / 만날 생각 해). 이 판정은 문맥과
    무관하게 통사적으로 하나뿐인 정답이라 자동 교정한다.

    적용 조건(전부 만족할 때만):
    - '명사(NNG) + 하(XSV)'가 공백 없이 한 어절로 붙어 있다('생각하').
    - 그 명사 바로 앞(공백 하나 사이)에 관형사(MM) 또는 관형형 어미(ETM)로
      끝나는 말이 온다. → 관형어가 이 명사를 직접 꾸민다.
    부사(예: '잘/MAG')가 앞에 오면 동사 '생각하다'를 수식하는 것이므로 나누지
    않는다. 관형어가 다른 명사를 꾸미는 경우('그 사람 사랑한다'의 '그'는 '사람'을
    꾸밈)도 대상이 아니다(명사 앞 토큰이 관형사/관형형이 아님).

    반환값: (교정된 텍스트, 적용 로그)."""
    tokens = _kiwi.tokenize(text)
    cuts = []  # '하'(XSV)가 시작하는 위치 = 여기에 공백을 넣는다
    for i in range(2, len(tokens)):
        hae, noun, adnom = tokens[i], tokens[i - 1], tokens[i - 2]
        if hae.tag != "XSV" or hae.form != "하":
            continue
        if noun.tag != "NNG":
            continue
        if noun.start + noun.len != hae.start:
            continue  # '명사'와 '하'가 이미 떨어져 있으면 대상 아님
        if adnom.tag not in _ADNOMINAL_TAGS:
            continue  # 관형사/관형형/관형격 조사가 아니면(부사 등) 나누지 않는다
        # **관형어는 어절 처음에 온다.** 어절 중간의 MM은 kiwi가 모르는 낱말을 쪼갠
        # 결과다 — 2026-08-04 사용자 제공 자막 6강 166번에서 고유명사 '엘모'가
        # '엘'(NNG)+'모'(MM)로 쪼개져 '엘모 인터뷰할 때'가 '엘모 인터뷰 할 때'로 갈렸다.
        if adnom.tag == "MM" and adnom.start > 0 and not text[adnom.start - 1].isspace():
            continue  # 관형사형 어미(ETM)는 본래 어절 안에 있으므로 MM에만 적용한다
        if text[adnom.start + adnom.len : noun.start] not in (" ", ""):
            continue  # 관형어가 이 명사 바로 앞이 아니면 수식 관계가 아님
        cuts.append(hae.start)
    if not cuts:
        return text, []
    corrected = text
    for pos in sorted(set(cuts), reverse=True):
        corrected = corrected[:pos] + " " + corrected[pos:]
    return corrected, [_localized_change(text, corrected)]


# 사람을 높여 부르는 의존명사. 성이나 이름 뒤에서는 띄어 쓴다(홍길동 님, 홍길동 씨).
# 근거: 표준국어대사전 '님'(의존 명사) "그 사람을 높여 이르는 말. '씨'보다 높임의
# 뜻을 나타낸다.", 온라인가나다 — "그 사람을 높이거나 대접하여 부르거나 이르는 말로
# 쓸 때는 의존 명사이므로 앞말과 띄어 쓴다('김 씨', '길동 씨', '홍길동 씨')".
# 직위·관계 뒤의 '-님'은 접미사라 붙여 쓴다(사장님, 부모님, 고객님) — kiwi가 이 둘을
# 앞말 태그로 갈라 준다(고유명사 NNP = 사람 이름 / 일반명사 NNG = 직위·관계).
_HONORIFIC_DEPENDENT_NOUNS = ("님", "씨")


def correct_honorific_dependent_noun_spacing(text: str) -> tuple[str, list[str]]:
    """성명 뒤에 붙여 쓴 '님'·'씨'를 띄어 쓴다('홍길동님' -> '홍길동 님').

    앞말이 **두 글자 이상의 고유명사(NNP)**일 때만 자동 교정한다. 한 글자 고유명사
    (성 한 글자)는 '김씨'(성씨 가문·접미사)와 '김 씨'(그 사람·의존명사)가 표기만으로
    갈리지 않아 자동으로 바꾸지 않고 check_honorific_dependent_noun()이 플래그한다.
    일반명사 뒤('사장님', '고객님')는 접미사이므로 대상이 아니다.

    반환값: (교정된 텍스트, 적용 로그)."""
    tokens = _kiwi.tokenize(text)
    cuts = []
    for i in range(1, len(tokens)):
        honorific, prev = tokens[i], tokens[i - 1]
        if honorific.form not in _HONORIFIC_DEPENDENT_NOUNS:
            continue
        if prev.tag != "NNP" or len(prev.form) < 2:
            continue
        if prev.start + prev.len != honorific.start:
            continue  # 이미 띄어 써 있으면 대상 아님
        cuts.append(honorific.start)
    if not cuts:
        return text, []
    corrected = text
    for pos in sorted(set(cuts), reverse=True):
        corrected = corrected[:pos] + " " + corrected[pos:]
    return corrected, [_localized_change(text, corrected)]


def check_honorific_dependent_noun(index: int, text: str) -> FlagItem | None:
    """성 한 글자 뒤에 붙여 쓴 '씨'·'님'을 확인 플래그한다('김씨').

    '김씨'는 두 가지로 읽힌다 — 접미사 '-씨'(그 성씨 자체·가문: '김해 김씨')면 붙여
    쓰고, 의존명사 '씨'(그 사람: '김 씨는 밥을 차려 주었다')면 띄어 쓴다. 표기만으로는
    갈리지 않아 사람이 판단한다(온라인가나다 답변이 두 쓰임을 나란히 제시한다)."""
    tokens = _kiwi.tokenize(text)
    for i in range(1, len(tokens)):
        honorific, prev = tokens[i], tokens[i - 1]
        if honorific.form not in _HONORIFIC_DEPENDENT_NOUNS:
            continue
        if prev.tag != "NNP" or len(prev.form) != 1:
            continue
        if prev.start + prev.len != honorific.start:
            continue
        suggested = text[: honorific.start] + " " + text[honorific.start :]
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=suggested,
            reason=(
                f"'{prev.form}{honorific.form}'{_josa(honorific.form, '이')} 그 사람을 높여 부르는 "
                f"말이면 의존명사라 "
                f"'{prev.form} {honorific.form}'처럼 띄어 씁니다. 성씨 자체나 가문을 뜻하면"
                f"(김해 김씨) 접미사라 붙여 쓰므로 문맥 확인이 필요합니다."
            ),
        )
    return None


def check_adnominal_noun_verb_split(index: int, text: str) -> FlagItem | None:
    """관형어 뒤에 붙여 쓴 '명사+하다'에서 kiwi가 '하'를 **동사(VV)**로 읽은 자리를
    확인 플래그한다('이런 말하지 마', '첫 방송했어').

    자동 교정(`correct_adnominal_noun_verb_split`)은 '하'가 접미사(XSV)로 태깅된
    자리만 가른다. 같은 문장을 띄어 써 온 원문에서는 kiwi가 '하'를 동사로 읽는
    일이 잦아 그 자리는 규칙이 아예 발동하지 않았다(`docs/BACKLOG.md` 30번).

    **왜 자동 교정이 아니라 플래그인가**(2026-08-04 사용자 결정): VV까지 자동으로
    가르면 붙임형이 사전 표제어인 고정 표현이 깨진다 — kiwi가 '두말하지'를
    '두'(MM)+'말'(NNG)+'하'(VV)로, '한잔했어'를 '한'(MM)+'잔'+'하'로 쪼개기 때문에
    `두말하다`·`한잔하다`·`딴말하다`·`딴짓하다`가 모두 갈릴 후보로 잡혔다(실측 4건).
    사전 조회로 막을 수는 있으나 사전 API 장애 때 `word_exists`가 미등재와 같은
    False를 돌려주므로 가드가 열린다. 자동 교정은 정답이 100% 하나일 때만 한다는
    원칙에 따라 사람 확인으로 남긴다."""
    tokens = _kiwi.tokenize(text)
    for i in range(2, len(tokens)):
        hae, noun, adnom = tokens[i], tokens[i - 1], tokens[i - 2]
        if hae.tag != "VV" or hae.form != "하":
            continue
        if noun.tag != "NNG":
            continue
        if noun.start + noun.len != hae.start:
            continue  # 이미 띄어 써 있으면 확인할 것이 없다
        if adnom.tag not in _ADNOMINAL_TAGS:
            continue
        # 자동 교정 쪽과 같은 가드: 어절 중간의 MM은 kiwi가 모르는 낱말을 쪼갠 결과다.
        if adnom.tag == "MM" and adnom.start > 0 and not text[adnom.start - 1].isspace():
            continue
        if text[adnom.start + adnom.len : noun.start] not in (" ", ""):
            continue
        suggested = text[: hae.start] + " " + text[hae.start :]
        adnom_form = text[adnom.start : adnom.start + adnom.len]
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=suggested,
            reason=(
                f"관형어 '{adnom_form}'{_josa(adnom_form, '이')} '{noun.form}'{_josa(noun.form, '을')} "
                f"꾸미면 그 뒤의 '하다'는 동사라 "
                f"'{noun.form} 하…'처럼 띄어 씁니다. 다만 '{adnom_form}{noun.form}하다'가 "
                f"사전에 한 낱말로 오른 고정 표현이면(두말하다·한잔하다·딴짓하다) 붙여 쓴 "
                f"표기가 맞으므로, 어느 쪽인지 확인한 뒤 반영하세요."
            ),
        )
    return None


def _cheo_prefix_candidate(text: str, tokens, i: int):
    """'쳐'(치+어) 뒤에 용언이 오는 자리에서 접두사 '처-' 후보를 찾는다.

    돌려주는 값: (쳐 시작 위치, 뒤 용언 시작 위치, 붙임형, 뒤 용언 태그) 또는 None.
    """
    stem, ending = tokens[i], tokens[i + 1]
    if stem.tag != "VV" or stem.lemma != "치다":
        return None
    if ending.tag != "EC" or ending.form != "어":
        return None
    # 원문에 실제로 '쳐'로 줄어 있어야 한다('치어'는 대상 아님)
    surface_end = ending.start + ending.len
    if text[stem.start:surface_end] != "쳐":
        return None
    if i + 2 >= len(tokens):
        return None
    verb = tokens[i + 2]
    if verb.tag not in ("VV", "VX"):
        return None
    joined = "처" + (verb.lemma or "")
    if not joined.endswith("다"):
        return None
    # 사전 근거: 붙임형(처X)이 표제어이고 쳐X는 표제어가 아닐 때만 다룬다.
    # '쳐다보다'·'쳐들다'·'쳐들어가다'는 쳐-형 자체가 표제어라 이 조건에서 빠진다.
    if not word_exists(joined) or word_exists("쳐" + (verb.lemma or "")):
        return None
    return stem.start, verb.start, joined, verb.tag


def correct_intensive_prefix_cheo(text: str) -> tuple[str, list[str]]:
    """접두사 '처-'를 '쳐'로 잘못 적은 것을 고친다('쳐먹어라' -> '처먹어라',
    '쳐 먹어라' -> '처먹어라').

    '처-'는 '마구/함부로'의 뜻을 더하는 접두사이고, 사전은 그 파생어를 하이픈으로
    표시해 등재한다(처-먹다 "'먹다'를 속되게 이르는 말", 처-넣다 "마구 집어넣다").
    '쳐먹다'·'쳐넣다'는 어느 사전에도 없다. 접두사이므로 뒤 용언과 붙여 쓴다.

    파생어가 사전에 없어도(처맞다 미등재) 붙여 쓴 '쳐+본용언'은 고친다 — 접두사
    결합밖에 될 수 없기 때문이다. 자동 교정은 **뒤가 본용언(VV)일 때만** 한다. 보조 용언(VX) 자리는 '치다'의 활용과
    구분되지 않는다 — '박수를 쳐 줘'의 '쳐 주다'는 정상이고 '처주다'도 사전 표제어라
    조건만으로는 걸러지지 않는다. 그 자리는 check_intensive_prefix_cheo()가 플래그한다.

    반환값: (교정된 텍스트, 적용 로그)."""
    tokens = _kiwi.tokenize(text)
    edits = []  # (쳐 시작, 뒤 용언 시작)
    for i in range(len(tokens) - 2):
        found = _cheo_prefix_candidate(text, tokens, i)
        if found:
            start, verb_start, joined, verb_tag = found
            # 붙임형이 **한자어뿐**이면 접두사 '처-' 파생어가 아니다('처하다'=處하다).
            # 그 표기로 바꾸면 뜻이 다른 낱말이 된다 — check_intensive_prefix_cheo()가
            # "둘 다 비표준"으로 알린다(2026-08-04 사용자 지적, §64).
            if verb_tag == "VV" and not only_sino_korean_headword(joined):
                edits.append((start, verb_start))
            continue
        # 파생어가 사전에 없어도, **붙여 쓴** '쳐+본용언'은 접두사 결합밖에 될 수 없다.
        # '맞다'는 보조 용언이 아니므로 '치어 + 맞다'를 한 어절로 붙여 쓸 근거가 없다
        # ('쳐맞고'는 틀린 표기, '처맞고'가 맞다 — 2026-08-03 사용자 지정).
        undocumented = _undocumented_cheo_derivative(text, tokens, i)
        if undocumented:
            start, verb_start, _joined = undocumented
            edits.append((start, verb_start))
    if not edits:
        return text, []
    corrected = text
    for start, verb_start in sorted(edits, reverse=True):
        # '쳐' -> '처'로 바꾸고, 사이 공백은 지워 붙인다.
        corrected = corrected[:start] + "처" + corrected[verb_start:]
    return corrected, [_localized_change(text, corrected)]


def _undocumented_cheo_derivative(text: str, tokens, i: int):
    """사전에 파생어가 없는 '쳐+용언' 결합을 찾는다('쳐맞고' — 처맞다·쳐맞다 모두 미등재).

    접두사 '처-'는 뒤 용언에 붙여 쓰므로 파생어가 사전에 없어도 표기는 '처X'다. 다만
    사전이 확인해 주지 않으니 자동으로 바꾸지 않고 후보만 알린다.

    돌려주는 값: (쳐 시작 위치, 뒤 용언 시작 위치, 붙임형) 또는 None.
    """
    stem, ending = tokens[i], tokens[i + 1]
    if stem.tag != "VV" or stem.lemma != "치다":
        return None
    if ending.tag != "EC" or ending.form != "어":
        return None
    if text[stem.start : ending.start + ending.len] != "쳐":
        return None
    if i + 2 >= len(tokens):
        return None
    verb = tokens[i + 2]
    if verb.tag != "VV" or verb.start != ending.start + ending.len:
        return None  # 붙여 쓴 경우만 — 띄어 쓴 '쳐 맞고'는 '치다'의 활용일 수 있다
    lemma = verb.lemma or ""
    if not lemma.endswith("다") or not word_exists(lemma):
        return None
    if word_exists("처" + lemma) or word_exists("쳐" + lemma):
        return None  # 사전에 근거가 있으면 correct_intensive_prefix_cheo()가 다룬다
    return stem.start, verb.start, "처" + lemma


def check_intensive_prefix_cheo(index: int, text: str) -> FlagItem | None:
    """보조 용언 자리의 '쳐'를 접두사 '처-'로 볼지 확인 플래그한다('쳐 하든가').

    '처하다'는 표준국어대사전에 있으나 뜻이 '어떤 형편이나 처지에 놓이다'(處하다)여서
    접두사 '처-'의 뜻과 다르다. 즉 붙임형이 표제어라는 사실만으로 정답을 확정할 수
    없다. 자동으로 바꾸지 않고 사람에게 넘긴다(2026-08-03 사용자 보고).

    **붙임형이 한자어뿐인 자리는 대안을 제시하지 않는다**(2026-08-04 사용자 지적):
    `쳐 하다`·`쳐하다`는 둘 다 비표준인데, 전에는 `처하다`를 제안했다 — 그 표제어는
    한자어 處하다여서 이 자리의 대안이 못 된다(§64). 정답은 문맥에 맞는 다른 표현이라
    도구가 만들 수 없으므로, 무엇이 문제인지만 알린다(제안 없음)."""
    tokens = _kiwi.tokenize(text)
    for i in range(len(tokens) - 2):
        found = _cheo_prefix_candidate(text, tokens, i)
        if not found:
            continue
        start, verb_start, joined, verb_tag = found
        sino_only = only_sino_korean_headword(joined)
        if verb_tag != "VX" and not sino_only:
            continue
        if sino_only:
            # 사람이 볼 문구에는 원문 어절을 그대로 인용한다 — 무엇을 지적하는지
            # 바로 보이지 않으면 판단할 수 없다.
            word_end = text.find(" ", verb_start)
            quoted = text[start : len(text) if word_end == -1 else word_end]
            origin = sino_korean_origin(joined)
            return FlagItem(
                line_index=index,
                original_text=text,
                reason=(
                    f"'{quoted}'{_josa(quoted, '는')} 표준 표기가 아닙니다 — 접두사는 '처-'이므로 "
                    "'쳐'로 적은 "
                    "이 표기는 띄어 쓰든 붙여 쓰든 맞지 않습니다. 그렇다고 붙여 쓴 "
                    f"'{joined}'로 바꿀 수도 없습니다: 그 표제어는 한자어 "
                    f"{origin or '다른 낱말'}(어떤 형편이나 처지에 놓이다)로 뜻이 전혀 "
                    "다릅니다. 문맥에 맞는 다른 표현으로 고쳐 주세요."
                ),
            )
        suggested = text[:start] + "처" + text[verb_start:]
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=suggested,
            reason=(
                f"'마구/함부로'의 뜻이라면 접두사 '처-'를 써서 '{joined}'처럼 붙여 씁니다"
                f"(사전 표제어). '치다'의 활용('박수를 쳐 주다')이면 원문이 맞으므로 "
                "문맥 확인이 필요합니다."
            ),
        )
    return None


def correct_ordinal_prefix_je(text: str) -> tuple[str, list[str]]:
    """접두사 '제-'를 뒤 말과 붙여 쓴다('제 1차' -> '제1차', '제 3자' -> '제3자').

    접두사는 반드시 뒤따르는 말에 붙여 쓴다(한글 맞춤법 접두사 규정). kiwi는 순번을
    뜻하는 '제'를 접두사(XPN)로, 1인칭 소유격 대명사 '제'('제 생각')는 대명사(NP)로
    갈라 태깅한다 — 실측: '제1차'의 '제'는 XPN, '제 생각'의 '제'는 NP. 이 태그 하나로
    동형이의어가 갈리므로 자동 교정한다(작업자자료 이미지-판정 NOTA-007, '제1차'(o)/
    '제 1차'(x), '제일차'(o)/'제 일차'(x) — '차'는 앞말에 붙여도 띄워도 맞으므로
    건드리지 않는다).

    반환값: (교정된 텍스트, 적용 로그)."""
    tokens = _kiwi.tokenize(text)
    cuts = []
    for i in range(1, len(tokens)):
        nxt, je = tokens[i], tokens[i - 1]
        if je.form != "제" or je.tag != "XPN":
            continue
        if text[je.start + je.len : nxt.start] != " ":
            continue
        cuts.append((je.start + je.len, nxt.start))
    if not cuts:
        return text, []
    corrected = text
    for gap_start, gap_end in sorted(cuts, reverse=True):
        corrected = corrected[:gap_start] + corrected[gap_end:]
    return corrected, [_localized_change(text, corrected)]


def check_action_noun_affix(index: int, text: str) -> FlagItem | None:
    """동작성 명사 뒤에 띄어 쓴 `시키다`·`받다`·`당하다`를 붙일지 확인 플래그한다.

    2026-08-05까지는 자동으로 붙였다. `일단 술 시켜요`가 `일단 술시켜요`가 된 뒤
    제안으로 내렸다 — 근거가 간접적이기 때문이다(위 `_SUGGEST_ONLY_AFFIX_LEMMAS`
    주석 참고). 사람이 보면 한눈에 갈리는 자리라 제안으로는 그대로 쓸모가 있다.
    """
    tokens = _kiwi.tokenize(text)
    for i in range(1, len(tokens)):
        noun, affix = tokens[i - 1], tokens[i]
        if noun.tag not in ("NNG", "NNP") or affix.lemma not in _SUGGEST_ONLY_AFFIX_LEMMAS:
            continue
        if text[noun.start + noun.len : affix.start] != " ":
            continue
        n = noun.form
        if n in _AFFIX_ACTION_EXCLUDE or not _is_action_noun(n):
            continue
        joined = n + affix.lemma
        suggested = text[: noun.start + noun.len] + text[affix.start :]
        listed = word_exists(joined)
        evidence = (
            f"'{joined}'{_josa(joined, '는')} 사전 표제어입니다."
            if listed
            else f"'{n}하다'가 표제어라 '{n}'{_josa(n, '을')} 행위로 볼 수 있습니다 — "
            f"다만 '{joined}'{_josa(joined, '는')} 사전에 없습니다."
        )
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=suggested,
            reason=(
                f"'{n}'{_josa(n, '이')} 행위를 뜻하면 '{affix.lemma[:-1]}-'는 접미사라 "
                f"'{joined}'처럼 붙여 씁니다. {evidence} '{n}'{_josa(n, '이')} 사물을 "
                f"뜻하면(술을 시키다, 상을 받다) 동사라 띄어 쓴 원문이 맞으므로 "
                "문맥 확인이 필요합니다."
            ),
        )
    return None
