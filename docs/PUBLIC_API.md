# 공개 계약 — 이 저장소를 라이브러리로 부를 때

이 교정기는 **다른 도구가 `import`해서 쓴다.** 아래 넷은 그 도구가 기대는 모양이고,
바꾸면 밖이 깨진다. **우리 시험은 그것을 못 잡는다** — 우리 시험은 우리 호출부만 본다.

`tools/check_public_api.py`가 이 문서의 내용을 정적으로 지킨다(커밋 훅에 물려 있다).

---

## 1. `subtitle_corrector.engine.pipeline.correct_entries`

```python
correct_entries(
    entries: list[SubtitleEntry],
    ...,
    doc_type: str = "subtitle",
    spacing_mode: str = "principle",
    ...,
) -> tuple[list[SubtitleEntry], list[FlagItem], list[AppliedNote]]
```

- **반환은 3-튜플이다**: (자동 교정이 반영된 entries, 플래그 목록, 자동 교정 로그)
- 부르는 쪽은 **문서 전체를 한 번에** 넘긴다. 용어 일관성·존댓말 검사가 문서 단위라
  줄 단위로 쪼개 부르면 판정이 달라진다
- `doc_type`·`spacing_mode`는 **이름으로 넘긴다**(위치 인자로 받지 않는다)

## 2. `subtitle_corrector.parsers.SubtitleEntry`

`index` · `start` · `end` · `text`

밖에서는 타임코드를 갖고 있지 않은 채로 부르기도 한다(`start=""`, `end=""`).
**타임코드가 비어도 교정이 돌아야 한다.**

## 3. `subtitle_corrector.report.FlagItem`

`line_index` · `original_text` · `suggested_fix` · `reason`

밖은 이 넷을 그대로 자기 리포트로 옮긴다. 이름이 바뀌면 그 리포트가 빈칸이 된다.

## 4. `subtitle_corrector.report.AppliedNote`

`message` · `line_index` · `is_edit` · **`text()`**

**2026-08-04에 실제로 깨진 자리다**(구현 이력 §59). 그전에는 자동 교정 로그가 문자열
목록이었고, 밖에서 `"[12] …"` 같은 문자열을 다시 파싱하고 있었다. 구조로 바꾸면서
그 파싱이 조용히 깨졌다.

사람이 읽는 한 줄이 필요하면 **`text()`를 쓴다.** 문자열을 다시 파싱하지 않는다 —
로그 문구를 바꿀 때마다 깨진다.

`line_index`가 `None`이면 문서 전체에 대한 안내이고, `is_edit`이 거짓이면 무언가를
**하지 않았다**는 안내다. 줄 단위 되돌리기가 이 둘에 기댄다.

---

## 계약을 바꿔야 할 때

1. `tools/check_public_api.py`의 `CONTRACT`를 고친다
2. 이 문서를 고친다
3. **그 커밋 메시지에 "밖이 깨진다"를 적는다**

검사가 막는 것은 실수이지 결정이 아니다. 일부러 바꾸는 것은 막지 않는다 — 다만
**모르고 바꾸는 일이 없게** 한다.

## 이 문서가 부르는 쪽을 적지 않는 이유

이 저장소는 **일반 사용자용 범용 교정기**다. 어떤 도구가 이것을 쓰는지 알 필요가 없고,
알면 그쪽 사정이 이 저장소 설계에 스며든다. 의존은 한 방향이다 — 밖이 우리를 부르고,
우리는 밖을 모른다.
