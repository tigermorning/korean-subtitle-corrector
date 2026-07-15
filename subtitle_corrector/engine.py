"""자막 교정 엔진 — v1: 형태소 분석 기반 미등재 단어 탐지

명사/동사/형용사 같은 내용어만 형태소 단위로 뽑아 사전 기본형(표제어)으로
복원한 뒤 표준국어대사전에 있는지 확인한다. 조사(은/는/이/가)나 어미(-세요,
-습니다) 같은 기능 형태소는 그 자체가 독립된 표제어가 아니므로 검사 대상에서
제외한다.

주의: 이건 여전히 PRD 3단계 판단 엔진 중 1단계(사전/규범 근거)의 "미등재 단어
탐지"일 뿐이다. 문맥에 따라 갈리는 진짜 띄어쓰기 판단(예: "한번" vs "한 번")은
형태소 분석만으로는 못 잡고, 온라인가나다 아카이브 검색과 사람 확인 단계가
추가로 필요하다.
"""

from kiwipiepy import Kiwi

from .dictionary import word_exists
from .parsers import SubtitleEntry
from .report import FlagItem

_CONTENT_TAGS = {"NNG", "NNP", "VV", "VA"}

_kiwi = Kiwi()


def _content_lemmas(text: str) -> list[str]:
    tokens = _kiwi.tokenize(text)
    return [t.lemma for t in tokens if t.tag in _CONTENT_TAGS]


def check_spelling(index: int, text: str) -> FlagItem | None:
    unknown = [w for w in _content_lemmas(text) if not word_exists(w)]
    if unknown:
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=f"사전에 없는 단어: {', '.join(unknown)}",
        )
    return None


def check_spacing(index: int, text: str) -> FlagItem | None:
    """띄어쓰기 제안은 신뢰도를 알 수 없으므로 절대 자동 적용하지 않고
    원문과 다르면 무조건 사람 확인용으로 플래그한다 (예: '한번'/'한 번'처럼
    문맥에 따라 정답이 갈리는 경우 잘못 우겨서 고치는 걸 막기 위함)."""
    suggested = _kiwi.space(text)
    if suggested != text:
        return FlagItem(
            line_index=index,
            original_text=text,
            reason="띄어쓰기 확인 필요 (문맥에 따라 정답이 다를 수 있음)",
            suggested_fix=suggested,
        )
    return None


def check_entries(entries: list[SubtitleEntry]) -> list[FlagItem]:
    flags = []
    for e in entries:
        flags.extend(
            f for f in (check_spelling(e.index, e.text), check_spacing(e.index, e.text)) if f
        )
    return flags
