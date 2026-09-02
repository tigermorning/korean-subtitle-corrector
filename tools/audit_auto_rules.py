"""자동 교정 규칙을 **근거의 성격**으로 분류하고, 코퍼스에서 실제로 무엇을 바꾸는지 센다.

**왜 필요한가**: 2026-08-04 실사용 원고 전수 대조에서 오교정 14건이 나왔는데
**11건이 "붙임형/대체형이 사전에 있다"는 긍정 근거로 자동 적용된 것**이었다
(`docs/log-archive/2026-h2.md` §55~§57). 반대로 "사전에 그런 낱말이 없다"는 부정
근거로 판정한 규칙은 한 건도 사고를 내지 않았다.

    긍정 근거 = "X가 표제어다" -> 원문을 X로 바꾼다.
      X를 쓸 수도 있다는 뜻일 뿐, **원문이 틀렸다는 근거는 아니다.**
      원문과 X가 둘 다 성립하면 뜻이 바뀐다('집 개' -> '집개').
    부정 근거 = "원문 형태가 사전에 없다" -> 사전에 있는 형태로 바꾼다.
      원문이 성립하지 않는다는 직접 근거라 뜻이 바뀔 여지가 없다.

이 도구는 규칙마다 그 극성을 라벨로 달고(아래 RULES), 코퍼스를 돌려 각 규칙이
실제로 몇 줄을 바꾸는지와 그 목록을 찍는다. **판정은 사람이 한다** — 이 도구는
"어느 규칙이 얼마나 위험한 근거로 얼마나 자주 원문을 바꾸는가"를 눈에 보이게 할 뿐이다.

    python tools/audit_auto_rules.py                 # 전체 코퍼스
    python tools/audit_auto_rules.py --limit 100     # 앞 100줄만
    python tools/audit_auto_rules.py --polarity 긍정 # 그 극성 규칙만
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from subtitle_corrector.engine import (  # noqa: E402
    correct_action_noun_affix,
    correct_adnominal_noun_verb_split,
    correct_always_wrong,
    correct_aux_verb_spacing,
    correct_colon_spacing,
    correct_compound_spacing,
    correct_unit_case,
    correct_unit_spacing,
    correct_discriminatory_terms,
    correct_former_terms,
    correct_honorific_dependent_noun_spacing,
    correct_gumeon_ending,
    correct_intensive_prefix_cheo,
    correct_interjection_vocative_comma,
    correct_loanwords,
    correct_bun_spacing,
    correct_duration_cha_spacing,
    correct_mot_hada_compound,
    correct_nonstandard_terms,
    correct_ordinal_prefix_je,
    correct_particle_spacing,
)

from diff_behavior import build_corpus  # noqa: E402


def _loanwords(text: str) -> str:
    corrected, _applied, _mixed, _proper = correct_loanwords(text)
    return corrected


def _former_terms(text: str) -> str:
    corrected, _applied, _flags = correct_former_terms(1, text)
    return corrected


def _plain(fn):
    """(텍스트, 로그) 계약의 규칙을 텍스트만 돌려주게 감싼다."""

    def run(text: str) -> str:
        return fn(text)[0]

    return run


# (규칙 이름, 실행 함수, 근거 극성, 근거 설명)
#
# 극성 표기
#   긍정 — 대체형이 사전에 있다는 것만으로 원문을 바꾼다. 뜻이 바뀔 수 있다.
#   부정 — 원문 형태가 사전에 없다는 근거로 바꾼다.
#   규범 — 어문 규정이 문맥과 무관하게 정답을 하나로 정한다.
#   목록 — 사람이 검증해 고정한 정적 목록.
#   태그 — kiwi 형태소 분석 결과가 유일한 근거다(사전 확인 없음).
RULES = [
    (
        "외래어표기",
        _loanwords,
        "긍정",
        "kornorms에 '원문(X) -> 정답' 용례가 있으면 반영. 원문이 사전 표제어면 제외(부정 근거 병용), 인명·지명 용례뿐이면 플래그로 강등(2026-08-04)",
    ),
    (
        "조사어미띄어쓰기",
        _plain(correct_particle_spacing),
        "태그",
        "제41항. 조사·어미 태그가 붙은 경계만 정리한다. 사전 확인은 동형 접두사('과-')에서만",
    ),
    (
        "관형어명사분리",
        _plain(correct_adnominal_noun_verb_split),
        "태그",
        "관형사(MM)·관형형(ETM) 뒤 '명사+하' 결합을 가른다. 사전 근거 없음",
    ),
    (
        "동작성명사접사붙임",
        _plain(correct_action_noun_affix),
        "긍정",
        "'명사+하다'가 표제어면 동작성으로 보고 접사를 붙인다. '되다'는 '명사되다'가 표제어일 때 붙인다",
    ),
    (
        "님씨띄어쓰기",
        _plain(correct_honorific_dependent_noun_spacing),
        "태그",
        "두 글자 이상 NNP 뒤 '님/씨'를 띄운다. 사전 확인 없이 kiwi 태그만 본다",
    ),
    (
        "접두사처",
        _plain(correct_intensive_prefix_cheo),
        "부정",
        "'처X'가 표제어이고 '쳐X'는 아닐 때만 바꾼다. 둘 다 미등재인 붙여 쓴 '쳐+본용언'도 바꾼다(규범 근거)",
    ),
    (
        "접두사제",
        _plain(correct_ordinal_prefix_je),
        "태그",
        "kiwi가 순번 '제'를 접두사(XPN)로 태깅한 자리만 뒤 말에 붙인다. 사전 확인 없음(2026-09-02, BACKLOG 작업자자료4, NOTA-007)",
    ),
    (
        "감탄사호격쉼표",
        _plain(correct_interjection_vocative_comma),
        "태그",
        "IC/JKV 태그 자리에 쉼표를 넣는다. 대안 분석 가드 다수(§55·§57)",
    ),
    (
        "합성어붙임",
        _plain(correct_compound_spacing),
        "긍정",
        "**2026-08-04 제안으로 강등됨** — 자동 교정 없음(후보만 모아 플래그)",
    ),
    (
        "보조용언띄어쓰기",
        _plain(correct_aux_verb_spacing),
        "규범",
        "제47항. 문서 전체 기준(원칙/허용)으로 통일. 붙임형이 표제어면 띄우지 않는다(긍정 근거는 **원문 보존** 방향으로만 쓴다)",
    ),
    (
        "확정오류표현",
        _plain(correct_always_wrong),
        "목록",
        "common_errors.ALWAYS_WRONG — 문맥 무관 오용으로 검증된 정적 목록",
    ),
    (
        "종결어미구먼",
        _plain(correct_gumeon_ending),
        "태그",
        "'구먼'(표준, '-군'의 본말)을 잘못 적은 '구만'을 고친다. kiwi가 그 자리를 종결 어미(EF)로 태깅했는지만 본다 — 지명·어근 뜻이면 NNG/NNP로 갈린다(2026-09-02, 작업자자료3)",
    ),
    (
        "쌍점띄어쓰기",
        _plain(correct_colon_spacing),
        "규범",
        "문장부호 규정. 숫자:숫자(시각·대비)는 양옆 붙임, 그 외(표제: 설명)는 앞만 붙이고 뒤 한 칸(2026-09-01, BACKLOG 작업자자료4)",
    ),
    (
        "단위대소문자",
        _plain(correct_unit_case),
        "규범",
        "SI 접두어 '킬로'는 소문자 k가 원칙. 숫자 바로 뒤(또는 한 칸 뒤) Km/KM/Kg/KG만 소문자로(2026-09-01, BACKLOG 작업자자료4)",
    ),
    (
        "단위띄어쓰기",
        _plain(correct_unit_spacing),
        "규범",
        "한글 맞춤법 제43항 — 단위 명사는 띄어 씀이 원칙, 아라비아 숫자가 바로 앞일 때만 붙임 허용. 온라인가나다 확인(qna_seq=8756, '100만 km')(2026-09-02, 작업자자료3)",
    ),
    (
        "규범표기재지정",
        _plain(correct_nonstandard_terms),
        "긍정",
        "우리말샘이 \"규범 표기는 'X'\"라고 명시하면 X로 바꾼다. 표준 동형이의어가 하나라도 있으면 제외(부정 근거 병용)",
    ),
    (
        "부사못하다활용",
        _plain(correct_mot_hada_compound),
        "부정",
        "'부사+하다'가 사전에 없고 '부사+못하다'가 표제어일 때만 '못'을 끼운다(표준어 규정 제25항 '안절부절못하다')",
    ),
    (
        "의존명사뿐",
        _plain(correct_bun_spacing),
        "규범",
        "제42항. 체언 뒤면 조사라 붙이고 관형사형 어미(ETM) 뒤면 의존명사라 띄운다. 앞말 품사가 정답을 정하므로 문맥이 개입하지 않는다(qna_seq=310591)",
    ),
    (
        "기간차띄어쓰기",
        _plain(correct_duration_cha_spacing),
        "규범",
        "제42항. 숫자(SN)+기간 단위(년/개월/주/일/달)+'차'가 붙어 있으면 띄운다. 이 자리에는 동형이의어가 없다(qna_seq=309642 '입사 3년 차')",
    ),
    (
        "차별적표현",
        _plain(correct_discriminatory_terms),
        "목록",
        "common_errors.DISCRIMINATORY_TERMS — 토큰 경계 일치할 때만 치환",
    ),
    (
        "전용어",
        _former_terms,
        "긍정",
        "표준국어대사전 \"'X'의 전 용어\" 안내로 바꾼다. 다른 뜻이 하나라도 있으면 플래그로 강등",
    ),
]


def is_prose_line(line: str) -> bool:
    """코퍼스에 섞인 docstring·코드 조각을 걸러 실제 문장만 남긴다
    (tools/audit_blocked_corrections.py와 같은 기준)."""
    if "\n" in line or len(line) > 80:
        return False
    return not any(tok in line for tok in ("()", "->", "_", "`", "#", "assert"))


def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    polarity_filter = None
    if "--polarity" in sys.argv:
        polarity_filter = sys.argv[sys.argv.index("--polarity") + 1]

    rules = [r for r in RULES if polarity_filter is None or r[2] == polarity_filter]
    corpus = [l for l in build_corpus() if is_prose_line(l)]
    if limit:
        corpus = corpus[:limit]

    changes: dict[str, list[tuple[str, str]]] = {name: [] for name, *_ in rules}
    for line in corpus:
        for name, run, _polarity, _basis in rules:
            try:
                after = run(line)
            except Exception as exc:  # 규칙 자체가 터지면 그 사실을 알려야 한다
                print(f"[규칙 오류] {name}: {line!r} -> {exc}")
                continue
            if after != line:
                changes[name].append((line, after))

    print(f"코퍼스 {len(corpus)}줄, 규칙 {len(rules)}개\n")
    print(f"{'규칙':<20} {'근거':<6} {'변경':>5}")
    print("-" * 34)
    for name, _run, polarity, _basis in rules:
        print(f"{name:<20} {polarity:<6} {len(changes[name]):>5}")

    for name, _run, polarity, basis in rules:
        rows = changes[name]
        if not rows:
            continue
        print(f"\n== {name} [{polarity}] {len(rows)}건")
        print(f"   근거: {basis}")
        for before, after in rows:
            print(f"   - {before}")
            print(f"     {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
