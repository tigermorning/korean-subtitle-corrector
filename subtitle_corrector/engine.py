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
2. 맞춤법 — 일반명사/동사/형용사 같은 내용어를 형태소 단위로 뽑아 사전 기본형
   (표제어)으로 복원한 뒤 표준국어대사전에 있는지 확인한다. 없으면 플래그만
   하고 자동 수정하지 않는다 (어떤 게 맞는 표기인지 알 수 없기 때문).
   고유명사(NNP, 사람 이름 등)는 이 검사에서 제외한다 — 정상적인 이름도
   사전 표제어가 아닌 경우가 대부분이라, 포함시키면 멀쩡한 이름을 전부
   오탐하게 된다.
3. 띄어쓰기 — kiwi.space()가 제안하는 띄어쓰기가 원문과 다르면 플래그한다.
   신뢰도를 알 수 없고 '한번/한 번'처럼 문맥에 따라 정답이 갈리는 경우가
   있어 절대 자동 적용하지 않는다.

주의: 이건 여전히 PRD 3단계 판단 엔진 중 1단계(사전/규범 근거)에 해당한다.
온라인가나다 아카이브 검색(2단계)은 아직 없다.
"""

from kiwipiepy import Kiwi

from .dictionary import compound_status, loanword_fix, word_exists
from .parsers import SubtitleEntry
from .report import FlagItem

# NNP(고유명사)는 여기서 제외한다. 사람 이름 같은 고유명사는 표준국어대사전에
# 등재돼 있지 않은 게 정상이라, 포함시키면 "지민", "민준" 같은 멀쩡한 이름을
# 전부 "사전에 없는 단어"로 오탐하게 된다 (부산대 맞춤법 검사기가 사람 이름을
# 이상하게 바꾼다는 지적과 같은 종류의 문제).
_SPELLING_CHECK_TAGS = {"NNG", "VV", "VA"}
_LOANWORD_TAGS = {"NNG", "NNP"}

_kiwi = Kiwi()


def _content_lemmas(text: str) -> list[str]:
    return [t.lemma for t in _kiwi.tokenize(text) if t.tag in _SPELLING_CHECK_TAGS]


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


def correct_compound_spacing(text: str) -> tuple[str, list[str]]:
    """인접한 두 명사가 사전에 하나의 합성어(품사 있음, 하이픈 표기)로
    등재되어 있는데 띄어 쓰여 있으면 붙여 쓰도록 자동 교정한다.

    사전이 "이 조합은 무조건 붙여 쓰는 하나의 단어"라고 직접 확인해 준
    경우만 반영한다. 명사구(품사 없음, 캐럿 표기)는 띄어쓰기·붙여쓰기 둘 다
    허용되므로 건드리지 않는다. kiwi.space()는 이런 합성어를 놓치는 경우가
    있어(예: '노천 카페' -> 안 고침) 사전 조회로 보완한다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    tokens = [t for t in _kiwi.tokenize(text) if t.tag == "NNG"]
    fixes = []  # (start, end, replacement, description)
    for t1, t2 in zip(tokens, tokens[1:]):
        gap = t2.start - (t1.start + t1.len)
        if gap <= 0:
            continue  # 이미 붙어 있음
        combined = t1.form + t2.form
        if compound_status(combined) == "합성어":
            fixes.append((t1.start, t2.start + t2.len, combined, f"{t1.form} {t2.form} -> {combined}"))

    corrected = text
    applied = []
    for start, end, replacement, desc in sorted(fixes, key=lambda f: f[0], reverse=True):
        corrected = corrected[:start] + replacement + corrected[end:]
        applied.append(desc)
    return corrected, list(reversed(applied))


_AUX_EC_FORMS = {"아", "어", "여"}
_AUX_NNB_FORMS = {"뻔", "만", "법", "듯", "성", "직", "척", "체", "양"}


def _force_span(suggested: str, original_span: str, other_span: str) -> str:
    """suggested 안에서 other_span(kiwi가 밀어붙이려는 형태)을 original_span
    (원문에 실제로 쓰인, 마찬가지로 유효한 형태)으로 되돌린다."""
    if other_span != original_span:
        return suggested.replace(other_span, original_span)
    return suggested


def _normalize_aux_verb_spacing(text: str, suggested: str) -> str:
    """한글 맞춤법 제47항: 보조 용언은 붙여 써도, 띄어 써도 되는 경우(붙임
    허용)가 원칙이다. kiwi.space()는 둘 중 하나의 형태를 임의로 강제 제안하는
    경향이 있어("할만하다" -> "할 만하다"), 이미 올바른 표기까지 불필요하게
    "확인 필요"로 플래그하는 오탐이 생긴다. 이를 막기 위해 붙임 허용 구간에서는
    kiwi의 제안을 원문 형태로 되돌린다.

    단, 본용언이 3음절 이상의 사전 등재 합성어인 경우(예: 덤벼들어보아라)는
    항상 띄어 써야 하는 예외이므로 건드리지 않는다 — kiwi가 이미 정확히
    띄어 주는 부분이다.
    """
    tokens = _kiwi.tokenize(text)

    def surface(tok):
        # tok.form 대신 원문에서 실제 그 위치의 글자를 그대로 잘라 쓴다.
        # 어미 활용으로 받침이 다음 형태소로 넘어가는 경우(예: '낸다' ->
        # 내(VX)+ᆫ다(EF))에는 tok.form이 표면형과 달라서 문자열 슬라이싱이
        # 어긋나기 때문이다.
        return text[tok.start : tok.start + tok.len]

    for i in range(1, len(tokens) - 1):
        prev, cur, nxt = tokens[i - 1], tokens[i], tokens[i + 1]

        # 패턴 1: 본용언(VV/VA) + -아/어(EC) + 보조용언(VX)
        if prev.tag in ("VV", "VA") and cur.tag == "EC" and nxt.tag == "VX" and cur.form in _AUX_EC_FORMS:
            stem_len = (cur.start + cur.len) - prev.start
            if stem_len >= 3 and compound_status(prev.lemma) == "합성어":
                continue  # 항상 띄움 예외 -> kiwi 제안을 그대로 둔다
            original_span = text[prev.start : nxt.start + nxt.len]
            attached = text[prev.start : cur.start + cur.len] + surface(nxt)
            spaced = text[prev.start : cur.start + cur.len] + " " + surface(nxt)
            other = spaced if original_span == attached else attached
            suggested = _force_span(suggested, original_span, other)

        # 패턴 2: 관형사형(ETM, prev에 결합) + 의존명사(만/듯/척/체/법/양/성/직
        # 등, NNB) + 하다/싶다(XSA, XSV 또는 VX) — 항상 붙임 허용
        if cur.tag == "NNB" and cur.form in _AUX_NNB_FORMS and nxt.tag in ("XSA", "XSV", "VX"):
            original_span = text[prev.start : nxt.start + nxt.len]
            attached = surface(prev) + surface(cur) + surface(nxt)
            spaced = surface(prev) + " " + surface(cur) + surface(nxt)
            other = spaced if original_span == attached else attached
            suggested = _force_span(suggested, original_span, other)

    return suggested


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

    # kiwi는 사전에 등재된 합성어를 모르는 경우가 있어(예: '노천카페'), 이미
    # correct_compound_spacing()이 사전 근거로 확정 붙여쓰기한 부분을 다시
    # 갈라놓자고 제안할 수 있다. 확정된 합성어는 사전이 kiwi보다 권위 있는
    # 근거이므로, kiwi의 제안에서 그 부분만 원상복구해 오탐을 막는다.
    tokens = [t for t in _kiwi.tokenize(text) if t.tag == "NNG"]
    for t1, t2 in zip(tokens, tokens[1:]):
        if t2.start - (t1.start + t1.len) > 0:
            continue  # 이미 떨어져 있으면 합성어 자동 교정 대상이 아니었음
        if compound_status(t1.form + t2.form) == "합성어":
            suggested = suggested.replace(f"{t1.form} {t2.form}", t1.form + t2.form)

    suggested = _normalize_aux_verb_spacing(text, suggested)

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
        corrected_text, compound_fixes = correct_compound_spacing(corrected_text)
        applied_log.extend(f"[{e.index}] {fix}" for fix in applied_fixes + compound_fixes)

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


def apply_report_fixes(
    report_rows: list[dict], entries: list[SubtitleEntry]
) -> tuple[list[SubtitleEntry], int]:
    """리포트에서 사용자가 직접 채운 수정값(suggested_fix)을 entries에 반영한다.

    한 줄에 플래그가 여러 개 걸려 여러 행이 있을 수 있는데, 그중 사용자가
    실제로 값을 채운 행만 순서대로 적용한다 (같은 줄에 값이 여러 번 채워져
    있으면 리포트 파일에서 나중에 나오는 행이 최종 반영된다).

    반환값: (반영된 entries, 실제로 반영된 건수)
    """
    by_index = {e.index: e for e in entries}
    applied_count = 0

    for row in report_rows:
        fix = (row.get("suggested_fix") or "").strip()
        if not fix:
            continue
        try:
            line_index = int(row["line_index"])
        except (KeyError, TypeError, ValueError):
            continue
        entry = by_index.get(line_index)
        if entry is None:
            continue
        entry.text = fix
        applied_count += 1

    return entries, applied_count
