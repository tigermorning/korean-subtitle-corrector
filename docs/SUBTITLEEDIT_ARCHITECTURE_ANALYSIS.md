# SubtitleEdit 코드 분석 — 재사용 지점과 빈 땅

분석일: 2026-08-11
분석 대상: `git clone --depth 1 https://github.com/SubtitleEdit/subtitleedit` → `/mnt/c/Users/user/Documents/subtitleedit-src` (67MB, C# 파일 2,330개)
목적: 이 코드보다 자동화·정확도가 한 단계 위인 자막 편집기를 만들기 위한 사전 조사

## 1. 라이선스

- 저장소 전체 **MIT** (GitHub API `spdx_id: MIT`). 카피레프트 아님 → 포크·상용화·클로즈드 배포 가능, 저작권 고지만 유지
- **`libse`는 NuGet 패키지로 분리 배포됨**: `libse` 5.1.0 (2026-07-29), MIT, .NET Standard 2.1 / .NET 10, 누적 56만 다운로드
  → UI 코드를 뜯지 않고 엔진만 의존성으로 가져올 수 있다
- 별도 저장소 `SubtitleEdit/subtitleedit-cli`는 **LGPL-3.0**이고 SE 3.6.9 기반 구버전이다. 혼동 주의
- 번들 컴포넌트(ffmpeg, Tesseract, hunspell 사전, Whisper 모델)는 각자 라이선스 → 재배포 시 별도 확인

## 2. 구조 지도

```
src/
├── libse/        712개  ← 엔진 (NuGet 배포분)
│   ├── SubtitleFormats/   408개  ← 자막 포맷 구현체. 여기가 이 프로젝트의 최대 자산
│   ├── Common/             92개  ← Paragraph, Subtitle, Utilities, 텍스트 계산기
│   ├── ContainerFormats/   70개  ← mp4/mkv/ts 컨테이너 파싱
│   ├── Forms/              52개  ← FixCommonErrors, RemoveTextForHI, SplitLongLines 등 로직
│   ├── Cea608/ Cea708/     40개  ← 방송 캡션
│   ├── BluRaySup/ VobSub/  20개  ← 이미지 자막
│   └── Interfaces/          8개
├── libuilogic/          ← Whisper(AudioToText) 등 UI 비의존 로직
├── ui/                  ← 화면 + Netflix Quality Check
└── seconv/              ← CLI 변환기
```

## 3. 확장점 세 개 (여기에 붙이면 된다)

### 3.1 `IFixCommonError` — 교정 규칙 플러그인

`src/libse/Interfaces/IFixCommonError.cs`, 인터페이스가 딱 한 줄이다:

```csharp
public interface IFixCommonError
{
    void Fix(Subtitle subtitle, IFixCallbacks callbacks);
}
```

구현체가 `src/libse/Forms/FixCommonErrors/` 아래 40개 넘게 있다 (`FixLongLines`, `FixShortDisplayTimes`, `FixMusicNotation`, `FixHyphensInDialog`, `FixInvalidItalicTags`, `FixContinuationStyle` …).

`FixLongLines.cs` 실제 구현 — 패턴이 단순하다:

```csharp
if (HasTooLongLine(p.Text.SplitToLines()) && callbacks.AllowFix(p, fixAction))
{
    var oldText = p.Text;
    p.Text = Utilities.AutoBreakLine(p.Text, callbacks.Language);
    if (oldText != p.Text) { callbacks.AddFixToListView(p, fixAction, oldText, p.Text); }
}
```

→ **한국어 규칙 하나 = 클래스 하나.** 우리 룰(T5 줄 끝 마침표, S5 `[외국어로 말한다]` 등)을 이 인터페이스로 그대로 구현 가능.

### 3.2 `ICalcLength` — 글자 수 계산 전략

`src/libse/Common/TextLengthCalculator/` 에 전략 패턴으로 13개. `CalcFactory.MakeCalculator(strategy)`로 갈아끼운다.

`CalcCjk.cs`가 **넷플릭스 한국어 규칙을 이미 구현하고 있다**: 한글·CJK는 1자, 나머지(라틴·공백·문장부호)는 0.5자.

```csharp
else if (... LanguageAutoDetect.Letters.Korean.Contains(ch) || IsCjk(ch)) { length++; }
else { length += 0.5m; }
```

### 3.3 `RulesProfile` — 플랫폼 프로파일

`src/libse/Common/RulesProfile.cs`. JSON 직렬화되는 설정 묶음:

`SubtitleLineMaximumLength` / `SubtitleMaximumCharactersPerSeconds` / `SubtitleOptimalCharactersPerSeconds` / `SubtitleMinimumDisplayMilliseconds` / `SubtitleMaximumDisplayMilliseconds` / `MinimumMillisecondsBetweenLines` / `CpsLineLengthStrategy` / `MaxNumberOfLines` / `DialogStyle` / `ContinuationStyle`

→ "넷플릭스 한국어 SDH", "넷플릭스 한국어 번역" 프로파일을 데이터로 정의할 자리가 이미 있다.
→ **단, 지금은 수치만 담는다.** 표기 규칙(따옴표 역할, 화자 표시 형식, 금지 표현)은 담을 필드가 없다. 여기가 확장 포인트.

## 4. 이미 구현돼 있는 것 (헛수고 방지)

**`src/ui/Logic/NetflixQualityCheck/`** — 넷플릭스 QC가 이미 있다. 체크 17종:

BridgeGaps / DialogHyphenSpace / EllipsesNotThreeDots / Glyph / Italics / MaxCps / MaxDuration / MaxLineLength / MinDuration / NumberOfLines / NumbersOneToTenSpellOut / ShotChange / StartNumberSpellOut / TextForHiUseBrackets / TimedTextFrameRate / TwoFramesGap / WhiteSpace

그리고 **`NetflixQualityController`는 `IsSDH`와 `IsChildrenProgram` 플래그로 SDH/번역을 이미 구분한다.** 한국어 수치도 우리가 정리한 공식 규정과 정확히 일치:

| 조건 | ko 값 | 우리 문서 |
|---|---|---|
| 번역 자막 성인 | 12 CPS | 12 ✓ |
| 번역 자막 아동 | 9 CPS | 9 ✓ |
| SDH 성인 | 14 CPS | 14 ✓ |
| SDH 아동 | 11 CPS | 11 ✓ |
| 한 줄 최대 | 16자 | 16 ✓ |

`NetflixCheckMaxLineLength`는 `ko`일 때 `CalcCjk`로 세도록 분기까지 돼 있다.

**결론: 수치 검사는 이미 끝난 영역이다. 여기를 다시 만들면 낭비다.**

그 외 이미 있는 자동화: Whisper 받아쓰기(AudioToText, CppEngine·ConstMe·CTranslate2·FasterWhisper), 번역 엔진 73개 파일 규모, OCR, 싱크 보정(TimeCodesBeautifier), 갭 브리징, HI 텍스트 제거(RemoveTextForHI).

## 5. 빈 땅 (진짜 기회)

### 5.1 한국어 언어 지식이 통째로 없다

- **`Dictionaries/ko_NoBreakAfterList.xml`이 없다.** (ar, bg, cs, da, de, el, en, es, et, fi, fr, hr, hu, id, it, lt, lv, mk, nb … 있는데 ko만 없음)
- `Utilities.AutoBreakLinePrivate`은 `IsCjkLanguage(language)`면 **공백 기준 어절 분리 경로를 아예 타지 않는다.** 한국어 조사·의존명사·어절 인식이 0이다
- 즉 **한국어 줄바꿈 품질은 사실상 "글자 수로 자르기"** 수준. 넷플릭스가 요구하는 "역피라미드 + 문법 단위 유지"를 못 지킨다

→ 여기가 정확도로 이길 수 있는 1순위 지점이다. 그리고 이 프로젝트(korean-subtitle-corrector)가 이미 한국어 형태소·맞춤법 자산을 갖고 있다.

### 5.2 표기 규칙(문서 규정)은 검사 안 한다

넷플릭스 QC 17종은 전부 **형식·수치·글리프** 검사다. 아래는 전무:

| 미구현 규칙 | 근거 |
|---|---|
| 줄 끝 마침표·쉼표 금지 (한국어 전용) | Korean TTSG I.13 |
| 큰따옴표=화면 텍스트 / 작은따옴표=인용 역할 구분 | I.14 |
| `[외국어로 말한다]` 금지 | SDH II.6 |
| 효과음 어미 "들린다/소리" 지양 | SDH II.9 |
| `[말을 더듬으며]` 지양 | SDH II.9 |
| ♪ 와 텍스트 사이 공백, 음표 짝 맞춤 | SDH II.7 |
| 화자 표시 일관성 (`[김 경위]` ↔ `[진수]` 혼용) | SDH II.8 |
| 삐 처리 `*` 개수 = 음절 수 | SDH II.10 |
| 존댓말/반말 일관성 | I.19 |
| 24시간제·원화 환산·비미터법 | I.12 |
| 강제 자막과 대사 혼재 | I.8 |
| 자막 내 동일 어구 반복 번역 | I.16 |

### 5.3 자동화 레벨

SE의 자동화는 **"기능 단위 수동 실행"**이다. 사용자가 메뉴를 눌러 Whisper 돌리고, 눌러 Fix common errors 돌리고, 눌러 Netflix check 돌린다.

한 단계 위 = **프로파일 지정 → 전 파이프라인 무인 실행 → 근거 리포트**:
영상 입력 → 받아쓰기/싱크 → 플랫폼 프로파일 로드 → 형식 교정 → 한국어 언어 교정 → 규정 위반 리포트(조항 번호 인용) → 납품 포맷 출력.

## 6. 판단

이길 지점은 "포맷 파서"나 "CPS 계산기"가 아니다. 그건 libse가 이미 압도적이고 MIT라 그냥 가져다 쓰면 된다.

이길 지점 두 개:
1. **한국어 언어 계층** — 조사·어미·경어체·줄바꿈. SE에 완전히 비어 있고, 이 프로젝트에 이미 있다.
2. **규정 준수 계층** — 공식 스타일 가이드 조항을 데이터로 정의하고 위반을 조항 번호와 함께 리포트. SE의 QC는 넷플릭스 형식 검사 일부만 커버.

## 7. 다음 결정 사항

- [ ] 언어/런타임: C#으로 libse 직접 참조 vs 파이썬 유지 + seconv/libse를 CLI·서비스로 호출
- [ ] 규칙 표현 방식: 코드(IFixCommonError 구현) vs 데이터(YAML/JSON 규칙 파일 + 인터프리터)
- [ ] 이 저장소를 포크할지, libse만 NuGet 의존성으로 쓸지
- [ ] `ko_NoBreakAfterList.xml` 만들어 업스트림에 기여할지(신뢰도·홍보 효과)
- [ ] .NET SDK 설치 (현재 이 환경에 `dotnet` 없음)

## 8. 참고

- 저장소: https://github.com/SubtitleEdit/subtitleedit (MIT, 별 13.8k, 마지막 푸시 2026-08-10)
- NuGet: https://www.nuget.org/packages/libse (5.1.0, 2026-07-29)
- CLI(별도, LGPL-3.0): https://github.com/SubtitleEdit/subtitleedit-cli
- 로컬 클론: `/mnt/c/Users/user/Documents/subtitleedit-src`
- 관련 문서: `SUBTITLE_GUIDE_SDH.md`, `SUBTITLE_GUIDE_TRANSLATION.md`
