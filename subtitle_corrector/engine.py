"""자막 교정 엔진

세 가지를 확인한다:
1. 외래어 표기 — 국립국어원 어문 규범(kornorms)이 명시적으로 "이 표기는
   틀렸다"고 확정하고 정답까지 준 경우 자동으로 교정한다.
   - 일반 용어(예: 초코렛 -> 초콜릿): 문맥과 무관하게 하나의 공식 정답만
     있으므로 조용히 자동 반영하고 플래그하지 않는다.
   - 인명·지명: 원지음 표기 원칙에 따라 우선 자동 반영하지만, 같은 이름에
     성경식 표기와 현대 인명 표기처럼 서로 다른 관례가 동시에 존재할 수
     있고 실제 발음은 영상을 들어야만 확정할 수 있어, 반영은 하되 항상
     사람이 더블체크하도록 리포트에 플래그한다.
2. 맞춤법 — 명사/동사/형용사 같은 내용어를 형태소 단위로 뽑아 사전 기본형
   (표제어)으로 복원한 뒤 표준국어대사전에 있는지 확인한다. 없으면 플래그만
   하고 자동 수정하지 않는다 (어떤 게 맞는 표기인지 알 수 없기 때문).
3. 띄어쓰기 — kiwi.space()가 제안하는 띄어쓰기가 원문과 다르면 플래그한다.
   신뢰도를 알 수 없고 '한번/한 번'처럼 문맥에 따라 정답이 갈리는 경우가
   있어 절대 자동 적용하지 않는다.

주의: 이건 여전히 PRD 3단계 판단 엔진 중 1단계(사전/규범 근거)에 해당한다.
온라인가나다 아카이브 검색(2단계)은 아직 없다.
"""

from kiwipiepy import Kiwi

from .dictionary import loanword_fix, word_exists
from .parsers import SubtitleEntry
from .report import FlagItem

_CONTENT_TAGS = {"NNG", "NNP", "VV", "VA"}
_LOANWORD_TAGS = {"NNG", "NNP"}

_kiwi = Kiwi()


def _content_lemmas(text: str) -> list[str]:
    return [t.lemma for t in _kiwi.tokenize(text) if t.tag in _CONTENT_TAGS]


def correct_loanwords(text: str) -> tuple[str, list[str], list[tuple[str, str]]]:
    """kornorms가 확정한 외래어 표기 오류를 자동으로 고친다.

    반환값: (수정된 텍스트, 확인 불필요 자동 교정 로그, 확인 필요 교정 목록)
    확인 불필요 로그 항목은 '원문 -> 정답' 문자열이다.
    확인 필요 목록 항목은 ('원문 -> 정답', 전체 맥락) 튜플이다.
    """
    candidates = [t for t in _kiwi.tokenize(text) if t.tag in _LOANWORD_TAGS]
    replacements = []  # (start, len, original, fix, needs_review, context)
    for t in candidates:
        fix, needs_review, context = loanword_fix(t.form)
        if fix:
            replacements.append((t.start, t.len, t.form, fix, needs_review, context))

    corrected = text
    applied = []
    needs_review_log = []
    for start, length, original, fix, needs_review, context in sorted(
        replacements, key=lambda r: r[0], reverse=True
    ):
        corrected = corrected[:start] + fix + corrected[start + length :]
        entry = f"{original} -> {fix}"
        if needs_review:
            needs_review_log.append((entry, context))
        else:
            applied.append(entry)

    return corrected, list(reversed(applied)), list(reversed(needs_review_log))


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


def correct_entries(
    entries: list[SubtitleEntry],
) -> tuple[list[SubtitleEntry], list[FlagItem], list[str]]:
    """entries를 처리한다.

    반환값: (자동 교정 반영된 entries, 플래그 목록, 확인 불필요 자동 교정 로그)
    나머지 검사(맞춤법/띄어쓰기)는 자동 교정이 끝난 텍스트를 기준으로 수행한다.
    """
    corrected_entries = []
    flags = []
    applied_log = []

    for e in entries:
        corrected_text, applied_fixes, review_fixes = correct_loanwords(e.text)
        applied_log.extend(f"[{e.index}] {fix}" for fix in applied_fixes)

        corrected_entries.append(
            SubtitleEntry(index=e.index, start=e.start, end=e.end, text=corrected_text)
        )

        for fix, context in review_fixes:
            flags.append(
                FlagItem(
                    line_index=e.index,
                    original_text=corrected_text,
                    reason=(
                        f"인명/지명 표기 자동 적용됨 ({fix}, 참고: {context}) — "
                        "원지음 표기 원칙에 따른 추정치이므로 실제 발음 확인 필요"
                    ),
                )
            )

        flags.extend(
            f
            for f in (
                check_spelling(e.index, corrected_text),
                check_spacing(e.index, corrected_text),
            )
            if f
        )

    return corrected_entries, flags, applied_log
