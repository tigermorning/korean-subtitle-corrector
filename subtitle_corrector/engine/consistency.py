"""문서 전체 일관성 검사(제49항·제50항 혼용). 한 줄만 봐서는 알 수 없어
줄 단위 파이프라인이 모두 끝난 뒤 한 번 훑는다.
"""

import re
from collections import Counter
from ..dictionary import word_exists
from ..parsers import SubtitleEntry
from ..report import FlagItem
from .kiwi_adapter import _TERM_RUN_TAGS, _kiwi
from .spacing import _ALWAYS_ATTACHED_AUX_LEMMAS, _AUX_EC_FORMS
from .text_utils import _josa

# 한 덩어리 용어로 볼 수 있는 길이(공백 제외). 짧은 조합은 우연히 같은 글자열이
# 되는 경우가 많고('한 번'/'한번'처럼 다른 규칙이 다루는 것 포함), 지나치게 긴
# 구간은 용어가 아니라 문장 조각이다.
_TERM_RUN_MIN_CHARS = 4


_TERM_RUN_MAX_CHARS = 30


# 한 후보에 넣을 최대 토큰 수. '마포 경찰서 강력 팀'(4)·'만성 골수 성 백혈병'(4)
# 정도면 충분하고, 더 늘리면 용어가 아닌 문장 조각까지 후보로 들어온다.
_TERM_RUN_MAX_TOKENS = 6


def _term_runs(text: str) -> list[str]:
    """제49항(고유명사)·제50항(전문 용어) 대상이 될 수 있는 용어 후보 구간을
    표면 텍스트로 뽑는다.

    _TERM_RUN_TAGS에 속하는 토큰이 공백만 사이에 두고 이어지는 구간이 후보이며,
    최대 구간뿐 아니라 그 안의 부분 구간도 전부 후보로 낸다. 최대 구간만 쓰면
    '만성 골수성 백혈병 진단'과 '만성골수성백혈병 치료'처럼 뒤에 붙는 말이 달라
    같은 용어인데도 짝지어지지 않기 때문이다.

    붙여 쓴 형태('만성골수성백혈병')는 토큰이 적게, 띄어 쓴 형태('만성 골수성
    백혈병')는 많게 잡히지만, 공백을 지운 문자열은 같으므로 같은 용어의 두
    표기로 짝지을 수 있다.

    의존명사(NNB)는 제외한다 — 관형사형+의존명사 띄어쓰기는 제42항이 항상
    띄어 쓰라고 정한 별개 규칙이라, 여기 섞으면 정당한 오류를 통일 문제로
    오인하게 된다(_TERM_COMPOUND_TAGS가 NNB를 뺀 것과 같은 이유).
    """
    tokens = _kiwi.tokenize(text)
    runs = []
    for i, first in enumerate(tokens):
        if first.tag not in _TERM_RUN_TAGS:
            continue
        end = first.start + first.len
        for token in tokens[i : i + _TERM_RUN_MAX_TOKENS]:
            if token.tag not in _TERM_RUN_TAGS or text[end : token.start].strip() != "":
                break
            end = max(end, token.start + token.len)
            run = text[first.start : end]
            if _TERM_RUN_MIN_CHARS <= len(re.sub(r"\s", "", run)) <= _TERM_RUN_MAX_CHARS:
                runs.append(run)
    return runs


# 거리 이름에서 이름에 붙여 쓰는 것이 원칙인 말('세종대로', '충무로', '종로2가').
# '길'·'거리'는 반대로 띄어 씀이 원칙이지만 고유명사로 보아 전부 붙임도 허용되므로
# (예: '개나리 길' / '개나리길') 어느 쪽도 틀리지 않아 여기 넣지 않는다.
_STREET_ATTACHED_RE = re.compile(r"\s(대로|로|가)(?=\s|$)")


def _violates_street_name_rule(variant: str) -> bool:
    """'세종 대로'처럼 거리 이름의 '대로/로/가'를 띄어 쓴 표기인지.

    통일 후보를 고를 때만 쓴다 — 이 형태를 그 자체로 오류 플래그하지는 않는다.
    여기서 하는 일은 "어차피 하나로 통일해야 한다면 규정에 어긋나지 않는 쪽을
    제안한다"까지다. 의존명사 '대로'('말한 대로')는 NNB라 애초에 용어 후보
    구간에 들어오지 않으므로 여기까지 오지 않는다.
    """
    return bool(_STREET_ATTACHED_RE.search(variant))


# 도로명에서 이름에 붙여 쓰는 구분 기준. '대로'·'로'·'가'만 다룬다 — '길'·'거리'는
# 띄어 씀도 맞아(개나리 길 / 개나리길) 플래그할 근거가 없다.
_STREET_SUFFIXES = ("대로", "로", "가")


def check_street_name_spacing(index: int, text: str) -> FlagItem | None:
    """도로명의 '대로/로/가'를 띄어 쓴 표기를 확인 플래그한다('세종 대로' -> '세종대로').

    `docs/BACKLOG.md` 16번. 전에는 **혼용이 있을 때 통일 후보를 고르는 데만** 이
    규칙을 썼다(`_violates_street_name_rule`). `세종 대로`가 문서에 한 번만 나오면
    아무 말도 하지 않았다.

    **무엇으로 도로명과 일반명사를 가르는가**(2026-08-04 실측 정답표):

        세종 대로에서 만나     세종(NNP) + 대로(NNG)    -> 도로명 후보, 플래그
        테헤란 로에서         테헤란(NNP) + 로(NNG)     -> 도로명 후보, 플래그
        충무 로에 갔다        충무(NNP) + 로(NNG)       -> 도로명 후보, 플래그
        왕복 8차선 대로       차선(NNG) + 대로(NNG)     -> 일반명사 '대로'(大路), 대상 아님
        말한 대로 하면 된다    …(ETM) + 대로(NNB)        -> 의존명사, 대상 아님
        서울로 갔다           서울(NNP) + 로(JKB)       -> 조사, 대상 아님
        종로 2가에서          2(SN) + 가(NNG)          -> 앞말이 수라 대상 아님(아래 참고)

    **앞말이 고유명사(NNP)일 때만** 플래그한다 — 일반명사·수량·의존명사·조사 자리는
    태그가 갈라 준다. 사전으로는 가를 수 없다: `종로`·`충무로`·`을지로`는 표제어인데
    `세종대로`·`테헤란로`·`강남대로`는 미등재다(같은 부류인데 등재만 갈린다).

    **자동 교정하지 않는다.** `세종 대로`가 세종시의 큰길(大路)을 뜻할 수도 있어
    표기만으로는 확정되지 않는다. 붙임형이 사전 표제어면 그 사실을 사유에 실어
    근거를 강화한다.
    """
    tokens = _kiwi.tokenize(text)
    for i in range(1, len(tokens)):
        suffix, prev = tokens[i], tokens[i - 1]
        if suffix.tag != "NNG" or suffix.form not in _STREET_SUFFIXES:
            continue
        if prev.tag != "NNP":
            continue
        if text[prev.start + prev.len : suffix.start] != " ":
            continue  # 이미 붙여 써 있으면 확인할 것이 없다
        spaced = text[prev.start : suffix.start + suffix.len]
        joined = prev.form + suffix.form
        # 한 글자 '가'는 뜻이 너무 많다(街·價·家…). 붙임형이 사전 표제어일 때만
        # 묻는다 — 그렇지 않으면 '명동 가'처럼 도로명이 아닌 자리까지 묻게 된다.
        if suffix.form == "가" and not word_exists(joined):
            continue
        evidence = (
            f"'{joined}'{_josa(joined, '는')} 사전 표제어입니다."
            if word_exists(joined)
            else f"'{joined}'{_josa(joined, '는')} 사전에 없지만 도로명은 대부분 사전에 "
            "오르지 않습니다"
            "(세종대로·테헤란로·강남대로 모두 미등재)."
        )
        return FlagItem(
            line_index=index,
            original_text=text,
            suggested_fix=text[: prev.start] + joined + text[suffix.start + suffix.len :],
            reason=(
                f"'{spaced}'{_josa(spaced, '가')} 도로명이면 '{joined}'처럼 붙여 씁니다(도로명은 이름과 "
                f"구분 기준을 붙여 적습니다). {evidence} 다만 일반명사 '대로'(大路, "
                "크고 넓은 길)로 쓴 것이면 원문이 맞으므로 문맥 확인이 필요합니다."
            ),
        )
    return None


def unify_term_spacing_by_principle(
    entries: list[SubtitleEntry], skip_indices: set[int] | None = None
) -> list[tuple[int, str, str, str]]:
    """제49·50항 혼용을 **원칙(띄어 쓰기)** 쪽으로 자동 통일할 목록을 만든다.

    2단계에서 사용자가 띄어쓰기 기준을 '원칙'으로 골랐으면 이 자리는 물을 것이 아니라
    적용할 것이다(2026-08-05 사용자 지적). `무게 중심`(2회)과 `무게중심`(2회)이 섞여
    있는데 기준이 이미 정해져 있으면 `무게 중심`으로 맞추면 된다.

    **띄우는 방향만 자동으로 한다.** 원래 자동 통일을 미뤄 둔 이유는 "붙이려면 어디까지가
    한 용어인지 알아야 하는데 그 경계가 사전에 없다"는 것이었다. 그 사정은 붙이는
    방향에만 해당한다 — 띄우는 쪽의 목표 표기는 **문서가 이미 쓰고 있는 변이형**이라
    경계를 추측할 일이 없다. 반대로 '허용' 기준은 붙임 경계를 새로 정해야 하므로
    지금도 플래그로 남긴다(`check_term_spacing_consistency`).

    반환값: `(entry.index, 원문 조각, 통일 표기, 요약)` 목록. 실제 치환은 호출부가 한다.
    """
    plans = []
    for key, found, variants, preferred in _mixed_term_variants(entries, skip_indices):
        principle = max(variants, key=lambda v: (v.count(" "), -len(v)))
        if principle.count(" ") == 0:
            continue  # 띄어 쓴 변이형이 없으면 원칙 형태를 만들 수 없다(붙임 경계 추측 금지)
        if _violates_street_name_rule(principle):
            continue  # 도로명은 붙임이 원칙이라 이 규칙이 정할 자리가 아니다
        summary = _variant_summary(variants)
        for entry, run in found:
            if run != principle:
                plans.append((entry.index, run, principle, summary))
    return plans


def _variant_summary(variants) -> str:
    return ", ".join(f"'{v}'({variants[v]}회)" for v in sorted(variants, key=lambda v: -variants[v]))


def _mixed_term_variants(entries: list[SubtitleEntry], skip_indices: set[int] | None):
    """문서에서 같은 용어를 두 가지 이상으로 적은 구간을 찾는다.

    `check_term_spacing_consistency`와 `unify_term_spacing_by_principle`이 같은 판정을
    쓰도록 떼어 놓은 것이다 — 한쪽만 고치면 플래그와 자동 통일이 서로 다른 구간을
    보게 된다.
    """
    skip_indices = skip_indices or set()
    occurrences: dict[str, list[tuple[SubtitleEntry, str]]] = {}
    for entry in entries:
        if entry.index in skip_indices:
            continue  # 사투리 protect 화자: 어떤 플래그도 남기지 않는다
        for run in _term_runs(entry.text):
            occurrences.setdefault(re.sub(r"\s", "", run), []).append((entry, run))

    # 부분 구간까지 후보로 냈으므로 같은 혼용이 '만성 골수성'·'만성 골수성 백혈병'
    # 처럼 여러 길이로 걸린다. 가장 긴 것만 남긴다 — 짧은 쪽은 같은 지점을 가리키는
    # 중복이고, 사람이 봐야 할 단위는 용어 전체다.
    conflicting = {key for key, found in occurrences.items() if len({run for _, run in found}) >= 2}
    maximal = {key for key in conflicting if not any(key != other and key in other for other in conflicting)}

    for key in sorted(maximal):
        found = occurrences[key]
        variants = Counter(run for _, run in found)
        # 통일 후보 우선순위: 거리 이름 규칙을 어기지 않는 표기 -> 더 자주 쓴
        # 표기 -> (동률이면) 공백이 많은 원칙 형태 -> 사전순.
        preferred = sorted(
            variants,
            key=lambda v: (_violates_street_name_rule(v), -variants[v], -v.count(" "), v),
        )[0]
        yield key, found, variants, preferred


def check_term_spacing_consistency(
    entries: list[SubtitleEntry], skip_indices: set[int] | None = None
) -> list[FlagItem]:
    """제49항·제50항 띄어쓰기 혼용을 문서 전체 단위로 잡아 플래그한다.

    한글 맞춤법 제49항(고유 명사)과 제50항(전문 용어)은 둘 다 "단어별로 띄어
    씀을 원칙으로 하되 붙여 쓸 수 있다"고 정한다. 즉 '마포 경찰서 강력 팀'과
    '마포경찰서 강력팀', '만성 골수성 백혈병'과 '만성골수성백혈병'은 모두 맞는
    표기이고, 어느 쪽을 쓸지는 작품의 선택이다. 다만 한 작품 안에서 두 표기가
    섞이면 그건 선택이 아니라 오류다.

    자동 통일하지 않는 이유: 붙이려면 어디까지가 한 용어인지(고유명사는 의미
    단위, 전문 용어는 전체) 알아야 하는데, 그 경계는 사전에 없고 문맥 추측이
    필요하다. 이 프로젝트는 확률적 추측으로 자동 교정하지 않으므로(§5), 혼용
    사실만 결정론적으로 — 공백을 지운 문자열이 같은데 표면형이 다른지 —
    확인해 사람에게 넘긴다. 같은 이유로 '부분만 붙임'(전문 용어에서는 금지,
    고유명사에서는 허용) 판정도 하지 않는다. 그건 그 표기가 전문 용어인지
    고유명사인지 알아야 갈리는데, 그 구분 자체가 추측이기 때문이다.

    통일 후보(suggested_fix)는 문서에서 더 자주 쓴 표기로 제안한다. 횟수가
    같으면 원칙(더 많이 띄어 쓴 형태)을 제안한다 — 제49·50항의 기본이 띄어
    쓰기이므로, 근거 없이 허용 쪽으로 몰지 않기 위함이다.
    """
    flags = []
    for _key, found, variants, preferred in _mixed_term_variants(entries, skip_indices):
        summary = _variant_summary(variants)
        for entry, run in found:
            if run == preferred:
                continue
            flags.append(
                FlagItem(
                    line_index=entry.index,
                    original_text=entry.text,
                    reason=(
                        f"고유명사·전문 용어 띄어쓰기 혼용 (제49항·제50항) — 같은 표기를 "
                        f"문서에서 {summary}로 다르게 씀. 둘 다 맞는 표기지만 한 작품 "
                        f"안에서는 한쪽으로 통일해야 함"
                    ),
                    suggested_fix=entry.text.replace(run, preferred, 1),
                )
            )
    return flags


def check_aux_verb_consistency(
    entries: list[SubtitleEntry], skip_indices: set[int] | None = None
) -> list[FlagItem]:
    """보조 용언 띄어쓰기(제47항) **혼용**을 문서 전체 단위로 잡아 플래그한다.

    제47항은 "띄어 씀을 원칙으로 하되 붙여 씀도 허용"하므로 둘 다 맞는 표기다. 그래서
    기본값은 원문 유지이고 자동으로 통일하지 않는다(2026-08-04 사용자 결정) — 납품처마다
    요구가 달라 미리 정할 수 없다. 다만 **한 문서에 두 표기가 섞이면 그건 선택이 아니라
    오류**이므로, 혼용 사실만 결정론적으로 확인해 사람에게 넘긴다.

    판정: 같은 (본용언 어간 + 보조 용언) 짝이 어떤 줄에서는 붙어 있고 다른 줄에서는 띄어
    있는지 본다. 통일 후보는 문서에서 더 자주 쓴 쪽으로 제안하고, 횟수가 같으면 원칙(띄어
    씀)을 제안한다 — 제47항의 기본이 원칙이기 때문이다.

    **대상은 제47항이 붙임을 허용한 구성뿐이다**(2026-08-05 사용자 지적으로 바로잡음).
    전에는 보조 용언(VX) 태그만 보고 셌더니 `-지 않다`가 걸려 "'않' 띄어쓰기가 섞였다"는
    플래그가 나갔다 — **`-지 않다`는 붙임 허용 대상이 아니라 언제나 띄어 쓴다.** 제47항의
    붙임 허용은 `본용언 + -아/-어 + 보조 용언`과 `관형사형 + 의존명사 + 하다/싶다`
    두 구성에만 적용된다. 규정이 인정하지 않는 표기를 "다른 선택지"로 내놓은 것이라
    문구가 아니라 판정 자체가 틀렸다.

    붙어 있는 것으로 세지 않는 것이 하나 더 있다 — `그렇잖아`·`괜찮다`처럼 어미와
    보조 용언이 **한 음절로 줄어든** 형태다. 표면에 공백이 없을 뿐 띄어 쓸 자리가
    애초에 없다(kiwi가 이 자리를 겹치는 위치로 돌려준다).
    """
    skip_indices = skip_indices or set()
    joined: Counter = Counter()
    spaced: Counter = Counter()
    lines: dict[str, list[SubtitleEntry]] = {}

    for entry in entries:
        if entry.index in skip_indices:
            continue
        tokens = _kiwi.tokenize(entry.text)
        for i in range(2, len(tokens)):
            aux, ending, stem = tokens[i], tokens[i - 1], tokens[i - 2]
            if aux.tag != "VX" or aux.lemma in _ALWAYS_ATTACHED_AUX_LEMMAS:
                continue
            # 제47항 붙임 허용 구성인지 — 본용언(VV/VA) + '-아/-어/-여'(EC).
            if not (stem.tag.startswith("VV") or stem.tag.startswith("VA")):
                continue
            if ending.tag != "EC" or ending.form not in _AUX_EC_FORMS:
                continue
            ending_end = ending.start + ending.len
            if aux.start < ending_end:
                continue  # 축약형('그렇잖아') — 띄어 쓸 자리가 없다
            gap = entry.text[ending_end : aux.start]
            if gap not in ("", " "):
                continue
            key = f"{stem.form}+{aux.form}"
            (joined if gap == "" else spaced)[key] += 1
            lines.setdefault(key, []).append(entry)

    flags = []
    for key in sorted(set(joined) & set(spaced)):
        stem, _, aux = key.partition("+")
        if joined[key] > spaced[key]:
            preferred = "붙여 쓴 쪽이 더 많습니다"
        elif spaced[key] > joined[key]:
            preferred = "띄어 쓴 쪽이 더 많습니다"
        else:
            preferred = "횟수가 같아 원칙(띄어 씀)을 권합니다"
        flags.append(
            FlagItem(
                line_index=lines[key][0].index,
                original_text=lines[key][0].text,
                reason=(
                    f"보조 용언 '{aux}' 띄어쓰기가 문서 안에서 섞였습니다 — "
                    f"붙여 쓴 곳 {joined[key]}군데, 띄어 쓴 곳 {spaced[key]}군데. "
                    f"제47항은 둘 다 인정하지만 한 문서에서는 하나로 통일해야 합니다"
                    f"({preferred}). 위쪽 '띄어쓰기 기준'에서 한쪽을 고르면 문서 전체를"
                    " 그 기준으로 통일합니다."
                ),
            )
        )
    return flags
