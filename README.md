<!-- lang-switcher:start -->
<p align="center">
  한국어
  ·
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

자막(.srt)/일반 텍스트(.txt)/MS Word(.docx) 등 다양한 형식의 한국어 문서의 띄어쓰기·맞춤법을 자동 교정하는 도구. CLI와 웹 API(FastAPI) 두 가지 방식으로 쓸 수 있다.

국립국어원 어문 규범, 표준국어대사전, 우리말샘을 근거로 판단하며, 근거가 불확실한 항목은 자동 수정하지 않고 사용자에게 확인을 요청한다.

자세한 내용은 [PRD.md](./PRD.md) 참고.

## 상태

개발 완료. CLI(`main.py`)와 웹 API(`subtitle_corrector/api.py`, FastAPI + `static/index.html`) 모두 구현되어 있고, Supabase 연동(교정 결과 저장/재조회)까지 확인됨. 클라우드 배포는 [DEPLOY.md](./DEPLOY.md) 참고.

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

### 2. 웹 서버로 실행 (추천 — 브라우저에서 바로 테스트 가능)

```powershell
.venv\Scripts\uvicorn subtitle_corrector.api:app --reload
```

브라우저에서 http://127.0.0.1:8000 접속 → 파일 업로드 → 교정 결과 확인.

### 3. CLI로 실행

```powershell
.venv\Scripts\python main.py correct examples\sample.srt
```

## 테스트

```
pip install -r requirements-dev.txt
pytest
```

테스트가 실제 표준국어대사전/우리말샘 API를 실시간으로 조회하므로(정적으로 캡처해 둔 응답을 쓰지 않음), `.env`에 `STDICT_API_KEY`/`OPENDICT_API_KEY`가 설정되어 있어야 하고 네트워크가 필요하다. 실패하면 코드 회귀인지, 국립국어원 사전이 실제로 개정된 것인지부터 확인한다(PRD.md §5).
