"""교정 파이프라인 오케스트레이션. 규칙은 여기 두지 않고 각 규칙 모듈을 순서대로 부른다.
"""

from dataclasses import replace
from ..dictionary import lookup_stats, reset_failed_lookups
from ..parsers import SubtitleEntry
from ..report import AppliedNote, FlagItem
from .kiwi_adapter import detect_recurring_unknown_words, register_custom_words
from .options import (
    PunctuationStyle,
    SubtitleMarkers,
    normalize_dialect_mode,
    normalize_spacing_mode,
    resolve_dialect_mode,
)
from .markers import _is_marker_only_line, _screen_text_spans, _split_by_marker
from .spacing import (
    _aux_verb_spacing,
    check_ambiguous_compound,
    check_compound_merge_candidate,
    correct_compound_spacing,
    correct_particle_spacing,
)
from .affix import (
    check_adnominal_noun_verb_split,
    check_honorific_dependent_noun,
    check_intensive_prefix_cheo,
    correct_action_noun_affix,
    correct_adnominal_noun_verb_split,
    correct_honorific_dependent_noun_spacing,
    correct_intensive_prefix_cheo,
)
from .punctuation import (
    check_ambiguous_interjection_comma,
    check_joined_interjection_spacing,
    correct_interjection_vocative_comma,
)
from .subtitle_rules import (
    correct_subtitle_bracket_spacing,
    correct_subtitle_ellipsis,
    correct_subtitle_final_period,
    correct_subtitle_internal_period,
    correct_subtitle_quotes,
)
from .loanwords import check_colloquial_loanword, correct_loanwords
from .replacements import (
    check_ambiguous_particle,
    check_contracted_form,
    correct_always_wrong,
    correct_discriminatory_terms,
    correct_former_terms,
    correct_nonstandard_terms,
)
from .spelling import check_purified_terms, check_spelling
from .dialect import check_dialect
from .consistency import check_aux_verb_consistency, check_term_spacing_consistency
from .spacing_guards import check_spacing
from .edit_guard import verify_edit

def _correct_line_with_markers(
    index: int,
    text: str,
    doc_type: str,
    spacing_mode: str,
    markers: SubtitleMarkers | None = None,
    style: PunctuationStyle | None = None,
) -> tuple[str, list[FlagItem], list[AppliedNote]]:
    """자막 편집 표지를 지킨 채로 교정한다.

    표지가 없거나 자막 모드가 아니면 그냥 _correct_line()이다. 표지가 있으면:
      1. 위치 표지·화면자막 구간을 보호 조각으로 떼어 두고,
      2. 줄바꿈 표지는 실제 줄바꿈으로 바꿔 교정한 뒤,
      3. 교정이 끝나면 표지를 원래 문자로 되돌린다.

    플래그의 original_text/suggested_fix는 구간이 아니라 **줄 전체**로 다시 맞춘다.
    그렇게 하지 않으면 리포트에 조각만 보이고, apply-report가 그 조각으로 줄
    전체를 덮어써서 나머지 대사를 지워 버린다.
    """
    markers = markers or SubtitleMarkers()
    if doc_type != "subtitle" or not markers.any_set:
        return _correct_line(index, text, doc_type, spacing_mode, markers, style)

    # 1. 보호 조각(위치 표지 / 화면자막 구간)과 교정 대상 조각으로 나눈다.
    pieces: list[tuple[str, bool]] = []  # (조각, 보호 여부)
    for chunk in _split_by_marker(text, markers.position):
        if markers.position and chunk == markers.position:
            pieces.append((chunk, True))
            continue
        cursor = 0
        for start, end in _screen_text_spans(chunk, markers.screen_text):
            if start > cursor:
                pieces.append((chunk[cursor:start], False))
            pieces.append((chunk[start:end], True))
            cursor = end
        if cursor < len(chunk):
            pieces.append((chunk[cursor:], False))

    # 2. 교정 대상 조각만 돌린다. 줄바꿈 표지는 교정하는 동안만 실제 줄바꿈이 된다 —
    #    그래야 줄 끝 마침표 규칙이 화면에 보이는 줄과 같은 기준으로 적용된다.
    out_parts = []
    flags: list[FlagItem] = []
    applied: list[AppliedNote] = []
    for piece, protected in pieces:
        if protected or not piece.strip():
            out_parts.append(piece)
            continue
        target = piece.replace(markers.line_break, "\n") if markers.line_break else piece
        fixed, piece_flags, piece_applied = _correct_line(
            index, target, doc_type, spacing_mode, markers, style
        )
        if markers.line_break:
            fixed = fixed.replace("\n", markers.line_break)
            piece_flags = [
                replace(
                    f,
                    original_text=f.original_text.replace("\n", markers.line_break),
                    suggested_fix=(f.suggested_fix or "").replace("\n", markers.line_break),
                )
                for f in piece_flags
            ]
        out_parts.append(fixed)
        flags.extend((piece, f) for f in piece_flags)
        applied.extend(piece_applied)

    corrected = "".join(out_parts)

    # 표시 인접 규칙은 조각을 합친 **뒤에** 한 번 더 본다. 위치 표기는 보호 조각으로
    # 먼저 떼어지므로, 조각 안에서만 보면 '{n8} [민수]'처럼 조각 경계를 사이에 둔
    # 공백을 볼 수 없다.
    if doc_type == "subtitle":
        corrected, adjacency_log = correct_subtitle_bracket_spacing(corrected, markers)
        applied.extend(AppliedNote(message=m, is_edit=True) for m in adjacency_log)

    # 3. 플래그를 줄 전체 기준으로 되돌린다.
    whole_flags = []
    for original_piece, f in flags:
        suggested = f.suggested_fix
        if suggested:
            suggested = corrected.replace(f.original_text, suggested, 1) if f.original_text in corrected else None
        # replace()로 옮긴다 — 필드를 하나씩 옮겨 적으면 새로 생긴 필드
        # (source_lookup_token 등)가 표지 모드에서만 조용히 사라진다.
        whole_flags.append(replace(f, original_text=text, suggested_fix=suggested or ""))
    return corrected, whole_flags, applied


def _correct_line(
    index: int,
    text: str,
    doc_type: str,
    spacing_mode: str,
    markers: "SubtitleMarkers | None" = None,
    style: "PunctuationStyle | None" = None,
) -> tuple[str, list[FlagItem], list[AppliedNote]]:
    """텍스트 한 덩어리에 교정 파이프라인 전체를 적용한다.

    correct_entries()의 줄 단위 본문을 **그대로 떼어낸 것**이다(순수 이동, 로직 변경
    없음). 자막 편집 표지(화면자막·줄바꿈·위치)를 다루려면 한 줄을 여러 구간으로
    쪼개 "보호할 구간은 건너뛰고 나머지만" 교정해야 하는데, 파이프라인이
    correct_entries 안에 박혀 있으면 그렇게 부를 수 없어서 분리했다.

    반환값: (교정된 텍스트, 플래그, 자동 교정 로그 — line_index는 아직 비어 있고
    correct_entries()가 채운다)
    """
    flags: list[FlagItem] = []
    applied: list[AppliedNote] = []
    corrected_text = text

    # 규칙 하나가 끝날 때마다 edit_guard가 "이 변경을 규칙이 설명할 수 있는가"를 검사한다.
    # 설명되지 않는 낱말 변경은 그 규칙의 결과를 버리고 원문을 유지한다(fail-closed).
    # 파일과 무관한 보장이 필요해서 넣은 관문이다 — 자세한 이유는 edit_guard.py 참고.
    blocked: list[str] = []

    def _guard(rule: str, before: str, after: str, declared: list[str]) -> str:
        accepted, refusal = verify_edit(rule, before, after, declared)
        if refusal:
            blocked.append(refusal)
        return accepted

    before = corrected_text
    corrected_text, applied_fixes, review_fixes, proper_noun_fixes = correct_loanwords(corrected_text)
    corrected_text = _guard("외래어 표기", before, corrected_text, applied_fixes)
    before = corrected_text
    corrected_text, particle_fixes = correct_particle_spacing(corrected_text, markers)
    corrected_text = _guard("조사·어미 띄어쓰기", before, corrected_text, particle_fixes)
    before = corrected_text
    corrected_text, adnominal_fixes = correct_adnominal_noun_verb_split(corrected_text)
    corrected_text = _guard("관형어+명사 분리", before, corrected_text, adnominal_fixes)
    before = corrected_text
    corrected_text, affix_fixes = correct_action_noun_affix(corrected_text)
    corrected_text = _guard("접사 붙임", before, corrected_text, affix_fixes)
    before = corrected_text
    corrected_text, honorific_fixes = correct_honorific_dependent_noun_spacing(corrected_text)
    corrected_text = _guard("의존명사 님·씨", before, corrected_text, honorific_fixes)
    before = corrected_text
    corrected_text, cheo_fixes = correct_intensive_prefix_cheo(corrected_text)
    corrected_text = _guard("접두사 처-", before, corrected_text, cheo_fixes)
    before = corrected_text
    corrected_text, comma_fixes = correct_interjection_vocative_comma(corrected_text)
    corrected_text = _guard("감탄사·호격 쉼표", before, corrected_text, comma_fixes)
    before = corrected_text
    corrected_text, compound_fixes = correct_compound_spacing(corrected_text)
    corrected_text = _guard("합성어 붙임", before, corrected_text, compound_fixes)
    before = corrected_text
    corrected_text, aux_verb_fixes, aux_verb_blocked = _aux_verb_spacing(
        corrected_text, spacing_mode
    )
    corrected_text = _guard("보조 용언 띄어쓰기", before, corrected_text, aux_verb_fixes)
    applied.extend(
        AppliedNote(message=f"[붙임 불가] {note}", is_edit=False) for note in aux_verb_blocked
    )
    before = corrected_text
    corrected_text, always_wrong_fixes = correct_always_wrong(corrected_text)
    corrected_text = _guard("확정 오류 표현", before, corrected_text, always_wrong_fixes)
    before = corrected_text
    corrected_text, nonstandard_fixes = correct_nonstandard_terms(corrected_text)
    corrected_text = _guard("규범 표기 재지정", before, corrected_text, nonstandard_fixes)
    before = corrected_text
    corrected_text, discriminatory_fixes = correct_discriminatory_terms(corrected_text)
    corrected_text = _guard("차별적 표현", before, corrected_text, discriminatory_fixes)
    before = corrected_text
    corrected_text, former_term_fixes, former_term_flags = correct_former_terms(
        index, corrected_text
    )
    corrected_text = _guard("전 용어", before, corrected_text, former_term_fixes)
    # edit_guard가 거부한 건은 "무엇을 하지 않았는지" 알리는 안내이지 교정이 아니다.
    applied.extend(AppliedNote(message=m, is_edit=False) for m in blocked)
    applied.extend(
        AppliedNote(message=m, is_edit=True)
        for m in (
            applied_fixes
            + particle_fixes
            + adnominal_fixes
            + affix_fixes
            + honorific_fixes
            + cheo_fixes
            + comma_fixes
            + compound_fixes
            + aux_verb_fixes
            + always_wrong_fixes
            + nonstandard_fixes
            + discriminatory_fixes
            + former_term_fixes
        )
    )
    flags.extend(former_term_flags)

    for fix, context in review_fixes:
        applied_token = fix.partition(" -> ")[2] or fix
        flags.append(
            FlagItem(
                line_index=index,
                original_text=corrected_text,
                reason=(
                    f"인명/지명 표기 자동 적용됨 ({fix}, 참고: {context}) — "
                    "원지음 표기 원칙에 따른 추정치이므로 실제 발음 확인 필요. "
                    "원어를 알고 있으면 아래 칸에 넣어 국립국어원 용례로 확인하세요"
                ),
                source_lookup_token=applied_token,
            )
        )

    for fix, context in proper_noun_fixes:
        original_token, _, replacement_token = fix.partition(" -> ")
        flags.append(
            FlagItem(
                line_index=index,
                original_text=corrected_text,
                reason=(
                    f"고유명사 외래어 표기 확인 필요 ({fix}, 참고: {context or '국립국어원 확정 표기'}) — "
                    # 판단 기준은 "원어가 무엇인가"다. `러스`는 kornorms에 'Ruth, Babe'의
                    # 오표기로 등재돼 `루스`가 후보로 떴지만, 원고의 인물은 Russ였다
                    # (§57, 7강 123번). 번역가가 무엇을 확인해야 하는지 문구가 직접
                    # 말해 주지 않으면 이 플래그로는 판단할 수 없다(`docs/BACKLOG.md` 28번).
                    f"**원어가 무엇인지 확인하세요** — 등재된 용례의 원어와 같은 대상이면 "
                    f"'{replacement_token}'이 맞고, 원어가 다른 이름이면(Ruth ↔ Russ처럼) "
                    f"'{original_token}'이 맞을 수 있습니다. 작품 제목처럼 고유하게 고정된 "
                    "표기일 수도 있어 자동 반영하지 않습니다. 아래 칸에 원어를 넣으면 "
                    "국립국어원 용례로 확정 표기를 찾아 줍니다"
                ),
                suggested_fix=corrected_text.replace(original_token, replacement_token, 1),
                source_lookup_token=original_token,
            )
        )


    # 자막 모드 구두점 규칙(사용자 지정 2026-08-02). 일반 글 모드는 구두점을
    # 그대로 두므로 하나도 적용하지 않는다. 순서가 중요하다 — 말줄임표를 먼저
    # 온점 세 개로 통일해야 그 뒤의 마침표 규칙이 '...'을 문장 종결 마침표로
    # 오인하지 않고, 문장 사이 마침표를 쉼표로 바꾼 뒤에 줄 끝 마침표를 지워야
    # "보여 주세요. 궁금해요."가 "보여 주세요, 궁금해요"로 한 번에 정리된다.
    if doc_type == "subtitle":
        for rule in (
            lambda t: correct_subtitle_bracket_spacing(t, markers),
            lambda t: correct_subtitle_ellipsis(t, style),
            lambda t: correct_subtitle_quotes(t, style),
            correct_subtitle_internal_period,
            correct_subtitle_final_period,
        ):
            corrected_text, log = rule(corrected_text)
            applied.extend(AppliedNote(message=m, is_edit=True) for m in log)

    # 같은 지점을 여러 검사가 같은 suggested_fix로 중복 플래그하는 경우
    # (예: 행 끝 '나'를 check_ambiguous_particle과 check_spacing이 모두
    # '백 배나'로 제안) 하나만 남긴다.
    seen_fixes = set()
    checks = [
        check_spelling(index, corrected_text),
        check_purified_terms(index, corrected_text),
        check_colloquial_loanword(index, corrected_text),
        check_ambiguous_compound(index, corrected_text),
        check_compound_merge_candidate(index, corrected_text),
        check_ambiguous_particle(index, corrected_text),
        check_contracted_form(index, corrected_text),
        check_joined_interjection_spacing(index, corrected_text),
        check_ambiguous_interjection_comma(index, corrected_text),
        check_honorific_dependent_noun(index, corrected_text),
        check_adnominal_noun_verb_split(index, corrected_text),
        check_intensive_prefix_cheo(index, corrected_text),
        check_spacing(index, corrected_text),
    ]
    for f in checks:
        if not f:
            continue
        if f.suggested_fix and f.suggested_fix in seen_fixes:
            continue
        if f.suggested_fix:
            seen_fixes.add(f.suggested_fix)
        flags.append(f)

    return corrected_text, flags, applied


def correct_entries(
    entries: list[SubtitleEntry],
    dialect_map: dict[str, str] | None = None,
    dialect_modes: dict[str, str] | None = None,
    doc_type: str = "subtitle",
    spacing_mode: str = "principle",
    dialect_region: str | None = None,
    dialect_mode: str | None = None,
    markers: SubtitleMarkers | None = None,
    style: PunctuationStyle | None = None,
) -> tuple[list[SubtitleEntry], list[FlagItem], list[AppliedNote]]:
    """entries를 처리한다.

    반환값: (자동 교정 반영된 entries, 플래그 목록, 확인 불필요 자동 교정 로그)

    자동 교정 로그는 `AppliedNote` 목록이다. 어느 줄의 기록인지(`line_index`)와
    텍스트를 실제로 바꿨는지(`is_edit`)를 구조로 들고 있어서, 화면이 줄 단위
    "되돌리기"를 제공할 수 있다. 사람이 읽는 한 줄은 `AppliedNote.text()`다.
    나머지 검사(맞춤법/띄어쓰기)는 자동 교정이 끝난 텍스트를 기준으로 수행한다.

    본격적인 처리 전에, 문서 전체에서 반복 등장하는 미등록 단어(주로
    고유명사)를 자동으로 감지해 kiwi에 등록한다(register_custom_words
    참고) — 사용자가 이름 목록을 따로 적지 않아도 이 자동 감지만으로
    대부분의 고유명사 오분석이 해결된다.

    dialect_map에 지정된 화자는 dialect_modes의 모드에 따라 처리한다(기본값은
    "protect"):
      - protect: 원문을 그대로 두고 표준화 교정·플래그를 전부 건너뛴다.
      - assist: 텍스트는 그대로, 표준어→사투리 제안 플래그만 남긴다.
      - to_standard: 사투리→표준어 변환 후 표준화 파이프라인을 적용한다.
    사투리 미지정 화자는 기존대로 표준화 파이프라인을 돌리고, 이름이 있으면
    자동 감지 플래그(비율 >= 0.15)를 남긴다.

    spacing_mode는 제47항 보조 용언 띄어쓰기 기준을 문서 전체에 하나로 정한다
    (principle=원칙·띄어 씀, allowance=허용·붙여 씀). 한 작품 안에서 두 기준이
    섞이면 안 되므로 여기서 한 번 정규화해 모든 줄에 같은 값을 넘긴다.

    style은 구두점 표기 방식(말줄임표·따옴표)이다. 어문 규범이 하나로 정해 주지 않고
    납품처마다 다르므로 설정으로 받는다. 기본값은 반각 기호와 온점 세 개.

    markers는 자막 편집 표지(화면자막·줄바꿈·위치)다. 지정된 표지는 어문 규범의
    대상이 아니라 기술적 표지이므로 교정에서 제외한다. 자막 모드에서만 쓴다.

    dialect_region/dialect_mode는 문서 전체 사투리 설정이다. 화자별 지정이 없는
    줄에 이 값이 적용되므로, 화자 표기가 없는 일반 글(소설 등) 전체를 한 사투리로
    다룰 수 있다. 화자별 지정이 있으면 그쪽이 우선한다.
    """
    corrected_entries = []
    flags = []
    applied_log: list[AppliedNote] = []
    # 이번 실행에서 어느 사전 API가 죽었는지 기록하려고 초기화한다. 조회 실패는
    # "등재된 표기 없음"으로 흡수되므로(크래시보다 안전하다) 교정이 조용히 건너뛰어진다 —
    # 그 사실을 사용자에게 알려야 한다(2026-08-04: kornorms가 안 붙는 동안
    # '판넬 -> 패널'이 그냥 통과했고, 화면에는 아무 표시도 없었다).
    reset_failed_lookups()
    protected_indices: set[int] = set()
    spacing_mode = normalize_spacing_mode(spacing_mode)
    if dialect_region:
        applied_log.append(
            AppliedNote(
                message=(
                    f"[사투리 기준] 문서 전체를 '{dialect_region}' 사투리로 보고 "
                    f"'{normalize_dialect_mode(dialect_mode)}' 모드로 처리합니다"
                    " (화자별 지정이 있으면 그 화자는 화자별 설정을 따릅니다)."
                )
            )
        )
    if spacing_mode == "allowance":
        # 기본값(원칙)이 아닌 쪽을 골랐을 때만 남긴다 — 문서 전체가 어떤 기준으로
        # 통일됐는지 결과만 보고도 알 수 있어야 하기 때문이다.
        applied_log.append(
            AppliedNote(
                message="[띄어쓰기 기준] 제47항 허용(보조 용언 붙여 씀)으로 문서 전체를 통일합니다."
            )
        )

    # 자막에서 화자명이 없는 줄은 **직전 화자가 계속 말하는 것**이다(사용자 지정
    # 2026-08-02). 사투리 설정을 화자별로 걸 때 이 승계가 없으면 같은 사람의 대사인데
    # 첫 줄만 적용되고 나머지는 빠진다. 다만 대사 없이 표시만 있는 줄(효과음·지문)은
    # 승계하지 않는다 — 그건 누구의 말도 아니다.
    if doc_type == "subtitle":
        last_speaker = None
        for e in entries:
            if e.speaker:
                last_speaker = e.speaker
            elif last_speaker and e.text.strip() and not _is_marker_only_line(e.text, markers):
                e.speaker = last_speaker

    auto_detected = detect_recurring_unknown_words(entries)
    if auto_detected:
        register_custom_words(auto_detected, tag="NNP")
        applied_log.append(
            AppliedNote(
                message=f"[자동 감지] 반복 등장하는 고유명사로 인식해 등록: {', '.join(auto_detected)}"
            )
        )

    for e in entries:
        # 사투리 모드를 가장 먼저 결정한다 — 표준화 파이프라인을 돌리기 전에
        # 이 화자의 대사를 건드려도 되는지 판단해야 하기 때문이다. 대본 속
        # 사투리는 대부분 작가의 의도이므로, 지정된 화자의 기본값(protect)은
        # 어떤 교정·플래그도 하지 않고 원문을 그대로 둔다.
        region, mode = resolve_dialect_mode(
            e.speaker, dialect_map, dialect_modes, dialect_region, dialect_mode
        )

        # protect — 원문을 완전히 그대로 둔다. 표준화 교정도, 외래어/고유명사
        # 검토 플래그도, 맞춤법/순화어/띄어쓰기 검사도 전부 건너뛴다.
        # (지정된 화자의 대사 안에 진짜 오타가 있어도 그대로 두는 것을 감수한다 —
        #  "의도된 사투리"와 "오타"를 확실히 구분하는 것은 판별 불가능한 경계
        #  사례라, 확률적 추정으로 자동 수정하지 않는 것이 이 프로젝트의 정책이다.)
        if region is not None and mode == "protect":
            protected_indices.add(e.index)
            corrected_entries.append(replace(e))
            continue

        # assist — 텍스트는 그대로 두고 표준화 파이프라인도 돌리지 않는다
        # (표준화는 의도와 정반대다). 표준어→사투리 제안 플래그만 남긴다.
        if region is not None and mode == "assist":
            _, dialect_flags = check_dialect(e.index, e.text, region, mode)
            flags.extend(dialect_flags)
            corrected_entries.append(replace(e))
            continue

        # 여기부터: 사투리 미지정 화자 또는 to_standard 화자.
        # to_standard도 사투리 부분은 **바꾸지 않고 제안 플래그만** 받는다(2026-08-03
        # 변경, `engine/dialect.py` 참고). 그 뒤 원문 그대로 일반 표준화 파이프라인을
        # 적용한다 — 이 화자는 표준 출력을 원하므로 맞춤법·띄어쓰기 교정은 계속한다.
        corrected_text = e.text
        if region is not None and mode == "to_standard":
            _, dialect_flags = check_dialect(e.index, corrected_text, region, mode)
            flags.extend(dialect_flags)

        corrected_text, line_flags, line_applied = _correct_line_with_markers(
            e.index, corrected_text, doc_type, spacing_mode, markers, style
        )
        flags.extend(line_flags)
        for note in line_applied:
            note.line_index = e.index
        applied_log.extend(line_applied)

        # dataclasses.replace로 만들면 형식별 원문 조각(raw_prefix/raw_suffix,
        # original_text)이 그대로 따라온다 — 필드를 하나 늘릴 때마다 여기를 고치는
        # 실수를 막는다.
        corrected_entries.append(replace(e, text=corrected_text))

    # 제49항·제50항 혼용 검사는 한 줄만 봐서는 알 수 없다(같은 용어를 다른 줄에서
    # 어떻게 썼는지 비교해야 한다). 그래서 줄 단위 파이프라인이 모두 끝나고
    # 교정이 확정된 뒤에 문서 전체를 한 번 훑는다.
    flags.extend(check_term_spacing_consistency(corrected_entries, protected_indices))
    flags.extend(check_aux_verb_consistency(corrected_entries, protected_indices))

    # 사투리 자동 감지는 넣지 않는다(2026-08-02 재확인). 화자 단위로 모아 봐도
    # 현재 표지 사전으로는 표준어 화자와 갈리지 않는다 — 실측에서 전라도 화자의
    # 평균 사투리 비율 0.080 vs 표준어 화자 0.073으로, 어떤 문턱을 잡아도 오탐이
    # 생긴다. 근거가 이 정도면 알리지 않는 편이 낫다.

    # 실패를 **건수로** 알린다. 전에는 이름만 모아 "이 사전이 담당하는 교정은 이번
    # 결과에 반영되지 않았습니다"라고 했는데, 수천 건 중 한 건이 순간적으로 실패해도
    # 같은 문구가 떠서 사용자가 사전 연결이 끊긴 줄 알았다(2026-08-04 사용자 보고, §62).
    for api, stats in sorted(lookup_stats().items()):
        failures, attempts = stats["failures"], stats["attempts"]
        samples = ", ".join(stats["queries"])
        if failures >= attempts:
            message = (
                f"[사전 조회 실패] {api} — 이번 실행의 조회 {failures}건이 전부 실패했습니다. "
                "이 사전이 담당하는 교정은 이번 결과에 반영되지 않았습니다"
                "(네트워크·서버 상태를 확인하고 다시 돌려 주세요)."
            )
        else:
            message = (
                f"[사전 조회 일부 실패] {api} — 조회 {attempts}건 중 {failures}건이 "
                "재시도 3회까지 실패했습니다. 그 낱말에 대한 판정만 건너뛰었고 나머지 교정은 "
                "정상입니다"
            )
            message += f" (실패한 낱말: {samples})." if samples else "."
        applied_log.append(AppliedNote(message=message))

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
