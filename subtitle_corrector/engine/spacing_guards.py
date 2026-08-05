"""띄어쓰기 **제안**을 내보내기 전에 근거 없는 부분을 되돌리는 가드 계층.

`check_spacing`이 kiwi 제안을 그대로 내보내면 사전 근거 없는 분리·결합까지
따라 나온다. 여기 있는 `_protect_*` 함수들이 그중 근거가 없는 변경만 원문으로
되돌린다 — `docs/DESIGN_PRINCIPLES.md` 원리 2·3의 공유 가드다.
"""

from ..dictionary import (
    compound_status,
    is_contemporary_general_word,
    registered_ending,
    word_exists,
)
from ..report import FlagItem
from .text_utils import (
    _bracket_spans,
    _force_span,
    _hangul_run_bounds,
    _inserted_space_ranges,
    _inside_any_span,
    _removed_space_points,
    _strip_space_before_punctuation,
)
from .kiwi_adapter import (
    _ATTACH_TAGS,
    _NUMBER_SYMBOL_TAGS,
    _TERM_RUN_TAGS,
    _kiwi,
    _straddling_tokens,
    _token_containing,
    _token_index,
    _tokenization_unstable_near,
)
from .affix import (
    _cheo_prefix_candidate,
    _undocumented_cheo_derivative,
    is_honorific_drida_affix,
)
from .lexicon import _PASSIVE_ONLY_BATDA_NOUNS, _is_action_noun
from .spacing import _compound_candidate_spans, _normalize_aux_verb_spacing

def _protect_unfounded_joining(text: str, suggested: str) -> str:
    """kiwi.space()가 사전에도 없고 어문 규정에도 근거가 없는 채로 원문의
    공백을 지워버리는(두 단어를 붙여버리는) 것을 되돌린다.

    "그만하려고 합니다"(-려고 하다: 의도를 나타내는 본동사 구성, 제47항
    보조 용언 붙임 허용 대상이 전혀 아니라 항상 띄어 써야 함)를 kiwi가
    "그만하려고합니다"로 붙여버리는 사고에서 발견함. _protect_unfounded_
    respacing()은 kiwi가 "근거 없이 새로 공백을 끼워 넣는 것"만 막고
    있었고, "근거 없이 있던 공백을 지워버리는 것"은 전혀 막지 못하고
    있었다 — 이 함수가 그 반대 방향을 담당한다.

    두 토큰 사이에 공백이 정확히 하나 있던 단순한 경우만 다루고(다른
    요인이 섞인 복잡한 경우는 판단을 보류), 합친 형태가 사전에 실제로
    등재되어 있을 때만(word_exists) kiwi의 판단을 신뢰해 그대로 둔다.

    두 토큰 사이 "간격"만 위치 기반으로 확인한다(표면형을 이어붙여
    비교하지 않는다) — '합니다'처럼 어간(하)과 다음 형태소(ᆸ니다)가 받침
    하나를 공유해 표면형과 실제 글자가 어긋나는 kiwi 특성(제41항 관련
    로직에서도 이미 확인됨) 때문에, 표면형 재구성 비교는 이런 경우를
    엉뚱하게 걸러내 버린다."""
    tokens = _kiwi.tokenize(text)
    to_restore = []
    for pos, insert_at in _removed_space_points(text, suggested):
        before, after = _straddling_tokens(tokens, pos)
        if before is None or after is None:
            continue
        if text[before.start + before.len : after.start] != " ":
            continue
        if before.form == "안" and after.lemma == "되다":
            # "안 되다"(금지: ~면 안 돼)와 "안되다"(상황이 안 됨: 농사가 안돼)는
            # 같은 형태인데 띄어쓰기가 완전히 반대다. kiwi.space()는 이 둘을
            # 구분하지 못하고 불규칙하게 제안한다(농사가 안돼→안 돼, 테드, 안 돼→안돼).
            # _andoeda_forces_split가 금지 구성(-면/-거든 등)을 확실히 잡으면
            # 그 경우만 띄어쓰기를 강제하고, 나머지는 원문의 띄어쓰기를 보존해
            # 사람이 최종 판단하게 한다 — "애매하면 자동 수정하지 않는다" 원칙.
            if _andoeda_forces_split(tokens, after):
                to_restore.append(insert_at)  # 금지 구성 확정 -> 항상 띄어씀
            else:
                to_restore.append(insert_at)  # 애매함 -> 원문 보존 (사람 확인)
            continue
        if before.tag.startswith("J") and after.tag == "VX":
            # 한글 맞춤법 제47항 단서: **앞말에 조사가 붙으면** 그 뒤의 보조 용언은
            # 띄어 쓴다(붙임 허용 대상이 아니다). kiwi.space()는 '보기만 해도'를
            # '보기만해도'로 붙이자고 제안했는데, '만'이 조사이므로 규정상 불가다
            # (2026-08-02 실사용 보고). 사전 조회 이전에 규정으로 걸러낸다.
            to_restore.append(insert_at)
            continue
        if before.tag == "NNG" and after.lemma == "받다" and (
            _is_action_noun(before.form) or before.form in _PASSIVE_ONLY_BATDA_NOUNS
        ):
            continue  # 동작성 명사+받다(접사) -> "호출받다"처럼 사전 미등재라도 항상 붙여씀
        # before가 연결어미(EC)면 어간까지 포함한 실제 용언 표면형으로 확인한다
        # (예: '싶어 하다'의 before는 '어'뿐이라, '어'+'하다'='어하다'라는 무관한
        # 표제어와 우연히 겹쳐 근거 없는 결합을 정당한 것으로 오인한다 — '집→지브'
        # 사고와 같은 유형. 어간을 붙여 '싶어'+'하다'='싶어하다'로 검사해야 맞다).
        before_part = before.form
        if before.tag == "EC":
            before_idx = _token_index(tokens, before)
            stem = tokens[before_idx - 1] if before_idx and before_idx >= 1 else None
            if stem is not None and stem.tag.startswith("V") and stem.start < before.start:
                before_part = text[stem.start : before.start + before.len]
        elif before.tag.startswith("V"):
            before_part = before.lemma
        after_part = after.lemma if after.tag.startswith("V") else after.form
        joined_form = before_part + after_part
        if not word_exists(joined_form) or not is_contemporary_general_word(joined_form):
            # 사전에 있어도 그 표제어가 역사·방언 같은 특수 분야에만 있으면 현대
            # 문장을 붙여 쓸 근거가 못 된다('오고하다' = 五考하다, 역사).
            to_restore.append(insert_at)

    for insert_at in sorted(to_restore, reverse=True):
        suggested = suggested[:insert_at] + " " + suggested[insert_at:]
    return suggested


# "안"(부정 부사)+"되다"는 뜻이 갈리는 두 가지 서로 다른 구성이다 —
# "안되다"(형용사/동사, 하나의 단어: 상황이 좋지 않다·훌륭하게 되지 못하다
# 등, 예: "공부가 안된다")와 "안 되다"(부정 부사 "안"+동사 "되다": 허용·
# 가능하지 않다, 예: "~하면 안 됩니다")는 사전 등재 여부만으로는 구분할 수
# 없다(§20 실사용 버그). 다만 "-면"/"-거든"/"-아서는/-어서는" 같은 조건·전제
# 어미로 이어지는 절 안에 오는 "안 되다"는 사실상 예외 없이 금지·불가
# 구성이므로, 이 경우만 확실한 문법적 근거로 삼아 항상 띄어 쓰도록 강제한다.
# 그 외의 경우(예: "공부가 안된다")는 이 신호가 없으므로 기존 사전 등재
# 판단(항상 붙임)을 그대로 따른다 — 확신이 없는 나머지 경우까지 추정으로
# 판단하지 않는다.
_CONDITIONAL_EC_FORMS = {"면", "거든", "다면", "라면"}


# 2026-07-21 발견: "그렇게 하시면 결과가 안됩니다"처럼 조건 어미와 "안" 사이에
# 주어 등 다른 어절이 끼면, 조건 어미가 "안" 바로 앞 토큰인지만 보는 인접
# 검사가 신호를 놓친다. 그 사이에 오는 어절이 체언(+조사)·부사뿐이고 중간에
# 용언 어간·다른 종결/연결 어미·문장부호가 없으면 여전히 같은 절 안이라고
# 안전하게 볼 수 있으므로, 그 범위까지는 뒤로 훑어 조건 어미를 찾는다.
# 용언 어간이나 다른 어미는 그 자체로 끝나는 형태소가 없어 walk가 그 어미
# 토큰에서 먼저 멈추므로 별도로 막지 않아도 안전하다 — 처음 만나는 EC가
# 조건형이 아니면 그 자리에서 탐색을 끝낸다(더 앞쪽의 조건 어미는 다른 절에
# 속하므로 무시).
_INTERVENING_TAGS = {
    "NNG", "NNP", "NNB", "NR", "SN", "XSN",
    "JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC",
    "MAG",
}


_MAX_CONDITIONAL_LOOKBACK = 5


def _conditional_marker_before(tokens, start_idx: int):
    """start_idx부터 뒤로 훑어, 같은 절 안에서 처음 만나는 어미(EC) 토큰을
    돌려준다. 체언·조사·부사(_INTERVENING_TAGS)는 건너뛰고, 그 외 태그나
    탐색 범위(_MAX_CONDITIONAL_LOOKBACK)를 넘으면 None을 돌려준다."""
    i = start_idx
    steps = 0
    while i >= 0 and steps < _MAX_CONDITIONAL_LOOKBACK:
        token = tokens[i]
        if token.tag == "EC":
            return token
        if token.tag not in _INTERVENING_TAGS:
            return None
        i -= 1
        steps += 1
    return None


def _andoeda_forces_split(tokens, after) -> bool:
    """after가 '되다'(그 직전이 부정 부사 '안')일 때, 그 앞 절이 조건·전제
    어미로 이어지는 금지 구성인지 확인한다."""
    idx = _token_index(tokens, after)
    if idx is None or idx < 2:
        return False
    if tokens[idx - 1].form != "안" or tokens[idx - 1].tag != "MAG":
        return False
    marker = _conditional_marker_before(tokens, idx - 2)
    if marker is None:
        return False
    return marker.form in _CONDITIONAL_EC_FORMS or marker.form.startswith(("어서", "아서"))


def _protect_unfounded_respacing(text: str, suggested: str) -> str:
    """kiwi.space()가 사전에도 없고 어문 규정에도 근거가 없는 채로 공백을
    새로 끼워 넣자고 제안하는 경우를 되돌린다. 다섯 가지를 막는다:

    0. kiwi 자신의 tokenize()가 이미 하나의 형태소로 본 토큰 내부에 공백을
       넣는 것 — tokenize()와 space()가 서로 다른 모델이라 어긋난 경우고,
       kiwi 스스로도 확신이 없다는 신호이므로 근거 확인 없이 되돌린다.
    1. 고유명사(NNP) 토큰 경계를 갈라놓는 것 (예: '연실' -> '연 실') —
       kiwi가 모르는 이름일 뿐, 원래 하나의 토큰으로 붙어 있던 걸 갈라야
       한다는 근거가 없다.
    2. 표준국어대사전/우리말샘에 이미 붙여 쓴 형태로 등재된 경우 (예:
       '한잔하다', '탄두리치킨') — 사전이 kiwi의 통계적 추정보다 권위
       있는 근거다. correct_compound_spacing()의 명사 합성어 전용 처리를
       모든 품사 조합으로 일반화한 버전이다.
    3. '/' 바로 뒤, 또는 '[이름/상황]' 형태의 자막 브래킷 표기 안 — 이건
       실제 문장이 아니라 관례적 메타 표기라 한글 맞춤법이 다루는 대상이
       아니다. "'/' 뒤에 띄어 쓴다"는 규정 자체가 존재하지 않는다.
    4. 전문 용어·고유명사·편제 번호 성격의 토큰끼리(_TERM_COMPOUND_TAGS)
       원래 붙어 있던 경우 (예: '제505공수보병연대원', '폭파병', 'E중대',
       '2대대', '20만') — 제49항/제50항이 이미 붙여쓰기를 허용하므로,
       사전에 그 정확한 조합이 없다는 것만으로는 갈라야 할 근거가 안 된다.
    """
    brackets = _bracket_spans(text)
    tokens = None
    to_remove = []  # suggested 상에서 지울 (j1, j2) 목록
    for i1, j1, j2 in _inserted_space_ranges(text, suggested):
        if _inside_any_span(i1, brackets) or (i1 > 0 and text[i1 - 1] == "/"):
            to_remove.append((j1, j2))
            continue
        if tokens is None:
            tokens = _kiwi.tokenize(text)
        if _token_containing(tokens, i1) is not None:
            to_remove.append((j1, j2))
            continue
        before, after = _straddling_tokens(tokens, i1)
        if before is None or after is None:
            continue
        if _tokenization_unstable_near(tokens, before, after):
            to_remove.append((j1, j2))
            continue  # kiwi 자신도 이 구간의 형태소 경계를 확신하지 못함 -> 원문 보존
        if before.tag == "NNP" or after.tag == "NNP":
            to_remove.append((j1, j2))
            continue
        if before.tag in _TERM_RUN_TAGS and after.tag in _TERM_RUN_TAGS:
            # _TERM_COMPOUND_TAGS가 아니라 어근(XR)·명사 파생 접미사(XSN)까지
            # 포함한 _TERM_RUN_TAGS로 본다. 이 둘이 빠져 있으면 '만성골수성백혈병'을
            # '만성골수성 백혈병'으로, '강력팀'을 '강력 팀'으로 갈라 놓자는 제안이
            # 보호를 못 받고 그대로 나간다 — 전문 용어는 붙이려면 전부 붙여야 하므로
            # (제50항) 이건 규정에 어긋나는 부분 붙임을 사람에게 권하는 셈이 된다.
            # XR·XSN은 어차피 앞말과 항상 붙는 형태소라 이 자리에 공백이 들어갈
            # 근거 자체가 없다.
            to_remove.append((j1, j2))
            continue
        if before.tag in _NUMBER_SYMBOL_TAGS and after.tag in _NUMBER_SYMBOL_TAGS:
            to_remove.append((j1, j2))
            continue  # "80%" 같은 숫자+기호 표기 관례 (사전 등재 여부와 무관)
        if before.form == "안" and after.lemma == "되다" and _andoeda_forces_split(tokens, after):
            continue  # 금지 구성 확정 -> 이 공백 삽입은 정답이므로 되돌리지 않는다
        if before.tag.startswith("J") and after.tag == "VX":
            # 한글 맞춤법 제47항 단서: **앞말에 조사가 붙으면** 그 뒤의 보조 용언은
            # 띄어 쓴다(붙임 허용 대상이 아니다). 이 함수가 다루는 건 kiwi가
            # **넣자고** 한 공백이므로, 이 자리의 삽입은 규정상 정답이다 — 되돌리지
            # 않고 그대로 둔다('보고는싶다' -> '보고는 싶다'). 바로 위 '안 되다'
            # 분기와 같은 처리다.
            #
            # 반대 방향(kiwi가 '보기만 해도'를 '보기만해도'로 붙이자고 하는 경우)은
            # _protect_unfounded_joining()이 막는다. 2026-08-02에 그 규칙을 이 함수에도
            # 넣으면서 저쪽 함수의 변수 이름(to_restore/insert_at)을 그대로 옮겨 적어
            # 이 분기가 NameError로 터졌다 — 조사+보조용언을 붙여 쓴 줄('알고는있다')
            # 하나가 파일 전체 교정을 무너뜨렸다. 2026-08-02 발견·수정.
            continue
        if before.tag == "NNG" and after.lemma == "받다" and (
            _is_action_noun(before.form) or before.form in _PASSIVE_ONLY_BATDA_NOUNS
        ):
            to_remove.append((j1, j2))
            continue  # 동작성 명사+받다(접사) -> "호출받다"처럼 사전 미등재라도 항상 붙여씀
        if before.tag == "NNG" and after.lemma == "드리다" and is_honorific_drida_affix(before.form):
            to_remove.append((j1, j2))
            continue  # 동작성 명사+드리다(접미사) -> '부탁드리다'는 미등재라도 붙여 쓴다
        if after.form == "요" and after.len == 1:
            to_remove.append((j1, j2))
            continue  # 존대 보조사 "요" — _mechanical_respace()와 같은 이유로 항상 보호한다
            # (kiwi가 관형사 등으로 잘못 태깅해도, 원문에 이미 붙어 있었다면 그대로 둔다)
        if after.tag in _ATTACH_TAGS or registered_ending(after.form):
            to_remove.append((j1, j2))
            continue  # 조사·어미(EF뿐 아니라 EC 등 _ATTACH_TAGS 전체)는 제41항에 따라
            # 항상 앞말에 붙는다(_mechanical_respace()와 같은 원칙) — "같잖아요"
            # ("같"+"지"+"않"+"어요"가 "잖"이라는 축약된 한 글자로 압축되는 kiwi
            # 특성 때문에 tokenize()와 space()가 서로 다른 경계를 봄)처럼 앞
            # 형태소가 축약되어 있어도 갈라놓을 근거는 없다. kiwi가 태그를 다르게
            # 매길 가능성에 대비해, "-form"이 사전에 등재된 어미·접사 표제어인지도
            # 함께 확인한다(registered_ending — kiwi 태그가 아니라 사전 표제어
            # 자체를 최종 근거로 삼는다).
        # 용언(동사/형용사) 토큰은 표면형이 어간뿐이라(예: '하다가'의 '하'),
        # 사전 기본형(lemma)으로 합쳐야 '한잔하다' 같은 등재된 복합동사를
        # 알아볼 수 있다. '한잔'+'하'로는 사전에 없지만 '한잔'+'하다'는 있음.
        # 간격 확인은 표면형을 이어붙여 비교하지 않는다 — '잘해야'(잘+하다의
        # 활용형 '해')처럼 어간과 어미가 받침/음절을 공유해 표면형과 실제
        # 글자가 어긋나는 kiwi 특성(제41항 관련 로직에서도 이미 확인됨)
        # 때문에, 표면형 재구성 비교는 이런 경우를 엉뚱하게 걸러내 버린다.
        # 대신 두 토큰이 실제로 빈틈없이 맞닿아 있는지만 위치로 확인한다.
        if before.start + before.len != after.start:
            continue
        # before가 연결어미(EC)이고 그 앞에 어간이 바로 붙어 있으면(예:
        # '기어다니다'의 '기'+'어', '데려다주다'의 '데리'+'어다'), EC 하나만
        #으로는 사전 표제어와 비교할 수 없다 — 어간까지 포함한 실제 표면형
        # ('기어', '데려다')을 써야 correct_aux_verb_spacing() 패턴 1과 같은
        # 방식으로 후보를 만들 수 있다. lemma가 아니라 표면형을 쓰는 이유는
        # '기다'+'어'='기어'처럼 축약된 실제 표기를 그대로 보존해야 하기
        # 때문이다(어간 lemma를 쓰면 '기다다니다'처럼 없는 말이 된다).
        before_part = before.form
        if before.tag == "EC":
            # 어간과 어미가 받침/음절을 공유해 위치가 살짝 겹치는 경우
            # ('데리'+'어다'='데려다'처럼 어간의 끝과 EC의 시작 위치가
            # 정확히 맞닿지 않는 경우도 있음)까지 잡기 위해, 토큰 목록
            # 상의 순서(바로 이전 토큰)로 어간을 찾는다 — 위치 비교
            # (_straddling_tokens)는 겹치는 경우 엉뚱한 토큰을 찾아온다.
            before_idx = _token_index(tokens, before)
            stem = tokens[before_idx - 1] if before_idx and before_idx >= 1 else None
            if stem is not None and stem.tag.startswith("V") and stem.start < before.start:
                before_part = text[stem.start : before.start + before.len]
        elif before.tag.startswith("V"):
            before_part = before.lemma
        after_part = after.lemma if after.tag.startswith("V") else after.form
        if word_exists(before_part + after_part):
            to_remove.append((j1, j2))

    for j1, j2 in sorted(to_remove, key=lambda r: r[0], reverse=True):
        suggested = suggested[:j1] + suggested[j2:]
    return suggested


def _protect_headword_run_splits(text: str, suggested: str) -> str:
    """kiwi.space()가 사전 표제어(용언 포함) '내부'에 공백을 끼워 넣는 경우를
    되돌린다. _protect_unfounded_respacing()의 사전 검사는 공백을 사이에 둔 두
    토큰만 이어 보므로, '껄쩍지근하다'(방언 형용사)처럼 여러 형태소에 걸친
    표제어를 '껄쩍 지근하게'로 쪼개는 것을 놓친다. 여기서는 공백이 끼워진
    지점을 포함하는 한글 런 전체를 사전과 대조한다 — 사전이 kiwi의 통계적
    추정보다 권위 있는 근거다."""
    to_remove = []
    for i1, j1, j2 in _inserted_space_ranges(text, suggested):
        run_start, run_end = _hangul_run_bounds(text, i1)
        run = text[run_start:run_end]
        if len(run) < 2:
            continue
        if word_exists(run):
            to_remove.append((j1, j2))
            continue
        run_tokens = _kiwi.tokenize(run)
        if not run_tokens:
            continue
        # 용언이면 마지막 어미를 떼고 기본형(어간+다)으로 사전을 확인한다.
        if run_tokens[-1].tag.startswith("E"):
            stem = run[: run_tokens[-1].start]
            if len(stem) >= 2 and word_exists(stem + "다"):
                to_remove.append((j1, j2))
                continue
        # 체언이면 뒤에 붙은 조사를 떼고 다시 확인한다. 런은 어절 단위라 조사가
        # 붙어 있으면("짬짜면을") 표제어 조회가 실패한다 — 2026-08-02 실사용에서
        # `word_exists('짬짜면')`이 참인데도 '짬 짜면을'로 쪼개자는 제안이 나갔다.
        if run_tokens[-1].tag.startswith("J"):
            body = run[: run_tokens[-1].start]
            if len(body) >= 2 and word_exists(body):
                to_remove.append((j1, j2))
    for j1, j2 in sorted(to_remove, key=lambda r: r[0], reverse=True):
        suggested = suggested[:j1] + suggested[j2:]
    return suggested


def _dictionary_backed(piece: str) -> bool:
    """조각이 사전으로 뒷받침되는 말인지 — 표제어이거나, 조사·어미를 떼면 표제어인지.

    한 글자 조각은 판정하지 않고 통과시킨다(조사·의존명사·관형사 등 한 글자 말이
    많아 여기서 막으면 정당한 분리까지 취소된다).
    """
    piece = piece.strip()
    if len(piece) <= 1:
        return True
    if word_exists(piece):
        return True
    tokens = _kiwi.tokenize(piece)
    if not tokens:
        return True
    tail = tokens[-1]
    body = piece[: tail.start]
    if body and tail.tag.startswith("J"):  # 체언 + 조사
        if word_exists(body):
            return True
    if body and tail.tag.startswith("E"):  # 용언 어간 + 어미
        if word_exists(body + "다"):
            return True
    if body:
        # 표면형으로 잘라 조회했는데 사전에 없다면, 그 조각은 사전으로 설명되지
        # 않는 것이다. 여기서 첫 형태소로 다시 봐주면 '짓골에'가 '짓'(표제어)
        # 때문에 통과해 버려 이 규칙 자체가 무력해진다(2026-08-02 실측).
        return False
    # 표면형으로 자를 수 없는 활용(어간과 어미가 받침을 공유하는 '됩니다' 등)만
    # 첫 형태소의 기본형으로 확인한다. 이 갈래가 없으면 '안 됩니다' 같은 정당한
    # 분리 제안까지 "근거 없음"으로 취소된다(실측에서 3건 깨졌다).
    head = tokens[0]
    lemma = head.lemma or head.form
    if head.tag.startswith(("V", "XSV", "XSA")):
        return bool(word_exists(lemma if lemma.endswith("다") else lemma + "다"))
    return bool(word_exists(lemma))


def _protect_unresolvable_splits(text: str, suggested: str) -> str:
    """분리해서 생기는 조각이 사전으로 설명되지 않으면 그 분리를 되돌린다.

    2026-08-02 실사용에서 사극 지명 '한짓골'이 '한 짓골'로 쪼개졌다. '한'은
    관형사로 태깅돼 기존 보호(_TERM_COMPOUND_TAGS)에서 빠졌고, '한짓골'은 사전에
    없어 표제어 보호에도 걸리지 않았다. 그런데 **쪼갠 결과인 '짓골'도 사전에
    없다** — 즉 이 분리는 어느 쪽으로도 사전 근거가 없다.

    원문이 붙어 있었다는 사실이 유일한 근거라면, 근거 없이 갈라놓는 것보다
    그대로 두는 편이 이 프로젝트의 원칙에 맞는다("확실한 것만 자동 처리, 애매하면
    사람에게"). 분리 후 조각이 전부 사전으로 설명될 때만 제안을 남긴다.
    """
    # 한 어절이 여러 번 쪼개질 수 있으므로(먹을수있다 -> 먹을 / 수 / 있다) 삽입
    # 지점을 어절별로 모아 **최종 조각 전체**를 본다. 삽입 하나만 놓고 좌우를
    # 판정하면 '수있다' 같은 중간 상태를 사전에 조회하게 되어 정당한 제안까지
    # 취소된다(2026-08-02 첫 시도에서 실제로 그렇게 깨졌다).
    by_run: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for i1, j1, j2 in _inserted_space_ranges(text, suggested):
        start, end = _hangul_run_bounds(text, max(0, i1 - 1))
        if not (start < i1 < end):
            continue  # 어절 경계에 넣는 공백은 이 규칙의 대상이 아니다
        by_run.setdefault((start, end), []).append((i1, j1, j2))

    to_remove = []
    for (start, end), points in by_run.items():
        cuts = sorted(p[0] for p in points)
        pieces = [text[a:b] for a, b in zip([start] + cuts, cuts + [end])]
        if not all(_dictionary_backed(piece) for piece in pieces):
            to_remove.extend((j1, j2) for _i1, j1, j2 in points)
    for j1, j2 in sorted(to_remove, key=lambda r: r[0], reverse=True):
        suggested = suggested[:j1] + suggested[j2:]
    return suggested


def check_spacing(index: int, text: str) -> FlagItem | None:
    """띄어쓰기 제안은 신뢰도를 알 수 없으므로 절대 자동 적용하지 않고
    원문과 다르면 무조건 사람 확인용으로 플래그한다 (예: '한번'/'한 번'처럼
    문맥에 따라 정답이 갈리는 경우 잘못 우겨서 고치는 걸 막기 위함)."""
    suggested = _kiwi.space(text)

    # kiwi는 사전에 등재된 합성어를 모르는 경우가 있어(예: '노천카페', '그때',
    # '쓴맛'), 이미 correct_compound_spacing()이 사전 근거로 확정 붙여쓰기한
    # 부분을 다시 갈라놓자고 제안할 수 있다. 확정된 합성어는 사전이 kiwi보다
    # 권위 있는 근거이므로, kiwi의 제안에서 그 부분만 원상복구해 오탐지를 막는다.
    for start, boundary, end in _compound_candidate_spans(text):
        tail = text[boundary:end].lstrip(" ")
        combined = text[start:boundary] + tail
        if text[start:end] != combined:
            continue  # 이미 떨어져 있으면 합성어 자동 교정 대상이 아니었음
        if compound_status(combined) == "합성어":
            spaced = text[start:boundary] + " " + tail
            suggested = _force_span(suggested, combined, spaced)

    suggested = _normalize_aux_verb_spacing(text, suggested)
    suggested = _protect_unfounded_respacing(text, suggested)
    suggested = _protect_headword_run_splits(text, suggested)
    suggested = _protect_unfounded_joining(text, suggested)
    suggested = _protect_unresolvable_splits(text, suggested)
    suggested = _protect_cheo_prefix_gap(text, suggested)
    suggested = _protect_cheo_prefix_split(text, suggested)
    suggested = _protect_myeoch_number_spacing(text, suggested)
    # 구두점 앞 공백은 어떤 경우에도 제안하지 않는다(문맥 무관 규칙).
    suggested = _strip_space_before_punctuation(suggested)

    if suggested != text:
        return FlagItem(
            line_index=index,
            original_text=text,
            reason="띄어쓰기 확인 필요 (문맥에 따라 정답이 다를 수 있음)",
            suggested_fix=suggested,
        )
    return None


def _protect_myeoch_number_spacing(text: str, suggested: str) -> str:
    """'몇' + 수사(몇만·몇백만·몇십) 자리의 원문 표기를 그대로 지킨다.

    `docs/BACKLOG.md` 4번을 조사한 결과다. 이 자리는 **사전으로 갈리지 않는다** —
    `몇만`·`몇십`·`몇백`·`몇천`·`몇억`·`몇백만`이 표준국어대사전·우리말샘에
    **전부 미등재**인데(반면 접두사 '수-' 파생어 `수만`·`수백만`·`수십만`은 등재),
    그렇다고 갈라 써야 한다는 근거도 없다. 한글 맞춤법 제44항은 "수를 적을 적에는
    만 단위로 띄어 쓴다"로 수의 자릿수 띄어쓰기를 정한 조항이라 '몇'과 수사의
    결합 문제를 직접 답하지 않는다(2026-08-04 조사).

    그런데도 kiwi는 붙여 쓴 `몇만 원`을 `몇 만 원`으로 갈라 쓰자고 제안했다.
    근거는 토큰 경계뿐이다 — 이 프로젝트에서 자동 교정도 제안도 하지 않기로 한
    부류다(사전 근거 없이 임의 판단 금지). 어느 쪽이 맞는지는 '몇'이 정확한 수를
    묻는 의문인지 막연한 큰 수인지에 달렸고, 그건 텍스트만으로 가릴 수 없다.

    그래서 **원문 표기를 그대로 둔다** — 붙여 썼으면 붙인 채로, 띄어 썼으면 띄운
    채로. 근거 없는 제안을 지우는 것이므로 원문을 바꾸지 않는다.
    """
    tokens = _kiwi.tokenize(text)
    for i in range(len(tokens) - 1):
        myeoch, number = tokens[i], tokens[i + 1]
        if myeoch.form != "몇" or number.tag != "NR":
            continue
        gap = text[myeoch.start + myeoch.len : number.start]
        if gap not in ("", " "):
            continue
        original = text[myeoch.start : number.start + number.len]
        other = original.replace(" ", "") if gap == " " else f"{myeoch.form} {number.form}"
        suggested = _force_span(suggested, original, other)
    return suggested


def _protect_cheo_prefix_gap(text: str, suggested: str) -> str:
    """'쳐 하든가'의 공백을 그냥 없애자는 제안을 되돌린다.

    이 자리는 접두사 '처-'를 쓸 자리일 수 있어(처하다) 표기가 '쳐'냐 '처'냐부터
    갈린다. 그 판단은 check_intensive_prefix_cheo()가 근거와 함께 사람에게 묻는다 —
    여기서 '쳐하든가'를 함께 제안하면 서로 어긋나는 제안 두 개가 리포트에 남는다
    (2026-08-03 사용자 보고 처리 중 발견).
    """
    tokens = _kiwi.tokenize(text)
    for i in range(len(tokens) - 2):
        found = _cheo_prefix_candidate(text, tokens, i)
        if not found:
            continue
        start, verb_start, _joined, _tag = found
        if not text[start:verb_start].endswith(" "):
            continue  # 원문이 이미 붙어 있으면 되돌릴 것이 없다
        word_end = text.find(" ", verb_start)
        if word_end == -1:
            word_end = len(text)
        verb_word = text[verb_start:word_end]
        suggested = _force_span(suggested, "쳐 " + verb_word, "쳐" + verb_word)
    return suggested


def _protect_cheo_prefix_split(text: str, suggested: str) -> str:
    """'처맞고'를 '처 맞고'로 갈라놓자는 제안을 되돌린다.

    '처-'는 '마구/함부로'의 뜻을 더하는 접두사이므로 뒤 용언에 붙여 쓴다(사전이
    처-먹다·처-넣다처럼 하이픈으로 표시한다). 파생어가 사전에 없어도(처맞다는 미등재)
    접두사 결합이라 띄어 쓸 근거가 없다 — kiwi는 이 '처'를 명사(NNG)로 읽어 뒤 용언과
    가르자고 제안한다(2026-08-03 사용자 보고: '처맞고 들어오는 것보다…').
    """
    tokens = _kiwi.tokenize(text)
    for i in range(len(tokens) - 1):
        head, verb = tokens[i], tokens[i + 1]
        if head.form not in ("처", "쳐") or head.tag not in ("NNG", "NNP"):
            continue
        if verb.tag not in ("VV", "VA", "VX"):
            continue
        if head.start + head.len != verb.start:
            continue  # 원문에서 이미 떨어져 있으면 이 규칙의 대상이 아니다
        word_end = text.find(" ", verb.start)
        if word_end == -1:
            word_end = len(text)
        joined = text[head.start:word_end]
        suggested = _force_span(suggested, joined, head.form + " " + text[verb.start:word_end])

    # kiwi가 '쳐맞고'를 '치'(VV)+'어'(EC)+'맞'(VV)으로 읽는 경우도 같은 자리다.
    # 위 갈래는 '처/쳐'가 명사로 태깅될 때만 걸린다.
    for i in range(len(tokens) - 2):
        found = _undocumented_cheo_derivative(text, tokens, i)
        if not found:
            continue
        start, verb_start, _joined = found
        word_end = text.find(" ", verb_start)
        if word_end == -1:
            word_end = len(text)
        suggested = _force_span(
            suggested, text[start:word_end], "쳐 " + text[verb_start:word_end]
        )
    return suggested
