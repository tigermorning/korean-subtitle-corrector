"""사용자가 제안을 채택했는지 기각했는지 남기는 기록장(2026-08-12 추가).

**무엇을 위한 것인가.** 이 도구의 제안 하나하나에는 사람이 답을 준다 — 채택하면
정답, 안 고르면 오답이다. 그 판단은 지금 화면에서 소비되고 사라진다. 그것을 줄
단위로 모아 두면 `(원문, 고친 문장, 사람의 판정)` 쌍이 쌓이고, 그것이 나중에
언어 모델을 이 작업에 맞춰 학습시킬 때 쓸 유일한 재료가 된다. 규정 문서와
평가셋으로는 그 짝을 만들 수 없다 — 규정은 "무엇이 맞는가"를 말할 뿐 "이 작업자가
이 자막에서 무엇을 골랐는가"를 말해 주지 않는다.

**기본은 꺼짐이고, 켜는 것은 사용자의 명시적 행동이다.** 여기 쌓이는 것은 남의
원고다. 자막 대본은 대개 저작물이고 납품 전 자료다. 그것을 도구가 알아서 디스크에
모으기 시작하면 안 된다. `FEEDBACK_LOG_DIR` 환경변수에 경로를 넣은 사람만 켠다.
꺼져 있으면 이 모듈의 모든 함수는 아무 일도 하지 않고 0을 돌려준다.

**'기각'의 뜻을 정확히 적어 둔다.** 사용자가 화면에서 '반영'을 누른 순간, 고른
제안은 채택이고 **고르지 않은 제안은 기각으로 적는다**. 이건 "틀렸다고 판단했다"
보다 약한 신호다 — 아직 못 봤을 수도, 나중에 보려고 남겨 뒀을 수도 있다. 그래도
이보다 나은 신호가 없고, 학습에 쓸 때 이 차이를 아는 것이 중요하므로 필드 이름을
`accepted`로만 두고 "기각"이라는 단정적인 이름은 쓰지 않는다.

**원문 전체는 저장하지 않는다.** 문서를 가리는 데는 해시 앞자리만 있으면 된다
(같은 원고를 두 번 돌렸을 때 같은 판정이 중복으로 쌓이는 것을 나중에 걸러내려는
목적뿐이다). 줄 단위 텍스트는 그 짝이 학습 재료 자체이므로 남긴다.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# 켜는 스위치이자 저장 위치. 값이 없으면 기능 전체가 꺼진다.
FEEDBACK_LOG_DIR = os.getenv("FEEDBACK_LOG_DIR", "").strip()


# 한 번의 요청으로 받을 판정 수와 필드 길이 상한. 웹으로 열린 창구라 상한이 없으면
# 디스크를 채우는 통로가 된다. 자막 한 편의 플래그가 이 수를 넘는 일은 없다.
MAX_RECORDS_PER_CALL = 2000


MAX_FIELD_LENGTH = 2000


# 제안 문구에서 출처와 규칙 이름을 뽑는다. `llm_pass`는 `[모델 제안] 되/돼 — …`,
# 규칙 엔진은 `[제42항] …` 같은 형태로 쓴다. 파싱이 실패해도 기록은 남아야 하므로
# 못 뽑으면 빈 값으로 둔다.
_MODEL_REASON = re.compile(r"^\[모델 제안\]\s*([^—-]*)")


_RULE_REASON = re.compile(r"^\[([^\]]+)\]")


def is_enabled() -> bool:
    return bool(FEEDBACK_LOG_DIR)


def _clip(value) -> str:
    text = "" if value is None else str(value)
    return text[:MAX_FIELD_LENGTH]


def document_id(text: str) -> str:
    """원고를 가리키는 짧은 해시. 원문 복원은 불가능하고 동일 여부만 알 수 있다."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def classify(reason: str) -> tuple[str, str]:
    """제안 문구에서 (출처, 규칙 이름)을 뽑는다.

    출처를 나누는 이유: 규칙 제안과 모델 제안은 학습에서 값어치가 다르다. 규칙
    제안의 채택률은 그 규칙이 쓸 만한지를 말해 주고(규칙을 고칠 근거), 모델 제안의
    채택률은 모델이 이 작업에 맞는지를 말해 준다(학습에 쓸 재료).
    """
    model_match = _MODEL_REASON.match(reason or "")
    if model_match:
        return "model", model_match.group(1).strip()
    rule_match = _RULE_REASON.match(reason or "")
    return "rule", rule_match.group(1).strip() if rule_match else ""


def record_decisions(decisions: list[dict], doc_hash: str = "") -> int:
    """판정 목록을 한 줄씩 덧붙인다. 꺼져 있거나 쓸 수 없으면 0을 돌려준다.

    한 줄에 하나씩 쓰는 JSONL이라, 나중에 학습 데이터로 읽을 때 파일 전체를 메모리에
    올리지 않아도 되고 중간에 프로세스가 죽어도 앞부분이 온전하다.

    **여기서는 어떤 예외도 밖으로 내보내지 않는다.** 기록은 교정의 부수 작업이다.
    디스크가 가득 찼다고 이미 끝난 교정 결과가 사라지면 안 된다.
    """
    if not is_enabled() or not decisions:
        return 0

    stamp = datetime.now(timezone.utc).isoformat()
    written = 0
    try:
        directory = Path(FEEDBACK_LOG_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        # 날짜로 쪼갠다. 한 파일이 무한정 자라면 나중에 다루기 어렵고, 어느 시점의
        # 판정인지로 잘라 쓰는 일이 실제로 생긴다(규칙을 고친 뒤의 것만 보기 등).
        path = directory / f"decisions-{stamp[:10]}.jsonl"
        with open(path, "a", encoding="utf-8") as log:
            for decision in decisions[:MAX_RECORDS_PER_CALL]:
                if not isinstance(decision, dict):
                    continue
                before = _clip(decision.get("before"))
                after = _clip(decision.get("after"))
                # 짝이 성립하지 않는 것은 학습 재료가 아니다.
                if not before or not after or before == after:
                    continue
                reason = _clip(decision.get("reason"))
                source, rule = classify(reason)
                log.write(
                    json.dumps(
                        {
                            "ts": stamp,
                            "doc": _clip(doc_hash),
                            "line": decision.get("line_index"),
                            "source": source,
                            "rule": rule,
                            "before": before,
                            "after": after,
                            "accepted": bool(decision.get("accepted")),
                            "reason": reason,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1
    except OSError:
        return 0
    return written


def summarize() -> dict:
    """쌓인 판정을 세어 본다. 학습을 시작할 때가 됐는지 판단하는 용도다.

    반환값: {"enabled", "total", "accepted", "by_source": {출처: {건수, 채택}}}.
    깨진 줄은 건너뛴다 — 통계 하나 때문에 조회가 실패하면 안 된다.
    """
    summary = {"enabled": is_enabled(), "total": 0, "accepted": 0, "by_source": {}}
    if not is_enabled():
        return summary
    try:
        files = sorted(Path(FEEDBACK_LOG_DIR).glob("decisions-*.jsonl"))
    except OSError:
        return summary

    for path in files:
        try:
            with open(path, encoding="utf-8") as log:
                for line in log:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    source = str(record.get("source") or "unknown")
                    bucket = summary["by_source"].setdefault(source, {"total": 0, "accepted": 0})
                    summary["total"] += 1
                    bucket["total"] += 1
                    if record.get("accepted"):
                        summary["accepted"] += 1
                        bucket["accepted"] += 1
        except OSError:
            continue
    return summary
