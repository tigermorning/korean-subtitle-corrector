"""조사 '(으)로서'/'(으)로써' 검사.

표준국어대사전 뜻풀이:
  - '(으)로서': 지위나 신분 또는 자격을 나타내는 격 조사.
  - '(으)로써': 어떤 물건의 재료나 원료 / 어떤 일의 수단이나 도구 / 시간을 셈할 때
    셈에 넣는 한계(기준) / 어떤 일의 이유를 나타내는 격 조사.

앞 명사가 사람인지는 한국어기초사전 의미 범주(semanticCategory)로 본다. 색인은
`tools/build_krdict_semcat.py`가 `<DICT_LOCAL_DIR>/index/krdict_semcat.json`에 만든다(저장소 밖,
CC BY-SA). 색인이 없으면 이 검사는 조용히 꺼진다(배포판·시험 기본).

판단(2026-11-13 사용자 결정):
  1. 앞 명사의 범주가 **모두** 사람 범주인데 '(으)로써'를 썼으면 -> '(으)로서'로 자동 교정.
  2. 사람 범주와 다른 범주가 섞였는데 '(으)로써'를 썼으면 -> 확인 필요(제안 '(으)로서').
  3. 그 밖은 아무것도 하지 않는다. 특히 '사람이 아닌 명사 + (으)로서'는 표시도 하지 않는다 —
     실측에서 '팀으로서'처럼 단체도 자격이 될 수 있어 '로써'로 보는 판단이 틀렸다.
"""
from __future__ import annotations

import json
import os

from ..report import FlagItem
from .kiwi_adapter import _kiwi

PERSON_KEYS = ("주체", "직위", "친족", "직업", "인물", "사람", "인간관계", "인간 관계")
_PARTICLES = ("로서", "으로서", "로써", "으로써")

EVIDENCE = (
    "표준국어대사전: '(으)로서'는 지위나 신분 또는 자격을 나타내는 격 조사, "
    "'(으)로써'는 재료·원료, 수단·도구, 시간의 한계(기준), 이유를 나타내는 격 조사"
)

_CACHE: tuple[str, dict[str, list[str]]] | None = None


def semcat_path() -> str:
    folder = (os.getenv("DICT_LOCAL_DIR") or "").strip()
    return os.path.join(folder, "index", "krdict_semcat.json") if folder else ""


def _semcats() -> dict[str, list[str]]:
    global _CACHE
    path = semcat_path()
    if not path or not os.path.exists(path):
        return {}
    if _CACHE is None or _CACHE[0] != path:
        try:
            with open(path, encoding="utf-8") as fp:
                _CACHE = (path, json.load(fp))
        except (OSError, ValueError):
            _CACHE = (path, {})
    return _CACHE[1]


def _is_person(category: str) -> bool:
    return any(k in category for k in PERSON_KEYS)


def _find(text: str) -> list[tuple[int, int, str, str, str]]:
    """[(명사 시작, 조사 끝, 명사, 쓴 조사, 판정 'all'|'mixed')] — '(으)로써'를 쓴 자리만."""
    cats = _semcats()
    if not cats or "로써" not in text:
        return []
    tokens = _kiwi.tokenize(text)
    out = []
    for i, t in enumerate(tokens):
        if not (t.tag.startswith("J") and t.form in ("로써", "으로써")):
            continue
        j = i - 1
        if j < 0 or not tokens[j].tag.startswith("NN") or tokens[j].end != t.start:
            continue
        start, noun = tokens[j].start, tokens[j].form
        if j > 0 and tokens[j - 1].tag.startswith("NN") and tokens[j - 1].end == tokens[j].start:
            start, noun = tokens[j - 1].start, tokens[j - 1].form + noun  # 붙여 쓴 복합 명사
        found = cats.get(noun) or cats.get(tokens[j].form) or []
        if not found:
            continue
        person = [c for c in found if _is_person(c)]
        if not person:
            continue
        end = t.start + t.len
        if text[start:end] != noun + t.form:
            continue  # 원문 글자와 형태소가 어긋나면(축약 등) 건드리지 않는다
        out.append((start, end, noun, t.form, "all" if len(person) == len(found) else "mixed"))
    return out


def correct_rosseo(text: str) -> tuple[str, list[str]]:
    """앞 명사의 뜻이 모두 사람 범주인 '(으)로써'를 '(으)로서'로 고친다."""
    fixes = []
    result = text
    for start, end, noun, used, kind in reversed(_find(text)):
        if kind != "all":
            continue
        wrong = noun + used
        right = noun + used[:-1] + "서"
        result = result[:start] + right + result[end:]
        fixes.append(f"{wrong} -> {right}")
    fixes.reverse()
    return result, fixes


def check_rosseo(index: int, text: str) -> FlagItem | None:
    """사람 범주와 다른 범주가 섞인 명사 뒤 '(으)로써'를 확인 필요로 알린다."""
    for start, end, noun, used, kind in _find(text):
        if kind != "mixed":
            continue
        right = noun + used[:-1] + "서"
        return FlagItem(
            line_index=index,
            original_text=text,
            reason=(
                f"'{noun + used}' 확인 필요 — '{noun}'에는 사람을 가리키는 뜻도 있고 다른 뜻도 "
                "있습니다. 지위·신분·자격이면 '(으)로서', 재료·수단·도구·이유면 '(으)로써'입니다. "
                f"({EVIDENCE})"
            ),
            suggested_fix=text[:start] + right + text[end:],
        )
    return None
