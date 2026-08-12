<!-- lang-switcher:start -->
<p align="center">
  <a href="README.en.md">English</a>
  ·
  <a href="README.zh-CN.md">中文(简体)</a>
  ·
  <a href="README.zh-TW.md">中文(繁體)</a>
  ·
  <a href="README.ja.md">日本語</a>
  ·
  <a href="README.es.md">Español</a>
  ·
  <a href="README.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# 한국어 띄어쓰기·맞춤법 자동 교정 도구

> ### 📌 Main Quest 2 제출물 → **[`poc/mq2-spacing-retrieval/`](./poc/mq2-spacing-retrieval/)**
>
> **"한국어 띄어쓰기 교정에 AI를 넣으면 나아지는가"**
>
> 이 교정기는 규정·사전·판례를 이미 갖고 있다. 문제는 그 방대한 데이터 안에서
> **문맥과 의미에 상관없이 아무거나 골라와 띄거나 붙인다**는 것이다. 그 자리에 AI
> 검색(문장 임베딩·로컬 LLM)을 얹으면 나아지는지 실측했다.
>
> **결론: 얹지 않는다.** 임베딩과 LLM을 실제로 돌렸고 둘 다 신경망을 쓰지 않는 방법에
> 졌다. 이미 맞게 쓴 문장을 망가뜨린 것은 임베딩뿐이었다. 정답과 근거가 문서로 확정된
> 영역에서는 확률적 생성이 강점이 아니라 약점이며, 무엇보다 확률 모델은 **모를 때
> 기권할 줄 모른다.**
>
> 실험 2회 · 평가셋 76건 · 비교 대상 7종 · 실사용 오교정 사례집 50건 · 재현 절차 ·
> 실패 사례 · 한계와 다음 단계가 그 폴더에 있다 →
> [**PoC README**](./poc/mq2-spacing-retrieval/README.md)

자막(.srt)/일반 텍스트(.txt)/MS Word(.docx) 등 다양한 형식의 한국어 문서의 띄어쓰기·맞춤법을 자동 교정하는 도구. CLI와 웹 API(FastAPI) 두 가지 방식으로 쓸 수 있다.

국립국어원 어문 규범, 표준국어대사전, 우리말샘을 근거로 판단하며, 근거가 불확실한 항목은 자동 수정하지 않고 사용자에게 확인을 요청한다.

자세한 내용은 [PRD.md](./PRD.md) 참고.

## 상태

개발 완료(2026-08-11 기준 테스트 401건 전부 통과). CLI(`main.py`)와 웹 API(`subtitle_corrector/api.py`, FastAPI + `static/index.html`) 모두 구현되어 있고, Supabase 연동(교정 결과 저장/재조회)까지 확인됨.

**실행은 로컬에서 합니다(2026-08-02 결정).** 클라우드 배포는 하지 않습니다 — 형태소 분석기 kiwipiepy 모델이 약 310MB라 Render 무료 티어 512MB 안에서 교정 요청을 처리할 수 없습니다(`POST /api/correct`가 502). 자원 한계라 코드로 우회되지 않습니다. 배포 절차 자체는 [DEPLOY.md](./DEPLOY.md)에 남겨 두었고, 예전에 올려 둔 Render 주소가 아직 열리지만 **옛 버전이고 교정이 동작하지 않으니 사용하지 마세요.** 아래 "실행 방법"대로 로컬에서 띄우면 모든 기능이 동작합니다.

## 실행 방법 (Windows)

### 1. 준비

```powershell
git clone https://github.com/tigermorning/korean-subtitle-corrector.git
cd korean-subtitle-corrector
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

`.env`를 열어 아래 값을 채운다 (국립국어원 오픈 API 포털에서 무료 발급):

- `STDICT_API_KEY` / `OPENDICT_API_KEY` / `KORNORMS_API_KEY` — 표준국어대사전·우리말샘·국립국어원 어문규범 API 키. 없으면 서버는 켜지지만, 교정 기능을 실제로 호출할 때 오류가 난다.
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` — 교정 결과 저장용(선택). 없어도 교정 자체는 정상 동작하고, 저장만 실패로 표시된다.

아래 둘은 **선택 기능이고 기본은 꺼짐**이다. 값을 넣지 않으면 도구는 지금까지와 똑같이 동작한다.

- `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` — 언어 모델 패스. 규칙 교정이 **모두 끝난 뒤** 남은 텍스트를 모델에게 보여 주고 문맥 판단이 필요한 자리만 확인 항목으로 더 받는다. **본문은 바뀌지 않는다** — 모델에는 사전 같은 확정 근거가 없으므로 제안만 하고, 사람이 고른 것만 반영된다. 모델이 내놓은 제안도 규칙 교정과 똑같은 `edit_guard` 관문을 통과해야 목록에 오른다(근거를 밝히지 않은 변경·줄바꿈 개수를 바꾸는 변경은 버려진다). OpenAI 호환 주소라 로컬(Ollama·llama.cpp·vLLM)과 상용 API를 같은 설정으로 쓴다. 타임코드는 모델에게 보내지 않는다.
- `FEEDBACK_LOG_DIR` — 판정 기록장. 화면에서 '반영'을 누를 때마다 `(원문, 제안, 채택 여부)`를 그 폴더에 JSONL로 쌓는다. 나중에 이 작업에 맞춰 모델을 학습시킬 때 쓸 재료다. **켜기 전에 읽을 것**: 여기 쌓이는 것은 작업 중인 원고의 대사다. 원고 전문은 저장하지 않고 해시만 남기지만, 줄 단위 텍스트는 그것이 재료 자체이므로 그대로 남는다. 남의 저작물을 다루는 자리라면 켜지 않는 것이 기본이다. 쌓인 건수는 `GET /api/feedback/summary`로 본다.

### 2. 웹 서버로 실행 (추천 — 브라우저에서 바로 테스트 가능)

```powershell
.venv\Scripts\uvicorn subtitle_corrector.api:app --reload
```

브라우저에서 http://127.0.0.1:8000 접속 → 파일 업로드 → 교정 결과 확인.

### 3. CLI로 실행

```powershell
.venv\Scripts\python main.py correct examples\sample.srt
```

보조 용언 띄어쓰기 기준(한글 맞춤법 제47항)은 원칙(띄어 씀)이 기본값이고, 붙여 쓰는 허용 기준을 고를 수도 있습니다. 둘 다 맞는 표기지만 한 작품 안에서 섞이면 안 되므로, 고른 기준이 문서 전체에 적용됩니다.

```powershell
.venv\Scripts\python main.py correct examples\sample.srt --spacing allowance
```

## 테스트

```
pip install -r requirements-dev.txt
pytest
```

테스트가 실제 표준국어대사전/우리말샘 API를 실시간으로 조회하므로(정적으로 캡처해 둔 응답을 쓰지 않음), `.env`에 `STDICT_API_KEY`/`OPENDICT_API_KEY`가 설정되어 있어야 하고 네트워크가 필요하다. 실패하면 코드 회귀인지, 국립국어원 사전이 실제로 개정된 것인지부터 확인한다(PRD.md §5).
