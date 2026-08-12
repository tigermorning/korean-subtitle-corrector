"""비교 대상(arm) 구현. 각 arm은 문장 하나를 받아 교정된 문장을 돌려준다.

    B0  현재 시스템 전체            기준선
    B1  축적 판례 정확 일치만        지금의 검색 방식
    B2a 근거 검색 — 낱말 겹침       비신경 대조군
    B2b 근거 검색 — 문장 임베딩     AI 모델을 쓰는 arm
    B3  로컬 LLM 직접 판정          확률적 대조군

**모든 arm은 같은 인터페이스다**: `run(text) -> (교정문, 근거목록)`. 근거목록이 비면
"근거를 못 댔다"는 뜻이고, 성공 기준 S3(출처 제시율)이 이것을 센다.

B2 계열의 핵심 설계: **모델이 정답을 만들지 않는다.** 모델은 이 문장에 해당하는
판정 규칙을 축적된 근거 중에서 고를 뿐이고, 붙일지 띄울지는 그 근거가 정한다.
프로젝트 최우선 원칙(확률적 추측 금지)을 깨지 않으려는 설계이며, 동시에 판정마다
국립국어원 출처를 댈 수 있게 한다.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from subtitle_corrector.engine import correct_entries  # noqa: E402
from subtitle_corrector.gananda_precedents import check_precedent  # noqa: E402
from subtitle_corrector.parsers import SubtitleEntry  # noqa: E402


# ---------------------------------------------------------------- 근거 지식베이스
#
# `docs/GRAMMAR_PRECEDENTS_TABLE.md`의 판정 규칙을 그대로 옮긴 것이다. 규칙 문구를
# 내가 지어내지 않았다 — 국립국어원 온라인가나다 답변 요지가 원문이고 `qna` 필드에
# 그 글 번호가 있다. **검색이 찾아야 하는 것이 바로 이 항목들이다.**
#
# 이 지식베이스가 PoC의 핵심 재료다. 지금 시스템은 이것을 사람이 읽는 문서로만
# 갖고 있고 판정에 쓰지 못한다(정확 문자열 일치 판례 6건만 쓴다).

@dataclass
class Evidence:
    word: str          # 대상 이중 기능 단어
    verdict: str       # "joined"(붙임) 또는 "spaced"(띄움)
    condition: str     # 이 판정이 적용되는 조건 — 검색이 문장과 대조할 문구
    examples: list     # 국립국어원이 제시한 용례
    qna: str           # 출처

    def cite(self) -> str:
        return f"제42항 {self.word} — {self.condition} ({self.qna})"


KB: list[Evidence] = [
    Evidence("뿐", "joined", "체언이나 부사어 바로 뒤에 오면 조사다. 제한·유일의 뜻이다",
             ["너뿐이다", "실력뿐이다", "셋뿐이야"], "qna_seq=310591"),
    Evidence("뿐", "spaced", "용언의 관형사형 어미 뒤에 오면 의존명사다. '따름'의 뜻이다",
             ["웃을 뿐이다", "들었을 뿐이네", "떨 뿐이었다"], "qna_seq=310591"),
    Evidence("만", "spaced", "명사나 수관형사구 뒤에서 경과한 시간이나 횟수를 뜻하면 의존명사다",
             ["십 년 만의 귀국", "세 번 만에 합격하다"], "mcfaq_seq=6720"),
    Evidence("만", "joined", "제한·한정·조건의 뜻이면 보조사다",
             ["잠만 자다", "사과 하나만 먹었으면", "눈만 감으면"], "mcfaq_seq=6720"),
    Evidence("지", "spaced", "관형사형 뒤에서 그 일이 있었던 때로부터 지금까지의 동안을 뜻하면 "
                            "의존명사다. 자리에 시간·동안·세월을 넣어도 어색하지 않다",
             ["떠난 지 삼 년", "먹은 지 두 시간"], "qna_seq=314315"),
    Evidence("지", "joined", "의문이나 추측을 나타내는 어미 '-ㄴ지'다",
             ["얼마나 지난지 모르겠지만", "큰지 작은지 모르겠다"], "qna_seq=314315"),
    Evidence("차", "joined", "명사 뒤에서 목적을 뜻하면 접미사다",
             ["인사차", "사업차", "연구차", "면접차", "접수차"], "qna_seq=319170"),
    Evidence("차", "spaced", "용언의 관형사형 뒤에서 때나 기회를 뜻하면 의존명사다",
             ["고향에 갔던 차에", "마침 가려던 차였다"], "qna_seq=326715"),
    Evidence("차", "spaced", "기간을 나타내는 명사구 뒤에서 주기나 경과의 해당 시기를 뜻하면 "
                            "의존명사다",
             ["입사 3년 차", "임신 8주 차", "결혼 10년 차"], "qna_seq=309642"),
    Evidence("판", "spaced", "수관형사 뒤에서 승부나 상황을 세는 단위면 의존명사다",
             ["한 판", "두 판을 더 이겨야 한다"], "qna_seq=326715"),
    Evidence("판", "joined", "한 번 벌이는 판이라는 고유한 뜻으로 어휘화된 합성명사다",
             ["한판 잔치를 벌이다"], "qna_seq=326715"),
    Evidence("들", "joined", "명사 바로 뒤에 붙어 복수를 뜻하면 접미사다",
             ["사람들", "학생들"], "qna_seq=325894"),
    Evidence("들", "spaced", "쉼표로 나열된 두 개 이상의 사물 뒤에서 그 밖에 같은 종류가 더 "
                            "있음을 뜻하면 의존명사다. 등(等)으로 바꿀 수 있다",
             ["사과, 배, 감 들을 먹었다"], "qna_seq=325894"),
    Evidence("대로", "spaced", "용언의 관형사형 뒤에 오면 의존명사다",
             ["말한 대로", "본 대로"], "제42항"),
    Evidence("대로", "joined", "체언 뒤에 오면 조사다",
             ["법대로", "약속대로"], "제42항"),
    Evidence("만큼", "spaced", "용언의 관형사형 뒤에 오면 의존명사다",
             ["노력한 만큼", "아는 만큼"], "제42항"),
    Evidence("만큼", "joined", "체언 뒤에 오면 조사다",
             ["너만큼", "산만큼"], "제42항"),
    Evidence("번", "joined", "시도나 기회를 뜻하는 '한번'은 합성어다",
             ["한번 해 보자", "다시 한번"], "표준국어대사전 표제어 '한번'"),
    Evidence("번", "spaced", "횟수를 셀 때는 수관형사 '한'과 의존명사 '번'이다",
             ["딱 한 번 만났다", "두 번 봤다"], "제42항"),
]

# 대상 낱말이 문장 어디에 있는지 찾는 무늬. 붙은 형태와 띄운 형태를 모두 잡는다.
TARGET = {e.word for e in KB}


def find_target(text: str, want: str | None = None) -> tuple[str, int, bool] | None:
    """문장에서 이중 기능 단어를 찾는다. 반환: (낱말, 위치, 지금 붙어 있는가).

    `want`를 주면 그 낱말만 본다. **평가에서는 반드시 준다** — 한 문장에 대상이 둘
    이상 있을 수 있고(`세 번 만에`는 '번'과 '만'이 둘 다 대상이다), 어느 자리를
    재는지가 정해지지 않으면 arm끼리 다른 자리를 고쳐 놓고 비교하게 된다.
    """
    best = None
    for word in ([want] if want else TARGET):
        for m in re.finditer(rf"(\s?){re.escape(word)}", text):
            # 낱말 앞이 문장 첫머리면 판정 대상이 아니다.
            if m.start() == 0:
                continue
            joined = m.group(1) == ""
            pos = m.start()
            if best is None or pos < best[1]:
                best = (word, pos, joined)
    return best


def apply_verdict(text: str, word: str, pos: int, verdict: str) -> str:
    """판정대로 그 자리의 띄어쓰기를 맞춘다. 다른 자리는 건드리지 않는다."""
    m = re.compile(rf"(\s?){re.escape(word)}").match(text, pos)
    if not m:
        return text
    head, tail = text[: m.start()], text[m.start() + len(m.group(1)) :]
    return head + ("" if verdict == "joined" else " ") + tail


# ---------------------------------------------------------------- B0 현재 시스템

def run_b0(text: str, word: str | None = None) -> tuple[str, list[str]]:
    """지금 배포돼 있는 파이프라인 전체. 이것이 기준선이다.

    **답은 자동 교정된 본문이고, 플래그는 근거로만 센다.** 처음에는 플래그의
    `suggested_fix`를 답으로 삼았는데, 그러면 "본문을 안 바꾸고 사람에게 물었다"가
    "이렇게 고쳤다"로 잘못 기록된다(2026-08-12 실측: `술 시켜요`가 §75에서 자동
    교정 대상에서 내려갔는데도 오교정으로 집계됐다). 이 도구가 파일에 실제로 쓰는
    것은 본문이고, 제안은 사람이 고를 때만 반영된다 — 그 차이를 지표가 지켜야 한다.
    """
    entry = SubtitleEntry(index=1, start="", end="", text=text)
    fixed, flags, _notes = correct_entries([entry], doc_type="subtitle")
    why = [f"[제안] {f.suggested_fix} — {f.reason}" for f in flags if f.suggested_fix]
    return fixed[0].text, why


# ---------------------------------------------------------------- B1 정확 일치 판례

def run_b1(text: str, word: str | None = None) -> tuple[str, list[str]]:
    """축적 판례를 **정확 문자열 일치**로만 조회한다. 지금의 검색 방식 그 자체다."""
    found = find_target(text, word)
    if not found:
        return text, []
    word, pos, joined = found
    # 붙인 형태를 만들어 판례에 있는지 본다.
    joined_form = apply_verdict(text, word, pos, "joined")
    m = re.compile(rf"(\s?){re.escape(word)}").match(text, pos)
    span_start = max(0, m.start() - 6)
    query = joined_form[span_start : m.start() + len(word) + 1].strip()
    verdict = check_precedent(query)
    if verdict is None:
        return text, []          # 판례가 없으면 아무것도 못 한다
    return apply_verdict(text, word, pos, "joined" if verdict else "spaced"), [
        f"축적 판례 정확 일치: {query}"
    ]


# ---------------------------------------------------------------- 근거 검색 공통
#
# B2a와 B2b는 **고르는 방법만** 다르다. 후보(같은 낱말의 판정 규칙 2~3개)와 판정을
# 근거가 정한다는 점은 같다. 모델은 "어느 근거가 이 문장에 해당하는가"만 고른다.
#
# 대조 대상을 조건 문구와 용례 **둘 다**로 잡는다. 조건은 문법을 말하고(관형사형 어미
# 뒤 등) 용례는 표면을 보여 주는데, 어느 쪽이 검색에 유효한지가 이 실험의 관심사다.

def candidates(word: str) -> list[Evidence]:
    return [e for e in KB if e.word == word]


def _texts_of(ev: Evidence) -> list[str]:
    return [ev.condition] + ev.examples


def _retrieve(text: str, word: str, scorer) -> tuple[Evidence | None, float]:
    """후보 근거 중 문장과 가장 잘 맞는 것을 고른다. scorer(문장, 근거문구) -> 점수."""
    best, best_score = None, -1.0
    for ev in candidates(word):
        score = max(scorer(text, t) for t in _texts_of(ev))
        if score > best_score:
            best, best_score = ev, score
    return best, best_score


def _run_retrieval(text: str, scorer, want: str | None = None) -> tuple[str, list[str]]:
    found = find_target(text, want)
    if not found:
        return text, []
    word, pos, _joined = found
    ev, score = _retrieve(text, word, scorer)
    if ev is None:
        return text, []
    return apply_verdict(text, word, pos, ev.verdict), [f"{ev.cite()} [유사도 {score:.3f}]"]


# ---------------------------------------------------------------- B2a 낱말 겹침
#
# 저장소에 이미 있는 방식이다(§73 `건초` 판정 — "표준 용어 뜻풀이와의 낱말 겹침").
# 신경망을 쓰지 않으므로 설치할 것도, 내려받을 것도 없다. **임베딩이 이것보다
# 나은지**가 B2b를 만들지 말지를 가른다.

_kiwi_lemmas = None


def _lemmas(s: str) -> set:
    global _kiwi_lemmas
    if _kiwi_lemmas is None:
        from subtitle_corrector.engine.kiwi_adapter import _content_lemmas
        _kiwi_lemmas = _content_lemmas
    try:
        return set(_kiwi_lemmas(s))
    except Exception:
        return set(s.split())


def _overlap(text: str, evidence_text: str) -> float:
    a, b = _lemmas(text), _lemmas(evidence_text)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)          # 자카드 유사도


def run_b2a(text: str, word: str | None = None) -> tuple[str, list[str]]:
    return _run_retrieval(text, _overlap, word)


# ---------------------------------------------------------------- B2b 문장 임베딩
#
# `precedent_search.py`가 쓰는 것과 같은 모델을 쓴다(paraphrase-multilingual-
# MiniLM-L12-v2, Apache 2.0). 그 파일은 이 점수를 "사람에게 보여주기"에만 쓰고 판정에
# 쓰는 것을 금지하는데, 이 PoC가 재는 것이 바로 **그 금지를 풀어도 되는가**이다.

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_model = None
_vec_cache: dict = {}


def _embed(s: str):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    if s not in _vec_cache:
        _vec_cache[s] = _model.encode(s, normalize_embeddings=True)
    return _vec_cache[s]


def _cosine(text: str, evidence_text: str) -> float:
    return float(_embed(text) @ _embed(evidence_text))


def run_b2b(text: str, word: str | None = None) -> tuple[str, list[str]]:
    return _run_retrieval(text, _cosine, word)


# ---------------------------------------------------------------- B3 로컬 LLM
#
# 모델에게 자유 재작성을 시키지 않는다. **후보 근거 중 하나를 고르게** 한다 — 그래야
# B2와 같은 조건에서 비교되고, 판정에 국립국어원 출처가 따라붙는다. 자유 생성은 오늘
# 이미 훼손 22%로 측정된 바 있어(`tools/audit_llm_pass.py`) 이 자리에 쓰지 않는다.

LLM_MODEL = "exaone3.5:7.8b"


def run_b3(text: str, word: str | None = None) -> tuple[str, list[str]]:
    from subtitle_corrector.engine.llm_pass import _chat_cli, normalize_llm_settings

    found = find_target(text, word)
    if not found:
        return text, []
    word, pos, _joined = found
    cands = candidates(word)
    menu = "\n".join(f"{i+1}. {e.condition} (예: {', '.join(e.examples[:2])})"
                     for i, e in enumerate(cands))
    prompt = (f"문장: {text}\n\n"
              f"이 문장에서 '{word}'의 쓰임에 해당하는 것을 아래에서 하나 고르세요.\n"
              f"{menu}\n\n번호만 답하세요.")
    settings = normalize_llm_settings(enabled=True, model=LLM_MODEL, backend="cli")
    if not settings.enabled:
        return text, []
    try:
        reply = _chat_cli(prompt, settings)
    except Exception:
        return text, []
    m = re.search(r"[1-9]", reply)
    if not m:
        return text, []
    idx = int(m.group()) - 1
    if not 0 <= idx < len(cands):
        return text, []
    ev = cands[idx]
    return apply_verdict(text, word, pos, ev.verdict), [f"{ev.cite()} [LLM 선택]"]


ARMS = {"B0": run_b0, "B1": run_b1, "B2a": run_b2a, "B2b": run_b2b, "B3": run_b3}


# ============================================================ 실사용 오교정용 arm
#
# 위 arm들은 제42항 이중 기능 단어 전용이다. 여기부터는 **사용자가 실제로 보고한
# 오교정**(`dataset_realusage.jsonl`)을 겨냥한다. 그 사례들의 공통 원인은 하나다:
#
#   표제어가 있다는 사실만으로 붙였다. 그 표제어의 **뜻**은 보지 않았다.
#
# `사진하다`가 그 증거다. 표준국어대사전에 있고 분야 표시도 없어 현대 일반어
# 게이트를 통과하지만, 뜻풀이 첫 줄이 "벼슬아치가 규정된 시간에 근무지로
# 출근하다"(仕進하다)이다. 사진(寫眞)과 아무 상관이 없다. 반면 `요리하다`·`공부하다`의
# 뜻풀이는 문장 문맥과 맞는다.
#
# 즉 **가르는 근거가 사전 안에 이미 있는데 지금은 안 꺼내 쓴다.** 불리언 하나로 뭉갠다.
# 이 arm은 그 뜻풀이를 꺼내 문맥과 대조하는 가드다. §73의 `건초` 판정(표준 용어
# 뜻풀이와의 낱말 겹침)을 붙임 판정으로 확장한 것이다.

_defs_cache: dict = {}


def _definitions(word: str) -> list[str]:
    from subtitle_corrector.dictionary import headword_definitions
    if word not in _defs_cache:
        try:
            _defs_cache[word] = list(headword_definitions(word) or [])
        except Exception:
            _defs_cache[word] = []
    return _defs_cache[word]


def _merged_spans(before: str, after: str) -> list[tuple[int, str]]:
    """B0가 붙인 자리를 찾는다. 반환: (입력 어절 위치, 붙여진 어절)."""
    a, b = before.split(), after.split()
    merges, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1; j += 1
        elif i + 1 < len(a) and b[j] == a[i] + a[i + 1]:
            merges.append((i, b[j])); i += 2; j += 1
        else:
            i += 1; j += 1
    return merges


def _lemma_of(surface: str) -> str:
    """붙여진 어절에서 사전에 조회할 기본형을 뽑는다('사진하러' -> '사진하다').

    **`_content_lemmas`를 쓰면 안 된다.** 그것은 NNG/VV/VA만 남기므로 파생 접미사
    '하'(XSV)가 걸러져 `요리하는`에서 `요리`만 나온다. 그러면 가드가 엉뚱한 표제어를
    조회한다 — 실측에서 `요리`(利料, "재물을 불리어 이익을 늘림")를 보고 정당한
    붙임을 되돌렸다(2026-08-12). 조회할 낱말을 틀리면 뒤의 판정은 전부 무의미하다.

    그래서 형태소 태그를 직접 본다. 파생 접미사가 있으면 앞말에 붙여 기본형을 만들고
    (`사진`+`하`+`다`), 없으면 명사 연쇄 자체를 쓴다(`턱밑`, `노천카페`).
    """
    from subtitle_corrector.engine.kiwi_adapter import _kiwi

    try:
        toks = _kiwi.tokenize(surface)
    except Exception:
        return surface
    # 명사 연쇄 뒤에 오는 첫 용언·접미사를 기본형의 어간으로 삼는다. kiwi는 같은
    # '하'를 문장에 따라 XSV로도 VV로도 태깅하므로(실측: `요리하는`은 XSV,
    # `사진하는`은 VV) 태그 하나만 보면 절반을 놓친다.
    for i, t in enumerate(toks):
        if t.tag in ("XSV", "XSA", "VV", "VA", "VX"):
            stem = "".join(x.form for x in toks[:i] if x.tag.startswith("NN"))
            if stem:
                return f"{stem}{t.form}다"
            break
    nouns = [t.form for t in toks if t.tag.startswith("NN")]
    return "".join(nouns) if nouns else surface


def _definition_fits(sentence: str, lemma: str, scorer) -> tuple[bool, float, str]:
    """붙임형의 뜻풀이가 이 문장 문맥과 맞는가.

    맞지 않으면 그 표제어는 이 문장에서 쓰인 것이 아니므로 붙일 근거가 없다.
    """
    defs = _definitions(lemma)
    if not defs:
        # 뜻풀이를 못 가져왔으면 판단하지 않는다 — 근거가 없으면 기존 동작을 바꾸지
        # 않는다는 이 프로젝트의 관례를 따른다.
        return True, 0.0, "뜻풀이 없음(판단 보류)"
    best, best_def = -1.0, ""
    for d in defs:
        s = scorer(sentence, d)
        if s > best:
            best, best_def = s, d
    return best >= _FIT_THRESHOLD, best, best_def


# 문턱값. 낮추면 놓치고 높이면 정당한 붙임까지 되돌린다. 0.02는 자카드 유사도
# 기준으로 "뜻풀이와 문장이 내용어를 하나도 안 겹치지는 않는다" 수준이다.
_FIT_THRESHOLD = 0.02


def _run_definition_guard(text: str, scorer) -> tuple[str, list[str]]:
    out, why = run_b0(text)
    if out == text:
        return out, why
    reverted = out
    for _idx, merged in _merged_spans(text, out):
        lemma = _lemma_of(merged)
        fits, score, evidence = _definition_fits(text, lemma, scorer)
        if not fits:
            # 되돌린다 — 그 표제어의 뜻이 이 문장에 없다.
            a = text.split()
            for i in range(len(a) - 1):
                if a[i] + a[i + 1] == merged:
                    reverted = reverted.replace(merged, f"{a[i]} {a[i + 1]}", 1)
                    break
            why = why + [f"[가드] '{lemma}' 뜻풀이가 문맥과 맞지 않아 붙임을 되돌렸다 "
                         f"(유사도 {score:.3f}, 뜻풀이: {evidence[:40]})"]
    return reverted, why


def run_b4a(text: str, word: str | None = None) -> tuple[str, list[str]]:
    """B0 + 뜻풀이 가드 (낱말 겹침, 비신경)."""
    return _run_definition_guard(text, _overlap)


def run_b4b(text: str, word: str | None = None) -> tuple[str, list[str]]:
    """B0 + 뜻풀이 가드 (문장 임베딩)."""
    return _run_definition_guard(text, _cosine)


ARMS["B4a"] = run_b4a
ARMS["B4b"] = run_b4b
