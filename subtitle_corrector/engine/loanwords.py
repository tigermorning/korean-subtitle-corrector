"""외래어 표기(kornorms 확정 표기). 일반 용어는 자동 반영, 고유명사는 플래그만 남긴다.
"""

from ..dictionary import loanword_fix, word_exists
from ..report import FlagItem
from .kiwi_adapter import _LOANWORD_TAGS, _kiwi
from .lexicon import _tensified_headword_variant

def correct_loanwords(
    text: str,
) -> tuple[str, list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    """kornorms가 확정한 외래어 표기 오류를 고친다.

    NNG(일반 명사)는 kornorms 정답이 하나뿐이면 조용히 자동 반영하고, 서로
    다른 관례가 공존하면 반영은 하되 확인 플래그를 남긴다 — 기존 방식 그대로.

    NNP(고유명사)는 이 둘 중 어느 쪽이든 절대 텍스트에 자동 반영하지 않고
    항상 확인 플래그로만 제안한다. "스노우"가 인명(스노우 기자)이면 표기
    규칙대로 "스노"가 맞지만, 같은 표기가 영화 제목("스노우맨")처럼 배급사가
    정한 고유 표기일 수도 있어 규칙을 강제하면 실제 고유명사를 훼손할 위험이
    있다 — 텍스트만으로는 이 둘을 구분할 방법이 없으므로, 고유명사는 자동화
    대신 항상 사람이 최종 판단하게 한다.

    반환값: (수정된 텍스트, 확인 불필요 자동 교정 로그, 확인 필요 교정 목록,
    고유명사 확인 제안 목록)
    확인 불필요 로그 항목은 '원문 -> 정답' 문자열이다.
    확인 필요 목록 항목은 ('원문 -> 정답', 전체 맥락) 튜플이다.
    고유명사 확인 제안 목록 항목도 ('원문 -> 정답', 전체 맥락) 튜플이다 —
    텍스트 자체는 바뀌지 않고 이 제안만 리포트에 남는다.
    """
    candidates = [t for t in _kiwi.tokenize(text) if t.tag in _LOANWORD_TAGS]
    replacements = []  # (start, len, original, fix, needs_review, context, is_proper_noun)
    for t in candidates:
        # 이미 표준국어대사전에 정식 등재된 단어는 애초에 외래어 오표기 후보가
        # 아니므로 건드리지 않는다. 그렇지 않으면 "집"처럼 흔한 고유어가
        # kornorms의 전혀 무관한 외래어 항목과 우연히 겹쳐 "지브" 같은 엉뚱한
        # 말로 둔갑하는 사고가 생긴다 (실제로 발견된 버그).
        if word_exists(t.form):
            continue
        # 된소리 구어형이 사전 표제어면(빤스→빤쓰) 외래어 표기로 자동 교정하지
        # 않고 check_colloquial_loanword()가 사람 확인 플래그를 남긴다.
        if _tensified_headword_variant(t.form):
            continue
        fix, needs_review, context = loanword_fix(t.form)
        if fix:
            replacements.append((t.start, t.len, t.form, fix, needs_review, context, t.tag == "NNP"))

    corrected = text
    applied = []
    needs_review_log = []
    proper_noun_suggestions = []
    for start, length, original, fix, needs_review, context, is_proper_noun in sorted(
        replacements, key=lambda r: r[0], reverse=True
    ):
        entry = f"{original} -> {fix}"
        if is_proper_noun:
            proper_noun_suggestions.append((entry, context))
            continue
        corrected = corrected[:start] + fix + corrected[start + length :]
        if needs_review:
            needs_review_log.append((entry, context))
        else:
            applied.append(entry)

    return (
        corrected,
        list(reversed(applied)),
        list(reversed(needs_review_log)),
        list(reversed(proper_noun_suggestions)),
    )


def check_colloquial_loanword(index: int, text: str) -> FlagItem | None:
    """'빤스'처럼 외래어 표기 교정 대상이지만 된소리 구어형('빤쓰')이 사전
    표제어로 있어 화자의 말투일 수 있는 경우, 자동 교정하지 않고 구어형과
    외래어 표기 중 어느 쪽으로 적을지 사람이 정하도록 플래그한다."""
    for t in _kiwi.tokenize(text):
        if t.tag not in _LOANWORD_TAGS or word_exists(t.form):
            continue
        variant = _tensified_headword_variant(t.form)
        if not variant:
            continue
        fix, _needs_review, _context = loanword_fix(t.form)
        if not fix:
            continue
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{t.form}'은 구어형 '{variant}'(사전 표제어)일 수도, 외래어 표기 "
                f"'{fix}'일 수도 있습니다 — 말투를 살릴지 여부를 사람이 판단하세요."
            ),
            suggested_fix=text[: t.start] + variant + text[t.start + t.len :],
        )
    return None
