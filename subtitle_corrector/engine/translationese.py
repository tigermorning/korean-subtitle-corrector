"""번역투 — 원문 문법을 그대로 옮겨 와 한국어답지 않은 표현.

`docs/BACKLOG.md` 작업자 실무 자료 반영 1번의 첫 하위 항목(이중 피동)만 다룬다.
"""

from ..report import FlagItem
from .kiwi_adapter import _kiwi
from .text_utils import _josa, _surface_span

# 이미 피동 접미사(이/히/리/기)로 피동이 된 낱말에 '-어지다'를 또 붙이면 피동이
# 두 번 겹친다("이중 피동", 번역투의 대표 사례 — '읽혀지다'는 '읽다'+히(피동)+
# 어지다(피동)). 여기 실은 아홉 낱말은 `grammar-rule-verify-then-code` 절차로
# 하나씩 확인했다(2026-09-02) — word_exists()로 결합형("잊혀지다" 등)은 표준
# 국어대사전·우리말샘 둘 다 표제어가 없고, 단일 피동형("잊히다" 등)은 전부
# 등재돼 있음을 확인했다.
#
# 이/히/리/기는 사동으로도 읽히는 다의 접미사이지만('보이다'=피동/보다 또는
# 사동/보여 주다), 그 사동형에 다시 '-어지다'(피동)를 붙인 "사동+피동" 결합은
# 실제로 거의 쓰이지 않는다 — 반면 피동을 중복한 오류로 읽는 것이 국어 교육에서
# 대표적으로 지적되는 자리다. 그래도 뜻이 갈릴 여지가 있어 자동 교정하지 않고
# 확인 플래그로만 남긴다.
_DOUBLE_PASSIVE_LEMMAS = {
    "잊히다", "쓰이다", "보이다", "놓이다", "담기다",
    "믿기다", "짜이다", "읽히다", "열리다",
}


def _touching(text: str, a, b) -> bool:
    """토큰 a 바로 뒤에 b가 공백 없이 붙어 있는가.

    '이+어→여'류 모음 축약이 있으면 kiwi가 두 형태소의 표시 구간을 겹쳐
    보고한다(예: '잊혀졌다'에서 어간 '잊히'가 9번째 글자 '혀'까지 차지하는데,
    다음 어미 '어'도 같은 9번째 글자에서 시작한다) — 그래서 `a.start+a.len ==
    b.start` 같은 단순 등식으로는 축약형을 놓친다. 겹치면(overlap) 축약으로
    보고 붙어 있다고 판단하고, 겹치지 않으면 그 사이에 실제 공백이 없을 때만
    붙어 있다고 본다."""
    end = a.start + a.len
    if b.start < end:
        return True
    return text[end : b.start] == ""


def check_double_passive_voice(index: int, text: str) -> FlagItem | None:
    """이중 피동(피동형+'-어지다')을 확인 플래그한다('잊혀지다', '읽혀지고 있다').

    kiwi는 이 결합을 이미 피동으로 굳은 동사(VV, 예: 잊히다)+'어/아'(EC)+
    '지다'(VX)로 분석한다 — 그 VV의 표제어가 `_DOUBLE_PASSIVE_LEMMAS`에 있고
    세 토큰이 어절 안에서 실제로 붙어 있으면(원문에 이미 띄어 쓴 '잊혀 지다'는
    대상 아님 — 그 경우 '지다'가 별개 낱말일 가능성이 있어 판단이 다르다)
    이중 피동 후보다. 정적 목록(활용형 나열)이 아니라 이 구조 조건으로 잡으므로
    '읽혀지고'·'보여지는'처럼 조사·어미가 붙은 모든 활용형에도 그대로 적용된다."""
    tokens = _kiwi.tokenize(text)
    for i in range(len(tokens) - 2):
        stem, ec, vx = tokens[i], tokens[i + 1], tokens[i + 2]
        if stem.tag != "VV" or stem.lemma not in _DOUBLE_PASSIVE_LEMMAS:
            continue
        if ec.tag != "EC" or ec.form not in ("어", "아"):
            continue
        if not _touching(text, stem, ec):
            continue  # 어간과 어미가 붙어 있어야 한다
        if vx.tag != "VX" or vx.lemma != "지다":
            continue
        if not _touching(text, ec, vx):
            continue  # '-어지다'가 붙여 쓴 한 어절이어야 한다
        span = _surface_span(text, stem.start, vx.start + vx.len)
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{span}'{_josa(span, '은')} 이미 피동으로 굳은 '{stem.lemma}'에 "
                "'-어지다'가 다시 붙어 피동이 두 번 겹치는 이중 피동일 수 있습니다"
                "(번역투로 자주 지적되는 자리). 다만 '보이다'류는 사동(보여 주다)"
                "+피동으로 읽힐 여지가 있어 자동으로 바꾸지 않습니다 — 문맥을 "
                f"확인하고, 단순 피동이 맞으면 '{stem.lemma}' 활용형만으로 고치세요."
            ),
        )
    return None
