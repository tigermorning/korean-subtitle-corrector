"""축적된 온라인가나다 판례 중 의미가 비슷한 것을 찾아 **사람에게 보여주는** 보조 도구.

교정 판정에는 절대 쓰지 않는다. `check_precedent()`는 표기가 정확히 일치할 때만
True/False를 돌려주고, 그 동작은 이 모듈이 있어도 변하지 않는다. 이 모듈은
정확히 일치하는 판례가 없을 때 "이런 비슷한 판례가 있으니 사람이 직접 판단해
보라"는 후보 목록만 만든다. 문장 임베딩 유사도는 규범 근거가 아니므로
(AGENTS.md 최우선 원칙: 확률적 추측 금지, 애매하면 사람에게 확인) 자동 교정
결정에 이 점수를 쓰면 안 된다.

의존성(`sentence-transformers`, 모델 약 500MB)은 선택 사항이다. 웹 배포
환경에서는 설치하지 않는다 — Render 무료 티어 512MB 메모리 한계 때문에
kiwipiepy만으로도 이미 한계에 걸린 기록이 있다(docs/KNOWN_LIMITATIONS.md).
그래서 이 모듈은 서버 요청 경로에서 호출되지 않고, 감수자가 로컬에서
직접 실행할 때만 모델을 올린다.

로컬 사용:
    pip install sentence-transformers
    python -m subtitle_corrector.precedent_search 갈만하다
"""

from __future__ import annotations

from subtitle_corrector.gananda_precedents import PRECEDENTS, check_precedent

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model = None
_cached_expressions: list[str] = []
_cached_vectors = None


class PrecedentSearchUnavailable(RuntimeError):
    """sentence-transformers가 설치되지 않아 유사 판례 검색을 쓸 수 없음."""


def _load_model():
    """모델을 CPU에 올린다(GPU 불필요). 한 번 올리면 모듈 수준에서 재사용한다."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise PrecedentSearchUnavailable(
                "유사 판례 검색에는 sentence-transformers가 필요하다. "
                "로컬에서만 `pip install sentence-transformers`로 설치해라 "
                "(웹 배포 환경에는 설치하지 말 것 — 메모리 한계)."
            ) from error
        _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


def _default_encode(texts: list[str]):
    """텍스트를 길이 1로 정규화된 벡터로 만든다. 정규화했으므로 내적이 곧 코사인 유사도."""
    return _load_model().encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    )


def _precedent_vectors(encode, expressions: list[str]):
    """판례 표현들의 벡터를 캐시한다. PRECEDENTS가 바뀌면 다시 계산한다."""
    global _cached_expressions, _cached_vectors
    if _cached_vectors is None or _cached_expressions != expressions:
        _cached_vectors = encode(expressions)
        _cached_expressions = list(expressions)
    return _cached_vectors


def find_similar_precedents(
    expression: str,
    top_n: int = 5,
    min_similarity: float = 0.5,
    encode=None,
) -> list[dict]:
    """expression과 의미가 비슷한 판례를 유사도 높은 순으로 돌려준다.

    반환 항목은 PRECEDENTS의 원본 dict(expression/correct/source/verified)에
    similarity를 더한 것이다. source와 verified를 그대로 넘기는 이유는, 감수자가
    유사도 점수가 아니라 **국립국어원 답변 요지 원문**을 근거로 판단해야 하기
    때문이다.

    표기가 정확히 일치하는 판례가 이미 있으면 빈 목록을 돌려준다 — 그 경우는
    check_precedent()가 확정 답을 주므로 유사 검색이 끼어들 이유가 없다.

    encode는 테스트에서 모델 없이 검증하기 위한 주입점이다. 실제 사용에서는
    생략하면 CPU 임베딩 모델을 쓴다.
    """
    if check_precedent(expression) is not None:
        return []

    candidates = [entry for entry in PRECEDENTS if entry["expression"] != expression]
    if not candidates:
        return []

    encode = encode or _default_encode
    expressions = [entry["expression"] for entry in candidates]
    vectors = _precedent_vectors(encode, expressions)
    query_vector = encode([expression])[0]

    similarities = vectors @ query_vector
    order = similarities.argsort()[::-1][:top_n]
    return [
        {**candidates[index], "similarity": float(similarities[index])}
        for index in order
        if float(similarities[index]) >= min_similarity
    ]


def format_similar_precedents(expression: str, matches: list[dict]) -> str:
    """감수자에게 보여줄 텍스트. 판정이 아니라 확인 요청임을 문면에 남긴다."""
    if not matches:
        return f"'{expression}'과 비슷한 축적 판례 없음."

    lines = [
        f"'{expression}'에 대한 확정 판례는 없다. 아래는 의미가 비슷한 판례이며,",
        "유사도는 참고 수치일 뿐 규범 근거가 아니다. 사람이 직접 판단해라.",
        "",
    ]
    for entry in matches:
        verdict = "맞음" if entry["correct"] else "틀림"
        lines.append(
            f"- {entry['expression']} ({verdict}, 유사도 {entry['similarity']:.3f}, "
            f"확인 {entry['verified']})"
        )
        lines.append(f"  근거: {entry['source']}")
    return "\n".join(lines)


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("사용법: python -m subtitle_corrector.precedent_search <표현>")
    expression = sys.argv[1]
    try:
        matches = find_similar_precedents(expression)
    except PrecedentSearchUnavailable as error:
        raise SystemExit(str(error)) from error
    print(format_similar_precedents(expression, matches))


if __name__ == "__main__":
    main()
