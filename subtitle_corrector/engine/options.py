"""문서 단위 설정값과 그 정규화. 어문 규범이 하나로 정해 주지 않아 납품처·작품마다
달라지는 선택지(구두점 표기, 제47항 기준, 자막 편집 표지, 사투리 모드)를 모은다.
"""

from typing import NamedTuple

# 구두점 표기 방식. 말줄임표와 따옴표를 어떤 글자로 쓸지는 어문 규범이 하나로
# 정해 주지 않고 **납품처마다 다르다**(사용자 지정 2026-08-02). 기본값은 반각 기호와
# 온점 세 개 — 자막 편집기·플레이어 호환이 가장 넓기 때문이다.
#
#   ellipsis: "keep" -> 원문 유지(기본) / "dots" -> ...      / "char" -> …
#   quotes:   "keep" -> 원문 유지(기본) / "half" -> ' 와 "   / "full" -> ‘ ’ 와 “ ”
#
# **기본값을 "원문 유지"로 바꿨다(2026-08-03).** 전에는 온점 세 개·곧은따옴표가
# 기본이어서, 실제 원고를 넣으면 원문의 '…'와 '“ ”'가 문서 전체에서 통째로 바뀌었다.
# 문장부호 규정은 말줄임표를 '……'(원칙)·'…'·'......'·'...' 모두 인정하고 따옴표도
# 두 표기를 다 허용한다 — 즉 이 변환은 교정이 아니라 **맞는 표기를 다른 맞는 표기로
# 바꾸는 임의 치환**이다. 낱말에서 그것을 금지하는 원칙(평가셋 t12: '도리어'를 '되레'로
# 바꾸지 않는다)이 부호에도 똑같이 적용된다. 납품처가 특정 표기를 요구할 때만 고른다.
ELLIPSIS_STYLES = ("keep", "dots", "char")


QUOTE_STYLES = ("keep", "half", "full")


class PunctuationStyle(NamedTuple):
    ellipsis: str = "keep"
    quotes: str = "keep"


def normalize_punctuation_style(ellipsis_style=None, quote_style=None) -> PunctuationStyle:
    """설정값을 정규화한다. 모르는 값은 기본값(원문 유지)으로 떨어뜨린다."""
    ellipsis_value = str(ellipsis_style or "").strip().lower()
    quote_value = str(quote_style or "").strip().lower()
    return PunctuationStyle(
        ellipsis_value if ellipsis_value in ELLIPSIS_STYLES else "keep",
        quote_value if quote_value in QUOTE_STYLES else "keep",
    )


# 한글 맞춤법 제47항은 보조 용언을 "띄어 씀을 원칙으로 하되, 붙여 씀도 허용"한다.
# 둘 다 맞는 표기이므로 어느 쪽을 쓸지는 규범이 아니라 작품의 선택이고, 대신
# 한 작품 안에서는 한쪽으로 통일해야 한다(혼용은 그 자체가 교정 대상이다).
# 그래서 이 값은 문서 단위로 한 번만 정하고 모든 줄에 같은 값을 적용한다.
#   principle — 원칙: 붙여 쓴 것을 띄어 쓴다(기본값)
#   allowance — 허용: 띄어 쓴 것을 붙여 쓴다
#
# **선택지는 둘뿐이다(2026-08-05 사용자 결정: "'원문 유지'는 불필요해").** 전에는
# `keep`(원문 유지)이 기본값이었다 — 제47항이 둘 다 인정하므로 맞는 표기를 다른 맞는
# 표기로 바꾸지 말자는 취지였다(2026-08-04). 그런데 그 선택지는 **혼용을 그대로 두는
# 것**이기도 하다: 한 작품 안에서 두 표기가 섞이는 것은 규범이 인정하는 선택이 아니라
# 교정 대상이고, `keep`을 고르면 도구가 그 사실을 플래그로 알릴 뿐 고치지는 못한다.
# 어느 기준이든 하나를 고르면 문서가 그 기준으로 통일되므로, 고르지 않는 선택지는
# 사용자에게 "혼용을 남기겠다"는 뜻밖에 되지 않는다.
SPACING_MODES = ("principle", "allowance")


def normalize_spacing_mode(mode: str | None) -> str:
    """띄어쓰기 기준을 SPACING_MODES 중 하나로 정규화한다.

    모르는 값·빈 값은 원칙(principle)으로 떨어뜨린다 — 화면 2단계의 '띄어쓰기 기준'이
    원칙으로 미리 선택돼 있으므로 값이 안 왔을 때도 같은 결과가 나와야 한다
    (2026-08-04 사용자 지정: "사용자가 2단계에서 지정한 대로 해야 한다").
    없어진 `keep`도 여기서 원칙으로 흡수된다 — 옛 요청·저장된 설정이 오류가 되지
    않게 한다.
    """
    value = str(mode or "").strip().lower()
    return value if value in SPACING_MODES else "principle"


# 화자별 사투리 처리 모드.
#   - "protect": (지정된 화자의 기본값) 사투리를 그대로 보호한다. 어떤
#     자동 교정도, 어떤 플래그도 남기지 않는다. 대본 속 사투리는 대부분
#     작가의 의도이므로 기본적으로 건드리지 않는다.
#   - "assist": 텍스트는 그대로 두고, 표준어→사투리 제안 플래그만 남긴다
#     (작가가 사투리 화자를 원하지만 사투리에 익숙하지 않은 경우 도움).
#   - "to_standard": 사투리→표준어 자동 변환 + 확인 플래그(드문 opt-in).
_VALID_DIALECT_MODES = frozenset({"protect", "assist", "to_standard"})


# 이전 모드명과의 하위 호환: 옛 호출부가 넘기는 문자열을 새 모드로 매핑한다.
#   - "flag_only"(사투리를 의심스러운 것으로 플래그하던 옛 기본값) → "protect"
#   - "to_dialect"(표준어→사투리 자동 재작성) → "assist"
_DIALECT_MODE_ALIASES = {
    "flag_only": "protect",
    "to_dialect": "assist",
}


def normalize_dialect_mode(mode: str | None) -> str:
    """모드 문자열을 유효한 새 모드명으로 정규화한다.

    빈 값/미지정은 "protect"(기본값). 하위 호환 별칭(flag_only/to_dialect)은
    각각 protect/assist로 매핑한다. 알 수 없는 값도 안전하게 "protect"로 둔다.
    """
    if not mode:
        return "protect"
    mode = _DIALECT_MODE_ALIASES.get(mode, mode)
    if mode not in _VALID_DIALECT_MODES:
        return "protect"
    return mode


def resolve_dialect_mode(
    speaker: str | None,
    dialect_map: dict[str, str] | None,
    dialect_modes: dict[str, str] | None,
    document_region: str | None = None,
    document_mode: str | None = None,
) -> tuple[str | None, str | None]:
    """화자의 사투리 (지역, 모드)를 결정한다.

    화자별 지정이 우선이고, 없으면 문서 전체 설정으로 내려간다. 자막처럼 화자가
    갈리는 문서는 화자별로, 소설처럼 글 전체가 한 사투리인 문서(예: 박경리 '토지'를
    표준어로 바꾸는 경우)는 문서 전체 설정으로 다루기 위해서다. 일반 글에는 화자
    표기 자체가 없어서, 문서 전체 설정이 없으면 사투리 기능이 아예 걸리지 않는다.

    반환값:
        - 화자가 dialect_map에 있으면 (그 화자의 지역, 정규화된 모드).
        - 아니고 document_region이 있으면 (문서 전체 지역, 정규화된 문서 전체 모드).
        - 둘 다 없으면 (None, None) — 사투리 미지정.
    """
    if dialect_map and speaker and speaker in dialect_map:
        return dialect_map[speaker], normalize_dialect_mode((dialect_modes or {}).get(speaker))
    if document_region:
        return document_region, normalize_dialect_mode(document_mode)
    return None, None


# 자막 편집 표지. 업계 공통 규칙이 없어 작업자·편집기마다 다르므로 값을 하드코딩하지
# 않고 그때그때 설정으로 받는다(사용자 지정 2026-08-02). 여기 지정된 표지는 어문
# 규범의 대상이 아니라 기술적 표지이므로 교정에서 제외한다.
#
#   screen_text — 화면자막 표기. 짝이 있는 문자('"', "'", '「' 등)를 주면 감싸인
#                 구간만, 짝이 없는 문자('@', '#' 등)를 주면 그 줄 전체를 제외한다.
#   line_break  — 줄바꿈 표기('|' 등). 교정할 때만 실제 줄바꿈으로 취급해 줄 끝
#                 마침표 규칙 등이 화면과 같게 적용되도록 하고, 결과에는 표지를
#                 그대로 되돌린다.
#   position    — 자막 위치 표기('{\\an8}' 등). 제어 코드라 통째로 보호한다.
_MARKER_PAIRS = {
    '"': '"', "'": "'", "“": "”", "‘": "’",
    "「": "」", "『": "』", "《": "》", "〈": "〉",
    "(": ")", "[": "]", "<": ">", "{": "}",
}


# 화자명·어조 표기에 쓰는 부호. OTT·스튜디오마다 대괄호와 괄호가 갈려서 이것도
# 설정으로 받는다(사용자 지정 2026-08-02). 값을 안 주면 대괄호를 쓴다 — 지금까지의
# 동작이 대괄호 기준이었으므로 기본값을 바꾸면 기존 사용자의 결과가 달라진다.
_DEFAULT_TAG_BRACKET = "[]"


class SubtitleMarkers(NamedTuple):
    screen_text: str = ""
    line_break: str = ""
    position: str = ""
    speaker: str = _DEFAULT_TAG_BRACKET
    tone: str = _DEFAULT_TAG_BRACKET

    @property
    def any_set(self) -> bool:
        return bool(self.screen_text or self.line_break or self.position)


def _normalize_bracket_pair(value: str | None) -> str:
    """'[', '[]', '(' 처럼 들어온 값을 '여는+닫는' 두 글자로 맞춘다.

    한 글자만 주면 짝을 찾아 채우고(_MARKER_PAIRS), 짝이 없는 문자면 미설정으로
    본다 — 화자명 표기는 여닫는 짝이 있어야 어디까지가 화자명인지 정해진다.
    """
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) >= 2:
        return value[0] + value[-1]
    closing = _MARKER_PAIRS.get(value)
    return value + closing if closing else ""


def normalize_subtitle_markers(
    screen_text: str | None = None,
    line_break: str | None = None,
    position: str | None = None,
    speaker: str | None = None,
    tone: str | None = None,
) -> SubtitleMarkers:
    """설정에서 받은 표지 문자열을 정규화한다.

    공백만 있는 값은 미설정으로 본다 — 표지가 공백이면 문서 전체가 보호 구간이
    되어 교정이 통째로 멈춘다. 화자명·어조 부호는 미설정이면 기본값(대괄호)이다.
    """
    return SubtitleMarkers(
        (screen_text or "").strip(),
        (line_break or "").strip(),
        (position or "").strip(),
        _normalize_bracket_pair(speaker) or _DEFAULT_TAG_BRACKET,
        _normalize_bracket_pair(tone) or _DEFAULT_TAG_BRACKET,
    )
