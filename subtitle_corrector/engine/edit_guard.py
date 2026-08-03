"""자동 교정이 **설명되지 않는 변경**을 내보내지 못하게 막는 마지막 관문.

왜 필요한가 (2026-08-03 사용자 지적): 실제 자막 파일을 넣으면 원문의 맞춤법·띄어쓰기가
왜곡되는 일이 반복됐다. 개별 규칙을 고치는 방식으로는 끝나지 않는다 — 새 규칙을 넣을
때마다 같은 부류가 다시 생기고, 파일마다 다른 자리에서 터진다. 그래서 "테스트로 확인"이
아니라 **구조상 통과할 수 없게** 만든다.

규칙 하나가 한 줄을 고칠 때마다 아래를 검사한다.

1. 아무것도 바뀌지 않았으면 통과.
2. **글자 뼈대**(공백과 문장부호를 뺀 나머지)가 그대로면 통과 — 띄어쓰기·부호 교정이다.
3. 뼈대가 바뀌었으면, 그 규칙이 남긴 교정 로그(`'원문 -> 정답'`)로 원문을 재구성해 본다.
   재구성한 뼈대가 결과와 같으면 통과 — 규칙이 스스로 밝힌 치환이다.
4. 그래도 다르면 **그 규칙의 결과를 버리고 원문을 그대로 쓴다**(fail-closed). 무엇을 왜
   바꿨는지 설명하지 못하는 변경은 나갈 수 없다.

이 검사는 파일과 무관하다. 규칙이 어떤 이유로 폭주해도 근거 없는 문자 변화는 통과하지
못한다. 실제로 이 장치가 있으면 `그래 노래를 불렀다` -> `그라고 노라고를 불렀다`
(사투리 표 사고, §52)는 규칙을 고치지 않아도 막혔다.

**막지 못하는 것도 분명히 적어 둔다**: 근거는 있으나 문맥상 틀린 교정(동형이의어를 사전
근거로 바꾸는 경우)은 3번을 통과한다. 그건 왜곡이 아니라 오교정이며, 자동 적용 대상을
"사전이 유일한 정답을 주는 것"으로 좁히는 방법으로만 줄인다.
"""

# 뼈대 계산에서 빼는 문자 — 공백과 문장부호. 이들만 달라진 변경은 띄어쓰기·부호 규칙의
# 정상 동작이다. 자막 규칙이 다루는 부호(마침표·쉼표·말줄임표·따옴표·괄호)를 모두 넣는다.
_IGNORED_IN_SKELETON = set(" \t\n.,!?…\"'“”‘’()[]{}·-—~")


def _skeleton(text: str) -> str:
    """공백·문장부호를 뺀 글자 뼈대. 이것이 같으면 낱말 자체는 바뀌지 않았다."""
    return "".join(ch for ch in text if ch not in _IGNORED_IN_SKELETON)


# 받침 유무에 따라 형태가 바뀌는 조사 짝. 낱말을 치환하면 뒤 조사도 함께 바뀌는데
# (`로보트를` -> `로봇을`), 규칙의 로그에는 낱말 치환만 남는다(`로보트 -> 로봇`). 그래서
# 재구성 결과와 실제 결과가 조사 한 글자만큼 달라진다 — 이형태는 닫힌 집합이므로 비교할
# 때 한쪽으로 모아 같은 것으로 본다. 이 보정 없이 검사를 켜면 정당한 교정이 막힌다
# (2026-08-04 평가셋 g01 '로보트를 샀다'에서 확인).
_PARTICLE_ALLOMORPHS = {"가": "이", "는": "은", "를": "을", "와": "과"}


def _canonical(text: str) -> str:
    """뼈대에서 조사 이형태를 한쪽으로 모은다."""
    return "".join(_PARTICLE_ALLOMORPHS.get(ch, ch) for ch in _skeleton(text))


def _reconstruct(before: str, declared: list[str]) -> str:
    """규칙이 남긴 로그(`'원문 -> 정답'`)를 원문에 적용해 결과를 재구성한다."""
    expected = before
    for note in declared:
        wrong, separator, right = note.partition(" -> ")
        if not separator:
            continue
        expected = expected.replace(wrong.strip(), right.strip())
    return expected


def verify_edit(rule: str, before: str, after: str, declared: list[str]) -> tuple[str, str | None]:
    """한 규칙의 결과를 검사한다.

    반환값: (채택할 텍스트, 거부 사유 또는 None). 거부되면 원문을 그대로 돌려준다.
    """
    if after == before:
        return after, None
    if _skeleton(before) == _skeleton(after):
        return after, None
    if _canonical(_reconstruct(before, declared)) == _canonical(after):
        return after, None
    return before, (
        f"[자동 교정 차단] {rule}이(가) 근거 없이 낱말을 바꾸려 해 적용하지 않았습니다: "
        f"'{before}' -> '{after}'"
    )
