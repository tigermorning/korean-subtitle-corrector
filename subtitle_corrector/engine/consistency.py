"""문서 전체 일관성 검사(제49항·제50항 혼용). 한 줄만 봐서는 알 수 없어
줄 단위 파이프라인이 모두 끝난 뒤 한 번 훑는다.
"""

import re
from collections import Counter
from ..parsers import SubtitleEntry
from ..report import FlagItem
from .kiwi_adapter import _TERM_RUN_TAGS, _kiwi

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
    skip_indices = skip_indices or set()
    occurrences: dict[str, list[tuple[SubtitleEntry, str]]] = {}
    for entry in entries:
        if entry.index in skip_indices:
            continue  # 사투리 protect 화자: 어떤 플래그도 남기지 않는다
        for run in _term_runs(entry.text):
            occurrences.setdefault(re.sub(r"\s", "", run), []).append((entry, run))

    # 부분 구간까지 후보로 냈으므로 같은 혼용이 '만성 골수성'·'만성 골수성 백혈병'
    # 처럼 여러 길이로 걸린다. 가장 긴 것만 남긴다 — 짧은 쪽은 같은 지점을 가리키는
    # 중복 플래그이고, 사람이 봐야 할 단위는 용어 전체다.
    conflicting = {key for key, found in occurrences.items() if len({run for _, run in found}) >= 2}
    maximal = {key for key in conflicting if not any(key != other and key in other for other in conflicting)}

    flags = []
    for key in sorted(maximal):
        found = occurrences[key]
        variants = Counter(run for _, run in found)
        # 통일 후보 우선순위: 거리 이름 규칙을 어기지 않는 표기 -> 더 자주 쓴
        # 표기 -> (동률이면) 공백이 많은 원칙 형태 -> 사전순.
        preferred = sorted(
            variants,
            key=lambda v: (_violates_street_name_rule(v), -variants[v], -v.count(" "), v),
        )[0]
        summary = ", ".join(f"'{v}'({variants[v]}회)" for v in sorted(variants, key=lambda v: -variants[v]))
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
    """
    skip_indices = skip_indices or set()
    joined: Counter = Counter()
    spaced: Counter = Counter()
    lines: dict[str, list[SubtitleEntry]] = {}

    for entry in entries:
        if entry.index in skip_indices:
            continue
        tokens = _kiwi.tokenize(entry.text)
        for i in range(1, len(tokens)):
            aux, stem = tokens[i], tokens[i - 1]
            if aux.tag != "VX":
                continue
            gap = entry.text[stem.start + stem.len : aux.start]
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
