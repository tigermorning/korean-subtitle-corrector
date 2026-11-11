"""낱말 목록이 아니라 부류 전체를 보는 장치(2026-11-11, `docs/IMPLEMENTATION_LOG.md` §105).

- 어미 없이 끝난 용언 어간(문법 부류): '되'는 '돼' 자동, 다른 어간은 표시.
- 표준국어대사전이 '→ 다른 어미'로 넘겨주는 어미(사전 조회): 자동, 뒤에 '?'면 표시.
- 붙여 쓴 '명사+용언'의 자모 하나 차이 오기(사전 조회): 제안만.

이 파일은 §105 검증표를 옮긴 것이다 — 표에 없는 사례가 나오면 표부터 고친다.
어간 검사는 kiwi만 쓰고, 나머지는 실시간 사전 API를 부른다.
"""
import pytest

from subtitle_corrector.dictionary import ending_redirect, one_syllable_headword_variant
from subtitle_corrector.engine import (
    check_bare_stem,
    check_ending_redirect_question,
    check_glued_noun_predicate,
    correct_doe_dwae,
    correct_ending_redirect,
    correct_entries,
)
from subtitle_corrector.parsers import SubtitleEntry


# --- 어간 부류: '되' 자동 교정 ---------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("그러면 안되", "그러면 안돼"),
        ("너는 왜 안 되", "너는 왜 안 돼"),
        ("선생님이 되", "선생님이 돼"),
        ("이 정도면 되", "이 정도면 돼"),
        ("그렇게 하면 되.", "그렇게 하면 돼."),
        ("이게 말이 되?", "이게 말이 돼?"),
        ("잘 되!", "잘 돼!"),
        ("안 되. 그만해", "안 돼. 그만해"),
        ("다 됬어", "다 됐어"),
        ("잘 됬다", "잘 됐다"),
        ("됬나요", "됐나요"),
        ("안됬네", "안됐네"),
        ("그러면 되요", "그러면 돼요"),
        ("안 되요", "안 돼요"),
        ("거기 가면 되요?", "거기 가면 돼요?"),
        ("잘 되서 다행이야", "잘 돼서 다행이야"),
        ("의사가 되서", "의사가 돼서"),
        ("못되서", "못돼서"),
    ],
)
def test_doe_dwae_fixed(text, expected):
    corrected, notes = correct_doe_dwae(text)
    assert corrected == expected
    assert notes  # 고쳤으면 로그가 있어야 한다(edit_guard가 로그로 재구성한다)


@pytest.mark.parametrize(
    "text",
    [
        "쌀 한 되", "쌀 두 되.", "그럼 되지", "되고 싶어", "되면 좋겠다", "되다",
        "말은 하되", "친구이되", "돈은 주되",  # 연결 어미 '-되'
        "안 되...", "안되~",  # 끊긴 대사
        "글자는 '되'", "다 됐어", "다 되었다", "돼요", "되지요", "되세요", "잘 되셔서",
        "되어요", "되어서", "한 되서 두 되로", "안 돼",
    ],
)
def test_doe_dwae_left_alone(text):
    assert correct_doe_dwae(text) == (text, [])


# --- 어간 부류: '되' 말고는 표시만 ----------------------------------------

@pytest.mark.parametrize("text", ["이거 먹", "이제 그만 쉬", "내가 하", "나도 할 수 있"])
def test_bare_stem_flagged(text):
    flag = check_bare_stem(1, text)
    assert flag is not None
    assert flag.suggested_fix == ""  # 무엇이 빠졌는지 모르므로 제안하지 않는다


@pytest.mark.parametrize(
    "text",
    [
        "그러면 안되",  # '되'는 자동 교정 쪽
        "안/않", "보조 용언 '않'",  # 낱말 언급
        "그만 가", "잘 자", "빨리 와", "됐어 됐어", "말은 하되", "이제 그만 쉬...",
        "여기 서", "자 이제 가자", "민지야 일어나", "그건 아니", "날 믿어", "좀 쉬어",
    ],
)
def test_bare_stem_not_flagged(text):
    assert check_bare_stem(1, text) is None


# --- 사전이 넘겨주는 어미 --------------------------------------------------

def test_ending_redirect_lookup():
    assert ending_redirect("ㄹ께") == "ㄹ게"  # 표준국어대사전 100390 "→ -ㄹ게."
    assert ending_redirect("을께") == "을게"  # 262165 "→ -을게."
    assert ending_redirect("구만") == "구먼"  # 394115 "→ -구먼." (명사 '구만'은 하이픈 없음)
    assert ending_redirect("든") is None  # '-든'에 표준 동형어('-든지'의 준말)가 있다
    assert ending_redirect("든가") is None
    assert ending_redirect("ㄹ게") is None  # 표준 어미


@pytest.mark.parametrize(
    "text, expected",
    [
        ("몇일 뒤에 다시 올께요", "몇일 뒤에 다시 올게요"),
        ("내가 할께", "내가 할게"),
        ("먹을께요", "먹을게요"),
        ("갈께.", "갈게."),
        ("전화할께요", "전화할게요"),
        ("도와줄께", "도와줄게"),
        ("알려 줄께", "알려 줄게"),
        ("나 먼저 갈께 안녕", "나 먼저 갈게 안녕"),
        ("날씨가 좋구만", "날씨가 좋구먼"),
    ],
)
def test_ending_redirect_fixed(text, expected):
    corrected, notes = correct_ending_redirect(text)
    assert corrected == expected
    assert notes


@pytest.mark.parametrize(
    "text",
    [
        "선생님께 드릴게요", "선생님께서 오셨다", "어머님께", "형님께도", "선생님께요",
        "께름칙하다", "다시 올게요", "뭐든 해", "하든가 말든가", "가든지 말든지",
        "구만리 밖에서 왔다", "할께요?",
    ],
)
def test_ending_redirect_left_alone(text):
    assert correct_ending_redirect(text) == (text, [])


def test_ending_redirect_question_is_flag_only():
    flag = check_ending_redirect_question(1, "할께요?")
    assert flag is not None and flag.suggested_fix == ""
    assert check_ending_redirect_question(1, "할께요") is None  # 자동 교정 쪽


# --- 붙여 쓴 '명사+용언'의 자모 하나 차이 오기 -----------------------------

def test_one_syllable_variant_lookup():
    # 음절 하나 차이로는 어김없다·어림없다·어이없다 셋이라 정해지지 않는다 — 자모 하나 차이로 하나.
    assert one_syllable_headword_variant("어의없다", "없다") == "어이없다"
    assert one_syllable_headword_variant("어이없다", "없다") is None  # 이미 표제어


@pytest.mark.parametrize(
    "text, suggested",
    [
        ("어의없네 정말", "어이없네 정말"),
        ("어의없다", "어이없다"),
        ("어의없는 일", "어이없는 일"),
        ("정말어의없네", "정말어이없네"),
        ("어의없었다", "어이없었다"),
    ],
)
def test_glued_noun_predicate_suggested(text, suggested):
    flag = check_glued_noun_predicate(1, text)
    assert flag is not None
    assert flag.suggested_fix == suggested


@pytest.mark.parametrize(
    "text",
    [
        "어의 없이 치료했다", "어의가 없다", "어의 없네", "어이없네", "맛있다", "재미없네",
        "시간없어", "정신없네", "상관없어", "말없이 떠났다", "힘없이 웃었다", "관계없다",
        "쓸데없이 왜 그래", "밥먹자", "물마시고 와", "걱정없어", "문제없어", "의미없어",
        "할말없어", "말없어", "그 사람 말없어", "차없어", "말있어", "눈치없네", "약속있어",
        "생각있어", "이유없이 화내", "기운없어 보여",
    ],
)
def test_glued_noun_predicate_not_flagged(text):
    assert check_glued_noun_predicate(1, text) is None


# --- 파이프라인(실시간 사전 API) -------------------------------------------

def _run(text: str):
    entry = SubtitleEntry(index=1, start="00:00:00,000", end="00:00:02,000", text=text, speaker=None)
    corrected, flags, applied = correct_entries([entry], None, None)
    return corrected[0].text, flags, applied


def test_pipeline_an_dwae_keeps_spacing_flag():
    # '안되다'가 표제어라 띄어쓰기는 문맥에 따라 갈린다 — 확인 필요로 남는 것이 맞다.
    out, flags, applied = _run("그러면 안되")
    assert out == "그러면 안돼"
    assert any(f.suggested_fix == "그러면 안 돼" for f in flags)
    assert any(a.is_edit and a.message == "안되 -> 안돼" for a in applied)


def test_pipeline_eoi_offers_both_readings():
    # 자동으로 고치지 않는다. 오기 제안과 띄어쓰기 제안을 둘 다 보여 사람이 고른다.
    out, flags, _ = _run("어의없네 정말")
    assert out == "어의없네 정말"
    fixes = {f.suggested_fix for f in flags}
    assert "어이없네 정말" in fixes


def test_pipeline_lkke_and_myeochil():
    out, _, _ = _run("몇일 뒤에 다시 올께요")
    assert out == "며칠 뒤에 다시 올게요"


def test_pipeline_euroseo_untouched():
    # 로서/로써는 사전 정보로 앞말의 뜻(자격인가)을 가를 수 없어 규칙을 두지 않는다(§105).
    out, flags, _ = _run("선생님으로써 한 말이야")
    assert out == "선생님으로써 한 말이야"
    assert not any("로서" in f.suggested_fix for f in flags)
