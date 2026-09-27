# FEATURE_MAP — 한국어 자막/문서 교정 웹앱

> **이 맵을 믿는 범위 (2026-09-25 재검토)**
> - 공통 섹션과 기능별 `사용자 경로`·`선택자`·`파일` 줄은 2026-09-25에 소스(`static/index.html`, `subtitle_corrector/api.py`)와 대조해 다시 감사했다.
> - `파일`·`선택자`는 체커(`my-skills/.claude/skills/feature-map/scripts/check_feature_map.py`)가 코드와 대조한다.
> - 문장으로 적은 `사용자 경로`·`검증`은 체커가 못 본다. 이번 재검토도 코드 읽기만 했고 앱은 실행하지 않았다.
> - `1차 작성 때 관찰(재확인 안 함)`은 예전 실행 기록이다. 지금도 그렇다는 보장은 없다.
> - `(미확인)`은 실행으로 확인된 적이 없다는 뜻이다.
> - 문장대로 동작하지 않으면 버그라고 단정하기 전에 `파일` 줄의 코드부터 확인한다.

UI는 한 페이지(`static/index.html`)이고, 그 페이지를 서빙하는 API(`subtitle_corrector/api.py`)와 같은 서버에서 돈다.

## 실행 방법

```powershell
cd korean-subtitle-corrector
.venv\Scripts\python.exe -m uvicorn subtitle_corrector.api:app --port <빈 포트>
```

- 저장소 기본 설정(`.claude/launch.json`의 `corrector-api`)은 포트 8000이다.
- 브라우저로 `http://127.0.0.1:<포트>/` 를 열면 페이지가 뜬다.
- 조작 대상은 일반 HTML 폼·버튼이다. 대부분 `id`로 찾을 수 있다.
- 환경변수 (`.env`, 값은 적지 않고 이름만):
  - 사전·규범 조회: `STDICT_API_KEY`, `OPENDICT_API_KEY`, `KORNORMS_API_KEY`, `ONYONGEO_KEY`, `KRDICT_KEY`, `DIALECT_API_KEY`
  - 결과 저장·공유 링크: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
  - 언어 모델 패스(선택): `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BACKEND`
  - 판정 기록장(선택): `FEEDBACK_LOG_DIR`
- 테스트 데이터: `examples/sample.srt` (자막), `examples/sample_dialect.srt`, `examples/sample_loanword.srt`

## 시작 전제조건

모든 검증이 아래 상태에서 시작한다고 가정한다. 기능 섹션이 따로 정하면 그쪽을 따른다.

- 서버가 자기 포트에서 떠 있고 `GET /` 가 200을 돌려준다.
- 페이지를 새로 열었다.
  - `2단계 · 교정 옵션` 패널은 접혀 있다.
  - `사용 목적`은 `일반 글`이 선택돼 있다.
  - `띄어쓰기 기준`은 `원칙 — 띄어 씀`이 선택돼 있다.
  - 결과 영역(`#result`)은 보이지 않는다.
- 로그인·계정 개념이 없다. 모달도 없다.
- 입력 파일은 `examples/sample.srt`처럼 저장소에 있는 예시만 쓴다.
- 교정 1회는 외부 서비스를 부른다. 그래서 (미확인: 이 환경에 키가 있는지) 다음이 필요하다.
  - 국립국어원 계열 사전 API에 연결되는 네트워크와 위 사전 키
  - 키가 없을 때 서버가 어떻게 반응하는지는 (미확인)
- 외부 서비스로 나가는 것:
  - 사전 API: 교정할 때마다 문장 속 단어를 조회한다.
  - 언어 모델: `LLM_MODEL`과 (주소 또는 로컬 `ollama`)가 있으면 켜진다. 켜지면 원고 일부가 그 모델로 간다. 화면에서는 끄고 켤 수 없다.
  - Supabase: `SUPABASE_URL`·`SUPABASE_SERVICE_KEY`가 있으면 교정 결과 전문이 저장된다.
- **사용자의 자막·원고 파일은 검증 중에 외부 서비스로 보내지 않는다.**
  - 저장소 루트에 있는 `*.srt`, `*.html` 과제·발표 파일은 사용자의 것이다. 올리지 않는다.
  - 예시 파일만 쓰더라도 위 세 경로로 그 내용이 나간다는 점을 보고에 적는다.
- 도구가 닿을 수 없는 것:
  - 브라우저 데스크톱 알림 권한 창 (OS·브라우저 UI)
  - 파일 선택 창 (OS 대화상자): `#fileInput`에 파일을 직접 주입할 수 있는 도구가 없으면 수동
  - 다운로드된 파일이 디스크에 저장되는 것 (브라우저 UI)
  - Supabase 저장 성공 경로: 이 환경에서 (미확인)

## 조작 관례

- **격리**
  - 사용자가 이미 띄운 서버(포트 8000 등)와 브라우저 프로필에 붙지 않는다.
  - 자기 포트를 정해 서버를 띄우기 전에 그 포트가 비어 있는지 확인한다.
  - 끝나면 **자기가 띄운 PID만** 종료한다. 이름으로 프로세스를 죽이지 않는다.
  - 저장소 루트의 `pid.txt`, `server.pid`는 사용자 것일 수 있으니 읽지도 지우지도 않는다.
- **사전 점검**
  - 조작 전에 `GET /` 와 `GET /api/dialect-regions` 가 200인지 본다. 아니면 멈춘다.
  - `#dialectRows`에 화자 안내문이 나오고 `#documentDialectRegion`에 지역 옵션이 채워졌는지도 본다.
- **대기**
  - 교정은 사전을 실시간 조회해서 오래 걸린다. 고정 `sleep`으로 끝났다고 보지 않는다.
  - 교정을 시작했다면 `#status`가 `교정 중입니다 · …경과`에서 `완료! (…)` 또는 `오류: …`로 바뀔 때까지 기다린다(경과는 1분이 지나면 `N분 M초 경과`로 표시). 입력이 없어 안내문이 뜬 경우와 `?id=` 접속에는 이 규칙을 적용하지 않는다.
  - 교정을 시작한 뒤에는 `#submitBtn`이 비활성이었다가 다시 활성화되면 끝난 것이다. 이 신호는 반드시 비활성이 확인된 뒤에만 쓰고, 단독으로 끝났다고 판단하지 않는다.
- **입력**
  - 좌표보다 `id`로 조작한다.
  - `2단계` 패널이 접혀 있으면 안의 입력칸을 조작할 수 없다. `2단계 · 교정 옵션` 요약줄을 눌러 먼저 연다.
  - 자막 전용 그룹(`#punctuationOptions`, `#markerOptions`)은 `사용 목적`을 `자막`으로 골라야 보인다.
- **읽기 전용 평가**
  - 페이지 JS 평가는 값·문구를 읽는 데만 쓴다.
  - `applySelectedFixes` 같은 함수를 직접 호출해 UI 조작을 대신하지 않는다.
- **콘솔**
  - `검증`에 "콘솔 에러 없음"이 있으면 콘솔을 켜 둔 채 조작한다.
- **API 직접 호출**
  - 페이지는 같은 서버의 `/api/...` 만 부른다. 다른 도메인 호출은 없다.
  - UI 동작을 검증할 때는 UI를 거친다. 아래 엔드포인트 직접 호출은 API 수준 확인에만 쓴다.
  - 직접 호출해도 되는 것:

    | 엔드포인트 | 조건 |
    |---|---|
    | `GET /api/dialect-regions` | 제한 없음. 외부 호출 없음 |
    | `GET /api/feedback/summary` | 읽기 전용 |
    | `GET /api/loanword-source?source=Ruth` | 짧은 로마자 낱말만. 국립국어원 API를 부른다 |
    | `POST /api/export/docx` | `text`에 임의의 짧은 문구만. 외부 호출 없음 |
    | `POST /api/correct` | `examples/` 파일만. 외부 사전(·설정 시 언어 모델·Supabase)으로 내용이 나간다 |
    | `GET /api/reports/{id}` | 알려진 id만. Supabase를 읽는다 |

  - 직접 호출하지 않는 것:
    - `POST /api/feedback`: `FEEDBACK_LOG_DIR`가 켜져 있으면 디스크에 기록이 남는다. 화면 조작으로만 일으킨다.
    - `POST /api/speakers`: 화면에서 부르지 않는다. 아래 `사용자가 닿을 수 없는 것` 참고.
- **건드리지 않기**
  - `.env`, `FEEDBACK_LOG_DIR` 폴더, Supabase 데이터는 바꾸지 않는다.
  - 교정 1회마다 Supabase에 리포트가 쌓일 수 있다. 몇 건 만들었는지 보고에 적는다.
  - 저장소 루트의 추적되지 않는 `발표_대본.html`은 사용자 소유다. 건드리지 않는다.
- **수동 영역**
  - OS 파일 선택 창, 데스크톱 알림 권한, 다운로드 저장은 도구가 지원하지 않으면 수동으로 표시한다.
- **스트리밍·로딩**
  - 결과는 스트리밍되지 않는다. `/api/correct` 응답 한 번으로 화면이 한꺼번에 채워진다.

## 증거와 건너뜀 보고

```markdown
- 대상: <기능 / 변경>
- 전제조건: 시작 전제조건 충족 여부 (다르면 무엇이 달랐는지)
- 한 것: <실행한 명령·조작 순서>
- 관찰: <본 것을 그대로 — 문구, 개수, 응답 코드, 로그 한 줄>
- 버그 수정이면: 수정 전 커밋에서 재현됨 / 수정 후 사라짐
- 증거 파일: <스크린샷·녹화·로그 경로> (없으면 "없음")
- 건너뜀: <맵에 있는 변형 중 못 한 것과 이유> (없으면 "없음")
```

- 맵에 나열된 변형 가운데 하나라도 빠졌으면 증거는 불완전하다. 빠진 것은 `건너뜀`에 적는다.
- `관찰`에는 본 것만 적는다. 코드에서 추론한 것은 `추론:`으로 따로 적는다.

## 기능

### 파일 업로드 후 교정
- 사용자 경로: 첫 화면 → `1단계 · 파일 선택`의 파일 입력 → `3단계 · 실행`의 `교정하기` 버튼
- 선택자: `#fileInput`, `#submitBtn`, `#status`, `#result`
- 파일: `static/index.html`, `subtitle_corrector/api.py::correct_subtitle`, `subtitle_corrector/engine/pipeline.py`
- 검증:
  - `examples/sample.srt` 선택 → `교정하기` → `#status`에 `완료! (` 로 시작하는 문구가 나온다.
  - `#result`가 보이고 `#correctedSrt`에 교정문이 채워진다.
  - `#appliedCount`, `#flagCount`가 숫자로 채워진다.
  - `#submitBtn`이 다시 활성화된다. 콘솔 에러는 없다.
  - 파일도 붙여넣은 글도 없이 `교정하기` → `#status`에 `파일을 선택하거나 글을 붙여넣으세요.`
  - 1차 작성 때 관찰(재확인 안 함): `POST /api/correct`에 `examples/sample.srt`를 보내 응답 JSON에서 `entries` 10건, `flags` 3건, `applied_log` 5건.

### 파일 없이 텍스트 붙여넣기
- 사용자 경로: 첫 화면 → `1단계 · 파일 선택` 아래 붙여넣기 칸에 글 입력 → `교정하기`
- 선택자: `#pasteInput`, `#submitBtn`
- 파일: `static/index.html`
- 검증: 파일 없이 짧은 문장을 붙여넣고 `교정하기` → `#status`에 `완료! (`, `#correctedSrt`에 글이 보인다. (미확인)

### 교정 옵션 패널 열기와 사용 목적
- 사용자 경로: 첫 화면 → `2단계 · 교정 옵션` 요약줄 클릭으로 펼침 → `사용 목적`의 `자막` / `일반 글` 라디오
- 선택자: `#optionsPanel`, `input[name="docType"]`, `2단계 · 교정 옵션`
- 파일: `static/index.html`, `subtitle_corrector/api.py::correct_subtitle`
- 검증:
  - 처음에는 `일반 글`이 선택돼 있고 `#optionsPanel`이 접혀 있다.
  - `자막`을 고르면 `#punctuationOptions`와 `#markerOptions`가 나타나고, `일반 글`로 돌리면 다시 사라진다. (미확인)

### 구두점 표기 (말줄임표·따옴표)
- 사용자 경로: `2단계` 펼침 → `사용 목적`을 `자막`으로 → `구두점 표기` 그룹의 `말줄임표`·`따옴표` 드롭다운
- 선택자: `#punctuationOptions`, `#ellipsisStyle`, `#quoteStyle`
- 파일: `static/index.html`, `subtitle_corrector/engine/options.py::normalize_punctuation_style`
- 검증:
  - `자막`일 때만 `#punctuationOptions`가 보인다.
  - 두 드롭다운에 `원문 유지 (권장)`, `온점 세 개 (...)`, `한 글자 (…)` / `곧은따옴표 ( ' " )`, `둥근따옴표 ( ‘ ’ “ ” )` 선택지가 있다. (미확인)

### 자막 편집 표지
- 사용자 경로: `2단계` 펼침 → `사용 목적`을 `자막`으로 → `자막 편집 표지` 그룹의 입력칸에 기호 입력
- 선택자: `#markerOptions`, `#screenTextMarker`, `#lineBreakMarker`, `#positionMarker`, `#speakerBracket`, `#toneBracket`
- 파일: `static/index.html`, `subtitle_corrector/api.py::correct_subtitle`, `subtitle_corrector/engine/options.py::normalize_subtitle_markers`
- 검증: `자막`일 때 다섯 입력칸이 보이고 각 칸에 흐린 예시 문구가 있다. 교정 결과에서 지정한 표지가 그대로 남는지는 (미확인)

### 띄어쓰기 기준
- 사용자 경로: `2단계` 펼침 → `띄어쓰기 기준`에서 `원칙 — 띄어 씀` / `허용 — 붙여 씀` 라디오
- 선택자: `input[name="spacingMode"]`, `띄어쓰기 기준`
- 파일: `static/index.html`, `subtitle_corrector/engine/options.py::normalize_spacing_mode`
- 검증: 기본으로 `원칙 — 띄어 씀`이 선택돼 있고 `허용 — 붙여 씀`으로 바꿀 수 있다. 결과 문장이 달라지는지는 (미확인)

### 고유명사·요리·음료 이름 등록
- 사용자 경로: `2단계` 펼침 → `[선택사항] 고유명사·요리·음료 이름` 칸에 한 줄에 하나씩 입력
- 선택자: `#namesInput`
- 파일: `static/index.html`, `subtitle_corrector/api.py::correct_subtitle`, `subtitle_corrector/engine/kiwi_adapter.py::register_custom_words`
- 검증: 이름을 적고 교정했을 때 오류 없이 `완료! (`이 뜬다. 그 이름이 쪼개지지 않는지는 (미확인)

### 사투리 설정 — 문서 전체
- 사용자 경로: `2단계` 펼침 → `[선택사항] 사투리 설정` → `문서 전체` 줄의 지역 드롭다운과 반영 수준 드롭다운
- 선택자: `#documentDialectRegion`, `#documentDialectMode`, `문서 전체`
- 파일: `static/index.html`, `subtitle_corrector/api.py::get_dialect_regions`, `subtitle_corrector/dictionary/dialect.py`
- 검증:
  - `#documentDialectRegion`의 선택지가 `설정 안함`과 서버가 준 지역 목록이다.
  - `#documentDialectMode`에 `그대로 보호 (교정·플래그 안 함)`, `사투리로 고쳐주기 제안`, `표준어로 바꾸기 제안 (자동 변환 아님)`이 있다. (미확인)
  - 1차 작성 때 관찰(재확인 안 함): `GET /api/dialect-regions` → `{"regions":["경상도","제주도","전라도","충청도"]}`.

### 사투리 설정 — 화자별
- 사용자 경로: `사투리 설정` → `화자 이름` 칸에 이름 입력 → `+ 화자 추가` → 생긴 행에서 지역·반영 수준 선택 → 행 끝 `×`로 삭제
- 선택자: `#newSpeakerName`, `#addSpeakerBtn`, `#dialectRows`, `.dialect-region-select`, `.dialect-mode-select`, `.remove-btn`, `+ 화자 추가`
- 파일: `static/index.html`, `subtitle_corrector/api.py::correct_subtitle`
- 검증:
  - 페이지를 연 직후 `/api/dialect-regions` 응답이 처리되고 나면 `#dialectRows`에 `사투리를 지정할 화자 이름을 아래에 직접 추가하세요.`가 보인다. 그 전에는 비어 있다.
  - 이름을 넣고 `+ 화자 추가`를 누르면 그 이름의 행이 생기고 칸이 비워진다.
  - 같은 이름을 다시 추가해도 행이 늘지 않는다.
  - `×`를 누르면 행이 사라진다. (미확인)

### 교정 결과 본문과 하이라이트 이동
- 사용자 경로: 교정 완료 후 `교정된 결과` 영역의 강조 문구 클릭 ↔ 아래 `자동 교정 로그`·`확인이 필요한 항목`의 항목 클릭
- 선택자: `#correctedSrt`, `.corr-line`, `#appliedList`, `#flagBody`, `.hl-active`, `자동 교정`, `확인 필요`
- 파일: `static/index.html`
- 검증:
  - 강조된 문구(`.corr-line`)를 누르면 같은 줄 번호의 로그 항목이나 확인 항목에 `hl-active` 테두리가 잠깐(약 1.6초) 붙는다.
  - 반대로 목록 항목을 누르면 본문 쪽 문구에 붙는다. (미확인)

### 자동 교정 로그와 줄 단위 되돌리기
- 사용자 경로: 결과 화면 `자동 교정 로그` 목록에서 항목의 `되돌리기` 체크 → `선택 반영하기 (제안 채택 + 자동 교정 되돌리기)` 버튼
- `되돌리기` 체크칸은 줄 번호가 있고 실제로 글자를 바꾼 로그 항목에만 있다. 문서 전체 안내 항목과 `?id=`로 다시 연 결과에는 없다.
- 선택자: `#appliedList`, `.auto-revert`, `#applyBtn`, `#appliedCount`, `#applyNote`, `되돌리기`
- 파일: `static/index.html`, `subtitle_corrector/api.py::correct_subtitle`
- 검증:
  - `되돌리기`를 체크하고 `#applyBtn`을 누르면 `#applyNote`에 `제안 N건 반영, 자동 교정 M건 되돌림.` 형태의 문구가 뜬다.
  - `#correctedSrt`에서 그 줄이 교정 전 문구로 돌아간다.
  - 아무것도 체크하지 않고 누르면 `반영할 항목을 먼저 체크하세요 (제안 채택 또는 자동 교정 되돌리기).`가 뜬다. (미확인)
  - 1차 작성 때 관찰(재확인 안 함): 응답 `applied_log` 원소가 `message`, `line_index`, `is_edit` 키를 가진다.

### 확인이 필요한 항목 표와 제안 채택
- 사용자 경로: 결과 화면 `확인이 필요한 항목` 표에서 `채택` 체크 → `선택 반영하기 (제안 채택 + 자동 교정 되돌리기)`
- 선택자: `#flagBody`, `.flag-pick`, `#flagCount`, `.flag-suggestion`, `#applyBtn`, `채택`
- 파일: `static/index.html`
- 검증:
  - 표에 `줄`, `내용`, `이유`, `제안` 열이 있고 `#flagCount`가 행 수와 같다.
  - 제안이 있는 행의 `채택`을 체크하고 `#applyBtn`을 누르면 `#correctedSrt`에 제안이 반영된다. 그 줄을 되돌렸거나 같은 줄에 다른 제안이 이미 반영됐으면 건너뛰고 `#applyNote`에 `N건은 그 줄이 이미 바뀌어 건너뛰었습니다`가 붙는다.
  - 확인 항목이 없으면 표에 `없음`이 보인다. (미확인)
  - 1차 작성 때 관찰(재확인 안 함): 응답 `flags`에 `line_index`, `original_text`, `reason`, `suggested_fix` 키가 있었고 3건이었다.

### 외래어 원어(로마자) 조회
- 사용자 경로: 확인 필요 항목 표의 이유 칸 안 `원어(로마자)` 입력칸에 로마자 입력 → `국립국어원 용례 확인` 버튼 → 후보 줄의 `'…'로 반영` 버튼
- 선택자: `.src-input`, `.src-btn`, `.src-result`, `.src-apply`, `원어(로마자)`, `국립국어원 용례 확인`
- 파일: `static/index.html`, `subtitle_corrector/api.py::get_loanword_by_source`, `subtitle_corrector/dictionary/clients.py`
- 검증:
  - 입력칸을 비운 채 버튼을 누르면 결과 칸에 `원어(로마자) 표기를 넣어 주세요.`
  - `Ruth`를 넣고 누르면 잠시 `조회 중…` 뒤 후보 목록이 뜬다. 서버 조회가 실패하면 `국립국어원 어문 규범 서버 조회에 실패했습니다.` 등 실패 문구가 뜬다.
  - 확정·일치 후보에는 `'…'로 반영` 버튼이 있다(그 줄에서 해당 토막을 찾지 못하면 버튼 대신 `(이 줄에서 그 토막을 찾지 못해 반영 버튼을 주지 않습니다)`가 나온다). `참고` 후보에는 버튼이 없다. 후보는 최대 8개까지 보인다.
  - 이 입력칸은 외래어 음차 플래그와 사전 미등재 단어 플래그처럼 원어를 조회할 토막이 있는 행에 생긴다. `examples/sample_loanword.srt`로 그런 행이 생기는지는 (미확인)
  - 1차 작성 때 관찰(재확인 안 함): `GET /api/loanword-source?source=Ruth` → `candidates` 24건, `confirmed:true`.

### 반영 판정 기록
- 사용자 경로: `선택 반영하기 (제안 채택 + 자동 교정 되돌리기)` 클릭이 자동으로 판정을 서버에 보낸다. 사용자가 따로 누르는 버튼은 없고 화면에 표시되지도 않는다.
- 선택자: `#applyBtn`
- 파일: `static/index.html`, `subtitle_corrector/api.py::record_feedback`, `subtitle_corrector/feedback.py::record_decisions`
- 검증:
  - 채택 또는 자동 교정 되돌리기를 하나 이상 체크하고 `#applyBtn`을 누르면(제안이 있는 확인 항목이 있을 때) `POST /api/feedback`이 한 번 나간다. 아무것도 체크하지 않고 누르면 요청이 나가지 않는다. `'…'로 반영` 버튼을 눌러도 같은 요청이 나간다.
  - 응답은 200이다. 기능이 꺼져 있으면 `{"enabled": false, "recorded": 0}` 이다.
  - 실패해도 화면에는 아무 오류가 뜨지 않는다.
  - 1차 작성 때 관찰(재확인 안 함): `GET /api/feedback/summary` → `{"enabled":true,"total":0,"accepted":0,"by_source":{}}`.

### 결과 저장과 공유 링크
- 사용자 경로: 교정 완료 후 결과 상단 `#shareBox`의 문구 확인. 저장에 성공하면 주소창이 `?id=…`로 바뀐다.
- 선택자: `#shareBox`
- 파일: `static/index.html`, `subtitle_corrector/api.py::correct_subtitle`, `subtitle_corrector/store.py::save_report`
- 검증:
  - 저장 성공이면 `#shareBox`에 `✅ 저장됨. 이 결과를 다시 보려면:` 와 `?id=` 가 든 주소가 나온다. (미확인)
  - 저장 실패이면 `⚠️ 결과 저장에 실패해 공유 링크를 만들지 못했습니다.`로 시작하는 문구가 나오고 교정 결과는 그대로 보인다.
  - 1차 작성 때 관찰(재확인 안 함): 그 환경에서는 Supabase 주소를 해석하지 못해 응답의 `id`가 늘 `null`이었다. 성공 경로는 실행된 적이 없다.

### 저장된 결과 다시 열기
- 사용자 경로: 주소창에 `?id=<저장 id>`를 직접 입력해 접속
- 선택자: `#status`, `#shareBox`
- 파일: `static/index.html`, `subtitle_corrector/api.py::get_report`, `subtitle_corrector/store.py::get_report`
- 검증:
  - 없는 id(예: uuid 형식이 아닌 값)로 접속하면 `#status`에 `오류: 저장된 결과를 찾을 수 없습니다.`가 뜬다.
  - 존재하는 id면 `#status`에 `불러옴 (id: …)`이 뜨고 결과 영역이 채워진다. 이 성공 경로는 (미확인)
  - 1차 작성 때 관찰(재확인 안 함): `GET /api/reports/{id}`의 오류 경로만 호출해 404/502를 받았다.

### 결과 내려받기 — 자막·텍스트·마크다운·검토표
- 사용자 경로: 결과 화면 `내려받기 형식` 드롭다운에서 형식 선택 → `교정 결과 내려받기`
- 선택자: `#downloadFormat`, `#downloadBtn`, `#downloadNote`, `교정 결과 내려받기`
- 파일: `static/index.html`
- 검증:
  - 형식을 고르고 버튼을 누르면 `#downloadNote`에 `파일 이름: <원본 이름>_교정본.<확장자>`가 뜬다.
  - `검토 표 (.csv, 엑셀에서 열림)`이면 이름 끝이 `_검토표.csv`다.
  - 타임코드가 없는 입력(붙여넣기·`.txt`)에서 `srt`·`vtt`·`smi`를 고르면 `#downloadNote`에 `이 파일에는 타임코드가 없어 자막 형식으로 바꿀 수 없습니다. 텍스트로 내려받습니다.`가 뜬다.
  - 실제 파일이 저장되는 단계는 브라우저 UI라 수동이다. (미확인)

### 결과 내려받기 — 워드 문서(.docx)
- 사용자 경로: `내려받기 형식`에서 `문서 · 워드 (.docx)` 선택 → `교정 결과 내려받기`
- 선택자: `#downloadFormat`, `#downloadBtn`, `#downloadNote`, `문서 · 워드 (.docx)`
- 파일: `static/index.html`, `subtitle_corrector/api.py::export_docx`
- 검증:
  - 잠시 `#downloadNote`에 `워드 문서를 만드는 중...`이 뜬 뒤 `파일 이름: <이름>.docx`로 바뀐다.
  - 서버가 실패하면 `워드 문서를 만들지 못했습니다 (서버 오류 <코드>)`가 뜬다. (미확인)
  - 1차 작성 때 관찰(재확인 안 함): `POST /api/export/docx`에 `text=hello world&filename=test` → HTTP 200, `content-type`이 `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.

### 교정 완료 알림
- 사용자 경로: `교정하기` 클릭 때 알림 권한 요청 → 완료·실패 시 데스크톱 알림. 탭이 숨겨져 있으면 탭 제목도 바뀐다.
- 선택자: 없음 (브라우저 알림과 탭 제목이라 화면 요소가 아니다)
- 파일: `static/index.html`
- 검증:
  - 교정 중 다른 탭으로 이동했다가 완료되면 탭 제목이 `✅ 교정 완료 — 한국어 띄어쓰기·맞춤법 교정`이 된다.
  - 그 탭으로 돌아오면 원래 제목으로 돌아온다.
  - 권한 창과 데스크톱 알림은 수동이다. (미확인)

### 교정 중 진행 표시
- 사용자 경로: `교정하기` 클릭 후 `3단계 · 실행` 아래 상태 영역
- 선택자: `#status`, `.spinner`, `교정 중입니다`
- 파일: `static/index.html`
- 검증:
  - 교정 중 `#status`에 스피너와 `교정 중입니다 · N초 경과`가 나오고 매초 올라간다. 1분이 넘으면 `M분 S초 경과`로 표시된다. 끝나면 `완료! (N초 경과)` 또는 `완료! (M분 S초 경과)`로 바뀐다.
  - 그동안 `#submitBtn`은 비활성이다.
  - 끝나면 `완료! (N초 경과)`로 바뀐다. (미확인)

## 사용자가 닿을 수 없는 것

- `POST /api/speakers`: 화면 어디서도 부르지 않는다. 예시 파일로 직접 호출하면 화자 목록 JSON을 준다.
  - 1차 작성 때 관찰(재확인 안 함): `examples/sample.srt`에 `{"speakers":[]}`.
- `main.py correct <파일>` CLI는 UI 밖이라 이 맵이 다루지 않는다.
- 첫 화면 상단 `이 교정기가 하는 일` 패널은 읽기 전용 설명이라 기능으로 다루지 않는다.
