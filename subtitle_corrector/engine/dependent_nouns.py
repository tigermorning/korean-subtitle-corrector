"""한글 맞춤법 제42항 의존명사 — 같은 글자가 조사·접미사로도 쓰이는 자리.

제42항이 이름을 대는 여덟 낱말(들/뿐/대로/만큼/만/지/차/판)은 **앞말이 무엇이냐**로
의존명사(띄움)와 조사·접미사·어미(붙임)가 갈린다. `대로`·`만큼`·`만`·`지`·`들`은
kiwi와 기존 규칙이 이미 처리하므로(2026-08-05 실측: 맞게 쓴 문장 18건 전부 그대로
두고, 틀린 것 중 `십 년만의`·`떠난지`는 제안, `사람 들이`는 자동 교정), 이 모듈은
남아 있던 `뿐`·`차`·`판`만 다룬다.

판정 규칙과 그 근거는 `docs/GRAMMAR_PRECEDENTS_TABLE.md`에 있고, 인용한 온라인가나다
답변은 2026-08-05에 다시 열어 살아 있는지 확인했다(310591·319170·309642·326715).
"""

from ..dictionary import word_exists
from ..report import FlagItem
from .kiwi_adapter import _kiwi
from .text_utils import _localized_change

# '뿐' 앞에서 조사 읽기를 만드는 체언 태그. 명사(NNG/NNP/NNB)·대명사(NP)·수사(NR)·
# 숫자(SN)·로마자(SL)·명사 파생 접미사(XSN)가 여기 든다.
_BODY_TAGS_BEFORE_BUN = frozenset({"NNG", "NNP", "NNB", "NP", "NR", "SN", "SL", "XSN"})


def correct_bun_spacing(text: str) -> tuple[str, list[str]]:
    """제42항 '뿐'의 띄어쓰기를 앞말로 확정한다.

    - **체언 뒤**면 보조사라 붙여 쓴다(`너뿐이야`·`실력뿐이었다`·`셋뿐이야`).
    - **용언의 관형사형 어미(ETM) 뒤**면 의존명사라 띄어 쓴다(`웃을 뿐이다`).

    표준국어대사전이 '뿐'을 두 표제어로 싣는다 — 의존 명사("다만 어떠하거나 어찌할
    따름이라는 뜻") / 조사("그것만이고 더는 없음"). 어느 쪽인지는 **앞말의 품사가
    정하고 문맥이 개입하지 않는다.** 온라인가나다 `qna_seq=310591`(2025-02-24):
    "조사 '뿐'은 붙이지만 의존 명사 '뿐'은 띄어 쓴다 — '떨 뿐'은 동사의 관형사형 뒤라
    띄어 쓰는 것이 맞다".

    그래서 자동 교정한다(`correct_adnominal_noun_verb_split`과 같은 부류 — 통사적으로
    정답이 하나뿐인 자리). 앞말이 조사·부사처럼 이 둘 중 어느 쪽도 아니면 손대지
    않는다.

    반환값: (교정된 텍스트, 적용 로그)."""
    tokens = _kiwi.tokenize(text)
    cuts: list[tuple[int, int]] = []  # 공백을 지워 붙일 구간
    inserts: list[int] = []  # 공백을 넣어 띄울 위치
    for i in range(1, len(tokens)):
        bun, prev = tokens[i], tokens[i - 1]
        if bun.form != "뿐" or bun.tag not in ("NNB", "JX"):
            continue
        gap = text[prev.start + prev.len : bun.start]
        if prev.tag == "ETM":
            if gap == "":
                inserts.append(bun.start)
        elif prev.tag in _BODY_TAGS_BEFORE_BUN and gap == " ":
            cuts.append((prev.start + prev.len, bun.start))
    if not cuts and not inserts:
        return text, []
    corrected = text
    for pos in sorted(inserts, reverse=True):
        corrected = corrected[:pos] + " " + corrected[pos:]
    for gap_start, gap_end in sorted(cuts, reverse=True):
        corrected = corrected[:gap_start] + corrected[gap_end:]
    return corrected, [_localized_change(text, corrected)]


# 기간을 세는 의존명사. 온라인가나다 `qna_seq=309642`의 용례가 `년`·`주`·`개월`이고,
# 같은 부류로 `일`·`달`을 더했다. 이 목록에 없는 단위는 손대지 않는다 — 넓히려면
# 그 단위로 '차'를 쓴 용례를 먼저 확인할 것.
_DURATION_UNITS = frozenset({"년", "개월", "주", "일", "달"})


def correct_duration_cha_spacing(text: str) -> tuple[str, list[str]]:
    """기간 명사구 뒤에 붙여 쓴 '차'를 띄어 쓴다(`입사 3년차` -> `입사 3년 차`).

    의존명사 '차'는 "일정한 기간을 나타내는 명사구 뒤에 쓰여 주기나 경과의 해당
    시기를 나타내는 말"이라 띄어 쓴다 — 온라인가나다 `qna_seq=309642`(2025-02-04),
    용례 `입사 3년 차`·`임신 8주 차`·`결혼 10년 차`.

    **숫자(SN) + 기간 단위 + 차**가 한 어절로 붙어 있을 때만 다룬다. 이 자리에는
    동형이의어가 없다 — `3년차`를 다르게 읽을 방법이 없으므로 자동 교정한다. 목적을
    뜻하는 접미사 '-차'(`인사차`)는 앞말이 숫자가 아니라 이 규칙에 걸리지 않는다.

    반환값: (교정된 텍스트, 적용 로그)."""
    tokens = _kiwi.tokenize(text)
    inserts: list[int] = []
    for i in range(2, len(tokens)):
        cha, unit, number = tokens[i], tokens[i - 1], tokens[i - 2]
        if cha.form != "차" or cha.tag != "NNB":
            continue
        if unit.form not in _DURATION_UNITS or unit.tag != "NNB":
            continue
        if number.tag != "SN":
            continue
        # 셋이 빈틈없이 붙어 있어야 한다('3년 차'는 이미 맞는 표기다).
        if number.start + number.len != unit.start or unit.start + unit.len != cha.start:
            continue
        inserts.append(cha.start)
    if not inserts:
        return text, []
    corrected = text
    for pos in sorted(set(inserts), reverse=True):
        corrected = corrected[:pos] + " " + corrected[pos:]
    return corrected, [_localized_change(text, corrected)]


def check_purpose_cha_spacing(index: int, text: str) -> FlagItem | None:
    """목적을 뜻하는 '차'를 명사와 띄어 쓴 자리를 확인 플래그한다(`인사 차 들렀다`).

    접미사 '-차'는 명사 뒤에서 '목적'을 뜻하며 붙여 쓴다 — 온라인가나다
    `qna_seq=319170`(2025-08-06): "'택배 접수차'처럼 접사 '-차'는 앞말에 붙여 쓴다".

    **자동 교정하지 않는다.** 이 자리를 가르는 신호가 kiwi 태그뿐이기 때문이다 —
    같은 글자가 茶·車일 때 kiwi는 일반명사(NNG)로, 목적·순번의 '차'일 때 의존명사
    (NNB)로 읽는다(실측: `회사 차 타고`·`따뜻한 차 한 잔`은 NNG / `출장 차`·`연구 차`·
    `면접 차`는 NNB). 신호가 정확해 보이지만 태그 하나에 기대어 낱말을 붙여 버리면
    `회사 차`가 `회사차`가 되는 사고가 남는다. 붙임형이 사전에 있는지도 근거가 못
    된다 — 접미사 결합은 규칙적이라 `면접차`·`접수차`는 미등재다(§67 '-드리다'와 같은
    사정).

    기간 명사구 뒤(`3년 차`)와 관형사형 뒤(`갔던 차에`)는 띄어 쓴 표기가 맞으므로
    대상이 아니다."""
    tokens = _kiwi.tokenize(text)
    for i in range(1, len(tokens)):
        cha, prev = tokens[i], tokens[i - 1]
        if cha.form != "차" or cha.tag != "NNB":
            continue
        if prev.tag != "NNG":
            continue  # 기간 단위(NNB)·관형사형(ETM) 뒤는 띄어 쓴 표기가 맞다
        if text[prev.start + prev.len : cha.start] != " ":
            continue
        joined = prev.form + "차"
        suggested = text[: prev.start + prev.len] + text[cha.start :]
        evidence = (
            f"'{joined}'는 사전 표제어입니다."
            if word_exists(joined)
            else f"'{joined}'는 사전에 없지만 접미사 결합은 규칙적이라 파생어가 다 오르지는 않습니다."
        )
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=suggested,
            reason=(
                f"'{prev.form}'을 하러 간다는 **목적**의 뜻이면 '차'는 접미사라 "
                f"'{joined}'처럼 붙여 씁니다(온라인가나다: '택배 접수차'). {evidence} "
                "마실 것(茶)이나 탈것(車)을 뜻하는 것이면 원문이 맞으므로 문맥 확인이 "
                "필요합니다."
            ),
        )
    return None


def check_hanpan_spacing(index: int, text: str) -> FlagItem | None:
    """붙여 쓴 `한판`이 승부를 세는 단위인지 확인 플래그한다(`한판 더 하자`).

    수 관형사 '한' + 의존명사 '판'(승부·상황을 세는 단위)이면 띄어 쓰고, 어휘화된
    한 낱말 '한판'("한 번 벌이는 판")이면 붙여 쓴다 — 온라인가나다
    `qna_seq=326715`: "'한 판'으로 띄어 쓰는 것이 맞다. 수 관형사 '한'과 '승부를
    겨루는 일을 세는 단위'인 의존 명사 '판'의 구성이기 때문이다."

    **표기만으로는 갈리지 않는다.** `한판`이 표준국어대사전 표제어라 붙여 쓴 표기도
    맞을 수 있고, 어느 쪽인지는 문장이 무엇을 세고 있는지에 달렸다. kiwi가 이 둘을
    다르게 읽기는 하지만(`한판 더 하자`는 MM+NNG, `한판 잔치`는 NNG 한 덩어리) 그
    태그 하나로 낱말을 갈라놓지 않는다 — 사용자 결정(2026-08-04)에 따라 확인 플래그로
    남긴다."""
    tokens = _kiwi.tokenize(text)
    for i in range(1, len(tokens)):
        pan, han = tokens[i], tokens[i - 1]
        if pan.form != "판" or pan.tag != "NNG":
            continue
        if han.form != "한" or han.tag != "MM":
            continue
        if han.start + han.len != pan.start:
            continue  # 이미 띄어 써 있으면 확인할 것이 없다
        suggested = text[: pan.start] + " " + text[pan.start :]
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=suggested,
            reason=(
                "승부·판을 세는 단위면 '판'은 의존명사라 '한 판'처럼 띄어 씁니다"
                "(온라인가나다: \"수 관형사 '한'과 의존 명사 '판'의 구성\"). "
                "'한판 잔치를 벌이다'처럼 '한 번 크게 벌이는 판'을 뜻하는 한 낱말이면"
                "(표준국어대사전 표제어) 붙여 쓴 원문이 맞으므로 문맥 확인이 필요합니다."
            ),
        )
    return None
