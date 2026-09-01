"""규칙이 끝난 뒤 남은 것만 언어 모델에게 물어보는 마지막 패스(2026-08-12 추가).

**왜 필요한가.** 규칙 엔진은 사전이 유일한 정답을 주는 것만 고친다. 그래서 문맥을
봐야 갈리는 것들이 그대로 남는다 — `되/돼`가 어느 쪽인지, 조사가 문장 구조에 맞는지,
자막 한 줄이 앞뒤 대사와 이어지는지. 이것들은 사전을 아무리 잘 뒤져도 답이 안 나온다.
언어 모델은 이 자리에만 쓴다.

**무엇을 하지 않는가.** 이 패스는 `entries`의 텍스트를 **절대 바꾸지 않는다.**
`FlagItem`(사람이 확인할 제안)만 만든다. `pipeline.py`가 명시한 정책 — "확률적
추정으로 자동 수정하지 않는다" — 이 그대로 적용되기 때문이다. 규칙 엔진은 사전이라는
확정 근거를 들고 고치지만 언어 모델에는 그런 근거가 없다. 근거의 성격이 다른데
같은 권한을 주면, 이 도구가 지금까지 지켜 온 "왜곡 없음" 보장이 통째로 무너진다.
사용자가 화면에서 고르면 `apply_report_fixes()`가 반영한다.

**그래도 게이트를 통과시키는 이유.** 제안일 뿐이어도 거르지 않으면 안 된다. 화면의
제안은 사람이 누르면 그대로 적용되고, 자막 한 편에 제안이 수백 개 뜨면 사람은
하나씩 검증하지 않는다. 그래서 모델이 내놓은 것을 규칙 엔진과 **똑같은**
`verify_edit()` 관문에 넣는다(`edit_guard.py` 참고). 설명하지 못하는 낱말 변경은
제안 목록에도 오르지 못한다.

여기서 규칙 엔진보다 **더 조이는** 것이 셋 있다.

1. `declared`(무엇을 무엇으로 바꿨는지)가 비어 있으면 무조건 버린다. `verify_edit`는
   띄어쓰기·부호만 바뀐 변경을 근거 없이 통과시키는데(뼈대가 같으므로), 모델에게는
   그 면제를 주지 않는다. 모델은 한 줄을 통째로 다시 띄어 쓸 수 있고 그것이 전부
   "뼈대 동일"로 통과해 버린다.
2. 줄바꿈 개수가 달라지면 버린다. 자막에서 줄바꿈은 화면 배치이지 문장부호가 아니다.
   `edit_guard`의 뼈대 계산은 `\n`을 무시하므로 이 사고를 못 잡는다.
3. 보낸 원문과 모델이 되돌려준 `before`가 다르면 버린다. 모델이 문맥을 지어냈다는
   뜻이고, 그 위에서 만든 `after`는 볼 가치가 없다.

**타임코드는 모델에게 보내지 않는다.** `index`와 텍스트만 보낸다. 시간은 코드가
들고 있는다 — 모델은 숫자를 조용히 틀리고, 자막에서 그건 복구가 어려운 사고다.
"""

import glob
import json
import os
import re
import shutil
import subprocess
from typing import Callable, NamedTuple

import requests
from dotenv import load_dotenv

from ..parsers import SubtitleEntry
from ..report import AppliedNote, FlagItem
from .edit_guard import verify_edit
from .markers import _is_marker_only_line
from .options import SubtitleMarkers

load_dotenv()


# OpenAI 호환 `/chat/completions` 하나만 쓴다. 로컬(llama.cpp·Ollama·vLLM)과 상용
# API가 전부 이 규격을 내주므로, 이것만 맞추면 새 의존성 없이 양쪽을 다 쓴다
# (`requirements.txt`의 `requests`로 충분하다). 어느 쪽을 쓸지는 사용자가 정한다 —
# 자막 한 편이면 호출 수가 수십 건이라 로컬 모델로도 감당되고, 원고가 민감하면
# 밖으로 내보내지 않는 선택이 필요하다.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")


LLM_MODEL = os.getenv("LLM_MODEL", "")


LLM_API_KEY = os.getenv("LLM_API_KEY", "")


# "http" / "cli" / "auto". 비워 두면 auto — 주소가 있으면 HTTP, 없고 `ollama`
# 실행 파일이 있으면 명령으로 부른다(WSL에서는 이쪽이 유일한 길이다).
LLM_BACKEND = os.getenv("LLM_BACKEND", "")


# 한 번에 보낼 줄 수. 너무 크면 모델이 뒤쪽 줄을 성의 없이 처리하고, 너무 작으면
# 문맥이 끊겨 이 패스의 존재 이유(문맥 판단)가 사라진다.
_DEFAULT_BATCH_SIZE = 40


# 한 줄에 허용하는 제안 개수. 이보다 많으면 모델이 그 줄을 "다시 쓰고" 있는 것이지
# 교정하고 있는 것이 아니다. 자막 한 줄은 길어야 두 줄 40자 안팎이라 진짜 오류가
# 네 개 이상 겹치는 일은 드물다.
_MAX_DECLARED_PER_LINE = 3


class LlmSettings(NamedTuple):
    """언어 모델 패스 설정. 기본값은 **꺼짐**이다.

    이 패스는 네트워크·비용·외부 전송이 걸리는 유일한 선택 기능이므로, 켜는 것은
    항상 사용자의 명시적 행동이어야 한다. 설정이 없으면 도구는 지금까지와 완전히
    똑같이 동작한다.
    """

    enabled: bool = False
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    # "http" — OpenAI 호환 주소로 부른다. "cli" — `ollama run`을 직접 부른다.
    # WSL에서 Windows 쪽 Ollama는 HTTP로 닿지 않아 cli가 유일한 길이다(_chat_cli 참고).
    backend: str = "http"
    timeout: float = 60.0
    batch_size: int = _DEFAULT_BATCH_SIZE
    # 0이면 제한 없음. 값을 주면 앞에서부터 그만큼만 보고 나머지는 건너뛴다 —
    # 건너뛴 사실은 반드시 로그로 알린다(조용히 자르면 "전부 검토했다"로 읽힌다).
    max_lines: int = 0


def normalize_llm_settings(
    enabled: bool | str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    backend: str | None = None,
    timeout: float | str | None = None,
    batch_size: int | str | None = None,
    max_lines: int | str | None = None,
) -> LlmSettings:
    """설정값을 정규화한다. 값이 모자라면 **꺼진 설정**으로 떨어뜨린다.

    모델 이름은 어느 경로로든 반드시 있어야 한다. 그 위에서 부르는 길을 정한다.

        backend=http   주소가 있어야 켜진다 (OpenAI 호환 서버·상용 API)
        backend=cli    `ollama` 실행 파일이 있어야 켜진다 (주소 불필요)
        backend=auto   주소가 있으면 http, 없고 실행 파일이 있으면 cli

    기본값이 `auto`인 이유: 이 도구를 쓰는 자리가 WSL이면 HTTP가 아예 닿지 않고
    (`_chat_cli` 참고) 사용자가 그 사실을 미리 알 방법이 없다. 주소를 안 적었는데
    Ollama가 깔려 있으면 조용히 되는 쪽으로 붙는 것이 맞다.

    켤 수 없는 설정은 꺼진 것으로 떨어뜨린다 — 그 상태로 호출하면 매 요청이
    실패하고 로그만 쌓인다. 켜졌다고 표시해 놓고 아무 일도 안 하는 것보다 낫다.
    """
    if isinstance(enabled, str):
        enabled_value = enabled.strip().lower() in ("1", "true", "yes", "on", "y")
    else:
        enabled_value = bool(enabled)

    resolved_base = (base_url or LLM_BASE_URL or "").strip().rstrip("/")
    resolved_model = (model or LLM_MODEL or "").strip()
    resolved_backend = (backend or LLM_BACKEND or "auto").strip().lower()
    if resolved_backend not in ("http", "cli", "auto"):
        resolved_backend = "auto"
    if resolved_backend == "auto":
        resolved_backend = "http" if resolved_base else ("cli" if find_ollama_exe() else "http")

    if not resolved_model:
        enabled_value = False
    elif resolved_backend == "http" and not resolved_base:
        enabled_value = False
    elif resolved_backend == "cli" and not find_ollama_exe():
        enabled_value = False

    def _number(value, fallback):
        try:
            return type(fallback)(value)
        except (TypeError, ValueError):
            return fallback

    return LlmSettings(
        enabled=enabled_value,
        base_url=resolved_base,
        model=resolved_model,
        api_key=(api_key or LLM_API_KEY or "").strip(),
        backend=resolved_backend,
        timeout=max(1.0, _number(timeout, 60.0)),
        batch_size=max(1, _number(batch_size, _DEFAULT_BATCH_SIZE)),
        max_lines=max(0, _number(max_lines, 0)),
    )


# 모델에게 주는 지시. 세 가지를 반복해서 못 박는다: (1) 확신이 없으면 내놓지 말 것,
# (2) 바꾼 것을 전부 `declared`에 적을 것, (3) 말투를 건드리지 말 것.
#
# (3)이 이 도구에서 제일 중요하다. 자막 대사의 구어체·비문·사투리는 대부분 작가의
# 의도이고, 언어 모델은 지시가 없으면 그것을 전부 표준 문어체로 밀어 버린다.
# `dialect.py`가 지키는 것과 같은 선을 여기서도 지켜야 한다.
_SYSTEM_PROMPT = """너는 한국어 자막 교정 보조자다. 규칙 기반 교정기가 이미 한 번 훑고
지나간 뒤라, 사전으로 확정되는 오류는 남아 있지 않다. 너는 **문맥을 봐야만 판단되는 것**만
찾는다.

찾을 것:
- 문맥으로만 갈리는 표기 (되/돼, 안/않, 로서/로써, 데/대)
- 문장 구조에 맞지 않는 조사
- 앞뒤 대사와 이어지지 않는 명백한 전사 오류

절대 건드리지 말 것:
- 말투, 구어체, 사투리, 반말/존댓말 — 전부 작가의 의도다
- 맞는 표기를 다른 맞는 표기로 바꾸는 것 (도리어→되레 같은 것)
- 줄바꿈 위치와 개수
- 문장부호 취향 (…와 ... 중 어느 쪽인지 등)
- 고유명사 표기

출력은 JSON 객체 하나뿐이다. 설명도 코드펜스도 붙이지 마라.

{"proposals": [{"id": 3, "before": "원문 그대로", "after": "고친 문장",
  "rule": "되/돼", "declared": ["됬다 -> 됐다"]}]}

규칙:
- `before`는 받은 원문과 **한 글자도 다르지 않아야** 한다.
- `declared`에는 바꾼 낱말을 `"틀린것 -> 맞는것"` 형식으로 **빠짐없이** 적는다.
  여기 적지 않은 변경이 `after`에 있으면 그 제안은 버려진다.
- 고칠 것이 없으면 `{"proposals": []}`를 반환한다. 억지로 찾지 마라.
"""


# 출력 형식을 **지시문이 아니라 서버**에 맡기는 자리(2026-09-01 추가).
#
# 지시문에 "JSON만 내라"고 적는 것은 부탁이지 강제가 아니다. 실제로 모델은 코드펜스를
# 붙이고 설명 문장을 앞에 단다 — `_parse_proposals`의 방어 코드가 그 흔적이다. OpenAI
# 호환 규격에는 스키마를 서버가 강제하게 만드는 자리(`response_format`)가 있으므로,
# 부탁 대신 그것을 쓴다. 형식이 어긋난 응답 자체가 나올 수 없게 된다.
#
# 뿌리를 배열이 아니라 객체(`{"proposals": [...]}`)로 잡은 이유: 상용 API의 엄격
# 모드가 최상위 배열을 받지 않는다. 로컬 서버는 양쪽 다 받으므로 좁은 쪽에 맞춘다.
#
# **지원은 백엔드마다 갈린다.** 상용 API·최신 Ollama·llama.cpp·vLLM이 각각 다르고,
# `ollama run`을 직접 부르는 cli 경로에는 이 자리가 아예 없다. 그래서 스키마는 "걸리면
# 좋은 것"으로 두고, 서버가 거절하면 한 번만 스키마 없이 다시 부른 뒤 그 사실을
# 기억한다. 지원하지 않는 서버에서도 도구는 지금까지와 똑같이 동작한다.
_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "subtitle_proposals",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "before": {"type": "string"},
                            "after": {"type": "string"},
                            "rule": {"type": "string"},
                            "declared": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "before", "after", "rule", "declared"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["proposals"],
            "additionalProperties": False,
        },
    },
}


# 스키마를 모르는 서버는 이 상태코드들로 되돌려준다. 500대는 넣지 않는다 — 그건
# 서버가 잠깐 아픈 것이지 자리를 모르는 것이 아니어서, 기능을 영구히 끄면 안 된다.
_SCHEMA_REJECTED = (400, 404, 422)


# (주소, 모델) -> 스키마 강제가 걸렸는가. 한 번 거절당한 조합은 다시 시도하지 않는다.
# 자막 한 편이면 구간이 수십 개라 매번 두 번씩 부르면 그대로 두 배가 된다.
_SCHEMA_SUPPORT: dict[tuple[str, str], bool] = {}


def _chat(prompt: str, settings: LlmSettings) -> str:
    """OpenAI 호환 서버에 한 번 물어본다. 실패는 예외로 올린다(호출부가 로그로 바꾼다).

    출력 형식은 지시문으로 부탁하지 않고 `response_format`으로 서버에 맡긴다
    (`_RESPONSE_FORMAT` 주석 참고). 서버가 그 자리를 모르면 스키마를 빼고 한 번만
    다시 부른다 — 재시도는 딱 한 번이고, 같은 조합에는 두 번 다시 시도하지 않는다.
    """
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        # 교정은 창작이 아니다. 같은 원고를 두 번 돌렸을 때 결과가 달라지면
        # 사용자가 무엇을 신뢰해야 할지 알 수 없다.
        "temperature": 0,
    }

    key = (settings.base_url, settings.model)
    if _SCHEMA_SUPPORT.get(key, True):
        payload["response_format"] = _RESPONSE_FORMAT

    def _post():
        return requests.post(
            f"{settings.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=settings.timeout,
        )

    response = _post()
    if "response_format" in payload:
        if response.status_code in _SCHEMA_REJECTED:
            _SCHEMA_SUPPORT[key] = False
            payload.pop("response_format")
            response = _post()
        else:
            _SCHEMA_SUPPORT[key] = True

    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"] or ""


# WSL에서 Windows 쪽 Ollama를 부를 때 쓸 실행 파일 자리. 사용자 이름이 리눅스
# 쪽과 다를 수 있어 별표로 훑는다.
_OLLAMA_EXE_PATTERNS = (
    "/mnt/c/Users/{user}/AppData/Local/Programs/Ollama/ollama.exe",
    "/mnt/c/Program Files/Ollama/ollama.exe",
)


def find_ollama_exe() -> str:
    """`ollama` 실행 파일을 찾는다. 없으면 빈 문자열."""
    for name in ("ollama", "ollama.exe"):
        found = shutil.which(name)
        if found:
            return found
    for pattern in _OLLAMA_EXE_PATTERNS:
        matches = glob.glob(pattern.replace("{user}", "*"))
        if matches:
            return matches[0]
    return ""


# `ollama run`은 진행 표시를 그리느라 커서 제어 코드를 출력에 섞는다(2026-08-12
# 실측). 그냥 지우면 안 된다 — `\x1b[1D\x1b[K`는 "한 칸 왼쪽으로 가서 거기부터
# 지워라", 즉 **직전 글자를 없애라**는 뜻이라, 코드만 떼면 지워졌어야 할 글자가
# 남아 JSON이 깨진다. 실제로 이것 때문에 모든 응답이 파싱에 실패해 제안이 0건으로
# 나왔다. 그래서 코드가 시키는 대로 흉내 내서 최종 화면을 복원한다.
_CSI = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")


def _render_terminal(raw: str) -> str:
    """커서 제어 코드를 실행해 '화면에 남았을 글자'만 남긴다.

    다루는 것은 실제로 관측된 것뿐이다: 커서 좌우 이동(D/C), 줄 끝까지 지우기(K),
    캐리지 리턴. 나머지 코드는 화면 색깔 같은 것이라 떼기만 한다.
    """
    lines: list[list[str]] = [[]]
    col = 0
    index = 0
    while index < len(raw):
        match = _CSI.match(raw, index)
        if match:
            amount = int(match.group(1) or 1) if match.group(1).isdigit() else 1
            command = match.group(2)
            if command == "D":
                col = max(0, col - amount)
            elif command == "C":
                col = min(len(lines[-1]), col + amount)
            elif command == "K":
                del lines[-1][col:]
            index = match.end()
            continue
        char = raw[index]
        index += 1
        if char == "\n":
            lines.append([])
            col = 0
        elif char == "\r":
            col = 0
        elif char == "\x08":
            col = max(0, col - 1)
        else:
            current = lines[-1]
            if col < len(current):
                current[col] = char
            else:
                current.extend([" "] * (col - len(current)))
                current.append(char)
            col += 1
    return "\n".join("".join(line) for line in lines)


def _chat_cli(prompt: str, settings: LlmSettings) -> str:
    """`ollama run`을 직접 부른다. **포트를 하나도 열지 않는다.**

    WSL에서 작업할 때 Windows 쪽 Ollama는 127.0.0.1에만 붙어 있어 HTTP로 닿지
    않는다(2026-08-12 실측: 게이트웨이 172.27.112.1도 마찬가지). 뚫으려면 Ollama를
    `0.0.0.0`에 열어야 하는데, 그건 같은 망의 다른 컴퓨터에도 열어 주는 일이다 —
    남의 원고를 다루는 자리에서 할 일이 아니다. 자막 편집기 쪽도 같은 이유로 같은
    선택을 했다(`checker/translate.py`).

    `ollama run`에는 시스템 지시를 따로 주는 자리가 없어 프롬프트 앞에 붙인다.
    """
    exe = find_ollama_exe()
    if not exe:
        raise RuntimeError(
            "ollama 실행 파일을 찾지 못했습니다. 설치했다면 LLM_BASE_URL로 "
            "HTTP 주소를 지정해 주세요."
        )
    result = subprocess.run(
        [exe, "run", settings.model],
        input=f"{_SYSTEM_PROMPT}\n\n{prompt}\n",
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=settings.timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").replace("\r", "").strip()[:200]
        raise RuntimeError(f"Ollama 오류: {detail}")
    return (result.stdout or "").strip()


def _parse_proposals(raw: str) -> tuple[list, str | None]:
    """응답에서 제안 목록을 꺼낸다. 반환값은 (목록, **못 꺼낸 이유** 또는 None).

    스키마를 강제하지 못한 서버에서는 모델이 여전히 코드펜스를 붙이고 설명 문장을
    앞에 단다. 그런 응답 하나 때문에 교정 전체가 실패하면 안 되므로, 가장 바깥 괄호
    쌍만 잘라서 읽어 보는 방어는 남겨 둔다. 형식은 두 가지를 다 받는다 — 스키마가
    요구하는 `{"proposals": [...]}`와, 맨 배열 `[...]`(스키마 없이 부른 경로).

    **못 꺼낸 것과 고칠 게 없는 것은 다르다.** 앞은 그 구간이 검토되지 않은 것이고
    뒤는 검토된 것이다. 둘을 같은 빈 목록으로 뭉개면 사용자는 "모델이 괜찮다고 했다"로
    읽는다 — `search_dialect()`가 장애와 매칭 없음을 구분하지 못해 겪은 일, 그리고
    우리말샘 조회 실패가 '사전 불통'으로 과장돼 보이던 일과 같은 자리다(`AGENTS.md`).
    그래서 이유를 돌려주고, 호출부가 로그로 남긴다.

    커서 제어 코드부터 실행한다(`_render_terminal`). 어느 경로로 받은 응답이든
    같은 방어가 걸려야 해서 백엔드가 아니라 여기에 둔다.
    """
    raw = _render_terminal(raw)
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = raw.find(opener), raw.rfind(closer)
        if start < 0 or end <= start:
            continue
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            items = parsed.get("proposals")
            if isinstance(items, list):
                return items, None
            continue
        if isinstance(parsed, list):
            return parsed, None
    # 사용자가 무엇을 받았는지 알아야 원인(모델 선택·주소·거절)을 짚을 수 있다.
    excerpt = " ".join(raw.split())[:120]
    return [], excerpt or "(빈 응답)"


def _restore_padding(original: str, stripped_after: str) -> str:
    """모델이 떼어 낸 앞뒤 공백을 원문 그대로 되돌린다.

    모델은 거의 항상 앞뒤 공백을 지우고 답한다. 그것만으로 제안을 버리면 멀쩡한
    교정이 대량으로 사라지므로, 비교는 `strip()`한 값으로 하고 결과에는 원문의
    여백을 그대로 붙인다 — 여백 자체는 모델이 건드릴 대상이 아니다.
    """
    leading = original[: len(original) - len(original.lstrip())]
    trailing = original[len(original.rstrip()) :]
    return f"{leading}{stripped_after}{trailing}"


def _accept(
    proposal: dict,
    text_by_index: dict[int, str],
) -> tuple[FlagItem | None, str | None]:
    """제안 하나를 검사한다.

    반환값: (채택된 플래그 또는 None, 거부 사유 또는 None). 둘 다 None이면 조용히
    버린 것이다(고칠 것 없음 등, 사용자에게 알릴 내용이 아니다).
    """
    if not isinstance(proposal, dict):
        return None, None

    try:
        index = int(proposal.get("id"))
    except (TypeError, ValueError):
        return None, None

    original = text_by_index.get(index)
    if original is None:
        # 보내지 않은 줄에 대한 제안. 모델이 번호를 지어냈다.
        return None, f"[모델 제안 차단] 존재하지 않는 줄 번호 {index}에 대한 제안을 버렸습니다."

    before = str(proposal.get("before") or "")
    after = str(proposal.get("after") or "")
    rule = str(proposal.get("rule") or "문맥 교정").strip() or "문맥 교정"
    declared = [str(note) for note in proposal.get("declared") or [] if str(note).strip()]

    if before.strip() != original.strip():
        return None, (
            f"[모델 제안 차단] {index}번 줄 — 모델이 원문을 다르게 인용해 제안을 버렸습니다: "
            f"'{before}' (실제 원문 '{original}')"
        )

    after = _restore_padding(original, after.strip())
    if after == original:
        return None, None

    if not declared:
        return None, (
            f"[모델 제안 차단] {index}번 줄 — 무엇을 바꿨는지 밝히지 않아 버렸습니다: "
            f"'{original}' -> '{after}'"
        )

    if len(declared) > _MAX_DECLARED_PER_LINE:
        return None, (
            f"[모델 제안 차단] {index}번 줄 — 한 줄에서 {len(declared)}곳을 바꾸려 해 버렸습니다"
            f"(교정이 아니라 재작성입니다): '{original}' -> '{after}'"
        )

    if original.count("\n") != after.count("\n"):
        return None, (
            f"[모델 제안 차단] {index}번 줄 — 줄바꿈 개수를 바꾸려 해 버렸습니다"
            f"(줄 나눔은 화면 배치이지 교정 대상이 아닙니다): '{original}' -> '{after}'"
        )

    accepted, refusal = verify_edit(f"모델 제안({rule})", original, after, declared)
    if refusal:
        return None, refusal
    if accepted == original:
        return None, None

    return (
        FlagItem(
            line_index=index,
            original_text=original,
            reason=f"[모델 제안] {rule} — {', '.join(declared)} (확인 후 반영해 주세요)",
            suggested_fix=accepted,
        ),
        None,
    )


def _build_prompt(batch: list[tuple[int, str]]) -> str:
    """줄 번호와 텍스트만 담은 요청문. 타임코드·화자 설정은 넣지 않는다."""
    lines = "\n".join(f"{index}\t{text}" for index, text in batch)
    return (
        "아래는 자막 원고의 일부다. 각 줄은 `번호<탭>내용` 형식이다.\n"
        "문맥을 보고 판단해야 하는 오류만 찾아 JSON 배열로 답하라.\n\n"
        f"{lines}"
    )


def propose_corrections(
    entries: list[SubtitleEntry],
    settings: LlmSettings,
    markers: SubtitleMarkers | None = None,
    skip_indices: set[int] | frozenset[int] = frozenset(),
    complete: Callable[[str, LlmSettings], str] | None = None,
) -> tuple[list[FlagItem], list[AppliedNote]]:
    """규칙 교정이 끝난 entries를 모델에게 보여 주고 **제안만** 받아 온다.

    entries는 읽기만 한다. 반환값은 (확인 플래그, 로그)이며, 로그에는 무엇을 왜
    버렸는지가 들어간다 — 규칙 엔진의 `[자동 교정 차단]`과 같은 성격이다.

    `skip_indices`에는 사투리 protect 화자의 줄 번호를 넣는다. 그 대사는 규칙
    엔진이 통째로 건너뛰는 자리이므로 모델에게 보내지도 않는다. 보내면 모델은
    반드시 사투리를 표준어로 고치려 든다.

    `complete`는 시험용 주입점이다. 넣지 않으면 실제 HTTP 호출을 쓴다.
    """
    if not settings.enabled or not entries:
        return [], []

    caller = complete or (_chat_cli if settings.backend == "cli" else _chat)
    notes: list[AppliedNote] = []

    candidates: list[tuple[int, str]] = []
    for entry in entries:
        if entry.index in skip_indices:
            continue
        if not entry.text.strip():
            continue
        # 표지만 있는 줄(효과음·위치 지정 등)은 어문 규범의 대상이 아니다.
        if _is_marker_only_line(entry.text, markers):
            continue
        # 보호 표지가 섞인 줄은 통째로 건너뛴다. 표지 안쪽을 지키면서 바깥만
        # 교정하려면 구간을 쪼개 보내야 하는데, 그러면 문맥이 끊겨 이 패스의
        # 값어치가 사라진다. 규칙 엔진이 이미 그 줄의 바깥 구간을 처리했다.
        if markers and any(
            token and token in entry.text
            for token in (markers.screen_text, markers.line_break, markers.position)
        ):
            continue
        candidates.append((entry.index, entry.text))

    if not candidates:
        return [], []

    if settings.max_lines and len(candidates) > settings.max_lines:
        skipped = len(candidates) - settings.max_lines
        candidates = candidates[: settings.max_lines]
        notes.append(
            AppliedNote(
                message=(
                    f"[모델 검토 범위] 설정된 상한({settings.max_lines}줄)에 맞춰 앞에서부터만 "
                    f"검토했습니다 — 뒤쪽 {skipped}줄은 모델이 보지 않았습니다."
                )
            )
        )

    flags: list[FlagItem] = []
    text_by_index = dict(candidates)
    failed_batches = 0
    total_batches = 0

    for start in range(0, len(candidates), settings.batch_size):
        batch = candidates[start : start + settings.batch_size]
        total_batches += 1
        try:
            raw = caller(_build_prompt(batch), settings)
        except Exception as error:  # 네트워크·서버·응답 형식 어느 쪽이든 교정은 계속된다
            failed_batches += 1
            notes.append(
                AppliedNote(
                    message=(
                        f"[모델 호출 실패] {batch[0][0]}~{batch[-1][0]}번 줄 구간을 검토하지 "
                        f"못했습니다({type(error).__name__}: {error}). "
                        "이 구간에는 모델 제안이 없습니다 — 규칙 교정 결과는 정상입니다."
                    )
                )
            )
            continue

        proposals, parse_failure = _parse_proposals(raw)
        if parse_failure is not None:
            # 응답은 왔지만 제안 목록이 없다. 이 구간은 검토되지 않은 것이므로
            # 호출 실패와 같은 무게로 알린다 — 조용히 넘기면 "모델이 괜찮다고 했다"가 된다.
            failed_batches += 1
            hint = ""
            if _SCHEMA_SUPPORT.get((settings.base_url, settings.model)) is False:
                hint = " (이 서버는 출력 스키마 강제를 지원하지 않아 형식을 지시문에만 의존했습니다)"
            notes.append(
                AppliedNote(
                    message=(
                        f"[모델 응답 형식 오류] {batch[0][0]}~{batch[-1][0]}번 줄 구간의 응답에서 "
                        f"제안 목록을 읽지 못했습니다{hint}. 이 구간은 검토되지 않은 것으로 "
                        f"보셔야 합니다 — 받은 응답: {parse_failure}"
                    )
                )
            )
            continue

        for proposal in proposals:
            flag, refusal = _accept(proposal, text_by_index)
            if flag:
                flags.append(flag)
            if refusal:
                notes.append(AppliedNote(message=refusal, is_edit=False))

    if failed_batches and failed_batches == total_batches:
        notes.append(
            AppliedNote(
                message=(
                    "[모델 검토 없음] 모든 구간의 호출이 실패해 이번 결과에는 모델 제안이 "
                    "하나도 반영되지 않았습니다(주소·모델 이름·키를 확인해 주세요)."
                )
            )
        )
    elif flags:
        notes.append(
            AppliedNote(
                message=(
                    f"[모델 제안] 문맥 판단이 필요한 자리 {len(flags)}건을 제안 목록에 올렸습니다. "
                    "본문은 바꾸지 않았습니다 — 확인하고 고르셔야 반영됩니다."
                )
            )
        )

    return flags, notes
