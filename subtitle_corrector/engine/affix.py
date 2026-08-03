"""접사 붙임 규칙(하다/시키다/당하다/받다) 및 관형어+명사 분리.
"""

from ..dictionary import word_exists
from ..report import FlagItem
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


def _has_adverb_reading(text: str, token) -> bool:
    """명사로 태깅된 토큰이 같은 자리에서 부사(MAG)로도 읽히는지.

    '어제 청소했다'의 '어제'는 시간 부사어라 뒤 명사를 꾸미지 않는다. 그런데 kiwi는
    같은 낱말을 문장에 따라 NNG로도 MAG로도 태깅한다('어제 청소 했다'에서는 MAG,
    붙여 놓으면 NNG). 판정 근거는 kiwi 자신의 대안 분석이다 — 부사 읽기가 있으면
    명사구 수식으로 단정하지 않는다(`_has_determiner_reading`과 같은 방식).
    """
    for tokens, _score in _kiwi.analyze(text, top_n=5):
        for candidate in tokens:
            if candidate.start == token.start and candidate.tag == "MAG":
                return True
    return False


def check_noun_phrase_affix_spacing(index: int, text: str) -> FlagItem | None:
    """'명사 + 명사 + 하다'가 한 어절로 붙어 있으면 띄어 쓸 후보를 플래그한다
    (예: '나물 타령하셨어' → '나물 타령 하셨어').

    **왜 자동 교정이 아니라 플래그인가**: 해석이 둘 다 열려 있다. 온라인가나다는
    `수학 공부 하다` 문의에 "'수학'이 '공부'를 수식해 명사구를 만든 것으로 보면
    띄어 쓰는 것이 바르다"고 하면서도 "'수학을 공부하다'처럼 조사 '을'이 생략된
    목적어로 이해할 수도 있다"고 답했다. 앞 명사가 관형어인지 목적어인지는 표면만
    보고 가릴 수 없으므로 사람에게 남긴다(2026-08-03 사용자 보고로 추가).

    관형사·관형형이 앞에 오는 경우(`뭔 생각하냐`)는 해석이 하나뿐이라
    `correct_adnominal_noun_verb_split()`이 자동으로 나눈다 — 여기서 다루지 않는다.
    """
    tokens = _kiwi.tokenize(text)
    for i in range(2, len(tokens)):
        hae, noun, prev = tokens[i], tokens[i - 1], tokens[i - 2]
        if hae.tag != "XSV" or hae.form != "하":
            continue
        if noun.tag != "NNG":
            continue
        if noun.start + noun.len != hae.start:
            continue  # 명사와 '하'가 이미 떨어져 있으면 대상 아님
        if prev.tag not in ("NNG", "NNP"):
            continue
        if text[prev.start + prev.len : noun.start] != " ":
            continue  # 앞 명사가 바로 앞이 아니면 수식 관계로 볼 수 없다
        if _has_adverb_reading(text, prev):
            continue  # '어제 청소했다'의 '어제'처럼 부사로도 읽히면 수식 관계가 아니다
        suggested = text[: hae.start] + " " + text[hae.start :]
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=suggested,
            reason=(
                f"'{prev.form} {noun.form}'이 명사구라면 뒤의 '하다'는 접사가 아니라 "
                f"동사이므로 '{noun.form} 하…'처럼 띄어 씁니다(온라인가나다 qna_seq=320467). "
                f"반대로 '{prev.form}'을 목적어로 보면 붙여 쓴 표기도 가능해 문맥 확인이 필요합니다."
            ),
        )
    return None
