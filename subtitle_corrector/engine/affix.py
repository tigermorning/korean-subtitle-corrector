"""접사 붙임 규칙(하다/시키다/당하다/받다) 및 관형어+명사 분리.
"""

from ..dictionary import word_exists
from .text_utils import _localized_change
from .kiwi_adapter import _kiwi
from .lexicon import _is_action_noun

# 동작성 신호로 쓰는 word_exists(N+"하다")가 동형이의어로 오탐하는 명사들.
# '상'(賞)은 '상하다'(음식이 상하다)·'상당하다'·'상되다'가 사전에 있어 동작성으로
# 오판되지만 실제로는 동작성이 없다('상 받다'는 띄움). '돈'·'벌'도 마찬가지.
_AFFIX_ACTION_EXCLUDE = {"상", "돈", "벌"}


# 동작성 명사 뒤에 붙는 접사(하다/시키다/당하다/받다). '되다'는 성격이 달라
# 별도 처리한다(붙임형이 사전 표제어일 때만 — 피동성 조건).
_AFFIX_LEMMAS = {"하다", "시키다", "당하다", "받다"}


def correct_action_noun_affix(text: str) -> tuple[str, list[str]]:
    """동작성 명사 뒤의 접사(하다/시키다/당하다/받다/되다)가 띄어 써 있으면 붙인다
    (예: '선물 받았어'→'선물받았어', '배달 시켜서'→'배달시켜서', '무시 당하다'→
    '무시당하다', '음악 하는'→'음악하는'). 동작성 없는 명사 뒤에서는 이들이 동사라
    띄어 쓴다('상 받다', '짜장면 시키다', '팀장 되다'는 그대로).

    동작성 판정 = _is_action_noun(word_exists(N+'하다')). 다만 이 신호는 '상하다'
    (부패) 같은 동형이의어로 오탐하므로 _AFFIX_ACTION_EXCLUDE(상/돈/벌)를 먼저
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
            if prev.tag in ("MM", "ETM") and text[prev.start + prev.len : noun.start] in (" ", ""):
                continue
        n = noun.form
        if n in _AFFIX_ACTION_EXCLUDE:
            continue
        affix_is_hada = affix.lemma == "하다" or (affix.tag == "XSV" and affix.form == "하")
        if affix.lemma == "되다":
            attach = word_exists(n + "되다")
        elif affix.lemma in _AFFIX_LEMMAS or affix_is_hada:
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
        if adnom.tag != "MM" and adnom.tag != "ETM":
            continue  # 관형사/관형형이 아니면(부사 등) 나누지 않는다
        if text[adnom.start + adnom.len : noun.start] not in (" ", ""):
            continue  # 관형어가 이 명사 바로 앞이 아니면 수식 관계가 아님
        cuts.append(hae.start)
    if not cuts:
        return text, []
    corrected = text
    for pos in sorted(set(cuts), reverse=True):
        corrected = corrected[:pos] + " " + corrected[pos:]
    return corrected, [_localized_change(text, corrected)]
