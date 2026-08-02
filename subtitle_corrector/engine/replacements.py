"""어휘 치환 — 항상 틀린 표기, 비표준어, 차별적 표현, 전(前) 용어. 조사 이형태 보정 포함.
"""

from ..common_errors import ALWAYS_WRONG, DISCRIMINATORY_TERMS
from ..dictionary import (
    former_term_field,
    former_term_lookup,
    standard_term_replacement,
    word_exists,
)
from ..report import FlagItem
from .text_utils import _has_batchim
from .kiwi_adapter import _kiwi
from .lexicon import _tensified_headword_variant

def check_ambiguous_particle(index: int, text: str) -> FlagItem | None:
    """행 끝에 띄어 쓴 '나'가 조사('백 배 나'→'백 배나')인지 '낫다'의 활용
    '나아'의 오기인지 모호할 때 확인 플래그한다. correct_particle_spacing()이
    이 경우 자동으로 붙이지 않으므로, 사람이 문맥으로 판단하게 남긴다."""
    tokens = _kiwi.tokenize(text)
    if len(tokens) < 2:
        return None
    last, prev = tokens[-1], tokens[-2]
    if last.form == "나" and last.tag == "JX" and prev.start + prev.len < last.start:
        joined = text[: prev.start + prev.len] + text[last.start :]  # 사이 공백 제거
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                "행 끝 '나'가 조사('~나')인지 '낫다'의 활용 '나아'의 오기인지 "
                "모호합니다 — 문맥 확인이 필요합니다."
            ),
            suggested_fix=joined,
        )
    return None


# 받침 유무에 따라 형태가 바뀌는 조사 짝: (받침 있을 때 형태, 받침 없을
# 때 형태). "으로/로"는 ㄹ받침 예외("물로"이지 "물으로"가 아님)가 있어
# 일반화하기 까다로워 제외한다 — 확신 없는 부분은 건드리지 않는다는 원칙.
_PARTICLE_ALLOMORPH_GROUPS = [("이", "가"), ("은", "는"), ("을", "를"), ("과", "와")]


_PARTICLE_TO_GROUP = {form: group for group in _PARTICLE_ALLOMORPH_GROUPS for form in group}


def _matching_particle_allomorph(replacement: str, tail: str) -> tuple[str | None, int]:
    """단어를 치환한 뒤(예: "벙어리"->"언어장애인"), 바로 뒤에 오는 조사가
    새 단어의 받침 유무와 안 맞으면("언어장애인가"는 틀림, "언어장애인이"가
    맞음) 맞는 형태로 바꿔 돌려준다.

    반환값: (바꿀 조사 또는 None, 원문에서 지워야 할 길이). 조사가 아니거나
    이미 맞는 형태면 (None, 0)을 돌려줘 원문 그대로 둔다."""
    if not tail or tail[0] not in _PARTICLE_TO_GROUP:
        return None, 0
    with_batchim, without_batchim = _PARTICLE_TO_GROUP[tail[0]]
    desired = with_batchim if _has_batchim(replacement) else without_batchim
    if tail[0] == desired:
        return None, 0
    return desired, 1


def _apply_replacements(text: str, mapping: dict) -> tuple[str, list[str]]:
    """mapping의 각 (원문, 정답) 쌍을 text에 적용한다. 긴 표현부터 먼저
    치환해서, 짧은 표현이 긴 표현의 일부일 때 잘못 겹쳐 치환되는 사고를
    막는다 (예: '벙어리장갑'을 '벙어리'보다 먼저 처리).

    또한 kiwi 토큰 경계와 정확히 일치하는 위치만 교체한다 — 그렇지 않으면
    "재판장님"(재판장+님)처럼 전혀 무관한 긴 단어 안에 짧은 표현("장님")이
    우연히 부분 문자열로 들어있는 경우까지 잘못 건드려 "재판시각장애인" 같은
    사고가 생긴다. 단순 글자 일치가 아니라 실제로 그 형태소 그대로 등장한
    경우에만 교정을 적용한다."""
    corrected = text
    applied = []
    for wrong, right in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
        if wrong not in corrected:
            continue
        tokens = _kiwi.tokenize(corrected)
        token_starts = {t.start for t in tokens}
        token_ends = {t.start + t.len for t in tokens}
        matches = []
        search_from = 0
        while True:
            idx = corrected.find(wrong, search_from)
            if idx == -1:
                break
            end = idx + len(wrong)
            if idx in token_starts and end in token_ends:
                matches.append(idx)
            search_from = idx + 1
        if not matches:
            continue
        for idx in sorted(matches, reverse=True):
            end = idx + len(wrong)
            tail = corrected[end:]
            new_particle, old_len = _matching_particle_allomorph(right, tail)
            if new_particle is not None:
                corrected = corrected[:idx] + right + new_particle + corrected[end + old_len :]
            else:
                corrected = corrected[:idx] + right + tail
        applied.append(f"{wrong} -> {right}")
    return corrected, applied


def correct_always_wrong(text: str) -> tuple[str, list[str]]:
    """문맥과 무관하게 예외 없이 항상 틀린 표현을 자동으로 고친다
    (예: '그리고 나서' -> '그러고 나서'). 국립국어원 API로 조회하는 게
    아니라 잘 알려진 관용적 오용 사례를 직접 정리한 목록(common_errors.py)에
    근거하므로, 초코렛->초콜릿 같은 kornorms 확정 오류와 같은 성격이다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    return _apply_replacements(text, ALWAYS_WRONG)


def correct_nonstandard_terms(text: str) -> tuple[str, list[str]]:
    """우리말샘이 "규범 표기는/표준 용어는 'X'이다"로 이미 명시해 둔 비표준
    표기(예: "요오드"->"아이오딘")를 자동 교정한다.

    correct_always_wrong()의 ALWAYS_WRONG(정적 목록)이나 correct_loanwords()의
    kornorms(외래어 표기 용례)와는 다른 세 번째 원천이다 — "요오드"는
    kornorms엔 오히려 정답으로("Jod"의 정식 번역어) 등재되어 있어
    correct_loanwords()로는 못 잡고, 우리말샘 자체의 표준화 안내에서만
    확인된다(실사용 검증으로 발견). 매번 실시간으로 우리말샘을 조회하므로
    정적 목록과 달리 국립국어원이 표준 용어를 바꿔도 코드 수정이 필요 없다.

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    replacements = {}
    for t in _kiwi.tokenize(text):
        if t.tag not in ("NNG", "NNP"):
            continue
        # 된소리 구어형이 사전 표제어면(빤스→빤쓰) 규범 표기로 자동 바꾸지 않고
        # check_colloquial_loanword()가 말투 보존 여부를 사람에게 묻는다.
        if _tensified_headword_variant(t.form):
            continue
        replacement = standard_term_replacement(t.form)
        if replacement:
            replacements[t.form] = replacement
    if not replacements:
        return text, []
    return _apply_replacements(text, replacements)


def correct_discriminatory_terms(text: str) -> tuple[str, list[str]]:
    """차별적·비하적 표현은 관례냐 아니냐를 따질 문제가 아니라 항상 바꿔야
    하므로 자동으로 교정한다 (예: '간질' -> '뇌전증').

    반환값: (수정된 텍스트, 적용된 수정 설명 목록: '원문 -> 정답')
    """
    return _apply_replacements(text, DISCRIMINATORY_TERMS)


def correct_former_terms(index: int, text: str) -> tuple[str, list[str], list[FlagItem]]:
    """표준국어대사전이 "'X'의 전 용어"로 표시한 옛 용어(지양 대상)를 처리한다.

    correct_nonstandard_terms()가 우리말샘의 "규범 표기는/표준 용어는" 안내를
    보는 것과 원천만 다를 뿐 같은 성격의 실시간 동적 규칙이다 — 정적 목록이
    아니라 매번 표준국어대사전을 조회하므로 국립국어원이 표준 용어를 바꿔도
    코드 수정이 필요 없다.

    안전 규칙(동형이의어 오교정 방지):
    - 모든 뜻이 "전 용어" 뜻인 단어(예: "정신분열증" → 전부 "조현병"의 전 용어)는
      문맥과 무관하게 하나의 정답만 있으므로 조용히 자동 교정한다.
    - "전 용어" 뜻 외에 다른 뜻도 있는 동형이의어(예: "간질" — 옛 용어(뇌전증)
      외에 곤충·조직·'간질거리다' 어근 뜻도 있음)는 자동 교정하지 않고 플래그만
      남긴다. 텍스트만으로 어느 뜻인지 자동 판별하는 것은 확률적 추정이라 이
      프로젝트가 금지하는 방식이므로(문맥 기반 의미 판별 시도 안 함), 사람이
      문맥으로 판단하도록 다른 뜻들을 사유에 실어 안전하게 넘긴다.

    반환값: (수정된 텍스트, 자동 교정 로그: '원문 -> 정답', 확인 플래그 목록)

    kiwi는 "정신분열증"을 "정신"+"분열증"으로 쪼갠다 — 그런데 "정신분열증"
    (정신^분열증)은 통째로 하나의 옛 용어 표제어다. 개별 토큰만 조회하면
    "분열증"만 잡혀 "정신조현병" 같은 오교정이 난다. 그래서 공백 없이 바로
    이어진 명사 토큰들의 최대 구간에서 **긴 결합부터** 사전을 조회해, 여러
    형태소로 이루어진 옛 용어(정신분열증)를 한 단위로 처리한다."""
    tokens = _kiwi.tokenize(text)
    noun_tags = ("NNG", "NNP")
    n = len(tokens)
    auto_replacements: dict[str, str] = {}
    flags: list[FlagItem] = []
    flagged: set[str] = set()

    i = 0
    while i < n:
        if tokens[i].tag not in noun_tags:
            i += 1
            continue
        # 공백 없이 바로 이어진 명사 토큰들의 최대 구간(run)을 모은다.
        j = i
        while (
            j + 1 < n
            and tokens[j + 1].tag in noun_tags
            and tokens[j + 1].start == tokens[j].start + tokens[j].len
        ):
            j += 1
        # run 안에서 긴 결합부터 그리디 매칭 — 가장 긴 옛 용어를 한 단위로 잡는다.
        p = i
        while p <= j:
            matched = False
            for q in range(j, p - 1, -1):
                surface = text[tokens[p].start : tokens[q].start + tokens[q].len]
                result = former_term_lookup(surface)
                if result is None:
                    continue
                # '수강생'처럼 이 명사(수강)가 뒤따르는 접미사(생/XSN)와 결합해
                # 별개의 표제어를 이루면, 그 안의 '수강'을 옛 용어로 보지 않는다
                # (더 긴 표제어 우선 — '수강생'은 '수강(옛 용어)'과 무관한 단어).
                k = q + 1
                while (
                    k < n
                    and tokens[k].tag == "XSN"
                    and tokens[k].start == tokens[k - 1].start + tokens[k - 1].len
                ):
                    k += 1
                if k > q + 1:
                    extended = text[tokens[p].start : tokens[k - 1].start + tokens[k - 1].len]
                    if word_exists(extended):
                        p = q + 1
                        matched = True
                        break
                target = result["target"]
                if not result["ambiguous"]:
                    auto_replacements[surface] = target
                elif former_term_field(surface):
                    # 옛 용어 안내가 **특정 전문 분야 뜻**에만 달려 있고 그 밖의 일반
                    # 뜻도 있는 경우다(2026-08-02 실사용: '원통'의 안내는 우리말샘에서
                    # cat='수학'인 뜻, 즉 '원기둥'의 옛 용어에만 달려 있고 '분하고
                    # 억울함'이라는 일상적인 뜻과는 무관하다). 일반 문장에서 그 분야
                    # 용어로 쓰였다는 근거가 없으므로 플래그하지 않는다.
                    #
                    # 분야 표시가 없는 옛 용어(예: '간질' — 우리말샘 cat 없음)는
                    # 지금까지처럼 플래그한다. 실측으로 두 사례가 이 신호로 갈렸다.
                    pass
                elif surface not in flagged:
                    flagged.add(surface)
                    others = "; ".join(result["other_meanings"])
                    flags.append(
                        FlagItem(
                            line_index=index,
                            original_text=text,
                            reason=(
                                f"표준국어대사전이 '{surface}'을(를) '{target}'의 전 용어(옛 "
                                f"용어)로 표시함 — 지양 대상이나, '{surface}'에 다른 뜻도 있어 "
                                f"자동 교정하지 않고 플래그만 남김(문맥으로 판단 필요). "
                                f"다른 뜻: {others}"
                            ),
                            suggested_fix=target,
                        )
                    )
                p = q + 1
                matched = True
                break
            if not matched:
                p += 1
        i = j + 1

    corrected, applied = text, []
    if auto_replacements:
        corrected, applied = _apply_replacements(text, auto_replacements)
    return corrected, applied, flags
