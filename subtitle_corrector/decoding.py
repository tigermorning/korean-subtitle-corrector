"""업로드 파일을 **바이트 그대로 읽어** 텍스트로 만드는 유일한 경로.

왜 필요한가 (2026-08-03 사용자 지적): 이 도구가 교정하는 것은 사용자가 가진 파일이어야
한다. 우리가 읽어 낸 텍스트가 파일과 다르면, 그 뒤의 교정이 아무리 정확해도 **다른 문서를
고친 것**이 된다. 원문 왜곡은 오교정보다 심각하다.

전에는 모든 파서가 `read_text(encoding="utf-8-sig")`로 하드코딩돼 있었다. 국내 자막
파일에 흔한 cp949(EUC-KR) 파일은 그 자리에서 `UnicodeDecodeError`로 죽었고, 운이 나쁘면
깨진 글자로 읽혔다. 인코딩 판정을 한곳에 모아 그 사고를 없앤다.

판정 순서와 근거:

1. **BOM이 있으면 BOM을 따른다** — UTF-8/UTF-16 BOM은 파일이 스스로 밝힌 인코딩이라
   추측이 아니다.
2. BOM이 없으면 **UTF-8로 엄격히 디코드**해 본다. UTF-8은 아무 바이트열이나 통과하지
   않으므로(다바이트 시퀀스 규칙이 엄격하다) 성공하면 UTF-8로 보아도 안전하다.
3. 실패하면 **cp949 → euc-kr** 순으로 시도한다. cp949는 euc-kr의 확장이라 먼저 본다.
4. 그래도 실패하면 어떤 인코딩인지 알 수 없다 — **글자를 추측해 채우지 않고**
   `UnicodeDecodeError`를 그대로 올린다. 깨진 글자로 교정하는 것보다 실패가 낫다.
"""

import codecs
from pathlib import Path

# BOM → 그 BOM에 맞는 코덱 이름. 긴 BOM부터 봐야 UTF-32 BOM을 UTF-16으로 잘못 읽지 않는다.
_BOM_CODECS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

# BOM이 없을 때 시도할 순서. 한국어 자막 파일에서 실제로 쓰이는 것만 둔다.
_FALLBACK_CODECS = ("utf-8", "cp949", "euc-kr")


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """(텍스트, 사용한 인코딩)을 돌려준다. 어느 것으로도 못 읽으면 예외를 올린다."""
    for bom, codec in _BOM_CODECS:
        if raw.startswith(bom):
            return raw.decode(codec), codec
    last_error: UnicodeDecodeError | None = None
    for codec in _FALLBACK_CODECS:
        try:
            return raw.decode(codec), codec
        except UnicodeDecodeError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def normalize_newlines(text: str) -> str:
    """CRLF·CR을 LF로 맞춘다.

    `Path.read_text()`는 이 변환(universal newlines)을 자동으로 해 주는데, 인코딩을
    직접 판정하려고 `read_bytes()`로 바꾸면 그 변환이 사라진다. 그대로 두면 CRLF
    자막(윈도우 도구가 만드는 `.srt` 대부분)에서 `split("\\n\\n")`이 먹지 않아 **파일
    전체가 자막 한 항목으로 뭉친다** — 타임코드까지 대사에 섞여 들어간다. 이 함수를
    빼먹고 실측에서 바로 확인했다(2026-08-03).
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_text(path: Path) -> str:
    """파일을 인코딩 판정과 함께 읽는다. 파서들은 이 함수만 쓴다."""
    return normalize_newlines(decode_bytes(Path(path).read_bytes())[0])


def detect_encoding(path: Path) -> str:
    """어떤 인코딩으로 읽었는지만 알려 준다(사용자에게 보고할 때 쓴다)."""
    return decode_bytes(Path(path).read_bytes())[1]


def verify_ingest_fidelity(source_text: str, texts: list[str]) -> list[str]:
    """읽어 낸 대사들이 **원문에 그대로 있는지** 확인한다.

    "우리가 교정하는 것이 사용자의 파일인가"를 매번 증명하기 위한 검사다(2026-08-03
    사용자 요구: "사용자가 업로드한 원문 그대로를 가져와 교정해야 한다"). 파서가 원문을
    조금이라도 바꿔 놓으면 그 뒤 교정이 아무리 정확해도 **다른 문서를 고친 것**이 된다.

    판정: 각 대사가 원문(개행만 LF로 맞춘 것)의 부분 문자열이어야 한다. 파싱은 구조를
    **잘라내는** 일이지 글자를 바꾸는 일이 아니므로, 형식과 무관하게 성립해야 하는
    조건이다. 실제로 이 검사가 CRLF 자막에서 파일 전체가 한 항목으로 뭉치던 사고를
    잡아냈다(개행 정규화 누락).

    돌려주는 값: 어긋난 항목의 설명 목록. 빈 목록이면 원문과 같다.
    """
    normalized = normalize_newlines(source_text)
    problems = []
    for i, text in enumerate(texts, start=1):
        if not text.strip():
            continue
        if text not in normalized:
            problems.append(
                f"{i}번째 항목이 원문에 그대로 없습니다(파싱이 원문을 바꿨습니다): {text!r}"
            )
    return problems
